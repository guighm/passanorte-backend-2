# Implementation Plan: JSON camelCase API Contract

**Branch**: `005-camelcase-json-contract` | **Date**: 2026-10-31 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-camelcase-json-contract/spec.md`

## Summary

Establish a cross-cutting JSON contract for the PassaNorte modular monolith:
every HTTP JSON boundary (request bodies AND responses, success and error)
speaks 100% camelCase; input is strict (snake_case and unknown keys → 422
with a unified error payload); Swagger DTO names stay PascalCase properties
camelCase. Enforcement lives in `src/passanorte_back/core/` as a shared
Pydantic base class (`alias_generator` camelCase + `extra="forbid"`) plus
global exception handlers mapping every error to the unified error schema.
Already-live endpoints (specs 002–004: auth, employees, tourists) are
migrated retroactively — direct break on v1, same route paths, same status
codes, no business-logic changes — and a contract-sweep test walks every
registered route and fails on any key containing `_` (clarifications Q1–Q3).

## Technical Context

**Language/Version**: Python 3.13 (type hints everywhere, PEP 8 snake_case
internally)

**Primary Dependencies**: FastAPI, Pydantic v2 (`alias_generators.to_camel`),
pydantic-settings, SQLAlchemy 2 (untouched), Alembic (untouched — no schema
change)

**Storage**: relational (PostgreSQL prod / SQLite tests) — unchanged; no
migration required by this feature

**Testing**: pytest + FastAPI `TestClient` — contract (`tests/contract/`),
integration (`tests/integration/`), unit (`tests/unit/`); in-memory SQLite
via `tests/conftest.py` fixtures

**Target Platform**: Linux server (uvicorn, Docker dev environment from
feature 004)

**Project Type**: modular monolith web service (bounded contexts under
`src/passanorte_back/modules/`, shared infra in `src/passanorte_back/core/`)

**Performance Goals**: no regression — contract conversion happens only at
serialization/validation border; RNF11 response cadence preserved for auth,
tourist spot list, visitation marking

**Constraints**: zero module-boundary breaches; no new third-party
dependency (only Pydantic v2 stdlib-adjacent helpers); route paths and HTTP
status codes unchanged; internal Python identifiers and DB columns remain
snake_case

**Scale/Scope**: ~20 existing schema classes across 3 modules + 1 core base
class + unified error schema + 3 exception handlers + 1 sweep test module +
update of existing contract tests

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Notes |
|------|--------|-------|
| I. API-Contract-First | PASS | Swagger stays the reference contract; camelCase + PascalCase DTOs make it directly generatable into TS types |
| II. Security & LGPD | PASS | Password fields keep `extra="forbid"` strictness; no new sensitive data flow; unified error never echoes credential values |
| III. Test-First (NON-NEGOTIABLE) | PASS | Sweep test + unified-422 contract tests are written RED before the core base class lands; existing contract tests updated alongside |
| IV. Geospatial correctness | N/A | No coordinate logic touched |
| V. Simplicity/YAGNI | PASS | No new dependency; one base class + three handlers; no middleware layer invented beyond what Pydantic aliases give |
| VI. Portability by configuration | PASS | Convention is code-level, city data untouched |
| VII. Maintainability / English naming | PASS | New identifiers in English (`ApiModel`, `error_handlers.py`, errorCode values); docstrings in English; user-facing error `message` strings in English per existing API convention |
| Monolito Modular rules 1–6 | PASS | Infra lives in `core/`; modules only inherit from it; no cross-module imports; no queues/network between modules |
| Quality Gates (ruff, migrations, PT identifiers) | PASS | No Alembic migration (no DB change); ruff kept clean; no snake_case→Portuguese identifiers introduced |

No violations — Complexity Tracking stays empty.

**Post-Phase-1 re-check**: confirmed — design adds only `core/schemas.py`,
`core/error_handlers.py`, two `main.py` registration lines, and test files;
no gate affected.

## Project Structure

### Documentation (this feature)

```text
specs/005-camelcase-json-contract/
├── plan.md              # This file
├── research.md          # Phase 0 output — decisions R1–R7
├── data-model.md        # Phase 1 output — contract entities & mappings
├── quickstart.md        # Phase 1 output — validation guide
├── contracts/
│   └── camelcase-json.md  # JSON contract convention + unified error schema
├── checklists/
│   └── requirements.md  # Spec quality checklist (16/16)
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
src/passanorte_back/
├── core/
│   ├── schemas.py          # NEW: ApiModel base (camelCase aliases, extra=forbid) + ApiError unified error schema
│   └── error_handlers.py   # NEW: 3 exception handlers → unified camelCase error payload
├── main.py                 # EDIT: register the exception handlers
└── modules/
    ├── auth/schemas/__init__.py        # EDIT: inherit ApiModel (5 classes)
    ├── employees/schemas/__init__.py   # EDIT: inherit ApiModel (5 classes)
    └── tourists/schemas/tourists.py    # EDIT: inherit ApiModel (8 classes)

tests/
├── contract/
│   ├── test_camelcase_contract.py      # NEW: FR-011 sweep (FR-001, FR-005, FR-006/007) + camelCase↔snake_case↔unknown-key matrix (FR-003/004) + canary (SC-006)
│   ├── test_unified_error.py           # NEW: ApiError shape probe tests (FR-005)
│   ├── test_strict_input.py            # NEW: strict-input matrix via probe app (US2/FR-003/FR-004)
│   ├── _camelcase.py                   # NEW: pure-function key detector shared by test suites
│   ├── test_auth.py                    # EDIT: camelCase payloads/keys
│   ├── test_employees.py               # EDIT: camelCase payloads/keys
│   ├── test_tourists_register.py       # EDIT: camelCase payloads/keys
│   ├── test_tourists_login.py          # EDIT: camelCase payloads/keys
│   ├── test_tourists_profile.py        # EDIT: camelCase payloads/keys
│   └── test_tourists_interests.py      # EDIT: camelCase payloads/keys
└── unit/
    ├── test_schemas_core.py            # NEW: unit tests for ApiModel alias rules
    └── test_camelcase_detector.py      # NEW: unit tests for the sweep detector (SC-001 canary)
```

**Structure Decision**: Single-project modular monolith (existing layout
from features 001–004). Shared contract infrastructure goes into `core/`
(like `config.py`, `db.py`, `routers.py`); modules only inherit — no
module-local casing rules anywhere, satisfying FR-008/FR-012 by
construction.

## Complexity Tracking

> Empty — no Constitution Check violations to justify.