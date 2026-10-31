# Contrato HTTP: Grupos de Rotas de Módulo

Feature: `/specs/001-fundacao-monolito-modular/spec.md` | Date: 2026-10-30
(renomeado para nomes canônicos em inglês em 2026-10-31 — constituição v1.1.0,
Princípio VII)

Na fundação, os módulos são registrados na aplicação única **sem endpoints de
negócio** (FR-006/FR-007). O contrato abaixo define o espaçamento de nomes que
as features futuras obrigatoriamente reutilizam — contratos de cada RF virão
nas specs/contratos correspondentes e na OpenAPI de runtime.

## Convenções de espaço de nomes

- **Prefixo versionado**: `/api/v1` (clarificação Q4) — todo contrato de
  negócio vive sob este prefixo.
- **Fonte dos nomes**: lista canônica `DOMAIN_MODULES` em
  `src/passanorte_back/core/modules.py` (constituição, regra 2; nomes de
  pacote em inglês, nomenclatura English-only NON-NEGOTIABLE — Princípio VII).
- **Prefixo de módulo**: nome canônico do domínio com `_` → `-`
  (ex.: `tourist_spots` → `/api/v1/tourist-spots`); implementado por
  `module_prefix()` em `core/routers.py`.
- **Fora do prefixo**: `GET /health` e a documentação (`/docs`, `/openapi.json`)
  na raiz.

## Grupos registrados na fundação

| Grupo de rotas | Prefixo | Endpoints na fundação |
|---|---|---|
| auth | `/api/v1/auth` | nenhum (esqueleto) |
| employees | `/api/v1/employees` | nenhum |
| tourists | `/api/v1/tourists` | nenhum |
| tourist_spots | `/api/v1/tourist-spots` | nenhum |
| events | `/api/v1/events` | nenhum |
| gamification | `/api/v1/gamification` | nenhum |
| visitation | `/api/v1/visitation` | nenhum |
| dashboard | `/api/v1/dashboard` | nenhum |
| notifications | `/api/v1/notifications` | nenhum |
| chatbot | `/api/v1/chatbot` | nenhum |

## Verificações de contrato (suíte smoke)

- A aplicação sobe com todos os grupos montados (US-2, cenário 2).
- Os routers montados correspondem 1:1 a `DOMAIN_MODULES` com os prefixos
  acima (routers vazios não geram paths no OpenAPI — verificação pelos
  routers, não pelos paths).
- O OpenAPI (`/openapi.json`) expõe os 10 prefixos acima quando os routers
  ganharem endpoints.
- Nenhum endpoint fora do padrão de prefixo (exceto `/health` e docs).
- `GET /health` não exige autenticação para nenhum dos grupos.