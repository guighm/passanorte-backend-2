# Quickstart: Fundação do Monolito Modular Backend PassaNorte

Guia de validação da feature — prova de ponta a ponta que a fundação funciona
(critério de aceitação: app sobe, `/health` responde, migration roda, smoke
passa). Implementação em `tasks.md`; contratos em [contracts/](./contracts/).

## Pré-requisitos

- Python 3.13 e `uv` instalados.
- Para validar o perfil de produção localmente: Docker (PostgreSQL) — opcional;
  o fluxo padrão de desenvolvimento/testes usa SQLite.

## 1. Ambiente

```bash
uv sync                     # instala dependências do pyproject (dev deps inclusas)
```

Criar `.env` na raiz (nunca versionado — FR-011):

```bash
# Essenciais (a aplicação se recusa a subir sem eles):
export DATABASE_URL="sqlite:///./passanorte-dev.db"   # perfil dev
export JWT_SECRET="<segredo-sintético-do-dev>"

# Opcionais — defaults: JWT_TTL=3600, raio=100.0, cidade/idiomas de config/location.json
# export JWT_TTL=7200
# export GPS_TOLERANCE_RADIUS_M=100.0
# export CITY_NAME="Passa Quatro"
# export ENABLED_LANGUAGES='["pt-BR","en"]'
```

Verificação esperada: `uv sync` conclui sem erros.

## 2. App sobe e /health responde

```bash
uv run uvicorn passanorte_back.main:app --port 8000 &
sleep 2 && curl -sS http://localhost:8000/health
```

**Esperado**: `{"status":"ok","database":"ok"}` (HTTP 200, < 1 s — SC-002).

Degradado (clarificação Q1): reiniciar com `DATABASE_URL` apontando a um banco
inexistente/inacessível → `curl -sS -o /dev/null -w '%{http_code}' http://localhost:8000/health`
**espera `503`** e o corpo `{"status":"degraded","database":"unavailable"}`.

Erro de config (FR-012): sem `JWT_SECRET` no ambiente → processo sobe? **Não**
— falha antes de servir, com mensagem nomeando `JWT_SECRET`.

## 3. Migration inicial

```bash
uv run alembic upgrade head      # primeira execução: aplica baseline
uv run alembic downgrade base    # reverte limpo
uv run alembic upgrade head      # reaplica
```

**Esperado**: os três comandos concluem sem erro; banco contém apenas
`alembic_version` (SC-003).
Com `DATABASE_URL` de SQLite dev, um `passanorte-dev.db` é criado na raiz.

### 3.1. Validação do perfil de produção (PostgreSQL, T029)

Comando executado na validação desta feature (Docker local, container efêmero):

```bash
docker run -d --rm --name passanorte-pg-test -e POSTGRES_PASSWORD=pgtest \
  -e POSTGRES_DB=passanorte -p 55321:5432 postgres:16-alpine
# aguardar pg_isready, então:
export DATABASE_URL="postgresql://postgres:pgtest@localhost:55321/passanorte"
uv run alembic upgrade head && uv run alembic downgrade base && uv run alembic upgrade head
docker stop passanorte-pg-test
```

**Resultado (2026-10-30)**: `upgrade -> 0001_baseline`, `downgrade 0001_baseline -> base`
e re-`upgrade -> 0001_baseline` concluíram sem erro; introspecção do banco
confirmou apenas a tabela `alembic_version` no schema `public` (nenhuma tabela
de negócio — FR-007).

## 4. Suíte de smoke

```bash
uv run pytest
```

**Esperado**: tudo verde em < 1 min (SC-004), cobrindo: contrato `/health`
(200/503), módulos registrados sob `/api/v1` (10 routers montados — routers
vazios geram paths no OpenAPI apenas quando ganham endpoints; a verificação
roda pelos routers montados), settings (essenciais/defaults/inválidos),
auditoria (registro JSON com os 5 campos) e fronteiras de módulo (AST:
0 violações). Nenhum segredo real em teste.

## 5. Qualidade

```bash
uv run ruff check .
uv run ruff format --check .
```

**Esperado**: sem erros (FR-020, Quality Gate).

## 6. Portabilidade (SC-006) — opcional

1. Editar `config/location.json` trocando `city`/`languages` (ou definir
   `CITY_NAME`/`ENABLED_LANGUAGES`).
2. Reiniciar a aplicação e conferir os novos valores efetivos — nenhuma linha de
   código alterada.

## Referências

- Contratos: [contracts/health.md](contracts/health.md),
  [contracts/module-routers.md](contracts/module-routers.md)
- Entidades e validações: [data-model.md](data-model.md)
- Decisões técnicas: [research.md](research.md)