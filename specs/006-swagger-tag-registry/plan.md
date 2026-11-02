# Implementation Plan: Centralized Swagger Tag Registry

**Branch**: `006-swagger-tag-registry` | **Date**: 2026-11-02 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/006-swagger-tag-registry/spec.md`

## Summary

Organize the generated API documentation by tags: a hand-written catalog of
exactly 11 tags (10 domain tags in canonical order + `Health` last) declared
once in `core/`, attached at the single canonical-router creation point
(`MODULE_ROUTERS`) and on the root `/health` route, with a cross-cutting
contract test sweeping the OpenAPI document that fails on any untagged,
default-tagged, multi-tag or unregistered operation. No route paths, JSON
contract (spec 005 camelCase) or business logic changes.

## Technical Context

**Language/Version**: Python 3.13, FastAPI + Pydantic v2 (constitutional stack)

**Primary Dependencies**: FastAPI (native `openapi_tags` metadata + native
`tags=[...]` support on `APIRouter` and route decorators) — **no new
dependency**

**Storage**: N/A (documentation metadata only; no schema change, no migration)

**Testing**: pytest (existing `tests/contract/`, `tests/smoke/`,
`tests/unit/` layout)

**Target Platform**: Same single-process FastAPI app (`passanorte_back.main:app`)

**Project Type**: web-service (modular monolith backend)

**Performance Goals**: N/A — OpenAPI generation already happens once per
schema request; 11 static tag entries add no measurable cost

**Constraints**: Zero route path/method status; zero payload change (spec 005
camelCase contract frozen); English-only identifiers (constitutional VII);
test-only enforcement (spec clarification Q1) — no startup guard

**Scale/Scope**: 11 registry entries; ~20 existing endpoint operations
(auth, employees, tourists, /health) tagged retroactively via 2 declaration
points + 1 new contract test module

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Evidence |
|---|---|---|
| Monolito Modular Primeiro (preamble) | PASS | Tag registry lives in `core/` (shared infrastructure, preamble rule 4); one tag per entry of `DOMAIN_MODULES`; modules never name tags inline (FR-003) — consistent with bounded-context separation |
| I. API-Contract-First | PASS | OpenAPI/Swagger IS the documented contract; this feature improves exactly that contract; no frontend-visible API change (FR-008) |
| V. Simplicidade / YAGNI | PASS | Native FastAPI mechanism (`openapi_tags`, `tags=[...]`), no new dependency, no startup guard (clarification Q1), no extra abstractions beyond one small `core/tags.py` |
| VII. Manutenibilidade — English-only naming | PASS | Tag names are the canonical English names (`Auth`, `Employees`, …) mirroring `DOMAIN_MODULES`; descriptions in English (developer-facing docs) |
| III. Test-First | PASS | Cross-cutting sweep tests specified in spec (SC-001..004) and detailed in Phase 1; test plan precedes implementation in task ordering (enforced by `/speckit-tasks`) |
| Quality Gates (no cross-module import, no Portuguese identifiers, migrations reviewed) | PASS | No schema change → no migration; `core/tags.py` imported by `core/routers.py` (core→core) and `main.py`; module route files untouched |

**Post-Phase-1 re-check**: PASS — design touches `core/tags.py` (new),
`core/routers.py` (1 line), `main.py` (1 line), `main.py` FastAPI
constructor (openapi_tags) and adds one test module. Nothing crosses module
private boundaries; `modules/*/routes/*` files remain untouched (tags are
inherited from the canonical router), which also satisfies spec FR-003's
"no loose tag strings in module code".

## Project Structure

### Documentation (this feature)

```text
specs/006-swagger-tag-registry/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── openapi-tags.md  # Tag catalog + sweep contract
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
src/passanorte_back/
├── main.py                      # + openapi_tags on FastAPI(), + tags on /health route
└── core/
    ├── tags.py                  # NEW: tag registry (names, descriptions, order, lookup)
    └── routers.py               # + tags=[...] on the canonical MODULE_ROUTERS creation

tests/
└── contract/
    └── test_openapi_tags.py     # NEW: cross-cutting sweep (untagged/default/multi/unregistered + alignment + order)
```

**Structure Decision**: Single-project layout already established by the
constitution (modular monolith, `core/` + `modules/`). The change is pure
shared-infrastructure: one new `core/` unit plus one-line attachments, one
new cross-cutting test module under `tests/contract/`. No module directory
gains or loses files.

## Complexity Tracking

> No constitution violations to justify — table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| — | — | — |