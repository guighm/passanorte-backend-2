# Data Model: Turistas e Perfil (módulo tourists)

Feature: `/specs/003-turistas-perfil/spec.md` | Date: 2026-10-31

Tabelas persistidas: 2, em 1 migration de domínio
(`20261031_0003_tourists`, acima de `20261031_0002_auth_accounts`).
Nenhuma tabela compartilhada entre domínios (regra 4); escrita em
`auth_sessions` só pelo serviço público de `auth` (regra 5). Nenhuma FK
cruzada entre domínios (`tourist_interests` → `tourists` são do mesmo
domínio).

## 1. Tourist (tabela `tourists` — módulo `tourists`)

Conta do turista na aplicação Passaporte. Campos sensíveis armazenados
**criptografados** (Fernet, IV aleatório — RNF08); campos de igualdade
ganham coluna irmã `*_lookup` com HMAC-SHA256 keyado (research R1).

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | PK (int) | — |
| `first_name` | string(100) | obrigatório; 1–100 após trim (FR-013d) |
| `last_name` | string(100) | obrigatório; 1–100 após trim (FR-013d) |
| `country_of_origin` | string(100) | obrigatório; texto livre, 1–100 após trim (FR-013a/FR-013d) |
| `email_encrypted` | string(n/a) | Fernet; **nunca texto claro** (RNF08) |
| `email_lookup` | string(64) | HMAC-SHA256 de e-mail normalizado (trim+lower, FR-013); **unique entre turistas** (FR-003, clar. s1-Q1); indexado |
| `phone_encrypted` | string(n/a) | Fernet; formato `+DDI` validado na entrada (FR-013b) |
| `cpf_encrypted` | string(n/a) nullable | Fernet; CPF normalizado (11 dígitos, FR-013c) |
| `cpf_lookup` | string(64) nullable | HMAC do CPF; **unique** (com NULLs distintos) |
| `passport_encrypted` | string(n/a) nullable | Fernet; alfanumérico 6–10 (FR-002, clar. s2-Q2) |
| `passport_lookup` | string(64) nullable | HMAC do passaporte; **unique** (com NULLs distintos) |
| `password_hash` | string(255) | bcrypt existente (RNF10); senha ≥ 8 chars (FR-005a); jamais retornado fora de consulta de credencial |
| `created_at`, `updated_at` | timestamp (UTC) | geridas no código |

Regras de integridade:

- **Exatamente um documento**: `cpf_lookup` XOR `passport_lookup`
  obrigatório no cadastro (FR-001); troca de documento na edição aceita se
  válido e único (edge case da spec).
- Unicidade de `email_lookup`/`cpf_lookup`/`passport_lookup` **somente
  entre turistas** — contas admin/funcionário fora da checagem
  (clarificação s1-Q1). Falha → 409.
- Repositório: criação/atualização por colunas `*_encrypted`/`*_lookup`;
  **nenhum método de leitura descriptografa** (SC-005) — descriptografia
  acontece em `services`, apenas para o próprio perfil ou admin
  (descriptografia controlada, FR-006).

## 2. TouristInterest (tabela `tourist_interests` — módulo `tourists`)

Seleção de categorias de interesse do turista (RF25).

| Coluna | Tipo | Regras |
|---|---|---|
| `id` | PK (int) | — |
| `tourist_id` | int, FK → `tourists.id`, indexado, ON DELETE CASCADE | dono da seleção |
| `category_key` | string(100) | **deve** pertencer a `Settings.resolved_interest_categories()` no momento da escrita (FR-011) |
| unique `(tourist_id, category_key)` | — | sem duplicatas |

Estado/operacional (sem transições próprias):

- **Escrita** (`PUT /tourists/me/interests`): substitui integralmente a
  seleção — delete+insert na mesma transação (FR-010, s3-Q1: sem teto
  artificial de quantidade).
- **Categoria órfã** (removida da configuração após cadastro): linha
  permanece, mas a leitura do turista **filtra pelas categorias ainda
  configuradas** — não quebra, não reaparece (edge case da spec).
- Leitura por joins futuros (notificações) — tabela relacional, R5.

## 3. Extensão da fundação: `auth_sessions` (módulo `auth` — spec 002)

Sem mudança de schema (coluna `account_type: String(10)` sem CHECK):

| Alteração | Detalhe |
|---|---|
| `AccountType` | `Literal["admin", "employee", "tourist"]` (enum em código) |
| `ACCOUNT_TYPES` | `+ ("tourist",)` |
| Linhas de turista | criadas **apenas** por `auth.services.issue_session` (ex-`_issue_pair`, now pública) chamado por `tourists.services` |

## Valores de runtime (não persistidos)

- **Access token**: claims existentes — `account_type="tourist"`,
  `role="tourist"`, `sub=<tourists.id>`, `sid=<auth_sessions.id>`,
  `exp`/`iat` com `jwt_ttl` (reuso integral de `core.security`).
- **Refresh token**: opaco `urlsafe(32)`; hash SHA-256 na sessão (padrão
  da fundação).
- **Config nova em `core/config.py`**:
  - `sensitive_data_key: str` — **sem default**, obrigatória (Fernet key
    url-safe de 32 bytes); erro nomeando o campo no boot (padrão
    `database_url`/`jwt_secret`).
  - `resolved_interest_categories()` — de `location.json`
    (`interest_categories: [{key, label}, ...]`), keys em inglês, label em
    português (RNF06; default da spec: gastronomy/nature/culture).
- **`location.json` novo bloco** (dados, não código):
  `"interest_categories": [{"key": "gastronomy", "label": "Gastronomia"},
  {"key": "nature", "label": "Natureza"}, {"key": "culture", "label":
  "Cultura"}]`.
- **HMAC lookup key**: derivada de `sensitive_data_key` (HKDF com sal fixo
  e info distinta por campo) — nenhuma segunda chave em env.

## Regras de integridade transversais

- Nenhum dado sensível em texto plano: persistência (Fernet), logs
  (nunca), respostas (só descriptografia controlada para self/admin) —
  RNF08, SC-005.
- Nenhuma senha em texto plano em código/banco/testes — RNF10.
- Auditoria (RNF19, `core.audit`): `tourist.register`,
  `tourist.login.success`/`tourist.login.failure` (mensagem genérica sem
  distinguir causa — FR-014), `tourist.profile.update`,
  `tourist.interests.update`.
- RBAC na fundação: `get_current_user` resolve `account_type="tourist"`
  recarregando estado do turista a cada requisição; `require_tourist`
  (403) protege rotas exclusivas do app Passaporte; `/tourists/{id}`
  aceita self **ou** admin (princípio I), rejeita outro turista (403) —
  FR-009/s16.