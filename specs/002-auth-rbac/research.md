# Research: Autenticação e Controle de Acesso (RBAC)

Feature: `/specs/002-auth-rbac/spec.md` | Date: 2026-10-31

## R1 — Hash de senha: biblioteca e parâmetros

**Decision**: `bcrypt` diretamente (pip `bcrypt>=4`), rounds padrão (12); sem
passlib (em manutenção irregular, sem ganho sobre o bcrypt puro).
**Rationale**: exigência explícita de RNF10 ("ex.: bcrypt"), dependência
minimalista (YAGNI), API estável e verificável com
`bcrypt.checkpw()`; hash+salt incluído na própria string do hash.
**Alternatives considered**: argon2 (também aceito pela Constituição, dep
extra sem necessidade aparente nesta escala); passlib (camada desnecessária).

## R2 — Access token: formato e verificação

**Decision**: JWT assinado HS256 com `pyjwt>=2.10`, segredo `JWT_SECRET`
env; claims: `sub`, `account_type` (`admin` | `employee`), `role`, `exp`,
`iat`. Vida curta = `JWT_TTL` (default 3600 s, já existente no config).
**Rationale**: RNF09 pede JWT explicitamente; HS256 + segredo único é o mais
simples para um monolito de processo único (sem rotação assimétrica — YAGNI).
**Alternatives considered**: RS256/par de chaves (justificado só com
múltiplos emissores/verificadores — não é o caso); opaque stateless (não dá
perfil na resposta nem padrão JWT exigido).

## R3 — Credencial de renovação: representação e revogação

**Decision**: refresh **opaco** (secrets.token_urlsafe, 32 bytes) persistido
como **hash** (SHA-256) na tabela `auth_sessions` do módulo `auth`, com
expiração `JWT_REFRESH_TTL` (default 7 dias), emissão única (troca sempre
por novo par) e revogação por linha (`revoked_at`). Logout = revogar a linha
da sessão corrente (identificada por `jti`/`sid` claim no access token).
**Rationale**: o par clarificado (Q1) exige logout e revogação efetiva da
credencial de renovação — estado no servidor é o mais simples e o mais
barato para revogar imediatamente (YAGNI). Reuso de credencial de renovação
trocada → negado por emissão única (a linha vira estado "rotated").
**Alternatives considered**: JWT como refresh (revogação exige denylist —
mesmo custo, mais peças); não persistir (impossibilita logout/revogação).

## R4 — Revogação efetiva para sessões em curso (FR-013)

**Decision**: resolução do usuário autenticado = verificar assinatura/exp do
JWT **e recarregar estado da conta no banco a cada requisição**
(`is_active`/status do funcionário). Conta inativa → 401.
**Rationale**: a spec exige que revogar um funcionário mate sessões em
curso; com monolito/banco relacional o custo de 1 SELECT por requisição é
insignificante nesta escala e elimina a necessidade de denylist.
**Alternatives considered**: confiar só no claim do token (violaria FR-013);
denylist/cache (complexidade sem necessidade — YAGNI).

## R5 — Divisão de responsabilidade auth × employees

**Decision**: `auth` é dono de: `admin_users`, `auth_sessions`, login/refresh/
logout, bootstrap da conta admin, hashing/verificação (via `core.security`) e
das dependências de RBAC. `employees` é dono de: tabela/service `employees`
(criar/editar/revogar/reativar). `auth` consulta credenciais de funcionário
exclusivamente por função pública de `employees.services`
(`find_by_username` → username, password_hash, status); `employees` verifica
disponibilidade de username exclusivamente por função pública de
`auth.services` (`is_username_taken`, cobrindo admin_users). **Nenhuma
tabela compartilhada; nenhuma escrita cross-domain direta** (regras 3–5).
**Rationale**: limite de domínio que espelha o corte de microsserviços:
`auth` sobrevive à extração como serviço de identidade.
**Alternatives considered**: tabela única de contas (mais simples, viola a
separação de bounded contexts e dificulta a extração futura); duplicar checagem
de unicidade por SQL (compartilharia tabela entre domínios).

## R6 — RBAC e 401/403

**Decision**: dependências FastAPI em `core/security.py`:
`get_current_user` (401 sem token/inválido/expirado/conta inativa) e
`require_admin` (403 com conta autenticada sem perfil admin). Todas as rotas
do painel usam `require_admin`; o endpoint futuro de concessão de benefícios
usará `require_admin` + `get_current_user` de funcionário (a permissão da
funcionalidade é da feature futura — os testes desta fase verificam 403 nos
endpoints administrativos e 401/403 genéricos).
**Rationale**: erro de autenticação ≠ autorização (FR-015); dependências
centrais evitam repetição por módulo e facilitam auditoria do gate.
**Alternatives considered**: decorators por serviço (menos idiomático em
FastAPI); RBAC por tabela de permissões (superflúzilo — YAGNI; perfis são 2).

## R7 — Bootstrap da conta administrativa (RF01)

**Decision**: script `scripts/create_admin.py` com entrada
`[project.scripts] create-admin` no `pyproject` (`uv run create-admin`).
Env obrigatórios: `ADMIN_USERNAME`, `ADMIN_PASSWORD` (ausentes → erro claro,
sem tocar o banco). Upsert por **designação de bootstrap** (clarificação Q4):
a conta é marcada com `is_bootstrap = True`; reexecução atualiza
em vigor username e senha (novo hash bcrypt) e restaura `is_active`; nunca
cria segunda conta. Auditoria registra a ação (actor "system/bootstrap").
**Rationale**: regras RF01 + clarificação Q4 + FR-002 (env-only);
idempotência verificável por teste de integração.
**Alternatives considered**: CLI interativa (não idempotente nem
automação-friendly); seed no app startup (executa com o processo em
produção — menor controle/observabilidade).

## R8 — Configuração nova

**Decision**: adicionar `jwt_refresh_ttl: int = 604800` (s) ao
`core/config.py` com a mesma validação `> 0` existente; nenhum segredo novo
com default. `JWT_SECRET`, `ADMIN_USERNAME`, `ADMIN_PASSWORD` continuam sem
default (erro claro na ausência).
**Rationale**: VI (portabilidade por configuração); padrão já estabelecido
pela fundação. **Alternatives considered**: fixar vida útil no código
(viola VI); unificar TTL única (remove o par clarificado).

## R9 — Testes com banco isolado

**Decision**: fixture de app de teste sobrescrevendo a dependência
`get_session` com um engine SQLite em memória por sessão/tabela
(`StaticPool`, migrations executadas no startup do fixture) + fixture que
semeia admin de teste e captura auditoria (logger
`passanorte.audit` com handler próprio, via `caplog`).
TTLs curtos configuráveis por env do teste para expiração de token.
**Rationale**: princípio III + padrão já usado pelos smoke tests da fundação.
**Alternatives considered**: banco em arquivo por teste (mais lento);
mock de repositório (não exercita integração ponta a ponta).

## R10 — Convenções

**Decision**: rotas/campos/schemas em inglês (Princípio VII); código de erro
de login → 401 com mensagem genérica ("invalid credentials", sem revelar
qual campo falhou); username unique case-insensitive (comparação
case-folding em serviço); respostas Pydantic (nunca expor `password_hash`);
auditoria em create/edit/revoke/reactivate de employees + login/logout/
bootstrap.
**Rationale**: qualidade de contrato do painel + FR-014/RNF19 + NFR de
segurança (não revelar existência/não-existência de usuário).