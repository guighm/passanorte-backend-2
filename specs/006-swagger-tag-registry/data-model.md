# Data Model: Centralized Swagger Tag Registry

Feature: 006-swagger-tag-registry | Date: 2026-11-02

No database entities, tables or migrations are involved (spec FR-008:
documentation metadata only). The "data" of this feature lives in the
application's in-memory OpenAPI metadata.

## Entities

### TagRegistryEntry (conceptual — in-memory constant)

| Field | Type | Constraint |
|---|---|---|
| `name` | string | Exactly one of the 11 canonical names (`Auth`, `Employees`, `Tourists`, `Tourist Spots`, `Events`, `Gamification`, `Visitation`, `Dashboard`, `Notifications`, `Chatbot`, `Health`); unique across the registry |
| `description` | string | Non-empty, English, describes what the group covers |
| `position` | implicit (list order) | The 10 domain tags follow the canonical `DOMAIN_MODULES` order; `Health` is last (spec clarification Q2) |

Registry size: exactly 11 entries — 10 domain (1:1 with `DOMAIN_MODULES`,
verified by test) + 1 infrastructure. No entry may exist without a canonical
module (except `Health`), and every canonical module must have one
(FR-002).

### TaggedOperation (existing concept, newly constrained)

An OpenAPI operation (path + HTTP method) in the generated document.

| Attribute | New constraint |
|---|---|
| `tags` | Required, non-empty, **exactly one** entry, member of the registry (FR-004, FR-005) |
| `path`/`method`/`payloads` | FROZEN — unchanged by this feature (FR-008) |

## Relationships

- `TagRegistryEntry.name` 1:1 `DOMAIN_MODULES` entry (only for the 10 domain tags); `Health` pairs with core-owned routes (today: `GET /health`).
- `TaggedOperation` references exactly one `TagRegistryEntry.name`.

## State transitions

None. Static metadata, immutable at runtime.

## Validation summary

All validation is test-enforced (spec clarification Q1): the sweep in
`tests/contract/test_openapi_tags.py` asserts catalog declaration, order,
1:1 alignment, per-operation single registered tag, and reports offending
path + method on failure.