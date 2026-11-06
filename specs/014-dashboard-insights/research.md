# Research: Dashboard e Insights (014-dashboard-insights)

Phase 0 output. Every decision below resolves a design unknown of the spec
(clarifications Q1–Q6 already recorded in spec.md `## Clarifications`).
Cross-checked against the live codebase (`core/modules.py`, `core/tags.py`,
`core/routers.py`, `auth/services/security.py`, migration log, `config/location.json`).

## R1 — How does the dashboard read other domains' tables without importing their models?

**Decision**: a dedicated read-projection file
(`modules/dashboard/repositories/read_projections.py`) declaring lightweight
SQLAlchemy Core `table()`/`column()` constructs — non-registered, write-free,
no FKs — for `visitations`, `tourist_spots`, `tourists`, `tourist_interests`.
All aggregations run as `select(func.count...)` / `GROUP BY` through the
shared `get_session` session.

**Rationale**: the constitution forbids importing another module's internals
(models, private repositories) and the spec (FR-021) sanctions "own read
queries". `sa.table()` constructs satisfy both: zero imports from other
modules, schema parity guarded by column names + covered by every
integration test. `tourist_spots` even notes "read-only references
(constitution rule 4)" on its FKs — the codebase already anticipates this
pattern.

**Alternatives considered**:
- Import owner-module ORM models — violates the AST boundary gate
  (`tests/smoke/test_boundaries.py`); rejected.
- Owner-module read services for every aggregate (e.g. `visitation.services
  count_visits_by_spot`) — clean seams but forces every owner module to grow
  analytics-specific APIs, bloating four modules for one consumer (YAGNI).
- ETL/denormalized metrics tables — premature; no volume need (SC-006
  volumes are small).

## R2 — How is the access event recorded for "every tourist-authenticated request"?

**Decision**: a dashboard-owned Starlette `BaseHTTPMiddleware`
(`modules/dashboard/services/access_recording.py`), registered from
`main.py` (`register_access_recording(app)` — `main` is the composition
root, exempt in the boundary checker). On each request it peeks the
`Authorization: Bearer` access token via a NEW tiny public seam in
`auth.services` (`decode_tourist_token`, signature+expiry verified, no DB
session check) and inserts one `access_events` row when the claim is a
tourist token. Recording is best-effort (Q6): exceptions are swallowed into
a structured log line; the tourist request still succeeds. Reuses the
existing engine/session factory; commits in its own transaction.

**Rationale**: a middleware is independent of route wiring — it equally
covers Tourist-exclusive routes and public routes consulted with a tourist
token (Q4, option A). It never imports another module's private internals
(only the new public `auth.services` function). Recording inside dependencies
(e.g. `get_current_user`) would miss public endpoints carrying tourist
tokens and would put an INSERT into the hot auth path.

**Alternatives considered**:
- Hook inside `auth.services.get_current_user` — misses public endpoints
  with tourist tokens; rejected.
- Unverified JWT decode — forges metrics; rejected (signature check kept).
- Async/buffered queue — complexity the constitution reserves for
  demonstrated need; Q6 chose best-effort.

## R3 — Storage shape for the access log and the "unique tourists per day" metric

**Decision**: new table `access_events` (migration 0009):

- `id` PK; `tourist_id` FK→`tourists.id` (indexed); `occurred_at` datetime
  UTC (indexed); `day` DATE precomputed with `ZoneInfo(city_timezone)`
  (RNF06) at recording time.
- Indexes: `ix_access_events_day` (`day`), `ix_access_events_tourist_day`
  (`tourist_id`, `day`).

"Turistas únicos por dia" = `COUNT(DISTINCT tourist_id)` per `day` bucket
— one indexed `GROUP BY day`. Period totals aggregate over the same day
column. No per-request dedup mechanism needed (turista×day is derived, not
stored as a unique pair).

**Alternatives considered**:
- Raw `occurred_at` + timezone-correcting SQL (`AT TIME ZONE` /
  `DATE(occurred_at)` in SQLite's local view) — dialect-dependent and
  wrong under UTC-served datetimes; the precomputed `day` column keeps one
  dialect-proof query shape.
- Unique constraint (tourist_id, day) with upsert counting — adds write
  contention on every request for no gain over `COUNT(DISTINCT)`;
  rejected.

## R4 — Windows, anchors and day/month/year granularity

**Decision**: all time logic in
`modules/dashboard/services/metrics.py` computes window bounds with
`ZoneInfo(settings.city_timezone)` (from `config/location.json` /
`CITY_TIMEZONE`):

- Heat map / distributions: optional `startDate`/`endDate`, inclusive both
  ends, `endDate >= startDate` else 422 (`ApiError` via unified handler).
- Access counter: `period=today|week|month` (`week` anchored to city-tz
  Monday→Sunday; `month` = calendar month) or `period=custom` +
  `startDate`+`endDate` required (missing → 422).
- Ranking: `granularity=day|month|year` + `referenceDate` (default: today);
  window bounds computed in city tz (day → reference date; month → its
  1st..last day; year → Jan 1..Dec 31), inclusive.
- `limit` (rank top N): default 5, minimum 1, maximum 100; out of range →
  422.

**Rationale**: matches spec FR-006/009/012/013 and assumptions (server
anchors, inclusive custom range, top N 5/100). City-tz anchoring honors
RNF06 (no hardcoded America/Sao_Paulo in code).

## R5 — Region definition for the heat map (Q2)

**Decision**: optional data block `regions` in `config/location.json`:

```json
{ "regions": [ { "key": "waterfalls", "label": "Cachoeiras",
                 "spots": ["Cachoeira Édem", "Cachoeira do Serra"] } ] }
```

Regions aggregate by spot **name** (data-level, RNF06; spot names are
Portuguese data — constitution). Region marker = centroid of the
constituent spots' coordinates, weight = summed visits. Unknown/unremoved
spot names are skipped (logged, not fatal); `groupBy=region` with no
`regions` in config → 422 clear error (FR-005). Parsing lives in
`services/metrics.py` (unit-tested); no new endpoint for regions.

**Alternatives considered**: geohash grid (not data-driven, less legible to
the manager) and configurable circles (overlap/orphan edge cases) — both
rejected in Q2.

## R6 — Populations and share math for RF09/RF10

**Decision**: population of both distributions = tourists with ≥ 1
visitation in the optional window (Q5-confirmed: same population). Country
share = tourists-per-country / total distinct visitors ≈ sums to 100%
(ROUND to keep 1-decimal tolerance). Interests share = selections per
category key / total selections (a tourist with N interests counts N
times, per spec US5); tourists with zero declared interests don't
contribute. Country "not informed" (empty string) buckets as
`"not informed"` label `Não informado` at the schema layer. Response
carries raw counts + shares; the percentage is computed in SQL
(`ROUND(100.0 * cnt / total, 1)`) — set-based, no Python loops.

## R7 — Which visits count? (soft-removed spots)

**Decision**: aggregations join `visitations` to `tourist_spots` by id only
for label/coordinate retrieval; removed spots (`removed_at IS NOT NULL`)
still contribute their historical visits (spec edge case "dados órfãos")
but show alongside their name; spot status is irrelevant to counting. The
ranking list and heatmap include every spot with ≥1 visit in the window,
removed or not.

## R8 — Migration 0009 contents

**Decision**: single migration `20261106_0009_access_events.py` creating
`access_events` (+ the two indexes of R3). No columns on existing tables;
no data backfill (access metrics only cover requests after deploy —
documented in quickstart). Downgrade drops the table.
