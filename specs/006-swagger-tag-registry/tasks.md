# Tasks: Centralized Swagger Tag Registry

**Input**: Design documents from `/specs/006-swagger-tag-registry/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/openapi-tags.md ✅, quickstart.md ✅

**Tests**: Test tasks are REQUIRED by constitution Principle III (Test-First,
NON-NEGOTIABLE) — sweep tests written and failing before any implementation
attachment.

**Organization**: Tasks grouped by user story (US1 sweep guarantee = MVP;
US2 catalog/alignment guards; US3 boundary-faithful grouping). All
implementation lands in `core/` + `main.py` — no module route file is
touched (research R2).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

Single pre-existing project (modular monolith): sources under
`src/passanorte_back/`, tests under `tests/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish the baseline; nothing to initialize (project exists).

- [x] T001 Run the full existing suite to record the baseline green state: `uv run pytest -q` and `uv run ruff check .` must pass before any change (FR-008 guard — the contract is frozen from commit 0)

**Checkpoint**: Baseline green — proceed to Foundational.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The tag registry — the single source of truth every story consumes. MUST exist before any attachment or sweep assertion.

**⚠️ CRITICAL**: No story work can begin until this phase is complete.

- [x] T002 Create the tag registry `src/passanorte_back/core/tags.py`: ordered `OPENAPI_TAGS_METADATA` (list of `{name, description}` dicts, exact names/descriptions/canonical order per `contracts/openapi-tags.md` — 10 domain tags `Auth`…`Chatbot`, then infrastructure `Health` as the 11th/last, clarification Q2); `module_tag(module: str) -> str` resolving every canonical `DOMAIN_MODULES` name to its tag (bijective table from research R4 — `tourist_spots` → `Tourist Spots`, all others derived per the table, verbatim strings only); `INFRASTRUCTURE_TAG: Final = "Health"`; fully type-hinted, English identifiers/docstrings; imports nothing from `modules/` (only `core.modules`), raising a clear error for an unknown module name. Do NOT wire it anywhere yet — wiring is story work.

**Checkpoint**: Registry exists and imports cleanly (`python -c "from passanorte_back.core.tags import OPENAPI_TAGS_METADATA, module_tag, INFRASTRUCTURE_TAG"`); app still unchanged and baseline suite still green.

> **Test-First classification (constitution III)**: the tag registry is shared
> infrastructure whose contract tests are the cross-cutting sweep — T003
> (red before the app-level attachments) and T007 (catalog/alignment).
> T002 therefore lands without its own unit-level red step; the red→green
> cycle for this feature is T003 red → T004–T006 green.

---

## Phase 3: User Story 1 — Every endpoint under exactly one declared tag (Priority: P1) 🎯 MVP

**Goal**: Every operation of the generated OpenAPI carries exactly one registered tag; the cross-cutting sweep fails on untagged/default/multi/unregistered operations.

**Independent Test**: `uv run pytest tests/contract/test_openapi_tags.py -v` — sweep green after T006; red if any tag attachment is reverted.

### Tests for User Story 1 (write FIRST, ensure FAIL before attachment)

- [x] T003 [P] [US1] Write the per-operation sweep in `tests/contract/test_openapi_tags.py`: iterate every path × method operation from the real app's OpenAPI document (import pattern of `tests/smoke/test_health.py`) and assert for each: `tags` present, non-empty, **exactly one** entry (FR-005/SC-002), and a member of the registry names (FR-004); assertion messages MUST name the offending path + method (SC-004 discipline; multi-tag and empty cases get distinct failure text). Run it — MUST be red (all operations currently untagged) before T004–T006.

### Implementation for User Story 1

- [x] T004 [P] [US1] Attach module tags at the canonical router creation point in `src/passanorte_back/core/routers.py`: `APIRouter(prefix=module_prefix(name), tags=[module_tag(name)])` (research R2) — every existing operation of auth/employees/tourists inherits its tag; no `modules/*/routes/*.py` file is modified.
- [x] T005 [US1] Declare the catalog in `src/passanorte_back/main.py`: `FastAPI(..., openapi_tags=OPENAPI_TAGS_METADATA)` — no change to `custom_openapi` (research R5: it only patches `components/schemas`).

  > **Implemented delta (red test caught R5)**: `custom_openapi` calls
  > `get_openapi()` directly, which does NOT pick up `app.openapi_tags` —
  > the hook was updated to re-pass `tags=app.openapi_tags` (FR-006).
  > Research R5 corrected accordingly.
- [x] T006 [US1] Tag the core-owned route in `src/passanorte_back/main.py`: `@app.get("/health", tags=[INFRASTRUCTURE_TAG])` — path, status codes and payload unchanged (FR-008).

Run T003 suite → green. **Checkpoint**: US1 fully functional — every operation tagged exactly once with a registered tag; verify `GET /docs` shows no uncategorized group.

---

## Phase 4: User Story 2 — Tag catalog defined once in core, aligned 1:1 (Priority: P2)

**Goal**: The catalog is verifiably the single source of truth: exact content, hand-written descriptions, canonical order, bijective alignment with `DOMAIN_MODULES` (clarification Q3).

**Independent Test**: The catalog/alignment tests in `tests/contract/test_openapi_tags.py` pass; they fail if any tag is renamed, reordered, added or dropped.

### Tests for User Story 2 (regression guards — red only if the registry deviates)

- [x] T007 [P] [US2] Add catalog + alignment tests to `tests/contract/test_openapi_tags.py`: (a) the OpenAPI document declares exactly the 11 registry tags with non-empty English descriptions and the exact canonical display order — 10 domain tags then `Health` last (FR-006/SC-003, clarification Q2); (b) bijective alignment between `DOMAIN_MODULES` and the 10 domain tags via `module_tag` (FR-002/SC-003): every canonical module resolves to a distinct catalog tag and no extra domain tag exists; (c) descriptions match `contracts/openapi-tags.md` verbatim.

**Checkpoint**: US2 complete — catalog content, order and module alignment are locked by tests.

---

## Phase 5: User Story 3 — Documentation grouping matches module boundaries (Priority: P3)

**Goal**: Each shipped domain module's operations are grouped under exactly its tag; `GET /health` under `Health`; no foreign operation leaks into a group (SC-005).

**Independent Test**: The grouping test passes and fails if any operation changes group (e.g. a route is moved to a wrong router).

### Tests for User Story 3 (regression guards)

- [x] T008 [P] [US3] Add the grouping test to `tests/contract/test_openapi_tags.py`: for each shipped module (`auth`, `employees`, `tourists`), every operation whose path starts with the module's prefix (`/api/v1/<name-with-hyphens>` per `module_prefix`) carries exactly that module's tag — and conversely, no operation outside that prefix carries it; `GET /health` carries only `Health` (US3 acceptance scenarios; SC-005/SC-006).

**Checkpoint**: All user stories complete — groupings map 1:1 onto bounded contexts.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Frozen-contract regression sweep and documentation.

- [x] T009 Run the full regression sweep: `uv run pytest -q` (all contract/integration/smoke/unit suites of specs 002–005 pass with assertions untouched — FR-008/SC-006; the camelCase sweep of spec 005 stays green, research R6) and `uv run ruff check .` clean.

> **FR-007 fulfillment**: spec FR-007's "update/extend existing contract
> tests" is satisfied by **extending the contract suite with the new module
> `tests/contract/test_openapi_tags.py`** (T003/T007/T008) while leaving all
> pre-existing tests untouched — which is the stronger form of "without
> weakening any pre-existing assertion" (nothing to accidentally weaken).
> No task edits existing test files.
- [x] T010 [P] Update `README.md` (or the docs section that documents the API/Swagger, if present) with the tag registry convention: tags declared only in `core/tags.py`, one per canonical module + `Health`, endpoints tagged by router attachment — in English (Principle VII).
- [x] T011 Run the `quickstart.md` validation end-to-end, including the local negative check (temporarily revert T004, observe the sweep fail naming path + method, then restore — SC-004; do not commit the reverted state).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none — start immediately.
- **Foundational (Phase 2)**: after T001; **blocks all stories** (registry is imported by every attachment and asserted by every sweep test).
- **US1 (Phase 3)**: after T002; T003 (tests, red) → T004/T005/T006 (attachments) → sweep green.
- **US2 (Phase 4)**: after T002 (registry) and logically after T005 (catalog visible in the document) — T007.
- **US3 (Phase 5)**: after T004 + T006 (grouping observable) — T008.
- **Polish (Phase 6)**: after all stories (T009 → T010 ∥ T011).

### User Story Dependencies

- **US1**: blocked only by Foundational — independent, delivers the MVP alone.
- **US2**: test-only guards; can be written once T002 exists, but the assertion over the rendered document requires T005.
- **US3**: test-only guard; requires T004 + T006 to be observable.

### Within Each User Story

- Tests written and failing BEFORE implementation (US1); guard tests (US2/US3) are written after the behavior they lock is green, per constitution Test-First applied to this feature's red-green core (US1).
- No task modifies more than one story's file set — no cross-story file conflicts.

### Parallel Opportunities

- T010 (docs) runs in parallel with T011.
- T003 may be written while T002 is in review — but its red run requires no attachment to exist.
- This feature is intentionally single-threaded (2-line + 1-file + 1-test-module scope); parallelism marks are advisory only.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. T001 baseline → T002 registry → T003 red sweep → T004–T006 attachments → sweep green.
2. **STOP and VALIDATE**: `uv run pytest tests/contract/test_openapi_tags.py -v` + `GET /docs` visual check.
3. The API documentation contract (SC-001..004) is fully delivered.

### Incremental Delivery

- +US2 (T007): catalog becomes tamper-evident (order/description/alignment locked).
- +US3 (T008): boundary fidelity locked.
- +Polish (T009–T011): frozen-contract sweep, README, quickstart walkthrough.

---

## Notes

- Constitution gates for every task: English identifiers only; `ruff` clean; no module-private import across domains (`core/tags.py` imports only `core.modules`); no new dependency; no route path/method/payload/status change; no migration (no schema change).
- Commit after each task or logical group (per repo convention, conventional commits in English).
- Verify tests fail before implementing (US1) / fail when guarding (US2/US3 via a quick local revert).