# Tarefas: Clipador sob demanda (MVP1)

**Entrada**: [spec.md](./spec.md), [plan.md](./plan.md)

Formato: `- [ ] T001 [P] [H1] Descrição` · `[P]` paralelo · `[Hn]` história.

## Fase 1: Preparação

- [x] T001 Projeto `uv` com Python 3.12 e dependências em `pyproject.toml`
- [x] T002 [P] `.gitignore`, `.env.example`, `iniciar.bat`, `README.md`

## Fase 2: Base

- [x] T003 Configuração via `.env` em `src/clipes/config.py`
- [x] T004 SQLite (jobs, clipes, canais) e fila em `src/clipes/db.py`
- [x] T005 Retomar envios interrompidos ao iniciar (`db.iniciar`)

## Fase 3: Histórias 1 e 2 (P1) — achar momentos de qualquer origem

- [x] T006 [P] [H2] Classificar origem por URL em `fontes.classificar` + testes
- [x] T007 [H2] Metadados, heatmap e comentários via yt-dlp em `fontes.resolver`
- [x] T008 [H1] Baixar só o trecho (`download_ranges`) ou cortar arquivo local em `fontes.baixar_trecho`
- [x] T009 [P] [H1] Sinal de áudio em streaming em `sinais.audio`
- [x] T010 [P] [H1] Sinal de chat replay em `sinais.chat`
- [x] T011 [P] [H2] Sinais de heatmap e comentários em `sinais.heatmap` / `sinais.comentarios` + testes
- [x] T012 [H1] `picos_relativos`, `combinar`, `escolher_janelas` (distância mínima) + testes
- [x] T013 [H1] Vídeo curto (≤ 90 s) vira 1 clipe direto em `worker.processar`
- [x] T014 [H1] Limite de clipes por envio, mais fortes primeiro

## Fase 4: Julgamento

- [x] T015 Transcrição com tempo por palavra em `transcricao.py` (áudio via ffmpeg)
- [x] T016 Triagem com LLM simples em `llm.triar`
- [x] T017 Corte, título, gancho, hashtags e spoiler com LLM complexo em `llm.finalizar`
- [x] T018 Lista de spoilers editável em `data/spoilers.txt`

## Fase 5: História 4 (P2) — clipe com cara própria

- [x] T019 Legenda `.ass` palavra a palavra, gancho e crédito em `render.gerar_ass` + testes
- [x] T020 Layouts 9:16 (webcam em cima / fundo desfocado) em `render.filtro_video`
- [x] T021 Detecção de webcam por canal com cache em `llm.achar_webcam` + `worker._webcam`

## Fase 6: História 3 (P1) — revisar

- [x] T022 Página de envio (links + upload + limite) e lista com atualização automática
- [x] T023 Página do envio com filtros, player, aprovar/rejeitar/desfazer, editar título, baixar, copiar texto
- [x] T024 Página de canais com "detectar de novo"

## Fase final: Validação

- [x] T025 Teste ponta a ponta com LLM simulado (upload com 2 picos → 2 clipes; vídeo curto → 1 clipe)
- [x] T026 Teste real: YouTube (metadados, heatmap, comentários, áudio, trecho, Whisper)
- [ ] T027 Teste real com chave da OpenAI (triagem, finalização, webcam)
- [ ] T028 Teste real de VOD da Twitch com chat replay
- [ ] T029 Teste real de clipe da Twitch e de Kick
- [ ] T030 Medir custo real na primeira semana e atualizar `plan.md` (CS-002, CS-003)
- [ ] T031 Medir tempo de um VOD de 4 h no notebook (CS-001)
