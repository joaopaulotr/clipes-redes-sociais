# Spec: Monitor de lives com aviso no celular

**Branch**: `002-monitor-lives` · **Criada**: 2026-11-11 · **Status**: Rascunho

> O quê e por quê. Como será implementado: `plan.md` (a escrever). Andamento: `tasks.md` (a escrever).

## Contexto

No MVP1 ([001](../001-mvp1-clipador/spec.md)) o usuário precisa achar o vídeo e colar o link. Na semana
do lançamento do GTA VI (19/nov/2026) ganha quem posta primeiro o momento que viralizou, e o VOD só
fica disponível horas depois. O usuário não quer assistir lives: quer que o sistema vigie os
streamers autorizados, transforme os momentos fortes em clipes enquanto a live acontece e avise no
celular quando houver algo para revisar.

Esta spec cobre as etapas que o MVP1 deixou de fora: **descoberta** (lista de canais vigiados),
**detecção ao vivo** e **aviso**. Publicação automática nas redes fica para uma spec futura.

## Histórias de usuário

### História 1 — Lista de canais vigiados (Prioridade: P1)

O usuário cadastra os streamers que pode clipar (com campanha ativa ou autorização) e o sistema só
vigia e só clipa esses canais.

**Por que esta prioridade**: é a base de tudo e aplica o princípio II (permissão primeiro) na prática.

**Teste independente**: cadastrar 3 canais, desativar 1 e ver que só os 2 ativos aparecem como vigiados.

**Cenários de aceite**:
1. **Dado** um link de canal, **quando** o usuário cadastra, **então** o canal aparece na lista com
   plataforma, nome, status (ao vivo / offline) e a campanha ou autorização associada.
2. **Dado** um canal cadastrado, **quando** o usuário o desativa, **então** o sistema para de vigiá-lo
   sem perder o histórico de clipes.
3. **Dado** um canal sem campanha ou autorização informada, **quando** o usuário tenta ativá-lo,
   **então** o sistema pede essa informação antes de vigiar.

### História 2 — Clipe automático do momento quente durante a live (Prioridade: P1)

Enquanto um canal vigiado está ao vivo, o sistema percebe quando o chat e o áudio explodem em
relação ao normal daquela live e gera um clipe desse momento, que cai na revisão como qualquer
outro clipe do MVP1.

**Por que esta prioridade**: é a vantagem de velocidade; o clipe fica pronto minutos depois do
momento, em vez de horas depois do VOD.

**Teste independente**: vigiar uma live real por 1 h e receber pelo menos 1 clipe em revisão de um
momento que aconteceu nessa hora.

**Cenários de aceite**:
1. **Dado** um canal vigiado ao vivo, **quando** a atividade do chat passa muito do normal daquela
   live, **então** o sistema gera um clipe que contém o momento, com título, gancho, legenda e alerta
   de spoiler, e o coloca em "Para revisar".
2. **Dado** dois picos a menos de 60 s um do outro, **quando** o sistema reage, **então** gera um clipe
   só.
3. **Dado** uma live com chat muito ativo o tempo todo, **quando** o sistema compara, **então** usa o
   normal daquela live (não um número fixo) para decidir o que é pico.
4. **Dado** que o limite de clipes por hora do canal foi atingido, **quando** surge outro pico,
   **então** o sistema registra o momento sem gerar clipe e o mostra como "momento não clipado".

### História 3 — Aviso no celular (Prioridade: P1)

O usuário recebe no celular um aviso quando um clipe novo fica pronto para revisar, com o título,
o canal e um link para abrir o clipe.

**Por que esta prioridade**: sem aviso o usuário precisaria ficar olhando o site, que é exatamente o
que ele não quer.

**Teste independente**: gerar um clipe e receber o aviso no celular em menos de 1 min.

**Cenários de aceite**:
1. **Dado** um clipe que entrou em "Para revisar", **quando** isso acontece, **então** o usuário
   recebe um aviso com título, canal, nota e se há suspeita de spoiler.
2. **Dado** vários clipes prontos em poucos minutos, **quando** os avisos seriam enviados, **então**
   o sistema agrupa em um aviso só para não virar spam.
3. **Dado** que o usuário silenciou os avisos, **quando** um clipe fica pronto, **então** nenhum aviso
   é enviado e o clipe continua na revisão.

### História 4 — VOD automático no fim da live (Prioridade: P2)

Quando a live de um canal vigiado termina, o sistema coloca o VOD na fila do MVP1 sozinho para
achar os momentos que a vigilância ao vivo não pegou.

**Por que esta prioridade**: complementa a História 2 sem trabalho do usuário, mas não é urgente,
porque o momento mais forte já foi clipado ao vivo.

**Teste independente**: deixar uma live vigiada acabar e ver o VOD aparecer na fila sozinho.

**Cenários de aceite**:
1. **Dado** uma live vigiada que terminou, **quando** o VOD fica disponível, **então** ele entra na
   fila com o limite de clipes padrão do canal.
2. **Dado** um momento que já virou clipe ao vivo, **quando** o VOD é processado, **então** esse
   momento não gera um clipe repetido.

### Casos de borda

- Canal fica ao vivo e cai várias vezes seguidas: o sistema trata como a mesma live se voltar em
  poucos minutos.
- Chat indisponível ou bloqueado: o sistema segue só com o áudio e avisa na lista de canais.
- O streamer desativa VODs ou clipes: a História 2 continua; a História 4 é pulada com aviso.
- O computador dorme ou perde a internet: ao voltar, o sistema retoma a vigilância sem duplicar
  clipes e mostra o intervalo em que ficou cego.
- Muitas lives ao mesmo tempo: existe um limite de canais vigiados simultâneos; os excedentes
  esperam por prioridade definida pelo usuário.
- Momento de história (spoiler) detectado ao vivo: vira clipe com alerta de spoiler em destaque, como
  no MVP1; nunca é tratado como pronto sem revisão.

## Requisitos

### Requisitos funcionais

- **RF-001**: O usuário DEVE poder cadastrar, editar, ativar e desativar canais vigiados.
- **RF-002**: O sistema DEVE exigir campanha ou autorização registrada para ativar um canal.
- **RF-003**: O sistema DEVE vigiar somente canais ativos da lista.
- **RF-004**: O sistema DEVE perceber quando um canal vigiado entra e sai do ar em até 5 min.
- **RF-005**: O sistema DEVE detectar picos durante a live comparando com o normal daquela própria
  live, usando apenas sinais gratuitos antes de qualquer modelo pago.
- **RF-006**: Cada pico aceito DEVE virar um clipe no mesmo fluxo de triagem, corte, textos,
  render e revisão do MVP1.
- **RF-007**: O sistema DEVE respeitar um limite de clipes por hora por canal, configurável.
- **RF-008**: O sistema DEVE avisar o usuário no celular quando um clipe entra em revisão, agrupando
  avisos próximos. [PRECISA ESCLARECER: por qual canal de aviso — Telegram, notificação push do
  celular (ex.: ntfy) ou outro?]
- **RF-009**: O aviso DEVE trazer um link que abre o clipe para revisão, também fora de casa, por
  um acesso remoto seguro (o site não tem senha e não pode ficar aberto na internet).
- **RF-010**: O usuário DEVE poder silenciar e reativar os avisos.
- **RF-011**: Ao fim de uma live vigiada, o sistema DEVE colocar o VOD na fila sem duplicar momentos já
  clipados ao vivo.
- **RF-012**: O sistema DEVE mostrar, por canal, o status atual, o último pico, os clipes gerados e os
  intervalos em que não conseguiu vigiar.
- **RF-013**: Nenhum clipe gerado ao vivo DEVE ser considerado pronto para postar sem aprovação do
  usuário (princípio I).
- **RF-014**: O sistema DEVE vigiar lives da Twitch. [PRECISA ESCLARECER: Kick e YouTube Live também
  nesta spec, ou só Twitch agora?]
- **RF-015**: A vigilância DEVE rodar enquanto o computador do usuário estiver ligado.
  [PRECISA ESCLARECER: basta rodar com o Mac ligado, ou é preciso vigiar 24/7 mesmo com o Mac
  desligado? 24/7 exige servidor pago e uma justificativa pelo princípio IV.]

### Entidades

- **Canal vigiado**: estende o `Canal` do MVP1; plataforma, link, ativo, campanha/autorização
  (link ou nota), prioridade, limite de clipes por hora, status atual.
- **Sessão de live**: uma transmissão de um canal; início, fim, título, VOD associado, intervalos sem
  vigilância.
- **Momento**: um pico detectado numa sessão; instante, força, se virou clipe ou o motivo de não ter
  virado.
- **Aviso**: um envio ao celular; clipes incluídos, horário, se foi entregue.

## Critérios de sucesso

- **CS-001**: Do momento na live até o clipe estar em "Para revisar": menos de 10 min.
- **CS-002**: Do clipe em revisão até o aviso chegar no celular: menos de 1 min.
- **CS-003**: Zero clipes gerados de canais fora da lista ou sem campanha/autorização.
- **CS-004**: Custo adicional desta spec abaixo de US$15/mês vigiando 5 canais por 4 h/dia.
- **CS-005**: Pelo menos 1 de cada 3 clipes gerados ao vivo é aprovado pelo usuário após a primeira
  semana de ajuste.
- **CS-006**: Vigiar 3 lives ao mesmo tempo sem atrasar o processamento além do CS-001.

## Fora do escopo

- Publicar automaticamente no TikTok, YouTube ou Instagram (spec futura)
- Enviar clipes aprovados para um Drive (spec futura)
- Descobrir streamers novos sozinho ou buscar campanhas novas nos marketplaces
- Login/senha no site
- Clipar canais que não estão na lista

## Esclarecimentos

- 2026-11-11 P: Revisar só em casa ou também fora? → R: Também fora de casa, com acesso remoto seguro.
- 2026-11-11 Proposta (a confirmar com o usuário): publicação fica fora desta spec; a prioridade é
  velocidade antes de 19/nov e publicação vira spec própria.
