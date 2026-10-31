# Contrato HTTP: Verificação de Saúde

Feature: `/specs/001-fundacao-monolito-modular/spec.md` | Date: 2026-10-30

Referência de verdade: a documentação OpenAPI gerada pela própria aplicação
(`/docs`, na raiz — fora de `/api/v1`). Este arquivo é o resumo do contrato da
fase; a OpenAPI em runtime prevalece.

## GET /health

- **Autenticação**: nenhuma (público — sondas de infraestrutura).
- **Prefixo**: raiz (fora de `/api/v1` — clarificação Q4).

### Resposta saudável

`HTTP 200` quando aplicação e banco estão operáveis:

```json
{
  "status": "ok",
  "database": "ok"
}
```

### Resposta degradada (clarificação Q1)

`HTTP 503` quando o banco indicado por `DATABASE_URL` está inacessível
(ping falha dentro do timeout):

```json
{
  "status": "degraded",
  "database": "unavailable"
}
```

### Critérios de contrato (testes)

- 200 + corpo acima com `sqlite:///:memory:` conectado.
- 503 + corpo acima com URL apontando para banco inacessível.
- Tempo de resposta < 1 s em ambos os casos (SC-002).
- Sem requisitos de autenticação ou de corpo de requisição.