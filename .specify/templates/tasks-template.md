# Tarefas: [NOME DA FUNCIONALIDADE]

**Entrada**: [spec.md](./spec.md), [plan.md](./plan.md)

Formato: `- [ ] T001 [P] [H1] Descrição com caminho do arquivo`
- `[P]` = pode rodar em paralelo (arquivos diferentes, sem dependência)
- `[H1]` = história de usuário atendida
- Marque `[x]` ao concluir, no mesmo commit da implementação.

## Fase 1: Preparação

- [ ] T001 [descrição] em `caminho/arquivo`

## Fase 2: Base (bloqueia as histórias)

- [ ] T002 ...

## Fase 3: História 1 (P1) — MVP

**Objetivo**: [o que entrega]
**Teste independente**: [como validar]

- [ ] T003 [P] [H1] Teste de ... em `tests/...`
- [ ] T004 [H1] Implementar ... em `src/clipes/...`

## Fase 4: História 2 (P2)

- [ ] T005 ...

## Fase final: Acabamento

- [ ] T0XX Atualizar README e spec com o que mudou
- [ ] T0XX Validação manual ponta a ponta

## Dependências

[Fase 2 bloqueia 3+. Histórias independentes entre si podem rodar em paralelo.]
