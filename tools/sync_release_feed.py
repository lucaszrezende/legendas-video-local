#!/usr/bin/env python3
"""Generate and publish an update feed from a released DMG, without running it."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import tempfile
from urllib.parse import urlsplit

REPOSITORY = "lucaszrezende/legendas-video-local"
BUNDLE_ID = "com.lure.whisperpro.cld"
LEGACY_VERSION = "0.13.0"
LEGACY_BUILD = 17
INSTALLERS = ("Transkript.dmg", "WhisperPRO.dmg")
MAX_FEED_BYTES = 64 * 1024


class PublicationError(ValueError):
    def __init__(self, message, reference):
        super().__init__(message)
        self.reference = reference


def command(*args):
    return subprocess.check_output(args, text=True)


def gh_json(*args):
    return json.loads(command("gh", "api", *args))


def semantic_version(version):
    if not isinstance(version, str) or not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version):
        raise ValueError("Versão semântica inválida.")
    return tuple(map(int, version.split(".")))


def validate_feed(feed, tag=None):
    if not isinstance(feed, dict):
        raise ValueError("Manifesto precisa ser um objeto JSON.")
    if feed.get("notes") is not None and not isinstance(feed["notes"], str):
        raise ValueError("Notas do manifesto precisam ser texto ou null.")
    semantic_version(feed.get("version"))
    if type(feed.get("build")) is not int or feed["build"] < 1:
        raise ValueError("Build do manifesto inválido.")
    if not isinstance(feed.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", feed["sha256"]):
        raise ValueError("SHA-256 do manifesto inválido.")
    expected_tag = "v" + feed["version"]
    if tag is not None and tag != expected_tag:
        raise ValueError("Tag e manifesto divergem.")
    url = urlsplit(feed.get("url", ""))
    prefix = f"/{REPOSITORY}/releases/download/{expected_tag}/"
    if (url.scheme != "https" or url.netloc != "github.com" or url.query or url.fragment
            or url.path not in [prefix + name for name in INSTALLERS]):
        raise ValueError("URL do manifesto não pertence à release esperada.")
    if len((json.dumps(feed, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")) > MAX_FEED_BYTES:
        raise ValueError("Manifesto excede o limite de 64 KiB do aplicativo.")
    return feed


def parse_feed(body, tag=None):
    raw = body.encode("utf-8") if isinstance(body, str) else body
    if len(raw) > MAX_FEED_BYTES:
        raise ValueError("Corpo do manifesto excede o limite de 64 KiB do aplicativo.")
    return validate_feed(json.loads(raw.decode("utf-8")), tag)


def download_asset(tag, name, directory):
    directory.mkdir(parents=True, exist_ok=True)
    subprocess.run(["gh", "release", "download", tag, "--repo", REPOSITORY,
                    "--pattern", name, "--dir", str(directory)], check=True)
    return directory / name


def repository_manifest():
    response = subprocess.run(["gh", "api", f"repos/{REPOSITORY}/contents/version.json"],
                              text=True, capture_output=True)
    if response.returncode:
        if "404" in response.stderr:
            return None
        raise RuntimeError("Não foi possível verificar o feed anterior.")
    entry = json.loads(response.stdout)
    body = base64.b64decode(entry["content"]).decode()
    return parse_feed(body), entry["sha"]


def release_manifest(release):
    if release["draft"] or release["prerelease"]:
        raise ValueError("A referência precisa ser uma release estável publicada.")
    assets = {asset["name"]: asset for asset in release["assets"]}
    if "version.json" not in assets:
        raise ValueError("A release de referência não contém manifesto.")
    with tempfile.TemporaryDirectory(prefix="transkript-reference-") as directory:
        path = download_asset(release["tag_name"], "version.json", Path(directory))
        feed = parse_feed(path.read_bytes(), release["tag_name"])
    name = urlsplit(feed["url"]).path.rsplit("/", 1)[1]
    if name not in assets:
        raise ValueError("O instalador do manifesto anterior está ausente.")
    check_asset_digest(assets[name], feed["sha256"])
    return feed


def check_asset_digest(asset, expected):
    if asset.get("digest") is not None and asset["digest"] != "sha256:" + expected:
        raise ValueError("SHA-256 publicado pelo GitHub diverge do instalador.")


def publication_reference():
    mirror = repository_manifest()
    latest = gh_json(f"repos/{REPOSITORY}/releases/latest")
    if mirror:
        return {"feed": mirror[0], "sha": mirror[1], "source": "mirror", "latest": latest}
    if any(asset["name"] == "version.json" for asset in latest["assets"]):
        return {"feed": release_manifest(latest), "sha": None, "source": "release", "latest": latest}
    # Bootstrap an existing distribution without inventing a build number for
    # newer tags. Look for the last verified manifest, then the known baseline.
    releases = gh_json(f"repos/{REPOSITORY}/releases?per_page=100")
    stable = [release for release in releases if not release["draft"] and not release["prerelease"]]
    stable.sort(key=lambda release: semantic_version(release["tag_name"].removeprefix("v")), reverse=True)
    for release in stable:
        if any(asset["name"] == "version.json" for asset in release["assets"]):
            return {"feed": release_manifest(release), "sha": None, "source": "release", "latest": latest}
    if any(release["tag_name"] == "v" + LEGACY_VERSION
           and any(asset["name"] == "WhisperPRO.dmg" for asset in release["assets"]) for release in stable):
        return {"feed": {"version": LEGACY_VERSION, "build": LEGACY_BUILD},
                "sha": None, "source": "baseline", "latest": latest}
    raise ValueError("Distribuição sem manifesto anterior ou baseline verificada.")


def validate_candidate_against_publication(feed):
    """Read-only preflight shared by the local publisher and release workflow."""
    validate_feed(feed)
    reference = publication_reference()
    previous = reference["feed"]
    latest_version = semantic_version(reference["latest"]["tag_name"].removeprefix("v"))
    candidate_version = semantic_version(feed["version"])
    if candidate_version < latest_version:
        raise PublicationError("Recusada versão inferior à release latest.", reference)
    same = (feed["version"] == previous["version"] and feed["build"] == previous["build"]
            and feed["sha256"] == previous.get("sha256"))
    baseline_bootstrap = (reference["source"] == "baseline" and feed["version"] == LEGACY_VERSION
                          and feed["build"] == LEGACY_BUILD)
    if same or baseline_bootstrap:
        return reference
    if candidate_version <= semantic_version(previous["version"]) or feed["build"] <= previous["build"]:
        raise PublicationError("Versão e build devem superar a publicação anterior.", reference)
    return reference


def restore_previous_latest(error, rejected):
    reference = error.reference
    if reference["source"] == "baseline":
        return
    current = gh_json(f"repos/{REPOSITORY}/releases/latest")
    if current["id"] != rejected["id"]:
        return
    previous = reference["feed"]
    tag = "v" + previous["version"]
    if tag == rejected["tag_name"]:
        return
    release = gh_json(f"repos/{REPOSITORY}/releases/tags/{tag}")
    verified = release_manifest(release)
    if any(verified[key] != previous[key] for key in ("version", "build", "url", "sha256")):
        raise ValueError("Referência anterior divergente: latest não alterada.")
    subprocess.run(["gh", "release", "edit", tag, "--repo", REPOSITORY, "--latest"], check=True)
    if gh_json(f"repos/{REPOSITORY}/releases/latest")["id"] != release["id"]:
        raise RuntimeError("Não foi possível confirmar a restauração de latest.")
    print(f"Latest restaurada para {tag}; publicação incompatível recusada.")


def prepare_release_assets(release, directory, dmg, feed):
    """Validate existing assets before returning the missing files to upload."""
    tag = release["tag_name"]
    assets = {asset["name"]: asset for asset in release["assets"]}
    primary_name = dmg.name
    check_asset_digest(assets[primary_name], feed["sha256"])
    names = ["WhisperPRO.dmg"] if feed["version"] == LEGACY_VERSION and primary_name == "WhisperPRO.dmg" else list(INSTALLERS)
    pending = []
    for name in names:
        if name == primary_name:
            continue
        if name in assets:
            existing = download_asset(tag, name, directory / "compatibility")
            if digest(existing) != feed["sha256"]:
                raise ValueError("Os dois nomes do instalador têm conteúdos diferentes.")
            check_asset_digest(assets[name], feed["sha256"])
        else:
            alias = directory / name
            shutil.copyfile(dmg, alias)
            pending.append(alias)
    checksum_file = directory / "SHA256SUMS.txt"
    checksums = {name: feed["sha256"] for name in names}
    if "SHA256SUMS.txt" in assets:
        existing = download_asset(tag, "SHA256SUMS.txt", directory / "checksums")
        actual = {}
        for line in existing.read_text().splitlines():
            match = re.fullmatch(r"([0-9a-f]{64}) [ *](Transkript\.dmg|WhisperPRO\.dmg)", line)
            if not match or match[2] in actual:
                raise ValueError("Arquivo SHA256SUMS inválido.")
            actual[match[2]] = match[1]
        if actual != checksums:
            raise ValueError("SHA256SUMS diverge dos instaladores.")
    else:
        checksum_file.write_text("".join(f"{checksums[name]}  {name}\n" for name in names))
        pending.append(checksum_file)
    body = json.dumps(feed, ensure_ascii=False, indent=2) + "\n"
    if "version.json" in assets:
        existing = download_asset(tag, "version.json", directory / "existing")
        existing_feed = parse_feed(existing.read_bytes(), tag)
        for key in ("version", "build", "url", "sha256"):
            if existing_feed[key] != feed[key]:
                raise ValueError(f"Manifesto publicado diverge do DMG: {key}")
        body = existing.read_text()
    else:
        output = directory / "version.json"
        output.write_text(body)
        pending.append(output)
    return body, pending


def manifest(info, tag, asset_name, digest, notes):
    version = info.get("CFBundleShortVersionString", "")
    build = info.get("CFBundleVersion", "")
    if info.get("CFBundleIdentifier") != BUNDLE_ID:
        raise ValueError("O DMG não contém o aplicativo Transkript esperado.")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) or tag != "v" + version:
        raise ValueError("Tag e versão do aplicativo divergem.")
    if not str(build).isdigit() or int(build) < 1:
        raise ValueError("Build do aplicativo inválido.")
    if asset_name not in ("Transkript.dmg", "WhisperPRO.dmg"):
        raise ValueError("Nome de instalador inesperado.")
    return validate_feed({"version": version, "build": int(build),
                         "url": f"https://github.com/{REPOSITORY}/releases/download/{tag}/{asset_name}",
                         "notes": notes.strip()[:2000], "sha256": digest}, tag)


def inspect_dmg(path):
    attached = plistlib.loads(subprocess.check_output(
        ["hdiutil", "attach", "-readonly", "-nobrowse", "-plist", str(path)]))
    mounts = [Path(e["mount-point"]) for e in attached["system-entities"] if "mount-point" in e]
    try:
        infos = []
        for mount in mounts:
            for app in mount.glob("*.app"):
                info_path = app / "Contents/Info.plist"
                if info_path.exists():
                    info = plistlib.loads(info_path.read_bytes())
                    if info.get("CFBundleIdentifier") == BUNDLE_ID:
                        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
                        infos.append(info)
        if len(infos) != 1:
            raise ValueError("Esperado exatamente um aplicativo compatível no DMG.")
        return infos[0]
    finally:
        for mount in mounts:
            subprocess.run(["hdiutil", "detach", str(mount), "-quiet"], check=True)


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    parser.add_argument("--dmg", type=Path, help="Validar um DMG local, sem publicar")
    parser.add_argument("--notes", default="")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.dmg:
        feed = manifest(inspect_dmg(args.dmg), args.tag, "Transkript.dmg", digest(args.dmg), args.notes)
        validate_candidate_against_publication(feed)
        body = json.dumps(feed, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.write_text(body)
        print(body)
        return

    if os.environ.get("GITHUB_REPOSITORY", REPOSITORY) != REPOSITORY:
        raise ValueError("Repositório de distribuição inesperado.")
    release = gh_json(f"repos/{REPOSITORY}/releases/tags/{args.tag}")
    if release["draft"] or release["prerelease"]:
        raise ValueError("O feed só aceita releases estáveis publicadas.")
    assets = {asset["name"]: asset for asset in release["assets"]}
    name = "Transkript.dmg" if "Transkript.dmg" in assets else (
        "WhisperPRO.dmg" if args.tag == "v" + LEGACY_VERSION and "WhisperPRO.dmg" in assets else None)
    if not name:
        raise ValueError("Publicação sem instalador: feed não alterado.")
    with tempfile.TemporaryDirectory(prefix="transkript-release-") as directory:
        directory = Path(directory)
        subprocess.run(["gh", "release", "download", args.tag, "--repo", REPOSITORY,
                        "--pattern", name, "--dir", str(directory)], check=True)
        dmg = directory / name
        feed = manifest(inspect_dmg(dmg), args.tag, name, digest(dmg), release.get("body") or "")
        try:
            validate_candidate_against_publication(feed)
        except PublicationError as error:
            restore_previous_latest(error, release)
            raise
        body, pending = prepare_release_assets(release, directory, dmg, feed)
        if pending:
            subprocess.run(["gh", "release", "upload", args.tag, *(str(path) for path in pending),
                            "--repo", REPOSITORY], check=True)

        latest = gh_json(f"repos/{REPOSITORY}/releases/latest")
        if latest["id"] != release["id"]:
            print("Release validada; não é latest, portanto feed principal preservado.")
            return
        # Keep a small, public mirror for diagnostics. Never downgrade a build.
        reference = validate_candidate_against_publication(feed)
        payload = {"message": f"Update Transkript feed to {args.tag}",
                   "content": base64.b64encode(body.encode()).decode(), "branch": "main"}
        if reference["sha"] is not None:
            if reference["feed"] == json.loads(body):
                print("Feed publicado e verificado; já está atualizado.")
                return
            payload["sha"] = reference["sha"]
        request = directory / "request.json"
        request.write_text(json.dumps(payload))
        command("gh", "api", "--method", "PUT", f"repos/{REPOSITORY}/contents/version.json", "--input", str(request))
        print(f"Feed publicado: {feed['version']} (build {feed['build']}).")


if __name__ == "__main__":
    main()
