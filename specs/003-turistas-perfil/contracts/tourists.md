# API Contract: tourists

Base: `/api/v1/tourists` (prefixo canônico de `core/routers.py`; módulo
`tourists`). Rotas/campos em inglês — Princípio VII. Payloads de exemplo em
português quando texto de usuário.

Autenticação: `Authorization: Bearer <access_token>` exceto nos endpoints
públicos `POST /tourists` e `POST /tourists/login`. Erros de requisição
(sintaxe/campos) → 422 (padrão Pydantic/FastAPI).

## POST /api/v1/tourists — cadastro de turista (RF22)

**Público.**

**Request** `TouristCreateRequest`:

```json
{
  "first_name": "string (1–100)",
  "last_name": "string (1–100)",
  "country_of_origin": "string (1–100)",
  "cpf": "123.456.789-09 | null",
  "passport_number": "AB123456 | null",
  "phone": "+5511999999999",
  "email": "ana@example.com",
  "password": "string (min 8)"
}
```

Validações (falha → 422 com mensagem específica do campo):

- `cpf`: com/sem máscara, normalizado a 11 dígitos, dígitos verificadores
  válidos (FR-013c). `passport_number`: `^[A-Za-z0-9]{6,10}$` (FR-002).
- **Exatamente um** de `cpf`/`passport_number` (FR-001).
- `phone`: `^\+[0-9]{8,15}$` (FR-013b). `email`: formato válido; trim +
  lowercase (FR-013). `password`: ≥ 8 (FR-005a). Textos: 1–100 após trim.

**201** `TouristRegistered` — **sem dado sensível em texto claro**:

```json
{ "id": 1, "first_name": "Ana", "last_name": "Silva", "country_of_origin": "Brasil" }
```

- Duplicado (`email_lookup`/`cpf_lookup`/`passport_lookup` já existe entre
  turistas) → **409** `{"detail": "tourist already registered"}` — sem
  revelar dados da conta existente.
- Auditoria: `tourist.register` (success) / tentativa falha de unicidade
  registrada como falha.

## POST /api/v1/tourists/login — login do turista (RF23)

**Público.**

**Request** `TouristLoginRequest`:

```json
{ "email": "ana@example.com", "password": "string" }
```

E-mail normalizado (trim+lower) antes da busca por `email_lookup`.

**200** `SessionResponse` (mesma forma da fundação — reuso):

```json
{
  "access_token": "string",
  "refresh_token": "string",
  "token_type": "bearer",
  "expires_in": 3600,
  "role": "tourist"
}
```

- Par completo (access JWT + refresh opaco single-use) emitido via
  `auth.services.issue_session` com `account_type="tourist"`.
  Renovação/log.out usam os endpoints **existentes** da fundação
  (`/auth/refresh`, `/auth/logout`) — nenhum endpoint duplicado.
- **401** `{"detail": "invalid credentials"}` — mensagem **genérica**:
  senha errada, e-mail inexistente ou não distinguível (FR-014).

## GET /api/v1/tourists/me — próprio perfil (RF24)

**Auth**: `require_tourist` (401 sem/inválido; 403 para admin/funcionário —
rota exclusiva do app Passaporte, FR-015).

**200** `TouristProfileResponse` — descriptografia controlada do próprio
documento/contato (FR-006/FR-007):

```json
{
  "id": 1,
  "first_name": "Ana",
  "last_name": "Silva",
  "country_of_origin": "Brasil",
  "email": "ana@example.com",
  "phone": "+5511999999999",
  "cpf": "12345678909",
  "passport_number": null,
  "interests": ["gastronomy", "nature"]
}
```

- Apenas categorias **atualmente configuradas** aparecem em `interests`
  (categoria órfã é omitida — edge case da spec).

## PATCH /api/v1/tourists/{tourist_id} — editar perfil (RF24/FR-009)

**Auth**: `get_current_user`. Permissão: **própria conta ou admin**.
Outro turista → **403** (cenário de aceitação da spec). Alvo inexistente
quando admin → **404**. Turista sem permissão → 403 **sem vazar** se o
id existe.

**Request** `TouristUpdateRequest` (campos opcionais, PATCH parcial):

```json
{
  "first_name": "string|null",
  "last_name": "string|null",
  "country_of_origin": "string|null",
  "phone": "+55...|null",
  "email": "ana@example.com|null",
  "cpf": "123.456.789-09|null",
  "passport_number": "AB123456|null"
}
```

Regras:

- Mesmas validações do cadastro para cada campo presente.
- **Troca de documento** (cpf ↔ passport) aceita: o campo enviado substitui
  o par; é obrigatório manter exatamente um documento após a edição
  (422 se o resultado final não tiver documento, ex.: enviar
  `{"passport_number": null}` sem `cpf`).
- Unicidade revalidada (e-mail/cpf/passaporte) → **409** em colisão.
- `password` **não** é editável aqui (fora de escopo — recuperação de
  senha é out-of-scope da spec).
- 204 sem corpo em sucesso; auditoria `tourist.profile.update`.
- Leitura equivalente: `GET /api/v1/tourists/{tourist_id}` devolve
  `TouristProfileResponse` com as mesmas regras de permissão (self/admin;
  403 para outro turista).

## GET /api/v1/tourists/interest-categories — categorias configuradas (FR-012)

**Auth**: qualquer conta autenticada (`get_current_user`; é dado de
configuração, não pessoal).

**200** `InterestCategoriesResponse` — exatamente as categorias do
`location.json` (RNF06):

```json
{
  "categories": [
    { "key": "gastronomy", "label": "Gastronomia" },
    { "key": "nature", "label": "Natureza" },
    { "key": "culture", "label": "Cultura" }
  ]
}
```

## GET /api/v1/tourists/me/interests — ler seleção (RF25)

**Auth**: `require_tourist`.

**200** `TouristInterestsResponse`:

```json
{ "interests": ["gastronomy", "nature"] }
```

Turista sem seleção → `{"interests": []}` (200, sem erro). Só categorias
configuradas; sem duplicatas.

## PUT /api/v1/tourists/me/interests — salvar/atualizar seleção (RF25)

**Auth**: `require_tourist`.

**Request** `TouristInterestsUpdateRequest`:

```json
{ "interests": ["gastronomy", "nature"] }
```

- Substitução **integral** da seleção (FR-010) — sem teto de quantidade
  (s3-Q1); lista vazia → limpa a seleção (válido).
- `category_key` fora da configuração → **422** com mensagem indicando a
  categoria inválida (FR-011).
- Duplicatas na entrada são normalizadas (aceitas uma vez) → **200**
  `TouristInterestsResponse` (mesma forma do GET) com a seleção persistida
  sem duplicatas.
- Auditoria `tourist.interests.update`.

## Regras transversais do contrato

- Rotas **exclusivas do turista** (`/me`, `/me/interests`,
  `PUT /me/interests`) → 403 para non-tourist autenticado
  (`require_tourist`, FR-015/s16).
- `/tourists/{tourist_id}` (GET/PATCH) → 401 (sem token), 403 (turista em
  conta alheia), 404 (admin, alvo inexistente).
- Mensagens de erro de credencial genéricas (FR-014); erros de unicidade
  sem vazamento (409).
- Nenhuma resposta contém `*_encrypted`, `*_lookup` ou `password_hash`.