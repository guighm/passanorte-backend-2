# Implementation Plan: Portas de Serviços Configuráveis via .env (Docker Compose)

**Branch**: `010-configurable-service-ports` | **Date**: 2026-11-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/010-configurable-service-ports/spec.md`

## Summary

Formalizar a configuração de portas do ambiente Compose (feature 004) para os
três serviços via variáveis `${VAR:-default}`: `API_PORT` passa a ser
end-to-end (mapeamento host **e** porta de escuta do uvicorn — hoje fixa na
8000 no `command:`), `POSTGRES_PORT` passa a expor o PostgreSQL à máquina host
com vínculo `127.0.0.1` (clarificação Q2), e `DBGATE_PORT` é apenas
formalizada. Portas internas (db 5432, dbgate 3000) permanecem fixas — toda
comunicação inter-serviços continua pela rede interna do Compose. Mudança
confinada a `compose.yaml` + `.env.example` (+ espelho no `.env` local,
git-ignored); Dockerfile, entrypoint, Dockerfile/EXPOSE e lógica de negócio
intactos (FR-007/008/009).

## Technical Context

**Language/Version**: Python 3.13 (projeto), Docker Compose v2 (sintaxe
`compose.yaml` com interpolação `${VAR:-default}`)

**Primary Dependencies**: `postgres:18-alpine`, `dbgate/dbgate:7.3.3`, imagem
`passanorte-back:dev` (build do Dockerfile da spec 004) — todos já existentes;
nenhuma dependência nova.

**Storage**: PostgreSQL 18 (volume nomeado `postgres-data` — sem alterações;
nenhum estado novo além das variáveis de ambiente).

**Testing**: suíte pytest existente (specs 001–003) não é afetada (nenhuma
variável de porta no ambiente de testes); validação desta feature é via
quickstart manual (precedente da 004) + `docker compose config` para validar
interpolação.

**Target Platform**: Docker Engine + Compose v2 na máquina host (Linux/macOS/Windows
com Docker Desktop) — ambiente de desenvolvimento local já estabelecido pela 004.

**Project Type**: infraestrutura técnica (monolito modular `passanorte_back`;
nenhum código em `src/` é tocado).

**Performance Goals**: N/A — não há novo caminho quente; a troca de porta exige
no máximo 1 restart do ambiente (SC-002/003).

**Constraints**: nenhum segredo novo no repositório; Dockerfile/EXPOSE e
`entrypoint.sh` intocados; inter-serviços sempre via rede interna (host `db`,
porta interna 5432); nenhuma porta interna configurável.

**Scale/Scope**: 3 serviços, 3 variáveis de porta, 2 arquivos alterados
(`compose.yaml`, `.env.example`), 1 espelho local (`.env`).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio (constituição v1.2.0) | Avaliação |
|---|---|
| I. API-Contract-First | **Pass** — nenhum endpoint ou contrato REST é tocado |
| II. Segurança e LGPD por Padrão | **Pass** — nova exposição do db é vinculada a `127.0.0.1` (não visível na rede local; SC-005); nenhum segredo novo cometido |
| III. Test-First (NON-NEGOTIABLE) | **Pass** — suíte pytest existente permanece verde (nenhum código de negócio tocado); validação da infra via quickstart V1–V5, precedente da 004 |
| IV. Dados geoespaciais | N/A — sem dados |
| V. Simplicidade (YAGNI) | **Pass** — 2 arquivos, 3 variáveis; sem resolução automática de conflito de porta (explícito no spec) |
| VI. Portabilidade por Configuração | **Pass (essência da feature)** — portas tornam-se configuração, não código |
| VII. Manutenibilidade | **Pass** — artefatos em inglês, comentários no compose mantidos e atualizados |
| Workflow (migrations/Alembic) | N/A — sem mudança de schema |
| Fronteiras (checker `modules/`) | **Pass** — nenhum arquivo em `src/passanorte_back/` é alterado |

**Veredicto pós-Phase 1: PASS** — sem violações; nenhuma entrada em Complexity
Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/010-configurable-service-ports/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── runtime-contracts.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
compose.yaml            # ALTERADO: ports do db (novo), api (end-to-end), dbgate (formalizado)
.env.example            # ALTERADO: adiciona POSTGRES_PORT (+ comentários revisados)
.env                    # Espelho local (git-ignored) — cp .env.example .env + ajustes do dev
Dockerfile              # INTACTO (EXPOSE 8000 = documentação; FR-009)
docker/entrypoint.sh    # INTACTO (recebe o command: do compose; nenhuma porta hardcoded nele)
src/, migrations/, tests/  # INTACTOS (specs 001–003)
```

**Structure Decision**: Nenhuma estrutura nova — feature de infraestrutura que
altera apenas arquivos de configuração de ambiente existentes (criados pela
spec 004). O checker de fronteiras de `src/passanorte_back/` não é exercitado
(nenhum arquivo de módulo muda).

## Complexity Tracking

> Vazio — Constitution Check passou sem violações (veredicto pós-design acima).