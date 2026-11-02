# Specs do Projeto PassaNorte (Backend FastAPI)

> Especificações derivadas de `docs/SYSTEM_REQUIREMENTS.md`, organizadas como
> features incrementais para o fluxo Spec Kit. Cada spec tem um prompt pronto
> para colar após o comando `/speckit-specify` (ver seção de cada spec).
>
> Ordem de entrega = sequência recomendada de implementação. Cada spec
> aproveita o que as anteriores já entregam.
>
> Conforme a constituição v1.1.0 (Princípio VII, English-only NON-NEGOTIABLE),
> os módulos de domínio usam **nomes canônicos em inglês** — a lista canônica
> é `DOMAIN_MODULES` em `src/passanorte_back/core/modules.py` e os prefixos
> HTTP são `/api/v1/<nome>` (com `_` → `-`). Termos em português de
> documentos de entrada (ex.: `funcionarios`) são traduzidos ao nome canônico
> (ex.: `employees`) antes de virar código.

## Índice

| # | Feature | Módulo(s) de domínio | Requisitos | Status |
| --- | --- | --- | --- | --- |
| 001 | Fundação do Monolito Modular | infra transversal (`core/`) | RNF01*, RNF03, RNF17, RNF06, RNF19, RNF20 | ✅ Implementada |
| 002 | Autenticação e Controle de Acesso | `auth`, `employees` | RF01–RF05, RF23, RNF09, RNF10 | ✅ Implementada |
| 003 | Turistas e Perfil | `tourists` | RF22, RF24, RF25, RNF08 | ✅ Implementada |
| 004 | Containerização da API e Ambiente Docker | infra (Docker/Compose) | RNF17, RNF15 | — |
| 005 | Contrato HTTP em camelCase (case conforme frontend TS) | infra transversal (`core/`) + módulos existentes | — (transversal, contrato JSON) | — |
| 006 | Organização do Swagger por Tags | infra transversal (`core/`) + módulos existentes | — (transversal, documentação OpenAPI) | — |
| 007 | Pontos Turísticos | `tourist_spots` | RF11–RF15, RF27 | — |
| 008 | Eventos | `events` | RF16, RF17 | — |
| 009 | Rotas Turísticas e Gamificação | `gamification` | RF18–RF20, RF29, RF30, RF34–RF36 | — |
| 010 | Visitação Geolocalizada | `visitation` | RF31–RF33, RNF14 | — |
| 011 | Resgate de Brindes | `gamification` | RF21 | — |
| 012 | Descoberta no Passaporte | `tourist_spots` | RF26, RF28, RNF12, RNF18 | — |
| 013 | Dashboard e Insights | `dashboard` | RF06–RF10 | — |
| 014 | Notificações por Interesse | `notifications` | RF37 | — |
| 015 | Chatbot de Planejamento (RAG) | `chatbot` | RF38, RF39 | — |

> `*` RNF01/RNF02/RNF07 (sistema distribuído/microsserviços): **deliberadamente
> adaptados** nesta fase. Ver `docs/CONSTITUTION.md` — o monolito modular
> preserva as fronteiras de domínio para extração futura de microsserviços.

---

## 001 — Fundação do Monolito Modular

**Status:** ✅ Implementada e convergida (`specs/001-fundacao-monolito-modular/`).

**Escopo:** estrutura do projeto como módulos de domínio independentes, em
`src/passanorte_back/modules/<domain>/` (nomes canônicos em inglês: `auth`,
`employees`, `tourists`, `tourist_spots`, `events`, `gamification`,
`visitation`, `dashboard`, `notifications`, `chatbot`), cada um com camadas
`routes/`, `services/`, `repositories/`, `schemas/`; infraestrutura comum em
`src/passanorte_back/core/` (config, db, audit, routers, `modules.py` com a
lista canônica `DOMAIN_MODULES`, `boundaries.py` com a verificação AST de
fronteiras); app FastAPI único com routers sob `/api/v1` + `/health` na raiz
(200/503) e lifespan que descarta a engine no shutdown; settings via
pydantic-settings; banco relacional (PostgreSQL em produção, SQLite para
testes) com SQLAlchemy 2.0 + Alembic (migration baseline aplicável e
reversível); auditoria estruturada log-only (1 linha JSON por ação);
configuração de cidade/idiomas em `config/location.json` (RNF06).

**Fora de escopo:** toda lógica de negócio dos RFs (spec 002 em diante).

### Prompt (original usado para implementar — registro histórico)

```text
Implementar a fundação do backend PassaNorte como um MONOLITO MODULAR em FastAPI (Python 3.13, uv), conforme docs/CONSTITUTION.md. Requisitos: (a) estrutura src/passanorte_back com pacote de módulos de domínio auth, funcionarios, turistas, pontos_turisticos, eventos, gamificacao, visitacao, dashboard, notificacoes, chatbot, cada um com subpastas routes/services/repositories/schemas, sem imports cruzados de internals privados entre módulos; (b) app FastAPI único em src/passanorte_back/main.py montando routers por módulo e /health; (c) settings via pydantic-settings com variáveis de ambiente (DATABASE_URL, JWT_SECRET, JWT_TTL, raio padrão de tolerância GPS, cidade padrão, idiomas habilitados); (d) persistência com SQLAlchemy 2.0 + Alembic, PostgreSQL em produção e SQLite para testes (RNF17); (e) infra de auditoria: serviço de log estruturado para ações administrativas (RNF19); (f) configuração de dados de cidade/idiomas em settings/dados, não em código (RNF06). Requisitos de referência: RNF03, RNF06, RNF17, RNF19, RNF20. Não implementar RFs de negócio nesta fase. Critério de aceitação: app sobe, /health responde, migration inicial roda, testes de smoke passam.
```

---

## 002 — Autenticação e Controle de Acesso

**Escopo:** script de geração de credenciais de administrador de alto nível
(RF01); login do painel para admin e funcionário (RF02); RBAC admin total vs.
funcionário restrito (RF03); CRUD de funcionários com credenciais de acesso
restrito (RF04, RF05); JWT com expiração/renovação (RNF09); senhas com bcrypt
(RNF10); login do turista já previsto no contrato (RF23 conecta com spec 003).

**Fora de escopo:** perfil do turista (spec 003); endpoints de negócio que virão
nas demais specs.

### Prompt

```text
Implementar Autenticação e Controle de Acesso do PassaNorte (backend FastAPI, módulos auth e employees) conforme docs/CONSTITUTION.md e docs/SYSTEM_REQUIREMENTS.md. Requisitos: RF01 — script de geração de credenciais de administrador de alto nível para acesso ao painel (dashboard, pontos, eventos, funcionários, recompensas), segredos via variáveis de ambiente; RF02 — endpoints de login para administradores e funcionários do painel web; RF03 — RBAC: administrador tem acesso total, funcionário acessa apenas concessão de benefícios (sem cadastro de pontos turísticos e sem visualização do dashboard); RF04 — admin cadastra funcionários gerando credenciais de acesso restrito; RF05 — admin edita dados ou revoga acesso de funcionário. RNF09 — autenticação por JWT com expiração e renovação controladas; RNF10 — senhas com hash bcrypt, nunca texto plano. Estrutura em camadas (routes/services/repositories/schemas) dentro dos módulos. Critério de aceitação: testes de contrato cobrindo login válido/inválido, renovação de token, 401 sem token, 403 de funcionário tentando endpoint administrativo; teste de integração do ciclo de vida do funcionário (criar → editar → revogar → login bloqueado).
```

---

## 003 — Turistas e Perfil

**Escopo:** cadastro único de turista com telefone, e-mail, CPF ou passaporte,
país de origem, nome e sobrenome (RF22); login do turista na aplicação
Passaporte (RF23); visualização e edição dos próprios dados (RF24); seleção de
categorias de interesse para personalização (RF25); criptografia de dados
sensíveis conforme LGPD (RNF08).

**Fora de escopo:** endpoints de descoberta (spec 012), gamificação (spec 009).

### Prompt

```text
Implementar Turistas e Perfil do PassaNorte (backend FastAPI, módulo tourists), reutilizando a fundação de JWT e RBAC da spec 002 (docs/CONSTITUTION.md). Requisitos: RF22 — cadastro único de turista com telefone, e-mail, CPF ou número de passaporte, país de origem, nome e sobrenome; RF23 — autenticação do turista na aplicação Passaporte pelas credenciais cadastradas; RF24 — turista visualiza e edita seus próprios dados cadastrais; RF25 — turista seleciona categorias de interesse (ex.: gastronomia, natureza, cultura) para personalização de conteúdo e notificações, com opção de atualizar a seleção. RNF08 — dados sensíveis (CPF, passaporte, telefone, e-mail) armazenados de forma criptografada em conformidade com a LGPD; RNF10 — hash de senha. A lista de categorias de interesse deve ser configurável (RNF06). Critério de aceitação: testes de contrato do cadastro (validação de CPF/passaporte/e-mail), login do turista, edição restrita ao próprio perfil (403 em edição de outro usuário), e teste de integração cadastro → login → editar perfil → atualizar interesses; dado sensível nunca retornado em leitura de repositório sem descriptografia controlada.
```

---

## 004 — Containerização da API e Ambiente Docker

**Escopo:** containerização da API com Dockerfile multi-stage (Python 3.13 +
uv) e `.dockerignore`; ambiente de desenvolvimento local via Docker Compose com
três serviços: `api` (FastAPI sob uvicorn), `db` (PostgreSQL com volume
persistente e healthcheck) e `dbgate` (UI web para inspecionar o Postgres) — o
DbGate deve abrir em `http://localhost:8080` com a conexão ao Postgres **já
pré-configurada** (via variável de ambiente `CONNECTIONS` do DbGate, em JSON,
apontando para o serviço `db` com credenciais do `.env`); a API aplica
migrations automaticamente (`alembic upgrade head`) antes de subir;
configuração 100% por variáveis de ambiente através de `.env` (`.env.example`
com valores não-secretos cometidos; `.env` no `.gitignore`). Reforça RNF17 —
o ambiente containerizado roda PostgreSQL end-to-end, alinhando dev e
produção (testes de unidade/contrato continuam em SQLite) — e RNF15
(stack de desenvolvimento sem custo, imagens oficiais gratuitas). O
`compose.yaml` existente na raiz é apenas um esqueleto com placeholders; esta
spec o materializa.

**Fora de escopo:** CI/CD e deploy em nuvem; reverse proxy/TLS; trocar o banco
dos testes; imagens de produção em registry.

### Prompt

```text
Containerizar a API do PassaNorte (FastAPI, Python 3.13, uv) e criar o ambiente de desenvolvimento local com Docker Compose, conforme docs/CONSTITUTION.md (monolito modular). Requisitos: (a) Dockerfile multi-stage — stage de build com uv para sincronizar dependências (pyproject/uv.lock) e stage de runtime slim, usuário não-root, sem segredos na imagem, porta da API exposta, process iniciado com uvicorn; (b) .dockerignore excluindo .venv, __pycache__, tests, specs, docs, .git, caches e artefatos locais; (c) compose.yaml com os serviços: db (imagem official do PostgreSQL, volume nomeado para os dados, healthcheck pg_isready, credenciais via .env), api (build do Dockerfile, env_file .env, DATABASE_URL apontando para o serviço db, depends_on com condição service_healthy, executa alembic upgrade head antes de subir o uvicorn) e dbgate (imagem dbgate/dbgate, porta 8080, conexão ao Postgres PRÉ-CONFIGURADA via variável CONNECTIONS em JSON — conId, engine postgres@dbgate, server db, port 5432, user/password/database do .env — para que ao abrir http://localhost:8080 a conexão já exista sem digitação). (d) Nenhum segredo real no repositório: .env.example documentando as variáveis (DATABASE_URL, POSTGRES_*, credenciais do DbGate), .env no .gitignore. (e) Não alterar lógica de negócio nem fronteira de domínios existentes (specs 001-003). Critério de aceitação: docker compose up --build sobe os três serviços; /health responde HTTP 200 com o banco PostgreSQL conectado; migrations aplicadas (tabelas das specs 001-003 presentes no Postgres); DbGate acessível em http://localhost:8080 mostrando a conexão pré-carregada e navegando nas tabelas; docker compose down + up reutiliza o volume sem perder dados.
```

---

## 005 — Convenção de Contrato da API (JSON camelCase)

**Escopo:** padronização transversal do contrato HTTP da API para espelhar o
frontend em TypeScript — e padrão global para todas as specs seguintes
(006–015). O JSON trocado com o frontend passa a ser 100% **camelCase**, tanto
na entrada quanto na saída (ex.: `accessToken`, `firstName`, `touristSpot`), via
alias de serialização global Pydantic (`alias_generator` to-camel, base comum
de schemas em `core/`) aplicado a todos os schemas de todos os módulos —
conversão apenas na fronteira HTTP: identificadores Python internos e colunas
de banco permanecem snake_case (PEP 8). A API **aceita apenas chaves
camelCase** em corpos de requisição: chaves snake_case ou desconhecidas
resultam em 422 com mensagem clara; respostas, payloads de erro e estruturas
aninhadas também em camelCase. Nomes de tipos/schemas (classes Pydantic e os
tipos/interface TypeScript gerados a partir do OpenAPI/Swagger) ficam em
**PascalCase**, refletindo o frontend TS. Migração retroativa dos endpoints já
implementados (auth, employees, tourists — specs 002–004), com atualização dos
testes de contrato e do frontend em conjunto.

**Fora de escopo:** mudança de caminhos HTTP (`/api/v1/...` em kebab-case,
conforme `DOMAIN_MODULES`); lógica de negócio; migrations (colunas do banco
permanecem snake_case).

### Prompt

```text
Implementar a convenção de contrato JSON camelCase da API PassaNorte como infra transversal do monolito modular (docs/CONSTITUTION.md), em core/ + adaptação dos módulos auth, employees e tourists das specs 002-004. Requisitos: (a) em core/, base comum de schemas (Pydantic BaseModel com alias_generator camelCase) aplicada a TODOS os schemas de todos os módulos: entrada e saída HTTP em JSON 100% camelCase (ex.: accessToken, firstName, touristSpot), refletindo os tipos TypeScript do frontend, com conversão apenas na borda HTTP — identificadores Python internos e colunas de banco permanecem snake_case (PEP 8); (b) a API ACEITA APENAS chaves camelCase: corpo com chave snake_case ou desconhecida resulta em 422 com mensagem clara; payloads de erro, respostas de exceção e estruturas aninhadas também em camelCase; (c) nomes de classes de schema/DTO (e os tipos gerados no OpenAPI/Swagger) em PascalCase, servindo o Swagger como fonte para os tipos TypeScript do frontend; (d) migração retroativa dos endpoints já implementados (specs 002-004: auth, employees, tourists) para o novo contrato, atualizando os testes de contrato existentes; (e) sem alterar caminhos de rotas (/api/v1/... em kebab-case) nem lógica de negócio. Critério de aceitação: teste transversal que varre respostas de todos os endpoints e falha se qualquer chave snake_case aparecer; testes de contrato demonstrando entrada camelCase aceita, entrada snake_case rejeitada (422) e os endpoints de auth/employees/tourists validados sob o novo contrato retroativamente.
```

---

## 006 — Organização do Swagger por Tags

**Escopo:** organização transversal da documentação OpenAPI/Swagger — padrão
global para todas as specs seguintes (007–015) e retroativo aos endpoints já
implementados (specs 002–005). Nenhum endpoint da API pode aparecer na tag
`default` do Swagger: todo endpoint é obrigatoriamente agrupado em uma tag
explícita, uma por módulo de domínio (nomes canônicos em inglês, Princípio
VII: `Auth`, `Employees`, `Tourists`, `Tourist Spots`, `Events`,
`Gamification`, `Visitation`, `Dashboard`, `Notifications`, `Chatbot`) mais
uma tag de infraestrutura (ex.: `Health`). O registro central de tags vive em
`core/` (metadados `openapi_tags` com nome, descrição e ordem de exibição,
derivable de `DOMAIN_MODULES` no app FastAPI) e é a única fonte de verdade —
os routers de cada módulo declaram `tags=[...]` apontando para as constantes
do registro, sem strings soltas espalhadas. Migração retroativa de todos os
endpoints existentes (auth, employees, tourists, `/health`) para o regime de
tags.

**Fora de escopo:** mudança de caminhos HTTP, de contrato JSON ou de lógica de
negócio; geração de clientes TypeScript (o frontend consome as tags, mas
gerá-los é trabalho do frontend).

### Prompt

```text
Implementar a organização do Swagger por tags da API PassaNorte como infra transversal do monolito modular (docs/CONSTITUTION.md), em core/ + adaptação dos módulos auth, employees e tourists das specs 002-005. Requisitos: (a) registro central de tags em core/ metadados openapi_tags do app FastAPI com nome, descrição e ordem de exibição, uma tag por módulo de domínio com nomes canônicos em inglês (Auth, Employees, Tourists, Tourist Spots, Events, Gamification, Visitation, Dashboard, Notifications, Chatbot) e uma tag de infraestrutura para /health — única fonte de verdade, sem strings de tag soltas nos módulos; (b) TODOS os endpoints da API declarados explicitamente com sua tag via tags=[...] nos routers/operações — NENHUM endpoint pode ficar na tag default do Swagger; endpoints sem tag explícita devem ser tratados como erro; (c) migração retroativa de todos os endpoints já existentes (auth, employees, tourists, /health) com atualização dos testes de contrato existentes; (d) sem alterar caminhos de rotas, contrato JSON (camelCase da spec 005) nem lógica de negócio. Critério de aceitação: teste transversal que varre o OpenAPI gerado e falha se qualquer operação estiver sem tag, com a tag default, ou com uma tag fora do registro central; teste validando que cada módulo aparece agrupado sob exatamente a sua tag no Swagger.
```

---

## 007 — Pontos Turísticos

**Escopo:** CRUD de pontos turísticos com nome, descrição, categoria,
localização lat/lng (RF11, RF12); associação a uma ou mais categorias
pré-definidas (RF13); cronograma de dias e horários de funcionamento (RF14);
status aberto/fechado temporariamente/fechado permanentemente (RF15);
integração com Google Maps/OSM para dados de localização (RNF18, no contratado
de dados, não de frontend); auditoria de ações administrativas (RNF19);
endpoint de detalhes do ponto usado pelo Passaporte (RF27).

**Fora de escopo:** ordenação por relevância (spec 012), eventos (spec 008).

### Prompt

```text
Implementar Gerenciamento de Pontos Turísticos do PassaNorte (backend FastAPI, módulo tourist_spots), protegido por RBAC de administrador (spec 002). Requisitos: RF11 — administrador cadastra ponto turístico com nome, descrição, localização (latitude/longitude) e categoria; RF12 — edição e remoção de ponto turístico; RF13 — associação de cada ponto a uma ou mais categorias pré-definidas (lazer, cultura, gastronomia, natureza, arte, cinema, extensível); RF14 — cadastro de cronograma de dias e horários de funcionamento por ponto; RF15 — status do ponto: aberto ao público, temporariamente fechado ou fechado permanentemente, com filtro por status; RF27 — endpoint público de detalhes do ponto (descrição, categoria, horários, status, eventos associados) consumido pela aplicação Passaporte — incluir campo calculado de links para Google Maps (RNF18). RNF19 — audit logs nas ações administrativas de criação/edição/remoção. Coordenadas validadas como decimais WGS-84. A lista de categorias padrão é configurável (RNF06). Todos os endpoints deste módulo agrupados sob a tag "Tourist Spots" do registro central de tags da spec 006. Critério de aceitação: testes de contrato do CRUD completo (201/200/204/403/404), validação de coordenadas, teste que valida o cronograma de funcionamento por dia/horário, teste de auditoria registrando ação do admin.
```

---

## 008 — Eventos

**Escopo:** cadastro de eventos associados a um ponto turístico com data,
descrição e preço do ingresso (RF16); edição e remoção (RF17); eventos
aparecem nos detalhes do ponto (RF26 usa data, spec 012).

**Fora de escopo:** recomendação por eventos recentes (spec 012), notificações
de novo evento (spec 014), custo em roteiro do chatbot (spec 015).

### Prompt

```text
Implementar Gerenciamento de Eventos do PassaNorte (backend FastAPI, módulo events), protegido por RBAC de administrador (spec 002). Requisitos: RF16 — administrador cadastra evento associado a um ponto turístico existente, informando data de ocorrência, descrição e preço do ingresso; RF17 — edição e remoção de evento. Regras: evento só referencia ponto não permanentemente fechado (bloqueio com 409); listagem de eventos por ponto e por faixa de datas para o painel; endpoints incluídos na resposta de detalhes do ponto (RF27 da spec 007). RNF19 — audit logs. Preço do ingresso armazenado como valor monetário explícito (necessário depois para o chatbot, RF39). Todos os endpoints deste módulo agrupados sob a tag "Events" do registro central de tags da spec 006. Critério de aceitação: testes de contrato do CRUD (incluindo 404 em ponto inexistente e 409 em ponto permanentemente fechado) e teste de integração criando ponto → criando evento → listando por ponto e por data.
```

---

## 009 — Rotas Turísticas e Gamificação

**Escopo (coração do produto):** cadastro de rota composta por lista ordenada de
pontos turísticos e brinde associado à conclusão (RF18); edição/remoção (RF19);
controle de estoque dos brindes por rota (RF20); inscrição do turista em rota
(RF29); acompanhamento de progresso com barra e pontos visitados/pendentes
(RF30); atualização automática do progresso quando um ponto é visitado (RF34);
insígnia digital na conclusão (RF35); código único de resgate na conclusão
(RF36).

**Fora de escopo:** validação GPS da visitação (spec 010), resgate pelo
funcionário (spec 011).

**Nota:** a interface de serviço de RF34 (atualização de progresso a partir de
visitação) é o contrato que o módulo `visitation` consumirá na spec 010.

### Prompt

```text
Implementar Rotas Turísticas e Gamificação do PassaNorte (backend FastAPI, módulo gamification), o núcleo do produto (docs/CONSTITUTION.md: monolito modular). Requisitos: RF18 — administrador cadastra rota turística composta por lista de pontos turísticos e brinde associado à conclusão; RF19 — edição e remoção de rota; RF20 — cadastro e controle da quantidade em estoque de cada brinde vinculado a uma rota, com reservas idempotentes (nenhuma concessão sem estoque); RF29 — turista se inscreve em rota disponível, iniciando o acompanhamento de progresso; RF30 — sistema exibe progresso da rota: pontos já visitados e pendentes, com taxa de conclusão calculada; RF34 — ao registrar a visitação de um ponto (entrada vinda via serviço, ainda sem GPS — spec 010 conectará), o sistema atualiza o progresso de TODAS as rotas em andamento do turista que contêm esse ponto; RF35 — ao concluir todos os pontos da rota, o turista recebe insígnia digital de conclusão; RF36 — na conclusão, o sistema gera código de resgate de uso ÚNICO, seguro, não previsível, para retirada do brinde quando o turista desejar e o ponto permitir. Regras de domínio: inscrição duplicada bloqueada (409); código único não reutilizável; estoque nunca fica negativo; remoção de rota preserva histórico de turistas ativos conforme decisão registrada na spec. Expor interface de serviço pública `register_spot_visit(tourist_id, tourist_spot_id)` para o módulo visitation consumir (fronteira de domínio; identificadores em inglês — constituição, Princípio VII). Todos os endpoints deste módulo agrupados sob a tag "Gamification" do registro central de tags da spec 006. Critério de aceitação: teste de integração completo — inscrever → visita de todos os pontos → insígnia emitida → código único gerado → segunda tentativa de uso do código falha; teste de concorrência/estoque insuficiente bloqueando conclusão do resgate.
```

---

## 010 — Visitação Geolocalizada

**Escopo:** botão "marcar visitação" recebendo leitura de GPS do turista e
ponto em que ele se declara (RF31); validação de presença via Haversine com
raio de tolerância configurável por ponto (RF32, RNF14); registro do status
"visitado" do ponto para o usuário (RF33); integração com gamificação via
interface de serviço da spec 009 (RF34).

**Depende de:** 007 (pontos) e 009 (interface de serviço).

### Prompt

```text
Implementar Visitação Geolocalizada do PassaNorte (backend FastAPI, módulo visitation). Requisitos: RF31 — turista aciona 'marcar visitação' estando em um ponto turístico cadastrado, enviando coordenadas GPS atuais e o ponto em questão; RF32 — o sistema valida a presença por Haversine entre coordenadas do GPS e do ponto, considerando raio de tolerância configurável por ponto turístico (default global em settings), sem falsos positivos evidentes; RF33 — após validação, grava status 'visitado' do ponto para o turista, com registro imutável de visitação (timestamp, coordenadas validadas); RF34 — após gravar, chama o serviço público de gamificação que atualiza progresso das rotas vinculadas (interface da spec 009) — nunca escreve diretamente nas tabelas de outro módulo (fronteira de domínio do monolito modular). Repetição de visitação não gera novas atualizações de progresso (idempotente) mas pode ser registrada como visita adicional. RNF14 — precisão geoespacial. Todos os endpoints deste módulo agrupados sob a tag "Visitation" do registro central de tags da spec 006. Critério de aceitação: testes unitários da fórmula de Haversine (casos exatos: dentro do raio, fora, borda, antípodas); teste de integração visitação válida → status gravado → progresso de rota atualizado; teste de visitação fora do raio rejeitada (409/422); teste de idempotência de visita repetida.
```

---

## 011 — Resgate de Brindes

**Escopo:** funcionário escaneia o código único gerado pelo turista para
validar e conceder o brinde correspondente (RF21); baixa automática no estoque
(RF20); apenas funcionários/admin têm acesso (RF03).

**Depende de:** 009 (código, estoque), 002 (RBAC funcionário).

### Prompt

```text
Implementar Resgate de Brindes do PassaNorte (backend FastAPI, módulo gamification), endpoint restrito a funcionários e administradores conforme RF03 (spec 002). Requisitos: RF21 — funcionário escaneia o código único gerado pelo turista em rota concluída; o sistema valida o código (existente, ainda não usado, do turista correto ou válido na entrega presencial) e concede o brinde correspondente, com BAIXA AUTOMÁTICA no estoque do brinde da rota (RF20), de forma transacional e idempotente: um código nunca gera duas baixas. Respostas: sucesso com dados do brinde e novo estoque; erro claro para código inválido, expirado (se aplicável), já utilizado ou rota sem estoque disponível. RNF19 — audit log do resgate (funcionário, turista, brinde, estoque antes/depois). Reuso: transação única sobre serviço público do módulo gamification — sem tocar tabelas de outro módulo. Todos os endpoints deste módulo agrupados sob a tag "Gamification" do registro central de tags da spec 006. Critério de aceitação: teste de contrato de resgate bem-sucedido reduzindo estoque; testes de falha: código inexistente, código duplicado (idempotência), estoque insuficiente bloqueando; teste de RBAC (turista não resgata, sem token 401); teste de auditoria.
```

---

## 012 — Descoberta no Passaporte

**Escopo:** tela inicial do Passaporte listando pontos ordenados por
relevância — combina interesses do usuário, proximidade geográfica e eventos
recentes (RF26); links de redirecionamento para Google Maps, Uber e 99 a
partir da localização do ponto (RF28); desempenho (RNF12); suporte a mapas
Google/OSM (RNF18).

**Depende de:** 003 (interesses), 007 (pontos), 008 (eventos).

### Prompt

```text
Implementar Descoberta no Passaporte do PassaNorte (backend FastAPI, módulos tourist_spots e gamification — endpoints públicos autenticados como turista, spec 002/003). Requisitos: RF26 — tela inicial exibe pontos turísticos ordenados por relevância considerando: interesses selecionados pelo turista (match de categorias), proximidade geográfica (distância Haversine a partir da localização atual enviada) e eventos recentes (eventos com data futura/próxima elevam o ponto); documentar a fórmula de score e permitir desempate determinístico; paginado. RF28 — além dos links para Google Maps (spec 007), gerar deep links para Uber e 99 a partir da localização do ponto, e endpoint que, recebendo a posição do turista, devolve os três links prontos (maps/de carro). RNF12 — consultas respondem em tempo hábil para mobile: implementar ordenação de forma consultável (no máximo O(n) por página, com índices apropriados), sem varredura cara por requisição; se necessário, cache configurável simples. RNF18 — suporte Google Maps ou OSM. Todos os endpoints deste módulo agrupados sob as tags de seus módulos (`Tourist Spots`, `Gamification`) do registro central da spec 006. Critério de aceitação: teste de contrato da listagem com ordenação por relevância (casos: usuário com interesses vs. sem interesses, sem posição enviada, com eventos vs. sem); teste dos geradores de deeplink para Google Maps, Uber e 99; teste de performance simples garantindo consulta paginada e ordenada dentro de limite definido na spec.
```

---

## 013 — Dashboard e Insights

**Escopo:** mapa de calor com concentração de visitas por região/ponto (RF06);
contador de acessos ao sistema em períodos configuráveis (RF07); ranking de
pontos turísticos por dia/mês/ano (RF08); distribuição de visitantes por país
de origem (RF09); distribuição por interesses (RF10). Todo endpoint restrito a
administrador (RF03 — funcionário não vê dashboard).

**Depende de:** 007 (pontos), 010 (visitados), 003 (país/interesses), 002
(admin RBAC, contagem de acessos).

### Prompt

```text
Implementar Dashboard e Insights do PassaNorte (backend FastAPI, módulo dashboard), endpoints restritos a administrador (RF03 — funcionário recebe 403). Requisitos: RF06 — mapa de calor da cidade com marcações de concentração de visitas por região/ponto turístico: endpoint que devolve lista (latitude, longitude, peso = nº de visitas) agregada por ponto/região configurável (RNF06: cidade é configurável, não hardcoded Manaus); RF07 — contador total de acessos ao sistema (aplicação Passaporte) em períodos configuráveis (hoje/semana/mês/custom) — instrumentar access log por requisição de turista a partir da spec 002, contando acessos únicos por turista/dia; RF08 — ranking de pontos turísticos mais visitados segmentado por dia, mês e ano, com top N configurável; RF09 — distribuição da proporção de usuários que visitaram pontos segmentada por país de origem cadastrado; RF10 — distribuição da proporção de usuários segmentada pelos interesses cadastrados no perfil. Toda métrica derivada de dados reais registrados (visitados, acessos, cadastros) — nunca inventada. Performance: agregações SQL, não laços em Python; índices adequados. Respeitar fronteira de domínio: dashboard LÊ (via consultas de leitura próprias/repositories de leitura) mas não escreve em outros módulos. Todos os endpoints deste módulo agrupados sob a tag "Dashboard" do registro central de tags da spec 006. Critério de aceitação: teste de integração popular visitações e cadastros de múltiplos turistas de países/interesses distintos e validar cada um dos cinco endpoints com dados esperados; teste de RBAC (funcionário → 403); teste de agregação por período.
```

---

## 014 — Notificações por Interesse

**Escopo:** turista se inscreve em interesses para receber notificações de
novos eventos/pontos/rotas relacionados (RF37, RF25 base). No monolito: tabela
de notificações gerada por eventos de negócio (novo evento, novo ponto, nova
rota) que casem com interesses do turista; entrega ao app por polling
(pull/GET), sem push service nesta fase (RNF15).

**Depende de:** 003 (interesses), 008 (eventos), 007, 009.

### Prompt

```text
Implementar Notificações por Interesse do PassaNorte (backend FastAPI, módulo notifications) no monolito modular. Requisitos: RF37 — turista se inscreve em interesses específicos para receber notificações relacionadas e também cancela a inscrição; quando um NOVO evento (spec 008), novo ponto turístico (spec 007) ou nova rota (spec 009) é cadastrado, gerar notificações para os turistas cujos interesses casem com as categorias do item (RFP25 como fonte de interesses). No monolito, a geração entra pelo serviço público de notifications (create_notification_for_interests) chamado pelos módulos emissores via interface de serviço — nunca escrevendo direto na tabela emissor; entrega ao app via endpoint GET de notificações não lidas/marcar como lida (polling), sem push nesta fase (RNF15 baixo custo). Conteúdo da notificação deve ser apresentável (título, descrição, tipo, referência ao item com ID para deep link). i18n-ready: título/descrição armazenados com possibilidade de localização futura (RNF16 low custo). Todos os endpoints deste módulo agrupados sob a tag "Notifications" do registro central de tags da spec 006. Critério de aceitação: teste de integração — turista com interesse 'gastronomia' recebe notificação quando admin cria evento/ponto/rota com categoria 'gastronomia', e NÃO recebe quando categoria não casa; teste de marcar como lida; teste de cancelamento de inscrição.
```

---

## 015 — Chatbot de Planejamento (RAG)

**Escopo:** chatbot de IA generativa com RAG que monta roteiros personalizados
em linguagem natural (RF38); considera custo dos ingressos, proximidade entre
pontos, interesses do usuário e horários de funcionamento (RF39).

**Depende de:** 007 (pontos/horários), 008 (eventos/preços), 003
(interesses).

**Decisões a definir na spec:** provedor de LLM com free tier (RNF15);
estratégia de RAG (embedding da base de pontos/eventos; recuperação por
similaridade + filtros estruturados); limite de contexto e custo por sessão.

### Prompt

```text
Implementar Chatbot de Planejamento de Roteiro do PassaNorte (backend FastAPI, módulo chatbot), IA generativa com RAG (RF38/RF39), autenticado como turista. Requisitos: RF38 — chatbot em conversa de linguagem natural monta roteiros personalizados com base nos pontos turísticos e eventos cadastrados no banco (fonte de verdade), e devolve roteiro estruturado (lista ordenada de pontos/eventos com horários sugeridos e custo total estimado) que pode ser visualizado no Passaporte; RF39 — o roteiro considera: custo dos ingressos (preço dos eventos), proximidade geográfica entre pontos (ordenação por rota razoável, Haversine entre consecutivos), interesses do usuário (priorização de categorias) e horários de funcionamento (não sugerir ponto fechado no horário). Arquitetura: RAG sobre a base cadastrada — dados de pontos/eventos persistidos são indexados (recuperação por similaridade semântica + filtros estruturados em SQL); o LLM só recebe contexto recuperado, nunca inventa pontos/eventos; sessões de chat persistidas com histórico do turista. Provedor de LLM com free tier (RNF15), chave via variáveis de ambiente, sem chave no repositório; comportamento degradado documentado se provedor indisponível. RNF06 — sem hardcode de localidade. Todos os endpoints deste módulo agrupados sob a tag "Chatbot" do registro central de tags da spec 006. Critério de aceitação: teste do pipeline de recuperação (query relevante retorna pontos certos da base de teste); teste de constraint que roteiro referenciado contém apenas pontos/eventos existentes no banco, respeitando horário de funcionamento e soma de ingressos esperada; teste de integração de sessão (histórico persiste entre mensagens). Mockar provedor de LLM nos testes; sem chamada externa real em suite de CI.
```

---

## Como usar com Spec Kit

1. **Constituição:** ✅ ratificada — v1.1.0 em `.specify/memory/constitution.md`
   (espelhada em `docs/CONSTITUTION.md`). Emendas seguem o fluxo de Governance.
2. **Por feature, em ordem (a partir da 002):** rodar `/speckit-specify` e colar
   o prompt da spec correspondente. Em seguida, `/speckit-clarify` →
   `/speckit-plan` → `/speckit-tasks` → `/speckit-implement` (e
   `/speckit-analyze` e/ou `/speckit-checklist` quando quiser verificação
   extra).
3. `/speckit-converge` ao final de uma feature para garantir que nada
   especificado ficou por implementar.