# Data Model: Tourist Spots Management (feature 007)

Module-owned data — the `tourist_spots` domain owns these three tables
exclusively; no other module reads or writes them (constitution rule 4).
Events never gain spot-owned rows: the association is read-only and lives
in the events domain (resolved at read time, R8).

## 1. Entities (conceptual)

### TouristSpot (table `tourist_spots`)

| Field | Type | Rules |
|---|---|---|
| `id` | int PK | system-generated |
| `name` | String(200) | Portuguese-facing, 1..200 chars (user content); duplicates allowed (spec edge case) |
| `description` | String(2000) | Portuguese-facing, 1..2000 chars |
| `latitude` | Float | decimal WGS-84 degrees, −90.0 ≤ v ≤ 90.0, validated at every write |
| `longitude` | Float | decimal WGS-84 degrees, −180.0 ≤ v ≤ 180.0 |
| `status` | String(20) | exactly one of `open` (default) / `temporarilyClosed` / `permanentlyClosed` (R9) |
| `removed_at` | datetime UTC, nullable | NULL = active; non-NULL = removed (soft delete, R6) — indexed |
| `created_at` / `updated_at` | datetime UTC | audit timestamps (employees precedent) |

- No uniqueness beyond PK: homonymous spots are legitimate (spec edge case).
- Relations: owns many `tourist_spot_categories` rows and many
  `tourist_spot_schedule_entries` rows (`cascade="all, delete-orphan"`).

### SpotCatalogEntry — NOT a table

The catalog is configuration data only (`interest_categories` in
`config/location.json`, extended with leisure/art/cinema — R1). Spots
persist category **keys** (`tourist_spot_categories.category_key`);
validation against the configured catalog happens at write time only
(R3/R13). Reads return stored keys verbatim, even if the config later
drops them (clarification Q2).

### SpotCategory (table `tourist_spot_categories`)

| Field | Type | Rules |
|---|---|---|
| `id` | int PK | system-generated |
| `spot_id` | FK → tourist_spots.id | cascade delete |
| `category_key` | String(50), indexed | canonical English key validated against config at write; ≥1 per spot on every write of the attribute; duplicates within one submission rejected (422) |

Unique constraint `(spot_id, category_key)` — defense in depth. In-
submission duplicates are rejected with 422 at validation time; nothing is
normalized before storage.

### SpotScheduleEntry (table `tourist_spot_schedule_entries`)

| Field | Type | Rules |
|---|---|---|
| `id` | int PK | system-generated |
| `spot_id` | FK → tourist_spots.id | cascade delete |
| `weekday` | SmallInteger | ISO-8601 day number: 1 = monday … 7 = sunday (R4); contracted as `"monday"`… `"sunday"` |
| `opens_at` | Time | pure wall-clock `HH:MM`, city-timezone semantics (R5) |
| `closes_at` | Time | pure wall-clock `HH:MM`; strictly after `opens_at` (R13 schema rule) |

Write rules (all enforced per FR-007): ≥1 entry per write of the
attribute; no two entries for the same `weekday` with strictly
overlapping intervals in one submission (back-to-back intervals —
close == next open — are unambiguous and valid, describing continuous
operation) (R13 service rule); multiple disjoint intervals per day are
valid (US3 scenario 4).

## 2. Table DDL shape (migration `20261102_0004_tourist_spots`)

```text
tourist_spots:
  id INTEGER PK
  name VARCHAR(200) NOT NULL
  description VARCHAR(2000) NOT NULL
  latitude FLOAT NOT NULL
  longitude FLOAT NOT NULL
  status VARCHAR(20) NOT NULL DEFAULT 'open'
  removed_at TIMESTAMP NULL, index
  created_at TIMESTAMP NOT NULL
  updated_at TIMESTAMP NOT NULL

tourist_spot_categories:
  id INTEGER PK
  spot_id INTEGER FK(tourist_spots.id, ON DELETE CASCADE) NOT NULL, indexed
  category_key VARCHAR(50) NOT NULL, indexed
  UNIQUE (spot_id, category_key)

tourist_spot_schedule_entries:
  id INTEGER PK
  spot_id INTEGER FK(tourist_spots.id, ON DELETE CASCADE) NOT NULL, indexed
  weekday SMALLINT NOT NULL   # 1..7, ISO-8601
  opens_at TIME NOT NULL
  closes_at TIME NOT NULL
```

## 3. State transitions

```text
Spot status (any → any via PATCH; FR-003/US4):
  open ──→ temporarilyClosed ──→ open            (ordinary edit)
  any ──→ permanentlyClosed ──→ any              (ordinary edit; no gate)
Create without status ⟹ open (FR-008); create MAY set it explicitly.

Spot lifecycle:
  active (removed_at NULL)
    ├── PATCH ──→ stays active (any change; revalidated if touched: R3)
    └── DELETE ──→ removed (removed_at set; terminal in this milestone)
  removed ⟹ invisible for GET list / GET public detail; act-target ops → 404
```

## 4. Derived values (never stored)

| Value | Source | Rule |
|---|---|---|
| `mapLink` | `latitude`/`longitude` | `https://www.google.com/maps/search/?api=1&query={lat},{lng}` built at read time (R10, FR-012) |
| `events` (public detail) | events domain public service | `list_public_spot_events(session, spot_id)` → `[]` until events ship (R8) |
| `categories` labels (public detail) | config catalog | each stored `key` resolved to `{key, label}` at read time from `resolved_interest_categories()`; orphan key (Q2) → `{key, label: null}` (R3) |
| catalog validity | config | write-time check only (R3) |