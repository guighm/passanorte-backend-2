# Quickstart: 004-docker-compose-dev-env

Phase 1 output — runnable validation scenarios. Each scenario (V1–V7) maps to
the spec's success criteria (SC-001–SC-009) and validates the runtime contracts
in [contracts/runtime-contracts.md](contracts/runtime-contracts.md). Commands
below are the acceptance procedure; exact file contents belong to
`tasks.md`/implementation.

## Prerequisites

- Docker Engine with Compose v2 (`docker compose version` works).
- A cloned repository.
- Before first run: `cp .env.example .env` (then edit placeholders if desired —
  the copied values alone are valid for startup: SC-007).

Reference artifacts: [data-model.md](data-model.md) (entities/lifecycle),
[research.md](research.md) (D1–D12 decisions).

## V1 — Full stack from a clean checkout (**SC-001, SC-002, SC-008**)

```sh
cp .env.example .env
docker compose up --build -d
docker compose ps            # all 3: db, api, dbgate → running/healthy
curl -i http://localhost:8000/health   # → HTTP 200, {"status": "ok", "database": "ok"}
```

Expected:

1. `db` reaches `healthy` (`pg_isready` passing) before `api` starts — check
   `docker compose ps` status column or `docker compose logs api` ordering
   (migrations log lines precede uvicorn startup lines).
2. `/health` returns **200** with application **and** database statuses OK.
3. Cold start (clone → healthy stack) measured ≤ **5 minutes** on a typical
   machine (SC-001).
4. **Hot reload (FR-019)**: with the stack up, edit a harmless marker inside a
   file under `src/` (e.g. add a comment) → within seconds `docker compose
   logs api` shows the uvicorn watcher/reload line and the change is live —
   no `--build`, no container restart; revert the marker.
5. Context audit for SC-008: `docker compose build api` output shows no
   context warnings; `docker image inspect` on the built image layer list
   shows no `tests/`, `docs/`, `specs/`, `.git`, `.venv`, `.env`, `*.db`
   entries (see V7 for the image-side check).

## V2 — Migrations applied before serving (**SC-003**, FR-008(v), FR-011)

```sh
docker compose logs api | grep -i alembic      # migration lines precede uvicorn
docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c '\dt'
```

Expected: tables introduced by specs 001–003 exist
(baseline structures, auth/admin/RBAC/employee tables, tourist tables) —
confirm the exact table names against `migrations/versions/` during
implementation; the listing equals what `alembic current` reports.

## V3 — DbGate browsing without typing credentials (**SC-004**, US-3)

Open `http://localhost:8080` in a browser (or `$DBGATE_PORT`).

Expected:

1. DbGate UI loads at the published host port.
2. The connection list already contains **PassaNorte PostgreSQL** (server `db`,
   port 5432, engine `postgres` via the `passanorte` connection env vars) —
   no credential typing.
3. Opening it lists the schemas including the migrated tables (V2's list) and
   their rows; browsing works (US-3 acceptance 1–3).

## V4 — Persistence across down/up and idempotent migrations (**SC-005**, US-2, FR-012/FR-013)

```sh
# seed a data point of an implemented domain (e.g. register a tourist via the
# API or create an employee via the auth/RBAC endpoints); note its identifier
docker compose down                                  # NO -v here
docker compose ps -a --filter name=db                # container removed...
docker volume list | grep <project>_postgres-data    # ...volume kept
docker compose up -d
curl -s http://localhost:8000/health                 # 200 again
docker compose logs api | grep -i alembic            # no re-run of applied chain
# verify the seeded record still exists (browser @ :8080 or HTTP GET)
```

Expected: record survives restart 100% (SC-005); no migration is re-applied
(FR-013). Only `docker compose down -v` (then `up`) starts from an empty
database re-running the full chain.

## V5 — Failure paths behave as specified (spec Edge Cases)

Manual one-time checks:

1. **Missing `.env`**: `mv .env /tmp; docker compose up` → compose errors
   immediately (missing variable interpolation) and/or the README documents
   the required copy step; no half-running stack. Restore `.env`.
   (Complement: app-level failure is covered by spec 001 FR-012 tests.)
2. **Port conflict**: start something on 8000 locally, then `docker compose up
   api` without changing `.env` → bind error naming port 8000; after setting
   `API_PORT=8100` in `.env` and restarting, service is reachable on 8100
   (FR-010).
3. **db down**: `docker compose stop db` → `curl /health` flips to **503**
   with degraded state (existing app semantics, spec 001 FR-009 — verifies
   compose wiring doesn't break it); `docker compose start db` returns it to
   200.
4. **Migration failure**: (optional) corrupt one pending migration, `up` →
   `api` container exits non-zero; `docker compose logs api` shows the alembic
   error; `/health` never returns 200. Revert the change.

## V6 — Business behavior unchanged (**SC-009**, FR-018)

```sh
git diff --stat origin/master..HEAD -- src migrations tests   # expect: empty
uv run pytest                                                 # existing suite: 100% green
uv run ruff check                                             # lint gate passes
```

Expected: no source/migration diffs from the feature; the pre-existing
suite (including boundary checks) passes unmodified — the infra change is
invisible to business code. **Documented exception** (approved during
implementation): `tests/smoke/test_settings_essentials.py` gains empty-CWD
isolation in the two missing-essential tests so a local `.env` (this feature's
dev file, read by pydantic-settings) cannot satisfy them; the tests' original
intent is unchanged (the essential must be absent from ALL sources).

## V7 — Image and repo hygiene (**SC-006, SC-007**, FR-002/FR-004/FR-014)

```sh
docker compose build api
docker run --rm --entrypoint sh <api-image> -c 'whoami; ls -a /app; find / -name "*.env" -o -name ".env" 2>/dev/null'
git status --porcelain                                   # no `.env` staged ever
grep -c ENV_SECRET .env.example                          # example documents all values, none real
```

Expected: `whoami` → `app` (non-root); `/app` listing shows only intended
artifacts (src, migrations, config, .venv, alembic.ini); no `.env` anywhere
in the image; repo tracked files contain no credential values (only
placeholders in `.env.example`); `docker compose exec api env` (when
performing V1–V4) does contain the env values — they arrive at **runtime**
only, never baked.

## Optional — Admin bootstrap (**FR-020**, opt-in)

```sh
docker compose exec api create-admin     # script from spec 002, unchanged; reads ADMIN_* from env
```

Expected: bootstrap admin created/updated in the fresh volume; login via
`/api/v1` works — run **after** V1, only when the tester wants to validate the
auth flow end to end (not required for infra acceptance).

## Cleanup

```sh
docker compose down      # keeps data (V4 behavior)
docker compose down -v   # explicit purge when a fresh start is desired
```