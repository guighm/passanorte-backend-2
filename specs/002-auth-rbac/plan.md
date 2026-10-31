# Implementation Plan: Autenticação e Controle de Acesso (RBAC)

**Branch**: `002-auth-rbac` | **Date**: 2026-10-31 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-auth-rbac/spec.md`

## Summary

Autenticação do painel (RF01–RF05, RNF09/RNF10/RNF19): script de bootstrap
upsert da conta administrativa (segredos via env), login único
(admin/funcionário) emitindo par de credenciais (access JWT curto + refresh
opaco persistido com revogação/logout), RBAC em todos os endpoints do painel
(admin = total; funcionário = apenas concessão de benefícios futura), ciclo
de vida de funcionário (criar com senha gerada exibida 1×, editar/reativar,
revogar com efeito imediato) e auditoria estruturada via `core.audit`.

Technical approach: módulos `auth` (autenticação, emissão/verificação de
token, sessões de renovação, dependências RBAC em `core/security`) e
`employees` (CRUD de contas de funcionário); comunicação cruzada apenas via
interfaces públicas de serviço (regra 3 da Constituição).

## Technical Context

**Language/Version**: Python 3.13 (type hints obrigatórios — princípio VII)

**Primary Dependencies**: FastAPI (routers da fundação), Pydantic v2,
PyJWT (access token JWT), bcrypt (hash de senha — RNF10), SQLAlchemy 2.0 +
Alembic (persistência), pydantic-settings (config).

**Storage**: PostgreSQL (produção) / SQLite (testes, banco isolado) —
novo migration Alembic com 3 tabelas (admin_users, employees, auth_sessions).

**Testing**: pytest — testes de contrato (schemas/HTTP codes) e de integração
(ciclo de vida ponta a ponta), banco SQLite em memória por teste
(princípio III); `ruff check` no gate.

**Target Platform**: Linux server, aplicação FastAPI monolítica (deploy único).

**Performance Goals**: login < 1 s em condições normais (SC-006);
autenticação independente de subsistemas pesados (RNF11/12).

**Constraints**: segredos exclusivamente via env (`ADMIN_USERNAME`,
`ADMIN_PASSWORD`, `JWT_SECRET`/`JWT_TTL`/`JWT_REFRESH_TTL`); nenhuma senha em
texto plano em código/banco/logs; identificação de contas revalidada contra o
banco a cada requisição (revogação efetiva para sessões em curso — FR-013).

**Scale/Scope**: painel administrativo (administradores + funcionários em
decenas); endpoints novos: login, refresh, logout, employees (CRUD + revoke),
bootstrap script.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Princípio | Status |
|---|---|---|
| Monolito modular — apenas `auth` e `employees`, routers canônicos da fundação reutilizados | Fundação (regras 1–6) | ✅ |
| Comunicação cruzada só por serviço público (`employees.services` ↔ `auth.services`) | I / regra 3 | ✅ |
| Sem endpoint privado sem RBAC | I | ✅ (dependências RBAC em `core/security`, aplicadas em todas as rotas do painel) |
| JWT com expiração/renovação; senhas com hash (bcrypt); segredos por env; auditoria estruturada | II | ✅ |
| Test-First: contrato + integração com banco isolado por teste | III | ✅ (tasks geram teste vermelho antes) |
| Nenhuma tabela compartilhada entre domínios | regra 4 | ✅ (`admin_users`+`auth_sessions` em auth; `employees` em employees) |
| Escritas cross-domain via serviço dono dos dados | regra 5 | ✅ (unicidade global de username checada via serviço público) |
| YAGNI — sem filas/caches/deps desnecessárias | V | ✅ (2 deps novas: pyjwt, bcrypt) |
| Portabilidade por configuração | VI | ✅ (TTLs e cidade via config) |
| Código 100% em inglês (identificadores, commit, comments) | VII | ✅ (dados/UX-pt permanecem) |
| Migration Alembic revisada quando houver mudança de schema | Quality Gates | ✅ (`migrations/versions` com 1 migration nova) |

## Project Structure

### Documentation (this feature)

```text
specs/002-auth-rbac/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (auth.md, employees.md)
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
src/passanorte_back/
├── core/
│   ├── security.py          # NOVO: primitivos — hashing bcrypt, encode/decode
│   │                        #   de access token JWT (HS256)
│   ├── config.py            # EXTEND: jwt_refresh_ttl
│   └── (db, routers, audit, boundaries, modules — inalterados)
├── modules/
│   ├── auth/
│   │   ├── routes/          # POST /login, /refresh, /logout; GET /me
│   │   ├── services/        # login, refresh, logout, bootstrap upsert;
│   │   │                    #   dependências RBAC públicas (get_current_user,
│   │   │                    #   require_admin); interface p/ employees
│   │   ├── repositories/    # admin_users, auth_sessions
│   │   └── schemas/         # LoginRequest/SessionResponse/RefreshRequest...
│   └── employees/
│       ├── routes/          # POST /employees, GET list/detail, PATCH /{id},
│       │                    #   POST /{id}/revoke
│       ├── services/        # create (senha gerada exibida 1×), edit, revoke,
│       │                    #   reactivate; interface pública find_by_username
│       ├── repositories/    # employees
│       └── schemas/         # EmployeeCreate/Update/Reactivation, CredentialView
├── scripts/
│   └── create_admin.py      # NOVO: bootstrap upsert (env-only secrets, RF01)
main.py                      # inalterado (register_routers monta os routers existentes)

tests/
├── contract/test_auth.py, test_employees.py, test_rbac.py
├── integration/test_admin_bootstrap.py, test_employee_lifecycle.py
├── unit/test_security.py, test_rbac_dependencies.py
└── conftest.py              # app de teste + banco SQLite em memória por teste

pyproject.toml               # deps: pyjwt, bcrypt; [project.scripts]: create-admin
migrations/versions/         # 1 migration: admin_users, employees, auth_sessions
```

**Structure Decision**: mantém a estrutura da fundação (monolito modular,
camadas `routes/services/repositories/schemas` nos módulos, infra em
`core/`); novas peças são `core/security.py` (infra compartilhada de
autenticação/RBAC) e `scripts/create_admin.py`, com entrada
`create-admin` no `pyproject`. Nenhum módulo novo além dos dois canônicos.

## Complexity Tracking

> Sem violações de Constituição — seção vazia.