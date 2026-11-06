---
description: Task list for feature implementation
---

# Tasks: Notificações por Interesse (015-interest-notifications)

**Input**: Design documents from `/specs/015-interest-notifications/`

**Prerequisites**: plan.md (required), spec.md (required for user stories),
research.md, data-model.md, contracts/

**Tests**: REQUIRED — constitution section III (test-first NON-NEGOTIABLE):
every task group writes failing tests before implementation.

**Organization**: grouped by user story (US1 subscriptions, US2 emission by
emitters, US3 delivery/read marking) — all P1.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to
- Include exact file paths in descriptions

## Path Conventions

Modular monolith (repository root): code in `src/passanorte_back/`,
migrations in `migrations/versions/`, tests in `tests/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm the existing scaffold; no project initialization needed
(`notifications` module scaffolds exist; router/tag pre-mounted).

- [x] T001 Verify the notifications scaffold wiring: `MODULE_ROUTERS["notifications"]` exists with tag `Notifications` (`src/passanorte_back/core/routers.py`, `core/tags.py`); scaffold has empty `routes/`, `services/`, `repositories/`, `schemas/` packages; emitter seams exist (`events.services.create_event`, `tourist_spots.services.create_spot`, `gamification.services.create_route`) — record findings, change nothing unless missing.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Migration 0010 (both tables), ORM repositories, text templates
and the tourist_spots category read seam — blocked prerequisites for every
story.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Tests (write first, watch them fail)

- [x] T002 [P] Write failing migration test in `tests/test_migrations.py`: upgrade to head creates `notification_subscriptions` (columns `id`, `tourist_id` FK, `category_key`, `created_at`; unique `(tourist_id, category_key)`; index on `category_key`) and `notifications` (columns `id`, `tourist_id` FK, `item_type`, `item_id`, `title`, `description`, `created_at`, nullable `read_at`; unique `(tourist_id, item_type, item_id)`; index `ix_notifications_tourist_read` on `(tourist_id, read_at)`); downgrade drops both (data-model.md §1–§2, research R1/R9)
- [x] T003 [P] Write failing unit tests for text templates in `tests/unit/test_notification_templates.py`: per-type composition `Novo evento: <name>` / `Novo ponto turístico: <name>` / `Nova rota turística: <name>` with the emitter description truncated to the documented 200-char cap; keys `event|spot|route` validated (422 for unknown type, research R5, Q2)
- [x] T004 [P] Write failing unit tests for the new tourist_spots read seam in `tests/unit/test_categories_for_spots.py` (or extend an existing tourist_spots unit file): `categories_for_spots(session, spot_ids)` returns `dict[int, list[str]]` keyed per spot with all its category keys; empty/unknown ids → no entry (Q3, research R4)

### Implementation

- [x] T005 Create migration `migrations/versions/20261106_0010_notifications.py`: create both tables + the unique constraints and indexes of T002; downgrade drops them (make T002 pass)
- [x] T006 [P] Create repositories in `src/passanorte_back/modules/notifications/repositories/`: `subscriptions.py` (ORM `NotificationSubscription`, `replace_for_tourist`, `keys_for_tourist`, `cancel`, `subscribed_tourist_ids_for_categories` — the set-based DISTINCT match query) and `notifications.py` (ORM `Notification`, `insert_many_dedupe` via `on_conflict_do_nothing`, `list_for_tourist` most-recent + limit + unread filter with total, `count_unread`, `mark_read_idempotent`, `mark_all_read`) — insert-only semantics for notifications (no update/delete paths)
- [x] T007 [P] Implement the tourist_spots public read seam `categories_for_spots(session, *, spot_ids)` in `src/passanorte_back/modules/tourist_spots/services/tourist_spots.py` (export in the module's public interface; make T004 pass)
- [x] T008 Implement text templates in `src/passanorte_back/modules/notifications/services/emission.py`: data-map keyed by item type (`event|spot|route`), `compose_title`, `compose_description` with the 200-char cap, type validation 422 (make T003 pass)

**Checkpoint**: migration applies; repositories and templates exist; no
endpoint or emitter wired yet.

---

## Phase 3: User Story 1 — Turista se inscreve e cancela inscrição (Priority: P1) 🎯 MVP

**Goal**: tourist-exclusive subscription management: read current selection,
replace selection (validated against the city catalog), cancel one key
(idempotent).

**Independent Test**: register tourist → PUT subscriptions → GET → DELETE
one → GET (spec US1).

### Tests (write first, watch them fail)

- [x] T009 [P] [US1] Write failing contract tests in `tests/contract/test_notifications.py::test_subscriptions_contract`: GET/PUT/DELETE shapes per contracts/notifications.md §1 (`categoryKeys` camelCase); PUT replace semantics; idempotent repeat; catalog-invalid key → 422 naming it; DELETE non-subscribed valid key → 200; anonymous → 401; admin/employee/tourist tokens → 403 (FR-001/FR-004/FR-005/FR-006, RF03)
- [x] T010 [P] [US1] Write failing integration test in `tests/integration/test_notifications_flow.py::test_subscribe_and_cancel`: register tourist via API → subscribe ["gastronomy","nature"] → cancel "nature" → re-read shows only "gastronomy"; re-subscribe idempotent; profile interests untouched by subscription (Q1 independence — FR-007)

### Implementation

- [x] T011 [US1] Implement `src/passanorte_back/modules/notifications/services/subscriptions.py`: `replace_subscriptions` (catalog validation 422 naming invalid key, ordered dedupe, replace whole selection), `keys_for_tourist`, `cancel_subscription` (idempotent) over the T006 repository (data-model.md §3)
- [x] T012 [US1] Create `src/passanorte_back/modules/notifications/schemas/notifications.py` + `routes/subscriptions.py`: DTOs (`SubscriptionsResponse`, `SubscriptionsUpdateRequest` — `ApiModel`, camelCase, strict) and the three tourist routes (GET/PUT/DELETE; path variable `category_key` snake_case in code, camelCase in OpenAPI; failures via unified `ApiError`; NO tag strings in the file) (make T009/T010 pass)

**Checkpoint**: subscriptions channel fully functional and independently
testable — MVP increment.

---

## Phase 4: User Story 2 — Emissão por casamento de categorias (Priority: P1)

**Goal**: creation of a new event/spot/route generates one notification per
subscribed tourist matching the item's categories; best-effort (never
blocks the item creation); dedupe tourist×item.

**Independent Test**: tourist subscribed to 'gastronomia' → admin creates
each item type with 'gastronomia' (plus a no-match item) → exactly one
notification for the matched items (spec US2, acceptance criterion).

### Tests (write first, watch them fail)

- [x] T013 [P] [US2] Write failing integration tests in `tests/integration/test_notification_emission.py`: (a) subscribed tourist receives notification after admin creates a SPOT with 'gastronomia' and NOT one with only 'natureza'; (b) EVENT creation inherits the target spot's categories (research R4); (c) ROUTE creation matches the union of its spots' categories and a category-less route emits nothing; (d) tourist matching in 2 categories of one item receives exactly ONE notification (FR-009 dedupe); (e) zero-matching item emits nothing and creation still succeeds; (f) emission failure (stubbed insert error) does NOT fail the item creation and logs a structured error (FR-011, research R2)
- [x] T014 [P] [US2] Write failing contract-test addition in `tests/contract/test_notifications.py::test_emission_seam_contract` (direct service call): `create_interest_notification` returns the notified count; unknown `item_type` → 422; duplicate emission for the same tourist×item is a no-op (dedupe — research R3)

### Implementation

- [x] T015 [US2] Implement the PUBLIC seam `create_interest_notification(session, *, item_type, item_id, item_name, item_description, category_keys)` in `src/passanorte_back/modules/notifications/services/emission.py`: set-based match via `subscribed_tourist_ids_for_categories`, text via templates (T008), bulk insert dedupe `on_conflict_do_nothing`, ALL inside `session.begin_nested()` with failure → savepoint rollback + structured error log + count 0 (FR-008/FR-009/FR-011, research R2/R3; make T014 pass)
- [x] T016 [US2] Wire the emission hook in `src/passanorte_back/modules/tourist_spots/services/tourist_spots.py::create_spot`: pass its own `payload.categories` after flush (research R8)
- [x] T017 [US2] Wire the emission hook in `src/passanorte_back/modules/events/services/events.py::create_event`: read the target spot's categories via the public seam `categories_for_spots` (T007) and emit after flush (research R4)
- [x] T018 [US2] Wire the emission hook in `src/passanorte_back/modules/gamification/services/gamification.py::create_route`: union of `categories_for_spots` over the route's spot ids; empty/absent categories → no emission call (Q3, research R4; make T013 pass)

**Checkpoint**: emission chain works through all three emitters end to end;
item creation proven resilient to emission failure.

---

## Phase 5: User Story 3 — Consulta e marcação como lida (Priority: P1)

**Goal**: tourist delivery: unread list (default) / full history, unread
count probe, mark one as read (idempotent, 404 foreign), mark all.

**Independent Test**: with notifications issued (via US2 seam), poll list +
count, mark one then all, re-poll (spec US3, acceptance criterion).

### Tests (write first, watch them fail)

- [x] T019 [P] [US3] Write failing contract tests in `tests/contract/test_notifications.py::test_delivery_contract`: GET `?onlyUnread=true` default shape per contracts/notifications.md §2 (camelCase `itemType`/`itemId`/`createdAt`/`readAt` + `unreadCount` total); `onlyUnread=false` includes read ones; fixed most-recent ordering; unread-count endpoint; POST read idempotent (first `readAt` kept); POST read foreign/unknown id → 404; read-all → zero; anonymous → 401; staff → 403 (FR-012/FR-013/FR-013a, Q4/Q5)
- [x] T020 [P] [US3] Write failing integration test in `tests/integration/test_notifications_flow.py::test_delivery_and_unsubscribe_stop`: full lifecycle — subscribe, emit via items, read one, mark all, unsubscribe → next item does NOT notify but history remains (SC-003/SC-004, edge cases)

### Implementation

- [x] T021 [US3] Implement `src/passanorte_back/modules/notifications/services/delivery.py`: `list_notifications` (most-recent + fixed 50 limit + unread total regardless of filter), `count_unread`, `mark_read` (idempotent first-instant; foreign/unknown → None), `mark_all_read` over the T006 repository (data-model.md §5)
- [x] T022 [US3] Extend `src/passanorte_back/modules/notifications/schemas/notifications.py` + create `src/passanorte_back/modules/notifications/routes/notifications.py`: `NotificationsResponse`/`NotificationView`/`UnreadCountResponse` DTOs and the four routes (GET list, GET unread-count, POST read, POST read-all) (make T019/T020 pass)

**Checkpoint**: the whole RF37 loop (subscribe → emit → poll → read) works
end to end.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: spec-level acceptance criteria and repo-wide gates.

- [x] T023 [P] Write the performance budget for SC-005 in `tests/perf/test_notifications_budget.py`: 1,000 tourists with subscriptions, 100 items' notifications seeded in bulk (chunked inserts — SQLite per-statement bind limit); GET list, unread-count and subscriptions reads each answer below 2 s with set-based SQL (FR-020 analog)
- [x] T024 [P] Write the OpenAPI single-tag test addition in `tests/contract/test_notifications.py::test_openapi_single_notifications_tag`: all 7 notification paths listed under the single `Notifications` tag (FR-002)
- [x] T025 Run `ruff check && ruff format` until clean; docstrings (English) in every new file; confirm `modules/tourist_spots/services` exposes ONLY the public seam additions and the notifications module imports no emitter internals (AST gate green) and notifications repository never selects tourist sensitive columns (LGPD)
- [x] T026 Run full `quickstart.md` automated validation block (unit templates + contract + 2 integration + migrations/boundaries/tags + perf budget) as the Definition-of-Done gate

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none — immediate.
- **Foundational (Phase 2)**: blocks every story (T002→T005; T003→T008;
  T004→T007; T006 parallel).
- **US1 (Phase 3)**: needs T006 (subscriptions repo).
- **US2 (Phase 4)**: needs T007 (categories seam) + T008 (templates) +
  T015 (seem) — independent of US1 at code level; integration tests seed
  subscriptions, so running after US1 makes acceptance tests natural.
- **US3 (Phase 5)**: needs T006 (notifications repo); tests need emitted
  notifications from US2 paths.
- **Polish (Phase 6)**: after all stories.

### User Story Dependencies

- US1 → Phase 2 only (subscriptions).
- US2 → Phase 2 + T015; hooks T016–T018 touch three different emitter files
  (parallelizable).
- US3 → Phase 2 + T015 (delivery reads issued notifications).
- Shared files: `schemas/notifications.py` (T012, T022) — assign stories
  sequentially or merge additively.

### Parallel Opportunities

- Tests first: T002/T003/T004 together; T009/T010, T013/T014, T019/T020
  per story.
- After Phase 2: T006/T007/T008 parallel; the three emission hooks
  T016/T017/T018 are three distinct emitter files (parallelizable).
- Polish: T023/T024 parallel; T025–T026 last.

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 + Phase 2 (foundation green).
2. Phase 3 (US1 subscriptions) → validate independently.
3. Stop and demo the subscription channel; emission/delivery untouched.

### Incremental Delivery

Phase 2 → US1 (MVP) → US2 (emission through the three emitters) → US3
(delivery) → Phase 6. Each increment ships RF37 value without breaking the
previous ones.

### Parallel Team Strategy

Assign whole stories per contributor after Phase 2; merge order US1 → US2 →
US3 to avoid conflicts on the shared schema file.

---

## Notes

- Test-first is mandatory (constitution): every "write failing test" task
  must demonstrably fail before its implementation task flips it.
- [P] = different files, no dependency on an incomplete task.
- Emission is best-effort by design (FR-011): the seam never raises out of
  its savepoint; emitters call it unconditionally after flush.
- No push, no pagination, no retention (YAGNI — Q4/Q4-assumptions).
- Commit after every task or logically green group.
