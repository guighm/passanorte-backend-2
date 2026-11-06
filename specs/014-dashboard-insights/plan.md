# Implementation Plan: Dashboard e Insights (014-dashboard-insights)

**Branch**: `014-dashboard-insights` | **Date**: 2026-11-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/014-dashboard-insights/spec.md`

## Summary

Backfill of the `dashboard` domain module (currently an empty scaffold): five
admin-only read endpoints under the `Dashboard` tag (RF03 gate — employee →
403). A new immutable `access_events` table (migration 0009) records one
event per tourist-authenticated request via a best-effort HTTP middleware
owned by the dashboard module (spec clarifications Q4, Q6); day bucketing is
precomputed in the configured city timezone (RNF06) so "unique tourists per
day" is a plain SQL `COUNT(DISTINCT tourist_id) GROUP BY day`. Heat map
(RF06), ranking (RF08), visitor-country (RF09) and visitor-interest (RF10)
distributions are set-based SQL aggregations issued by the dashboard's own
read layer over lightweight, write-free table projections of the existing
`visitations`, `tourist_spots`, `tourists` and `tourist_interests` tables
(no ORM models of other modules imported; constitution rule 3 preserved).
Regions (RF06) are data: each named region in `config/location.json` lists
the spot names it groups; the region marker weight is the sum of its spots'
visits and its coordinate the centroid of those spots.

## Technical Context

**Language/Version**: Python 3.13 (constitution — mandatory stack, RNF03)

**Primary Dependencies**: FastAPI, Pydantic v2 (`core.schemas.ApiModel`
camelCase contract, spec 005), SQLAlchemy 2.0 (Core constructs for read
projections; one new ORM model for `access_events`), Alembic (migrations
0001–0008 exist; this feature adds 0009). Starlette `BaseHTTPMiddleware`
for access recording. No new third-party dependency.

**Storage**: PostgreSQL in production / in-memory SQLite for tests — only
via `database_url` (RNF17; `StaticPool` per `tests/conftest.py`).

**Testing**: pytest suites `tests/unit`, `tests/contract`,
`tests/integration`, `tests/smoke` (constitution section III: test-first
NON-NEGOTIABLE; contract + integration tests per endpoint).

**Target Platform**: single-process FastAPI monolith (Docker, feature 004).

**Performance Goals**: SC-006 — each dashboard aggregate responds under 2 s
with 10k visitation events and 50k access events; all aggregation done by
the database (single `GROUP BY`/`COUNT`/`ORDER BY` + `LIMIT` queries), no
per-row loops in Python (FR-020).

**Constraints**: modular-monolith boundaries (constitution rules 3–5,
AST-checked by `tests/smoke/test_boundaries.py`); `ApiModel` camelCase HTTP
contract with `extra="forbid"` (spec 005); tag `Dashboard` applied only at
`core/routers.py` (spec 006); unified `ApiError` payloads; dashboard never
writes to other modules' tables (FR-021); access recording is best-effort
(FR-022) — essential services never depend on the metrics subsystem;
city/portability data only in `config/location.json` (RNF06).

**Scale/Scope**: one new table (`access_events`), 5 endpoints in the
`dashboard` module, read-projection repository for 4 existing tables,
optional `regions` block in `config/location.json`, migration 0009,
~8 test files (contract + integration + unit + RBAC).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Evidence |
|------|--------|----------|
| Module in `DOMAIN_MODULES` (`core/modules.py`) | ✅ PASS | `dashboard` is a canonical module; its router is already mounted via `modules.dashboard.routes` (empty today) |
| Single tag from `core/tags.py`, never in route files | ✅ PASS | tag `Dashboard` already assigned at `MODULE_ROUTERS` creation; endpoints inherit it |
| `ApiModel` camelCase for every HTTP-bound schema | ✅ PASS | all response schemas inherit `core.schemas.ApiModel`; contract tests assert camelCase |
| Unified `ApiError` failure payload | ✅ PASS | no custom error format; HTTPException detail strings feed the unified handler |
| RBAC: admin-only (RF03) | ✅ PASS | every route depends on `auth.services.require_admin` (employee → 403) |
| Boundaries: no import of other modules' private internals | ✅ PASS | read layer uses own lightweight `sa.table()` projections (no other-module models imported); access recording only imports `auth.services` public surface |
| Dashboard reads; never writes other domains | ✅ PASS | only write is to its own `access_events` table; aggregations are SELECT-only |
| Metrics derive from real recorded data | ✅ PASS | all values from `visitations`, `access_events`, `tourists`, `tourist_interests` — no invented numbers (constitution principle IV) |
| YAGNI / no premature optimization | ✅ PASS | no cache, no queue; one table, one migration, set-based SQL; best-effort recording chosen over async buffering (clarification Q6) |
| Portability (RNF06) | ✅ PASS | day bucketing + period anchors use `city_timezone`/location config; no city-specific values in code; no hardcoded Manaus |
| Test-first with contract + integration coverage | ✅ PASS | acceptance tests defined in [quickstart.md](quickstart.md) before implementation |

## Project Structure

### Documentation (this feature)

```text
specs/014-dashboard-insights/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── dashboard.md     # Phase 1 output (5 endpoints + schemas)
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
src/passanorte_back/
├── main.py                          # wires register_access_recording(app)
├── core/
│   ├── routers.py                   # (unchanged) mounts /api/v1/dashboard with tag Dashboard
│   └── tags.py                      # (unchanged) "Dashboard" tag already registered
├── scripts/                         # (unchanged)
└── modules/dashboard/
    ├── routes/metrics.py            # 5 admin-only endpoints (GET)
    ├── schemas/metrics.py           # ApiModel response schemas (camelCase)
    ├── services/
    │   ├── metrics.py               # orchestrates repos; windows/granularity logic
    │   └── access_recording.py      # middleware + record_access_event (best-effort)
    └── repositories/
        ├── access_events.py         # ORM model AccessEvent + insert + aggregates
        └── read_projections.py      # sa.table() read-only projections + aggregate queries
migrations/versions/20261106_0009_access_events.py   # access_events + indexes
config/location.json                 # optional "regions" block (data, RNF06)
tests/
├── contract/test_dashboard_metrics.py   # schemas, camelCase, 422 shapes, tag,
│                                        # RBAC 403, access-counts + ranking contracts
│                                        # (incl. the 5×3 admin-only matrix, T030)
├── integration/test_dashboard_metrics_flow.py  # seeded multi-tourist data per endpoint (acceptance)
├── integration/test_access_events_flow.py      # recording middleware flows (T014)
├── perf/test_dashboard_budget.py        # SC-006 budget: < 2 s × 10k visits/50k events
├── unit/test_dashboard_windows.py       # today/week/month anchors + granularity windows
└── unit/test_dashboard_regions.py       # region parsing/centroid from location data
```

**Structure Decision**: the canonical modular-monolith layout — all new code
inside `modules/dashboard/` (routes → services → repositories), one Alembic
migration, one entry in `config/location.json`. No changes to other modules:
the access-recording middleware lives in dashboard and only touches the
public `auth.services` token seam; aggregates live in dashboard's own read
layer.

## Complexity Tracking

> No Constitution Check violations to justify.
