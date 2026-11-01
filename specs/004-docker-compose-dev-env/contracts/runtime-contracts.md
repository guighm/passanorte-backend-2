# Runtime Contracts: 004-docker-compose-dev-env

Phase 1 output. The business REST API contract is **unchanged** by this feature
(FR-018) — `GET /health` keeps its existing semantics (200 `{status, database}`
or 503 `{degraded, unavailable}`) and every `/api/v1` route stays as
implemented. What this feature introduces are **runtime contracts** between the
new artifacts themselves — the obligations each artifact fulfils toward the
others. These define acceptance for the tasks phase.

## Contract 1 — The image (what `Dockerfile` promises)

Toward the `api` service, whoever starts a container from this image is
entitled to:

| Promise | Verification hook |
|---|---|
| `alembic upgrade head` runs before port 8000 serves HTTP | quickstart V2 |
| uvicorn serves `passanorte_back.main:app` on `0.0.0.0:8000` | quickstart V2 |
| process runs as non-root `app` (UID 1000) | quickstart V7 |
| image contains no `.env`, no credential value, no `.venv`-less toolchain (uv/pytest/ruff absent) | quickstart V7 |
| dependencies come exclusively from `uv.lock` (`--frozen`) | quickstart V7 |
| exits non-zero when migrations fail | quickstart V5 scenario (manual check) |

## Contract 2 — The compose file (what `compose.yaml` promises)

| Promise | Verification hook |
|---|---|
| `up` (with `--build`) brings up `db` + `api` + `dbgate`; `db` healthy gates the `api` start | quickstart V1 |
| `api` gets `DATABASE_URL` addressed to service `db` (compose-environment value takes precedence over the `env_file` copy) | quickstart V2 |
| `dbgate` publishes `${DBGATE_PORT:-8080}` and carries the preloaded connection (per-connection env vars `CONNECTIONS: passanorte` + `ENGINE_/SERVER_/USER_/PASSWORD_/DATABASE_passanorte` — server `db`, engine `postgres@dbgate-plugin-postgres`, credentials from `POSTGRES_*` via compose substitution; see research D8 correction) | quickstart V3 |
| `down` preserves the named volume; `down -v` destroys it | quickstart V4 |
| fresh volume → only pending migration entries exist (idempotency) | quickstart V4 step 4 |

## Contract 3 — Environment variables (the single configuration surface)

Every variable the three services consume; example values in `.env.example` are
placeholders — never production secrets.

| Variable | Consumer | Required | Default / example policy |
|---|---|---|---|
| `POSTGRES_USER` | `db`, `dbgate`, `api` (via DATABASE_URL) | yes | non-production placeholder (e.g. `passanorte`) |
| `POSTGRES_PASSWORD` | `db`, `dbgate`, `api` (via DATABASE_URL) | yes | non-production placeholder — **must change locally** |
| `POSTGRES_DB` | `db`, `dbgate`, `api` (via DATABASE_URL) | yes | e.g. `passanorte` |
| `DATABASE_URL` | `api` (pydantic-settings), Alembic | yes | `postgresql+psycopg://${POSTGRES_USER}:...@db:5432/${POSTGRES_DB}` — service address `db` for the containerized run |
| `JWT_SECRET` | `api` (required by spec 001 FR-012) | yes | non-production placeholder, e.g. `dev-only-jwt-secret-change-me` |
| `SENSITIVE_DATA_KEY` | `api` (required by spec 001 FR-012 — LGPD RNF08) | yes | Fernet-format key generated locally; the example shows how (`cryptography.fernet.Fernet.generate_key()`) |
| `JWT_TTL`, `JWT_REFRESH_TTL`, `GPS_TOLERANCE_RADIUS_M` | `api` (defaults already in code) | no | defaults 3600 / 604800 / 100.0 — example may uncomment to override |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | `create-admin` script only (FR-020, opt-in) | only for that step | non-production placeholder |
| `API_PORT` | compose (host port of `api`) | no | 8000 |
| `DBGATE_PORT` | compose (host port of `dbgate`) | no | 8080 |

Invariants:

1. `.env` is the only file holding credentials locally; it is never committed
   (`.gitignore` matches exactly `.env`) and never copied into the image.
2. `.env.example` documents **every** row above with a non-production value
   that the app accepts at startup (no blanks for the required trio) —
   "SC-007: copy alone is sufficient".
3. Compose substitution is the mechanism by which `POSTGRES_*` values reach
   both the `db` container and the `dbgate` connection variables — the same
   trio configures all three services.
4. Renaming `POSTGRES_DB`/`POSTGRES_USER` after a volume exists requires a
   documented re-initialization (`down -v`) — Postgres initializes the volume
   from those variables once (noted in quickstart for the README's FAQ).

## Contract 4 — Validation commands (what `quickstart.md` promises)

The quickstart scenarios V1–V7 map 1:1 to the spec's success criteria
SC-001–SC-009; each is runnable by hand or as a scripted smoke and its
expected outcome is written in observable terms (HTTP status, container state,
volume presence, file diff). See [quickstart.md](../quickstart.md) for the
executable version.