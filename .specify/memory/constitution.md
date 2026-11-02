<!--
SYNC IMPACT REPORT
- Version change: 1.1.0 → 1.2.0 (MINOR: materially expanded guidance and
  structural alignment with the codebase as of 2026-11-02; no principle
  removed or redefined incompatibly)
- Ratified: 2026-10-30 (unchanged)
- Last Amended: 2026-11-02
- Modified principles:
  - I. API-Contract-First → expanded (features 005/006): camelCase JSON
    contract now NON-NEGOTIABLE — every HTTP-bound schema inherits
    `core.schemas.ApiModel` (snake_case Python, camelCase JSON, strict
    border with `extra="forbid"`, no snake_case input); single unified
    `ApiError` payload for every failure path; OpenAPI tags centralized
    in `core/tags.py` (one tag per domain + `Health`), assigned only at
    router creation (`core/routers.py`) — route files never write tag
    strings
  - II. Segurança e LGPD → expanded (feature 003): sensitive data uses the
    shared field-crypto primitives in `core/crypto.py` (Fernet via env key
    `SENSITIVE_DATA_KEY`; HKDF/HMAC-SHA256 `*_lookup` subkeys for
    uniqueness/equality columns); the app refuses to start without
    DATABASE_URL, JWT_SECRET, SENSITIVE_DATA_KEY
  - VI. Portabilidade → expanded (feature 003): interest categories now
    live in `config/location.json` alongside city/languages — pure data
- Modified sections:
  - Preamble rule 2 (no procedural change) — canonical list remains
    `DOMAIN_MODULES` in `src/passanorte_back/core/modules.py`
  - Preamble rule 4 — shared infrastructure enumeration updated: core also
    holds `crypto.py`, `schemas.py`, `error_handlers.py`, `tags.py`,
    `security.py`
  - Stack → Docker deployment is part of this phase (feature 004:
    Dockerfile + compose.yaml); Alembic migrations exist (baseline +
    auth + tourists)
  - Quality Gates → reorganized test suite structure (unit / contract /
    integration / smoke); boundary gate is enforced by AST in
    `tests/smoke/test_boundaries.py` breaking the build; added gate: no
    schema without `ApiModel` and no tag string outside `core/tags.py`
- Added sections: none
- Removed sections: none
- Follow-up TODOs: none
- Traceability note: principles reference RFs/RNFs defined in
  docs/SYSTEM_REQUIREMENTS.md (RNF01–RNF20, RF01, RF03, RF38-39)
-->

# PassaNorte Constitution

## Decisão arquitetural fundamental: Monolito Modular Primeiro

O documento de requisitos (`docs/SYSTEM_REQUIREMENTS.md`) prevê sistemas
distribuído e microsserviços (RNF01, RNF02, RNF07). **Decisão deliberada para
esta fase:** o PassaNorte será implementado como um **monolito modular**,
com limites de domínio rígidos que espelham exatamente o corte de
microsserviços previsto, permitindo extração futura de serviços sem
reescrita. Regras que decorrem disso:

1. Um único processo FastAPI, um único banco de dados, um único deploy.
2. O código é organizado em **módulos de domínio** (bounded contexts),
   nomeados em inglês: `auth`, `employees`, `tourists`, `tourist_spots`,
   `events`, `gamification`, `visitation`, `dashboard`, `notifications`,
   `chatbot`. A lista canônica mora em
   `src/passanorte_back/core/modules.py` (`DOMAIN_MODULES`) — única fonte
   de verdade para registro de routers e verificação de fronteiras.
3. Módulos se comunicam **apenas** via interfaces explícitas de serviço
   (funções de serviço públicas) — nunca importando internals de outro
   módulo (models, schemas, repositories privados).
4. Cada módulo em `src/passanorte_back/modules/<domain>/` mantém sua própria
   área de camadas (`routes/`, `services/`, `repositories/`, `schemas/`);
   a infraestrutura compartilhada vive em `src/passanorte_back/core/`:
   config (`config.py` + dados de localidade), db (`db.py`), routers
   (`routers.py`), auditoria (`audit.py`), checagem de fronteiras por AST
   (`boundaries.py`), criptografia de campos (`crypto.py`), schemas-base do
   contrato HTTP (`schemas.py`), handlers de erro unificados
   (`error_handlers.py`), registro de tags OpenAPI (`tags.py`) e primitivas
   de segurança (`security.py`). Não há compartilhamento de tabelas entre
   domínios.
5. Toda escrita entre domínios (ex.: visitation atualizando progresso de
   gamification) passa por uma função de serviço do domínio dono dos dados,
   nunca por UPDATE direto em suas tabelas.
6. Nenhuma fila de mensagens, service mesh ou comunicação em rede entre
   módulos nesta fase. Quando um módulo evoluir para microsserviço, sua
   interface de serviço vira o contrato de API interna (client HTTP ou
   mensageria), sem mudança de semântica.

## Core Principles

### I. API-Contract-First

A API RESTful FastAPI é o único contrato: painel web (React) e aplicativo
Passaporte (Kotlin) consomem os **mesmos endpoints** (RNF03, RNF05). Todo
endpoint é definido por schema Pydantic (request/response) antes da
implementação; OpenAPI/Swagger gerado automaticamente é a documentação de
referência — entregue exatamente como a API se comporta. Frontends não
integram lógica que a API não expõe. Nenhum endpoint privado sem RBAC:
administrador tem acesso total; funcionário acessa apenas concessão de
benefícios (RF03).

**Contrato JSON camelCase (NON-NEGOTIABLE)**: todo schema HTTP-bound em
qualquer módulo herda `core.schemas.ApiModel` — atributos Python em
snake_case (PEP 8), chaves JSON em camelCase com acrônimos em minúsculas
(`user_cpf` → `userCpf`). A fronteira HTTP é estrita: `extra="forbid"` e
`populate_by_name` desabilitado — chaves desconhecidas e snake_case são
rejeitadas com 422. A conversão snake↔camel acontece apenas na fronteira
HTTP, nunca espalhada pelo código. Todo caminho de falha expõe o payload
único `core.schemas.ApiError` (`errorCode`, `message`, `details`) via
`core.error_handlers` — nenhum endpoint inventa formato de erro próprio.

**Tags OpenAPI centralizadas**: exatamente uma tag por módulo canônico
(`DOMAIN_MODULES`) mais a tag de infraestrutura `Health`, registradas
em `core/tags.py` (`OPENAPI_TAGS_METADATA`) — única fonte de verdade
aplicada em `main.py`/`core.routers`; arquivos de rota nunca escrevem
string de tag.

### II. Segurança e LGPD por Padrão

Autenticação exclusivamente por JWT com expiração e renovação controladas
(RNF09). Senhas de administrador, funcionário e turista são sempre
armazenadas com hash bcrypt/argon2 — nunca em texto plano (RNF10). Dados
sensíveis (CPF, passaporte, telefone, e-mail) armazenados criptografados em
conformidade com LGPD (RNF08), exclusivamente via primitivas compartilhadas
de `core/crypto.py`: Fernet com chave de ambiente `SENSITIVE_DATA_KEY` e
subchaves HMAC-SHA256 (HKDF, um contexto por campo) para as colunas de
unicidade/igualdade (`*_lookup`) — nenhum valor sensível é persistido em
texto claro e a mesma chave cobre criptografia e lookup. Ações
administrativas críticas (cadastro/edição/remoção de pontos, eventos,
funcionários) geram log de auditoria estruturado (RNF19). Credenciais de
alto nível são geradas apenas por script (`create-admin`), nunca hardcoded
no código ou no repositório (RF01; segredos via variáveis de ambiente). A
aplicação se recusa a subir sem as credenciais essenciais (`DATABASE_URL`,
`JWT_SECRET`, `SENSITIVE_DATA_KEY`), nomeando o campo ausente.

### III. Test-First (NON-NEGOTIABLE)

Test-first obrigatório: teste escrito → falha → implementação → verde.
Toda feature de API possui no mínimo: (a) teste de contrato (schema
request/response e códigos de status HTTP), (b) teste de integração
exercitando o fluxo ponta a ponta do domínio (ex.: inscrever → visitar
pontos → concluir rota → gerar código → resgatar brinde). Testes rodam contra
banco isolado (SQLite em memória ou banco efêmero por teste). Cobertura é
critério de aceitação da tarefa, não aspiração.

### IV. Relevância e Corretude dos Dados Geoespaciais

A validação de presença usa fórmula de Haversine com raio de tolerância
configurável por ponto turístico (RNF14). Coordenadas são sempre
(decimal, WGS-84) e validadas por schema. O ranking/dashboard nunca deve
inventar dados: toda métrica deriva de eventos de visitação registrados,
jamais estimada "em código".

### V. Simplicidade e Escopo Minimizado (YAGNI)

Começar pelo mais simples que atende o requisito em mãos. A complexidade é
justificada caso a caso (no constitution check). Sem otimizações prematuras,
sem caches multicamada, sem filas. Priorizar ferramentas gratuitas e open
source (RNF15). Menos tabelas, menos endpoints, menos dependências —
crescer por necessidade real demonstrada em teste.

### VI. Portabilidade por Configuração

A adaptação do sistema para outra cidade/estado/país exige apenas troca de
dados configuráveis (pontos, categorias, horários, idiomas) — zero
reestruturação de código ou arquitetura (RNF06). Nome da cidade, coordenadas
raiz, categorias de interesse padrão e idiomas habilitados vivem em
dados (`config/location.json`) ou configuração, não em lógica de código —
trocar de cidade/idiomas/categorias é editar JSON e reiniciar.

### VII. Manutenibilidade e Consistência

Python 3.13 com type hints em todos os módulos, Pydantic para schemas,
organização em camadas (routes → services → repositories) dentro de cada
módulo de domínio (RNF20). Linter (ruff) e formatter (ruff format) no
pipeline. README e docstrings atualizados junto com o código.

**Todo o código é escrito em inglês (NON-NEGOTIABLE)**: nomes de módulos,
pacotes, classes, funções, variáveis, constantes, rotas de API, campos de
schema, mensagens de commit e comentários/docstrings de código — em inglês.
Conteúdo de dados e texto de usuário (nomes de pontos turísticos,
descrições/UX exibidas ao turista) permanecem em português, conforme o
princípio VI. Toda vez que um requisito ou documento de entrada traz um
termo em português (ex.: `funcionarios`), ele deve ser traduzido ao nome
canônico em inglês (ex.: `employees`) antes de virar código.

## Requisitos Adicionais (Constraints)

### Stack Tecnológica Obrigatória (RNF03–05)

- **Backend**: Python 3.13, FastAPI, Pydantic v2 (validação de schemas).
- **Frontend web do painel**: React (JavaScript), fora do escopo deste
  backend, mas define o contrato de API.
- **Mobile Passaporte**: Kotlin + Jetpack Compose, fora do escopo deste
  backend, mas define o contrato de API.
- **Persistência**: banco relacional estruturado (RNF17) — PostgreSQL em
  produção; SQLite em memória/arquivo para testes; SQLAlchemy 2.0 como
  acesso a dados; Alembic para migrations (baseline + evoluções por
  feature).
- **Deploy desta fase**: containerizado (Dockerfile + compose.yaml) — um
  processo, um banco, um deploy; sobe apenas após ping de banco saudável.
- **Mapas**: Google Maps API ou OpenStreetMap (RNF18) — escolha por custo
  (open source preferido, RNF15).
- **Chatbot**: IA generativa com RAG sobre os dados cadastrados (RF38-39) —
  preferir provedores com free tier.

### Tempo de Resposta e Disponibilidade (RNF11, RNF12)

Consultas simples (listagem de pontos, status de rota) devem responder em
tempo hábil para uso mobile. Autenticação, consulta de pontos e marcação de
visitação são os serviços essenciais e não devem depender de subsistemas
pesados (dashboard, chatbot) para responder.

### i18n e Usabilidade (RNF13, RNF16)

Suporte multilíngue da aplicação Passaporte (baixa prioridade, mas o contrato
de API que responde ao front deve ser i18n-ready: mensagens localizáveis,
dados de idioma configuráveis).

## Development Workflow

1. **Specify** (`/speckit-specify`): criar spec da feature com requisitos
   rastreados aos RFs/RNFs de `docs/SYSTEM_REQUIREMENTS.md`.
2. **Clarify/Plan** (`/speckit-clarify`, `/speckit-plan`): resolver
   ambiguidades, gerar plano técnico respeitando limites de módulo.
3. **Tasks** (`/speckit-tasks`): gerar tarefas test-first, agrupadas pelo
   módulo de domínio responsável.
4. **Implement** (`/speckit-implement`): implementar tarefa por tarefa,
   sempre com teste vermelho antes do código verde.
5. **Analyse** (`/speckit-analyze`): verificar consistência entre artefatos.

### Quality Gates

- Testes de contrato e integração do domínio passando. A suíte é organizada
  em `tests/unit/`, `tests/contract/`, `tests/integration/` e
  `tests/smoke/` (+ `test_migrations.py`).
- `ruff check` sem erros.
- Nenhuma senha em texto plano, nenhum dado sensível não criptografado, no
  código e nos testes.
- Nenhum import cruzando a fronteira privada de outro módulo de domínio —
  verificado por AST (`core/boundaries.py` via `tests/smoke/`), quebra o
  build em qualquer import ilícito.
- Nenhum identificador de código em português: módulos, classes, funções,
  schemas, colunas e rotas seguem a nomenclatura canônica em inglês
  (`DOMAIN_MODULES` em `core/modules.py`).
- Nenhum schema HTTP-bound sem herdar `ApiModel`; nenhuma string de tag
  OpenAPI escrita fora de `core/tags.py`; nenhum payload de erro além de
  `ApiError`.
- Migrations Alembic revisadas quando houver mudança de schema.

## Governance

- A presente constituição prevalece sobre qualquer outra prática,
  preferência individual ou instrução ad hoc de tarefa individual.
- Emendas exigem documentação da mudança, aprovação do responsável e plano
  de migração para código existente; versionamento
  MAJOR.MINOR.PATCH (mudança em princípio = MAJOR).
- Qualquer extração futura de módulo para microsserviço deve partir de um
  amendment (não é decisão de tarefa individual) e deve preservar: mesma
  fronteira de dados, mesma semântica da interface de serviço, mesmo
  contrato REST exposto aos frontends.
- Complexidade extra precisa justificação explícita no PR e é contestável
  em review (YAGNI).

**Version**: 1.2.0 | **Ratified**: 2026-10-30 | **Last Amended**: 2026-11-02