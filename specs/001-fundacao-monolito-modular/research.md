# Research: Fundação do Monolito Modular Backend PassaNorte

Feature: `/specs/001-fundacao-monolito-modular/spec.md` | Date: 2026-10-30

Todas as decisões abaixo resolvem os pontos de design do plano e as
clarificações da sessão 2026-10-30 da spec. Não há NEEDS CLARIFICATION
remanescentes.

## R1. Configuração com pydantic-settings

- **Decision**: `core/config.py` define `Settings` (BaseSettings, `extra="ignore"`)
  com `model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")`.
  Campos:
  - Essenciais (sem default, exigidos pela validação Pydantic): `database_url: str`,
    `jwt_secret: str`.
  - Com default: `jwt_ttl: int = 3600` (env `JWT_TTL`), `gps_tolerance_radius_m: float = 100.0`,
    `city_name: str | None = None`, `languages: list[str] | None = None`,
    `location_data_path: Path = Path("config/location.json")`.
  - Validators: `jwt_ttl > 0`, `gps_tolerance_radius_m > 0`, lista de idiomas
    explicitamente vazia → erro; `database_url`/`database_url` ausentes → erro nativo
    do Pydantic com nome do campo (FR-012).
  - Propriedades `resolved_city() -> str` e `resolved_languages() -> list[str]`:
    retornam o override de ambiente quando presente, senão a leitura de
    `config/location.json` (FR-013). Falha com mensagem clara se o arquivo não
    existir ou não tiver as chaves.
- **Rationale**: atende FR-010/012/013 e a clarificação Q2 (2 essenciais + 4 com
  default); `.env` facilita o perfil dev sem segredos no repo (`.env` em
  `.gitignore`).
- **Alternatives considered**: python-dotenv cru (sem validação tipada — rejeitado,
  constituição exige Pydantic); Django settings (fora de stack); 6 variáveis todas
  essenciais (rejeitado na clarificação Q2).

## R2. Persistência e perfil de banco

- **Decision**: `core/db.py` cria `engine` (síncrono) e `sessionmaker` a partir de
  `settings.database_url`; `ping_database() -> bool` executa `SELECT 1` com
  timeout curto, usado pelo `/health`. SQLite em memória para testes via fixture
  de conftest que sobrescreve `Settings`. Nenhum `if "sqlite"` espalhado pela
  aplicação: a única convergência entre motores fica na URL do banco e em opções
  de `engine` (ex.: sem pool para SQLite-memória) concentradas em `core/db.py`.
- **Rationale**: simples, síncrono e compatível com Alembic sem configuração dupla
  (Princípio V); health de banco é subsistema leve (RNF11: /health não pode
  depender de nada pesado).
- **Alternatives considered**: engine assíncrono + drivers asyncpg/aiosqlite
  (rejeitado: complexidade extra sem RF que exija alta concorrência nesta fase);
  two engines dev/prod hardcoded (violaria FR-014 — escolha só pela config).

## R3. Alembic e migration baseline

- **Decision**: `alembic.ini` na raiz; `migrations/env.py` monta a URL a partir de
  `settings.database_url` (nunca hardcoded). Revision baseline (`baseline`)
  sem operações de schema — esta fase não tem tabelas de negócio; `upgrade
  head` sobre banco vazio e `downgrade base` revertem limpo (FR-015/016,
  SC-003). Features futuras adicionam revisions próprias.
- **Rationale**: estabelece o fluxo de migrations desde o primeiro dia sem
  inventar tabelas (YAGNI); `alembic_version` do próprio Alembic registra o
  estado.
- **Alternatives considered**: já criar tabela de auditoria (rejeitado —
  clarificação Q3 optou por log-only); `Base.metadata.create_all` no startup
  (rejeitado: contorna governança de schema da constituição — migrations
  versionadas).

## R4. Auditoria log-only estruturada

- **Decision**: `core/audit.py` expõe `record_action(actor, action, target,
  result, *, detail=None) -> None` que emite um dicionário JSON por linha
  (formatters de `logging`) pelo logger dedicado `passanorte.audit`, stdout em
  produção/dev e capturável em teste via handler. Campos mínimos garantidos:
  `timestamp` (ISO-8601 UTC), `actor`, `action`, `target`, `result`
  (FR-017/SC-007). `result` distingue ao menos `success`/`failure`. Levanta
  exceção própria (`AuditError`) quando o sink falha (FR-018).
- **Rationale**: clarificação Q3 (log-only, YAGNI); persistência em tabela fica
  para a primeira feature com ação administrativa real, que apenas troca/complementa
  o sink — interface do serviço não muda.
- **Alternatives considered**: `structlog` (rejeitado: dependência extra para emitir
  um dict; `logging` padrão com formatter JSON é suficiente); persistir em tabela
  agora (rejeitado na clarificação Q3).

## R5. Verificação de fronteiras entre módulos (FR-004/005)

- **Decision**: `tests/smoke/test_boundaries.py` percorre os módulos de domínio em
  `src/passanorte_back/` (a lista é derivada da estrutura de diretórios, os 10
  nomes), faz parse AST de cada `.py` e falha ao encontrar import de internals
  privados de outro módulo: `schemas`, `repositories`, `routes` e símbolos privados
  (prefixo `_`). Import de `passanorte_back.<outro>.services` é permitido
  (interface de serviço pública — constituição, regras 3/5); `core` e `main` são
  compartilháveis por todos.
- **Rationale**: prova a fronteira no build de teste sem dependência nova; cumpre
  FR-005 (violação quebra o teste) e o scenario 4 da US-2 (deliberadamente violado
  → falha apontando módulo/arquivo).
- **Alternatives considered**: `import-linter` (dependência de qualidade a mais;
  rejeitado por YAGNI — pode substituir o teste AST no futuro com o mesmo efeito);
  revisão manual em PR (rejeitado: não é verificação automatizada exigida por FR-005).

## R6. Registro central de routers e prefixo `/api/v1`

- **Decision**: `core/routers.py` mantém a lista ordem-estável dos routers (um por
  módulo, `include_router` em `main.py`), iterando `DOMAIN_MODULES`
  (`core/modules.py`). Contrato de negócio sob `/api/v1`;
  prefixo de cada módulo = nome canônico em inglês com `_` → `-` (`/api/v1/auth`,
  `/api/v1/employees`, `/api/v1/tourist-spots`, …). Routers vazios na
  fundação (sem operações; RNF03, clarificação Q4). `/health` e docs na raiz.
- **Rationale**: registro único facilita extrair cada módulo para serviço no
  futuro (contrato de API interna da constituição, regra 6); smoke test verifica
  que o OpenAPI contém os 10 prefixos.
- **Alternatives considered**: prefixo sem versionamento (rejeitado na
  clarificação Q4); paths distintos por frontend (rejeitado — viola Princípio I).

## R7. Dados de localidade (RNF06)

- **Decision**: `config/location.json` na raiz do repositório:
  `{"city": "Passa Quatro", "languages": ["pt-BR"]}`. Lidos por
  `Settings.resolved_city()/resolved_languages()`, nunca importados como código
  (não existe `config` como módulo Python).
- **Rationale**: PR-008/SC-006: trocar cidade/idiomas = editar JSON e reiniciar;
  caminho sobrescrevível via `LOCATION_DATA_PATH` se o deploy o requerer.
- **Alternatives considered**: YAML/TOML (JSON via stdlib `json` basta); variável
  de ambiente única com dict embutido (dados viram string de env — pior para
  portabilidade e revisão).

## R8. Suíte de smoke e estrutura de testes

- **Decision**: pytest; `tests/conftest.py` fixa `Settings` de teste
  (`DATABASE_URL=sqlite:///:memory:` via variáveis de ambiente do processo de
  teste e segredo sintético não-real). Grupos: health (contrato 200/503, Q1),
  módulos registrados, settings (essenciais/defaults/inválidos), auditoria
  (5 campos, 1 registro por ação, capturável), fronteiras AST, migrations
  up/down. `pytest` roda tudo; nenhum endpoint `/dev` de exemplo no app.
- **Rationale**: FR-021 cobre exatamente os grupos acima; segredos sintéticos de
  teste nunca reais (Quality Gate: nada de senha real em teste).
- **Alternatives considered**: httpx AsyncClient sem TestClient (rejeitado: TestClient
  já cobre contrato de forma síncrona e simples); separar smoke em `pytest -m
  smoke` (fase tem apenas smoke — sem markers por enquanto, YAGNI).

## R9. Limpeza do scaffold existente

- **Decision**: `main.py` atual será reescrito (remover `/items/{item_id}` de
  exemplo); `main()`/`dev.py` mantidos como scripts uv (`passanorte-back`,
  `dev`) apontando para o app real. `pyproject.toml` ganha as dependências das
  decisões R1–R3 e dev-dependencies (pytest, ruff) — sem mudar build backend.
- **Rationale**: reaproveita o scaffold existente; remove placeholder que
  violaria FR-007 (nenhum RF de negócio).
- **Alternatives considered**: renomear projeto/pacote (rejeitado: `passanorte_back`
  já é o nome acordado).