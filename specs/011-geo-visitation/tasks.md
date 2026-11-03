# Tasks: Geo-Visitation (011-geo-visitation)

**Input**: Design documents from `/specs/011-geo-visitation/`

**Prerequisites**: plan.md, spec.md (7 clarified decisions), research.md (R1–R9), data-model.md, contracts/visitation.md, quickstart.md

**Tests**: MANDATORY — constitution principle III is non-negotiable (test-first: red → implementation → green); coverage is an acceptance criterion of each task.

**Organization**: tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on incomplete tasks)
- **[Story]**: user story from spec.md (US1–US4)
- Exact file paths included in every description

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: verify the module shell that already exists (skeleton + router + tag); no initialization work is needed — `gps_tolerance_radius_m = 100.0` is already in `core/config.py` (research R2) and `visitation` is already in `DOMAIN_MODULES` with its tag mounted by `core/routers.py`.

- [X] T001 Confirm the visitation module skeleton (`src/passanorte_back/modules/visitation/{routes,services,repositories,schemas}/__init__.py`) is importable with no business code and that `tests/smoke/test_modules.py` still passes

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: migration + spot radius column — MUST be complete before ANY user story

**⚠️ CRITICAL**: no user story work can begin until this phase is complete (every story reads `visitations` and/or the effective radius).

- [X] T002 Create migration `0007_visitation` in `migrations/versions/20261103_0007_visitation.py`: table `visitations` (`id` PK; `tourist_id` Integer NOT NULL indexed read-only ref into `tourists`; `tourist_spot_id` Integer NOT NULL indexed read-only ref into `tourist_spots`; `visited_at` DateTime NOT NULL indexed UTC; `latitude` Float NOT NULL; `longitude` Float NOT NULL; NO unique constraint on the pair — repeat visits append per data-model.md §1) plus `op.add_column` of nullable `tolerance_radius_m` Float on `tourist_spots`; verified by the existing `tests/test_migrations.py` upgrade path
- [X] T003 [P] Add `tolerance_radius_m: Mapped[float | None]` (Float, nullable, documented "None → global default `settings.gps_tolerance_radius_m`") to `TouristSpot` in `src/passanorte_back/modules/tourist_spots/repositories/tourist_spots.py`
- [X] T004 [P] Add optional `toleranceRadiusM` (float > 0 or explicit null) to `SpotCreateRequest`/`SpotUpdateRequest`/`SpotView`/public spot views in `src/passanorte_back/modules/tourist_spots/schemas/tourist_spots.py` (camelCase contract per spec 005; absent in PATCH = unchanged, explicit null = back to global default) and thread it through `create_spot`/`update_spot`/`spot_to_view` in `src/passanorte_back/modules/tourist_spots/services/tourist_spots.py`
- [X] T005 [P] Write contract test `tests/contract/test_tourist_spots_radius.py` (red first): radius accepted in create, echoed in view, explicit null resets to global default, negative/zero values rejected 422 — constraint verbatim: "float > 0, nullable"

---

## Phase 3: User Story 1 — Turista marca visitação em um ponto presente (P1)

**Story goal**: tourist inside the tolerance radius marks the visitation and gets it persisted as "visitado" (RF31/RF32/RF33 core path).

**Independent test**: `POST /api/v1/visitation/spots/{spotId}/visits` with in-radius GPS → 201, immutable record with timestamp + validated coordinates (rejections come in US2; progress comes in US3).

**Acceptance refs**: spec US1 scenarios 1–3; SC-001/SC-003.

- [X] T006 [US1] Write contract test (red): `tests/contract/test_visitation.py` — POST inside radius returns 201 with camelCase keys (`id`, `spotId`, `visitedAt`, `latitude`, `longitude`, `firstVisit`, `routeOutcomes`), strict `extra="forbid"` payload; include the FR-013 422 cases (analyze C2): `latitude: 91`, `longitude: 181` and non-finite values must return 422 (unified `ApiError`) before any distance math (nothing persisted)
- [X] T007 [US1] Write unit test (red): `tests/unit/test_haversine.py` — exact cases from FR-005: zero distance (0.0), inside (~55 m < 100), outside (~5 km), border (distance == radius accepted), antipodes (≈ 2·R = 12 742 km rejected, `haversine(-22.7271, -45.0366, 22.7271, 134.9634)`), 1°-latitude anchor ≈ 111.19 km; plus `resolve_tolerance_radius_m` (spot override wins, None → `settings.gps_tolerance_radius_m`)
- [X] T008 [US1] Implement `haversine_distance_m(lat1, lng1, lat2, lng2) -> float` (standard `math`, mean radius `R = 6_371_008.8` m, research R1) and `resolve_tolerance_radius_m(spot, settings) -> float` in `src/passanorte_back/modules/visitation/services/geolocation.py` (green T007)
- [X] T009 [US1] Implement `Visitation` model + `insert_visit`/`exists_for_pair`/`list_for_tourist`/`visited_spot_rows` in `src/passanorte_back/modules/visitation/repositories/visitations.py` (append-only; fields per data-model.md §1) and register the new model in the explicit import list of the `db_engine` fixture in `tests/conftest.py` (analyze C1 — without it `Base.metadata.create_all` skips the `visitations` table and every visitation test fails with a missing-table error)
- [X] T010 [US1] Implement ApiModel schemas in `src/passanorte_back/modules/visitation/schemas/visitations.py`: `MarkVisitationRequest` (latitude/longitude, WGS-84 range + finite, `ApiModel` strict), `VisitationMarkedResponse`, `RouteOutcome`, `VisitationView`, `VisitationListView`, `VisitedSpotView`, `VisitedSpotsView`
- [X] T011 [US1] Implement `mark_visitation(session, *, user, spot_id, latitude, longitude)` in `src/passanorte_back/modules/visitation/services/visitations.py`: resolve tourist via public `tourists.services.get_tourist_account` (`user.account_id`, None → 404 `TouristMissingError`), load spot via public `tourist_spots.services.get_active_spot` (missing → `SpotMissingError`), resolve effective radius (T008), haversine check, `firstVisit = not exists_for_pair`, insert row (server UTC timestamp) — seam-less for now (`routeOutcomes: []`)
- [X] T012 [US1] Implement route `POST /visitation/spots/{spot_id}/visits` in `src/passanorte_back/modules/visitation/routes/visitations.py` on the pre-mounted module router (`core.routers.MODULE_ROUTERS[\"visitation\"]`, no tag strings), `Depends(require_tourist)` + `Depends(get_session)`, mapping domain exceptions to HTTP (404 `SPOT_NOT_FOUND`/`TOURIST_NOT_FOUND`); green T006 (docs use camelCase `{spotId}` like spec 009's `{routeId}`; code path vars stay snake_case — same precedent)
- [X] T013 [US1] Integration test: `tests/integration/test_visitation_flow.py` — mark inside radius → 201, row persisted with timestamp + validated coordinates (SC-003), and per-spot-radius scenario covered again end-to-end

---

## Phase 4: User Story 2 — Visitante fora do ponto é rejeitado (P1)

**Story goal**: presence outside the effective radius is rejected loudly — 409, unified error payload, structured log, nothing persisted (RF32/RNF14 anti-fraud side).

**Independent test**: `POST .../visits` with clearly distant GPS → 409 `OUTSIDE_TOLERANCE_RADIUS` (camelCase payload), zero new `visitations` rows, one structured warning log.

**Acceptance refs**: spec US2 scenarios 1–2; SC-002/SC-007.

- [X] T014 [US2] Write contract test (red, appended to `tests/contract/test_visitation.py`): outside radius → 409 `ApiError` with `errorCode: OUTSIDE_TOLERANCE_RADIUS`, camelCase keys, no snake_case; repeat of the request leaves history unchanged (nothing persisted)
- [X] T015 [US2] Implement `OutsideToleranceError` + rejection path in `src/passanorte_back/modules/visitation/services/visitations.py`: `logger.warning(\"outside_tolerance_radius\", extra={tourist_id, spot_id, distance_m, effective_radius_m})` via module logger (research R5), raising before (or rolling back) any insert — green T014; border case covered by T007
- [X] T016 [US2] Integration test (appended to `tests/integration/test_visitation_flow.py`): spot with per-spot radius 25 m rejects GPS 80 m away with 409 while global default is 100 m (US2 scenario 2); `caplog`/structlog assertion that exactly one structured warning was emitted (SC-007)

---

## Phase 5: User Story 3 — Progresso das rotas vinculadas é atualizado (P2)

**Story goal**: first visitation triggers the spec 009 public seam exactly once; repeats append history without progress updates (RF34, idempotency).

**Independent test**: tourist enrolled in an in-progress route containing the spot; mark inside radius → `routeOutcomes` shows `completionRate` rising; repeat mark → `firstVisit: false`, `routeOutcomes: []`, progress unchanged.

**Acceptance refs**: spec US3 scenarios 1–3; SC-004, SC-005.

- [X] T017 [US3] Write integration test (red, appended to `tests/integration/test_visitation_flow.py`): world seeded via public services only (`tourist_spots.create_spot`, `gamification.create_route` + `enroll_tourist`, `tourists.register_tourist` — same pattern as `tests/integration/test_gamification_visit.py`); first mark → `firstVisit: true` and `routeOutcomes` with rising `completionRate`; last pending spot completes enrollment exactly once (badge + redemption code exist, seam semantics of research R3)
- [X] T018 [US3] Implement seam wiring in `mark_visitation`: when `firstVisit`, call `passanorte_back.modules.gamification.services.gamification.register_spot_visit(session, tourist_id=user.account_id, tourist_spot_id=spot.id)` (the ONLY gamification import — public interface per `__all__`; never gamification internals) and map `VisitRouteOutcome` → `RouteOutcome` dtos; map seam `TouristMissingError`; same session = same transaction (research R4), green T017
- [X] T019 [US3] Write integration test (red): idempotency — repeat mark → 201, `firstVisit: false`, `routeOutcomes: []`, no new badge/code rows, route `completionRate` unchanged (FR-009; assert via gamification public views or direct gamification-model query inside the test, as the seam test already does)
- [X] T020 [US3] Verify (and fix if needed) repeat path: `exists_for_pair` gate skips the seam call entirely on repeat visits — green T019; the boundary smoke test `tests/smoke/test_boundaries.py` still passes (zero private cross-module imports)

---

## Phase 6: User Story 4 — Histórico de visitações do turista (P3)

**Story goal**: tourist reads own history and visited-spots projection.

**Independent test**: two visits on one spot → history shows both rows (ids, spotId, timestamps, coordinates); visited-spots shows one item with `firstVisitAt` = min timestamp and `visitCount` = 2; empty tourist → empty lists, 200.

**Acceptance refs**: spec US4 scenarios 1–2; FR-010.

- [X] T021 [US4] Write contract test (red, appended to `tests/contract/test_visitation.py`): `GET /visitation/visitations` (newest first) and `GET /visitation/visited-spots` shapes per contracts/visitation.md §2/§3; tourist-exclusive (403 for admin/employee); empty tourist → 200 `\"items\": []`
- [X] T022 [US4] Implement read models: repository queries + services (`list_visitations`, `list_visited_spots` — derivation `EXISTS`/`MIN(visited_at)`/`COUNT` per Q1, no status table) and route handlers `GET /visitation/visitations`, `GET /visitation/visited-spots` in `src/passanorte_back/modules/visitation/routes/visitations.py` (`require_tourist`), green T021

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T023 [P] Extend the existing `Visitation` tag description for the new domain endpoints in `src/passanorte_back/core/tags.py` (the only file allowed to hold tag metadata — spec 006); `tests/contract/test_openapi_tags.py` stays green
- [X] T024 Run `ruff check` + full validation battery: `pytest tests/unit/test_haversine.py tests/contract/test_visitation.py tests/contract/test_tourist_spots_radius.py tests/contract/test_openapi_tags.py tests/contract/test_strict_input.py tests/integration/test_visitation_flow.py tests/smoke/test_boundaries.py tests/smoke/test_modules.py tests/test_migrations.py -q` all green (quality gates of the constitution); update module docstrings (English) where tasks added new files

---

## Dependencies

**User story completion order** (each story yields a testable increment):

```text
T001 → T002 (migration) → T003, T004, T005 (spot radius delta)
      → US1: T006 → T007 → T008, T009, T010 → T011 → T012 → T013
      → US2: T014 → T015 → T016        (depends on US1 mark flow)
      → US3: T017 → T018 → T019 → T020 (depends on US1; seam from spec 009)
      → US4: T021 → T022               (depends on US1 records)
      → Polish: T023, T024
```

- **US2 depends on US1** (rejection is the other half of the same request path — implement after the accept path exists)
- **US3 depends on US1** (seam call site lives in `mark_visitation`)
- **US4 depends on US1** (reads rows the mark flow writes; no dependence on US2/US3)

## Parallel Execution Examples

- **Foundational**: T003 ∥ T004 ∥ T005 (different files; all blocked only by T002's migration design, not its merge)
- **US1 core**: T008 ∥ T009 ∥ T010 (geolocation / repository / schemas — disjoint files, T007's contract agreed)
- **US4**: T021 (contract test) is written while T022's repository queries are being designed
- **Polish**: T023 ∥ T024-after-everything

## Implementation Strategy

- **MVP first**: US1 + US2 (Phase 3 + 4) = P1 core: tourist can mark a validated visitation and fraud attempts are rejected — independently shippable and demonstrable in Swagger.
- **Increment 2** (US3): gamification progress via the existing spec 009 seam — the first cross-module write-through of the monolito modular.
- **Increment 3** (US4): read-only projections (history + visited-spots).
- Every task red-green: tests from each task's red step run first (constitution III).

---

## Phase 8: Convergence

- [X] T025 [US2] Extend `tests/contract/test_visitation.py` with the missing edge-case coverage per Edge Cases + FR-013 (partial): mark on a nonexistent spot id → 404 `resource_not_found`; mark on a removed spot (admin soft-delete via PATCH `status: permanentlyClosed`/remove, then tourist marks → 404 — removed spots are invisible everywhere, R6); a `NaN`/`Infinity` coordinate payload → 422 `validation_error` before any distance math (raw JSON body; verify nothing persisted via the empty history)
- [X] T026 [US4] Add the SC-003 immutability guard in `tests/contract/test_visitation.py`: assert the visitation module exposes NO mutative path for the ledger — `PUT`/`PATCH`/`DELETE` on `/api/v1/visitation/visitations*` and on marked spots' visits return 405 (method not allowed / never a data change), keeping FR-006's append-only contract verifiable (partial)
