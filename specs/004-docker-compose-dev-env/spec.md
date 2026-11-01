# Feature Specification: Containerização e Ambiente de Desenvolvimento Local (Docker Compose)

**Feature Branch**: `004-docker-compose-dev-env`

**Created**: 2026-10-31

**Status**: Draft

**Input**: User description: "Containerizar a API do PassaNorte (FastAPI, Python 3.13, uv) e criar o ambiente de desenvolvimento local com Docker Compose, conforme docs/CONSTITUTION.md (monolito modular). Requisitos: (a) Dockerfile multi-stage — stage de build com uv para sincronizar dependências (pyproject/uv.lock) e stage de runtime slim, usuário não-root, sem segredos na imagem, porta da API exposta, process iniciado com uvicorn; (b) .dockerignore excluindo .venv, __pycache__, tests, specs, docs, .git, caches e artefatos locais; (c) compose.yaml com os serviços: db (imagem official do PostgreSQL, volume nomeado para os dados, healthcheck pg_isready, credenciais via .env), api (build do Dockerfile, env_file .env, DATABASE_URL apontando para o serviço db, depends_on com condição service_healthy, executa alembic upgrade head antes de subir o uvicorn) e dbgate (imagem dbgate/dbgate, porta 8080, conexão ao Postgres PRÉ-CONFIGURADA via variável CONNECTIONS em JSON — conId, engine postgres@dbgate, server db, port 5432, user/password/database do .env — para que ao abrir http://localhost:8080 a conexão já exista sem digitação). (d) Nenhum segredo real no repositório: .env.example documentando as variáveis (DATABASE_URL, POSTGRES_*, credenciais do DbGate), .env no .gitignore. (e) Não alterar lógica de negócio nem fronteira de domínios existentes (specs 001-003). Critério de aceitação: docker compose up --build sobe os três serviços; /health responde HTTP 200 com o banco PostgreSQL conectado; migrations aplicadas (tabelas das specs 001-003 presentes no Postgres); DbGate acessível em http://localhost:8080 mostrando a conexão pré-carregada e navegando nas tabelas; docker compose down + up reutiliza o volume sem perder dados."

**Nota**: Como em 001, esta é uma feature de **infraestrutura técnica**, não de
negócio. A stack de containerização (Docker multi-stage, Compose, PostgreSQL
oficial, DbGate) é o próprio escopo da feature; por isso os requisitos abaixo
mencionam as tecnologias quando a tecnologia é o requisito em si. Os critérios
de sucesso permanecem observáveis e verificáveis sem depender de detalhes
internos de implementação. **Restrição dura**: nenhuma alteração de lógica de
negócio ou de fronteiras de módulos das specs 001–003.

## Clarifications

### Session 2026-10-31

- Q: Ao alterar código da API em `src/` durante o desenvolvimento, o container deve refletir a mudança automaticamente (hot reload), ou só após reconstruir a imagem? → A: Hot reload — o código de `src/` é montado por bind no container `api` e o uvicorn executa com recarregamento automático; mudanças aparecem sem rebuild (o rebuild valida o runtime real na subida, com build multi-stage e migrations).
- Q: Em um volume novo (primeiro `up` do ambiente), o banco deve já conter o usuário administrador de alto privilégio, ou a criação fica como passo manual opcional após a subida? → A: Manual após subida — a entrada do container `api` fica mínima (migrations + uvicorn); a criação do administrador continua sendo comando opcional documentado (script da spec 002 executável via `docker compose exec api ...`), sem bootstrap implícito de credenciais na subida.
- Q: Como resolver o conflito entre o `.env` local (lido pelo pydantic-settings) e os 2 smoke tests que esperam falha sem nenhum `.env` presente? → A: Fix mínimo nos 2 tests aprovado — `tests/smoke/test_settings_essentials.py` ganha isolamento de CWD (`monkeypatch.chdir(tmp_path)`) para que um `.env` local da feature 004 não satisfaça o essencial; a intenção original é preservada (essencial ausente de TODAS as fontes falha nomeando o campo). Executada durante a implementação (2026-10-31), com aprovação explícita do usuário.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ambiente completo de desenvolvimento com um único comando (Priority: P1)

Uma desenvolvedora (ou revisor externo) que clona o repositório e possui apenas
Docker instalado levanta o ambiente completo de desenvolvimento com uma única
instrução: banco de dados PostgreSQL, API FastAPI (com migrations já aplicadas)
e ferramenta de administração de banco — sem instalar Python, uv, PostgreSQL
local ou rodar comandos manuais. Ao final, o endpoint de verificação de saúde
responde HTTP 200 indicando a aplicação no ar **e** o banco PostgreSQL
conectado.

**Why this priority**: É o fluxo central do onboarding: sem ele, cada
desenvolvedora monta o ambiente manualmente e de forma não reproduzível.
Entrega valor isolado: "repo clonado → API funcionando conectada ao banco" é um
slice completo e demonstrável.

**Independent Test**: Executar o comando único de subida do ambiente a partir do
repositório clonado (com um arquivo `.env` criado a partir do exemplo) e
verificar que os três serviços sobem e a verificação de saúde responde com
estado saudável da aplicação e do banco, em poucos minutos.

**Acceptance Scenarios**:

1. **Given** repositório clonado e a imagem da API ainda não construída, **When**
   o ambiente é iniciado com construção de imagem (comando único de Compose),
   **Then** os três serviços (banco de dados, API e ferramenta de
   administração) sobem e a verificação de saúde responde HTTP 200 informando a
   aplicação saudável **e** o banco PostgreSQL conectado.
2. **Given** o ambiente recém-subido, **When** as migrations são verificadas no
   banco, **Then** as tabelas das specs 001–003 (fundação, auth/rbac, turistas)
   existem no PostgreSQL — resultado de migrações aplicadas automaticamente
   antes de o serviço da API começar a servir tráfego.
3. **Given** a máquina da desenvolvedora sem Python, uv ou PostgreSQL instalados
   nativamente, **When** o ambiente é iniciado, **Then** nada além de Docker é
   necessário para executar o fluxo anterior.

---

### User Story 2 - Persistência de dados entre reinicializações (Priority: P2)

Uma desenvolvedora cadastra turistas e autentica usuários durante o dia; no fim,
encerra o ambiente. No dia seguinte, sobe o ambiente novamente e encontra todos
os dados intactos — sem recadastrar nada e sem reaplicar migrações do zero. Os
dados do banco sobrevivem a paradas e subidas completas do ambiente.

**Why this priority**: Sem persistência, o ambiente de desenvolvimento perde
dados a cada `down`, o que o torna inviável para iterar sobre as features
001–003 já implementadas (cadastro de turistas, perfis, interesses). Depende da
US-1 (ambiente subindo), mas é demonstrável de forma independente.

**Independent Test**: Criar um registro via API (ou migração), derrubar o
ambiente (removendo containers, preservando o volume de dados), subir novamente
e verificar que o registro continua lá e as migrações aplicadas não foram
refeitas.

**Acceptance Scenarios**:

1. **Given** o ambiente ativo com ao menos um dado persistido (ex.: um turista
   cadastrado), **When** o ambiente é derrubado (containers removidos) e elevado
   novamente, **Then** o dado persistido continua presente e navegável.
2. **Given** o ambiente derrubado com migrações já aplicadas, **When** sobe
   novamente, **Then** as migrações são idempotentes (nada pendente é
   reexecutado) e a API sobe sem erros sobre o estado anterior do schema.
3. **Given** o ambiente derrubado (não purgado), **When** o volume de dados é
   inspecionado, **Then** ele ainda existe — a parada nunca destrói dados por
   padrão; a destruição deliberada só ocorre por comando explícito de purge
   (`docker compose down -v` ou equivalente documentado).

---

### User Story 3 - Exploração do banco via ferramenta visual de administração pré-configurada (Priority: P3)

Uma desenvolvedora abre `http://localhost:8080` no navegador e encontra a
ferramenta visual de administração de banco (DbGate) com a conexão ao PostgreSQL
do ambiente **já pré-carregada** — host, porta, usuário, senha e banco lidos da
configuração do ambiente. Um clique na conexão abre o schema; outra navega às
tabelas das features 001–003 para inspecionar linhas. Nenhuma digitação de
credenciais é necessária.

**Why this priority**: Acelera depuração e validação do dia a dia, mas é
auxiliar — o ambiente funciona sem ela (US-1 e US-2 não dependem). O valor
está em eliminar a configuração manual repetida da conexão a cada uso.

**Independent Test**: Subir o ambiente, abrir a porta da ferramenta no
navegador e verificar que a conexão ao banco aparece pronta para uso; abrir a
conexão e listar as tabelas aplicadas pelas migrações sem digitar credenciais.

**Acceptance Scenarios**:

1. **Given** o ambiente ativo, **When** `http://localhost:8080` é aberto em um
   navegador, **Then** a ferramenta de administração responde no navegador com a
   interface carregada.
2. **Given** a ferramenta aberta, **When** a lista de conexões é consultada,
   **Then** a conexão com o PostgreSQL do ambiente já existe (nome,
   servidor/hosts internos do Compose, banco, usuário e senha provenientes do
   arquivo `.env`), pronta para uso sem digitação.
3. **Given** a conexão pré-configurada, **When** ela é aberta e as tabelas são
   navegadas, **Then** as tabelas criadas pelas migrações (specs 001–003) são
   listadas e seus registros visíveis.

---

### User Story 4 - Configuração externa sem segredos no repositório (Priority: P4)

Uma operadora ou desenvolvedora configura credenciais e parâmetros do ambiente
em um único arquivo `.env` local (nunca versionado), criado a partir de um
arquivo de exemplo documentado (**versionado**, sem segredos reais). A imagem
da API não contém segredo algum; todos os valores sensíveis entram por
configuração em execução. A troca de credenciais não exige rebuild da imagem.

**Why this priority**: Segurança e LGPD por padrão (Princípio II da
constituição; FR-011 da spec 001). Vem por último na ordem de leitura, mas sua
violação bloquearia o merge — é requisito de aceitação transversal.

**Independent Test**: Auditar o repositório e a imagem construída: nenhum valor
sensível real presente; o arquivo de exemplo documenta todas as variáveis
necessárias; copiar e preencher `.env.example` → `.env` é suficiente para subir
o ambiente.

**Acceptance Scenarios**:

1. **Given** o repositório, **When** o controle de versão é consultado, **Then**
   `.env` e artefatos locais de banco (ex.: `*.db`) não aparecem nenhuma vez —
   apenas o arquivo de exemplo documentado aparece.
2. **Given** o arquivo de exemplo versionado, **When** lido por alguém novo no
   projeto, **Then** ele documenta todas as variáveis exigidas pelos serviços
   (endereço do banco, credenciais do PostgreSQL, credenciais repassadas à
   ferramenta de administração, e demais parâmetros da API), com valores de
   exemplo claramente não-produção.
3. **Given** a imagem da API construída, **When** inspecionada, **Then** nenhum
   segredo (senha, chave de assinatura) está embutido na imagem — todos os
   valores sensíveis chegam em tempo de execução pelo arquivo de ambiente.
4. **Given** um arquivo `.env` preenchido como exemplo, **When** o ambiente
   sobe, **Then** todos os serviços recebem suas configurações desse único
   arquivo, e trocar seus valores (ex.: senha do Postgres) em um volume já
   existente requer apenas reinicialização documentada — nunca rebuild da
   imagem.

---

### Edge Cases

- O que acontece quando a API sobe **antes** de o banco aceitar conexões? O
  serviço da API não tenta conectar às cegas: ele só inicia depois de o serviço
  do banco reportar-se pronto por healthcheck; as migrações rodam nesse
  momento, antes de o uvicorn servir tráfego.
- O que acontece quando a migração falha (ex.: erro de schema)? O processo da
  API não sobe "verde" por cima do problema: o container da API termina com
  erro visível em `docker compose logs api`, e o healthcheck nunca responde
  200.
- O que acontece quando `.env` não existe? O ambiente falha cedo com mensagem
  clara apontando para o arquivo de exemplo (copie `.env.example` → `.env`), em
  vez de subir com valores implícitos diferentes dos documentados.
- O que acontece quando a porta da API (8000) ou a porta da ferramenta
  visual (8080) já está ocupada no host? Os mapeamentos de porta são
  configuráveis pelo arquivo de ambiente (defaults: 8000 e 8080); conflito é
  erro do Compose, não um serviço silenciosamente trocado.
- O que acontece quando o volume já existe com um schema mais antigo que o
  código? `upgrade head` aplica apenas as migrações pendentes — nunca reexecuta
  migrações já contabilizadas no banco (idempotência).
- O que acontece quando `docker compose down` é executado? Containers e rede
  são removidos; o **volume de dados é preservado** por padrão (princípio da
  US-2); a única forma de apagar dados é o purge explícito documentado.

## Requirements *(mandatory)*

### Functional Requirements

**Imagem da API (build multi-stage)**

- **FR-001**: A imagem da API MUST ser construída em duas fases (multi-stage):
  uma fase de build que instala o gerenciador de pacotes uv e sincroniza as
  dependências a partir de `pyproject.toml` + `uv.lock` (reprodutível por
  lockfile), e uma fase de runtime slim que copia os artefatos (código em
  `src/` e ambiente de dependências) sem carregar toolchain de build
  (constituição, stack obrigatória: Python 3.13 + uv).
- **FR-002**: A imagem da API MUST executar como usuário não-root.
- **FR-003**: A imagem da API MUST declarar e expor a porta da API (8000) e o
  processo iniciado com uvicorn servindo a aplicação.
- **FR-004**: A construção da imagem MUST não incorporar segredos (ver
  FR-014/FR-016): nenhuma credencial ou chave é `COPY`'d, `ARG`'d em runtime ou
  embutida em camada da imagem.
- **FR-005**: MUST existir um `.dockerignore` impedindo que `.venv`,
  `__pycache__`/caches Python, `tests/`, `specs/`, `docs/`, `.git`,
  bancos de dados locais (`*.db`/`*.sqlite3`), `.env`/artefatos de ambiente
  local e demais artefatos locais (build, dist, caches) entrem no contexto de
  build — mantendo o contexto mínimo e impossibilitando vazamento de segredos
  via contexto.

**Orquestração (compose.yaml)**

- **FR-006**: MUST existir um `compose.yaml` orquestrando os três serviços:
  `db` (PostgreSQL oficial), `api` (construída do Dockerfile) e `dbgate`
  (ferramenta visual de administração).
- **FR-007**: O serviço `db` MUST usar a imagem oficial do PostgreSQL, montar
  um **volume nomeado** para os dados (sobrevivência entre `down`/`up`,
  FR-012) e definir um healthcheck que só reporta saudável quando o servidor
  aceita conexões (`pg_isready`).
- **FR-008**: O serviço `api` MUST: (i) ser construído a partir do Dockerfile;
  (ii) carregar o arquivo `.env` do repositório; (iii) apontar
  `DATABASE_URL` para o serviço `db` (host interno do Compose) — sobrepondo o
  valor apenas quanto ao endereço, mantendo as demais configurações do `.env`;
  (iv) depender do `db` apenas após `service_healthy`; (v) executar
  `alembic upgrade head` **antes** de iniciar o uvicorn, no container da API.
- **FR-009**: O serviço `dbgate` MUST usar a imagem `dbgate/dbgate`, publicar a
  porta 8080 do host (mapeada para a porta web interna da imagem — 3000,
  definida pela própria imagem) e receber a conexão ao PostgreSQL
  **pré-configurada** via variáveis de ambiente no formato suportado pela
  imagem: `CONNECTIONS` com a lista de IDs de conexão e as variáveis
  correspondentes (`ENGINE_*`, `SERVER_*`, `PORT_*`, `USER_*`, `PASSWORD_*`,
  `DATABASE_*`) — engine `postgres@dbgate-plugin-postgres`, servidor `db`,
  porta 5432, usuário/senha/banco vindos do `.env`. (Correção documentada em
  2026-10-31: o formato JSON numa única variável — descrito no pedido original
  — não é aceito pela imagem 7.3.3 e gera o erro `DBGM-00006 Invalid
  CONNECTIONS configuration`.) O resultado é: a conexão já existe na interface
  em `http://localhost:8080` sem digitação (US-3).
- **FR-010**: As portas publicadas no host (API 8000 e DbGate 8080, e demais se
  necessário) MUST ser configuráveis pelo arquivo de ambiente, com os defaults
  documentados no arquivo de exemplo (Edge Case de conflito de porta).

**Persistência e migrations**

- **FR-011**: As migrações aplicadas no banco (specs 001–003) MUST refletir
  exatamente o estado de `migrations/` do código no momento da subida — o
  container da API aplica sempre `upgrade head` antes de servir.
- **FR-012**: Os dados do PostgreSQL MUST persistir em volume nomeado com
  ciclo de vida desacoplado dos containers: `down` preserva, `down -v` (purge
  explícito documentado) apaga. Nenhum dado é gravado fora do volume.
- **FR-013**: A subida sobre um volume existente MUST reutilizar as migrações
  já contabilizadas (idempotência): `upgrade head` aplica apenas o pendente
  (ver Edge Case).
- **FR-014**: Nenhum segredo real MUST existir no repositório; a autenticação
  essencial do ambiente (senhas, segredos) chega ao Compose exclusivamente via
  `.env` — o arquivo `.env` MUST permanecer fora do versionamento
  (`.gitignore`), e o exemplo documentado `.env.example` MUST estar versionado
  sem valores reais (Princípio II da constituição; FR-011 da spec 001).

**Arquivos de configuração e documentação**

- **FR-015**: MUST existir `.env.example` versionado documentando todas as
  variáveis exigidas pelos serviços: `DATABASE_URL` (exemplo apontando para
  `db`, serviço do Compose), variáveis do PostgreSQL (`POSTGRES_USER`,
  `POSTGRES_PASSWORD`, `POSTGRES_DB`), credenciais repassadas ao DbGate (coerentes
  com as do Postgres) e demais parâmetros já exigidos pela spec 001 (segredo
  JWT, TTL, raio GPS, etc.), com valores de exemplo não-produção e comentários.
  Nota: o `.gitignore` atual ignora `.env.*` (qualquer sufixo); MUST ser
  ajustado para que **apenas** `.env` (e o SQLite local) continue ignorado,
  garantindo que `.env.example` fique versionável.
- **FR-016**: A imagem da API e o volume com dados inicializado pelo Compose
  MUST não conter segredos reais: apenas valores de exemplo não-produção
  provenientes do arquivo local do desenvolvedor (fruto de FR-004 + FR-014).
- **FR-017**: O README (ou documento equivalente) MUST documentar como subir o
  ambiente com Docker Compose: pré-requisitos (Docker), cópia de
  `.env.example` → `.env`, comando de subida, endereço do `/health`,
  endereço do DbGate e o comando de purge explícito que apaga dados (US-2).
- **FR-018**: Nenhuma lógica de negócio ou fronteira de módulo das specs 001–003
  MUST ser alterada: features do código, rotas, schemas, migrations e checks
  de fronteiras permanecem intocados — esta feature adiciona apenas arquivos de
  containerização (`Dockerfile`, `.dockerignore`, `compose.yaml` completo,
  `.env.example`, ajuste mínimo de `.gitignore`, README) (US-1, restrição "e" do
  escopo). Exceção documentada (aprovada na implementação, 2026-10-31): ajuste
  mínimo em `tests/smoke/test_settings_essentials.py` (isolamento de CWD nos 2
  tests de essencial ausente) — necessário para que a suíte siga verde com o
  `.env` local de dev da feature; intenção dos tests inalterada.

**Experiência de desenvolvimento (hot reload)**

- **FR-019**: No ambiente de desenvolvimento, o container `api` MUST montar o
  código-fonte de `src/` por bind no lugar da cópia embutida na imagem e
  executar o uvicorn com recarregamento automático, de modo que alterações em
  `src/` apareçam na API em execução sem recarregamento de imagem (clarification
  2026-10-31). A imagem multi-stage continua sendo construída normalmente
  (build valida o runtime real); quando código ou dependências mudam no
  lockfile, `up --build` reconstrói a imagem, e o bind sobrepõe apenas `src/`
  em execução.
- **FR-020**: A entrada do container `api` MUST executar apenas migrações e
  uvicorn — nenhum bootstrap automático de credenciais de alto nível ocorre na
  subida (clarification 2026-10-31; Princípio II da constituição: credenciais
  geradas apenas por script). O README (FR-017) MUST documentar o comando
  opcional para criar o administrador de alto nível em volume novo via
  `docker compose exec api` com o script já existente da spec 002, sem
  alterá-lo.

### Key Entities *(include if feature involves data)*

- **Ambiente de desenvolvimento**: conjunto de três serviços orquestrados —
  banco de dados (PostgreSQL com volume persistente), API (imagem construída
  com migrações automáticas) e ferramenta de administração (DbGate com conexão
  pré-carregada) — configurados por um único arquivo de ambiente local.
- **Imagem da API**: artefato reprodutível das fases multi-stage (build com uv
  sincronizando dependências → runtime slim), desprovida de segredos e de
  toolchain de build, executando uvicorn (Python 3.13) como usuário não-root.
- **Arquivo de ambiente (`.env`)**: segredos e parâmetros locais do ambiente
  (nunca versionados), criado a partir do arquivo de exemplo versionado e
  documentado (`.env.example`), fonte única de configuração para os três
  serviços.
- **Volume de dados**: armazenamento nomeado do PostgreSQL, desacoplado do
  ciclo de vida dos containers — preservado por paradas/subidas, apagado
  somente por purge explícito documentado.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: De repositório clonado (com `.env` criado do exemplo) a `/health`
  respondendo HTTP 200 com banco PostgreSQL conectado, levando no máximo **5
  minutos** em uma máquina com Docker, executando **apenas** os dois comandos
  documentados (copiar arquivo de ambiente + comando único de subida).
- **SC-002**: `docker compose up --build` do zero sobe os três serviços, e o
  `/health` responde 200 com o banco conectado — nenhum serviço em estado
  unhealthy/restarting após a subida.
- **SC-003**: Após a subida, todas as migrações das specs 001–003 aplicadas:
  as tabelas das features fundação, auth/rbac e turistas visíveis no
  PostgreSQL (verificáveis pela ferramenta visual ou CLI do banco).
- **SC-004**: Em `http://localhost:8080` o DbGate responde no navegador e a
  conexão ao PostgreSQL já existe pré-carregada na lista de conexões; abri-la
  e navegar às tabelas requer **zero digitação de credenciais**.
- **SC-005**: `down` seguido de `up` reutiliza o volume: 100% dos dados de
  exemplo criados antes do `down` permanecem presentes e navegáveis após o
  `up` (verificado com ao menos um registro por domínio já implementado).
- **SC-006**: A imagem construída contém **zero segredos** — verificado por
  inspeção: nenhuma credencial de `.env` aparece em camadas, env ou
  filesystem da imagem (além de nada em texto plano no Dockerfile/compose
  versionado).
- **SC-007**: O repositório versionado não contém `.env`, nem segredo real em
  texto plano — o `.env.example` documenta 100% das variáveis exigidas para
  subir o ambiente (checagem: subir ambiente usando somente os valores do
  exemplo, sem ajustar nada além de copiar o arquivo).
- **SC-008**: O contexto de build enviado ao Docker não contém `.venv`,
  `__pycache__`, `tests/`, `specs/`, `docs/`, `.git` nem bancos de dados locais (`.db`) —
  verificado por inspeção do `.dockerignore` e pelo tempo/tamanho do contexto
  (build repetido mais rápido e contexto pequeno).
- **SC-009**: O codebase de negócio das specs 001–003 permanece inalterado —
  `git diff` não mostra troca em `src/`, `migrations/` ou `tests/` após a
  feature (a exceção documentada: nenhum ajuste em código foi necessário).

## Assumptions

- A stack de containerização é escopo da feature (como em spec 001): Docker
  multi-stage, Docker Compose v2 (`compose.yaml`, sem env legado
  `docker-compose.yml`), imagem oficial `postgres` e `dbgate/dbgate` — open
  source e gratuito (RNF15; Princípio V, YAGNI).
- O ambiente de **desenvolvimento local** é o foco: segredos de exemplo com
  valores não-produção são aceitáveis no `.env` local do desenvolvedor. O mesmo
  `compose.yaml` serve de base para produção futura, sem que esta spec defina
  deploy de produção (YAGNI — produção fica para feature própria).
- O host do desenvolvedor possui Docker (Engine + Compose v2) instalado; essa
  é a única dependência fora do repositório para os fluxos de US-1 e US-2.
- O `/health` existente da spec 001 (HTTP 200 quando banco saudável, 503 +
  degradação quando não) é reutilizado sem modificação — esta feature não
  altera endpoints.
- O `alembic upgrade head` roda no mesmo container da API antes do uvicorn
  (comando de entrada composto); não é criado um container/services separado
  para migrações (YAGNI, simplicidade de orchestration neste estágio).
- O volume nomeado default do Compose (prefixado por projeto) é suficiente;
  binds de host não são usados para dados do banco.
- A porta do PostgreSQL (5432) não precisa ser publicada no host para o fluxo
  normal (DbGate acessa pela rede interna do Compose); pode ser exposta
  opcionalmente para ferramentas nativas do desenvolvedor, configurável pelo
  arquivo de ambiente se ativada.
- `.gitignore` atualmente ignora `.env.*` (qualquer arquivo de ambiente com
  sufixo); um ajuste mínimo é necessário para permitir versionar
  `.env.example` (detalhado em FR-015).
- Os nomes/serviços do Compose (`db`, `api`, `dbgate`) e o mapeamento de portas
  (8000 API, 8080 DbGate) seguem exatamente o pedido da feature e ficam
  documentados no README; nomes de identificadores em código/arquivos de
  infraestrutura permanecem em inglês (Princípio VII da constituição).