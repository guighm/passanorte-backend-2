# Tasks: Fundação do Monolito Modular Backend PassaNorte

**Input**: Design documents from `/specs/001-fundacao-monolito-modular/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Tests**: Incluídos — a constituição torna Test-First NON-NEGOTIABLE (Princípio III) e a spec exige suíte de smoke (FR-021). Cada story tem tarefas de teste QUE DEVEM SER ESCRITAS PRIMEIRO E FALHAR antes da implementação correspondente.

**Organization**: Tarefas agrupadas por user story (US1–US5 da spec) para implementação e teste independentes.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Pode rodar em paralelo (arquivos diferentes, sem dependência de tarefa incompleta)
- **[Story]**: Story de origem (US1–US5)
- Caminhos exatos incluídos em cada descrição

## Path Conventions

Projeto único (layout src, gerenciado por uv): `src/passanorte_back/`, `tests/`,
`config/`, `migrations/` na raiz do repositório.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Dependências, tooling de qualidade e dados de localidade. Nenhuma
dependência entre si — T001 completa primeiro (toda a árvore depende dos deps).

- [X] T001 Adicionar dependências ao pyproject.toml: `pydantic-settings`, `sqlalchemy>=2.0`, `alembic` em [project].dependencies; `pytest` e `ruff` em [dependency-groups] / dev; executar `uv sync` e confirmar instalação limpa
- [X] T002 [P] Configurar ruff no pyproject.toml (target `py313`, line-length 100, regra de qualidade padrão) e verificar `uv run ruff check .` zero erros na base atual
- [X] T003 [P] Criar `config/location.json` com `{"city": "Passa Quatro", "languages": ["pt-BR"]}` (dados de localidade, RNF06 — nunca importado como código)
- [X] T004 [P] Adicionar ao .gitignore: `.env`, `.env.*`, `*.db`, `*.sqlite3` (nenhum segredo ou banco versionado — FR-011)

**Checkpoint**: `uv sync` roda; `ruff check` limpo; dados de localidade versionados sem segredos.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Infraestrutura usada por TODAS as stories: esqueleto dos 10 módulos,
conftest de teste e Settings essenciais. ⚠️ CRITICAL: nenhuma story começa antes
desta fase completa.

- [X] T005 Criar os 10 pacotes de domínio em `src/passanorte_back/` — `auth`, `funcionarios`, `turistas`, `pontos_turisticos`, `eventos`, `gamificacao`, `visitacao`, `dashboard`, `notificacoes`, `chatbot` — cada um com `routes/`, `services/`, `repositories/`, `schemas/` (subpacotes vazios com `__init__.py` e docstring) (FR-002, FR-003)
- [X] T006 [P] Criar `tests/conftest.py`: fixture de ambiente de teste fixando env `DATABASE_URL=sqlite:///:memory:` e `JWT_SECRET` sintético (nunca real — Quality Gate), autouse para todos os testes
- [X] T007 [P] Escrever `tests/smoke/test_settings_essentials.py` (RED primeiro): ausência de `DATABASE_URL` ou de `JWT_SECRET` deve interromper a construção de Settings com mensagem nomeando o campo (FR-012); nenhum valor default para os 2 essenciais
- [X] T008 Implementar `src/passanorte_back/core/config.py`: `Settings` (BaseSettings, `env_file=".env"`, `extra="ignore"`) com `database_url: str` e `jwt_secret: str` essenciais, validadores exigindo strings não vazias (FR-010/011/012; research R1) — T007 fica verde

**Checkpoint**: Settings essenciais verde; esqueleto de módulos e conftest prontos — stories podem começar.

---

## Phase 3: User Story 1 — App executável com verificação de saúde (P1) 🎯 MVP

**Goal**: Aplicação única sobe, `/health` responde 200 saudável / 503 degradado
com estado do banco (clarificação Q1).

**Independent Test**: `uv run uvicorn passanorte_back.main:app` + `curl /health`
→ 200 `{"status":"ok","database":"ok"}`; com banco inacessível → 503
`{"status":"degraded","database":"unavailable"}` (quickstart passo 2).

**Why MVP**: valida toda a cadeia build/execute/teste — é o único slice
necessário para o critério de aceitação mínimo "app sobe, /health responde".

### Tests for User Story 1 ⚠️ (escrever primeiro, garantir RED)

- [X] T009 [P] [US1] Escrever contrato `/health` saudável em `tests/smoke/test_health.py`: HTTP 200 com corpo `{"status":"ok","database":"ok"}` usando SQLite em memória do conftest, via TestClient (contracts/health.md)
- [X] T010 [P] [US1] Escrever contrato `/health` degradado em `tests/smoke/test_health.py`: HTTP 503 com corpo `{"status":"degraded","database":"unavailable"}` quando o ping do banco falha (contracts/health.md)

### Implementation for User Story 1

- [X] T011 [US1] Implementar `src/passanorte_back/core/db.py`: engine síncrono + `sessionmaker` a partir de `settings.database_url` e `ping_database() -> bool` executando `SELECT 1` com timeout fixo de 2 s (SC-002 "< 1 s" vale para o caso saudável; caso degradado não tem meta de tempo, apenas correção do 503); todas as convergências de motor concentradas aqui (research R2) (T008)
- [X] T012 [US1] Reescrever `src/passanorte_back/main.py`: app FastAPI único, remover o placeholder `/items/{item_id}`, adicionar `GET /health` na raiz com 200/503 por `ping_database()`; scripts `passanorte-back`/`dev` continuam funcionando. Montagem de routers ocorre em T015 (US2) — US1 não depende de routers (T009, T010, T011 verdes)

**Checkpoint**: MVP funcional — app sobe, `/health` 200/503 correto, testes de
contrato verdes; scripts `passanorte-back`/`dev` continuam funcionando (research R9).

---

## Phase 4: User Story 2 — Esqueleto de módulos com fronteiras rígidas (P2)

**Goal**: 10 módulos registrados sob `/api/v1` com verificação automatizada de
fronteira (0 imports ilícitos; violação deliberada quebra o teste).

**Independent Test**: Executar suíte de fronteiras → 0 violações; introduzir
import ilegal deliberado → teste falha apontando módulo/arquivo; OpenAPI expõe
os 10 prefixos.

### Tests for User Story 2 ⚠️ (escrever primeiro)

- [X] T013 [P] [US2] Escrever `tests/smoke/test_modules.py`: app via TestClient sobe sem erro; `app.routes` contém os routers montados com os 10 prefixos `/api/v1/<modulo>` (contrato em contracts/module-routers.md, tabela completa — routers vazios não geram paths no OpenAPI, por isso a verificação é pelos routers montados, não pelos paths); `/health` e `/docs` fora do prefixo (RED contra T015)
- [X] T014 [P] [US2] Escrever `tests/smoke/test_boundaries.py`: varredura AST de `src/passanorte_back/*` falhando ao detectar import cruzado de internals privados de outro módulo (`schemas`, `repositories`, `routes`, símbolos com prefixo `_`); imports de `<modulo>.services`, `core.*` e `main` permitidos; incluir teste negativo embutido que viola em memória e espera falha da função de detecção (FR-004/005; research R5)

### Implementation for User Story 2

- [X] T015 [US2] Implementar `src/passanorte_back/core/routers.py`: registro central ordem-estável com 1 APIRouter por módulo, prefixo = nome do pacote com `_` → `-` (ex.: `pontos_turisticos` → `/api/v1/pontos-turisticos`) e `include_router` efetivado em `main.py` (T013 verde)
- [X] T016 [US2] Provar eficácia da verificação (SC-005): introduzir temporariamente um import ilegal deliberado em um módulo, confirmar que `test_boundaries.py` falha apontando módulo/arquivo ofensores, e reverter — registrar resultado no checklist final da story

**Checkpoint**: Estrutura de módulos íntegra e montada; fronteiras exigidas pelo
build de teste.

---

## Phase 5: User Story 3 — Configuração inteiramente externa ao código (P3)

**Goal**: Defaults documentados + dados de cidade/idiomas lidos de
`config/location.json` (RNF06), override por ambiente, valores inválidos falham.

**Independent Test**: Alterar `config/location.json` (ou env) e reiniciar → novos
valores efetivos sem mudança de código; `GPS_TOLERANCE_RADIUS_M=0` ou
`ENABLED_LANGUAGES=[]` explícito → startup falha com mensagem clara.

### Tests for User Story 3 ⚠️ (escrever primeiro)

- [X] T017 [P] [US3] Escrever `tests/smoke/test_settings_portability.py` (RED): defaults aplicados (`jwt_ttl=3600`, `gps_tolerance_radius_m=100.0`), `resolved_city()`/`resolved_languages()` lendo `config/location.json`, overrides por env (`CITY_NAME`, `ENABLED_LANGUAGES`, `JWT_TTL`, `GPS_TOLERANCE_RADIUS_M`), e erros para `JWT_TTL<=0`, raio `<= 0`, lista de idiomas explicitamente vazia e `location_data_path` inexistente (FR-010/012/013; data-model AppConfig)

### Implementation for User Story 3

- [X] T018 [US3] Completar `src/passanorte_back/core/config.py`: campos `jwt_ttl`, `gps_tolerance_radius_m`, `city_name`, `languages`, `location_data_path` com defaults do data-model e `resolved_city()`/`resolved_languages()` (override env → arquivo; arquivo ausente/inválido/sem chaves → mensagem explícita) (T017 verde)
- [X] T019 [US3] Atualizar `config/location.json` se necessário para conter exatamente as chaves `city` e `languages` esperadas pela leitura (SC-006: troca de dados sem código)

**Checkpoint**: Portabilidade provada — cidade/idiomas/parâmetros são dados, não código.

---

## Phase 6: User Story 4 — Persistência versionada e portável (P4)

**Goal**: Alembic com baseline vazio aplicável e reversível; PostgreSQL produção
/ SQLite testes pela URL (RNF17).

**Independent Test**: `alembic upgrade head` sobre banco vazio → OK; `alembic
downgrade base` → estado vazio; re-up → OK (quickstart passo 3).

### Tests for User Story 4 ⚠️ (escrever primeiro)

- [X] T020 [P] [US4] Escrever `tests/test_migrations.py` (RED): `upgrade head` sobre SQLite temporário vazio conclui; `downgrade base` reverte; re-`upgrade` reaplica; banco contém apenas `alembic_version` (FR-015/016, SC-003)

### Implementation for User Story 4

- [X] T021 [US4] Criar `alembic.ini` na raiz e `migrations/env.py` lendo `settings.database_url` (nunca hardcoded) + `script.py.mako` do scaffold do Alembic
- [X] T022 [US4] Criar revision baseline vazia em `migrations/versions/` (up/down idempotentes, sem tabela de negócio — FR-007 e clarificação Q3) (T020 verde)

**Checkpoint**: Fluxo de migrations versionadas estabelecido para todas as features futuras.

---

## Phase 7: User Story 5 — Infraestrutura de auditoria pronta para uso (P5)

**Goal**: Serviço `record_action` emitindo registro JSON estruturado com os 5
campos obrigatórios (RNF19), log-only (clarificação Q3).

**Independent Test**: Registrar ação simulada no teste e inspecionar a linha
emitida: JSON com `timestamp`, `actor`, `action`, `target`, `result`.

### Tests for User Story 5 ⚠️ (escrever primeiro)

- [X] T023 [P] [US5] Escrever `tests/smoke/test_audit.py` (RED): `record_action` emite exatamente 1 registro JSON por ação com os 5 campos mínimos e `detail` opcional; `result` distingue `success`/`failure`; falha do sink levanta `AuditError` (FR-017/018, SC-007)

### Implementation for User Story 5

- [X] T024 [US5] Implementar `src/passanorte_back/core/audit.py`: `record_action(actor, action, target, result, *, detail=None)` via logger dedicado `passanorte.audit` com formatter JSON (ISO-8601 UTC), `AuditError` própria, consumível por qualquer módulo via import de `core` (research R4) (T023 verde)

**Checkpoint**: Auditoria consumível por toda feature futura sem reinventar formato (FR-019).

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T025 [P] Escrever `README.md`: objetivo, estrutura de módulos, variáveis de ambiente (essenciais e defaults), como rodar (referência a quickstart.md)
- [X] T026 [P] Documentar serviço de auditoria e fronteira de módulos em docstrings de `src/passanorte_back/core/audit.py` e `core/routers.py` (Princípio VII)
- [X] T027 Auditar segurança: `grep` por segredos/valores hardcoded no código e históricos de teste (FR-011); confirmar `.env` não rastreado pelo git
- [X] T028 Executar validação end-to-end do `specify`: `specs/001-fundacao-monolito-modular/quickstart.md` passo a passo (app sobe, `/health` 200/503, alembic up/down, pytest 100%, ruff limpo) — checklist do critério de aceitação
- [X] T029 [P] Validar migration contra PostgreSQL em container (`alembic upgrade head` + `downgrade base` com `DATABASE_URL=postgresql://...` local), documentando comando e resultado no quickstart passo 3 (FR-016, perfil produção)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (T001–T004)**: sem dependências — T002/T003/T004 [P] podem rodar em paralelo após T001
- **Foundational (T005–T008)**: depende de Setup; T005/T006/T007 [P] em paralelo, T008 após T007 (red→green)
- **User Stories**: todas dependem da Foundational completa
  - US1 (T009–T012): sem dependência de outras stories — **MVP**
  - US2 (T013–T016): T015 depende de T012 (main.py existente); testes de US2 [P] independentes
  - US3 (T017–T019): depende de T008; independente de US1/US2 (paralelizável)
  - US4 (T020–T022): depende de T008; independente de US1/US2/US3 (paralelizável)
  - US5 (T023–T024): depende de T006 (conftest); independente das outras stories (paralelizável)
- **Polish (T025–T028)**: após todas as stories

### User Story Dependencies

- **US1 → US2**: a montagem de routers (T015) edita o `main.py` criado em T012
- **US3, US4, US5**: independentes entre si e de US1/US2 (exceto Foundational)

### Within Each User Story

- Testes primeiro (RED por contrato) → implementação (GREEN) → checkpoint de validação independente

### Parallel Opportunities

- T002/T003/T004 (setup, arquivos distintos)
- T005/T006/T007 (arquivos distintos)
- T009/T010 (mesma story, testes independentes) e T013/T014, T017, T020, T023
- Stories US3/US4/US5 podem ser implementadas em paralelo após Foundational (arquivos distintos: `core/config.py`, `alembic*`, `core/audit.py`)

---

## Parallel Example: User Story 1

```bash
# Testes de contrato juntos (arquivos/casos independentes):
Task: "T009 Contrato /health saudável em tests/smoke/test_health.py"
Task: "T010 Contrato /health degradado em tests/smoke/test_health.py"

# Em seguida, sequencial:
T011 core/db.py → T012 main.py
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Fases 1–2 completas (Setup + Foundational — bloqueiam tudo)
2. US1 completa (T009–T012) → app sobe, `/health` 200/503
3. **STOP and VALIDATE**: quickstart passos 1–2 + `uv run pytest` verde
4. Critério de aceitação mínimo atendido ("app sobe, /health responde")

### Incremental Delivery

1. Foundational → Settings essenciais verde
2. US1 (MVP) → validação independente
3. US2 → fronteiras exigidas pelo build; US3 → portabilidade provada; US4 → migrations; US5 → auditoria
4. Polish → README, docstrings, auditoria de segurança, validação end-to-end
5. Cada story adiciona valor sem quebrar as anteriores — `pytest` permanece verde em cada checkpoint

### Parallel Team Strategy

Com múltiplos desenvolvedores após Foundational:
- Dev A: US1 → US2 (dependentes)
- Dev B: US3 (config)
- Dev C: US4 (migrations) + US5 (auditoria)

---

## Notes

- [P] = arquivos diferentes, sem dependências incompletas
- [Story] rastreia tarefa à user story da spec
- Todos os testes escritos ANTES da implementação (Princípio III, NON-NEGOTIABLE)
- Commit após cada tarefa ou grupo lógico
- Parar em cada checkpoint para validar a story independentemente
- Nenhuma tabela de negócio, nenhum endpoint de RF nesta fase (FR-007)
## Phase 9: Convergence

- [X] T030 Tipar `register_routers(app: FastAPI)` em `src/passanorte_back/core/routers.py`, removendo o `type: ignore[attr-defined]`, mantendo `ruff check`/`ruff format` limpos (FR-020, Princípio VII) (partial)
