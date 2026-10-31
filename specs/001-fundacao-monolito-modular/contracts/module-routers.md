# Contrato HTTP: Grupos de Rotas de Módulo

Feature: `/specs/001-fundacao-monolito-modular/spec.md` | Date: 2026-10-30

Na fundação, os módulos são registrados na aplicação única **sem endpoints de
negócio** (FR-006/FR-007). O contrato abaixo define o espaçamento de nomes que
as features futuras obrigatoriamente reutilizam — contratos de cada RF virão
nas specs/contratos correspondentes e na OpenAPI de runtime.

## Convenções de espaço de nomes

- **Prefixo versionado**: `/api/v1` (clarificação Q4) — todo contrato de
  negócio vive sob este prefixo.
- **Prefixo de módulo**: nome do pacote com `_` → `-`
  (ex.: `pontos_turisticos` → `/api/v1/pontos-turisticos`).
- **Fora do prefixo**: `GET /health` e a documentação (`/docs`, `/openapi.json`)
  na raiz.

## Grupos registrados na fundação

| Grupo de rotas | Prefixo | Endpoints na fundação |
|---|---|---|
| auth | `/api/v1/auth` | nenhum (esqueleto) |
| funcionarios | `/api/v1/funcionarios` | nenhum |
| turistas | `/api/v1/turistas` | nenhum |
| pontos_turisticos | `/api/v1/pontos-turisticos` | nenhum |
| eventos | `/api/v1/eventos` | nenhum |
| gamificacao | `/api/v1/gamificacao` | nenhum |
| visitacao | `/api/v1/visitacao` | nenhum |
| dashboard | `/api/v1/dashboard` | nenhum |
| notificacoes | `/api/v1/notificacoes` | nenhum |
| chatbot | `/api/v1/chatbot` | nenhum |

## Verificações de contrato (suíte smoke)

- A aplicação sobe com todos os grupos montados (US-2, cenário 2).
- O OpenAPI (`/openapi.json`) expõe os 10 prefixos acima.
- Nenhum endpoint fora do padrão de prefixo (exceto `/health` e docs).
- `GET /health` não exige autenticação para nenhum dos grupos.