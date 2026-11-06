# Research: Chatbot de Planejamento de Roteiro (RAG) — RF38/RF39

Feature: `016-chatbot-roteiro-rag` · Date: 2026-11-06 · Spec: [spec.md](./spec.md)

## R1 — Acesso ao provedor de IA generativa (RNF15, FR-017)

**Decision**: cliente HTTP injetável (`services/providers.py`), protocolo
compatível com API de chat-completions OpenAI (padrão de facto suportado
por todos os provedores de free tier: Groq, OpenRouter, Google AI Studio
via endpoint compatível, etc.). Configuração por `Settings`:
`CHATBOT_LLM_API_KEY` (default vazio = degradado), `CHATBOT_LLM_BASE_URL`,
`CHATBOT_LLM_MODEL`, `CHATBOT_TIMEOUT_SECONDS` (default 30).

**Rationale**: abstração de um único client evita SDK de provedor
específico (YAGNI, troca livre); httpx já está disponível no stack do
FastAPI (`fastapi[standard]`; confirmado em implementação — se ausente,
adicionar dependência explícita); timeout aplicado no cliente garante
FR-018/SC-005. App sobe com chave ausente — o provider reporta
`unavailable` e o serviço responde em modo degradado.

**Alternatives considered**:
- SDK oficial de um provedor único → acoplamento, troca custosa;
  rejeitado.
- Abstração com embeddings + chat → dobraria a superfície de integração
  nesta fase; rejeitado (ver R2).

## R2 — Estratégia de recuperação (RAG sobre a base, FR-007, FR-020)

**Decision**: recuperação em duas etapas, 100% determinística, sem
serviço externo de embeddings:

1. **Filtros estruturados em SQL** via `sa.table()` read-projections
   (padrão 014) sobre `tourist_spots` (ativos, sem `removed_at`), `events`
   (`occurrence_date` = dia alvo), horários de funcionamento e categorias.
2. **Ranqueamento de relevância in-process**: normalização lexical pt-BR
   (lowercase, sem acentos, stopwords básicas removidas) e score de
   sobreposição de tokens entre o pedido do turista e
   nome/descrição/labels de categoria; boost para categorias de interesse
   do turista e penalização de custo alto.

**Rationale**: catálogo de uma cidade é pequeno (dezenas/centenas) —
relevância lexical normalizada + filtros estruturados resolve o problema
real com zero dependência externa, é determinístico (testável em CI —
FR-020/SC-001) e roda offline (FR-023). "Similaridade de significado" é
atendida pela normalização (acentos/plural/stopwords) sobre o texto
cadastrado.

**Alternatives considered**:
- Embeddings do provedor + similaridade vetorial → rejeitado nesta fase:
  adicionaria dependência externa ao caminho de recuperação (quebraria
  recuperação testável/CI offline e degradaria com provedor fora, mesmo
  para perguntas triviais). Ponto de troca futuro: `retrieval.py` é
  modular — uma fase futura pode inserir um scorer vetorial atrás da
  mesma interface.
- Banco vetorial (pgvector etc.) → infra extra sem necessidade no scale
  atual; rejeitado (YAGNI).

## R3 — Construção do roteiro (FR-005/006/009–012, RF39)

**Decision**: montagem estrutural 100% determinística em código
(`services/planning.py`); o LLM participa como **narrador/seletor**, nunca
como autor da estrutura:

1. `retrieval.py` devolve candidatos válidos (spot aberto no momento alvo
   conforme `tourist_spot_schedule_entries`; evento só do dia alvo —
   FR-024; custo = `ticket_price_cents`, spot = 0).
2. LLM recebe o JSON compacto dos candidatos e devolve
   `{"text": ..., "spotIds": [...], "eventIds": [...]}`.
3. `validator.py` ancora cada id devolvido contra o conjunto recuperado
   (FR-006): id fora do conjunto → item descartado; saída não-JSON/insuficiente →
   degradado (R4).
4. `planning.py` aplica a ordem final por greedy nearest-neighbor com
   Haversine (FR-011/SC-003), horários sugeridos sequenciais (dwell
   configurável `CHATBOT_DWELL_MINUTES`, default 60) respeitando o horário
   de funcionamento e custo total = soma dos ingressos (FR-010).
5. Snapshot de exibição (id + nome/hora/custo do momento) é embutido na
   mensagem do assistente (FR-025/SC-006).

**Rationale**: constituição IV ("nunca inventar dados") + constraint
testável (FR-021) exigem que a estrutura não dependa da criatividade do
LLM; o LLM adiciona personalização de seleção e linguagem natural.

**Alternatives considered**:
- Confiar no LLM para ordem/horários e apenas validar → a validação
  rejeitaria saídas válidas com frequência (LLMs erram Haversine/hora);
  rejeitado.
- Solver completo de otimização (TSP) → desnecessário para ~6 itens;
  greedy é suficiente para "rota razoável" (spec, YAGNI).

## R4 — Comportamento degradado (FR-018, Story 4)

**Decision**: classificar o problema em `ProviderUnavailable`
(chave ausente) / `ProviderError` (rede, HTTP non-2xx, timeout ~30s) /
`ProviderMalformedOutput` (não-JSON, ids não ancoráveis em nada). Em todos
os casos: mensagem do turista **é** persistida; mensagem do assistente
persistida com texto padrão de indisponibilidade localizável (FR-019) e
**sem** roteiro; nenhum erro opaco/HTTP 5xx para o turista; sessões
anteriores intactas.

**Rationale**: a história 4 exige resposta conversacional, não exceção;
persistir ambos os lados mantém a coesão da conversa (histórico sensato)
e é trivialmente testável com fakes.

## R5 — Leituras cross-domain (preamble 3)

**Decision**: read-projections `sa.table()`/`sa.column()` em
`repositories/` do chatbot espelhando apenas as colunas usadas, com os
mesmos nomes de tabelas/colunas de `migrations` (autoridade =
models dos donos):

- `tourist_spots(id, name, description, latitude, longitude, status, removed_at)`
- `tourist_spot_schedule_entries(spot_id, weekday, opens_at, closes_at)`
- `tourist_spot_categories(spot_id, category_key)`
- `events(id, spot_id, occurrence_date, description, ticket_price_cents)`
- `tourist_interests(tourist_id, category_key)` (checar colunas exatas em
  `tourists/repositories/tourist_interests.py` na implementação)

Intuições de configuração (cidade, idiomas, categorias) via
`core.config`/`Settings`. Escritas: **nenhuma** fora do domínio chatbot.

**Rationale**: precedente consolidado no 014 (dashboard); fronteiras AST
permanecem verdes; evita inflar interfaces públicas dos módulos donos com
funções de leitura que ninguém mais usa.

## R6 — Modelo de dados do módulo (FR-001–004, FR-008, FR-025)

**Decision** (detalhes em [data-model.md](./data-model.md)):
`chat_sessions(id, tourist_id FK→tourists.id, created_at)` e
`chat_messages(id, session_id FK ON DELETE RESTRICT, role
'user'|'assistant', content Text, itinerary JSON NULL, created_at)`.
Alembic `20261106_0011_chatbot_sessions.py`. Roteiro embutido na mensagem
(clarificação Q2) com snapshot de exibição (clarificação Q6).

**Rationale**: 2 tabelas, sem estado de encerramento (clarificação Q1);
FK restrita — exclusão de turista não existe nesta fase (assumption da
spec).

## R7 — Contrato HTTP (FR-016, I-ApiModel)

**Decision**: endpoints sob prefixo `/chatbot` (criado por
`core/routers.py` a partir de `DOMAIN_MODULES`; tag `Chatbot` automática —
arquivos de rota nunca escrevem tag). Schemas herdam `ApiModel`
(camelCase, `extra="forbid"`); falhas sempre `ApiError`. Autenticação
turista via `Depends(require_tourist)` (mesmo padrão da visitation).
Detalhes em [contracts/chatbot-api.md](./contracts/chatbot-api.md).

## R8 — Configuração (FR-017, RNF06, VI)

**Decision**: novos campos em `core/config.py Settings` —
`chatbot_llm_api_key: str | None = None`, `chatbot_llm_base_url: str | None = None`,
`chatbot_llm_model: str | None = None`, `chatbot_timeout_seconds: int = 30`,
`chatbot_dwell_minutes: int = 60`. Nenhum novo campo obrigatório — falta
de chave não impede o boot (degradado). Cidade/idiomas/categorias
continuam vindo de `config/location.json` via `Settings.resolved_*`.

## R9 — Testologia (III-Test-first, FR-020–023, SC-001–005)

**Decision**: fake provider injetável por dependency override no app +
construção direta dos serviços em unit tests (seeds via
`sessionfactory_for` com `session.commit()` explícito — memória do
projeto). Casos críticos: recuperação correta (base de controle),
constraint do roteiro (validator), persistência entre mensagens, degradado
(4 cenários), Haversine/horário/custo. Proibido: chamada real de rede —
provider sempre fake/mock.
