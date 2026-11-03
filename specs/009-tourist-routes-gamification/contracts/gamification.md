# Contracts: Tourist Routes and Gamification (feature 009)

Endpoints do módulo `gamification`, todos montados no router canônico
`MODULE_ROUTERS["gamification"]` (prefixo `/api/v1/gamification`, tag
central "Gamification" aplicada em `core/routers.py` — nenhum route file
escreve tag). Todo schema HTTP-bound herda `ApiModel` (camelCase estrito,
`extra="forbid"`, snake_case rejeitado com 422); toda falha devolve o
payload único `ApiError` (`errorCode`, `message`, `details`) — taxonomia:
401 `authentication_failed`, 403 `authorization_failed`, 404
`resource_not_found`, 409 `conflict`, 422 `validation_error`.

Atores: **admin** (`require_admin`), **turista** (`require_tourist`),
**staff** (`require_staff` = admin OU employee, R6). Turista só lê o
próprio estado (FR-013).

## 1. Route management (admin — RF18/RF19; audit por escrita)

### `POST /api/v1/gamification/routes` (201)

Cria a rota **e o brinde embutido** (Q1: entidade de catálogo, nasce com a
rota). `spots` não pode ser vazio; todo `spotId` deve referenciar ponto
ativo (404 caso contrário; removido → 404); `displayOrder`s não lacunares
podem ser normalizados pelo serviço (serviço normaliza posições).

```json
// request
{
  "name": "Rota Histórica do Centro",
  "description": "Caminhada pelos pontos históricos de Passa Quatro.",
  "spots": [{"spotId": 1, "displayOrder": 1}, {"spotId": 2, "displayOrder": 2}],
  "prize": {"name": "Caneca do Festival", "initialStock": 10}
}
// response 201 — TouristRouteView
{
  "id": 5,
  "name": "Rota Histórica do Centro",
  "description": "Caminhada pelos pontos históricos de Passa Quatro.",
  "spots": [{"spotId": 1, "displayOrder": 1}, {"spotId": 2, "displayOrder": 2}],
  "prize": {"id": 3, "name": "Caneca do Festival", "stockQuantity": 10},
  "status": "active"
}
```

- 422: shape inválida (nome/descrição vazios, spots vazio, `initialStock` < 0)
- 404: `spotId` inexistente/remanejado (payload completo rejeitado)
- 403/401: não-admin

### `PATCH /api/v1/gamification/routes/{routeId}` (200)

Edição parcial (todos os campos opcionais; lista de spots fornecida é
revalidada integralmente; brinde não é trocável — vinculado na criação,
spec FR-002 esclarecida na análise F1). Inscrições existentes permanecem
válidas contra a rota atualizada.

- 404: rota inexistente/arquivada ou spot inválido
- 422: spots vazio ou duplicado na lista
- 200 com corpo revalidado; sem mudança efetiva → 200 sem audit (007 precedent)

### `DELETE /api/v1/gamification/routes/{routeId}` (204)

Arquiva a rota (`removed_at`); para de aparecer em listagens e de aceitar
inscrições (404); histórico de inscritos/progresso/insígnias/códigos
intacto (FR-012, Removal Decision).

- 404: rota inexistente/arquivada
- 204 sem corpo; 1 audit `route.delete`

### `GET /api/v1/gamification/routes` (200)

Listagem. **Turista**: apenas rotas ativas (browsing para inscrição —
RF29). **Admin**: query opcional `?includeArchived=true` expõe também as
arquivadas (Removal Decision). Sem paginação nesta versão (YAGNI, 008
precedent). Ordenação estável por `(name, id)`.

```json
{"items": [{"id": 5, "name": "…", "description": "…", "spotCount": 4,
            "prize": {"id": 3, "name": "Caneca do Festival", "stockQuantity": 10},
            "status": "active"}]}
```

### `GET /api/v1/gamification/routes/{routeId}` (200)

Detalhe completo (mesmo corpo de `TouristRouteView` + spots por
`displayOrder`). Admin: qualquer estado. Turista: ativa apenas (404 em
arquivada — Removal Decision).

## 2. Enrollment e progresso (turista — RF29/RF30)

### `POST /api/v1/gamification/routes/{routeId}/enrollments` (201)

Inscrição do turista autenticado (`require_tourist` — 403 para
admin/employee). Cria inscrição `in_progress` com todos os spots pendentes,
`completionRate` 0.

- 409 `conflict`: inscrição duplicada do mesmo turista na mesma rota
  (original intacto — SC-006)
- 404: rota inexistente/arquivada
- 201 resposta: enrollment summary (`routeId`, `status`, `completionRate` 0)

### `GET /api/v1/gamification/enrollments` (200)

As inscrições do turista autenticado (nenhum outro é legível — FR-013),
com progresso resumido: status, `completionRate`, `completedAt` null
quando in_progress. Ordenado por `createdAt` desc.

### `GET /api/v1/gamification/enrollments/{enrollmentId}` (200)

Progresso completo (RF30): spots da rota por ordem de display com
`visited` booleano, totais e `completionRate` (inteiro 0–100). Quando
`completed`: embute a **insígnia** (`grantedAt`) e o **código de resgate**
(`/code`, `status`) do titular — jamais de outro turista (FR-013).

```json
{
  "id": 8, "routeId": 5, "status": "completed", "completionRate": 100,
  "spots": [{"spotId": 1, "visited": true}, {"spotId": 2, "visited": true}],
  "visitedCount": 2, "totalSpots": 2,
  "badge": {"routeId": 5, "grantedAt": "2026-11-02T12:00:00Z"},
  "redemptionCode": {"code": "k2jH9mPqLxZ_", "status": "unused"}
}
```

- 404: inscrição inexistente **ou** de outro turista (indistinguível — FR-013)

## 3. Prize stock (admin — RF20)

### `PATCH /api/v1/gamification/prizes/{prizeId}` (200)

Ajuste de estoque: `{"stockQuantity": 25}` — ≥ 0 obrigatório; rejeitado
(422) abaixo de `reserved_quantity` já comprometida (edge case da spec).

- 404: brinde inexistente; 403/401: não-admin; 1 audit `prize.stock_update`

## 4. Prize concession (staff — RF36, Q3)

### `POST /api/v1/gamification/redemptions` (201)

Registra a retirada física contra um código (uso único, consumindo
exatamente uma unidade de estoque; guarda atômica R4):

```json
// request — require_staff (admin OU employee)
{"code": "k2jH9mPqLxZ_", "spotId": 2}
// response 201
{"code": "k2jH9mPqLxZ_", "prize": {"id": 3, "name": "Caneca do Festival"},
 "routeId": 5, "touristId": 11, "pickupSpotId": 2, "concededBy": "maria.panel",
 "usedAt": "2026-11-02T14:30:00Z"}
```

- 409 `conflict`: código já usado **ou** estoque insuficiente (código
  permanece válido/unused, estoque inalterado — never negative)
- 404: código inexistente ou `spotId` inexistente (concessão não registrada)
- 422: shape (`code` vazio, `spotId` ausente)
- 401/403: sem token / não-staff (turista não concede)

## 5. Domain service seam (não-HTTP; consumida por visitation — spec 010)

`modules/gamification/services` re-exporta (precedente `events.services`):

```python
register_spot_visit(session, *, tourist_id: int, tourist_spot_id: int) -> list[VisitRouteOutcome]
```

- Grava a visita (UNIQUE `tourist_id, tourist_spot_id`; re-submissão é
  no-op idempotente e devolve o estado corrente).
- Atualiza o progresso de TODAS as inscrições `in_progress` do turista que
  contêm o ponto em uma transação (RF34); conclui a rota, emite insígnia +
  código + reserva do brinde na mesma transação quando é a última pendência
  (idempotente — R2).
- Retorna por rota afetada: `route_id`, `completion_rate` (0–100),
  `completed` (Q5). Erros: `TouristMissingError`/`TouristSpotMissingError`
  (chamador mapeia para 4xx — a seam é de domínio, não HTTP).

## 6. Error matrix (resumo dos status por endpoint)

| Endpoint | 201/200/204 | 401 | 403 | 404 | 409 | 422 |
|---|---|---|---|---|---|---|
| POST /routes | 201 | ✔ | não-admin | spot inexistente | – | shape/spots vazios |
| PATCH /routes/{id} | 200 | ✔ | não-admin | rota/spot inexistente | – | shape/revalidação |
| DELETE /routes/{id} | 204 | ✔ | não-admin | rota inexistente | – | – |
| GET /routes | 200 | ✔ | – | – | – | – |
| GET /routes/{id} | 200 | ✔ | – | inexistente (turista: arquivada) | – | – |
| POST /routes/{id}/enrollments | 201 | ✔ | não-turista | rota inexistente/arquivada | duplicada | – |
| GET /enrollments | 200 | ✔ | – | – | – | – |
| GET /enrollments/{id} | 200 | ✔ | – | inexistente/de outro turista | – | – |
| PATCH /prizes/{id} | 200 | ✔ | não-admin | brinde inexistente | – | < min reservado/negativo |
| POST /redemptions | 201 | ✔ | não-staff | código/spot inexistente | usado/estoque 0 | shape |