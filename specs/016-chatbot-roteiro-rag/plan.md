# Implementation Plan: Chatbot de Planejamento de Roteiro (RAG) — RF38/RF39

**Branch**: `016-chatbot-roteiro-rag` | **Date**: 2026-11-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/016-chatbot-roteiro-rag/spec.md`

## Summary

Chatbot de planejamento de roteiro para turistas autenticados: sessões de
chat persistidas com histórico; mensagens em linguagem natural; retrieval
(RAG) sobre a base cadastrada de pontos turísticos e eventos (fontes
de verdade dos módulos 007/008) combinando filtros estruturados em SQL com
ranqueamento de relevância in-process; roteiro estruturado (ordem geográfica
razoável, horários sugeridos, custo total) montado deterministicamente em
código e ancorado aos candidatos recuperados, com narração em linguagem
natural gerada por provedor de IA generativa de free tier (RNF15), chave
exclusivamente via variáveis de ambiente e comportamento degradado quando
o provedor falta/falha (timeout ~30s).

## Technical Context

**Language/Version**: Python 3.13 (type hints em tudo)

**Primary Dependencies**: FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic,
httpx (cliente HTTP do provedor — verificado em pesquisa R1)

**Storage**: PostgreSQL (produção) / SQLite (testes), migración Alembic
`0011_chatbot_sessions`

**Testing**: pytest (unit / contract / integration / smoke), provedor
de IA simulado (fake injetável, zero chamada externa na suíte — FR-023)

**Target Platform**: backend monolito modular FastAPI (um processo, um
banco, um deploy); consumido por painel React e app Passaporte Kotlin

**Performance Goals**: pedidos ao provedor abortados em ~30s no pior caso
(FR-018/SC-005); listagem/histórico de sessões no padrão das demais
consultas simples (RNF11)

**Constraints**: nenhuma chamada de rede externa na suíte de testes;
nenhuma chave/segredo no repositório (env-only); sem hardcode de
localidade (RNF06); recuperação nunca depende exclusivamente de serviço
externo de embeddings (ver pesquisa R2)

**Scale/Scope**: catálogo de uma cidade (ordem de dezenas/centenas de
spots e eventos), turistas individuais com sessões indefinidamente
continuáveis → modelagem relacional simples, sem infraestrutura vetorial

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Evidence |
|---|---|---|
| Preamble 1 — um processo, um banco, um deploy | ✅ | Módulo `chatbot` dentro do monolito; sem serviço extra |
| Preamble 2 — módulo em `DOMAIN_MODULES` | ✅ | `chatbot` já listado em `core/modules.py`; tag `Chatbot` já registrada em `core/tags.py` |
| Preamble 3 — fronteiras via interfaces públicas | ✅ | Leia-se da base via `sa.table()` read-projections (precedente 014) + `tourists.services` público; nenhuma leitura direta de internals alheios |
| Preamble 4 — camadas próprias em `modules/chatbot/` | ✅ | `routes/services/repositories/schemas` já esqueletados; nenhuma infra nova em `core/` além de `Settings` |
| Preamble 6 — escritas entre domínios por serviço do dono | ✅/n/a | Chatbot escreve apenas suas próprias tabelas; leituras são read-only |
| I — ApiModel camelCase + ApiError + tag central | ✅ | Todos os schemas HTTP-bound herdam `core.schemas.ApiModel`; `ApiError` via `core.error_handlers`; tag aplicada em `core/routers.py` |
| II — Segurança/LGPD | ✅ | `require_tourist` (mesma dependência da visitation); conteúdo de chat não é dado sensível RNF08 (CPF/passaporte/telefone/e-mail); nenhuma credencial em código (env-only) |
| III — Test-first | ✅ | Tarefas test-first; contract + integration + unit; fake provider |
| IV — Geoespacial | ✅ | Ordenação da rota por Haversine entre coordenadas WGS-84 persistidas |
| V — Simplicidade (YAGNI) | ✅ | Sem banco vetorial, sem embedding externo, sem solver completo (greedy nearest-neighbor); provedor atrás de um único client injetável |
| VI — Portabilidade (RNF06) | ✅ | Cidade, categorias e idiomas vindos de `config/location.json`/`Settings`; zero nomes de locais no código |
| VII — Código em inglês | ✅ | Módulos/classes/funções/rotas em inglês; conteúdo de usuário (texto de chat, narração) em pt-BR conforme idioma configurado |
| Quality gates | ✅ | Ruff, fronteiras AST, ApiModel/tag gates, migration revisada (0011) |

Nenhuma violação → `Complexity Tracking` permanece vazio.

## Project Structure

### Documentation (this feature)

```text
specs/016-chatbot-roteiro-rag/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (chatbot-api.md)
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
src/passanorte_back/modules/chatbot/
├── __init__.py                     # module docstring
├── repositories/
│   ├── __init__.py                 # public persistence surface (own tables)
│   ├── chat.py                     # ChatSession, ChatMessage entities + queries
│   └── read_projections.py         # sa.table() read-only catalog projections (research R5)
├── services/
│   ├── __init__.py                 # public service interface (routes layer only)
│   ├── chat.py                     # orchestration: sessions, messages, degraded mode
│   ├── retrieval.py                # RAG pipeline: SQL filters + relevance ranking
│   ├── planning.py                 # itinerary assembly: anchor/filter, Haversine order, times, cost
│   ├── validator.py                # FR-021 constraint validator (reusable by tests)
│   └── providers.py                # injectable LLM client (httpx, OpenAI-compatible)
├── schemas/
│   ├── __init__.py                 # HTTP-bound DTO re-exports
│   └── chat.py                     # ApiModel request/response schemas (camelCase)
└── routes/
    ├── __init__.py                 # route module import (side-effect decorators)
    └── chat.py                     # endpoints (tag applies via core/routers.py)

migrations/
└── versions/20261106_0011_chatbot_sessions.py   # chat_sessions + chat_messages

tests/
├── contract/test_chatbot_api.py    # schemas, status codes, auth, error payloads
├── integration/test_chatbot_flow.py# end-to-end: session → messages → history (fake provider)
├── integration/test_chatbot_degraded.py # story 4 scenarios (no key, error, timeout, bad output)
├── helpers/
│   ├── fake_llm.py                 # provider fakes (FR-023 — no network)
│   └── chatbot_seeds.py            # shared tourist/spot/event seeds (T033)
└── unit/chatbot/
    ├── test_retrieval.py           # FR-020 pipeline de recuperação
    ├── test_planning.py            # Haversine order, times, cost, FR-024 event-day
    ├── test_validator.py           # FR-021 constraint
    └── test_localization.py        # FR-019 picker + SC-007 config portability (T036)
```

**Structure Decision**: módulo canônico único `chatbot` dentro do monolito
modular existente (preamble 2/4). Nenhuma nova infra em `core/` além de
campos em `Settings`. Leituras cross-domain usam o padrão `sa.table()`
read-projection do feature 014 (`dashboard/repositories/read_projections.py`)
— sem import de models de outros módulos.

## Complexity Tracking

> Vazio — nenhuma violação de constituição a justificar.
