---
description: Task list for feature implementation
---

# Tasks: Dashboard e Insights (014-dashboard-insights)

**Input**: Design documents from `/specs/014-dashboard-insights/`

**Prerequisites**: plan.md (required), spec.md (required for user stories),
research.md, data-model.md, contracts/

**Tests**: REQUIRED — the constitution (section III, NON-NEGOTIABLE) mandates
test-first: every task group writes failing tests before implementation.

**Organization**: grouped by user story (US1 heatMap, US2 accessCounts,
US3 spotRanking, US4 visitorCountries, US5 visitorInterests).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to
- Include exact file paths in descriptions

## Path Conventions

Modular monolith (repository root): code in `src/passanorte_back/`,
migrations in `migrations/versions/`, tests in `tests/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm the existing scaffold; no new project initialization needed
(the `dashboard` module skeleton, `DOMAIN_MODULES` entry, `Dashboard` tag and
`/api/v1/dashboard` mounting already exist).

- [x] T001 Verify the dashboard module scaffold is wired end to end: `DOMAIN_MODULES` contains `dashboard` (`src/passanorte_back/core/modules.py`), `MODULE_ROUTERS` mounts `modules.dashboard.routes` with tag `Dashboard` (`src/passanorte_back/core/routers.py`), tag registered in `src/passanorte_back/core/tags.py`; scaffold has empty `routes/`, `services/`, `repositories/`, `schemas/` packages — record findings, change nothing unless missing.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: `access_events` table, read projections and time-window math —
blocked prerequisites for every metric story.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Tests (write first, watch them fail)

- [x] T002 [P] Write failing migration test in `tests/test_migrations.py`: upgrading to head creates `access_events` with columns `id`, `tourist_id` (FK `tourists.id`), `occurred_at`, `day`; indexes `ix_access_events_at`, `ix_access_events_day`, `ix_access_events_tourist_day` (`tourist_id`, `day`); downgrade drops the table (research R8, data-model.md §1)
- [x] T003 [P] Write failing unit tests for window/granularity math in `tests/unit/test_dashboard_windows.py`: `today` anchor at city tz midnight→now, `week` Monday→Sunday in city tz, `month` calendar month, custom inclusive range, ranking windows for `granularity=day|month|year` from `referenceDate`, limit clamps/422 bounds 1–100 — using `ZoneInfo(city_timezone)` config, never hardcoded tz (research R4)

### Implementation

- [x] T004 [P] Create migration `migrations/versions/20261106_0009_access_events.py`: create `access_events` table + the three indexes of T002; downgrade drops them (make T002 pass)
- [x] T005 [P] Create `AccessEvent` ORM model + repository in `src/passanorte_back/modules/dashboard/repositories/access_events.py`: `add_access_event(session, *, tourist_id, occurred_at)` with `day` computed via `ZoneInfo(settings.city_timezone)` at write time; aggregate helpers `count_unique_tourist_days(session, start_day, end_day)`, `count_events(session, start_day, end_day)`, `daily_series(session, start_day, end_day)`, each a set-based SQL aggregate (no Python loops — FR-020); insert-only, no update/delete paths
- [x] T006 [P] Create read-only projections in `src/passanorte_back/modules/dashboard/repositories/read_projections.py`: non-registered `sa.table()` constructs `visitations_v`, `tourist_spots_v`, `tourists_v`, `tourist_interests_v` mirroring only the columns listed in data-model.md §2 (no sensitive columns ever projected); zero imports from other modules (boundary gate)
- [x] T007 Create window/period service module in `src/passanorte_back/modules/dashboard/services/metrics.py`: `resolve_period_window(period, start_date, end_date, today)`, `resolve_ranking_window(granularity, reference_date, today)`, `validate_limit(limit)` — all city-tz (`ZoneInfo(city_timezone)` from `core.config`), inclusive ranges, raising the 422 `HTTPException` shapes of contracts/dashboard.md §4 (make T003 pass; depends on T005/T006 only for typing)

**Checkpoint**: migration applies; window math unit-tested; projections and
access aggregates exist but no endpoint exposes them yet.

---

## Phase 3: User Story 1 — Administrador visualiza o mapa de calor de visitas (Priority: P1) 🎯 MVP

**Goal**: `GET /api/v1/dashboard/heatmap` returns markers (latitude,
longitude, weight = number of visits) aggregated by spot or, when
`regions` exists in location data, by region.

**Independent Test**: seed visits on known spots → each returned marker's
weight equals the expected visit count per spot/region (spec US1).

### Tests (write first, watch them fail)

- [x] T008 [P] [US1] Write failing unit tests for region parsing in `tests/unit/test_dashboard_regions.py`: regions from location data resolve spot name → spot group; centroid = mean of constituent spot coordinates; unknown spot names skipped with structured log; `regions` block absent → `groupBy=region` rejeitado (422 `ApiError`, contracts §6) (research R5)
- [x] T009 [P] [US1] Write failing contract test for the heatmap endpoint in `tests/contract/test_dashboard_metrics.py::test_heatmap_contract`: 200 camelCase `HeatmapResponse` shape (`markers[]` with `spotId`, `name`, `latitude`, `longitude`, `weight`); `groupBy=spot|region` accepted; `region` without regions data → 422; `endDate < startDate` → 422; anonymous → 401; employee → 403; tag `Dashboard` in the OpenAPI entry

### Implementation

- [x] T010 [US1] Implement spot-mode aggregate in `src/passanorte_back/modules/dashboard/services/metrics.py`: `heatmap(session, *, group_by, start_date, end_date)` — set-based `GROUP BY tourist_spot_id` over `visitations_v` joined to `tourist_spots_v` for name/coordinates, window inclusive (FR-004/FR-006/FR-007); removed spots keep counting (research R7)
- [x] T011 [US1] Implement region-mode aggregation + region resolver in `src/passanorte_back/modules/dashboard/services/metrics.py`: parse `regions` from location data (unique keys), centroid coordinates, weight = Σ of constituent spots' visits; only when the block exists, else 422 (FR-005; make T008 pass)
- [x] T012 [US1] Create `src/passanorte_back/modules/dashboard/schemas/metrics.py`: `HeatmapResponse`/`HeatmapMarker` inheriting `ApiModel` (camelCase, `extra="forbid"`, snake_case attributes; `spotId: int | None` for region markers)
- [x] T013 [US1] Create `src/passanorte_back/modules/dashboard/routes/metrics.py`: `GET /heatmap` admin-only via `require_admin`, query params `groupBy|startDate|endDate`, 422 paths feed the unified `ApiError` handler; no tag strings in the file (FR-002; make T009 pass)

**Checkpoint**: `heatmap` fully functional and independently testable —
MVP increment for the admin map.

---

## Phase 4: User Story 2 — Administrador visualiza o contador de acessos por período (Priority: P1)

**Goal**: tourist-authenticated requests record access events (best-effort
middleware) and `GET /api/v1/dashboard/access-counts` reports
`uniqueTouristDays`, `totalAccessEvents` and the daily series per
configurable period.

**Independent Test**: authenticated tourist requests in distinct days →
counter equals the recorded distinct tourist×day pairs and totals for
each period (spec US2, SC-002).

### Tests (write first, watch them fail)

- [x] T014 [P] [US2] Write failing integration tests in `tests/integration/test_access_events_flow.py`: tourist-authenticated request (including a public endpoint consulted with tourist token) → exactly one `access_events` row with correct `occurred_at`/`day` (city tz); employee/anonymous requests write nothing; recording failure (stubbed insert error) still returns 200 to the tourist and logs a structured error (FR-008/FR-011/FR-022 — research R2)
- [x] T015 [P] [US2] Write failing contract test in `tests/contract/test_dashboard_metrics.py::test_access_counts_contract`: `period=today|week|month|custom` shapes (`uniqueTouristDays`, `totalAccessEvents`, `daily[]` camelCase); `custom` without dates → 422; unknown `period` → 422; anonymous → 401; employee → 403; empty window → zeros with empty `daily`

### Implementation

- [x] T016 [P] [US2] Add the small public seam `decode_tourist_token(token) -> int | None` to `src/passanorte_back/modules/auth/services/security.py` (signature+expiry verified, no DB session check, tourist claims only, exported via the module's public interface) (research R2)
- [x] T017 [P] [US2] Implement best-effort recording middleware in `src/passanorte_back/modules/dashboard/services/access_recording.py`: peek `Authorization: Bearer`, call `decode_tourist_token`, insert one event via `access_events` repository in its own transaction; every exception swallowed into a structured error log, tourist request unaffected; export `register_access_recording(app)`
- [x] T018 [US2] Wire `register_access_recording(app)` in `src/passanorte_back/main.py` (composition root — exempt from the boundary gate; make T014 pass)
- [x] T019 [US2] Implement `/access-counts` in `src/passanorte_back/modules/dashboard/routes/metrics.py` + `AccessCountsResponse`/`AccessDailyCount`/`DailyCountItem` schemas in `src/passanorte_back/modules/dashboard/schemas/metrics.py`: uses `resolve_period_window` + the aggregates of T005; ascending `daily[]` only for days with events (FR-009/FR-010; make T015 pass)

**Checkpoint**: counters accurate against the ledger for every period;
essential services proven unaffected by recording failure.

---

## Phase 5: User Story 3 — Administrador visualiza o ranking de pontos mais visitados (Priority: P1)

**Goal**: `GET /api/v1/dashboard/spot-ranking` returns the top N spots by
real visits for one window (`granularity=day|month|year` with
`referenceDate`).

**Independent Test**: visits spread across spots and windows → ordering,
counts and limit match the ledger for each granularity (spec US3, SC-003).

### Tests (write first, watch them fail)

- [x] T020 [P] [US3] Write failing contract test in `tests/contract/test_dashboard_metrics.py::test_spot_ranking_contract`: descending `items[]` (`position`, `spotId`, `name`, `visits`) honoring `limit` (default 5, max 100 → 422 outside 1–100); unknown `granularity` → 422; missing `referenceDate` defaults to today; anonymous → 401; employee → 403

### Implementation

- [x] T021 [US3] Implement ranking aggregate in `src/passanorte_back/modules/dashboard/services/metrics.py`: `spot_ranking(...)` — `GROUP BY spot ORDER BY COUNT DESC, spot_id ASC LIMIT N` over the visitation projection; only spots with ≥1 visit (FR-012/FR-013/FR-014; removed spots stay ranked — research R7)
- [x] T022 [US3] Implement `GET /spot-ranking` in `src/passanorte_back/modules/dashboard/routes/metrics.py` + `SpotRankingResponse`/`RankingItem` schemas in `src/passanorte_back/modules/dashboard/schemas/metrics.py` (make T020 pass)

**Checkpoint**: ranking independently correct for all three granularities.

---

## Phase 6: User Story 4 — Administrador visualiza a distribuição por país de origem (Priority: P2)

**Goal**: `GET /api/v1/dashboard/visitor-countries` returns tourists and
shares per `country_of_origin` over the visitor population.

**Independent Test**: tourists of distinct countries with/without
visitations → shares relative to visitors only, summing to 100 ±0.5 (spec
US4, SC-004).

### Tests (write first, watch them fail)

- [x] T023 [P] [US4] Write failing contract test in `tests/contract/test_dashboard_metrics.py::test_visitor_countries_contract`: 200 camelCase (`totalVisitors`, `items[]` with `country`, `tourists`, `share`); tourists without visits excluded; empty country → `Não informado` bucket; optional window `startDate`/`endDate`; anonymous → 401; employee → 403

### Implementation

- [x] T024 [US4] Implement country-distribution aggregate in `src/passanorte_back/modules/dashboard/services/metrics.py`: population = `COUNT(DISTINCT tourist_id)` over visitations within the optional window; share = `ROUND(100.0 * visitors_of_country / total_visitors, 1)` in SQL (no Python loops); descending by `tourists` (FR-015/FR-016; research R6)
- [x] T025 [US4] Implement `GET /visitor-countries` in `src/passanorte_back/modules/dashboard/routes/metrics.py` + `VisitorCountriesResponse`/`CountryShareItem` schemas in `src/passanorte_back/modules/dashboard/schemas/metrics.py` (make T023 pass)

**Checkpoint**: distribution correct and independently testable.

---

## Phase 7: User Story 5 — Administrador visualiza a distribuição por interesses (Priority: P2)

**Goal**: `GET /api/v1/dashboard/visitor-interests` returns tourists and
shares per declared interest over the same visitor population.

**Independent Test**: visitors with overlapping multi-interest profiles →
counts per key, shares relative to `totalSelections` (may exceed 100) —
spec US5, SC-004.

### Tests (write first, watch them fail)

- [x] T026 [P] [US5] Write failing contract test in `tests/contract/test_dashboard_metrics.py::test_visitor_interests_contract`: 200 camelCase (`totalVisitors`, `totalSelections`, `items[]` with `interestKey`, `interestLabel`, `tourists`, `share`); a tourist counts once per declared interest; visitors without interests contribute nothing; unselected categories absent; same params/error paths as US4; anonymous → 401; employee → 403

### Implementation

- [x] T027 [US5] Implement interest-distribution aggregate in `src/passanorte_back/modules/dashboard/services/metrics.py`: population = same window-filtered visitor set (Q5), join `tourist_interests_v` per visitor, counts per `category_key`, share over `totalSelections` in SQL; `interestLabel` resolved from location categories (unknown key → key as label) (FR-017/FR-018)
- [x] T028 [US5] Implement `GET /visitor-interests` in `src/passanorte_back/modules/dashboard/routes/metrics.py` + `VisitorInterestsResponse`/`InterestShareItem` schemas in `src/passanorte_back/modules/dashboard/schemas/metrics.py` (make T026 pass)

**Checkpoint**: all five endpoints live; dashboard still read-only outside
its own tables.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: the spec's holistic acceptance criteria and repo-wide gates.

- [x] T029 [P] Write the full acceptance flow in `tests/integration/test_dashboard_metrics_flow.py` per spec criterion: seed multiple tourists from distinct countries with distinct interest sets + visitations across several days/spots (some to removed spots), request days via tourists so `access_events` accrue; assert all five endpoints exactly against the seeded expectation (SC-001..SC-004, SC-007) and that zero metrics are synthesized
- [x] T030 [P] Write the RBAC matrix test in `tests/contract/test_dashboard_metrics.py::test_all_endpoints_admin_only`: for each of the five endpoints, employee session → 403 and tourist session → 403 (RF03, SC-005) and unauthenticated → 401
- [x] T031 [P] Add the migration-0009 upgrade/downgrade round trip to `tests/test_migrations.py` if not fully covered by T002; run `pytest tests/test_migrations.py tests/smoke/test_boundaries.py tests/contract/test_openapi_tags.py -q` green
- [x] T032 Run `ruff check && ruff format` until clean; update module docstrings (English) of every new file and the module README section if the repo keeps one; verify no sensitive column is ever referenced in `read_projections.py` (data-model.md §2 — LGPD, SC-007)
- [x] T033 Run full `quickstart.md` automated validation block (all dashboard suites + boundaries + migrations + tags) as the final Definition-of-Done gate
- [x] T034 [P] Write the performance budget for SC-006 in `tests/perf/test_dashboard_budget.py`: ~10 spots, 100 tourists, 10k visitations and 50k access events seeded in bulk (chunked inserts — SQLite per-statement bind limit); every aggregate call answers under 2 s (post-`/speckit-analyze` remediation C1)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none — immediate.
- **Foundational (Phase 2)**: blocks every user story (T002→T004; T003→T007;
  T005/T006 parallel).
- **US1 (Phase 3)**: needs Phase 2 (projections + windows + migration).
- **US2 (Phase 4)**: needs T004/T005 (access tables) — independent of US1.
- **US3 (Phase 5)**, **US4 (Phase 6)**, **US5 (Phase 7)**: need Phase 2 only
  (projections/windows); mutually independent.
- **Polish (Phase 8)**: after all desired stories (T029/T030 touch every
  endpoint).

### User Story Dependencies

- US1 → Phase 2 (no cross-story deps).
- US2 → Phase 2 + T004/T005; T016–T018 independent of US1/US3–US5 code.
- US3/US4/US5 → Phase 2 only; strictly independent of each other.
- Schemas/routes inside a story are sequential (tests red → service →
  schemas → route green).

### Parallel Opportunities

- Foundational: T002/T003 (tests) together; T004/T005/T006 together.
- Story tests (T008/T009, T014/T015, T020, T023, T026) can all be written
  before their story's implementation.
- After Phase 2, the five stories are parallelizable across contributors
  (different files; only `schemas/metrics.py` and `routes/metrics.py` are
  shared — assign whole stories, not tasks, to avoid conflicts).
- Polish: T029/T030/T031 parallel; T032–T033 sequential last.

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 + Phase 2 (foundation green).
2. Phase 3 (US1 heat map) → validate independently (T008–T009).
3. Stop and demo the map increment; the counter/ranking/distributions
   remain untouched.

### Incremental Delivery

Phase 2 → US1 (MVP) → US2 → US3 → US4 → US5 → Phase 8. Each story ships
value without breaking the previous ones; the shared files
(`routes/metrics.py`, `schemas/metrics.py`) grow additively.

### Parallel Team Strategy

Assign whole stories per contributor after Phase 2; merge order US1 → US2 →
US3 → US4 → US5 to minimize conflicts on the two shared files.

---

## Notes

- Test-first is mandatory (constitution): every "write failing test" task
  must demonstrably fail before its implementation task flips it.
- [P] = different files, no dependency on an incomplete task.
- No story may import another module's internals — only
  `auth.services`'s public surface (T016) and `core.*`.
- Commit after every task or logically green group.
