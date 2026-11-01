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

## Configuração (3 essenciais + demais com default)

| Variável | Obrigatória | Default | Uso |
|---|---|---|---|
| `DATABASE_URL` | **sim** | — | Perfil do banco (PostgreSQL prod / SQLite testes) |
| `JWT_SECRET` | **sim** | — | Segredo JWT via env — nunca no código |
| `SENSITIVE_DATA_KEY` | **sim** | — | Chave Fernet (32 bytes url-safe) de e-mail/CPF/passaporte/telefone (RNF08, feature 003) |
| `JWT_TTL` | não | `3600` | TTL do token de acesso (s), > 0 |
| `JWT_REFRESH_TTL` | não | `604800` | TTL da credencial de renovação (s), > 0 |
| `ADMIN_USERNAME` | **sim** (script) | — | Usuário do bootstrap administrativo (`create-admin`) |
| `ADMIN_PASSWORD` | **sim** (script) | — | Senha do bootstrap administrativo (env-only — RF01) |
| `GPS_TOLERANCE_RADIUS_M` | não | `100.0` | Raio de presença (m), > 0 |
| `CITY_NAME` | não | arquivo de localidade | Override da cidade |
| `ENABLED_LANGUAGES` | não | arquivo de localidade | Override dos idiomas (JSON list) |
| `LOCATION_DATA_PATH` | não | `config/location.json` | Caminho do arquivo de localidade |

Sem `DATABASE_URL`, `JWT_SECRET` ou `SENSITIVE_DATA_KEY` a aplicação se recusa
a subir, nomeando o campo ausente. Gere a chave Fernet uma única vez
(em env/`.env` — nunca no repositório):

```sh
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

`SENSITIVE_DATA_KEY` protege os dados sensíveis do turista e gera subchaves
HMAC-SHA256 (HKDF, um contexto por campo: e-mail/CPF/passaporte) para as
colunas de unicidade/igualdade (`*_lookup`) — nenhum valor sensível é
persistido em texto claro (RNF08) e a mesma chave serve para criptografar e
para lookup, sem segundo segredo em env.

Cidade, idiomas e **categorias de interesse** são **dados**
(`config/location.json`) — trocar de cidade/idiomas/categorias é editar JSON
e reiniciar, zero código. Bloco de categorias (RNF06, feature 003):

```json
{ "interest_categories": [
  { "key": "gastronomy", "label": "Gastronomia" },
  { "key": "nature", "label": "Natureza" },
  { "key": "culture", "label": "Cultura" }
] }
```

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

## Ambiente de desenvolvimento com Docker Compose (feature 004)

Pré-requisito único: **Docker** (Engine + Compose v2) — não é preciso Python,
uv ou PostgreSQL locais.

```bash
cp .env.example .env                 # credenciais locais (placeholders de dev) — .env nunca é versionado
docker compose up --build -d         # sobe db + api + dbgate (build da primeira vez)
curl http://localhost:8000/health    # {"status":"ok","database":"ok"} — migrations já aplicadas
```

O que sobe:

| Serviço | Porta (host) | Descrição |
|---|---|---|
| `db` | *não publicada* | PostgreSQL (imagem oficial), dados em volume nomeado |
| `api` | `API_PORT` (padrão **8000**) | API FastAPI; `alembic upgrade head` roda **antes** do uvicorn; hot reload ativo (alterações em `src/` aparecem sem rebuild) |
| `dbgate` | `DBGATE_PORT` (padrão **8080**) | Explorador visual do banco — abra `http://localhost:8080`: a conexão **já vem pré-carregada** (credenciais do `.env`), é só clicar nela e navegar pelas tabelas |

Trocando de porta em caso de conflito no host: edite `API_PORT`/`DBGATE_PORT`
no `.env` e reinsira com `docker compose up -d` (sem rebuild).

Reinícios e dados:

- `docker compose down` — para e remove containers; **os dados persistem** no
  volume nomeado (recria-se o ambiente e o banco segue intacto; migrações
  pendentes, se houver, são aplicadas idempotentemente ao subir).
- `docker compose down -v` — **apaga** o volume de dados (uso deliberado para
  começar do zero; o próximo `up` reexecuta toda a cadeia de migrações).
- Trocou `POSTGRES_USER`/`POSTGRES_DB`? O volume só é inicializado uma
  vez — para renomear o banco/usuário de um volume existente é preciso
  `docker compose down -v` e subir de novo (o PostgreSQL inicializa o volume
  uma única vez).

Admin de alto nível (passo opcional, feature 002): com a stack de pé
(`docker compose exec api create-admin`) — o script usa `ADMIN_USERNAME`/`ADMIN_PASSWORD`
do `.env` e cria/atualiza a única conta bootstrap (RF01).

Guia de validação ponta a ponta da feature:
[specs/004-docker-compose-dev-env/quickstart.md](specs/004-docker-compose-dev-env/quickstart.md).

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

## Turistas e perfil (feature 003-turistas-perfil)

Fluxo do app Passaporte sob `/api/v1/tourists` (contratos completos em
[specs/003-turistas-perfil/contracts/tourists.md](specs/003-turistas-perfil/contracts/tourists.md)):

1. **Cadastro** (RF22) — `POST /api/v1/tourists` (público): nome, sobrenome,
   país, telefone (`+DDI`), e-mail, senha (≥ 8) e **exatamente um** documento
   (CPF com/sem máscara **ou** passaporte alfanumérico 6–10). 201 retorna só
   id/nome/país; duplicado e-mail/CPF/passaporte → 409 sem vazamento.
2. **Login** (RF23) — `POST /api/v1/tourists/login` (público): par de
   credenciais da fundação com `role: "tourist"`; falha → 401 genérico.
   Renovação/`logout` usam `POST /api/v1/auth/refresh` e `/auth/logout`.
3. **Perfil** (RF24) — `GET /tourists/me` (turista) e
   `GET/PATCH /tourists/{id}` (próprio ou admin — outro turista → 403, admin
   sem alvo → 404): dados sensíveis descriptografados SOMENTE para self/admin
   (RNF08). Não há edição de senha nesta feature.
4. **Interesses** (RF25) — `GET /tourists/interest-categories` (qualquer
   conta autenticada; categorias do `location.json`), `GET/PUT
   /tourists/me/interests` (turista; PUT substitui a seleção integralmente,
   categoria inválida → 422).

Os dados sensíveis do turista (e-mail, CPF, passaporte, telefone) são
armazenados **criptografados** (Fernet) com colunas irmã de lookup
(HMAC-SHA256 keyado) para unicidade — nunca em texto claro (RNF08); a senha
fica em bcrypt (RNF10).

Scripts `uv run passanorte-back` e `uv run dev` sobem o app (o `dev` com reload).
## Contrato JSON camelCase (feature 005)

O contrato HTTP da API é **100% camelCase** — entradas e saídas, em qualquer
nível de aninhamento, espelhando os tipos TypeScript do frontend (`accessToken`,
`firstName`, `touristSpot`, `countryOfOrigin`). Nomes de classes de schema/DTO
no Swagger são **PascalCase** (`TouristSessionResponse`, `ApiError`) e servem
como fonte única para geração de tipos TS.

Regras (fonte única: `specs/005-camelcase-json-contract/contracts/camelcase-json.md`):

1. **Saída**: toda resposta JSON tem chaves camelCase. Internamente os
   atributos Python e colunas de banco permanecem snake_case (PEP 8) — a
   conversão acontece só na fronteira HTTP (base `ApiModel` em
   `src/passanorte_back/core/schemas.py`).
2. **Entrada estrita**: a API aceita **apenas** chaves camelCase declaradas —
   `snake_case` ou chaves desconhecidas → **422** (`errorCode`:
   `validation_error`) nomeando a chave recebida.
3. **Erros unificados**: todo corpo de erro segue o schema `ApiError`
   (`errorCode`, `message`, `details[]` com `key`/`message`), documentado no
   Swagger.

```json
{
  "errorCode": "validation_error",
  "message": "Request body is invalid.",
  "details": [{ "key": "first_name", "message": "Extra inputs are not permitted" }]
}
```

A varredura de contrato (`tests/contract/test_camelcase_contract.py`) caminha
por **todas** as rotas registradas e o documento OpenAPI inteiro e **falha**
se qualquer chave com `_` aparecer em sucesso ou erro.
