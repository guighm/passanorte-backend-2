# Research: Prize Redemption (Employee Scan) — feature 012

Fecha os pontos de decisão do plan. Nenhum NEEDS CLARIFICATION restante da
spec (Clarifications registra as decisões de produto: confiar no código;
sem audit de falhas).

## R1 — Onde expor o "novo estoque" na resposta de sucesso (FR-004)

**Decision**: dentro do objeto `prize` da resposta —
`RedemptionPrizeView` ganha `stock_quantity: int` (JSON `stockQuantity`),
espelhando o `RoutePrizeView` existente (`GET /routes/{id}`.prize já
exponde `stockQuantity`).

**Rationale**: o estoque é atributo do brinde, não da concessão; manter o
mesmo shape do `RoutePrizeView` torna o payload autoconsistente (o
funcionário vê tudo do brinde num só objeto) e evita campo top-level
solto. O route handler já faz `find_prize_by_id` pós-concessão — a leitura
pós-dedução está disponível sem nova query de design.

**Alternatives considered**:
- Campo top-level `newStockQuantity` na `RedemptionView` — rejeitado:
  duplica contexto do brinde e foge do shape do `RoutePrizeView`.
- Retornar reservas (`reservedQuantity`) também — rejeitado (YAGNI): o
  requisito pede o novo estoque; reservas são internalidade de domínio
  exposta apenas no ajuste de estoque (espec 009 edge case).

## R2 — Capturar estoque antes/depois para o audit (FR-007, RNF19)

**Decision**: o serviço `concede_prize` lê o estoque atual do brinde
(`find_prize_by_id`) antes do guard atômico `try_consume_stock` e grava no
`detail` do `record_action`: `stockQuantityBefore` e `stockQuantityAfter`
(= before − 1, garantido pelo `rowcount == 1`; rejeitado recalcular depois
por reler — evita janela com ajuste concorrente de estoque e mantém a
semântica "esta concessão consumiu exatamente 1").

**Rationale**: `core.audit.record_action` é log-only com campo `detail`
JSON — nenhum schema/core muda. A leitura "before" na mesma transação (o
SQLite/PostgreSQL serializam a linha do brinde durante o guard atômico)
torna o par before/after consistente com a baixa registrada. O detail ganha
também `touristId` e `prizeId` (spec exige actor, turista, brinde, pickup,
antes/depois); `routeId` e `pickupSpotId` já existem.

**Alternatives considered**:
- Registrar "after" relendo o brinde pós-dedução — rejeitado: segundo
  resgate concorrente de outro brinde na mesma tabela não afeta, mas leitura
  pós-flush adiciona I/O e pode reflitir ajustes de estoque simultâneos no
  mesmo registro; e o par (before, before−1) é o significado exato de RNF19
  para esta concessão.
- Tabela de auditoria persistida — rejeitado: constituição decidiu audit
  log-only nesta fase (clarification Q3 da infra de audit); a interface
  `record_action` permanece.

## R3 — Distinção dos dois conflitos (FR-005) sem migrar errorCode (FR-011/unified)

**Decision**: manter o HTTP 409 + `errorCode: "conflict"` para ambos
(código já usado; estoque insuficiente) e diferenciar a causa pela
`message` do `ApiError`: `"redemption code has already been used"` e
`"no stock available for this route's prize"`. Hoje o route handler mescla
as duas exceções numa mensagem só (`"redemption code already used or
insufficient stock"`) — os `except` são separados em duas cláusulas com
mensagens canônicas distintas.

**Rationale**: a taxonomia de `errorCode` vem do registro unificado
(`core.error_handlers`) e não aceita códigos ad hoc por módulo; FR-005 pede
"um erro claro por causa" com significado — a `message` é o veículo
previsto pelo payload único (`errorCode`, `message`, `details`), e o
frontend distingue pelo texto localizável (i18n-ready, RNF13).

**Alternatives considered**:
- Novo `errorCode` (ex.: `prize_stock_unavailable`) — rejeitado: exigiria
  extensão do registro central de erros (feature 005) por causa de uma
  nuance semântica; a fronteira do contrato unificado é preservada e o
  custo/benefício é desfavorável (YAGNI).
- Estoque insuficiente como 422 — rejeitado: o estado é conflito de
  recurso (código válido, sem unidade), não falha de shape.

## R4 — Estratégia de testes de idempotência/concorrência

**Decision**:
- **Repetição (contrato)**: após 201, loop de N (≥ 3) resubmissões → 409
  em todas, estoque estável, exatamente 1 `record_action` "prize.concede"
  (via fixture `audit_logs`/caplog, padrão existente em
  `test_create_route_audit_record_identifies_actor`).
- **Concorrência (integração)**: estende o padrão já usado em
  `test_gamification_lifecycle.py` ("stock race — two tourists"): duas
  sessões/threads submetendo o mesmo código; exatamente um 201 e um 409,
  uma unidade consumida, um único audit record. Repositório já provê o
  guard (`try_consume_stock` atualiza condicional com `rowcount`) — o teste
  prova que nenhuma janela no serviço permite dupla baixa.
- **Audit antes/depois (contrato)**: estoque inicial conhecido → resgate →
  assert detail tem `stockQuantityBefore == N` e `stockQuantityAfter == N-1`
  mais `touristId`/`prizeId`/`pickupSpotId`/ator.

**Rationale**: test-first na suíte de contrato (critério de aceitação da
spec: SC-001..SC-007); reuso dos fixtures/padrões existentes evita
infraestrutura de teste nova.

**Alternatives considered**:
- Só teste unitário de serviço concorrente — rejeitado: o critério de
  aceitação é de contrato HTTP; unit test fica como camada fina se o
  lifecycle não cobrir as janelas.
- Teste de concorrência com processos separados — rejeitado: custo de
  orquestração desnecessário para SQLite/Single-process desta fase.

## R5 — Sem migration e sem mudança de repositories

**Decision**: nenhuma migração Alembic e nenhuma alteração em
`repositories/gamification.py` — `try_consume_stock` (guard atômico que
liberta reserva) e `claim_redemption_code` (claim condicional single-use)
já implementam FR-003/FR-006 na camada correta.

**Rationale**: o delta da feature 012 é contrato+audit+testes; tocar o
repositório reabriria a superfície já validada pela spec 009 e pela suíte
atual (zero risco de regressão de estoque).

**Alternatives considered**: nenhuma viável — mudar repositório sem
necessidade viola YAGNI e abre risco na lógica de guard testada.