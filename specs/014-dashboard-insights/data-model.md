# Data Model: Dashboard e Insights (014-dashboard-insights)

Owner of the model: `dashboard` module. Only one new table; everything else
is a read-only projection of existing tables (research R1).

## 1. New table — `access_events` (dashboard-owned)

Immutable access-log ledger (spec FR-008/FR-011). One row per
tourist-authenticated HTTP request (best-effort insert, FR-022).

| Column        | Type        | Constraints                                   | Notes                                     |
| ------------- | ----------- | --------------------------------------------- | ----------------------------------------- |
| `id`          | int         | PK, autoincrement                             |                                           |
| `tourist_id`  | int         | NOT NULL, FK `tourists.id`, indexed           | tourista que fez a requisição             |
| `occurred_at` | datetime    | NOT NULL, UTC, indexed (`ix_access_events_at`) | instante bruto da requisição              |
| `day`         | date        | NOT NULL, indexed (`ix_access_events_day`)    | `occurred_at` convertido para o fuso da cidade (`ZoneInfo(city_timezone)`) — RNF06; base do agrupamento "turista único por dia" |

Composite index `ix_access_events_tourist_day` (`tourist_id`, `day`) —
serves `COUNT(DISTINCT tourist_id) GROUP BY day` and period scans.

No unique constraint on (`tourist_id`, `day`): repeated requests on the
same day each append a row; the uniqueness lives in the query
(`DISTINCT`), never in the write path.

Lifecycle: immutable, insert-only (no update/delete paths in the
repository). Retention/expurgo: out of scope this phase (spec Deferred).

## 2. Read-only projections (dashboard's own SELECT layer)

Lightweight, non-registered `sa.table()` constructs in
`repositories/read_projections.py` — column names must mirror the owner
schemas; never inserted/updated (FR-021). Covered by the boundary gate
(no owner-module imports) and by every integration test (schema parity).

| Projection          | Source table          | Columns used                                                             |
| ------------------- | --------------------- | ------------------------------------------------------------------------ |
| `visitations_v`     | `visitations` (011)   | `id`, `tourist_id`, `tourist_spot_id`, `visited_at`                      |
| `tourist_spots_v`   | `tourist_spots` (007) | `id`, `name`, `latitude`, `longitude`                                    |
| `tourists_v`        | `tourists` (003)      | `id`, `country_of_origin`                                                |
| `tourist_interests_v` | `tourist_interests` (003) | `tourist_id`, `category_key`                                      |

Sensitive columns (`*_encrypted`, `*_lookup`, `password_hash`) are **not**
projected — the dashboard never selects them (LGPD, constitution II).

## 3. Existing entities consumed (unchanged, for reference)

- **`visitations`** — immutable visit ledger; `visited_at` indexed. Base of
  heat-map weights, ranking counts and the visitor population.
- **`tourist_spots`** — `name`, `latitude`, `longitude`; soft delete
  (`removed_at`); historical visits of removed spots still count (R7).
- **`tourists`** — `country_of_origin` (plain text, ≤100 chars); the only
  projected field.
- **`tourist_interests`** — (`tourist_id`, `category_key`) pairs, unique
  per pair; N rows per tourist with N declared interests.

## 4. Configuration — `regions` block (data, RNF06)

Optional list added to `config/location.json`:

```json
{
  "city": "Passa Quatro",
  "regions": [
    { "key": "waterfalls", "label": "Cachoeiras",
      "spots": ["Cachoeira Édem", "Cachoeira do Serra"] }
  ]
}
```

- `key`/`label`: identifiers/display of the region (keys unique).
- `spots`: tourist-spot **names** (Portuguese data). Names not matching
  any registered spot are skipped (logged); regions resolve at query time —
  adding a region never requires a migration.
- Aggregate (RF06 region mode): weight = Σ visits of the constituent
  spots; coordinate = centroid of the spots' coordinates
  (mean of latitudes, mean of longitudes). Region with zero constituent
  spots resolves to zero visits and no marker.
- Absence of the block ⇒ `groupBy=region` rejeitado (422, FR-005).

## 5. Derived metric definitions (canonical glossary)

| Métrica                | Definição (SQL-set)                                                                                       |
| ---------------------- | --------------------------------------------------------------------------------------------------------- |
| Peso do marcador (spot)   | `COUNT(*)` de `visitations` do ponto dentro da janela (inclusiva)                                        |
| Peso do marcador (região) | Σ dos pesos dos pontos da região; coordenada = centroid                                                  |
| Turistas únicos/dia       | `COUNT(DISTINCT tourist_id)` por `access_events.day`                                                     |
| Total de acessos          | `COUNT(*)` de `access_events` na janela                                                                  |
| Visitantes (população)    | `COUNT(DISTINCT tourist_id)` de `visitations` na janela                                                  |
| Share por país            | `ROUND(100 * COUNT(DISTINCT tourist_id) / total_visitantes, 1)` por `country_of_origin`                  |
| Share por interesse       | `ROUND(100 * COUNT(DISTINCT tourist_id) / total_selecoes, 1)` por `category_key` (turista vale N vezes)  |
| Ranking                   | `GROUP BY spot ORDER BY COUNT DESC LIMIT N`; só pontos com ≥ 1 visita no período                          |

Every number is reconstructible from stored rows (SC-007) — no synthetic
metric exists in the module.
