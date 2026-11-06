# HTTP Contract: Notifications (015-interest-notifications)

Module `notifications` · prefix `/api/v1/notifications` · tag
`Notifications` (assigned only at `core/routers.py`, spec 006). All
endpoints are tourist-exclusive (`auth.services.require_tourist` — FR-001):
401 anonymous · 403 admin/employee/tourist-mismatch. Every response schema
inherits `core.schemas.ApiModel` (camelCase, `extra="forbid"` — spec 005);
every failure path uses the unified `ApiError` payload.

Common validation: subscription keys outside the city catalog → 422 naming
the invalid key (FR-005).

---

## 1. Subscription selection (RF37, Q1)

`GET /api/v1/notifications/subscriptions`

`200` — `SubscriptionsResponse`:

```json
{ "categoryKeys": ["gastronomy", "nature"] }
```

`PUT /api/v1/notifications/subscriptions`

Request `SubscriptionsUpdateRequest`: `{ "categoryKeys": ["gastronomy"] }`
— replaces the WHOLE selection (FR-004, same pattern as profile interests);
order-preserving dedupe; idempotent per key (unique constraint).

`200` — same shape as GET.

`DELETE /api/v1/notifications/subscriptions/{category_key}`

(Path variable stays snake_case in code per the spec-011 URL precedent — the published OpenAPI path is authoritative.)

Idempotent cancel (FR-006): canceling a non-subscribed key returns 200 with
the remaining selection. Unknown key in catalog terms is allowed only if it
is not subscribed — a catalog-invalid key is 422 (validation happens before
cancel for consistency with PUT).

`200` — `SubscriptionsResponse` (remaining selection).

## 2. Delivery — list, count, mark (RF37 polling, Q4/Q5)

`GET /api/v1/notifications?onlyUnread=true`

| Param        | Values            | Default | Notes                              |
| ------------ | ----------------- | ------- | ---------------------------------- |
| `onlyUnread` | `true` · `false`  | `true`  | false = full history with states   |

`200` — `NotificationsResponse`:

```json
{ "unreadCount": 2, "items": [
    { "id": 9, "itemType": "event", "itemId": 3,
      "title": "Novo evento: Festival de Peixes",
      "description": "Peixes típicos no centro...",
      "createdAt": "2026-11-06T12:00:00Z", "readAt": null }
] }
```

- Ordered most-recent first (`createdAt DESC, id DESC`), fixed limit 50
  (Q4); `unreadCount` = total unread of the tourist regardless of the
  filter/limit.

`GET /api/v1/notifications/unread-count`

`200` — `UnreadCountResponse`: `{ "unreadCount": 2 }` (cheap polling probe, Q5).

`POST /api/v1/notifications/{notificationId}/read`

- Idempotent (FR-013): marking an already-read notification keeps the FIRST
  `readAt`; returns the notification view (200) with the same body shape of
  the list items.
- 404 when the notification does not exist OR belongs to another tourist
  (isolation — no existence leak).

`POST /api/v1/notifications/read-all`

`200` — `UnreadCountResponse` (always `{"unreadCount": 0}`).

## 3. OpenAPI/tag wiring (FR-002)

- All seven routes declared on `MODULE_ROUTERS["notifications"]` — single
  `Notifications` tag from the central registry; `tests/contract/test_openapi_tags.py`
  keeps passing.

---

## Error responses (uniform, spec 005)

| Scenario                                        | Status | `ApiError` (`errorCode`)     |
| ----------------------------------------------- | ------ | ------------------------------ |
| No bearer token                                 | 401    | authentication_failed          |
| Admin/employee session (tourist-only module)    | 403    | authorization_failed           |
| Subscription with catalog-invalid key (PUT)     | 422    | request_error (422 taxonomy)   |
| Cancel/subscribe catalog-invalid key            | 422    | request_error                  |
| Unknown notification id / another tourist's     | 404    | resource_not_found             |
| Unknown path param shape                        | 422    | validation_error               |

## Emission seam (module-to-module, not HTTP)

Documented in data-model.md §3 — emitters call
`notifications.services.create_interest_notification(...)` (best-effort
savepoint, notified-count return). No HTTP involved; boundaries AST-gated.
