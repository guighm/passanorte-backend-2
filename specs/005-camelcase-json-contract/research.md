# Research: JSON camelCase API Contract

Resolved against the existing codebase (`specs/002-004` artifacts) and the
clarifications Q1–Q3 in spec.md. All NEEDS CLARIFICATION items: none pending.

## R1 — Enforcement mechanism: shared Pydantic base class in `core/`

**Decision**: New `src/passanorte_back/core/schemas.py` exporting
`ApiModel` — a `pydantic.BaseModel` with:

- `alias_generator = to_camel` (from `pydantic.alias_generators`)
- `extra = "forbid"` (unknown keys → validation error, FR-003b)
- `populate_by_name` **not set** (Pydantic v2 default `False`) — this is
  what makes snake_case aliases *not* accepted at validation time (FR-003a).
  Setting `populate_by_name=True` would silently accept `first_name` with
  `first_name_name`-style drift unpoliced — explicitly avoided.
- Serialization: FastAPI serializes `response_model` with `by_alias=True`
  by default → responses carry camelCase automatically.

**Rationale**: One code point satisfies FR-008/FR-012 (inherited by
construction, no opt-out). Pydantic v2 `to_camel("user_cpf") == "userCpf"`
matches clarification Q2 folding (lowercase everything, no acronym
whitelist); `to_camel("cpf") == "cpf"`. Attribute names stay snake_case
(PEP 8 untouched, FR-002); DB columns untouched (no Alembic migration).

**Alternatives considered**:
- Per-module `model_config` duplication — rejected: violates FR-008
  (modules could opt out / drift).
- Middleware rewriting JSON keys in/out — rejected: loses static Swagger
  correctness (FR-007) and adds a hidden layer; contract-first prefers
  schema-true keys.
- Pyproject-wide Pydantic plugin — rejected: no such stable mechanism in
  the pinned stack; overengineering (YAGNI).

## R2 — Input strictness → 422 with named key

**Decision**: With `extra="forbid"` + no `populate_by_name`, bodies
containing snake_case or unknown keys raise Pydantic validation errors of
types `extra_forbidden` / (for typo'd keys) `missing`. The unified
validation handler (R3) maps each error item to `{key, message}` where
`key` is the offending key **as received** (a JSON string value inside the
error payload — exempt from casing checks) and `message` states the
problem in English. Multiple offending keys → all reported in `details`;
status 422; `errorCode: "validation_error"`.

**Rationale**: Meets FR-003/FR-004 verbatim ("message naming the offending
key"; no partial application since the whole body fails validation).

**Alternatives considered**: HTTP 400 with ad-hoc body — rejected: spec
pins 422 and framework validation errors already surface as 422.

## R3 — Unified error schema + three exception handlers

**Decision** (clarification Q1): `core/schemas.py` defines
`ApiErrorKeyDetails {key, message}` and `ApiError {errorCode, message,
details: list[ApiErrorKeyDetails]}` — PascalCase class names (FR-006),
camelCase properties (FR-007). New `core/error_handlers.py` registers on
the app (wired in `main.py`):

1. `RequestValidationError` → 422 `validation_error` (details per R2).
2. `StarletteHTTPException` → status preserved; HTTPException `detail`
   str becomes `message`; taxonomy mapping: 401→`authentication_failed`,
   403→`authorization_failed`, 404→`resource_not_found`,
   409→`conflict`, others→`request_error`.
3. Unhandled `Exception` → 500 `internal_error` with generic message
   (no internals leaked; II. Security).

`details` defaults to `[]`, keeping the shape uniform across all paths
(FR-005).

**Alternatives considered**: Keep default FastAPI `{"detail": ...}` /
`{"detail": [{"loc", "msg", ...}]}` bodies — rejected: contradicts
clarification Q1 (single Swagger-documented schema, nested keys camelCase;
default body mixes snake_case loc items and is not unified).

## R4 — Contract-sweep test strategy (FR-011, SC-001–SC-006)

**Decision**: `tests/contract/test_camelcase_contract.py` combines:

- **Static OpenAPI sweep**: iterate `app.openapi()` — every schema name
  PascalCase, every property name free of `_` (FR-006/FR-007).
- **Runtime sweep**: walk every route in `app.routes`; for each reachable
  endpoint build the minimal request (auth flows seeded via existing
  conftest fixtures; protected endpoints exercised both unauthenticated —
  asserting the unified 401 JSON — and through seeded-token flows);
  recursively assert every JSON key (success or error) contains no `_`.
- **Canary (SC-001)**: a planted snake_case key in a response model makes
  the sweep fail (asserted by unit-level recheck of the detector helper,
  which is a pure function: `assert no_snake_case(payload) is False`).
- **SC-006 canary**: a temporary `ApiModel` subclass with a snake_case
  attribute proves inheritance (alias is camel) without any module-local
  config.

**Rationale**: covers live behavior and Swagger truth from one suite;
detector-as-pure-function makes SC-001 provable without violating sweep
integrity at runtime.

**Alternatives considered**: Sweep only contract tests' captured bodies —
rejected: misses endpoints no current test covers (future modules).
HTTP-crawl-only — rejected: 404/405 bodies don't prove schema truth.

## R5 — Value exemption boundaries

**Decision**: JSON string *values* (emails, CPFs, descriptions, error
message text) are never casing-inspected; enum string values follow the
same lowercase-fold rule when introduced (Q2-consistent) but are not
swept. Dates stay ISO-8601 (value-level, unchanged); `token_type:
"bearer"` value unchanged.

**Rationale**: spec Assumptions + Edge Cases; prevents false positives.

## R6 — Root routes outside `/api/v1`

**Decision**: `GET /health` (keys `status`, `database` — already
camelCase-safe, returned via `JSONResponse`) is included in the runtime
sweep; stays outside the ApiModel regime (no body schema). `/docs`,
`/openapi.json` are documentation surfaces — excluded from the sweep
(their structure is framework-defined).

**Rationale**: matches `core/routers.py` (research R6 of feature 001) —
`/health` and docs live at the root by design.

## R7 — Migration touchpoints confirmed in code

**Decision**: exact edits (grounded in current source):

- 18 schema classes inherit `ApiModel` (drop `BaseModel`): auth
  (`LoginRequest`, `RefreshRequest`, `SessionResponse`,
  `CurrentUserResponse`, `AdminAccountStatus`), employees
  (`EmployeeCreateRequest`, `EmployeeView`, `EmployeeCreatedResponse`,
  `EmployeeListResponse`, `EmployeeUpdateRequest`), tourists
  (`TouristCreateRequest`, `TouristLoginRequest`, `TouristSessionResponse`,
  `TouristRegistered`, `TouristProfileResponse`, `TouristUpdateRequest`,
  `InterestCategory`, `InterestCategoriesResponse`,
  `TouristInterestsResponse`, `TouristInterestsUpdateRequest`).
- Existing `ConfigDict(extra="forbid")` declarations collapse into the
  base (no behavior change); `from_attributes=True` on
  `AdminAccountStatus` is preserved alongside the base config
  (`from_attributes` composes with alias config in Pydantic v2).
- Class names unchanged → DTO names already PascalCase (FR-006 zero
  churn); only JSON output keys change (`access_token`→`accessToken`,
  `is_active`→`isActive`, `updated_at`→`updatedAt`, `first_name`→
  `firstName`, `country_of_origin`→`countryOfOrigin`, `passport_number`→
  `passportNumber`…).
- Route paths, status codes, business logic: untouched (FR-009/FR-013).

**Rationale**: minimal-diff migration; test updates are the observable
side (payloads in camelCase, snake_case-rejection assertions added).