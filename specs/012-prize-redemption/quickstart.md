# Quickstart: Prize Redemption (Employee Scan) — feature 012

Guia de validação ponta a ponta do resgate de brindes (RF21). Não contém
implementação — detalhes de contrato em
[contracts/gamification-redemptions.md](./contracts/gamification-redemptions.md)
e de estado em [data-model.md](./data-model.md).

## Pré-requisitos

- Ambiente de dev ativo (Docker do compose ou ambiente local com as
  credenciais essenciais: `DATABASE_URL`, `JWT_SECRET`, `SENSITIVE_DATA_KEY`)
- Um administrador e um funcionário existentes no painel (funcionário criado
  por administrador; admin via `create-admin`)
- Rota já existente com brinde vinculado (spec 009)

## Cenário 1 — fluxo completo até o resgate (aceitação primária)

1. **Preparar**: como admin, criar rota com brinde de estoque N ≥ 1; como
   turista, instalar o app ou usar o endpoint de registro (spec 003) e se
   inscrever na rota; registrar visita a **todos** os pontos da rota
   (`register_spot_visit` via fluxo de check-in da spec 011 / serviço).
2. **Observar**: progresso do turista na rota chega a 100 %, insígnia
   concedida e exatamente **um** código (`redemptionCode`) no payload de
   progresso.
3. **Resgatar**: como funcionário (ou admin):
   `POST /api/v1/gamification/redemptions` com o `code` do passo 2 e o
   `spotId` do ponto de retirada.
4. **Esperado**: 201 com `prize.stockQuantity == N - 1`, além do código,
   brinde (nome/identificador), `routeId`/`touristId`,
   `pickupSpotId`/`concededBy`.

## Cenário 2 — idempotência (um código, uma baixa)

- Reabrir o mesmo código em novo request (mesmo com estoque grande):
  409 com mensagem *"redemption code has already been used"*; o estoque
  permanece o do passo 4; repetir quantas vezes quiser — nunca há 201
  novamente nem segunda baixa.

## Cenário 3 — rota sem estoque disponível

- Ajustar o estoque do brinde para 0 (`PATCH /api/v1/gamification/prizes/{id}`
  com `{"stockQuantity": 0}`) e resgatar um código válido e não usado de
  outra rota concluída com esse brinde: 409 com mensagem *"no stock
  available for this route's prize"*; o código permanece utilizável
  (repor estoque → o resgate então sucede; sem expiração).

## Cenário 4 — falhas claras

- Código aleatório/inexistente → 404 (`resource_not_found`);
- Ponto de retirada inexistente no `spotId` → 404, código intacto;
- Sem token → 401 (`authentication_failed`); token de turista → 403
  (`authorization_failed`);
- Corpo com snake_case (`{"spot_id": 1}`) ou campo desconhecido → 422.

## Cenário 5 — auditoria (RNF19)

- Nas linhas do logger `passanorte.audit` (stdout): exatamente um registro
  `action: "prize.concede"` por concessão, com `actor` (funcionário), e
  `detail` contendo `touristId`, `prizeId`, `routeId`,
  `pickupSpotId`/`stockQuantityBefore`/`stockQuantityAfter`
  (before = N, after = N − 1). Falhas de resgate não geram linhas.

## Suíte automatizada (validação mais rápida)

```bash
pytest tests/contract/test_gamification.py -k redemption_or_concession   # contrato
pytest tests/integration/test_gamification_lifecycle.py                   # fluxo completo + race
pytest tests/contract/test_openapi_tags.py                                 # tag Gamification intacta
ruff check && pytest tests/smoke/                                           # gates de fronteira/ruff
```

Todo cenário acima está coberto por um teste automatizado (criterios
SC-001..SC-007 da spec); este guia existe para demonstração manual e
revisão de contrato.