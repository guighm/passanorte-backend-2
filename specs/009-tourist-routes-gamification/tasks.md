# Tasks: Tourist Routes and Gamification (feature 009)

**Input**: Design documents from `/specs/009-tourist-routes-gamification/`

**Prerequisites**: plan.md (required), spec.md (required for user stories),
research.md, data-model.md, contracts/, quickstart.md

**Tests**: included — constitution III (Test-First, NON-NEGOTIABLE) mandates
test→fail→implement→green, and the spec's acceptance gate IS the full
journey (SC-007) plus the stock-race/insufficient-stock blocking test. Every
story phase starts with failing tests.

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

**Purpose**: Nothing required — the `gamification` module skeleton already
exists (canonical entry in `core/modules.py`, mounted empty
`MODULE_ROUTERS["gamification"]` router with prefix `/api/v1/gamification`,
tag "Gamification" in `core/tags.py` + applied in `core/routers.py`). No new
configuration data or dependency (R5: code generation via stdlib `secrets`).

- No tasks.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Migration, persistence, DTOs, domain exceptions and the
code-generation primitive — blocking prerequisites for ALL user stories

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T001 [P] Write failing unit tests FIRST in
  `tests/unit/test_gamification_codes.py` (research R5/R10): code
  generation exposes `new_redemption_code() -> str` with — 32-char
  URL-safe alphabet (`secrets.token_urlsafe(16)`, 128-bit entropy,
  assertion via alphabet + length), uniqueness across a 1 000-code batch,
  no structural derivability from any counter/identifier (two consecutive
  codes share no prefix relationship; codes for the same tourist-route pair
  differ across simulated re-issues), and no expiration marker in the
  value. Run `pytest tests/unit/test_gamification_codes.py` red before T005
  (import fails — the function does not exist yet). Isolated from app
  machinery (pure unit test)
- [X] T002 [P] Create Alembic migration
  `migrations/versions/20261102_0006_gamification.py` creating exactly the
  7 tables of `specs/009-tourist-routes-gamification/data-model.md` §1:
  `tourist_routes` (`id` PK; `name` String(200) 1..200 Portuguese content;
  `description` String(2000) 1..2000; `prize_id` FK → `prizes.id` NOT
  NULL; `created_at`/`updated_at` datetime UTC (007 precedent);
  `removed_at` datetime null = archive soft delete; partial UNIQUE INDEX
  `prize_id` `WHERE removed_at IS NULL` — Q1: prize linkable to at most one
  route at a time), `route_spots` (`id` PK; `route_id` FK →
  `tourist_routes.id` `ondelete="CASCADE"`; `tourist_spot_id` FK →
  `tourist_spots.id`; `display_order` int ≥ 1 display-only — Q2;
  `UNIQUE (route_id, tourist_spot_id)`), `prizes` (`id` PK; `name`
  String(200) 1..200; `stock_quantity` Integer NOT NULL ≥ 0 (never
  negative — guard in SQL, R4); `reserved_quantity` Integer NOT NULL
  default 0 ≥ 0; timestamps), `route_enrollments` (`id` PK; `route_id` FK;
  `tourist_id` FK → `tourists.id` (read-only reference, R3); `status`
  String `in_progress`|`completed` NOT NULL; `completed_at` datetime null;
  `created_at` timestamp; `UNIQUE (route_id, tourist_id)` — FR-005/
  SC-006), `spot_visits` (`id` PK; `tourist_id` FK; `tourist_spot_id` FK;
  `visited_at` datetime UTC; `UNIQUE (tourist_id, tourist_spot_id)` —
  idempotent per pair; index on `tourist_id` for the progress join;
  owned by gamification for this feature — research R1), 
  `completion_badges` (`id` PK; `route_id` FK; `tourist_id` FK;
  `granted_at` datetime UTC; `UNIQUE (route_id, tourist_id)` — RF35), 
  `redemption_codes` (`id` PK; `code` String UNIQUE indexed (128-bit
  CSPRNG value, never expiring — Q4 + R5); `route_id`, `tourist_id`,
  `prize_id` FKs; `status` String `unused`|`used` NOT NULL;
  `created_at`, `used_at` null, `pickup_spot_id` FK →
  `tourist_spots.id` null until concession, `conceded_by` String null
  until concession (Q3); `UNIQUE (route_id, tourist_id)` — SC-003).
  Foreign keys to `tourists`/`tourist_spots` are read-only references —
  no cross-domain table sharing (constitution rule 4). Verify with
  `pytest tests/test_migrations.py` (upgrade head applies 0006 down
  cleanly)
- [X] T003 [P] Create the 7 SQLAlchemy models + data access in
  `src/passanorte_back/modules/gamification/repositories/gamification.py`
  per data-model §1 with the exact column set of T002 (models:
  `TouristRoute`, `RouteSpot`, `Prize`, `RouteEnrollment`, `SpotVisit`,
  `CompletionBadge`, `RedemptionCode`); data access functions: routes
  (`add_route_with_prize_and_spots`, `find_route_by_id`,
  `list_routes(include_archived: bool)` ordered `(name, id)`,
  `replace_route_spots`, `archive_route`, `count_route_spots`),
  prizes (`create_prize`, `find_prize_by_id`, `adjust_stock`),
  enrollments (`add_enrollment`, `find_enrollment` (by pair and by id),
  `list_enrollments_of_tourist` ordered `created_at DESC`),
  visits (`record_visit` idempotent INSERT-or-lookup per pair),
  badges (`grant_badge` idempotent lookup-first), codes (`add_code`,
  `find_code_by_value`), plus the two atomic guards as raw conditional
  UPDATEs (research R4): `try_reserve_prize(session, prize_id)` —
  `UPDATE prizes SET reserved_quantity = reserved_quantity + 1
  WHERE id = :id AND stock_quantity - reserved_quantity >= 1` returning
  rowcount; `try_consume_stock(session, prize_id)` —
  `UPDATE prizes SET stock_quantity = stock_quantity - 1,
  reserved_quantity = max(reserved_quantity - 1, 0) WHERE id = :id
  AND stock_quantity >= 1` returning rowcount. No business rules here —
  services own every rule
- [X] T004 Create the DTOs in
  `src/passanorte_back/modules/gamification/schemas/gamification.py` per
  `specs/009-tourist-routes-gamification/contracts/gamification.md` §1–§4,
  all inheriting `core.schemas.ApiModel` (camelCase JSON, strict border):
  `RouteSpotItemInput` (`spotId` ≥ 1, `displayOrder` ≥ 1),
  `RoutePrizeInput` (`name` 1..200, `initialStock` int ≥ 0),
  `RouteCreateRequest` (`name` 1..200, `description` 1..2000 both
  Portuguese content, `spots` min 1 item, `prize` required — empty spots
  list → 422, US1-5), `RouteUpdateRequest` (all keys optional; a provided
  `spots` is fully re-validated), `RoutePrizeView` (`id`, `name`,
  `stockQuantity`), `TouristRouteView` (`id`, `name`, `description`,
  `spots`, `prize`, `status` value `active`|`archived`),
  `RouteListResponse` (`items`, no pagination this version — YAGNI/008
  precedent), `EnrollmentSummaryView` (`id`, `routeId`, `status`,
  `completionRate` int 0..100, `createdAt`, `completedAt` null),
  `EnrollmentProgressView` (summary + `spots` list of
  `{spotId, visited}`, `visitedCount`, `totalSpots`; `badge`
  (`{routeId, grantedAt}`) and `redemptionCode` (`{code, status}`) present
  only when completed — contract §2),
  `PrizeStockUpdateRequest` (`stockQuantity` int ≥ 0),
  `RedemptionCreateRequest` (`code` 1..128, `spotId` ≥ 1),
  `RedemptionView` (`code`, `prize` `{id,name}`, `routeId`, `touristId`,
  `pickupSpotId`, `concededBy`, `usedAt`). `completionRate` is the
  integer floor percentage — research R8
- [X] T005 Create the domain-exception + code-generation primitive in
  `src/passanorte_back/modules/gamification/services/gamification.py`:
  exceptions `RouteMissingError`, `InvalidRouteInputError`,
  `TouristSpotMissingError` (single name for "spot not found" — mapped
  → 404 wherever the spot is part of a route payload or a pickup,
  contracts §1/§4; never 422 — análise F3),
  `EnrollmentConflictError`, `EnrollmentMissingError`,
  `PrizeStockInsufficientError`, `CodeAlreadyUsedError`,
  `PrizeMissingError`, `CodeMissingError`
  (all route-mapped per contracts §6); `new_redemption_code()` with
  retry-on-collision against a uniqueness check (research R5) making T001
  green. Keep the file structured for the story flows that follow (T007,
  T011, T016, T020) — do not implement flows yet

**Checkpoint**: Foundation ready — user story implementation can now begin

---

## Phase 3: User Story 1 - Administrator manages tourist routes with a completion prize (Priority: P1) 🎯 MVP

**Goal**: Admin CRUD over tourist routes with an embedded prize creation
(validated spots via the `tourist_spots` public seam), archive removal
preserving the enrollments' history, administrative listing with optional
archive exposure, and exactly one audit record per write (RNF19).

**Independent Test**: As an authenticated administrator (fixtures
`seeded_admin`, `client`): create route + prize → 201 ordering preserved;
edit → 200; archive → 204 with enrollments/progress intact; non-admin →
403; unknown/empty/removed spot → 404; missing route → 404; invalid shapes
→ 422; one `route.*` audit record per write.

### Tests for User Story 1 (write FIRST, verify they FAIL) ⚠️

- [X] T006 [P] [US1] Write the route-management contract tests in
  `tests/contract/test_gamification.py` per
  `contracts/gamification.md` §1: 201 create with full camelCase
  `TouristRouteView` body (spots order preserved from the payload); 200
  edit of every field incl. full spots-list re-validation; 204 archive;
  403 `authorization_failed` for anonymous/tourist/employee on POST/PATCH/
  DELETE; 404 `resource_not_found` on unknown `spotId` in create/edit (one
  spot PATCH-ed to removed first via `DELETE /api/v1/tourist-spots/{id}` —
  007 flow) and on unknown/already-archived `routeId`; 422
  `validation_error` for empty spots list, negative `initialStock`,
  unknown/snake_case keys, oversized names/description; 200 `GET /routes`
  excludes archived routes, `?includeArchived=true` (admin) includes them
  (Removal Decision), tourist GET sees only active ones; 200
  `GET /routes/{id}` (admin: any state; tourist: 404 on archived).
  Alongside, add the 7 gamification model imports to the `db_engine`
  fixture in `tests/conftest.py` so tables exist and the red run fails for
  the right reason (routes missing). Run red
- [X] T007 [US1] Implement the route-management flows in
  `src/passanorte_back/modules/gamification/services/gamification.py`
  (research R3/R7): `create_route(session, actor, payload)` — validate
  every `spotId` through the `tourist_spots` public seam
  `get_active_spot` (unknown/removed → `RouteMissingError` for 404),
  create the prize entity + route + ordered spots (display positions from
  the payload), persist with `added` repo functions, ONE
  `audit.record_action` `route.create` (target `route:{id}`, detail with
  `spotCount` + prize id); `update_route` — partial edit, provided spots
  list fully re-validated (empty → `InvalidRouteInputError` → 422),
  name/description replace (the prize is bound at creation and NOT
  rebindable — análise F1), no-op → return unchanged with **no**
  audit (007 precedent), 1 audit `route.update` on change;
  `archive_route` — set `removed_at` (FR-012: enrollments/badges/codes
  untouched), 1 audit `route.delete`; listings
  (`list_routes_active`, `list_routes_admin(include_archived)`) and
  `get_route_for_admin` raising `RouteMissingError` for
  unknown/archived-per-actor rules
- [X] T008 [US1] Implement routes in
  `src/passanorte_back/modules/gamification/routes/gamification.py` on the
  canonical router `MODULE_ROUTERS["gamification"]` — **no tag strings
  here** (feature 006): `POST ""` → 201, `PATCH "/routes/{route_id}"` →
  200, `DELETE "/routes/{route_id}"` → 204, `GET ""` (tourists included:
  `get_current_user`; admin-only `includeArchived` query — camelCase
  `Query(alias="includeArchived")` — 008 precedent), `GET
  "/routes/{route_id}"` — admin paths gated `require_admin`, tourist
  visibility per T006 contracts; map `RouteMissingError` → 404,
  `InvalidRouteInputError` → 422 (mirroring
  `events/routes/events.py` handler style). Make T006 green
- [X] T009 [US1] Run `pytest tests/contract/test_gamification.py` plus the
  smoke gates (`pytest tests/smoke/test_boundaries.py
  tests/smoke/test_modules.py tests/contract/test_openapi_tags.py`) — all
  green, tag "Gamification" on the new OpenAPI paths, audit assertions
  holding

**Checkpoint**: US1 fully functional and independently testable (MVP)

---

## Phase 4: User Story 2 - Tourist enrolls in a route and tracks progress (Priority: P1)

**Goal**: Tourist enrollment (duplicates → 409), progress derivation
(visited/pending spots + integer completion rate) for own enrollments
only, and the public domain seam `register_spot_visit` propagating a
single visit to ALL in-progress enrollments containing the spot (RF34).

**Independent Test**: Seed spots + an active route (US1 endpoint) → as a
tourist: enroll → 201 (in_progress, 0 %); duplicate enrollment → 409 with
the original intact; `GET /enrollments` / `GET /enrollments/{id}` show
pending spots; call `register_spot_visit` — visits of spots in two
enrolled routes advance both in one call; re-registration of the same
visit is a no-op; visits to spots outside the tourist's routes change
nothing.

### Tests for User Story 2 (write FIRST, verify they FAIL) ⚠️

- [X] T010 [P] [US2] Extend `tests/contract/test_gamification.py` with the
  enrollment/progress contract per `contracts/gamification.md` §2: 201
  enrollment with `EnrollmentSummaryView` (`status` `"inProgress"`,
  `completionRate` 0 — wire enum rendering per data-model §4); 409
  `conflict` on duplicate enrollment (original unchanged); 404 for
  archived/unknown route enrollment; 403 `authorization_failed` for
  admin/employee on `POST /routes/{id}/enrollments`; 200 `GET
  /enrollments` listing only the caller's own enrollments ordered
  `createdAt` desc with summaries; 200 `GET /enrollments/{id}` full
  progress (spots with `visited` flags, `visitedCount`, `totalSpots`,
  `completionRate` recomputed, no badge/code keys while in-progress); 404
  for another tourist's enrollment (indistinguishable from unknown —
  FR-013). Run red (enrollment endpoints missing)
- [X] T011 [P] [US2] Write the propagation integration test in
  `tests/integration/test_gamification_visit.py` per research R12: admin
  creates 2 overlapping routes (shared spot X) → tourist enrolls in both
  → direct call `register_spot_visit(session, tourist_id=…,
  tourist_spot_id=X)` in one session updates BOTH enrollments (return
  value: one `VisitRouteOutcome` per route with `route_id`,
  `completion_rate`, `completed` — Q5); unknown tourist/spot → domain
  exception (not-found mapping); visit of a spot outside both routes →
  empty outcome list, no state change; idempotent re-call → same outcome,
  exactly one `spot_visits` row (UNIQUE pair). Run red (seam missing)
- [X] T012 [US2] Implement enrollment + progress + the public seam in
  `src/passanorte_back/modules/gamification/services/gamification.py`
  (research R1/R3/R12): `enroll_tourist(session, tourist_id, route_id)` —
  route active via US1 reads (404 archived/unknown), tourist active via
  `tourists.services.get_tourist_account` (404), IntegrityError on
  `UNIQUE (route_id, tourist_id)` → `EnrollmentConflictError` (409);
  `get_enrollment_progress(session, tourist_id, enrollment_id)` — derived
  join `route_spots` (display order) × `spot_visits`, integer floor
  `completion_rate` (R8), `EnrollmentMissingError` for unknown/foreign
  enrollment; `list_tourist_enrollments`; 
  `register_spot_visit(session, *, tourist_id, tourist_spot_id)` —
  validate tourist (tourists seam → `TouristMissingError`) and spot
  (`tourist_spots` public seam → `TouristSpotMissingError`), 
  `record_visit` idempotent, single call recalculates EVERY
  `in_progress` enrollment of routes containing the spot and returns
  `list[VisitRouteOutcome]` per affected route; re-export the seam in
  `src/passanorte_back/modules/gamification/services/__init__.py`
  (precedente `events.services`); make T010's progress paths and T011
  (propagation) green — route completion and reward issuance are
  implemented in Phase 5 (T017): until then the outcome's `completed`
  flag stays False for last-pending visits (assert accordingly)
- [X] T013 [US2] Implement routes in
  `src/passanorte_back/modules/gamification/routes/gamification.py`:
  `POST "/routes/{route_id}/enrollments"` → 201 (`require_tourist` —
  R6/FR-013), `GET "/enrollments"` → 200, `GET "/enrollments/{enrollment_id}"`
  → 200 — all tourist-scoped via `require_tourist` + `user.account_id`
  as `tourist_id`; map `EnrollmentConflictError` → 409,
  `RouteMissingError`/`EnrollmentMissingError`/`TouristMissingError` →
  404. Make T010 green (T011 stays green)
- [X] T014 [US2] Run `pytest tests/contract/test_gamification.py
  tests/integration/test_gamification_visit.py` plus the smoke gates — 
  green across the board

**Checkpoint**: US1 AND US2 both work independently

---

## Phase 5: User Story 3 - Route completion grants a badge and a single-use redemption code (Priority: P1)

**Goal**: Automatic, exactly-once completion on the last pending visit:
insignia granted (RF35) and unique unguessable code issued (RF36) in the
same transaction as the completion, idempotent under repetition and
concurrency, visible through the tourist's progress payload.

**Independent Test**: Complete a route (US2 flows) → badge + code present
in `GET /enrollments/{id}`, exactly once; repeat the last visit →
identical outcome, still exactly one badge/one code row.

### Tests for User Story 3 (write FIRST, verify they FAIL) ⚠️

- [X] T015 [P] [US3] Extend `tests/contract/test_gamification.py` with the
  completed-progress contract per `contracts/gamification.md` §2: after
  the last visit, `GET /enrollments/{id}` carries `status`
  `"completed"`, `completionRate` 100, the `badge` object
  (`routeId`, `grantedAt`) and the `redemptionCode` object (`code`,
  `status` `"unused"`); the code is stable across repeated reads and never
  appears in another tourist's payload (FR-013). Run red
- [X] T016 [P] [US3] Write the completion-idempotency integration test in
  `tests/integration/test_gamification_visit.py` (extend T011 file):
  complete a route via `register_spot_visit` for the last pending spot →
  exactly one `completion_badges` row and one `redemption_codes` row for
  the tourist-route pair, enrollment `completed` with `completed_at`;
  re-visit of the last spot and a repeated completion attempt → still
  exactly one of each (idempotent — SC-003), outcome `completed` True
  without duplicate issuance; the code issued is unique across the whole
  table (SC-004) and the outcome payload reports it via the seam return
  (Q5). Run red (completion flow missing)

### Implementation for User Story 3

- [X] T017 [US3] Implement the completion + rewards flow in
  `src/passanorte_back/modules/gamification/services/gamification.py`
  (research R2/R4/R5) inside `register_spot_visit`'s per-enrollment
  processing: on the last pending spot — conditional enrollment UPDATE
  `WHERE status = 'in_progress'` (rowcount 0 → already completed, emit
  nothing — the race-safe guard); the winner of the conditional update
  grants the badge (`grant_badge` idempotent), generates the code via T005's
  `new_redemption_code` (collision retry — R5) and persists it
  (`add_code`), then `try_reserve_prize` (R4 guard — no stock: completion
  still succeeds, reservation simply not held — FR-004 clarified, F9); all
  in the SAME transaction/flush as the visit (single seam call — R12);
  update `VisitRouteOutcome` to carry the completed flag (and route_id/
  completion_rate) so T011/T016 run green; make T015 green
- [X] T018 [US3] Run `pytest tests/contract/test_gamification.py
  tests/integration/test_gamification_visit.py tests/unit/
  test_gamification_codes.py` plus smoke gates — green

**Checkpoint**: US1, US2 AND US3 all work independently

---

## Phase 6: User Story 4 - Prize stock control and concession against an idempotent reservation (Priority: P2)

**Goal**: Staff-authorized concession of the physical prize against a
single-use code (Q3: employee or admin, pickup spot recorded), stock
guard never going negative, insufficient stock blocking the concession
without altering state (code stays valid), and the full acceptance
journey (SC-007) green end-to-end.

**Independent Test**: Completed route with a known code → concession by
employee (and by admin) → 201, stock −1, code `used`, pickup recorded;
second concession attempt → 409; with stock 0 → 409 and code stays
`unused`; two tourists racing for the last unit of the same route's
prize → exactly one holds the reservation.

### Tests for User Story 4 (write FIRST, verify they FAIL) ⚠️

- [X] T019 [P] [US4] Extend `tests/contract/test_gamification.py` with the
  prize-stock + concession contract per `contracts/gamification.md` §3–§4
  and add a `require_staff` scenario matrix: 200
  `PATCH /prizes/{id}` (`stockQuantity` ≥ 0) by admin; 403 non-admin;
  404 unknown prize; 422 negative stock and stock below
  `reserved_quantity` (edge case: adjustment below committed reservations);
  201 concession by employee (`seeded_employee` fixture) and by admin;
  401 `authentication_failed` for anonymous and 403 for an
  authenticated tourist (non-staff) on concession; 409 `conflict` for already-used code (no
  state change regardless of available stock); 409 for the
  insufficient-stock concession attempt (code remains unused/valid and
  prize stock untouched); 404 for unknown code and unknown `spotId`
  (nothing registered); 422 shape failures. Run red (endpoints/gate
  missing)
- [X] T020 [P] [US4] Add the `require_staff` gate in
  `src/passanorte_back/modules/auth/services/security.py` (research R6):
  FastAPI dependency accepting `account_type` in `("admin", "employee")`
  with an active account (state reload already guaranteed by
  `get_current_user`), raising 403 `authorization_failed` otherwise —
  documented as the concession gate (RF36/Q3); export it in the module's
  `__all__`; verified by T019's 403 matrix; make the gate tests green
- [X] T021 [US4] Write the acceptance-journey + stock-race integration
  test in `tests/integration/test_gamification_lifecycle.py` per
  quickstart (SC-007): admin login → create 2 spots → create route
  (prize stock 1) → tourista login → enroll (duplicate → 409) →
  visit every spot via the seam → enrollment completed with badge + code
  → `POST /api/v1/gamification/redemptions` with the code + pickup spot →
  201 (stock 0 after) → second concession attempt with the same code →
  409 `conflict`; then: a fresh tourist completes the same route but with
  prize stock 0 at completion → code issued but reservation not held →
  concession attempt → 409 (insufficient stock, code remains valid) →
  admin raises stock → concession now succeeds (consuming the direct
  unit); two tourists racing for the last single unit → exactly one holds
  a reservation (second ends without concession rights — data-model §2,
  R4); route archive preserves the enrolled tourist's progress, badge and
  code readable (Removal Decision). Run red (concession missing)

### Implementation for User Story 4

- [X] T022 [US4] Implement the stock + concession flows in
  `src/passanorte_back/modules/gamification/services/gamification.py`
  (research R4): `adjust_prize_stock(session, actor, prize_id,
  stock_quantity)` — negative or below `reserved_quantity` →
  `InvalidRouteInputError` (422), unknown prize → `PrizeMissingError`,
  1 audit `prize.stock_update`; `concede_prize(session, actor, code,
  spot_id)` — unknown code → `CodeMissingError` (404), already-used →
  `CodeAlreadyUsedError` (409), code status flipped `unused → used` via
  conditional update in the same guard as stock (R4: single transaction —
  `try_consume_stock` rowcount 0 → `PrizeStockInsufficientError` (409,
  code untouched), pickup spot validated through the `tourist_spots`
  public seam (`TouristSpotMissingError` → 404 — single name, F3),
  `pickup_spot_id` +
  `conceded_by` + `used_at` recorded, 1 audit `prize.concede`; make T019
  green
- [X] T023 [US4] Implement routes in
  `src/passanorte_back/modules/gamification/routes/gamification.py`:
  `PATCH "/prizes/{prize_id}"` → 200 (`require_admin`), `POST
  "/redemptions"` → 201 (`require_staff` — T020); error mapping per
  contracts §6 (`CodeAlreadyUsedError`/`PrizeStockInsufficientError` →
  409, `CodeMissingError`/`TouristSpotMissingError`/`PrizeMissingError` →
  404, shape → 422); make T021's full journey green (SC-007 achieved)

**Checkpoint**: ALL user stories independently functional — acceptance
journey green

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Quality gates affecting every story

- [X] T024 [P] Sweep for consistency: `ruff check` + `ruff format` clean on
  all new/changed files; module docstrings in English referencing the
  spec/research decisions (constitution VII); README section for the
  gamification endpoints mirroring the events section structure (only if
  the README already documents per-module endpoints); Portuguese user
  content only inside data/name/description values
- [X] T025 Run the full validation from
  `specs/009-tourist-routes-gamification/quickstart.md`: complete pytest
  suite (contract sweeps `test_camelcase_contract.py`/`test_strict_input.
  py`/`test_unified_error.py` must absorb the new module unchanged, tags
  registry 1:1, boundary AST scan) and `pytest tests/test_migrations.py`;
  optionally the manual smoke of quickstart §Manual smoke

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: empty — nothing to do, start anywhere
- **Foundational (Phase 2)**: T001 + T002 + T003 parallel; T004 and T005
  after T003/T001 respectively — BLOCKS all user stories
- **US1 (Phase 3)**: T006 (contract tests + conftest registration) →
  T007 → T008 → T009
- **US2 (Phase 4)**: T010 + T011 (both red) → T012 → T013 → T014;
  depends on Phase 3 (routes/gamification.py exists, reading routes)
- **US3 (Phase 5)**: T015 + T016 (red) → T017 → T018; depends on Phase 4
  (progress flows + seam exist)
- **US4 (Phase 6)**: T019 + T020 (parallel; red) + T021 (red) → T022 →
  T023; depends on Phases 2–5 (completion must exist before concession)
- **Polish (Phase 7)**: after all stories

### User Story Dependencies

- **US1 (P1)**: starts after Foundational only — no other story needed
- **US2 (P1)**: builds on US1 (routes exist to enroll into); 
  independently testable once Phases 2–3 are done
- **US3 (P1)**: builds on US2 (the completion lives inside
  `register_spot_visit`'s processing); independently testable as the
  badge/code emission on top of progress
- **US4 (P2)**: builds on US3 (a concession needs an issued code); the
  stock guards are foundational-owned (T003) but their HTTP/flows are here;
  the acceptance journey (SC-007) closes only after US4

### Within Each User Story

- Tests MUST fail before their implementation task
- Services before routes; the seam re-export after flows
- Story complete (checkpoint) before the next priority

### Parallel Opportunities

- T001 + T002 + T003 (different files, pure additions)
- T004 + T005 after their prerequisites land (T004 ← T003; T005 ← T001)
- T006 (contract test file) alongside T007 (service file) — different
  files
- T010 + T011; T015 + T016; T019 + T020 + T021 (test files and the auth
  gate) — each pair/trio touches disjoint files
- T024 alongside any final wait

---

## Parallel Example: Foundational + US1

```bash
# Phase 2 start (parallel):
Task T001: "Failing unit tests in tests/unit/test_gamification_codes.py"
Task T002: "Alembic migration migrations/versions/20261102_0006_gamification.py"
Task T003: "Models + data access in
src/passanorte_back/modules/gamification/repositories/gamification.py"
# Then T004 + T005, then:
Task T006: "Contract tests in tests/contract/test_gamification.py (+ conftest tables)"
# Then T007 → T008 → T009
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 2 (Foundational) — migration, models, DTOs, exceptions + code
   primitive
2. Phase 3 (US1) — route CRUD + archive + prize creation + audit
3. **STOP and VALIDATE**: `pytest tests/contract/test_gamification.py` +
   smoke gates green → routes are manageable under RBAC with 403/404/422
   rules (MVP)

### Incremental Delivery

1. MVP (US1) → validate → US2 (enrollment + derived progress + the RF34
   seam the visitation spec will consume) → US3 (badge + single-use code —
   the gamified payoff) → US4 (stock discipline + staff concession + the
   full SC-007 journey) → Polish

### Parallel Team Strategy

- Solo sequential execution in ID order is sufficient (single module);
  with capacity, split Foundational vs US1 test authoring, and later
  US4's test authoring (T019/T021) against the US3 checkpoint

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Verify tests fail before implementing (constitution III)
- Commit after each task or logical group
- Avoid: snake_case JSON keys anywhere (strict border), tag strings in
  route files, business rules in repositories (services own every rule),
  cross-module imports beyond the two public seams
  (`tourists.services.get_tourist_account`, `tourist_spots` public
  service) and the `auth` gate (R3/R6), float/derived-progress storage
  (R1/R8), and any state change on a refused concession (R4)
---

## Phase 8: Convergence

**Purpose**: Residual work found by assessing the implemented code against
spec.md, plan.md, tasks.md and the constitution (2026-11-02)

- [X] T026 [HIGH] Re-evaluate in-progress enrollments when the route's
  spots list shrinks (per spec.md Edge Cases 1 — *missing*: `update_route`
  in `src/passanorte_back/modules/gamification/services/gamification.py`
  only replaces entries without rechecking completions,
  tests/integration/test_gamification_lifecycle.py has no scenario) —
  after `replace_route_spots`, for every `in_progress` enrollment of the
  route whose remaining spots are all already visited: complete it exactly
  once with the reward flow (badge + unique code + reservation attempt)
  through the same conditional-update guard (`mark_enrollment_completed`
  rowcount 1 = issuer; zero = already done), one audit for the route edit
  only (no per-completion audit); write the integration scenario FIRST
  (red) in `tests/integration/test_gamification_lifecycle.py`: enroll →
  visit spot A of a 2-spot route → admin edits the route down to just
  spot A → enrollment ends `completed` with exactly one badge + one code;
  and the inverse: adding a spot keeps `in_progress` enrollments valid
  with the new pending spot (edge case 2a). (partial)
- [X] T027 [MEDIUM] Keep completed enrollments' progress stable when the
  route gains spots later (per spec.md Edge Cases 2 — *partial*:
  `get_enrollment_progress_view` in
  `src/passanorte_back/modules/gamification/services/gamification.py`
  recomputes `completionRate` from live spots, so a later-added spot drags
  a completed enrollment below 100 and lists it pending) — completed
  enrollments report `completionRate` 100 unconditionally (the completion
  invariant) and never regress below it; earned rewards (badge + code)
  remain untouched; write the contract-scenario test FIRST (red) in
  `tests/contract/test_gamification.py`: complete an enrollment → admin
  adds a spot to the route → progress read still `completionRate` 100,
  `status` `completed`, badge/code intact. (partial)
