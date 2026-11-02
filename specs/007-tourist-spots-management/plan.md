# Implementation Plan: Tourist Spots Management

**Branch**: `007-tourist-spots-management` | **Date**: 2026-11-02 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/007-tourist-spots-management/spec.md`

## Summary

CRUD administrativo (RBAC de administrador) de pontos turísticos com
coordenadas WGS-84 decimais, categorias validadas contra o catálogo de
configuração (`config/location.json` — chaves persistidas, sem tabela de
catálogo), cronograma semanal por dia/horário com validação de intervalos,
status de operação em três valores com filtro na listagem paginada, e
remoção lógica (`removed_at`) com audit trail via `core.audit`. O endpoint
público `(GET /api/v1/tourist-spots/{spotId})` entrega o detalhe completo
para o app Passaporte sem autenticação, incluindo categorias resolvidas em
`{key, label}` a partir do catálogo configurado, eventos (seam público do
módulo `events`, `[]` até o milestone de eventos) e o link do Google Maps
calculado em tempo de leitura (RNF18). Todos os endpoints sob a tag central
"Tourist Spots"; contrato JSON camelCase estrito via `ApiModel`; falhas via
`ApiError` unificado.

## Technical Context

**Language/Version**: Python 3.13 (type hints em todos os módulos)

**Primary Dependencies**: FastAPI, Pydantic v2 (schemas HTTP-bound),
SQLAlchemy 2.0 (persistência), Alembic (migrations), pydantic-settings
(config), `zoneinfo` (validação do fuso configurado, stdlib)

**Storage**: PostgreSQL em produção / SQLite em memória nos testes (URL
única via `DATABASE_URL`); novas tabelas `tourist_spots`,
`tourist_spot_categories`, `tourist_spot_schedule_entries`

**Testing**: pytest (suíte organizada em unit/contract/integration/smoke +
`test_migrations.py`)

**Target Platform**: Linux, containerizado (Dockerfile + compose.yaml,
feature 004); um processo FastAPI, um banco, um deploy

**Project Type**: web-service (monolito modular FastAPI)

**Performance Goals**: detalhe público < 1 s (SC-005); consulta simples em
tempo hábil para mobile (RNF11) — single-table reads + associação,
sem subsistemas pesados no caminho

**Constraints**: contrato JSON camelCase estrito (`ApiModel`, 422 em chave
desconhecida/snake_case); `ApiError` único em toda falha; tag central
"Tourist Spots"; código em inglês; dados de usuário em português

**Scale/Scope**: volume administrativo de prefeitura (centenas de pontos);
listagem sempre paginada (page/pageSize, máx. 100)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Evidence |
|---|---|---|
| Monolito modular — módulo canônico (`DOMAIN_MODULES`) | PASS | `tourist_spots` já listado em `core/modules.py`; router canônico vazio, routes decoram `MODULE_ROUTERS["tourist_spots"]` |
| Fronteiras entre módulos (só interface de serviço pública) | PASS | Único cruzamento: `tourist_spots` → `events.services.list_public_spot_events` (stub público, seam R8); imports lazy como `employees` → `auth.services` |
| API-Contract-First — schemas Pydantic herdam `ApiModel` | PASS | Todos os DTOs de `modules/tourist_spots/schemas/` herdam `core.schemas.ApiModel` (camelCase, extra=forbid) |
| Tags centralizadas em `core/tags.py` | PASS | Tag `Tourist Spots` já registrada; nenhuma string de tag em arquivos de rota (FR-013) |
| Erro unificado `ApiError` | PASS | Falhas 403/404/422/409 sobem `HTTPException` convertidas por `core.error_handlers` (padrão employees) |
| Test-First (NON-NEGOTIABLE) | PASS | tasks ordenadas red→green; suíte mapeada em research R14 |
| Dados geoespaciais (WGS-84 decimal, validação por schema) | PASS | lat ∈ [-90,90], lng ∈ [-180,180] em Pydantic; decimal degrees only |
| YAGNI / Simplicidade | PASS | Sem tabela de catálogo, sem API de categorias (config), stub mínimo de events, remoção lógica |
| Portabilidade por configuração (RNF06) | PASS | Catálogo + `city_timezone` em `config/location.json`; expansão por JSON |
| Código em inglês (NON-NEGOTIABLE) | PASS | Identificadores/rotas em inglês; conteúdo (nomes/descrições/labels) em português |
| LGPD/segurança (RNF08–10) | PASS | Nenhum dado sensível no domínio (conteúdo público); RBAC via `require_admin`; audit via `core.audit` |
| Migrations Alembic revisadas | PASS | Migration nova `xxxx_tourist_spots` + `tests/test_migrations.py` |

**Post-design re-check**: PASS — nenhum gate violado; sem necessidade de
Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/007-tourist-spots-management/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   └── tourist-spots.md # HTTP contract of the module
└── tasks.md             # Phase 2 output (/speckit-tasks command)
```

### Source Code (repository root)

```text
src/passanorte_back/
├── core/
│   ├── config.py                      # + resolved_city_timezone() (R5)
│   ├── tags.py / routers.py / audit.py / schemas.py / error_handlers.py  # unchanged (used as-is)
│   └── modules.py                     # unchanged (tourist_spots already canonical)
├── modules/
│   ├── tourist_spots/
│   │   ├── routes/
│   │   │   └── tourist_spots.py       # 5 endpoints on the canonical router (R7)
│   │   ├── services/
│   │   │   └── tourist_spots.py       # CRUD flows + validations + audit (R12/R13)
│   │   ├── repositories/
│   │   │   └── tourist_spots.py       # TouristSpot + categories + schedule persistence
│   │   └── schemas/
│   │       └── tourist_spots.py       # ApiModel DTOs (requests/responses, spot_status)
│   └── events/
│       └── services/
│           └── events.py              # NEW public stub list_public_spot_events (R8)
└── config/
    └── (config/location.json)         # + leisure/art/cinema catalog entries + city_timezone (R1/R5)

config/location.json                   # + 3 catalog entries + "city_timezone": "America/Sao_Paulo"

migrations/versions/
└── 20261102_0004_tourist_spots.py     # 3 tables (data-model.md §2)

tests/
├── contract/test_tourist_spots.py     # contract suite (research R14)
├── integration/test_tourist_spots_lifecycle.py
└── unit/test_city_timezone.py
```

**Structure Decision**: single FastAPI monolith (existing). The feature adds
only the canonical module bodies under
`src/passanorte_back/modules/tourist_spots/`, one public-service stub under
`modules/events/`, one migration, config data and tests — no new top-level
structure, no option forks.

## Complexity Tracking

> Not needed: Constitution Check has no violations.