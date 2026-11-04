# Feature Specification: Passaporte Discovery (Ranked Spots & Navigation Links)

**Feature Branch**: `013-descoberta-passaporte`

**Created**: 2026-11-03

**Status**: Draft

**Input**: User description: "Implementar Descoberta no Passaporte do PassaNorte (backend FastAPI, módulos tourist_spots e gamification — endpoints públicos autenticados como turista, spec 002/003). Requisitos: RF26 — tela inicial exibe pontos turísticos ordenados por relevância considerando: interesses selecionados pelo turista (match de categorias), proximidade geográfica (distância Haversine a partir da localização atual enviada) e eventos recentes (eventos com data futura/próxima elevam o ponto); documentar a fórmula de score e permitir desempate determinístico; paginado. RF28 — além dos links para Google Maps (spec 007), gerar deep links para Uber e 99 a partir da localização do ponto, e endpoint que, recebendo a posição do turista, devolve os três links prontos (maps/de carro). RNF12 — consultas respondem em tempo hábil para mobile: implementar ordenação de forma consultável (no máximo O(n) por página, com índices apropriados), sem varredura cara por requisição; se necessário, cache configurável simples. RNF18 — suporte Google Maps ou OSM. Todos os endpoints deste módulo agrupados sob as tags de seus módulos (`Tourist Spots`, `Gamification`) do registro central da spec 006. Critério de aceitação: teste de contrato da listagem com ordenação por relevância (casos: usuário com interesses vs. sem interesses, sem posição enviada, com eventos vs. sem); teste dos geradores de deeplink para Google Maps, Uber e 99; teste de performance simples garantindo consulta paginada e ordenada dentro de limite definido na spec."

## Clarifications

### Session 2026-11-03

- Q: Como os três fatores de relevância (interesses, proximidade e eventos) devem ser ponderados no score default da listagem? → A: Proximidade domina quando a posição é enviada; interesses em segundo; eventos como fator menor.
- Q: A tela de descoberta deve exibir pontos turísticos temporariamente fechados, ou apenas pontos plenamente abertos ao público? → A: Incluir temporariamente fechados com o status visível no item do feed; apenas permanentemente fechados são excluídos.
- Q: O aumento de relevância por evento futuro vale para qualquer data futura, ou apenas para eventos em uma janela próxima? → A: Qualquer evento futuro gera acréscimo crescente conforme a data se aproxima, saturando em uma janela configurável (datas fora da janela valem o acréscimo mínimo).
- Q: Esta feature inclui algum endpoint sob a tag Gamification, ou os endpoints ficam exclusivamente sob Tourist Spots? → A: Todos os endpoints desta feature sob a tag Tourist Spots; nenhum endpoint novo sob Gamification nesta feature.
- Q: Qual escala de catálogo de pontos turísticos o teste de performance da listagem (SC-006) deve usar como dataset de referência? → A: ~1.000 pontos (margem realista de crescimento para uma cidade).
- Q: O item do feed de descoberta deve incluir o score de relevância calculado na resposta, ou apenas a lista ordenada sem o valor numérico? → A: Score numérico por item, sem detalhamento dos fatores.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Tourist opens the Passaporte home feed ranked by relevance (Priority: P1)

A tourist opens the initial screen of the Passaporte app and sees tourist
spots ordered by **relevance** — not alphabetically, not arbitrarily. The
system computes a relevance score for each spot from three factors, in the
context of *that* tourist:

1. **Interest match** — how many of the tourist's selected interest
   categories (spec 003) match the spot's associated categories (spec 007).
   A spot sharing the tourist's interests is more relevant than one that
   does not.
2. **Geographic proximity** — the distance between the tourist's current
   position (sent with the request via the same Haversine approach used for
   visitation validation, RNF14) and the spot's location. Closer spots rank
   ahead of farther ones.
3. **Upcoming events** — a spot with at least one event dated in the future
   (spec 008) gets a boost, stronger the closer the event date is. Past
   dates give no boost.

The feed is paginated and the ordering is **stable**: consecutive pages
continue the same ordering with no repeated or skipped spots. Equal scores
are broken by a **deterministic tie-break** rule, so the same request always
yields the same order.

The ranking formula — its three components, their weights and the
tie-break — is explicitly documented and exposed for API consumers as part
of the contract, so the ordering is auditable, not a black box.

**Why this priority**: This is the opening screen of the consumer product —
the first thing every tourist of the app sees. Without it, discovery
degenerates into a raw, unordered list of spots, and RF26 (the highest-value
remaining tourist requirement in this feature) is unmet.

**Independent Test**: Fully testable by exercising only the discovery
listing — seed spots (with and without categories matching a tourist's
interests, with and without upcoming events), authenticate as a tourist, and
verify the response order for the contract cases: tourist with interests vs.
without interests, no position sent, spots with events vs. without.

**Acceptance Scenarios**:

1. **Given** a tourist with selected interest categories and spots whose
   categories do and do not match, **When** they request the discovery feed
   (all other factors equal), **Then** spots matching the tourist's
   interests are ranked ahead of non-matching ones.
2. **Given** a tourist with **no** interests selected, **When** they request
   the feed, **Then** the request succeeds with a valid ranking derived from
   the remaining factors only — the missing interests neither error nor
   skew the ranking towards arbitrary spots.
3. **Given** a request **without** the tourist's current position,
   **When** the feed is computed, **Then** the proximity factor is neutral
   (neither a penalty nor an advantage) and the ranking still reflects
   interests and upcoming events with a deterministic order.
4. **Given** two spots identical in every factor except that one has an
   upcoming event dated next week and the other has none, **When** the feed
   is computed, **Then** the spot with the upcoming event is ranked first;
   a spot whose event dates are all in the past receives **no** boost.
5. **Given** two spots with exactly equal scores, **When** the feed is
   computed repeatedly, **Then** the tie is broken by the documented
   deterministic rule and both requests return the identical order.
6. **Given** more spots than one page can hold, **When** the tourist
   requests page after page, **Then** every spot appears at most once across
   pages, no spot is skipped, and all pages maintain one consistent
   ordering.
7. **Given** a spot marked as permanently closed (spec 007), **When** the
   feed is computed, **Then** the spot does not appear in the discovery
   listing; a temporarily closed spot **is** included and shown with its
   current status visible in the feed item.

---

### User Story 2 - Tourist opens navigation to a spot in Google Maps, Uber or 99 (Priority: P2)

A tourist viewing a spot wants to get there. Beyond the Google Maps link the
spot already carries (spec 007 — RF27), the system now produces **deep links
for Uber and 99** built from the spot's location, so tapping them opens the
respective app/site with the trip pre-filled. Additionally, an endpoint
receives the tourist's current position and returns, for a given spot, all
three links ready to be opened (map directions and ride-hailing with a
pickup), with no extra parameters or assembly needed by the app.

**Why this priority**: Directly supports getting tourists to physical spots
(RF28) but depends on the spots from the feed/detail being available first,
and one spot at a time is less central than the ranked discovery screen.

**Independent Test**: Fully testable with a single spot and a position —
call the link-generation paths and verify each of the three produced
targets (Google Maps, Uber, 99) opens the correct destination/pickup
coordinates.

**Acceptance Scenarios**:

1. **Given** an existing spot, **When** the tourist asks for its navigation
   links, **Then** the response contains three ready-to-open deep links —
   Google Maps directions, Uber and 99 — each pointing to the spot's
   coordinates as destination.
2. **Given** a spot and the tourist's current position, **When** the
   tourist requests the navigation links, **Then** the returned links use
   the provided position as the trip's pickup/reference point and the spot
   as the destination, all three fully formed without client-side assembly.
3. **Given** a request for navigation links **without** the tourist's
   position, **When** the links are generated, **Then** the system falls
   back to a documented default reference (the spot's own location) instead
   of failing, and clearly indicates the origin used.
4. **Given** a nonexistent or invalid spot reference, **When** navigation
   links are requested, **Then** the system responds with the standard
   not-found/validation failure contract.
5. **Given** coordinates within valid WGS-84 decimal ranges, **When** the
   links are built, **Then** the generated targets preserve the exact
   destination coordinates end-to-end (no precision loss or coordinate
   swap between origin/destination).

---

### User Story 3 - Feed navigability under response budget (Priority: P3)

A tourist on a mobile network interacts with the feed: pages load fast
enough to feel responsive (RNF12) even as the spot catalog grows. The
ranking is computed so that serving a page does not depend on expensive,
unbounded work; a simple, **optional and configurable** cache of the ranking
inputs may be applied. The link provider is chosen by configuration —
Google Maps or OpenStreetMap — with no functional change to the tourist
(RNF18).

**Why this priority**: Quality-of-service property of Stories 1–2 rather
than a separate user-visible feature; it gates launch quality but delivers
no new capability alone.

**Independent Test**: Testable by observing the paged, ranked listing under
the acceptance performance test: a paginated ordered query completes within
the budget defined below on a representative dataset.

**Acceptance Scenarios**:

1. **Given** the reference dataset of approximately 1,000 spots, **When**
   the ranked paginated listing is served, **Then** each page responds
   within the performance budget defined for this feature (Success
   Criteria SC-006).
2. **Given** the link provider configuration pointing to either supported
   map provider, **When** map/navigation links are requested, **Then** the
   generated links are valid for the configured provider with no behavioral
   difference for the tourist.

### Edge Cases

- What happens when the tourist has no interests **and** no position is
  sent? The ranking must still be produced from the remaining factors
  (upcoming events plus neutral defaults) with a deterministic order —
  never an error and never an arbitrary/rotating order.
- How does the system handle a spot with only past-dated events? It must
  receive no event boost (a past event must never inflate relevance).
- What happens with invalid coordinates (out of the WGS-84 decimal range)
  in the request? The system must respond with the standard validation
  failure contract before any ranking is computed.
- What happens when a page beyond the last is requested? The system must
  return an empty page (valid, empty result set), not an error.
- What happens when two ties are resolved and the request is repeated
  identically? The order must be bit-for-bit stable (no time-dependent or
  random component may break ties).
- What happens to the relevance ranking when the interest catalog changes
  (categories added or removed, RNF06)? Spots tied to categories no longer
  in the catalog must not break the feeding — they are ranked as
  non-matching.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001** (RF26): System MUST expose, to authenticated tourist sessions,
  a paginated listing of tourist spots ordered by a **relevance score**
  composed of exactly three factors: (a) match between the tourist's
  selected interest categories and the spot's categories; (b) geographic
  proximity measured with the Haversine distance between the provided
  position and the spot's location; (c) future events associated with the
  spot (spec 008) — any future event gives the spot a boost that grows as
  the event date approaches, saturating at a configurable maximum window
  beyond which the minimum boost applies; already-passed events give **no**
  boost.
- **FR-002**: The relevance formula MUST be **single and documented** — its
  components, default weights and normalization exposed as part of the API
  contract documentation — such that the ordering of any given input set can
  be independently re-derived by a reader. Each feed item MUST carry its
  **computed relevance score** as a numeric field (clarified session
  2026-11-03), without a per-factor breakdown.
- **FR-003**: The listing ordering MUST be **deterministically tie-breakable**:
  equal scores are resolved by a fixed, explicitly documented rule (e.g.,
  alphabetical name followed by identifier), never by insertion order,
  current time or randomness.
- **FR-004**: The listing MUST be **paginated**, with a documented default
  page size and a stable continuation of the ordering across pages
  (no duplicates, no omissions).
- **FR-005**: The listing MUST accept requests **without position**: the
  proximity factor is then neutral and does not distort the outcome of the
  other factors.
- **FR-006**: The listing MUST accept tourists **without interests**: the
  interest factor is then neutral and does not distort the outcome of the
  other factors.
- **FR-007**: The discovery listing MUST NOT include spots marked
  **permanently closed**; spots **temporarily closed** MUST be included
  with their current operating status visible in the response; the listing
  MUST NOT break on spots holding categories no longer present in the
  catalog or events that have already passed.
- **FR-008** (RF28): For any existing spot, the system MUST produce deep
  links to **Google Maps, Uber and 99** derived from the spot's location,
  extending the spot detail contract (spec 007).
- **FR-009** (RF28): System MUST expose an endpoint that, receiving the
  tourist's current position and a spot, returns the **three ready-to-open
  links** (map directions + two ride-hailing services) with the provided
  position as pickup/reference and the spot as destination.
- **FR-010**: The ride-hailing/map link generation MUST degrade gracefully
  when the tourist's position is absent: a documented default origin is
  used and clearly communicated in the response, rather than failing.
- **FR-011** (RNF18): Map/navigation links MUST be generated for the map
  provider selected by configuration — Google Maps or OpenStreetMap —
  switching providers by configuration alone, with no change to API shape
  or tourist-visible behavior beyond the link targets.
- **FR-012** (RNF12): The ranked paged listing MUST be served with bounded,
  predictable work per page — no full unmanaged re-ranking of the whole
  catalog per request when the page can be served from ordered data; when
  caching is used, it MUST be simple, **optional and configurable**, and
  the feed correctness (fresh data reflected within a documented, bounded
  delay) MUST not depend on it.
- **FR-013**: All endpoints of this feature MUST be registered under the
  central OpenAPI tag `Tourist Spots` (spec 006); **no** new endpoint is
  exposed under the `Gamification` tag in this feature (Gamification remains
  available in the registry for future features) — and no new tag may be
  created.
- **FR-014**: Coordinate inputs (tourist position) MUST be validated as
  decimal WGS-84 pairs before any computation (consistent with RNF14).

### Key Entities *(include if feature involves data)*

- **Tourist interests** (spec 003, read-only here): the set of interest
  categories selected by the authenticated tourist — one ranking input.
- **Tourist spot** (spec 007, read-only here): name, description, decimal
  WGS-84 location, associated categories, operating status, and the
  navigation links it exposes.
- **Event** (spec 008, read-only here): occurrence date associated to a
  spot — determines the future-event boost factor per spot.
- **Tourist position** (transient, this feature): optional latitude/
  longitude pair sent per request; used for distance and as pickup for
  navigation links. Never persisted in this feature.
- **Navigation links** (computed, this feature): per-spot, per-origin deep
  links to Google Maps, Uber and 99; pure derivations of coordinates, not
  stored state.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With all other factors equal, 100% of spot-category matches
  with a tourist's interests appear ahead of non-matching spots in the
  feed (contract-verified for a tourist with interests and one without).
- **SC-002**: A request without position yields a valid, deterministic
  ranking; the same tourist repeating an identical request receives the
  exact same order every time.
- **SC-003**: For two otherwise-equal spots, the one with an upcoming event
  dated closer ranks higher than the one with a farther event, and both
  rank higher than one without events; spots with only past events rank
  identically to spots with no events.
- **SC-004**: 100% of link requests return three functioning targets
  (Google Maps, Uber, 99) whose destination coordinates equal the spot's
  coordinates exactly; with a position provided, the pickup equals the
  provided position.
- **SC-005**: Across pagination, zero spots repeat and zero spots are
  skipped; concatenating all pages reproduces the full deterministic
  ordering.
- **SC-006** (RNF12): The ranked, paginated listing responds for any single
  page within **1 second** on a reference dataset of approximately
  **1,000 spots** (clarified session 2026-11-03 — the simple performance
  test of the acceptance criteria enforces this budget).
- **SC-007** (RNF18): Switching the configured map provider from Google
  Maps to OpenStreetMap (or vice versa) requires configuration change only
  and keeps every endpoint of this feature at identical status codes and
  response shapes.

## Assumptions

- **Page size and shape**: pagination follows the page-based convention
  already used by the existing listings; default page size of 20 items is
  assumed (final value confirmed during planning).
- **Score weights**: the three relevance factors contribute as a weighted
  combination where, by default, **proximity dominates when a position is
  provided, interest match ranks second, and the upcoming-event boost is a
  minor factor** (clarified session 2026-11-03). Exact numeric weights are
  configuration-defined, not hardcoded, and the dominant/secondary/minor
  hierarchy holds by default. Without a position, interests lead the
  ranking that remains.
- **Distance metric**: Haversine on decimal WGS-84 coordinates — the same
  metric already established for presence validation (RNF14) is reused for
  proximity ranking.
- **Proximity normalization**: when no position is sent, the proximity
  factor takes a fixed neutral value that neither rewards nor punishes any
  spot.
- **Visibility**: the discovery feed and navigation endpoints are consumed
  only by authenticated tourist sessions (spec 002/003); administrators and
  employees are not the target consumers here.
- **Deep link targets**: Uber and 99 deep links are the public, free
  URL/deep-link forms of each service (no paid API, RNF15); Google Maps
  links remain web directions URLs as in spec 007.
- **Default map provider**: Google Maps is the launch default (links
  already exist in spec 007); OSM compatibility is by configuration (RNF18).
- **Fallback origin**: when the tourist's position is absent, navigation
  links use the spot's own coordinates as origin and the response indicates
  the origin used.
- **Cache**: starts disabled/off by default; simple and configurable so it
  can be enabled without re-architecture — and the feature must remain
  correct with it off (Constitution Principle V, YAGNI).
- **Tag assignment**: all endpoints of this feature (ranked listing and
  per-spot navigation links) live under the `Tourist Spots` tag; no
  gamification-facing endpoint is part of this feature (clarified session
  2026-11-03).

## Dependencies

- Spec 002 (auth/JWT) — tourist authentication for all endpoints.
- Spec 003 (tourists + interest categories) — reads the interest selection.
- Spec 007 (tourist spots) — spot catalog, categories, status and map links.
- Spec 008 (events) — event dates feeding the relevance boost.
- Spec 006 (tag registry) — tag `Tourist Spots`.