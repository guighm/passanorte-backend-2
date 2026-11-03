# Phase 0 Research: Geo-Visitation (011-geo-visitation)

Date: 2026-11-03. Every item below was verified against the actual codebase
(not assumed). No `NEEDS CLARIFICATION` remains from the plan's Technical
Context; spec clarifications Q1–Q7 are already encoded in the spec.

## R1 — Haversine implementation

**Decision**: implement `haversine_distance_m(lat1, lng1, lat2, lng2) -> float`
with the standard `math` module, using the IUGG mean Earth radius
`R = 6_371_008.8` meters, and a small `validate_within_radius(distance_m,
radius_m) -> bool` helper (`distance <= radius`, inclusive border per spec
Edge Cases). Unit-test target `tests/unit/test_haversine.py` covers: zero
distance (0.0 m exact), inside, outside, exact border (distance == radius),
antipodes (≈ 2·R, ~12_742 km, rejected), and range sanity (km-scale known
pair).

**Rationale**: RNF14 needs a single well-known formula; the exact cases of
the acceptance criteria are property-testable with `math.radians` alone.
A known-good reference pair to anchor the tests: ~111.19 km between
(lat −22.7, lng −45.0) and (lat −22.7+1°, lng −45.0) (1° of latitude).

**Alternatives considered**:
- `geopy.distance.geodesic` — extra dependency for one formula (rejected:
  YAGNI/constitution V; geodesic accuracy gain is irrelevant at ≤100 m
  radius against GPS urban noise of 5–30 m).
- PostGIS `ST_Distance` — database-side geo (rejected: column type change
  to geography, heavier migration; radius math in session scope is enough
  for one spot per request).
- Spherical law of cosines / equirectangular approximations — less stable
  numerically (cos of small angles near poles) with no benefit.

## R2 — Tolerance radius resolution (per-spot override → global default)

**Decision**: effective radius for a spot =

```text
spot.tolerance_radius_m  if not None  (positive float, meters)
settings.gps_tolerance_radius_m         otherwise (already in core/config.py: float = 100.0)
```

Resolution lives in `visitation/services/geolocation.py`
(`resolve_tolerance_radius_m(spot, settings) -> float`), so it is unit-
testable in isolation. The global default already exists in
`core/config.py` (`gps_tolerance_radius_m: float = 100.0`, validated
`> 0` — verified) and its autouse env-cleaner in `tests/conftest.py`
already covers `GPS_TOLERANCE_RADIUS_M` — no change to core needed.

**Rationale**: matches spec FR-003/Q2 (100 m global default, per-spot
override) with zero new infrastructure. The nullable column keeps existing
spots valid without backfill.

**Alternatives considered**: storing the composed value on the spot row
(denormalizes config; stale after settings change); separate
configuration table (YAGNI).

## R3 — Progress-update seam (RF34) — the spec 009 public interface

**Decision**: visitation calls
`passanorte_back.modules.gamification.services.gamification.register_spot_visit(session, tourist_id=..., tourist_spot_id=...)`
— re-exported via `gamification.services.__all__` (verified), the only
cross-module importable surface. Behavior verified by reading the source:
- validates tourist and active spot; raises `TouristMissingError` /
  `TouristSpotMissingError` (domain exceptions, caller maps to HTTP).
- `gamification_repositories.record_visit` is **insert-or-lookup
  idempotent** per tourist-spot pair (returns `(visit, created)`).
- recalculates every in-progress enrollment of the tourist containing the
  spot, completes at rate 100 exactly once, emits badge + redemption code
  inside the same transaction, returns `list[VisitRouteOutcome(route_id,
  completion_rate, completed)]`.
- its integration test docstring anticipates this feature: "the visitation
  module does not exist yet — spec 010 will call this seam."

**Rationale**: constitution rules 3/5 (owner-side service function, never
direct writes); RF34 semantics already implemented and tested by spec 009;
zero duplicate logic.

**Idempotency wiring (FR-009)**: visitation checks its own `visitations`
table first — the seam is invoked **only when it is the tourist's first
visitation for that spot**. On repeat visits the immutable record is
appended and no seam call happens, satisfying "idempotent progress,
additional visit recorded". Gamification's own ledger is recomputation-
proof by construction (unique pair + rate derived from visits), which is
the cheap backstop for the accepted simple-race policy (Q4).

**Alternatives considered**: calling the seam on every visit and letting
gamification dedupe (works but violates the contract's MUST NOT trigger
new progress update as an explicit call); duplicating enrollment math in
visitation (forbidden by constitution).

## R4 — Transactionality of visitation + progress (edge case policy)

**Decision**: one unit of work. `mark_visitation` runs inside the request
session (`core.db.get_session`); the visitation insert and the seam call
share the same session/transaction, so a failure in the progress update
aborts the whole operation — no visitation row is committed. Client retry
re-runs the same path safely (the spec-seam checks are idempotent).

**Rationale**: edge-case policy in the spec ("operational consistency"
default) with the modular-monolith's single database this becomes trivial:
same session = same transaction. No outbox/queue (constitution rule 6).

**Alternatives considered**: visitation committed then progress retried
async (rejected: rule 6 forbids queues this phase; violates the accepted
consistency policy).

## R5 — Observability of rejected attempts (SC-007)

**Decision**: standard library `logging` on a module logger
(`passanorte_back.modules.visitation`) — `logger.warning("outside_tolerance_radius", extra={...})`
with tourist_id, spot_id, distance_m, effective_radius_m. No log for
accepted visits (Q6: not administrative actions); rejected attempts are
never persisted.

**Rationale**: SC-007 requires a structured trace for diagnosis without
persisting fraud data; `core/audit.py` is scoped to admin actions (RNF19)
and must not be extended (tourist action ≠ administrative).

**Alternatives considered**: persisting rejected attempts (rejected in
Q6); emitting metrics (no metrics infrastructure exists — YAGNI).

## R6 — Data model & migration (`0007_visitation`)

**Decision**: new table `visitations` owned by visitation —
`tourist_id` (indexed read-only reference into `tourists`), `tourist_spot_id`
(indexed read-only reference into `tourist_spots`), `visited_at` (server
UTC), `latitude`/`longitude` (Float, cleartext, Q7). No unique constraint
on the pair (repeat visits are first-class — spec Edge Cases). Also
`op.add_column` of nullable `tolerance_radius_m` (Float) on `tourist_spots`
— a table that module already owns; its admin CRUD schemas gain the
optional field in this same feature so the override is usable.

**Rationale**: spec FR-006/Key Entities; the gamification table
`spot_visits` keeps its own idempotent-ledger semantics untouched (its
uniqueness per pair is gamification's internal rule, not visitation's).

**Alternatives considered**: reusing gamification's `spot_visits` as the
history (rejected: it cannot hold validated coordinates/timestamps per
visit and would couple two domains); unique pair index + additive counter
(rejected: immutable append-only history is the spec's contract).

## R7 — Authentication & tourist resolution

**Decision**: routes use `Depends(require_tourist)` from
`auth.services.security` (verified public dependency; 403 for
admin/employee). For an authenticated tourist, `tourist_id ==
user.account_id` (verified: `tourists.services.tourists.register_tourist`
sets `account_id=tourist.id`); existence is re-validated with the public
`tourists.services.get_tourist_account(session, tourist_id)` — `None` →
404 (`TOURIST_NOT_FOUND`), before any distance math.

**Rationale**: no cross-module private imports; tourists is the owner of
the tourist row.

## R8 — Timestamp semantics

**Decision**: `visited_at` is captured server-side in UTC
(`datetime.now(UTC)`, same pattern as `core`/`tourist_spots` models).
Client sends no clock data (mobile clocks are untrustworthy; RNF14).

## R9 — Error mapping (contract)

**Decision** (fixed by spec FR-004/FR-013 + single `ApiError` payload):

| Condition | HTTP | `errorCode` |
|-----------|------|-------------|
| Non-tourist authenticated (admin/employee) | 403 | `authorization_failed` |
| Spot missing / removed / inactive | 404 | `resource_not_found` |
| Tourist record missing | 404 | `resource_not_found` |
| Coordinates outside WGS-84 range / non-finite | 422 | `validation_error` |
| Valid coordinates, Haversine distance > radius | 409 | `conflict` (unified taxonomy of spec 005 §2 — cause detailed in the message) |
| Spot row without valid coordinates, or effective radius ≤ 0 (unmarkable state) | 409 | `conflict` (synced with contracts/visitation.md §1 — analyze I1) |

All failures flow through `core.error_handlers` (`ApiError`: `errorCode`,
`message`, `details`) — no bespoke payload.

**Alternatives considered**: 422 for out-of-radius (rejected in spec
clarify: distance mismatch is a state conflict, not a syntactic failure).