# Constituição do projeto Clipes

Princípios que toda spec, plano e código deste repositório seguem. Uma spec ou PR que viole um
princípio precisa justificar na seção "Verificação da constituição" do `plan.md`.

## Princípios

### I. Revisão humana obrigatória
Nenhum clipe é publicado sem aprovação explícita de uma pessoa. A automação sugere; o humano decide.
Qualquer fluxo de publicação parte de um clipe com status `aprovado`.

### II. Permissão primeiro
Só se processa conteúdo de criadores com campanha ativa ou autorização explícita para clipes.
Spoiler de história (política da Rockstar) é sempre sinalizado na revisão.

### III. Custo mínimo por clipe
Ordem obrigatória do mais barato ao mais caro: sinais grátis (chat, áudio, heatmap, comentários)
→ LLM simples → LLM complexo. Baixa-se só o trecho candidato, nunca o vídeo inteiro (exceto vídeos curtos).
Toda feature nova estima custo mensal no `plan.md`.

### IV. Local primeiro
Roda no PC do usuário sem servidor. Infra paga (Railway, VPS) só entra com spec própria que mostre
necessidade (ex.: monitorar lives 24/7).

### V. Spec antes de código
Toda funcionalidade nova passa por `specs/NNN-nome/spec.md` → `plan.md` → `tasks.md` antes da
implementação. Correção de bug pequena não precisa de spec, mas atualiza a spec afetada se mudar comportamento.

### VI. Testável sem gastar API
Lógica de decisão (sinais, janelas, legendas, classificação de URL) fica em funções puras com testes
em `tests/`. Chamadas de LLM ficam isoladas em `llm.py` para poderem ser simuladas.

### VII. Provedor de LLM trocável
Modelos configurados no `.env` em dois níveis (simples e complexo). Nenhum outro módulo conhece o
nome do modelo.

## Governança

- Mudar um princípio exige PR que altere este arquivo e explique o motivo.
- Versão segue semver: MAJOR remove/redefine princípio, MINOR adiciona, PATCH esclarece texto.

**Versão**: 1.0.0 · **Ratificada**: 2026-11-11 · **Última alteração**: 2026-11-11
