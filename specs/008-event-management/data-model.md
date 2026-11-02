# Data Model: Tourist Spot Events Management (feature 008)

Dados do módulo `events` exclusivamente. A referência ao ponto é somente
leitura e vive no domínio `events` (FK `spot_id`); nenhum módulo externo
lê ou escreve as linhas de evento diretamente (constituição regra 4).
Sem nenhuma tabela nova fora do domínio.

## 1. Entity (table `events`)

### Event

| Field | Type | Rules |
|---|---|---|
| `id` | int PK | system-generated |
| `spot_id` | int FK → `tourist_spots.id` (`ondelete="CASCADE"`) | indexed; exactly one spot per event; writable only through the events service, which validates existence (404) and non-permanently-closed status (409) against the spot's public service interface |
| `occurrence_date` | Date | calendar date (no time-of-day); past dates accepted (spec assumption); indexed |
| `description` | String(2000) | Portuguese-facing user content, 1..2000 chars |
| `ticket_price_cents` | Integer, no nulls | exact monetary amount in cents (never float — R1); ≥ 0; ≤ 999999999999 cents (contract `max_digits=12`); 0 = free event |
| `created_at` / `updated_at` | datetime UTC | audit timestamps (007 precedent) |

- **No uniqueness beyond PK** — multiple events per spot per date are
  allowed (spec edge case).
- **No soft delete** — removal is physical (hard delete); the cascade
  contract (clarification 2026-11-02) makes events cease to exist together
  with their spot, so no row ever remains unlisted/orphaned (R9).
- Ordered listings: `(occurrence_date, id)` stable order.

### TouristSpot — referenced, not owned

The spot lives in the `tourist_spots` domain (feature 007). `events`
consumes its existence and status **only** through the public service
function `get_active_spot_status` + public constant
`STATUS_PERMANENTLY_CLOSED` (R3). On spot removal (soft delete
`removed_at`), `tourist_spots.remove_spot` calls the events public service
`delete_spot_events(session, spot_id)` — the events domain executes the
hard delete of its own rows (R4, cross-module write via owner service).

## 2. State transitions

| Transition | Trigger | Effect |
|---|---|---|
| (none) → exists | admin `POST /events` on valid spot (exists, ≠ permanentlyClosed) | one audit record `event.create` |
| exists → exists (new state) | admin `PATCH /events/{id}` (≥ 1 field) | full re-validation of target spot (404/409) when spotId changes; one audit record `event.update` |
| exists → (none) | admin `DELETE /events/{id}` | physical row delete; one audit record `event.delete` |
| exists → (none), in batch | `tourist_spots.remove_spot` on a spot with events | `delete_spot_events` hard-deletes the spot's rows in the same transaction; no per-event audit (the action belongs to the spot domain's remove action) |

## 3. Contract ↔ storage mapping

| JSON (camelCase, via `ApiModel`) | Storage | Conversion |
|---|---|---|
| `ticketPrice` | `ticket_price_cents` | service converts `Decimal → cents` on write, `cents → Decimal` on read (R1; unit-tested both directions) |
| `occurrenceDate` | `occurrence_date` | ISO `YYYY-MM-DD` ↔ `datetime.date` |
| `id`, `spotId`, `description` | `id`, `spot_id`, `description` | verbatim |