# Spec: Clipador sob demanda (MVP1)

**Branch**: `feat/mvp1` · **Criada**: 2026-11-11 · **Status**: Implementada

> O quê e por quê. Como está implementado: [plan.md](./plan.md). Andamento: [tasks.md](./tasks.md).

## Contexto

Conta de clipes de GTA VI no TikTok, YouTube Shorts e Instagram Reels, com renda vinda de campanhas
de clipping. O lançamento (19/nov/2026) é o maior pico de clipes de games da década; ganha quem
posta primeiro o momento que viralizou. O usuário não quer assistir lives nem editar: só escolher
o que entra e revisar o que sai.

## Histórias de usuário

### História 1 — Gerar vários clipes de um VOD (Prioridade: P1)

O usuário cola o link de um VOD longo e recebe vários clipes verticais prontos dos momentos mais
fortes, sem assistir o VOD.

**Por que esta prioridade**: VODs de lives de GTA são a principal fonte de momentos com campanha ativa.

**Teste independente**: enviar um VOD de 1 h ou mais e receber ≥ 3 clipes em pontos diferentes do vídeo.

**Cenários de aceite**:
1. **Dado** um link de VOD da Twitch, **quando** o usuário envia com limite 20, **então** recebe até 20
   clipes de momentos distintos, ordenados pela força do momento.
2. **Dado** dois picos a menos de 60 s um do outro, **quando** o sistema escolhe momentos, **então**
   gera um clipe só para os dois.
3. **Dado** um VOD sem chat disponível, **quando** processa, **então** usa outros sinais e ainda gera clipes.

### História 2 — Aceitar qualquer origem de vídeo (Prioridade: P1)

O usuário envia link do YouTube, VOD ou clipe da Twitch, Kick, link direto de `.mp4` ou sobe um
arquivo, sem precisar dizer o tipo.

**Teste independente**: enviar um link de cada tipo e todos serem processados.

**Cenários de aceite**:
1. **Dado** vários links, um por linha, **quando** envia, **então** cada link vira um envio separado na fila.
2. **Dado** um clipe curto (≤ 90 s), **quando** processa, **então** o vídeo inteiro vira um clipe, sem procurar momentos.
3. **Dado** um vídeo do YouTube, **quando** processa, **então** usa os trechos "mais repetidos" e as
   minutagens citadas nos comentários para achar momentos.

### História 3 — Revisar e aprovar (Prioridade: P1)

O usuário vê cada clipe com título, gancho, hashtags, nota e alerta de spoiler; aprova, rejeita,
edita o título, baixa o vídeo e copia o texto do post.

**Teste independente**: abrir um envio pronto, aprovar um clipe e baixar o arquivo.

**Cenários de aceite**:
1. **Dado** um clipe em revisão, **quando** o usuário aprova, **então** ele sai de "Para revisar" e
   aparece em "Aprovados".
2. **Dado** um clipe marcado como spoiler, **quando** aparece na revisão, **então** tem destaque visual
   e o motivo.
3. **Dado** um clipe aprovado por engano, **quando** o usuário clica em desfazer, **então** volta para revisão.

### História 4 — Clipe com cara própria (Prioridade: P2)

Cada clipe sai em 9:16 com webcam do streamer em cima e jogo embaixo (ou jogo sobre fundo desfocado
quando não há webcam), legenda palavra a palavra, gancho nos primeiros segundos e crédito ao criador.

**Cenários de aceite**:
1. **Dado** um canal novo, **quando** o primeiro clipe é gerado, **então** a posição da webcam é
   detectada e reaproveitada nos próximos clipes desse canal.
2. **Dado** uma detecção errada, **quando** o usuário pede para detectar de novo, **então** o próximo
   processamento refaz a detecção.

### Casos de borda

- Download bloqueado (YouTube pedindo login): o envio fica com erro legível e pode ser reprocessado
  depois de configurar cookies.
- App fechado no meio de um envio: ao abrir de novo, o envio volta para a fila e continua.
- Vídeo sem fala: o clipe sai sem legenda, só com gancho e crédito.
- Nenhum sinal encontrado: o sistema avalia fatias espaçadas do vídeo.

## Requisitos

### Requisitos funcionais

- **RF-001**: O sistema DEVE aceitar links do YouTube, Twitch (VOD e clipe), Kick, `.mp4` direto e upload de arquivo.
- **RF-002**: O sistema DEVE identificar o tipo de origem sozinho.
- **RF-003**: O sistema DEVE encontrar momentos fortes combinando sinais gratuitos (chat, volume do
  áudio, "mais repetidos", minutagens em comentários) antes de usar qualquer modelo pago.
- **RF-004**: Cada sinal DEVE ser comparado com o próprio vídeo (canal grande e pequeno funcionam sem ajuste manual).
- **RF-005**: O sistema DEVE baixar apenas os trechos candidatos, não o vídeo inteiro.
- **RF-006**: O usuário DEVE poder definir o máximo de clipes por envio (padrão 20, até 100).
- **RF-007**: Um modelo barato DEVE fazer a triagem de todos os candidatos; um modelo melhor DEVE
  rodar só nos aprovados pela triagem.
- **RF-008**: Cada clipe DEVE ter entre 15 e 60 s, título, gancho, descrição com crédito e 3 a 6 hashtags.
- **RF-009**: O sistema DEVE marcar suspeita de spoiler da história usando uma lista editável pelo usuário.
- **RF-010**: Nenhum clipe DEVE ser considerado pronto para postar sem aprovação do usuário.
- **RF-011**: O sistema DEVE rodar no PC do usuário, sem servidor.
- **RF-012**: Os arquivos brutos baixados DEVEM ser apagados ao fim de cada envio.

### Entidades

- **Envio (job)**: uma origem enviada; tipo, título, criador, duração, limite de clipes, status e etapa atual.
- **Clipe**: um momento de um envio; início/fim, notas, textos, spoiler, status e arquivo final.
- **Canal**: um criador; posição da webcam (ou ausência dela).

## Critérios de sucesso

- **CS-001**: Um VOD de 4 h gera clipes prontos para revisão em menos de 60 min num notebook sem GPU.
- **CS-002**: Custo médio de modelo abaixo de US$0,03 por clipe gerado.
- **CS-003**: Custo mensal total abaixo de US$15 no uso médio (5 clipes da Twitch, 3 vídeos do YouTube,
  2 VODs e 1 arquivo por dia).
- **CS-004**: Pelo menos metade dos clipes em revisão é aprovada pelo usuário após a primeira semana de ajuste.

## Fora do escopo

- Monitorar lives ao vivo
- Buscar vídeos novos de canais automaticamente
- Postar automaticamente nas redes
- Notificação no celular
- Login/senha no site (roda local)

## Esclarecimentos

- 2026-11-11 P: Rodar em servidor ou local? → R: Local (custo do servidor não compensa no MVP1).
- 2026-11-11 P: Qual provedor de LLM? → R: OpenAI, em dois níveis (simples e complexo), trocável por configuração.
- 2026-11-11 P: Telegram ou site para revisar? → R: Site.
- 2026-11-11 P: Um clipe por VOD ou vários? → R: Vários, com limite configurável.
