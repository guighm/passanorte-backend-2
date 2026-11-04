# Contracts: Tourist Spots — Discovery (013)

**Date**: 2026-11-03 | **Spec**: [spec.md](spec.md)

All response/request wire shapes are camelCase `ApiModel` (`extra="forbid"`,
snake_case and unknown keys rejected with 422). Every failure path emits the
unified `ApiError` payload `{ errorCode, message, details }`. Both endpoints
require an authenticated tourist session (`require_tourist`); any other
token (none, employee, admin) gets `403 { "errorCode": "forbidden" }`.
All endpoints live under the `Tourist Spots` tag (no new tag).

Common query validation (422 `ApiError`): out-of-range coordinates
(`latitude` ∉ [‑90, 90], `longitude` ∉ [‑180, 180]), non-integer paging.

---

## 1. `GET /api/v1/tourist-spots/discover`

Ranked, paginated discovery feed (RF26). Query parameters:

| Param | Type | Required | Notes |
|---|---|---|---|
| `latitude` | number | no | valid WGS-84 if present |
| `longitude` | number | no | valid WGS-84 if present |
| `page` | int ≥ 1 | no | default 1 |
| `pageSize` | int 1–100 | no | default 20 (camelCase alias) |

**200 Response**:

```json
{
  "items": [
    {
      "id": 12,
      "name": "Mirante do Vale do Paraíba",
      "description": "…",
      "latitude": -22.4968,
      "longitude": -45.0086,
      "status": "open",
      "categories": [
        { "key": "nature", "label": "Natureza" }
      ],
      "relevanceScore": 0.812,
      "upcomingEventDate": "2026-11-15",
      "mapLink": "https://www.google.com/maps/search/?api=1&query=-22.4968,-45.0086"
    }
  ],
  "page": 1,
  "pageSize": 20,
  "totalItems": 137,
  "totalPages": 7
}
```

Contract rules (traceable to spec FR/SC):

1. Ordering = `relevanceScore` desc → `name` (case-insensitive) asc →
   `id` asc (FR-003). Repeated identical requests return identical order.
2. Permanently closed spots never appear; temporarily closed spots appear
   with their own `status` value (`"temporarily_closed"`) — FR-007.
3. No position sent ⇒ every item's score is computed with the neutral
   proximity constant (FR-005); the response shape does not change.
4. Tourist without interests ⇒ every item scored with interest factor 0 —
   request succeeds, no error (FR-006).
5. `upcomingEventDate` is the spot's nearest future event date or `null`
   (past events never appear — FR-001).
6. `relevanceScore` present on every item (FR-002 clarification).
7. Pagination: page beyond the last → 200 with `"items": []` (edge case).
8. `status: "permanently_closed"` never occurs in `items`.

**422** (validation failure contract, unified `ApiError`) — invalid
coordinates or paging bounds; **403** — non-tourist token.

---

## 2. `GET /api/v1/tourist-spots/{id}/navigation-links`

Ready-to-open navigation links for one spot (RF28/FR-009). Query
parameters: `latitude`, `longitude` (optional, valid WGS-84 if present).

**200 Response**:

```json
{
  "origin": { "latitude": -22.4901, "longitude": -45.0001 },
  "mapLink": "https://www.google.com/maps/dir/?api=1&destination=-22.4968,-45.0086&origin=-22.4901,-45.0001",
  "uberLink": "https://m.uber.com/ul/?action=setPickup&pickup[latitude]=-22.4901&pickup[longitude]=-45.0001&dropoff[latitude]=-22.4968&dropoff[longitude]=-45.0086",
  "ninetyNineLink": "99taxi://ride?pickupLatitude=-22.4901&pickupLongitude=-45.0001&dropLatitude=-22.4968&dropLongitude=-45.0086"
}
```

Contract rules:

1. `origin` echoes the pickup coordinates actually used: the provided
   position, or the spot's own coordinates when none was sent (FR-010 —
   the fallback is self-documenting; US2-AS3).
2. All three links carry the spot's exact coordinates as destination
   (SC-004 — no precision loss, no origin/destination swap).
3. `mapLink`'s target follows the configured provider (`google_maps`
   default or `osm`), with same status codes and shape either way
   (FR-011/SC-007).

**404** (`ApiError`, `resource_not_found`) — unknown/removed spot;
**422** — invalid coordinates; **403** — non-tourist token.

---

## 3. Additive extension: `GET /api/v1/tourist-spots/{id}` (existing, spec 007)

The existing public detail response gains two additive fields (FR-008):

```json
{
  "id": 12,
  "…existing 007 fields unchanged…": "…",
  "mapLink": "https://www.google.com/maps/search/?api=1&query=-22.4968,-45.0086",
  "uberLink": "https://m.uber.com/ul/?action=setPickup&pickup[latitude]=-22.4968&pickup[longitude]=-45.0086&dropoff[latitude]=-22.4968&dropoff[longitude]=-45.0086",
  "ninetyNineLink": "99taxi://ride?pickupLatitude=-22.4968&pickupLongitude=-45.0086&dropLatitude=-22.4968&dropLongitude=-45.0086"
}
```

Origin falls back to the spot itself (no request position exists in the
detail route). Additive only — every existing field and existing 007
contract expectation is preserved.

---

## Errors summary

| Scenario | Status | `errorCode` |
|---|---|---|
| No bearer token (unauthenticated) | 401 | `authentication_failed` (plain 401 shape) |
| Authenticated but not a tourist (admin/employee) | 403 | `authorization_failed` |
| Invalid coordinates or paging | 422 | `validation_error` |
| Unknown or removed spot (links route) | 404 | `resource_not_found` |
| Unknown paging param shape | 422 | `validation_error` |

Exact message text follows the unified `core.error_handlers` mapping used
by the existing tourist-facing modules (authentication precedes RBAC, as in
every other tourist-exclusive route).