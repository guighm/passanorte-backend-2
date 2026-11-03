# Runtime Contracts: 010-configurable-service-ports

Phase 1 output. The REST contract is **unchanged** (spec FR-008): `GET /health`
keeps its semantics, every `/api/v1` route stays as implemented, and the
migrations/entrypoint flow from spec 004 is untouched. This feature's contracts
are the **port-configuration obligations** each artifact fulfils — the
amendments to the spec-004 contracts (Contract 2/3 there) plus the new `db`
exposure. These define acceptance for the tasks phase.

## Contract 1 — `compose.yaml` port surface (what the compose file promises)

| Promise | Verification hook |
|---|---|
| `api` publishes and listens on the **same** port: `"${API_PORT:-8000}:${API_PORT:-8000}"`, and `command:` interpolates `--port ${API_PORT:-8000}` | quickstart V2 |
| `db` publishes `127.0.0.1:${POSTGRES_PORT:-5432}:5432` — loopback-only, internal port fixed at 5432 | quickstart V1, V4 |
| `dbgate` keeps `"${DBGATE_PORT:-8080}:3000"` — formalized, no behavior change | quickstart V3 |
| Unset variables never break boot: defaults 8000/8080/5432 are built into the definitions | quickstart V1 (with variables deleted from `.env`) |
| `dbgate` preloaded connection stays internal-only: `SERVER_passanorte: db`, `PORT_passanorte: 5432` — no host-port variable leaks into `DATABASE_URL` or the DbGate connection | quickstart V4 |
| `docker compose config` renders with any port assignment (default, custom, or unset) | quickstart V0 (parse-time gate) |

## Contract 2 — Environment variables (single configuration surface)

| Variable | Consumer | Required | Default policy |
|---|---|---|---|
| `API_PORT`       | `api` (ports + uvicorn listen)   | no | `8000` built-in; example value committed in `.env.example` |
| `POSTGRES_PORT`  | `db` (host exposure only)        | no | `5432` built-in; example value committed in `.env.example` (new) |
| `DBGATE_PORT`    | `dbgate` (host mapping)          | no | `8080` built-in; example value committed in `.env.example` |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` / `DATABASE_URL` / `JWT_SECRET` / `SENSITIVE_DATA_KEY` | unchanged from spec 004 | unchanged (`:?required` rules untouched) | not touched by this feature |

Non-secret by nature: port values and defaults are committed (FR-005/007);
`.env` stays git-ignored; no secret is introduced.

## Contract 3 — Artifacts left intact (inherited promises)

Toward spec 004's runtime contracts, this feature must not regress:

| Inherited promise | Guard |
|---|---|
| `Dockerfile` and `EXPOSE 8000` unchanged (metadata-only declaration, FR-009) | tasks diff scope |
| `docker/entrypoint.sh` unchanged (still `alembic upgrade head` → `exec "$@"`, receives the port from compose-rendered command) | tasks diff scope |
| `db` healthcheck still gates `api` startup; migrations still run before uvicorn serves | quickstart V2 |
| Hot reload (FR-019 of spec 004) still works with a non-default port | quickstart V5 |
| No `src/passanorte_back/`, `migrations/`, or `tests/` file changes | boundary checker / diff scope |