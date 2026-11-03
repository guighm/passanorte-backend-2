# Contract: OpenAPI Tags Catalog (feature 006)

The externally-observed contract of this feature is the **tags catalog of
the generated OpenAPI document** of `passanorte_back.main:app`, consumed by
the Swagger UI, the React panel and the Kotlin Passaporte codegen. Routes,
methods, request/response payloads and status codes are unchanged (spec 006
FR-008); only the `tags` arrays and the top-level catalog are added.

## Catalog (declaration + display order)

`FastAPI(openapi_tags=...)` receives, in this exact order:

| # | Name | Description (contract wording, English) | Kind |
|---|---|---|---|
| 1 | `Auth` | Authentication and session management: login, token refresh, logout and the current user identity (auth module). | domain |
| 2 | `Employees` | Employee management and benefit authorization (employees module). | domain |
| 3 | `Tourists` | Tourist registration, login, profile and interests (tourists module). | domain |
| 4 | `Tourist Spots` | Registered tourist spots with coordinates, schedules and multilingual content (tourist_spots module). | domain |
| 5 | `Events` | Cultural events and schedules (events module). | domain |
| 6 | `Gamification` | Routes, achievements and reward codes (gamification module). | domain |
| 7 | `Visitation` | GPS-validated check-ins at tourist spots: mark visitation (RF31) with Haversine presence validation (RF32), the immutable visitation ledger (RF33) and visitation history/visited-spots projections (visitation module; feature 011). | domain |
| 8 | `Dashboard` | Aggregated metrics and rankings for administrators (dashboard module). | domain |
| 9 | `Notifications` | Push notifications and communication (notifications module). | domain |
| 10 | `Chatbot` | Generative chatbot over registered content (chatbot module). | domain |
| 11 | `Health` | Operational health of the API and its database connectivity. | infrastructure |

## Operation tagging contract

For **every** operation in `paths`:

- `tags` is present, non-empty, and holds **exactly one** name.
- The name belongs to the catalog above (`Health` only for core-owned
  non-domain routes — today `GET /health`; domain routes carry their
  module's tag).
- Domain operations inherit the tag from their canonical module router
  (`core.routers.MODULE_ROUTERS`); module route files declare no tag
  strings.
- Any operation violating the above is a **contract violation**: the
  cross-cutting test suite must fail and report the offending path +
  method (spec FR-004/FR-005; enforcement is test-suite-only per
  clarification Q1).

## Alignment contract (registry ↔ modules)

- Each `DOMAIN_MODULES` entry maps bijectively to exactly one domain tag
  (`tourist_spots` → `Tourist Spots`; all others `X` → `X` capitalized or
  `_` → ` ` capitalized).
- The registry contains no tag outside this mapping except `Health`.

## Frozen guarantees (regression guards)

- `GET /health` path, status codes (200/503) and payload keys stay put.
- All contract tests of specs 002–005 pass with assertions untouched
  (existing payloads unchanged in behavior).
- No snake_case key appears in any response (spec 005 sweep remains green).