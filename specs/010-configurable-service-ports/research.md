# Research: 010-configurable-service-ports

Phase 0 output — resolves every technical decision left open by the spec. The
spec (and its clarify session) carried **no** unresolved `[NEEDS CLARIFICATION]`.
The items below are technology-selection / mechanism decisions delegated to
planning. Constitution context: YAGNI (V), English-only artifacts (VII),
security by default (II), Portabilidade por Configuração (VI). All facts below
verified against the actual `compose.yaml`, `.env.example`, `Dockerfile` and
`docker/entrypoint.sh` at planning time.

## D1 — How API_PORT becomes end-to-end

**Decision**: single interpolation point in `compose.yaml`, used twice for the
same service — `ports: ["${API_PORT:-8000}:${API_PORT:-8000}"]` and
`command: uvicorn passanorte_back.main:app --host 0.0.0.0 --port
${API_PORT:-8000} --reload`. Compose interpolates `${VAR:-default}` in **all**
string values of the service definition (including `command:`) at config-parse
time, before the entrypoint runs, so the rendered command literal contains the
resolved port — no shell inside the container is needed and `entrypoint.sh`
(`alembic upgrade head` + `exec "$@"`) passes it through untouched.

**Rationale**: host-side and container-side then derive from one variable, so
they can never diverge (the "split-brain" the spec removes — US2). Keeping the
compose-level interpolation also preserves the existing behavior that a
shell-level `API_PORT` env var overrides the `.env`/default (standard Compose
semantics, spec Assumptions).

**Alternatives considered**: a new container env var (e.g.
`UVICORN_PORT`) read by the entrypoint — rejected (touches `entrypoint.sh`,
violates FR-008; one more indirection than needed); hardcoding two variables
(`API_PORT` + `API_PORT_CONTAINER`) — rejected (defeats the single-source
goal); Docker `EXPOSE` change — rejected (metadata only, FR-009).

## D2 — db host exposure and 127.0.0.1 binding

**Decision**: add to the `db` service:
`ports: ["127.0.0.1:${POSTGRES_PORT:-5432}:5432"]` — host interface fixed to
loopback, container port fixed at 5432 (internal, FR-004).

**Rationale**: clarify session (2026-11-03) chose Option A — the new exposure
is the only new attack surface, so it binds to loopback only (SC-005: reachable
via `localhost`, refused via the machine's LAN IP). The internal `5432`
container/port stays hard-coded because inter-service traffic (`DATABASE_URL`
host `db`, DbGate `SERVER_passanorte: db`) never uses the host mapping.

**Alternatives considered**: no binding prefix (Compose default = all
interfaces) — rejected per clarify (dev DB with known password must not appear
on the LAN); dynamic free-port selection — rejected (YAGNI, spec edge case says
conflicts surface as a visible Compose error); publishing 5432 also for
`api`/`dbgate` — out of scope (FR-003a keeps them unprefixed all-interfaces,
existing behavior).

## D3 — Defaults vs `:?required` for port variables

**Decision**: keep the `${VAR:-default}` shape everywhere with defaults 8000,
8080, 5432 (never replace with `${VAR:?required}`).

**Rationale**: spec FR-001 mandates built-in defaults so a fresh
`.env.example`→`.env` copy — or even a missing/misconfigured local `.env` —
still boots the full environment at the agreed ports (US1, edge case "variable
absent"). This mirrors spec 004's split: `:?required` only for credential
variables, `:-default` for non-secret operational ones. `.env.example` will
list the three port variables uncommented with the default values
(non-secret, FR-005, matches existing `API_PORT`/`DBGATE_PORT` convention).

**Alternatives considered**: `:?error` — rejected (breaks zero-config boot);
`.env`-only defaults — rejected (single source of truth would move to a
git-ignored file).

## D4 — Formalizing DBGATE_PORT (no behavior change)

**Decision**: leave `"${DBGATE_PORT:-8080}:3000"` exactly as-is; no edit to the
`dbgate` service beyond documentation/comment upkeep, plus the commented
`DBGATE_PORT` entry already in `.env.example` (and `POSTGRES_PORT` as the only
new addition).

**Rationale**: spec US3 is "formalization only" (FR-003a keeps the existing
all-interfaces binding); the only actionable gap was the missing
`POSTGRES_PORT` documentation (FR-005). The DbGate preloaded connection
(`CONNECTIONS: passanorte`, `SERVER_passanorte: db`, `PORT_passanorte: 5432`)
stays untouched — it is internal-network-only (FR-004), which is exactly what
makes it immune to `POSTGRES_PORT` changes (SC-003).

**Alternatives considered**: also making DbGate's `PORT_passanorte` variable
interpolated — rejected (it refers to the *internal* container port, which
spec FR-004 fixes).

## D5 — Hot reload interaction

**Decision**: keep `volumes: ["./src:/app/src"]` and `--reload` untouched; the
port is orthogonal to the bind-mount watcher.

**Rationale**: spec 004 (clarify Q1) pinned hot reload as FR-019; changing the
listen port via interpolation does not touch the file watcher or the mount.
Quickstart V2 re-verifies reload still works after a port change to guard the
interaction the spec's FR-002/SC-002 don't cover.

**Alternatives considered**: none (no viable alternative exists; the flag pair
`--host/--port` is the only uvicorn knobs in play).

## D6 — Verification mechanism (how quickstart assertions are run)

**Decision**: compose-native commands only: `docker compose config` (parse-time
validation of interpolation), `docker compose port <svc> <internal>` (reports
the host binding, including the `127.0.0.1:` prefix), `docker compose exec`
(for checks *inside* the container, e.g. the listening port), and plain host
curl/psql. No new test tooling, no new CI job.

**Rationale**: the spec's verification surface is the host machine plus the
Compose runtime; these commands observe exactly that, keeping precedent with
004's quickstart style (manual verification guide, no pytest additions).
`docker compose config` additionally catches the invalid-value edge case
(`API_PORT=numa`) at parse time without starting containers.

**Alternatives considered**: pytest integration tests booting compose —
rejected for this feature (heavy, redundant with quickstart; 004 precedent);
CI workflow changes — rejected (spec FR-008 confines the change).