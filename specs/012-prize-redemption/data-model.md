# Data Model: Prize Redemption (Employee Scan) — feature 012

Nenhuma entidade nova e nenhuma mudança de schema (sem migration). Este
documento registra os deltas de estado e os campos derivados expostos pelo
fluxo de resgate, sobre as entidades da spec 009.

## Entidades reusadas (deltas em negrito)

### RedemptionCode — `redemption_codes` (existente)

- `id`, `code` (único, indexado), `route_id` → tourist_routes, `tourist_id`
  → tourists, `prize_id` → prizes
- `status`: `'unused' | 'used'` (check constraint) — transição única
  **`unused → used`, irreversível, via claim condicional no mesmo UPDATE
  que só dispara com `status == 'unused'`** (idempotência FR-003/FR-006)
- `used_at`, `pickup_spot_id`, `conceded_by`: `NULL` até o resgate;
  preenchidos exatamente uma vez

### Prize — `prizes` (existente)

- `id`, `name` (português, dado de usuário), `stock_quantity`,
  `reserved_quantity` (check constraints ≥ 0)
- **No resgate concedido: `stock_quantity` − 1** (guard condicional
  `stock_quantity >= 1` → nunca negativo) e **`reserved_quantity`
  = max(reserved_quantity − 1, 0)** — o guard liberta a reserva tomada na
  conclusão da rota, herdado da spec 009 sem alteração (research R5)

### Audit record — log-only (`core.audit.record_action`) (existente)

Um JSON line por concessão, action `prize.concede`, emitido **na mesma
transação** da baixa (FR-007). **`detail` passa a conter**:

| Campo | Conteúdo | Origem |
|---|---|---|
| `actor` (campo mandatório) | username do funcionário/admin | sessão staff |
| `action` | `"prize.concede"` (inalterado) | — |
| `target` | `"code:{código}"` (inalterado) | RedemptionCode |
| `detail.routeId` | rota da qual o brinde veio | RedemptionCode |
| `detail.touristId` | turista dono do código (novo) | RedemptionCode |
| `detail.prizeId` | brinde concedido (novo) | RedemptionCode |
| `detail.pickupSpotId` | ponto de retirada (inalterado) | request |
| `detail.stockQuantityBefore` (novo) | estoque lido antes do guard | Prize.stock_quantity |
| `detail.stockQuantityAfter` (novo) | `before − 1` (rowcount 1 garante) | — |

Falhas de resgate **não** emitem registro (decisão v1 em Clarifications).

## Contrato HTTP (deltas de shape — detalhes em contracts/)

- `RedemptionPrizeView` (resposta 201): **+ `stock_quantity`** (JSON
  `stockQuantity`) — o novo estoque pós-dedução (FR-004)
- Payload de erro 409: `errorCode: "conflict"` para ambas as causas;
  **`message` distinto** por causa (research R3)

## Derivações de leitura (nenhuma tabela nova)

- "novo estoque" na resposta = re-read pós-concessão de
  `find_prize_by_id` no route handler (já existente) — mesma transação
- Turista "correto" da FR-002 = vínculo de emissão (`tourist_id` do
  código, preenchido na conclusão da rota); nunca há input de turista no
  request (clarification: confiar no código)