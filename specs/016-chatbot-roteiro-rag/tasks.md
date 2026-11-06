---
description: "Task list for feature 016-chatbot-roteiro-rag"
---

# Tasks: Chatbot de Planejamento de Roteiro (RAG) — RF38/RF39

**Input**: Design documents from `/specs/016-chatbot-roteiro-rag/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Incluídos — a constituição (III, NON-NEGOTIABLE) exige test-first
em toda feature; cada história tem testes escritos ANTES da implementação e
vermelhos antes do código verde.

**Organization**: por user story (US1–US4 da spec), cada um independentemente
implementável/testável.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência de
  tarefa incompleta)
- **[Story]**: user story da spec
- Caminhos absolutos implícitos: raiz do repo (`src/passanorte_back/…`,
  `tests/…`)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: preparar configuração e dependências compartilhadas. Módulo
`chatbot` (esqueleto), tag `Chatbot` e registro em `DOMAIN_MODULES` já
existem — nada a criar ali.

- [X] T001 Verify/test dependency httpx in pyproject.toml (needed by provider client; `uv sync` + `uv run python -I -c "import httpx"`; add explicit `httpx` to `[project].dependencies` if import fails), then `uv run ruff check`
- [X] T002 [P] Add chatbot settings to Settings in src/passanorte_back/core/config.py: `chatbot_llm_api_key: str | None = None`, `chatbot_llm_base_url: str | None = None`, `chatbot_llm_model: str | None = None`, `chatbot_timeout_seconds: int = 30`, `chatbot_dwell_minutes: int = 60` (all optional/env-only — research R8; app boots without them)
- [X] T003 [P] Write module docstring in src/passanorte_back/modules/chatbot/__init__.py describing the domain boundary (chat sessions/messages owned here; catalog read-only via projections — plan.md)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: entidades, migração e projeções de leitura que TODAS as
histórias usam. **⚠️ CRITICAL**: nenhuma história começa antes deste
checkpoint.

- [X] T004 Create ChatSession and ChatMessage entities per data-model.md §chat_sessions/§chat_messages in src/passanorte_back/modules/chatbot/repositories/chat.py — `chat_sessions(id PK, tourist_id FK→tourists.id, created_at)`, `chat_messages(id PK, session_id FK→chat_sessions.id, role String(20) 'user'|'assistant', content Text, itinerary JSON nullable, created_at)`; role constrained to the two literals; order by id/created_at
- [X] T005 Create Alembic migration 0011 mapping both tables in migrations/versions/20261106_0011_chatbot_sessions.py (down_revision = 0010; schema must match Base.metadata produced by T004 — test_migrations.py must stay green)
- [X] T006 [P] Create read-only sa.table()/sa.column() projections in src/passanorte_back/modules/chatbot/repositories/read_projections.py mirroring exactly the owner tables (research R5): `tourist_spots(id, name, description, latitude, longitude, status, removed_at)`, `tourist_spot_schedule_entries(spot_id, weekday, opens_at, closes_at)`, `tourist_spot_categories(spot_id, category_key)`, `events(id, spot_id, occurrence_date, description, ticket_price_cents)`, `tourist_interests(tourist_id, category_key)` — verify column names against owner models in src/passanorte_back/modules/tourist_spots/repositories/tourist_spots.py, src/passanorte_back/modules/events/repositories/events.py and src/passanorte_back/modules/tourists/repositories/tourist_interests.py; NO imports of other modules' models (AST boundary gate)
- [X] T007 Verify migration + projections against the test harness: `uv run pytest tests/test_migrations.py tests/smoke` green (checkpoint)
- [X] T008 [P] Create fake LLM provider doubles for tests (in tests/conftest.py or tests/helpers/fake_llm.py): FakeLlmProvider returning configurable canned JSON `{"text":…,"spotIds":[…],"eventIds":[…]}`; variants for error, timeout and malformed-output; NO real network calls (FR-023)

**Checkpoint**: fundação pronta — histórias podem começar. Suíte existente
ainda verde.

---

## Phase 3: User Story 1 — Conversa em linguagem natural monta um roteiro (Priority: P1) 🎯 MVP

**Goal**: turista autenticado cria sessão, envia mensagem em linguagem
natural e recebe resposta com narração + roteiro estruturado ancorado à
base (seqüência ordenada, horário, custo total), com sessão/mensagens
persistidas (FR-001–008, RF38).

**Independent Test**: com base de teste conhecida e provider fake, POST de
mensagem relevante devolve 201 com `assistantMessage.content` + `itinerary`
cujos `refId` existem na base; histórico da sessão retorna ambas as
mensagens.

### Tests for User Story 1 (write FIRST, must FAIL before implementation)

- [X] T009 [P] [US1] Contract tests for the 4 endpoints in tests/contract/test_chatbot_api.py: 201/200 payloads per contracts/chatbot-api.md, camelCase keys, `extra="forbid"` 422 on unknown/snake_case keys, 401 unauthenticated, 403 non-tourist, 404 foreign/unknown session (foreign = 404, not 403), ApiError shape on every failure
- [X] T010 [P] [US1] Integration test: full chat flow end-to-end in tests/integration/test_chatbot_flow.py — seed tourist + spots/events (explicit `session.commit()`), create session, send message with FakeLlmProvider, assert user+assistant messages persisted and GET history returns both, itinerary embedded in assistant message only, refIds ∈ seeded base (FR-006)

### Implementation for User Story 1

- [X] T011 [US1] Implement session/message persistence queries in src/passanorte_back/modules/chatbot/repositories/chat.py: create_session, list_sessions_for_tourist, get_owned_session, add_message, list_messages (depends on T004)
- [X] T012 [US1] Implement the injectable LLM provider interface and HTTP client in src/passanorte_back/modules/chatbot/services/providers.py: `LlmProvider` protocol `complete(...)`; `HttpLlmProvider` using httpx against Settings-provided base_url/model with `chatbot_timeout_seconds` timeout; raises typed `ProviderUnavailable`/`ProviderError` per research R4; unreadable/absent settings → `ProviderUnavailable`
- [X] T013 [US1] Implement retrieval pipeline in src/passanorte_back/modules/chatbot/services/retrieval.py per research R2 (signature per implementation: `retrieve_candidates(session, *, tourist_id, at, target_day, query)`): SQL structural filters over read_projections (active spots `status='open'` and `removed_at IS NULL`; events of target day), normalized token-overlap relevance scoring; final signature per implementation: `retrieve_candidates(session, *, tourist_id, at, target_day, query)` (lowercase, accent-stripped, basic pt-BR stopwords) on name/description/category labels; returns candidates with score (FR-007)
- [X] T014 [US1] Implement itinerary planner + snapshot assembly in src/passanorte_back/modules/chatbot/services/planning.py: anchor provider ids to retrieved candidates (drop unanchorable — FR-006), order candidates, sequential suggested times with `chatbot_dwell_minutes`, cost per item (`ticket_price_cents`, spots=0) and `totalCostCents`; emits the itinerary snapshot dict per data-model.md shape (FR-005, FR-025)
- [X] T015 [US1] Implement the orchestrating service in src/passanorte_back/modules/chatbot/services/chat.py: create/list/get history + send-message flow — persist user message, retrieve candidates, build prompt (city/config context only — RNF06), call provider, anchor + plan + assemble assistant message, persist both (FR-013; i18n-ready content per configured language — FR-019)
- [X] T016 [US1] Create API schemas in src/passanorte_back/modules/chatbot/schemas/chat.py (all inheriting `core.schemas.ApiModel`, snake attrs → camelCase JSON per contracts/chatbot-api.md): CreateSessionResponse, SessionListItem, SessionListResponse, SessionHistoryResponse, ChatMessageView, ItineraryView/ItineraryItemView, SendMessageRequest (non-empty text), MessagePairResponse
- [X] T017 [US1] Implement routes in src/passanorte_back/modules/chatbot/routes/chat.py: POST/GET /sessions, GET /sessions/{session_id}, POST /sessions/{session_id}/messages — `Depends(require_tourist)` (pattern from src/passanorte_back/modules/visitation/routes/visitations.py), 404 for foreign/unknown session, NO tag strings (applied by core/routers.py), errors via core.error_handlers only
- [X] T018 [US1] Run all US1 tests + gates: `uv run pytest tests/contract/test_chatbot_api.py tests/integration/test_chatbot_flow.py tests/smoke tests/test_migrations.py && uv run ruff check` green

**Checkpoint**: MVP funcional ponta a ponta — sessões, conversa e roteiro
ancorado à base, testáveis isoladamente (demo com provider fake).

---

## Phase 4: User Story 2 — Roteiro considera os critérios do RF39 (Priority: P2)

**Goal**: roteiro respeita horários de funcionamento, custo de ingressos,
proximidade geográfica (Haversine greedy) e prioriza interesses do turista
(FR-009–012, FR-021, FR-024, SC-001–003).

**Independent Test**: com base de teste de coordenadas/horários/categorias
controladas, o roteiro observado exclui ponto fechado na hora alvo, soma
ingressos corretamente, ordena por rota razoável e prioriza categorias de
interesse.

### Tests for User Story 2 (write FIRST, must FAIL before implementation)

- [X] T019 [P] [US2] Unit tests for retrieval relevance + interest boost in tests/unit/chatbot/test_retrieval.py: relevant query returns the RIGHT seeded spots (FR-020/SC-001); interests of the tourist outrank non-interest candidates (FR-012); closed/wrong-day events never become candidates (FR-009/FR-024)
- [X] T020 [P] [US2] Unit tests for planning criteria in tests/unit/chatbot/test_planning.py: greedy nearest-neighbor Haversine order avoids zigzag (SC-003); suggested times stay inside operating hours (FR-009); total cost = sum of event ticket prices, free spots add 0 (FR-010/SC-002)
- [X] T021 [P] [US2] Unit tests for the FR-021 constraint validator in tests/unit/chatbot/test_validator.py: itinerary referencing only existing ids, only open-now items, correct cost sum → valid; inventing an id, closed item, wrong sum → invalid with error reasons

### Implementation for User Story 2

- [X] T022 [US2] Implement constraint validator in src/passanorte_back/modules/chatbot/services/validator.py (FR-021): validate ids against candidate set, operating-hours per suggested time, event-day match, cost sum recomputation; returns pass/fail with reasons; raise used by chat service to drop invalid items (depends on T013/T014)
- [X] T023 [US2] Upgrade planning to full RF39 criteria in src/passanorte_back/modules/chatbot/services/planning.py: greedy nearest-neighbor ordering by Haversine on spot coordinates; interest-category prioritization from tourist_interests projection; skip/penalize closed items; event-day-only filtering (FR-024); target-day/time resolution (tourist-stated time or conversation moment — spec clarification)
- [X] T024 [US2] Wire validator + criteria plan into the send-message flow in src/passanorte_back/modules/chatbot/services/chat.py: validator result drops unanchorable items; empty valid itinerary → FR-014 natural-language "no compatible options" response without itinerary
- [X] T025 [US2] Run all US2 tests + gates green (`tests/unit/chatbot/…`, full suite, ruff; SC-001–003 verified)

**Checkpoint**: roteiros passam na constraint FR-021 — qualidade do RF39
provada por testes, independente do provedor.

---

## Phase 5: User Story 3 — Sessão persistida com histórico do turista (Priority: P3)

**Goal**: continuidade da conversa — o histórico da sessão alimenta a
resposta seguinte; histórico sobrevive a retomadas (FR-022, Story 3).

**Independent Test**: duas mensagens na mesma sessão; a segunda (ajuste
"troque X por algo mais barato") produz resposta coerente com a primeira;
histórico lido depois contém tudo.

### Tests for User Story 3 (write FIRST, must FAIL before implementation)

- [X] T026 [P] [US3] Integration test: conversation continuity in tests/integration/test_chatbot_flow.py (append) — two sequential sends in one session; assert second prompt received by FakeLlmProvider embeds prior history (fake records prompt), and GET history returns all four messages in order (FR-022/SC-004)

### Implementation for User Story 3

- [X] T027 [US3] Include session history in the generation context in src/passanorte_back/modules/chatbot/services/chat.py: prompt assembly carries the last N messages of the session (bounded, oldest→newest) plus prior itineraries as compact context (FR-013; no history leakage across sessions)
- [X] T028 [US3] Run US3 tests + full suite + ruff green

**Checkpoint**: conversa multi-turno coerente com o contexto do turista.

---

## Phase 6: User Story 4 — Comportamento degradado sem provedor (Priority: P4)

**Goal**: provedor ausente/falho/timeout/malformado → resposta
conversacional de indisponibilidade, nunca 5xx, sem roteiro parcial;
sessões anteriores intactas (FR-017, FR-018, Story 4, SC-005).

**Independent Test**: com fakes de erro/timeout/malforma/sem-chave, POST
mensagem devolve 201 com `itinerary:null` + content padrão; histórico
mantém mensagens; app sobe sem chave.

### Tests for User Story 4 (write FIRST, must FAIL before implementation)

- [X] T029 [P] [US4] Integration tests: degraded scenarios in tests/integration/test_chatbot_degraded.py — (1) no API key configured, (2) FakeProvider raises ProviderError, (3) timeout > `chatbot_timeout_seconds`, (4) malformed output (non-JSON / zero anchorable ids): each returns 201, `itinerary:null`, localized unavailability text, user message persisted, prior history intact, no 5xx ever

### Implementation for User Story 4

- [X] T030 [US4] Implement degraded handling in src/passanorte_back/modules/chatbot/services/chat.py: catch ProviderUnavailable/ProviderError/timeout/malformed per research R4; persist assistant message with localized standard text (single source text constant, pt-BR via config language — FR-019), `itinerary:null`; document behavior in module docstring
- [X] T031 [US4] Run US4 tests + full suite + ruff green

**Checkpoint**: robustez comprovada — todos os 4 cenários degradados verdes.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T032 [P] Update README.md feature list / docs with the Chatbot endpoints, env vars (CHATBOT_LLM_API_KEY/BASE_URL/MODEL/TIMEOUT/DWELL) and degraded-mode behavior note (concise, English docs)
- [X] T033 [P] Add `tests/unit/chatbot` retrieval/planning/validator seed fixtures to the shared test harness conventions (reuse sessionfactory_for + explicit commit patterns from tests — project memory), removing any duplicated seed code
- [X] T034 Run quickstart.md validation end-to-end: full `uv run pytest` (unit/contract/integration/smoke + migrations), `uv run ruff check && uv run ruff format --check`, AST boundary gate green — zero external network proven
- [X] T036 [P] Close analyze findings F2/F3 (FR-019 localization + SC-007 portability): unit tests for the localized-text picker (exact language, language-base fallback, Portuguese canonical) and config-driven category labels in tests/unit/chatbot/test_localization.py (alternative location fixture — no language/city/category hardcode)
- [X] T035 Final walkthrough of FR-001…FR-019 and SC-001…SC-008 against the implemented code with /speckit-analyze (cross-artifact consistency) — walkthrough performed inline during implementation; formal analysis completed by /speckit-analyze session 2026-11-06

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (P1: T001–T003)**: imediato, sem dependências.
- **Foundational (P2: T004–T008)**: depende do Setup; **bloqueia todas as
  histórias** (entidades + migração + projeções + fakes).
- **US1 (P3: T009–T018)**: MVP — depende da fundação; entrega roteiro
  end-to-end.
- **US2 (P4: T019–T025)**: depende de US1 (usa retrieval/planning/chat);
  adiciona os critérios RF39 + validator.
- **US3 (P5: T026–T028)**: depende de US1 (fluxo de chat existente);
  independente de US2.
- **US4 (P6: T029–T031)**: depende de US1 (fluxo de chat + providers);
  independente de US2/US3.
- **Polish (P7: T032–T035)**: depende da conclusão das histórias desejadas.

### User Story Dependencies

- US1 após fundação — sem dependência entre histórias.
- US2 estende o planejador de US1 (mesmos arquivos) → sequencial após US1.
- US3 e US4 tocam `services/chat.py` também → sequencial após US1; entre
  si, US3 e US4 podem ser paralelizadas se editadas em commits separados.

### Within Each User Story

- Testes primeiro (vermelhos), depois modelos/serviços, depois rotas,
  depois execução da suíte completa (gates da constituição).

### Parallel Opportunities

- Setup/Foundational: T002, T003, T006, T008 em paralelo.
- Por história: todos os testes ([P]) antes da implementação podem ser
  escritos em paralelo.
- US3 e US4 paralelizáveis (após US1).

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phases 1–2 → fundação.
2. Phase 3 (US1) → **STOP and VALIDATE** (checkpoint T018).
3. Demo com provider fake; deploy/demo se pronto.

### Incremental Delivery

US1 (MVP) → US2 (qualidade RF39) → US3 (continuidade) → US4 (robustez) →
Polish. Cada incremento deixa a suíte completa verde.

---

## Notes

- Código em inglês (NON-NEGOTIABLE); conteúdo de usuário pt-BR via config.
- Nenhum segredo no repo; nenhuma chamada externa em testes (FR-023).
- Commit após cada tarefa ou grupo lógico.
