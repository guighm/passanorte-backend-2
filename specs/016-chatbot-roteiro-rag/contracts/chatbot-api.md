# API Contract: Chatbot (tag `Chatbot`)

Feature: `016-chatbot-roteiro-rag` · Date: 2026-11-06

Prefixo `/chatbot` e tag aplicados por `core/routers.py` (routes nunca
escrevem tag). Todos os schemas HTTP-bound herdam `core.schemas.ApiModel`
(chaves JSON camelCase, `extra="forbid"`); toda falha usa `ApiError`
(`errorCode`, `message`, `details`). Autenticação: JWT Bearer; endpoints
exclusivos de turista (`require_tourist`) — FR-001.

## Endpoints

### `POST /chatbot/sessions` — cria sessão de conversa

Resposta `201`:

```json
{
  "sessionId": 12,
  "createdAt": "2026-11-06T10:30:00Z"
}
```

Falhas: `401` (não autenticado), `403` (não turista), `409` — não há;
sempre cria.

### `GET /chatbot/sessions` — lista sessões do turista logado

Resposta `200`:

```json
{
  "sessions": [
    { "sessionId": 12, "createdAt": "2026-11-06T10:30:00Z", "lastMessageAt": "2026-11-06T10:45:00Z" }
  ]
}
```

### `GET /chatbot/sessions/{sessionId}` — histórico completo

Resposta `200`:

```json
{
  "sessionId": 12,
  "messages": [
    {
      "messageId": 41,
      "role": "user",
      "content": "Quero roteiro de cachoeiras grátis amanhã de manhã",
      "itinerary": null,
      "createdAt": "2026-11-06T10:31:00Z"
    },
    {
      "messageId": 42,
      "role": "assistant",
      "content": "Claro! Comece pela Cachoeira da Saudade às 9h…",
      "itinerary": {
        "generatedAt": "2026-11-06T10:31:05Z",
        "targetDate": "2026-11-07",
        "totalCostCents": 0,
        "items": [
          {
            "kind": "spot",
            "refId": 7,
            "displayName": "Cachoeira da Saudade",
            "suggestedAt": "2026-11-07T09:00:00-03:00",
            "ticketCostCents": 0
          }
        ]
      },
      "createdAt": "2026-11-06T10:31:05Z"
    }
  ]
}
```

Falhas: `401` (não autenticado), `404` (sessão inexistente **ou** de outro
turista — não existe para quem pergunta; evita enumeração).

### `POST /chatbot/sessions/{sessionId}/messages` — envia mensagem

Request:

```json
{ "text": "Quero cachoeiras grátis amanhã de manhã" }
```

`422` se schema inválido (`ApiError`, extra="forbid").

Resposta `201` (a própria mensagem do turista + resposta do chatbot):

```json
{
  "userMessage": { "messageId": 41, "role": "user", "content": "…", "itinerary": null, "createdAt": "…" },
  "assistantMessage": {
    "messageId": 42,
    "role": "assistant",
    "content": "Claro! Sugiro começar pela Cachoeira da Saudade às 9h…",
    "itinerary": { "…": "… mesmo shape do GET acima" },
    "createdAt": "…"
  }
}
```

**Modo degradado (FR-018)** — provedor indisp./timeout/malformado:
resposta `201` normal, mas `assistantMessage.itinerary = null` e
`content` = texto padrão de indisponibilidade (localizável). Nenhum
endpoint devolve 5xx por falha do provedor.

Falhas: `401`, `403`, `404` (sessão inexistente/outra pessoa), `422`.

## Notas de mapeamento camelCase

- `sessionId`, `createdAt`, `lastMessageAt`, `messageId`
- `itinerary.totalCostCents`, `itinerary.ticketCostCents`,
  `itinerary.refId`, `itinerary.suggestedAt`, `itinerary.displayName`
- Snakes internos (`ticket_price_cents` → `ticketCostCents`) só na
  fronteira HTTP, via `ApiModel`.

## Contratos não-HTTP (interfaces internas)

- `chatbot.services.providers.LlmProvider` (protocolo): `complete(...)`
  — implementado por `HttpLlmProvider` (httpx) e fakes de teste.
- `chatbot.services.retrieval.retrieve_candidates(session, tourist_id,
  query, at)` → candidatos + scores (FR-020).
- `chatbot.services.validator.validate_itinerary(plan, candidates,
  session, target)` → bool/erros (FR-021) — reutilizado pelos testes
  de constraint.
