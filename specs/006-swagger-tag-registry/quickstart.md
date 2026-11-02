# Quickstart: Validate the Swagger Tag Registry (feature 006)

Prove the feature end-to-end: catalog declared, every operation tagged
exactly once with a registered tag, order preserved, and nothing else in
the API changed.

## Prerequisites

- Repo checked out on branch `006-swagger-tag-registry`
- Python 3.13 environment with the project installed (`uv sync` or
  `pip install -e .`)

## 1. Run the cross-cutting sweep

```bash
uv run pytest tests/contract/test_openapi_tags.py -v
```

Expected: all green. Coverage of each test maps to the spec:

- catalog declaration test → the OpenAPI document exposes the 11 catalog
  tags with descriptions and the exact order (10 domains, `Health` last)
- per-operation sweep tests → every path×method has exactly one tag,
  drawn from the catalog (SC-001..003; FR-004/FR-005)
- alignment test → bijective mapping `DOMAIN_MODULES` ↔ domain tags
  (FR-002)

## 2. Verify nothing regressed

```bash
uv run pytest -q          # full suite: contract + integration + smoke + unit
uv run ruff check .
```

Expected: full suite green (specs 002–005 behavior untouched — FR-008),
ruff clean.

## 3. Negative check — prove the guard is real (SC-004)

Locally only (do not commit): temporarily remove the tag attachment for
one module (e.g. drop `tags=[...]` from the canonical router creation) or
add a throwaway untagged route in a scratch branch, then run:

```bash
uv run pytest tests/contract/test_openapi_tags.py -q
```

Expected: **red**, with the assertion naming the offending path + method.
Revert the change; the suite returns green. This demonstrates the sweep
actually detects violations rather than passing vacuously.

## 4. See it in the browser (optional)

```bash
uv run passanorte-back   # or: uv run uvicorn passanorte_back.main:app
```

Open <http://localhost:8000/docs>:

- 11 tag groups displayed in the canonical order (`Auth`…`Chatbot`, then
  `Health`)
- Every existing operation listed under its module group (no uncategorized
  "default" group)
- `GET /health` under `Health`
- A response from any endpoint still shows camelCase keys (spec 005)

## References

- Tag catalog wording: `contracts/openapi-tags.md`
- Sweep assertions: `research.md` R3
- Registry shape: `data-model.md`