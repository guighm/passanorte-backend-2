# Research: Notificações por Interesse (015-interest-notifications)

Phase 0 output. Resolves design unknowns of the spec (clarifications Q1–Q5
already in spec.md `## Clarifications`), cross-checked against the live
codebase (emitter seams `events.services.create_event`,
`tourist_spots.services.create_spot`, `gamification.services.create_route`;
empty notifications scaffold; tag pre-mounted).

## R1 — Storage shape for subscriptions and notifications

**Decision** (migration 0010, data-model.md):

- `notification_subscriptions`: `id`, `tourist_id` (FK, indexed),
  `category_key`, created_at; **unique (tourist_id, category_key)** —
  idempotent subscribe (Q1 channel of its own).
- `notifications`: `id`, `tourist_id` (indexed), `item_type`
  (`event|spot|route`), `item_id`, `title`, `description`, `created_at`
  (indexed), `read_at` (nullable). **Unique (tourist_id, item_type,
  item_id)** — one notification per tourist×item (FR-009 dedupe, DB-level).
- Index `ix_notifications_tourist_read` (`tourist_id`, `read_at`) serves
  the unread list/filter and the count (SC-005).

**Alternatives**: per-category notification rows (violates FR-009); join
table read-state (denormalizes what is a single owner row); enum column
vs string — string + validated at schema/service (matches repo norms).

## R2 — Best-effort emission that cannot poison the emitter's transaction

**Decision**: the public seam
`notifications.services.create_interest_notification(...)` runs its own
work inside `session.begin_nested()` (SAVEPOINT): any failure rolls back
ONLY the savepoint, logs a structured error (best-effort, FR-011) and
returns normally — the emitter's in-progress item creation (same session,
outer transaction) is untouched. Insert rides
`insert(...).on_conflict_do_nothing()`, portable SQLite/PostgreSQL.

**Rationale**: 014 used a separate engine session because recording happened
at the HTTP edge; here emission is inside the emitter's service (same
request-scoped transaction) — a separate session would commit the
notification before the item row exists in the DB (FK/visibility race) or
require deferred jobs (YAGNI). The savepoint keeps atomicity semantics with
zero new infrastructure.

**Alternatives**: seam raises → emitter wraps try/except (duplicates the
guard in three modules); separate engine session after commit (visibility
race + drift from FR-011 test); async queue (constitution reserves it).

## R3 — Match generation (set-based)

**Decision**: one query `SELECT DISTINCT tourist_id FROM
notification_subscriptions WHERE category_key IN (:keys)`; then bulk insert
with `on_conflict_do_nothing` of (tourist_id, item_type, item_id).
Zero-match → zero inserts (US2/AC5). Category keys arrive from the emitter
(already-validated domain data).

## R4 — Category resolution per emitter (Q2/Q3)

**Decision**: emitters pass what the item really has:

- **tourist_spots.create_spot**: its own `payload.categories` (already
  validated against the catalog).
- **events.create_event**: events have NO categories of their own — the
  event **inherits the categories of its target spot** (same reasoning as
  Q3 for routes; recorded here for traceability). The events service reads
  them through the NEW public read seam `tourist_spots.services.
  categories_for_spots(session, spot_ids) -> dict[int, list[str]]`.
- **gamification.create_route**: union of `categories_for_spots` over the
  route's spots (Q3). Route with no spots/categories → no notification.

Notifications never resolves categories itself (it only crosses subscription
data) — emitters own their item's categories; the seam signature stays
category-agnostic. `categories_for_spots` is a read-only public service in
tourist_spots (allowed: services are the public surface; AST gate-compliant).

## R5 — Text composition (Q2), i18n-ready but single-language now

**Decision**: templates live in `notifications.services.emission` as a
data map keyed by item type — title `f"Novo {label}: {item_name}"`,
description = emitter-provided short description (truncated to a documented
cap, e.g. 200 chars); labels: evento/ponto turístico/rota turística
(Portuguese-facing content stays Portuguese — constitution VII).
The map is the single i18n seam (RNF16): a future translation table swaps
this data map, no code restructuring.

**Unit-tested** (templates exact strings) so future i18n changes are
deliberate.

## R6 — Delivery endpoints (Q4/Q5), tourist-exclusive

**Decision** — 7 endpoints under `/api/v1/notifications`:

- `GET /subscriptions` / `PUT /subscriptions` (replace selection — same
  pattern as profile interests, FR-004/Q1) /
  `DELETE /subscriptions/{category_key}` (idempotent cancel — path
  variable snake_case in code, camelCase in OpenAPI, spec 011 precedent).
- `GET /notifications?onlyUnread=true` (default true; fixed most-recent
  limit 50 — Q4; returns `unreadCount` total alongside, so the client can
  also derive count from the list).
- `GET /notifications/unread-count` → `{"unreadCount": N}` (Q5 — cheap
  polling probe).

- `POST /notifications/{notification_id}/read` (idempotent; 404 for
  another tourist's notification — isolation).
- `POST /notifications/read-all`.

Marking sets `read_at` once; re-mark keeps the FIRST read_at (idempotent,
FR-013). Unknown notification id → 404; marking another tourist's → 404
(does not leak existence).

## R7 — Subscription validation (FR-005, RNF06)

**Decision**: PUT validates keys against `settings.resolved_interest_categories()`
(same catalog as profile interests); 422 naming the invalid key (spec 003
precedent). Dedupe via unique constraint + ordered-dict normalization.

## R8 — Emitter hook placement

**Decision**: emission call is the LAST step of each *_create* service,
after `session.flush()` materializes ids (events 008, tourist_spots 007,
gamification 009). Audit records (0011) unchanged; update/remove services
do NOT emit (spec edge case). Update paths of spots/routes/categories are
not emissions — only creation.

## R9 — Migration 0010 contents

**Decision**: single migration creating both tables + unique constraints +
`ix_notifications_tourist_read` + `ix_notification_subscriptions_category`
(category_key, for the match query). Downgrade drops both. No backfill
(nobody has subscribed yet).

## R10 — Performance budget harness (SC-005)

**Decision**: `tests/perf/test_notifications_budget.py` per 013/014
precedent: 1,000 tourists + subscriptions + 100 items' notifications
(chunked inserts), then assert GET list, unread-count, subscriptions read —
all < 2 s. Set-based queries only (FR-020 analog).
