# Implementation Plan: Notificações por Interesse (015-interest-notifications)

**Branch**: `015-interest-notifications` | **Date**: 2026-11-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/015-interest-notifications/spec.md`

## Summary

Backfill of the `notifications` domain module (empty scaffold — like 011/014):
tourists subscribe to categories via dedicated tourist-exclusive endpoints
(Q1: channel of their own, independent of the profile interests), and the
three emitters (events/008, tourist_spots/007, gamification/009) call the
new public seam `notifications.services.create_interest_notification` when
an item is CREATED — matching subscribed tourists by category (events
inherit their spot's categories; routes inherit the union of their spots'
categories — Q3), one notification per tourist×item (DB-level dedupe).
Delivery is polling-only (RNF15): `GET` unread/history list (fixed most-
recent limit, Q4), dedicated unread-count endpoint (Q5), mark-as-read
(idempotent, one or all). Notification text (title/description) is composed
centrally by the notifications module from emitter data (Q2), i18n-ready
(RNF16). Emission is best-effort via a SAVEPOINT inside the emitter's
transaction (FR-011). Migration 0010 adds both tables + indexes.

## Technical Context

**Language/Version**: Python 3.13 (constitution — mandatory stack, RNF03)

**Primary Dependencies**: FastAPI, Pydantic v2 (`core.schemas.ApiModel`
camelCase, spec 005), SQLAlchemy 2.0 (incl. `begin_nested` savepoints and
dialect `on_conflict_do_nothing` for the tourist×item dedupe), Alembic
(migrations 0001–0009 exist; this feature adds 0010). No new third-party
dependency; no push (RNF15).

**Storage**: PostgreSQL in production / in-memory SQLite for tests — only
via `database_url` (RNF17; `StaticPool` per `tests/conftest.py`).

**Testing**: pytest suites `tests/unit`, `tests/contract`,
`tests/integration`, `tests/smoke`, `tests/perf` (constitution III;
test-first NON-NEGOTIABLE — red before green per task).

**Target Platform**: single-process FastAPI monolith (Docker, feature 004).

**Performance Goals**: SC-005 — notification queries below 2 s with
1,000 tourists and 100 items; match generation is one set-based SQL query
(`SELECT DISTINCT tourist_id ... WHERE category_key IN (...)`) riding the
composite index; list/count queries ride `ix_notifications_tourist_read`.

**Constraints**: modular-monolith boundaries (rules 3–5; AST gate
`tests/smoke/test_boundaries.py`); emitters call ONLY
`notifications.services` public seam — the seam never imports emitters;
`ApiModel` camelCase strict; tag `Notifications` assigned only at
`core/tags.py`/`core/routers.py` (spec 006); unified `ApiError` payload;
no push, no retention/expurgo (YAGNI).

**Scale/Scope**: two new tables (`notification_subscriptions`,
`notifications`), 7 tourist endpoints in `notifications`, ONE new public
read seam in `tourist_spots.services` (`categories_for_spots` — needed by
gamification for Q3), emission hooks in 3 emitter services, migration 0010,
~9 test files.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Evidence |
|------|--------|----------|
| Module in `DOMAIN_MODULES` (`core/modules.py`) | ✅ PASS | `notifications` canonical; router already mounted with tag `Notifications` (`core/tags.py`, scaffold empty) |
| Tag única central (spec 006) | ✅ PASS | tag comes from `MODULE_ROUTERS`; route files never write tag strings |
| `ApiModel` camelCase (`extra="forbid"`) | ✅ PASS | all HTTP schemas inherit `core.schemas.ApiModel` |
| `ApiError` unificado | ✅ PASS | failures via `HTTPException` → unified handlers (spec 005) |
| RBAC (RF03/FR-001) | ✅ PASS | tourist endpoints use `require_tourist`; no staff endpoints in this module |
| Fronteiras (rule 3) | ✅ PASS | emitters → `notifications.services` public seam; gamification → new public `tourist_spots.services` read seam; zero other-module internals imported |
| Regra 5 (escrita entre domínios via serviço público) | ✅ PASS | emitters never write notifications tables directly — generation is inside the notifications seam (FR-008/FR-016) |
| Best-effort sem bloquear emissor (FR-011) | ✅ PASS | SAVEPOINT (`begin_nested`) around generation; failure → savepoint rollback + structured log; item creation intact (research R2) |
| Dados reais (Princípio IV) | ✅ PASS | interested list derived from real subscriptions × real item categories; nothing synthetic (FR-010/FR-017) |
| YAGNI / RNF15 | ✅ PASS | no push, no queue, no retention job, no pagination (Q4 fixed limit), no cache |
| Portabilidade (RNF06) | ✅ PASS | subscription catalog = `resolved_interest_categories()` (city config), zero city values in code |
| i18n-ready (RNF16/FR-015) | ✅ PASS | templates isolated as data structure (per-type title/description template), single-language delivery this phase |
| Test-first + contract/integration coverage | ✅ PASS | acceptance tests defined in [quickstart.md](quickstart.md) before implementation |

## Project Structure

### Documentation (this feature)

```text
specs/015-interest-notifications/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── notifications.md # Phase 1 output (7 endpoints + seam signatures)
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
src/passanorte_back/
├── core/
│   ├── routers.py/tags.py               # (unchanged) /api/v1/notifications + tag Notifications
└── modules/
    ├── notifications/
    │   ├── routes/subscriptions.py      # GET/PUT subscriptions + DELETE one (tourist)
    │   ├── routes/notifications.py      # GET list, GET unread-count, POST read/read-all (tourist)
    │   ├── schemas/notifications.py     # ApiModel DTOs (camelCase)
    │   ├── services/subscriptions.py    # replace/select/cancel + catalog validation
    │   ├── services/delivery.py         # list/count/mark-as-read (idempotent)
    │   └── services/emission.py         # PUBLIC seam: create_interest_notification (savepoint + templates)
    ├── tourist_spots/services/tourist_spots.py  # + categories_for_spots public read seam (Q3)
    ├── events/services/events.py                # + emission hook in create_event (item = event)
    ├── gamification/services/gamification.py    # + emission hook in create_route (categories = union of spots')
    └── (tourist_spots/services/tourist_spots.py create_spot hook lives here too)
migrations/versions/20261106_0010_notifications.py  # 2 tables + indexes
tests/
├── unit/test_notification_templates.py       # Q2 text composition (PT labels)
├── contract/test_notifications.py            # shapes/codes/422/tag/RBAC per endpoint
├── integration/test_notifications_flow.py    # acceptance: match / no-match, read marking, unsubscribe
├── integration/test_notification_emission.py # emitter seams: event/spot/route → match + best-effort
├── perf/test_notifications_budget.py         # SC-005: < 2 s, 1,000 tourists × 100 items
└── test_migrations.py (extended)             # 0010 upgrade/downgrade
```

**Structure Decision**: canonical modular-monolith layout — everything new
inside `modules/notifications/` plus minimal public-seam hooks in the three
emitter services and one public read seam in `tourist_spots.services`.
No new shared infra; migration owns the two tables.

## Complexity Tracking

> No Constitution Check violations to justify.
