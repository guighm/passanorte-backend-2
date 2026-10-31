# Data Model: Fundação do Monolito Modular Backend PassaNorte

Feature: `/specs/001-fundacao-monolito-modular/spec.md` | Date: 2026-10-30

Esta fase **não cria tabelas de negócio** (FR-007). O schema persistido é apenas
o registro de estado do Alembic. As "entidades" abaixo são valores de runtime e
arquivos de configuração/dados da fundação.

## Entidades

### 1. AppConfig (runtime, não persistida)

Configuração carregada do ambiente na inicialização; imutável durante a execução
(Key Entity da spec).

| Campo | Fonte | Essencial | Default | Validação |
|---|---|---|---|---|
| `database_url` | env `DATABASE_URL` | sim | — | string não vazia; motor deduzido da URL |
| `jwt_secret` | env `JWT_SECRET` | sim | — | string não vazia |
| `jwt_ttl` | env `JWT_TTL` | não | `3600` | `> 0` (s) |
| `gps_tolerance_radius_m` | env `GPS_TOLERANCE_RADIUS_M` | não | `100.0` | `> 0` |
| `city_name` | env `CITY_NAME` | não | do arquivo de localidade | — |
| `languages` | env `ENABLED_LANGUAGES` | não | do arquivo de localidade | lista explicitamente vazia → erro |
| `location_data_path` | env `LOCATION_DATA_PATH` | não | `config/location.json` | arquivo precisa existir quando acessado |

Estado: nenhuma transição — carregada uma vez no startup; ausência de essencial
ou valor inválido interrompe a inicialização (FR-012).

### 2. LocationData (arquivo de dados — `config/location.json`)

Dados de localidade da instalação (RNF06; trocáveis sem código — SC-006).

```json
{
  "city": "Passa Quatro",
  "languages": ["pt-BR"]
}
```

- `city`: string, nome da cidade atendida (exibição/UX em português).
- `languages`: lista não vazia de tags de idioma habilitadas (i18n-ready, RNF13).
- Falhas tratadas: arquivo ausente, JSON inválido, chaves ausentes ou lista
  vazia → erro de configuração no startup com mensagem explícita.

### 3. AuditRecord (registro de auditoria — log estruturado, log-only)

Evento emitido pelo serviço `core/audit.py` (RNF19; clarificação Q3 — sem
tabela nesta fase).

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `timestamp` | ISO-8601 UTC | sim | momento da emissão |
| `actor` | string | sim | identificador de quem executou a ação (ex.: id de funcionário/admin) |
| `action` | string | sim | tipo de ação (ex.: `create_point`, `remove_event`, `upsert_employee`) |
| `target` | string | sim | referência do alvo (ex.: `<tipo>:<id>`) |
| `result` | enum (`success`, `failure`) | sim | resultado da ação |
| `detail` | objeto/string | não | contexto adicional |

Emissão: 1 linha JSON por ação via logger `passanorte.audit` (stdout);
falha de emissão sinaliza `AuditError` ao chamador (FR-018).

### 4. DomainModule (conceito estrutural, não persistido)

Unidade organizacional do monolito; registro central em `core/routers.py`,
lista canônica em `DOMAIN_MODULES` (`core/modules.py` — constituição, regra 2).

- 10 módulos (nomes de pacote em inglês): `auth`, `employees`, `tourists`,
  `tourist_spots`, `events`, `gamification`, `visitation`, `dashboard`,
  `notifications`, `chatbot`.
- Cada módulo em `src/passanorte_back/modules/<domain>/`: camadas `routes/`,
  `services/`, `repositories/`, `schemas/`.
- Prefixo HTTP: `/api/v1/<nome-com-hifens>` (ex.: `/api/v1/tourist-spots`).
- Regra de fronteira (testada por AST): outros módulos só importam
  `<modulo>.services`; `schemas`/`repositories`/`routes`/símbolos privados são
  privados ao módulo.

## Persistência (estado do banco nesta fase)

- SQLite/PostgreSQL vazio em conteúdo; migrations gerenciam apenas
  `alembic_version` (revision `baseline`, sem operações de schema).
- Nenhuma tabela de negócio; nenhuma tabela de auditoria (Q3).

## Validações derivadas da spec

- `/health`: HTTP 200 `{status: "ok", database: "ok"}`; HTTP 503
  `{status: "degraded", database: "unavailable"}` (FR-009, clarificação Q1).
- Config inválida: `jwt_ttl <= 0`, `gps_tolerance_radius_m <= 0`, `languages = []`
  explícito, essencial ausente → startup interrompido com mensagem nomeando o
  item (FR-012/Edge Cases).