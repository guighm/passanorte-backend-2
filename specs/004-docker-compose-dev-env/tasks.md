---
description: "Task list for feature 004-docker-compose-dev-env"
---

# Tasks: Containerização e Ambiente de Desenvolvimento Local (Docker Compose)

**Input**: Design documents from `/specs/004-docker-compose-dev-env/`

**Prerequisites**: plan.md (required), spec.md (required for user stories),
research.md, data-model.md, contracts/runtime-contracts.md, quickstart.md

**Tests**: Business tests are NOT touched by this feature (FR-018/SC-009: the
existing pytest suite is the regression gate). Validation of this infra feature
is by the executable scenarios of quickstart.md (V1–V7), referenced as
verification tasks. No new pytest tasks exist.

**Organization**: Tasks are grouped by user story (spec.md P1–P4). All file
artifacts live at repository root (plan.md "Structure Decision"); comments in
Dockerfile/compose/`.env.example` in English (constitution Principle VII).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1)
- Include exact file paths in descriptions

## Path Conventions

Single-project layout (plan.md): all new files at repository root
(`Dockerfile`, `.dockerignore`, `compose.yaml`, `.env.example`), entrypoint
script under `docker/`, plus one-line `README.md` and `.gitignore` updates.
`src/`, `migrations/`, `tests/` remain untouched.

---

## Phase 1: Setup (Container Artifact Skeleton)

**Purpose**: Build-context hygiene and the image — prerequisites for every
other task since all of them depend on the image building.

- [X] T001 [P] Write `.dockerignore` excluding, verbatim per FR-005: `.venv/`, `__pycache__/` and all Python caches (`*.py[oc]`, `.pytest_cache/`, `.ruff_cache/`), `tests/`, `specs/`, `docs/`, `.git/` (`.gitignore`, `.dockerignore` themselves), local databases (`*.db`, `*.sqlite3` — including the repo's existing `passanorte-dev.db`), `.env` and any local environment artifacts (`.env.*`), plus local artifacts (`build/`, `dist/`); goal is the minimal build context (SC-008)
- [X] T002 Write `Dockerfile` at repo root, multi-stage per FR-001–FR-004 and research D1–D5: (a) build stage `python:3.13-slim` + uv copied from `ghcr.io/astral-sh/uv` pinned to the minor version consistent with the repository's `uv.lock` (0.9.x — pin exact value, never `latest`); (b) create non-root user `app` (UID/GID 1000); (c) `COPY pyproject.toml uv.lock` then `uv sync --frozen --no-dev` (D2 — dependency cache layer before code copy; dev group `pytest`/`ruff` excluded); (d) `COPY . .` (context already cleaned by T001) and set `WORKDIR /app`, `ENV VIRTUAL_ENV=/app/.venv PATH=/app/.venv/bin:$PATH`; (e) runtime stage `python:3.13-slim` receiving `/app/.venv`, `src/`, `migrations/`, `config/`, `alembic.ini`, `docker/entrypoint.sh` from the build stage, same non-root user, `EXPOSE 8000`, `USER app` and `CMD ["uvicorn", "passanorte_back.main:app", "--host", "0.0.0.0", "--port", "8000"]` (the entrypoint's `exec "$@"` — T003 — consumes this CMD or a compose override); (f) zero secrets in any layer (FR-004/FR-016)
- [X] T003 [P] Write `docker/entrypoint.sh` per FR-008(v) and research D3: `set -e`; run `alembic upgrade head` (alembic resolves `script_location = migrations` relative to `/app`); on any failure exit non-zero (container stops — spec Edge Case); then `exec "$@"` (exec hands PID 1 to the argument command — the image `CMD` from T002 or a compose `command:` override such as T007's `--reload` — so both paths keep the migrations-first gate and clean SIGTERM)

**Checkpoint**: `docker build .` succeeds and `docker run --rm <image>
whoami` prints `app`; image contains no uv/pytest/ruff and no `.env` file.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The configuration surface — every compose up (any story) fails
without these two.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 Write `.env.example` at repo root per FR-015 and research D7/D8/D11, with English comments and non-production placeholder values for ALL of: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` (e.g. `passanorte` / clearly-flagged-change-me password / `passanorte`); `DATABASE_URL=postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}` (psycopg 3 dialect — driver in pyproject.toml; `db` is the compose service name); `JWT_SECRET` (e.g. `dev-only-jwt-secret-change-me`); `SENSITIVE_DATA_KEY` Fernet-format key (required by spec 001 FR-012 / RNF08 — include the regeneration command `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`) as comment; `ADMIN_USERNAME`/`ADMIN_PASSWORD` (optional step, FR-020); `API_PORT` (default 8000), `DBGATE_PORT` (default 8080); an explicit header comment "local development only — never use these values in production"
- [X] T005 [P] Update `.gitignore` exactly as research D10: replace the pattern `.env.*` with plain `.env` (keeping the surrounding comment and the existing `*.db`/`*.sqlite3` lines unchanged); verify afterwards with `git status --porcelain` that `.env.example` shows as untracked-includable and that no `.env` real file would be staged

**Checkpoint**: `cp .env.example .env && set -a && . ./.env && set +a && uv run
alembic upgrade head` succeeds against a local throwaway PostgreSQL **or** the
env-echo check confirms every required trio present (`DATABASE_URL`,
`JWT_SECRET`, `SENSITIVE_DATA_KEY`, `POSTGRES_*`).

---

## Phase 3: User Story 1 — Ambiente completo com um único comando (Priority: P1) 🎯 MVP

**Goal**: `docker compose up --build` brings up db + api; `/health` returns
200 with PostgreSQL connected; migrations of specs 001–003 applied before
serving; hot reload active (FR-019).

**Independent Test**: quickstart V1 + V2 — clean checkout (with `.env` copied)
→ `docker compose up --build -d` → `docker compose ps` healthy → `/health`
200 → tables listed (V2). Only Docker is needed.

### Implementation for User Story 1

- [X] T006 [US1] Add the `db` service to `compose.yaml` per FR-007 and research D1/D6/D9: image `postgres:18-alpine` (pinned major — never `latest`); environment `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` via Compose variable substitution from `.env` (`${POSTGRES_USER}` style — NOT hardcoded literals); healthcheck `pg_isready -U $POSTGRES_USER -d $POSTGRES_DB` with `interval: 5s`, `timeout: 3s`, `retries: 5`, `start_period: 30s`; **no host port published by default** (spec assumption — DbGate is the explorer; expose is documented, not built); no volume yet (US2 adds it)
- [X] T007 [US1] Add the `api` service to `compose.yaml` per FR-003/FR-008 and research D3/D4/D7/D9: `build: .`; `env_file: .env`; `environment: DATABASE_URL: postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}` (compose-env value takes precedence over `env_file` — the compose network address always wins: FR-008(iii)); ports `${API_PORT:-8000}:8000`; `depends_on: db: {condition: service_healthy}`; bind mount `./src:/app/src` (FR-019 hot reload); command override `uvicorn passanorte_back.main:app --host 0.0.0.0 --port 8000 --reload` (entrypoint still runs migrations first)
- [X] T008 [US1] Verify quickstart **V1 + V2**: `docker compose up --build -d` from clean state; `docker compose ps` → all healthy; `curl -i http://localhost:${API_PORT:-8000}/health` → HTTP 200 `{"status": "ok", "database": "ok"}`; `docker compose logs api` shows alembic lines **before** uvicorn startup; `docker compose exec db psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} -c '\dt'` lists specs 001–003 tables; record cold-start wall time (target ≤ 5 min — SC-001); verify **FR-019 hot reload**: with the stack up, edit a harmless marker inside a file under `src/`, wait a few seconds, confirm the change took effect without rebuild (uvicorn watcher line in `docker compose logs api` and/or a changed response), then revert the marker

**Checkpoint**: User Story 1 fully functional and independently testable —
clean checkout to healthy 2-services stack (db + api) in one command.

---

## Phase 4: User Story 2 — Persistência de dados entre reinicializações (Priority: P2)

**Goal**: PostgreSQL data outlives `down`/`up` via a named volume; migrations
idempotent on existing state; purge only via explicit `down -v`.

**Independent Test**: quickstart V4 — seed one record → `docker compose down` →
volume still listed → `docker compose up -d` → record present, no migration
re-run.

### Implementation for User Story 2

- [X] T009 [US2] Add the named volume to the `db` service in `compose.yaml` per FR-012/FR-013 and research D6: top-level `volumes:` declaring `postgres-data:`; service-level `volumes: - postgres-data:/var/lib/postgresql` (postgres 18 official image keeps data under `/var/lib/postgresql` — mounting the parent covers the layout); nothing else changes in `api` (it talks only to `db`)
- [X] T010 [US2] Verify quickstart **V4 + V5.4**: create one record through the API of an implemented domain (tourists 003 or auth 002) → `docker compose down` → `docker volume list` still shows `<project>_postgres-data` → `docker compose up -d` → record still present (browsed at the V3 connection or via psql), `docker compose logs api | grep -i alembic` shows NO re-executed applied chain (FR-013); then `docker compose down -v && docker compose up -d` once to prove `down -v` re-runs the full chain and destroys data (documented purge — FR-012)

**Checkpoint**: User Stories 1 AND 2 both work independently; data now
survives normal restarts.

---

## Phase 5: User Story 3 — Exploração do banco via DbGate pré-configurada (Priority: P3)

**Goal**: DbGate at `http://localhost:8080` with the PostgreSQL connection
preloaded from `.env` — zero credential typing (SC-004).

**Independent Test**: quickstart V3 — open the host port in a browser → UI
loads → connection `passanorte-postgres` already listed → open and browse
the migrated tables and rows without typing anything.

### Implementation for User Story 3

- [X] T011 [US3] Add the `dbgate` service to `compose.yaml` per FR-009 and research D8: image `dbgate/dbgate` pinned to the current stable tag (exact tag set during this task — same rule as the rest: pin, never `latest`); ports `${DBGATE_PORT:-8080}:3000` (DbGate's internal web port is 3000 — host side is what FR-010 controls); `environment: CONNECTIONS: '[{"conId":"passanorte-postgres","engine":"postgres@dbgate","server":"db","port":5432,"user":"${POSTGRES_USER}","password":"${POSTGRES_PASSWORD}","database":"${POSTGRES_DB}"}]'` — single line of JSON with compose variable substitution from the same `.env` trio; no `depends_on` hard gate required (DbGate reconnects on demand), but `network` shared with the stack implicitly
- [X] T012 [US3] Verify quickstart **V3**: from a browser (or `curl http://localhost:${DBGATE_PORT:-8080}` returning the UI shell), confirm the preloaded connection exists in the list, opens without credentials, lists the schema of specs 001–003, and browses rows (US-3 acceptance scenarios 1–3; SC-004 zero-typing rule)

**Checkpoint**: All three services coexist; DbGate exploration requires
nothing beyond opening a browser tab.

---

## Phase 6: User Story 4 — Configuração externa sem segredos no repositório (Priority: P4)

**Goal**: No real secret anywhere in the repo or image; `.env` only locally;
`.env.example` complete and versioned; credential change without rebuild.

**Independent Test**: quickstart V7 — image inspection: `whoami` = `app`, no
`.env` file in the image, no uv/pytest/ruff; `git status` never stages `.env`;
changing `.env` credentials + documented reinit works without `--build`.

### Implementation for User Story 4

- [X] T013 [US4] Audit and remediate secret hygiene per FR-004/FR-014/FR-016 and quickstart V7: `docker run --rm --entrypoint sh <api-image> -c 'whoami; ls -a /app; find / -name ".env*" 2>/dev/null'` → user `app`, no `.env` anywhere; `git check-ignore .env && git status --porcelain` → `.env` ignored, `.env.example` trackable, no credential literal in any tracked file; confirm changing `POSTGRES_PASSWORD` in `.env` + documented re-init (`down -v` + `up`) behaves as Contract 4 invariant 4 (no `--build` needed)

**Checkpoint**: All four stories independently functional; hygiene provable
with commands.

---

## Final Phase: Polish & Cross-Cutting Concerns

**Purpose**: Documentation and final regression validation.

- [X] T014 [P] Extend `README.md` (currently pt-BR — keep the section in Portuguese, following the file's language) with a "Ambiente de desenvolvimento com Docker Compose" section per FR-017: prerequisites (Docker + Compose v2 only), `cp .env.example .env`, `docker compose up --build -d`, `/health` at `http://localhost:8000/health`, DbGate at `http://localhost:8080`, optional admin bootstrap `docker compose exec api create-admin` (spec 002 script — unchanged, FR-020), `docker compose down` (keeps data) vs `down -v` (purges), FAQ entries for port conflicts (`API_PORT`/`DBGATE_PORT`) and for renaming `POSTGRES_DB`/`POSTGRES_USER` on an existing volume (requires `down -v` reinit — Contract 4 invariant 4)
- [X] T015 Run the full quickstart validation **V1 → V7 in order** fixing any deviation found against the contracts (each scenario's "Expected" block is the acceptance gate); record pass/fail per scenario in this file's Notes section or the PR description
- [X] T016 Run the regression gate per SC-009/FR-018: `git diff --stat origin/master..HEAD -- src migrations` returns empty; `git diff` in `tests/` shows ONLY the documented exception (`tests/smoke/test_settings_essentials.py` — empty-CWD isolation in the two missing-essential tests, approved during implementation); `uv run pytest` 100% green (including the module boundary checks); `uv run ruff check` clean

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T001+T003 parallel → T002 (needs `.dockerignore` to keep context clean) — image must build before anything else works
- **Foundational (Phase 2)**: T004/T005 parallel between themselves, only require the repo (no image dep) — but ALL of Phase 2 must exist before any `docker compose up`
- **US1 (Phase 3)**: needs Phases 1+2 - the first runnable increment (MVP)
- **US2 (Phase 4)**: needs US1's `db` service (edits the same `compose.yaml` — sequential on T006/T007, different story phase)
- **US3 (Phase 5)**: needs US1's network/services up (edits the same `compose.yaml` — after T007; DbGate only makes sense with the tables from US1's migrations)
- **US4 (Phase 6)**: hygiene audit — needs the image (T002) and compose (T006–T011) to inspect them; verify tasks last
- **Polish**: depends on all stories

### User Story Dependencies

- **US1**: independent (foundational only)
- **US2**: extends US1's `db` service (same file — cannot parallelize with US3, which edits the same file in a different section; keep story phases sequential). **Note**: FR-007 is only fully satisfied after US2 — its named-volume component lands in T009; the US1 MVP alone satisfies FR-007 without persistence
- **US3**: extends the stack (same file — sequential after US2)
- **US4**: audit of the artifacts built by US1–US3 — last by nature, not by value (its requirements were enforced throughout; this story is the proof pass)

### Within Each User Story

- Implementation task (compose edit) before its verification task
- Verification tasks reference specific quickstart scenario numbers — run them verbatim

### Parallel Opportunities

- T001 + T003 (Phase 1, different files)
- T004 + T005 (Phase 2, different files)
- T014 (README polish) can proceed in parallel with T013 (audit) — different files

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Setup + Foundational → image builds and `.env` exists
2. US1 → `up --build` → `/health` 200 with PostgreSQL connected
3. **STOP and VALIDATE**: V1 + V2 green — the stack is usable for
   development (migrations applied, hot reload working)
4. DbGate (US3) can wait; persistence (US2) can wait if disposable storage is
   acceptable for a spike

### Incremental Delivery

1. Setup + Foundational → hygiene + configuration surface ready
2. US1 → usable stack (MVP!)
3. US2 → restart-safe data
4. US3 → visual database exploration
5. US4 → hygiene proven by inspection commands
6. Polish → README + full quickstart pass + regression gate

### Notes

- All compose edits are to **one file** (`compose.yaml`) — story phases are
  sequential by necessity, but each story's edit is a self-contained block
- No task touches `src/`, `migrations/`, or `tests/` — if any task requires
  it, the plan/spec must be revisited (FR-018 is a hard constraint)
- Pin all image tags at task time (research D1/D8 rule: pin current stable,
  never `latest`)
- Commit after each checkpoint