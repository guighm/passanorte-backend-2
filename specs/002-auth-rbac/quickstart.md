# Quickstart: Autenticação e Controle de Acesso (RBAC)

Feature: `/specs/002-auth-rbac/spec.md` | Contratos: [auth](contracts/auth.md), [employees](contracts/employees.md) | Dados: [data-model.md](data-model.md)

## Pré-requisitos

- Python 3.13 + uv; banco (PostgreSQL local ou SQLite para teste).
- Segredos em variáveis de ambiente (nenhuma com default — RF01/RNF09/RNF10):

```bash
export DATABASE_URL="postgres://..."
export JWT_SECRET="<segredo-long>"
export JWT_TTL="3600"            # opcional (s) — vida do access token
export JWT_REFRESH_TTL="604800"  # opcional (s) — vida da credencial de renovação
export ADMIN_USERNAME="<usuário-admin>"
export ADMIN_PASSWORD="<senha-admin>"
```

## 1. Bootstrap da conta administrativa

```bash
uv run alembic upgrade head   # cria admin_users, employees, auth_sessions
uv run create-admin
```

- OK: mensagem com a conta upsertada (não imprime a senha). Reexecutável:
  atualiza a mesma conta em vigor (inclusive com usuário/senha mudados —
  nunca cria outra).
- Sem `ADMIN_USERNAME`/`ADMIN_PASSWORD`: erro claro e **nenhum banco
  alterado**.

## 2. Subir a API

```bash
uv run dev            # http://localhost:8000 — Swagger em /docs
```

`GET /health` → 200 `{"status": "ok", "database": "ok"}`.

## 3. Fluxo de validação manual (end-to-end)

```bash
# 1) login do administrador (par de credenciais + role)
curl -s -X POST localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"'"$ADMIN_USERNAME"'","password":"'"$ADMIN_PASSWORD"'"}'
#   → 200 com access_token, refresh_token, role="admin"

# 2) criar funcionário (senha inicial gerada, exibida UMA vez)
ADMIN=<access_token>  # do passo anterior
curl -s -X POST localhost:8000/api/v1/employees \
  -H "Authorization: Bearer $ADMIN" -H 'Content-Type: application/json' \
  -d '{"name":"Maria Souza","username":"maria.souza"}'
#   → 201 com initial_password (guarde-a) ; sem token → 401

# 3) login do funcionário
curl -s -X POST localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"maria.souza","password":"<initial_password>"}'
#   → 200 com role="employee"

# 4) RBAC
curl -s -X GET localhost:8000/api/v1/employees -H 'Content-Type: application/json' \
  -H "Authorization: Bearer <token-do-funcionario>"
#   → 403 (funcionário não acessa gestão de funcionários; idem dashboard/pontos)

# 5) renovação (novo par, sem senha)
curl -s -X POST localhost:8000/api/v1/auth/refresh \
  -H 'Content-Type: application/json' \
  -d '{"refresh_token":"<refresh_token>"}'
#   → 200 novo par ; reusar o mesmo refresh → 401

# 6) logout invalida a credencial de renovação
curl -s -X POST localhost:8000/api/v1/auth/logout \
  -H "Authorization: Bearer <access_token>"
#   → 204 ; refresh com o token anterior → 401

# 7) revogar funcionário: acesso cai imediatamente
curl -s -X POST localhost:8000/api/v1/employees/<id>/revoke \
  -H "Authorization: Bearer $ADMIN"
#   → 204 ; chamadas seguintes do funcionário → 401 ; login dele → 401
#      PATCH status=active reativa (sessões antigas continuam recusadas)

# 8) auditoria visível em stdout (linhas JSON "passanorte.audit"):
#    login.success/login.failure, employee.create/update/reactivate/revoke, logout
```

## 4. Bateria de testes

```bash
uv run pytest                      # contratos + integração (ciclo de vida)
uv run pytest tests/integration/test_employee_lifecycle.py -v
uv run ruff check && uv run ruff format --check
```

Cobertura esperada (aceitação da spec): login válido/ inválido (401),
renovação (200 novo par / 401 rotada-reusada-expirada), 401 sem token,
403 de funcionário em endpoint administrativo (dashboard, tourist_spots,
employees) e integração criar → editar → revogar → login bloqueado.

> Os valores de teste são gerados nos fixtures (admin semeados via teste)
> — **nenhuma credencial real no repositório** (FR-002; qualidade gate da Constituição).

## Referências

- Convenções internas: [contracts/module-routers](../../specs/001-fundacao-monolito-modular/contracts/module-routers.md)
- Decisões técnicas: [research.md](research.md)