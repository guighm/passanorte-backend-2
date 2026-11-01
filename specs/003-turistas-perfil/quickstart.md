# Quickstart: Turistas e Perfil (validação ponta a ponta)

Feature: `/specs/003-turistas-perfil/spec.md` | Date: 2026-10-31

Guia de validação — como provar que a feature funciona, de fora para dentro
(artefatos de design em `data-model.md` e `contracts/tourists.md`; passos de
implementação em `tasks.md`).

## Pré-requisitos

- Python 3.13 com o ambiente do projeto (`uv sync` ou equivalente do
  `pyproject.toml`) — dependência nova `cryptography` precisa estar
  instalada.
- Variáveis de ambiente obrigatórias (nada de segredo em código — RNF08/11):

```sh
DATABASE_URL="sqlite:///./dev.db"        # ou PostgreSQL em prod
JWT_SECRET="<segredo-em-env>"
SENSITIVE_DATA_KEY="<fernet-key-32-bytes-urlsafe>"  # NOVO e obrigatório
```

- Gerar chave Fernet (uma vez, em env/.env — nunca no repo):

```sh
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

- `config/location.json` com o bloco `interest_categories`
  (gastronomy/nature/culture — ver `data-model.md`).

## Suíte de testes (critério de aceitação)

```sh
uv run pytest tests/unit/test_crypto.py tests/contract/test_tourists_register.py tests/contract/test_tourists_login.py tests/contract/test_tourists_profile.py tests/contract/test_tourists_interests.py tests/integration/test_tourists_lifecycle.py
```

O que cada cenário prova (rastreabilidade SC→teste):

| Cenário | Teste | Prova |
|---|---|---|
| Cadastro com CPF com máscara válido → 201 sem dado sensível na resposta | `contract/test_tourists_register.py` | RF22, FR-013c, SC-005 |
| CPF inválido (verificadores) / e-mail malformado / telefone sem `+` / passaporte fora de `6-10` alfanumérico → 422 específico | idem | SC-001 |
| E-mail duplicado (e cpf/passaporte) → 409 sem vazamento | idem | SC-002 |
| Dois cadastros simultâneos com mesmo e-mail → exatamente 1 persiste | idem | SC-002 |
| Senha < 8 → 422 | idem | FR-005a |
| Login correto → par de tokens com `role=tourist` | `contract/test_tourists_login.py` | RF23, FR-004 |
| Login errado → 401 mensagem genérica (senha errada == e-mail inexistente) | idem | FR-014 |
| Token de admin/funcionário em rota exclusiva (`/me`) → 403 | idem | FR-015 |
| `GET /me` retorna dados descriptografados do próprio perfil | `contract/test_tourists_profile.py` | FR-006/FR-007 |
| `GET/PATCH /tourists/{outro_id}` do turista → **403**, nada muda | idem | FR-009, SC-004 |
| Editar próprio perfil → 204 e leitura seguinte reflete valores | idem | RF24 |
| Troca de e-mail para e-mail alheio → 409 | idem | FR-003 |
| Categorias listadas == configuração | `contract/test_tourists_interests.py` | RNF06, SC-006 |
| Interesses salvos/atualizados integralmente; categoria inexistente → 422 | idem | RF25, FR-010/FR-011 |
| Turista sem seleção → `[]` sem erro | idem | edge case |
| **Ponta a ponta**: cadastro → login → `GET /me` → `PATCH /me` → `PUT /me/interests` → `GET /me/interests` | `integration/test_tourists_lifecycle.py` | SC-003 |
| Nenhum `*_encrypted`/`*_lookup` em texto claro na base após o fluxo | idem (inspeção da sessão SQLite) | SC-005/SC-007 |

## App real: rodar e exercitar a API

```sh
uv run uvicorn passanorte_back.main:app --reload   # /docs no Swagger
```

Sequência no Swagger (`http://localhost:8000/docs`):

1. `POST /api/v1/tourists` — cadastre um turista com CPF com máscara.
   **201** com apenas id/nome/país na resposta (documento jamais volta).
2. `POST /api/v1/tourists/login` — autentique com e-mail+senha.
   **200** com `role: "tourist"` e par de tokens. Um e-mail errado →
   **401** genérico.
3. `GET /api/v1/tourists/me` (Authorize com o access token) — perfil
   completo, incluindo CPF/e-mail/telefone legíveis (somente o próprio).
4. `GET /api/v1/tourists/{outro_id}` com o mesmo token — **403**.
5. `PATCH /api/v1/tourists/{meu_id}` — troque país/telefone; **204**;
   `GET /me` reflete.
6. `GET /api/v1/tourists/interest-categories` — 3 categorias do
   `location.json`.
7. `PUT /api/v1/tourists/me/interests` — `["gastronomy","culture"]`;
   **200**; `GET /me/interests` confirma. Envie `["xpto"]` → **422**.
8. Renovação/encerramento pelos endpoints da fundação:
   `POST /api/v1/auth/refresh` (novo par), `POST /api/v1/auth/logout`
   (sessão morre — acesso com o access token passa a **401**).

## Checagens de qualidade da constituição

```sh
uv run ruff check . && uv run ruff format --check .
uv run pytest tests/test_migrations.py   # migration 20261031_0003 aplicável/limpa
uv run python -m passanorte_back.core.boundaries  # nenhuma fronteira violada
```

Nada de dado sensível em texto plano nos artefatos/testes — busque por
valores de exemplo de CPF/telefone apenas nas constantes de **entrada** dos
testes (payloads válidos/inválidos), nunca como estado persistido esperado.