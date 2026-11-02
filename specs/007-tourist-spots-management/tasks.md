# Tasks: Tourist Spots Management (feature 007)

**Input**: Design documents from `/specs/007-tourist-spots-management/`

**Prerequisites**: plan.md (required), spec.md (required for user stories),
research.md, data-model.md, contracts/, quickstart.md

**Tests**: included — constitution III (Test-First, NON-NEGOTIABLE)
mandates test→fail→implement→green, and the spec's acceptance gate IS the
contract suite (SC-007). Every story phase starts with failing tests.

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

**Purpose**: Configuration data the whole feature reads (category catalog
+ city timezone — pure data, RNF06)

- [X] T001 [P] Extend `config/location.json`: add catalog entries
  `{"key": "leisure", "label": "Lazer"}`, `{"key": "art", "label":
  "Arte"}`, `{"key": "cinema", "label": "Cinema"}` to `interest_categories`
  (keeping the existing gastronomy/nature/culture entries first) and add
  top-level key `"city_timezone": "America/Sao_Paulo"` (research R1, R5)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Configuration reader, migration and persistence layer shared
by ALL user stories

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T002 [P] Add `resolved_city_timezone()` to
  `src/passanorte_back/core/config.py`: reads the `city_timezone` key from
  the location file (env override field `city_timezone` mirroring
  `city_name`), validates it with `zoneinfo` raising `LocationDataError`
  for a missing/empty/unknown timezone; write
  `tests/unit/test_city_timezone.py` FIRST (happy path, env override,
  invalid key → error, file without the key → error) and follow
  test→fail→implement→green (research R5); tests isolate the location file
  (fixture writes a tiny temp JSON via the `LOCATION_DATA_PATH` env
  override — T001's `config/location.json` change is not a dependency)
- [X] T003 Create Alembic migration
  `migrations/versions/20261102_0004_tourist_spots.py` creating the three
  tables of `specs/007-tourist-spots-management/data-model.md` §2 verbatim:
  `tourist_spots` (name VARCHAR(200) NOT NULL, description VARCHAR(2000)
  NOT NULL, latitude FLOAT NOT NULL, longitude FLOAT NOT NULL, status
  VARCHAR(20) NOT NULL DEFAULT 'open', removed_at TIMESTAMP NULL indexed,
  created_at/updated_at TIMESTAMP NOT NULL), `tourist_spot_categories`
  (spot_id FK ON DELETE CASCADE indexed, category_key VARCHAR(50) NOT NULL
  indexed, UNIQUE (spot_id, category_key)), `tourist_spot_schedule_entries`
  (spot_id FK ON DELETE CASCADE indexed, weekday SMALLINT NOT NULL
  [ISO-8601 1..7], opens_at TIME NOT NULL, closes_at TIME NOT NULL); verify
  `tests/test_migrations.py` stays green
- [X] T004 Create the persistence layer in
  `src/passanorte_back/modules/tourist_spots/repositories/tourist_spots.py`
  exactly mirroring `data-model.md` §1: `TouristSpot` (relationships to the
  two child tables with `cascade="all, delete-orphan"`), `TouristSpotCategory`,
  `TouristSpotScheduleEntry`, plus query helpers: `add_spot`,
  `find_active_by_id`, `list_active` (order by id, `removed_at IS NULL`
  filter), `replace_categories` (delete+insert in one transaction —
  interests precedent), `replace_schedule`; constants
  `STATUS_OPEN="open"`, `STATUS_TEMPORARILY_CLOSED="temporarilyClosed"`,
  `STATUS_PERMANENTLY_CLOSED="permanentlyClosed"` (stored verbatim = JSON
  values, R9), `WEEKDAYS: dict[str,int]` monday=1..sunday=7 (R4)

**Checkpoint**: Foundation ready — user story implementation can now begin

---

## Phase 3: User Story 1 — Administrator manages tourist spots (P1) 🎯 MVP

**Goal**: Full CRUD of spots (create/edit/remove) restricted to
administrators, with soft-delete removal and one audit record per write —
the foundation every other story consumes.

**Independent Test**: Authenticated admin creates a spot (201), reads it
back (200 via PATCH response), removes it (204); anonymous/tourist/employee
are refused (403) on every management action; unknown id → 404; exactly one
audit entry per admin write, zero for refused attempts (SC-004).

### Tests for User Story 1 ⚠️ (write FIRST — must FAIL)

- [X] T005 [P] [US1] Add contract tests to
  `tests/contract/test_tourist_spots.py`: create → 201 with full camelCase
  `SpotView` echo; 403 `authorization_failed` for anonymous, tourist and
  employee on create/edit/remove/listing (SC-006); edit → 200 reflecting
  the new state (partial: submit only `name`, others unchanged — FR-017);
  remove → 204 then spot absent from listing; edit/remove on unknown id →
  404 `resource_not_found`; strict input (unknown key → 422; snake_case key
  → 422); coordinate validation (SC-002): `latitude: 95.0` → 422 and
  `longitude: -181.0` → 422 on create, plus `latitude: 91.0` on an edit →
  422 with the spot unchanged (nothing created/altered); DMS-style
  coordinate string (e.g. `"-22°43'37S"`) → 422 — decimal degrees only;
  audit: exactly one JSON record (via caplog on logger
  `passanorte.audit`) per successful create/edit/remove with
  `action` `tourist_spot.create|update|delete`, `target`
  `tourist-spot:{id}`, actor = admin username, and none for refused
  attempts (R12, SC-004) — use valid catalog keys
  (`["nature"]`) and a one-entry valid schedule (`{"weekday":
  "saturday", "opensAt": "08:30", "closesAt": "17:00"}`)
- [X] T006 [P] [US1] Add integration test
  `tests/integration/test_tourist_spots_lifecycle.py`: admin create → read
  state via edit response → edit name + status → remove → spot invisible
  for follow-up edit/remove (404) — SC-001 happy path in one flow

### Implementation for User Story 1

- [X] T007 [US1] Create DTOs in
  `src/passanorte_back/modules/tourist_spots/schemas/tourist_spots.py` —
  ALL inherit `core.schemas.ApiModel` (camelCase, `extra="forbid"`):
  `SpotStatus` (str-enum with the 3 stored values, R9);
  `SpotScheduleEntryInput` (name: one of `"monday"`..`"sunday"`;
  `opens_at`/`closes_at` `"HH:MM"` strings parsed to `datetime.time` with
  `opens_at` strictly BEFORE `closes_at` — US3 scenario 2);
  `SpotCreateRequest` (`name` 1..200, `description` 1..2000, `latitude`
  float −90.0..90.0, `longitude` float −180.0..180.0 — decimal WGS-84
  only, FR-002; `status` optional → default open at service (FR-008);
  `categories` list[str] min-length 1 unique; `schedule` list min-length 1);
  `SpotScheduleEntryView`; `SpotUpdateRequest` (same fields, ALL optional,
  FR-017); `SpotView` (id, name, description, latitude, longitude, status,
  categories, schedule, createdAt, updatedAt); `SpotListResponse` (items,
  total, page, pageSize); `PublicSpotDetailView` (id, name, description,
  latitude, longitude, status, categories (keys on admin views),
  schedule, events, mapLink) plus `CategoryView {key, label}` used ONLY
  in `PublicSpotDetailView.categories` — labels resolved at read time from
  the configured catalog, orphan stored key → `{"key": <stored>, "label":
  null}` (analysis U1, R1/R3)
- [X] T008 [US1] Implement service flows in
  `src/passanorte_back/modules/tourist_spots/services/tourist_spots.py`:
  `create_spot` (applies FR-008 default status, persists categories +
  schedule verbatim keys/days, audit `tourist_spot.create`);
  `update_spot` partial edit (only provided fields, full re-validation of
  provided categories/schedule lists, audit `tourist_spot.update` only when
  something changed); `remove_spot` (soft delete: sets `removed_at`, audit
  `tourist_spot.delete`); `get_active_spot` (active-only, raises
  `SpotMissingError` → route maps 404); custom error classes
  `SpotMissingError`, `InvalidSpotInputError` (422). Every write emits
  exactly one `core.audit.record_action` (R12)
- [X] T009 [US1] Implement routes in
  `src/passanorte_back/modules/tourist_spots/routes/tourist_spots.py` on
  `MODULE_ROUTERS["tourist_spots"]` (no tag strings anywhere — FR-013):
  `POST ""` → 201 `SpotView`; `PATCH "/{spot_id}"` → 200 `SpotView`;
  `DELETE "/{spot_id}"` → 204; all three depend on `require_admin`
  (spec 002) + `get_session`; map `SpotMissingError`→404,
  `InvalidSpotInputError`→422 (`HTTPException`, unified `ApiError` via
  `core.error_handlers` — FR-014/FR-015)

**Checkpoint**: User Story 1 (MVP) fully works independently — create/
edit/remove with RBAC + audit; US2–US5 add validation depth and reads.

---

## Phase 4: User Story 2 — Categories validated against the configured catalog (P2)

**Goal**: Submitted category keys are checked against
`config/location.json` (≥1, all catalog keys); associations persist and
reads return stored keys verbatim (orphan-safe, R3); catalog extension is
pure data.

**Independent Test**: Create with an unknown key → 422, spot unchanged;
create with `[]` → 422; extend the catalog via config → new key accepted
with zero code change; previously stored key removed from config keeps
returning on reads (Q2/R3).

### Tests for User Story 2 ⚠️ (write FIRST — must FAIL)

- [X] T010 [P] [US2] Add category tests to
  `tests/contract/test_tourist_spots.py`: unknown key (e.g. `"festival"`)
  in create → 422 naming the invalid key, nothing stored; `"categories":
  []` → 422; duplicate keys in one submission (e.g. `["nature",
  "nature"]`) → 422; associations persist: created spot's keys returned
  identically on the edit response; orphan pass-through (Q2/R13): a stored
  category stays returned as-is on admin reads regardless of config (no
  filtering), and on the public detail it carries `label: null` (U1);
  acceptance US2-4: point `LOCATION_DATA_PATH` at a
  temp copy of `config/location.json` with an extra key (fixture) → create
  with that key → 201 with no code change (R1)

### Implementation for User Story 2

- [X] T011 [US2] Implement catalog validation in
  `src/passanorte_back/modules/tourist_spots/services/tourist_spots.py`:
  new `InvalidSpotCategoryError` (→422); on every write of the categories
  attribute, fetch config keys via
  `get_settings().resolved_interest_categories()` (R13 lazy import
  precedent) and reject submissions with 0 entries, unknown keys, or
  in-submission duplicates; repository `replace_categories` persists the
  validated keys — reads pass stored keys through untouched (R3), and the
  public detail resolves labels via
  `get_settings().resolved_interest_categories()` (U1 — orphan key →
  `label: null`)

**Checkpoint**: US1 + US2 work: CRUD with catalog-true categories.

---

## Phase 5: User Story 3 — Per-spot operating schedule validated (P2)

**Goal**: Impossible schedules cannot persist: known weekdays, opening
strictly before closing, ≥1 entry, no overlapping same-day intervals —
disjoint same-day intervals allowed (US3 scenario 4).

**Independent Test**: Submit each invalid schedule shape → 422 with
nothing stored; submit two disjoint intervals for one weekday → both
persist and read back.

### Tests for User Story 3 ⚠️ (write FIRST — must FAIL)

- [X] T012 [P] [US3] Add schedule tests to
  `tests/contract/test_tourist_spots.py`: unknown weekday `"funday"` →
  422; `opensAt == closesAt` → 422 (US3-2); `opensAt` after `closesAt` →
  422; malformed `"8:30"`/`"25:00"` → 422; `"schedule": []` → 422 (US3-6);
  two overlapping intervals on the same weekday → 422 and the spot keeps
  its previous schedule (US3-5); two DISJOINT same-day intervals → 201/200
  and both returned in order (US3-4, SC-003)

### Implementation for User Story 3

- [X] T013 [US3] Implement same-day overlap rejection (pairwise interval
  check per weekday within one submission — service layer, R13): new
  `OverlappingScheduleError` (→422) raised from
  `validate_schedule_entries()` in
  `src/passanorte_back/modules/tourist_spots/services/tourist_spots.py`,
  called on create and on every write of the schedule within `update_spot`
  (rejected edit leaves the stored schedule untouched)

**Checkpoint**: US1+US2+US3 work: CRUD with catalog-true categories and
impossible-schedule-proof writes.

---

## Phase 6: User Story 4 — Status lifecycle with filtering (P2)

**Goal**: New spots default `"open"` (FR-008); any→any status transitions
via ordinary edits; admin listing filtered by `status` and always
paginated/bounded (FR-009, FR-016).

**Independent Test**: Three spots in three statuses: filtered listing
returns only the requested status, unfiltered returns all actives, unknown
status value → 422, pagination params enforced (page ≥1, pageSize
1..100), transitions persist.

### Tests for User Story 4 ⚠️ (write FIRST — must FAIL)

- [X] T014 [P] [US4] Add listing tests to
  `tests/contract/test_tourist_spots.py`: create without `status` →
  response `"status": "open"` (FR-008/US4-1); seed three spots (one per
  status) → filtered `GET ?status=temporarilyClosed` returns exactly that
  one (US4-2); unfiltered `GET` returns all three (US4-3); edit `open` →
  `permanentlyClosed` persists on subsequent read (US4-4); `?status=junk`
  → 422; `page=0` → 422; `pageSize=0`/`pageSize=101` → 422; removed spot
  never appears in listing with any filter (R6)

### Implementation for User Story 4

- [X] T015 [US4] Implement the listing endpoint in
  `src/passanorte_back/modules/tourist_spots/routes/tourist_spots.py` +
  service/repository: `GET ""` (admin only, `require_admin`) with query
  params `status` (optional, validated against the 3-value set → 422),
  `page` (default 1, ≥1) and `pageSize` (default 20, 1..100) → 200
  `SpotListResponse` `{items, total, page, pageSize}` ordered by `id`,
  excluding removed spots (FR-009/FR-016/R11)

**Checkpoint**: US1–US4 work: the administrative panel use case is fully
covered.

---

## Phase 7: User Story 5 — Public detail endpoint for the Passaporte app (P3)

**Goal**: Unauthenticated detail with name, description, categories
(resolved `{key, label}`), schedule, status, events (`[]` this milestone)
and the computed Google Maps link — closed spots still visible; single
`Tourist Spots` tag.

**Independent Test**: Without credentials, `GET /api/v1/tourist-spots/{id}`
returns 200 with every contract element and a `mapLink` matching the
stored coordinates; unknown/removed id → 404; all module endpoints carry
exactly one OpenAPI tag — the registry tag.

*(SC-005 latency (<1 s) is validated manually in the quickstart smoke
(step 7); no load-test infrastructure is built — YAGNI, constitution V.
RNF11's "tempo hábil" is the operative norm.)*

### Tests for User Story 5 ⚠️ (write FIRST — must FAIL)

- [X] T016 [P] [US5] Add public-detail tests to
  `tests/contract/test_tourist_spots.py`: GET without any credentials →
  200 containing `id`, `name`, `description`, `categories`, `schedule`,
  `status`, `events` and `mapLink` (US5-1/SC-005), with categories as
  `{key, label}` objects where labels come from the configured catalog in
  Portuguese (e.g. `{"key": "nature", "label": "Natureza"}` — U1); `mapLink` equals
  `"https://www.google.com/maps/search/?api=1&query=-22.7271,-45.0366"`
  for the seeded coordinates (R10/US5-2); a `temporarilyClosed` spot is
  returned with its visible status (not hidden — US5 body); unknown id →
  404; removed id → 404; `events` is `[]` and not an error (R8/US5 edge);
  orphan stored key on the public detail → `{"key": <stored>, "label":
  null}` (U1/Q2) — seeded via direct repository write in the test;
  OpenAPI sweep: every tourist-spots path in `openapi.json` carries
  exactly the tag `"Tourist Spots"` (FR-013/US5-4 — extend the module's
  assertions, tag registry sweep in `tests/contract/test_openapi_tags.py`
  already guards the registry)

### Implementation for User Story 5

- [X] T017 [P] [US5] Create the events public-service seam
  `src/passanorte_back/modules/events/services/events.py` (and export from
  `modules/events/services/__init__.py`): `list_public_spot_events(session,
  spot_id) -> list` returning `[]`, docstring stating this is the
  events-domain public interface future event data plugs into — consumed
  only through this public service call (constitution rules 3/5, R8)
- [X] T018 [US5] Implement the public route `GET "/{spot_id}"` in
  `src/passanorte_back/modules/tourist_spots/routes/tourist_spots.py` (NO
  auth dependency) → 200 `PublicSpotDetailView` for active spots of any
  status; build `map_link` from stored decimal coordinates per R10 and
  resolve category `{key, label}` objects from
  `get_settings().resolved_interest_categories()` (orphan key → `label:
  null`, U1) in the service (`build_public_detail` calling
  `events.services.list_public_spot_events` via lazy import, R8); unknown/
  removed → 404 (FR-004/R6)

**Checkpoint**: All five user stories independently functional.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Quality gates and documentation for the whole feature

- [X] T019 Run the full validation of `specs/007-tourist-spots-management/
  quickstart.md`: `uv run pytest` (whole suite: contract + integration +
  unit + migration + smoke `test_boundaries.py`), `uv run ruff check`,
  `uv run ruff format --check .` — fix any red gate before completion;
  confirm Swagger UI (`/docs`) groups everything under `Tourist Spots`
- [X] T020 [P] Documentation: update the module structure/dev notes in
  `README.md` (tourist_spots endpoints, config catalog + `city_timezone`
  keys from T001) and verify module docstrings reflect the final flows —
  English code identifiers, Portuguese user content only (principle VI/VII)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies — start immediately (data-only)
- **Foundational (Phase 2)**: T002 ∥ T001 ∥ T003; T004 after T003 (mapped
  columns mirror the migration); blocks ALL user stories
- **US1 (Phase 3)**: after T004 — T007 → T008 → T009 (same module, layered routes→services→repositories); T005/T006 red before T007–T009
- **US2/US3 (Phases 4–5)**: after US1 (they harden the write path US1
  built) — their tests (T010/T012) red first, then T011/T013
- **US4 (Phase 6)**: after US1 (listing rides the created spots; T014 red
  first, then T015)
- **US5 (Phase 7)**: after US1 (reads spots created by it; T016/T017 ∥,
  T018 last)
- **Polish (Phase 8)**: after US1–US5

### Parallel Opportunities

- T001, T002, T003 are fully parallel; T005+T006 and each story's test
  task parallel with its own phase prep
- T010 ∥ T012 ∥ T014 ∥ T016/T017 only in the sense that the FILE test
  additions are story-scoped — test tasks in different stories touch the
  same file (`test_tourist_spots.py`), so sequence them (or append per
  story class)
- US2→US3→US4→US5 have no cross-file implementation conflicts (each adds
  distinct service/route pieces), so a pair could implement US2 (write
  validations) and US5 (read seam) simultaneously after US1

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 + 2 (config data, config reader, migration, repository)
2. Phase 3 (US1 CRUD + RBAC + audit) — **STOP and VALIDATE**: T005/T006
   green; MVP has a working managed catalog of spots
3. Deploy/demo if ready

### Incremental Delivery

- +US2 → catalog-true classification (dashboard-ready data quality)
- +US3 → trustworthy schedules (RF14 fully enforced)
- +US4 → daily administration ergonomics (filter + pagination)
- +US5 → the Passaporte consumer value (public detail + map link, RF27)

## Notes

- All tasks: English identifiers; user data Portuguese (constitution VII);
  every HTTP schema inherits `ApiModel`; no tag strings in route files;
  failures only as `HTTPException` mapped by `core.error_handlers`
- Validate test RED before each implementation task (TDD, constitution III)
- Commit after each task or logical group; specs/007 branch history is
  linear on master per project convention (memory: one commit per feature)
---

## Phase 9: Convergence

- [X] T021 Remove the unused public surface flagged by convergence
  (`unrequested` per plan Project Structure / YAGNI — Constitution V):
  delete the consumer-less `list_spots` wrapper from
  `src/passanorte_back/modules/tourist_spots/services/tourist_spots.py`
  and its `services/__init__.py` export (routes use `list_spots_paged`;
  the planned `list_active` repository helper stays), and delete the
  unused `_token_headers` helper from
  `tests/contract/test_tourist_spots.py`; re-run the module contract +
  integration tests after removal
