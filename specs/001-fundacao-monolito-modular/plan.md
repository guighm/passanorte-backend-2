# Implementation Plan: Fundação do Monolito Modular Backend PassaNorte

**Branch**: `001-fundacao-monolito-modular` | **Date**: 2026-10-30 |
**Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-fundacao-monolito-modular/spec.md`

## Summary

Fundação técnica do backend PassaNorte como monolito modular: uma única aplicação
FastAPI (Python 3.13, uv) que monta os routers de 10 módulos de domínio sob
`/api/v1` mais `/health` na raiz (200 saudável / 503 com banco degradado),
configuração por variáveis de ambiente com 2 essenciais (DATABASE_URL,
JWT_SECRET) e 4 com default (TTL 3600 s, raio GPS 100 m, cidade/idiomas do
arquivo `config/location.json`), persistência SQLAlchemy 2.0 + Alembic
(PostgreSQL produção / SQLite testes), serviço de auditoria em log estruturado
e verificação automatizada de fronteiras entre módulos. Nenhum RF de negócio
nesta fase.

## Technical Context

**Language/Version**: Python 3.13 (`.python-version`), gerenciado por uv, build
`uv_build`, layout `src/` já existente (`src/passanorte_back/`).

**Primary Dependencies**: FastAPI ≥0.162 `[standard]` (já no pyproject) e
Pydantic v2 (transitiva); a adicionar: `pydantic-settings`, `sqlalchemy>=2.0`,
`alembic`; dev/test: `pytest`, `ruff` (linter + formatter, já exigidos pela
constituição).

**Storage**: PostgreSQL em produção (perfis locais validáveis via container);
SQLite em memória para testes (RNF17); escolha exclusivamente pela
`DATABASE_URL`.

**Testing**: pytest com `TestClient` do FastAPI (testes de contrato),
testes de integração/smoke contra SQLite em memória, teste AST de fronteiras de
módulo (FR-005); alembic exercitado em up/down pela suíte.

**Target Platform**: Linux server via uvicorn (script `dev` existente em
`src/passanorte_back/dev.py`); PostgreSQL opcional em container para validação
do perfil de produção.

**Project Type**: web-service monolito modular (API única; frontends React e
Kotlin são consumidores externos do contrato).

**Performance Goals**: `/health` < 1 s (SC-002); inicialização de `uv sync` a
`/health` respondendo em ≤ 15 min (SC-001) e suíte de smoke < 1 min (SC-004).
Demais metas (RNF11) aplicam-se a features futuras.

**Constraints**: segredos apenas via variáveis de ambiente (FR-011); falha de
inicialização com item essencial ausente ou valor inválido (FR-012); nenhuma
lógica de cidade/idiomas em código (FR-013); 0 violações de fronteira de módulo
(FR-004); ruff sem erros (FR-020); nenhuma fila, cache multicamada ou
comunicação em rede entre módulos (Princípio V).

**Scale/Scope**: 10 módulos de domínio esqueleto (`auth`, `funcionarios`,
`turistas`, `pontos_turisticos`, `eventos`, `gamificacao`, `visitacao`,
`dashboard`, `notificacoes`, `chatbot`), 1 infraestrutura comum (`core`), 1
migration baseline, suíte de smoke com 5 grupos de verificação (FR-021).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate (Princípio) | Status | Evidência no design |
|---|---|---|
| I. API-Contract-First | PASS | Contrato único em `/api/v1` (clarificação Q4); `/health` e docs na raiz; routers montados por módulo mesmo sem endpoints (FR-006); testes de contrato com TestClient |
| II. Segurança e LGPD por Padrão | PASS | JWT_SECRET essencial via env, falha sem ele (FR-011/FR-012); nenhum dado sensível nesta fase; serviço de auditoria estruturado (FR-017–019, log-only conforme clarificação Q3) |
| III. Test-First (NON-NEGOTIABLE) | PASS | Suíte smoke com 5 grupos (FR-021); tarefas test-first previstas para `/speckit-tasks`; testes contra SQLite em memória |
| IV. Dados Geoespaciais | PASS | Raio de tolerância é setting com default 100 m e validação > 0; nenhuma estimativa de métrica nesta fase |
| V. Simplicidade / YAGNI | PASS | Sem filas/caches; auditoria log-only; migration baseline vazia; nenhuma dependência extra além das 3 essenciais |
| VI. Portabilidade por Configuração | PASS | Cidade/idiomas em `config/location.json`, raiz do repositório; troca de perfil de banco apenas via `DATABASE_URL` |
| VII. Manutenibilidade | PASS | Camadas routes/services/repositories/schemas por módulo; type hints obrigatórios; ruff no pipeline |

**Deviation Protocol**: n/a — nenhum gate violado; Complexity Tracking vazio.

## Project Structure

### Documentation (this feature)

```text
specs/001-fundacao-monolito-modular/
├── plan.md              # Este arquivo (/speckit-plan)
├── research.md          # Fase 0 — decisões técnicas
├── data-model.md        # Fase 1 — entidades da fundação
├── quickstart.md        # Fase 1 — guia de validação
├── contracts/           # Fase 1 — contratos HTTP
│   ├── health.md
│   └── module-routers.md
└── tasks.md             # Fase 2 (/speckit-tasks — não criado aqui)
```

### Source Code (repository root)

```text
src/passanorte_back/
├── main.py                # app única: monta routers, /health, ciclo de vida
├── dev.py                 # script dev (uvicorn reload, já existente)
├── core/                  # infraestrutura comum (NÃO é módulo de domínio)
│   ├── __init__.py
│   ├── config.py          # Settings (pydantic-settings) + dados de localidade
│   ├── db.py              # engine/session (SQLAlchemy 2.0), health do banco
│   ├── audit.py           # serviço de auditoria (log estruturado JSON)
│   └── routers.py         # registro central dos routers de domínio
├── auth/
│   ├── __init__.py
│   ├── routes/__init__.py         # APIRouter, prefixo /api/v1/auth
│   ├── services/__init__.py       # interface de serviço pública
│   ├── repositories/__init__.py   # acesso a dados (vazio na fundação)
│   └── schemas/__init__.py        # DTOs Pydantic (vazio na fundação)
├── funcionarios/…         # mesmas 4 subpastas (padrão idêntico)
├── turistas/…
├── pontos_turisticos/…
├── eventos/…
├── gamificacao/…
├── visitacao/…
├── dashboard/…
├── notificacoes/…
└── chatbot/…

config/
└── location.json          # dados de localidade: city, languages (RNF06)

migrations/
├── env.py                 # lê DATABASE_URL dos settings
├── script.py.mako
└── versions/
    └── *_baseline.py      # migration inicial (rev vazia, up/down idempotentes)

tests/
├── conftest.py            # settings do teste (SQLite memória), settings override
├── smoke/
│   ├── test_health.py         # contrato /health (200/503)
│   ├── test_modules.py        # routers registrados sob /api/v1 e app sobe
│   ├── test_settings.py       # essenciais/defaults/valores inválidos (FR-010..013)
│   ├── test_audit.py          # registro estruturado com 5 campos (FR-017..019)
│   └── test_boundaries.py     # AST: 0 imports ilícitos entre módulos (FR-004/005)
└── test_migrations.py         # alembic upgrade head + downgrade base (FR-015/016)

alembic.ini                  # raiz, aponta para migrations/
```

**Structure Decision**: Opção 1 (projeto único) expandida para monolito modular —
um único pacote `src/passanorte_back` com os 10 módulos de domínio como pacotes
irmãos e infraestrutura comum em `core/` (fora do domínio, compartilhável por
todos os módulos sem violar fronteira). `config/location.json` fica na raiz do
repositório (dados, não código — RNF06). `migrations/` na raiz integrada a
alembic.ini. `tests/` na raiz com suíte smoke separada em `tests/smoke/`.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

*Vazio — nenhum gate violado; nenhuma desvio de constituição pendente de justificativa.*