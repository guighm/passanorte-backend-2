# Feature Specification: JSON camelCase API Contract

**Feature Branch**: `005-camelcase-json-contract`

**Created**: 2026-10-31

**Status**: Draft

**Input**: User description: "Implementar a convenção de contrato JSON camelCase da API PassaNorte como infra transversal do monolito modular (docs/CONSTITUTION.md), em core/ + adaptação dos módulos auth, employees e tourists das specs 002-004..."

## Clarifications

### Session 2026-10-31

- Q: When the API rejects a request (snake_case input, unknown key, business
  error), should the error response body follow a unified project-specific
  error format, or keep the framework's default error structure converted to
  camelCase? → A: A single, Swagger-documented unified error schema with
  camelCase keys (e.g. `errorCode`, `message`, `details`), used by all
  endpoints — including the 422 input rejections.
- Q: How should acronyms/initialisms inside multi-word field names be cased,
  and what does the contract-sweep test count as a violation? → A: Full
  lowercase folding — acronyms become ordinary lowercase words when composed
  (`userCPF` → `userCpf`, `CPF` → `cpf`); word boundaries exist only where an
  underscore originally separated words; and the sweep test rejects exactly
  the keys containing an underscore (`_`) — no acronym whitelist, no extra
  casing rules beyond that.
- Q: How should the retroactive contract break of the existing endpoints be
  rolled out relative to API v1 (deprecation window, dual casing, or version
  bump)? → A: Direct break on v1 — same paths, camelCase output only and
  snake_case input rejected immediately, with no deprecation window and no
  v2; frontends update in the same release as the API.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Consistent camelCase JSON on every API response (Priority: P1)

A developer building the React admin panel or the Kotlin Passaporte app
consumes any PassaNorte endpoint and receives JSON whose keys are 100%
camelCase, matching the TypeScript types generated from Swagger: `accessToken`,
`firstName`, `touristSpot`, no exceptions and no mixed conventions. Nested
structures (lists, objects inside objects) follow the same rule, and every
exception/error payload — validation failures, authentication errors, business
errors — is delivered in camelCase as well.

**Why this priority**: This is the core cross-cutting guarantee the frontend
depends on; without it, every module integration becomes hand-cased.

**Independent Test**: A contract sweep exercises every registered HTTP
endpoint — dual source: static sweep over the OpenAPI operation list plus
runtime sweep over the registered routes — and fails if any response JSON
key contains a snake_case (underscore-separated) name.

**Acceptance Scenarios**:

1. **Given** any authenticated or public endpoint of the API, **When** its
   response is parsed as JSON, **Then** every key — at any nesting level — is
   camelCase (no underscore-separated keys anywhere in success responses).
2. **Given** an endpoint that returns a list of objects, **When** the list is
   inspected, **Then** the keys of each object are camelCase.
3. **Given** any HTTP error response (validation failure, authentication
   failure, business rule rejection, unexpected exception), **When** the
   response body is parsed, **Then** all its keys are camelCase.
4. **Given** the OpenAPI/Swagger document, **When** it is compared against
   real responses, **Then** all schema property names and DTO (model) names in
   Swagger match the keys actually delivered in JSON.

### User Story 2 - Strict camelCase-only input (Priority: P1)

A frontend client that sends a request body containing snake_case or unknown
keys gets a single, unambiguous rejection: HTTP 422 with a clear message
identifying the offending key(s). The API never silently accepts
`first_name` in place of `firstName`, nor ignores unrecognized keys — a
misspelled or wrongly-cased payload fails loudly at the contract border
instead of producing silently-dropped data downstream.

**Why this priority**: Strictness is half of the contract; without rejection
of snake_case input, contract drift between backends and frontends goes
unnoticed.

**Independent Test**: For each endpoint that accepts a JSON body, send a
valid payload with one key rewritten to snake_case and one payload with an
added unknown key; both must be rejected with 422 and a message naming the
key.

**Acceptance Scenarios**:

1. **Given** a valid camelCase payload for an endpoint that accepts a body,
   **When** it is submitted, **Then** the request is accepted with the
   expected success status (business validation aside).
2. **Given** the same payload with one field rewritten in snake_case
   (e.g. `first_name` instead of `firstName`), **When** it is submitted,
   **Then** the API responds 422 with a message that clearly identifies the
   rejected key.
3. **Given** a payload containing an unrecognized key, **When** it is
   submitted, **Then** the API responds 422 and the message identifies the
   unknown key.
4. **Given** a payload that mixes camelCase and snake_case for the same data
   (e.g. both `firstName` and `first_name`), **When** it is submitted,
   **Then** the API responds 422 naming the snake_case key, and data is not
   partially applied.

### User Story 3 - Retroactive migration of shipped modules (Priority: P2)

The already-implemented endpoints (specs 002–004: auth, employees, tourists —
login, session/refresh, current user, employee management, tourist
registration/login/profile/interests) follow the new contract with no change
to route paths or business behavior. Existing contract tests are updated to
assert camelCase output and camelCase-only input, and a frontend consuming the
old endpoints with TypeScript-typed camelCase payloads works without adapters.

**Why this priority**: The contract only has value once the living endpoints
comply; but it lands right after the core guarantee.

**Independent Test**: Run the auth, employees and tourists contract suites —
all pass with camelCase assertions; route paths (`/api/v1/...`, kebab-case)
are byte-for-byte unchanged; HTTP status codes and business outcomes for
valid flows are unchanged.

**Acceptance Scenarios**:

1. **Given** the auth endpoints (login, refresh, current user), **When** the
   pre-existing contract tests run, **Then** they pass with camelCase request
   bodies and assert camelCase responses (e.g. `accessToken`, token expiry
   fields).
2. **Given** the employees endpoints (create, list, edit), **When** a
   camelCase payload is submitted, **Then** the operations succeed and the
   responses expose camelCase keys (e.g. `firstName`, `lastName`, `email`).
3. **Given** the tourists endpoints (register, login, profile, update,
   interests), **When** camelCase payloads are submitted, **Then** the
   operations succeed and responses expose camelCase keys.
4. **Given** the same snake_case/unknown-key payloads from User Story 2
   against these modules, **When** submitted, **Then** each is rejected with
   422 naming the key.

### User Story 4 - Swagger as the single source for frontend types (Priority: P3)

A developer generating TypeScript types from the Swagger document gets model
(DTO) names in PascalCase (e.g. `TouristSessionResponse`,
`EmployeeCreateRequest`), property names in camelCase, and enum string values
— when present — following the same lowercase-fold rule (`touristSpot`,
`cpf`); as values rather than keys, they are not machine-checked by the
sweep. Generated types drop into frontend code without renaming.

**Why this priority**: Improves DX and type-safety of consumption; depends on
both strictness guarantees above.

**Independent Test**: Download `/openapi.json` and assert: every public
schema name is PascalCase, every schema property name is camelCase, and
schema names for the migrated modules are unchanged relative to their
existing code names (updated only where required by the new convention).

**Acceptance Scenarios**:

1. **Given** the published OpenAPI document, **When** model names are
   inspected, **Then** every exposed schema/DTO name is PascalCase.
2. **Given** the published OpenAPI document, **When** schema properties are
   inspected, **Then** every property name is camelCase.
3. **Given** a type-generation run on the Swagger document, **Then** the
   produced types compile against JSON responses of the corresponding
   endpoints without key translation.

### Edge Cases

- What happens when the client sends neither camelCase nor snake_case but an
  unknown field entirely? → Rejected 422 naming the key (User Story 2).
- What happens when a string **value** contains an underscore
  (e.g. an email, a CPF, `first_name_tourist` as literal text)? → Values are
  never inspected for casing; only JSON **keys** follow the convention.
- What happens when a nested error structure (e.g. validation errors with
  field locations) is returned? → Nested keys, including error-location
  fields, must be camelCase.
- What happens with query parameters or path parameters? → Route paths and
  their query/path parameter names are out of scope (paths stay kebab-case as
  today); the convention applies to JSON bodies and JSON responses.
- What happens to identifiers internal to Python code and database columns?
  → They remain snake_case per Python/DB convention; conversion happens only
  at the HTTP border.
- What happens when a legacy name contains an acronym or initialism (e.g.
  `CPF`, `userCPF`)? → Folded to full lowercase at the border (`cpf`,
  `userCpf`); no acronym uppercase is preserved, and no whitelist is needed —
  only keys containing `_` are violations.
- What happens to endpoints whose schemas do not exist yet (future specs)?
  → The convention is a mandatory starting point for all new schemas.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST deliver HTTP JSON responses with 100% camelCase
  keys at every nesting level, for all endpoints (public, authenticated, and
  error paths), using examples such as `accessToken`, `firstName`,
  `touristSpot`. Acronyms inside composed names fold to full lowercase
  (`userCPF` → `userCpf`, `CPF` → `cpf`); word boundaries exist only where an
  underscore originally separated words.
- **FR-002**: The system MUST apply the JSON key convention only at the HTTP
  border: internal Python identifiers and database columns remain snake_case
  (Python/PEP 8 and SQL conventions untouched).
- **FR-003**: The system MUST reject, with HTTP 422 and a clear message
  naming the offending key, any request body that (a) contains keys — at any
  nesting level of the body tree — in snake_case or any casing other than the
  declared camelCase contract, or (b) contains unrecognized keys.
- **FR-004**: The system MUST reject payloads mixing camelCase and snake_case
  for the same data with 422 (no partial application of valid keys).
- **FR-005**: All error payloads — validation errors, authentication/authorization
  failures, business-rule errors, unhandled exception responses, and the 422
  input rejections from FR-003 — MUST use a single, unified error schema with
  camelCase keys (e.g. `errorCode`, `message`, `details`), documented in the
  OpenAPI/Swagger document and identical in shape across all endpoints.
- **FR-006**: All schema/DTO class names exposed in the OpenAPI/Swagger
  document MUST be PascalCase.
- **FR-007**: All schema property names shown in the OpenAPI/Swagger document
  MUST be camelCase and identical to the actual JSON keys delivered, so that
  Swagger serves as the single source for generating frontend TypeScript
  types.
- **FR-008**: The camelCase convention MUST be implemented as shared,
  cross-cutting infrastructure in the project's core layer, such that every
  module's schemas inherit it by construction (no per-module reimplementation
  and no module able to opt out).
- **FR-009**: The specs 002–004 endpoints (auth, employees, tourists) MUST be
  migrated retroactively to the new contract with (a) no change to route
  paths, (b) no change to HTTP status codes for existing valid/invalid flows,
  and (c) no change to business logic. The rollout is a direct break on v1:
  no deprecation window, no v2, no dual-casing response mode — frontends
  update in the same release as the API.
- **FR-010**: Existing contract tests for auth, employees and tourists MUST
  be updated to the new contract and MUST demonstrate: camelCase input
  accepted, snake_case input rejected with 422, and camelCase responses.
- **FR-011**: A cross-cutting contract test MUST sweep the responses of all
  registered HTTP endpoints and FAIL if any response JSON key at any nesting
  level contains an underscore (`_`) — the sole, deterministic violation rule;
  for success and error responses alike.
- **FR-012**: Every future schema added to any module MUST inherit the
  shared camelCase contract by construction; adding a schema that
  unintentionally breaks the convention MUST fail the test suite.
- **FR-013**: Route paths (`/api/v1/...`, kebab-case), query/path parameter
  behavior, and authentication/RBAC semantics MUST remain unchanged by this
  feature.

*Assumed defaults (documented, no clarification needed):*
- JSON string **values** are exempt from casing inspection — only keys follow
  the convention (prevents false positives on emails, CPFs, descriptions).
- Existing schema class names in auth/employees/tourists already follow
  PascalCase patterns (e.g. `LoginRequest`, `TouristProfileResponse`); their
  names mostly survive the migration, updated only where the new convention
  demands.
- The 422 rejection behavior applies to JSON request bodies of endpoints that
  accept one; bodyless endpoints (e.g. GET) are unaffected.

### Key Entities *(include if feature involves data)*

- **JSON Contract (cross-cutting)**: the shared convention binding every HTTP
  JSON boundary — attributes: camelCase keys, strict input rejection,
  PascalCase DTO names, single core-wide enforcement point.
- **Migrated Endpoints (specs 002–004)**: auth (token issuance/refresh,
  current user), employees (management CRUD), tourists (registration, login,
  profile, interests) — attributes: unchanged route paths, unchanged status
  codes, camelCase bodies/responses, updated contract tests.
- **Contract Sweep Test**: automated verification artifact that walks all
  registered endpoints from the OpenAPI registry and enforces camelCase-only
  response keys.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A contract sweep over all registered endpoints passes with zero
  snake_case keys found in any response (success or error), and demonstrably
  fails when a snake_case key is planted — proving the check isn't vacuous.
- **SC-002**: 100% of body-accepting endpoints reject a snake_case field and
  an unknown field with HTTP 422 plus a message naming the key.
- **SC-003**: All existing auth, employees and tourists contract tests pass
  under the new contract with route paths and business outcomes unchanged.
- **SC-004**: 100% of DTO names in the published Swagger document are
  PascalCase and 100% of their property names match the camelCase keys
  actually delivered in responses.
- **SC-005**: A frontend developer can consume any endpoint with TypeScript
  types generated from Swagger without writing any key-translation code.
- **SC-006**: Adding a new schema to any module automatically complies with
  the camelCase contract with no module-local configuration (verified by a
  test creating a synthetic snake_case-named schema and observing the
  convention hold).

## Assumptions

- The existing route paths in kebab-case under `/api/v1/` are stable and out
  of scope; only JSON key casing and body strictness change.
- The project's modular-monolith architecture (per `docs/CONSTITUTION.md`)
  stays intact: shared contract infrastructure lives in the core layer
  (`src/passanorte_back/core/`), and modules consume it without owning
  per-module serialization rules.
- Current response payload shapes (fields present, nesting) remain as
  implemented in specs 002–004; this feature changes key casing and input
  strictness only, not payload structure.
- Error message content is user-facing and stays in English at the technical
  layer (consistent with current API error messages), with the offending key
  named explicitly in each rejection.
- Endpoints of modules not yet implemented (specs beyond 002–004) have no
  live routes today; for them, the convention simply applies when their
  schemas are created — retroactive migration only concerns live
  auth/employees/tourists routes.