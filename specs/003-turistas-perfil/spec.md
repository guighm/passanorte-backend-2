# Feature Specification: Turistas e Perfil do PassaNorte

**Feature Branch**: `003-turistas-perfil`

**Created**: 2026-10-31

**Status**: Draft

**Input**: User description: "Implementar Turistas e Perfil do PassaNorte (backend, módulo tourists), reutilizando a fundação de JWT e RBAC da spec 002 (docs/CONSTITUTION.md). Requisitos: RF22, RF23, RF24, RF25; RNF08, RNF10; categorias configuráveis (RNF06). Critérios de aceitação: testes de contrato do cadastro, login do turista, edição restrita ao próprio perfil, teste de integração cadastro → login → editar perfil → atualizar interesses; dado sensível nunca retornado em leitura de repositório sem descriptografia controlada."

## Clarifications

### Session 2026-10-31

- Q: A unicidade de e-mail deve ser garantida apenas entre turistas ou em
  toda a base (incluindo administradores e funcionários da spec 002)? →
  A: Apenas entre turistas — contas da fundação `auth` (admin/funcionário)
  não participam da checagem de unicidade.
- Q: Qual deve ser a política mínima de senha para o cadastro do turista? →
  A: Mínimo de 8 caracteres, sem exigência adicional de símbolos/complexidade.
- Q: Como o país de origem do turista deve ser validado e armazenado? →
  A: Texto livre (com trim/espaços normalizados), sem validação contra lista
  de países nesta fase.
- Q: Em qual formato o telefone do turista deve ser aceito e armazenado? →
  A: Formato internacional com código de país (ex.: +5511999999999),
  validado por padrão simples; entrada sem +DDI é rejeitada.
- Q: O cadastro deve aceitar CPF digitado com máscara de pontuação (ex.:
  "123.456.789-09")? → A: Sim — aceitar a entrada com máscara e normalizar
  para 11 dígitos antes de validar os dígitos verificadores e armazenar.
- Q: Qual regra concreta aceita um número de passaporte informado? →
  A: Alfanumérico (letras e dígitos, sem espaços/símbolos) com tamanho
  entre 6 e 10 caracteres.
- Q: As tentativas repetidas de login do turista devem ser limitadas nesta
  feature? → A: Fora do escopo nesta feature (YAGNI); sem throttling além do
  hash de senha e da mensagem genérica de erro.
- Q: Quantas categorias de interesse um turista pode ter selecionadas ao
  mesmo tempo? → A: Sem limite artificial — o único vínculo é pertencer à
  lista de categorias configuradas; selecionar todas as configuradas é válido.
- Q: Qual deve ser o limite de tamanho para os textos de nome, sobrenome e
  país de origem? → A: Máximo de 100 caracteres em cada — entradas maiores
  são rejeitadas com mensagem específica.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Cadastro único de turista (Priority: P1)

Um turista — brasileiro ou estrangeiro — se cadastra na aplicação Passaporte
fornecendo telefone, e-mail, país de origem, nome e sobrenome, e um documento
de identificação: CPF (brasileiros) **ou** número de passaporte (estrangeiros
ou quem não possui CPF). O sistema valida o formato e os dados do documento,
verifica a unicidade de e-mail, CPF e passaporte, e cria a conta com senha
protegida (RNF10).

**Why this priority**: Sem cadastro não existe turista; é o pré-requisito de
todas as demais histórias (RF22 é porta de entrada do domínio tourists).

**Independent Test**: Pode ser testada enviando requisições de cadastro com
combinações válidas e inválidas de campos e validando as respostas de
sucesso/erro — entrega uma conta de turista persistida sem expor dados
sensíveis.

**Acceptance Scenarios**:

1. **Given** um turista com todos os campos válidos e CPF de 11 dígitos com
   dígitos verificadores corretos, **When** solicita cadastro, **Then** a
   conta é criada, os dados sensíveis (CPF, telefone, e-mail) ficam
   armazenados de forma criptografada (RNF08) e a resposta confirma o
   cadastro sem retornar o documento em texto claro.
2. **Given** um turista estrangeiro sem CPF, **When** solicita cadastro
   informando número de passaporte válido, **Then** a conta é criada
   normalmente.
3. **Given** um cadastro com CPF inválido (dígitos verificadores incorretos),
   **When** solicita cadastro, **Then** o cadastro é rejeitado com erro de
   validação específico sobre o CPF, e nenhuma conta é criada.
4. **Given** um cadastro com e-mail em formato inválido, **When** solicita
   cadastro, **Then** o cadastro é rejeitado com erro de validação específico
   sobre o e-mail, e nenhuma conta é criada.
5. **Given** que já existe turista com determinado e-mail (ou CPF, ou
   passaporte), **When** outro cadastro é enviado com o mesmo valor,
   **Then** o cadastro é rejeitado com erro de unicidade, sem revelar dados
   da conta existente.
6. **Given** um cadastro sem CPF e sem passaporte, **When** solicita
   cadastro, **Then** a requisição é rejeitada por falta de documento de
   identificação.

---

### User Story 2 - Login do turista (Priority: P1)

O turista cadastrado autentica-se na aplicação Passaporte com suas
credenciais cadastradas (e-mail e senha) e recebe um token de acesso em
conformidade com a fundação de autenticação da spec 002 (RNF09). Credenciais
incorretas não distinguem "usuário não existe" de "senha errada".

**Why this priority**: O turista só consegue visualizar/editar perfil e
gerenciar interesses após autenticar-se (RF23); é a porta de uso de tudo o
que já existe de fundação JWT.

**Independent Test**: Pode ser testada autenticando com credenciais corretas
(recebe acesso) e incorretas (acesso negado), independentemente do cadastro
ter sido feito na mesma sessão de teste.

**Acceptance Scenarios**:

1. **Given** um turista cadastrado, **When** autentica-se com e-mail e senha
   corretos, **Then** recebe um token de acesso com identidade de turista
   (perfil/papel "turista" no esquema de permissões existente).
2. **Given** um turista cadastrado, **When** autentica-se com senha
   incorreta, **Then** o acesso é negado com mensagem única e genérica.
3. **Given** um e-mail não cadastrado, **When** tenta autenticar, **Then** o
   acesso é negado com a mesma mensagem genérica do caso anterior.
4. **Given** um turista autenticado, **When** usa o token antes da expiração,
   **Then** o acesso às rotas do seu perfil é aceito; **Given** token
   expirado, **When** o usa, **Then** o acesso é negado e o turista precisa
   autenticar-se novamente.

---

### User Story 3 - Visualizar e editar o próprio perfil (Priority: P2)

O turista autenticado visualiza seus dados cadastrais e edita-os (telefone,
e-mail, país de origem, nome, sobrenome e, quando aplicável, documento). Ele
nunca consegue editar o perfil de outro turista, e dados sensíveis só lhe são
apresentados no contexto da própria conta (RF24).

**Why this priority**: Depende do cadastro e do login (P1), mas é
independente da personalização por interesses (P3); entrega valor de
autonomia ao turista corrigir seus próprios dados.

**Independent Test**: Pode ser testada autenticando dois turistas e
verificando que cada um lê/edita apenas o próprio perfil — incluindo a
rejeição (acesso proibido) ao tentar editar o perfil alheio.

**Acceptance Scenarios**:

1. **Given** um turista autenticado, **When** solicita seus dados
   cadastrais, **Then** recebe nome, sobrenome, país de origem, documento
   (descriptografia controlada somente no contexto da própria conta),
   telefone e e-mail — nunca outro turista.
2. **Given** um turista autenticado, **When** edita o próprio perfil com
   dados válidos, **Then** as alterações persistem e a leitura seguinte
   reflete os novos valores.
3. **Given** o turista A autenticado, **When** tenta editar o perfil do
   turista B, **Then** a operação é negada (403) e nada muda no perfil de B.
4. **Given** um turista não autenticado (sem token), **When** tenta ler ou
   editar qualquer perfil, **Then** a operação é negada (401).
5. **Given** um turista autenticado, **When** tenta alterar o e-mail para um
   já usado por outra conta, **Then** a edição é rejeitada por unicidade.

---

### User Story 4 - Seleção e atualização de categorias de interesse (Priority: P2)

O turista autenticado seleciona categorias de interesse (ex.: gastronomia,
natureza, cultura) para personalização de conteúdo e notificações, e pode
atualizar essa seleção a qualquer momento (RF25). A lista de categorias
disponível é configurável — trocá-la/adaptá-la para outra cidade não exige
mudança de comportamento do sistema (RNF06).

**Why this priority**: Habilita a personalização prevista no produto
(notificações e conteúdo); depende do login, mas é independente da edição de
dados cadastrais.

**Independent Test**: Pode ser testada autenticando um turista, consultando
a lista de categorias configuradas, aplicando uma seleção e atualizando-a —
verificando que apenas categorias existentes na lista configurada são
aceitas.

**Acceptance Scenarios**:

1. **Given** um turista autenticado, **When** consulta as categorias
   disponíveis, **Then** recebe exatamente as categorias definidas na
   configuração (default: gastronomia, natureza, cultura, e as demais de
   dados configuráveis), de forma amigável à localização.
2. **Given** um turista autenticado, **When** salva uma seleção de
   interesses contendo apenas categorias válidas, **Then** a seleção
   persiste e consultas seguintes retornam a mesma lista.
3. **Given** um turista autenticado, **When** atualiza sua seleção
   removendo e/ou adicionando categorias, **Then** a seleção reflete
   exatamente a última atualização (sem duplicatas, sem valores antigos
   residuais).
4. **Given** um turista autenticado, **When** inclui uma categoria não
   existente na configuração, **Then** a operação é rejeitada com erro
   indicando categoria inválida.
5. **Given** um turista sem nenhuma seleção, **When** consulta seu perfil
   de interesses, **Then** recebe lista vazia (sem interesses) sem erro.

---

### Edge Cases

- O que acontece quando dois cadastros são submetidos quase simultaneamente
  com o mesmo e-mail? Apenas um persiste; o outro recebe erro de unicidade.
- CPF digitado com máscara/pontuação (ex.: "000.000.000-00") é aceito e
  normalizado para 11 dígitos antes de validar e armazenar (FR-013c).
- Como o sistema trata turista que tenta trocar de documento (CPF →
  passaporte ou vice-versa) na edição de perfil? A troca deve ser aceita
  desde que o novo documento seja válido e único.
- Como o sistema trata espaços em branco e capitalização de e-mail/nome
  (" Ana@exemplo.com ")? Deve normalizar antes de comparar/persistir.
- Como o sistema trata a exclusão/desativação de uma categoria que já está
  na seleção de interesses de turistas? A categoria órfã não deve quebrar a
  leitura dos interesses do turista.
- Como o sistema responde quando o token é válido mas pertence a um
  administrador/funcionário tentando acessar rotas exclusivas de turista? O
  acesso é negado conforme as regras de papel da fundação de permissões.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001** (RF22): O sistema MUST permitir o cadastro único de turista com
  telefone, e-mail, país de origem, nome e sobrenome, e **um** documento de
  identificação: CPF **ou** número de passaporte.
- **FR-002** (RF22): O sistema MUST validar o CPF informado (incluindo
  dígitos verificadores) e o número de passaporte — alfanumérico (letras e
  dígitos, sem espaços ou símbolos) com tamanho entre 6 e 10 caracteres —,
  rejeitando valores inválidos com mensagem específica.
- **FR-003** (RF22): O sistema MUST garantir unicidade de e-mail, CPF e
  número de passaporte **entre contas de turista** — a checagem não considera
  contas de administrador/funcionário da fundação de autenticação (spec 002).
- **FR-004** (RF23): O sistema MUST autenticar o turista com as credenciais
  cadastradas (e-mail e senha), emitindo token de acesso com expiração
  conforme a fundação da spec 002 (RNF09).
- **FR-005** (RNF10): O sistema MUST armazenar senhas apenas como hash
  criptográfico forte, nunca em texto plano — para turista tanto quanto já
  garantido para administrador e funcionário.
- **FR-005a**: O sistema MUST rejeitar senha de turista com menos de 8
  caracteres; não há exigência adicional de símbolos, maiúsculas ou números.
- **FR-006** (RNF08): O sistema MUST armazenar CPF, número de passaporte,
  telefone e e-mail de forma criptografada em conformidade com LGPD. Qualquer
  leitura de repositório desses campos retorna a forma criptografada;
  descriptografia é controlada e restrita aos fluxos que exigem o valor
  legível (ex.: resposta ao próprio turista, uso em notificações).
- **FR-007** (RF24): O turista autenticado MUST poder visualizar seus dados
  cadastrais, com dados sensíveis descriptografados somente no contexto da
  própria conta.
- **FR-008** (RF24): O turista autenticado MUST poder editar seus próprios
  dados cadastrais, aplicando as mesmas validações e unicidade do cadastro.
- **FR-009** (RF24): O sistema MUST impedir que um turista leia ou edite
  perfil de outro turista, negando a operação (403) e mantendo o dado
  inalterado.
- **FR-010** (RF25): O turista autenticado MUST poder salvar e atualizar sua
  seleção de categorias de interesse, com a seleção substituindo integralmente
  a anterior. Não há quantidade máxima artificial de interesses — selecionar
  todas as categorias configuradas é válido.
- **FR-011** (RNF06): O sistema MUST aceitar como categorias de interesse
  válidas somente as categorias presentes em uma lista configurável —
  adaptar/expandir as categorias não pode exigir mudança de comportamento do
  código.
- **FR-012**: O sistema MUST consultar a lista de categorias configuradas
  como operação disponível ao turista autenticado, para que o aplicativo
  ofereça as opções exibibles (i18n-ready, RNF13/RNF16).
- **FR-013**: O sistema MUST normalizar entrada de e-mail (trim e
  case-insensitive) e CPF antes de validar, comparar e persistir.
- **FR-013a**: O país de origem é texto livre obrigatório no cadastro; o
  sistema MUST aplicar trim à entrada e não exige validação contra lista de
  países nesta fase.
- **FR-013d**: Nome, sobrenome e país de origem MUST ter no máximo 100
  caracteres cada (após trim); entradas maiores são rejeitadas com mensagem
  específica.
- **FR-013b**: O telefone do turista MUST ser aceito apenas em formato
  internacional com código de país (ex.: +5511999999999, padrão
  `+` seguido de dígitos); entradas sem `+DDI` são rejeitadas com mensagem
  específica.
- **FR-013c**: O CPF MUST ser aceito com ou sem máscara de pontuação
  (ex.: "123.456.789-09") e normalizado para 11 dígitos numéricos antes da
  validação dos dígitos verificadores e do armazenamento criptografado.
- **FR-014**: Mensagens de erro de credenciais inválidas MUST ser genéricas
  (sem distinguir conta inexistente de senha incorreta).
- **FR-015**: Rotas do domínio turista MUST respeitar as regras de
  permissões/papéis da fundação da spec 002 — papéis diferentes de turista
  não têm acesso às operações exclusivas do turista comum.

### Key Entities *(include if feature involves data)*

- **Turista (Tourist)**: conta individual da aplicação Passaporte. Atributos:
  nome, sobrenome, país de origem, documento (CPF ou passaporte — exatamente
  um presente, o outro opcional), telefone, e-mail e senha (apenas hash).
  Dados sensíveis (CPF, passaporte, telefone, e-mail) armazenados
  criptografados (RNF08). Relaciona-se com a seleção de interesses.
- **Seleção de Interesses (Interest Selection)**: conjunto de categorias
  escolhidas pelo turista, atualizável a qualquer momento; cada item refere-se
  a uma categoria configurada.
- **Categoria de Interesse (Interest Category)**: item da lista configurável
  de categorias (ex.: gastronomia, natureza, cultura); provém de
  configuração/dados, não de código (RNF06); tem rótulo amigável e
  localizável.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% das tentativas de cadastro com CPF inválido, passaporte em
  formato inválido ou e-mail malformado são rejeitadas com mensagem de erro
  específica do campo problemático.
- **SC-002**: Todas as tentativas de cadastro duplicado (mesmo e-mail, CPF ou
  passaporte) são rejeitadas; em um conjunto de cadastros válidos simultâneos
  com o mesmo e-mail, exatamente um persiste.
- **SC-003**: Um turista consegue concluir o fluxo cadastro → login → editar
  perfil → atualizar interesses sem erro, em uma única sessão de
  teste/integração ponta a ponta.
- **SC-004**: 100% das tentativas de um turista acessar ou editar o perfil de
  outro turista são negadas com código de acesso proibido (403), sem
  vazamento de dados.
- **SC-005**: Em nenhuma leitura de persistência os dados sensíveis (CPF,
  passaporte, telefone, e-mail) são retornados em texto claro fora de um
  fluxo de descriptografia controlada — verificado por inspeção de testes
  automatizados que exercitam as leituras de repositório.
- **SC-006**: A adição/alteração de categorias de interesse na configuração
  reflete-se imediatamente nas categorias aceitas e listadas ao turista, sem
  alteração de código ou de comportamento do sistema.
- **SC-007**: Todas as senhas de turista persistidas estão em forma de hash
  irreversível; não há ocorrência de senha em texto plano na persistência.

## Assumptions

- A fundação de autenticação JWT e o esquema de RBAC da spec 002 (`auth`) já
  estão implementados e serão reutilizados — o papel "turista" é adicionado
  ao esquema de permissões existente, sem reescrever a fundação.
- Credencial de login do turista é o **e-mail** cadastrado (padrão de setor
  para autenticação por credenciais); o telefone é dado de contato, não
  credencial.
- Turistas brasileiros informam CPF; estrangeiros (ou quem não tem CPF)
  informam número de passaporte. Exatamente um dos dois é obrigatório no
  cadastro; a troca de documento na edição é aceita se o novo valor for
  válido e único.
- Validação de CPF segue as regras oficiais de dígitos verificadores;
  validação de passaporte é apenas de formato (alfanumérico, 6–10 caracteres,
  FR-002), sem webservice de consulta nesta fase.
- A lista de categorias de interesse default inclui, no mínimo: gastronomia,
  natureza e cultura, e vive em configuração/dados (portável por RNF06) —
  a curadoria final dos itens é decisão de conteúdo da operação, não da spec.
- Conformidade LGPD nesta fase: criptografia dos dados sensíveis em repouso,
  hash de senha e controle de acesso por papéis; fluxos adicionais de LGPD
  (anonimização, portabilidade, consentimento explícito) são escopo de
  requisitos próprios, não desta feature.
- Remoção/exclusão de conta de turista, recuperação de senha, verificação de
  e-mail/telefone por código e limitação de tentativas repetidas de login
  (throttling) estão fora do escopo desta feature (crescem por
  necessidade demonstrada, princípio de YAGNI).