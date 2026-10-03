# Ferramentas de distribuição

A ação **Update feed** roda quando uma release estável é publicada. Ela verifica o DMG sem executar o aplicativo, confere a identidade, a versão, o build e a assinatura, gera `version.json` e mantém o nome de download `WhisperPRO.dmg` para instalações antigas.

Para cada lançamento, publique `Transkript.dmg` com uma versão e um build maiores que os anteriores. O feed usa os dados do instalador; não edite números manualmente. Releases de prévia não entram no feed. Versões menores são recusadas. Os arquivos de áudio, transcrições e código-fonte do aplicativo não são enviados por esta ação.

O publicador local prepara instalador, compatibilidade, manifesto e SHA-256 como rascunho antes de tornar a release pública. Se publicar manualmente pelo GitHub, aguarde a ação terminar com sucesso. Para repetir uma validação, execute **Run workflow** e informe a tag da release.

## Espelhamento opcional do instalador

Para evitar enviar duas vezes o mesmo instalador pelo Mac, a ação **Mirror compatible installer** pode criar `WhisperPRO.dmg` no GitHub a partir de `Transkript.dmg`. Ela trabalha somente em uma release estável ainda em rascunho e não a publica.

1. Valide o instalador localmente no Mac, incluindo versão, build e assinatura. Prepare o rascunho e conclua o envio de `Transkript.dmg`, `version.json` e `SHA256SUMS.txt`. O manifesto deve conter o SHA-256 validado; os checksums devem declarar esse mesmo hash para os dois nomes do instalador.
2. Se um envio falhar, confirme que a tentativa encerrou. Remova apenas o asset incompleto da sua própria tentativa no rascunho, identificado como `starter` e sem digest. Preserve assets completos e não remova arquivos enquanto ainda houver um upload em andamento. A ação recusa qualquer asset incompleto e não faz essa limpeza automaticamente.
3. Em **Actions → Mirror compatible installer → Run workflow**, selecione `main`, informe a `tag` do rascunho, como `v0.15.4`, e o `expected_sha256` do instalador validado localmente: 64 caracteres hexadecimais minúsculos. Durante a execução, mantenha outros uploads e edições desse rascunho parados.
4. Aguarde o workflow terminar com sucesso. Confira que `Transkript.dmg` e `WhisperPRO.dmg` aparecem com estado `uploaded`, o mesmo tamanho e o digest `sha256:` seguido do hash esperado. Um alias completo já existente com esses valores é preservado; um alias divergente interrompe a ação.
5. Só então publique a release. A ação **Update feed** continua verificando o conteúdo do DMG no macOS e preparando o feed; aguarde também seu resultado com sucesso.

O espelhamento confere os bytes, o manifesto e os checksums. A inspeção do aplicativo dentro do DMG permanece na validação local e na ação **Update feed**. Áudios, transcrições e código-fonte do aplicativo não são enviados.

## Envio opcional em partes

Quando a conexão local não conclui o envio de um DMG inteiro, **Assemble verified installer** recompõe `Transkript.dmg` no GitHub a partir de partes verificadas. O workflow aceita somente um rascunho estável e mantém a release sem publicar.

1. Valide o DMG no Mac e calcule seu SHA-256. Divida os bytes em partes sequenciais de **2 MiB**, deixando somente a última parte menor. Use os nomes `transkript-upload-v0.15.4-part-000.bin`, `transkript-upload-v0.15.4-part-001.bin` e assim por diante, substituindo `v0.15.4` pela tag escolhida.
2. Prepare `transkript-upload-v0.15.4-manifest.json` com este formato. `parts` deve listar todas as partes na ordem exata, com o tamanho e o SHA-256 de cada uma; `size` e `sha256` identificam o DMG original. São permitidas até 900 partes e um manifesto de até 256 KiB.

   ```json
   {
     "version": 1,
     "tag": "v0.15.4",
     "filename": "Transkript.dmg",
     "size": 501025636,
     "sha256": "<SHA-256 do DMG original>",
     "parts": [
       {"name": "transkript-upload-v0.15.4-part-000.bin", "size": 2097152, "sha256": "<SHA-256 da parte>"}
     ]
   }
   ```

3. Envie todas as partes, o manifesto de transporte, `version.json` e `SHA256SUMS.txt` ao mesmo rascunho. Aguarde os uploads terminarem e inspecione eventuais assets `starter`; a ação recusa qualquer arquivo incompleto. Mantenha uploads e edições do rascunho parados durante a execução.
4. Em **Actions → Assemble verified installer → Run workflow**, selecione `main` e informe `tag`, `manifest_asset` e `expected_sha256`. Para este exemplo, são `v0.15.4`, `transkript-upload-v0.15.4-manifest.json` e o SHA-256 original do DMG. A ação baixa quatro partes em paralelo, verifica cada digest remoto e local, recompõe na ordem do manifesto e compara os bytes totais com o tamanho e o hash originais antes de criar `Transkript.dmg`.
5. Aguarde o sucesso e confira o digest e o tamanho do instalador completo. Execute **Mirror compatible installer** para criar `WhisperPRO.dmg` e confira os dois instaladores. Após essa confirmação, as partes e o manifesto de transporte podem ser removidos do rascunho; preserve os dois DMGs, `version.json` e `SHA256SUMS.txt`. Só então publique e aguarde **Update feed** concluir.

A composição não sobrescreve arquivos, não remove assets e não publica releases. Um `Transkript.dmg` completo já existente com tamanho e hash corretos é preservado; qualquer divergência interrompe a ação. Os arquivos enviados são partes do instalador distribuível, sem código-fonte do aplicativo.

## Reconstrução opcional por delta

**Restore verified installer delta** reduz o envio local reutilizando o instalador publicado em `v0.15.3`. Exige um delta validado localmente que reconstrua o DMG completo byte por byte, incluindo o rodapé da imagem. A conversão ocorre no macOS e só termina se os hashes do instalador base, das imagens intermediárias e do instalador final coincidirem. O aplicativo não é executado.

Envie o ZIP do delta em partes de 2 MiB com nomes `transkript-upload-<tag>-delta-part-000.bin` e seguintes. O manifesto de transporte `transkript-upload-<tag>-delta-manifest.json` usa o formato da seção anterior, com `filename` igual a `transkript-upload-<tag>-delta.zip`. Informe no workflow a `tag`, o `expected_installer_sha256` do DMG completo e o `expected_delta_sha256` do ZIP. A ação cria somente `Transkript.dmg` em um rascunho; não sobrescreve, remove ou publica arquivos.

Depois do sucesso, execute o espelhamento, confira os dois instaladores e remova apenas as partes e os manifestos de transporte dessa operação. Preserve `version.json` e `SHA256SUMS.txt`. Publique somente com os arquivos finais completos e aguarde **Update feed**.

Verificações locais das ferramentas: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p 'test_release_feed.py'`.
