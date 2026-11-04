# Research: Passaporte Discovery (013)

**Date**: 2026-11-03 | **Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

All NEEDS CLARIFICATION entries from the plan's Technical Context were
resolved: none remained open — the technical context is fully determined by
the existing stack (Python 3.13 / FastAPI / SQLAlchemy 2.0, spec 002–011).
The research below records the design decisions that the spec left to
planning (clarified sessions 2026-11-03) and verifies them against the
codebase.

## R1 — Where the ranking lives (module placement)

**Decision**: Discovery is a slice of the `tourist_spots` domain:
`modules/tourist_spots/services/discovery.py` (score + feed assembly) and a
new `services/navigation_links.py` (deep-link builders). Endpoints join the
existing `Tourist Spots` router (`core/routers.py` mounts routers per
`DOMAIN_MODULES`; route files never write tag strings — feature 006).

**Rationale**: The spec (clarification Q4, session 2026-11-03) assigns every
endpoint of this feature to the `Tourist Spots` tag; the feed ranks the
module's own aggregate (`TouristSpot`). Creating a fifth module would
violate YAGNI (constitution V) and the tag decision.

**Alternatives considered**: (a) new `discovery` module — rejected: no new
tag allowed, domain already owns the data; (b) ranking inside the routes
layer — rejected: violation of the routes→services layering (constitution
VII).

## R2 — Score formula (single, documented, deterministic)

**Decision** — the canonical formula, all factors normalized to [0, 1]:

```
interest  = |spot_categories ∩ tourist_interests| / |spot_categories|
            (spots are never category-less — spec 007 R; no interests
            selected ⇒ tourist_interests = ∅ ⇒ interest = 0 for every
            spot, order-preserving neutrality)
proximity = clamp(1 - d / MAX_DISTANCE_KM, 0, 1)
            d = Haversine km between tourist position and spot location
            (no position sent ⇒ proximity = NEUTRAL_PROXIMITY (0.5)
            constant for every spot — FR-005)
event     = BOOST_MIN + (1 - BOOST_MIN) * max(0, 1 - days/event_window_days)
            days = distance in days from today to the spot's nearest
            future event (occurrence_date ≥ today); days > window ⇒ the
            BOOST_MIN floor; no future event ⇒ event = 0 (FR-001; past
            events never counted)
score     = W_PROXIMITY * proximity + W_INTEREST * interest + W_EVENT * event
```

**Defaults (Settings, env-overridable, hierarchy per clarification Q1)**:
`DISCOVERY_W_PROXIMITY=0.5`, `DISCOVERY_W_INTEREST=0.35`,
`DISCOVERY_W_EVENT=0.15`, `DISCOVERY_MAX_DISTANCE_KM=10`,
`DISCOVERY_EVENT_WINDOW_DAYS=30`, `DISCOVERY_EVENT_BOOST_MIN=0.25`,
`DISCOVERY_NEUTRAL_PROXIMITY=0.5`. Weights stay in `Settings` (constitution
VI — configuration, not code), validated to be positive and to sum to 1.

**Tie-break (FR-003)**: equal `score` ⇒ order by `name` ascending
(case-insensitive Unicode comparison), then `id` ascending. No time- or
randomness-dependent component ever enters the sort key.

**Rationale**: Proximity dominance follows clarification Q1 (proximity >
interests > events); normalization to [0, 1] keeps weights meaningful and
the formula re-derivable by a reader (FR-002). The interest ratio uses the
spot's category count as denominator so large-category spots are not
inflated. `clamp` keeps Haversine tail values from going negative.

**Alternatives considered**: distance-decay exponential
(`exp(-d/τ)`) — rejected: harder to explain/audit for a stakeholder-facing
score; raw distance sort — rejected: ignores the three-factor formula
mandated by RF26.

## R3 — Query strategy, O(n) budget, indexing (RNF12/FR-012)

**Decision**: one indexed query loads all active spots once per request
(`removed_at IS NULL AND status != 'permanently_closed'`, FR-007
visibility), scoring and sorting happen in-process, then the page slice is
taken. Sorting 1,000 rows is sub-millisecond; the per-request cost is
O(n log n) — strictly under the spec budget of "no worse than O(n) per
page" for a mobile-plausible n (SC-006 = 1 s @ ≈1,000 rows leaves
≈3 orders of magnitude of headroom). The future-event dates come from one
indexed events query (already indexed on `occurrence_date`, migration 0005)
grouped by `spot_id`; interests come from one indexed query per tourist.
**No cache in v1** (constitution V; spec assumption says a configurable
cache may be *later* attached — the settings toggle exists but the
implementation starts off).

**Indexes**: migration `20261103_0008_spot_discovery_index.py` adds
`ix_tourist_spot_status_active` — a partial index on
`tourist_spots(status) WHERE removed_at IS NULL` (SQLite and PostgreSQL
both support partial indexes). No other index changes needed; the events
table already carries `ix_events_occurrence_date` and a `spot_id` index.

**Alternatives considered**: SQL-side scoring — rejected: Haversine in SQL
is dialect-specific (SQLite/Postgres mismatch, spec 010 RNF17 dual
environment) and the constitution mandates YAGNI; database-agnostic Python
scoring keeps one formula. Cache-first — rejected: premature.

## R4 — Deep links: Google Maps / OSM, Uber, 99 (RF28, RNF18)

**Decision** — pure string builders in `services/navigation_links.py`
(unit-testable, no network):

- **Map provider** (`DISCOVERY_MAP_PROVIDER` = `google_maps` | `osm`,
  default `google_maps` per spec 007 continuity):
  - Google Maps (existing `build_map_link` format kept for destination-only,
    extended with direction context):
    `https://www.google.com/maps/dir/?api=1&destination={lat},{lng}&origin={lat},{lng}`
    (destination-only when origin absent, matching the existing
    `build_map_link` contract).
  - OSM: `https://www.openstreetmap.org/directions?engine=fossgis_osrm_car&route={lat1},{lng1};{lat2},{lng2}`
    (destination-only becomes a `&to={lat},{lng}` target).
- **Uber**: `https://m.uber.com/ul/?action=setPickup&pickup[latitude]={lat}&pickup[longitude]={lng}&dropoff[latitude]={lat}&dropoff[longitude]={lng}`
  (universal link; opens web fallback when the app is missing).
- **99**: `99taxi://ride?pickupLatitude={lat}&pickupLongitude={lng}&dropLatitude={lat}&dropLongitude={lng}`
  (public app scheme — free, RNF15; documented that a web fallback is
  unavailable without a paid partner key).

**Rationale**: All three targets are free, publicly documented, coordinate
preserving (SC-004 exactness — decimal WGS-84 in ⇒ same decimals out).
Provider swap by configuration alone (FR-011/SC-007) is satisfied because
the builders are selected by a Settings lookup, not by branching code
paths in the routes.

**Alternatives considered**: 99 web universal URL — rejected: no official
free coordinate-parameter web link exists; paid partner deep links —
rejected (RNF15).

## R5 — Public seams added / reused (constitution rule 3)

**Decision**:
- `tourists`: reuse the existing `interests.list_tourist_interest_keys`
  service path (public module service; returns clean `list[str]` keys —
  not the wire schema) to read the authenticated tourist's selection.
- `events`: add one public service function
  `list_upcoming_event_dates(session, from_date) -> list[tuple[int, date]]`
  returning `(spot_id, nearest_future_event_date)` pairs — a read-only
  explicit seam, mirroring the established `list_public_spot_events` seam
  pattern (feature 007 contract).
- No module internals (models, repositories, wire schemas of other domains)
  are imported anywhere (monitored by `core/boundaries.py`, feature 001).

**Rationale**: Read-only cross-domain access must go through owner public
service functions (constitution "Regras que decorrem disso §3/§5");
both seams cost one function each, no tables shared.

## R6 — Auth surface (spec 002/003)

**Decision**: both endpoints use `Depends(require_tourist)` — identical to
the visitation routes (spec 011 research). Admin/employee tokens receive
the standard forbidden `ApiError`. Coordinates are validated decimal
WGS-84 by the request model (Pydantic ge/le bounds), so invalid queries are
rejected with 422 `ApiError` before scoring (FR-014).

## R7 — Wire contract additions (camelCase `ApiModel`)

**Decision** — additive, camelCase, `extra="forbid"`:
- `GET /api/v1/tourist-spots/discover?latitude=&longitude=&page=&pageSize=`
  → `items[]` (id, name, description, latitude, longitude, status,
  categories[], `relevanceScore`, `upcomingEventDate`, `mapLink`) + paging
  envelope (page, pageSize, totalItems, totalPages). Query keys camelCase
  (`pageSize`) per the ApiModel alias generator.
- `GET /api/v1/tourist-spots/{id}/navigation-links?latitude=&longitude=`
  → `{ origin, mapLink, uberLink, ninetyNineLink }` (`origin` = the
  lat/lng actually used as pickup, making the fallback self-documenting,
  FR-010/US2-AS3).
- Existing `GET /api/v1/tourist-spots/{id}` public detail gains additive
  `uberLink` + `ninetyNineLink` fields (origin = the spot itself, per
  FR-008 extension of the spec 007 contract). The existing
  `map_link` field is preserved (backward-compatible additive change;
  contract tests of 007 keep passing).

Full shapes: [contracts/tourist-spots-discovery.md](contracts/tourist-spots-discovery.md).

## R8 — Test strategy (constitution III; spec acceptance criteria)

**Decision**:
- **Contract** (`tests/contract/`): feed ordering cases (with-interests vs
  without, no position, with vs without future events — each asserting both
  order and the `relevanceScore` values derived from the documented
  formula); temporarily-closed included with visible status; permanently
  closed absent; 422 on invalid coordinates; 403 for non-tourist token;
  beyond-last page = empty; camelCase wire keys end-to-end.
- **Unit** (`tests/unit/`): score formula (weights, neutral factors, clamp,
  event saturation floor), tie-break determinism (repeat calls → identical
  order), each deep-link builder byte-exact.
- **Integration** (`tests/integration/`): authenticate → set interests →
  discover → navigate (full flow), pagination walk with
  zero-duplicates/zero-omissions across all pages (SC-005).
- **Perf**: `tests/perf/test_feed_budget.py` — StaticPool harness seeded
  with the 1,000-spot dataset; each of 5 pages called once, wall-clock
  asserted < 1 s per page (SC-006). Race/condition proofs are not needed
  (read-only feature); the StaticPool caveat memory still applies to how
  the harness seeds the dataset.

## R9 — Settings & config surface (constitution VI)

**Decision**: discovery knobs live in `core/config.py` `Settings` with
`.env` overrides (`DISCOVERY_*` keys above + `DISCOVERY_MAP_PROVIDER`);
`config/location.json` is untouched (city data, not policy). Settings
validator keeps weights positive and summing to 1 to fail fast at startup
(same refusal-to-start philosophy as spec 002 for missing secrets).