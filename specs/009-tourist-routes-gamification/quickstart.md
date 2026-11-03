# Quickstart: Tourist Routes and Gamification (feature 009)

Validation scenarios proving the feature works end-to-end. Prerequisites
and setup reference shared project infrastructure — this guide never
duplicates implementation details (contracts: [contracts/gamification.md](contracts/gamification.md);
data: [data-model.md](data-model.md); source of truth: [spec.md](spec.md)).

## Prerequisites

- Python 3.13 environment of the repository (existing tooling — see repo
  README for venv setup).
- The test suite runs against the fixed synthetic environment in
  `tests/conftest.py` (in-memory SQLite per test, admin/employee seeds,
  tourist authentication through the public auth interface, audit capture)
  — no local services or secrets needed.

## Automated gate (primary acceptance)

```bash
pytest tests/contract/test_gamification.py             # endpoint contracts & refusal paths
pytest tests/integration/test_gamification_lifecycle.py # acceptance journey + stock race
pytest tests/unit/test_gamification_codes.py            # code entropy/uniqueness
pytest tests/test_migrations.py                         # migrations create the 7 tables
pytest                                                  # full suite incl. smoke/boundaries sweeps
```

Expected outcomes (acceptance criteria from spec.md, SC-001..SC-007):

- **Contract suite**: route create → 201 (brinde embutido), edit → 200,
  archive → 204; não-admin nas escritas → 403 `authorization_failed`;
  rota/ponto/código/brinde inexistente → 404 `resource_not_found`;
  inscrição duplicada, código já usado, estoque 0 na concessão → 409
  `conflict`; shape inválida, chave snake_case ou desconhecida,
  `initialStock` < 0, ajuste abaixo da reserva → 422
  `validation_error`; corpo sempre camelCase via `ApiModel`.
- **Integration suite (SC-007 — the acceptance journey)**: admin cria
  spots + rota com brinde → turista se inscreve (duplicada → 409) →
  visita de cada ponto via `register_spot_visit` (uma visita atualiza
  duas rotas afins — RF34) → último ponto: rota `completed` com
  `completionRate` 100 → exatamente uma insígnia e um código → segunda
  tentativa de uso do código → 409 com nenhum efeito; estoque: dois
  turistas competindo pela unidade final (exatamente um reserva),
  concessão com estoque 0 → 409 bloqueada sem alterar estado (código
  permanece válido), concessão com estoque → consome 1 unidade, marca
  usado, grava `pickupSpotId`/`concededBy`; remoção de rota → arquivada,
  histórico do inscrito intacto (progresso, insígnia, código legíveis).
- **Unit suite**: código gerado por CSPRNG com 128 bits de entropia,
  único sob volume, não derivável de contadores/identificadores, sem
  expiração.
- **Migrations**: as 7 tabelas do domínio gamification existem pós-migrate
  (e as unicidades chave: `route_id+tourist_id` ×3, `tourist_id+spot_id`,
  `code`).
- **Smoke/boundaries**: nenhum import cruzando fronteira privada (AST
  gate); nenhuma tag string fora de `core/tags.py`; nenhum schema sem
  `ApiModel`.

## Manual smoke (optional, running app)

```bash
# start the app (dev environment of the repo)
uvicorn passanorte_back.main:app --reload
```

1. `POST /api/v1/auth/admin/login` (admin do seed) → token.
2. `POST /api/v1/gamification/routes` com spots reais (criados via
   `POST /api/v1/tourist-spots`) e brinde embutido → anote `routeId`.
3. Login de turista (`POST /api/v1/tourists/...` — fluxo de autenticação
   turista existente) e `POST /api/v1/gamification/routes/{routeId}/enrollments`.
4. `GET /api/v1/gamification/enrollments/{id}` — todos os spots `pending`,
   `completionRate` 0.
5. Registre visitas chamando a seam de serviço (até a spec 010 não há
   endpoint HTTP de visita): uma sessão Python rápida chamando
   `register_spot_visit` cobre isso — ou confirme via o teste de
   integração, que é a validação primária.
6. Repita 4: `completionRate` sobe; na última visita, `status` =
   `completed`, insígnia e código presentes.
7. `PATCH /api/v1/gamification/prizes/{prizeId}` com `stockQuantity: 0`,
   após `POST /api/v1/gamification/redemptions` com o código e um ponto →
   409 `conflict` bloqueando a retirada com estoque zero.

Swagger UI (`/docs`) mostra todos os endpoints agrupados sob a tag
"Gamification".