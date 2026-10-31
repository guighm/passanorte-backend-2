<!--
SYNC IMPACT REPORT
- Version change: (none — scaffold) → 1.0.0 (initial ratification)
- Ratified: 2026-10-30
- Modified principles: none (new document, 7 principles created)
- Added sections:
  - Fundamental architectural decision: Modular Monolith First (Preamble)
  - Core Principles I–VII (API-Contract-First; Security & LGPD by Default;
    Test-First [NON-NEGOTIABLE]; Geospatial Data Relevance & Correctness;
    Simplicity & Minimized Scope (YAGNI); Portability by Configuration;
    Maintainability & Consistency)
  - Additional Constraints (stack, response time, i18n)
  - Development Workflow (specify → clarify/plan → tasks → implement → analyse)
  - Quality Gates
  - Governance
- Removed sections: none
- Follow-up TODOs: none — all placeholders resolved
- Traceability note: principles reference RFs/RNFs defined in
  docs/SYSTEM_REQUIREMENTS.md (RNF01–RNF20, RF01, RF03, RF38-39)
-->

# PassaNorte Constitution

## Decisão arquitetural fundamental: Monolito Modular Primeiro

O documento de requisitos (`docs/SYSTEM_REQUIREMENTS.md`) prevê sistemas
distribuído e microsserviços (RNF01, RNF02, RNF07). **Decisão deliberada para
esta fase:** o PassaNorte será implementado como um **monolito modular**,
com limites de domínio rígidos que espelham exatamente o corte de
microsserviços previsto, permitindo extração futura de serviços sem
reescrita. Regras que decorrem disso:

1. Um único processo FastAPI, um único banco de dados, um único deploy.
2. O código é organizado em **módulos de domínio** (bounded contexts):
   `auth`, `funcionarios`, `turistas`, `pontos_turisticos`, `eventos`,
   `gamificacao`, `visitacao`, `dashboard`, `notificacoes`, `chatbot`.
3. Módulos se comunicam **apenas** via interfaces explícitas de serviço
   (funções de serviço públicas) — nunca importando internals de outro
   módulo (models, schemas, repositories privados).
4. Cada módulo mantém sua própria área de modelos/schemas/serviços/rotas;
   não há compartilhamento de tabelas entre domínios.
5. Toda escrita entre domínios (ex.: visitacao atualizando progresso de
   gamificacao) passa por uma função de serviço do domínio dono dos dados,
   nunca por UPDATE direto em suas tabelas.
6. Nenhuma fila de mensagens, service mesh ou comunicação em rede entre
   módulos nesta fase. Quando um módulo evoluir para microsserviço, sua
   interface de serviço vira o contrato de API interna (client HTTP ou
   mensageria), sem mudança de semântica.

## Core Principles

### I. API-Contract-First

A API RESTful FastAPI é o único contrato: painel web (React) e aplicativo
Passaporte (Kotlin) consomem os **mesmos endpoints** (RNF03, RNF05). Todo
endpoint é definido por schema Pydantic (request/response) antes da
implementação; OpenAPI/Swagger gerado automaticamente é a documentação de
referência (docs/contracts). Frontends não integram lógica que a API não
expõe. Nenhum endpoint privado sem RBAC: administrador tem acesso total;
funcionário acessa apenas concessão de benefícios (RF03).

### II. Segurança e LGPD por Padrão

Autenticação exclusivamente por JWT com expiração e renovação controladas
(RNF09). Senhas de administrador, funcionário e turista são sempre
armazenadas com hash bcrypt/argon2 — nunca em texto plano (RNF10). Dados
sensíveis (CPF, passaporte, telefone, e-mail) armazenados criptografados em
conformidade com LGPD (RNF08). Ações administrativas críticas
(cadastro/edição/remoção de pontos, eventos, funcionários) geram log de
auditoria estruturado (RNF19). Credenciais de alto nível são geradas apenas
por script, nunca hardcoded no código ou no repositório (RF01; segredos via
variáveis de ambiente).

### III. Test-First (NON-NEGOTIABLE)

Test-first obrigatório: teste escrito → falha → implementação → verde.
Toda feature de API possui no mínimo: (a) teste de contrato (schema
request/response e códigos de status HTTP), (b) teste de integração
exercitando o fluxo ponta a ponta do domínio (ex.: inscrever → visitar
pontos → concluir rota → gerar código → resgatar brinde). Testes rodam contra
banco isolado (SQLite em memória ou banco efêmero por teste). Cobertura é
critério de aceitação da tarefa, não aspiração.

### IV. Relevância e Corretude dos Dados Geoespaciais

A validação de presença usa fórmula de Haversine com raio de tolerância
configurável por ponto turístico (RNF14). Coordenadas são sempre
(decimal, WGS-84) e validadas por schema. O ranking/dashboard nunca deve
inventar dados: toda métrica deriva de eventos de visitação registrados,
jamais estimada "em código".

### V. Simplicidade e Escopo Minimizado (YAGNI)

Começar pelo mais simples que atende o requisito em mãos. A complexidade é
justificada caso a caso (no constitution check). Sem otimizações prematuras,
sem caches multicamada, sem filas. Priorizar ferramentas gratuitas e open
source (RNF15). Menos tabelas, menos endpoints, menos dependências —
crescer por necessidade real demonstrada em teste.

### VI. Portabilidade por Configuração

A adaptação do sistema para outra cidade/estado/país exige apenas troca de
dados configuráveis (pontos, categorias, horários, idiomas) — zero
reestruturação de código ou arquitetura (RNF06). Nomes de cidade,
coordenadas raiz, categorias padrão e idiomas habilitados vivem em
configuração/dados, não em lógica de código.

### VII. Manutenibilidade e Consistência

Python 3.13 com type hints em todos os módulos, Pydantic para schemas,
organização em camadas (routes → services → repositories) dentro de cada
módulo de domínio (RNF20). Linter (ruff) e formatter (ruff format) no
pipeline. Nomenclatura uniforme em inglês no código, descrições/UX em
português nos dados. README e docstrings atualizados junto com o código.

## Requisitos Adicionais (Constraints)

### Stack Tecnológica Obrigatória (RNF03–05)

- **Backend**: Python 3.13, FastAPI, Pydantic v2 (validação de schemas).
- **Frontend web do painel**: React (JavaScript), fora do escopo deste
  backend, mas define o contrato de API.
- **Mobile Passaporte**: Kotlin + Jetpack Compose, fora do escopo deste
  backend, mas define o contrato de API.
- **Persistência**: banco relacional estruturado (RNF17) — PostgreSQL em
  produção; SQLite em memória/arquivo para testes; SQLAlchemy como acesso a
  dados; Alembic para migrations.
- **Mapas**: Google Maps API ou OpenStreetMap (RNF18) — escolha por custo
  (open source preferido, RNF15).
- **Chatbot**: IA generativa com RAG sobre os dados cadastrados (RF38-39) —
  preferir provedores com free tier.

### Tempo de Resposta e Disponibilidade (RNF11, RNF12)

Consultas simples (listagem de pontos, status de rota) devem responder em
tempo hábil para uso mobile. Autenticação, consulta de pontos e marcação de
visitação são os serviços essenciais e não devem depender de subsistemas
pesados (dashboard, chatbot) para responder.

### i18n e Usabilidade (RNF13, RNF16)

Suporte multilíngue da aplicação Passaporte (baixa prioridade, mas o contrato
de API que responde ao front deve ser i18n-ready: mensagens localizáveis,
dados de idioma configuráveis).

## Development Workflow

1. **Specify** (`/speckit-specify`): criar spec da feature com requisitos
   rastreados aos RFs/RNFs de `docs/SYSTEM_REQUIREMENTS.md`.
2. **Clarify/Plan** (`/speckit-clarify`, `/speckit-plan`): resolver
   ambiguidades, gerar plano técnico respeitando limites de módulo.
3. **Tasks** (`/speckit-tasks`): gerar tarefas test-first, agrupadas pelo
   módulo de domínio responsável.
4. **Implement** (`/speckit-implement`): implementar tarefa por tarefa,
   sempre com teste vermelho antes do código verde.
5. **Analyse** (`/speckit-analyze`): verificar consistência entre artefatos.

### Quality Gates

- Testes de contrato e integração do domínio passando.
- `ruff check` sem erros.
- Nenhuma senha em texto plano, nenhum dado sensível não criptografado, no
  código e nos testes.
- Nenhum import cruzando a fronteira privada de outro módulo de domínio.
- Migrations Alembic revisadas quando houver mudança de schema.

## Governance

- A presente constituição prevalece sobre qualquer outra prática,
  preferência individual ou instrução ad hoc de tarefa individual.
- Emendas exigem documentação da mudança, aprovação do responsável e plano
  de migração para código existente; versionamento
  MAJOR.MINOR.PATCH (mudança em princípio = MAJOR).
- Qualquer extração futura de módulo para microsserviço deve partir de um
  amendment (não é decisão de tarefa individual) e deve preservar: mesma
  fronteira de dados, mesma semântica da interface de serviço, mesmo
  contrato REST exposto aos frontends.
- Complexidade extra precisa justificação explícita no PR e é contestável
  em review (YAGNI).

**Version**: 1.0.0 | **Ratified**: 2026-10-30 | **Last Amended**: 2026-10-30