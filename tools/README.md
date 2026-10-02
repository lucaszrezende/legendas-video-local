# Ferramentas de distribuição

A ação **Update feed** roda quando uma release estável é publicada. Ela verifica o DMG sem executar o aplicativo, confere a identidade, a versão, o build e a assinatura, gera `version.json` e mantém o nome de download `WhisperPRO.dmg` para instalações antigas.

Para cada lançamento, publique `Transkript.dmg` com uma versão e um build maiores que os anteriores. O feed usa os dados do instalador; não edite números manualmente. Releases de prévia não entram no feed. Versões menores são recusadas. Os arquivos de áudio, transcrições e código-fonte do aplicativo não são enviados por esta ação.

O publicador local prepara instalador, compatibilidade, manifesto e SHA-256 como rascunho antes de tornar a release pública. Se publicar manualmente pelo GitHub, aguarde a ação terminar com sucesso. Para repetir uma validação, execute **Run workflow** e informe a tag da release.

Verificações locais das ferramentas: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p 'test_release_feed.py'`.
