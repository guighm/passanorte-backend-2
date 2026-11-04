# Implementation Plan: Passaporte Discovery (Ranked Spots & Navigation Links)

**Branch**: `013-descoberta-passaporte` | **Date**: 2026-11-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/013-descoberta-passaporte/spec.md`

## Summary

Implement the Passaporte discovery surface in the existing `tourist_spots`
domain (tag `Tourist Spots`): a tourist-authenticated, paginated feed of
tourist spots ranked by a documented, deterministic relevance score
(proximity-dominant → interest match → minor upcoming-event boost) plus
ready-to-open navigation deep links (Google Maps/OSM, Uber, 99) per spot —
both in the feed and via a dedicated origin-aware links endpoint and the
existing public detail response. No new tables: the feature computes over
existing `tourist_spots`, `tourist_interests` and `events` rows through
each owner module's public service seams. The only schema change is one
partial index on `tourist_spots(status)` for the active-spots filter.

## Technical Context

**Language/Version**: Python 3.13 (type hints everywhere — constitution VII)

**Primary Dependencies**: FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic

**Storage**: PostgreSQL (production) / SQLite in-memory (tests) — no new
tables; one partial index migration

**Testing**: pytest — `tests/contract/` (feed ordering + links + status
codes), `tests/unit/` (score/deeplink generators), `tests/integration/`
(interest auth + pagination walk), `tests/perf/` (1,000-spot dataset,
< 1 s/page budget — SC-006); StaticPool harness per [[test-harness-staticpool]]
memory (race proofs via repo guards, never threads)

**Target Platform**: Linux container (Dockerfile + compose.yaml, feature
004); consumers: Passaporte app (Kotlin) and admin panel share the same API

**Project Type**: web service (modular monolith)

**Performance Goals**: any single page of the ranked feed responds within
**1 s** on a ~1,000-spot reference dataset (SC-006); ranking work
per request bounded O(n) sort (n = active spots) with in-Python scoring

**Constraints**: RNF12 (mobile-friendly response), RNF15 (free/open-source
only — deep links are public URL forms, no paid API), RNF18 (Google Maps
or OSM by configuration), cache disabled by default (constitution V)

**Scale/Scope**: ~1,000 spots, events per city in hundreds; two new
endpoints + additive fields on the existing public detail response

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Evidence |
|------|--------|----------|
| I. API-Contract-First — ApiModel camelCase, extra="forbid", unified ApiError, tags from `core/tags.py` only | ✅ PASS | New wire schemas in `modules/tourist_spots/schemas/` inherit `core.schemas.ApiModel`; endpoints mounted on the existing `Tourist Spots` router (no new tag); failures use `ApiError` via `core.error_handlers` |
| II. Segurança e LGPD — JWT tourist auth, no new sensitive storage | ✅ PASS | Both endpoints under `require_tourist` (same seam as visitation, spec 011); tourist position is transient, never persisted |
| III. Test-First — contract + integration per feature | ✅ PASS | Acceptance tests enumerated in quickstart.md §4 before implementation; red → green order enforced by /speckit-implement |
| IV. Geospatial correctness — Haversine, WGS-84 validated, no invented metrics | ✅ PASS | Distance reuses the Haversine helper pattern from visitation (RNF14); coordinates validated as decimal WGS-84 before scoring (FR-014) |
| V. YAGNI — simplest passing design, no premature caches | ✅ PASS | No cache in v1 (configurable off-switch documented for later); single index migration; score computed in-process over ≤ 1,000 rows |
| VI. Portabilidade — city/policy data in config | ✅ PASS | Discovery weights, max distance, event window and map provider live in `Settings` (env, `.env`) — zero restructure to re-tune |
| VII. Maintainability — English code, layered modules, ruff | ✅ PASS | Ranking lives in `modules/tourist_spots/` (services/routes/schemas); cross-module reads go through public service functions only |
| Cross-domain integrity — writes via owner service; no internals imports | ✅ PASS | This feature is read-only across domains: tourist interests via `tourists` public seam, future events via a new explicit `events` public function; no other module's models/repositories touched |
| Quality gates — no snake_case JSON, no tag strings outside `core/tags.py`, no `ApiError` variants, migrations reviewed | ✅ PASS | Contract tests assert camelCase wire keys and error payload; migration 0008 reviewed in the change set |

**Post-Phase-1 re-check**: PASS (all artifacts conform; no violation to
justify in Complexity Tracking).

## Project Structure

### Documentation (this feature)

```text
specs/013-descoberta-passaporte/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── tourist-spots-discovery.md   # Feed + navigation-links contract
├── checklists/
│   └── requirements.md  # Spec quality checklist (16/16)
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT here)
```

### Source Code (repository root)

```text
src/passanorte_back/
├── core/
│   ├── config.py                     # + discovery settings (weights distance window provider)
│   ├── modules.py / routers.py / tags.py   # unchanged (Tourist Spots router reused)
│   └── schemas.py / error_handlers.py       # unchanged
├── modules/
│   ├── tourist_spots/
│   │   ├── routes/tourist_spots.py   # + GET /discover, GET /{id}/navigation-links
│   │   ├── services/
│   │   │   ├── tourist_spots.py      # + discovery service (score, sort, tie-break)
│   │   │   └── navigation_links.py   # + deep-link builders (maps/osm uber 99)
│   │   ├── schemas/tourist_spots.py  # + discovery wire models (ApiModel camelCase)
│   │   └── repositories/tourist_spots.py  # + active-spots feed query (indexed)
│   └── events/
│       └── services/events.py        # + list_upcoming_events() public seam (dates)
├── tourists/                          # unchanged: interests read via existing seam
└── visits/ etc.                       # unchanged

migrations/versions/
└── 20261103_0008_spot_discovery_index.py   # partial index ix_tourist_spot_status_active

tests/
├── contract/test_discovery_feed.py   # ordering cases + errors + camelCase
├── contract/test_navigation_links.py # links endpoint + detail additive fields
├── unit/test_relevance_score.py      # formula + tie-break + neutral factors
├── unit/test_navigation_link_builders.py  # maps/osm/uber/99 exact targets
├── integration/test_discovery_flow.py     # auth + interests + pagination walk
└── perf/test_feed_budget.py          # 1,000 spots < 1 s per page (SC-006)
```

**Structure Decision**: extend the existing modular-monolith layout —
discovery is a tourist-facing slice of `tourist_spots` (spec 007 module),
with two explicit read-seams added to `events` (public service function) and
`tourists` (reuse the existing interests service). No new module, no new
router, no new tag (clarification FR-013).