# Contract: Tourist Spots (feature 007)

Source of truth: `spec.md` (FR-001..FR-017) + clarifications Q1–Q3 and
`research.md` (R1–R14). Companion of `contracts/camelcase-json.md` (spec
005) — convention rules and the unified error schema apply unchanged.

All endpoints mount on the canonical router
(`MODULE_ROUTERS["tourist_spots"]`, prefix `/api/v1/tourist-spots`) and
carry the single central-registry tag **`Tourist Spots`** (`core/tags.py`);
no route file writes a tag string (FR-013). Every failure path answers the
unified `ApiError` payload (FR-014).

## 0. Shared conventions

- JSON keys camelCase; request bodies strict (`extra="forbid"`, no
  snake_case keys — 422).
- `status` value set (stored verbatim): `"open"` | `"temporarilyClosed"`
  | `"permanentlyClosed"` (R9).
- Weekdays: `"monday"` … `"sunday"` (JSON) ↔ ISO 1..7 (stored, R4).
- Times: `"HH:MM"` 24-h, pure wall-clock, city-timezone semantics
  (clarification Q3; `city_timezone` in `config/location.json`, R5).
- Categories: canonical catalog **keys** on administrative views
  (`"gastronomy"`, `"nature"`, `"culture"`, `"leisure"`, `"art"`,
  `"cinema"` by default — R1/R2). The **public detail** resolves each key
  to `{key, label}` at read time from the configured catalog (labels are
  Portuguese user content, principle VI) so the anonymous Passaporte
  consumer can render it without a second endpoint; an orphan stored key
  (clarification Q2) returns `{"key": <stored>, "label": null}`.
- Error codes ⇄ statuses: per `camelcase-json.md` §2
  (`validation_error`→422, `authorization_failed`→403,
  `resource_not_found`→404). Nuance: 422s raised from **schema/parsing
  shape** failures surface as `validation_error` (the generic
  ``RequestValidationError`` path), while 422s raised from **service
  semantic validations** (unknown/duplicated category key, overlapping
  intervals, unknown status) use a plain ``HTTPException`` and therefore
  surface as `request_error` — same status, unified payload, per the
  global mapping (employees precedent).
- RBAC: admin-only via `require_admin` (spec 002) on POST/GET list/PATCH/
  DELETE; the single-spot detail is public (RF27).

## 1. POST /api/v1/tourist-spots — create (admin) → 201

Request (`SpotCreateRequest`):

```json
{
  "name": "Mirante Pedra do Bauzinho",
  "description": "Mirante com vista para o vale e trilha curta.",
  "latitude": -22.7271,
  "longitude": -45.0366,
  "status": "temporarilyClosed",
  "categories": ["nature", "leisure"],
  "schedule": [
    { "weekday": "saturday", "opensAt": "08:30", "closesAt": "17:00" },
    { "weekday": "saturday", "opensAt": "18:00", "closesAt": "21:00" }
  ]
}
```

- `name` 1..200; `description` 1..2000 (Portuguese user content).
- `latitude` ∈ [−90, 90], `longitude` ∈ [−180, 180] — decimal degrees
  only (FR-002; any out-of-range/incompatible-numeric input → 422,
  SC-002).
- `status` optional — omitted ⇒ `"open"` (FR-008).
- `categories`: 1..N unique catalog keys (`[]`/missing/unknown key → 422,
  FR-006/R13).
- `schedule`: 1..N entries; `opensAt` strictly before `closesAt`; no
  overlapping intervals on the same weekday; ≥1 entry (FR-007, US3).
- Unknown weekday / malformed `"HH:MM"` → 422.

Response 201 (`SpotView`): administrative view of the stored spot:

```json
{
  "id": 1,
  "name": "Mirante Pedra do Bauzinho",
  "description": "Mirante com vista para o vale e trilha curta.",
  "latitude": -22.7271,
  "longitude": -45.0366,
  "status": "temporarilyClosed",
  "categories": ["nature", "leisure"],
  "schedule": [
    { "weekday": "saturday", "opensAt": "08:30", "closesAt": "17:00" },
    { "weekday": "saturday", "opensAt": "18:00", "closesAt": "21:00" }
  ],
  "createdAt": "2026-11-02T12:00:00Z",
  "updatedAt": "2026-11-02T12:00:00Z"
}
```

Failures: 403 (`authorization_failed`) anonymous/tourist/employee
(SC-006), 422 (`validation_error`) with per-key details. **Audit**:
`tourist_spot.create` (R12).

## 2. GET /api/v1/tourist-spots — administrative paginated listing (admin) → 200

Query parameters: `status` (optional; one of the three values — anything
else → 422), `page` (optional, ≥1, default 1), `pageSize` (optional,
1..100, default 20 — FR-016/R11).

Response 200 (`SpotListResponse`): `{ "items": [SpotView, …],
"total": <int>, "page": <int>, "pageSize": <int> }` — `items` ordered by
`id`; filtered by `status` when present; **removed spots never included**
(R6); unfiltered returns every active status (US4 scenario 3).

Failures: 403, 422 (bad filter/pagination values).

## 3. GET /api/v1/tourist-spots/{spotId} — public detail (no auth) → 200

Response 200 (`PublicSpotDetailView`) — exactly the elements RF27/US5
require (plus id/name for navigation):

```json
{
  "id": 1,
  "name": "Mirante Pedra do Bauzinho",
  "description": "Mirante com vista para o vale e trilha curta.",
  "latitude": -22.7271,
  "longitude": -45.0366,
  "status": "temporarilyClosed",
  "categories": [
    { "key": "nature", "label": "Natureza" },
    { "key": "leisure", "label": "Lazer" }
  ],
  "schedule": [
    { "weekday": "saturday", "opensAt": "08:30", "closesAt": "17:00" }
  ],
  "events": [],
  "mapLink": "https://www.google.com/maps/search/?api=1&query=-22.7271,-45.0366"
}
```

- Returned for any active spot in any status — closed spots are visible
  with their status (spec US5); removed/unknown → 404 (FR-004/R6).
- `mapLink` computed at read time from stored decimal coordinates, never
  stored (FR-012/R10).
- `events`: the events domain's public service result — `[]` in this
  milestone, never an error (R8).
- No credentials accepted or required.

Failures: 404 (`resource_not_found`). No 401/403.

## 4. PATCH /api/v1/tourist-spots/{spotId} — partial edit (admin) → 200

Request (`SpotUpdateRequest`): same field set as create, **all optional**
(FR-017). Rules when a field is present: validated exactly as in create
(categories ≥1 valid key; schedule ≥1 valid non-overlapping entry, etc.);
fields omitted stay unchanged (US1 edge case "edits are partial"). Empty
body `{}` → no-op returning the current state.

Response 200 (`SpotView`, full new state). Failures: 403, 404
(unknown/removed), 422 (invalid values — including partial payloads, e.g.
`"categories": []` alone). **Audit**: `tourist_spot.update` when any field
changed (R12).

## 5. DELETE /api/v1/tourist-spots/{spotId} — remove (admin) → 204

Success: 204 no content; the spot leaves listing/public detail; audit
`tourist_spot.delete` (SC-004); removal is reversible at the data level
(soft delete, R6) but not exposed in this milestone.

Failures: 403, 404 (unknown or already removed — idempotent-refused).
Category/schedule rows remain (physical disposal out of scope).

## 6. Status codes summary (SC-007 / acceptance gate)

| Case | Status |
|---|---|
| Create success | 201 |
| Read (list/detail)/edit success | 200 |
| Delete success | 204 |
| Non-admin on any management operation | 403 |
| Unknown/removed target (edit, remove, public detail) | 404 |
| Validation failure (shape, coordinates, catalog, schedule, pagination) | 422 |
| Unexpected failure | 500 (`internal_error`, no internals) |