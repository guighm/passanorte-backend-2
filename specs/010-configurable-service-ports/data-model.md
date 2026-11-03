# Data Model: 010-configurable-service-ports

Phase 1 output. No data entities are added or changed — no DB schema, no
migrations, no persisted state beyond environment variables. The feature's
"data model" is the **configuration surface**: three variables, their
resolution rules and their reach. Nothing else changes shape.

## Configuration entities

Three environment variables (all optional, all with built-in defaults):

| Variable | Default  | Scope changed                | Read/expanded by                |
|----------|----------|------------------------------|---------------------------------|
| `API_PORT`      | `8000` | host port **and** container listen port (end-to-end, FR-002) | Compose interpolation (ports + `command:`) |
| `POSTGRES_PORT` | `5432` | host port (new exposure; loopback-bound, FR-003) | Compose interpolation (ports) |
| `DBGATE_PORT`   | `8080` | host port (formalized only)  | Compose interpolation (ports) |

**Resolution order** (Compose standard, spec Assumptions): shell environment >
`.env` file > built-in `${VAR:-default}`. An unset variable can never break the
boot (D3).

## Fixed (non-configurable) ports — the invariant

| Internal port | Service | Fixed because |
|---|---|---|
| `5432` | `db`        | `DATABASE_URL` (api) and `SERVER_passanorte`/`PORT_passanorte` (dbgate) address the compose-internal hostname, never the host mapping (FR-004) |
| `3000` | `dbgate`    | container's own listen port; only the host side is remapped |
| `8000` | `Dockerfile EXPOSE` | documentation only (FR-009); does not gate or constrain the effective port |

## What is NOT part of the model

- No change to `POSTGRES_*` credentials, `DATABASE_URL`, `JWT_SECRET`,
  `SENSITIVE_DATA_KEY`, admin bootstrap variables (untouched from spec 004).
- No new files, tables, volumes or relationships. `postgres-data` volume
  semantics unchanged.
- No port value is a secret; all three are committed in `.env.example` (FR-005,
  007).

## Validation rules (from spec, enforced at parse/quickstart level)

- Default boot: unset variables → 8000/8080/5432 (US1/SC-001).
- Loopback-only db exposure: host side must start with `127.0.0.1:` (FR-003,
  SC-005).
- Host/container API sides equal: mapping is
  `${API_PORT:-8000}:${API_PORT:-8000}` (FR-002).
- Inter-service isolation: no `${*_PORT}` host variable may appear in
  `DATABASE_URL`, `SERVER_passanorte`, `PORT_passanorte`, or any `command:`
  arg other than the uvicorn listen port (FR-004).