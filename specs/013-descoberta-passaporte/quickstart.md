# Quickstart: Passaporte Discovery (013)

**Feature**: [spec.md](spec.md) | **Contracts**: [contracts/tourist-spots-discovery.md](contracts/tourist-spots-discovery.md) | **Data model**: [data-model.md](data-model.md)

End-to-end validation of the discovery surface, from a bootstrapped city to
a tourist's phone-call-equivalent HTTP session.

## 1. Prerequisites

- Python 3.13, project deps installed (`pip install -e ".[dev]"` or the
  project's existing test bootstrap).
- Env essentials respected by the app (spec 002): `DATABASE_URL`,
  `JWT_SECRET`, `SENSITIVE_DATA_KEY` — provided by the test harness, not
  by you.
- Discoverability knobs: defaults come from `Settings`; overrides via
  `.env` (`DISCOVERY_*` keys — see [research.md](research.md) §R2/§R9).

## 2. Seed a discoverable city (test data)

1. Admin creates spots (spec 007 contract): a *gastronomy* spot near the
   city center, a *nature* spot 8 km away, a spot carrying a future event
   (spec 008), and one permanently closed spot as a negative control.
2. A tourist registers (spec 003) and selects interest categories, e.g.
   `["gastronomy", "cinema"]`. A second tourist selects none.

## 3. Run the acceptance flows

```bash
# contract + unit + integration suites (red → green in /speckit-implement)
pytest tests/contract/test_discovery_feed.py      -q   # ordering cases, R8 §R8
pytest tests/contract/test_navigation_links.py    -q   # links + additive detail
pytest tests/unit/test_relevance_score.py         -q   # formula + tie-break
pytest tests/unit/test_navigation_link_builders.py -q  # maps/osm/uber/99 exact
pytest tests/integration/test_discovery_flow.py   -q   # auth + pagination walk
pytest tests/perf/test_feed_budget.py             -q   # SC-006 budget
pytest tests/smoke/test_boundaries.py             -q   # seams stay legal
```

Expected: all green; `tests/test_migrations.py` green with the new
partial index migration in place.

## 4. Manual HTTP session (equivalent of the acceptance scenarios)

With a tourist bearer token (`TOKEN`):

```bash
# 1. Feed with position + interests (US1-AS1: gastronomy spot first)
curl -H "Authorization: Bearer $TOKEN" \
  "localhost:8000/api/v1/tourist-spots/discover?latitude=-22.49&longitude=-45.00&page=1"

# 2. Same, no position — order still deterministic (US1-AS3)
curl -H "Authorization: Bearer $TOKEN" \
  "localhost:8000/api/v1/tourist-spots/discover"

# 3. Repeat #2 — byte-identical `items[].id` order (FR-003/SC-002)

# 4. Navigation links for a spot (US2-AS2: origin echoes request position)
curl -H "Authorization: Bearer $TOKEN" \
  "localhost:8000/api/v1/tourist-spots/12/navigation-links?latitude=-22.4901&longitude=-45.0001"

# 5. Detail still works; now carries uberLink/ninetyNineLink additively
curl -H "Authorization: Bearer $TOKEN" \
  "localhost:8000/api/v1/tourist-spots/12"
```

Expected outcomes: step 1 ranks interest-matching spots ahead (SC-001) and
items carry `relevanceScore`; step 2 has valid deterministic order (SC-002);
step 4 returns `origin` + three ready links with exact destination
coordinates (SC-004); step 5 shows additive fields without breaking the
007 contract; the permanently closed control spot never appears (FR-007);
`Swagger UI` shows both routes grouped under the `Tourist Spots` tag.

## 5. Failure-path probes

```bash
# invalid coordinates → 422 ApiError (FR-014)
curl -H "Authorization: Bearer $TOKEN" \
  "localhost:8000/api/v1/tourist-spots/discover?latitude=999&longitude=-45"

# employee/admin token on the feed → 403 ApiError
# unknown spot link route → 404 resource_not_found
# page beyond last → 200 with empty items[]  (edge case)
```

## 6. Definition of done for the feature

- All suites above green (contract, unit, integration, perf, smoke,
  migrations) — constitution III + Quality Gates.
- `ruff check` clean.
- Boundaries smoke test passes: only public-seam imports cross modules.
- Wire keys camelCase end-to-end; every failure payload is `ApiError`.
- Perf test proves the 1 s / page budget on ~1,000 seeded spots (SC-006).