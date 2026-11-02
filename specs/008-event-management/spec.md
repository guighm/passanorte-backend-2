# Feature Specification: Tourist Spot Events Management

**Feature Branch**: `008-event-management`

**Created**: 2026-11-02

**Status**: Draft

**Input**: User description: "Implementar Gerenciamento de Eventos do PassaNorte (backend FastAPI, módulo events), protegido por RBAC de administrador (spec 002). Requisitos: RF16 — administrador cadastra evento associado a um ponto turístico existente, informando data de ocorrência, descrição e preço do ingresso; RF17 — edição e remoção de evento. Regras: evento só referencia ponto não permanentemente fechado (bloqueio com 409); listagem de eventos por ponto e por faixa de datas para o painel; endpoints incluídos na resposta de detalhes do ponto (RF27 da spec 007). RNF19 — audit logs. Preço do ingresso armazenado como valor monetário explícito (necessário depois para o chatbot, RF39). Todos os endpoints deste módulo agrupados sob a tag "Events" do registro central de tags da spec 006. Critério de aceitação: testes de contrato do CRUD (incluindo 404 em ponto inexistente e 409 em ponto permanentemente fechado) e teste de integração criando ponto → criando evento → listando por ponto e por data."

## Clarifications

### Session 2026-11-02

- Q: When an administrator removes a tourist spot that still has registered
  events, what should happen to those events? → A: Cascade delete — the
  events cease to exist with the spot; no orphaned events ever remain.
- Q: For the administrative event listings, should the date-range listing
  also support an optional tourist-spot filter (spot + date range in one
  query)? → A: Combined optional filter — the range listing accepts an
  optional spot filter; both shapes (all spots in range, single spot in
  range) are served by one endpoint.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Administrator manages events for tourist spots (Priority: P1)

An administrator of the PassaNorte panel creates, edits and removes events
associated with existing tourist spots. Each event carries an occurrence
date, a public description and an explicit ticket price. The system only
accepts events pointing at a tourist spot that still exists and is not
permanently closed. Every administrative write action is recorded in the
audit log, so a reviewer can trace who created, edited or removed each
event and when.

**Why this priority**: Events are content shown to tourists in the
Passaporte app (RF27) and their ticket price is a planning input for the
future chatbot (RF39). Without the CRUD there is no event data at all.
It is also the primary enforcement point of the new business rule
"event only on a non-permanently-closed spot".

**Independent Test**: Fully testable by exercising the events CRUD as an
authenticated administrator: create an event on an existing spot, edit it,
remove it, plus refusal paths (non-admin caller → 403; nonexistent spot →
404; permanently closed spot → 409) and audit-record inspection after each
write.

**Acceptance Scenarios**:

1. **Given** an authenticated administrator and an existing spot whose
   status is open or temporarily closed, **When** they submit an event with
   occurrence date, description and ticket price, **Then** the event is
   created, returned with its identifiers and association to that spot, and
   an audit record of the creation exists referencing that administrator.
2. **Given** an existing event, **When** the administrator edits any of its
   attributes (date, description, price, or a different associated spot
   that is also not permanently closed), **Then** the result returned
   reflects exactly the new state, and an audit record of the edition
   exists referencing that administrator.
3. **Given** an existing event, **When** the administrator removes it,
   **Then** the request succeeds with no content, the event no longer
   appears in any listing or detail response, and an audit record of the
   removal exists referencing that administrator.
4. **Given** a caller who is not an administrator (unauthenticated, tourist
   or employee session), **When** they attempt any event write action or
   the administrative event listings, **Then** the system refuses the
   access with the standard forbidden contract.
5. **Given** an event submission targeting a tourist spot identifier that
   does not exist (or whose spot was already removed), **When** the event
   is created or edited onto it, **Then** the system answers with the
   standard not-found contract and nothing is created or altered.
6. **Given** an event submission targeting a spot whose status is
   "permanently closed", **When** the event is created or edited onto it,
   **Then** the system refuses the operation with the standard conflict
   contract (409), exposing an error code that identifies the
   permanently-closed-spot cause, and nothing is created or altered.
7. **Given** an event that does not exist (or was already removed),
   **When** any actor requests it for edit, removal or read, **Then** the
   system answers with the standard not-found contract.
8. **Given** each of the write actions above performed by an
   administrator, **When** the audit log is inspected, **Then** a
   structured audit record exists for the action referencing the acting
   administrator and the affected event (RNF19).

---

### User Story 2 - Events are listed for the panel and embedded in public spot details (Priority: P1)

The panel needs two listing shapes over events: all events of a given
tourist spot, and all events inside a date range (for calendar/planning
views) — the latter optionally narrowed to one spot, so a per-spot
calendar view needs a single query. Independently of the panel, every tourist spot's public detail
response (delivered by spec 007's detail endpoint, RF27) must include the
events associated with that spot — date, description and ticket price — so
the Passaporte app can show them and the future chatbot can use their cost
in itinerary planning (RF39). Only administrators can use the panel
listings; the events embedded in the public detail response are readable
by anyone.

**Why this priority**: Listing is what makes event data usable: the panel
views are the administration surface, and the public embedding is the
reason events exist at all in the product. This story is separable from
Story 1 only in test shape, not in value — both are P1 because either
alone is not a usable feature, but each is independently testable.

**Independent Test**: Testable by seeding one spot with several events on
known dates and asserting: the per-spot listing returns exactly that spot's
events; the date-range listing returns exactly the events inside the range
(bounds inclusive, per current contract); a spot outside any seeded event
returns empty listings; and the public detail response of the spot embeds
its events with date, description and price.

**Acceptance Scenarios**:

1. **Given** an authenticated administrator and a spot with several
   registered events, **When** they list the events of that spot, **Then**
   exactly the events associated with that spot are returned, each with
   date, description, ticket price and identifiers.
2. **Given** an authenticated administrator, **When** they list events by
   a date range (with or without an optional spot filter), **Then** only
   the events whose occurrence date falls inside the range — and, when a
   spot filter is given, only those of the referenced spot — are returned,
   with the range bounds treated as inclusive.
3. **Given** an authenticated administrator, **When** they request a
   date-range listing whose start date is after its end date, **Then** the
   system rejects the request with the standard validation failure
   contract.
4. **Given** any caller (including unauthenticated), **When** they read the
   public detail of a spot, **Then** the response includes the events of
   that spot with occurrence date, description and ticket price.
5. **Given** any caller, **When** they read the public detail of a spot
   that has no events, **Then** the response includes an empty events
   collection (not an error).
6. **Given** a caller who is not an administrator, **When** they attempt
   the panel listings (by spot or by date range), **Then** the system
   refuses the access with the standard forbidden contract.

---

### User Story 3 - Ticket price is an explicit monetary value (Priority: P2)

Every event carries an explicitly stored ticket price: an exact monetary
amount (never a floating-point approximation), with zero expressing a free
event. This value is returned identically by the administrative CRUD, the
panel listings and the public detail embedding, so downstream consumers —
notably the chatbot's cost-aware planning (RF39) — read a single
consistent representation.

**Why this priority**: The price is a hard data-quality requirement
(RF39 depends on it), but it rides on Story 1's CRUD and Story 2's
readings; it adds no new endpoints or journeys by itself.

**Independent Test**: Testable by creating an event with a representative
exact monetary amount (including a free/zero-price event), reading it back
through create response, edit response, listings and the public detail
embedding, and asserting the amount round-trips identically; and by
submitting invalid prices (negative, missing, malformed) and asserting
rejection with the standard validation failure contract.

**Acceptance Scenarios**:

1. **Given** an authenticated administrator, **When** they create an event
   with an exact monetary amount (e.g. "15.50" in the configured
   currency), **Then** the stored and returned value equals the submitted
   amount exactly in every read path (create response, edit response,
   listings, public detail embedding).
2. **Given** an authenticated administrator, **When** they create an event
   with a zero price, **Then** the event is created as a free event and
   the zero is preserved on every read.
3. **Given** any event submission with a negative, missing or malformed
   price, **When** it is submitted, **Then** the system rejects the
   request with the standard validation failure contract.

## Edge Cases

- What happens when a spot is removed while it still has registered
  events? The events lose their referenced spot; per the clarification of
  session 2026-11-02 (FR-014) they are removed with it (cascade delete),
  so no orphaned event remains in any listing or detail response.
- What happens when the administrator edits an event, changing its
  associated spot to one that does not exist or is permanently closed?
  The same rules as creation apply: not-found for a nonexistent spot,
  conflict for a permanently closed one, and the event keeps its previous
  state in both cases.
- What happens when an event's occurrence date is in the past? Accepted:
  the system does not block historical records in this version; the
  date-range listing is the tool to window events in time.
- What happens when a spot's status is edited to "permanently closed"
  while it still has events? Out of scope for this feature: event data
  remains as-is (its embedding in the public detail response follows
  spec 007's visibility rules for that spot's status). This feature's
  conflict rule guards only event creation/edition against
  permanently-closed targets, and it is evaluated at the moment of the
  event write.
- How does the system handle several events of the same spot on the same
  date? Allowed: nothing forbids multiple events per spot per date.
- What happens when the optional spot filter of the date-range listing
  references a tourist spot that does not exist? The system answers with
  the standard not-found contract, mirroring the event-creation rule.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow an administrator to create an event
  associated with an existing tourist spot, providing occurrence date,
  description and ticket price (RF16).
- **FR-002**: System MUST allow an administrator to edit any attribute of
  an existing event, including changing the associated tourist spot
  (RF17).
- **FR-003**: System MUST allow an administrator to remove an existing
  event (RF17).
- **FR-004**: System MUST reject event creation and edition whose target
  tourist spot does not exist, with the standard not-found contract.
- **FR-005**: System MUST reject event creation and edition whose target
  tourist spot is permanently closed, with the standard conflict contract
  (409) and an error code identifying the cause.
- **FR-006**: System MUST refuse every event-management operation (create,
  edit, remove, panel listings) to callers that are not administrators,
  with the standard forbidden contract (RBAC, spec 002).
- **FR-007**: System MUST provide an authenticated administrative listing
  of the events of a given tourist spot.
- **FR-008**: System MUST provide an authenticated administrative listing
  of events filtered by an occurrence-date range, treating the range
  bounds as inclusive, and the range listing MUST optionally accept a
  tourist-spot filter, so that a single endpoint serves both "all events
  in a range" and "one spot's events in a range".
- **FR-009**: System MUST reject a date-range listing whose start date is
  after its end date, with the standard validation failure contract.
- **FR-010**: System MUST include, in the public detail response of a
  tourist spot (RF27, spec 007), the events associated with that spot —
  occurrence date, description and ticket price — readable by any caller.
- **FR-011**: System MUST store the ticket price as an exact monetary
  amount (no floating-point representation), accepting zero for free
  events and rejecting negative amounts, and MUST return the identical
  value on every read path (RF39 dependency).
- **FR-012**: System MUST record a structured audit log entry for every
  administrative event write action (creation, edition, removal),
  referencing the acting administrator and the affected event (RNF19).
- **FR-013**: System MUST expose all event endpoints grouped under the
  canonical "Events" tag of the central OpenAPI tag registry (spec 006),
  with no tag strings written in route files.
- **FR-014**: System MUST NOT allow orphaned events: when its associated
  tourist spot is removed, its events are removed with it (cascade
  delete) through the tourist spots module's service interface — no
  orphaned event ever appears in any listing or public detail response.

### Key Entities *(include if feature involves data)*

- **Event**: A cultural/scheduled occurrence attached to exactly one
  tourist spot. Attributes: occurrence date (calendar date), public
  description (Portuguese-facing content), ticket price (explicit
  monetary amount, zero = free), and its association to the tourist spot.
  Belongs to the `events` domain module; references a spot only by its
  identifier through the spot module's service interface.
- **Tourist Spot** (existing, spec 007): The referenced entity. Its
  existence and non-permanently-closed status are prerequisites for any
  event pointing at it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An administrator can complete the full event lifecycle
  (create → edit → list by spot → list by date range → remove) through
  the API, with every step answering as fast as the comparable
  tourist-spot listing of spec 007 (RNF11 simple-query budget).
- **SC-002**: 100% of event submissions referencing a nonexistent spot
  receive the not-found contract and 100% referencing a permanently
  closed spot receive the conflict contract — verified without any
  partial write occurring.
- **SC-003**: The public detail response of every tourist spot embeds that
  spot's events (date, description, price) with no additional request
  needed by the Passaporte app.
- **SC-004**: Every administrative event write action produces
  exactly one audit record referencing the acting administrator —
  verifiable by counting audit records against performed actions.
- **SC-005**: A ticket price submitted once round-trips identically (same
  exact monetary value) through create response, edit response, both panel
  listings and the public detail embedding.
- **SC-006**: All contract tests of the events CRUD (including the 403
  non-admin refusals, 404 nonexistent-spot and 409 permanently-closed-spot
  paths) and the end-to-end integration flow (create spot → create event →
  list by spot → list by date range) pass as acceptance.

## Assumptions

- Only administrators authenticate against event-management endpoints;
  employees and tourists never manage events (aligned with spec 002 RBAC
  and RF16/RF17 actor).
- Removing a tourist spot removes its associated events with it (events
  have no meaning without the spot; confirmed via clarification session
  2026-11-02). The cross-module write is mediated by the tourist spots
  module's service interface, per the modular-monolith constitution.
- Occurrence date is a calendar date (no time-of-day component) for this
  version; scheduling detail beyond the date is out of scope.
- Events with past occurrence dates are accepted and listed — no
  automatic hiding or purge in this version.
- Multiple events per spot on the same date are allowed; no uniqueness
  constraint applies.
- Administrative listings are not paginated in this version: the volume of
  events for one city panel makes full listings practical; pagination is
  deferred until real need is demonstrated (constitution YAGNI).
- The optional spot filter of the date-range listing uses the same
  not-found contract as other spot references (nonexistent spot →
  standard not-found).
- The ticket price uses the system's configured currency context; the spec
  fixes only the exactness and non-negativity requirements, not the
  currency itself (RNF06 portability).
- The events module is registered as the canonical `events` domain module
  (constitution `DOMAIN_MODULES`) and communicates with the tourist spots
  module exclusively through its public service interface.