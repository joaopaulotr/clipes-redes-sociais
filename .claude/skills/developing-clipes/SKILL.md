---
name: developing-clipes
description: Use when working in the clipes-redes-sociais repository - adding a feature, video source, signal or LLM step, fixing the clip pipeline, changing render/layout, or writing or updating anything under specs/ or .specify/.
---

# Desenvolvendo no Clipes

## Visão geral

Clipador local: envia vídeo → acha momentos com sinais grátis → LLM barato faz triagem → LLM melhor
corta e escreve → ffmpeg gera 9:16 → humano revisa no site. Fluxo **spec-driven** (Spec Kit):
nada de feature nova sem `spec.md` → `plan.md` → `tasks.md`.

Antes de mudar qualquer coisa, leia `.specify/memory/constitution.md` (7 princípios). Os que mais
pesam: nada publica sem aprovação humana, sinais grátis antes de LLM, LLM só em `llm.py`.

## Feature nova

1. Próximo número livre em `specs/` → crie `specs/NNN-nome-curto/` e a branch `NNN-nome-curto`.
2. Copie `.specify/templates/spec-template.md` → `spec.md`. Só **o quê/por quê**: histórias com
   prioridade, cenários Dado/Quando/Então, `RF-xxx`, critérios mensuráveis. Sem tecnologia.
   Dúvida → `[PRECISA ESCLARECER: ...]` e pergunte ao usuário; registre em "Esclarecimentos".
3. `plan-template.md` → `plan.md`: **como**, tabela da constituição preenchida, custo mensal estimado.
4. `tasks-template.md` → `tasks.md`: `T001…` com `[P]`, `[Hn]` e caminho do arquivo.
5. Implemente na ordem; marque `[x]` no mesmo commit da tarefa.
6. Mudou comportamento existente? Atualize a spec antiga (ex.: `specs/001-mvp1-clipador/`).

Bug pequeno não precisa de spec nova.

## Mapa do código (`src/clipes/`)

| Quer mudar… | Arquivo |
|---|---|
| Tipo de origem / download | `fontes.py` (`classificar`, `resolver`, `baixar_trecho`) |
| Sinal novo ou peso | `sinais.py` + `PESOS` em `worker.py` |
| Ordem do pipeline, limites | `worker.py` (`processar`, `_processar_candidato`) |
| Prompt, schema, modelo | `llm.py` (modelos vêm do `.env`) |
| Layout, legenda, gancho | `render.py` |
| Tabelas / status | `db.py` (status na spec e no plan) |
| Telas | `web/app.py`, `web/templates/` |

Sinal novo = função que devolve `np.ndarray` 0–1 por segundo; use `picos_relativos` para contagens brutas.

## Comandos

```bash
uv sync
uv run pytest
uv run python -m clipes          # site em http://localhost:8000
```

Teste do pipeline sem gastar API: monkeypatch de `llm.triar`, `llm.finalizar`, `llm.achar_webcam`
e `WHISPER_MODELO=tiny DATA_DIR=<pasta temporária>`.

## Armadilhas conhecidas

| Sintoma | Causa / correção |
|---|---|
| `ModuleNotFoundError: clipes` | `[tool.uv] package = true` no `pyproject.toml`; rode `uv sync` |
| `open() got an unexpected keyword argument 'metadata_errors'` | PyAV incompatível: passe áudio decodificado pelo ffmpeg (`transcricao._audio_16k`) |
| Filtro `ass` não acha o arquivo no Windows | ffmpeg com `cwd` na pasta do clipe e nome relativo |
| Site sem estilo, erro de CORS | CDN precisa de CORS para SRI: use jsDelivr com `integrity` |
| "Sign in to confirm you're not a bot" | `YTDLP_COOKIES` no `.env` |
| Chat da Twitch vazio | `chat-downloader` é não oficial; o pipeline segue com áudio |

## Erros comuns

- Chamar modelo fora de `llm.py` ou com nome fixo no código (quebra o princípio VII).
- Baixar o vídeo inteiro de VOD (quebra o III).
- Implementar antes de `tasks.md` existir.
- Esquecer de marcar a tarefa `[x]` ou de atualizar o custo no `plan.md`.
