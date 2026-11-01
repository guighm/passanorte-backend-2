# Contract: PassaNorte JSON camelCase Convention

Source of truth: `spec.md` (FR-001..FR-013) + clarifications Q1–Q3. This
document is the machine-facing companion: the convention rules, the unified
error schema, and the per-endpoint key mappings for the migrated endpoints
(auth, employees, tourists — specs 002–004). Route paths and status codes
for valid flows are unchanged.

## 1. Convention rules

1. All HTTP JSON keys — request bodies and responses, at every nesting
   level — are camelCase with **full-lowercase folding** of acronyms:
   word boundaries exist only where an underscore originally separated
   words (`user_cpf` → `userCpf`, `CPF` → `cpf`). No acronym whitelist.
2. Internal Python identifiers and DB columns remain snake_case; conversion
   happens only at the HTTP border (shared `ApiModel` base in
   `core/schemas.py`).
3. Request bodies are **strict**: keys not matching the declared camelCase
   contract (snake_case or other casings) and unknown keys are rejected
   with **422** — `errorCode: "validation_error"` — each offending key
   named in `details`. Whole body fails together (no partial application).
4. JSON string values are never casing-checked (emails, CPFs, PT labels,
   `token_type` value `"bearer"`). Enum string values, when introduced,
   follow the same folding rule but are not machine-swept.
5. Swagger/OpenAPI: schema (DTO) names PascalCase; schema properties
   camelCase and identical to delivered keys — the generated TypeScript
   types drop in without renaming.
6. Route paths stay kebab-case under `/api/v1`; status codes for valid
   flows unchanged. Direct break on v1 (no deprecation window, no v2).

## 2. Unified error schema (all failure paths)

Shape (keys exactly):

```json
{
  "errorCode": "validation_error",
  "message": "Request body is invalid.",
  "details": [
    {
      "key": "first_name",
      "message": "Extra inputs are not permitted"
    }
  ]
}
```

- `errorCode` — stable machine code; `message` — one-line English summary;
  `details` — one item per offending key (`key` = the key **as received**,
  i.e. a value — exempt from folding; `message` = why it was rejected).
- `details` is `[]` when not applicable (e.g. 500, plain 401 without body
  specifics). 500 never leaks internals.
- `errorCode` ⇄ status mapping: `validation_error`→422,
`authentication_failed`→401, `authorization_failed`→403,
`resource_not_found`→404, `conflict`→409, `request_error`→other 4xx,
`internal_error`→500.

OpenAPI registers this payload as `ApiError` (PascalCase DTO name).

## 3. Endpoint key mappings (migrated endpoints)

### auth — `/api/v1/auth`

| Endpoint | Direction | camelCase keys |
|----------|-----------|----------------|
| POST `/login` | request | `username`, `password` |
| POST `/login` | response | `accessToken`, `refreshToken`, `tokenType`, `expiresIn`, `role` |
| POST `/refresh` | request | `refreshToken` |
| POST `/refresh` | response | as login response |
| GET `/me` | response | `username`, `role` |
| POST `/logout` | — | 204 No Content (no body; errors follow `ApiError`) |
| admin bootstrap | response | `username`, `role`, `isActive`, `created`, `updatedAt` |

### employees — `/api/v1/employees`

| Endpoint | Direction | camelCase keys |
|----------|-----------|----------------|
| POST `` | request | `name`, `username` |
| POST `` | response | `id`, `name`, `username`, `status`, `createdAt`, `updatedAt`, `initialPassword` |
| GET `` | response | `items` (each = employee view w/o `initialPassword`), `total` |
| GET `/{id}` | response | employee view (as above, w/o `initialPassword`) |
| PATCH `/{id}` | request | `name`?, `username`?, `status`? |
| PATCH `/{id}` | response | employee view |
| POST `/{id}/revoke` | — | 204 No Content (no body; errors follow `ApiError`) |

### tourists — `/api/v1/tourists`

| Endpoint | Direction | camelCase keys |
|----------|-----------|----------------|
| POST `` (register) | request | `firstName`, `lastName`, `countryOfOrigin`, `cpf`?, `passportNumber`?, `phone`, `email`, `password` |
| POST `` (register) | response | `id`, `email` |
| POST `/login` | request | `email`, `password` |
| POST `/login` | response | `accessToken`, `refreshToken`, `tokenType`, `expiresIn`, `role` |
| GET `/me` (profile) | response | `id`, `firstName`, `lastName`, `countryOfOrigin`, `email`, `phone`, `cpf`?, `passportNumber`?, `interests` |
| GET `/{id}` (profile) | response | tourist profile view |
| PATCH `/{id}` | request | optional subset of register keys — 204 No Content on success |
| GET `/interest-categories` | response | `categories` (`key`, `label`) |
| GET `/me/interests` | response | `interests` |
| PUT `/me/interests` | request | `interests` |

*(Path spellings verified against `routes/authentication.py`,
`routes/management.py`, `routes/profile.py`, `routes/interests.py`,
`routes/tourists.py`, feature 005 remediation C1.)*

## 4. Enforcement points (what makes this hold)

- `core/schemas.py`: `ApiModel` (rules 1–3) + `ApiError` (section 2);
  every module schema inherits `ApiModel` — adding a schema outside it
  fails the sweep by construction (SC-006 canary).
- `core/error_handlers.py` + two lines in `main.py`: sections 2.
- `tests/contract/test_camelcase_contract.py`: detector + static OpenAPI
  sweep + runtime sweep over `app.routes` + canaries (SC-001).