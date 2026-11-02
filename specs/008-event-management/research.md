# Research: Tourist Spot Events Management (feature 008)

Todas as decisões aqui ancoradas no padrão consolidado do feature 007
(`tourist_spots`) e nas convenções centrais (specs 002/005/006). Nenhuma
tecnologia nova; nenhuma dependência nova. Fonte de verdade: `spec.md`
(FR-001..FR-014) + clarificações da sessão 2026-11-02 + constituição.

## R1 — Armazenamento e contrato do preço do ingresso

**Decision**: preço armazenado como **cents inteiros**
(`events.ticket_price_cents: Integer`, coluna `not null`); no contrato HTTP
o campo `ticketPrice` é `Decimal` com exatamente 2 casas
(`Field(ge=0, decimal_places=2, max_digits=…)`), serializado como número
JSON. Zero = evento gratuito.

**Rationale**: "valor monetário explícito" (spec FR-011) proíbe
representação de ponto flutuante no armazenamento — cents inteiros são
exatos por construção e evitam qualquer deriva de arredondamento no
PostgreSQL e no SQLite dos testes. `Decimal` no Pydantic valida e
quantiza a 2 casas; todo valor ≤ 2 casas codifica sem perda em centavos
inteiros e round-trips numericamente idêntico em todas as vias de leitura
(SC-005). A moeda não entra no armazenamento nem no contrato — RNF06
(portabilidade) mantém a moeda no contexto configurado do sistema.

**Alternatives considered**: `Float` (rejeitado — erro de representação
binária quebra SC-005); `String` formatada (rejeitado — string no contrato
complica frontends sem ganho); `Numeric(10,2)` do banco (rejeitado —
drivers SQLite/psycopg devolvem variações float/Decimal e a exatidão
dependeria do driver; cents inteiros são determinísticos em ambos).

## R2 — 409 para ponto permanentemente fechado

**Decision**: serviço de `events` levanta `SpotPermanentlyClosedError`;
route converte em `HTTPException(409, detail="tourist spot is permanently
closed")`. O handler unificado (`core.error_handlers`) já mapeia
409 → `errorCode: "conflict"`, e a `message` identifica a causa (spec
FR-005) — sem inventar formato próprio (constituição I).

**Rationale**: a taxonomia unificada (spec 005, `camelcase-json.md` §2) já
contém 409 → `conflict`; `HTTPException` é o uso estabelecido (007). O
código central `"conflict"` + mensagem descritiva satisfaz FR-005 sem
adicionar um código paralelo.

**Alternatives considered**: código dedicado (`"spot_permanently_closed"`,
rejeitado — romperia a taxonomia única do spec 005); `ApiResponse` manual
(rejeitado — handler unificado é a única via de falha).

## R3 — Leitura cruzada events → tourist_spots (existência e status)

**Decision**: nova função pública de serviço no módulo `tourist_spots`:
`get_active_spot_status(session, spot_id) -> str`, que levanta
`SpotMissingError` (404) e devolve o status do ponto ativo; a constante
`STATUS_PERMANENTLY_CLOSED` ("permanentlyClosed") é re-exportada no nível
de serviço e passa a fazer parte da interface pública. O módulo `events`
consume **apenas** essas duas peças públicas e decide a regra 409
consigo mesmo.

**Rationale**: constituição (regra 3/5 — comunicação entre módulos apenas
via funções de serviço públicas; nunca internals de outro módulo). `events`
não toca `TouristSpot` nem os repositories de `tourist_spots`; o status
armazenado verbatim ("permanentlyClosed") é o valor de contrato (R9 do
007), então comparar via constante pública é seguro e estável. A direção
de leitura também já é a sanccionada pelo 007 na direção oposta
(tourist_spots → events, `list_public_spot_events`).

**Alternatives considered**: eventos consultar o repositório de spots
(rejeitado — quebra a fronteira verificada por `tests/smoke
/test_boundaries.py`); duplicar a regra de status dentro de events com
string mágica (rejeitado — dois pontos de verdade para o mesmo valor).

## R4 — Cascade dos eventos na remoção do ponto

**Decision**: `tourist_spots.services.remove_spot` (delete lógico
`removed_at`) chama a nova função pública do módulo `events`
`delete_spot_events(session, spot_id)` — hard delete das linhas
pertencentes ao ponto — antes do flush, na mesma transação. Eventos de
ponto ainda não removido nunca são afetados.

**Rationale**: clarificação da sessão 2026-11-02 — cascade delete, "no
orphaned events ever remain"; a remoção do ponto é soft delete (R6/007,
terminal nesta fase), então o FK físico `ondelete="CASCADE"` nunca é
disparado por ela e a escrita cruzada precisa pasar explicitamente pela
função de serviço do domínio dono (constituição, regra 5). Com as linhas
eliminadas, todas as listagens e o embedding público ficam
automaticamente órfão-free — sem filtro condicional espalhado.

**Alternatives considered**: bloquear a remoção do ponto enquanto houver
eventos (rejeitado — troca UX/admin por atrito e não é o decidido);
manter linhas e filtrar por ponto vivo em cada leitura (rejeitado —
orphanage semanticamente vivo contradiz a clarificação e espalha a regra
por todos os leitores).

## R5 — Superfície HTTP do módulo events

**Decision**: endpoints no router canônico `MODULE_ROUTERS["events"]`
(prefixo `/api/v1/events`, tag central "Events"):

- `POST /api/v1/events` (admin) → 201
- `GET /api/v1/events` (admin) — listagem única com
  `spotId`, `startDate`, `endDate` **opcionais** (cobrir FR-007 e FR-008,
  incl. filtro combinado, clarificação 2026-11-02) → 200
- `PATCH /api/v1/events/{eventId}` (admin) → 200 (edição parcial,
  incluindo trocar o ponto associado — revalida 404/409 contra o novo
  ponto)
- `DELETE /api/v1/events/{eventId}` (admin) → 204

**Rationale**: um endpoint de listagem com filtros opcionais cobre
"por ponto", "por faixa" e o combinado com um contrato só (clarificação
Q2 da sessão 2026-11-02); nomenclatura de query em camelCase via alias
(precedente `pageSize` do 007). PATCH parcial é o padrão do 007 (FR-017
precedente). Sem paginação nesta versão (especificação 008 — assumida;
YAGNI).

**Alternatives considered**: `GET /events/{spotId}` como rota separada
(rejeitado — colide semânticamente com leitura de um evento por `eventId`);
query `spotId obrigatória` na listagem (rejeitado — o combinado exige
opcional).

## R6 — Regras de validação por camada

**Decision**: SHAPE nos schemas (`ApiModel`, 422 pela via genérica):
`occurrenceDate` = `date` ISO (YYYY-MM-DD); `description` 1..2000
(conteúdo de usuário em português — paridade com a descrição do ponto);
`ticketPrice: Decimal(≥ 0, 2 casas)`. CONFIG/cross-entry no serviço
(422 via `HTTPException`, taxa `"request_error"` — precedente do 007):
faixa `startDate > endDate` rejeitada; `spotId` do filtro combinado
desconhecido → 404 (espelha a criação). Escrita: ponto inexistente → 404
(`SpotMissingError` cruzada), ponto permanentemente fechado → 409 (R2).
Edição sem nenhum campo: no-op 200, sem audit (precedente `update_spot`).

**Rationale**: mesma divisão do 007 (schemas = forma; serviço = regra entre
campos/config) mantém os testes de contrato previsíveis: `validation_error`
para shape, `request_error`/404/409 para semântica. `Field(ge=0)` elimina
negativo na fronteira (FR-011).

**Alternatives considered**: validar faixa de datas no schema com
model_validator (rejeitado — a faixa é semântica da listagem, não da forma
do corpo; além disso um 404 de `spotId` também é semântico).

## R7 — Audit trail (RNF19)

**Decision**: uma chamada `core.audit.record_action` por escrita
bem-sucedida: `action ∈ {event.create, event.update, event.delete}`,
`target = "event:{id}"`, `actor = admin.username`, `detail` com campos
pertinentes (ex.: spotId, ticketPrice). No-op de edição não auditа.
**Rationale**: idêntico ao padrão `tourist_spot.*` do 007 (SC-004:
exatamente um registro por ação de escrita).

## R8 — Seam público para o detalhe do ponto (RF27)

**Decision**: `list_public_spot_events(session, spot_id)` continua sendo o
único ponto de consumo do `tourist_spots` — deixa de devolver `[]` e passa
a consultar a tabela real (só linhas existentes; cascade R4 garante
ausência de órfãos), devolvendo uma lista de dicts **já em forma de fio
(camelCase)**: `{"id", "spotId", "occurrenceDate", "description",
"ticketPrice"}`, ordenada por `(occurrence_date, id)`. O campo
`events: list[dict[str, object]]` do `PublicSpotDetailView` embute o
resultado verbatim (comportamento atual do 007).

**Rationale**: o seam é o contrato interno prometido no 007 ("quando o
events milestone persistir, esta função cresce a consulta — nunca erro");
dicts já em camelCase evitam que o módulo `tourist_spots` conheça schemas
de `events` (fronteira). Ordenação estável e determinística para o app.

**Alternatives considered**: `EventView` (ApiModel) exportado por events e
referenciado em tourist_spots.schemas (rejeitado — acoplamento de schemas
entre módulos viola a fronteira de tipos; dicts com forma documentada
mantêm o acoplamento só na função pública).

## R9 — Persistência e migration

**Decision**: tabela `events` exclusiva do módulo: `id` PK,
`spot_id` FK → `tourist_spots.id` (`ondelete="CASCADE"`), `occurrence_date`
`Date`, `description` String(2000), `ticket_price_cents` Integer,
timestamps `created_at`/`updated_at` (precedente 007). Índices: `spot_id`,
`occurrence_date`. Migration Alembic `20261102_0005_events.py`. Sem
`removed_at` no evento — remoção é física (hard delete), pois o evento não
participa de fluxos históricos nesta fase (dashboard/visitation consultam
visitação, não eventos; se um dia precisarem de histórico, a evolução
acrescenta soft delete com justificativa).
**Rationale**: menos colunas/estados (YAGNI); cascade físico cobre o caso
hipotético de delete físico do ponto; os casos reais da spec são cobertos
por R4.

## R10 — Estratégia de testes (test-first)

**Decision** (mapeia o critério de aceitação da spec e a Gate III):
- **Contract** `tests/contract/test_events.py`: DTOs/status por caminho —
  201 create (corpo camelCase completo), 200 patch/get-list, 204 delete,
  403 não-admin (turista/employee/anônimo), 404 (ponto inexistente na
  criação e na edição; eventId inexistente; spotId inexistente no filtro),
  409 (ponto permanentemente fechado em criação e edição), 422 (price
  negativo, >2 casas, desconhecido/snake_case keys, startDate > endDate,
  datas malformadas).
- **Integration** `tests/integration/test_events_lifecycle.py`: cria
  admin → cria ponto → cria evento → lista por ponto → lista por faixa de
  datas (com filtro combinado) → edita → remove → verifica audit
  (`audit_logs`), remoção do ponto e cascade dos eventos, embedding público
  no detalhe do ponto.
- **Unit** `tests/unit/test_events_price.py`: helper
  `price → cents → Decimal` exato (15.50 ↔ 1500), zero = gratuito,
  quantização/recusa de >2 casas.
- **Migrations** `tests/test_migrations.py` ganha a tabela no baseline
  check existente (upgrade head inclui 0005).

**Rationale**: banco isolado por teste (conftest) já provê engine SQLite,
seed de admin/employee e captura de audit — reuso direto; a suíte smoke não
muda (fronteira de módulo varre `modules/` por AST).

## R11 — Fuso e datas

**Decision**: `occurrenceDate` é data de calendário pura (especificação
008, assumido); a faixa inclusive compara datas sem transformação de fuso
(sem hora do dia não há ponto de TZ). O filtro usa as datas recebidas
como estão.
**Rationale**: sem componente de tempo, não há semântica de `city_timezone`
a aplicar (diferente dos horários HH:MM do 007); comparar no fuso do
servidor/introduzir TZ só adicionaria um estado sem significado.

## R12 — Convenções de JSON e erros

Herdadas sem novo research: camelCase (`ApiModel`), `ApiError` unificado,
estrict input (`extra="forbid"`, snake_case → 422) — cobertos pela suíte
sweep existente (`test_camelcase_contract.py`, `test_strict_input.py`,
`test_unified_error.py`), que já varre todos os módulos dinamicamente.
Tag "Events" já registrada (`core/tags.py`); nenhum route file escreve
tag (FR-013 da spec 008 herda FR-003 do 006).