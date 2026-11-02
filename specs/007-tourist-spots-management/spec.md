# Feature Specification: Tourist Spots Management

**Feature Branch**: `007-tourist-spots-management`

**Created**: 2026-11-02

**Status**: Draft

**Input**: User description: "Implementar Gerenciamento de Pontos Turísticos do PassaNorte (backend FastAPI, módulo tourist_spots), protegido por RBAC de administrador (spec 002). Requisitos: RF11 — administrador cadastra ponto turístico com nome, descrição, localização (latitude/longitude) e categoria; RF12 — edição e remoção de ponto turístico; RF13 — associação de cada ponto a uma ou mais categorias pré-definidas (lazer, cultura, gastronomia, natureza, arte, cinema, extensível); RF14 — cadastro de cronograma de dias e horários de funcionamento por ponto; RF15 — status do ponto: aberto ao público, temporariamente fechado ou fechado permanentemente, com filtro por status; RF27 — endpoint público de detalhes do ponto (descrição, categoria, horários, status, eventos associados) consumido pela aplicação Passaporte — incluir campo calculado de links para Google Maps (RNF18). RNF19 — audit logs nas ações administrativas de criação/edição/remoção. Coordenadas validadas como decimais WGS-84. A lista de categorias padrão é configurável (RNF06). Todos os endpoints deste módulo agrupados sob a tag "Tourist Spots" do registro central de tags da spec 006. Critério de aceitação: testes de contrato do CRUD completo (201/200/204/403/404), validação de coordenadas, teste que valida o cronograma de funcionamento por dia/horário, teste de auditoria registrando ação do admin."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Administrator manages tourist spots (Priority: P1)

An administrator of the PassaNorte panel creates, updates and removes
tourist spots of the city. Each spot carries its Portuguese-facing name, a
public description, its exact location (decimal WGS-84 latitude/longitude),
one or more categories and its opening status. Every administrative action
is recorded in the audit log, so a reviewer can trace who created, edited
or removed each spot and when.

**Why this priority**: Without the CRUD there is no curated content for the
Passaporte app at all — this is the foundation the public endpoint and the
future visitation/gamification flows consume. It is also the first
non-trivial consumption of the RBAC model (spec 002) and the audit trail
requirement (RNF19).

**Independent Test**: Fully testable by exercising the CRUD endpoints as an
authenticated administrator (create → read → update → remove) with
contract-level status expectations (201/200/204/403/404) and by inspecting
that an audit record with the administrator identity exists after each
write action.

**Acceptance Scenarios**:

1. **Given** an authenticated administrator, **When** they submit a new
   spot with name, description, WGS-84 coordinates, categories and opening
   schedule, **Then** the spot is created and returned with its
   identifiers, and an audit record of the creation exists referencing that
   administrator.
2. **Given** an existing spot, **When** the administrator edits any of its
   attributes (including categories and schedule), **Then** the result
   returned reflects exactly the new state, and an audit record of the
   edition exists referencing that administrator.
3. **Given** an existing spot, **When** the administrator removes it,
   **Then** the request succeeds (no content), the spot no longer appears
   as available in the administrative listing, and an audit record of the
   removal exists referencing that administrator.
4. **Given** a caller who is not an administrator (unauthenticated, tourist
   or employee session), **When** they attempt any write action (create,
   edit or remove) or the administrative listing, **Then** the system
   refuses the access without exposing spot-management operations.
5. **Given** a spot that does not exist (or already removed), **When** any
   actor requests it for edit, removal or detailed read, **Then** the
   system answers with the standard not-found contract.
6. **Given** a spot submission whose latitude or longitude is outside its
   valid WGS-84 range (e.g. latitude beyond ±90 or longitude beyond ±180),
   **When** it is submitted, **Then** the system rejects the request with
   the standard validation failure contract and nothing is created or
   altered.

---

### User Story 2 - Administrator classifies spots with configurable categories (Priority: P2)

Each tourist spot is associated with one or more categories taken from a
pre-defined catalog (default catalog: lazer, cultura, gastronomia,
natureza, arte, cinema — extensible). The catalog comes from configuration
data, not from hardcoded logic, so adapting the system for another city
means editing the configuration (RNF06). When a spot is created or edited,
the submitted categories are checked against the current catalog.

**Why this priority**: Categories are the classification backbone of the
public detail endpoint and of every future filter/discovery feature;
getting the catalog source right (configurable, extensible) matters more
than the exact CRUD ergonomics, which are covered by Story 1.

**Independent Test**: Testable by creating a spot with a mix of valid and
invalid category keys, by verifying that associations persist on read,
and by confirming that the default catalog used for validation comes from
configuration data.

**Acceptance Scenarios**:

1. **Given** the configured default catalog, **When** the administrator
   creates a spot associating at least one catalog category, **Then** the
   spot is created with those associations and they are visible on every
   subsequent read.
2. **Given** the configured default catalog, **When** any spot submission
   references a category that is not in the catalog, **Then** the system
   rejects the request with the standard validation failure contract and
   the spot is left unchanged.
3. **Given** the configured default catalog, **When** a spot submission
   references zero categories, **Then** the system rejects the request
   (a spot must always belong to at least one category).
4. **Given** the catalog extended by configuration (a new category key
   added to the configuration), **When** a submission references that new
   category, **Then** the association is accepted without any code change.

---

### User Story 3 - Per-spot opening schedule is registered and validated (Priority: P2)

The administrator registers, for each tourist spot, an operating schedule
made of days of the week and one or more opening time intervals for each
day. The schedule is part of the spot payload on create and edit, is
returned on every read (including the public detail endpoint), and is
validated so that impossible schedules cannot become permanent data.

**Why this priority**: The schedule is a hard requirement of the public
content shown to tourists (RF14, RF27) and feeds "is it open now" use
cases later; its validation rules are self-contained and testable
independently of permissions.

**Independent Test**: Testable by submitting schedules that are valid
(one or more well-formed day/time entries) and invalid (unknown weekday,
open time after close time, empty schedule) and comparing accepted/rejected
outcomes.

**Acceptance Scenarios**:

1. **Given** a schedule with known weekdays and time intervals where each
   opening time precedes its closing time, **When** the administrator
   submits it, **Then** it is persisted and returned exactly as registered.
2. **Given** a schedule entry with opening time after (or equal to) closing
   time, **When** it is submitted, **Then** the system rejects it.
3. **Given** a schedule entry with an unknown weekday, **When** it is
   submitted, **Then** the system rejects it.
4. **Given** the same weekday appearing more than once, **When** distinct
   non-overlapping intervals are submitted for it, **Then** all intervals
   are persisted for that day.
5. **Given** the same weekday with overlapping intervals in one
   submission, **When** it is submitted, **Then** the system rejects it so
   the schedule stays unambiguous.
6. **Given** a submission with no schedule entry at all, **When** the
   administrator submits it, **Then** the system rejects it (every spot
   declares at least one scheduled day).

---

### User Story 4 - Status lifecycle with filtering (Priority: P2)

Every spot has an operating status with exactly three values: open to the
public, temporarily closed, or permanently closed. The administrator sets
and changes the status with ordinary edits, and the administrative listing
can be filtered by status so the team can quickly work on closed spots or
review open ones.

**Why this priority**: The status is the semantic the public app relies on
to present or withhold a spot; the filter is the only listing ergonomics
required for daily administration work in this milestone.

**Independent Test**: Testable by creating spots with different statuses
and verifying (a) the listing returns only the requested status when
filtered, (b) the complete listing when unfiltered, and (c) status
transitions via edit are persisted.

**Acceptance Scenarios**:

1. **Given** a default value, **When** a spot is created without an
   explicit status, **Then** it is born "open to the public".
2. **Given** spots in all three statuses, **When** the administrative
   listing is filtered by one specific status, **Then** only spots in that
   status are returned.
3. **Given** spots in all three statuses, **When** the administrative
   listing is requested without a filter, **Then** all spots (any status)
   are returned.
4. **Given** an existing spot "temporarily closed", **When** the
   administrator edits it to "open to the public", **Then** the new status
   is persisted and returned on subsequent reads.

---

### User Story 5 - Public detail endpoint for the Passaporte app (Priority: P3)

The Passaporte mobile application shows to any person (no login) the full
detail of a tourist spot: name, description, categories, opening schedule,
current status, the associated events and a ready-to-use map link computed
from the spot's coordinates (RNF18). A spot that exists but is closed is
still returned — with its status visible — not hidden, so tourists learn
it exists even while closed.

**Why this priority**: It is the consumer-facing value of everything
above, but it depends on Stories 1–3 existing; it can be built and shown
after the management core works.

**Independent Test**: Testable by requesting the public detail of a spot
without any authentication and comparing the returned content, the map
link against the stored coordinates, and the behavior for an unknown
identifier.

**Acceptance Scenarios**:

1. **Given** an existing spot, **When** the detail is requested publicly
   (without credentials), **Then** name, description, categories,
   schedule, status and associated events are all present in the response.
2. **Given** an existing spot with known coordinates, **When** the detail
   is requested, **Then** the response contains a map link to the shared
   map service (Google Maps, RNF18) computed from those coordinates — the
   link is computed on read, never stored.
3. **Given** an unknown (or removed) spot identifier, **When** the detail
   is requested publicly, **Then** the system answers with the standard
   not-found contract.
4. **Given** the public detail of a spot, **When** inspected, **Then**
   the response carries exactly one documentation tag matching this
   module's registry tag of spec 006, together with all other endpoints of
   this module.

### Edge Cases

- What happens when a write request omits a mandatory attribute (name,
  description, coordinates, categories or schedule)? The request is
  rejected with the standard validation failure contract; nothing is
  created or altered.
- What happens when coordinates use an invalid numeric format? The request
  is rejected; only decimal degrees are accepted (no degrees/minutes/
  seconds notation).
- What happens when the spot listing is requested with
  pagination parameters? The listing is paginated so that the panel and
  the app never receive an unbounded payload.
- What happens when two spots share the same name? Duplicate names are
  allowed — coordinates and identifier disambiguate (city-level duplication
  is legitimate, e.g. homonymous plazas).
- What happens when an administrator edits only the schedule of a spot?
  The other attributes remain untouched — edits are partial.
- What happens when an authentication token is expired during an
  administrative action? The standard refusal contract of the auth module
  applies.
- What happens when an event associated to a spot is no longer visible?
  The events collection in the public detail reflects whatever the events
  domain exposes at read time; a spot with no associated events returns an
  empty list, never an error.
- What happens when a category stored on an existing spot is no longer in
  the configuration catalog (renamed or removed from config)? The spot
  keeps returning its stored categories as-is on every read; the catalog
  is revalidated only when that attribute is rewritten via create or edit
  — no startup routine or data migration rewrites stored spots.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST let an administrator create a tourist spot with
  Portuguese-facing name, public description, location as decimal WGS-84
  latitude/longitude, one or more catalog categories and an operating
  schedule (RF11, RF13, RF14).
- **FR-002**: System MUST validate latitude within its WGS-84 valid range
  and longitude within its WGS-84 valid range on every write of the
  location, accepting decimal degrees only (RF11).
- **FR-003**: System MUST allow the administrator to edit any attribute of
  an existing spot, including categories, schedule and status (RF12).
- **FR-004**: System MUST allow the administrator to remove an existing
  spot, after which the spot stops being available for the public detail
  endpoint and the administrative listing (RF12).
- **FR-005**: System MUST restrict every spot-management operation
  (create, edit, remove, administrative listing) to administrators — any
  other caller is refused (RF11-15; RBAC of spec 002).
- **FR-006**: System MUST validate submitted categories against the
  configured catalog, accepting one or more catalog entries and rejecting
  unknown ones or none at all (RF13; catalog configurable per RNF06).
  Associations persist the category keys themselves — validated at write
  time against the configuration catalog, with no catalog database table
  or foreign keys.
- **FR-007**: System MUST validate the operating schedule: known weekday,
  opening time strictly preceding closing time, at least one interval per
  scheduled day, no overlapping intervals for the same day, and at least
  one scheduled day present on every write of the schedule (RF14).
- **FR-008**: System MUST assign the value "open to the public" as the
  default status of a newly created spot (RF15).
- **FR-009**: System MUST expose an administrative listing of spots with
  optional filtering by operating status (RF15).
- **FR-010**: System MUST record a structured audit entry — action, target
  spot, actor identity, timestamp — for every creation, edition and
  removal of a spot (RNF19).
- **FR-011**: System MUST expose a public (unauthenticated) detail endpoint
  of a spot returning name, description, categories, schedule, current
  status and associated events, consumed by the Passaporte app with no
  login (RF27).
- **FR-012**: System MUST include in the public detail a map link to
  Google Maps computed from the spot's coordinates at read time — never
  stored as data (RNF18).
- **FR-013**: System MUST group every endpoint of this module under the
  single central-registry tag "Tourist Spots" of spec 006, with no
  ad-hoc tag strings in route files.
- **FR-014**: System MUST answer every failure path of this module with
  the unified error contract (consistent error code, human-readable
  message, details) — never an ad-hoc error payload.
- **FR-015**: System MUST answer contract-level status expectations: 201
  on successful creation, 200 on successful read/edit, 204 on successful
  removal, 403 on insufficient permissions, 404 on unknown target.
- **FR-016**: System MUST keep administrative listing responses bounded
  (paginated).
- **FR-017**: System MUST allow editing a spot partially: submitting only
  the changed attributes keeps the remaining attributes unchanged.

### Key Entities *(include if feature involves data)*

- **TouristSpot**: a curated point of interest of the city; attributes —
  Portuguese-facing name, public description, decimal WGS-84 latitude and
  longitude, operating status (one of: open to the public / temporarily
  closed / permanently closed); catalog categories persisted as key
  values on the spot, validated against the configuration catalog at
  write time; relationships — owns one operating schedule, associated
  events (read-only association to the events domain).
- **SpotCategory**: NOT a persisted database entity in this feature. An
  entry of the extensible catalog (default: lazer, cultura, gastronomia,
  natureza, arte, cinema); sourced from configuration data, not code;
  used to validate spot submissions (spec 007) and by the tourists'
  interest profile (spec 003 domain, shared catalog source).
- **SpotScheduleEntry**: one day-of-week plus one opening/closing time
  interval; a spot owns zero or more entries forming its schedule. Times
  are pure HH:MM values without timezone, canonically interpreted in the
  city's timezone configured in configuration data (America/Sao_Paulo).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An administrator completes the full lifecycle of one spot
  (create, edit, remove) in under 2 minutes using only the documented
  API operations, with the result of each step reflected in the next read.
- **SC-002**: 100% of attempts to persist a location outside the WGS-84
  valid ranges are rejected before any data is stored (measured by the
  contract tests for coordinate validation).
- **SC-003**: 100% of impossible schedules (unknown weekday, opening time
  not preceding closing time, overlapping same-day intervals, empty
  schedule) are rejected before any data is stored.
- **SC-004**: 100% of creation, edition and removal actions performed by an
  administrator produce exactly one audit entry identifying the actor;
  actions by non-administrators produce zero audit entries because they
  are refused.
- **SC-005**: A consumer of the public detail endpoint (no credentials)
  receives, in under 1 second, every element required by the contract —
  description, categories, schedule, status, associated events and the
  computed map link — for an existing spot.
- **SC-006**: Non-administrative actors (unauthenticated, tourist,
  employee) are refused on 100% of management operations with the
  expected refusal contract.
- **SC-007**: The full contract suite of this module (CRUD status
  expectations 201/200/204/403/404, coordinate validation, schedule
  validation, status filtering, public detail content, audit verification)
  passes as the acceptance gate of the feature.

## Assumptions

- **Category catalog source**: the default catalog (lazer, cultura,
  gastronomia, natureza, arte, cinema) lives in configuration data,
  consistent with the portability principle — extension to new categories
  happens by editing configuration, not by building a category-management
  API in this milestone (YAGNI; the catalog is the data source shared with
  spec 003's interest categories).
- **Removal semantics**: removal hides the spot from listing and the
  public detail while preserving the audit trail of the removal; physical
  data disposal is out of scope for this milestone.
- **Map link format**: the public detail uses the standard Google Maps
  universal link composed of the spot's latitude/longitude; no API key is
  required for the link itself.
- **Events association**: the public detail surfaces associated events
  through the events domain's public service interface; until the events
  module ships its data (later milestone), the field is an (empty)
  collection, never an error, and this module never writes to events
  tables.
- **Schedule model**: each scheduled day carries one or more non-over
  lapping open/close intervals; days not in the schedule are interpreted
  as closed days; the schedule is always non-empty — a spot is required to
  declare at least one scheduled day, even if its current status is
  "temporarily closed" (the schedule describes its normal operation, not
  its current state).
- **Public reachability of "permanently closed" spots**: the public detail
  still responds for permanently closed spots (status visible), since the
  removal operation — not the status — is what takes a spot off the app.
- **Category representation per audience**: administrative payloads carry
  canonical category keys (English identifiers, project standard); the
  public detail resolves each stored key to its `{key, label}` pair at
  read time from the same configured catalog, so the unauthenticated
  Passaporte consumer receives Portuguese display content without needing
  a second (auth-gated) categories endpoint; a stored key no longer in the
  catalog shows `label: null` (consistent with the stored-data pass-through).
- **Locale of content**: spot names and descriptions are user-facing
  Portuguese content entered by administrators; identifiers, fields and
  API paths remain English, per the project standard.

## Clarifications

### Session 2026-11-02

- Q: How should a spot's categories be persisted, given the catalog lives
  in configuration data (config/location.json) and not in code? → A:
  Validate against the configuration catalog and persist the category
  keys (canonical catalog identifiers) directly associated with the
  spot; no catalog database table and
  no foreign keys to one (simplest catalog-as-data approach per YAGNI and
  the portability principle).
- Q: What happens to existing spots whose categories leave the catalog
  when the configuration catalog changes (category renamed or removed
  from config/location.json)? → A: Existing data is returned as stored;
  catalog validation applies only when that attribute is written (create/
  update). No data migration or startup routine repairs them — editing
  the spot naturally triggers revalidation.
- Q: In which timezone are the schedule's opening/closing times
  interpreted (today for validation and storage, later for "open now"
  checks)? → A: Pure times (HH:MM, no timezone attached), canonically
  interpreted in the city's timezone, fixed in configuration
  (America/Sao_Paulo) — the same schedule behaves identically on any
  server or environment.