import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("release_feed", Path(__file__).with_name("sync_release_feed.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
DIGEST = "a" * 64


def feed(version="0.15.1", build=20, digest=DIGEST, name="Transkript.dmg"):
    return {"version": version, "build": build, "sha256": digest, "notes": "Notes",
            "url": f"https://github.com/{module.REPOSITORY}/releases/download/v{version}/{name}"}


def release(version="0.15.1", identifier=20, assets=()):
    return {"tag_name": "v" + version, "id": identifier, "draft": False,
            "prerelease": False, "assets": [{"name": name} for name in assets]}


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.info = {"CFBundleIdentifier": module.BUNDLE_ID,
                     "CFBundleShortVersionString": "0.15.1", "CFBundleVersion": "20"}

    def test_legacy_parser_compatible_feed(self):
        result = module.manifest(self.info, "v0.15.1", "Transkript.dmg", DIGEST, " Notes \n")
        self.assertEqual(result["build"], 20)
        self.assertEqual(result["version"], "0.15.1")
        self.assertEqual(result["notes"], "Notes")
        self.assertEqual(result["url"], "https://github.com/lucaszrezende/legendas-video-local/releases/download/v0.15.1/Transkript.dmg")

    def test_rejects_wrong_app_version_or_build(self):
        for key, value in [("CFBundleIdentifier", "other.app"),
                           ("CFBundleShortVersionString", "0.13.0"),
                           ("CFBundleVersion", "0"), ("CFBundleVersion", "20.0")]:
            info = dict(self.info, **{key: value})
            with self.assertRaises(ValueError):
                module.manifest(info, "v0.15.1", "Transkript.dmg", DIGEST, "")

    def test_rejects_unexpected_download_name(self):
        with self.assertRaises(ValueError):
            module.manifest(self.info, "v0.15.1", "another.dmg", DIGEST, "")

    def test_preserves_old_download_name(self):
        result = module.manifest(self.info, "v0.15.1", "WhisperPRO.dmg", DIGEST, "")
        self.assertTrue(result["url"].endswith("/WhisperPRO.dmg"))

    def test_reference_contract_rejects_foreign_url_tag_digest_and_bool_build(self):
        for changes in [{"url": "https://evil.invalid/Transkript.dmg"},
                        {"url": feed()["url"].replace(module.REPOSITORY, "other/repo")},
                        {"url": feed()["url"] + "?redirect=elsewhere"},
                        {"url": feed()["url"].replace("v0.15.1", "v0.14.0")},
                        {"sha256": "abc"}, {"build": True}, {"version": "0.015.1"}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                module.validate_feed(dict(feed(), **changes))


class MonotonicTests(unittest.TestCase):
    def setUp(self):
        self.reference = {"feed": feed("0.15.0", 19), "sha": "git-file-sha",
                          "source": "mirror", "latest": release("0.15.0", 19)}

    def validate(self, candidate):
        with patch.object(module, "publication_reference", return_value=self.reference):
            return module.validate_candidate_against_publication(candidate)

    def test_new_version_and_build_must_both_increase(self):
        self.assertEqual(self.validate(feed()), self.reference)
        for candidate in [feed("0.14.9", 20), feed("0.15.0", 20),
                          feed("0.15.1", 19), feed("0.16.0", 18)]:
            with self.subTest(candidate=candidate), self.assertRaises(module.PublicationError):
                self.validate(candidate)

    def test_equal_publication_requires_same_version_build_and_digest(self):
        self.assertEqual(self.validate(feed("0.15.0", 19)), self.reference)
        with self.assertRaises(module.PublicationError):
            self.validate(feed("0.15.0", 19, "b" * 64))

    def test_manual_latest_downgrade_is_rejected_against_mirror(self):
        self.reference["latest"] = release("0.14.0", 18)
        with self.assertRaises(module.PublicationError):
            self.validate(feed("0.14.0", 18))

    def test_candidate_cannot_replace_a_newer_latest_even_before_its_feed_exists(self):
        self.reference["latest"] = release("0.16.0", 21)
        with self.assertRaises(module.PublicationError):
            self.validate(feed())

    def test_bootstrap_uses_known_legacy_build_without_inventing_newer_builds(self):
        old = release("0.13.0", 17, ["WhisperPRO.dmg"])
        with patch.object(module, "repository_manifest", return_value=None), \
                patch.object(module, "gh_json", side_effect=[old, [old]]):
            reference = module.publication_reference()
        self.assertEqual(reference["feed"], {"version": "0.13.0", "build": 17})
        self.reference = reference
        self.validate(feed())
        self.validate(feed("0.13.0", 17, name="WhisperPRO.dmg"))
        with self.assertRaises(module.PublicationError):
            self.validate(feed("0.14.0", 16))


class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.dmg = self.directory / "Transkript.dmg"
        self.dmg.write_bytes(b"validated DMG bytes")
        self.feed = feed(digest=module.digest(self.dmg))
        self.release = release(assets=["Transkript.dmg"])

    def downloaded(self, contents):
        def download(tag, name, directory):
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / name
            value = contents[name]
            target.write_bytes(value.encode() if isinstance(value, str) else value)
            return target
        return download

    def test_missing_compatibility_name_and_checksums_are_created_without_remote_writes(self):
        with patch.object(module.subprocess, "run") as run:
            body, pending = module.prepare_release_assets(self.release, self.directory, self.dmg, self.feed)
        run.assert_not_called()
        self.assertEqual({path.name for path in pending}, {"WhisperPRO.dmg", "SHA256SUMS.txt", "version.json"})
        self.assertEqual((self.directory / "WhisperPRO.dmg").read_bytes(), self.dmg.read_bytes())
        self.assertEqual((self.directory / "SHA256SUMS.txt").read_text(),
                         "".join(f"{self.feed['sha256']}  {name}\n" for name in module.INSTALLERS))
        self.assertEqual(json.loads(body), self.feed)

    def test_existing_compatibility_installer_must_match(self):
        self.release["assets"].append({"name": "WhisperPRO.dmg"})
        with patch.object(module, "download_asset", side_effect=self.downloaded({"WhisperPRO.dmg": b"old build"})), \
                self.assertRaises(ValueError):
            module.prepare_release_assets(self.release, self.directory, self.dmg, self.feed)

    def test_existing_checksums_and_feed_are_checked_and_preserved(self):
        self.release["assets"] += [{"name": name} for name in ["WhisperPRO.dmg", "SHA256SUMS.txt", "version.json"]]
        body = json.dumps(dict(self.feed, notes="Existing release notes"))
        contents = {"WhisperPRO.dmg": self.dmg.read_bytes(), "version.json": body,
                    "SHA256SUMS.txt": "".join(f"{self.feed['sha256']}  {name}\n" for name in module.INSTALLERS)}
        with patch.object(module, "download_asset", side_effect=self.downloaded(contents)):
            result, pending = module.prepare_release_assets(self.release, self.directory, self.dmg, self.feed)
        self.assertEqual(result, body)
        self.assertEqual(pending, [])

    def test_mismatched_checksums_are_not_replaced(self):
        self.release["assets"].append({"name": "SHA256SUMS.txt"})
        contents = {"SHA256SUMS.txt": f"{'b' * 64}  Transkript.dmg\n{'b' * 64}  WhisperPRO.dmg\n"}
        with patch.object(module, "download_asset", side_effect=self.downloaded(contents)), \
                self.assertRaises(ValueError):
            module.prepare_release_assets(self.release, self.directory, self.dmg, self.feed)

    def test_github_asset_digest_is_checked(self):
        self.release["assets"][0]["digest"] = "sha256:" + "b" * 64
        with self.assertRaises(ValueError):
            module.prepare_release_assets(self.release, self.directory, self.dmg, self.feed)

    def test_legacy_baseline_keeps_its_original_installer_name(self):
        old_dmg = self.directory / "WhisperPRO.dmg"
        old_dmg.write_bytes(self.dmg.read_bytes())
        old_feed = feed("0.13.0", 17, self.feed["sha256"], "WhisperPRO.dmg")
        _, pending = module.prepare_release_assets(release("0.13.0", 17, ["WhisperPRO.dmg"]),
                                                  self.directory, old_dmg, old_feed)
        self.assertEqual({path.name for path in pending}, {"SHA256SUMS.txt", "version.json"})


class PublicationStateTests(unittest.TestCase):
    def test_draft_and_prerelease_never_download_or_publish(self):
        for flag in ["draft", "prerelease"]:
            candidate = release(assets=["Transkript.dmg"])
            candidate[flag] = True
            with patch.object(sys, "argv", ["sync_release_feed.py", "v0.15.1"]), \
                    patch.object(module, "gh_json", return_value=candidate), \
                    patch.object(module.subprocess, "run") as run, self.assertRaises(ValueError):
                module.main()
            run.assert_not_called()

    def test_modern_release_cannot_use_only_legacy_name(self):
        candidate = release(assets=["WhisperPRO.dmg"])
        with patch.object(sys, "argv", ["sync_release_feed.py", "v0.15.1"]), \
                patch.object(module, "gh_json", return_value=candidate), \
                patch.object(module.subprocess, "run") as run, self.assertRaises(ValueError):
            module.main()
        run.assert_not_called()

    def test_local_dmg_preflight_rejects_downgrade_before_output_is_written(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "version.json"
            info = {"CFBundleIdentifier": module.BUNDLE_ID, "CFBundleShortVersionString": "0.15.1", "CFBundleVersion": "20"}
            with patch.object(sys, "argv", ["sync_release_feed.py", "v0.15.1", "--dmg", "file.dmg", "--output", str(output)]), \
                    patch.object(module, "inspect_dmg", return_value=info), \
                    patch.object(module, "digest", return_value=DIGEST), \
                    patch.object(module, "validate_candidate_against_publication", side_effect=ValueError("downgrade")), \
                    self.assertRaises(ValueError):
                module.main()
            self.assertFalse(output.exists())

    def test_rejected_remote_release_does_not_upload_feed_or_alias(self):
        candidate = release(assets=["Transkript.dmg"])
        error = module.PublicationError("downgrade", {})
        info = {"CFBundleIdentifier": module.BUNDLE_ID, "CFBundleShortVersionString": "0.15.1", "CFBundleVersion": "20"}
        with patch.object(sys, "argv", ["sync_release_feed.py", "v0.15.1"]), \
                patch.object(module, "gh_json", return_value=candidate), \
                patch.object(module, "inspect_dmg", return_value=info), \
                patch.object(module, "digest", return_value=DIGEST), \
                patch.object(module, "validate_candidate_against_publication", side_effect=error), \
                patch.object(module, "restore_previous_latest") as restore, \
                patch.object(module.subprocess, "run") as run, self.assertRaises(module.PublicationError):
            module.main()
        restore.assert_called_once_with(error, candidate)
        self.assertFalse(any("upload" in call.args[0] for call in run.call_args_list))

    def test_rollback_checks_reference_manifest_and_confirms_latest(self):
        rejected = release("0.14.0", 18)
        previous = release("0.15.1", 20, ["Transkript.dmg", "version.json"])
        reference = {"feed": feed(), "source": "mirror"}
        with patch.object(module, "gh_json", side_effect=[rejected, previous, previous]), \
                patch.object(module, "release_manifest", return_value=feed()), \
                patch.object(module.subprocess, "run") as run:
            module.restore_previous_latest(module.PublicationError("downgrade", reference), rejected)
        run.assert_called_once_with(["gh", "release", "edit", "v0.15.1", "--repo", module.REPOSITORY, "--latest"], check=True)

    def test_rollback_refuses_a_reference_manifest_with_wrong_digest(self):
        rejected = release("0.14.0", 18)
        reference = {"feed": feed(), "source": "mirror"}
        with patch.object(module, "gh_json", side_effect=[rejected, release()]), \
                patch.object(module, "release_manifest", return_value=feed(digest="b" * 64)), \
                patch.object(module.subprocess, "run") as run, self.assertRaises(ValueError):
            module.restore_previous_latest(module.PublicationError("downgrade", reference), rejected)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
