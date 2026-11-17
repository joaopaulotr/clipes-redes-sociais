# Plano de implementação: Monitor de lives com aviso no celular

**Branch**: `002-monitor-lives` · **Data**: 2026-11-17 · **Spec**: [spec.md](./spec.md)

> Este plano descreve **como**. Cada decisão aponta para o requisito (RF-xxx) que atende.

## Resumo

Uma thread "monitor" vigia os canais ativos da Twitch. Para cada canal ao vivo ela grava a live num
buffer local de segmentos de 10 s (`streamlink` → `ffmpeg`), lê o chat pelo IRC anônimo e calcula,
segundo a segundo, quanto o chat está acima do normal recente daquela live. Num pico, espera 30 s,
junta os segmentos em volta do momento num `.mp4` e cria um envio `ao_vivo` na fila. Esse envio
segue o pipeline do MVP1 (Whisper → triagem → finalização → render) com prioridade. Quando um clipe
entra em revisão, uma thread de avisos manda uma mensagem agrupada no Telegram com link para o clipe.
Ao fim da live, o VOD entra sozinho na fila, ignorando os momentos já clipados.

## Contexto técnico

- **Linguagem/versão**: Python 3.12 (`uv`)
- **Dependências novas**: `streamlink` — grava a live da Twitch e diz se o canal está no ar, sem
  precisar de app na Twitch. Chat via IRC anônimo (`socket` da biblioteca padrão) e Telegram via
  Bot API (`urllib`), sem dependências extras.
- **Armazenamento**: SQLite (tabelas novas `vigiados`, `sessoes`, `momentos`, `avisos`, `ajustes`);
  buffer em `data/ao_vivo/<canal>/` (~260 MB por canal em 720p, 10 min)
- **Testes**: pytest; detector de picos e agrupamento de avisos são funções puras; Telegram e
  streamlink simulados
- **Plataforma**: macOS (Apple Silicon), local
- **Restrições**: sem servidor (RF-015); CPU compartilhada com o Whisper

## Verificação da constituição

| Princípio | Atende? | Observação |
|---|---|---|
| I. Revisão humana | ✅ | Clipe ao vivo entra em `revisao`; aviso só leva ao site (RF-013) |
| II. Permissão primeiro | ✅ | Canal só ativa com autorização registrada (RF-002); só lista branca é vigiada (RF-003) |
| III. Custo mínimo | ✅ | Pico decidido só pelo chat (grátis); LLM roda depois, no trecho do pico; limite por hora (RF-007) |
| IV. Local primeiro | ✅ | Tudo roda no Mac; acesso remoto via Tailscale, sem servidor |
| V. Spec antes de código | ✅ | spec → plan → tasks antes do código |
| VI. Testável sem API | ✅ | `Detector`, `agrupar_avisos`, parsing de IRC puros e testados |
| VII. LLM trocável | ✅ | Nenhuma chamada de LLM nova fora de `llm.py` |

## Estrutura afetada

```
src/clipes/
├── config.py          # + TELEGRAM_*, URL_BASE, limites do monitor
├── db.py              # + tabelas vigiados/sessoes/momentos/avisos/ajustes; fila com prioridade ao_vivo
├── fontes.py          # + resolver ao_vivo (arquivo local com canal); timestamp do VOD
├── twitch.py          # NOVO: login a partir do link, está ao vivo?, gravação, chat IRC, último VOD
├── detector.py        # NOVO: Detector de picos online (puro)                     (RF-005, RF-007)
├── monitor.py         # NOVO: thread por canal: sessão, buffer, picos, corte, VOD  (H2, H4)
├── avisos.py          # NOVO: Telegram, agrupamento, silenciar, descobrir chat_id (H3)
├── worker.py          # tipo ao_vivo: triagem + corte livre; filtro de momentos já clipados no VOD
└── web/
    ├── app.py         # + /monitor (H1, RF-012), silenciar avisos, teste do Telegram
    └── templates/     # + monitor.html, _vigiados.html; link "Monitor" no menu
tests/test_monitor.py  # NOVO
```

## Desenho

### Fluxo de um canal ao vivo

```
monitor (a cada 60 s) → canal ativo está no ar? (streamlink)
  └─ sim → abre sessão → grava: streamlink 720p → ffmpeg -f segment 10 s → data/ao_vivo/<login>/
                       → chat: IRC anônimo (justinfan) → msgs/s com peso 3× em gatilhos
                       → Detector.empurrar(contagem do segundo) → pico?
                             └─ sim → espera 30 s → limite/hora ok? → concatena segmentos [pico-60s, pico+30s]
                                    → cria job tipo ao_vivo (origem = .mp4, canal = login) → momento registrado
  └─ fora do ar por 5 min → fecha sessão → apaga buffer → acha último VOD → job twitch_vod (H4)
```

### Detector (online, puro)

- Entrada: contagem ponderada de mensagens por segundo.
- Normal = média e desvio dos últimos 300 s (só passado, sem olhar o futuro).
- z = (média dos últimos 5 s − normal) / desvio. Pico quando z ≥ `LIMIAR_Z` (3,0), a média dos 5 s ≥
  `MIN_MSGS_S` (2 msgs/s) e já houve 120 s de histórico. Atende RF-005 e o cenário 3 da H2.
- Depois de um pico, ignora novos picos por 60 s (cenário 2 da H2). Atraso do chat: 8 s, como no MVP1.

### Envio `ao_vivo` no worker

- `fontes.resolver` trata `ao_vivo` como arquivo local, com `canal` = login do streamer.
- Uma janela só (o arquivo todo); **com** triagem (o MVP1 pula triagem em vídeo curto) e corte livre
  do LLM entre 15 e 60 s.
- Fila: `pegar_proximo_job` tem duas threads, uma só para `ao_vivo` e outra para o resto, para um VOD
  longo não atrasar o clipe ao vivo (CS-001).

### VOD sem duplicar (RF-011)

- `momentos` guarda o instante UTC do pico. No VOD, `fontes.resolver` lê `timestamp` (início da live).
- Janelas do VOD a menos de 60 s de um momento já clipado são descartadas antes do download.

### Avisos (H3)

- Quando um clipe vai para `revisao`, nasce uma linha em `avisos` (pendente).
- Thread de avisos a cada 5 s: se há pendentes e o mais novo tem ≥ 15 s (ninguém novo chegando),
  envia **uma** mensagem com todos (cenário 2). Pior caso ~20 s + rede, dentro do CS-002.
- Mensagem: título, canal, nota, ⚠ spoiler, e botão "Revisar" com `URL_BASE/job/<id>`.
- Silenciar: chave `avisos_silenciados` na tabela `ajustes`; pendentes são marcados como
  `silenciado` (cenário 3).
- `uv run python -m clipes.avisos` mostra o `chat_id` depois que o usuário manda "oi" ao bot.

### Acesso fora de casa (RF-009)

Tailscale no Mac e no celular + `tailscale serve --bg 8000`. O site continua em `127.0.0.1`;
`URL_BASE` no `.env` aponta para o endereço `https://<mac>.<tailnet>.ts.net`. Nada fica exposto
na internet.

### Modelo de dados (novo)

- `vigiados(login PK, nome, autorizacao, ativo, prioridade, limite_hora, status, ultimo_pico,
  erro, criado_em)` — status: `offline | ao_vivo | gravando | erro`
- `sessoes(id, login, inicio, fim, titulo, vod_job_id)`; `cegos` = JSON com intervalos sem vigiar
- `momentos(id, sessao_id, login, instante, forca, job_id, motivo)` — `motivo` quando não virou clipe
- `avisos(id, clipe_id, status, criado_em, enviado_em)` — status: `pendente | enviado | silenciado | erro`
- `ajustes(chave PK, valor)`

### Casos de borda

- Live cai e volta em < 5 min: mesma sessão (o fechamento só ocorre após 5 min fora).
- Chat cai: reconecta com espera crescente; o intervalo vira "cego" na sessão.
- Mac dorme: o laço percebe salto de relógio > 30 s e registra o intervalo cego.
- Mais lives que `MAX_LIVES` (3): grava as de maior prioridade; as outras ficam "na espera".

## Decisões e alternativas

| Decisão | Alternativa descartada | Motivo |
|---|---|---|
| `streamlink` para status e gravação | Twitch Helix API | Helix exige criar app e segredo; streamlink não, e já grava |
| Buffer em segmentos de 10 s | Pedir clipe oficial (`POST /helix/clips`) | Clipe oficial exige token de usuário e limita a 60 s |
| IRC anônimo para chat | `chat-downloader` ao vivo | IRC é oficial, estável e sem dependência |
| Pico só pelo chat ao vivo | Chat + áudio ao vivo | Áudio ao vivo dobra CPU; o áudio já é usado no VOD e o LLM filtra depois |
| Telegram via `urllib` | `python-telegram-bot` | Só precisamos de `sendMessage` e `getUpdates` |
| Duas threads de fila | Prioridade numa thread só | Um VOD de 4 h travaria o clipe ao vivo |
| Tailscale | Expor porta com senha | O site não tem login; Tailscale não expõe nada |

## Custo estimado

5 canais × 4 h/dia, ~3 clipes por canal por hora no máximo.

| Item | US$/mês |
|---|---|
| Triagem (luna), ~60 chamadas/dia | ~1–2 |
| Finalização (terra), ~25 chamadas/dia | ~8–12 |
| streamlink, IRC, Telegram, Tailscale (plano grátis) | 0 |
| **Total adicional** | **~9–14** (CS-004: < 15) |

## Riscos

- Twitch muda o player e o `streamlink` quebra → `uv lock --upgrade-package streamlink`.
- Anúncios no início da live entram no buffer → `--twitch-disable-ads`.
- Pico falso (spam/raid) → limite por hora + triagem do LLM descarta.
- Disco: 3 lives × ~260 MB de buffer → apagado ao fim de cada sessão.
- O Mac dormir durante a live → instruir `caffeinate` no `iniciar.sh`.
