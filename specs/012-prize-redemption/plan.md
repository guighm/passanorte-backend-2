# Implementation Plan: Prize Redemption (Employee Scan)

**Branch**: `012-prize-redemption` | **Date**: 2026-11-03 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/012-prize-redemption/spec.md`

## Summary

Harden the existing staff-gated prize redemption of the gamification module
(endpoint `POST /api/v1/gamification/redemptions`, service `concede_prize`,
spec 009 US4) to RF21's exact contract (feature 012): the success response
exposes the prize's new stock quantity after the single-unit deduction
(FR-004), the unified error contract distinguishes "no stock available for
this route's prize" from "code already used" on the two conflict paths
(FR-005), and the audit record (RNF19) identifies tourist, prize, pickup
spot and stock quantity before/after inside the granting transaction
(FR-007). No schema change: all work is service/contract/test hardening over
existing models, plus the acceptance contract tests (success reducing stock,
unknown code, duplicate code idempotency, insufficient stock blocking, RBAC
tourist-refused/no-token-401, audit verification).

## Technical Context

**Language/Version**: Python 3.13 (type hints everywhere, Princípio VII)

**Primary Dependencies**: FastAPI, Pydantic v2 (ApiModel camelCase fronteira),
SQLAlchemy 2.0, ruff (lint+format)

**Storage**: PostgreSQL em produção / SQLite em memória nos testes —
**nenhuma mudança de schema** nesta feature (sem migration Alembic)

**Testing**: pytest — suíte `tests/contract/` + `tests/integration/`
(+ `tests/unit/`, `tests/smoke/`), TestClient; audit capturável via
`caplog` no logger `passanorte.audit`

**Target Platform**: Linux container (Dockerfile + compose.yaml, feature 004)

**Project Type**: monolito modular FastAPI (único processo, um banco)

**Performance Goals**: resgate responde em tempo hábil para uso mobile
(RNF11) — fluxo de leitura+2 updates atômicos, sem subsistemas pesados

**Constraints**: sem fila/mensageria; boundary check por AST
(`tests/smoke/test_boundaries.py`) quebra o build em import ilícito;
nenhuma string de tag fora de `core/tags.py`; nenhum schema HTTP sem
`ApiModel`

**Scale/Scope**: 1 endpoint ajustado, 1 serviço ajustado, 1 schema ajustado,
~6 novos/alterados testes de contrato + extensão do teste de lifecycle

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Status | Evidência |
|---|---|---|
| I. API-Contract-First (camelCase, ApiError, tags centralizadas) | PASS | `RedemptionView`/`RedemptionPrizeView` já herdam `ApiModel`; campo novo `stock_quantity` → `stockQuantity` via ApiModel; falhas continuam no payload único `ApiError` (errorCode `conflict`/`resource_not_found`…, distinção de causa na `message`); tag "Gamification" já aplicada no router central |
| II. Segurança e LGPD | PASS | RBAC `require_staff` intocado (RF03): funcionário/admin; turista → 403, sem token → 401; audit RNF19 enriquecido; nenhum dado sensível novo manipulado |
| III. Test-First | PASS | Testes escritos primeiro: contrato de sucesso com novo estoque, idempotência (duplicado + concorrência), estoque insuficiente, RBAC, audit antes/depois — todos falham contra o código atual |
| IV. Geoespacial | N/A | Nenhuma validação de presença nesta feature (pickup spot já validado por serviço público de tourist_spots) |
| V. YAGNI | PASS | Zero tabelas novas, zero endpoints novos, zero dependências; só endurecimento de contrato |
| VI. Portabilidade | N/A | Nenhuma mudança de dados configuráveis |
| VII. Manutenibilidade | PASS | Código em inglês, camadas routes→services→repositories preservadas, ruff no pipeline |
| Fronteira de módulos (regra 3/5 do monolito) | PASS | Único cross-module permanece leitura via serviço público `tourist_spots.get_active_spot`; nenhuma tabela de outro módulo tocada; boundary AST gate cobre |
| Migrations revisadas quando houver mudança de schema | N/A | Sem mudança de schema — nenhuma migration nova |

**Pós-Phase 1 re-check**: PASS — sem violação a justificar (Complexity
Tracking vazio).

## Project Structure

### Documentation (this feature)

```text
specs/012-prize-redemption/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── gamification-redemptions.md
└── tasks.md             # Phase 2 output (/speckit-tasks) — NOT created here
```

### Source Code (repository root)

```text
src/passanorte_back/modules/gamification/
├── routes/gamification.py       # POST /redemptions: payload com novo estoque;
│                                # mensagens de conflito distintas (usado vs sem estoque)
├── services/gamification.py     # concede_prize: captura estoque antes, detail de
│                                # audit com touristId/prizeId/stock antes/depois
├── schemas/gamification.py      # RedemptionPrizeView + stock_quantity
└── repositories/gamification.py # SEM mudanças (try_consume_stock/claim já atômicos)

tests/contract/test_gamification.py   # + testes: estoque na resposta, mensagens de
                                      # conflito distintas, idempotência em repetição,
                                      # audit antes/depois; ajuste de REDEMPTION_KEYS
tests/integration/test_gamification_lifecycle.py  # + estoque no sucesso do fluxo completo
```

**Structure Decision**: monolito modular existente (`src/passanorte_back/`
com `core/` + `modules/`); toda a mudança é intra-módulo em
`modules/gamification/` com testes nas suítes de contrato e integração —
sem novo módulo, sem mudança em `core/` (a infra de audit
`core/audit.py` já atende FR-007; nada muda nela).

## Complexity Tracking

> (vazio — nenhuma violação de constituição a justificar)