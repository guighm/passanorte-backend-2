# Tasks: JSON camelCase API Contract

**Input**: Design documents from `/specs/005-camelcase-json-contract/`

**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/camelcase-json.md ✓

**Tests**: Included and MANDATORY — constitution Principle III (Test-First NON-NEGOTIABLE): every task labeled RED must fail before its GREEN counterpart lands; contract + unit coverage per feature.

**Organization**: Grouped by user story (US1–US4 from spec.md). Key structural note (grounded in research.md R7): the strict-input behavior (US2) and camelCase *output* on live endpoints (US3) materialize when module schemas migrate — core infrastructure is built in Phase 2 and first proven endpoint-independent (US2 uses a probe app), with the retroactive migration of the live schemas in US3.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

## Path Conventions

Single-project modular monolith (plan.md): `src/passanorte_back/` (core/ + modules/), `tests/` (contract/, integration/, unit/).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish the verified green baseline before any RED test lands.

- [X] T001 Verify pre-feature baseline per quickstart.md §1: `uv run pytest -q` reports 142 passed and `uv run ruff check .` is clean — no file changes, records the starting point for T019 parity checks

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core contract infrastructure in `core/` that MUST be complete before ANY user story. ⚠️ No story work starts until this phase is green.

- [X] T002 RED Unit tests for the contract base: create `tests/unit/test_schemas_core.py` asserting `ApiModel` behavior — camelCase aliases from snake_case attributes (incl. acronym folding `user_cpf`→`userCpf`, `cpf`→`cpf` per contracts rule 1), `extra="forbid"` on unknown keys, snake_case key rejected at validation time (no `populate_by_name`), `model_dump(by_alias=True)`/serialized-alias output — must fail (class does not exist yet)
- [X] T003 GREEN Implement `ApiModel` base class in `src/passanorte_back/core/schemas.py` per research.md R1 — `BaseModel` with `ConfigDict(alias_generator=to_camel, extra="forbid")` and NO `populate_by_name`; docstring quoting FR-002/FR-008 — makes T002 pass. Deviation recorded: an `__init__` bridge leaks into `model_validate` (Pydantic 2.14) — internal construction uses the `from_internal` classmethod (snake kwargs preserved, FR-002) instead; test extended accordingly
- [X] T004 RED Tests for the unified error payload + key detector: create `tests/unit/test_camelcase_detector.py` (pure detector function — accepts camelCase payload trees, fails on any key containing `_`, deep recursion incl. lists/dicts; canary plant proves RED-on-violation per SC-001) and `tests/contract/test_unified_error.py` (probe FastAPI app + TestClient: 422 shape `{errorCode, message, details[{key, message}]}` naming the received key, HTTPException→errorCode taxonomy per contracts §2, 500 generic message with no internals) — must fail
- [X] T005 GREEN Implement `ApiError` + `ApiErrorKeyDetails` in `src/passanorte_back/core/schemas.py` (PascalCase DTO names, camelCase properties, `details=[]` default — contracts/camelcase-json.md §2) and the detector helper module `tests/contract/_camelcase.py` (pure function imported by both test suites) — makes T004's schema/detector portions pass
- [X] T006 GREEN Implement the three exception handlers in `src/passanorte_back/core/error_handlers.py` per research.md R3 — `RequestValidationError`→422 `validation_error` with per-offending-key `details` (key as received, per contracts rule 3), `StarletteHTTPException`→status-preserving taxonomy mapping (401 `authentication_failed`, 403 `authorization_failed`, 404 `resource_not_found`, 409 `conflict`, other 4xx `request_error`), unhandled `Exception`→500 `internal_error` generic message (constitution II: no internals leaked) — and register them on the app in `src/passanorte_back/main.py` — makes T004 pass fully
- [X] T007 Verify foundational checkpoint: `uv run pytest tests/unit/test_schemas_core.py tests/unit/test_camelcase_detector.py tests/contract/test_unified_error.py -q` green + full `uv run pytest -q` green (no live endpoint changed yet)

**Checkpoint**: Core contract infra ready — user stories can proceed.

---

## Phase 3: User Story 1 — Consistent camelCase JSON on every response (Priority: P1) 🎯 MVP

**Goal**: The sweep machinery that fails on ANY snake_case response key, green on currently-compliant surfaces (errors, OpenAPI, `/health`); success-path activation completes at US3.

**Independent Test**: `uv run pytest tests/contract/test_camelcase_contract.py -q` — canary proves the detector fails on a planted `_` key (SC-001); static+runtime sweep green on compliant surfaces.

### Tests for User Story 1 (RED first)

- [X] T008 RED [US1] Create the sweep suite `tests/contract/test_camelcase_contract.py` per research.md R4: (1) detector canary — planted snake_case key in a canned payload makes the check fail (SC-001); (2) static OpenAPI sweep — every `app.openapi()` property name contains no `_` and `ApiError` is registered; (3) runtime sweep — walk `app.routes`, request each endpoint (unauthenticated 401 JSON bodies included), recursively assert no key contains `_`; include `/health` (research.md R6); success paths of live un-migrated endpoints marked with an explicit pending-migration exclusion list (removed by T015–T017/T019) — must fail on exclusion surfaces it can already see

### Implementation for User Story 1

- [X] T009 GREEN [US1] Drive the sweep portion GREEN: fix any violation the sweep exposes on compliant surfaces (likely none — errors/unified payload already camelCase from Phase 2); confirm canary RED-on-plant works and success-path exclusions are the only skips; `uv run ruff check .` clean

**Checkpoint**: Sweep machinery live and proven non-vacuous; full-green completion lands with US3 migration.

---

## Phase 4: User Story 2 — Strict camelCase-only input (Priority: P1)

**Goal**: Endpoint-independent proof that bodies speak strict camelCase: snake_case and unknown keys → 422 with the key named; whole body fails together (FR-003/FR-004).

**Independent Test**: `uv run pytest tests/contract/test_strict_input.py -q` — matrix green against the core infra via a probe app (live-endpoint strictness is asserted by US3 task tests).

### Tests for User Story 2 (RED first)

- [X] T010 RED [US2] Create the strict-input matrix `tests/contract/test_strict_input.py`: probe FastAPI app wired with core handlers (T006) + a request schema inheriting `ApiModel` (e.g. `firstName: str`); assert (1) camelCase body accepted, (2) one-field snake_case rewrite → 422 naming the received key in `details`, (3) unknown extra key → 422 naming it, (4) mixed camelCase+snake_case → 422 with NO partial application, (5) nested-object and list-of-objects bodies obey the whole-tree rule (FR-003 any nesting level), (6) keys inside string values (e.g. e-mail containing `_`) pass — must fail where infra gaps surface

**Implementation for User Story 2**

- [X] T011 GREEN [US2] Fix any infra gap T010 exposes (expected: none — `extra="forbid"` + no `populate_by_name` already enforce; candidates: nested-body detail `key` path formatting in the 422 handler per contracts §2); `uv run pytest tests/contract/test_strict_input.py -q` green

**Checkpoint**: Strict-input contract proven end-to-end independent of module migration.

---

## Phase 5: User Story 3 — Retroactive migration of shipped modules (Priority: P2)

**Goal**: auth, employees, tourists (specs 002–004) fully under the new contract — same paths, same status codes, zero business-logic change; existing contract tests updated; full sweep green with zero exclusions.

**Independent Test**: `uv run pytest tests/contract -q` green with camelCase payloads; sweep runs with NO exclusions and SC-003 parity assertion holds.

### Tests for User Story 3 (RED first — all [P], different files)

- [X] T012 RED [P] [US3] Update `tests/contract/test_auth.py` per data-model.md auth mapping: payloads/responses in camelCase (`refreshToken`, `accessToken`, `tokenType`, `expiresIn`, `isActive`, `updatedAt`) + new assertions: snake_case input → 422 naming key, camelCase accepted (FR-009/FR-010) — must fail now
- [X] T013 RED [P] [US3] Update `tests/contract/test_employees.py`: camelCase payloads (`initialPassword`, `createdAt`, `updatedAt`) + snake_case/unknown-key 422 assertions — must fail now
- [X] T014 RED [P] [US3] Update `tests/contract/test_tourists_register.py`, `test_tourists_login.py`, `test_tourists_profile.py`, `test_tourists_interests.py`: camelCase payloads (`firstName`, `lastName`, `countryOfOrigin`, `passportNumber`) + snake_case/unknown-key 422 assertions — must fail now
- [X] T015 RED [US3] Extend `tests/contract/test_camelcase_contract.py` runtime sweep: remove the pending-migration exclusion list (T008) so ALL success paths are swept; add SC-003 parity assertion — `app.openapi()["paths"]` keys byte-identical to the T001 baseline and status codes unchanged for existing flows — must fail (live endpoints still snake_case)

### Implementation for User Story 3 (all [P], different files)

- [X] T016 GREEN [P] [US3] Migrate `src/passanorte_back/modules/auth/schemas/__init__.py`: 5 classes `BaseModel`→`ApiModel`; preserve `from_attributes=True` on `AdminAccountStatus` (research.md R7); collapse now-redundant per-class `extra="forbid"` into the base — makes T012 pass
- [X] T017 GREEN [P] [US3] Migrate `src/passanorte_back/modules/employees/schemas/__init__.py`: 5 classes → `ApiModel`; collapse redundant config — makes T013 pass
- [X] T018 GREEN [P] [US3] Migrate `src/passanorte_back/modules/tourists/schemas/tourists.py`: 8 classes → `ApiModel`; collapse redundant config — makes T014 pass
- [X] T019 GREEN [US3] Drive the full sweep GREEN: run `tests/contract/test_camelcase_contract.py`, fix whatever the exclusion-free sweep exposes (depends T016–T018); then `uv run pytest -q` full suite green + `uv run ruff check .` clean

**Checkpoint**: All specs 002–004 endpoints under the contract retroactively; sweep exclusion-free.

---

## Phase 6: User Story 4 — Swagger as the single source for frontend types (Priority: P3)

**Goal**: OpenAPI verified as TS-source: PascalCase DTO names, camelCase properties identical to delivered keys.

**Independent Test**: `uv run pytest tests/contract/test_camelcase_contract.py::test_openapi_dto_names -q` green; types generated from `/openapi.json` compile against responses (quickstart.md §2–§3).

### Tests for User Story 4 (RED first)

- [X] T020 RED [P] [US4] Add DTO-name assertions to `tests/contract/test_camelcase_contract.py` (`test_openapi_dto_names`): every OpenAPI schema/DTO name PascalCase and property names camelCase-identical to delivered keys (FR-006/FR-007); `ApiError` and all migrated module DTOs listed — RED procedure: assert first against a small canned OpenAPI mini-fixture containing a deliberate snake_case property and a lowercase DTO name inside the test module (deterministic RED without mutating production code or config), then run against the real `app.openapi()` which must pass clean

### Implementation for User Story 4

- [X] T021 GREEN [US4] Confirm T020 green with the real OpenAPI (expected: pass immediately — class names were already PascalCase, research.md R7); fix if any name violates; note: no code change anticipated

**Checkpoint**: Swagger verified as frontend-type source of truth.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T022 [P] Update documentation: add a "JSON Contract (camelCase)" section to `README.md` referencing `specs/005-camelcase-json-contract/contracts/camelcase-json.md`; summarize feature 005 in `docs/SPECS.md` following the existing per-feature format
- [X] T023 Final gate per constitution Quality Gates: `uv run pytest -q` fully green (baseline 142 + new), `uv run ruff check .` + `uv run ruff format --check .` clean, no Alembic migration needed (data-model.md), no module-boundary breach (`core/boundaries.py` check passes), SC-006 canary — temporary `ApiModel` subclass with snake_case attribute aliases camelCase asserted in `tests/unit/test_schemas_core.py`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (T001)**: no dependencies — start immediately
- **Foundational (T002–T007)**: depends on T001; **BLOCKS all user stories**
- **US1 (T008–T009)**: depends on Phase 2; sweep exclusions removed later by US3
- **US2 (T010–T011)**: depends on Phase 2; independent of US1/US3 (probe app)
- **US3 (T012–T019)**: depends on Phase 2 (core infra) and conceptually completes US1's sweep; test tasks T012–T015 [P]; impl T016–T018 [P]; T019 last (depends T016–T018)
- **US4 (T020–T021)**: depends on T019 (sweep stable); T020 [P]
- **Polish (T022–T023)**: depends on all stories complete

### Within Each Story

- RED test tasks before their GREEN counterparts (constitution III)
- T016/T017/T018 only after their respective RED tests exist
- Story complete at its checkpoint before next-priority work claims sweep scope

### Parallel Opportunities

- T012/T013/T014 (different test files) — one shot
- T016/T017/T018 (different module schema files) — one shot
- T022 alongside any final task; T020 parallel to nothing blocking

---

## Parallel Example: User Story 3

```bash
# RED tests together (different files):
Task: "Update tests/contract/test_auth.py (T012)"
Task: "Update tests/contract/test_employees.py (T013)"
Task: "Update tests/contract/test_tourists_*.py (T014)"

# Then migrations together (different files):
Task: "Migrate modules/auth/schemas/__init__.py (T016)"
Task: "Migrate modules/employees/schemas/__init__.py (T017)"
Task: "Migrate modules/tourists/schemas/tourists.py (T018)"
```

---

## Implementation Strategy

### MVP First (through US1)

1. T001 baseline → T002–T007 foundational
2. T008–T009 → sweep live and non-vacuous on compliant surfaces
3. **STOP and VALIDATE**: canary + probe tests prove the contract machinery

### Incremental Delivery

- +US2: strict-input proven end-to-end (probe) → strictness is real
- +US3: live endpoints migrate → full sweep exclusion-free green (the user-visible milestone)
- +US4: Swagger verified as TS source → frontend generation unblocked
- Polish: docs + final quality gates

### Notes

- Commit after each task or logical RED→GREEN group (constitution workflow)
- The detector is a pure function — never mutate payloads before checking
- No Alembic migration anywhere in this feature (data-model.md)
- Route paths and business logic: untouched by every task above (FR-009/FR-013)
---

## Phase 8: Convergence

- [X] T024 Add a schema-guard test asserting EVERY class declared in `src/passanorte_back/modules/*/schemas/` subclasses `ApiModel` (import/AST scan — closes the request-body blind spot: the sweep's static leg only walks `response_model` trees), so FR-012/SC-006 hold for future schemas regardless of usage — per FR-012/SC-006 (partial)
- [X] T025 Extend contract tests with snake_case-input → 422 (key named) and unknown-key → 422 assertions for the three remaining live body endpoints: `PATCH /api/v1/employees/{id}`, `PATCH /api/v1/tourists/{id}` and `PUT /api/v1/tourists/me/interests` (rule is already inherited; this closes the per-endpoint 100% coverage claim of SC-002) — per SC-002/FR-003 (partial)
