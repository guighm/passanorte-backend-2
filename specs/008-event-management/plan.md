# Implementation Plan: Tourist Spot Events Management

**Branch**: `008-event-management` | **Date**: 2026-11-02 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/008-event-management/spec.md`

## Summary

CRUD administrativo (RBAC de administrador) de eventos associados a pontos
turísticos: criação (RF16), edição (incluindo a troca do ponto associado) e
remoção (RF17), com preço do ingresso armazenado como valor monetário exato
(cents inteiros; zero = gratuito — dependência do chatbot RF39) e audit
trail via `core.audit` (RNF19). Regra de negócio central: um evento só
referencia um ponto ativo e **não** permanentemente fechado — ponto
inexistente → 404, ponto permanentemente fechado → 409 (`conflict` na
taxonomia unificada). Listagens do painel: um único endpoint administrativo
com filtro opcional por ponto (`spotId`) e/ou faixa inclusive de datas de
ocorrência (`startDate`/`endDate`; início > fim → 422) — esclarecimento da
sessão 2026-11-02. A resposta pública de detalhe do ponto (spec 007, RF27)
passa a embutir os eventos reais do ponto (data, descrição, preço) via a
mesma função de serviço pública do módulo `events`. Remoção do ponto
(delete lógico `removed_at`) faz cascade dos eventos (esclarecimento: os
eventos deixam de existir com o ponto), executando a escrita cruzada pela
função pública de serviço do domínio dono. Todos os endpoints sob a tag
central "Events"; contrato camelCase estrito via `ApiModel`; falhas via
`ApiError` unificado.

## Technical Context

**Language/Version**: Python 3.13 (type hints em todos os módulos)

**Primary Dependencies**: FastAPI, Pydantic v2 (schemas HTTP-bound,
`Decimal` para o valor monetário), SQLAlchemy 2.0 (persistência),
Alembic (migrations), pydantic-settings (config)

**Storage**: PostgreSQL em produção / SQLite em memória nos testes (URL
única via `DATABASE_URL`); nova tabela `events` (FK `spot_id` →
`tourist_spots.id`)

**Testing**: pytest (suíte unit/contract/integration/smoke +
`test_migrations.py`); `tests/conftest.py` fornece banco isolado por teste,
admin/employee seed e captura de audit (`audit_logs`)

**Target Platform**: Linux, containerizado (feature 004); um processo
FastAPI, um banco, um deploy

**Project Type**: web-service (monolito modular FastAPI)

**Performance Goals**: leitura de associados ao ponto em tempo hábil mobile
(RNF11) — single-table query por índice `spot_id`; sem subsistemas pesados
no caminho

**Constraints**: contrato JSON camelCase estrito (`ApiModel`, 422 em chave
desconhecida/snake_case); `ApiError` único em toda falha (409 →
`errorCode: "conflict"` via `core.error_handlers`); tag central "Events";
código em inglês; descrição de evento = conteúdo de usuário em português

**Scale/Scope**: volume administrativo de prefeitura (centenas de eventos);
listagens sem paginação nesta versão (especificação 008, YAGNI)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Evidence |
|---|---|---|
| Monolito modular — módulo canônico (`DOMAIN_MODULES`) | PASS | `events` já listado em `core/modules.py`; router canônico existe e está vazio; routes decorarão `MODULE_ROUTERS["events"]` |
| Comunicação entre módulos só via interface pública de serviço | PASS | eventos lê a existência/status do ponto pela função pública do módulo `tourist_spots` (nova função de consulta pública — ver research R3); `tourist_spots.remove_spot` executa o cascade chamando a função pública de serviço de `events` (R5); nunca importa models/repos privados |
| Sem compartilhamento de tabelas entre domínios | PASS | tabela `events` pertence ao módulo `events`; FK ao `tourist_spots.id` é referência somente-leitura dona por `events` (precedente do data-model 007) |
| API-Contract-First: schemas `ApiModel` + tag central | PASS | todos os DTOs herdarão `core.schemas.ApiModel`; tag "Events" já registrada em `core/tags.py` e aplicada em `core/routers.py`; nenhum route file escreve tag |
| Falhas via `ApiError` unificado | PASS | 409 já mapeado em `core.error_handlers` (`conflict`); 404/403/422 pelos handlers existentes |
| Segurança/LGPD: RBAC admin | PASS | escritas e listagens administrativas via `require_admin` (spec 002) — precedente `tourist_spots`/`employees`; nenhum dado sensível LGPD no evento |
| RNF19 audit | PASS | `core.audit.record_action` — 1 registro por escrita (create/update/delete), precedente spec 007 |
| Preço monetário explícito (RF39) | PASS | armazenamento em cents inteiros (`Integer`), sem float; contrato `Decimal` com 2 casas (R1) |
| Test-First (NON-NEGOTIABLE) | PASS | tarefas serão test-first: contrato (schemas/status codes) + integração (ponto → evento → listagens), cobertura como critério |
| YAGNI | PASS | sem paginação nesta versão (especificação 008); sem cache, sem dependências novas |
| Portabilidade (RNF06) | PASS | moeda fica no contexto configurado do sistema; nada de moeda em lógica de código |

## Project Structure

### Documentation (this feature)

```text
specs/008-event-management/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/
│   └── events.md        # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/passanorte_back/
├── core/                          # (unchanged — events uses the shared infra as-is)
│   ├── modules.py                 # "events" already canonical
│   ├── tags.py                    # "Events" tag already registered
│   ├── routers.py                 # MODULE_ROUTERS["events"] already mounted
│   ├── schemas.py                 # ApiModel / ApiError
│   ├── error_handlers.py          # 404/409/403 → unified payload
│   └── audit.py                   # record_action
└── modules/events/
    ├── repositories/
    │   └── events.py              # NEW: Event model + data access (events-owned table)
    ├── schemas/
    │   └── events.py              # NEW: request/response DTOs (ApiModel)
    ├── services/
    │   └── events.py              # EXTEND: real flows + public spot events seam
    └── routes/
        └── events.py              # NEW: admin CRUD + filtered listing on MODULE_ROUTERS["events"]

src/passanorte_back/modules/tourist_spots/
├── services/tourist_spots.py      # EXTEND: remove_spot cascade via events public service
└── (queries for spot existence/status consumed via public service function)

migrations/versions/
└── 20261102_0005_events.py        # NEW: events table + index

tests/
├── contract/
│   ├── test_events.py             # NEW: CRUD contract (201/200/204/403/404/409/422)
│   └── (camelcase/strict-input sweeps already cover the new module)
├── integration/
│   └── test_events_lifecycle.py   # NEW: spot → event → list by spot / by date range → edit → delete
└── unit/
    └── test_events_price.py       # NEW: monetary exactness (cents ⇄ Decimal, negatives rejected)
```

**Structure Decision**: módulo canônico `events` já existe como skeleton
(`core/modules.py`) com o seam público `list_public_spot_events`
(`modules/events/services/events.py`, devolvido do feature 007). O padrão
de referência é o módulo `tourist_spots` (007): routes → services →
repositories → schemas, tag exclusivamente em `core/routers.py`, erros via
`HTTPException` mapeada pela taxonomia unificada, uma ação = uma linha de
audit. A tabela `events` é exclusiva do domínio; a referência ao ponto é
por FK e só pode ser escrita pela interface de serviço.

## Complexity Tracking

> Nenhuma violação de constituição a justificar — a feature segue o padrão
> consolidado do módulo `tourist_spots` sem novas dependências, sem novos
> princípios e sem estrutura extra.