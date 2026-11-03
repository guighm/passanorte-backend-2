# Research: Tourist Routes and Gamification (feature 009)

Decisions resolved before design. The spec has 5 integrated clarifications
(Q1–Q5); this research resolves the remaining technical unknowns so that
Phase 1 (data-model, contracts, quickstart) needs no further clarification.

## R1 — Domínio das tabelas de visita/progresso (`spot_visits`)

- **Decision**: a tabela de visitas registradas (`spot_visits`) pertence ao
  domínio `gamification`, não ao `visitation`. Progresso é **derivado em
  leitura** (join `route_spots` × `spot_visits`), sem tabelas desnormalizadas
  de progresso por inscrição.
- **Rationale**: a visita registrada por `register_spot_visit` é o insumo do
  progresso (spec: "the input that drives progress"); nesta feature não
  existe ainda entrada HTTP de visitação — a visitação (spec 010) fará
  check-in georreferenciado e chamará a função pública. Derivar o progresso
  por query mantém o modelo simples (YAGNI) e imune a drift de
  sincronização.
- **Alternatives considered**: tabela `route_progress` por inscrição
  (desnormalizada) — rejeitada: duplica estado, precisa de dupla escrita
  atômica em toda visita e completa uma chamada que já é multirrota; tabela
  `spot_visits` em `visitation` — rejeitada: gamification passaria a ler
  dados privados de outro domínio, quebrando a regra 4 da constituição.

## R2 — Idempotência de conclusão e emissão única (badge + código)

- **Decision**: conclusão idempotente garantida por unicidade de bancos:
  ` UNIQUE (route_id, tourist_id)` em `route_enrollments` (inscrição),
  `completion_badges` e `redemption_codes`; a transição de status da
  inscrição (`in_progress → completed`) é executada por UPDATE condicional
  (`WHERE status = 'in_progress'`) — quem atualiza 1 linha conclui e emite
  recompensas na mesma transação; quem atualiza 0 linhas é idempotente e não
  emite nada.
- **Rationale**: nenhuma execução concorrente ou repetida consegue emitir
  duas insígnias ou dois códigos: a união da guarda de status com o índice
  único fecha a janela de corrida sem locks manuais (single-process
  monolith, one DB — constitution preamble).
- **Alternatives considered**: controle de versão otimista na inscrição —
  rejeitado: duplica a guarda com menos garantias; fila/trava de aplicação —
  rejeitada: constituição veta filas e locks de aplicação nesta fase.

## R3 — Validação cruzada de turistas e pontos (leitura entre domínios)

- **Decision**: `gamification` valida turistas e pontos exclusivamente pelas
  seams públicas já existentes: `tourists.services.get_tourist_account`
  (turista inexistente/inativo → 404) e `tourist_spots.services`.
  `get_active_spot`/função pública equivalente (ponto inexistente/removido →
  404). Pontos removidos (`removed_at`) não são aceitos em nova rota nem na
  concessão (pickup spot informado precisa estar ativo).
- **Rationale**: precedente consolidado da spec 008 (R3/R4 de 008): FK de
  referência só escrita após validação pela seam do módulo dono.
- **Alternatives considered**: FK com constraint referencial e leitura direta
  de models — rejeitada: viola a fronteira (AST boundary gate quebra o build).

## R4 — Estoque: guardas atômicas em SQL

- **Decision**: brinde carrega `stock_quantity` (ajustável, ≥ 0) e
  `reserved_quantity` (unidades comprometidas por conclusões). Duas guardas
  atômicas, no próprio SQL:
  - **Reserva na conclusão**: `UPDATE prizes SET reserved_quantity =
    reserved_quantity + 1 WHERE id = :id AND stock_quantity -
    reserved_quantity >= 1` — rowcount 0 = sem estoque: a conclusão da rota
    segue (insígnia + código emitidos), mas sem reserva (código válido,
    concessão bloqueada até repor estoque).
  - **Concessão**: `UPDATE prizes SET stock_quantity = stock_quantity - 1,
    reserved_quantity = max(reserved_quantity - 1, 0) WHERE id = :id AND
    stock_quantity >= 1` — rowcount 0 → 409 `conflict`, código permanece
    válido, nada muda.
  - **Ajuste pelo admin**: rejeita `stock_quantity < reserved_quantity`
  (422) — não é possível descer abaixo do já comprometido (edge case da
  spec).
- **Rationale**: `UPDATE` condicional é atômico no banco (row-level guard),
  funciona em PostgreSQL e SQLite, e dá o "estoque nunca fica negativo" sem
  lock de aplicação. Concorrência de processo é simulada nos testes por duas
  conclusões sequenciais competindo pela unidade final + tentativas de
  concessão repetidas (mesma semântica da guarda; `SELECT FOR UPDATE` não é
  portável para SQLite em memória).
- **Alternatives considered**: contadores derivados por query (sem coluna
  `reserved_quantity`) — rejeitado: a reserva precisa persistir entre
  conclusão e concessão; decremento em aplicação (`stock -= 1` depois de
  `if stock > 0`) — rejeitado: janela de corrida sob qualquer pool real.

## R5 — Geração do código de resgate

- **Decision**: `secrets.token_urlsafe(16)` (stdlib) — 128 bits de
  entropia, alfanumérico URL-safe, sem caracteres ambíguos relevantes para
  leitura/transcrição; coluna `code` com índice UNIQUE; retry em colisão
  (probabilidade desprezível, mas tratada). Não expira (Q4).
- **Rationale**: `secrets` é o CSPRNG padrão do Python — imprevisível,
  não derivável de contador/identificador (SC-004); zero dependências novas.
- **Alternatives considered**: UUID4 — rejeitado como payload de resgate:
  traços e formato interno, menos ergonômico para transcrever no balcão;
  código sequencial com sal — rejeitado: previsível (viola SC-004);
  `uuid4().hex` — rejeitado: 32 chars desnecessários.

## R6 — Gate de concessão: `require_staff` no módulo auth

- **Decision**: nova dependência `require_staff` em
  `modules/auth/services/security.py` (ao lado de `require_admin` /
  `require_tourist`): aceita `account_type` em (`admin`, `employee`) com
  conta ativa; 403 caso contrário. Concessão e ajuste de estoque: ajuste de
  estoque e rotas = `require_admin`; concessão de brinde = `require_staff`
  (esclarecimento Q3).
- **Rationale**: o módulo auth é o dono do RBAC (princípio I; precedente
  spec 002): a regra de "quem concede" é política de acesso, não de
  gamification — crescer a família de gates no dono evita duplicar lógica de
  identidade em rotas de outro módulo.
- **Alternatives considered**: gate local no módulo gamification checando
  `account_type` — rejeitado: duplica a política de acesso fora do dono
  (auth), rompe com o padrão 008.

## R7 — Superfície HTTP do módulo (contrato)

- **Decision** (única router canônico `MODULE_ROUTERS["gamification"]`,
  prefixo `/api/v1/gamification`, tag "Gamification" aplicada em
  `core/routers.py`):
  - Admin (RF18/RF19/RF20): `POST /routes` (cria rota + brinde embutido com
    estoque inicial), `PATCH /routes/{id}`, `DELETE /routes/{id}`
    (arquivamento), `GET /routes` (listagem ativa; filtro
    `?includeArchived=true`), `GET /routes/{id}` (admin lê qualquer estado),
    `PATCH /prizes/{id}` (ajuste de estoque).
  - Turista (RF29/RF30/RF35/RF36): `GET /routes` (rotas ativas — mesma
    listagem, sem filtro archivado), `GET /routes/{id}` (detalhe público da
    rota ativa), `POST /routes/{id}/enrollments` (inscrição; 409 duplicada),
    `GET /enrollments` (minhas inscrições com progresso resumido),
    `GET /enrollments/{id}` (progresso completo: spots visitados/pendentes,
    taxa, insígnia e código quando concluída).
  - Staff (RF20/RF36, Q3): `POST /redemptions` `{code, spotId}` — concession
    (201; código usado exatamente uma vez; 409 estoque insuficiente/código
    já usado; 404 código/spot inexistente; 422 spot inválido). Turista lê o
    próprio código no progresso da inscrição (jamais em listagem de outros).
- **Rationale**: um recurso por conceito, verbo HTTP correto, caminhos
  estáveis para o Painel (React) e o app Passaporte (Kotlin — mesmo
  contrato, princípio I). Nenhuma listagem paginada nesta versão (YAGNI,
  precedente 008).
- **Alternatives considered**: aninhar inscrição em `/my/routes/...` —
  rejeitado: duplica prefixos sem valor; expor códigos em listagem de
  rotas concluídas separada — rejeitado: o código já é payload do
  progresso quando concluída (spec Story 3, cenário 5).

## R8 — Progresso e taxa de conclusão no contrato

- **Decision**: `completionRate` é um inteiro 0–100 no wire
  (percentagem inteira, piso); o payload de progresso traz a lista integral
  de spots da rota (ordem de display da rota) com estado
  `visited`/`pending`, o total, os visitados e a taxa. `register_spot_visit`
  (seam pública) devolve a mesma taxa por rota afetada + `completed`
  (Q5), como estrutura de serviço interna — nunca DTO HTTP.
- **Rationale**: número integral elimina qualquer problema de precisão
  decimal no wire (precedente do preço exato da 008) e dá à barra de
  progresso o valor direto (RF30).
- **Alternatives considered**: `Decimal` 2 casas / fração (0..1) —
  rejeitados: precisão sem uso e convenção oposta à leitura
  "percentual" da RNF/barra.

## R9 — Migração e persistência

- **Decision**: uma migration (`20261102_0006_gamification.py`) cria as 7
  tabelas com FKs, índices e unicidades (data-model.md). Sem soft-delete em
  gamification além do `removed_at` da rota (arquivamento — FR-012). Insígnias,
  códigos e inscrições são físicas e permanentes (histórico é o propósito).
- **Rationale**: precedente das migrations 0003–0005; Alembic já é o caminho
  de evolução (constituição — Stack).
- **Alternatives considered**: migrations separadas por história —
  rejeitado: o domínio nasce coeso; dividir gera estados intermediários
  sem valor.

## R10 — Estratégia de testes (test-first)

- **Decision**:
  - `tests/contract/test_gamification.py` — contrato de todos os endpoints:
    201/200/204 nos fluxos felizes; 403 (`authorization_failed`) para
    não-admin nas escritas administrativas e para não-turista na inscrição;
    401 sem token; 404 (`resource_not_found`) para rota/ponto/código
    inexistente; 409 (`conflict`) para inscrição duplicada, código já usado,
    estoque insuficiente; 422 (`validation_error`) para shape (camelCase
    estrito — sweeps da 005/006 já cobrem o módulo novo automaticamente).
  - `tests/integration/test_gamification_lifecycle.py` — jornada de
    aceitação SC-007: admin cria spots+rota+brinde → turista se inscreve →
    `register_spot_visit` para todos os spots → insígnia emitida → código
    único visível → segunda tentativa de uso do código falha (409); +
    propagação RF34 (uma visita atualiza duas rotas); + estoque: dois
    turistas competindo pela unidade final (segundo sem reserva) e
    concessão bloqueada com estoque 0 (código permanece válido), concessão
    bem-sucedida consumindo exatamente uma unidade e marcando o código como
    usado; + arquivamento preservando histórico.
  - `tests/unit/test_gamification_codes.py` — código: 128 bits de
    entropia, unicidade sob volume, ausência de derivação de
    identificadores.
- **Rationale**: espelha a estratégia 007/008 (contrato + integração + unit
  focal), cobre todos os SCs da spec e torna os critérios de aceitação
  executáveis.
- **Alternatives considered**: threads reais sobre SQLite em memória —
  rejeitado: não portável e instável em teste; a guarda atômica (R4) dá a
  mesma garantia com teste estável.

## R11 — Convenções de JSON, erros e auditoria

- **Decision**: DTOs herdam `core.schemas.ApiModel` (camelCase estrito,
  `extra="forbid"`); falhas só via exceções de domínio → `HTTPException`
  → `ApiError` (401 `authentication_failed`, 403
  `authorization_failed`, 404 `resource_not_found`, 409 `conflict`, 422
  `validation_error`); audit `record_action` com ações
  `route.create`/`route.update`/`route.delete`/`prize.stock_update`/
  `prize.concede`. Conteúdo de usuário (nomes/descrições) em português;
  identificadores e mensagens de código em inglês (Princípio VII).
- **Rationale**: igual aos módulos 007/008; nenhum payload de erro novo
  (gate da constituição).

## R12 — Semântica de `register_spot_visit` frente a estado

- **Decision**: a função grava `spot_visits` (UNIQUE
  `tourist_id, tourist_spot_id` — visita re-registrada é no-op idempotente,
  devolve o estado atual sem duplicar), valida turista ativo e ponto ativo
  (404-equivalentes na seam: exceções de domínio), e retorna
  `list[VisitRouteOutcome]` com `route_id`, `completion_rate`, `completed`
  (e `completion` inclui os resultados da emissão única de insígnia/código
  na mesma transação). A assinatura e a semântica ficam congeladas neste
  feature como contrato de domínio público para a spec 010.
- **Rationale**: uma transação por chamada (regra 5 da constituição: escrita
  cruzada por serviço do dono); sem retorno significa que a visitation
  precisaria de segunda leitura para saber se a rota completou (Q5).
- **Alternatives considered**: retorno booleano — rejeitado: perde a
  verificação da propagação RF34; DTO HTTP na seam — rejeitado: fronteira
  de domínio é de serviço, não de HTTP.