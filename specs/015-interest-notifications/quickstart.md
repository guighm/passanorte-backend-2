# Quickstart: Notificações por Interesse (015-interest-notifications)

Validation scenarios for RF37 (subscribe → match/emission → polling → read)
end-to-end. Artifacts referenced, never duplicated:
[data-model.md](data-model.md), [contracts/notifications.md](contracts/notifications.md).

## Prerequisites

- Python 3.13 environment with the project dependencies via the project's
  `uv` workflow (`uv sync`; run tests with `uv run pytest`).
- Synthetic test env provided by `tests/conftest.py` (in-memory SQLite,
  fixed `JWT_SECRET`/`SENSITIVE_DATA_KEY`) — never real credentials.
- Manual validation: `DATABASE_URL`/`JWT_SECRET`/`SENSITIVE_DATA_KEY` set;
  admin via `create-admin` (RF01); migration `0010` applied (`alembic upgrade head`).

## Automated validation (the acceptance criteria of the spec)

```bash
# Text templates (Q2): per-type composition, PT labels, description cap
pytest tests/unit/test_notification_templates.py -q

# Contract: camelCase shapes, status codes, unified errors, Notifications tag, RBAC 401/403
pytest tests/contract/test_notifications.py -q

# Acceptance flow: subscribe → admin creates event/spot/route with 'gastronomia'
# → notification appears; NO match → nothing; mark-as-read (one/all); unsubscribe
pytest tests/integration/test_notifications_flow.py -q

# Emitter seams: events/008 (spot categories), tourist_spots/007, gamification/009
# (route inherits spots' categories) + best-effort failure never blocks creation
pytest tests/integration/test_notification_emission.py -q

# Migration 0010 round trip + boundaries + tags
pytest tests/test_migrations.py tests/smoke/test_boundaries.py tests/contract/test_openapi_tags.py -q

# Performance budget (SC-005): queries < 2 s with 1,000 tourists × 100 items
pytest tests/perf/test_notifications_budget.py -q
```

All green ⇒ RF37 acceptance criteria + SC-001..SC-006 are satisfied by construction.

## Manual smoke against a running API

```bash
# 1. Migration (creates notification_subscriptions + notifications)
alembic upgrade head

# 2. Tourist session
curl -s -X POST localhost:8000/api/v1/tourists/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"<tourist>","password":"<password>"}'
TOURIST=...

# 3. Subscribe and confirm
curl -s -X PUT localhost:8000/api/v1/notifications/subscriptions \
  -H "Authorization: Bearer $TOURIST" -H 'Content-Type: application/json' \
  -d '{"categoryKeys":["gastronomy"]}'
curl -s localhost:8000/api/v1/notifications/subscriptions -H "Authorization: Bearer $TOURIST"

# 4. (As admin) create a spot/event/route with category 'gastronomia' via the
#    existing endpoints of specs 007/008/009 — then poll:
curl -s localhost:8000/api/v1/notifications/unread-count -H "Authorization: Bearer $TOURIST"
curl -s "localhost:8000/api/v1/notifications?onlyUnread=true" -H "Authorization: Bearer $TOURIST"

# 5. Mark as read and re-check
curl -s -X POST localhost:8000/api/v1/notifications/<id>/read -H "Authorization: Bearer $TOURIST"
curl -s -X POST localhost:8000/api/v1/notifications/read-all -H "Authorization: Bearer $TOURIST"
```

- Expected: shapes per `contracts/notifications.md`; an item whose
  categories do NOT match the subscription produces nothing (negative probe);
  canceling the subscription stops FUTURE notifications (SC-004).
- Staff-token probe on any notifications endpoint → 403 (RF03).
