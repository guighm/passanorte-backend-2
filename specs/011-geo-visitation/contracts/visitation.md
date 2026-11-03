# HTTP Contract: Visitation (011-geo-visitation)

Date: 2026-11-03. All schemas inherit `core.schemas.ApiModel` (spec 005:
camelCase JSON, `extra="forbid"`, no snake_case input); every failure path
emits the unified `ApiError` (`errorCode`, `message`, `details`). All
endpoints ride the module router pre-mounted by `core/routers.py` with the
central tag **`Visitation`** (spec 006) and prefix `/api/v1/visitation`.

Authorization: tourist-exclusive endpoints use `Depends(require_tourist)`
(auth module public dependency; 403 otherwise). For tourists,
`tourist_id == user.account_id` (research R7).

## 1. POST `/api/v1/visitation/spots/{spotId}/visits` — mark visitation (RF31–RF34, US1/US2/US3)

**Request** — `MarkVisitationRequest` (body only; spot comes from the path):

| JSON key | Type | Constraints |
|----------|------|-------------|
| `latitude` | float | decimal WGS-84, −90..90, finite (FR-013) |
| `longitude` | float | decimal WGS-84, −180..180, finite |

**Success — 201** `VisitationMarkedResponse`:

| JSON key | Type | Notes |
|----------|------|-------|
| `id` | int | visitation record id |
| `spotId` | int | |
| `visitedAt` | datetime | server-side UTC (R8), ISO-8601 |
| `latitude` / `longitude` | float | the validated coordinates persisted |
| `firstVisit` | bool | true ⇔ progress seam was invoked (FR-009) |
| `routeOutcomes` | list of `RouteOutcome` | empty when `firstVisit` false or no in-progress enrollment contains the spot |

`RouteOutcome`:

| JSON key | Type |
|----------|------|
| `routeId` | int |
| `completionRate` | int (0–100) |
| `completed` | bool |

**Failures** (unified `ApiError`):

| HTTP | `errorCode` | Trigger |
|------|-------------|---------|
| 401 | `authentication_failed` | missing/invalid token |
| 403 | `authorization_failed` | non-tourist account |
| 404 | `resource_not_found` | spot missing, removed or inactive (`SpotMissingError`); tourist record absent (R7) |
| 409 | `conflict` | valid coordinates with Haversine distance > effective radius (spec FR-004) — message carries the distance detail; plus the structured log of SC-007. Also the unmarkable state (spot row without valid coordinates or effective radius ≤ 0) |
| 422 | `validation_error` | schema violations: unknown snake_case/extra keys, non-finite or out-of-range coordinates (FR-013) |

`errorCode` values follow the unified platform taxonomy of spec 005 §2
(single source of truth in `core.error_handlers`) — no bespoke codes.

Semantics locked by the spec: inclusive border (`distance <= radius`
accepts, research R1); same-transaction consistency of record + progress
(R4); repeat visits append history and return `firstVisit: false` with
`routeOutcomes: []` (FR-009, Q5 no throttle).

## 2. GET `/api/v1/visitation/visitations` — visitation history (US4, FR-010)

Tourist-exclusive (`require_tourist`); returns **the caller's own**
history, newest first, ascending id tiebreak.

**Response — 200** `VisitationListView`:

| JSON key | Type | Notes |
|----------|------|-------|
| `items` | list of `VisitationView` | full immutable history (incl. repeat visits) |

`VisitationView`: `id` (int), `spotId` (int), `visitedAt` (datetime),
`latitude`/`longitude` (float). No cross-module denormalization of spot
names — clients enrich via the tourist-spots public endpoints (keeps the
frontier tight; US4 acceptance needs ids + timestamps only).

## 3. GET `/api/v1/visitation/visited-spots` — visited points projection (US4, FR-010)

Tourist-exclusive. 200 `VisitedSpotsView`: `items` — list of
`VisitedSpotView`:

| JSON key | Type | Notes |
|----------|------|-------|
| `spotId` | int | derived: `EXISTS` any visitation for the pair (Q1 — no status table) |
| `firstVisitAt` | datetime | `MIN(visited_at)` of the pair |
| `visitCount` | int | total immutable rows for the pair |

Empty history ⇒ `items: []` (US4 scenario 2).

## 4. Tourist-spots contract delta (radius management lives in its owner)

`SpotCreateRequest` / `SpotUpdateRequest` gain optional `toleranceRadiusM`
(float > 0, nullable); `SpotView` and public spot views echo it
(`toleranceRadiusM: float | null`). Absent in a PATCH = unchanged
(existing optional-field semantics); explicit `null` = back to global
default. No other spot contract changes.

## 5. OpenAPI metadata

Single tag `Visitation` (central registry, `core/tags.py`), applied only
at the pre-mounted module router; route files never write tag strings.
Tag description gains a Visitation-domain summary line in this feature's
task list (only edit inside `core/tags.py`).