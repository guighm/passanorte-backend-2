# API Contract: auth

Base: `/api/v1/auth` (router canônico da fundação, `core/routers.py`.
Rotas/schemas em inglês — Princípio VII).

## POST /api/v1/auth/login

Autentica admin/funcionário (endpoint único — clarificação Q2).

**Request** `LoginRequest`:

```json
{ "username": "string", "password": "string" }
```

**200** `SessionResponse`:

```json
{
  "access_token": "string",
  "refresh_token": "string",
  "token_type": "bearer",
  "expires_in": 3600,
  "role": "admin" | "employee"
}
```

- Ambos os tokens emitidos em par (Q1); `expires_in` = vida útil do access
  token (s). Sem cache de credencial; auditoria: `login.success`,
  `login.failure` (sem distinção entre senha errada/usuário inexistente/
  conta revogada — R10).
- **401** `{"detail": "invalid credentials"}` — senha incorreta, usuário
  inexistente, conta inativa/revogada. Mensagem genérica (R10).

## POST /api/v1/auth/refresh

**Request** `RefreshRequest`: `{ "refresh_token": "string" }`

**200** `SessionResponse` (novo par, mesma função do refresh anterior).

- Troca emissão única: a linha de sessão vira `rotated`.
- **401** — token inválido, inexistente, expirado, rotado, revogado ou conta
  inativa/revogada na revalidação do estado.

## POST /api/v1/auth/logout

**Auth**: `Authorization: Bearer <access_token>` (401 sem/inválido/expirado).

**204**

- Invalida a credencial de renovação daquela sessão (`sid` claim do access
  token) e encerra a sessão de imediato: como a identidade é revalidada
  contra o estado da sessão a cada requisição, a própria credencial de uso
  também é rejeitada a partir do logout (comportamento mais rigoroso que
  o texto original da FR-016 — a sessão inteira morre no logout; auditoria
  `logout`).

## Regras transversais do contrato

- Todo endpoint do painel fora de `/auth/login` e `/auth/refresh` exige
  bearer token (401) e a função requerida (403) — dependências
  `core.security.get_current_user` / `require_admin` (FR-015).
- Erros de requisição (sintaxe/campos) → 422 (padrão Pydantic/FastAPI).