# Implementation Plan: Turistas e Perfil (módulo tourists)

**Branch**: `003-turistas-perfil` | **Date**: 2026-10-31 | **Spec**:
[spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-turistas-perfil/spec.md`

## Summary

Implementar o domínio `tourists`: cadastro único de turista (RF22) com
documento CPF **ou** passaporte, login do turista (RF23) reutilizando a
fundação JWT/sessões da spec 002, visualização/edição restrita ao próprio
perfil (RF24, 403 para terceiros) e seleção/atualização de categorias de
interesse (RF25) validadas contra lista configurável (RNF06). Dados
sensíveis (e-mail, CPF, passaporte, telefone) são armazenados criptografados
(RNF08) com coluna de lookup com hash para unicidade/indexação; senha
apenas como hash bcrypt (RNF10).

## Technical Context

**Language/Version**: Python 3.13 (type hints obrigatórios — princípio VII)

**Primary Dependencies**: FastAPI, Pydantic v2, SQLAlchemy 2.x
(Mapped/mapped_column), Alembic, bcrypt (`core.security` existente), pyjwt
(existente), **cryptography** (NOVO — Fernet para RNF08), pydantic-settings

**Storage**: PostgreSQL (produção) / SQLite (testes) via `database_url`
(RNF17); 2 tabelas novas no domínio `tourists` + extensão da tabela
`auth_sessions` (novo valor de `account_type`)

**Testing**: pytest (contrato em `tests/contract`, integração em
`tests/integration`, unidade em `tests/unit`) — banco isolado por teste
(constituição III)

**Target Platform**: Linux server (API REST consumida por painel React e
app Kotlin — RNF03/RNF05)

**Project Type**: web-service (monolito modular FastAPI)

**Performance Goals**: conformes à fundação — serviços essenciais
(auth/consulta) sem subsistemas pesados no caminho (RNF11/RNF12)

**Constraints**: dados sensíveis nunca em texto plano na persistência nem
em leitura de repositório fora de descriptografia controlada (RNF08,
SC-005); segredos somente em ambiente (nunca em código/repositório);
identificadores de código em inglês (princípio VII)

**Scale/Scope**: 1 nova migration de domínio (`20261031_0003_*`), 2 tabelas
novas, ~8 endpoints REST sob `/api/v1/tourists`, extensão da fundação
`auth` (sessions + RBAC para `account_type="tourist"`)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio / Gate | Status | Evidência |
|---|---|---|
| Monolito Modular (limites de domínio) | ✅ PASS | Tabelas novas só em `modules/tourists`; escrita em `auth_sessions` pelo serviço público de `auth` (regra 5); `tourists` não importa internals de `auth` |
| Interface de serviço entre módulos | ✅ PASS | `tourists.services` usa funções públicas de `auth.services` (issue/resolve); `auth.services` resolve turistas via lazy import da interface pública de `tourists.services` (padrãoemployees) |
| API-Contract-First | ✅ PASS | Schemas Pydantic request/response definidos em `contracts/tourists.md` antes da implementação (Fase 1) |
| Segurança e LGPD (II) | ✅ PASS | Fernet no repouso + HMAC para lookup (RNF08); bcrypt existente (RNF10); chave de criptografia em env (novo `sensitive_data_key` obrigatório) |
| Test-First (III) | ✅ PASS | Contrato + integração cadastro→login→editar→interesses no escopo de tarefas (test-first não-negociável) |
| Simplicidade/YAGNI (V) | ✅ PASS | Zero filas/caches; 1 dependência nova justificada (cryptography, RNF08 não existe sem cripto); sem endpoints além do uso demonstrado |
| Portabilidade (VI) | ✅ PASS | Categorias de interesse em dados (`config/location.json`) com resolução em `Settings` — troca por outra cidade não altera código |
| Manutenibilidade/Inglês (VII) | ✅ PASS | Nomenclatura canônica: módulo `tourists`, campos `first_name`, `passport_number`, chave `auth_sessions` alinhada à fundação |
| Gates transversais | ✅ PASS | Sem senha plano; sem import cruzado privado; migrations Alembic no escopo |

**Resultado do gate (pré-Fase 0)**: PASS — nenhuma violação a justificar.
Re-verificação pós-Fase 1 no fim deste plano.

## Project Structure

### Documentation (this feature)

```text
specs/003-turistas-perfil/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/tourists.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
src/passanorte_back/
├── core/
│   ├── config.py               # + sensitive_data_key (env obrigatório), interest_categories (location data)
│   ├── crypto.py               # NOVO: Fernet encrypt/decrypt + keyed-hash lookup (infra compartilhada)
│   ├── security.py             # sem mudança (bcrypt/JWT reutilizados)
│   └── modules.py              # sem mudança ("tourists" já canônico)
├── modules/
│   ├── auth/                   # EXTENSÃO da fundação (spec 002):
│   │   ├── repositories/auth_sessions.py   # AccountType += "tourist"
│   │   └── services/
│   │       ├── authentication.py           # issue_session público; refresh/logout c/ turista
│   │       └── security.py                 # get_current_user resolve "tourist"; + require_tourist
│   └── tourists/               # NOVO módulo de domínio (camadas próprias):
│       ├── repositories/tourists.py        # tabela tourists (colunas criptografadas + lookup)
│       ├── repositories/tourist_interests.py
│       ├── schemas/                        # Pydantic v2 (contract-first)
│       ├── services/                       # cadastro, login, perfil, interesses, validadores
│       └── routes/                         # endpoints /api/v1/tourists/**
migrations/versions/20261031_0003_tourists.py   # NOVO: tourists + tourist_interests
config/location.json                            # + interest_categories (dados portáteis, RNF06)

tests/
├── conftest.py                 # fixtures existentes (+ crypto key de teste)
├── contract/
│   ├── test_tourists_register.py
│   ├── test_tourists_login.py
│   ├── test_tourists_profile.py
│   └── test_tourists_interests.py
├── integration/
│   └── test_tourists_lifecycle.py         # cadastro → login → editar → interesses (SC-003)
└── unit/
    └── test_crypto.py                     # Fernet/HMAC + validadores CPF/passaporte
```

**Structure Decision**: estrutura de monolito modular existente mantida —
módulo `tourists` com as quatro camadas próprias (regra 4 da constituição),
infra de criptografia compartilhada em `core/crypto.py` (infra é de core),
fundação `auth` estendida por novos valores de enum + dependência
`require_tourist` (mesma fronteira, sem reescrita).

## Complexity Tracking

> Nenhuma violação de constituição a justificar — seção vazia.