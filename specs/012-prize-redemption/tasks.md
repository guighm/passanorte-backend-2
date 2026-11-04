---
description: "Task list for feature 012-prize-redemption implementation"
---

# Tasks: Prize Redemption (Employee Scan)

**Input**: Design documents from `/specs/012-prize-redemption/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Tests**: OBRIGATÓRIOS — constituição Princípio III (Test-First, NON-NEGOTIABLE): todo teste escrito primeiro, verificado vermelho contra o código atual, depois verde. Os testes do plano (SC-001..SC-007) são critério de aceitação.

**Organization**: por user story (spec.md: US1 P1 — resgate com novo estoque na resposta; US2 P1 — falhas claras e idempotência; US3 P2 — audit antes/depois). Toda a mudança é intra-módulo em `modules/gamification/` — sem migration, sem mudança em `core/`, repositories/models intocados (research R5).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: paralelizável (arquivos diferentes, sem dependência pendente)
- **[Story]**: user story dona da tarefa (US1/US2/US3)
- Paths exatos em cada descrição

**Convenção de vermelho/verde**: cada fase começa pelos testes (devem falhar) e só então implementa; cada task de implementação termina com os testes da própria story passando.

## Phase 1: Setup (Baseline)

**Purpose**: confirmar o estado verde antes do toque no código

- [X] T001 Run the full existing gamification suites (`pytest tests/contract/test_gamification.py tests/integration/test_gamification_lifecycle.py`) and `ruff check` to record the green baseline on `src/passanorte_back/modules/gamification/` before any change

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: nenhum — o núcleo transacional (`concede_prize`, guard atômico `try_consume_stock`, claim condicional de código) já existe e está verde da spec 009; não há schema novo nem infraestrutura bloqueante (plan Constitution Check)

*(vazio — prosseguir direto para as user stories após o checkpoint T001)*

---

## Phase 3: User Story 1 — Resgate com novo estoque na resposta (P1) 🎯 MVP

**Goal**: resposta 201 do `POST /api/v1/gamification/redemptions` carrega `prize.stockQuantity` pós-dedução (FR-004), além do código/brinde/turista/rota/ponto/ator já existentes

**Independent Test**: contrato — completar rota com estoque N, resgatar como funcionário, assert 201 e `prize stockQuantity == N - 1` (SC-001)

### Tests for User Story 1 (write FIRST — must FAIL)

- [X] T002 [P] [US1] Update `REDEMPTION_KEYS`/prize keys in `tests/contract/test_gamification.py` and write `test_concession_201_response_carries_new_stock` asserting `body["prize"]["stockQuantity"] == before - 1` on `POST /api/v1/gamification/redemptions` (expect red: field absent today)
- [X] T003 [P] [US1] Extend `tests/integration/test_gamification_lifecycle.py` concession step to assert `prize.stockQuantity` matches the route's prize stock after the call (expect red)

### Implementation for User Story 1

- [X] T004 [US1] Add `stock_quantity: StockQuantity` (JSON `stockQuantity`) to `RedemptionPrizeView` in `src/passanorte_back/modules/gamification/schemas/gamification.py` (inherits `ApiModel`; mirrors `RoutePrizeView` — research R1)
- [X] T005 [US1] Pass the post-deduction `prize.stock_quantity` into `RedemptionView.from_internal` in `src/passanorte_back/modules/gamification/routes/gamification.py` — the handler already re-reads the prize after `concede_prize`; T002/T003 green after this

**Checkpoint**: US2/US3 podem começar — resposta expõe novo estoque (SC-001 ✅)

---

## Phase 4: User Story 2 — Falhas claras, state-preserving e idempotência (P1)

**Goal**: cada causa de falha com mensagem própria no `ApiError`; repetições/concorrência do mesmo código nunca geram segunda baixa (FR-005, FR-003, FR-006; SC-002..SC-004)

**Independent Test**: contrato — código aleatório 404; código usado 409 `redemption code has already been used`; estoque 0 409 `no stock available for this route's prize`; loop de resubmissões com estoque estável e exatamente um 201 histórico

### Tests for User Story 2 (write FIRST — must FAIL)

- [X] T006 [US2] Write `test_concession_conflict_messages_are_distinct` in `tests/contract/test_gamification.py`: assert the already-used 409 and the zero-stock 409 both carry `errorCode: "conflict"` but DISTINCT `message` values matching the canonical texts of contracts/gamification-redemptions.md (expect red: handler merges both messages today)
- [X] T007 [P] [US2] Write `test_concession_repeated_scans_never_double_deduct` in `tests/contract/test_gamification.py`: after one 201, resubmit the same code ≥ 3 times (with stock replenished) asserting every retry 409 and stock constant; zero-stock retry leaves code reusable, and after replenishing stock the SAME rescan succeeds with 201 (per quickstart Cenário 3, closes FR-006's recovery path / SC-004) (green today except the already-used retry `message` — turns red only against the merged handler and green again with T009)
- [X] T008 [US2] Write `test_concession_concurrent_same_code_race` in `tests/integration/test_gamification_lifecycle.py`: two concurrent submissions (threads, following the existing stock-race pattern) of the SAME code → exactly one 201, one 409, one unit deducted (expect red only if a window exists — proves FR-003 under race)
- [X] T009 [US2] Split the merged `(CodeAlreadyUsedError, PrizeStockInsufficientError)` except into two clauses with canonical messages — used: `"redemption code has already been used"`, no stock: `"no stock available for this route's prize"` — in `src/passanorte_back/modules/gamification/routes/gamification.py` (research R3); T006/T007 green; assert no error path changes state (codes intact, stock intact — FR-005)

**Checkpoint**: falhas 404/409/409-distintas/401/403/422 todas cobertas e state-preserving (SC-003, SC-004, SC-006 ✅)

---

## Phase 5: User Story 3 — Audit do resgate com estoque antes/depois (P2)

**Goal**: cada concessão bem-sucedida emite exatamente 1 registro `prize.concede` na transação, com actor, `touristId`, `prizeId`, `routeId`, `pickupSpotId`, `stockQuantityBefore`/`stockQuantityAfter` (FR-007, RNF19; SC-005); falhas não emitem

**Independent Test**: contrato — estoque inicial N conhecido → resgate → inspect logger `passanorte.audit` via fixture `audit_logs`: exatamente um registro com detail completo (before N, after N−1)

### Tests for User Story 3 (T010 red-first; T011 is a pre-green regression guard)

- [X] T010 [P] [US3] Write `test_concession_audit_record_carries_stock_before_and_after` in `tests/contract/test_gamification.py` using the `audit_logs` fixture (pattern of `test_create_route_audit_record_identifies_actor`): exactly one `"action": "prize.concede"` record whose detail contains touristId, prizeId, routeId, pickupSpotId, stockQuantityBefore == N, stockQuantityAfter == N - 1 and the staff actor (expect red: detail lacks the new fields today)
- [X] T011 [US3] Write `test_concession_failures_emit_no_audit_record` in `tests/contract/test_gamification.py`: for unknown code, already-used and zero-stock attempts, assert no new `"prize.concede"` record appears (v1 decision — Clarifications) (regression guard: expected green from the start — do not force red)

### Implementation for User Story 3

- [X] T012 [US3] In `concede_prize` in `src/passanorte_back/modules/gamification/services/gamification.py`: capture the prize's current `stock_quantity` (re-read via `find_prize_by_id`) BEFORE `try_consume_stock`, then enrich `record_action` detail with `touristId`, `prizeId`, `stockQuantityBefore`, `stockQuantityAfter` (= before − 1, guaranteed by `rowcount == 1`; keep existing routeId/pickupSpotId, same action name — research R2); T010 green
- [X] T013 [US3] Extend the lifecycle concession in `tests/integration/test_gamification_lifecycle.py` to include the audit assertion via caplog in the happy path (single record with before/after) — keeps the integration journey aligned with SC-005

**Checkpoint**: audit completo e transacional (SC-005 ✅)

---

## Phase 6: Polish & Cross-Cutting

- [X] T014 [P] Update the module docstrings (`src/passanorte_back/modules/gamification/routes/gamification.py` service header comments) to reflect the RF21 contract wording (new stock in response, distinct conflict messages, audit before/after) — English only (Princípio VII)
- [X] T015 [P] Verify OpenAPI docs render the updated `RedemptionView` shape and the "Gamification" tag grouping is unchanged (`tests/contract/test_openapi_tags.py` still green)
- [X] T016 Run the full gate sweep: `ruff check`, `ruff format --check`, `pytest tests/` (all suites incl. `tests/smoke/test_boundaries.py` + `test_migrations.py`) — all green; no migration generated (research R5)

---

## Dependencies

```text
T001 (baseline verde)
 └── US1: T002 → T004 → T005  (T003 paralelo a T002, verifica junto de T003→T005)
      └── US2: T006 ─┐
             T007 ─┤→ T009  (T008 paralelo a T006/T007)
             T008 ─┘
      └── US3: T010 ─┐
             T011 ─┘→ T012 → T013
Polish: T014, T015 (paralelos) → T016 (todos os gates)
```

- US1 → US2: T006/T007 dependem da resposta já estável (T004/T005) — o handler é o mesmo arquivo que T005 edita
- US3 depende de US1/US2 concluídas no serviço/handler para evitar conflito de edição em `routes/gamification.py` (T009) e `services/gamification.py` (T012 edita arquivos diferentes — poderia anteceder, mas manter T010→T012 na ordem dos checkpoints simplifica commits por story)
- Stories são independentes em lógica de domínio; a exclusividade de edição de arquivo é o único encadeamento real

## Parallel Execution Examples

- **US1**: T002 (contrato) ∥ T003 (lifecycle) — arquivos distintos
- **US2**: T007 [P] ∥ T008 [P] — arquivos distintos (`tests/contract/` vs `tests/integration/`); T006/T007 são blocos distintos do MESMO arquivo de contrato (`tests/contract/test_gamification.py`), aplicar em sequência (sem `[P]` em ambos)
- **US3**: T010 ∥ T013 (contrato vs lifecycle) e T014 ∥ T015 no polish; T010/T011 no mesmo arquivo — aplicar em sequência

## Implementation Strategy

- **MVP = US1 completa (T001–T005)**: o resgate já responde com o novo estoque — valor visível ao funcionário, contrato FR-004 fechado
- Incremento 2 (US2): contrato de falha confiável — nada de dupla baixa em nenhum cenário
- Incremento 3 (US3): compliance RNF19 completo
- Cada checkpoint de story = commit único (memória do projeto: commits de feature vão direto na `master`, um por feature — mas commits parciais por story são aceitáveis dentro da feature)
- Sempre vermelho antes do verde: se um teste não falhar contra o código atual, reavaliar o teste antes de implementar