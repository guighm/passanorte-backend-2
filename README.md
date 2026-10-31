# PassaNorte Backend

Backend do PassaNorte — plataforma de turismo de Passa Quatro (MG) —
implementado como **monolito modular** FastAPI: um único processo, um único
banco, módulos de domínio com fronteiras rígidas que espelham o corte de
microsserviços previsto para extração futura.

## Estrutura

```
src/passanorte_back/
├── main.py              # app única: routers, /health, scripts uv
├── dev.py               # script dev (uvicorn --reload)
├── core/                # infraestrutura comum (não é módulo de domínio)
│   ├── config.py        # Settings (pydantic-settings) + dados de localidade
│   ├── db.py            # engine/session SQLAlchemy 2.0 + ping_database
│   ├── audit.py         # auditoria estruturada log-only (1 linha JSON)
│   ├── routers.py       # registro central dos routers /api/v1/<módulo>
│   ├── boundaries.py    # verificação AST de fronteiras entre módulos
│   └── modules.py       # lista canônica dos 10 módulos
├── modules/             # 10 módulos de domínio (auth/ … chatbot/), cada um
│                        # com routes/ services/ repositories/ schemas/
config/location.json     # dados de localidade (city, languages) — dados, não código
migrations/              # Alembic (baseline rev ``0001_baseline``)
tests/                   # pytest: smoke + migrations
```

**Módulos de domínio**: `auth`, `employees`, `tourists`, `tourist_spots`,
`events`, `gamification`, `visitation`, `dashboard`, `notifications`, `chatbot`.
Comunicação entre módulos apenas via `passanorte_back.modules.<módulo>.services`; `schemas`,
`repositories`, `routes` e símbolos privados (`_`) são internos — a suíte de
smoke varre o código por AST e quebra o build em qualquer import ilícito.

## Configuração (2 essenciais + 4 com default)

| Variável | Obrigatória | Default | Uso |
|---|---|---|---|
| `DATABASE_URL` | **sim** | — | Perfil do banco (PostgreSQL prod / SQLite testes) |
| `JWT_SECRET` | **sim** | — | Segredo JWT via env — nunca no código |
| `JWT_TTL` | não | `3600` | TTL do token de acesso (s), > 0 |
| `JWT_REFRESH_TTL` | não | `604800` | TTL da credencial de renovação (s), > 0 |
| `ADMIN_USERNAME` | **sim** (script) | — | Usuário do bootstrap administrativo (`create-admin`) |
| `ADMIN_PASSWORD` | **sim** (script) | — | Senha do bootstrap administrativo (env-only — RF01) |
| `GPS_TOLERANCE_RADIUS_M` | não | `100.0` | Raio de presença (m), > 0 |
| `CITY_NAME` | não | arquivo de localidade | Override da cidade |
| `ENABLED_LANGUAGES` | não | arquivo de localidade | Override dos idiomas (JSON list) |
| `LOCATION_DATA_PATH` | não | `config/location.json` | Caminho do arquivo de localidade |

Sem `DATABASE_URL` ou `JWT_SECRET` a aplicação se recusa a subir, nomeando o
campo ausente. Cidade e idiomas são **dados** (`config/location.json`) —
trocar de cidade/idiomas é editar JSON e reiniciar, zero código.

## Como rodar

Consulte o guia de validação completo em
[specs/001-fundacao-monolito-modular/quickstart.md](specs/001-fundacao-monolito-modular/quickstart.md).
Resumo:

```bash
uv sync                                             # dependências
export DATABASE_URL="sqlite:///./passanorte-dev.db"
export JWT_SECRET="<segredo-sintético-do-dev>"
uv run alembic upgrade head                          # migrations
uv run uvicorn passanorte_back.main:app --port 8000  # app sobe
curl http://localhost:8000/health                    # {"status":"ok","database":"ok"}
uv run pytest                                        # suíte completa (smoke/contrato/integração)
uv run ruff check . && uv run ruff format --check .  # qualidade
```

Scripts `uv run passanorte-back` e `uv run dev` sobem o app (o `dev` com reload).

## Autenticação e acesso (feature 002-auth-rbac)

Fluxo em resumo (contratos completos em
[specs/002-auth-rbac/contracts/](specs/002-auth-rbac/contracts/)):

1. **Bootstrap do admin** (RF01) — `export ADMIN_USERNAME=... ADMIN_PASSWORD=...; uv run create-admin`.
   Upsert por designação de bootstrap: reexecutar atualiza a MESMA conta em vigor
   (inclusive com usuário/senha novos) e nunca cria outra; senha só via env, nunca ecoada.
2. **Login do painel** (RF02) — `POST /api/v1/auth/login` (endpoint único para os dois
   perfis) devolve par de credenciais (access token curto + credencial de renovação
   opaca, single-use) e o `role`.
3. **Renovação** (RNF09) — `POST /api/v1/auth/refresh` troca a credencial de renovação
   por um novo par (reuso/expiração/revogação → 401).
4. **Logout** — `POST /api/v1/auth/logout` invalida a credencial de renovação da sessão.
5. **RBAC** (RF03) — todo endpoint do painel exige sessão válida (401) e o perfil
   (`require_admin`): administrador tem acesso total; funcionário acessa apenas a
   concessão de benefícios (feature futura reutiliza `auth.services.require_admin`).
6. **Funcionários** (RF04/RF05) — admin gerencia via `/api/v1/employees` (criar com
   senha inicial gerada e exibida uma única vez, editar/reativar via PATCH,
   revogar via `POST /{id}/revoke` com efeito imediato).
7. **Auditoria** (RNF19) — ações críticas e login/logout/logout em linhas JSON no
   logger `passanorte.audit` (stdout).

O guia de validação ponta a ponta está em
[specs/002-auth-rbac/quickstart.md](specs/002-auth-rbac/quickstart.md). Nenhuma
senha é armazenada em texto plano (RNF10: bcrypt); credenciais reais nunca vão
para código, testes ou logs.

`GET /health` responde 200 `{"status":"ok","database":"ok"}` ou 503
`{"status":"degraded","database":"unavailable"}` quando o banco indicado por
`DATABASE_URL` está inacessível.

Scripts `uv run passanorte-back` e `uv run dev` sobem o app (o `dev` com reload).