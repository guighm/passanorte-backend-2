# Implementation Plan: Geo-Visitation (011-geo-visitation)

**Branch**: `011-geo-visitation` | **Date**: 2026-11-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/011-geo-visitation/spec.md`

## Summary

Backfill of the `visitation` domain module: the tourist marks a visitation at
a registered tourist spot by sending GPS coordinates; the backend validates
presence with the Haversine distance against a tolerance radius (per-spot
override or global 100 m default from settings), persists an immutable
visitation record (timestamp + validated coordinates), and — on the tourist's
**first** visitation for that spot — calls the existing public seam
`gamification.services.register_spot_visit` (spec 009) so in-progress route
enrollments update exactly once. Repeated visits append to the immutable
history without re-triggering progress (spec clarifications Q4–Q5, simple
idempotency). Rejected out-of-radius attempts return 409 and emit a
structured log; nothing is persisted for them (Q6/SC-007).

## Technical Context

**Language/Version**: Python 3.13 (constitution — mandatory stack, RNF03)

**Primary Dependencies**: FastAPI, Pydantic v2 (`core.schemas.ApiModel`
camelCase contract, spec 005), SQLAlchemy 2.0, Alembic (migrations
0001–0006 exist; this feature adds 0007). Haversine is implemented inline
with the standard `math` module — **no new geospatial dependency** (YAGNI;
see research R1).

**Storage**: PostgreSQL in production / in-memory SQLite for tests — only
via `database_url` (FR-014; test `StaticPool` per `tests/conftest.py`).

**Testing**: pytest suites `tests/unit`, `tests/contract`,
`tests/integration`, `tests/smoke` (quality gates of the constitution
section III).

**Target Platform**: single-process FastAPI monolith (Docker, feature 004).

**Performance Goals**: mark-visitation resolves in a single DB
transaction (insert + one seam call) — comfortably within the < 3 s
end-to-end target of SC-001; no heavy subsystem in the path (RNF11).

**Constraints**: modular-monolith boundaries (constitution rules 3–5,
AST-checked by `tests/smoke/test_boundaries.py`), `ApiModel` camelCase HTTP
contract, tag `Visitation` applied only at `core/routers.py` (spec 006),
coordinates always decimal WGS-84 validated at schema (FR-013), GPS values
stored in cleartext (Q7).

**Scale/Scope**: one new domain table + one nullable column on
`tourist_spots`; 3 endpoints in the `visitation` module; ~6 test files.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Evidence |
|------|--------|----------|
| Module in `DOMAIN_MODULES` (`core/modules.py`) | ✅ PASS | `visitation` is a canonical module; routers already mount `modules.visitation.routes` |
| Single tag from `core/tags.py` (`"Visitation"`), never in route files | ✅ PASS | tag assigned at `MODULE_ROUTERS[...]` creation; spec 011 FR-011 reuses it |
| Cross-module writes ONLY via public service functions | ✅ PASS | RF34 goes through `gamification.services.register_spot_visit` (public, `__all__`) — no gamification tables touched by visitation |
| Cross-module reads via public interfaces | ✅ PASS | spot lookup via `tourist_spots.services.get_active_spot`; tourist existence via `tourists.services.get_tourist_account` |
| No new persistence outside module owner | ✅ PASS | new `visitations` table owned by visitation; `tourist_spots.tolerance_radius_m` column on a table tourist_spots already owns (its admin schemas gain the field) |
| Test-first; contract + integration suites | ✅ PASS | plan mandates unit (Haversine exact cases), contract (request/response/status/error payload), integration (mark → status → progress; outside radius; idempotency) |
| `ApiModel` camelCase + `ApiError` on every failure path | ✅ PASS | all visitation schemas inherit `ApiModel` (spec 005 FR); no bespoke error payload |
| GPS coordinates cleartext (Q7), not in sensitive-field census | ✅ PASS | coordinates stay operational data; no `core.crypto` primitives involved |
| English code, PT-BR data/user-facing text only | ✅ PASS | identifiers/log messages in English; no user-facing text added |
| Alembic migration for schema change | ✅ PASS | `0007_visitation` (new table + spot radius column), reviewed by `tests/test_migrations.py` path |
| YAGNI: no lock, no throttle, no geo dependency | ✅ PASS | clarifications Q4/Q5; Haversine inline (R1) |

No violations — **Complexity Tracking stays empty**.

## Project Structure

### Documentation (this feature)

```text
specs/011-geo-visitation/
├── plan.md              # This file
├── research.md          # Phase 0 output — decisions R1..R9
├── data-model.md        # Phase 1 output — Visitation entity + spot radius column
├── quickstart.md        # Phase 1 output — runnable validation guide
├── contracts/
│   └── visitation.md    # HTTP contract: 3 endpoints + tourist_spots delta
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
src/passanorte_back/modules/visitation/     # module exists as skeleton; filled by this feature
├── routes/
│   └── visitations.py                      # POST /visitation/spots/{spotId}/visits; GET history/visited-spots
├── services/
│   ├── geolocation.py                      # haversine_distance_m + radius resolution (unit-test target)
│   └── visitations.py                      # mark_visitation, list_visitations, list_visited_spots
├── repositories/
│   └── visitations.py                      # Visitation model + immutable insert/queries
└── schemas/
    └── visitations.py                      # ApiModel request/response views

src/passanorte_back/modules/tourist_spots/  # minimal delta (radius field in schemas only)
├── schemas/tourist_spots.py                # optional toleranceRadiusM in create/update/view
└── repositories/tourist_spots.py           # TouristSpot.tolerance_radius_m column

src/passanorte_back/core/config.py          # gps_tolerance_radius_m already exists (no change)

tests/
├── unit/test_haversine.py                  # exact cases: inside, outside, border, antipodes, zero
├── contract/test_visitation.py             # request/response/status codes/ApiError payload
├── contract/test_tourist_spots_radius.py   # radius field contract delta
├── integration/test_visitation_flow.py     # mark → status → route progress; outside 409; idempotency
└── migrations/versions check via tests/test_migrations.py (existing path)

migrations/versions/20261103_0007_visitation.py   # visitations table + tourist_spots.tolerance_radius_m
```

**Structure Decision**: the canonical layout (constitution rule 4) — the
empty `visitation` skeleton grows its `routes/services/repositories/schemas`
layers exactly like the other six domain modules; zero new top-level
directories.

## Complexity Tracking

> Empty — no constitution violations to justify (gate passed before and
> after design).