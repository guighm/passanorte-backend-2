# Tasks: Tourist Spot Events Management (feature 008)

**Input**: Design documents from `/specs/008-event-management/`

**Prerequisites**: plan.md (required), spec.md (required for user stories),
research.md, data-model.md, contracts/, quickstart.md

**Tests**: included — constitution III (Test-First, NON-NEGOTIABLE)
mandates test→fail→implement→green, and the spec's acceptance gate IS the
contract suite (SC-006) plus the integration flow (spot → event → list by
spot / by date range). Every story phase starts with failing tests.

**Organization**: Tasks grouped by user story so each story can be
implemented and tested independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

## Path Conventions

Single project (monolith): `src/passanorte_back/`, `tests/` at repository
root (see plan.md Project Structure).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Nothing required — the `events` module skeleton (canonical
entry in `core/modules.py`, empty `MODULE_ROUTERS["events"]` router, tag
"Events" in `core/tags.py`, `list_public_spot_events` seam from feature
007) already exists. No configuration-data change is needed (R12): the
currency-context requirement lives in system configuration, and the module
introduces no new settings.

- No tasks.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Migration, persistence, DTOs and the exact-money conversion —
blocking prerequisites for ALL user stories

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T001 [P] Create Alembic migration
  `migrations/versions/20261102_0005_events.py` creating exactly the one
  table of `specs/008-event-management/data-model.md` §1: `events` with
  `id` int PK; `spot_id` int FK → `tourist_spots.id`
  (`ondelete="CASCADE"`) indexed; `occurrence_date` Date indexed
  (calendar date, no time-of-day); `description` String(2000);
  `ticket_price_cents` Integer NOT NULL (exact monetary amount in cents,
  never float — R1; ≥ 0 enforced above this layer); `created_at`/
  `updated_at` datetime UTC (007 precedent). Verify with
  `pytest tests/test_migrations.py` (upgrade head applies 0005 down
  cleanly)
- [X] T002 [P] Create the `Event` model + data access in
  `src/passanorte_back/modules/events/repositories/events.py` per
  data-model §1: `Event` SQLAlchemy model with the exact column set of the
  migration; functions `add_event(session, spot_id, occurrence_date,
  description, ticket_price_cents)`, `get_event`, `find_event_by_id`,
  `list_events(session, spot_id=None, start_date=None, end_date=None)`
  (filters combined, ordered `(occurrence_date, id)`, **no pagination**
  — spec 008 assumption), `delete_event`, `delete_spot_events` (hard
  delete of a spot's rows — research R4). No uniqueness beyond PK
  (multiple events per spot/date allowed)
- [X] T003 [P] Write failing unit tests FIRST in
  `tests/unit/test_events_price.py`: money conversion helpers
  (`price → cents → Decimal`) with exact round-trips (e.g. `15.50 ⇄
  1550`, `"0.00" ⇄ 0` free event, large value `987654.32 ⇄ 98765432`),
  rejection of >2 decimal places and of negative amounts, and DTO shape
  checks (strict input, `occurrenceDate` ISO `YYYY-MM-DD` only, `1..2000`
  description) — run `pytest tests/unit/test_events_price.py` red before
  T004 (research R1/R6). Isolated from any app machinery (pure schema/unit
  test)
- [X] T004 Create the DTOs in
  `src/passanorte_back/modules/events/schemas/events.py` per
  `specs/008-event-management/contracts/events.md` §1–§3, all inheriting
  `core.schemas.ApiModel` (camelCase JSON, strict border): `TicketPrice`
  = `Annotated[Decimal, Field(ge=0, decimal_places=2, max_digits=12)]`
  (research R1), `OccurrenceDate` = `datetime.date` (ISO wire format),
  `Description` = 1..2000 (Portuguese user content); `EventCreateRequest`
  (`spotId`, `occurrenceDate`, `description`, `ticketPrice` — all
  required), `EventUpdateRequest` (same keys, **all optional** — partial
  edit per contract §3), `EventView` (`id`, `spotId`, `occurrenceDate`,
  `description`, `ticketPrice`), `EventListResponse` (`items`); plus the
  money helpers `price_to_cents`/`cents_to_price` making T003 green
  (test→fail→implement→green)

**Checkpoint**: Foundation ready — user story implementation can now begin

---

## Phase 3: User Story 1 - Administrator manages events for tourist spots (Priority: P1) 🎯 MVP

**Goal**: Admin CRUD over events with the cross-module refusal rules
(404 nonexistent spot, 409 permanently closed spot), partial edit with
target re-validation, physical removal and exactly one audit record per
write (RNF19).

**Independent Test**: As an authenticated administrator (fixtures
`seeded_admin`, `client`): create → 201; edit → 200; delete → 204; each
write shows one `event.*` audit record; non-admin → 403; nonexistent spot
(create/edit) → 404; permanently closed spot (create/edit) → 409; unknown
eventId → 404; invalid shapes → 422.

### Tests for User Story 1 (write FIRST, verify they FAIL) ⚠️

- [X] T005 [P] [US1] Write contract tests in
  `tests/contract/test_events.py` covering per
  `specs/008-event-management/contracts/events.md` §1–§3: 201 create
  (full camelCase `EventView` body); 200 edit of every field; no-op
  empty patch = 200 with **no** audit record; 204 delete; 404 on create/
  edit with unknown `spotId` and on unknown `eventId`; 409 with
  `errorCode: "conflict"` on create/edit against a spot PATCH-ed to
  `"permanentlyClosed"` first (nothing created/altered); 403
  `authorization_failed` for anonymous/tourist/employee on POST/PATCH/
  DELETE; 422 `validation_error` for unknown/snake_case keys, negative
  price, >2dp price, malformed date, empty/oversized description; audit
  assert via the `audit_logs` fixture of `tests/conftest.py` (exactly one
  `event.create`/`event.update`/`event.delete` per successful write,
  `target = "event:{id}"`, admin username as actor). Alongside writing the
  tests, add the `Event` import to `db_engine` in `tests/conftest.py` so
  the fixture creates the table and the red run fails for the right
  reason (routes missing). Run red (routes do not exist yet)

### Implementation for User Story 1

- [X] T006 [US1] Add the cross-module read seam in
  `src/passanorte_back/modules/tourist_spots/services/tourist_spots.py`
  (research R3): public function `get_active_spot_status(session,
  spot_id) -> str` raising the existing `SpotMissingError` for unknown/
  removed spots, and re-export `STATUS_PERMANENTLY_CLOSED` at service
  level so it becomes part of the public interface — `events` consumes
  ONLY these two names (constitution rules 3/5; verified by
  `tests/smoke/test_boundaries.py`)
- [X] T007 [US1] Implement the write flows in
  `src/passanorte_back/modules/events/services/events.py` per research
  R2/R6/R7: `SpotMissingError` (re-exported/derived for route mapping) and
  new `SpotPermanentlyClosedError`; `create_event(session, actor,
  payload)` — resolve spot via T006 (404), refuse `permanentlyClosed`
  (409), persist cents via `price_to_cents`, emit `audit.record_action`
  `event.create` (target `event:{id}`, detail with `spotId` +
  `ticketPrice`); `update_event` — partial edit, when `spotId` provided
  re-validate the **new** spot (404/409) keeping prior state on refusal,
  no-op (no fields) → return unchanged with **no audit**; `remove_event`
  — physical delete + audit `event.delete`; keep the existing
  `list_public_spot_events` name untouched for US2
- [X] T008 [US1] Implement routes in
  `src/passanorte_back/modules/events/routes/events.py` on the canonical
  router `MODULE_ROUTERS["events"]` — **no tag strings here** (feature
  006): `POST ""` → 201, `PATCH "/{event_id}"` → 200, `DELETE
  "/{event_id}"` → 204, all `require_admin` (spec 002) mapping
  `SpotMissingError` → 404, `SpotPermanentlyClosedError` → 409 (detail
  "tourist spot is permanently closed" — unified `conflict`, research
  R2) and validation errors → 422, mirroring the
  `tourist_spots/routes/tourist_spots.py` handler style. Make T005 green
- [X] T009 [US1] Run `pytest tests/contract/test_events.py` plus the smoke
  gates (`pytest tests/smoke/test_boundaries.py
  tests/smoke/test_modules.py tests/contract/test_openapi_tags.py`) — all
  green, tag "Events" verified on the new OpenAPI paths

**Checkpoint**: US1 fully functional and independently testable (MVP)

---

## Phase 4: User Story 2 - Events listed for the panel and embedded in public spot details (Priority: P1)

**Goal**: Single administrative listing endpoint with optional
`spotId`/`startDate`/`endDate` filters (combined — clarification session
2026-11-02), plus the real events embedding in the public tourist spot
detail (RF27) and the cascade on spot removal.

**Independent Test**: Seed one spot with events on known dates → per-spot
listing returns exactly that spot's events; date-range listing returns
exactly the in-range events (inclusive bounds); combined filter narrows
correctly; unknown `spotId` filter → 404; `startDate > endDate` → 422; the
public spot detail embeds the events (date, description, price) and `[]`
when none; removing the spot makes its events vanish everywhere.

### Tests for User Story 2 (write FIRST, verify they FAIL) ⚠️

- [X] T010 [US2] Extend `tests/contract/test_events.py` with the listing
  contract per `contracts/events.md` §2: 200 with
  `EventListResponse` items in `(occurrenceDate, id)` order for
  `spotId`-only, range-only (`startDate`/`endDate` inclusive) and combined
  queries; empty `items` for non-matching range; 404 for unknown `spotId`
  filter; 422 `request_error` for `startDate > endDate`; 403 non-admin;
  and the public embedding per `contracts/events.md` §4: anonymous
  `GET /api/v1/tourist-spots/{id}` includes the event item shape
  (`id`/`spotId`/`occurrenceDate`/`description`/`ticketPrice`), `[]` when
  the spot has none, and spots remain readable while permanently closed
  (spec 007 visibility). Run red (listing endpoint/real seam missing)
- [X] T011 [US2] Write the integration test
  `tests/integration/test_events_lifecycle.py` per quickstart: admin
  login → create spot → create event → list by spot → list by date range
  (incl. combined filter) → patch (spot change + fields) → public detail
  embedding → delete event; then a fresh spot → event → `DELETE` the
  **spot** → assert the events no longer appear in
  `GET /api/v1/events?spotId={id}` nor in any future read (cascade,
  clarification 2026-11-02) and the audit trail holds exactly one record
  per administrative write. Run red

### Implementation for User Story 2

- [X] T012 [US2] Implement the filtered listing in
  `src/passanorte_back/modules/events/services/events.py` (service
  wrapper `list_events_admin(session, spot_id=None, start_date=None,
  end_date=None)`: unknown `spotId` → `SpotMissingError`, `startDate >
  endDate` → new `InvalidEventInputError`) and the route `GET ""` in
  `src/passanorte_back/modules/events/routes/events.py` with camelCase
  query aliases (`spotId`, `startDate`, `endDate` — `Query(alias=...)`,
  007 `pageSize` precedent), admin-only, mapping
  `InvalidEventInputError` → 422 (`request_error` semantic, research R6);
  make T010 green
- [X] T013 [US2] Implement the real public seam:
  `list_public_spot_events` in
  `src/passanorte_back/modules/events/services/events.py` queries the
  actual rows (spot_id filter) ordered `(occurrence_date, id)` and
  returns wire-shaped camelCase dicts
  (`{"id", "spotId", "occurrenceDate", "description", "ticketPrice"}` —
  cents via `cents_to_price`), replacing the `[]` stub; the
  `tourist_spots` public detail (`build_public_detail`) already embeds
  this result verbatim (007) — no other module change; make T010's
  embedding scenarios green
- [X] T014 [US2] Add the cascade in
  `src/passanorte_back/modules/tourist_spots/services/tourist_spots.py`
  `remove_spot` (research R4): call the events module's public function
  `delete_spot_events(session, spot_id)` in the same transaction before
  flush, so a soft-removed spot leaves zero event rows (no orphaned event
  ever remains); make T011 green

**Checkpoint**: US1 AND US2 both work independently

---

## Phase 5: User Story 3 - Ticket price is an explicit monetary value (Priority: P2)

**Goal**: The exact-money guarantee end-to-end: one submitted amount
round-trips identically through create response, edit response, both
listings and the public embedding (SC-005); `0` stays a free event on
every read path.

**Independent Test**: Create an event with `15.50` and another with `0` →
read every path (create response, patch response, `GET` listing, public
detail embedding) and compare the amounts — identical everywhere; no read
path ever renders a float-drifted value.

### Tests for User Story 3 (write FIRST, verify they FAIL/hold) ⚠️

- [X] T015 [US3] Write the round-trip guarantee tests in
  `tests/contract/test_events_price.py`: submit `15.50` → assert `15.50`
  (exactly, as Decimal comparison) returned by the create response, by
  `PATCH` response, by both listing shapes (`spotId` and range with
  combined filter), and in the public tourist-spot detail embedding;
  submit `0` → free event preserved verbatim everywhere; edge values
  (`0.01`, `123456.78`) round-trip; a >2dp submission is refused 422
  before persistence (nothing stored). Run red against the not-yet-
  guaranteed paths; if any path drifts (e.g. float leak), the fix belongs
  in `price_to_cents`/`cents_to_price` (T004 artifacts) — never a `Float`
  column (data-model §1: never float, R1)

**Checkpoint**: All user stories independently functional

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Quality gates affecting every story

- [X] T016 [P] Sweep for consistency: ruff lint + ruff format clean on all
  new/changed files; module docstrings in English referencing the spec/
  research decisions (constitution VII); README section for the events
  endpoints only if the README already documents per-module endpoints;
  Portuguese user content only inside data/description values
- [X] T017 Run the full validation from `specs/008-event-management/
  quickstart.md`: complete pytest suite (contract sweeps
  `test_camelcase_contract.py`/`test_strict_input.py`/
  `test_unified_error.py` must absorb the new module unchanged, tags
  registry 1:1, boundary AST scan) and `pytest tests/test_migrations.py`;
  optionally the manual probe of quickstart §Manual probe against the dev
  app

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: empty — nothing to do, start anywhere
- **Foundational (Phase 2)**: T001/T002/T003 parallel; T004 depends on
  T003 (tests red first) — BLOCKS all user stories
- **US1 (Phase 3)**: T005 parallel-safe (test file); T006 → T007 → T008 →
  T009 sequential (seam, flows, routes, gate)
- **US2 (Phase 4)**: T010/T011 first (red); T012+T013 green T010; T014
  green T011 — depends on Phase 3 (routes/services exist)
- **US3 (Phase 5)**: T015 depends on Phases 2–4 (all read paths exist);
  implementation fixes, if red, go to T004 helpers
- **Polish (Phase 6)**: after all stories

### User Story Dependencies

- **US1 (P1)**: starts after Foundational only — no other story needed
- **US2 (P1)**: builds on US1's service/routes files (same module
  surface); independently testable once Phases 2–3 are done
- **US3 (P2)**: verification story over US1+US2 read paths — naturally
  last among stories, independently valuable as the RF39 guarantee

### Within Each User Story

- Tests MUST fail before their implementation task
- Seam/validation before flows, flows before routes
- Story complete (checkpoint) before the next priority

### Parallel Opportunities

- T001 + T002 + T003 (different files, pure additions)
- T005 (contract test file) alongside T006 (service file)
- T010 + T011 (different test files) once Phase 3 is green
- T016 alongside any final wait

---

## Parallel Example: Foundational + US1

```bash
# Phase 2 start (parallel):
Task T001: "Create Alembic migration migrations/versions/20261102_0005_events.py"
Task T002: "Create Event model + data access in
src/passanorte_back/modules/events/repositories/events.py"
Task T003: "Write failing unit tests in tests/unit/test_events_price.py"
# Then T004, then (parallel):
Task T005: "Write contract tests in tests/contract/test_events.py"
Task T006: "Add get_active_spot_status seam in
src/passanorte_back/modules/tourist_spots/services/tourist_spots.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 2 (Foundational) — migration, model, DTOs, money helpers
2. Phase 3 (US1) — CRUD + refusals + audit
3. **STOP and VALIDATE**: `pytest tests/contract/test_events.py` + smoke
   gates green → events are creatable, editable, removable under RBAC
   with the 404/409 rules (MVP)

### Incremental Delivery

1. MVP (US1) → validate → US2 (listings + embedding + cascade: the
   feature becomes end-consumer-visible in the Passaporte detail) →
   US3 (the RF39 money guarantee locked by tests) → Polish

### Parallel Team Strategy

- Solo sequential execution in ID order is sufficient (small module);
  with capacity, split Foundational vs US1 test authoring

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Verify tests fail before implementing (constitution III)
- Commit after each task or logical group
- Avoid: snake_case JSON keys anywhere (strict border), tag strings in
  route files, float for money, cross-module imports beyond the two
  public seams (R3/R4/R8)
---

## Phase 7: Convergence

**Purpose**: Residual work found by assessing the implemented code against
spec.md, plan.md, tasks.md and the constitution (2026-11-02)

- [X] T018 Add an "Eventos (feature 008-event-management)" README section
  mirroring the existing "Pontos turísticos (feature 007)" structure:
  module, prefix `/api/v1/events`, the 4 admin endpoints with their
  refusal statuses, the public embedding in the spot detail, and the link
  to [specs/008-event-management/contracts/events.md] (partial) per T016
- [X] T019 Remove the unused public helper `get_event` from
  `src/passanorte_back/modules/events/repositories/events.py`
  (services use `find_event_by_id` — keep only that one) and re-run the
  events suites green (unrequested) per Constitution V (YAGNI)
