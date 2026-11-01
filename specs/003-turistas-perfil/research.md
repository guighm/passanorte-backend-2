# Research: Turistas e Perfil (módulo tourists)

Feature: `/specs/003-turistas-perfil/spec.md` | Date: 2026-10-31

Fase 0 — resolução de decisões técnicas. A fundação da spec 002
(autenticação JWT, sessões com refresh opaco, RBAC admin/funcionário) já
existe e foi lida em código; decisões abaixo partem dela.

## R1 — Criptografia de dados sensíveis (RNF08)

**Decision**: criptografia de campo com **Fernet** (lib `cryptography`,
AES-128-CBC + HMAC, IV aleatório) para os valores sensíveis em repouso,
**mais** uma coluna irmã de *lookup* com **HMAC-SHA256 keyado** para cada
campo que precisa de unicidade/busca por igualdade (e-mail, CPF,
passaporte). Telefone não participa de unicidade → só ciphertext.

- `email_encrypted` (Fernet) + `email_lookup` (HMAC) — login resolve por
  `email_lookup`; unicidade por `email_lookup` unique.
- `cpf_encrypted` + `cpf_lookup` (nullable) e `passport_encrypted` +
  `passport_lookup` (nullable) — unicidade entre turistas (resposta Q1-s1)
  por lookup unique, com `NULLs` distintos permitidos.
- Exibição ao próprio turista (FR-007) = descriptografia controlada no
  serviço de perfil; **repositório nunca descriptografa** (retorna
  ciphertext/lookup — SC-005).

**Rationale**: padrão de mercado para *searchable encryption* — o IV
aleatório do Fernet dá confidencialidade real, mas quebra busca por
igualdade; o HMAC keyado dá igualdade/indexação (unicidade) sem expor o
valor. Deterministic encryption única (AES-SIV) seria 1 coluna, mas
introduz modo hazardous e mescla dois papéis no mesmo artefato; as duas
colunas tornam a propriedade de cada dado explícita e testável.

**Alternatives considered**: AES-SIV determinístico único (rejeitado —
modo menos inspecionado, acoplamento igualdade↔confidencialidade);
armazenar texto plano (proibido RNF08); criptografia em nível de banco
(pgcrypto — acopla ao PostgreSQL, quebra testes SQLite).

## R2 — Chave de criptografia (RNF08 + FR-011 de segredos)

**Decision**: nova config **obrigatória** em `Settings`:
`sensitive_data_key: str` (Fernet key de 32 bytes url-safe, sem default).
Segredo em env/`.env` apenas. Fixture de teste gera chave efêmera. Ausente
no boot → erro nomeando o campo (padrão de `database_url`/`jwt_secret`).

**Rationale**: mesma disciplina da fundação (FR-010/FR-011 da spec 002).
**Alternatives**: key derivada do `jwt_secret` (rejeitado — reuso de
segredo entre propósitos distintos).

## R3 — Extensão da fundação auth para turista (RF23, RNF09)

**Decision**: turista é **terceiro tipo de conta** na fundação:

- `auth_sessions`: `ACCOUNT_TYPES += ("tourist",)`,
  `AccountType = Literal["admin", "employee", "tourist"]` — sem migration
  (coluna `account_type` é String(10) sem CHECK no banco; enum é em código).
- `auth.services.authentication`: `_issue_pair` vira função **pública**
  `issue_session(session, *, account_type, account_id, role)` — interface
  de serviço (regra 5) usada por `tourists.services` para emitir o par de
  credenciais do turista.
- `login`/`refresh` do auth permanecem para admin/funcionário (contrato
  atual inalterado). O login do turista mora em `POST /api/v1/tourists/login`
  (domínio dono do cadastro) e emite o par chamando `issue_session`.
- `refresh/logout` passam a revalidar estado do turista via *lazy import*
  da interface pública de `tourists.services` (mesmo padrão já usado com
  `employees.services` — resolve ciclos de import).
- `get_current_user` ganha ramo `account_type == "tourist"` (lazy import);
  novo gate `require_tourist` (403) para rotas exclusivas do app
  Passaporte — FR-015/s15: papel não-turista → 403.

**Rationale**: sessões são do domínio `auth` (regra 4 — nenhuma tabela
compartilhada); resolver/revalidar identidade é papel da dependência de
auth, que carrega estado via interfaces públicas. Separar
`/tourists/login` de `/auth/login` mantém credencial por tipo (e-mail vs
username) sem sobrecarregar o endpoint do painel.

**Alternatives**: turista logando no `/auth/login` genérico (rejeitado —
mistura contratos e campos diferentes); tabela de sessões própria em
`tourists` (rejeitado — duplica a fundação, fere regra 4).

## R4 — Categorias de interesse configuráveis (RNF06, FR-011/FR-012)

**Decision**: `config/location.json` ganha `interest_categories`: lista de
objetos `{"key": "<english-key>", "label": "<texto em pt>"}` — key canônica
de código em inglês (princípio VII), label é dado de usuário em português.
`Settings.resolved_interest_categories()` lê o arquivo com o mesmo padrão
de `resolved_languages()` (dados > código; erro estruturado se ausente/
vazio/inválido). Default exigido pela spec: gastronomia, natureza, cultura
(`gastronomy`, `nature`, `culture`).

**Rationale**: mesma mecânica de portabilidade já validada na fundação
(cidade/idiomas em dados). i18n-ready: a dupla key+label permite traduzir
labels sem tocar em lógica (RNF13/RNF16).

**Alternatives**: tabela no banco (rejeitado — mais uma migration e um
endpoint de CRUD para dado essencialmente estático/portável); constante em
código (rejeitado — fere RNF06/princípio VI).

## R5 — Persistência dos interesses (RF25)

**Decision**: tabela `tourist_interests` (`tourist_id`, `category_key`)
com unique `(tourist_id, category_key)` e FK para `tourists`. Escrita
substitui integralmente a seleção (delete+insert numa transação — FR-010).
Leitura do turista **filtra pelas categorias atualmente configuradas**
(edge case da categoria órfã — não quebra, não reaparece).

**Rationale**: relacional simples e verificável por constraint; notificações
futuras consultam por join. **Alternatives**: lista em coluna JSON
(rejeitado — sem integridade referencial e sem unique); tabela de categorias
no banco (rejeitado — ver R4).

## R6 — Validações de documento e contato (FR-002/FR-005a/FR-013*)

**Decision** (regras exatas para o contrato):

- **CPF**: aceita com/sem máscara; normaliza para 11 dígitos; valida
  dígitos verificadores oficiais (algoritmo peso 2–9 duas voltas).
- **Passaporte**: regex `^[A-Za-z0-9]{6,10}$` (alfanumérico, 6–10,
  clarificação s2-Q2).
- **Telefone**: regex `^\+[0-9]{8,15}$` (E.164-ish; sem `+` → rejeita,
  clarificação s1-Q4).
- **E-mail**: trim + lowercase antes de comparar/persistir (FR-013);
  validação por e-mail regex/`EmailStr` Pydantic.
- **Texto livre**: nome/sobrenome/país = 1–100 chars após trim
  (FR-013a/FR-013d).
- **Senha**: mínimo 8 caracteres (FR-005a); hash bcrypt com os rounds
  existentes (`core.security`), 255 chars de coluna.

**Rationale**: os limites vêm das clarificações registradas na spec — cada
regra vira um caso de teste de contrato determinístico.

## R7 — Contrato de rotas do domínio (RF22–25, FR-009/s16)

**Decision**: rotas em `/api/v1/tourists` (prefixo canônico `core/routers`):

- `POST /tourists` — cadastro público (201/409/422).
- `POST /tourists/login` — login público do turista (200/401).
- `GET/PATCH /tourists/{tourist_id}` — leitura/edição de perfil: própria
  conta **ou** admin (princípio I); turista em conta alheia → **403** (o
  cenário de aceitação da spec) e 404 para admin sem alvo existente.
- `GET /tourists/me` + `GET /tourists/me/interests` + `PUT
  /tourists/me/interests` — atalhos do próprio perfil (turista apenas,
  `require_tourist`).
- `GET /tourists/interest-categories` — categorias configuradas
  (qualquer conta autenticada; é dado de configuração, não pessoal).
- Leitura/edição por `tourist_id` expõe os dados descriptografados **só
  quando permitido** (self/admin) — descriptografia controlada (FR-006).

**Rationale**: `/tourists/{id}` materializa o teste "403 em edição de outro
usuário" de forma natural; `/me` simplifica o app. **Alternative**: só
`/me` (rejeitado — impossibilita o cenário 403 exigido e o acesso admin do
princípio I).

## R8 — Migração e estrutura do módulo

**Decision**: 1 migration de domínio `20261031_0003_tourists` criando as
2 tabelas do domínio (regra 4). Estrutura em camadas: `repositories/`,
`services/`, `schemas/`, `routes/` sob `modules/tourists/`. `core/crypto.py`
recebe Fernet+HMAC (infra compartilhada — outros domínios com dado sensível
reusarão). Auditoria: eventos `tourist.register`, `tourist.login.success`,
`tourist.login.failure`, `tourist.profile.update`, `tourist.interests.update`
via `core.audit.record_action` (RNF19, padrão da fundação).

**Alternatives**: 2 migrations separadas (rejeitado — mesmo domínio, menor
granularidade em 1 release); crypto dentro do módulo tourists (rejeitado —
infra de cripto é compartilhada por definição).