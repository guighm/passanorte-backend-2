# Quickstart: Chatbot de Planejamento de Roteiro (RAG)

Feature: `016-chatbot-roteiro-rag` · valida FR-020–023, SC-001–006.

## Pré-requisitos

- Python 3.13 + ambiente do projeto (`uv sync` ou equivalente).
- App sobe **sem** chave de LLM: modo degradado é o default do ambiente.

## 1. Rodar a suíte desta feature (zero rede externa — FR-023)

```bash
uv run pytest tests/unit/chatbot tests/contract/test_chatbot_api.py \
              tests/integration/test_chatbot_flow.py \
              tests/integration/test_chatbot_degraded.py
```

Esperado: verde. Casos que provam cada critério da spec:

| Teste | Critério |
|---|---|
| `tests/unit/chatbot/test_retrieval.py` | FR-020/SC-001 — query relevante retorna os pontos certos da base de teste |
| `tests/unit/chatbot/test_planning.py` | FR-009/010/011/024 — horário, custo, ordem Haversine, evento do dia |
| `tests/unit/chatbot/test_validator.py` | FR-021/SC-002 — constraint: ids anchíveis, horário, soma de ingressos |
| `tests/integration/test_chatbot_flow.py` | FR-022/SC-004 — histórico persiste entre mensagens; roteiro só itens existentes |
| `tests/integration/test_chatbot_degraded.py` | Story 4/SC-005 — sem chave/erro/timeout/saída malformada → resposta conversacional, sem 5xx |

Gates globais (já existentes): `uv run pytest tests/smoke` (fronteiras AST,
tags), `uv run ruff check`.

## 2. Fluxo manual em dev (com app subindo e BD de dev)

```bash
# 2.1 subir a API (sem CHATBOT_LLM_API_KEY → degradado)
uv run dev

# 2.2 entrar como turista (JWT do fluxo de auth existente) e criar sessão
curl -s -H "Authorization: Bearer $TOKEN" -X POST localhost:8000/chatbot/sessions

# 2.3 enviar mensagem → resposta em modo degradado (itinerary null)
curl -s -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"text":"Roteiro de cachoeiras amanhã de manhã"}' \
     localhost:8000/chatbot/sessions/1/messages

# 2.4 recuperar histórico → as 2 mensagens persistem
curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/chatbot/sessions/1
```

Esperado (sem chave): `2.3` devolve `201` com `assistantMessage.content`
de indisponibilidade e `itinerary: null`; `2.4` lista a conversa.

## 3. Fluxo manual com provedor (opcional, fora do CI)

```bash
export CHATBOT_LLM_API_KEY="…env-only…"
export CHATBOT_LLM_BASE_URL="https://…/v1"   # endpoint OpenAI-compatible
export CHATBOT_LLM_MODEL="modelo-do-provedor"
uv run dev
```

Repetir `2.2–2.4`. Esperado: `assistantMessage` com narração natural +
`itinerary` estruturado (itens ordenados, `suggestedAt`, `totalCostCents`
= soma dos ingressos), renderizável no Passaporte sem transformação.

## 4. Verificações de aceite rápido

- [ ] Suíte completa da feature verde sem nenhum socket externo (FR-023).
- [ ] Constraint do roteiro (FR-021) provada no teste de validator.
- [ ] Histórico persiste entre mensagens (FR-022) na integração.
- [ ] Degradado: 4 cenários → 201 + texto padrão, nenhum 5xx, sessão íntegra.
- [ ] `ruff check` limpo; fronteiras AST verdes (nenhum import cruzado).

Detalhes de contrato: [contracts/chatbot-api.md](./contracts/chatbot-api.md).
Modelo de dados: [data-model.md](./data-model.md). Decisões: [research.md](./research.md).
