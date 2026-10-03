# Transkript

Transcrição de áudio e vídeo no Mac, com Whisper Large V3, edição por frase,
identificação de falantes, análise de voz e refinamento opcional com IA local.
Anteriormente chamado **Whisper PRO** e **Legendas Vídeo Local**.

A versão atual é **0.15.2 (build 21)**. Este repositório hospeda os instaladores,
o feed de atualização e as ferramentas de publicação; o código-fonte do
aplicativo não é publicado aqui.

## Download e instalação

Baixe [Transkript.dmg](https://github.com/lucaszrezende/legendas-video-local/releases/latest/download/Transkript.dmg),
abra e arraste `Transkript.app` para Aplicativos. Confira as
[notas da última versão](https://github.com/lucaszrezende/legendas-video-local/releases/latest).

- Mac com chip Apple (M1 ou mais recente).
- macOS 26 ou mais recente.
- Internet para baixar os modelos no primeiro uso. Áudios, vídeos e
  transcrições são processados localmente.

O pacote tem assinatura ad-hoc e ainda não foi notarizado pela Apple.
Na primeira abertura, pode ser necessário autorizar o aplicativo em
**Ajustes do Sistema → Privacidade e Segurança → Abrir Mesmo Assim**.

## O que mudou

- Interface com fila de arquivos, histórico, busca, atalhos e modo foco.
- Estimativa do número de falantes e indicação de quem fala cada frase.
- Edição de texto e exportação SRT, VTT, TXT e JSON.
- Popup automático de atualização, notas da versão e acesso ao instalador.

## Atualizações

A partir do **Transkript 0.15.2**, uma versão com build superior ao instalado
abre automaticamente um popup nativo com **Baixar atualização** e **Mais tarde**.
O aviso aguarda o aplicativo ficar ativo e uma transcrição, importação ou outro
diálogo terminar. Ele aparece uma vez por versão em cada execução; ao escolher
**Mais tarde**, pode aparecer novamente na próxima abertura, enquanto houver
uma atualização disponível. Se você já usa a última versão, o popup não aparece.

Com **Avisar quando houver versão nova** ativado em Ajustes, cada abertura faz
uma consulta nova ao feed, mesmo que a consulta anterior seja recente. O app
também verifica ao retornar ao primeiro plano e uma vez por hora de uso ativo,
respeitando o intervalo de uma hora entre essas consultas. O aviso confirmado
permanece disponível ao reabrir ou quando a conexão falha; **Verificar agora**
permite consultar a qualquer momento. O download abre no navegador e a
instalação é feita pelo usuário.

Versões anteriores conservam os avisos dentro do aplicativo, na barra lateral
ou no banner, e recebem o popup nativo depois de atualizar para a 0.15.2.

O endereço usado pelo **Whisper PRO 0.13** voltou a funcionar e aponta para
o mesmo feed. Essa versão conserva o intervalo original de 23 horas entre
verificações na abertura. Para atualizar imediatamente, use
**Ajustes → Atualizações → Verificar agora**. O nome `WhisperPRO.dmg`
é mantido como compatibilidade e contém os mesmos bytes de `Transkript.dmg`.

Cada release estável aciona a ação
[Update feed](https://github.com/lucaszrezende/legendas-video-local/actions/workflows/update-feed.yml),
que verifica o instalador, gera `version.json` e registra os checksums.
Instruções para próximas publicações estão em [tools/README.md](tools/README.md).
