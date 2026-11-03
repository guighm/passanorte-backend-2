# Data Model: Tourist Routes and Gamification (feature 009)

Todas as 7 tabelas pertencem exclusivamente ao domínio `gamification`
(constituição, regra 4 — nenhum módulo externo lê ou escreve essas linhas
diretamente). Turistas e pontos são referenciados somente por FK e validados
apenas pelas seams públicas dos módulos donos (esclarecimentos
tourists/tourist_spots — research R3). Progresso é **derivado em leitura**,
nunca armazenado como estado separado (research R1).

## 1. Entities

### TouristRoute (table `tourist_routes`)

| Field | Type | Rules |
|---|---|---|
| `id` | int PK | system-generated |
| `name` | String(200) | Portuguese-facing user content, 1..200 chars (RF18) |
| `description` | String(2000) | Portuguese-facing user content, 1..2000 chars |
| `prize_id` | int FK → `prizes.id` | required; o brinde nasce com a rota (payload embutido); binding exclusivo: `UNIQUE INDEX` parcial `WHERE removed_at IS NULL` — um brinde ativo em no máximo uma rota (Q1); binding permanente — criado com a rota, não re-vinculável (análise F1) |
| `created_at` / `updated_at` | datetime UTC | audit timestamps (007 precedent) |
| `removed_at` | datetime \| null | archive/soft delete na remoção (FR-012); histórico de inscritos, progresso, insígnias e códigos permanece intacto |

### RouteSpot (table `route_spots`)

| Field | Type | Rules |
|---|---|---|
| `id` | int PK | system-generated |
| `route_id` | int FK → `tourist_routes.id` (`ondelete="CASCADE"`) | membership |
| `tourist_spot_id` | int FK → `tourist_spots.id` | referência somente-leitura; validada pela seam `tourist_spots` antes de qualquer escrita (R3) |
| `display_order` | int | posição de display/organização **apenas** — qualquer ordem de visita progride e conclui (Q2); ≥ 1, sem lacunas após validação |

- `UNIQUE (route_id, tourist_spot_id)` — mesmo ponto não repete na rota.
- Lista da rota não pode ser vazia na criação (422 — spec US1-5).

### Prize (table `prizes`)

| Field | Type | Rules |
|---|---|---|
| `id` | int PK | system-generated |
| `name` | String(200) | Portuguese-facing user content, 1..200 chars |
| `stock_quantity` | Integer ≥ 0 | unidades físicas em mãos, ajustáveis pelo admin (nunca negativo — guarda em SQL, research R4); ajuste rejeitado abaixo de `reserved_quantity` (422) |
| `reserved_quantity` | Integer ≥ 0, default 0 | unidades comprometidas por conclusões (reserva idempotente, FR-004); nunca excede `stock_quantity + emissões sem estoque à época` (a reserva só é criada com guarda de estoque) |
| `created_at` / `updated_at` | datetime UTC | audit timestamps |

- Brinde é entidade de catálogo independente (Q1) criada no payload da
  rota; não tem CRUD autônomo nesta versão — só ajuste de estoque.

### RouteEnrollment (table `route_enrollments`)

| Field | Type | Rules |
|---|---|---|
| `id` | int PK | system-generated |
| `route_id` | int FK → `tourist_routes.id` | enrollment |
| `tourist_id` | int FK → `tourists.id` | referência somente-leitura; validada pela seam `tourists` (R3) |
| `status` | String — `in_progress` \| `completed` | transição por UPDATE condicional (`WHERE status='in_progress'` — research R2) |
| `completed_at` | datetime \| null | moment da conclusão (uma vez) |
| `created_at` | datetime UTC | enrollment timestamp |

- `UNIQUE (route_id, tourist_id)` — inscrição duplicada impossível no
  banco (409 na borda; FR-005/SC-006).
- Turistas de rota arquivada mantêm as linhas e continuam a progredir
  (FR-012).

### SpotVisit (table `spot_visits`)

| Field | Type | Rules |
|---|---|---|
| `id` | int PK | system-generated |
| `tourist_id` | int FK → `tourists.id` | quem visitou |
| `tourist_spot_id` | int FK → `tourist_spots.id` | ponto visitado |
| `visited_at` | datetime UTC | primeiro registro do par |

- `UNIQUE (tourist_id, tourist_spot_id)` — visita re-registrada é no-op
  idempotente (spec Edge Cases); índice em `tourist_id` para o join do
  progresso.
- Dono: `gamification` nesta feature (research R1) — o módulo `visitation`
  (spec 010) entrará por `register_spot_visit`, não pela tabela.

### CompletionBadge (table `completion_badges`)

| Field | Type | Rules |
|---|---|---|
| `id` | int PK | system-generated |
| `route_id` | int FK → `tourist_routes.id` | route referenciada |
| `tourist_id` | int FK → `tourists.id` | receptor |
| `granted_at` | datetime UTC | moment da concessão (finalização da rota) |

- `UNIQUE (route_id, tourist_id)` — exatamente uma insígnia por par
  (RF35; FR-008).

### RedemptionCode (table `redemption_codes`)

| Field | Type | Rules |
|---|---|---|
| `id` | int PK | system-generated |
| `code` | String UNIQUE, indexed | `secrets.token_urlsafe(16)` — 128 bits de entropia CSPRNG, URL-safe, sem expiração (Q4; R5); unique em todo o sistema (SC-004) |
| `route_id` | int FK → `tourist_routes.id` | rota concluída |
| `tourist_id` | int FK → `tourists.id` | titular |
| `prize_id` | int FK → `prizes.id` | brinde a retirar |
| `status` | String — `unused` \| `used` | uso único; segunda tentativa → 409 (FR-009) |
| `created_at` | datetime UTC | emissão (conclusão da rota) |
| `used_at` | datetime \| null | moment da concessão |
| `pickup_spot_id` | int FK → `tourist_spots.id`, null até concessão | ponto onde a retirada ocorreu (Q3) |
| `conceded_by` | String, null até concessão | identidade do staff que concedeu (Q3) |

- `UNIQUE (route_id, tourist_id)` — um código por conclusão (SC-003);
  código gerado na mesma transação da conclusão (R2).

## 2. State transitions

| Transition | Trigger | Effect |
|---|---|---|
| rota: (none) → active | admin `POST /routes` | cria rota + brinde + spots validados; 1 audit `route.create` |
| rota: active → active' | admin `PATCH /routes/{id}` | revalidação de spots quando a lista muda; inscrições permanecem válidas; 1 audit `route.update` |
| rota: active → archived | admin `DELETE /routes/{id}` | `removed_at` setado; listagem/inscrição bloqueadas; histórico intacto; 1 audit `route.delete` |
| brinde: stock N → N' | admin `PATCH /prizes/{id}` | guarda: N' ≥ `reserved_quantity`; 1 audit `prize.stock_update` |
| inscrição: (none) → in_progress | turista `POST /routes/{id}/enrollments` | rota ativa; duplicada → 409 |
| visita: (none) → existe | `register_spot_visit(tourist_id, tourist_spot_id)` | INSERT idempotente; progresso de TODAS as inscrições em andamento que contêm o ponto recalculado derivadamente |
| inscrição: in_progress → completed | última visita completa a rota | status via UPDATE condicional; insígnia + código emitidos na mesma transação (idempotente — R2); reserva de unidade do brinde com guarda de estoque quando disponível (R4) |
| código: unused → used | staff `POST /redemptions` | guarda de estoque (R4): consome 1 unidade (reserva mantida pelo titular, quando existente); `used_at` + `pickup_spot_id` + `conceded_by`; estoque 0 → 409, código permanece válido |

## 3. Derivations (computed at read time, never stored)

| Derived value | Definition | Where contracted |
|---|---|---|
| `completionRate` | `floor(100 * visited_count / total_spots)` (integer 0–100; 0 spots excluded by rule — routes always have ≥ 1) | progress payload (RF30) + service outcome (R8) |
| visited/pending spots | join `route_spots` (display order) × `spot_visits` of the tourist | progress payload |
| reservation state | `stock_quantity - reserved_quantity` = units available for a next completion | stock adjust guard + reservation guard (internal; not on the wire beyond stockQuantity) |
| badge/code availability | presence of `completion_badges`/`redemption_codes` rows for the enrollment | progress payload when `status = completed` |

## 4. Contract ↔ storage mapping

| JSON (camelCase, via `ApiModel`) | Storage | Conversion |
|---|---|---|
| `initialStock` / `stockQuantity` | `stock_quantity` | verbatim integer, ≥ 0 |
| `displayOrder` | `display_order` | verbatim (service normalizes gaps) |
| `status` (rota/inscrição/código) | `status` / `removed_at is null` | rota: `archived` ⇄ `removed_at` (wire value `archived`); inscrição: storage `in_progress`/`completed` → wire `inProgress`/`completed` (precedente 007 de enum camelCase no wire); código: `unused`/`used` verbatim |
| `completionRate` | derived (§3) | read-time floor |
| `code` | `code` | verbatim, URL-safe |
| `pickupSpotId`, `concededBy`, `usedAt` | `pickup_spot_id`, `conceded_by`, `used_at` | verbatim/presente só quando `used` |