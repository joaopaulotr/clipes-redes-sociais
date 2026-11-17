# Tarefas: Monitor de lives com aviso no celular

**Entrada**: [spec.md](./spec.md), [plan.md](./plan.md)

Formato: `- [ ] T001 [P] [H1] Descrição` · `[P]` paralelo · `[Hn]` história.

## Fase 1: Preparação

- [ ] T001 Dependência `streamlink` em `pyproject.toml`
- [ ] T002 [P] Variáveis `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`, `URL_BASE`, `MAX_LIVES`, `LIMIAR_Z`, `LIMITE_HORA` em `.env.example` e `src/clipes/config.py`

## Fase 2: Base

- [ ] T003 Tabelas `vigiados`, `sessoes`, `momentos`, `avisos`, `ajustes` e funções em `src/clipes/db.py`
- [ ] T004 Fila com duas filas (ao vivo / resto) em `db.pegar_proximo_job` e `worker.loop`

## Fase 3: História 1 (P1) — lista de canais vigiados

- [ ] T005 [P] [H1] `twitch.login_do_link` + testes em `tests/test_monitor.py`
- [ ] T006 [H1] Página `/monitor`: cadastrar, ativar (exige autorização), desativar, prioridade, limite/hora em `web/app.py` + `templates/monitor.html`

## Fase 4: História 2 (P1) — clipe ao vivo

- [ ] T007 [P] [H2] `Detector` de picos online + testes em `src/clipes/detector.py`
- [ ] T008 [P] [H2] Parser de mensagens IRC + gatilhos em `src/clipes/twitch.py` + testes
- [ ] T009 [H2] `twitch.ao_vivo`, gravação em segmentos e leitura do chat em `src/clipes/twitch.py`
- [ ] T010 [H2] Corte do buffer em `.mp4` (`monitor.cortar_buffer`) + teste com segmentos sintéticos
- [ ] T011 [H2] Thread por canal: sessão, picos, limite/hora, intervalos cegos em `src/clipes/monitor.py`
- [ ] T012 [H2] Tipo `ao_vivo` no `fontes.resolver` e no `worker` (triagem + corte livre)

## Fase 5: História 3 (P1) — aviso no Telegram

- [ ] T013 [P] [H3] `agrupar_avisos` + formato da mensagem + testes em `src/clipes/avisos.py`
- [ ] T014 [H3] Envio pela Bot API, thread de avisos, silenciar, botão de teste no `/monitor`
- [ ] T015 [H3] `python -m clipes.avisos` para descobrir o `chat_id`

## Fase 6: História 4 (P2) — VOD no fim da live

- [ ] T016 [H4] Achar o último VOD do canal (`twitch.ultimo_vod`) e enfileirar ao fechar a sessão
- [ ] T017 [H4] Descartar janelas do VOD perto de momentos já clipados (`worker`) + teste

## Fase final: Acabamento

- [ ] T018 README: Telegram, Tailscale, monitor; `caffeinate` no `iniciar.sh`
- [ ] T019 Validação manual: vigiar uma live real por 1 h e receber o aviso (CS-001, CS-002)
- [ ] T020 Medir custo na primeira semana e atualizar `plan.md` (CS-004)

## Dependências

Fase 2 bloqueia 3+. T007/T008/T013 são puras e paralelas. H3 independe de H2 (dá para testar com
clipes do MVP1). H4 depende de T011.
