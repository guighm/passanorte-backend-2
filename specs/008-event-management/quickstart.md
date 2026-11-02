# Quickstart: Tourist Spot Events Management (feature 008)

Validation scenarios proving the feature works end-to-end. Prerequisites
and setup reference shared project infrastructure — this guide never
duplicates implementation details (contracts: [contracts/events.md](contracts/events.md);
data: [data-model.md](data-model.md); source of truth: [spec.md](spec.md)).

## Prerequisites

- Python 3.13 environment of the repository (existing tooling — see repo
  README for venv setup).
- The test suite runs against the fixed synthetic environment in
  `tests/conftest.py` (in-memory SQLite per test, synthetic admin seed,
  audit capture) — no local services or secrets needed.

## Automated gate (primary acceptance)

```bash
pytest tests/contract/test_events.py        # CRUD contract & refusal paths
pytest tests/integration/test_events_lifecycle.py   # end-to-end domain flow
pytest tests/unit/test_events_price.py      # monetary exactness
pytest tests/test_migrations.py             # migrations include the events table
pytest                                      # full suite incl. smoke/boundaries sweeps
```

Expected outcomes (acceptance criteria from spec.md, SC-001..SC-006):

- **Contract suite**: create → 201 with full camelCase body; edit → 200;
  delete → 204; non-admin callers → 403 `authorization_failed`;
  nonexistent spot (create, edit, spotId filter) → 404
  `resource_not_found`; permanently closed spot (create, edit) → 409
  `conflict`; negative/>2dp price, unknown or snake_case keys,
  `startDate > endDate` → 422.
- **Integration suite**: admin login → create spot → create event →
  list by spot → list by date range (incl. combined filter) → edit →
  delete; audit trail shows exactly one record per administrative write
  (`event.create`/`event.update`/`event.delete`); removing the spot makes
  its events vanish from listings and from the public detail embedding.
- **Unit suite**: `15.50 ⇄ 1500` cents round-trip exact; `0` = free;
  >2 decimal places rejected.
- **Full suite**: all pre-existing gates stay green (boundaries AST scan
  across `modules/`, camelCase/strict-input/unified-error contract sweeps,
  tags 1:1 registry check).

## Manual probe (optional, dev API)

With the dev app running (`README` quickstart of the repo):

1. `POST /api/v1/auth/login` as an administrator → bearer token.
2. `POST /api/v1/tourist-spots` → create one open spot; note `id`.
3. `POST /api/v1/events` with that `spotId` → expect 201 and the echoed
   `ticketPrice` identical to the submitted amount.
4. `GET /api/v1/events?spotId={id}` → the event appears.
5. `GET /api/v1/events?startDate=...&endDate=...` → appears when its
   `occurrenceDate` is inside the inclusive range; outside range → empty
   `items`.
6. `GET /api/v1/tourist-spots/{id}` **without** credentials → `events`
   array embeds the event (no second request needed).
7. Mark the spot `permanentlyClosed` via `PATCH /api/v1/tourist-spots/{id}`,
   then attempt another `POST /api/v1/events` on it → `409` with
   `errorCode: "conflict"`.
8. `DELETE` the spot → its events no longer appear in `GET /api/v1/events`
   (cascade clarification) and the (already-removed) spot itself → 404
   publicly.

Nothing in this guide requires new environment variables, services, or
configuration beyond the existing ones.