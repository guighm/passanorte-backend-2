# Research: Tourist Spots Management (feature 007)

All unknowns were resolved from codebase evidence (no external research
needed; the stack is fixed by the constitution and already in use by
features 001–006). Each decision below cites the precedent it follows.

## R1 — Category catalog source and shape

**Decision**: the spot-category catalog is the existing
`interest_categories` list in `config/location.json`
(`Settings.resolved_interest_categories()` — `core/config.py`), extended
with the three missing defaults so the catalog carries exactly: gastronomy,
nature, culture, leisure, art, cinema (labels Gastronomia, Natureza,
Cultura, Lazer, Arte, Cinema). Entries keep the existing `{key, label}`
shape: `key` = canonical English identifier (code identifier, principle
VII), `label` = Portuguese display text (user-facing data, principle VI).

**Rationale**: the spec assumption names `location.json` as the shared
catalog source with spec 003; the reader (`resolved_interest_categories`)
already exists, is validated, and needs zero new code paths. Extending the
JSON is pure data (RNF06) and, by design, automatically widens the
accepted interest keys of spec 003's profile — same catalog, one source of
truth.

**Alternatives considered**:
- A separate `tourist_spot_categories` config key — rejected: two catalogs
  with the same semantic (one shared catalog source per spec assumption,
  Key Entities §SpotCategory), drift risk.
- Category labels as the stored value — rejected: labels are Portuguese
  user content and mutable display data; code stores canonical keys
  (principle VII), matching the tourists-interests contract precedent.

**Public-detail representation (analysis U1)**: the anonymous Passaporte
consumer cannot resolve labels through `GET /tourists/interest-categories`
(auth-gated, spec 003 module) — so the public detail resolves each stored
key to `{key, label}` at read time from the same configured catalog;
orphan keys return `{key, label: null}` (consistent with Q2 pass-through
and the tourists interests read behavior being the only exception to it,
justified by the public contract needing displayable content).

## R2 — Category persistence on the spot

**Decision** (clarification Q1): one association table
`tourist_spot_categories` (`spot_id` FK + `category_key` string) per spot;
no catalog table, no FK to one. Rows carry the raw key; validation happens
at write time against the configured catalog (service layer).

**Rationale**: simplest catalog-as-data model consistent with R1; the
association stays queryable (future filter-by-category without loading
spots) and keeps referential clarity without orphan-prone FKs to a table
the config would have to keep in sync.

**Alternatives considered**:
- A single JSON column on `tourist_spots` — rejected: filtering by
  category (a likely next milestone need) becomes non-indexable; one small
  association table is the precedent-compatible cost.
- Seeded `SpotCategory` table + FK — rejected by spec clarification Q1
  (catalog is configuration, not data).

## R3 — Orphan categories after config change

**Decision** (clarification Q2): stored keys are returned verbatim on
reads; the catalog is re-validated only when the spot's categories are
rewritten (create/PATCH). No startup repair routine (mirrors the tourists
interests read behavior, which silently filters unknown keys — here the
spec demands no filtering, so stored keys pass through).

## R4 — Schedule storage and weekday shape

**Decision**: one table `tourist_spot_schedule_entries` (`spot_id` FK,
`weekday` small integer ISO-8601, monday=1 … sunday=7, `opens_at`/`closes_at`
as `Time`). The JSON contract uses the English day-of-week string
(`"monday"` … `"sunday"`, contract readability for frontends) plus
`"HH:MM"` strings; the mapping is a pure schema-level conversion.

**Rationale**: integer weekday is the canonical comparable form for
overlap checks and sorting; strings in the JSON follow the
API-contract-first principle (fields/paths English, no i18n in the wire
contract). `Time` columns need no timezone; the semantics ride on R5.

**Alternatives considered**: weekday strings in the DB — rejected:
string comparisons for overlap/sort logic are needless cost; both are
trivially convertible either way.

## R5 — Schedule timezone semantics

**Decision** (clarification Q3): `opens_at`/`closes_at` are pure wall-clock
times, canonically interpreted in the city's timezone. The timezone itself
is configuration data: a new `city_timezone` key in `config/location.json`
(default `"America/Sao_Paulo"`), read via a new
`Settings.resolved_city_timezone()` validated with `zoneinfo` (invalid →
`LocationDataError`), with a `CITY_TIMEZONE` env override mirroring
`city_name`/`languages`. It is not consumed by validation in this feature
(schedule entries are dateless) — it fixes the future "open now" semantics
and rejects invalid configuration at startup.

**Rationale**: pure `HH:MM` means the same schedule behaves identically on
a UTC server; making the timezone configuration (not a Python constant)
keeps principle VI intact for another city.

## R6 — Removal semantics (soft delete)

**Decision**: `DELETE /tourist-spots/{id}` is a soft delete — sets
`removed_at` (nullable timestamp). Removed spots leave the administrative
listing (the repository filters `removed_at IS NULL`), return 404 on admin
detail-style operations (get/update/remove target actives only) and on the
public detail — while their audit history stays untouched (spec
assumption; physical disposal out of scope).

**Rationale**: the spec assumption demands hiding while preserving the
audit trail; a nullable timestamp is the minimal reversible state and
matches the "physical data disposal is out of scope" assumption.

## R7 — Endpoint surface and public read path

**Decision**: one resource under the canonical router
(`/api/v1/tourist-spots`, tag `Tourist Spots` from `core/tags.py` via
`MODULE_ROUTERS` — FR-013, no ad-hoc tags):

| Method | Path | Auth | Success |
|---|---|---|---|
| POST | /api/v1/tourist-spots | admin | 201 |
| GET | /api/v1/tourist-spots (filter `status`, paginated) | admin | 200 |
| GET | /api/v1/tourist-spots/{spotId} | **public** | 200 |
| PATCH | /api/v1/tourist-spots/{spotId} | admin | 200 |
| DELETE | /api/v1/tourist-spots/{spotId} | admin | 204 |

The single read path (`GET /{spotId}`) is the public detail (RF27): the
admin panel needs the same payload (plus nothing more, per spec), so a
second admin read endpoint would be duplication (YAGNI). Admin listing
stays admin-only (FR-005); 403 is also delivered on the listing to
employees/tourists/anonymous via `require_admin`, precedent
`employees/routes/management.py`.

**Rationale**: public detail and admin read of one spot have identical
content per the spec's own wording; one route keeps one contract.
Distinguishing marker: no listing is public — only the detail.

## R8 — Public detail and the events seam

**Decision**: the public detail calls the events domain's public service
interface — a new stub `list_public_spot_events(session, spot_id)`
in `modules/events/services/` returning `[]` until the events milestone
ships data (spec assumption: empty collection, never an error). The stub
defines the seam future events work must honor (constitution rule 3: cross
module via public service interface only — same precedent as
`employees` → `auth.services` lazy imports).

**Rationale**: importing a tourist_spots-owned query into events later
would break the seam; defining the events-owned public function now keeps
the boundary direction correct from day one.

## R9 — Status values and transitions

**Decision**: status stored/contracted as the JSON enum strings
`"open"`, `"temporarilyClosed"`, `"permanentlyClosed"` (camelCase
contract, stored verbatim like `employees.status` `"active"`/`"revoked"`).
Any status is editable to any other via PATCH (spec US4 — transitions are
ordinary edits); `"open"` is applied when omitted on create (FR-008).

## R10 — Map link format (RNF18, clarification on FR-012)

**Decision**: `https://www.google.com/maps/search/?api=1&query={lat},{lng}`
computed inside the public-detail response construction from the stored
decimal coordinates (never stored; no API key needed — spec assumption).
Field name `mapLink`. Decimal dot formatting, comma separator
(percent-encoded at serialization).

**Rationale**: universal Google Maps search link works on web and mobile
without keys and accepts decimal WGS-84 directly; matches
`google.com/maps` precedent for "open this location" links.

## R11 — Pagination of the administrative listing (FR-016)

**Decision**: query params `page` (≥1, default 1) and `pageSize`
(1..100, default 20); response `{items, total, page, pageSize}` ordered by
`id` ascending (stable). New precedent for the API (employees listing is
still unpaginated — fixing that is out of scope here).

## R12 — Audit actions (RNF19, FR-010)

**Decision**: `core.audit.record_action` (log-only sink — table
persistence arrives when dashboards need it; interface unchanged):
`tourist_spot.create` / `tourist_spot.update` / `tourist_spot.delete`,
target `tourist-spot:{id}`, `result="success"`, `detail` carrying the
changed-field summary — one record per successful write, exactly matching
SC-004. Refused non-admin actions never reach the service (routes gate via
`require_admin`), so they log nothing — also per SC-004.

## R13 — Validation split (schema vs service)

**Decision**:
- **Schema (Pydantic, 422 at the border)**: field shapes — name/description
  lengths, latitude ∈ [-90, 90], longitude ∈ [-180, 180] (decimal
  degrees; DMS notation is simply not a number here), category list
  min-length 1, weekday in the day-name set, `"HH:MM"` times, opening
  strictly before closing per entry, at least one schedule entry.
- **Service (422 via `invalid-field` failures)**: category keys against
  the configured catalog (config is not importable at schema-definition
  time) and same-day interval overlap checks (pairs within one
  submission).

**Rationale**: matches the tourists module split (schema handles shape,
service handles config-dependent rules) and keeps 422 responses inside the
unified `ApiError` path.

## R14 — Tests map (constitution III — test-first)

- `tests/contract/test_tourist_spots.py`: CRUD statuses
  (201/200/204), 403 for anonymous/tourist/employee on all write paths +
  listing, 404 unknown id (write and public read), coordinate validation,
  category validation (unknown key, empty list), schedule validation
  (weekday, open<close, overlap, empty), status filter, pagination bounds,
  audit capture (caplog on logger `passanorte.audit`), public detail
  content + map link + `events: []`, single-tag OpenAPI assertion.
- `tests/integration/test_tourist_spots_lifecycle.py`: create → filter →
  edit categories/schedule → status changes → remove → public detail 404.
- `tests/unit/test_city_timezone.py`: `resolved_city_timezone` happy path +
  override + invalid key.
- `tests/test_migrations.py` handles the new migration automatically.