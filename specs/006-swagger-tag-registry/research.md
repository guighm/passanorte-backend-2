# Research: Centralized Swagger Tag Registry

Feature: 006-swagger-tag-registry | Date: 2026-11-02

## R1 — Where does the tag registry live and what shape does it take?

**Decision**: New `src/passanorte_back/core/tags.py`. Two public values:
`OPENAPI_TAGS_METADATA` (ordered list of `{name, description}` dicts, passed
directly to `FastAPI(openapi_tags=...)`), and `module_tag(module: str) -> str`
resolving a canonical module name to its tag name; plus
`INFRASTRUCTURE_TAG: Final = "Health"` used for core-owned non-domain routes
(`/health`).

**Rationale**: `core/` owns shared infrastructure (constitution preamble
rule 4). A dedicated unit avoids import cycles (`core.routers` and
`main.py` both consume it; neither depends on the other for tags) and keeps
`routers.py` focused on mounting. A hand-written ordered structure (spec
clarification Q3) preserves display order and per-tag descriptions without
mechanical derivation.

**Alternatives considered**:
- Tags inside `core/routers.py` — rejected: couples mounting and metadata;
  `main.py` would import from `core.routers` only for tag constants.
- Deriving tags from `DOMAIN_MODULES` automatically — rejected by
  clarification Q3 (descriptions are hand-written content; a test verifies
  1:1 alignment instead).

## R2 — How are tags attached so that NO module route file changes?

**Decision**: Attach once at the canonical router creation point:
`MODULE_ROUTERS: dict[str, APIRouter] = {name: APIRouter(prefix=..., tags=[module_tag(name)])}`. FastAPI merges router-level tags into every
operation registered on that router. `/health` gets `tags=[INFRASTRUCTURE_TAG]`
on its `@app.get` decorator in `main.py`, and the FastAPI constructor gets
`openapi_tags=OPENAPI_TAGS_METADATA`.

**Rationale**: All existing endpoints (auth, employees, tourists) are
already decorated on `MODULE_ROUTERS[name]` (`router = MODULE_ROUTERS["tourists"]`
pattern); router-level tagging retroactively tags every operation without
touching `modules/*/routes/*.py` — stronger than the spec's minimum (FR-003
forbids inline strings in module code; here module code contains no tag
reference at all). Exactly one declaration point per concern.

**Alternatives considered**:
- Per-operation `tags=[...]` on each decorator — rejected: duplicates the
  string in many places, contradicts FR-003's "reference the registry, never
  inline strings", and adds churn in every route file.
- Module-level `router = MODULE_ROUTERS["x"]` files each adding tags —
  rejected: `MODULE_ROUTERS` is the canonical shared router (spec 001
  decision); re-wrapping would fork it.

## R3 — What does the sweep test assert, and where does it live?

**Decision**: `tests/contract/test_openapi_tags.py`, using the generated
OpenAPI document from the real app (`list(main_module.app.openapi()["paths"].items())`
walk — same import pattern as `tests/smoke/test_health.py`). Assertions:

1. **Catalog declared**: `app.openapi_schema` (or the raw doc) contains all
   11 catalog tags with descriptions, in canonical domain order + `Health`
   last.
2. **Every operation tagged**: for every path × method operation, `tags`
   exists, is non-empty, and contains exactly one entry (SC-001/SC-002;
   FR-004/FR-005).
3. **Only registered tags**: every operation tag ∈ catalog names (FR-004).
4. **1:1 module alignment**: catalog domain tags ↔ `DOMAIN_MODULES` bijectively
   (FR-002; e.g. `tourist_spots` → `Tourist Spots`), infrastructure tag
   excluded from the bijection but present in the catalog.
5. **Failure reporting**: assertions name path + method (test idempotence:
   a deliberately untagged temporary route fixture is NOT injected in CI;
   the sweep is vacuously-safe — see quickstart for the negative-check
   discipline: temporarily remove a tag locally and observe the red run).

**Rationale**: Contract tests already host cross-cutting sweeps
(`tests/contract/test_camelcase_contract.py` precedent — spec 005). The spec
clarification Q1 pins enforcement to tests only, so no app middleware/startup
hook is built.

**Alternatives considered**:
- `tests/unit/` — rejected: the sweep runs against the mounted app, contract-level concern.
- Injecting a synthetic untagged route in a fixture to prove the sweep sees it —
  rejected for CI (mutating the app under test is fragile); SC-004 "guard is
  real" is demonstrated via the quickstart negative check and by construction
  (the sweep iterates all operations generically).

## R4 — Tag name mapping `DOMAIN_MODULES` → display tags

**Decision** (canonical English, human-readable with spaces where the module
name has underscores — matching the spec's given names):

| Module (`DOMAIN_MODULES`) | Tag name |
|---|---|
| `auth` | `Auth` |
| `employees` | `Employees` |
| `tourists` | `Tourists` |
| `tourist_spots` | `Tourist Spots` |
| `events` | `Events` |
| `gamification` | `Gamification` |
| `visitation` | `Visitation` |
| `dashboard` | `Dashboard` |
| `notifications` | `Notifications` |
| `chatbot` | `Chatbot` |
| — (core-owned) | `Health` (infrastructure, last) |

**Rationale**: Names are given verbatim by the input spec; order is the
canonical module order (constitution preamble rule 2) with infrastructure
last (clarification Q2).

## R5 — Does the custom OpenAPI hook (`custom_openapi`) interfere?

**Decision** (corrected during implementation — the red sweep test caught
it): operation tags ride on `app.routes` and are propagated untouched by the
hook, but the **top-level catalog** is not: `custom_openapi` calls
`get_openapi(...)` directly, which does not read `app.openapi_tags`. The hook
was updated to re-pass `tags=app.openapi_tags`. The unified `ApiError` merge
(spec 005) remains orthogonal.

**Rationale**: FastAPI's built-in `app.openapi()` injects the metadata;
a custom hook must pass everything explicitly to `get_openapi`.

## R6 — camelCase contract interplay (spec 005)

**Decision**: Tag names are documentation metadata, not JSON payload keys;
the camelCase sweep (`tests/contract/test_camelcase_contract.py`) inspects
response bodies and is unaffected. Tag display names keep the spec-given
capitalized English form (`Auth`…), which FR-009 explicitly permits.

**Rationale**: No payload/schema key is added anywhere; FR-008 (frozen
contract) holds by construction.