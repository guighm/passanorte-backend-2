# Implementation Plan: Tourist Routes and Gamification

**Branch**: `009-tourist-routes-gamification` | **Date**: 2026-11-02 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/009-tourist-routes-gamification/spec.md`

## Summary

Módulo `gamification` — o coração do produto (RF18–RF20, RF29–RF30,
RF34–RF36). Administradores cadastram/editam/arquivam rotas turísticas
compostas por uma lista ordenada (somente display — visita em ordem livre) de
pontos existentes do módulo `tourist_spots` e um brinde independente
vinculado a no máximo uma rota (esclarecimento Q1), com estoque ajustável
nunca negativo (RF20). Turistas se inscrevem em rota ativa (duplicada → 409
— RF29) e acompanham progresso derivado das visitas registradas: pontos
visitados/pendentes + taxa de conclusão (RF30). A função pública de serviço
`register_spot_visit(tourist_id, tourist_spot_id)` (única porta entre
domínios; spec 010 conectará o check-in) grava a visita idempotentemente por
par turista-ponto e atualiza **TODAS** as inscrições em andamento que contêm o
ponto em uma chamada, devolvendo por rota afetada `routeId` +
`completionRate` + `completed` (esclarecimento Q5). Na última visita, a rota
completa uma única vez: uma insígnia (RF35) e um código de resgate único,
criptograficamente imprevisível (`secrets`, stdlib), sem expiração, de uso
único (RF36; segundo uso → 409). A concessão física do brinde é registrada
por funcionário ou administrador contra o código em um ponto informado,
consumindo exatamente uma unidade (bloqueada com 409 quando o estoque está
zero — código permanece válido) (RF20/RF36). Remoção de rota = arquivamento
com histórico intacto (decisão da spec). Todos os endpoints sob a tag
central "Gamification"; contrato camelCase estrito via `ApiModel`; falhas via
`ApiError` unificado; escalonamento de reserva feito por UPDATE condicional
atómico (guarda de estoque na própria SQL), testado via conclusões
sequenciais competindo pela última unidade + bloqueio de concessão.

## Technical Context

**Language/Version**: Python 3.13 (type hints em todos os módulos)

**Primary Dependencies**: FastAPI, Pydantic v2, SQLAlchemy 2.0,
Alembic (migrations), `secrets` (stdlib — geração dos códigos, sem
dependência nova)

**Storage**: PostgreSQL em produção / SQLite em memória nos testes
(`DATABASE_URL` única); novas tabelas do domínio gamification:
`tourist_routes`, `route_spots`, `prizes`, `route_enrollments`,
`spot_visits`, `completion_badges`, `redemption_codes` (todas FK apenas
referência a `tourists.id` e `tourist_spots.id`)

**Testing**: pytest (unit/contract/integration/smoke + `test_migrations.py`);
`tests/conftest.py` fornece banco isolado por teste, seeds de admin/employee,
tokens turista (auth pública) e captura de audit

**Target Platform**: Linux, containerizado (feature 004); um processo
FastAPI, um banco, um deploy

**Performance Goals**: leitura de progresso e inscrição em tempo hábil
mobile (RNF11); progresso derivado por join indexado (enrollment + spots +
visitas) — sem subsistemas pesados no caminho

**Constraints**: contrato JSON camelCase estrito (`ApiModel`, 422); `ApiError`
único (409 → `errorCode: "conflict"`); tag central "Gamification"; código em
inglês, conteúdo de usuário (nomes/descrições de rota e brinde) em
português; fronteira de domínio — visitation só via função pública;
estoque nunca negativo (guarda em SQL, não em aplicação)

**Scale/Scope**: volume de prefeitura (dezenas de rotas, milhares de
inscrições/visitas); listagens sem paginação nesta versão (YAGNI, precedente
da spec 008); uma migration nova

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Evidence |
|---|---|---|
| Monolito modular — módulo canônico (`DOMAIN_MODULES`) | PASS | `gamification` já listado em `core/modules.py`; skeleton existe (routes/services/repositories/schemas vazios); routes decorarão `MODULE_ROUTERS["gamification"]` |
| Comunicação entre módulos só via interface pública de serviço | PASS | `register_spot_visit` é a porta única para visitation (spec 010); existência de turistas/pontos validada pelas seams públicas de `tourists`/`tourist_spots` (R3) — jamais import de models/repos privados |
| Sem compartilhamento de tabelas entre domínios | PASS | 7 tabelas novas pertencem exclusivamente a gamification; FKs `tourist_id`/`tourist_spot_id`/`pickup_spot_id` são referências somente-leitura (precedente 008) |
| API-Contract-First: schemas `ApiModel` + tag central | PASS | todos os DTOs herdam `core.schemas.ApiModel`; tag "Gamification" já registrada em `core/tags.py` e aplicada em `core/routers.py`; nenhum route file escreve tag |
| Falhas via `ApiError` unificado | PASS | 409 já mapeado em `core.error_handlers` (`conflict`); 401/403/404/422 pelos handlers existentes |
| Segurança/LGPD: códigos imprevisíveis + RBAC | PASS | códigos via `secrets.token_urlsafe` (128-bit, stdlib, R5); rotas admin via `require_admin`; turista só lê o próprio estado via `require_tourist`; concessão por nova gate `require_staff` no módulo auth (R6); nenhum dado sensível LGPD novo |
| RNF19 audit | PASS | `core.audit.record_action` — uma linha por escrita administrativa (create/update/archive/stock/concessão), precedente 007/008 |
| Test-First (NON-NEGOTIABLE) | PASS | contrato (schemas/status codes) + integração (jornada completa de aceitação SC-007) + concorrência de estoque; cobertura crítica |
| YAGNI | PASS | sem paginação, sem cache, sem filas, sem dependência nova (stdlib `secrets`); progresso derivado por query, não desnormalizado |
| Portabilidade (RNF06) | PASS | nenhum dado de conteúdo em lógica de código; tudo em schema/migration |

## Project Structure

### Documentation (this feature)

```text
specs/009-tourist-routes-gamification/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/
│   └── gamification.md  # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/passanorte_back/
├── core/                          # (unchanged — gamification usa a infra compartilhada)
│   ├── modules.py                 # "gamification" já canônico
│   ├── tags.py                    # tag "Gamification" já registrada
│   ├── routers.py                 # MODULE_ROUTERS["gamification"] já montado
│   ├── schemas.py                 # ApiModel / ApiError
│   ├── error_handlers.py          # 401/403/404/409/422 → payload unificado
│   └── audit.py                   # record_action
└── modules/gamification/
    ├── repositories/
    │   └── gamification.py        # NEW: models + data access das 7 tabelas
    ├── schemas/
    │   └── gamification.py        # NEW: request/response DTOs (ApiModel)
    ├── services/
    │   ├── gamification.py        # NEW: fluxos de rota/inscrição/progresso/recompensa
    │   └── __init__.py            # EXTEND: re-export do seam público (register_spot_visit)
    └── routes/
        └── gamification.py        # NEW: endpoints admin/turista/staff no router canônico

src/passanorte_back/modules/auth/
└── services/security.py           # EXTEND: require_staff (admin OU employee — R6)

migrations/versions/
└── 20261102_0006_gamification.py  # NEW: 7 tabelas + índices/unicidades

tests/
├── contract/
│   └── test_gamification.py       # NEW: contrato dos endpoints (201/200/204/403/404/409/422)
├── integration/
│   ├── test_gamification_visit.py      # NEW: propagação RF34 + idempotência da conclusão
│   └── test_gamification_lifecycle.py  # NEW: jornada completa (SC-007) + concorrência/estoque
└── unit/
    └── test_gamification_codes.py # NEW: imprevisibilidade/unicidade do código de resgate
```

**Structure Decision**: módulo canônico `gamification` já existe como skeleton
(`core/modules.py`) com o router montado em `MODULE_ROUTERS`. O padrão de
referência é o módulo `events` (008): routes → services → repositories →
schemas, tag exclusivamente em `core/routers.py`, exceções de domínio →
`HTTPException` na taxonomia unificada, uma escrita administrativa = uma
linha de audit. O domínio gamification possui TODAS as suas tabelas
(rotas, brinde, inscrições, progresso derivado de visitas, insígnias,
códigos); turistas e pontos são referenciados só por FK e validados
exclusivamente pelas seams públicas. `register_spot_visit` vive na camada de
services com re-export em `services/__init__.py` (precedente
`events.services`), pronta para o consumo da spec 010 sem mudança de
semântica.

## Complexity Tracking

> Nenhuma violação de constituição a justificar — a feature segue o padrão
> consolidado (tourist_spots/events) sem dependências novas, sem novos
> princípios e sem estrutura extra. A única extensão de infraestrutura é a
> gate `require_staff` no módulo auth (proprietário do RBAC — R6), que é
> extensão do domínio existente, não complexidade nova.