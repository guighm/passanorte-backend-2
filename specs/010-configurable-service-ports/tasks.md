# Tasks: Portas de Serviços Configuráveis via .env (Docker Compose)

**Input**: Design documents from `/specs/010-configurable-service-ports/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/, quickstart.md

**Tests**: No pytest test tasks in this file — no business code is touched (spec FR-008; plan Constitution Check III). Validation is via the manual quickstart.md scenarios referenced inside tasks; each story's checkpoint names its scenario.

**Organization**: Tasks grouped by user story. ⚠️ US1/US2/US3 all edit `compose.yaml`, so they must run **sequentially in priority order** (no cross-story parallelism; same-file conflict). Within a story, tasks touching different files are marked [P].

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Baseline local environment — no repository changes in this phase.

- [X] T001 Create local `.env` from `.env.example` if not already present (`cp .env.example .env`) and record the current values of `API_PORT`, `DBGATE_PORT` (they exist) and the absence of `POSTGRES_PORT`; confirm `.env` is git-ignored (`git check-ignore -v .env`)

**Checkpoint**: Local env exists, repo tree untouched.

---

## Phase 2: Foundational (Blocking Prerequisites)

None — the feature has no shared infrastructure beyond Phase 1 (plan.md §Project Structure: only `compose.yaml` + `.env.example` change; Dockerfile, `docker/entrypoint.sh`, `src/`, `migrations/`, `tests/` untouched).

---

## Phase 3: User Story 1 — Toda variável de porta tem default e sobe "out of the box" (Priority: P1) 🎯 MVP

**Goal**: Database becomes reachable from the host machine (loopback-bound) via `POSTGRES_PORT`, with all three port variables defaulting correctly on a zero-tweak boot (spec FR-001, FR-003, FR-005; internal port 5432 stays fixed, FR-004).

**Independent Test**: quickstart.md **V0 + V1** — `docker compose config --quiet` passes; boot with all variables unset brings up db/api/dbgate at 8000/8080/5432; host psql connects at `localhost:5432`.

### Implementation for User Story 1

- [X] T002 [P] [US1] Add host-port mapping to the `db` service in `compose.yaml`: `ports: ["127.0.0.1:${POSTGRES_PORT:-5432}:5432"]` with a comment stating (a) loopback-only host binding per spec 010 FR-003 (not visible on the LAN, SC-005), (b) internal port stays 5432 because inter-service traffic (`DATABASE_URL`, DbGate `PORT_passanorte`) uses the compose network, never the host mapping (FR-004)
- [X] T003 [P] [US1] Complete the host-ports documentation in `.env.example` — one pass over all three variables to satisfy spec 010 FR-005: add `POSTGRES_PORT=5432` (uncommented) with a comment explaining host exposure only for psql/IDEs, internal port remains 5432, loopback-only binding, not a secret (research D3); and enrich the existing terse `API_PORT`/`DBGATE_PORT` comments to state what each controls (API_PORT = REAL api port, host and container sides equal; DBGATE_PORT = host mapping only, internal 3000 fixed)
- [X] T004 [US1] Mirror the new variable in local `.env` (`POSTGRES_PORT=5432`) keeping `.env` aligned with `.env.example` (spec FR-006; depends on T003)
- [X] T005 [US1] Validate User Story 1 independently: run quickstart.md **V0** then **V1** from repo root and confirm the expected outcomes — `docker compose config` clean, three services healthy at default ports, `docker compose port db 5432` returns `127.0.0.1:5432`, host psql lists tables (depends on T002, T003, T004)

**Checkpoint**: User Story 1 fully functional and independently validated (MVP). `docker compose down` before continuing to US2 to avoid port-change races.

---

## Phase 4: User Story 2 — API_PORT muda a porta REAL da API, end-to-end (Priority: P2)

**Goal**: One-variable port change for the API, host and container sides equal (spec FR-002, FR-001; research D1/D5). No split-brain listener remains.

**Independent Test**: quickstart.md **V2** — set `API_PORT=9000`, recreate `api`, health answers only on 9000; inside the container the listener is 9000; 8000 answers nothing.

### Implementation for User Story 2

- [X] T006 [US2] Change the `api` service port mapping in `compose.yaml` from `"${API_PORT:-8000}:8000"` to `"${API_PORT:-8000}:${API_PORT:-8000}"` (host and container sides always equal; update the comment to note the end-to-end contract and that `EXPOSE 8000` in `Dockerfile` is documentation only, FR-009 — depends on T005)
- [X] T007 [US2] Change the `api` service `command:` in `compose.yaml` from `--port 8000` to `--port ${API_PORT:-8000}` (the same variable as T006 so host/container can never diverge; compose interpolates it into the rendered command string, `docker/entrypoint.sh` stays untouched, research D1)
- [X] T008 [US2] Validate User Story 2 independently: run quickstart.md **V2** — health 200 at `localhost:9000`, inside-container listener check via Python `connect_ex` (9000 → 0, 8000 → nonzero; the slim image has no `ss`), `docker compose port api 9000` → `0.0.0.0:9000` (depends on T006, T007)

**Checkpoint**: User Story 2 validated without touching the Dockerfile or entrypoint (diff scope check, contracts.md Contract 3).

---

## Phase 5: User Story 3 — DbGate formalizado (Priority: P3)

**Goal**: Formalize the existing `DBGATE_PORT` mapping and prove host-port changes never reach the preloaded connection (spec FR-003a/FR-004; research D4).

**Independent Test**: quickstart.md **V3** — remap DBGate and Postgres host ports; internal ports stay 3000/5432; preloaded connection still browses tables with a non-default `POSTGRES_PORT`.

### Implementation for User Story 3

- [X] T009 [US3] Formalize (comment-only, no mapping change) the `dbgate` service in `compose.yaml`: annotate `"${DBGATE_PORT:-8080}:3000"` with a comment stating host-port configurable / internal 3000 fixed, and that `SERVER_passanorte: db` + `PORT_passanorte: 5432` are internal-network-only and must not reference host-port variables (FR-004; depends on T008)
- [X] T010 [US3] Validate User Story 3 independently: run quickstart.md **V3** — DbGate UI answers at the remapped port, `docker compose port dbgate 3000` shows internal 3000 unchanged, preloaded connection browses tables while `POSTGRES_PORT=15432` is set (depends on T009)

**Checkpoint**: All three user stories independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Regression guards and final validation across all stories.

- [X] T011 [P] Cross-cutting diff-scope audit (spec FR-007/008/009): `git diff` for this feature touches **only** `compose.yaml` and `.env.example` (+ local `.env`, untracked); `Dockerfile`, `docker/entrypoint.sh`, `src/`, `migrations/`, `tests/` appear in no diff; no secret values in `.env.example`
- [X] T012 [P] Run the existing pytest suite (`uv run pytest`) and confirm green — spec 004 smoke tests and all specs 001–003 tests unaffected by port variables (plan Constitution Check III)
- [X] T013 Validate the full quickstart.md end-to-end: **V0, V4** (loopback-only db: reachable via localhost, refused via the machine's LAN IP, api still reachable via LAN IP per FR-003a), **V5** (hot reload works on a non-default API port), **V6** (restore defaults → V1 passes again) — completes SC-001..005 coverage (depends on T005, T008, T010)

**Checkpoint**: Feature complete — 0/0 unresolved. MVP scope shipped at US1.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: None (empty)
- **User Stories (Phase 3–5)**: **Sequential, in priority order** — same-file conflict (all three edit `compose.yaml`); T006 depends on T005 (clean baseline), T009 depends on T008
- **Polish (Phase 6)**: T011/T012 parallel after T010; T013 depends on all story checkpoints

### User Story Dependencies

- **User Story 1 (P1)**: Starts after Setup — no dependencies (MVP)
- **User Story 2 (P2)**: Needs US1 complete (same file; also validates US1's baseline in its Independent Test)
- **User Story 3 (P3)**: Needs US2 complete (same file)

### Within Each User Story

Implementation tasks → validation task is the only ordering rule; T002/T003 are parallel ([P]).

### Parallel Opportunities

- Minimal by design — this feature is two files and one variable of behavior change. Only T002+T003 (Phase 3), T011+T012 (Phase 6) are parallel-safe. **Cross-story parallelism is excluded deliberately.**

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (local `.env` baseline)
2. Complete Phase 3: db exposure + defaults (T002–T005)
3. **STOP and VALIDATE**: quickstart V0+V1 — the only net-new behavior (host psql access) is live and shippable

### Incremental Delivery

1. MVP (US1) → validated
2. Add US2 → the API_PORT split-brain is gone → validated (V2)
3. Add US3 → DbGate formalized → validated (V3)
4. Polish: diff-scope audit, pytest green, full V4–V6 sweep → feature done

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to spec.md user stories for traceability
- Every story's final task is the quickstart scenario named in its Independent Test — do not mark the story complete without it
- Commit after each story (or logical group); keep the per-feature commit pattern used in this repo
- Avoid: any edit outside `compose.yaml`/`.env.example` (FR-008); interpolation of host-port variables into `DATABASE_URL`, `SERVER_passanorte`, `PORT_passanorte`, or any value other than the uvicorn listen port (FR-004)