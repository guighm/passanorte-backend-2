# Quickstart: Dashboard e Insights (014-dashboard-insights)

Validation scenarios for the five admin-only metrics (RF06–RF10, RF03,
SC-001..SC-007). Artifacts referenced, never duplicated:
[data-model.md](data-model.md), [contracts/dashboard.md](contracts/dashboard.md).

## Prerequisites

- Python 3.13 environment with the project dependencies installed via the
  project's `uv` workflow (`uv sync` — `pyproject.toml`; run tests with
  `uv run pytest`).
- Synthetic test env provided by `tests/conftest.py` (in-memory SQLite,
  fixed `JWT_SECRET`/`SENSITIVE_DATA_KEY`) — never real credentials.
- For migration/quick manual validation: a database reachable via
  `DATABASE_URL` with `JWT_SECRET` and `SENSITIVE_DATA_KEY` set; an admin
  account from `create-admin` (RF01).

## Automated validation (the acceptance criteria of the spec)

```bash
# Window/granularity/anchor math: today/week/month, ranking windows, city-tz day bucket
pytest tests/unit/test_dashboard_windows.py -q

# Region parsing + centroid from location data (RNF06, rejeição quando ausente)
pytest tests/unit/test_dashboard_regions.py -q

# Contract: camelCase schemas, status codes (401/403/404/422), ApiError, one Dashboard tag
pytest tests/contract/test_dashboard_metrics.py -q

# RBAC gate: admin OK, employee → 403, tourist → 403 em todos os cinco endpoints (RF03, SC-005)
pytest tests/contract/test_dashboard_metrics.py -k rbac -q

# End-to-end: tourists from distinct countries/interests + seed visitations + access events;
# validates the five endpoints against expected values (SC-001..SC-004, SC-007)
pytest tests/integration/test_dashboard_metrics_flow.py -q

# Access recording: tourist-authenticated requests (incl. public endpoints) →
# access_events rows; counter per period (FR-007/FR-008, SC-002)
pytest tests/integration/test_access_events_flow.py -q

# Performance budget (SC-006): five aggregates × < 2 s on 10k visits + 50k accesses
pytest tests/perf/test_dashboard_budget.py -q

# Schema change (0009), best-effort failure of recording, boundaries, tags
pytest tests/test_migrations.py tests/smoke/test_boundaries.py tests/contract/test_openapi_tags.py -q
```

All green ⇒ the spec's acceptance criteria are satisfied by construction.

## Manual smoke against a running API

```bash
# 1. Apply migrations (creates access_events — data-model.md §1)
alembic upgrade head

# 2. Admin session
curl -s -X POST localhost:8000/api/v1/employees/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"<admin>","password":"<admin-password>"}'
# → { "accessToken": "...", "refreshToken": "..." }
ADMIN=...

# 3. Five metric queries (contracts/dashboard.md for exact shapes)
curl -s -H "Authorization: Bearer $ADMIN" \
  'localhost:8000/api/v1/dashboard/heatmap?groupBy=spot'
curl -s -H "Authorization: Bearer $ADMIN" \
  'localhost:8000/api/v1/dashboard/heatmap?groupBy=region'
curl -s -H "Authorization: Bearer $ADMIN" \
  'localhost:8000/api/v1/dashboard/access-counts?period=today'
curl -s -H "Authorization: Bearer $ADMIN" \
  'localhost:8000/api/v1/dashboard/spot-ranking?granularity=month&limit=5'
curl -s -H "Authorization: Bearer $ADMIN" \
  'localhost:8000/api/v1/dashboard/visitor-countries'
curl -s -H "Authorization: Bearer $ADMIN" \
  'localhost:8000/api/v1/dashboard/visitor-interests'
```

- Expected: 200 with the shapes of `contracts/dashboard.md`, every number
  agreeing with the stored rows (admin can cross-check via
  `SELECT tourist_spot_id, COUNT(*) FROM visitations GROUP BY 1;`).
- Negative probes: repeat any call with an **employee** token → 403;
  `?period=custom` without dates → 422 `ApiError`;
  `?groupBy=region` on an install without `regions` in location data → 422.
- Note: access metrics only reflect requests **after** the migration is
  applied (no backfill — research R8).
