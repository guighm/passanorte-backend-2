# Contract: Events (feature 008)

Source of truth: `spec.md` (FR-001..FR-014) + clarifications of session
2026-11-02 and `research.md` (R1–R12). Companion of
`contracts/camelcase-json.md` (spec 005) — convention rules and the unified
error schema apply unchanged.

All endpoints mount on the canonical router
(`MODULE_ROUTERS["events"]`, prefix `/api/v1/events`) and carry the single
central-registry tag **`Events`** (`core/tags.py`); no route file writes a
tag string (spec 008 FR-013). Every failure path answers the unified
`ApiError` payload. Every endpoint in this contract is **admin-only**
(`require_admin`, spec 002); the public consumption of events is the
existing tourist spot detail endpoint (spec 007, RF27 — §4 here).

## 0. Shared conventions

- JSON keys camelCase; request bodies strict (`extra="forbid"`, no
  snake_case keys → 422).
- `ticketPrice`: JSON number with at most 2 decimal places, ≥ 0; `0`
  means free (stored as exact integer cents — R1).
- `occurrenceDate` / `startDate` / `endDate`: ISO calendar dates,
  `"YYYY-MM-DD"`; range bounds are **inclusive**; no timezone semantics
  (R11).
- Error codes ⇄ statuses (per `camelcase-json.md` §2):
  `validation_error`→422 (shape failures via the generic
  `RequestValidationError` path), `request_error`→422 (service semantic
  validations — `startDate > endDate`), `authorization_failed`→403,
  `resource_not_found`→404, `conflict`→409 (spot permanently closed —
  the message names the cause, R2).
- Listing order: `(occurrenceDate, id)` ascending; **no pagination** in
  this version (spec 008 assumption).

## 1. POST /api/v1/events — create (admin) → 201

Request (`EventCreateRequest`):

```json
{
  "spotId": 42,
  "occurrenceDate": "2026-12-08",
  "description": "Festival de luzes no mirante com apresentação local.",
  "ticketPrice": 15.50
}
```

- `spotId`: existing, **not permanently closed** spot id.
- `description` 1..2000 (Portuguese user content).
- `ticketPrice`: ≥ 0, ≤ 2 decimal places, magnitude ≤ 9999999999.99
  (Integer-cent storage, data-model §1 — exact monetary amount); `0` — free.

Responses:

| Status | When | Body |
|---|---|---|
| 201 | created | `EventView` |
| 422 | shape violations (unknown/snake_case keys, negative or >2dp price, malformed/missing date, empty/oversized description) | `ApiError` `validation_error` |
| 404 | `spotId` does not exist (or spot removed) | `ApiError` `resource_not_found` |
| 409 | `spotId` points to a permanently closed spot | `ApiError` `conflict`, message names the cause |
| 403 | non-admin session (tourist/employee) | `ApiError` `authorization_failed` |
| 401 | anonymous caller (no credentials) | `ApiError` `authentication_failed` (auth precedent, spec 002) |

## 2. GET /api/v1/events — administrative filtered listing (admin) → 200

Query parameters (all optional, combinable — clarifications session
2026-11-02):

```
?spotId=42&startDate=2026-12-01&endDate=2026-12-31
```

- `spotId` alone → FR-007 (per-spot listing).
- `startDate`/`endDate` alone → FR-008 (date range, inclusive bounds).
- Combined → FR-008 + optional spot filter (single endpoint serves both).

Responses:

| Status | When | Body |
|---|---|---|
| 200 | — | `EventListResponse` — `{"items": [EventView…], }` in `(occurrenceDate, id)` order; empty `items` when nothing matches |
| 422 | `startDate > endDate` (`request_error`, service-semantic) or malformed query values (`validation_error`) | `ApiError` |
| 404 | `spotId` filter does not exist | `ApiError` `resource_not_found` (mirrors creation, spec edge case) |
| 403 | non-admin caller | `ApiError` `authorization_failed` |

## 3. PATCH /api/v1/events/{eventId} — edit (admin) → 200 / DELETE → 204

Request (`EventUpdateRequest`) — **all fields optional**, partial edit
(007 FR-017 precedent). Body example:

```json
{ "occurrenceDate": "2026-12-15", "ticketPrice": 0 }
```

Patch rules:

- Omitted fields stay unchanged; empty patch = no-op 200, **no audit**
  record (007 `update_spot` precedent).
- Providing `spotId` re-runs the full existence (404) and
  non-permanently-closed (409) validation against the **new** target spot;
  on refusal the event keeps its previous state.
- `event.update` audit record fires when at least one field changed.

`DELETE /api/v1/events/{eventId}` (admin) → `204 No Content`, physically
removes the row, fires `event.delete` audit record. Responses for both:

| Status | When |
|---|---|
| 200 / 204 | success (edit / delete) |
| 404 | `eventId` unknown or already removed; also 404 on patched `spotId` unknown |
| 409 | patched `spotId` permanently closed |
| 422 | shape violations of provided fields |
| 403 | non-admin caller |

### EventView (all read paths — create response, edit response, listings)

```json
{
  "id": 17,
  "spotId": 42,
  "occurrenceDate": "2026-12-08",
  "description": "Festival de luzes no mirante com apresentação local.",
  "ticketPrice": 15.50
}
```

Round-trip guarantee (SC-005): `ticketPrice` returns the exact submitted
amount in every read path (create response, patch response, listings, and
public embedding).

## 4. Public embedding — GET /api/v1/tourist-spots/{spotId} (spec 007, RF27)

The existing public (unauthenticated) tourist spot detail embeds, in its
`events` array, the events of that spot as produced by the events module's
public service (`list_public_spot_events` — resolved at read time, 007
data-model). Item shape (camelCase dicts — R8):

```json
{
  "id": 17,
  "spotId": 42,
  "occurrenceDate": "2026-12-08",
  "description": "Festival de luzes no mirante…",
  "ticketPrice": 15.50
}
```

- Ordered `(occurrenceDate, id)`; spots with no events render `[]` (never
  an error).
- Permanently closed spots keep rendering their embedded events as long as
  the rows exist — visibility follows spec 007 rules (closed spots stay
  publicly visible; rows cease to exist only at spot removal, R4).
- No event-management operation is publicly reachable through this seam.

## 5. Audit trail (RNF19)

Exactly one `core.audit.record_action` JSON line per successful write,
with the acting admin as `actor`:

| action | target | detail (non-exhaustive) |
|---|---|---|
| `event.create` | `event:{id}` | `spotId`, `ticketPrice` |
| `event.update` | `event:{id}` | changed fields summary |
| `event.delete` | `event:{id}` | — |

No audit record for the cascade deletes executed by
`remove_spot`/`delete_spot_events` — the audit trail of a spot removal is
the `tourist_spot.delete` record (the action belongs to the spot domain).