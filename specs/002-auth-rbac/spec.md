# Feature Specification: Autenticação e Controle de Acesso (RBAC)

**Feature Branch**: `002-auth-rbac`

**Created**: 2026-10-31

**Status**: Draft

**Input**: User description: "Implementar Autenticação e Controle de Acesso do PassaNorte (módulos auth e employees) conforme docs/CONSTITUTION.md e docs/SYSTEM_REQUIREMENTS.md. Requisitos: RF01–RF05, RNF09, RNF10. Critério de aceitação: testes de contrato e teste de integração do ciclo de vida do funcionário."

**Requisitos de origem**: RF01 (Geração de Credenciais Administrativas), RF02 (Login do Painel Administrativo), RF03 (Controle de Nível de Acesso — RBAC), RF04 (Cadastro de Funcionário), RF05 (Edição e Remoção de Funcionário), RNF09 (Autenticação Baseada em Token), RNF10 (Criptografia de Credenciais), RNF19 (Registro de Auditoria).

## Clarifications

### Session 2026-10-31

- Q: Como a credencial de sessão do login deve ser renovada pelo painel web quando ela expira? (FR-006, RNF09) → A: Par de credenciais: login emite credencial de uso (vida curta) + credencial de renovação (vida mais longa); endpoint de renovação troca a credencial de renovação por um novo par; tornar a credencial de renovação inválida cancela a sessão.
- Q: O painel deve oferecer uma forma de encerrar sessão voluntariamente (logout) que torne a credencial de renovação inutilizável, ou essa fase dispensa o logout e o painel apenas descarta as credenciais localmente? → A: Logout explícito: endpoint que, autenticado, invalida a credencial de renovação daquela sessão; a credencial de uso expira normalmente e a renovação passa a ser recusada.
- Q: O login do painel deve ser realizado por um único endpoint para ambos os perfis (administrador e funcionário), ou por um endpoint separado para cada perfil? (FR-004, RF02) → A: Um único endpoint de login que autentica administrador e funcionário e retorna o perfil (role) na resposta da sessão.
- Q: Deve ser possível reativar um funcionário cujo acesso foi revogado (retornando-o ao estado ativo), ou a revogação é definitiva nesta fase, cabendo apenas criar um novo cadastro se ele voltar a atuar? (FR-013, FR-012) → A: Reativação permitida: o administrador pode editar um funcionário revogado e retorná-lo ao estado ativo; sessões antigas continuam inválidas e novas são emitidas normalmente.
- Q: No cadastro de um novo funcionário, quem define a senha inicial — o administrador informa uma senha, ou o sistema gera uma credencial automática que o administrador entrega ao funcionário? (RF04, FR-010) → A: O sistema gera automaticamente a senha inicial e a apresenta uma única vez ao administrador na resposta do cadastro (para entrega manual); apenas o hash é armazenado.
- Q: Quando o script de bootstrap é executado num ambiente onde o usuário de acesso configurado nas variáveis de ambiente mudou em relação à execução anterior, o que ele deve fazer? (RF01, FR-003) → A: Upsert por designação de bootstrap: existe exatamente uma conta de bootstrap, identificada pelo sistema (não pelo texto do usuário); a reexecução a atualiza em vigor, inclusive quando o usuário configurado muda — nunca cria uma segunda conta.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Bootstrap de credenciais administrativas de alto nível (Priority: P1)

Antes de qualquer acesso ao painel, o deploy da solução precisa produzir a
conta de administrador de alto nível. Um operador de ambiente (pessoa
responsável pela operação/implantação) executa um script de inicialização em
um ambiente com as variáveis de segredo configuradas. O script cria a conta
administrativa inicial (ou a atualiza com segurança quando as variáveis
mudam), utilizando as credenciais informadas exclusivamente pelas variáveis
de ambiente — nunca por valores fixados no código ou no repositório. Com
essa conta, a pessoa administradora acessa o painel completo: dashboard,
cadastro de pontos turísticos, eventos, funcionários e recompensas.

**Why this priority**: Sem a conta de alto nível ninguém consegue nem logar
nem cadastrar funcionários; é o pré-requisito de todos os demais fluxos.

**Independent Test**: Executar o script em ambiente vazio, tentar login com
as credenciais das variáveis de ambiente e obter acesso total; verificar que
nenhuma credencial em texto plano consta no código-fonte ou no repositório.

**Acceptance Scenarios**:

1. **Given** ambiente recém-configurado com segredos em variáveis de ambiente, **When** o script de bootstrap é executado, **Then** a conta administrativa de alto nível existe e consegue autenticar no painel com acesso total.
2. **Given** o script executado novamente com as mesmas variáveis, **When** ele é reexecutado (idempotência), **Then** a conta não é duplicada e permanece funcional.
3. **Given** execução anterior com um usuário de acesso configurado, **When** o script é reexecutado com o usuário (e/ou senha) mudado nas variáveis de ambiente, **Then** a mesma conta de bootstrap é atualizada em vigor (novo usuário e/ou novo hash) e nenhuma segunda conta é criada.
4. **Given** o repositório e o código implantado, **When** qualquer pessoa inspeciona o código, **Then** nenhuma senha de administrador em texto plano é encontrada (segredos só via variáveis de ambiente).

---

### User Story 2 - Login no painel administrativo (Priority: P1)

Uma pessoa (administradora ou funcionária do painel web) abre o painel,
informe usuário e senha, e recebe uma credencial de sessão (token) que
permite usar a API pelas próximas interações, com prazo de validade e forma
de renovação. Credenciais inválidas, de conta revogada/inativa ou de
requisição sem token não garantem acesso.

**Why this priority**: Login é a porta de entrada de todo uso do painel;
sem ele nem administrador nem funcionário operam.

**Independent Test**: Chamar o endpoint de login com credenciais válidas e
inválidas (status distintos), acessar um endpoint protegido com e sem
token valido (aceito vs. 401) e renovar a credencial após emissão.

**Acceptance Scenarios**:

1. **Given** administrador com conta ativa, **When** ele faz login com credenciais corretas, **Then** recebe o par de credenciais de sessão válido com o perfil de administrador indicado na resposta e consegue acessar endpoints administrativos.
2. **Given** funcionário com conta ativa, **When** ele faz login com credenciais corretas, **Then** recebe credencial de sessão válida com perfil de apenas concessão de benefícios.
3. **Given** credenciais incorretas (senha errada, usuário inexistente, conta revogada), **When** o login é tentado, **Then** a autenticação falha com erro de credencial inválida e nenhuma sessão é emitida.
4. **Given** uma sessão emitida (par de credenciais de uso e renovação), **When** a credencial de uso expira e o painel web troca a credencial de renovação, **Then** recebe um novo par e o acesso continua funcionando sem novo login informando senha.
5. **Given** qualquer endpoint protegido, **When** a requisição chega sem credencial de sessão, **Then** o sistema responde com acesso negado por falta de autenticação (401).
6. **Given** uma sessão ativa, **When** o usuário encerra a sessão pelo logout, **Then** a credencial de renovação daquela sessão é invalidada (renovações seguintes recusadas) e a credencial de uso expira normalmente.

---

### User Story 3 - Restrição de acesso por perfil (RBAC) (Priority: P1)

Funcionários autenticados só conseguem operar a concessão de benefícios.
Tentativas de acessar o dashboard, cadastrar pontos turísticos ou executar
qualquer outra função administrativa são negadas. O administrador mantém
acesso total a todas as funções.

**Why this priority**: É o requisito central do controle de acesso (RF03) e
define o valor do modelo de perfis; sem ele, login de funcionário seria um
risco, não uma feature.

**Independent Test**: Com token de funcionário, verificar que endpoints
administrativos retornam proibição (403) e que apenas o conjunto de
funcionalidades de concessão de benefícios é aceito; com token de
administrador, verificar acesso pleno.

**Acceptance Scenarios**:

1. **Given** funcionário autenticado, **When** ele tenta visualizar o dashboard, **Then** o sistema nega com proibição por perfil (403).
2. **Given** funcionário autenticado, **When** ele tenta cadastrar um ponto turístico, **Then** o sistema nega com proibição por perfil (403).
3. **Given** funcionário autenticado, **When** ele opera a concessão de benefícios, **Then** a operação é permitida.
4. **Given** administrador autenticado, **When** ele acessa qualquer funcionalidade do painel (dashboard, pontos, eventos, funcionários, recompensas, concessão de benefícios), **Then** o acesso é permitido.

---

### User Story 4 - Cadastro de funcionário com credenciais restritas (Priority: P2)

O administrador cadastra um novo funcionário no painel, informando os dados
cadastrais e o usuário de acesso. O sistema gera automaticamente a senha
inicial e a apresenta uma única vez na resposta do cadastro, para que o
administrador a entregue ao funcionário com seu usuário de acesso. O novo
funcionário já consegue logar e operar apenas a concessão de
benefícios — sem acesso ao dashboard ou ao cadastro de pontos turísticos.

**Why this priority**: Depende do login e do RBAC; é o passo que traz
usuários restritos ao sistema no dia a dia.

**Independent Test**: Fluxo administrador → criar funcionário com credenciais → login do funcionário → acesso concedido apenas à concessão de benefícios e negado aos demais endpoints.

**Acceptance Scenarios**:

1. **Given** administrador autenticado, **When** ele cadastra um funcionário, **Then** o sistema gera automaticamente a senha inicial, armazena apenas o hash seguro e a apresenta exatamente uma vez na resposta do cadastro, junto ao usuário de acesso a entregar.
2. **Given** funcionário recém-cadastrado, **When** ele faz login com as credenciais recebidas, **Then** a autenticação é aceita e seu perfil é o restrito (apenas concessão de benefícios).
3. **Given** tentativa de cadastro duplicado (mesmo usuário de acesso já em uso), **When** administrador submete o cadastro, **Then** o sistema recusa indicando conflito, sem criar conta.

---

### User Story 5 - Edição de dados e revogação de acesso de funcionário (Priority: P2)

O administrador mantém o time atualizado: corrige dados cadastrais de um
funcionário e, quando necessário, revoga o acesso — a revogação é
efetiva nas próximas tentativas de uso do painel por esse funcionário.

**Why this priority**: Completa o ciclo de governança do recurso
funcionário (RF05) e é a garantia de que o acesso perdura apenas enquanto
legítimo (segurança).

**Independent Test**: Fluxo criar → editar (dados alterados visíveis e
retornados) → revogar → tentativa de uso/login do funcionário é bloqueada
com erro de credencial/conta inativa.

**Acceptance Scenarios**:

1. **Given** funcionário existente, **When** o administrador edita seus dados, **Then** as alterações são persistidas e refletidas em leituras e na sessão/atuação subsequente.
2. **Given** funcionário existente com sessão ativa, **When** o administrador revoga o acesso, **Then** as chamadas subsequentes do funcionário à API são rejeitadas (acesso negado) e o login se torna ineficaz.
3. **Given** funcionário revogado, **When** o administrador o reativa via edição, **Then** a conta volta ao estado ativo, novos logins são aceitos e as sessões antigas (anteriores à revogação) continuam recusadas.
4. **Given** tentativa de edição, revogação ou reativação de funcionário inexistente, **When** o administrador submete a operação, **Then** o sistema responde "não encontrado" sem alterar outras contas.

---

### Edge Cases

- O que acontece quando alguém faz login com a senha correta, mas a conta
  foi revogada? → Autenticação recusada (conta inativa), sem emissão de
  sessão.
- O que acontece quando a sessão (token) expira no meio de uma operação?
  → A requisição é rejeitada como não autenticada e o painel usa o fluxo de
  renovação para voltar a operar sem digitar senha.
- O que acontece se o próprio administrador tentar revogar a si ou ao
  último administrador ativo? → O sistema recusa a operação para não se
  isolar (não pode perder o único caminho de administração). *(Assumido — ver Assumptions.)*
- O que acontece quando a credencial de renovação é inválida, expirada ou
  reutilizada depois de trocada? → O endpoint de renovação recusa e nenhuma
  nova credencial é emitida; o painel web precisa refazer o login com
  usuário e senha.
- O que acontece com tentativas repetidas de login inválido? → Cada
  tentativa falha individualmente; não há bloqueio automático nesta fase
  (YAGNI), mas todas as ações administrativas continuam registradas em
  auditoria.
- O que acontece quando o script de bootstrap roda em ambiente sem as
  variáveis de segredo? → O script falha imediatamente com mensagem clara,
  sem alterar o banco.
- O que acontece quando o bootstrap é reexecutado com o usuário de acesso
  mudado nas variáveis? → A mesma conta de bootstrap é atualizada em vigor
  (novo usuário e/ou novo hash); nenhuma segunda conta é criada.
- O que acontece ao revogar um funcionário com sessão ainda não expirada?
  → A sessão deixa de ser honrada: as requisições seguintes do funcionário
  falham (revogação efetiva, não apenas no próximo login).
- O que acontece com a conta de um funcionário reativado depois de
  revogado? → Novos logins são aceitos; as sessões existentes antes da
  revogação continuam recusadas.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001** (RF01): O sistema MUST prover script de inicialização que gera a conta de administrador de alto nível do painel, capaz de acessar dashboard, gerenciamento de pontos, eventos, funcionários e recompensas.
- **FR-002** (RF01): O sistema MUST tomar os segredos de criação/atualização de credenciais administrativas exclusivamente de variáveis de ambiente; é proibido qualquer valor de credencial fixado em código ou repositório.
- **FR-003** (RF01): O script de bootstrap MUST ser reexecutável (idempotente), no modelo de upsert por designação de bootstrap: existe exatamente uma conta de bootstrap, identificada pelo sistema (não pelo texto do usuário); a reexecução a atualiza em vigor — inclusive quando o usuário configurado muda — sem duplicar contas nem corromper o estado.
- **FR-004** (RF02): O sistema MUST autenticar administradores e funcionários do painel web por meio de um único endpoint de login, validando credenciais previamente geradas e, em caso de sucesso, emitindo o par de credenciais de sessão e retornando o perfil (role) da conta autenticada na resposta.
- **FR-005** (RNF09): O sistema MUST garantir expiração controlada da credencial de sessão, de modo que sessões expiradas deixem de dar acesso.
- **FR-006** (RNF09): O sistema MUST prover renovação controlada da credencial de sessão no modelo de par de credenciais: o login emite uma credencial de uso (vida curta) e uma credencial de renovação (vida mais longa); o endpoint de renovação troca uma credencial de renovação válida por um novo par; credencial de renovação inválida, expirada ou revogada MUST ser rejeitada sem emitir novas credenciais e sem reenvio de senha.
- **FR-007** (RNF10): O sistema MUST armazenar senhas de administradores e funcionários apenas como hash seguro (nunca texto plano), inclusive em contas criadas pelo script de bootstrap.
- **FR-008** (RF03): O sistema MUST aplicar restrição por perfil (RBAC) em todo endpoint do painel: administrador com acesso total; funcionário com acesso apenas à concessão de benefícios.
- **FR-009** (RF03): O sistema MUST bloquear o acesso de funcionários ao dashboard e ao cadastro/gerenciamento de pontos turísticos, respondendo com proibição por perfil.
- **FR-010** (RF04): O administrador MUST poder cadastrar funcionários definindo os dados cadastrais e o usuário de acesso; o sistema MUST gerar automaticamente a senha inicial, armazenar apenas o hash e apresentá-la uma única vez ao administrador na resposta do cadastro, para entrega manual ao funcionário.
- **FR-011** (RF04): O sistema MUST garantir unicidade do identificador de acesso (usuário) entre administradores e funcionários, recusando cadastros duplicados.
- **FR-012** (RF05): O administrador MUST poder editar os dados cadastrais de um funcionário existente, incluindo reativar um funcionário revogado (transição revogado → ativo).
- **FR-013** (RF05): O administrador MUST poder revogar o acesso de um funcionário; a revogação MUST ser efetiva para sessões em curso e para novas tentativas de login, e o estado "revogado" não é definitivo (a reativação via edição retorna a conta ao estado ativo).
- **FR-014** (RNF19): O sistema MUST registrar em log de auditoria estruturado as ações administrativas críticas desta feature: criação, edição, revogação de funcionário e eventos de login de administrador/funcionário.
- **FR-015**: O sistema MUST responder com "não autenticado" (401) a toda requisição sem credencial de sessão válida em endpoint protegido, e com "proibido" (403) a toda requisição autenticada sem o perfil exigido.
- **FR-016**: O sistema MUST prover encerramento voluntário de sessão (logout): um endpoint que, autenticado com a credencial de uso ainda válida, invalida a credencial de renovação daquela sessão; após o logout, a credencial de uso expira normalmente e novas tentativas de renovação com aquela credencial de renovação são recusadas.

### Key Entities *(include if feature involves data)*

- **AdminUser** (Usuário Administrador): conta de administrador de alto nível gerada pelo script de bootstrap, na designação de bootstrap única do ambiente (identificada pelo sistema, não pelo texto do usuário). Atributos: identificador de acesso (usuário), hash de senha, perfil (administrador), estado ativo/inativo.
- **Employee** (Funcionário): conta de trabalhador do painel criada pelo administrador. Atributos: nome, identificador de acesso (usuário), hash de senha, perfil (funcionário), estado ativo/revogado, dados cadastrais.
- **Session Credential** (Credencial de Sessão): par de credenciais emitido no login — uso (vida curta, validada a cada requisição com o perfil/estado da conta no momento de cada uso) e renovação (vida mais longa, trocada por um novo par no endpoint de renovação); renovação controlada.
- **Audit Log Entry** (Registro de Auditoria): registro estruturado de ação administrativa crítica, com ator, ação, alvo e resultado.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% dos endpoints protegidos do painel rejeitam requisições sem sessão válida e requisições de funcionário em rotas administrativas — verificado por bateria de testes de contrato.
- **SC-002**: Um novo administrador consegue realizar login no painel em até 1 minuto após execução do script de bootstrap.
- **SC-003**: O ciclo de vida completo de um funcionário (criar → editar → revogar → login bloqueado) executa com sucesso em um único fluxo de teste de integração ponta a ponta.
- **SC-004**: Credenciais de uso expiradas deixam de conceder acesso (100% das tentativas rejeitadas); a troca da credencial de renovação emite um novo par e retoma a operação sem refornecer senha; credenciais de renovação inválidas/revogadas são 100% rejeitadas.
- **SC-005**: Nenhuma senha em texto plano pode ser encontrada no código, no banco ou na saída de logs; auditoria registra 100% das ações listadas em FR-014.
- **SC-006**: Operações de login respondem em tempo hábil para o uso do painel (< 1 segundo em condições normais, sem depender de subsistemas pesados).

## Assumptions

- Revogação de acesso desativa a conta (estado ativo/revogado); na revogação
  o funcionário deixa de autenticar e a sua sessão corrente deixa de ser
  honrada, incluindo a credencial de renovação.
- A revogação de administradores/execução do bootstrap por outros
  administradores, exclusão definitiva (vs. desativação) de funcionários e
  alteração de senha de funcionário pelo administrador ficam fora do escopo
  desta fase (YAGNI); a edição de dados cobre a necessidade cotidiana
  (RF05).
- Proteção contra força bruta (bloqueio automático após tentativas
  repetidas) é considerada reforço futuro; nesta fase cada tentativa falha
  individualmente e há auditoria (YAGNI).
- O painel web entrega as credenciais do funcionário ao novo colaborador
  (ex.: entrega manual pelo administrador); a entrega formal por e-mail não
  faz parte do escopo do backend. A senha inicial gerada pelo sistema é
  exibida uma única vez na resposta do cadastro; não há recuperação ou
  reexibição posterior — se a credencial for perdida antes da entrega, o
  caso é tratado com redefinição/ajuste futuro (fora do escopo desta
  fase).
- A concessão de benefícios em si (o endpoint operado pelo funcionário)
  pertence a outra feature/módulo; esta feature define apenas a permissão de
  acesso a ele.
- A revogação de sessões por troca/rotação de segredo é aceitável como
  efeito colateral natural da renovação controlada de sessão.
- O último administrador ativo não pode perder o acesso por erro de
  operação (o sistema recusa operações que isolem o sistema sem
  administrador).

## Dependencies

- Requer a fundação do monolito modular (spec 001-fundacao-monolito-modular):
  estrutura de módulos (`auth`, `employees`), camadas por módulo
  (routes/services/repositories/schemas), infraestrutura compartilhada em
  `core/` e configuração via variáveis de ambiente.
- A concessão de benefícios (funcionalidade operada por funcionários)
  pertence a feature futura; esta feature entrega permissões e o ciclo de
  vida das contas.