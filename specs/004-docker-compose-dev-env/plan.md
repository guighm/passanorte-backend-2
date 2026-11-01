# Implementation Plan: Containerização e Ambiente de Desenvolvimento Local (Docker Compose)

**Branch**: `004-docker-compose-dev-env` | **Date**: 2026-10-31 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/004-docker-compose-dev-env/spec.md`

## Summary

Containerizar a API PassaNorte (FastAPI/Python 3.13/uv) em imagem Docker multi-stage
(build com uv sincronizando `pyproject.toml`/`uv.lock` → runtime slim, usuário
não-root, uvicorn) e orquestrar o ambiente local de desenvolvimento com
`compose.yaml`: serviço `db` (PostgreSQL oficial + volume nomeado + healthcheck
`pg_isready`), `api` (build do Dockerfile, `DATABASE_URL` apontando para `db`,
`depends_on: service_healthy`, `alembic upgrade head` antes do uvicorn, hot reload
via bind de `src/` — clarificação Session 2026-10-31) e `dbgate` (porta 8080,
conexão ao Postgres pré-carregada via variáveis de conexão do DbGate — `CONNECTIONS`
com ID + `ENGINE_/SERVER_/USER_/PASSWORD_/DATABASE_` por conexão; ver research D8
corrigido). Segredos apenas em
`.env` local (nunca versionado), criado a partir de `.env.example` documentado; o
`.gitignore` é ajustado para ignorar apenas `.env`. Nenhuma alteração em `src/`,
`migrations/` ou `tests/` (FR-018).

## Technical Context

**Language/Version**: Python 3.13 (mandatório, constituição — stack obrigatória),
gerenciado por uv; Docker Engine + Docker Compose v2 no host.

**Primary Dependencies**: FastAPI + Pydantic v2 (app existente), SQLAlchemy 2.0 +
Alembic (migrations existentes), psycopg 3 (driver, já em `pyproject.toml`),
uv (gerenciador de pacotes — imagem de build `ghcr.io/astral-sh/uv`), imagens
oficiais `postgres` e `dbgate/dbgate`.

**Storage**: PostgreSQL em container (volume nomeado do Compose); a aplicação
continua selecionando engine apenas pela URL (`database_url` — RNF17). SQLite
continua reservado aos testes (não tocado).

**Testing**: pytest existente (roda no host, SQLite em memória — não tocado,
FR-018/SC-009). Esta feature de infraestrutura é validada por cenários
executáveis do `quickstart.md` (mapeados aos SC-001–SC-009 da spec); a suíte
existente deve continuar 100% verde como gate de regressão.

**Target Platform**: Estações de desenvolvimento Linux (host do repositório) com
Docker; artefatos reaproveitáveis para futuro deploy (fora do escopo desta
feature).

**Project Type**: web-service (monolito modular único) + tooling de
containerização.

**Performance Goals**: `/health` responda em menos de 1 s (SC-002 — comportamento
existente reutilizado, inalterado); ambiente completo do clone ao `/health` 200
em no máximo 5 minutos (SC-001).

**Constraints**: Nenhuma alteração em código de negócio (FR-018); nenhum segredo
real no repositório ou na imagem (FR-014/FR-016); usuário não-root (FR-002);
contexto de build sem `.venv`/`__pycache__`/`tests`/`specs`/`docs`/`.git`/
bancos locais (FR-005); portas host configuráveis com defaults 8000 (API) e 8080
(DbGate) (FR-010).

**Scale/Scope**: 3 serviços (`db`, `api`, `dbgate`), 10 módulos de domínio
existentes preservados; escopo limitado a arquivos de containerização na raiz.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Justificativa / evidência |
|---|---|---|
| Monolito Modular (regras 1–6) | PASS | Um único processo de API, um único banco; `compose.yaml` orquestra serviços de infraestrutura, não fragmenta domínios. Nenhum módulo é tocado. |
| I. API-Contract-First | PASS | Nenhum endpoint novo/alterado; `/health` e `/api/v1` permanecem como estão (assumptions da spec 004). |
| II. Segurança e LGPD | PASS | Segredos só via `.env` (nunca versionado/imagem); usuário não-root; `create-admin` permanece opt-in manual (FR-020) — credenciais alto-nível via script apenas. |
| III. Test-First (NON-NEGOTIABLE) | PASS (com nota) | Não há lógica de negócio nova — nada a cobrir com contrato/integração novos. Gate de regressão: suíte pytest existente 100% verde no host (SC-009); validação da feature via cenários do `quickstart.md` (padrão já adotado em features de infra, spec 001). |
| IV. Dados geoespaciais | PASS | Nenhum dado/lógica de visitação tocada. |
| V. Simplicidade (YAGNI) | PASS | 3 serviços apenas; sem registry, sem proxy reverso, sem CI de imagem; entrada do container mínima (migrations + uvicorn); produção adiada. Princípio V nota: ferramenta de administração (DbGate) é requisito explícito do usuário (não otimização prematura). |
| VI. Portabilidade por Configuração | PASS | Toda a config via `.env`/`.env.example`; portas e credenciais trocáveis sem rebuild. |
| VII. Manutenibilidade & English-only | PASS | Serviços identificados em inglês (`db`, `api`, `dbgate`); comentários do `Dockerfile`/`compose.yaml`/`.env.example` em inglês; README bilíngue seguindo padrão atual. |

**Verdict**: Sem violações — gate aberto para Phase 0. Re-check pós-design: PASS
(design adiciona apenas artefatos na raiz; `data-model.md` e `contracts/`
documentam contratos de runtime sem tocar código).

## Project Structure

### Documentation (this feature)

```text
specs/004-docker-compose-dev-env/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output — technical decisions resolved
├── data-model.md        # Phase 1 output — runtime entities of the compose env
├── quickstart.md        # Phase 1 output — runnable validation scenarios
├── contracts/
│   └── runtime-contracts.md  # Phase 1 output — image/compose/env contracts
└── tasks.md             # Phase 2 output (/speckit-tasks command)
```

### Source Code (repository root)

```text
Dockerfile              # NEW — multi-stage build (uv sync) → slim runtime
.dockerignore           # NEW — minimal build context (FR-005)
compose.yaml            # UPDATED — replaces stub: db + api + dbgate services
.env.example            # NEW — documented non-production variables (FR-015)
.gitignore              # MINOR UPDATE — ignore only `.env`, not `.env.*`
README.md               # UPDATED — Docker Compose onboarding (FR-017)

src/passanorte_back/    # UNTOUCHED (FR-018) — bind-mounted into `api` for hot reload
migrations/             # UNTOUCHED — applied by `alembic upgrade head` at container start
tests/                  # UNTOUCHED — host-side regression gate (SC-009)
```

**Structure Decision**: Artefatos de containerização exclusivamente na raiz do
repositório (padrão único de projeto/monolito). O código em `src/` é copiado na
imagem **e** bind-mounted em execução (hot reload, FR-019) — a cópia na imagem
garante o runtime real no build; o bind sobrepõe apenas `src/` em modo
desenvolvimento.

## Complexity Tracking

> Nesta execução o Constitution Check não tem violações a justificar — seção
> vazia por design (YAGNI).

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |