# Quickstart Validation Guide: 010-configurable-service-ports

Phase 1 output. Manual verification of the port-configuration feature on a
machine with Docker Compose v2. Assumes the spec-004 environment already works
(default ports). Reference: [contracts/runtime-contracts.md](contracts/runtime-contracts.md)
for what each check guards.

Setup for every scenario:

```bash
cp .env.example .env   # once; scenarios V2+ edit this file
```

## V0 — Parse-time gate: `docker compose config`

```bash
docker compose config --quiet
```

**Expected**: exits 0 (interpolation valid). Re-run after each scenario below —
any `API_PORT=numa`-style typo fails here *before* containers exist (spec edge
case, research D6).

## V1 — Default boot (US1 / FR-001 / SC-001)

Ensure `.env` has no port variables set (comment all three or use a copy
without them), then:

```bash
docker compose up -d
docker compose ps                        # db healthy → api → dbgate
curl -s localhost:8000/health            # {"status": "ok"...}, database connected
docker compose port db 5432              # → 127.0.0.1:5432 (loopback-bound, D2)
docker compose port dbgate 3000          # → 0.0.0.0:8080 (all interfaces, D2)
psql "postgresql://passanorte:dev-only-password-change-me@localhost:5432/passanorte" -c '\dt'
```

**Expected**: three services up at 8000/8080/5432; psql connects from the host
and lists tables (including specs 001–003 ones). This proves the new `db`
exposure with built-in defaults. If `psql` is not installed on the host, use
any available SQL client (DBeaver, IDE database tool) against
`localhost:5432` — the assertion is a successful host-side connection, not the
specific tool.

## V2 — API_PORT end-to-end (US2 / FR-002 / SC-002)

```bash
sed -i 's/^#\?API_PORT=.*/API_PORT=9000/' .env   # or edit by hand
docker compose config --quiet                    # V0 gate
docker compose up -d --force-recreate api
curl -s localhost:9000/health                    # 200, database connected
# Listener INSIDE the container (no extra binaries needed; the slim image has
# no `ss` — use Python, always present):
docker compose exec api python -c "import socket; print(socket.socket().connect_ex(('localhost', 9000)))"  # → 0 (9000 is listening)
docker compose exec api python -c "import socket; print(socket.socket().connect_ex(('localhost', 8000)))"  # → nonzero (8000 closed inside too)
docker compose port api 9000                     # → 0.0.0.0:9000 (both sides 9000)
curl -s localhost:8000/health                    # FAILS — no split-brain listener on 8000
```

**Expected**: API answers **only** on 9000 — host and container sides equal
(`connect_ex` = 0 on 9000, ≠ 0 on 8000 inside the container); rebuild never
needed (1 restart, SC-002). Restore with `API_PORT=8000`.

## V3 — DBGATE_PORT / POSTGRES_PORT host remap (US3 / FR-003 / SC-003)

```bash
sed -i 's/^#\?DBGATE_PORT=.*/DBGATE_PORT=9080/; s/^#\?POSTGRES_PORT=.*/POSTGRES_PORT=15432/' .env
docker compose up -d --force-recreate db dbgate
docker compose port db 5432                      # → 127.0.0.1:15432
docker compose port dbgate 3000                  # → 0.0.0.0:9080
psql "...@localhost:5432/passanorte" -c 'select 1'   # FAILS (old host port gone)
psql "...@localhost:15432/passanorte" -c 'select 1'  # works
curl -s localhost:9080                           # DbGate UI
curl -s localhost:8080                           # FAILS (spec US3: it must answer on 9080 and NOT on 8080)
```

**Expected**: host ports remapped; internal ports still 5432/3000 (both
`docker compose port` lines show the *internal* ports unchanged); **open
localhost:9080 in the browser** — the preloaded `PassaNorte PostgreSQL`
connection still browses tables with `POSTGRES_PORT=15432` set, proving the
connection bypasses the host mapping (V3 step 4 of contracts, SC-003).

## V4 — Loopback-only db exposure (FR-003 / SC-005)

```bash
# Host-LAN IP, portable across Linux (hostname -I, ip as fallback), macOS
# (Windows/Docker Desktop: pick the LAN-facing IP by hand, e.g. from `ipconfig`):
LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}') || \
  LAN_IP=$(ip -4 addr show scope global 2>/dev/null | awk '/inet /{print $2; exit}' | cut -d/ -f1) || \
  LAN_IP=$(ipconfig getifaddr en0 2>/dev/null)
docker compose port db 5432                      # prefix MUST be 127.0.0.1
psql "...@${LAN_IP}:5432/passanorte" -c 'select 1'   # FAILS/refused — not on the LAN
curl -s "http://${LAN_IP}:8000/health"           # WORKS — api stays all-interfaces (FR-003a)
```

**Expected**: db reachable via `localhost` but refused via the machine's LAN IP;
api still reachable via LAN IP. (`hostname -I` on Linux, `ipconfig getifaddr en0`
on macOS; set `LAN_IP` manually on Windows.)

## V5 — Hot reload intact on a non-default port (research D5)

With `API_PORT=9000` still set: touch a comment change in any file under
`src/passanorte_back/`, wait a few seconds, then:

```bash
curl -s localhost:9000/health
```

**Expected**: the API restarts itself and serves on 9000 without recreate —
the port change did not damage the spec-004 reload promise.

## V6 — Restore defaults

```bash
sed -i 's/^#\?API_PORT=.*/API_PORT=8000/; s/^#\?DBGATE_PORT=.*/DBGATE_PORT=8080/; s/^#\?POSTGRES_PORT=.*/POSTGRES_PORT=5432/' .env
docker compose config --quiet                    # V0 gate
docker compose up -d --force-recreate
docker compose port db 5432                      # → 127.0.0.1:5432
curl -s localhost:8000/health                    # 200
```

**Expected**: defaults restored (`.env` mirroring `.env.example`), all checks
of V1 pass again.