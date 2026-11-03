# Data Model: Geo-Visitation (011-geo-visitation)

Date: 2026-11-03. Ownership follows the modular-monolith constitution
(rule 4): each table below is owned by exactly one module; cross-module
touchpoints are read-only references or public service functions.

## 1. New entity — `Visitation` (owner: `visitation` module)

Table `visitations` — the immutable visitation ledger (spec FR-006,
Q1/Q7). Append-only: no update/delete path exists anywhere in the module.

| Field | Type | Rules | Origin |
|-------|------|-------|--------|
| `id` | Integer PK | autoincrement | server |
| `tourist_id` | Integer, NOT NULL, **indexed** | read-only reference into `tourists.id`; existence validated at write time (R7) | authenticated tourist (== `user.account_id`) |
| `tourist_spot_id` | Integer, NOT NULL, **indexed** | read-only reference into `tourist_spots.id`; only active spots are markable | request path |
| `visited_at` | DateTime, NOT NULL | server-side UTC (`datetime.now(UTC)`, R8); index for history ordering | server |
| `latitude` | Float, NOT NULL | decimal WGS-84 (−90..90), schema-validated (FR-013), cleartext (Q7) | request |
| `longitude` | Float, NOT NULL | decimal WGS-84 (−180..180), schema-validated, cleartext | request |

**Uniqueness**: intentionally **no** unique constraint on
`(tourist_id, tourist_spot_id)` — repeated valid visits append additional
rows (spec Edge Cases, Q5 no-throttle).

**Derived state (not stored)**: "spot visited by tourist" ==
`EXISTS(visitations WHERE tourist_id = ? AND tourist_spot_id = ?)` (Q1 —
derived from history, the immutable ledger is the single source of truth).
"First visitation" == `MIN(visited_at)` over the pair.

**Relationships**: `tourist_id`/`tourist_spot_id` are plain indexed
columns with FKs (same pattern as gamification's read-only references,
migration 0006 header) — no ORM relationships across module boundaries.

## 2. Modified entity — `TouristSpot` (owner: `tourist_spots` module)

One nullable column added by migration `0007_visitation`:

| Field | Type | Rules |
|-------|------|-------|
| `tolerance_radius_m` | Float, NULL | optional per-spot override of the presence radius, in meters, must be positive when present; `NULL` ⇒ use `settings.gps_tolerance_radius_m` (100 m default, Q2/R2) |

Admin CRUD surface gains it as optional `toleranceRadiusM` (spec 005
camelCase): accepted in `SpotCreateRequest`/`SpotUpdateRequest`, echoed in
views. Existing data/backfill: none required (NULL = global default).

## 3. Untouched tables read by this feature

- `tourists.id` (tourists module) — existence check via public
  `get_tourist_account`; no writes.
- `tourist_spots` rows (tourist_spots module) — read via public
  `get_active_spot` (404 when missing/removed/inactive); no writes from
  visitation.
- `gamification` tables (`spot_visits`, `route_enrollments`, `spot_visits`
  ledger, badges, codes) — **never touched by visitation**; progress flows
  only through the `register_spot_visit` seam (R3), whose result
  (`VisitRouteOutcome`) is consumed for the response DTOs.

## 4. State transitions

`Visitation` rows have no lifecycle (immutable). The observable state
"visited" is a projection:

```text
absent pair   →  first valid mark  →  visited (progress seam fires once)
visited       →  further valid marks  →  +1 history row (no progress call)
any mark      →  haversine > radius  →  409, structured log, nothing persisted
```

## 5. Validation rules summary

- Coordinates: finite numbers, WGS-84 ranges, checked by schema before any
  distance math (FR-013; 422).
- Radius: `> 0` (spot override) and settings already validate `> 0`
  (`core/config` validator — verified).
- Spot must be active (`get_active_spot`, else 404).
- Tourist must exist (`get_tourist_account`, else 404).
- Distance: `haversine(GPS, spot) <= effective_radius` else 409 + log.