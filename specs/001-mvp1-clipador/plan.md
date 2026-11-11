# Plano de implementação: Clipador sob demanda (MVP1)

**Branch**: `feat/mvp1` · **Data**: 2026-11-11 · **Spec**: [spec.md](./spec.md)

## Resumo

Site local (FastAPI + HTMX) com um worker em thread que processa uma fila no SQLite. Para cada envio:
`yt-dlp` lê metadados, sinais gratuitos viram séries "intensidade por segundo", os picos viram janelas
candidatas, só essas janelas são baixadas, o Whisper transcreve, um LLM barato faz a triagem, um LLM
melhor define corte e textos, e o `ffmpeg` renderiza o 9:16.

## Contexto técnico

- **Linguagem/versão**: Python 3.12 (gerenciado por `uv`)
- **Dependências**: fastapi, uvicorn, jinja2, python-multipart, yt-dlp, chat-downloader, faster-whisper,
  numpy, openai, pydantic, python-dotenv · `ffmpeg` no PATH
- **Armazenamento**: SQLite em `data/clipes.db` + pasta `data/` (uploads, trabalho, clipes)
- **Testes**: pytest (`tests/`), LLM simulado por monkeypatch
- **Plataforma**: Windows 11, notebook i7-1255U, 16 GB, sem GPU NVIDIA
- **Restrições**: CPU apenas; disco livre ~46 GB

## Verificação da constituição

| Princípio | Atende? | Observação |
|---|---|---|
| I. Revisão humana | ✅ | Status `revisao` → só o usuário muda para `aprovado` |
| II. Permissão primeiro | ✅ | Responsabilidade do usuário ao enviar; spoiler sinalizado |
| III. Custo mínimo | ✅ | Sinais grátis → luna → terra; download só dos trechos |
| IV. Local primeiro | ✅ | Sem servidor |
| V. Spec antes de código | ⚠️ | Spec escrita junto com o código (retroativa); próximas features seguem o fluxo |
| VI. Testável sem API | ✅ | `sinais`, `fontes`, `render` puros e testados; `llm` isolado |
| VII. LLM trocável | ✅ | `LLM_SIMPLES` / `LLM_COMPLEXO` no `.env` |

## Estrutura

```
src/clipes/
├── config.py          # .env → Settings (modelos, limites, pastas)
├── db.py              # SQLite: jobs, clipes, canais; fila
├── fontes.py          # classificar URL, metadados, baixar trecho, URL do áudio, minutagens   (RF-001,002,005)
├── sinais.py          # chat, áudio, heatmap, comentários → séries 0-1; escolher janelas     (RF-003,004)
├── transcricao.py     # faster-whisper com tempo por palavra (áudio via ffmpeg)
├── llm.py             # OpenAI Responses + structured outputs: triar, finalizar, achar_webcam (RF-007,008,009)
├── render.py          # frames, legenda .ass, filtro 9:16, render ffmpeg                    (História 4)
├── worker.py          # pipeline por envio + loop da fila                                    (RF-006,012)
├── __main__.py        # uv run python -m clipes
└── web/
    ├── app.py         # rotas: enviar, envios, revisão, ações, vídeo, canais                (História 3)
    └── templates/     # Jinja + HTMX + Tailwind (CDN com SRI)
tests/test_basico.py
```

## Desenho

### Pipeline (por envio)

```
resolver → [curto ≤ 90 s? → 1 janela] → sinais → combinar → escolher_janelas(max_clipes × 2)
  → para cada janela (mais forte primeiro, até max_clipes prontos):
       baixar_trecho → transcrever → triar (luna) → nota ≥ NOTA_MINIMA?
       → finalizar (terra, + 3 frames) → webcam do canal (cache) → renderizar → status revisao
→ apaga data/trabalho/<job>
```

### Sinais

| Sinal | Quando | Como |
|---|---|---|
| chat | VOD da Twitch, replay de live do YouTube | `chat-downloader`; msgs/s com peso 3× para gatilhos (KEKW, kkkk…); desconta 8 s de atraso |
| áudio | sempre | `ffmpeg` → PCM 8 kHz mono em streaming → RMS por segundo |
| heatmap | YouTube | `info["heatmap"]` do yt-dlp; primeiros 30 s atenuados |
| comentários | YouTube | regex de minutagem em até 300 comentários |

Chat e áudio passam por `picos_relativos`: z-score sobre média móvel de 300 s → auto-calibra por canal.
Pesos na combinação: heatmap 1.2, chat 1.0, comentários 0.8, áudio 0.6.
Janela: 90 s (2/3 antes do pico, 1/3 depois), distância mínima 60 s.

### Modelo de dados

- `jobs(id, origem, tipo, titulo, canal, duracao, max_clipes, status, etapa, erro, criado_em)`
  — status: `na_fila → resolvendo → sinais → processando → pronto | erro`
- `clipes(id, job_id, inicio, fim, nota_sinal, nota_llm, categoria, titulo, gancho, descricao, hashtags,
  spoiler, spoiler_motivo, status, arquivo, erro, criado_em)`
  — status: `candidato → descartado | renderizando → revisao → aprovado | rejeitado | erro`
- `canais(nome, webcam JSON {x,y,w,h} | null, atualizado_em)`

Ao iniciar, envios em andamento voltam para `na_fila`; candidatos pendentes são reaproveitados.

### Render

- Com webcam: crop da webcam → 1080×640 em cima; centro do jogo → 1080×1280 embaixo; `vstack`.
- Sem webcam: jogo 1080 de largura sobre o mesmo quadro desfocado.
- Legenda `.ass`: grupos de 3 palavras, palavra atual em amarelo; gancho em caixa branca 0–2,5 s; crédito embaixo.
- ffmpeg roda com `cwd` na pasta do clipe para o filtro `ass` não precisar escapar `C:\`.

## Decisões e alternativas

| Decisão | Alternativa descartada | Motivo |
|---|---|---|
| Local + SQLite | Railway + Postgres + bucket | Servidor ~US$15–25/mês sem necessidade no MVP1 |
| OpenAI luna + terra | Claude Haiku + Sonnet | Escolha do usuário; terra custa metade do equivalente |
| Whisper local | API de transcrição | ~US$25–75/mês a mais |
| Worker em thread | Processo/fila separados | Um comando só para subir tudo |
| Áudio do Whisper via ffmpeg | PyAV (padrão do faster-whisper) | Versão do PyAV incompatível quebrava a transcrição |
| Tailwind via jsDelivr com SRI | cdn.tailwindcss.com | Sem CORS, o SRI bloqueava o script |

## Custo estimado (uso médio)

| Item | US$/mês |
|---|---|
| LLM simples (luna, ~60 chamadas/dia) | ~1–2 |
| LLM complexo (terra, ~20 chamadas/dia) | ~6–12 |
| Servidor, Whisper, ffmpeg, yt-dlp | 0 |
| **Total** | **~8–14** |

## Riscos

- `chat-downloader` usa API não oficial da Twitch → falha vira aviso e segue sem chat.
- YouTube pede login para alguns vídeos → `YTDLP_COOKIES`.
- Detecção de webcam errada → página Canais permite refazer.
- Modelos não conhecem a história do GTA VI → lista `data/spoilers.txt` mantida pelo usuário.
