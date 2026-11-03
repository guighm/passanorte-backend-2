# Feature Specification: Tourist Routes and Gamification

**Feature Branch**: `009-tourist-routes-gamification`

**Created**: 2026-11-02

**Status**: Draft

**Input**: User description: "Implementar Rotas Turísticas e Gamificação do PassaNorte (backend FastAPI, módulo gamification), o núcleo do produto (docs/CONSTITUTION.md: monolito modular). Requisitos: RF18 — administrador cadastra rota turística composta por lista de pontos turísticos e brinde associado à conclusão; RF19 — edição e remoção de rota; RF20 — cadastro e controle da quantidade em estoque de cada brinde vinculado a uma rota, com reservas idempotentes (nenhuma concessão sem estoque); RF29 — turista se inscreve em rota disponível, iniciando o acompanhamento de progresso; RF30 — sistema exibe progresso da rota: pontos já visitados e pendentes, com taxa de conclusão calculada; RF34 — ao registrar a visitação de um ponto (entrada vinda via serviço, ainda sem GPS — spec 010 conectará), o sistema atualiza o progresso de TODAS as rotas em andamento do turista que contêm esse ponto; RF35 — ao concluir todos os pontos da rota, o turista recebe insígnia digital de conclusão; RF36 — na conclusão, o sistema gera código de resgate de uso ÚNICO, seguro, não previsível, para retirada do brinde quando o turista desejar e o ponto permitir. Regras de domínio: inscrição duplicada bloqueada (409); código único não reutilizável; estoque nunca fica negativo; remoção de rota preserva histórico de turistas ativos conforme decisão registrada na spec. Expor interface de serviço pública `register_spot_visit(tourist_id, tourist_spot_id)` para o módulo visitation consumir (fronteira de domínio; identificadores em inglês — constituição, Princípio VII). Todos os endpoints deste módulo agrupados sob a tag "Gamification" do registro central de tags da spec 006. Critério de aceitação: teste de integração completo — inscrever → visita de todos os pontos → insígnia emitida → código único gerado → segunda tentativa de uso do código falha; teste de concorrência/estoque insuficiente bloqueando conclusão do resgate."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Administrator manages tourist routes with a completion prize (Priority: P1)

An administrator of the PassaNorte panel registers a tourist route composed
of an ordered list of existing tourist spots (spec 007) and a prize ("brinde")
associated with completing that route. The route has a Portuguese-facing name
and description that will be shown to tourists in the Passaporte app. The
administrator can later edit any attribute of the route (spots list,
texts) or remove the route from circulation — the completion prize,
bound at creation, is managed through stock control. Administrative write
actions are
recorded in the audit log, consistent with how the panel already audits
spot and event management.

**Why this priority**: Routes are the product core — without a route there is
nothing to enroll in, no progress to track and no prize to earn. Prize and
stock are born together with the route because the completion reward (RF36)
only makes sense with a prize attached from day one.

**Independent Test**: Fully testable with the administrative CRUD alone —
create a route referencing real spots and a prize, read it back, edit it,
remove it — verifying contract-level status expectations (201/200/204, 403
for non-administrators, 404/422 for missing or invalid spots) and that an
audit record exists for each write.

**Acceptance Scenarios**:

1. **Given** an authenticated administrator, **When** they create a route with
   a name, description, an ordered list of identifiers of existing tourist
   spots and a prize (name plus initial stock), **Then** the route is created
   and returned with its identifier, the spots list preserved in the submitted
   order and the prize linked to the route.
2. **Given** an existing route, **When** the administrator edits any of its
   attributes, **Then** the response reflects exactly the new state and the
   enrollments already made by tourists remain valid against the updated
   route.
3. **Given** an existing route, **When** the administrator removes it,
   **Then** the request succeeds (no content), the route no longer appears as
   available for listing/enrollment, and — per the removal decision recorded
   in the Requirements section — every tourist already enrolled keeps their
   enrollment, their progress and their pending/earned rewards intact
   (historical record preserved).
4. **Given** a caller who is not an administrator (unauthenticated, tourist or
   employee session), **When** they attempt any route-management action,
   **Then** the system refuses the access with the standard forbidden
   contract.
5. **Given** a route submission that references a nonexistent tourist spot
   (or an empty spots list), **When** it is submitted, **Then** the system
   rejects it with the standard validation failure contract and nothing is
   created.
6. **Given** a request for a route that does not exist (or was removed),
   **When** it is read, edited or removed, **Then** the system answers with
   the standard not-found contract.

---

### User Story 2 - Tourist enrolls in a route and tracks progress (Priority: P1)

A tourist registered in PassaNorte (spec 003) browses the routes available
for enrollment and subscribes to one. From that moment the system tracks the
tourist's progress on that route. When a spot visitation is registered — the
entry point is the public service interface of this module,
`register_spot_visit(tourist_id, tourist_spot_id)`, consumed by the
visitation module (in spec 010; input for this feature comes directly through
the service) — the system updates the progress of **all** of that tourist's
in-progress routes that contain the visited spot, so a single visit can
advance several routes at once. The tourist can see, for each enrolled route,
which spots were already visited, which are pending and the completion rate
(percentage visited / total), the same number a progress bar will render in
the app (RF30).

**Why this priority**: This is the daily loop of the product — enroll, walk,
check progress. It is independently valuable (visible progress) even before
any prize flows, and it exercises the cross-cutting propagation rule (RF34)
that the visitation spec will rely on.

**Independent Test**: Testable end to end through the service and progress
endpoints: enroll a tourist, register visits via `register_spot_visit` and
verify the progress report advances only on routes containing the visited
spots, with the completion rate recomputed each time.

**Acceptance Scenarios**:

1. **Given** a tourist and a route available for enrollment, **When** the
   tourist enrolls, **Then** the enrollment is created with all spots pending,
   zero completion and status "in progress", and the route's progress becomes
   visible in the tourist's tracking.
2. **Given** a tourist already enrolled in a route, **When** they enroll again
   in the same route, **Then** the system blocks the duplicate enrollment with
   the standard conflict contract (409), leaving the original enrollment
   untouched.
3. **Given** a tourist enrolled in two routes that both contain spot X,
   **When** a visit of spot X is registered via `register_spot_visit`,
   **Then** the progress of both routes advances at once in a single call.
4. **Given** a tourist enrolled in routes, **When** they request the progress
   of one of them, **Then** the response lists every spot of the route with
   its visited/pending state and the current completion rate, so the pending
   spots and the progress bar can be rendered directly from it.
5. **Given** a previously visited spot of an enrolled route, **When** a visit
   of the same spot is registered again (by the service or a repeated call),
   **Then** the progress does not regress, duplicate or double-count: the
   completion rate stays the same and the outcome is idempotent.
6. **Given** a visit of a spot that does not belong to any of the tourist's
   in-progress routes, **When** it is registered, **Then** gamification state
   does not change and no route progress is created for it.
7. **Given** a tourist, **When** they attempt to enroll in a route that was
   removed or does not exist, **Then** the system answers with the standard
   not-found contract and no enrollment is created.

---

### User Story 3 - Route completion grants a badge and a single-use redemption code (Priority: P1)

When the last pending spot of a tourist's enrolled route is visited, the
system completes the route for that tourist. Two things happen exactly once:

1. the tourist receives a digital completion badge for the route (RF35);
2. the system generates a redemption code for the route's prize (RF36). The
   code is unique, unguessable and usable exactly once — the tourist shows it
   when they wish to pick up the prize, at a place that allows pickup.

The completion is detected automatically by the same progress-update flow of
Story 2: no administrator or second step is required. The badge and the code
are visible in the tourist's route tracking after completion.

**Why this priority**: This is the gamified payoff — the moment the loop of
enrollment + progress becomes a real reward. It carries the system's
security-relevant rules (unique, non-predictable, non-reusable code) and is
the acceptance target of the full integration test that defines this feature
as done.

**Independent Test**: Testable end to end: enroll a tourist, register visits
of every spot of the route via `register_spot_visit`, observe that exactly
one badge exists and exactly one code is issued, then attempt to use the code
a second time and confirm the system refuses it with the standard conflict
contract.

**Acceptance Scenarios**:

1. **Given** a tourist with one single pending spot in a route, **When** a
   visit of that spot is registered via `register_spot_visit`, **Then** the
   route's status turns to "completed", the completion rate reaches 100 % and
   exactly one completion badge is granted to the tourist for that route.
2. **Given** a completion, **When** the system issues the prize redemption
   code, **Then** the code is presentable to the tourist, is different from
   every other code ever issued (unique), is long/random enough to not be
   guessable from any knowledge of route, tourist or counter, and carries the
   prize of the completed route.
3. **Given** a completed route whose code was already used, **When** the
   tourist (or anyone holding the code) attempts to use it again, **Then** the
   system refuses with the standard conflict contract and no prize concession
   occurs.
4. **Given** a completion already processed (e.g. a last-spot visit registered
   twice or processed concurrently), **When** the completion flow runs,
   **Then** only one badge and only one code exist for that
   tourist-route pair — no duplicated rewards, ever (idempotent completion).
5. **Given** a tourist with an in-progress route, **When** the progress report
   is requested after completion, **Then** the report includes the badge and
   the redemption code availability for the completed route.
6. **Given** a tourist not enrolled in a route, **When** they request its
   progress, **Then** the system answers with the standard not-found
   contract.

---

### User Story 4 - Prize stock is controlled and conceded only against an idempotent reservation (Priority: P2)

The administrator controls the stock quantity of each prize linked to a route
(RF20): it can be adjusted (increased when a new batch arrives, decreased to
correct mistakes) down to zero. A prize concession — the physical handover of
the prize against a redemption code (registered by an authorized staff actor)
— is only possible when stock exists: each accepted concession consumes the
stock unit guaranteed by the idempotent reservation taken at route
completion — or, when no unit could be reserved at completion (stock
exhausted then), takes one directly from replenished stock. Stock is
never negative, and a concession attempt with insufficient stock is blocked
without altering any state, keeping the tourist's code valid and usable once
stock is replenished. A redemption code whose prize stock became zero remains
valid (single-use not yet consumed) but cannot be honored with a concession
until stock exists again.

**Why this priority**: The stock rule protects the physical prize logistics —
no concession without a unit, no negative stock, no double concession under
racing completions. It is decoupled from the progress loop (Stories 2–3)
and can be built and tested after the core loop, but before the feature is
considered done.

**Independent Test**: Testable with a completed route and controlled stock:
complete a route with stock 1, hold the unit, adjust the stock to 0 and
verify the concession is blocked; then adjust the stock and verify a single
concession succeeds, marks the code as used and drops the stock to zero with
no negative values under any repetition.

**Acceptance Scenarios**:

1. **Given** a prize with stock N, **When** the administrator adjusts the
   stock quantity, **Then** the new quantity is stored and returned, and it
   can never go below zero.
2. **Given** a completed route with a valid code, **When** an authorized
   actor registers the concession of the prize against the code, **Then** the
   code is marked as used (exactly once), the stock decreases by exactly one
   and the concession is recorded.
3. **Given** a completed route with a valid code and stock 0, **When** a
   concession is attempted, **Then** it is blocked with the standard conflict
   contract, the code remains unused and valid, and the stock stays at zero
   (never negative).
4. **Given** two tourists completing the same route concurrently while its
   prize stock holds a single unit, **When** both idempotent reservations
   resolve, **Then** exactly one completion holds a reservation and the other
   concludes without stock concession rights (no double reservation, no
   negative stock); the affected tourist's code remains valid but blocked
   from concession while stock is unavailable. (A prize is linkable to at
   most one route, per the Clarifications record, so the race is always
   among completions of the same route.)
5. **Given** a code that was already used, **When** any actor attempts another
   concession with it, **Then** the system refuses with the standard conflict
   contract regardless of available stock.
6. **Given** a random or nonexistent code, **When** any actor attempts a
   concession with it, **Then** the system answers with the standard
   not-found contract and nothing changes.

---

## Clarifications

### Session 2026-11-02

- Q: Can the same prize be linked to different tourist routes, or does each route carry its own exclusive prize with its own stock? → A: The prize is an independent catalog entity, but in v1 it is linkable to at most one route at a time (no shared stock across routes).

- Q: Must the tourist visit a route's spots in the order defined at route creation, or can the route be completed by visiting the spots in any order? → A: Free order — completion happens when all spots are visited regardless of order; the list order is for display/organization only.

- Q: Who in the system is allowed to register the physical prize handover against a tourist's redemption code, and should the handover record identify where it took place? → A: Employees and administrators are authorized; the concession record must carry the tourist spot where pickup occurred.

- Q: Does a redemption code expire, and if so after how long? → A: No expiration in v1 — the code remains valid until it is honored.

- Q: When a registered spot visit updates the tourist's active routes, what should the `register_spot_visit` service return to the visitation module? → A: Per affected route, its identifier, the recomputed completion rate and a completed flag — no gamification internals exposed.

### Edge Cases

- What happens when a route is edited to remove a spot the tourist has
  already visited? The tourist's completion rate is recomputed against the
  new spots list; if all remaining spots are already visited, the route
  completes and the normal reward flow (badge + code) applies, exactly once.
- What happens when a route is edited to add new spots to a route that some
  tourist already completed? The completed route and its earned rewards stay
  as they were; new spots only affect enrollments still in progress, which
  gain the new pending spot in their progress report.
- What happens when `register_spot_visit` receives an unknown tourist or an
  unknown spot? The service answers with the standard not-found contract and
  nothing changes.
- What happens when the same spot visit is registered many times
  concurrently? The spot counts as visited exactly once per
  tourist-spot pair; completion, badge and code are produced at most once.
- What happens when a tourist completes the same route code-free more than
  once (e.g. duplicate completion attempts)? The reward pair (badge + code)
  is unique per tourist-route pair; a repeated completion attempt neither
  produces a second badge nor a second code.
- How does the system handle stock adjustment to a value below the
  reservations already held? The stored quantity respects the rule that
  stock never becomes negative for concessions: held reservations cannot be
  revoked by an adjustment, so an adjustment cannot take effect below the
  units already committed to reservations that guarantee concessions.

## Requirements *(mandatory)*

### Removal Decision (recorded for future features)

Route removal **archives** the route: it stops being listed/enrollable and
disappears from default administrative listings, but all enrollments,
progress, badges and redemption codes of tourists already enrolled are
**preserved untouched**. Reason: a tourist who invested visits on a route
must keep their progress and rewards even if the administrator removes the
route afterwards. Enrollments against an archived route are rejected
(not found). Administrators can still read archived routes explicitly by
identifier when needed.

### Functional Requirements

- **FR-001**: System MUST allow an authenticated administrator to create a
  tourist route with a Portuguese-facing name and description, an ordered
  list of existing tourist spots and a prize associated with the route
  conclusion. (RF18)
- **FR-002**: System MUST allow the administrator to edit any attribute of an
  existing route (texts, spots list) and archive (remove) it, recording
  every administrative write in the audit log. (RF19) The completion prize
  is bound to the route at creation and is thereafter managed only through
  stock control (FR-003).
- **FR-003**: System MUST allow the administrator to register and adjust the
  stock quantity of each prize linked to a route, rejecting any quantity
  below zero. (RF20)
- **FR-004**: Completion MUST attempt one idempotent prize reservation —
  repeated or concurrent completions of the same tourist-route pair MUST
  produce at most one reservation; when no stock is available the
  completion still succeeds (badge + code) without a reservation and the
  concession is blocked until stock is replenished. The system MUST never
  concede a prize without stock (no concession without a consumable unit;
  stock can never go negative). (RF20)
- **FR-005**: System MUST allow a tourist to enroll in a route available for
  enrollment and MUST reject a duplicate enrollment of the same tourist in
  the same route with the standard conflict contract (HTTP 409). (RF29)
- **FR-006**: System MUST expose, for each enrollment, the progress of the
  route: every spot with its visited/pending state and the completion rate
  (percentage of visited spots), responsive enough to render a progress bar
  directly from it. Route completion is order-free: the route progresses and
  completes regardless of the sequence in which the spots are visited; the
  route's spots list order is for display/organization only. (RF30)
- **FR-007**: System MUST provide the public domain service
  `register_spot_visit(tourist_id, tourist_spot_id)` as the only entry point
  by which the visitation module updates gamification state, and it MUST
  update the progress of ALL in-progress routes of that tourist that contain
  the visited spot, in a single call. On success it MUST return, per affected
  route, the route's identifier, the recomputed completion rate and a
  completed flag — without exposing gamification internals. (RF34)
- **FR-008**: When the last pending spot of an enrollment is visited, the
  system MUST automatically complete the route for that tourist, exactly once
  (idempotent), and MUST grant exactly one digital completion badge per
  tourist-route pair. (RF35)
- **FR-009**: Upon completion, the system MUST generate one prize redemption
  code per tourist-route pair that is unique across all codes ever issued,
  cryptographically unguessable (not predictable from any counter or
  identifier), not expiring (valid until honored, per the Clarifications
  record) and single-use: once honored, a second use MUST be refused with
  the standard conflict contract. (RF36)
- **FR-010**: A prize concession against a code MUST only be granted to an
  employee or an administrator (the employee's dedicated access is exactly
  prize concession), only with available stock, consuming exactly one unit
  and marking the code as used exactly once. The concession record MUST
  identify the tourist spot where pickup occurred; a concession submitted
  with an unknown spot MUST be rejected with the standard validation failure
  contract. With insufficient stock the concession MUST be blocked without
  altering any state and the code MUST remain valid.
- **FR-011**: All HTTP-bound request/response schemas of the module MUST
  follow the centralized JSON contract of the constitution (camelCase payload,
  strict boundary, unified error payload), and every endpoint of this module
  MUST be grouped under the "Gamification" tag of the centralized OpenAPI tag
  registry — no tag string written outside it.
- **FR-012**: Route removal MUST archive the route (no longer listed or
  enrollable) while preserving untouched the enrollments, progress, badges
  and codes of tourists already enrolled, per the Removal Decision section.
- **FR-013**: Administrative route-management endpoints MUST enforce
  administrator-only access; a tourist MUST only read their own enrollments,
  progress, badges and codes, never another tourist's.

### Key Entities *(include if feature involves data)*

- **TouristRoute**: a gamified itinerary — Portuguese-facing name and
  description, an ordered list of tourist spots (spec 007 entities), a
  linked prize, availability status (active or archived by removal).
- **RouteSpot**: the membership of a tourist spot in a route with a
  display-order position (a spot may belong to many routes); the order is
  organizational only — completion is order-free.
- **Prize**: the completion reward material ("brinde") — Portuguese-facing
  name and controlled stock quantity, an independent catalog entity linked to
  at most one route at a time (never shared across routes in v1); stock is
  never negative.
- **RouteEnrollment**: the tourist's subscription to a route — status
  (in progress or completed), created at, unique per tourist-route pair.
- **RouteProgress**: the per-enrollment progress derived from registered
  spot visits — the set of visited spots and the completion rate.
- **CompletionBadge**: the digital badge granted once per tourist-route
  completion, referencing the route and the completed-at moment.
- **RedemptionCode**: the single-use prize redemption code issued once per
  tourist-route completion — the unguessable code value, its prize, its
  state (unused, used; never expiring) and when it was honored; when honored,
  the record identifies the tourist spot where pickup occurred and the
  authorizing staff identity; unique across all issuances.
- **SpotVisit**: the registration that spot X was visited by tourist Y at a
  given moment — the input that drives progress, created idempotently per
  tourist-spot pair. (This feature consumes/registers visits through the
  service interface; spec 010 will feed it from check-in with geolocation.)

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A tourist can enroll in a route and see their progress (visited
  spots, pending spots, completion rate) updated after each registered visit,
  within the response time expected for mobile usage (essential services
  responsiveness, RNF11).
- **SC-002**: A single registered spot visit updates, in one operation, the
  progress of every in-progress route of that tourist containing the spot —
  verified by observing two routes advance from one and the same call.
- **SC-003**: For a route with N spots, the completion flow emits exactly one
  badge and one code, 100 % of the times the route is completed exactly once;
  across repeated or concurrent completion attempts, the count of badges and
  codes per tourist-route pair never exceeds one.
- **SC-004**: Every issued redemption code is unique and unguessable: no two
  tourists/routes share a code, and no code can be derived from public
  identifiers or sequence numbers.
- **SC-005**: Stock never assumes a negative value, and no concession happens
  without stock: 100 % of concession attempts with stock 0 are blocked with
  no state alteration and the code stays valid.
- **SC-006**: A duplicate enrollment never registers: 100 % of duplicate
  enrollment attempts end with the conflict contract and the original
  enrollment intact.
- **SC-007**: The complete acceptance journey — enroll, visit all spots,
  badge granted, single code generated, second use of the code refused —
  passes as one automated integration test, plus a test of insufficient
  stock/concurrency blocking the prize concession.

## Assumptions

- Actors and permissions are already defined by specs 002/003: administrators
  manage routes and prizes; tourists enroll and track their own progress; an
  authorized staff actor registers the physical prize concession (the exact
  RBAC profile for concession follows the existing employee model).
- The visitation module (spec 010) does not exist yet: in this feature the
  `register_spot_visit` service is exercised directly (in tests and any
  current callers), and spec 010 will connect the check-in flow through it.
  No GPS validation is in scope here — geospatial presence validation belongs
  to the visitation feature (RNF14).
- Prize stock is managed per prize entity; per the Clarifications record, a
  prize is linkable to at most one route at a time in v1 (a route has one
  completion prize), since RF18 associates "um brinde" to the route
  conclusion. The prize is permanently bound to the route that created it;
  its stock is adjusted through the prize stock endpoint (RF20).
- Badge issuance is recorded at the moment of completion; badges are exposed
  through the completed enrollment's progress payload (Story 3). An
  aggregated cross-route "my badges" listing is deferred to a later feature
  (YAGNI).
- Audit of administrative write actions reuses the existing centralized audit
  infrastructure used by spots and events management (RNF19).
- The "Gamification" tag already exists in the centralized tag registry
  (spec 006); this feature only assigns it to the module routers and writes
  no tag string outside the registry.