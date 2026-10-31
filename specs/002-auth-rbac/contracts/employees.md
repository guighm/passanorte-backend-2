# API Contract: employees

Base: `/api/v1/employees` (router canônico da fundação). **Todos os endpoints
exigem perfil admin** (`require_admin`) — 401 sem sessão válida, 403
funcionário (RBAC, FR-008/009).

## POST /api/v1/employees

Cria funcionário; **o sistema gera a senha inicial** (clarificação Q3-s4):
nunca é recebida por input, persistida só como hash e retornada **uma única
vez** na resposta.

**Request** `EmployeeCreateRequest`:

```json
{ "name": "string", "username": "string" }
```

**201** `EmployeeCreatedResponse`:

```json
{
  "id": 1,
  "name": "string",
  "username": "string",
  "status": "active",
  "initial_password": "string"
}
```

- `initial_password` presente **somente nesta resposta** (nunca listagem,
  atualização ou log; auditoria registra apenas os dados do funcionário).
- **409** — username já utilizado (admin ou employee, case-insensitive);
  sem criar conta. **401/403** conforme RBAC.

## GET /api/v1/employees

**200** `EmployeeListResponse`:

```json
{ "items": [ EmployeeView ], "total": 0 }
```

`EmployeeView`: `{ id, name, username, status, created_at, updated_at }` —
sem qualquer campo de credencial.

## GET /api/v1/employees/{employee_id}

**200** `EmployeeView` | **404** (`{"detail": "employee not found"}`).

## PATCH /api/v1/employees/{employee_id}

Edita dados; aceita `name` e/ou `username` e/ou
`{"status": "active"}` para reativar funcionário revogado (clarificação Q3-s3;
sessões anteriores à revogação continuam recusadas). Mudar `status` para
`revoked` por este campo não é permitido — use a rota de revoke (claridade
de contrato).

**Request** `EmployeeUpdateRequest`:

```json
{ "name": "string", "username": "string", "status": "active" }
```
(campos opcionais)

**200** `EmployeeView` | **404** | **409** (username em conflito) |
**422** (`status = revoked` nesta rota).

## POST /api/v1/employees/{employee_id}/revoke

Revoga acesso: `status → revoked`, **efetivo imediatamente** para sessões em
curso (revalidação por requisição — research R4) e para novos logins (401).

**204** | **404**. Idempotente: revogar já revogado → 204 (estado final
igual). Reativação apenas pelo PATCH (não nesta rota).

## Regras transversais

- Unicidade global do username contra `admin_users` via serviço público de
  `auth` (regra 3/5 da Constituição; research R5).
- Auditoria (RNF19/FR-014) para: create (`employee.create`), edit
  (`employee.update`), reactivate (`employee.reactivate`) e revoke
  (`employee.revoke`) — com actor (username do admin), alvo (id) e resultado.