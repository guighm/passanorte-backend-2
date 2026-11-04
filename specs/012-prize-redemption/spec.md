# Feature Specification: Prize Redemption (Employee Scan)

**Feature Branch**: `012-prize-redemption`

**Created**: 2026-11-03

**Status**: Draft

**Input**: User description: "Implementar Resgate de Brindes do PassaNorte (backend FastAPI, módulo gamification), endpoint restrito a funcionários e administradores conforme RF03 (spec 002). Requisitos: RF21 — funcionário escaneia o código único gerado pelo turista em rota concluída; o sistema valida o código (existente, ainda não usado, do turista correto ou válido na entrega presencial) e concede o brinde correspondente, com BAIXA AUTOMÁTICA no estoque do brinde da rota (RF20), de forma transacional e idempotente: um código nunca gera duas baixas. Respostas: sucesso com dados do brinde e novo estoque; erro claro para código inválido, expirado (se aplicável), já utilizado ou rota sem estoque disponível. RNF19 — audit log do resgate (funcionário, turista, brinde, estoque antes/depois). Reuso: transação única sobre serviço público do módulo gamification — sem tocar tabelas de outro módulo. Todos os endpoints deste módulo agrupados sob a tag "Gamification" do registro central de tags da spec 006. Critério de aceitação: teste de contrato de resgate bem-sucedido reduzindo estoque; testes de falha: código inexistente, código duplicado (idempotência), estoque insuficiente bloqueando; teste de RBAC (turista não resgata, sem token 401); teste de auditoria."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Employee redeems a tourist's prize by scanning the unique code (Priority: P1)

A tourist completes a route (spec 009), receives the completion badge and a
single-use redemption code, and goes to a pickup spot to collect the physical
prize. An employee (or administrator) of the PassaNorte panel scans the code
the tourist presents. The system validates that the code exists (was issued
by the system), has never been used before, and belongs to a completed
enrollment of the presenting tourist — the code is bound to its tourist and
route at issuance, so honoring it is always against the correct tourist.
When the validation passes, the system concedes the corresponding prize of
the route with an automatic stock deduction of exactly one unit: the stock
guard, the code flip (unused → used) and the concession record all happen in
one atomic transaction under the gamification module's public service — no
other module's tables are touched. The success response carries the prize
data and the prize's new (post-deduction) stock, so the employee confirms at
a glance which prize was handed over and how many units remain.

**Why this priority**: This is RF21 itself — the moment the gamification
loop pays off physically. Without the scan endpoint the tourist's code is
just a string with no operational value.

**Independent Test**: Fully testable as a contract test against the
redemption endpoint: complete a route for a tourist, then submit the issued
code as an authenticated employee and verify a success response with the
prize identity and the stock reduced by exactly one.

**Acceptance Scenarios**:

1. **Given** a completed route whose tourist holds an unused redemption code
   and whose prize has stock ≥ 1, **When** an authenticated employee submits
   that code for redemption, **Then** the system returns a success response
   identifying the prize (name and identifier), the redeemed code, the
   tourist and the route, and the prize's new stock (exactly one unit lower).
2. **Given** the same redemption request, **When** it is processed, **Then**
   the stock deduction, the code flip to used and the concession record are
   committed together: no intermediate state (code used without stock
   deduction, or stock deducted without the code being consumed) is ever
   observable.
3. **Given** an administrator, **When** they submit the same kind of
   redemption request, **Then** it succeeds under the same contract — RBAC
   of this endpoint allows employees and administrators (RF03), and a tourist
   session is refused with the standard forbidden contract (a tourist can
   never redeem: this is the RBAC gate tested by the acceptance suite).
4. **Given** every endpoint of this module, **When** its contract is read,
   **Then** it belongs to the "Gamification" OpenAPI tag group of the
   centralized tag registry (spec 006) — redemption endpoints included.

---

### User Story 2 - Clear, state-preserving failures and a code that can never deduct twice (Priority: P1)

When the redemption cannot be completed, the system answers with one clear
error per cause and never changes any state: an unknown/random code is a
not-found error; a code that has already been honored is a conflict error
(idempotency — a code never generates two deductions, no matter how many
times or how many concurrent scans it receives); a code valid but with an
empty prize stock is a conflict error that explicitly means "route without
stock available" — and leaves the code unused and valid, so the tourist can
come back when stock is replenished. Codes do not expire (per the spec 009
clarification record), so no "expired" failure path exists in v1.

**Why this priority**: Same rank as Story 1 because the redemption is only
trustworthy when its failure semantics are exact: a double concession (gift
handed over twice) or a deducted stock without a concession is exactly what
RF21 exists to prevent.

**Independent Test**: Testable with a completed route and controlled stock:
submit a random code (not-found), submit the same valid code twice (second
attempt conflicts, stock unchanged), set the stock to zero and submit the
valid code (conflict, code still unused, stock still zero, no negative
value at any point).

**Acceptance Scenarios**:

1. **Given** a random or nonexistent code, **When** any authenticated staff
   actor submits it, **Then** the system answers with the standard
   not-found contract and nothing changes (no stock movement, no code state
   change).
2. **Given** a code that has already been honored, **When** any staff actor
   submits it again, **Then** the system answers with the standard conflict
   contract and no second stock deduction occurs — repeating this any number
   of times never produces more than one deduction for that code.
3. **Given** a valid unused code whose prize stock is zero, **When** a staff
   actor submits it, **Then** the system answers with the standard conflict
   contract meaning "no stock available for this route's prize", the code
   remains unused and valid, and the stock stays at zero (never negative).
4. **Given** repeated and concurrent redemption attempts with the same code
   (e.g. a scan retried by a flaky scanner or racing panel clients),
   **When** the attempts resolve, **Then** exactly one attempt grants the
   prize: one concession record, one stock unit deducted, all other attempts
   answered with the conflict contract (idempotency is enforced inside the
   same transaction, not by client discipline).

---

### User Story 3 - Every redemption is audited with the actors and the stock before/after (Priority: P2)

Each successful redemption generates a structured audit record (RNF19) that
identifies the acting employee (or administrator), the tourist who earned
the prize, the prize conceded (route bound to it), the pickup spot where it
happened and the prize's stock quantity before and after the deduction. A
blocked redemption is observable by its own failure contract but produces no
state to reconcile — the audit trail is about the granted concessions. The
audit record is written inside the same transaction as the concession, so
an audit entry always corresponds to a real state change.

**Why this priority**: Compliance requirement (RNF19) that depends on the
granted-concession flow being right, but does not change its outcome — a
redemption that works and is correctly contract-tested may ship with the
audit recording immediately after, still before the feature is done.

**Independent Test**: Testable directly after a successful redemption:
perform one redemption with stock known in advance and verify the audit log
contains exactly one record naming the staff actor, the tourist, the prize,
the pickup spot and both stock quantities (before and after).

**Acceptance Scenarios**:

1. **Given** a successful redemption with a prize whose stock was N before,
   **When** the audit log is inspected, **Then** there is exactly one record
   for that concession naming the staff actor, the tourist, the prize, the
   pickup spot and the stock before (N) and after (N − 1).
2. **Given** a redemption attempt that fails for any reason, **When** the
   audit log is inspected, **Then** no concession audit record exists for
   it (no concession happened) and the stock before/after state is intact.

---

## Clarifications

### Session 2026-11-03

- Q: Should the system verify the identity of the person presenting the code
  at pickup, or is the unique code's validation enough to concede the prize
  to whoever presents it? → A: Trust the code in v1 — the code is unique,
  unguessable and single-use, so no presenter identity check is required and
  no tourist identification data is added to the redemption request; the
  concession record still identifies the tourist through the code's
  issuance binding.

- Q: Should failed redemption attempts (unknown code, already used, no
  stock) also generate audit records, or is the explicit error to the staff
  actor enough in v1? → A: No audit records for failed attempts in v1 — the
  unified error contract makes every failure observable, codes are not
  brute-forceable, and no state changes occur to reconcile.

---

## Edge Cases

- What happens when the person presenting the code is not the tourist who
  earned it (e.g. a family member picking it up)? The system accepts it in
  v1: the validated single-use code authorizes the handover, and the
  concession record identifies the tourist through the code's issuance
  binding.
- What happens when a staff actor scans a code belonging to a tourist whose
  enrollment is not completed? Impossible by construction: codes are only
  issued upon route completion (spec 009); an unknown code is answered as
  not-found and no state changes.
- What happens when the code is valid but submitted without a pickup spot?
  The pickup spot is part of the concession contract (spec 009 clarification
  Q3): a submission without a valid existing spot is rejected with the
  standard validation/not-found contract and nothing changes.
- What happens when two different codes for the same tourist's completed
  route are honored consecutively? Can only occur if two completions of the
  same tourist-route pair each issued a code — which spec 009 forbids
  (completion is idempotent); a single completed route yields exactly one
  code, hence at most one concession.
- What happens when the stock is adjusted to a value equal to or below the
  units already committed to reservations while a redemption is attempted?
  Stock never goes negative: the deduction is guarded atomically (guarded
  decrement), and an insufficient-stock answer leaves the code usable.
- What happens when a redemption request arrives without authentication or
  with an expired/invalid token? The system answers with the standard
  unauthorized contract — only authenticated staff sessions reach the
  redemption validation.
- What happens when the same staff actor rescans a code that returned
  "no stock available" after stock was replenished? The code is still valid
  and unused, so the redemption then succeeds normally (no expiration, no
  penalty for the earlier blocked attempt).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST expose an authenticated prize-redemption endpoint
  restricted to employees and administrators (RF03); unauthenticated
  requests MUST be answered with the standard unauthorized contract, and
  tourist (or other non-staff) sessions MUST be answered with the standard
  forbidden contract — a tourist can never redeem.
- **FR-002**: The redemption flow MUST validate the scanned code before
  granting anything: the code MUST exist (system-issued, unknown codes
  answered with the standard not-found contract), MUST be unused (already
  honored codes answered with the standard conflict contract) and MUST be
  bound to a completed enrollment of the correct tourist (identity enforced
  by the code's issuance binding, and carried in the concession record).
  The system MUST NOT require presenter identity data: in v1 the validated
  code itself authorizes the handover (v1 decision recorded in
  Clarifications).
- **FR-003**: A granted redemption MUST concede the prize corresponding to
  the code's route with an automatic stock deduction of exactly one unit,
  performed in a single transaction that also consumes the code — a code
  MUST never generate two deductions under any repetition or concurrency
  (tokenized single-use claim inside the same transaction: either both the
  deduction and the code consumption happen, or neither does).
- **FR-004**: The success response MUST carry the redeemed code, the prize
  data (identifier and name), the tourist and route identified by the code,
  the pickup spot and the staff actor, plus the prize's new stock quantity
  after the deduction.
- **FR-005**: Failure responses MUST be one clear error per cause, via the
  unified error contract: unknown code → not-found; already used code →
  conflict; prize without available stock → conflict with a
  "no stock available for this route's prize" meaning; missing/invalid
  pickup spot → validation/not-found — and MUST leave the code, its tourist
  claim and the stock untouched in every failure case.
- **FR-006**: The stock quantity of a prize MUST never become negative:
  every deduction is atomically guarded, and a concession attempt against
  empty stock is blocked without state alteration, leaving the code unused
  and reusable once stock exists again (no expiration: a code is valid
  until honored, per the spec 009 clarification record).
- **FR-007**: Each successful redemption MUST generate exactly one
  structured audit record inside the granting transaction (RNF19),
  identifying the staff actor (employee or administrator), the tourist, the
  conceded prize (with its route), the pickup spot and the stock quantity
  before and after the deduction. Failed redemption attempts MUST produce
  no audit record of any kind in v1 (v1 decision recorded in
  Clarifications): the unified error contract is their observable trace.
- **FR-008**: The redemption MUST be implemented as a single transaction
  over the gamification module's public service interface — no other
  module's tables or internals are touched; cross-module reads the flow
  needs go through those domains' public services.
- **FR-009**: Every redemption endpoint of the module MUST be grouped under
  the "Gamification" tag of the centralized OpenAPI tag registry (spec 006),
  with request/response schemas following the centralized camelCase JSON
  contract and failure paths exposing the unified error payload.

### Key Entities *(include if feature involves data)*

- **RedemptionCode** (existing, spec 009): the single-use, unguessable code
  issued once per tourist-route completion — bound at issuance to its
  tourist, route and prize; state (unused, used), honored-at moment, pickup
  spot and honoring staff identity once used; never expires.
- **Prize** (existing, spec 009): the route's completion reward ("brinde")
  — Portuguese-facing name and controlled stock quantity; the redemption
  deducts exactly one unit per honored code; never negative.
- **Concession record**: the outcome of a granted redemption — the consumed
  code, its tourist/route/prize binding, the pickup spot, the staff actor
  and the moment of the concession.
- **Redemption audit record** (RNF19): one structured log entry per granted
  concession naming actor, tourist, prize, pickup spot and stock
  before/after, written in the same transaction as the concession.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A contract test of a successful redemption passes: submitting
  a valid unused code as an authenticated employee returns the prize data
  and a stock value reduced by exactly one, 100 % of the runs.
- **SC-002**: Idempotency holds in 100 % of repetitions and concurrency
  scenarios: no code, submitted any number of times (including racing
  requests), ever causes more than one stock deduction or exists in more
  than one concession record.
- **SC-003**: Every failure cause maps to its distinct standard error —
  unknown code → not-found; used code and insufficient stock → conflict —
  and 100 % of those failures leave the code unused (when it was unused)
  and the stock unchanged.
- **SC-004**: Stock never assumes a negative value: 100 % of concessions
  against zero stock are blocked with the no-stock conflict and zero state
  alteration.
- **SC-005**: 100 % of granted concessions have exactly one audit record
  naming the staff actor, the tourist, the prize, the pickup spot and the
  stock before/after; failed attempts have none.
- **SC-006**: 100 % of unauthorized or non-staff attempts (no token, tourist
  session) are refused by the RBAC gate before any validation, with the
  standard unauthorized/forbidden contracts.
- **SC-007**: The acceptance suite for this feature passes as automated
  contract tests: successful redemption reducing stock; nonexistent code;
  duplicate code (idempotency); insufficient stock blocking; RBAC
  (tourist-refused, no-token-401); audit record verification.

## Assumptions

- The gamification module already implements the concession core from spec
  009 (US4): staff-gated redemption endpoint, atomic guarded stock
  decrement, single-use code claim and success/concession responses. This
  feature's scope on top of it is RF21's exact contract hardening: success
  response exposing the new stock (FR-004) and the audit record enriched
  with stock before/after (FR-007, RNF19), plus the acceptance tests.
- Stock consumption semantics are inherited from spec 009 US4 unchanged:
  each granted redemption consumes one unit of the prize's available stock
  via the atomically guarded decrement (a concession never negates stock);
  the idempotent reservation taken at route completion (spec 009 FR-004)
  guarantees a unit will be available at concession time.
- The employee dedicated access is exactly the prize concession (RF03);
  the RBAC gate reuses the existing staff authentication model (spec 002)
  — employees and administrators only.
- The redemption request carries the pickup spot (spec 009 clarification
  Q3): the concession record identifies the tourist spot where pickup
  occurred; no scope change here.
- Codes never expire (spec 009 clarification record) — the "expired"
  failure path of RF21 is not applicable in v1 and is documented as such.
- The "Gamification" tag already exists in the centralized registry (spec
  006); this feature only assigns it and writes no tag string outside it.
- Audit logging reuses the centralized audit infrastructure (RNF19) already
  used by the module's administrative write actions.