# Feature Specification: Portas de Serviços Configuráveis via .env (Docker Compose)

**Feature Branch**: `010-configurable-service-ports`

**Created**: 2026-11-03

**Status**: Draft

**Input**: User description: "Ajustar o ambiente Docker Compose do PassaNorte (spec 004) para que TODOS os serviços tenham porta padrão configurável via .env, no formato ${VAR:-default} no compose.yaml, com as variáveis (POSTGRES_PORT, API_PORT, DBGATE_PORT) documentadas no .env.example (valores não-secretos cometidos) e espelhadas no .env local (git-ignored). Detalhes: (a) api — porta configurável END-TO-END: API_PORT (padrão 8000) define a porta em que o uvicorn escuta dentro do container e a exposta no host; mudar API_PORT muda a porta REAL da API, não só o redirecionamento (EXPOSE no Dockerfile é documentação e não precisa mudar); (b) db — hoje sem mapeamento de host: passar a expor "${POSTGRES_PORT:-5432}:5432" (acesso para psql/IDE na máquina host); (c) dbgate — manter "${DBGATE_PORT:-8080}:3000", apenas formalizada. As portas INTERNAS de db (5432) e dbgate (3000) permanecem fixas: a comunicação entre serviços (DATABASE_URL do api, conexão pré-configurada do DbGate) sempre usa a rede interna do Compose (host db, porta 5432), nunca a porta de host — mudar as variáveis afeta apenas o acesso a partir da máquina host. Sem segredos no repositório e sem alterar Dockerfile, entrypoint, lógica de negócio ou fronteiras de domínio (specs 001-003)."

**Nota**: Como em 004, esta é uma feature de **infraestrutura técnica**: o
mecanismo de configuração de portas (${VAR:-default} no ambiente de
containerização) é o próprio escopo, por isso os requisitos mencionam o formato
das variáveis quando o formato é o requisito em si. Os critérios de sucesso
permanecem observáveis a partir da máquina host (psql, navegador, cliente HTTP),
sem depender de detalhes internos de implementação. **Restrições duras**:
nenhuma alteração de lógica de negócio ou de fronteiras de módulos (specs
001–003), nenhum segredo real no repositório, nenhum novo estado persistido
(além das variáveis de ambiente já documentadas).

## Clarifications

### Session 2026-11-03

- Q: A porta configurável da API deve afetar apenas o redirecionamento
  (mapeamento host→container) ou a porta REAL em que o servidor escuta dentro
  do container? → A: End-to-end — a mesma variável define a porta de escuta
  interna do servidor da API e a porta exposta no host; mudar a variável muda a
  porta real do serviço, e não apenas o espelhamento (`host:container` são
  sempre iguais). A declaração de porta na imagem é documentação e permanece
  intocada.
- Q: O banco de dados deve continuar sem acesso a partir da máquina host ou
  passa a ser acessível? → A: Acessível — um mapeamento de porta host padrão
  (5432) passa a existir, para uso por ferramentas da máquina host (psql, IDEs);
  a comunicação entre serviços dentro do Compose continua pela rede interna e
  não depende dessa porta.
- Q: Portas internas dos serviços de banco de dados e ferramenta de
  administração podem também ser configuradas? → A: Não — permanecem fixas
  (5432 e 3000): toda comunicação entre serviços (URL de conexão da API à sua
  interface de consulta e conexão pré-configurada da ferramenta de
  administração) referencia essas portas internas fixas.
- Q: As portas de host devem vincular-se somente à interface local
  (`127.0.0.1`) ou a todas as interfaces da máquina? → A: Somente o novo
  mapeamento do banco de dados vincula-se a `127.0.0.1` (banco de dev não deve
  aparecer na rede local, pois é o único vetor de risco novo); API e ferramenta
  de administração mantêm a vinculação a todas as interfaces (padrão atual,
  formalização sem mudar comportamento) — a API continua testável por outros
  dispositivos da rede, quando necessário.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Toda variável de porta tem default e sobe "out of the box" (Priority: P1)

Uma desenvolvedora clona o repositório, copia o arquivo de exemplo de variáveis
de ambiente para o `.env` local e sobe o ambiente completo com o comando padrão
do Compose. Mesmo sem alterar nenhuma variável de porta, os três serviços ficam
acessíveis nas portas padrão acordadas (API na 8000, interface de administração
do banco na 8080, banco PostgreSQL na 5432 a partir da máquina host). Ela
consegue conectar um cliente SQL da sua máquina ao banco pela porta padrão —
antes desta feature isso não era possível (o banco ficava restrito à rede
interna do Compose).

**Why this priority**: É o caso dominante (ambiente recém-clonado) e inclui o
único comportamento novo visível sem ajustes: o banco fica acessível a partir
da máquina host. Sem isso, a feature não entrega valor isolado.

**Independent Test**: Copiar o exemplo de variáveis sem alterar nada, subir o
ambiente com o comando padrão e verificar que os três serviços respondem nas
portas padrão — incluindo um cliente SQL da máquina host conectando ao banco na
porta 5432.

**Acceptance Scenarios**:

1. **Given** `.env` recém-copiado do exemplo (nenhuma porta alterada), **When**
   o ambiente é iniciado com o comando único de Compose, **Then** os três
   serviços sobem com a API acessível na porta padrão 8000, a ferramenta de
   administração na 8080 e o banco PostgreSQL exposto à máquina host na 5432.
2. **Given** o ambiente no ar com portas padrão, **When** a desenvolvedora
   conecta um cliente SQL da máquina host (ex.: psql ou IDE) a
   `localhost:5432` com as credenciais do `.env`, **Then** a conexão é
   estabelecida e as tabelas das specs 001–003 estão visíveis.
3. **Given** uma máquina host em que a porta 5432 já está ocupada por um
   PostgreSQL instalado localmente, **When** a desenvolvedora define
   `POSTGRES_PORT=15432` no `.env` e reinicia o ambiente, **Then** o banco fica
   acessível à máquina host em `localhost:15432` e os serviços internos
   continuam funcionando sem alterar nenhuma outra configuração.

---

### User Story 2 - API_PORT muda a porta REAL da API, end-to-end (Priority: P2)

Uma desenvolvedora cuja porta 8000 já está ocupada por outro projeto define
`API_PORT=9000` no `.env` local e reinicia o ambiente. O servidor da API passa a
escutar REALMENTE na porta 9000 — não apenas a máquina host é remapeada: dentro
do container o servidor escuta na 9000, e a URL de acesso `localhost:9000`
responde. O endpoint de verificação de saúde continua funcionando e conectado
ao banco, sem qualquer outra alteração (nem no arquivo imagem/manifesto fixo,
nem em variáveis adicionais).

**Why this priority**: É o requisito mais sutil e o coração desta feature: hoje
alterar `API_PORT` só remapeia o host enquanto o servidor continua escutando na
8000 dentro do container — um "split-brain" de portas que confunde. Corrigir
isso é o principal ganho de previsibilidade.

**Independent Test**: Subir o ambiente com `API_PORT=9000` e verificar que a
verificação de saúde responde em `localhost:9000` e que NÃO há mais um servidor
escutando na 8000 em nenhum das pontas — a porta real do serviço mudou.

**Acceptance Scenarios**:

1. **Given** `API_PORT=9000` definido no `.env` local, **When** o ambiente é
   reiniciado, **Then** a API responde na porta 9000 da máquina host e o
   processo do servidor escuta, dentro do container, também na porta 9000 —
   nenhum endpoint fica disponível na 8000.
2. **Given** a API escutando na 9000, **When** o endpoint de verificação de
   saúde é consultado em `localhost:9000`, **Then** responde com estado
   saudável, incluindo o banco PostgreSQL conectado (sobe após o `db`, que
   depende do healthcheck — a mudança de porta não afeta a ordem de
   inicialização nem a comunicação inter-serviços).
3. **Given** o ambiente rodando na porta padrão 8000, **When** a desenvolvedora
   remove `API_PORT` do `.env` completamente (sem comentar — deletar), **Then**
   a API sobe novamente na porta padrão 8000 (o default embutido na definição
   do ambiente prevalece).

---

### User Story 3 - DbGate formalizado: porta de host configurável, conexão interna intacta (Priority: P3)

Uma desenvolvedora define `DBGATE_PORT=9080` no `.env` e reinicia. A interface
de administração do banco fica acessível em `localhost:9080`, com a conexão ao
PostgreSQL **pré-configurada** e funcionando exatamente como antes (a conexão
usa a rede interna do Compose — host interno do serviço de banco, porta interna
5432 — e nunca a porta de host). Mapear a porta de host não exige digitação de
nenhuma configuração na interface, nem altera a conexão pré-carregada.

**Why this priority**: Comportamento já correto na prática (a variável e o
mapeamento existem); o valor desta story é formalizar e documentar, garantindo
que a configuração de porta de host e a conexão interna são ortogonais. É o
slice de menor risco e menor ganho.

**Independent Test**: Definir `DBGATE_PORT=9080`, subir o ambiente, abrir
`localhost:9080` no navegador e verificar que a conexão pré-configurada exibe e
navega nas tabelas sem qualquer configuração adicional.

**Acceptance Scenarios**:

1. **Given** `DBGATE_PORT=9080` no `.env`, **When** o ambiente é reiniciado,
   **Then** a interface de administração responde em `localhost:9080` e NÃO
   responde na 8080.
2. **Given** a interface em `localhost:9080` com um `POSTGRES_PORT` diferente
   do default (ex.: 15432), **When** a conexão pré-configurada é usada para
   navegar nas tabelas, **Then** a navegação funciona — a porta de host do
   banco não influencia a conexão interna da ferramenta de administração.

---

### Edge Cases

- O que acontece quando a porta de host escolhida já está em uso por outro
  processo? → A subida do serviço falha com erro de vínculo de porta do
  Compose; nenhuma variável interna (portas fixas 5432/3000) é afetada — a
  desenvolvedora escolhe outra porta de host e reinicia. Este caso é um erro de
  infraestrutura conhecido e visível, não um comportamento a tratar
  automaticamente.
- O que acontece quando a variável de porta contém um valor inválido (ex.:
  `API_PORT=numa`)? → A subida falha com erro de interpolação/validação do
  Compose; o erro é de configuração local, detectável antes de qualquer
  serviço subir.
- O que acontece quando nenhuma variável de porta está definida (`.env` sem as
  variáveis)? → Todos os serviços sobem com os defaults embutidos (8000, 8080,
  5432) — os defaults fazem parte da definição do ambiente, não exigem o
  `.env`.
- E se as variáveis de porta forem definidas como variáveis de ambiente do
  shell em vez do `.env`? → Como qualquer variável interpolada pelo Compose, o
  valor do ambiente do shell prevalece sobre os defaults — comportamento
  padrão do Compose, não tratado especialmente nesta feature.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O ambiente de desenvolvimento local (Compose) MUST aceitar, para
  cada um dos três serviços, uma variável de porta no formato
  `${VAR:-<padrão>}` na definição do serviço, de modo que a ausência da
  variável resulte no padrão embutido: `API_PORT` (padrão 8000),
  `DBGATE_PORT` (padrão 8080) e `POSTGRES_PORT` (padrão 5432).
- **FR-002**: A porta da API MUST ser configurável de ponta a ponta: a mesma
  variável (`API_PORT`) define a porta em que o servidor da API escuta dentro
  do container **e** a porta exposta ao host — mapeamento sempre na forma
  `${API_PORT:-8000}:${API_PORT:-8000}`. Alterar a variável muda a porta real
  do serviço, não apenas o redirecionamento.
- **FR-003**: O serviço de banco de dados MUST expor sua porta à máquina local
  via mapeamento `127.0.0.1:${POSTGRES_PORT:-5432}:5432`, tornando o banco
  acessível a ferramentas da máquina host (psql, IDEs, clientes SQL) sem
  torná-lo visível para outros dispositivos da rede local (segurança por
  padrão).
- **FR-003a**: As vinculações das portas de host da API e da ferramenta de
  administração MUST continuar sem prefixo de interface (todas as interfaces,
  padrão atual), pois a feature apenas formaliza o mapeamento existente.
- **FR-004**: As portas internas (dentro da rede do Compose) dos serviços `db`
  (5432) e `dbgate` (3000) MUST permanecer fixas e não configuráveis: toda
  comunicação entre serviços — a URL de conexão da API ao banco e a conexão
  pré-configurada da ferramenta de administração — referencia a rede interna
  (host de serviço, porta interna), nunca a porta de host.
- **FR-005**: As três variáveis de porta (`POSTGRES_PORT`, `API_PORT`,
  `DBGATE_PORT`) MUST estar documentadas no arquivo de exemplo de variáveis de
  ambiente versionado (`.env.example`), com comentários explicando o que cada
  uma controla e os valores padrão — valores de porta não são segredos e podem
  ficar cometidos.
- **FR-006**: O `.env` local (git-ignored) MUST continuar sendo o local de
  ajuste das portas; o mecanismo não pode exigir edição de outros arquivos
  (imagem da API, entrypoint, scripts) para trocar uma porta.
- **FR-007**: Nenhum segredo real MUST ser introduzido no repositório por
  causa desta feature (os valores cometidos em `.env.example` são apenas
  portas e defaults não-secretos).
- **FR-008**: Nenhum arquivo de imagem da API, entrypoint, lógica de negócio ou
  fronteira de módulo (specs 001–003) MUST ser alterado por esta feature; a
  mudança é confinada à configuração do Compose e à documentação das variáveis.
- **FR-009**: A declaração de porta da imagem da API (EXPOSE) deve continuar
  intocada — ela é documentação e não participa da configuração de porta
  efetiva (nenhuma alteração necessária nela).

### Key Entities *(include if feature involves data)*

Não há novas entidades de dados. As "entidades" desta feature são as variáveis
de configuração:

- **POSTGRES_PORT**: porta de HOST para acesso à máquina ao PostgreSQL
  (exposição nova; a interna 5432 permanece fixa). Padrão 5432.
- **API_PORT**: porta REAL da API — escuta interna do servidor e exposição ao
  host, sempre iguais. Padrão 8000.
- **DBGATE_PORT**: porta de HOST da ferramenta de administração de banco
  (interna 3000 fixa). Padrão 8080. Já existia; é formalizada.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Com o `.env` recém-copiado do exemplo e nenhuma variável de porta
  alterada, o comando único de Compose sobe os três serviços e a API responde
  na 8000, a interface de administração na 8080 e o banco é acessível da
  máquina host na 5432 — 100% das três portas acordadas.
- **SC-002**: Trocar `API_PORT` para um valor não-default (ex.: 9000) e
  reiniciar faz a API responder exclusivamente na nova porta em até 1 restart
  completo do ambiente (sem rebuild de imagem e sem edição de nenhum arquivo
  além do `.env`) — a porta real mudou, não só o redirecionamento.
- **SC-003**: Trocar `DBGATE_PORT` e/ou `POSTGRES_PORT` e reiniciar mapeia as
  novas portas de host em até 1 restart, sem tocar nas internas — a conexão
  pré-configurada da ferramenta de administração e a comunicação inter-serviços
  seguem funcionando inalteradas em 100% dos cenários de troca de portas.
- **SC-004**: As três variáveis estão documentadas no arquivo de exemplo
  versionado com seus defaults — nenhum segredo novo é introduzido no
  repositório; o `.gitignore` continua impedindo a publicação do `.env` local.
- **SC-005**: Com o ambiente no ar, o banco PostgreSQL responde via
  `localhost:POSTGRES_PORT` e NÃO responde via o endereço IP da máquina na Rede
  local (mesma porta) — 100% dos testes: conexão local bem-sucedida, conexão
  via IP de rede recusada (API e ferramenta de administração permanecem
  acessíveis via IP de rede, conforme comportamento mantido).

## Assumptions

- Portas "não-secretas": portas de host e defaults podem e devem ficar
  cometidos no arquivo de exemplo versionado — seguindo o padrão já adotado
  para outras configurações não-secretas do projeto.
- O comportamento de variável de shell prevalecendo sobre `.env`/default é o
  padrão do Compose e não recebe tratamento especial nesta feature.
- Conflito de porta de host em uso é um erro visível e conhecido do Compose;
  não há resolução automática (ex.: buscar próxima porta livre) — isso seria
  escopo maior (YAGNI).
- A declaração de porta na imagem da API não é atualizada (é documentação; o
  padrão 8000 continua refletido nela), conforme decidido na especificação.
- Nenhum teste de lógica de negócio existente é afetado; o ambiente de testes
  usa a mesma suíte existente (specs 001–003) e não requer variáveis de porta.