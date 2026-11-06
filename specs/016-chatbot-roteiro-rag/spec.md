# Feature Specification: Chatbot de Planejamento de Roteiro (RAG) — RF38/RF39

**Feature Branch**: `016-chatbot-roteiro-rag`

**Created**: 2026-11-06

**Status**: Draft

**Input**: User description: "Implementar Chatbot de Planejamento de Roteiro do PassaNorte (backend, módulo chatbot), IA generativa com RAG (RF38/RF39), autenticado como turista. RF38 — chatbot em conversa de linguagem natural monta roteiros personalizados com base nos pontos turísticos e eventos cadastrados no banco (fonte de verdade), e devolve roteiro estruturado (lista ordenada de pontos/eventos com horários sugeridos e custo total estimado) que pode ser visualizado no Passaporte. RF39 — o roteiro considera custo dos ingressos, proximidade geográfica entre pontos, interesses do usuário e horários de funcionamento. Arquitetura: RAG sobre a base cadastrada — o LLM só recebe contexto recuperado, nunca inventa pontos/eventos; sessões de chat persistidas com histórico do turista. Provedor de LLM com free tier (RNF15), chave via variáveis de ambiente. Comportamento degradado documentado se provedor indisponível. RNF06 — sem hardcode de localidade. Endpoints agrupados sob a tag 'Chatbot' do registro central de tags da spec 006."

## Clarifications

### Session 2026-11-06

- Q: Uma sessão de chat tem ciclo de vida limitado ou permanece sempre utilizável pelo turista? → A: Sem encerramento — sessões permanecem ativas para sempre; o turista pode listar e continuar qualquer sessão antiga com o histórico completo; sem transição de estado.
- Q: O roteiro estruturado gerado pelo chatbot é armazenado como parte da mensagem do chatbot ou como um registro próprio separado? → A: Embutido na mensagem do chatbot — sem entidade de roteiro separada; o roteiro estruturado é persistido junto à mensagem do assistente e consultado pela sessão.
- Q: Quanto tempo no máximo o turista deve esperar por uma resposta do chatbot antes de o sistema desistir do provedor e responder em modo degradado? → A: ~30 segundos no pior caso; acima disso o pedido ao provedor é abortado e o turista recebe a resposta em modo degradado (FR-018).
- Q: O acesso ao chatbot deve ter limite de uso por turista para proteger a cota do provedor gratuito de IA, ou nenhuma limitação nesta fase? → A: Sem limite de uso nesta fase — a proteção prática vem do timeout (~30s) e do comportamento degradado (FR-018).
- Q: Quando um evento entra no roteiro, ele pode ser de qualquer data futura ou apenas de eventos que ocorrem no dia alvo do roteiro? → A: Apenas eventos que ocorrem no dia alvo do roteiro (roteiro de um único dia; um evento só entra se ocorrer/ter ingresso válido naquele dia).
- Q: Cada item do roteiro guardado na mensagem deve conter os dados de exibição do momento da geração, ou apenas a referência ao ponto/evento cadastrado? → A: Id + snapshot de exibição — cada item guarda o identificador e os dados de exibição do momento (nome, horário sugerido, custo); o roteiro permanece renderizável mesmo que o item mude ou seja excluído depois.
- Q: Em qual idioma o chatbot responde nesta fase, considerando que o perfil do turista não tem preferência de idioma? → A: No idioma único habilitado na configuração da localidade (pt-BR hoje); múltiplos idiomas por turista fica para fase futura.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Conversa em linguagem natural monta um roteiro (Priority: P1)

Um turista autenticado descreve em linguagem natural o tipo de passeio que
deseja ("quero conhecer lugares históricos gratuitos na segunda-feira"). O
chatbot busca no catálogo cadastrado os melhores candidatos, devolve em
linguagem natural um roteiro estruturado — lista ordenada de
pontos/eventos com horário sugerido para cada item e custo total estimado
— e explica brevemente as escolhas. O roteiro devolvido é estruturado e
pode ser renderizado pelo Passaporte.

**Why this priority**: É o núcleo do RF38 — sem esta conversa gerando
roteiro a partir dos dados cadastrados, as demais histórias não têm objeto.

**Independent Test**: Autenticado como turista, com uma base cadastrada
conhecida, uma mensagem relevante recebida na conversa devolve uma resposta
com texto natural e um roteiro cujos itens existem apenas na base de
teste. Testável de ponta a ponta mockando o provedor de IA.

**Acceptance Scenarios**:

1. **Given** turista autenticado, **When** envia mensagem pedindo um
   roteiro relevante à base, **Then** recebe resposta em linguagem natural
   contendo um roteiro estruturado (sequência ordenada de itens, horário
   sugerido por item, custo total estimado) cujo conteúdo se apoia nos
   pontos/eventos recuperados da base.
2. **Given** turista autenticado, **When** envia mensagem, **Then** o
   contexto entregue à geração é derivado de busca sobre os dados
   persistidos — nenhum ponto ou evento citado no roteiro deixa de existir
   na base (constraint do RF38: recuperação como fonte de verdade).
3. **Given** turista autenticado, **When** envia mensagem em nova conversa
   (nova sessão), **Then** a sessão de chat (mensagens do turista e do
   chatbot) é persistida e o histórico permanece disponível na sequência.

---

### User Story 2 - Roteiro critérios do RF39 (Priority: P2)

Os roteiros gerados levam em conta os quatro critérios do RF39: custo dos
ingressos (eventos têm preço), proximidade geográfica (a ordem dos
pontos segue uma rota razoável, com distância direta entre consecutivos —
sem cruzar a cidade várias vezes), interesses do usuário (o
perfil do turista prioriza categorias compatíveis) e horários de
funcionamento (nenhum item sugerido em horário em que o lugar está
fechado).

**Why this priority**: Diferencia um roteiro "improvisado" de um roteiro
realmente personalizado e coerente; depende da Us 1 mas vale
independentemente pelo conteúdo do roteiro gerado.

**Independent Test**: Com uma base de teste contendo pontos em
coordenadas distintas, com preços, horários e categorias controlados, o
roteiro observado respeita: funcionamento no horário sugerido, ordem
compatível com distâncias geográficas, priorização das categorias de
interesse do turista e custo total consistente com a soma dos ingressos.

**Acceptance Scenarios**:

1. **Given** ponto cadastrado fechado no horário alvo da conversa,
   **When** o turista pede que o chatbot monte o roteiro para aquele
   horário, **Then** aquele ponto não aparece no roteiro.
2. **Given** dois pontos candidatos com preços de ingresso conhecidos,
   **When** ambos entram no roteiro, **Then** o custo total estimado é a
   soma esperada dos ingressos (eventos pagos) e os pontos com entrada
   livre não somam custo.
3. **Given** pontos com coordenadas espalhadas e perfil de interesse do
   turista conhecido, **When** um roteiro é gerado, **Then** a sequência
   dos itens não viola a regra de rota razoável (distância direta entre
   consecutivos controlada) e os itens escolhidos favorecem as categorias
   de interesse do turista frente a candidatos comparáveis de categorias
   menos interessantes.

---

### User Story 3 - Sessão persistida com histórico do turista (Priority: P3)

O turista retoma a conversa e o chatbot leva em conta o contexto anterior
(da mesma sessão) para respondê-lo — correções e refinamentos ao
roteiro. O histórico é persistido por turista, de modo que a conversa
sobrevive a nova requisição/retomada da conversa no Passaporte.

**Why this priority**: Conclui o ciclo de uso — sem histórico, cada
mensagem seria tratada isoladamente, quebrando a experiência natural.

**Independent Test**: Duas mensagens enviadas na mesma sessão com o
turista fazendo referência à conversa anterior: a segunda resposta
aproveita ou mantém a coerência com a primeira; e ao listar/repromover a
sessão, o histórico persistido contém ambas as mensagens.

**Acceptance Scenarios**:

1. **Given** sessão existente com mensagens anteriores, **When** o
   turista envia nova mensagem pedindo ajuste ("troque X por algo mais
   barato"), **Then** a resposta dá continuidade ao contexto da sessão.
2. **Given** sessão encerrada/reaberta, **When** o turista recupera a
   conversa, **Then** todas as mensagens anteriores estão presentes
   (história persistida entre chamadas).

---

### User Story 4 - Comportamento degradado sem provedor disponível (Priority: P4)

Se o provedor de IA generativa estiver indisponível, mal configurado
(chave ausente) ou fora do ar, o serviço não falha de forma opaca: o
turista recebe uma mensagem de chatbot explicando que a geração via IA
não está disponível naquele momento; as sessões e as mensagens já
registradas continuam intactas e visualizáveis.

**Why this priority**: Requisito de robustez (comportamento degradado
documentado) — não agrega valor quando tudo funciona, mas evita
experiência quebrada quando o provedor gratuito limita/indisponibiliza.

**Independent Test**: Com o provedor de IA simulado como indisponível —
sem chamadas externas reais — o fluxo de chat devolve resposta de
indisponibilidade em vez de erro opaco, e o estado da sessão permanece
consistente.

**Acceptance Scenarios**:

1. **Given** provedor indisponível, **When** o turista envia mensagem,
   **Then** recebe resposta do chatbot sinalizando indisponibilidade (e
   nenhum roteiro parcial/errado é apresentado).
2. **Given** provedor indisponível, **When** a mensagem falha, **Then**
   as sessões e mensagens já persistidas continuam disponíveis.

---

### Edge Cases

- O que acontece quando a base não tem pontos/eventos compatíveis (ex.:
  turista pede categoria sem nenhum ponto relacionado)? → Resposta coerente
  informando que não há opções compatíveis, sem inventar pontos/eventos.
- O que acontece quando o pedido está incompleto (turista não informou
  data/horário)? → O chatbot assume um horário padrão (momento da conversa,
  no fuso configurado da localidade) e o informa na resposta; pedir a
  informação ao turista fica para fase futura.
- O que acontece quando o turista envia mensagem sem conteúdo útil
  (texto fora de tema, saudação)? → Resposta em conversa natural dirigindo
  para o propósito do Planejador de Roteiro, sem gerar roteiro vazio.
- O que acontece quando o roteiro gerado não pode ser ancorado a itens da
  base? → O roteiro degrada para nenhum item e o chatbot o comunica,
  em vez de apresentar itens impossíveis.
- O que acontece se a chave do provedor não está configurada? → Módulo sobe,
  endpoints respondem indisponibilidade (story 4); comportamento
  documentado.

## Requirements *(mandatory)*

### Functional Requirements

**Acesso e sessões**

- **FR-001**: Apenas usuários autenticados como turista podem criar
  sessões de chat e trocar mensagens com o chatbot; uma sessão pertence
  exclusivamente ao turista que a criou e não pode ser acessada por outro
  turista (nem listada nem continuada).
- **FR-002**: O turista pode criar uma nova sessão de conversa e listar as
  sessões que ele próprio criou.
- **FR-003**: O turista pode enviar mensagens em linguagem natural dentro
  de uma sessão; cada mensagem trocada (do turista e do chatbot) é
  persistida junto à sessão, com a rota retornando o histórico completo
  dela.
- **FR-004**: Sessões e mensagens persistidas sobrevivem entre requisições
  (histórico disponível em chamadas futuras — integração de sessão é
  um critério de aceitação).

**Planejamento de roteiro (RF38)**

- **FR-005**: O chatbot devolve, para pedidos de roteiro, uma resposta em
  linguagem natural acompanhada de um roteiro estruturado: sequência
  ordenada de itens (pontos turísticos e/ou eventos), horário sugerido
  para cada item e custo total estimado do roteiro.
- **FR-006**: O roteiro estruturado referencia apenas pontos/eventos que
  existem no cadastro — o gerador nunca introduz itens inexistentes na
  base (fonte de verdade). Nenhum item do roteiro é aceito se não puder
  ser amarrado a um registro persistido.
- **FR-007**: Todos os candidatos ao roteiro vêm de busca sobre a base
  cadastrada persistida: o contexto entregue ao gerador é composto
  exclusivamente por registros recuperados (busca por similaridade de
  significado combinada com critérios estruturados da base), nunca por
  conteúdo livre do gerador.
- **FR-008**: O roteiro gerado é persistido embutido na mensagem do
  chatbot correspondente (sem entidade separada de roteiro) e devolvido
  de forma visualizável no Passaporte (estrutura suficiente para
  renderização: itens na ordem, com horário estimado e custo).

**Critérios do RF39**

- **FR-009**: O roteiro não inclui ponto/evento em horário em que ele
  esteja fechado (restrito pelos horários de funcionamento cadastrados),
  considerando o horário alvo da conversa (momento da conversa por
  padrão, ou aquele mencionado pelo turista).
- **FR-024**: Um evento só entra no roteiro se ocorrer (ou tiver ingresso
  válido) no dia alvo do roteiro — roteiros são de um único dia; eventos
  de datas futuras diferentes do dia alvo não entram, mesmo dentro do
  período de vigência.
- **FR-010**: O roteiro considera o custo dos ingressos: eventos com
  ingresso entram no custo total com o preço cadastrado; lugares com
  entrada livre não geram custo; o custo total estimado é a soma esperada
  da sequência.
- **FR-011**: A ordem dos itens do roteiro é uma rota geográfica razoável:
  a distância direta entre itens consecutivos não pode ser arbitrariamente
  maior que a necessária (nenhum padrão de vai-e-vem atravessando a
  cidade), avaliada pela distância entre coordenadas dos pontos.
- **FR-012**: A escolha/priorização dos itens considera as categorias de
  interesse do perfil do turista: frente a candidatos comparáveis, o
  roteiro prioriza categorias de interesse declaradas pelo turista
  (categorias provenientes da configuração da localidade, sem hardcode).

**Conversa e conteúdo**

- **FR-013**: Respostas do chatbot são em linguagem natural, conversa
  continuada dentro da sessão (o histórico da sessão participa da resposta
  seguinte).
- **FR-014**: Quando a base não tem candidatos compatíveis com o pedido,
  o chatbot o comunica em linguagem natural e não devolve roteiro com
  itens.
- **FR-015**: Respostas do chatbot não devem se referir a locais/cidades
  específicas fixadas no código: conteúdo depende dos dados cadastrados e
  da configuração da localidade (RNF06 — portabilidade).
- **FR-016**: O contrato HTTP deste módulo fica agrupado sob a tag
  "Chatbot" do registro central de tags OpenAPI (spec 006), mantendo o
  padrão único de payload de erro da API (`ApiError`).
- **FR-017**: Provedor de IA generativa com plano gratuito (RNF15);
  credenciais de acesso exclusivamente via variáveis de ambiente —
  nenhuma chave ou segredo no repositório; ausência/misconfig não impede
  a aplicação de subir (comportamento degradado na FR-018).
- **FR-018**: Provedor indisponível, chave ausente, falha da geração ou
  resposta não recebida em até ~30 segundos resultam em resposta do
  chatbot de indisponibilidade (story 4), sem roteiro parcial; nenhum
  erro opaco exposto ao turista; sessões/mensagens anteriores permanecem
  intactas.
- **FR-019**: Respostas do chatbot são i18n-ready (RNF16): o chatbot
  responde no idioma único habilitado na configuração da localidade
  (pt-BR nesta fase), com textos padrão localizáveis (escolha por idioma
  exato, fallback pela base do idioma, então português); seleção de
  idioma por turista fica para fase futura.
- **FR-025**: Cada item do roteiro persistido carrega o identificador do
  ponto/evento e um snapshot dos dados de exibição do momento da geração
  (nome exibido, horário sugerido, custo estimado): o roteiro histórico
  permanece renderizável a partir da própria mensagem, mesmo que o
  ponto/evento mude ou seja excluído depois.

**Testabilidade (critérios de aceitação)**

- **FR-020**: Pipeline de recuperação é testável de forma isolada: dadas
  consultas relevantes contra uma base de teste conhecida, a recuperação
  retorna os pontos/eventos certos esperados.
- **FR-021**: Constraint automatizada garante que todo roteiro gerado
  referencia apenas entidades existentes na base de teste, respeita
  horários de funcionamento e soma de ingressos esperada.
- **FR-022**: Teste de integração de sessão demonstra o histórico
  persistindo entre mensagens da mesma sessão.
- **FR-023**: Nenhum teste na suíte faz chamada externa real ao provedor
  de IA: o provedor é simulado (mock/injetável) nos testes.

### Key Entities *(include if feature involves data)*

- **ChatSession**: sessão de conversa de um turista; pertence a exatamente
  um turista; possui momento de início; sem estado de encerramento — toda
  sessão permanece continuável indefinidamente.
- **ChatMessage**: mensagem de uma sessão; de autoria do turista
  (mensagem de usuário) ou do chatbot (resposta, podendo incluir texto
  natural e o roteiro estruturado anexo); ordenada no tempo dentro da
  sessão.
- **Itinerary**: roteiro estruturado produzido para uma mensagem do
  chatbot, embutido na própria mensagem (sem registro separado); contém
  sequência ordenada de itens, cada item referenciando o ponto turístico
  ou evento correspondente, com horário sugerido, custo estimado do item
  e custo total.
- **TouristSpot / Event** (existente nos módulos 007/008): fonte de
  verdade — nome, descrição, coordenadas, horários de funcionamento,
  categorias e, para eventos, preço do ingresso. Nenhuma mudança de
  dono: o módulo chat os lê via interface do módulo do dono, nunca via
  tabelas.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Para um conjunto de pedidos relevantes (>= 10 consultas de
  referência) sobre uma base de teste conhecida, a recuperação inclui os
  itens esperados em >= 90% das consultas.
- **SC-002**: 100% dos roteiros gerados em teste passam na constraint:
  apenas itens existentes na base, dentro dos horários de funcionamento e
  com custo total igual à soma esperada dos ingressos.
- **SC-003**: Num roteiro de ≥ 3 itens com coordenadas distintas, a ordem
  observada segue greedy nearest-neighbor a partir do primeiro item
  (cada item subsequente é o mais próximo ainda não visitado) — garantia
  mais forte que a heurística "sem par consecutivo com distância > 2× a
  alternativa razoável", que ela implica; provada em testes unitários.
- **SC-004**: 100% das mensagens trocadas numa sessão persistem e
  retornam na leitura do histórico em requisições subsequentes.
- **SC-005**: Com o provedor simulado indisponível (ou excedendo ~30
  segundos), 100% dos pedidos resultam em resposta de indisponibilidade
  clara (em vez de erro opaco) e a integridade da sessão é preservada.
- **SC-006**: Roteiros devolvidos são renderizáveis no Passaporte sem
  transformação adicional (itens ordenados, horário por item, custo por
  item e custo total presentes em 100% dos casos).
- **SC-007**: Migrar de cidade/localidade (troca dos dados configuráveis
  e do cadastro, sem alterar código) produz roteiros coerentes com a nova
  base — sem nomes de lugares ou cidades fixados no código.
- **SC-008**: A suíte de testes completa roda sem nenhuma chamada de rede
  externa ao provedor de IA (provado por simulação do provedor).

## Assumptions

- **Turista como ator único**: apenas o perfil turista conversa com o
  chatbot (RF38). Administrador/funcionário não têm acesso às sessões
  dos turistas. A exclusão/desativação de turista não existe nesta fase
  do backend; se for adicionada no futuro, os dados de chat seguem o
  mesmo destino dos dados do dono (LGPD, princípio II).
- **Fonte de recuperação**: o catálogo de pontos/eventos já cadastrados
  nos módulos próprios é a única fonte; não há cadastro de conteúdo novo
  dentro do chatbot, nem ingestão de conteúdo externo nesta fase.
- **Horário padrão**: quando o turista não informar horário, assume-se o
  momento da conversa (no fuso configurado da localidade).
- **Limites de custo/quantidade**: roteiro v1 é de um único dia (eventos
  só do dia alvo — FR-024), sem
  otimização de ordem além da rota razoável (nenhum solver completo —
  YAGNI); quantidade de itens limitada a algo gerenciável numa visita
  (da ordem de meia dúzia de itens); sem limite de uso/rate limit por
  turista nesta fase.
- **Provedor de IA**: qualquer serviço de geração com plano gratuito
  atende (RNF15); a integração é indireta (abstraída) para permitir troca
  de provedor e simulação em teste; a chave/credencial chega por
  variável de ambiente e a aplicação sobe mesmo sem ela.
- **Idioma**: conversas em pt-BR por padrão (idiomas habilitados vêm da
  configuração da localidade, princípio VI).
- **Fora do escopo nesta**: compartilhar/excluir sessão por API para o
  turista não ser essencial; exportação do roteiro para formatos
  arbitrários; histórico de sessões antigas expurgadas; interface do painel
  web; limite de uso (rate limit) por turista — a proteção da cota fica a
  cargo do timeout e do comportamento degradado.
- **Dependências existentes**: módulos de pontos turísticos (007) e
  eventos (008) fornecem os dados; perfil do turista (003) fornece
  categorias de interesse; registro de tags (006) fornece a tag "Chatbot".
