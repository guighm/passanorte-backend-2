# Feature Specification: Dashboard e Insights (Visualização Gerencial)

**Feature Branch**: `014-dashboard-insights`

**Created**: 2026-11-06

**Status**: Draft

**Input**: User description: "Implementar Dashboard e Insights do PassaNorte (backend FastAPI, módulo dashboard), endpoints restritos a administrador (RF03 — funcionário recebe 403). Requisitos: RF06 — mapa de calor da cidade com marcações de concentração de visitas por região/ponto turístico; RF07 — contador total de acessos ao sistema (aplicação Passaporte) em períodos configuráveis (hoje/semana/mês/custom), com acessos únicos por turista/dia; RF08 — ranking de pontos turísticos mais visitados segmentado por dia, mês e ano, com top N configurável; RF09 — distribuição da proporção de usuários que visitaram pontos segmentada por país de origem cadastrado; RF10 — distribuição da proporção de usuários segmentada pelos interesses cadastrados no perfil. Toda métrica derivada de dados reais registrados — nunca inventada. Agregações no banco de dados, não em laços; índices adequados. Respeitar fronteira de domínio: dashboard lê, nunca escreve em outros módulos. Endpoints agrupados sob a tag "Dashboard" do registro central de tags da spec 006."

**Requisitos de origem**: RF06 (Mapa de Calor), RF07 (Contador de Acessos), RF08 (Ranking de Pontos Turísticos), RF09 (Distribuição por País de Origem), RF10 (Distribuição por Interesses), RF03 (Controle de Nível de Acesso — RBAC), RNF06 (Portabilidade para Outras Localidades).

## Clarifications

### Session 2026-11-06

- Q: O que exatamente conta como um "acesso" no contador do RF07? → A: Toda
  requisição autenticada de turista grava um evento de acesso; o contador
  devolve turistas únicos (turista×dia conta uma vez) e o total de eventos
  de acesso no período (confirmado pelo usuário — opção A).

- Q: Como uma "região" do mapa de calor deve ser definida para o modo de
  agregação por região (RF06)? → A: Agrupamento de pontos configurado em
  dados: no arquivo de localidade da cidade, cada região nomeada lista os
  pontos que a compõem; o peso do marcador de região é a soma das visitas
  dos seus pontos e a coordenada é o centroide desses pontos (confirmado
  pelo usuário — opção A).

- Q: Qual deve ser a forma de saída do ranking segmentado (RF08)? → A: Uma
  janela por consulta: cada chamada recebe o modo (dia/mês/ano) e uma data
  de referência, e devolve o top N apenas naquela janela; o painel repete
  a consulta para trocar de janela (confirmado pelo usuário — opção A).

- Q: Quais requisições da aplicação Passaporte devem gerar um evento de
  acesso no log de acessos? → A: Toda requisição com JWT de turista
  autenticado grava um evento, incluindo endpoints públicos consultados
  autenticado (ex.: detalhes do ponto); requisições sem credencial de
  turista e requisições de funcionário não gravam (confirmado pelo usuário
  — opção A).

- Q: Sobre qual população de turistas a distribuição por interesses (RF10)
  deve ser calculada? → A: Somente turistas com pelo menos uma visitação
  registrada — a mesma população da distribuição por país (RF09), mantendo
  o painel coerente com o perfil de quem visita (confirmado pelo usuário —
  opção A).

- Q: Se a gravação do evento de acesso falhar, o que deve acontecer com a
  requisição do turista em andamento? → A: Best-effort — o log de acesso é
  observabilidade de segunda ordem: se a gravação falhar, a requisição do
  turista responde normalmente e a falha vira apenas log de erro no
  backend; os serviços essenciais nunca dependem do subsistema de métricas
  (confirmado pelo usuário — opção A).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Administrador visualiza o mapa de calor de visitas (Priority: P1)

O administrador abre o painel para entender onde os turistas estão indo. A
partir do histórico real de visitações registradas (especificação 011), o
sistema devolve uma lista de coordenadas geográficas acompanhadas de um peso
— número de visitas no período consultado — que o painel web renderiza como
um mapa de calor da cidade. A agregação pode ser feita por ponto turístico
individual ou, quando a cidade em configuração define regiões, por região.

**Why this priority**: O mapa de calor é o principal insumo visual de
decisão do gestor (prioridade "Alta" do RF06) e depende apenas de dados
já registrados pelo módulo de visitação.

**Independent Test**: Popular o sistema com visitas válidas em pontos
conhecidos e comparar cada marcador devolvido com as contagens esperadas
por ponto/região.

**Acceptance Scenarios**:

1. **Given** pontos turísticos cadastrados com visitas registradas em quantidades diferentes, **When** o administrador consulta o mapa de calor, **Then** cada item devolvido contém as coordenadas do ponto, o peso igual ao número de visitas registradas e a referência ao ponto, agregado por ponto turístico.
2. **Given** o modo de agregação por ponto, **When** o administrador informa um período (data inicial/data final), **Then** o peso de cada marcador considera somente as visitas dentro do período informado.
3. **Given** a cidade configurada possui uma definição de regiões em dados de configuração, **When** o administrador consulta o modo de agregação por região, **Then** os marcadores representam o centroide dos pontos de cada região configurada, com o peso igual à soma das visitas de todos os pontos daquela região.
4. **Given** a instalação foi reconfigurada para outra cidade (RNF06), **When** o administrador consulta o mapa de calor, **Then** nenhum valor específico de cidade influencia o resultado — todas as coordenadas vêm dos pontos cadastrados e/ou da configuração de localidade.

---

### User Story 2 - Administrador visualiza o contador de acessos por período (Priority: P1)

O administrador quer saber se a aplicação Passaporte está sendo usada. Cada
requisição autenticada de um turista à aplicação registrou um evento de
acesso (instrumentação do log de acesso definida nesta feature a partir da
base de autenticação de turistas da especificação 002). O contador devolve,
para períodos configuráveis (hoje, semana corrente, mês corrente ou um
intervalo personalizado), o número de turistas únicos por dia e o total de
eventos de acesso no período.

**Why this priority**: Métrica de adoção fundamental do aplicativo (RF07) e
fonte do único dado que não deriva de visitações — o uso geral do sistema.

**Independent Test**: Autenticar turistas e disparar requisições em dias
diferentes; verificar o contador para cada período (hoje/semana/mês/custom)
contra as quantidades registradas.

**Acceptance Scenarios**:

1. **Given** turistas que fizeram requisições autenticadas no dia corrente, **When** o administrador consulta o contador com período "hoje", **Then** recebe a contagem de turistas únicos do dia e o total de eventos de acesso do dia.
2. **Given** o mesmo turista fez requisições em dois dias diferentes dentro da semana corrente, **When** o administrador consulta a semana, **Then** o turista é contado uma vez por dia (distinguindo os dois dias distintos) e o total de eventos reflete todas as requisições.
3. **Given** o sistema sem nenhum acesso de turista no período consultado, **When** o administrador consulta qualquer período, **Then** recebe zero (ou estrutura vazia), sem erro.
4. **Given** um intervalo personalizado com datas inicial e final, **When** o administrador consulta o contador, **Then** os limites do intervalo são inclusivos.

---

### User Story 3 - Administrador visualiza o ranking de pontos mais visitados (Priority: P1)

O administrador quer identificar os pontos turísticos mais visitados para
decidir investimento e divulgação. O ranking lista pontos turísticos em
ordem decrescente de número de visitas registradas, segmentado por janela
temporal — por dia, por mês ou por ano — e limitado aos N primeiros, com N
configurável na requisição (padrão definível pelo próprio sistema).

**Why this priority**: Requisito de alta prioridade do RF08; é a leitura
mais direta do "onde está o movimento".

**Independent Test**: Criar visitas em vários pontos com volumes distintos
em janelas diferentes; verificar ordenação, contagem e limite N para cada
granularidade.

**Acceptance Scenarios**:

1. **Given** pontos com quantidades distintas de visitas no período, **When** o administrador consulta o ranking por dia/mês/ano, **Then** os pontos aparecem ordenados do mais visitado para o menos visitado com a contagem correta de cada um.
2. **Given** mais pontos visitados do que o N solicitado, **When** o administrador consulta o ranking, **Then** recebe somente os N primeiros.
3. **Given** visitas ao mesmo ponto em dias diferentes dentro do mês corrente, **When** o administrador consulta o ranking por mês, **Then** as visitas são somadas naquele mês; ao consultar por dia especificado, somente as visitas daquele dia são contadas.
4. **Given** um ponto sem nenhuma visita no período consultado, **When** o administrador consulta o ranking, **Then** o ponto não aparece na lista (o ranking contém apenas pontos visitados no período).

---

### User Story 4 - Administrador visualiza a distribuição de visitantes por país de origem (Priority: P2)

O administrador quer entender de onde vêm os turistas que efetivamente
visitaram os pontos. A distribuição calcula, sobre a população de turistas
que possuem pelo menos uma visitação registrada (no período consultado,
quando informado), a proporção por país de origem cadastrado no perfil
(especificação 003).

**Why this priority**: Insight demográfico de perfil "Média" no RF09; porém
depende das mesmas bases já prontas da visitação, por isso cabe após os
gráficos essenciais.

**Independent Test**: Cadastrar turistas de países distintos e registrar
visitas para parte deles; verificar proporções esperadas por país.

**Acceptance Scenarios**:

1. **Given** turistas de países distintos com visitações registradas, **When** o administrador consulta a distribuição por país, **Then** cada país de origem presente aparece com a quantidade de turistas visitantes e a proporção relativa ao total de visitantes.
2. **Given** turistas cadastrados que nunca visitaram ponto algum, **When** o administrador consulta a distribuição, **Then** esses turistas não entram na população da distribuição (o denominador é o total de visitantes).
3. **Given** a mesma base de dados, **When** o administrador soma todas as proporções retornadas, **Then** a soma é 100% (com arredondamento a um dígito aceitável).
4. **Given** um período informado, **When** o administrador consulta a distribuição, **Then** a população considera somente turistas com pelo menos uma visitação dentro do período.

---

### User Story 5 - Administrador visualiza a distribuição por interesses cadastrados (Priority: P2)

O administrador quer conhecer o perfil de interesses declarado pelos
turistas para direcionar campanhas e novos pontos/eventos. A distribuição
calcula proporções por categoria de interesse cadastrada no perfil
(especificação 003), sobre a população de turistas da distribuição por país (ver Assumptions).
Como um
turista pode escolher vários interesses, cada interesse é ponderado pela
quantidade de turistas que o selecionaram, e os percentuais se referem ao
total de seleções e ao total de turistas (podendo somar mais do que 100%
por seleção).

**Why this priority**: Complemento analítico do RF10, prioridade "Média";
usa apenas os interesses efetivamente declarados nos perfis.

**Independent Test**: Cadastrar turistas com conjuntos de interesses
distintos (múltiplas escolhas por turista) e verificar as proporções por
interesse.

**Acceptance Scenarios**:

1. **Given** turistas com conjuntos de interesses distintos, **When** o administrador consulta a distribuição por interesses, **Then** cada interesse selecionado por pelo menos um turista aparece com a quantidade de turistas que o escolheram e a proporção sobre o total de seleções.
2. **Given** um turista com mais de um interesse, **When** a distribuição é calculada, **Then** o turista é contado em cada um dos interesses que declarou (percentuais por interesse podem somar mais de 100% por turista).
3. **Given** turistas sem nenhum interesse declarado, **When** a distribuição é calculada, **Then** eles não contribuem para nenhum interesse (não distorcem os percentuais).
4. **Given** uma categoria de interesse cadastrada porém não escolhida por ninguém, **When** a distribuição é calculada, **Then** a categoria não aparece na resposta (ou aparece com zero, conforme decisão de formato documentada no plano).

---

### Edge Cases

- **Período sem dados**: qualquer métrica consultada para janela sem
  eventos devolve zeros/estrutura vazia com sucesso (não erro).
- **Intervalo personalizado invertido**: data final anterior à inicial é
  rejeitada com erro de validação (422).
- **Ponto turístico removido com histórico de visitas**: as métricas
  baseadas em visitas preservam o histórico registrado; a remoção de um
  ponto não apaga retroativamente as métricas passadas (agregações
  referenciam o registro histórico, não rejeitam dados órfãos).
- **Turista com país de origem não informado**: inalcançável via API — o
  cadastro da especificação 003 exige país informado e não vazio; a
  distribuição mantém a conversão de valor vazio para o bucket "Não
  informado" apenas como defesa, sem quebrar o cômputo.
- **Top N fora dos limites**: valor de N menor que 1 ou além do máximo
  permitido é rejeitado (422) ou substituído pelo máximo documentado.
- **Distribuição com nenhum turista na população**: devolve estrutura
  vazia com total zero, sem divisão por zero.

## Requirements *(mandatory)*

### Functional Requirements

**Controle de acesso (RF03) e organização do contrato**

- **FR-001**: Todos os endpoints do dashboard MUST exigir autenticação e
  papel de administrador; funcionário autenticado recebe 403 e
  requisição não autenticada recebe 401.
- **FR-002**: Todos os endpoints do módulo MUST ser agrupados sob a tag
  "Dashboard" do registro central de tags da especificação 006; nenhum
  arquivo de rota declara a string de tag fora do registro central.
- **FR-003**: O formato dos payloads MUST seguir o contrato JSON camelCase
  da especificação 005; todo caminho de falha usa o payload de erro único
  da spec 005.

**Mapa de calor (RF06)**

- **FR-004**: O sistema MUST expor um endpoint de mapa de calor devolvendo
  uma lista de marcadores, cada um com latitude, longitude e peso (número
  de visitas registradas no período consultado).
- **FR-005**: A agregação dos marcadores MUST ser configurável por ponto
  turístico individual ou por região; cada região é um agrupamento
  configurado em dados (no arquivo de localidade da cidade) que lista os
  pontos que a compõem — o peso do marcador de região é a soma das visitas
  dos seus pontos e a coordenada é o centroide desses pontos. A agregação
  por região só existe quando a cidade em configuração define regiões
  (RNF06) — caso contrário a requisição por região é rejeitada com erro
  claro.
- **FR-006**: O endpoint MUST aceitar período opcional (data inicial/data
  final, inclusivos) para restringir as visitas consideradas.
- **FR-007**: Nenhum valor de cidade ou coordenada padrão pode estar
  fixado em código: coordenadas derivam exclusivamente dos pontos
  cadastrados e/ou da configuração de localidade (RNF06).

**Contador de acessos (RF07)**

- **FR-008**: O sistema MUST registrar um evento de acesso para toda
  requisição com JWT de turista autenticado (aplicação Passaporte) —
  incluindo endpoints públicos consultados autenticado — como log de
  acesso instrumentado no backend (requisições sem credencial de turista e
  requisições de funcionário não gravam), a partir da base de autenticação
  de turistas da especificação 002.
- **FR-009**: O contador MUST aceitar períodos configuráveis: hoje, semana
  corrente, mês corrente ou intervalo personalizado (inclusivo).
- **FR-010**: O contador MUST devolver no período: a quantidade de turistas
  únicos por dia (turista × dia conta uma vez) e o total de eventos de
  acesso.
- **FR-011**: O registro do evento de acesso MUST incluir no mínimo turista
  e instante do acesso, suficientes para as agregações por dia.
- **FR-022**: A gravação do evento de acesso é best-effort: se falhar, a
  requisição do turista responde normalmente e a falha é registrada apenas
  em log de erro no backend — os serviços essenciais (autenticação,
  consulta de pontos, marcação de visitação) nunca dependem do subsistema
  de métricas.

**Ranking de pontos (RF08)**

- **FR-012**: O sistema MUST expor um ranking dos pontos turísticos mais
  visitados, ordenado por número de visitas registradas (decrescente),
  com uma janela por consulta: cada consulta recebe o modo (dia, mês ou
  ano) e uma data de referência (padrão: referência atual), devolvendo o
  top N apenas daquela janela.
- **FR-013**: O ranking MUST aceitar top N configurável por requisição
  (quantidade de itens), com valor padrão e limite máximo documentados.
- **FR-014**: O ranking MUST conter somente pontos com pelo menos uma
  visita no período consultado, cada item com a contagem de visitas.

**Distribuição por país (RF09)**

- **FR-015**: O sistema MUST expor a distribuição da proporção de turistas
  que visitaram pontos segmentada por país de origem cadastrado, com
  quantidade absoluta de turistas por país e percentual sobre o total de
  visitantes.
- **FR-016**: A população da distribuição por país MUST ser o conjunto de
  turistas com pelo menos uma visitação registrada (no período informado,
  quando houver); turistas sem visitação ficam fora do cálculo.

**Distribuição por interesses (RF10)**

- **FR-017**: O sistema MUST expor a distribuição da proporção de usuários
  segmentada pelas categorias de interesse cadastradas nos perfis, com
  quantidade de turistas por interesse e percentual sobre o total de
  seleções.
- **FR-018**: A população da distribuição por interesses MUST ser a mesma
  definida em FR-016 (decisão Q5), mantendo consistência do painel; um
  turista conta uma vez em cada interesse que declarou.

**Integridade das métricas e restrições de domínio**

- **FR-019**: Toda métrica do dashboard MUST derivar de dados reais
  registrados em eventos (visitações válidas da especificação 011, eventos
  de acesso, cadastros/perfis de turistas) — nenhuma métrica estimada,
  simulada ou "inventada" (Princípio IV da constituição).
- **FR-020**: As agregações MUST ser computadas pelo banco de dados
  (consultas agregadas por conjunto), não recomputadas em laços sobre as
  linhas em memória; o modelo de dados MUST ter índices compatíveis com os
  recortes de agregação (por ponto, por turista+dia, por instante).
- **FR-021**: O módulo dashboard MUST apenas LER dados de outros domínios
  por meio de consultas de leitura próprias (sem escrita em tabelas de
  outros módulos e sem mutation por serviço de terceiros) — fronteira do
  monolito modular (Princípios III/IV da constituição).

### Key Entities *(include if feature involves data)*

- **Evento de Acesso (AccessEvent)**: novo registro imutável de log de
  acesso gerado por requisição autenticada de turista; contém turista
  (referência) e instante do acesso. É a única entidade nova do módulo —
  todas as demais métricas derivam de dados existentes.
- **Visitação (VisitationRecord, existente)**: registro imutável
  (especificação 011) com turista, ponto turístico, instante e coordenadas
  validadas; base de peso do mapa de calor, ranking e população
  "visitantes" das distribuições.
- **Turista (Tourist, existente)**: perfil (especificação 003) com país de
  origem e categorias de interesse; dimensões das distribuições RF09/RF10.
- **Ponto Turístico (TouristSpot, existente)**: nome, coordenadas WGS-84
  decimais e status (especificação 007); posição e rótulo dos marcadores
  de mapa de calor e ranking.
- **Definição de Região (configuração de dados)**: quando existente no
  arquivo de configuração de localidade da cidade (RNF06), agrupa pontos
  ou área geográfica para a agregação por região do mapa de calor; ausente
  → agregação por região indisponível.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Com visitas reais registradas, 100% dos marcadores do mapa
  de calor refletem exatamente a contagem de visitas do ponto/região no
  período consultado (verificável por comparação direta com o histórico).
- **SC-002**: O contador de acessos por período reproduz exatamente a
  quantidade de turistas únicos por dia e o total de eventos de acesso
  registrados na janela (hoje/semana/mês/custom).
- **SC-003**: O ranking por dia/mês/ano retorna os pontos em ordem
  decrescente de visitas reais, respeitando o top N de cada consulta, com
  contagens 100% iguais ao histórico registrado.
- **SC-004**: As distribuições por país de origem e por interesses apresentam
  percentuais coerentes com os perfis cadastrados — a soma dos percentuais
  por país é 100% e as proporções por interesses refletem as seleções de
  cada perfil.
- **SC-005**: Nenhum endpoint do dashboard permite ação ao funcionário —
  100% das consultas de funcionário resultam em 403.
- **SC-006**: Com 10 mil eventos de visitação e 50 mil eventos de acesso no
  histórico, cada consulta agregada do dashboard responde em tempo hábil
  para o painel (abaixo de 2 segundos) — agregações por conjunto no banco,
  sem laço linha a linha aplicado.
- **SC-007**: Todas as métricas podem ser explicadas por dados presentes no
  histórico (auditor reverso consegue reconstruir cada número exibido) —
  zero métricas estimadas ou sintéticas.

## Assumptions

- **Population do RF10**: a distribuição por interesses usa a população
  definida em FR-016 (turistas com ≥ 1 visitação registrada), para que o
  painel seja uma leitura coerente do comportamento de quem visita —
  decisão confirmada pelo usuário (ver `## Clarifications`); a extensão a
  todos os turistas cadastrados ficaria para uma fase futura.
- **Definição de "acesso"**: toda requisição com JWT de turista
  autenticado à API (aplicação Passaporte) conta como um acesso, mesmo em
  endpoints públicos consultados autenticado; requisições sem credencial
  de turista e requisições de funcionário não contam. A medição por
  "turista único por dia" faz o número crescer por visitantes distintos e
  não por volume de chamadas (clarificado em `## Clarifications`).
- **Regiões** (mapa de calor): nesta fase, quando o modo "por região" for
  ativado, cada região é um agrupamento configurado em dados (associando
  pontos a regiões); caso a cidade configurada não defina regiões, a
  agregação por ponto é a única disponível.
- **Janelas de tempo**: "hoje", "semana corrente" e "mês corrente" são
  âncoras no horário do servidor; o intervalo personalizado é inclusivo
  nas duas pontas.
- **Top N**: o padrão do ranking é 5 itens e o limite máximo aceito é 100
  (ajustável em planejamento); valores fora da faixa resultam em erro de
  validação.
- **Dados órfãos**: métricas que envolvem visitação preservam o histórico
  mesmo se o ponto turístico for removido ou alterado (o registro de
  visitação é imutável desde a especificação 011).
- **Interesses excluídos/desativados**: categorias não escolhidas por
  ninguém não aparecem na distribuição por interesses (resposta contém
  somente interesses com contador maior que zero — decisão registrada em
  research.md R6).
