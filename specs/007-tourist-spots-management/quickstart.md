# Quickstart: Tourist Spots Management (feature 007)

Validation guide proving the feature end-to-end. Implementation and full
test bodies live in `tasks.md` / the implementation phase; this file links
`contracts/tourist-spots.md` (wire contract) and `data-model.md`
(persistence) instead of duplicating them.

## Prerequisites

- Python 3.13 + `uv` (deps of `pyproject.toml`).
- Synthetic environment for local/dev runs (never real secrets):
  `DATABASE_URL` (SQLite file is fine, e.g. `sqlite:///./passanorte-dev.db`),
  `JWT_SECRET`, `SENSITIVE_DATA_KEY` — the app refuses to start without
  them (constitution II).
- `config/location.json` with the extended `interest_categories`
  (gastronomy, nature, culture + leisure, art, cinema) and
  `"city_timezone": "America/Sao_Paulo"` (R1/R5; other cities edit the
  JSON — RNF06).
- An administrator account via `create-admin` (RF01) for admin flows.

## Run

```bash
uv run uvicorn passanorte_back.main:app --reload   # docs at /docs (tag: Tourist Spots)
```

## Test suite (acceptance gate — constitution III)

```bash
uv run pytest tests/contract/test_tourist_spots.py   # contract suite (SC-007)
uv run pytest tests/integration/test_tourist_spots_lifecycle.py
uv run pytest tests/unit/test_city_timezone.py tests/test_migrations.py
uv run pytest tests/smoke/test_boundaries.py         # module boundary gate
uv run ruff check && uv run ruff format --check .    # quality gates
```

Expected: all green — the contract suite covers the spec's acceptance
gate (CRUD 201/200/204/403/404, coordinate validation, schedule
validation, status filtering, public detail content + map link, audit
verification).

## Manual smoke (curl, after `create-admin` + login)

1. **Create (admin)** — `POST /api/v1/tourist-spots` with the body of
   `contracts/tourist-spots.md` §1 → **201** and the JSON echoes the
   stored state (camelCase).
2. **RBAC** — repeat the POST with a tourist/employee token (or none) →
   **403** `authorization_failed`; nothing created.
3. **Listing + filter** — `GET /api/v1/tourist-spots?status=temporarilyClosed`
   (admin) → **200**, only that status, paginated (`page`/`pageSize`).
4. **Schedule validation** — submit `"opensAt": "18:00", "closesAt": "08:00"`
   → **422** `validation_error`; nothing stored (SC-003).
5. **Coordinates** — `latitude: 95.0` → **422**; nothing stored (SC-002).
6. **Audit** — each admin write above emits one
   `passanorte.audit` JSON line with `actor`, `action`
   (`tourist_spot.create|update|delete`), `target` `tourist-spot:{id}`
   (RNF19, SC-004).
7. **Public detail (no auth)** — `GET /api/v1/tourist-spots/{id}` →
   **200** with name/description/categories (`{key, label}`, Portuguese
   labels)/schedule/status/`events: []` and `mapLink` computed from the
   stored coordinates (compare against `data-model.md` §4) — time the
   request; SC-005 expects < 1 s (manual check; no load-test infra,
   YAGNI).
8. **Remove then probe** — `DELETE /api/v1/tourist-spots/{id}` (admin) →
   **204**; repeat the public GET → **404**; the listing no longer
   contains it; audit shows `tourist_spot.delete`.

## Definition of done for the feature

- `tests/contract/test_tourist_spots.py` green (SC-007) plus the lifecycle
  integration test;
- new migration applied cleanly by `tests/test_migrations.py`;
- `ruff check` clean; boundary AST gate green;
- Swagger UI shows all endpoints under the single tag `Tourist Spots`
  (FR-013/US5 scenario 4).