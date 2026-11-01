---
description: "Task list for feature implementation"
---

# Tasks: Turistas e Perfil (módulo tourists)

**Input**: Design documents from `/specs/003-turistas-perfil/`

**Prerequisites**: plan.md (required), spec.md (required for user stories),
research.md, data-model.md, contracts/tourists.md, quickstart.md

**Tests**: OBRIGATÓRIOS nesta feature — Constituição III (Test-First
NON-NEGOTIABLE): teste escrito → falha → implementação → verde. Cada story
tem sua tarefa de teste ANTES das tarefas de implementação.

**Organization**: Tasks are grouped by user story to enable independent
implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

Monolito modular existente: `src/passanorte_back/` (código),
`migrations/versions/` (Alembic), `tests/` (pytest),
`config/location.json` (dados portáteis — RNF06).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Dependência nova e dados portáteis antes de qualquer código

- [X] T001 Add `cryptography` dependency to `pyproject.toml` (Fernet para
      RNF08 — única justificativa em `research.md` R1) e regenere o lockfile
- [X] T002 [P] Add `interest_categories` block to `config/location.json`:
      lista de objetos `{"key": "<english>", "label": "<pt-BR>"}` com no
      mínimo `gastronomy`/"Gastronomia", `nature`/"Natureza",
      `culture`/"Cultura" (RNF06 — dados, não código; research R4)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Infra compartilhada que BLOQUEIA todas as stories — sem isso,
nenhuma story começa

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T003 [P] Write unit tests for shared crypto in `tests/unit/test_crypto.py`
      (TEST-FIRST, deve FALHAR): roundtrip Fernet encrypt→decrypt,
      ciphertext ≠ valor plano, mesmo valor → ciphertext distinto (IV
      aleatório) mas mesmo lookup HMAC (determinístico), lookups de
      contextos distintos (ex.: cpf vs email) → HMACs distintos, chave
      ausente → erro explícito
- [X] T004 Implement `src/passanorte_back/core/crypto.py` (research R1):
      `encrypt_value(value, key)` (Fernet), `decrypt_value(ciphertext,
      key)` e `lookup_hash(value, *, context, key)` (HMAC-SHA256 keyado,
      contexto como info do HKDF derivado da chave) — faça os testes T003
      passar
- [X] T005 [P] Extend `src/passanorte_back/core/config.py` (research R2/R4):
      campo `sensitive_data_key: str` **sem default** (validação
      não-vazia idêntica a `database_url`/`jwt_secret`) e método
      `resolved_interest_categories()` com o mesmo padrão de
      `resolved_languages()` (location.json > nada em código; erro
      estruturado `LocationDataError` para bloco ausente/vazio/inválido;
      cada item precisa de `key` não-vazio e `label` não-vazia)
- [X] T006 [P] Write migration `migrations/versions/20261031_0003_tourists.py`
      (data-model.md): tabela `tourists` — `id` PK,
      `first_name` string(100) NOT NULL, `last_name` string(100) NOT NULL,
      `country_of_origin` string(100) NOT NULL, `email_encrypted` NOT NULL,
      `email_lookup` string(64) NOT NULL UNIQUE indexado, `phone_encrypted`
      NOT NULL, `cpf_encrypted` nullable, `cpf_lookup` string(64) nullable
      UNIQUE indexado, `passport_encrypted` nullable, `passport_lookup`
      string(64) nullable UNIQUE indexado, `password_hash` string(255) NOT
      NULL, `created_at`/`updated_at` timestamp UTC; tabela
      `tourist_interests` — `id` PK, `tourist_id` FK→`tourists.id` indexed
      ON DELETE CASCADE, `category_key` string(100) NOT NULL, UNIQUE
      `(tourist_id, category_key)`; down() derruba ambas; rode
      `uv run pytest tests/test_migrations.py` para validar
- [X] T007 [P] Create Tourist model in
      `src/passanorte_back/modules/tourists/repositories/tourists.py`
      espelhando exatamente a migration T006 (SQLAlchemy 2.x Mapped/
      mapped_column, padrão da fundação); repositório não descriptografa —
      apenas persiste/consulta por colunas `*_encrypted`/`*_lookup`
- [X] T008 Extend auth session types in
      `src/passanorte_back/modules/auth/repositories/auth_sessions.py`:
      `ACCOUNT_TYPES += ("tourist",)` e
      `AccountType = Literal["admin", "employee", "tourist"]` (sem
      migration — coluna String(10) sem CHECK, data-model §3)

**Checkpoint**: infra de cripto, config, tabelas e tipos de sessão prontos —
stories podem começar (em paralelo, se houver capacidade)

---

## Phase 3: User Story 1 — Cadastro único de turista (Priority: P1) 🎯 MVP

**Goal**: Um turista se cadastra com nome, sobrenome, país, telefone,
e-mail, senha e CPF **ou** passaporte; dados sensíveis ficam criptografados
(RF22, RNF08/10)

**Independent Test**: POST `/api/v1/tourists` com payload válido → 201 sem
dado sensível na resposta; payloads inválidos → 422 específico; duplicado →
409 — testável sem login

### Tests for User Story 1 (test-first ⚠️ — devem FALHAR antes da implementação)

- [X] T009 [P] [US1] Write contract tests for registration in
      `tests/contract/test_tourists_register.py`: 201 com CPF com máscara
      válido (resposta só `{id, first_name, last_name, country_of_origin}`),
      201 com passaporte `AB123456`, 422 CPF com verificadores inválidos,
      422 e-mail malformado, 422 telefone sem `+` (ex.:
      `5511999999999`), 422 passaporte fora de `^[A-Za-z0-9]{6,10}$`, 422
      sem nenhum documento, 422 com dois documentos, 422 senha < 8, 422
      nome/país > 100 chars, 409 e-mail duplicado (sem revelar a conta
      existente), 409 mesmo CPF em outro cadastro (clarificações s1/s2/s3
      e SC-001/SC-002), cadastro **concorrente**: 2 requisições em
      paralelo com o mesmo e-mail → exatamente 1 persiste e a outra
      recebe 409 (SC-002 / edge case da spec); ao final inspecione a
      sessão SQLite: nenhum valor
      sensível em texto claro (SC-005/SC-007)

### Implementation for User Story 1

- [X] T010 [US1] Create Pydantic schemas in
      `src/passanorte_back/modules/tourists/schemas/tourists.py`:
      `TouristCreateRequest` (campos + validadores de campo com as regras
      verbatim: cpf com/sem máscara normalizado a 11 dígitos com dígitos
      verificadores; passport `^[A-Za-z0-9]{6,10}$`; phone
      `^\+[0-9]{8,15}$`; email trim+lowercase; senha ≥ 8; nome/sobrenome/
      país 1–100 após trim; model validator "exatamente um documento" —
      FR-001/FR-002/FR-005a/FR-013a-c) e `TouristRegistered`
      (`id`, `first_name`, `last_name`, `country_of_origin` ONLY)
- [X] T011 [US1] Implement `register_tourist` in
      `src/passanorte_back/modules/tourists/services/tourists.py`:
      recriptografa os sensíveis via `core.crypto` (email/cpf/passaporte/
      phone; lookups HMAC com contexto por campo), checa unicidade por
      lookup (e-mail, CPF, passaporte — entre turistas SOMENTE, clar.
      s1-Q1), persiste bcrypt (rounds fundação), auditoria
      `tourist.register` (success/failure) e levanta erro de duplicidade
      mapeável para 409
- [X] T012 [US1] Implement `POST /tourists` route in
      `src/passanorte_back/modules/tourists/routes/tourists.py` no router
      canônico (import-time decoration, padrão da fundação): mapeia
      `InvalidCredentialsError`-analogias → 409 e erros de serviço → 422;
      faça os testes T009 passar

**Checkpoint**: US1 totalmente funcional e testável de forma independente —
MVP de cadastro pronto (`uv run pytest tests/contract/test_tourists_register.py`)

---

## Phase 4: User Story 2 — Login do turista (Priority: P1)

**Goal**: O turista autentica com e-mail+senha e recebe o par de credenciais
da fundação (`role="tourist"`); RBAC reconhece a identidade turista (RF23,
RNF09)

**Independent Test**: POST `/api/v1/tourists/login` com e-mail/senha
corretos → 200 com par; incorretos → 401 genérico; access token do turista
autentica (401 sem, 403 para admin/funcionário em rota exclusiva) — usa o
cadastro da US1 ou fixture

### Tests for User Story 2 (test-first ⚠️)

- [X] T013 [P] [US2] Write contract tests for login and tourist identity in
      `tests/contract/test_tourists_login.py`: login correto → 200 com
      `access_token`/`refresh_token`/`role: "tourist"`/`expires_in`; senha
      errada → 401 `{"detail": "invalid credentials"}`; e-mail inexistente
      → **mesma** mensagem 401; e-mail com espaços/maiúsculas
      (` ana@example.com `) loga igual (FR-013); POST `/auth/refresh` com o
      refresh do turista → 200 novo par (fundação extendida);
      `GET /tourists/me` com access token de turista → 200 (uso real do
      token); access token de admin em `/tourists/me` → 403; sem token →
      401 (FR-015, s16)

### Implementation for User Story 2

- [X] T014 [US2] Refactor auth credential issue to public service in
      `src/passanorte_back/modules/auth/services/authentication.py`:
      `_issue_pair` → `issue_session(session, *, account_type, account_id,
      role) -> SessionTokens` (interface pública, regra 5; assinatura
      existente admin/employee preservada nos call sites)
- [X] T015 [US2] Implement `tourist_login` in
      `src/passanorte_back/modules/tourists/services/tourists.py`:
      normaliza e-mail (trim+lower), busca por `email_lookup`, verificação
      bcrypt, `issue_session` do auth com `account_type="tourist"`,
      `role="tourist"`; auditoria `tourist.login.success`/
      `tourist.login.failure` com mensagem genérica sem distinguir causa
      (FR-014, pesquisa R3)
- [X] T016 [US2] Add `POST /tourists/login` route in
      `src/passanorte_back/modules/tourists/routes/tourists.py` (401 na
      falha)
- [X] T017 [US2] Extend tourist identity resolution in
      `src/passanorte_back/modules/auth/services/security.py`: branch
      `account_type == "tourist"` em `get_current_user` (lazy import da
      função pública `get_tourist_account` de
      `src/passanorte_back/modules/tourists/services/tourists.py` — padrão
      employees) e novo gate `require_tourist` (403
      `insufficient permissions` para não-turistas, exportado em
      `__all__`); crie essa função pública do lado dos turistas; também
      estenda a revalidação por id no `refresh` (branch tourist via lazy
      import); faça os testes T013 passar

**Checkpoint**: US2 funcional — turista autentica e usa o token; RBAC da
fundação reconhece o papel turista

---

## Phase 5: User Story 3 — Visualizar e editar o próprio perfil (Priority: P2)

**Goal**: Turista autenticado lê o próprio perfil (descriptografia
controlada) e edita-o; terceiro → 403; admin mantém acesso (princípio I)
(RF24)

**Independent Test**: com dois turistas cadastrados e logados, `GET/PATCH
/tourists/{outro_id}` → 403 e nada muda; `GET/PATCH /tourists/me` →
próprio dado descriptografado e persistido

### Tests for User Story 3 (test-first ⚠️)

- [X] T018 [P] [US3] Write contract tests for profile in
      `tests/contract/test_tourists_profile.py`: `GET /me` retorna e-mail/
      telefone/CPF legíveis do próprio (FR-006/FR-007) e
      `interests: []` quando sem seleção; `GET /tourists/{outro_id}` de
      outro turista → **403** sem vazar existência; `PATCH
      /tourists/{outro_id}` → **403** e dados do alvo inalterados
      (SC-004); `PATCH /me` troca país/telefone → 204 e `GET /me` reflete
      (RF24); troca de documento (passport no lugar de cpf) aceita quando
      válido/único; `PATCH` resultando em nenhum documento → 422; edição
      para e-mail já usado → 409; admin: `GET/PATCH /tourists/{id}` de
      qualquer turista → 200/204, alvo inexistente → 404; sem token → 401;
      `password` no payload é ignorado/rejeitado (fora de escopo)

### Implementation for User Story 3

- [X] T019 [P] [US3] Create profile schemas in
      `src/passanorte_back/modules/tourists/schemas/tourists.py`:
      `TouristProfileResponse` (id, first_name, last_name,
      country_of_origin, **email, phone, cpf, passport_number legíveis +
      interests**) e `TouristUpdateRequest` (todos opcionais, sem
      `password`), reusando os mesmos validadores de campo da US1
- [X] T020 [US3] Implement profile service in
      `src/passanorte_back/modules/tourists/services/profile.py`:
      `get_tourist_profile` (descriptografia controlada — services only,
      SC-005), `get_tourist_account` (view para a dependência de auth,
      lazy-importada em T017), `update_tourist_profile` (PATCH parcial,
      revalida cada campo presente, troca de documento mantendo XOR,
      unicidade → 409, auditoria `tourist.profile.update`)
- [X] T021 [US3] Implement routes in
      `src/passanorte_back/modules/tourists/routes/profile.py`:
      `GET /tourists/me` + `GET/PATCH /tourists/{tourist_id}` —
      permissão self-ou-admin em service/route (403 outro turista, 404
      admin sem alvo, 401 sem token); faça os testes T018 passar

**Checkpoint**: US3 funcional — perfil legível/editável com 403 real para
terceiros; junto com US1+US2, o fluxo cadastro→login→editar funciona

---

## Phase 6: User Story 4 — Seleção e atualização de interesses (Priority: P2)

**Goal**: Turista autenticado consulta categorias configuradas e
salva/atualiza sua seleção integralmente (RF25, RNF06)

**Independent Test**: `GET /tourists/interest-categories` == configuração;
`PUT /tourists/me/interests` com chaves válidas → 200 e leitura
consequente; chave inexistente → 422 — testável com login da US2

### Tests for User Story 4 (test-first ⚠️)

- [X] T022 [P] [US4] Write contract tests for interests in
      `tests/contract/test_tourists_interests.py`: lista de categorias ==
      exatamente o `location.json` (key/label; SC-006); PUT
      `["gastronomy","nature"]` → 200 e GET reflete; PATCH de troca
      (`remove uma, adiciona outra`) → reflete exatamente a última
      atualização, sem duplicatas nem resíduos (FR-010); lista vazia →
      limpa a seleção; PUT com `["xpto"]` → 422 nomeando a categoria
      inválida (FR-011); sem limite de quantidade (selecionar todas as
      categorias configuradas é válido — s3-Q1); duplicatas na entrada são
      normalizadas (aceitas uma vez) → resposta posterior sem duplicatas;
      `GET /me/interests` de turista sem
      seleção → `{"interests": []}` sem erro; rota sem token → 401;
      admin/funcionário em `PUT /me/interests` → 403 (FR-015)

### Implementation for User Story 4

- [X] T023 [P] [US4] Create TouristInterest model in
      `src/passanorte_back/modules/tourists/repositories/tourist_interests.py`
      e interest schemas in
      `src/passanorte_back/modules/tourists/schemas/tourists.py`
      (`InterestCategory` com key/label, `InterestCategoriesResponse`,
      `TouristInterestsResponse`, `TouristInterestsUpdateRequest`)
- [X] T024 [US4] Implement interests service in
      `src/passanorte_back/modules/tourists/services/interests.py`:
      `list_interest_categories` (de `Settings.resolved_interest_categories()`
      — RNF06), `get_tourist_interests` (filtra pelas categorias
      **atualmente configuradas** — categoria órfã omitida, edge case da
      spec), `update_tourist_interests` (valida cada key contra a
      configuração → erro 422; delete+insert numa transação = substituição
      integral; auditoria `tourist.interests.update`)
- [X] T025 [US4] Implement routes in
      `src/passanorte_back/modules/tourists/routes/interests.py`:
      `GET /tourists/interest-categories` (qualquer conta autenticada),
      `GET /tourists/me/interests` + `PUT /tourists/me/interests`
      (`require_tourist`); faça os testes T022 passar

**Checkpoint**: US4 funcional — todas as stories de usuário entregues; fluxo
de personalização completo

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Consistência final, fluxo capstone e gates da constituição

- [X] T026 Write full-lifecycle integration test in
      `tests/integration/test_tourists_lifecycle.py` (SC-003): cadastro →
      login → `GET /me` → `PATCH /me` (editar perfil) →
      `PUT /me/interests` (atualizar interesses) → `GET /me/interests`;
      inclua o 403 em `PATCH /tourists/{outro_id}` no mesmo fluxo e
      inspecione a sessão SQLite ao final: `*_encrypted`/`*_lookup`
      presentes, **nenhum** dado sensível em texto claro, senhas só em
      hash (SC-004/SC-005/SC-007)
- [X] T027 [P] Run `uv run ruff check . && uv run ruff format .`
      e `uv run python -m passanorte_back.core.boundaries` — zero erros
      (gates VII/fronteira)
- [X] T028 [P] Update README/docstrings junto ao código (princípio VII):
      documente `SENSITIVE_DATA_KEY` e o bloco `interest_categories` de
      `location.json` em README.md
- [X] T029 Run full test suite (`uv run pytest`) + validação do
      `specs/003-turistas-perfil/quickstart.md` roteiro — suíte verde e
      gates da constituição satisfeitos

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sem dependências — comece imediatamente
- **Foundational (Phase 2)**: depende do Setup — **BLOQUEIA todas as stories**
- **US1 (Phase 3)**: requer Foundational completo (T003–T008)
- **US2 (Phase 4)**: requer T010 (schemas/cadastro como fixture) e os
  repositórios da Foundational; estende a fundação auth (T014, T017)
- **US3 (Phase 5)**: requer US2 (`require_tourist`, identidade turista)
- **US4 (Phase 6)**: requer US2 (login) e T019 (schema de perfil com
  `interests` no `GET /me`); independente de US3 em conteúdo
- **Polish (Phase 7)**: depende de todas as stories desejadas

### User Story Dependencies

- **US1 (P1)**: independente após Foundational — nenhuma dependência de
  outras stories
- **US2 (P1)**: usa o cadastro da US1 como pré-condição de fixture; estende
  o auth module (arquivos compartilhados com US3 — sequenciar US2 antes)
- **US3 (P2)**: depende da identidade/`require_tourist` de US2; reusa
  validadores da US1
- **US4 (P2)**: depende de US2 (token de turista); independente de US3,
  exceto pelo campo `interests` no `TouristProfileResponse` (T019)

### Within Each User Story

- Testes primeiro (devem FALHAR) → schemas/model → services → routes →
  verde do checkpoint
- Commit após cada task ou grupo lógico

### Parallel Opportunities

- T001–T002 (Setup) quase todo paralelizável
- T003/T005/T006/T007 (Foundational) — arquivos distintos
- Tests de story em paralelo entre si (arquivos distintos)
- US4 pode ser desenvolvida em paralelo com US3 **após** T019 definir o
  schema compartilhado; sem paralelismo com US2 (extensão do auth é
  sequencial)

---

## Implementation Strategy

### MVP First (US1 only)

1. Setup (T001–T002) + Foundational (T003–T008)
2. US1 (T009–T012) → validar checkpoint independentemente
3. Deploy/demo do cadastro se desejado

### Incremental Delivery

1. Setup + Foundational → fundação de cripto/config/tabelas pronta
2. US1 → cadastro funcionando (SC-001/SC-002)
3. US2 → turista autentica com a fundação JWT estendida
4. US3 → perfil próprio e 403 real (SC-004)
5. US4 → interesses configuráveis (SC-006)
6. Polish → fluxo ponta a ponta SC-003 + gates

### Parallel Team Strategy

1. Time completa Setup + Foundational juntos
2. Dev A: US1 → US2 (sequência auth) · Dev B: aguarda T019 e toma US4
   enquanto Dev A faz US3

---

## Notes

- [P] tasks = arquivos diferentes, sem dependências
- [Story] label mapeia a task para rastreabilidade RF/SC
- Verifique que cada teste FALHA antes de implementar (Constituição III)
- Nenhum dado sensível em texto claro em código, teste ou banco
  (RNF08/SC-005) — valide fixtures com dados de exemplo apenas como payload
  de entrada
- Valide cada checkpoint antes de avançar de story
---

## Phase 8: Convergence

**Input**: `/speckit-converge` sobre a implementação das Fases 1–7 — avaliação
do código atual contra spec/plan/tasks/constituição (sem reescrita).

- [X] T030 Remove (or explicitly justify in code review) the unused service
      symbols `get_tourist_credential_view` + `CredentialPayload` and the
      unconsumed `TouristAccount.password_hash` field in
      `src/passanorte_back/modules/tourists/services/tourists.py` — dead code
      reached by no route, service or test (principle V — scope minimization)
      (unrequested)
