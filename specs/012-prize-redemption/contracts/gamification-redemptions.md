# Contract: Gamification — Prize Redemption (RF21)

Tag OpenAPI: `Gamification` (registro central, spec 006 — sem string de
tag fora de `core/tags.py`). Contrato JSON camelCase estrito
(`ApiModel`, `extra="forbid"`, snake_case rejeitado com 422); falhas
exclusivamente no payload único `ApiError` (`errorCode`, `message`,
`details`).

## POST `/api/v1/gamification/redemptions`

Registra a concessão do brinde contra um código de resgate single-use
(RF21/RF36). Restrito a funcionários e administradores (RF03).

### Request — `RedemptionCreateRequest` (inalterado)

| Campo JSON | Tipo | Regras |
|---|---|---|
| `code` | string | valor do código emitido na conclusão da rota; 422 se vazio/fora do shape |
| `spotId` | int | ponto turístico ativo da retirada; 404 se inexistente |

```json
{ "code": "3f9a2c81e7d4", "spotId": 5 }
```

### 201 — conceded (`RedemptionView`, **delta: `prize.stockQuantity`**)

```json
{
  "code": "3f9a2c81e7d4",
  "prize": { "id": 12, "name": "Caneca do Festival", "stockQuantity": 9 },
  "routeId": 7,
  "touristId": 34,
  "pickupSpotId": 5,
  "concededBy": "maria.panel",
  "usedAt": "2026-11-03T14:22:31Z"
}
```

- `prize.stockQuantity` é o estoque **pós-dedução** (exatamente uma unidade
  a menos — FR-004)
- Semântica transacional: baixa do estoque, flip `unused → used` e registro
  de concessão commitam juntos; audit `prize.concede` com
  `stockQuantityBefore/After`, `touristId`, `prizeId` na mesma transação
  (FR-007; falhas não emitem audit — decisão v1)

### Erros — `ApiError` (payload único)

| Situação | Status | errorCode | message |
|---|---|---|---|
| sem token / token inválido | 401 | `authentication_failed` | (padrão central) |
| sessão turista / não-staff | 403 | `authorization_failed` | (padrão central) |
| código inexistente | 404 | `resource_not_found` | (padrão central) |
| ponto de retirada inexistente/inativo | 404 | `resource_not_found` | (padrão central) |
| código já utilizado | 409 | `conflict` | `redemption code has already been used` |
| estoque do brinde insuficiente | 409 | `conflict` | `no stock available for this route's prize` |
| shape inválido, campo snake_case, campo desconhecido | 422 | `validation_failed` | (padrão central) |

- Nenhuma falha altera estado: código permanece `unused`/não reemite
  dedução; estoque fica intacto e nunca negativo (FR-005/FR-006)
- Os dois conflitos (409) diferenciam-se pela `message` (research R3) —
  errorCode permanece o registro central (`conflict`)
- Códigos não expiram (spec 009) — não existe caminho "expired"

### Idempotência observável (FR-003, SC-002)

Repetidas ou concorrentes submissões do mesmo código: no máximo um 201; os
demais retornam 409 `redemption code has already been used`; o estoque
sofre no máximo uma baixa; a auditoria registra no máximo um
`prize.concede`.

## Referências

- [data-model.md](../data-model.md) — estados e campos de audit
- [quickstart.md](../quickstart.md) — como validar o contrato
- Spec 009 `specs/009-tourist-routes-gamification/spec.md` — entidades e
  clarificações herdadas (Q1/Q3, sem expiração)