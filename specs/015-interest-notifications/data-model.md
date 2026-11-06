# Data Model: Notificações por Interesse (015-interest-notifications)

Owner of the model: `notifications` module. Two new tables (migration 0010);
emitters only call the public seam — their tables are unchanged.

## 1. `notification_subscriptions` (Q1 channel of its own)

| Column        | Type     | Constraints                          | Notes                    |
| ------------- | -------- | ------------------------------------ | ------------------------ |
| `id`          | int      | PK, autoincrement                    |                          |
| `tourist_id`  | int      | NOT NULL, FK `tourists.id`, indexed  | read-only reference      |
| `category_key` | str(100) | NOT NULL                            | cidade config catalog (RNF06) |
| `created_at`  | datetime | NOT NULL, default now(UTC)           |                          |

Unique: **(tourist_id, category_key)** — idempotent subscribe (FR-005).
Index: `(category_key)` serves the emission match query (research R3).

Lifecycle: insert-only + delete (cancel); PUT replaces the tourist's
selection (spec 003 replace-pattern).

## 2. `notifications` (one row per tourist×item received)

| Column        | Type      | Constraints                              | Notes                                  |
| ------------- | --------- | ---------------------------------------- | -------------------------------------- |
| `id`          | int       | PK, autoincrement                        |                                        |
| `tourist_id`  | int       | NOT NULL, FK `tourists.id`               | read-only reference                    |
| `item_type`   | str       | NOT NULL (`event` \| `spot` \| `route`)  | deep-link type (FR-014)                |
| `item_id`     | int       | NOT NULL                                 | deep-link target id                    |
| `title`       | str       | NOT NULL                                 | template-composed (Q2), i18n-ready (FR-015) |
| `description` | str       | NOT NULL                                 | emitter short desc, capped (Q2/R5)     |
| `created_at`  | datetime  | NOT NULL, default now(UTC), indexed      | ordering (most recent)                 |
| `read_at`     | datetime  | nullable                                 | NULL = unread; set once (idempotent)   |

Unique: **(tourist_id, item_type, item_id)** — FR-009 dedupe at the DB
(insert with `on_conflict_do_nothing`, research R2/R3).
Index: `ix_notifications_tourist_read` (`tourist_id`, `read_at`) — unread
list/filter/count (SC-005).

Lifecycle: insert-only (emission), read-state transition
`NULL → read_at` (one-way; marking again keeps the first instant).
No delete/expurgo this phase (Assumptions).

## 3. Public seam signatures (inter-module surface)

```text
notifications.services.emission:
  create_interest_notification(session, *, item_type, item_id, item_name,
                               item_description, category_keys) -> int
  # int = notified count (0 = no match); best-effort savepoint (R2)

notifications.services.subscriptions:
  replace_subscriptions(session, *, tourist_id, category_keys) -> list[str]
  list_subscriptions(session, *, tourist_id) -> list[str]
  cancel_subscription(session, *, tourist_id, category_key) -> list[str]  # idempotent

notifications.services.delivery:
  list_notifications(session, *, tourist_id, only_unread, limit) -> (items, unread_total)
  count_unread(session, *, tourist_id) -> int
  mark_read(session, *, tourist_id, notification_id) -> NotificationView | None
  mark_all_read(session, *, tourist_id) -> int

tourist_spots.services.tourist_spots:            # NEW public read seam (Q3/R4)
  categories_for_spots(session, *, spot_ids) -> dict[int, list[str]]
```

## 4. Existing entities consumed (read-only references)

- `tourists` — owner of subscriptions/notifications (FKs).
- `tourist_spot_categories` — categories of spots; read by the new
  tourist_spots seam for event/route inheritance (Q3/R4).
- Event/spot/route rows — emission inputs, unchanged.

## 5. Derived definitions (glossary)

| Definition            | Rule                                                                 |
| --------------------- | -------------------------------------------------------------------- |
| Interessados do item  | `DISTINCT tourist_id` de `notification_subscriptions` com `category_key` ∈ categorias do item (set-based) |
| Dedupe turista×item   | unique (tourist_id, item_type, item_id); segunda chamada não duplica  |
| Não lida              | `read_at IS NULL`                                                     |
| unreadCount           | `COUNT(*) WHERE tourist_id = :t AND read_at IS NULL`                  |
| Lista                 | `ORDER BY created_at DESC, id DESC LIMIT 50` (Q4), filtro opcional unread |
| Marcar lida           | `SET read_at = COALESCE(read_at, now)` (idempotente, primeira marcação persiste) |
