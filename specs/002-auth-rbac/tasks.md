---

description: "Task list for feature 002-auth-rbac implementation"
---

# Tasks: Autenticação e Controle de Acesso (RBAC)

**Input**: Design documents from `/specs/002-auth-rbac/` (plan.md, spec.md, research.md, data-model.md, contracts/auth.md, contracts/employees.md, quickstart.md)

**Prerequisites**: Constituição v1.1.0 — Test-First (III): cada tarefa de
implementação só inicia DEPOIS do teste correspondente estar escrito e
FALHA (vermelho). Código 100% em inglês (VII). Auditoria via
`core.audit.record_action` (RNF19). Nenhuma credencial em texto plano
(FR-002/FR-007, RNF10).

**Tests**: obrigatórios pela spec (critério de aceitação: testes de contrato
+ teste de integração do ciclo de vida) — incluídos como tarefas em vermelho
antes de cada implementação.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos distintos, sem dependência de tarefa incompleta)
- **[Story]**: user story de origem (US1–US5 do spec.md)
- Sempre com caminho exato de arquivo

## Path Conventions

Repositório único (monolito modular da fundação): `src/passanorte_back/`,
`tests/`, `migrations/versions/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: dependências e configuração novas sem tocar em lógica de domínio

- [X] T001 Add `pyjwt` and `bcrypt` dependencies to pyproject.toml `[project].dependencies` (research R1/R2 — no pinned-downgrade; uv lock refreshed)
- [X] T002 Extend core/config.py: add `jwt_refresh_ttl: int = 604800` env-backed setting with the same `> 0` validation used by `jwt_ttl` (validation on the `jwt_ttl`/`gps_tolerance_radius_m` validator; research R8; data unchanged — docstring updated)

**Checkpoint**: ambiente pronto — fases de domínio não dependem de mais nada externo ao repositório.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: primitivos de segurança, dependências RBAC, migrations e
interface mínima de funcionário que bloqueiam TODAS as user stories

**⚠️ CRITICAL**: nenhuma story começa antes deste checkpoint.

- [X] T003 [P] Write failing unit tests for password hashing and access-token round-trip in tests/unit/test_security.py (red): bcrypt hash does not store plaintext (RNF10), verify_password accepts correct and rejects wrong password, different hashes for same password; create_access_token/decode round-trip with claims `sub`, `account_type` (`admin`|`employee`), `role`, `sid`, `exp`/`iat` (JWT_TTL from settings); expired token rejected; forged signature rejected (research R2)
- [X] T004 Implement primitives in src/passanorte_back/core/security.py: `hash_password`, `verify_password` (bcrypt, 12 rounds), `generate_initial_password` (secure random, secrets.token_urlsafe), `create_access_token`, `decode_access_token` (HS256, `settings.jwt_secret`, JWT_TTL) — green T003 (research R1/R2/R9)
- [X] T005 [P] Write failing tests for RBAC dependencies in tests/unit/test_rbac_dependencies.py (red): missing/invalid/expired token → 401; admin and employee account inactive/revoked at request time → 401 (state reloaded per request, research R4); employee token on an admin-only route → 403; admin token → allowed (FR-015, clar. Q1/Q2/Q3-s3)
- [X] T006 Implement FastAPI security dependencies `get_current_user` and `require_admin` in src/passanorte_back/modules/auth/services/security.py (public interface — the boundary checker only allows cross-module imports from `services`; primitives from core/security; resolves admin from `admin_users` repo and employee via `employees.services` public function; revogação de conta derruba sessões em curso — FR-013). **CUIDADO (analyze F2)**: auth ↔ employees se referem mutuamente via services — faça o import de `employees.services` DENTRO da função (lazy) para evitar import circular no nível de módulo
- [X] T007 [P] Extend schema assertions in tests/test_migrations.py (red): after migrations `admin_users`, `employees` and `auth_sessions` exist with the columns/constraints of data-model.md (unique usernames; `status` enum `active`|`revoked`; `role` enum; `auth_sessions.refresh_token_hash` unique, `revoked_at` nullable)
- [X] T008 Create Alembic migration in migrations/versions/: `admin_users` (id, unique username, password_hash, role='admin', is_active, is_bootstrap, created_at/updated_at), `employees` (id, name, unique username, password_hash, role='employee', status, created_at/updated_at), `auth_sessions` (id, account_type, account_id, unique refresh_token_hash, created_at, expires_at, revoked_at nullable) — no cross-domain FK (data-model.md; rule 4) — green T007
- [X] T009 [P] Implement the minimal public credential interface of employees: src/passanorte_back/modules/employees/repositories/employees.py (table model + data access) and src/passanorte_back/modules/employees/services/__init__.py exporting `find_by_username(username) -> credential view (username, password_hash, active)`; NO routes yet (research R5; consumed by auth login in US2)

**Checkpoint**: primitivos de segurança, RBAC, schema e interface de
funcionário prontos — user stories podem iniciar.

---

## Phase 3: User Story 1 - Bootstrap de credenciais administrativas (Priority: P1) 🎯 MVP

**Goal**: script idempotente de upsert da única conta administrativa, com segredos exclusivamente via env (RF01, FR-001/002/003).

**Independent Test**: executar o script em banco vazio → conta criada e login possível; reexecutar → nada duplicado; mudar ADMIN_USERNAME/ADMIN_PASSWORD e reexecutar → mesma conta atualizada em vigor; ausência de env → erro claro sem tocar o banco.

### Tests for User Story 1

- [X] T010 [P] [US1] Write failing integration tests in tests/integration/test_admin_bootstrap.py (red): (a) create on empty database; (b) rerun with same env → single account, still active, login works (idempotência — FR-003); (c) rerun with changed ADMIN_USERNAME/ADMIN_PASSWORD → same bootstrap row updated in place, no second account (clar. Q4-s5); (d) missing ADMIN_* env → script fails with clear message and no DB change; (e) no plaintext password in DB/code/log output (RNF10, FR-002); (f) audit entry emitted (`bootstrap.upsert`, actor `system/bootstrap` — RNF19)

### Implementation for User Story 1

- [X] T011 [US1] Implement admin account schemas in src/passanorte_back/modules/auth/schemas/ (AdminUserCreate for bootstrap input from env; never expose password fields in responses)
- [X] T012 [US1] Implement src/passanorte_back/modules/auth/repositories/admin_users.py: find_bootstrap_account, upsert_bootstrap_account (fields per data-model.md: unique username, password_hash, role='admin', is_active, is_bootstrap — exactly one row with is_bootstrap=True)
- [X] T013 [US1] Implement src/passanorte_back/modules/auth/services/bootstrap.py: `bootstrap_upsert(admin_username, admin_password)` using hash_password (core/security, T004), restoring is_active on rerun, emitting audit via core.audit.record_action; plus public `is_username_taken(username) -> bool` in auth services (used by employees creates — FR-011, research R5) (depends on T011, T012)
- [X] T014 [US1] Implement src/passanorte_back/scripts/create_admin.py + `[project.scripts] create-admin` wiring in pyproject.toml: env-only secrets (ADMIN_USERNAME, ADMIN_PASSWORD; missing → clear error, exit non-zero, no DB change), calls bootstrap_upsert, prints account status without echoing the password (green T010)

**Checkpoint**: US1 independente — admin bootstrap funcional e testável por conta própria (sem login/funcionários).

---

## Phase 4: User Story 2 - Login do painel administrativo (Priority: P1)

**Goal**: login único dos dois perfis com par de credenciais (access JWT +
refresh opaco persistido), renovação single-use e logout (RF02, RNF09,
FR-004/005/006, clar. Q1/Q2/Q3-s1).

**Independent Test**: POST /login com admin e funcionário válidos → 200 com par + role; senha errada/usuário inexistente/conta inativa → 401; refresh válido → novo par (reuso → 401); logout → refresh recusado; requisição sem token → 401.

### Tests for User Story 2

- [X] T015 [P] [US2] Write failing contract tests in tests/contract/test_auth.py (red): POST /api/v1/auth/login 200 (SessionResponse: access_token, refresh_token, token_type="bearer", expires_in, role) for admin and for employee; 401 generic "invalid credentials" for wrong password / unknown user / revoked employee; POST /refresh 200 new pair, same role, single-use (reused old refresh → 401), invalid/expired/unknown refresh → 401; POST /logout 204 then refresh with old token → 401; request without bearer token on protected route → 401; request body schema validation → 422 (contracts/auth.md)

### Implementation for User Story 2

- [X] T016 [US2] Implement src/passanorte_back/modules/auth/repositories/auth_sessions.py: create session, find by refresh_token_hash, rotate (single-use), revoke — fields per data-model.md (account_type admin|employee, account_id, unique SHA-256 refresh_token_hash, expires_at, revoked_at) (depends on T008)
- [X] T017 [US2] Implement auth session schemas in src/passanorte_back/modules/auth/schemas/: LoginRequest (username, password), RefreshRequest (refresh_token), SessionResponse (access_token, refresh_token, token_type="bearer", expires_in, role) (contracts/auth.md)
- [X] T018 [US2] Implement auth flows in src/passanorte_back/modules/auth/services/authentication.py: `login` (finds admin via admin_users repo or employee via employees.services public `find_by_username`; verify_password; account active required; issues pair — access JWT via core/security with sid claim, refresh opaque hashed in auth_sessions with jwt_refresh_ttl; never distinguish failure causes); `refresh` (single-use rotation — old hash rows become rotated; revalidates account state); `logout` (revokes session by sid); audit login.success/login.failure/logout (FR-014, R10, research R3/R4) (depends on T004, T006, T009, T016, T017)
- [X] T019 [US2] Implement auth routes in src/passanorte_back/modules/auth/routes/: POST /login, POST /refresh, POST /logout mounted on the existing canonical router (core/routers.py; prefix /api/v1/auth; no auth on login/refresh, bearer on logout) — green T015

**Checkpoint**: US2 independente — login/refresh/logout contratualmente testados (US1 admin já existirá como seed do fixture).

---

## Phase 5: User Story 3 - Restrição de acesso por perfil — RBAC (Priority: P1)

**Goal**: RBAC aplicado a todo endpoint do painel: admin total, funcionário
apenas concessão de benefícios (futura); 401/403 corretos (RF03,
FR-008/009/015).

**Independent Test**: employee token em endpoint administrativo → 403; admin token no mesmo endpoint → 200/201/204; requisição sem token → 401.

> ⚠️ Dependência de execução: os endpoints administrativos existentes nesta
> fase são os de `employees` (Fases 6–7). As tarefas T021/T022 fecham com os
> testes verdes APÓS as fases 6–7 (ordem de execução na seção Dependencies).
>
> ℹ️ Deferral (analyze F1): o bloqueio de funcionário a **dashboard** e
> **tourist_spots** (FR-009) é validado neste ciclo no nível da dependência
> `require_admin` (T005/T006) — essas rotas de domínio ainda não existem
> (features futuras, que DEVE reutilizar `require_admin` de
> `auth.services`). SC-001/FR-015 cobrem todo endpoint existente.

### Tests for User Story 3

- [X] T020 [P] [US3] Write failing contract tests in tests/contract/test_rbac.py (red): GET /api/v1/auth/me without token → 401; with admin token → 200 {username, role:"admin"}; with employee token → 200 {username, role:"employee"}; employee token on POST /api/v1/employees, GET /api/v1/employees, PATCH /api/v1/employees/{id}, POST /api/v1/employees/{id}/revoke → 403 with same pair of credentials admin → allowed (FR-008/009/015; contracts/employees.md)

### Implementation for User Story 3

- [X] T021 [US3] Implement GET /api/v1/auth/me in src/passanorte_back/modules/auth/routes/ + CurrentUserResponse schema (username, role) in src/passanorte_back/modules/auth/schemas/ — protected by get_current_user (any authenticated role; contracts/auth.md) (depends on T006, T017)
- [X] T022 [US3] Apply require_admin to every admin-only route of this feature (employees endpoints created in Phases 6–7 already wired via their route tasks; this task audits that every protected route of the feature has RBAC wired and no route of the panel is exposed without it — FR-008 gate; run tests/contract/test_rbac.py to green)

**Checkpoint**: RBAC integral — nenhum endpoint do painel sem RBAC; testes de 403 cobertos em rota administrativa real.

---

## Phase 6: User Story 4 - Cadastro de funcionário (Priority: P2)

**Goal**: admin cadastra funcionário; sistema gera a senha inicial exibida uma única vez; RBAC admin-only (RF04, FR-010/011, clar. Q3-s4).

**Independent Test**: POST /employees 201 com initial_password (presente só nessa resposta); username duplicado (admin ou employee) → 409; funcionário criado loga com role employee.

### Tests for User Story 4

- [X] T023 [P] [US4] Write failing contract tests in tests/contract/test_employees.py (red): POST /api/v1/employees 201 (EmployeeCreatedResponse with id, name, username, status="active", initial_password — present only in this response); duplicate username (employee or admin, case-insensitive) → 409 no account created; GET list and GET detail return EmployeeView without credentials; 401 without token / 403 with employee token (contracts/employees.md; FR-011)

### Implementation for User Story 4

- [X] T024 [US4] Implement employee creation in src/passanorte_back/modules/employees/services/management.py: `create_employee(name, username)` — generates initial password via core/security (T004), stores only bcrypt hash, global uniqueness via auth.services.is_username_taken (research R5; FR-011), audit `employee.create` (FR-014). **CUIDADO (analyze F2)**: import de `auth.services` DENTRO da função (lazy) — evita import circular com auth.services.security (T006)
- [X] T025 [US4] Implement employees routes in src/passanorte_back/modules/employees/routes/: POST /employees (201 + initial_password one-time view), GET /employees, GET /employees/{employee_id} (200/404) — **all with require_admin** (RBAC gate from US3; contracts/employees.md) — green T023 and the employees part of tests/contract/test_rbac.py

**Checkpoint**: US4 independente — criação com credencial gerada validada por contrato.

---

## Phase 7: User Story 5 - Edição e revogação de acesso (Priority: P2)

**Goal**: admin edita dados (incl. reativação) e revoga acesso com efeito
imediato (RF05, FR-012/013, clar. Q3-s3).

**Independent Test**: fluxo criar → editar (persistido) → revogar (sessão em curso 401, login 401) → PATCH reativar (novo login ok, sessões antigas ainda recusadas) → 404 para id inexistente.

### Tests for User Story 5

- [X] T026 [P] [US5] Write failing integration tests in tests/integration/test_employee_lifecycle.py (red): full lifecycle create → edit → revoke → login blocked (SC-003 acceptance flow); revoke with active session → next API call 401 (immediate effect, FR-013, research R4); reactivate via PATCH {"status": "active"} → new login OK, pre-revocation sessions still rejected; PATCH {"status": "revoked"} → 422 (revoke only via revoke route); unknown id → 404 without touching other accounts; audit entries for employee.update / employee.reactivate / employee.revoke (FR-014)

### Implementation for User Story 5

- [X] T027 [US5] Implement employee management flows in src/passanorte_back/modules/employees/services/management.py: `update_employee` (name/username; reactivation via status=active; audit employee.update/employee.reactivate) and `revoke_employee` (status → revoked, idempotent 204, audit employee.revoke) (depends on T009, T024)
- [X] T028 [US5] Implement employees routes: PATCH /{employee_id} (200 EmployeeView; 404; 409 on username conflict; 422 for status=revoked) and POST /{employee_id}/revoke (204/404) — with require_admin — green T026 (contracts/employees.md)

**Checkpoint**: ciclo de vida completo (critério de aceitação principal da feature) verde.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: documentação e validação final dos gates

- [X] T029 [P] Update README.md (or docs/) documenting the auth flow, create-admin script usage, env variables (ADMIN_USERNAME, ADMIN_PASSWORD, JWT_SECRET, JWT_TTL, JWT_REFRESH_TTL) and endpoint summary (Principle VII — code/commits in English, docs content free)
- [X] T030 Run quickstart.md validation end-to-end and all quality gates: full `uv run pytest` (contract + integration + existing smoke), `uv run ruff check`, `uv run ruff format --check`, boundary scanner green, no plaintext credential in code/log fixtures, migrations applied cleanly from baseline

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)** → **Foundational (Phase 2)** → user stories
- **US1 (Phase 3)** depends on Phase 2 (hashing, migration, schemas)
- **US2 (Phase 4)** depends on Phase 2 (security deps, session infra, T009) and reads the seeded admin/employee accounts (US1 admin + T009 employee credential interface)
- **US4 (Phase 6)** depends on US2 (admin token needed to create employees — contract test uses seeded admin)
- **US5 (Phase 7)** depends on US4 (accounts to edit/revoke)
- **US3 (Phase 5)**: T021 (/me) can run right after US2; T022 (full 403 validation) runs **after Phases 6–7** — execution order below
- **Polish (Phase 8)** last

### Recommended Execution Order (dependency-driven)

```text
T001 → T002 → T003 → T004 → T005 → [T009, T012] → T006 → T007 → T008
→ T010 → T011 → T013 → T014               (US1)
→ T015 → T016 → T017 → T018 → T019        (US2)
→ T021                                     (US3 /me)
→ T023 → T024 → T025                      (US4)
→ T026 → T027 → T028                      (US5)
→ T020 → T022                              (US3 full RBAC validation)
→ T029 → T030                              (Polish)
```

### User Story Dependencies

- US1: independent (needs only Phase 2)
- US2: needs US1 admin account (seeded in fixtures) + T009 employee interface
- US3: dependencies implemented in Phase 2; e2e 403 validation needs US4/US5 routes
- US4: needs US2 (admin bearer token) — spec priority P2 respected
- US5: needs US4
- Stories remain independently testable via their own phases/checkpoints

### Within Each User Story

- Tests first (red) → repositories → services → routes (green) → audit
- Verify tests fail before implementing (Constitution III)

### Parallel Opportunities

- [P] tests (T003, T005, T007, T010, T015, T020, T023, T026) can be written in parallel with their phase's models/repos
- Repositories/schemas of different stories never touch the same files
- After Phase 2, US1 alone can proceed while a reviewer runs Phase 2 tests

---

## Implementation Strategy

### MVP First (Setup + Foundational + US1 + US2)

1. Phases 1–2 (T001–T009)
2. Phase 3 US1 (T010–T014) — admin bootstrap
3. Phase 4 US2 (T015–T019) — login/refresh/logout
4. **STOP and VALIDATE**: admin pode logar com par de credenciais; 401/403 base verdes

### Incremental Delivery

- +US3 partial (T021 /me) → painel resolve identidade
- +US4 → criação de funcionários (painel operável para o admin)
- +US5 → ciclo de vida completo (SC-003)
- +US3 final (T020, T022) → RBAC integral validado (SC-001)
- Polish (T029, T030)

### Notes

- Nenhuma credencial real no repositório; fixtures geram tudo
- Commits em inglês, por tarefa ou grupo lógico (Principle VII)
- Stop at any checkpoint to validate the story independently
---

## Phase 9: Convergence

> Generated by /speckit-converge (2026-10-31) — 2 actionable LOW findings.

- [X] T031 Document the actual logout behavior (both credentials die immediately — stricter than the current contract text) in specs/002-auth-rbac/contracts/auth.md and update tests/contract/test_auth.py to assert the stricter behavior explicitly (access token also rejected right after logout) (FR-016) (contradicts)
- [X] T032 Replace the `Any`-typed constants in src/passanorte_back/modules/employees/repositories/employees.py with `int`/`str` finals and use the `STATUS_ACTIVE`/`STATUS_REVOKED` constants from the repositories in management service flows instead of string literals (plan: code quality — Princípio VII) (partial)
