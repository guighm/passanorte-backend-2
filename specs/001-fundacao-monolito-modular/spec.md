# Feature Specification: Fundação do Monolito Modular Backend PassaNorte

**Feature Branch**: `001-fundacao-monolito-modular`

**Created**: 2026-10-30

**Status**: Implemented

**Input**: User description: "Implementar a fundação do backend PassaNorte como um MONOLITO MODULAR em FastAPI (Python 3.13, uv), conforme docs/CONSTITUTION.md. Requisitos: (a) estrutura src/passanorte_back com pacote de módulos de domínio auth, funcionarios, turistas, pontos_turisticos, eventos, gamificacao, visitacao, dashboard, notificacoes, chatbot, cada um com subpastas routes/services/repositories/schemas, sem imports cruzados de internals privados entre módulos; (b) app FastAPI único em src/passanorte_back/main.py montando routers por módulo e /health; (c) settings via pydantic-settings com variáveis de ambiente (DATABASE_URL, JWT_SECRET, JWT_TTL, raio padrão de tolerância GPS, cidade padrão, idiomas habilitados); (d) persistência com SQLAlchemy 2.0 + Alembic, PostgreSQL em produção e SQLite para testes (RNF17); (e) infra de auditoria: serviço de log estruturado para ações administrativas (RNF19); (f) configuração de dados de cidade/idiomas em settings/dados, não em código (RNF06). Requisitos de referência: RNF03, RNF06, RNF17, RNF19, RNF20. Não implementar RFs de negócio nesta fase. Critério de aceitação: app sobe, /health responde, migration inicial roda, testes de smoke passam."

**Nota**: Esta é uma feature de **infraestrutura técnica**, não de negócio. A escolha da
stack (FastAPI, Pydantic, SQLAlchemy, Alembic, PostgreSQL/SQLite, uv) é o próprio
escopo da feature e vem da constituição do projeto (RNF03–05, RNF17). Por isso, os
requisitos funcionais abaixo mencionam as tecnologias mandatórias quando a tecnologia
é o requisito em si; os critérios de sucesso permanecem observáveis e verificáveis
independentemente dos detalhes internos de implementação.

## Clarifications

### Session 2026-10-30

- Q: O que o endpoint de verificação de saúde deve responder quando o banco de dados está indisponível? → A: 200 com estado da aplicação e do banco quando tudo saudável; código HTTP 503 quando o banco estiver inacessível.
- Q: Quais itens de configuração são essenciais (interrompem a inicialização se ausentes) e quais admitem default? → A: Essenciais: endereço do banco e segredo de sessão. Com default documentado: TTL de sessão (3600 s), raio padrão de tolerância GPS (100 m), cidade padrão e idiomas lidos do arquivo de dados de localidade (pt-BR).
- Q: A infraestrutura de auditoria desta fase emite registros em log estruturado na saída padrão ou já os persiste em tabela do banco? → A: Log estruturado apenas (YAGNI); persistência do registro em tabela fica para a primeira feature com ação administrativa real.
- Q: As rotas dos módulos devem ser montadas sob um prefixo versionado de contrato (ex.: /api/v1) ou direto na raiz com /health isolado? → A: Prefixo /api/v1 para o contrato de negócio; /health e /docs fora do prefixo, direto na raiz.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Aplicação executável com verificação de saúde (Priority: P1)

Um operador/deployador inicia o serviço do backend PassaNorte e valida, com uma única
requisição, que a aplicação está no ar e aceitando tráfego. O endpoint de verificação
de saúde responde com o estado da aplicação, sem exigir autenticação. Nenhuma
funcionalidade de negócio é necessária para demonstrar valor nesta fase: a aplicação
sobe, responde, e está pronta para receber os módulos de domínio.

**Why this priority**: Sem uma aplicação executável e observável, nenhuma outra
feature posterior pode ser desenvolvida, testada ou implantada. É o menor slice
entregável e valida toda a cadeia de build/execute/teste do projeto.

**Independent Test**: Subir a aplicação e requisitar o endpoint de verificação de
saúde; a resposta deve indicar estado saudável em segundos.

**Acceptance Scenarios**:

1. **Given** o ambiente configurado com as variáveis de ambiente essenciais, **When**
   a aplicação é iniciada, **Then** ela sobe sem erros e fica disponível para
   requisições.
2. **Given** a aplicação no ar, **When** o endpoint de verificação de saúde é
   requisitado, **Then** responde com sucesso informando o estado da aplicação.
3. **Given** a suíte de smoke do repositório, **When** é executada, **Then** todos os
   testes de smoke passam sem configuração manual além do ambiente padrão de
   desenvolvimento.

---

### User Story 2 - Esqueleto de módulos de domínio com fronteiras rígidas (Priority: P2)

Uma desenvolvedora abre o repositório e encontra, de imediato, a organização em
módulos de domínio (`auth`, `employees`, `tourists`, `tourist_spots`, `events`,
`gamification`, `visitation`, `dashboard`, `notifications`, `chatbot` — lista
canônica em `DOMAIN_MODULES`, `core/modules.py`), cada um com as mesmas camadas
internas (routes, services, repositories, schemas).
As rotas de cada módulo já estão montadas na aplicação única. As fronteiras entre
módulos são verificáveis automaticamente: nenhum módulo importa os internals
privados (models, schemas, repositories) de outro.

**Why this priority**: A estrutura de módulos é o contrato arquitetural do monolito
modular (constituição, regra 2–5). Estabelecê-la vazio porém íntegro evita retrabalho
e garante que RFs futuros nasçam dentro dos limites corretos (RNF20).

**Independent Test**: Inspecionar a árvore de pacotes e executar uma verificação
estática de fronteiras presente na suíte de smoke; ela deve reportar zero violações
e a aplicação continua subindo e respondendo.

**Acceptance Scenarios**:

1. **Given** o repositório na fundação, **When** a árvore
   `src/passanorte_back/modules` é inspecionada, **Then** cada um dos 10 módulos
   de domínio existe com as camadas routes/services/repositories/schemas.
2. **Given** a aplicação no ar, **When** a documentação da API é consultada,
   **Then** cada módulo aparece como grupo de rotas (ainda sem endpoints de
   negócio nesta fase).
3. **Given** a suíte de smoke com verificação estática de fronteiras, **When**
   executada, **Then** não há imports cruzados de internals privados entre módulos.
4. **Given** um import deliberadamente ilegal introduzido em um módulo, **When** a
   verificação de fronteiras roda, **Then** ela falha apontando o módulo e o arquivo
   ofensores.

---

### User Story 3 - Configuração inteiramente externa ao código (Priority: P3)

Uma operadora adapta a instalação para outra cidade ou ajusta parâmetros de operação
(segredo de sessão, tempo de expiração, raio padrão de tolerância de presença,
idiomas habilitados) alterando apenas variáveis de ambiente e arquivos de dados —
sem tocar em nenhuma linha de lógica (RNF06). Segredos como a chave de assinatura
de sessão nunca estão no código ou no repositório.

**Why this priority**: Portabilidade por configuração é princípio constitucional
(RNF06) e desbloqueia implantação segura em produção; vem depois do app executável
porque precisa de aplicação que a consuma, antes da primeira feature de negócio.

**Independent Test**: Apontar o ambiente para outra cidade/idiomas e reiniciar: a
aplicação reflete a mudança sem alteração de código; repositório auditado não
contém segredos nem dados de cidade codificados.

**Acceptance Scenarios**:

1. **Given** a aplicação, **When** o ambiente define URL do banco, segredo e tempo
   de expiração de sessão, raio padrão de tolerância GPS, cidade padrão e idiomas
   habilitados, **Then** a aplicação carrega esses valores na inicialização.
2. **Given** a variável esencial ausente (ex.: segredo de sessão), **When** a
   aplicação é iniciada, **Then** ela falha cedo com mensagem explícita sobre o
   item de configuração faltante — nunca sobe com segredo de exemplo.
3. **Given** o repositório, **When** os dados de cidade padrão e idiomas habilitados
   são localizados, **Then** residem em arquivos de configuração/dados, não
   embutidos em lógica.
4. **Given** um novo idioma habilitado adicionado à configuração, **When** a
   aplicação reinicia, **Then** o novo idioma passa a compor os idiomas suportados
   sem mudanças de código.

---

### User Story 4 - Persistência versionada e portável entre bancos (Priority: P4)

Uma desenvolvedora executa a migração inicial sobre um banco de dados relacional
vazio, com sucesso; em produção o banco é um sistema relacional completo de servidor,
e nos testes um banco leve local ou em memória, sem alteração de código da aplicação
(RNF17). O schema evolui por migrações versionadas reversíveis a partir de agora.

**Why this priority**: Toda a primeira funcionalidade de negócio (auth, cadastros)
depende de persistência estabelecida; mas ela é consumível apenas em conjunto com
história 1–3, por isso P4.

**Independent Test**: Aplicar a migração inicial em banco vazio, verificar que as
tabelas base da fundação existem e que a migração reverte limpo; smoke tests
correm contra banco leve sem código condicional de banco espalhado pela aplicação.

**Acceptance Scenarios**:

1. **Given** um banco de produção vazio, **When** a migração inicial é aplicada,
   **Then** conclui com sucesso criando a estrutura base da fundação.
2. **Given** a migração inicial aplicada, **When** sua reversão é executada,
   **Then** o banco retorna ao estado vazio sem erros.
3. **Given** a suíte de testes, **When** executada, **Then** roda contra banco leve
   (em memória ou arquivo temporário) configurado pelo ambiente de teste, sem
   alterar o banco de desenvolvimento.
4. **Given** a aplicação com qualquer um dos perfis (produção ou teste), **When**
   inicia, **Then** adota o banco apontado exclusivamente pela configuração, sem
   código específico por banco espalhado pela aplicação.

---

### User Story 5 - Infraestrutura de auditoria pronta para uso (Priority: P5)

Uma desenvolvedora de feature futura (ex.: cadastro de pontos turísticos) tem à
disposição um serviço de auditoria que produz registros estruturados de ações
administrativas — quem executou, o quê, em qual alvo, quando, com qual resultado —
sem precisar reinventar o formato em cada módulo (RNF19). Nesta fase o serviço é
exercitado apenas pela suíte de smoke; nenhum RF de negócio o invoca ainda.

**Why this priority**: A infraestrutura precisa existir antes da primeira ação
administrativa real, mas só ganha consumidor quando as features de negócio chegarem.

**Independent Test**: Registrar uma ação administrativa simulada pela suíte de
smoke e inspecionar o registro produzido: estruturado, com todos os campos
obrigatórios presentes e legível por máquina.

**Acceptance Scenarios**:

1. **Given** o serviço de auditoria da fundação, **When** uma ação administrativa
   simulada é registrada, **Then** um registro estruturado é emitido contendo,
   no mínimo: data/hora, identificador do ator, tipo de ação, alvo da ação e
   resultado.
2. **Given** registros de auditoria emitidos, **When** inspecionados, **Then**
   são legíveis por máquina (formato estruturado, não linhas de texto livre).
3. **Given** uma ação registrada que falhou parcialmente, **When** o registro é
   emitido, **Then** o resultado da ação (sucesso/falha) é indicado no registro.

---

### Edge Cases

- O que acontece quando a variável de ambiente do banco aponta para um banco
  indisponível? A aplicação sobe (o processo está vivo) e a verificação de
  saúde responde HTTP 503 sinalizando a degradação do banco, em vez de
  apresentar-se como totalmente saudável.
- O que acontece quando a variável do raio de tolerância GPS recebe um valor inválido
  (ex.: não numérico, zero ou negativo)? A aplicação falha na inicialização com
  mensagem clara, pois um raio inválido corromperia toda validação de presença futura
  (Princípio IV da constituição).
- O que acontece quando a variável de idiomas habilitados recebe uma lista vazia?
  Se explicitamente definida como vazia, a aplicação falha na inicialização com
  mensagem clara: uma instalação sem idioma habilitado é erro de configuração, não
  um estado operável a mascarar silenciosamente. Quando não definida no ambiente,
  o idioma padrão vem do arquivo de dados de localidade.
- O que acontece quando o registro de auditoria não pode ser emitido (recurso de
  saída indisponível)? A ação de negócio não deve ser mascarada como bem-sucedida:
  o serviço de auditoria sinaliza a falha ao chamador.
- O que acontece quando dois módulos precisam da mesma dependência técnica (ex.:
  sessão de banco)? O compartilhamento ocorre apenas pela infraestrutura comum da
  aplicação, nunca por import direto do interno de outro módulo.

## Requirements *(mandatory)*

### Functional Requirements

**Estrutura e módulos (Monolito Modular)**

- **FR-001**: A aplicação MUST possuir um único ponto de entrada executável que
  monta as rotas de todos os módulos de domínio em um único processo de API
  (constituição, regras 1–2).
- **FR-002**: O repositório MUST conter pacotes separados para os 10 módulos de
  domínio em `src/passanorte_back/modules/`: `auth`, `employees`, `tourists`,
  `tourist_spots`, `events`, `gamification`, `visitation`, `dashboard`,
  `notifications`, `chatbot` — nomes canônicos em inglês, espelhados pela lista
  `DOMAIN_MODULES` em `core/modules.py` (RNF20; constituição, regras 2 e 4 e
  Princípio VII; nomenclatura English-only NON-NEGOTIABLE).
- **FR-003**: Cada módulo de domínio MUST expor a mesma organização interna em
  camadas — `routes/`, `services/`, `repositories/`, `schemas/` — sob
  `src/passanorte_back/modules/<domain>/`; a infraestrutura compartilhada
  (config, db, routers, audit, verificação de fronteiras, `DOMAIN_MODULES`)
  reside em `src/passanorte_back/core/` (RNF20; constituição, regra 4).
- **FR-004**: Um módulo MUST NOT importar internals privados (models, schemas
  internos, repositories) de outro módulo de domínio; comunicação entre módulos
  ocorre exclusivamente por funções de serviço públicas do módulo dono dos dados
  (constituição, regras 3 e 5).
- **FR-005**: A verificação de fronteiras entre módulos MUST ser automatizada na
  suíte de smoke, de modo que violações quebrem o build de teste.
- **FR-006**: Cada módulo MUST estar registrado na aplicação única como grupo de
  rotas, ainda que sem endpoints de negócio nesta fase (RNF03; constituição,
  Princípio I). O contrato de negócio é montado sob o prefixo versionado
  `/api/v1`; a verificação de saúde (`/health`) e a documentação dos contratos
  ficam na raiz, fora do prefixo.
- **FR-007**: Nenhum requisito funcional de negócio (RFs de `docs/SYSTEM_REQUIREMENTS.md`)
  MUST ser implementado nesta fase; módulos contêm apenas o esqueleto.

**Verificação de saúde**

- **FR-008**: A aplicação MUST expor um endpoint de verificação de saúde, sem
  autenticação, que responde informando o estado da aplicação.
- **FR-009**: A verificação de saúde MUST refletir o estado do banco de dados
  indicado pela configuração: responde com sucesso (HTTP 200) informando o estado
  da aplicação e do banco quando ambos estiverem saudáveis, e responde com o
  código HTTP 503 informando a degradação quando o banco estiver inacessível.

**Configuração (Portabilidade por Configuração)**

- **FR-010**: A aplicação MUST carregar toda a configuração operacional de
  variáveis de ambiente, incluindo no mínimo: endereço do banco de dados,
  segredo de assinatura de sessão, tempo de expiração da sessão, raio padrão de
  tolerância de presença GPS, cidade padrão e idiomas habilitados (RNF06, RNF14;
  constituição, Princípio VI). Itens não definidos no ambiente adotam o default
  documentado: TTL de sessão de 3600 s; raio padrão de tolerância de 100 m;
  cidade padrão e idiomas habilitados lidos do arquivo de dados de localidade
  (pt-BR).
- **FR-011**: Segredos MUST ser carregados exclusivamente de variáveis de
  ambiente; nenhum segredo hardcoded no código ou em arquivo versionado.
- **FR-012**: A ausência de um item de configuração essencial MUST interromper a
  inicialização com mensagem explícita identificando o item faltante. São
  essenciais apenas o endereço do banco de dados e o segredo de assinatura de
  sessão; os demais itens admitem defaults documentados (ver FR-010).
- **FR-013**: Dados de cidade (nome, contexto de localidade) e de idiomas
  habilitados MUST residir em arquivos de configuração/dados, não em lógica de
  código (RNF06; constituição, Princípio VI).

**Persistência**

- **FR-014**: A aplicação MUST usar acesso a dados sobre banco relacional
  estruturado, com PostgreSQL como banco de produção e banco leve (SQLite,
  memória ou arquivo temporário) para testes, escolhido apenas pela configuração
  (RNF17; constituição, stack obrigatória).
- **FR-015**: A evolução do schema de banco MUST ocorrer por migrações
  versionadas, aplicáveis e reversíveis.
- **FR-016**: A migração inicial MUST ser aplicada com sucesso sobre banco vazio
  nos dois perfis (produção e teste).

**Auditoria (infraestrutura)**

- **FR-017**: A aplicação MUST disponibilizar um serviço de auditoria, acessível
  a qualquer módulo, que registra ações administrativas em formato estruturado
  (legível por máquina) contendo, no mínimo: data/hora, ator, tipo de ação, alvo
  e resultado (RNF19; constituição, Princípio II).
- **FR-018**: O serviço de auditoria MUST sinalizar ao chamador quando um registro
  não pôde ser emitido.
- **FR-019**: O formato e o ponto de consumo do serviço de auditoria MUST ser
  definidos uma única vez na infraestrutura comum — cada módulo consome o serviço,
  sem implementar seu próprio formato de auditoria.

**Qualidade e governança**

- **FR-020**: Todo o código MUST ser tipado e manter o pipeline de qualidade
  (linter/formatter) sem erros (RNF20; constituição, Princípio VII e Quality Gates).
- **FR-021**: Testes de smoke da fundação MUST cobrir, no mínimo: aplicação sobe e
  responde verificação de saúde, migração aplica e reverte, fronteiras entre módulos
  íntegras, configuração carregada do ambiente, e emissão de registro de auditoria
  (constituição, Princípio III).

### Key Entities *(include if feature involves data)*

- **Configuração da aplicação**: coleção de valores operacionais carregados do
  ambiente na inicialização (banco, sessão, geolocalização, cidade e idiomas);
  imutável durante a execução.
- **Dados de localidade**: conjunto de arquivos de dados descrevendo a cidade
  atendida (nome, contexto de localidade) e os idiomas habilitados; trocável sem
  alteração de código.
- **Registro de auditoria**: evento estruturado gerado pelo serviço de auditoria,
  descrevendo quem (ator), o quê (ação), sobre o quê (alvo), quando (data/hora) e
  como terminou (resultado); nesta fase emitido em log estruturado, persistência
  própria em tabela ficará explícita em feature futura se necessário.
- **Módulo de domínio**: unidade organizacional da aplicação correspondendo a um
  bounded context, com fronteira privada (models/schemas/repositórios) e interface
  de serviço pública; espelha o corte de microsserviços previsto nos requisitos.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: De repositório clonado a aplicação respondendo a verificação de
  saúde, a operação completa (instalar dependências, configurar ambiente, subir,
  verificar) leva no máximo 15 minutos seguindo apenas a documentação do
  repositório.
- **SC-002**: A verificação de saúde responde em menos de 1 segundo no ambiente de
  desenvolvimento.
- **SC-003**: A migração inicial aplica-se a um banco vazio em menos de 30 segundos
  e reverte sem erro, nos dois perfis de banco.
- **SC-004**: A suíte de smoke da fundação completa em menos de 1 minuto com 100%
  de aprovação, cobrindo: saúde, migrações, fronteiras de módulo, configuração e
  auditoria.
- **SC-005**: A verificação automatizada de fronteiras reporta zero violações; ao
  introduzir um import ilegal deliberado, a verificação falha e o build de teste
  quebra (testado uma vez, manualmente, para provar a eficácia).
- **SC-006**: Adaptar a instalação para outra cidade e adicionar um idioma exige
  apenas editar dados de configuração e reiniciar — nenhuma linha de lógica alterada
  (verificável comparando duas execuções com conjuntos de dados diferentes e código
  idêntico).
- **SC-007**: Toda ação administrativa simulada na suíte de smoke gera exatamente um
  registro de auditoria estruturado com os cinco campos obrigatórios; registros são
  100% legíveis por máquina.
- **SC-008**: Um desenvolvedor novo no projeto consegue localizar o arquivo responsável
  por cada uma das camadas (rotas/serviços/repositórios/schemas) de qualquer um dos
  10 módulos em menos de 2 minutos, usando apenas a estrutura de diretórios e o README.

## Assumptions

- A stack tecnológica da constituição (Python 3.13, FastAPI, Pydantic v2, SQLAlchemy,
  Alembic, PostgreSQL/SQLite, uv, ruff) é mandatória e não reaberta nesta spec —
  tecnologia aqui é escopo, não detalhe de implementação.
- O PostgreSQL de produção pode não existir fisicamente nesta fase; o perfil de
  produção é validado por migração executada localmente contra servidor PostgreSQL
  (via container, por exemplo), enquanto o fluxo diário de desenvolvimento usa o
  perfil leve.
- Nesta fase, os registros de auditoria são emitidos em log estruturado
  (saída padrão em formato legível por máquina). A persistência de auditoria em
  tabela do banco ficará para a primeira feature que introduzir ações administrativas
  reais, caso ali se mostre necessária (YAGNI; Princípio V).
- Os endpoints dos módulos nesta fase existem apenas como grupos montados na
  aplicação; routers vazios (sem operações) são aceitáveis e não violam o contrato
  API-Contract-First, pois nenhum RF de negócio é implementado.
- Lista de idiomas habilitados vazia (quando explicitamente definida) ou raio de
  tolerância não positivo são erros de configuração: a inicialização interrompe
  com mensagem explícita (complementa FR-012 para valores presentes porém
  inválidos).
- Defaults adotados nesta fase: TTL de sessão de 3600 s, raio padrão de
  tolerância de 100 m, cidade padrão e idiomas a partir do arquivo de dados de
  localidade (pt-BR). Deploy pode sobrescrever todos via ambiente (RNF06).
- A estrutura de diretórios `src/passanorte_back` já é o formato exigido pelo
  projeto (layout src, gerenciado por uv); testes de smoke usam o mesmo perfil de
  banco leve da constituição (SQLite em memória).