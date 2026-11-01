# Data Model: 004-docker-compose-dev-env

Phase 1 output. This feature introduces **no business data** — its entities are
the runtime artifacts of the containerized development environment. No database
tables are added or changed (FR-018): the schema of the PostgreSQL database is
owned entirely by the existing `migrations/versions` chain of specs 001–003.
This document formalizes the entities' fields, lifecycle and validation rules.

## Entities

### 1. API Image (`passanorte-back:<tag>` built from `Dockerfile`)

What it represents: the reproducible, secret-free runtime artifact of the API.

| Attribute | Constraint / rule |
|---|---|
| Base (build) | `python:3.13-slim` + `ghcr.io/astral-sh/uv` (pinned minor) — research D1/D2 |
| Base (runtime) | `python:3.13-slim` — no build toolchain in the final layer |
| Dependency source | `pyproject.toml` + `uv.lock` only, `uv sync --frozen --no-dev` |
| Workdir layout | `/app/{src, migrations, config}` + `/app/.venv` + `alembic.ini` |
| Processed user | non-root `app` (UID/GID 1000) — FR-002 |
| Exposed port | `8000` (declared; published as `${API_PORT:-8000}`) — FR-003/FR-010 |
| Secrets embedded | **exactly zero** (FR-004/FR-016; SC-006 inspection gate) |
| Entrypoint | `alembic upgrade head` → `exec uvicorn ... --port 8000` (D3); non-zero exit aborts startup |
| State transitions | `created → running (migrations → serving)` or `exited (non-zero, migration/dependency failure)` |

Relations: built once per code/lockfile change (`--build`), consumed by the
`api` service; not persisted volume state.

### 2. Compose Environment (the `compose.yaml` deployment)

What it represents: the coordinated local development stack — the three
services and their wiring.

| Attribute | Constraint / rule |
|---|---|
| Services | `db`, `api`, `dbgate` — exactly these three (FR-006) |
| Startup order | `db` healthy (pg_isready) → `api` (migrations → uvicorn, `service_healthy` gate) → `dbgate` independent (FR-007/FR-008) |
| Configuration source | single local `.env` (never committed), composed from `environment:` + `env_file:`; compose-level substitution resolves variables (FR-014; D7/D8) |
| Published host ports | `API_PORT:-8000`, `DBGATE_PORT:-8080` — configurable (FR-010) |
| Missing `.env` | fail fast with a message pointing to `.env.example` (Edge Case; FR-015) |
| `down` semantics | removes containers/network; named volume persists (US-2/FR-012) |
| `down -v` semantics | explicit purge — documented, the only data-destroying path |

Relations: `api` depends on `db`; `dbgate` depends on `db` (same network,
same credentials).

### 3. Data Volume (named, host-independent storage of `db`)

What it represents: persistent PostgreSQL storage decoupled from container
lifecycle.

| Attribute | Constraint / rule |
|---|---|
| Mount point | `/var/lib/postgresql` (postgres 18 layout — research D6) |
| Lifecycle | independent of containers: survives `down`, destroyed only by `down -v` (FR-012) |
| Contents | all of specs 001–003 schema (via migrations) + user-created data |
| Idempotency rule | on restart, `upgrade head` applies only pending migrations (FR-013) |
| Creation | automatic on first `up` (fresh volume) |

Relations: single source of persistence for `db`; `api` reads/writes through
its DATABASE_URL; `dbgate` browses read/write via its preloaded connection.

### 4. Environment Variable Contract (`.env` local / `.env.example` committed)

What it represents: the single configuration surface. Full field list lives in
[contracts/runtime-contracts.md](contracts/runtime-contracts.md) (D7/D8/D11).
Key validation rules:

| Rule | Constraint |
|---|---|
| Commitment | `.env.example` versioned (FR-015); `.env` ignored by `.gitignore` (exactly `.env`, research D10) |
| Required by app | `DATABASE_URL`, `JWT_SECRET`, `SENSITIVE_DATA_KEY` — no defaults (spec 001 FR-012); example supplies valid non-production values (D11) |
| Required by `db` | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` |
| Required by `dbgate` | same POSTGRES_* triple + `DBGATE_PORT` |
| Optional | `API_PORT` (default 8000), `ADMIN_USERNAME`/`ADMIN_PASSWORD` (used only by the optional `create-admin` step, FR-020) |

### 5. Existing domain tables (not part of this feature — reference)

`baseline`, `auth_accounts` (admin users, RBAC, employees), `tourists`
(tourist profile + interests) per `migrations/versions/20261030_0001` →
`20261031_0003`. Verified present (SC-003) via DbGate or psql; no fields,
state transitions or relationships are touched here.

## State / lifecycle summary

```text
first up:   .env present → db created+healthy → volume created →
            api image built (multi-stage) → alembic upgrade head (fresh chain) →
            uvicorn serving → /health 200
restart:    down (containers/net gone, volume kept) → up →
            db healthy → upgrade head (no-op on applied chain) → /health 200
purge:      down -v → volume destroyed → next up starts from a fresh volume
```