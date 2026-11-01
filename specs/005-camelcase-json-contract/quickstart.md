# Quickstart: Validate the camelCase JSON Contract

Prerequisites: repo checked out on `005-camelcase-json-contract`, `uv`
installed, Docker optional (tests use in-memory SQLite).

## 1. Run the contract suites

```bash
uv run pytest tests/contract/test_camelcase_contract.py -q   # sweep + canaries (FR-011, SC-001/006)
uv run pytest tests/contract -q                              # all contract tests (camelCase everywhere)
uv run pytest tests/unit/test_schemas_core.py -q             # ApiModel alias rules
uv run pytest -q                                             # full suite — must be green (ruff clean)
```

Expected: all green. The sweep fails on **any** JSON key containing `_`;
canaries prove the detector isn't vacuous.

## 2. See the contract live (dev server)

```bash
uv run python -m passanorte_back.main      # or: docker compose up (feature 004)
```

- `http://localhost:8000/docs` → Swagger: DTO names PascalCase
  (`TouristSessionResponse`, `ApiError`), properties camelCase.
- `http://localhost:8000/health` → `{"status": "ok", "database": "ok"}`.

```bash
# 200 camelCase output
curl -s -X POST localhost:8000/api/v1/auth/login \
  -H 'content-type: application/json' \
  -d '{"username": "...", "password": "..."}' | jq keys
# -> ["accessToken","expiresIn","refreshToken","role","tokenType"]

# 422 snake_case rejected, key named
curl -s -X POST localhost:8000/api/v1/auth/login \
  -H 'content-type: application/json' \
  -d '{"username": "...", "password": "...", "refresh_token": "x"}'
# -> {"errorCode":"validation_error","message":"Request body is invalid.",
#     "details":[{"key":"refresh_token","message":"Extra inputs are not permitted"}]}

# 422 unknown key rejected the same way
curl -s -X POST localhost:8000/api/v1/auth/login \
  -H 'content-type: application/json' \
  -d '{"user": "x", "password": "y"}'
```

## 3. Acceptance checklist (traceability)

- SC-001: `test_camelcase_contract.py::test_sweep_*` green; canary test
  turning the detector red exists.
- SC-002: matrix tests — for each body endpoint, camelCase accepted /
  snake_case 422 / unknown-key 422.
- SC-003: `uv run pytest tests/contract/test_{auth,employees,tourists_}.py`
  green; route paths byte-identical to pre-feature (diff of
  `app.openapi()["paths"].keys()`).
- SC-004: static OpenAPI sweep green (PascalCase DTO names, camelCase
  properties).
- SC-006: canary inheriting `ApiModel` with snake_case attr aliases to
  camelCase — proves inheritance by construction.

Cross-references: convention rules and error schema in
[contracts/camelcase-json.md](./contracts/camelcase-json.md); entity
mappings in [data-model.md](./data-model.md).