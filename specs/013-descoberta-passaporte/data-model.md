# Data Model: Passaporte Discovery (013)

**Date**: 2026-11-03 | **Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

## Overview

This feature adds **no new persistent entity**. It computes over three
existing owner-domain tables through explicit public service seams
(research R5) and produces **computed, transient views** (feed items,
navigation links). The only schema change is one partial index.

## Referenced existing tables (read-only)

### `tourist_spots` (owner: `tourist_spots`, migration 0004)

Filters used by the feed: `removed_at IS NULL` and
`status != 'permanently_closed'` (FR-007 — temporarily closed included
with visible status). Fields consumed: `id`, `name`, `description`,
`latitude`, `longitude`, `status`.

**Change**: new partial index
`ix_tourist_spot_status_active (status) WHERE removed_at IS NULL`
(migration `20261103_0008_spot_discovery_index.py`).

### `tourist_spot_categories` (owner: `tourist_spots`, migration 0004)

`spot_id`, `category_key` (indexed) — the interest-match input side.

### `tourist_interests` (owner: `tourists`, migration 0003)

`tourist_id`, `category_key`, unique `(tourist_id, category_key)` — the
interest-match input side. Read via the `tourists` public service seam;
never touched directly from `tourist_spots`.

### `events` (owner: `events`, migration 0005)

`spot_id` (indexed, CASCADE), `occurrence_date` (indexed `Date`) — the
future-event boost input. Read via the new `events` public seam
`list_upcoming_event_dates(session, from_date)`; past events never enter
the computation.

## Computed, transient views (not persisted)

### DiscoveryFeedItem

| Field (wire, camelCase) | Python | Source |
|---|---|---|
| `id` | `int` | tourist_spots |
| `name` | `str` | tourist_spots |
| `description` | `str` | tourist_spots |
| `latitude` / `longitude` | `float` | tourist_spots |
| `status` | `str` | tourist_spots (visible even when temporarily closed) |
| `categories` | `list[CategoryView]` (key + label) | tourist_spots ∪ location.json labels |
| `relevanceScore` | `float` | computed — research R2 |
| `upcomingEventDate` | `iso date \| null` | events seam (nearest future) |
| `mapLink` | `str` | configured provider builder |

Ordering: `relevanceScore` desc → `name` (case-insensitive) asc → `id` asc.
Envelope adds `page`, `pageSize`, `totalItems`, `totalPages`.

### NavigationLinks

| Field (wire, camelCase) | Python | Source |
|---|---|---|
| `origin` | `{latitude, longitude}` | provided position, else the spot's own location (FR-010 fallback, self-documenting) |
| `mapLink` | `str` | configured provider builder |
| `uberLink` | `str` | uber builder (research R4) |
| `ninetyNineLink` | `str` | 99 builder (research R4) |

Key naming note: a JSON key cannot start with a digit, so the 99 link is
carried as `ninetyNineLink` (camelCase-consistent, no acronym — ApiModel
aliasing).

### Additive extension to the existing public spot detail (spec 007)

`GET /api/v1/tourist-spots/{id}` gains `uberLink` and `ninetyNineLink`
(origin = the spot's own coordinates). `map_link` is preserved unchanged —
backwards compatible; existing 007 contract tests continue to pass.

## Validation rules (FR-014)

- Request coordinates: `latitude ∈ [-90, 90]`, `longitude ∈ [-180, 180]`,
  decimal WGS-84, optional in both endpoints (absence ⇒ neutral proximity /
  fallback origin — FR-005, FR-010).
- Out-of-range or type-invalid coordinates rejected by the request model
  with the unified 422 `ApiError` before any scoring.

## Settings (policy, not data — constitution VI)

All discovery policy values are `Settings` fields (`.env`-overridable),
validated at startup:

| Setting | Default | Meaning |
|---|---|---|
| `discovery_w_proximity` | `0.5` | dominant weight (clarification Q1) |
| `discovery_w_interest` | `0.35` | second weight |
| `discovery_w_event` | `0.15` | minor weight |
| `discovery_max_distance_km` | `10` | proximity saturation |
| `discovery_event_window_days` | `30` | event-boost saturation window |
| `discovery_event_boost_min` | `0.25` | floor for events beyond the window |
| `discovery_neutral_proximity` | `0.5` | constant factor without position |
| `discovery_map_provider` | `google_maps` | `google_maps` \| `osm` |

Weights are validated positive and summing to 1.

## State transitions

None — the feature introduces no lifecycle; spot operating status (open /
temporarily closed / permanently closed) remains the spec 007 lifecycle and
only filters visibility as documented above.

## Relationships summary (for this feature's reads)

```text
tourist (auth, spec 002/003) --1:N--> tourist_interests (category_key*)  ← tourists seam
tourist_spot  --1:N--> tourist_spot_categories (category_key*)
tourist_spot  --1:N--> events (occurrence_date, filtered ≥ today)        ← events seam
feed item = tourist_spot + computed relevanceScore + links (transient)
```