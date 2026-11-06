# Data Model: Chatbot de Planejamento de Roteiro (RAG) — RF38/RF39

Feature: `016-chatbot-roteiro-rag` · Date: 2026-11-06

## Entidades do módulo (donos: `chatbot`)

### `chat_sessions`

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | int PK, autoincrement | |
| `tourist_id` | int, FK → `tourists.id` | dono exclusivo da sessão (FR-001); sem exclusão de turista nesta fase → FK RESTRICT implícito |
| `created_at` | datetime, default UTC now | |

Sem estado de encerramento (clarificação Q1) — toda sessão permanece
continuável. Listagem sempre filtrada por `tourist_id` do token.

### `chat_messages`

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | int PK, autoincrement | |
| `session_id` | int, FK → `chat_sessions.id` | mensagem pertence a uma sessão |
| `role` | String(20) | `'user'` (turista) ou `'assistant'` (chatbot) |
| `content` | Text | texto natural da mensagem (pt-BR / idioma configurado) |
| `itinerary` | JSON, nullable | roteiro estruturado embutido (clarificação Q2); `NULL` em mensagens `user` e em respostas degradadas |
| `created_at` | datetime, default UTC now | ordem temporal da conversa (ordenar por `id`/`created_at`) |

**`itinerary` (JSON) — shape do snapshot persistido (FR-005, FR-025, SC-006):**

```json
{
  "generatedAt": "2026-11-06T10:00:00+00:00",
  "targetDate": "2026-11-06",
  "totalCostCents": 2500,
  "items": [
    {
      "kind": "spot",                       // "spot" | "event"
      "refId": 7,                           // id em tourist_spots/events
      "displayName": "Cachoeira Édem",      // snapshot de exibição (FR-025)
      "suggestedAt": "2026-11-06T09:30:00-03:00",
      "ticketCostCents": 0                  // 0 p/ entrada livre
    },
    {
      "kind": "event",
      "refId": 3,
      "displayName": "Festival de Inverno",
      "suggestedAt": "2026-11-06T11:00:00-03:00",
      "ticketCostCents": 2500
    }
  ]
}
```

Campos `refId`/`kind` ancoram o item ao registro da base (FR-006/
constraint FR-021); `displayName`/`suggestedAt`/`ticketCostCents` são o
snapshot de exibição do momento da geração — o Passaporte renderiza só da
mensagem, mesmo se o item mudar/excluir depois (Q6).

## Projeções de leitura cross-domain (read-only, `sa.table()`)

Nomes idênticos aos models donos (autoridade: migrations/007/008/003):

| Projeção | Colunas espelhadas | Uso |
|---|---|---|
| `tourist_spots` | `id, name, description, latitude, longitude, status, removed_at` | candidatos ativos |
| `tourist_spot_schedule_entries` | `spot_id, weekday, opens_at, closes_at` | filtro horário (FR-009) |
| `tourist_spot_categories` | `spot_id, category_key` | match de interesses (FR-012) + relevância |
| `events` | `id, spot_id, occurrence_date, description, ticket_price_cents` | candidatos de evento do dia alvo (FR-024, FR-010) |
| `tourist_interests` | `tourist_id, category_key` (conferir colunas exatas no model 003) | priorização de interesses (FR-012) |

Nenhuma escrita nestas tabelas. Nenhum import de models destes módulos
(fronteira AST).

## Regras de validação/consistência (resumo)

- Só spots com `status = 'open'` e `removed_at IS NULL` entram como
  candidatos (FR-006/FR-009).
- Spot candidato só no dia da semana com `ScheduleEntry` cobrindo a hora
  alvo (`opens_at ≤ t < closes_at`).
- Evento candidato só com `occurrence_date` = dia alvo (FR-024).
- Item do roteiro só após ancoragem a candidato (FR-006); ordem por
  greedy nearest-neighbor Haversine (WGS-84 decimal, FR-011/SC-003);
  custo total = Σ `ticket_price_cents` de eventos selecionados (FR-010);
  eventos: custo = preço na data do evento.
- Degradado: mensagem do turista persiste; resposta do assistente sem
  `itinerary` (R4).

## Ciclo de vida

- Sessão: criada por POST; sem transições; sempre continuável.
- Mensagem: inserida apenas por fluxo do módulo (user no POST; assistant
  após provider/validador); nunca editada/excluída.
- Roteiro: imutável após persistir (snapshot).
