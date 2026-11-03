# Feature Specification: Geo-Visitation (Marcação de Visitação Geolocalizada)

**Feature Branch**: `011-geo-visitation`

**Created**: 2026-11-03

**Status**: Draft

**Input**: User description: "Implementar Visitação Geolocalizada do PassaNorte (backend FastAPI, módulo visitation). Requisitos: RF31 — turista aciona 'marcar visitação' estando em um ponto turístico cadastrado, enviando coordenadas GPS atuais e o ponto em questão; RF32 — o sistema valida a presença por Haversine entre coordenadas do GPS e do ponto, considerando raio de tolerância configurável por ponto turístico (default global em settings), sem falsos positivos evidentes; RF33 — após validação, grava status 'visitado' do ponto para o turista, com registro imutável de visitação (timestamp, coordenadas validadas); RF34 — após gravar, chama o serviço público de gamificação que atualiza progresso das rotas vinculadas (interface da spec 009) — nunca escreve diretamente nas tabelas de outro módulo (fronteira de domínio do monolito modular). Repetição de visitação não gera novas atualizações de progresso (idempotente) mas pode ser registrada como visita adicional. RNF14 — precisão geoespacial. Todos os endpoints deste módulo agrupados sob a tag "Visitation" do registro central de tags da spec 006. Critério de aceitação: testes unitários da fórmula de Haversine (casos exatos: dentro do raio, fora, borda, antípodas); teste de integração visitação válida → status gravado → progresso de rota atualizado; teste de visitação fora do raio rejeitada (409/422); teste de idempotência de visita repetida."

## Clarifications

### Session 2026-11-03

- Q: Como o status "visitado" de um ponto para um turista deve ser determinado pela API de consulta (US4)? → A: Derivado do histórico — não há registro/flag de status separado; consultas deduzem "visitado" da existência de qualquer visitação válida turista↔ponto (o registro imutável é a única fonte de verdade).
- Q: Qual deve ser o valor padrão global do raio de tolerância, em metros, usado quando o ponto turístico não define um raio próprio (FR-003)? → A: 100 metros — cobre a margem de erro típica de GPS urbano (5–30 m) com folga, sem tornar a validação fraudável.
- Q: A validação de presença deve considerar apenas as coordenadas GPS informadas, ou também a margem de erro estimada pelo aparelho do turista (FR-002, RNF14)? → A: Só coordenadas — a fronteira compara apenas lat/lng informada com o raio de tolerância; margem de precisão do aparelho fica fora do escopo desta feature (o raio global já absorve a imprecisão típica).
- Q: Deve existir qualquer limite de frequência para o mesmo turista marcar visitação no mesmo ponto dentro de um curto intervalo de tempo (FR-006)? → A: Sem throttle nesta fase — toda marcação válida grava uma visita no histórico imutável; nenhuma verificação de intervalo mínimo (YAGNI).
- Q: Cada marcação de visitação (aceita ou rejeitada) deve deixar algum rastro estruturado de observabilidade no backend, e em que nível (RNF14)? → A: Só rejeitadas em log — toda tentativa rejeitada por distância fora do raio gera um log estruturado no backend (diagnóstico de possível fraude de localização); nada persistido no banco para tentativas rejeitadas, e nenhuma auditoria especial para marcações aceitas (não são ações administrativas).
- Q: Se o mesmo turista enviar duas marcações quase simultâneas para o mesmo ponto (ambas chegam antes de qualquer resposta), o que o sistema deve garantir quanto ao progresso de rota (FR-009)? → A: Idempotência simples — sem mecanismo de lock explícito nesta fase; a proteção contra duplicação de progresso é a mesma das visitas repetidas sequenciais (atualização de progresso disparada somente pela primeira visita). Um mecanismo de exclusão forte em corrida seria complexidade prematura (YAGNI).
- Q: As coordenadas GPS validadas gravadas no registro imutável de visitação devem ser armazenadas criptografadas (como CPF/telefone via criptografia de campo), ou em texto claro (FR-006)? → A: Texto claro — coordenada de visitação é dado operacional de baixo risco (não identifica sozinha o indivíduo e é sempre vinculada ao turista por referência), fora do rol de campos sensíveis da constituição (CPF, passaporte, telefone, e-mail); não é criptografada e não usa primitivas de core/crypto.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Turista marca visitação em um ponto presente (Priority: P1)

Um turista autenticado chega fisicamente a um ponto turístico cadastrado,
aciona a opção "marcar visitação" no aplicativo Passaporte, e o aplicativo
envia sua posição GPS atual junto com o ponto em questão. O sistema confirma
que a posição informada corresponde de fato àquele ponto (dentro do raio de
tolerância) e, confirmada a presença, grava o ponto como "visitado" para
aquele turista em um registro de visitação permanente.

**Why this priority**: É o núcleo do requisito RF31/RF32/RF33 — sem a
capacidade de marcar uma visitação validada, nenhuma outra parte do fluxo
(gamificação, progresso de rotas, ranking) funciona. É o menor produto
viável isolado.

**Independent Test**: Pode ser testado integralmente enviando coordenadas
GPS de um ponto cadastrado e verificando que o status "visitado" fica
persistido para o turista — sem depender de gamificação, eventos ou
dashboards.

**Acceptance Scenarios**:

1. **Given** um turista autenticado e um ponto turístico cadastrado com
   coordenadas válidas, **When** o turista envia coordenadas GPS cuja
   distância (Haversine) até o ponto é menor que o raio de tolerância, **Then**
   o sistema grava a visitação com status "visitado" para aquele turista e
   responde com sucesso contendo o registro de visitação (timestamp e
   coordenadas validadas).
2. **Given** um turista autenticado e um ponto turístico cadastrado que tem
   um raio de tolerância próprio configurado, **When** a posição GPS enviada
   está dentro desse raio próprio (mesmo que estivesse fora do raio padrão
   global), **Then** a presença é validada e a visitação é gravada.
3. **Given** um ponto turístico sem raio próprio configurado, **When** o
   turista envia posição GPS, **Then** o sistema usa o raio de tolerância
   padrão global para validar a presença.

---

### User Story 2 - Visitante fora do ponto é rejeitado (Priority: P1)

Um turista (ou uma tentativa maliciosa de fraude) aciona "marcar visitação"
com coordenadas GPS que, ao serem comparadas com as coordenadas cadastradas
do ponto turístico, resultam em distância maior que o raio de tolerância.
O sistema rejeita a tentativa sem gravar nenhum status, sem registrar
visitação e sem alterar progresso em rotas.

**Why this priority**: É a contraparte de confiabilidade de RF32/RNF14 —
sem rejeitar presenças irreais, o sistema fica sujeito a falsos positivos
evidentes e toda a gamificação fica fraudável. Deve ser resolvido junto
com a US1 para o fluxo ter credibilidade.

**Independent Test**: Pode ser testado enviando coordenadas GPS claramente
distantes de um ponto cadastrado (por exemplo, a outro lado da cidade) e
verificando que a operação falha com erro de conflito e que nenhum
registro de visitação é criado.

**Acceptance Scenarios**:

1. **Given** um turista autenticado e um ponto turístico cadastrado, **When**
   o turista envia coordenadas GPS cuja distância (Haversine) até o ponto é
   maior que o raio de tolerância vigente (próprio ou global), **Then** o
   sistema rejeita a operação com erro de conflito (HTTP 409) indicando
   que a posição não corresponde ao ponto, grava um log estruturado da
   tentativa rejeitada (observabilidade de possível fraude), e nenhum
   dado de visitação é persistido.
2. **Given** um ponto turístico com raio próprio pequeno (por exemplo 25 m),
   **When** o turista envia posição GPS a 80 m do ponto, **Then** a operação
   é rejeitada mesmo estando dentro do raio global padrão.

---

### User Story 3 - Progresso das rotas vinculadas é atualizado (Priority: P2)

Após uma visitação validada e gravada, o sistema chama o serviço público de
gamificação (a interface de serviço da spec 009) para atualizar o progresso
de todas as rotas em andamento vinculadas àquele ponto — para o turista que
visitou. O módulo de visitação nunca escreve diretamente nas tabelas de
outro domínio; toda escrita vai pela função de serviço do dono dos dados.

**Why this priority**: A integração RF34 entrega o valor de gamificação
(assinaturas de rota que reagem à visitação), mas depende da US1 — só é
acionada depois de uma visitação válida gravada. É o segundo passo do
monolito modular, mantendo a fronteira de domínio.

**Independent Test**: Pode ser testado com uma visitação válida em um ponto
que pertence a uma rota com inscrição "em andamento" de um turista,
verificando que, após gravar a visitação, o progresso da inscrição sobe de
forma refletida na visão de progresso do turista — sem que visitation
toque qualquer tabela de gamification.

**Acceptance Scenarios**:

1. **Given** um turista inscrito em uma rota "em andamento" que contém o
   ponto P, **When** o turista marca visitação válida em P, **Then** o
   progresso da inscrição sobe (P passa a contar como ponto visitado na
   rota) e o sistema responde com a visitação gravada.
2. **Given** um turista marcando visitação em um ponto que não pertence a
   nenhuma rota em andamento dele, **Then** a marcação em si é gravada sem
   efeito de progresso de rota — a chamada ao serviço de gamificação não
   precisa falhar nem gerar erro.
3. **Given** um turista que já registrou a visitação do ponto P antes,
   **When** ele marca visitação novamente em P, **Then** o registro de
   visita adicional é gravado (histórico imutável preservado), mas o
   progresso de rota não é recalculado em duplicidade — a marcação anterior
   já contou o progresso (idempotente).

---

### User Story 4 - Histórico de visitações do turista (Priority: P3)

Um turista autenticado consulta suas visitações registradas, de forma que o
aplicativo Passaporte consegue exibir quais pontos ele já visitou (status
"visitado") e quando — mantendo o histórico imutável (timestamp e
coordenadas validadas de cada visita).

**Why this priority**: É camada de consulta sobre o fluxo principal —
entrega valor de UX, mas não é necessária para a operação de marcação.

**Independent Test**: Pode ser testado registrando duas ou mais visitações
para o mesmo turista e verificando a listagem completa e consistente com o
que foi gravado.

**Acceptance Scenarios**:

1. **Given** um turista com pelo menos uma visitação registrada, **When**
   ele consulta sua lista de pontos visitados, **Then** a listagem inclui
   todos os pontos com status "visitado" e o timestamp de cada visita.
2. **Given** um turista sem nenhuma visitação, **When** ele consulta sua
   lista, **Then** a listagem volta vazia, sem erros.

---

### Edge Cases

- O que acontece quando o turista envia coordenadas GPS exatamente na borda
  do raio (distância igual ao raio)? → É considerada dentro do raio
  (distância <= raio) e a visitação deve ser aceita; o teste unitário deve
  cobrir o caso de borda explicitamente.
- O que acontece quando o turista envia coordenadas no lado oposto da Terra
  (antípodas do ponto)? → A distância de Haversine dá o diâmetro máximo da
  Terra; a visitação é rejeitada, e o teste unitário deve cobrir esse caso
  exato (sem falso positivo por problemas de módulo/overflow de ângulo).
- O que acontece quando o ponto turístico informado não existe ou está
  inativo? → A marcação é rejeitada com erro de não encontrado (HTTP 404),
  e nenhuma escrita acontece.
- O que acontece quando o ponto turístico não tem coordenadas válidas? →
  A marcação é rejeitada com erro de conflito (HTTP 409), pois é
  impossível calcular distância.
- O que acontece quando o mesmo ponto é re-visitado (visita repetida)?
  → Uma nova entrada imutável de visitação é gravada (histórico), porém a
  atualização de progresso de rota é idempotente — não incrementa
  progresso nem contabiliza pontos de rota duas vezes. Sem limite de
  frequência nesta fase (esclarecido: sem throttle).
- O que acontece se as coordenadas GPS do turista forem inválidas (ex.:
  latitude > 90, longitude > 180, valores nulos)? → Rejeitadas por validação
  de schema com 422, antes de qualquer cálculo de distância.
- O que acontece se o serviço de gamificação falhar ou estiver
  indisponível no momento da marcação? → Política padrão: tudo acontece
  de forma consistente — se a atualização de progresso não conseguir ser
  registrada, a operação inteira falha e nenhuma visitação é gravada; o
  turista tenta de novo sem duplicar progresso. A definição técnica fina
  da transacionalidade fica no /speckit-plan.
- O que acontece quando coordenadas idênticas às do ponto são enviadas
  (distância 0)? → Aceitas: distância zero é menor ou igual ao raio.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001** (RF31): O sistema MUST expor endpoint autenticado para o
  turista marcar visitação em um ponto turístico, recebendo suas
  coordenadas GPS atuais (latitude WGS-84, longitude WGS-84) e o
  identificador do ponto turístico.
- **FR-002** (RF32): O sistema MUST validar a presença computando a
  distância de Haversine (RNF14) entre as coordenadas GPS enviadas e as
  coordenadas cadastradas do ponto, em graus decimais WGS-84, e comparando
  com o raio de tolerância vigente do ponto.
- **FR-003** (RF32): O raio de tolerância MUST ser configurável por ponto
  turístico; quando o ponto não tiver raio próprio, o sistema MUST usar o
  raio de tolerância global padrão definido na configuração do backend.
- **FR-004** (RF32/RNF14): O sistema MUST rejeitar a marcação de visitação
  quando a distância computada exceder o raio de tolerância, com erro 409
  (coordenadas válidas, porém sem correspondência física com o ponto),
  sem gravar nenhum dado; a falha deve ser observada com o payload único
  de erro do contrato (errorCode / message / details). Coordenadas
  inválidas (fora da faixa WGS-84) continuam recebendo 422, conforme
  FR-013.
- **FR-005** (RF32/RNF14): O sistema MUST evitar falsos positivos evidentes:
  o cálculo não deve aceitar posições claramente distantes (ex.: lado
  oposto da cidade) e o teste de unidade da fórmula deve cobrir casos
  exatos — dentro do raio, fora, borda (distância igual ao raio, aceito),
  antípodas (distância ≈ diâmetro da Terra, rejeitado), coordenadas
  idênticas (distância 0, aceito).
- **FR-006** (RF33): Após presença validada, o sistema MUST gravar o ponto
  como "visitado" para aquele turista, criando um registro imutável de
  visitação contendo, no mínimo: identificador do turista, identificador
  do ponto, timestamp da visita e coordenadas GPS validadas usadas na
  verificação. Registros de visitação não podem ser atualizados ou
  apagados por operação de usuário.
- **FR-007** (RF33): O sistema MUST registrar a primeira visitação válida
  do turista em um ponto como a marca que define o status "visitado"
  daquele ponto para aquele turista.
- **FR-008** (RF34): Após gravar a visitação, o sistema MUST acionar o
  serviço público do domínio de gamificação (a interface de serviço da
  spec 009) para atualizar o progresso das rotas em andamento do turista
  que contenham o ponto — atravessando a função de serviço do dono dos
  dados, nunca escrevendo diretamente em tabelas de outro módulo.
- **FR-009** (RF34 - idempotência): Quando o turista repetir a marcação de
  um ponto que já tinha status "visitado", o sistema MUST registrar a
  visita adicional no histórico imutável, mas MUST NOT gerar nova
  atualização de progresso de rota — a atualização é idempotente (a
  primeira visita já contabilizou o ponto). Esclarecido: nesta fase NÃO é
  exigido mecanismo de lock explícito contra marcações quase simultâneas
  (idempotência simples); a proteção de progresso é a mesma das visitas
  repetidas sequenciais.
- **FR-010**: O sistema MUST expor, para o turista autenticado, a consulta
  de seus pontos com status "visitado" e o histórico de visitações
  (timestamp e coordenadas), para uso no aplicativo Passaporte.
- **FR-011**: Todos os endpoints deste módulo MUST aparecer agrupados sob
  a tag "Visitation", conforme a centralização de tags da spec 006 —
  nenhum arquivo de rota escreve string de tag própria.
- **FR-012**: Todo dado trafegado e retornado no contrato HTTP deste
  módulo MUST seguir o contrato JSON camelCase da spec 005; falhas
  MUST sempre emitir o payload único de erro.
- **FR-013**: O sistema MUST validar as coordenadas por schema (faixa
  WGS-84: latitude −90..90, longitude −180..180; valores numéricos
  finitos) e rejeitar coordenadas inválidas com 422 antes de qualquer
  cálculo.

### Key Entities *(include if feature involves data)*

- **Visitation** (registro de visitação): ocorrência imutável de uma
  visita validada — turista, ponto turístico, timestamp, coordenadas
  GPS validadas (armazenadas em texto claro — dado operacional,
  esclarecido em Clarifications); não é atualizável nem apagável por
  operação de usuário.
- **Visitado (status por ponto/turista)**: ponto visto como já visitado
  na visão do turista — derivado da (primeira) visitação válida daquele
  turista naquele ponto (decisão esclarecida: derivado do histórico de
  visitações; nenhuma flag/armazenamento de status separado).
- **Raio de tolerância**: distância máxima (configurável por ponto
  turístico, com valor padrão global de 100 metros na configuração do
  backend) que separa uma presença real de uma tentativa inválida.
- **Ponto turístico** (já existe na spec 007): entidade de referência com
  coordenadas cadastradas; ganha a possibilidade de raio de tolerância
  próprio (opcional).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Um turista que está fisicamente dentro do raio de um ponto
  consegue marcar a visitação em uma única tentativa, recebendo a
  confirmação em menos de 3 segundos.
- **SC-002**: 100% das tentativas com posição claramente fora do raio
  (ex.: > 10× raio de tolerância) são rejeitadas com erro apropriado —
  zero falsos positivos evidentes nos casos de teste.
- **SC-003**: 100% das visitações registradas carregam timestamp e
  coordenadas validadas em registro imutável (nenhum update/delete de
  visitação nas operações normais do módulo).
- **SC-004**: 100% das rotas em andamento vinculadas a um ponto
  visitado pela primeira vez sobem de progresso exatamente uma vez por
  turista — nenhuma duplicação de progresso por visita repetida
  (idempotência verificada em teste).
- **SC-005**: Zero escritas do módulo visitation em tabelas de outros
  domínios (checagem de fronteira por AST passa no smoke test).
- **SC-006**: A suíte de testes cobre, no mínimo: fórmula de Haversine
  (dentro, fora, borda, antípodas), fluxo ponta a ponta visitação
  válida → status gravado → progresso de rota, rejeição fora do raio,
  e idempotência de visita repetida.
- **SC-007**: 100% das tentativas rejeitadas por distância fora do raio
  emitem um log estruturado no backend; tentativas aceitas não exigem
  auditoria especial (não são ações administrativas — alinhado ao RNF19).

## Assumptions

- A interface pública de serviço de gamificação (spec 009) já expõe o
  mecanismo de atualização de progresso por ponto visitado; o módulo
  visitation apenas o consome, sem conhecer seu schema interno.
- O ponto turístico (spec 007) existe como entidade com coordenadas
  cadastradas; a alteração de raio de tolerância por ponto pode ser
  feita por quem administra pontos (não por este módulo).
- O campo de raio de tolerância por ponto é novo neste escopo: esta
  feature introduz a possibilidade de sobrescrever o raio por ponto; a
  gestão (cadastro/edição) do valor acontece no módulo de administração
  de pontos turísticos, podendo ser tratada em task própria.
- Coordenadas são sempre decimal WGS-84, validadas por schema, e
  armazenadas no registro de visitação em texto claro (fora do rol de
  criptografia de campo da constituição).
- O default global do raio de tolerância vive na configuração do
  backend (settings), não hardcoded em lógica; valor padrão definido:
  100 metros (esclarecido em Clarifications — ajustável por configuração,
  não por código).
- A marcação de visitação é feita exclusivamente pelo turista autenticado
  (RBAC: perfil turista); administrador não marca visitação em nome de
  turista nesta fase.
- Escopo fora desta feature: edição retroativa de visitações, cancelamento
  de Visitado, cálculo de ranking/dashboard (consumidores de visitações),
  geolocalização por IP/estimada, margem de precisão horizontal do
  aparelho (a validação usa só as coordenadas GPS informadas), e a UX do
  painel e do mobile.
- A política de transacionalidade (visitação + progresso de rota na mesma
  operação) é refinada em /speckit-plan; o comportamento contratado é a
  política de consistência padrão descrita nos Edge Cases.
</content>