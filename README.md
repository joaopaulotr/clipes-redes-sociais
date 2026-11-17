# Clipes

Envia um vídeo (YouTube, VOD ou clipe da Twitch, Kick, link .mp4 ou arquivo) e recebe **vários clipes
verticais 9:16** com legenda, gancho, título, hashtags e alerta de spoiler, prontos para revisar.
Também **vigia lives da Twitch**: quando o chat explode, o trecho vira clipe em revisão e você recebe
o aviso no Telegram. Roda no seu computador.

## Documentação (spec-driven)

O projeto segue o padrão do [GitHub Spec Kit](https://github.com/github/spec-kit):

- [`.specify/memory/constitution.md`](.specify/memory/constitution.md): princípios que toda mudança segue
- [`.specify/templates/`](.specify/templates/): modelos de `spec.md`, `plan.md` e `tasks.md`
- [`specs/001-mvp1-clipador/`](specs/001-mvp1-clipador/): spec (o quê), plano (como) e tarefas do MVP1
- [`specs/002-monitor-lives/`](specs/002-monitor-lives/): monitor de lives da Twitch + avisos no Telegram

Feature nova: crie `specs/NNN-nome/` a partir dos modelos **antes** de codar.
Quem usa Claude Code tem a skill `developing-clipes` em `.claude/skills/`, que segue esse fluxo.

## Requisitos

- [uv](https://docs.astral.sh/uv/) e [ffmpeg](https://ffmpeg.org/) com libass no PATH
  - macOS: `brew install ffmpeg-full` (o `ffmpeg` comum do Homebrew não tem o filtro de legenda; o
    `iniciar.sh` já usa o `ffmpeg-full`)
  - Windows: `winget install Gyan.FFmpeg`
- Chave da API da OpenAI

## Rodar

1. Copie `.env.example` para `.env` e coloque sua `OPENAI_API_KEY`.
2. macOS: `./iniciar.sh` (mantém o Mac acordado enquanto roda). Windows: dois cliques em `iniciar.bat`.
3. Abra http://localhost:8000, cole os links (um por linha) e clique em **Gerar clipes**.

Na primeira transcrição o Whisper baixa o modelo (~500 MB no `small`).

## Como funciona

```
enviar → metadados → sinais (chat, áudio, "Mais repetidos", comentários) → candidatos
       → baixa só os trechos → Whisper → gpt-6-luna (triagem) → gpt-6.1-terra (corte, título, spoiler)
       → ffmpeg 9:16 com legenda → revisão no site
```

- Vídeo de até 90 s (clipe da Twitch, Short) vira 1 clipe direto.
- VOD/vídeo longo gera até **Máx. de clipes** (padrão 20).
- Webcam detectada 1x por canal (página **Canais** para refazer).
- Lista de spoilers do GTA VI: edite `data/spoilers.txt`.

## Monitor de lives (Twitch)

Página **Monitor**: cadastre o canal e a campanha/autorização (obrigatória para ativar). Enquanto o
canal está ao vivo, o app grava os últimos 10 min, lê o chat e, num pico, corta ~90 s em volta do
momento e manda para a fila com prioridade. A triagem do LLM descarta o que não presta. No fim da live,
o VOD entra na fila sozinho, sem repetir os momentos já clipados.

- Até `MAX_LIVES` (3) lives gravadas ao mesmo tempo, por prioridade.
- `LIMITE_HORA`: clipes ao vivo por canal por hora. Picos acima do limite aparecem como "não clipado".
- `LIMIAR_Z`: sensibilidade. Menor = mais clipes (e mais gasto de LLM).
- O Mac precisa ficar ligado e acordado (o `iniciar.sh` usa `caffeinate`; com a tampa fechada na
  bateria ele dorme mesmo assim).

## Avisos no Telegram

1. No Telegram, fale com **@BotFather** → `/newbot` → copie o token para `TELEGRAM_TOKEN` no `.env`.
2. Mande "oi" para o seu bot e rode `uv run python -m clipes.avisos`: ele mostra o `TELEGRAM_CHAT_ID`.
3. Cole no `.env`, reinicie e clique em **Enviar teste** na página Monitor.

Clipes que ficam prontos juntos chegam numa mensagem só. Dá para silenciar na página Monitor.

## Pelo celular (fora de casa)

O site **não tem senha**, então nunca abra a porta para a internet. Use o [Tailscale](https://tailscale.com)
(grátis):

1. Instale no Mac e no celular, com a mesma conta.
2. No Mac: `tailscale serve --bg 8000`. Ele mostra um endereço `https://<mac>.<tailnet>.ts.net`.
3. Coloque esse endereço em `URL_BASE` no `.env`: é para onde o botão do aviso leva.

Só na rede de casa: `HOST=0.0.0.0` e `URL_BASE=http://<ip-do-mac>:8000`.

## Testes

```bash
uv run pytest
```
