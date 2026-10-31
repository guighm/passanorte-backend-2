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
├── auth/ … chatbot/     # 10 módulos de domínio, cada um com camadas
│                        # routes/ services/ repositories/ schemas/
config/location.json     # dados de localidade (city, languages) — dados, não código
migrations/              # Alembic (baseline rev ``0001_baseline``)
tests/                   # pytest: smoke + migrations
```

**Módulos de domínio**: `auth`, `funcionarios`, `turistas`, `pontos_turisticos`,
`eventos`, `gamificacao`, `visitacao`, `dashboard`, `notificacoes`, `chatbot`.
Comunicação entre módulos apenas via `<módulo>.services`; `schemas`,
`repositories`, `routes` e símbolos privados (`_`) são internos — a suíte de
smoke varre o código por AST e quebra o build em qualquer import ilícito.

## Configuração (2 essenciais + 4 com default)

| Variável | Obrigatória | Default | Uso |
|---|---|---|---|
| `DATABASE_URL` | **sim** | — | Perfil do banco (PostgreSQL prod / SQLite testes) |
| `JWT_SECRET` | **sim** | — | Segredo JWT via env — nunca no código |
| `JWT_TTL` | não | `3600` | TTL do token (s), > 0 |
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
uv run uvicorn passanorte_back.main:app --port 8000  # app sobe
curl http://localhost:8000/health                    # {"status":"ok","database":"ok"}
uv run alembic upgrade head                          # migrations
uv run pytest                                        # suíte de smoke
uv run ruff check . && uv run ruff format --check .  # qualidade
```

`GET /health` responde 200 `{"status":"ok","database":"ok"}` ou 503
`{"status":"degraded","database":"unavailable"}` quando o banco indicado por
`DATABASE_URL` está inacessível.

Scripts `uv run passanorte-back` e `uv run dev` sobem o app (o `dev` com reload).