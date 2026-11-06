# HTTP Contract: Dashboard (014-dashboard-insights)

Module `dashboard` · prefix `/api/v1/dashboard` · tag `Dashboard`
(assigned only at `core/routers.py`, spec 006). Every response schema
inherits `core.schemas.ApiModel` (camelCase JSON, `extra="forbid"` — spec
005); every failure path uses the unified `ApiError` payload
(`errorCode`, `message`, `details`). All routes are admin-only
(`auth.services.require_admin`; RF03): 401 anonymous · 403 employee/tourist.

Common query-parameter validation: unknown key → 422; `endDate <
startDate` → 422; out-of-range `limit` → 422 (FR-013).

---

## 1. Heat map (RF06)

`GET /api/v1/dashboard/heatmap`

| Param       | Values                | Default | Notes                                |
| ----------- | --------------------- | ------- | ------------------------------------ |
| `groupBy`   | `spot` · `region`     | `spot`  | `region` requires `regions` in location data (FR-005 → 422 otherwise) |
| `startDate` | ISO date (`YYYY-MM-DD`) | —     | optional window start (inclusive)    |
| `endDate`   | ISO date              | —       | optional window end (inclusive)      |

`200` — `HeatmapResponse`:

```json
{ "markers": [
    { "spotId": 3, "name": "Cachoeira Édem", "latitude": -22.39, "longitude": -44.97, "weight": 12 }
] }
```

- `spot` mode: one marker per spot with ≥1 visit in the window;
  `spotId`/`name` always present.
- `region` mode: one marker per region with ≥1 visit (`spotId: null`,
  `name` = region `label`, coordinate = centroid of the region's spots —
  research R5).

## 2. Access counter (RF07)

`GET /api/v1/dashboard/access-counts`

| Param       | Values                                | Default | Notes                          |
| ----------- | ------------------------------------- | ------- | ------------------------------ |
| `period`    | `today` · `week` · `month` · `custom` | —       | required; `custom` requires both dates |
| `startDate` | ISO date                              | —       | `custom` only (inclusive)      |
| `endDate`   | ISO date                              | —       | `custom` only (inclusive)      |

`200` — `AccessCountsResponse`:

```json
{ "period": "week",
  "uniqueTouristDays": 9,
  "totalAccessEvents": 41,
  "daily": [
    { "date": "2026-11-04", "uniqueTourists": 3, "accessEvents": 15 }
  ] }
```

- `uniqueTouristDays`: distinct tourist×day pairs in the window (FR-010).
- `daily`: one entry per day **with** events (city-tz day), ascending;
  empty window → empty list and zeros (edge case).

## 3. Spot ranking (RF08)

`GET /api/v1/dashboard/spot-ranking`

| Param           | Values                 | Default        | Notes                     |
| --------------- | ---------------------- | -------------- | ------------------------- |
| `granularity`   | `day` · `month` · `year` | —            | required (one window per query — Q3) |
| `referenceDate` | ISO date               | today (city tz) | window anchor            |
| `limit`         | int 1–100              | 5              | top N (FR-013)            |

`200` — `SpotRankingResponse`:

```json
{ "granularity": "month", "referenceDate": "2026-11-06", "items": [
    { "position": 1, "spotId": 3, "name": "Cachoeira Édem", "visits": 27 }
] }
```

- Descending by visits; ties ordered by `spotId` (stable); only spots with
  ≥1 visit in the window (FR-014); removed spots remain ranked (R7).

## 4. Visitor-country distribution (RF09)

`GET /api/v1/dashboard/visitor-countries`

| Param       | Values    | Default | Notes                     |
| ----------- | --------- | ------- | ------------------------- |
| `startDate` | ISO date  | —       | optional population window (inclusive) |
| `endDate`   | ISO date  | —       | optional population window (inclusive) |

`200` — `VisitorCountriesResponse`:

```json
{ "totalVisitors": 8, "items": [
    { "country": "Brasil", "tourists": 5, "share": 62.5 }
] }
```

- Population = tourists with ≥1 visitation in the window (FR-016); empty
  country → item `{"country": "Não informado", "keyCountry": false}` —
  represented at schema level (R6).
- Shares sum to 100 (±0.5 rounding, SC-004); descending by `tourists`.

## 5. Visitor-interest distribution (RF10)

`GET /api/v1/dashboard/visitor-interests`

Same params as §4 (same population — Q5: visitors only).

`200` — `VisitorInterestsResponse`:

```json
{ "totalVisitors": 8, "totalSelections": 13, "items": [
    { "interestKey": "nature", "interestLabel": "Natureza", "tourists": 4, "share": 30.8 }
] }
```

- One item per category key selected by ≥1 visitor; a tourist counts once
  per declared interest (US5); tourists with no interests contribute
  nothing; shares computed over `totalSelections` (may sum >100).
- `interestLabel` from `config/location.json` categories; unknown key →
  label = key.

## 6. OpenAPI/tag wiring (FR-002)

- All five routes are declared on the module router handed by
  `MODULE_ROUTERS["dashboard"]`; `tests/contract/test_openapi_tags.py`
  still passes with every endpoint listed under the single `Dashboard`
  tag.
- Route files never write the tag string (quality gate).

---

## Error responses (uniform, spec 005)

| Scenario                                     | Status | `ApiError` example (`errorCode`)      |
| -------------------------------------------- | ------ | ------------------------------------- |
| No bearer token                              | 401    | authentication required               |
| Employee session (any endpoint in this file) | 403    | permission denied (RF03)              |
| Tourist session                              | 403    | permission denied                     |
| `endDate < startDate`                        | 422    | invalid period                        |
| `period=custom` without dates / unknown `period` | 422 | invalid period                      |
| `groupBy=region` with no regions configured  | 422    | regions unavailable                   |
| `limit=0` / `limit=101` / unknown `granularity` | 422  | invalid parameter                     |
