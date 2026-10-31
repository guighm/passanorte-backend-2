# Data Model: Autenticação e Controle de Acesso (RBAC)

Feature: `/specs/002-auth-rbac/spec.md` | Date: 2026-10-31

Tabelas persistidas: 3, em 2 migrações de domínio (1 migration Alembic nova
acima de `20261030_0001_baseline`). Nenhuma tabela compartilhada entre
domínios (regra 4 da Constituição).

## 1. AdminUser (tabela `admin_users` — módulo `auth`)

Conta de administrador de alto nível; bootstrap designa **exatamente uma**
(`is_bootstrap = True`).

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | PK (int) | — |
| `username` | string(100) | unique; case-insensitive (comparação em serviço); obrigatório |
| `password_hash` | string(255) | bcrypt (RNF10); jamais retornado fora de consulta de credencial |
| `role` | string enum `admin` | fixo `admin` para esta tabela |
| `is_active` | bool | default `True` |
| `is_bootstrap` | bool | default `False`; no máximo 1 linha |
| `created_at`, `updated_at` | timestamp (UTC) | geridas no código |

Estado: `is_active` True/Falso — sem fluxo de revogação nesta fase
(out-of-scope da spec).

## 2. Employee (tabela `employees` — módulo `employees`)

Conta de funcionário criada pelo administrador.

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | PK (int) | — |
| `name` | string(200) | obrigatório |
| `username` | string(100) | unique; case-insensitive; **único em toda a base** (contra `admin_users` também — checagem via serviço público de `auth`) |
| `password_hash` | string(255) | bcrypt; senha inicial gerada pelo sistema (exibida 1× — nunca persistida em texto plano) |
| `role` | string enum `employee` | fixo |
| `status` | string enum `active` \| `revoked` | default `active`; transição `active → revoked` (revoke) e `revoked → active` (reactivação via edição, clarificação Q3-s3) |
| `created_at`, `updated_at` | timestamp (UTC) | geridas no código |

Estados: `active` ⇄ `revoked`. Revogado: login recusado e **sessões em
curso recusadas** (FR-013 — revalidação de estado por requisição, research
R4). Nenhum soft-delete além disso (exclusão definitiva fora do escopo).

## 3. AuthSession (tabela `auth_sessions` — módulo `auth`)

Estado de renovação por sessão emitida (par de credenciais — clarificação Q1).

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | PK (int) | — |
| `account_type` | string enum `admin` \| `employee` | — |
| `account_id` | int | id em `admin_users` ou `employees` (sem FK cruzada entre domínios) |
| `refresh_token_hash` | string(64) | SHA-256 do token opaco; unique; indexado |
| `created_at` | timestamp (UTC) | emissão |
| `expires_at` | timestamp (UTC) | `created_at + JWT_REFRESH_TTL` |
| `revoked_at` | timestamp (UTC) nullable | logout, troca de par (emissão única) e nenhuma reutilização |

Transições: `ativa → rotated` (troca de par) | `ativa → revoked` (logout,
revogação de conta, bootstrap de senha da conta) | `ativa → expirada`
(`expires_at` passado). Credencial de renovação reutilizada/expirada/rotada/
revogada → recusa (401) sem emissão de novo par.

## Valores de runtime (não persistidos)

- **Access token (JWT HS256)**: claims `sub`, `account_type`, `role`, `sid`
  (id da AuthSession), `exp`/`iat` com `JWT_TTL`. Assinatura verificada e
  estado da conta recarregado a cada requisição (research R4).
- **Refresh token (opaco)**: `secrets.token_urlsafe(32)`; apenas o hash
  persiste; comparado por constante (hash no banco não devolve o segredo).
- **Config nova** (`core/config.py`): `jwt_refresh_ttl: int = 604800`
  (validação `> 0` igual ao padrão da fundação). `JWT_TTL` (3600) já existe.
- **Bootstrap (script)**: `ADMIN_USERNAME`, `ADMIN_PASSWORD` (env-only, sem
  default); upsert por `is_bootstrap = True` (research R7).

## Regras de integridade transversais

- Unicidade global de `username` (admin_users ∪ employees, case-insensitive)
  — FR-011; falha de cadastro/edição → 409 (não muta outras contas).
- Nenhuma senha em texto plano em código, banco, log ou resposta (RNF10,
  FR-007, FR-002).
- Toda escrita crítica gera registro de auditoria por `core.audit`
  (estrutura da fundação: actor/action/target/result/detail) — FR-014;
  login e logout de ambos os perfis também auditam.