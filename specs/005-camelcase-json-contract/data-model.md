# Data Model: JSON camelCase API Contract

No database change — zero Alembic migrations. This feature's "entities" are
contract artifacts: code-facing schema bases and their HTTP projections.

## Entity: `ApiModel` (core contract base) — NEW

- **Location**: `src/passanorte_back/core/schemas.py`
- **Represents**: the single base class every HTTP-bound Pydantic schema
  inherits (FR-008/FR-012)
- **Configuration**: `alias_generator=to_camel` (full-lowercase folding —
  Q2), `extra="forbid"`, no `populate_by_name`
- **Validation rules**: attribute names stay snake_case (PEP 8); aliases
  only exist at the HTTP border (FR-002)
- **Relationships**: parent of all 18+ module schema classes (below) and of
  the unified error schema

## Entity: `ApiError` (unified error payload) — NEW

- **Location**: `src/passanorte_back/core/schemas.py`
- **Represents**: the single error body for every failure path (Q1/FR-005)
- **Fields** (JSON): `errorCode: str`, `message: str`,
  `details: list[ApiErrorKeyDetails]` (default `[]`) —
  `ApiErrorKeyDetails` = `{key: str, message: str}`
- **errorCode taxonomy**: single source of truth — see
  [contracts/camelcase-json.md §2](./contracts/camelcase-json.md)
  (`validation_error`, `authentication_failed`, `authorization_failed`,
  `resource_not_found`, `conflict`, `request_error`, `internal_error`)
- **Relationships**: produced exclusively by the three handlers in
  `core/error_handlers.py`; consumed by tests and frontends

## Entity: Migrated endpoint schemas — EDITED (all: `BaseModel` → `ApiModel`)

Class names unchanged (PascalCase DTO names, FR-006 — zero churn). JSON
key mappings only:

| Module | Schema | Input as | JSON key(s) changed |
|--------|--------|----------|---------------------|
| auth | `LoginRequest` | body | `username`, `password` (unchanged) |
| auth | `RefreshRequest` | body | `refresh_token` → `refreshToken` |
| auth | `SessionResponse` | response | `access_token` → `accessToken`, `refresh_token` → `refreshToken`, `token_type` → `tokenType`, `expires_in` → `expiresIn`; `role` unchanged |
| auth | `CurrentUserResponse` | response | `username`, `role` (unchanged) |
| auth | `AdminAccountStatus` | response | `is_active` → `isActive`, `updated_at` → `updatedAt`; others unchanged |
| employees | `EmployeeCreateRequest` | body | `name`, `username` (unchanged) |
| employees | `EmployeeView` | response | `created_at` → `createdAt`, `updated_at` → `updatedAt`; others unchanged |
| employees | `EmployeeCreatedResponse` | response | inherits `EmployeeView` + `initial_password` → `initialPassword` |
| employees | `EmployeeListResponse` | response | `items`, `total` (unchanged) |
| employees | `EmployeeUpdateRequest` | body | `name`, `username`, `status` (unchanged) |
| tourists | `TouristCreateRequest` | body | `first_name` → `firstName`, `last_name` → `lastName`, `country_of_origin` → `countryOfOrigin`, `passport_number` → `passportNumber`; `cpf`, `phone`, `email`, `password` unchanged |
| tourists | `TouristLoginRequest` | body | `email`, `password` (unchanged) |
| tourists | `TouristSessionResponse` | response | as `SessionResponse` |
| tourists | `TouristRegistered` | response | `id`, `email` (unchanged) |
| tourists | `TouristProfileResponse` | response | as TouristCreateRequest keys; `interests` unchanged |
| tourists | `TouristUpdateRequest` | body | as TouristCreateRequest keys (all optional) |
| tourists | `InterestCategory` | response | `key`, `label` (unchanged — data values, PT labels) |
| tourists | `InterestCategoriesResponse` | response | `categories` (unchanged) |
| tourists | `TouristInterestsResponse` | response | `interests` (unchanged) |
| tourists | `TouristInterestsUpdateRequest` | body | `interests` (unchanged) |

## Entity: Contract-sweep test — NEW

- **Location**: `tests/contract/test_camelcase_contract.py`
- **Represents**: the always-on verification artifact (FR-011, SC-001/006)
- **Parts**: pure-function key detector (unit-testable), static OpenAPI
  sweep, runtime route sweep, canary checks
- **State transitions**: none (assertion artifact)

## Entity: `core/error_handlers.py` — NEW

- **Represents**: the three handlers (validation / HTTPException /
  unhandled) wiring `ApiError` onto every failure path; registered in
  `main.py` (two-line edit)

## Explicit non-entities (unchanged)

Route paths (`/api/v1/...`, kebab-case), HTTP status semantics for valid
flows, RBAC dependencies, SQLAlchemy models/tables, Alembic migrations,
`/health` payload keys (already compliant), business services/repositories.

## State transitions

None applicable — convention change, not lifecycle change. The only
behavioral state shift is: previously-accepted snake_case bodies now fail
with 422 (direct v1 break, Q3 — no dual-mode window).