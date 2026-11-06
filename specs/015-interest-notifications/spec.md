# Feature Specification: Notificações por Interesse (Entrega por Polling)

**Feature Branch**: `015-interest-notifications`

**Created**: 2026-11-06

**Status**: Draft

**Input**: User description: "Implementar Notificações por Interesse do PassaNorte (backend FastAPI, módulo notifications) no monolito modular. Requisitos: RF37 — turista se inscreve em interesses específicos para receber notificações relacionadas e também cancela a inscrição; quando um NOVO evento (spec 008), novo ponto turístico (spec 007) ou nova rota (spec 009) é cadastrado, gerar notificações para os turistas cujos interesses casem com as categorias do item (RF25 como fonte de interesses). No monolito, a geração entra pelo serviço público de notifications (create_notification_for_interests) chamado pelos módulos emissores via interface de serviço — nunca escrevendo direto na tabela emissor; entrega ao app via endpoint GET de notificações não lidas/marcar como lida (polling), sem push nesta fase (RNF15 baixo custo). Conteúdo da notificação deve ser apresentável (título, descrição, tipo, referência ao item com ID para deep link). i18n-ready: título/descrição armazenados com possibilidade de localização futura (RNF16 baixo custo). Endpoints sob a tag "Notifications" da spec 006. Critério: turista com interesse 'gastronomia' recebe notificação quando admin cria evento/ponto/rota com categoria 'gastronomia' e NÃO recebe quando categoria não casa; teste de marcar como lida; teste de cancelamento de inscrição."

**Requisitos de origem**: RF37 (Notificações por Interesse), RF25 (Interesses cadastrados — fonte da casagem), RNF15 (Gratuitidade/ferramentas open source — sem push), RNF16 (i18n-ready da API), constituição (regra 5 — serviço público inter-domínios).

## Clarifications

### Session 2026-11-06

- Q: A inscrição de notificações deve ser uma seleção independente do
  turista ou reaproveitar os interesses já cadastrados no perfil dele
  (RF25)? → A: Seleção independente — tabela/canal próprio do módulo
  notifications, gerenciado por endpoints deste módulo; o app pode
  pré-preencher na primeira visita à tela, mas a base é separada e a
  inscrição não altera o perfil nem vice-versa (confirmado pelo usuário —
  opção A).

- Q: Quem compõe o título e a descrição do texto da notificação? → A:
  Centralizado — o módulo notifications monta o texto a partir dos dados
  recebidos do emissor (ex.: "Novo evento: <nome>" + descrição curta do
  item); emissores passam apenas os dados do item, o texto fica
  consistente e pronto para localização futura (confirmado pelo usuário —
  opção A).

- Q: Como casar o interesse do turista com uma nova rota, que não possui
  categorias próprias no modelo atual? → A: A rota herda as categorias
  dos pontos que a compõem (rota → pontos → categorias): os interessados
  são os turistas inscritos em qualquer categoria dos spots da rota;
  rota sem pontos ou sem categorias deduzíveis — sem notificação
  (confirmado pelo usuário — opção A).

- Q: Como as listagens de notificações devem limitar o volume devolvido ao
  app (sem expurgo nesta fase)? → A: Limite fixo, mais recentes — as
  listas devolvem as N notificações mais recentes com padrão fixo
  documentado no planejamento (sem paginação nesta fase); o contador de
  não lidas guia o polling do app (confirmado pelo usuário — opção A).

- Q: O contador de notificações não lidas para o polling do app deve ser
  um endpoint próprio ou derivado da listagem? → A: Endpoint próprio —
  consulta barata devolvendo o total de não lidas do turista, que guia o
  polling; a listagem continua separada (confirmado pelo usuário — opção
  A).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Turista se inscreve e cancela inscrição em interesses (Priority: P1)

Um turista autenticado escolhe quais categorias de interesse o notificarão.
Ele seleciona uma ou mais categorias válidas do catálogo configurado da
cidade e, quando quiser, cancela a inscrição de uma ou mais delas. A
inscrição é idempotente (inscrever-se duas vezes na mesma categoria não
cria duplicidade) e o cancelamento de uma categoria não inscrita não falha
com erro — apenas confirma o estado ("não inscrito").

**Why this priority**: É o mecanismo que decide QUEM recebe notificações;
sem inscrição, nada nesta feature existe a entregar (RF37).

**Independent Test**: Cadastrado um turista, inscrever-se em categorias,
verificar a seleção vigente, cancelar uma delas e re-verificar.

**Acceptance Scenarios**:

1. **Given** turista autenticado, **When** ele se inscreve em um conjunto de categorias válidas, **Then** a inscrição fica registrada e a leitura da inscrição devolve exatamente essas categorias.
2. **Given** turista já inscrito em "gastronomia", **When** ele se inscreve novamente em "gastronomia", **Then** o resultado é idempotente (uma única entrada, sem erro).
3. **Given** turista inscrito em várias categorias, **When** ele cancela a inscrição de uma delas, **Then** apenas essa sai da seleção e as demais permanecem.
4. **Given** inscrição em uma categoria que não existe no catálogo configurado, **When** a requisição é feita, **Then** o sistema rejeita com erro de validação nomeando a categoria inválida.

---

### User Story 2 - Novo cadastro de item gera notificações para interessados (Priority: P1)

Quando o administrador cadastra um NOVO evento, ponto turístico ou rota
turística, o sistema gera uma notificação para cada turista inscrito em
pelo menos uma das categorias do item. A notifiable entrega acontece por
poling: o turista consulta suas notificações pelo aplicativo Passaporte.

**Why this priority**: É a entrega de valor central da feature — o conteúdo
que chega ao turista (RF37).

**Independent Test**: Com um turista inscrito em "gastronomia", criar um
item com categoria "gastronomia" (e outro com categoria sem casamento) e
verificar quem recebe e quem deixa de receber.

**Acceptance Scenarios**:

1. **Given** turista inscrito em "gastronomia", **When** o administrador cadastra um novo evento com categoria "gastronomia", **Then** o turista passa a ter uma notificação não lida sobre esse evento (título, descrição, tipo, referência ao item para deep link).
2. **Given** o mesmo turista, **When** o administrador cadastra um novo ponto turístico (ou nova rota) com categoria "gastronomia", **Then** surge notificação equivalente sobre o novo item, do tipo correspondente.
3. **Given** turista inscrito em "gastronomia", **When** um novo item só tem categorias que não casam (ex.: "natureza"), **Then** ninguna notificação é criada para ele.
4. **Given** vários turistas inscritos, parte em "gastronomia" e parte em "natureza", **When** um novo item com "gastronomia"+"arte" é cadastrado, **Then** somente os inscritos na interseção (gastronomia) recebem — um turista recebe UMA notificação por item, mesmo que casem em mais de uma categoria.
5. **Given** um item novo sem nenhum turista interessado, **When** o cadastro acontece, **Then** nenhuma notificação é criada e o cadastro do item não falha nem retarda.

---

### User Story 3 - Turista consulta e marca notificações como lidas (Priority: P1)

O turista consulta pelo aplicativo suas notificações (não lidas por
padrão), vê título, descrição, tipo e a referência para navegar ao item
(deep link), e marca como lida — individualmente ou todas de uma vez.
Notificações lidas deixam de aparecer na lista de não lidas.

**Why this priority**: Fechamento do ciclo de entrega por polling — sem
marcação de leitura, a lista de "não lidas" cresce indeterminadamente.

**Independent Test**: Gerar notificações para um turista, consultar não
lidas, marcar uma e depois todas, re-consultar.

**Acceptance Scenarios**:

1. **Given** turista com 3 notificações não lidas, **When** ele consulta suas não lidas, **Then** recebe as 3 com o conteúdo apresentável (título, descrição, tipo, identificador do item e o tipo de referência para deep link).
2. **Given** 3 notificações não lidas, **When** o turista marca uma como lida, **Then** a lista de não lidas passa a ter 2 e consultá-las nunca mais retorna a marcada (a marcação é persistente e não reabre).
3. **Given** notificações não lidas, **When** o turista marca todas de uma vez, **Then** a lista de não lidas fica vazia.
4. **Given** duas notificações, **When** o turista consulta o histórico completo (lidas + não lidas), **Then** recebe ambas com o respectivo estado de leitura (a lista de não lidas é um filtro da mesma base).
5. **Given** turista sem notificações, **When** consulta não lidas, **Then** recebe lista vazia com sucesso.

---

### Edge Cases

- **Inscrição idempotente**: inscrever-se duas vezes na mesma categoria
  resulta em uma única inscrição (sem duplicidade, sem erro).
- **Cancelamento sem inscrição prévia**: cancelar uma categoria inativa
  não falha — o estado final ("não inscrito") é confirmado.
- **Categoria inválida**: inscrição referindo categoria fora do catálogo
  configurado é rejeitada com erro de validação nomeando a categoria.
- **Emissão sem interessados**: cadastro de item sem nenhum turista
  inscrito nas categorias não cria nada e não afeta o cadastro do item.
- **Notificação de item removido depois**: a notificação permanece no
  histórico do turista como registro recebido (conteúdo textual
  autorcontido); a navegação (deep link) pode não resolver mais o item —
  o aplicativo trata item ausente com sua própria tela de erro.
- **Casagem em várias categorias**: um item com várias categorias gera
  UMA notificação por turista (não uma por categoria casada).
- **Isolamento entre turistas**: um turista nunca vê notificações de
  outro (a leitura é sempre do próprio perfil autenticado).
- **Item duplicado no emissor**: re-cadastro/edição de um item existente
  NÃO gera nova notificação — apenas a criação de itens novos emite
  (decisão de escopo: sem notificação de atualização nesta fase).

## Requirements *(mandatory)*

### Functional Requirements

**Controle de acesso e contrato**

- **FR-001**: Todos os endpoints de turista do módulo MUST exigir
  autenticação de turista (funcionário/administrador recebem 403;
  anônimo, 401).
- **FR-002**: Todos os endpoints MUST ser agrupados sob a tag
  "Notifications" do registro central de tags (spec 006); nenhum arquivo
  de rota escreve string de tag fora do registro central.
- **FR-003**: Toda operação de falha MUST usar o payload de erro único da
  spec 005; os schemas HTTP herdam o contrato base (camelCase, entrada
  estrita).

**Inscrição (RF37)**

- **FR-004**: O turista MUST poder se inscrever em um conjunto de
  categorias (substituindo integralmente a seleção anterior, mesmo padrão
  da seleção de interesses do perfil — RF25) e ler a seleção vigente.
- **FR-005**: A inscrição MUST ser idempotente por categoria e validada
  contra o catálogo configurado da cidade (portabilidade, RNF06).
- **FR-006**: O turista MUST poder cancelar a inscrição de uma categoria
  individualmente; cancelar categoria sem inscrição prévia não é erro.
- **FR-007**: A inscrição de notificações é independente dos interesses
  do perfil (RF25); cadastra-la não altera o perfil e vice-versa.

**Geração inter-módulos (RF37 + regra 5 da constituição)**

- **FR-008**: Quando um novo evento, ponto turístico ou rota é cadastrado,
  o módulo emissor (especificações 008, 007 e 009) MUST acionar o serviço
  público de notifications — nunca escrevendo diretamente em tabelas de
  outro módulo; a notificação é gerada para cada turista inscrito em
  ao menos uma das categorias do item. Para a rota, cujo modelo não tem
  categorias próprias, a casagem usa as categorias herdadas dos pontos
  que a compõem (decisão Q3 — rota sem pontos ou sem categorias:
  sem notificação).
- **FR-009**: Um turista que casa em várias categorias de um mesmo item
  MUST receber uma única notificação por item (dedupe por turista×item).
- **FR-010**: A geração MUST derivar a lista de interessados das
  inscrições reais (cruzamento de dados reais) — nenhuma lista estimada
  ou padrão.
- **FR-011**: A emissão de notificação não pode bloquear nem reverter o
  cadastro do item: falha da geração é observabilidade no backend
  (best-effort), mantendo o cadastro do item bem-sucedido.

**Entrega por polling**

- **FR-012**: O turista MUST poder consultar suas notificações não lidas
  (padrão) e o histórico completo (filtro), ordenadas do mais recente;
  as listas devolvem as N notificações mais recentes com padrão fixo
  documentado (decisão Q4 — sem paginação nesta fase).
- **FR-013**: O turista MUST poder marcar como lida uma notificação
  individual ou todas de uma vez; marcação é persistente e idempotente.
- **FR-013a**: O turista MUST dispor de um endpoint de contador que
  devolve o total de suas notificações não lidas (consulta barata que
  guia o polling do app)
- **FR-014**: Cada notificação MUST conter: título, descrição, tipo do
  item que gerou a notificação (evento/ponto/rota), o identificador do
  item (para deep link) e o instante de criação — conteúdo autossuficiente
  e apresentável no app sem consultas extra; o título/descrição são
  montados centralmente pelo módulo notifications a partir dos dados do
  item (decisão Q2), e cada emissor fornecerá apenas os dados (nome,
  descrição curta, categorias).
- **FR-015**: Título e descrição MUST ser armazenados de forma
  i18n-ready (RNF16): o campo está pronto para localização futura (a
  entrega nesta fase usa o idioma padrão da cidade, sem lógica de
  tradução implementada).

**Fronteira de domínio e integridade**

- **FR-016**: A base de notificações (inscrições + notificações) pertence
  exclusivamente ao módulo notifications; outros módulos tocam apenas via
  o serviço público de notificações (constituição, regra 5).
- **FR-017**: Todos os dados citados (inscrições, categorias do item,
  emissores) derivam de dados reais registrados; nenhuma notificação
  sintética.

### Key Entities *(include if data involved)*

- **Inscrição de notificação (NotificationSubscription)**: associação
  turista×categoria (única por par), criada/cancelada pelo próprio
  turista; catálogo de categorias é o configurado da cidade (RNF06).
- **Notificação (Notification)**: registro único por turista×item
  recebido, com instante, título, descrição, tipo
  (evento/ponto/rota), identificador do item (deep link) e estado de
  leitura (não lida/lida, com instante da leitura).
- **Emissor (dados existentes)**: evento (spec 008) e ponto turístico
  (spec 007) com suas categorias; rota turística (spec 009) herdando as
  categorias via pontos que a compõem (Q3) — entradas que disparam a
  geração; o módulo notifications não os cria nem os edita.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Com turistas inscritos em categorias distintas, 100% das
  notificações geradas por um item novo correspondem exatamente aos
  inscritos nas categorias do item (sem falso negativo ou falso
  positivo), com uma única notificação por turista×item.
- **SC-002**: Um turista inscrito em uma categoria passa a ver a
  notificação do novo item na primeira consulta de polling após o
  cadastro (uma viagem de ida/volta do app), sem push.
- **SC-003**: Marcação de leitura: 100% das marcações refletem no
  conteúdo das listas (não lidas diminuem; lidas permanecem lidas em
  qualquer consulta posterior).
- **SC-004**: Cancelamento de inscrição interrompe notificações futuras
  daquela categoria a partir do próximo item cadastrado (as anteriores
  permanecem no histórico).
- **SC-005**: Com 1.000 turistas e 100 itens novos com casamentos
  variados, cada consulta de notificações responde em tempo hábil para o
  app (abaixo de 2 segundos), com agregação/leitura por conjunto e
  índices adequados.
- **SC-006**: Nenhum módulo emissor escreve fora de seu domínio — o
  acionamento é unicamente via serviço público de notifications
  (verificável pelo gate de fronteiras).

## Assumptions

- **Inscrição independente do perfil**: resolução registrada em
  `## Clarifications` (Q1) — seleção própria do canal, gerenciada por
  endpoints deste módulo; a extensão a todos os turistas cadastrados
  ficaria para uma fase futura.
- **Inscrição por substituição integral** (mesmo padrão da seleção de
  interesses do perfil, RF25/FR-004) — sem endpoint incremental por
  categoria além do cancelar uma (FR-006).
- **Sem push**: entrega somente por polling (RNF15); o app controla o
  ritmo do polling.
- **Sem notificação de edição/remoção**: apenas criação de itens novos
  emite (edge case "item duplicado").
- **i18n**: campos armazenados prontos para localização futura (RNF16);
  nesta fase o conteúdo é apresentado em um único idioma da cidade.
- **Deep link**: a referência é o par tipo+identificador do item; o
  formato da URL final do app é responsabilidade do cliente.
- **Retenção das notificações**: sem política de expurgo nesta fase
  (YAGNI); as listagens aplicam o limite fixo de FR-012 (decisão Q4), e
  paginação/expurgo podem ser adicionados por fase futura quando o volume
  demonstrar necessidade.
