# Tasks: Passaporte Discovery (Ranked Spots & Navigation Links)

**Input**: Design documents from `/specs/013-descoberta-passaporte/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/tourist-spots-discovery.md, quickstart.md

**Tests**: Requested explicitly by the spec's acceptance criteria (contract, deeplink-generator, performance tests) and by constitution III (test-first, NON-NEGOTIABLE). Every story phase starts with tests written FIRST, verified FAILING, before implementation.

**Organization**: Grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

Modular monolith (existing project): `src/passanorte_back/core/` +
`src/passanorte_back/modules/<domain>/{routes,services,repositories,schemas}/`,
tests in `tests/{unit,contract,integration,perf,smoke}/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Verify the working baseline before any feature code lands.

- [x] T001 Run baseline checks — `pytest tests/smoke/test_boundaries.py tests/test_migrations.py -q` and `ruff check .` — confirming green before any change (feature 012 end state)
- [x] T002 [P] Document discovery policy keys (`discovery_w_proximity`, `discovery_max_distance_km`, `discovery_event_window_days`, `discovery_event_boost_min`, `discovery_neutral_proximity`, `discovery_map_provider` with defaults from research.md §R2) in `.env.example` and the settings table of README.md

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Configuration, index and cross-domain seams required by ALL user stories.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T003 Add discovery settings to `Settings` in src/passanorte_back/core/config.py — `discovery_w_proximity=0.5`, `discovery_w_interest=0.35`, `discovery_w_event=0.15` (validator: all > 0 and sum == 1, refuse to start otherwise), `discovery_max_distance_km=10`, `discovery_event_window_days=30`, `discovery_event_boost_min=0.25`, `discovery_neutral_proximity=0.5`, `discovery_map_provider: Literal["google_maps", "osm"] = "google_maps"` (research.md §R2/§R9)
- [x] T004 [P] Create migration migrations/versions/20261103_0008_spot_discovery_index.py — partial index `ix_tourist_spot_status_active` on `tourist_spots(status) WHERE removed_at IS NULL` (research.md §R3); verify with `pytest tests/test_migrations.py -q`
- [x] T005 [P] Unit test for the events seam in tests/unit/test_upcoming_events_seam.py — `list_upcoming_event_dates(session, from_date)` (to be added in T006) returns `(spot_id, nearest future occurrence_date)` pairs, excludes past events, returns `[]` for empty events (test-first: write, see FAIL)
- [x] T006 Implement the public events seam `list_upcoming_event_dates(session, *, from_date: date) -> list[tuple[int, date]]` in src/passanorte_back/modules/events/services/events.py — one indexed query on `occurrence_date` ≥ from_date ordered `(occurrence_date, id)`, grouped to nearest per spot (research.md §R5); make T005 pass

**Checkpoint**: Config validates at startup, index migration applies, events seam green.

---

## Phase 3: User Story 1 — Ranked discovery feed (Priority: P1) 🎯 MVP

**Goal**: Tourist-authenticated, paginated feed of spots ranked by the documented relevance score (proximity-dominant → interests → minor event boost), with tie-break determinism and visibility rules (spec US1, RF26).

**Independent Test**: Seed spots (interest matches/non-matches, future-event vs. none, temporarily/permanently closed), authenticate as tourist, assert feed order for every contract case — works without touching US2/US3.

### Tests for User Story 1 (write FIRST, verify FAIL)

- [x] T007 [P] [US1] Unit tests for the relevance score in tests/unit/test_relevance_score.py — cover: factor formulas normalized to [0,1] exactly per research.md §R2; interest ratio `|spot_categories ∩ tourist_interests| / |spot_categories|`; proximity `clamp(1 - d/max_km, 0, 1)` with d > max_km ⇒ 0; neutral proximity constant without position; event boost growing as date approaches, BOOST_MIN floor beyond window, zero for past/absent events; weighted sum `0.5/0.35/0.15`; tie-break `name` (case-insensitive) asc → `id` asc with repeated-call determinism
- [x] T008 [P] [US1] Contract test for the feed in tests/contract/test_discovery_feed.py — `GET /api/v1/tourist-spots/discover` per contracts/tourist-spots-discovery.md §1: interest-matching spots ranked ahead ( tourist with interests vs. without — SC-001); no position sent ⇒ valid deterministic order (SC-002); spot with imminent future event outranks identical spot without, past events give no boost (SC-003); permanently closed absent, temporarily closed present with visible status (FR-007); every item carries camelCase `relevanceScore` + `upcomingEventDate` + `mapLink` (FR-002); 422 ApiError for out-of-range coordinates; 403 for admin/employee/unauthenticated; page beyond last ⇒ 200 empty items; ruff-clean camelCase wire keys end-to-end

### Implementation for User Story 1

- [x] T009 [US1] Implement the discovery service in src/passanorte_back/modules/tourist_spots/services/discovery.py — `discover_spots(session, *, tourist_id, latitude | None, longitude | None, page, page_size)` reading: interests via the tourists public seam (interest keys), future event dates via `events.list_upcoming_event_dates`, active spots via repository; compute scores per research.md §R2; sort score desc → name casefold → id; return (items, total) (depends on T003, T006)
- [x] T010 [P] [US1] Add feed repository query `list_discovery_candidates` in src/passanorte_back/modules/tourist_spots/repositories/tourist_spots.py — one query `removed_at IS NULL AND status != permanently_closed` using `ix_tourist_spot_status_active`, categories preloaded (no N+1: single query per table — research.md §R3)
- [x] T011 [US1] Add wire schemas `DiscoveryFeedItem` (id, name, description, latitude, longitude, status, categories[], relevanceScore, upcomingEventDate, mapLink) and `DiscoveryFeedResponse` (items, page, pageSize, totalItems, totalPages) in src/passanorte_back/modules/tourist_spots/schemas/tourist_spots.py — inherit `ApiModel`, camelCase JSON, `extra="forbid"` (data-model.md Computed views)
- [x] T012 [US1] Add route `GET /discover` in src/passanorte_back/modules/tourist_spots/routes/tourist_spots.py — `Depends(require_tourist)`, optional query params `latitude`/`longitude` (WGS-84 bounds validated by the request model), `page ≥ 1`, `pageSize` 1–100 alias of `page_size`; no tag string in the file (router carries `Tourist Spots` from core/routers.py); failures only via unified ApiError (depends on T011)
- [x] T013 [US1] Integration test for the discovery flow in tests/integration/test_discovery_flow.py — tourist registers → sets interests (spec 003 seam) → discovers with and without position → walks every page asserting zero duplicates and zero omissions vs. the deterministic full order (SC-005) → links back to tourist_interests still replaceable (depends on T009–T012)

**Checkpoint**: `pytest tests/contract/test_discovery_feed.py tests/unit/test_relevance_score.py tests/integration/test_discovery_flow.py -q` green — US1 delivers RF26 end-to-end without US2/US3.

---

## Phase 4: User Story 2 — Navigation deep links (Priority: P2)

**Goal**: Google Maps/OSM, Uber and 99 deep links per spot — via `GET /api/v1/tourist-spots/{id}/navigation-links` with tourist position as pickup, and additive fields on the existing public detail (spec US2, RF28; contracts §2–§3).

**Independent Test**: One existing spot + a position; call the links endpoint and the generators; verify exact coordinates/targets — independent of the feed.

### Tests for User Story 2 (write FIRST, verify FAIL)

- [x] T014 [P] [US2] Unit tests for the link builders in tests/unit/test_navigation_link_builders.py — byte-exact targets per research.md §R4: Google Maps `maps/dir/?api=1&destination=…&origin=…` (destination-only when no origin, matching existing `build_map_link` semantics), OSM `openstreetmap.org/directions?engine=fossgis_osrm_car&route=…`, Uber `m.uber.com/ul/?action=setPickup&pickup[latitude]=…&dropoff[latitude]=…`, 99 `99taxi://ride?pickupLatitude=…&dropLatitude=…`; assert decimal WGS-84 coordinates pass through unchanged (no precision loss, no origin/destination swap — SC-004) and provider selection follows `discovery_map_provider`
- [x] T015 [P] [US2] Contract test for the links surface in tests/contract/test_navigation_links.py — per contracts §2–§3: `GET /api/v1/tourist-spots/{id}/navigation-links` returns `origin` + three ready links with provided position as pickup; without position, `origin` = spot coordinates (FR-010, US2-AS3); destination equals spot coordinates exactly; 404 `resource_not_found` for unknown/removed spot; 422 invalid coordinates; 403 non-tourist; additive `uberLink`/`ninetyNineLink` on existing detail response with all prior 007 fields unchanged; provider switch `google_maps` → `osm` via Settings override changes only `mapLink` target, status codes and shapes identical (SC-007)

### Implementation for User Story 2

- [x] T016 [P] [US2] Implement deep-link builders in src/passanorte_back/modules/tourist_spots/services/navigation_links.py — pure string builders `build_directions_map_link(lat, lng, origin | None)`, `uber_link(lat, lng, origin | None)`, `ninety_nine_link(lat, lng, origin | None)` selected by `Settings.discovery_map_provider` (research.md §R4); reuse/extend `build_map_link` for backward compatibility (depends on T003)
- [x] T017 [US2] Add `NavigationOrigin` and `NavigationLinksView` wire schemas (origin, mapLink, uberLink, ninetyNineLink — key naming note in data-model.md) and extend the public detail view with additive `uberLink`/`ninetyNineLink` (origin = spot's own coordinates) in src/passanorte_back/modules/tourist_spots/schemas/tourist_spots.py + `build_public_detail` in src/passanorte_back/modules/tourist_spots/services/tourist_spots.py — additive only (depends on T016)
- [x] T018 [US2] Add route `GET /{id}/navigation-links` in src/passanorte_back/modules/tourist_spots/routes/tourist_spots.py — `Depends(require_tourist)`, optional `latitude`/`longitude`; 404 via existing `SpotMissingError` mapping, 422 via request-model validation, ApiError-only failures (depends on T017)

**Checkpoint**: `pytest tests/contract/test_navigation_links.py tests/unit/test_navigation_link_builders.py -q` green; existing 007 contract suite still green (additive change proven backwards-compatible).

---

## Phase 5: User Story 3 — Performance budget (Priority: P3)

**Goal**: Feed + links respond within the 1 s / page budget on ≈1,000 spots (SC-006), with bounded, predictable work (RNF12, FR-012).

**Independent Test**: Seed the 1,000-spot dataset and time five pages; budget assertion is self-contained.

### Tests for User Story 3 (write FIRST, verify FAIL)

- [x] T019 [P] [US3] Performance test in tests/perf/test_feed_budget.py — seed ~1,000 active spots (varied coordinates/categories plus ~200 events) through the repositories; for tourist sessions with and without position, assert each of pages 1–5 completes below 1.0 s wall-clock (SC-006) and that scores/order match the unit suite's deterministic expectations exactly (order is not sacrificed for speed — FR-003)

### Implementation for User Story 3

- [x] T020 [US3] Tighten the data path for budget compliance in src/passanorte_back/modules/tourist_spots/services/discovery.py and src/passanorte_back/modules/tourist_spots/repositories/tourist_spots.py — exactly one query per table (spots+categories joined, events via the T006 seam, interests for the tourist), no N+1, scoring in one pass, in-memory stable sort; verify the partial index is actually chosen for the candidates query; keep cache off (constitution V; settings toggle unused in v1) (depends on T019)

**Checkpoint**: `pytest tests/perf/test_feed_budget.py -q` green with headroom (target well below the same 1 s ceiling).

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Cross-story quality gates and documentation.

- [x] T021 [P] Update README.md service docs — new tourist-facing endpoints (`GET /api/v1/tourist-spots/discover`, `GET /api/v1/tourist-spots/{id}/navigation-links`), the documented score formula reference (research.md §R2), and the `DISCOVERY_*` settings table (depends on T002, T012, T018)
- [x] T022 Run the full quality gate — `pytest tests/ -q` (unit, contract, integration, perf, smoke, migrations) and `ruff check .` and `ruff format --check .`; fix any residue (all prior checkpoints)
- [x] T023 Execute the quickstart acceptance walkthrough specs/013-descoberta-passaporte/quickstart.md §3–§5 end-to-end and confirm the Definition of Done checklist §6 (depends on T022)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: none — start immediately
- **Phase 2 (Foundational)**: depends on T001; **blocks all user stories** (T003 settings used by score and links; T004 index used by feed; T005/T006 seam used by feed scoring)
- **Phase 3 (US1)**: depends on Phase 2 only — no dependency on US2/US3
- **Phase 4 (US2)**: depends on Phase 2 only (T003 provider setting, T016 uses it); T017 depends on T016; independent of US1
- **Phase 5 (US3)**: depends on US1 (T009/T010 exist to be tightened — T019 seeds and times the real feed path)
- **Phase 6 (Polish)**: depends on all desired user stories

### User Story Dependencies

- **US1 (P1)**: foundational only — the MVP slice, independently testable
- **US2 (P2)**: independent of US1 — could run in parallel; T017/T018 need T016's builders
- **US3 (P3)**: needs US1's service path to be measurable; otherwise independent

### Within Each Story

1. Test tasks FIRST — run, confirm FAIL (constitution III)
2. Services/repositories before schemas before routes
3. Integration test only after endpoint exists
4. Story checkpoint green before next story's implementation

### Parallel Opportunities

- Phase 2: T004, T005 (+T006 after), T002 in parallel with T003
- US1: T007 ∥ T008 tests in parallel, then implementations T010 ∥ (T011 after) while T009
- US2: T014 ∥ T015 tests; T016 ∥ nothing else until schemas (T017)
- US3: T019 alone (needs US1), then T020
- Cross-story: US1 and US2 phases are fully disjoint file sets except schemas — coordinate T011/T017 edits to `schemas/tourist_spots.py` sequentially

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 + Phase 2 → foundation green
2. Phase 3 (US1) → **RF26 delivered end-to-end (ranked feed with interests/position/events)**
3. STOP — validate via T013 + contract tests, demo-able

### Incremental Delivery

1. Foundation → 2. US1 (MVP) → 3. US2 (RF28 links) → 4. US3 (budget proof) → 5. Polish
Each checkpoint is independently verifiable and leaves the suite green.

## Notes

- Every task description carries exact file paths; implementation must keep code in English (constitution VII), wire keys camelCase (I), failures via `ApiError` only (I) and no tag strings outside `core/tags.py` (I)
- Do not persist the tourist position anywhere (FR-014/II); no new tables (research.md R1)
- Test-first is NON-NEGOTIABLE: red → implement → green at each story phase
---

## Phase 7: Convergence

Appended by /speckit-converge (2026-11-03) after the implement pass: three
partial gaps remain against FR-007's catalog-change edge case and two plan
sub-items. Everything else converged (coverage table in the analysis run).

- [x] T024 [P] [US1] Filter the discovery interest factor by the currently configured catalog in src/passanorte_back/modules/tourist_spots/services/discovery.py — compute `interest` over the spot's categories that exist in `Settings.resolved_interest_categories()` keys only (a spot holding catalog-orphan keys, reachable after a location.json catalog shrink — RNF06, spec 007 persistence, ranks as NON-matching per FR-007 edge case; denominator uses the filtered list so an all-orphan spot scores interest 0); add the red-first case to tests/unit/test_relevance_score.py (orphan category ⇒ factor 0) and a catalog-shrink contract case to tests/contract/test_discovery_feed.py (spot keeps its stored orphan key; the feed never breaks and the orphan does not match) per FR-007 (partial)
- [x] T025 [P] [US2] Add the byte-exact unit case for the OSM destination-only variant in tests/unit/test_navigation_link_builders.py — `build_directions_map_link(..., origin=None, provider="osm")` returns the documented marker link (`https://www.openstreetmap.org/?mlat=...&mlon=...#map=17/`) per plan §R4 (partial)
- [x] T026 [US3] Assert the feed candidates query actually uses the partial index in tests/perf/test_feed_budget.py — run `EXPLAIN QUERY PLAN` against the seeded staticpool database for the `list_discovery_candidates` query and assert the plan contains `ix_tourist_spot_status_active` (not a full table scan) per tasks T020 sub-item (partial)
