# Spec — MVP1: clipador sob demanda (local)

## Objetivo

Você envia um vídeo (link ou arquivo) por um site local e recebe **vários clipes verticais 9:16**
prontos para revisar, com título, gancho, hashtags e alerta de spoiler. Você aprova, baixa e posta.

Roda **no notebook** (sem servidor). Custo mensal estimado: **~US$8–14** no uso médio (só API da OpenAI).

## Fora do MVP1

- Monitorar lives ao vivo
- RSS automático de canais
- Postagem automática via API (no MVP1: botão de download + copiar título)
- Notificação push

## Entradas aceitas

| Entrada | Tipo interno | Sinal de momento quente |
|---|---|---|
| Link do YouTube (vídeo, Short, replay de live) | `youtube` | Heatmap "Mais repetidos" + comentários com minutagem + replay do chat (se foi live) + áudio |
| Link de VOD da Twitch | `twitch_vod` | Replay do chat + picos de áudio |
| Link de clipe da Twitch | `twitch_clip` | O clipe inteiro já é o momento |
| Link da Kick (VOD/clipe) | `kick` | Picos de áudio (+ chat se disponível) |
| Link direto `.mp4` | `mp4_url` | Picos de áudio |
| Upload de MP4 | `upload` | Picos de áudio |
| Qualquer outro link suportado pelo yt-dlp | `generic` | Picos de áudio |

Vídeos curtos (≤ 90 s) viram 1 clipe direto, sem detecção.

## Pipeline

```
enviar → resolver (metadados) → sinais → candidatos → baixar trechos → transcrever
       → LLM simples (triagem) → LLM complexo (corte, título, gancho, spoiler) → render → revisão
```

1. **Resolver** — `yt-dlp` extrai metadados sem baixar o vídeo (duração, título, canal, heatmap, comentários).
2. **Sinais** — cada sinal vira uma série "intensidade por segundo", normalizada 0–1:
   - **chat**: mensagens por segundo comparadas com a média móvel do próprio canal (auto-calibra);
     palavras-gatilho (KEKW, LUL, kkkk, clip…) pesam mais. Compensa ~8 s de atraso do chat.
   - **áudio**: volume RMS por segundo comparado com a média móvel.
   - **heatmap**: valores do "Mais repetidos".
   - **comentários**: minutagens citadas nos comentários (`2:14`, `1:02:33`).
3. **Candidatos** — soma ponderada dos sinais → escolhe picos com distância mínima entre eles
   (padrão 60 s) → janela de ~90 s ao redor de cada pico. Pega `max_clipes × 2` candidatos.
4. **Baixar trechos** — só as janelas candidatas (`yt-dlp --download-sections`), em até 720p.
   Arquivo local: corta com `ffmpeg`.
5. **Transcrever** — `faster-whisper` (modelo `small`, CPU, int8) com timestamp por palavra.
6. **LLM simples** (`gpt-6-luna`) — nota 0–10, categoria, suspeita de spoiler. Roda em todos.
7. **LLM complexo** (`gpt-6.1-terra`) — só para nota ≥ `NOTA_MINIMA` (padrão 6) ou suspeita de spoiler:
   início/fim exatos (15–60 s), título, gancho (texto dos 2 primeiros segundos), descrição,
   hashtags, spoiler sim/não + motivo. Recebe até 3 frames do trecho.
8. **Render** — `ffmpeg` 1080×1920:
   - com webcam conhecida para o canal: webcam no terço de cima, jogo nos dois terços de baixo;
   - sem webcam: jogo centralizado sobre fundo desfocado;
   - legenda palavra a palavra (`.ass`, fonte grossa, palavra atual destacada);
   - gancho no topo nos primeiros 2 s; crédito ao criador.
9. **Revisão** — site mostra os clipes: player, nota, título editável, alerta de spoiler,
   botões Aprovar / Rejeitar / Baixar / Copiar título.

**Vários clipes por VOD**: o limite é por envio (`max_clipes`, padrão 20, editável no formulário).

## Detecção de webcam

Na primeira vez que um canal aparece, o LLM complexo recebe 1 frame e devolve a caixa da webcam
(frações 0–1 da tela) ou "sem webcam". Fica salvo por canal na tabela `canais`.
Pode ser corrigido/limpo no site.

## Spoiler

Os modelos não conhecem a história do GTA VI. O prompt leva `data/spoilers.txt`
(missões, personagens, eventos da história — você atualiza). Cutscene ou nome de missão = suspeito.
Palavra final: sua revisão.

## Modelos (configuráveis no `.env`)

| Nível | Padrão | Alternativa |
|---|---|---|
| Simples | `gpt-6-luna` | — |
| Complexo | `gpt-6.1-terra` | `gpt-6.1-sol` (melhor, 2× preço) |

## Stack

- Python 3.12 + `uv`
- FastAPI + Jinja2 + HTMX + Tailwind (CDN), em `http://localhost:8000`
- SQLite (`data/clipes.db`) + pasta `data/`
- Worker em thread dentro do mesmo processo (fila no SQLite)
- `yt-dlp`, `chat-downloader`, `ffmpeg`, `faster-whisper`, `numpy`, SDK `openai`

## Dados

- `jobs`: um envio (url/arquivo, tipo, título, canal, status, erro, max_clipes)
- `clipes`: candidato → clipe (início, fim, notas, textos, spoiler, status, arquivo)
- `canais`: webcam por canal

Status do job: `na_fila → resolvendo → sinais → processando → pronto | erro`
Status do clipe: `candidato → descartado | renderizando → revisao → aprovado | rejeitado | erro`

## Limpeza

Trechos brutos são apagados ao final do job. Clipes ficam em `data/clipes/<job>/`.

## Riscos conhecidos

- Chat replay da Twitch depende de API não oficial (`chat-downloader`): se falhar, segue só com áudio.
- YouTube pode pedir login para alguns vídeos: suporta `YTDLP_COOKIES` (arquivo de cookies) no `.env`.
- Permissão: só envie vídeo de criador com campanha ativa ou que liberou clipe.
