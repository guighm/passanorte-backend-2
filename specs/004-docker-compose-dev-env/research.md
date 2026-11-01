# Research: 004-docker-compose-dev-env

Phase 0 output — resolves every technical decision left open by the spec. The
spec itself carried **no** `[NEEDS CLARIFICATION]` markers; the items below are
technology-selection decisions delegated to planning (spec sections: "decisões
de implementação de plano"). Constitution context: YAGNI (V), English-only
artifacts (VII), no secrets in images (II).

## D1 — Base images and version pinning

**Decision**: build stage `python:3.13-slim` (matches `requires-python =
">=3.13"` and `uv_build` backend); runtime stage `python:3.13-slim`; uv copied
into the build stage from `ghcr.io/astral-sh/uv:<minor>` (pin the minor version
that produced `uv.lock` — 0.9.x per `uv_build>=0.12.5` era of the lockfile).
PostgreSQL: official `postgres:18-alpine`. DbGate: `dbgate/dbgate` with an
explicit tag pinned at implementation time (latest stable at build, e.g. `:6`).

**Rationale**: `python:3.13-slim` is the base officially recommended by uv docs
for minimal runtimes and keeps the image free of build toolchains; `postgres:18`
is the current stable major of the official image (alpine variant = smallest
footprint for dev tooling); pinning majors/minors prevents silent runtime drift
while still taking security patches.

**Alternatives considered**: `python:3.13-alpine` (musl/`psycopg[binary]` wheel
compatibility friction — rejected); `python:latest`/unpinned tags
(non-reproducible — rejected); `ubuntu + deadsnakes` (heavier, needless for
dev-only env). The exact `dbgate` tag and `uv` minor tag are set as a task
parameter — the plan decision is "pin the current stable tag, never `latest`".

## D2 — uv dependency sync in the build stage

**Decision**: `COPY pyproject.toml uv.lock` → `uv sync --frozen --no-dev` →
`COPY . .` → final copy of `/.venv` + project files into the runtime stage.
Dev group (`pytest`, `ruff`) is excluded from the image.

**Rationale**: `--frozen` refuses to drift from `uv.lock` (reproducible build,
SC-001); a single `uv sync` populates the venv **and** performs an editable
install of the project itself (uv build backend) so `passanorte_back` imports
resolve inside the venv. Layering lockfile before `COPY . .` preserves the
dependency cache layer (SC-008's fast rebuilds).

**Alternatives considered**: `uv export > requirements.txt` + pip (loses
uv-native resolution, extra moving part — rejected); `uv pip install --system`
(no venv isolation in image — rejected); full `uv sync` including dev group
(bloats runtime with test tooling — rejected).

## D3 — Runtime layout and entrypoint

**Decision**: runtime stage receives
`/.venv` → `/app/.venv`, plus `src/`, `alembic.ini`, `migrations/`, `config/`;
`WORKDIR /app`; `ENV VIRTUAL_ENV=/app/.venv PATH=/app/.venv/bin:$PATH`;
`CMD ["uvicorn", "passanorte_back.main:app", "--host", "0.0.0.0", "--port",
"8000"]`. Entrypoint script (in-repo, `docker/entrypoint.sh`):
`alembic upgrade head` then `exec "$@"` — the entrypoint must consume the CMD
(or a compose `command:` override) instead of hardcoding uvicorn, so the
development override `--reload` (research D4) still runs after the migrations
gate. `alembic.ini` already resolves `script_location = migrations` relative
to workdir.

**Rationale**: `alembic` and `uvicorn` live in `/app/.venv/bin` — no uv needed
at runtime. Migrations-before-serve satisfies FR-008(v); if `upgrade head`
fails, the script exits non-zero and the container stops (spec Edge Case:
API never serves green over a failed migration). `exec` hands PID 1 to uvicorn
so SIGTERM/`docker compose stop` shuts down cleanly.

**Alternatives considered**: `uv run` in runtime (would force uv into the
slim image — rejected); separate `migrate` compose service (extra orchestration
surface, spec explicitly prefers a single compound entrypoint — rejected); app
`lifespan` migrations (violates spec FR-008(v)'s "before uvicorn" — rejected).

## D4 — Hot reload (clarification Session 2026-10-31, FR-019)

**Decision**: `compose.yaml`'s `api` service bind-mounts `./src:/app/src` and
overrides the command with `uvicorn ... --reload`. The editable install inside
the venv points at `/app/src`, so the mount swaps in host code transparently;
the image's own baked `src/` remains the real runtime for `--build` starts.

**Rationale**: reload watcher runs in-container over the bind; no image rebuild
on Python edits (FR-019). `--host 0.0.0.0` already used by the project's own
`dev.py`.

**Alternatives considered**: Docker volumes/named volume sync tools (native
bind mounts are sufficient on Linux hosts — rejected); mounting `tests/` too
(unneeded, tests stay host-side per SC-009 note).

## D5 — Non-root user

**Decision**: create user/group `app` (UID/GID 1000) in the runtime stage via
`useradd`; `chown -R` copies; `USER app` in both runtime and build
(ownership fixed before copy where possible); bind mount stays readable as the
container user aligns with a typical host UID (host files remain writable on
Linux when host UID == 1000; noted in quickstart).

**Rationale**: FR-002 + constitution Principle II; hardens the image against
accidental writes to system paths.

**Alternatives considered**: root with `--user` override in compose (runtime
convenience only, image remains root-default — rejected per FR-002); matching
UID from a build arg (adds a knob with no spec requirement — YAGNI, rejected;
documented workaround: `user: "1000:1000"` per developer if needed).

## D6 — PostgreSQL 18 data directory

**Decision**: named volume mounted at `/var/lib/postgresql` in `db`
(postgres:18 official image keeps its data set in `/var/lib/postgresql/...`;
the compose mount covers the parent so `down`/`up` reuse works); healthcheck:
`pg_isready -U $POSTGRES_USER -d $POSTGRES_DB` with interval ~5 s, retries ≥ 5,
start period ≥ 30 s.

**Rationale**: postgres 18 changed the default PGDATA layout; mounting the
parent directory is the documented pattern and guarantees state across
containers (US-2). Healthcheck gates `api` via `service_healthy` (FR-008(iv)).

**Alternatives considered**: legacy `/var/lib/postgresql/data` mount (would
silently split PGDATA on 18 — rejected after checking image docs);
`init.sql`-based wait loops in `api` (healthcheck is the spec-mandated
mechanism — rejected).

## D7 — DATABASE_URL wiring and precedence

**Decision**: `.env.example` documents
`DATABASE_URL=postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}`
(expandable in the developer's local file; psycopg 3 dialect — driver already in
`pyproject.toml`). The `api` service **also** declares
`environment: DATABASE_URL: postgresql+psycopg://...@db:5432/...` built by
Compose variable substitution from the same `.env` values, which takes
precedence over `env_file` — so the compose network address always wins
(hostnames like `localhost` in a hand-edited `$DATABASE_URL` cannot break
in-container resolution, matching FR-008(iii) "compose address wins, other
values come from `.env`").

**Rationale**: `pydantic-settings` reads `.env`/environment; explicit
`environment:` in compose satisfies FR-008(iii) without editing the app.
`postgresql+psycopg://` is the SQLAlchemy dialect for psycopg 3; the plain
`postgresql://` scheme defaults to psycopg 2 — not a dependency here, so the
explicit dialect avoids a runtime surprise at first connect.

**Alternatives considered**: relying on `$DATABASE_URL` from `env_file`
(fragile: one typo breaks resolution with no compose-level guard — rejected);
URL rewriting in app code (touches `src/` — violates FR-018, rejected).

## D8 — DbGate preconfigured connection

**Decision** (corrected 2026-10-31 after live verification): the `dbgate`
service receives the connection as **per-connection environment variables** —
the only format the image (7.3.3) actually parses:

```yaml
environment:
  CONNECTIONS: passanorte
  LABEL_passanorte: PassaNorte PostgreSQL
  ENGINE_passanorte: postgres@dbgate-plugin-postgres
  SERVER_passanorte: db
  PORT_passanorte: 5432
  USER_passanorte: ${POSTGRES_USER}
  PASSWORD_passanorte: ${POSTGRES_PASSWORD}
  DATABASE_passanorte: ${POSTGRES_DB}
```

**Rationale**: DbGate reads `CONNECTIONS` as a list of connection IDs; each
field comes from its own `ENGINE_[id]`/`SERVER_[id]`/... variable (per the
official docs at docs.dbgate.io). The **JSON-in-one-variable** form originally
proposed (and requested verbatim in the feature input) is **not accepted** by
the image — a live run logged `DBGM-00006 Invalid CONNECTIONS configuration,
missing ENGINE for connection ID` because DbGate splits the value by commas and
treats each fragment as a connection ID. The corrected format logged
`DBGM-00005 Using connections from ENV variables` with the connection parsed
intact. The requirement outcome is unchanged: preloaded connection at
`localhost:8080`, zero typing (US-3/SC-004). Spec FR-009 was updated to
document this correction (the `postgres@dbgate` engine id from the input maps
to `postgres@dbgate-plugin-postgres` in 7.x).

**Alternatives considered**: JSON array in a single `CONNECTIONS` variable
(requested in the feature input — rejected: image logs `DBGM-00006`, no usable
preloaded connection); `envsubst` sidecar templating (extra moving part —
rejected; compose substitution is built-in); DbGate's internal user/password
store volume (manual configuration — violates the no-typing requirement).

## D9 — Ports on the host

**Decision**: defaults `api` 8000→8000 and `dbgate` 8080→8080; map as
`${API_PORT:-8000}:${INTERNAL}` style with defaults declared in
`.env.example` (`API_PORT`, `DBGATE_PORT`) so conflicts resolve by editing
`.env` only (FR-010). Postgres port stays unpublished on the host by default
(spec assumption); DbGate is the intended explorer (US-3). Exposing it later is
a one-line `.env`/compose change — documented, not built in (YAGNI).

**Rationale**: meets FR-010 without adding a per-service port table to the
spec; keeps `compose.yaml` free of hardcoded numbers that would clash with
local services.

**Alternatives considered**: fixed hardcoded ports (no conflict relief —
rejected); publishing `5432` by default (spec assumption says no — rejected).

## D10 — `.gitignore` adjustment (FR-015)

**Decision**: replace the glob `.env.*` with an exact `.env` entry while
keeping `*.db`/`*.sqlite3`; `.env.example` becomes committed. One-line diff,
no code impact.

**Rationale**: current `.gitignore` has `.env.*` which would also ignore
`.env.example` — violating FR-015 (example must be versioned). Pattern keeps
local environment files out while making the documented example visible in the
checkout.

**Alternatives considered**: `!.env.example` negation after `.env.*`
(also valid, but the explicit narrow pattern `.env` is clearer and avoids
relying on negation order in gitignore rules).

## D11 — Secrets in the local dev `.env`

**Decision**: `.env.example` ships non-production placeholder values for
**all** required settings (`DATABASE_URL`, `POSTGRES_USER`, `POSTGRES_PASSWORD`,
`POSTGRES_DB`, `JWT_SECRET`, `SENSITIVE_DATA_KEY`, `ADMIN_USERNAME`,
`ADMIN_PASSWORD`, `API_PORT`, `DBGATE_PORT`) clearly marked with comments as
"local development only — never for production".

**Rationale**: `Settings` in `core/config.py` treats `database_url`,
`jwt_secret`, `sensitive_data_key` as required with no defaults
(FR-012 of spec 001) — omitting any of them fails `create_engine`/startup, so
the example must supply a valid non-production value for each. `ADMIN_*` are
included because FR-020 documents the optional `create-admin` step via
`docker compose exec api` — the script reads `ADMIN_USERNAME`/`ADMIN_PASSWORD`
from env only (spec 002). `sensitive_data_key` (RNF08, LGPD encryption key for
CPF/passport/phone/email) is Fernet-like → a 32-byte URL-safe base64 example
with a note on regeneration (e.g. `python -c "from cryptography.fernet import
Fernet; print(Fernet.generate_key().decode())"`).

**Alternatives considered**: leaving JWT/crypt keys blank and failing at first
startup (contradicts FR-012's "documented default" intent and the 5-minute
SC-001 onboarding window — rejected); real-looking but weak placeholders
(accepted, since this is dev-only by constitution and by assumptions).

## D12 — No-op on `src/`, `migrations/`, `tests/`

**Decision**: zero diff expected under those trees; existing pytest suite is
the regression gate (SC-009). All feature files live at repo root / docs.

**Rationale**: FR-018 hard constraint; smoke of "unchanged" is a `git diff`
check recorded in the quickstart.

**Alternatives considered**: none (hard spec constraint).