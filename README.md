# Clipes — MVP1

Envia um vídeo (YouTube, VOD ou clipe da Twitch, Kick, link .mp4 ou arquivo) e recebe **vários clipes
verticais 9:16** com legenda, gancho, título, hashtags e alerta de spoiler, prontos para revisar.
Roda no seu PC.

## Documentação (spec-driven)

O projeto segue o padrão do [GitHub Spec Kit](https://github.com/github/spec-kit):

- [`.specify/memory/constitution.md`](.specify/memory/constitution.md): princípios que toda mudança segue
- [`.specify/templates/`](.specify/templates/): modelos de `spec.md`, `plan.md` e `tasks.md`
- [`specs/001-mvp1-clipador/`](specs/001-mvp1-clipador/): spec (o quê), plano (como) e tarefas do MVP1

Feature nova: crie `specs/NNN-nome/` a partir dos modelos **antes** de codar.
Quem usa Claude Code tem a skill `developing-clipes` em `.claude/skills/`, que segue esse fluxo.

## Requisitos

- [uv](https://docs.astral.sh/uv/) e [ffmpeg](https://ffmpeg.org/) no PATH (`winget install Gyan.FFmpeg`)
- Chave da API da OpenAI

## Rodar

1. Copie `.env.example` para `.env` e coloque sua `OPENAI_API_KEY`.
2. Dê dois cliques em `iniciar.bat` (ou rode `uv run python -m clipes`).
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

## Pelo celular

No `.env`, `HOST=0.0.0.0` e abra `http://<ip-do-pc>:8000` na mesma rede Wi-Fi.
**Não tem senha**: só faça isso em rede de casa. Fora de casa, use o Tailscale.

## Testes

```bash
uv run pytest
```
