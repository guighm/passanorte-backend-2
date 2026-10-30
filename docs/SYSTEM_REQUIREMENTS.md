# Levantamento de Requisitos — PassaNorte

> Transcrição do documento `docs/SPD-PassaNorte.xlsx` (aba: "Levantamento De Requisitos").

## Identificação do Projeto

| Campo | Valor |
| --- | --- |
| **Nome do Projeto** | PassaNorte |
| **Descrição do Projeto** | Sistema distribuído com foco em gamificação do turismo da cidade de Manaus, integrando tecnologias de geolocalização, planejamento e análise de dados. |

## Requisitos Funcionais (RF)

| ID | Requisito | Descrição | Persona | Módulo | Prioridade | Complexidade |
| --- | --- | --- | --- | --- | --- | --- |
| RF01 | Geração de Credenciais Administrativas | Script para geração de credenciais de alto nível destinadas ao acesso do painel de controle (dashboard, gerenciamento de pontos, eventos, funcionários e recompensas). | Administrador | Autenticação | Alta | Baixa |
| RF02 | Login do Painel Administrativo | O sistema deve permitir autenticação de administradores e funcionários no painel web via credenciais previamente geradas. | Administrador / Funcionário | Autenticação | Alta | Baixa |
| RF03 | Controle de Nível de Acesso (RBAC) | O sistema deve restringir funcionalidades conforme o perfil autenticado: administrador possui acesso total; funcionário acessa apenas a concessão de benefícios. | Administrador / Funcionário | Autenticação | Alta | Média |
| RF04 | Cadastro de Funcionário | O administrador deve poder cadastrar funcionários, gerando credenciais de acesso restrito, que não devem possuir permissão de cadastro de pontos turísticos ou visualização do dashboard. | Administrador | Controle de Funcionários | Média | Baixa |
| RF05 | Edição e Remoção de Funcionário | O administrador deve poder editar dados ou revogar o acesso de um funcionário cadastrado. | Administrador | Controle de Funcionários | Baixa | Baixa |
| RF06 | Dashboard - Mapa de Calor | O painel deve exibir um mapa de calor da cidade com marcações indicando a concentração de visitas por região/ponto turístico. | Administrador | Dashboard e Insights | Alta | Alta |
| RF07 | Dashboard - Contador de Acessos | O painel deve exibir a contagem total de acessos ao sistema (aplicação Passaporte) em períodos configuráveis. | Administrador | Dashboard e Insights | Média | Baixa |
| RF08 | Dashboard - Ranking de Pontos Turísticos | O painel deve exibir o ranking dos pontos turísticos mais visitados, segmentado por dia, mês e ano. | Administrador | Dashboard e Insights | Alta | Média |
| RF09 | Dashboard - Distribuição por País de Origem | O painel deve exibir a proporção de usuários que visitaram pontos turísticos, segmentada por país de origem cadastrado. | Administrador | Dashboard e Insights | Média | Média |
| RF10 | Dashboard - Distribuição por Interesses | O painel deve exibir a proporção de usuários segmentada pelos interesses cadastrados no perfil. | Administrador | Dashboard e Insights | Média | Média |
| RF11 | Cadastro de Ponto Turístico | O administrador deve poder cadastrar um ponto turístico informando nome, descrição, localização (latitude/longitude com integração ao Google Maps) e categoria. | Administrador | Gerenciamento de Pontos Turísticos | Alta | Média |
| RF12 | Edição e Remoção de Ponto Turístico | O administrador deve poder editar ou remover um ponto turístico previamente cadastrado. | Administrador | Gerenciamento de Pontos Turísticos | Média | Baixa |
| RF13 | Categorização de Ponto Turístico | O sistema deve permitir associar cada ponto turístico a uma ou mais categorias pré-definidas (lazer, cultura, gastronomia, natureza, arte, cinema, entre outras). | Administrador | Gerenciamento de Pontos Turísticos | Alta | Baixa |
| RF14 | Cadastro de Cronograma de Funcionamento | O sistema deve permitir o cadastro dos dias e horários de funcionamento de cada ponto turístico. | Administrador | Gerenciamento de Pontos Turísticos | Alta | Baixa |
| RF15 | Controle de Status do Ponto Turístico | O sistema deve permitir a definição do status do ponto turístico entre: aberto ao público, temporariamente fechado ou fechado permanentemente. | Administrador | Gerenciamento de Pontos Turísticos | Alta | Baixa |
| RF16 | Cadastro de Evento | O administrador deve poder cadastrar eventos associados a um ponto turístico, informando data de ocorrência, descrição e preço do ingresso. | Administrador | Gerenciamento de Eventos | Alta | Média |
| RF17 | Edição e Remoção de Evento | O administrador deve poder editar ou remover um evento previamente cadastrado. | Administrador | Gerenciamento de Eventos | Baixa | Baixa |
| RF18 | Cadastro de Rota Turística | O administrador deve poder cadastrar uma rota composta por uma lista de pontos turísticos e um brinde associado à sua conclusão. | Administrador | Gamificação e Benefícios | Alta | Média |
| RF19 | Edição e Remoção de Rota Turística | O administrador deve poder editar ou remover uma rota turística previamente cadastrada. | Administrador | Gamificação e Benefícios | Baixa | Baixa |
| RF20 | Controle de Estoque de Brindes | O sistema deve permitir o cadastro e controle da quantidade disponível em estoque de cada brinde vinculado a uma rota. | Administrador | Gamificação e Benefícios | Alta | Média |
| RF21 | Escaneamento de Código para Concessão de Brinde | O funcionário deve poder escanear o código único gerado pelo turista para validar e conceder o brinde correspondente, com baixa automática no estoque. | Funcionário | Gamificação e Benefícios | Alta | Média |
| RF22 | Cadastro de Usuário (Turista) | O sistema deve permitir o cadastro único do turista com telefone, email, CPF ou número de passaporte, país de origem, nome e sobrenome. | Turista | Cadastro e Perfil | Alta | Baixa |
| RF23 | Login do Turista | O sistema deve permitir a autenticação do turista na aplicação Passaporte por meio de suas credenciais cadastradas. | Turista | Autenticação | Alta | Baixa |
| RF24 | Edição de Perfil do Turista | O turista deve poder visualizar e editar seus dados cadastrais na aplicação. | Turista | Cadastro e Perfil | Baixa | Baixa |
| RF25 | Seleção de Interesses | O turista deve poder selecionar categorias de interesse (ex: gastronomia, natureza, cultura) para personalização de conteúdo e notificações. | Turista | Cadastro e Perfil | Alta | Baixa |
| RF26 | Listagem de Pontos por Relevância | A tela inicial deve exibir os pontos turísticos ordenados por relevância, considerando interesses do usuário, proximidade geográfica e eventos recentes. | Turista | Aplicação Passaporte | Média | Alta |
| RF27 | Visualização de Detalhes do Ponto Turístico | O turista deve poder visualizar informações detalhadas do ponto: descrição, categoria, horário de funcionamento, status e eventos associados. | Turista | Aplicação Passaporte | Alta | Baixa |
| RF28 | Redirecionamento para Aplicativos Externos | O sistema deve gerar links de redirecionamento para Google Maps, Uber e 99 a partir da localização do ponto turístico. | Turista | Integração Externa | Média | Baixa |
| RF29 | Inscrição em Rota Turística | O turista deve poder se inscrever em uma rota disponível, iniciando o acompanhamento de progresso dos pontos associados. | Turista | Gamificação e Benefícios | Alta | Média |
| RF30 | Acompanhamento de Progresso da Rota | O sistema deve exibir ao turista o progresso da rota, indicando os pontos já visitados e os pendentes, bem como uma barra de progresso responsiva à taxa de conclusão da rota. | Turista | Gamificação e Benefícios | Alta | Baixa |
| RF31 | Marcação de Visitação | O turista deve poder acionar a opção 'marcar visitação' ao estar em um ponto turístico cadastrado. | Turista | Geolocalização | Alta | Baixa |
| RF32 | Validação de Presença via GPS (Haversine) | O sistema deve confirmar a presença do usuário no ponto turístico por meio da leitura de GPS e cálculo de proximidade utilizando o algoritmo de Haversine. | Turista | Geolocalização | Alta | Alta |
| RF33 | Registro de Status de Visitação | Após validação de presença, o sistema deve gravar o status 'visitado' do ponto turístico para o usuário. | Turista | Geolocalização | Alta | Média |
| RF34 | Atualização de Progresso em Rotas Vinculadas | Ao registrar a visitação de um ponto, o sistema deve atualizar o progresso de todas as rotas em andamento que contenham esse ponto. | Turista | Gamificação e Benefícios | Alta | Média |
| RF35 | Emissão de Insígnia Digital | Ao concluir todos os pontos de uma rota, o sistema deve conceder ao turista uma insígnia digital de conclusão. | Turista | Gamificação e Benefícios | Média | Média |
| RF36 | Geração de Código Único de Resgate | Ao concluir uma rota, o sistema deve gerar um código de uso único para que o turista resgate o brinde associado junto a um funcionário assim que desejar e seja possível a retirada. | Turista | Gamificação e Benefícios | Alta | Média |
| RF37 | Assinatura de Notificações por Interesse | O turista deve poder se inscrever em interesses específicos para receber notificações relacionadas (novos eventos, pontos ou rotas). | Turista | Notificações | Média | Média |
| RF38 | Chatbot de Planejamento de Roteiro (RAG) | O sistema deve disponibilizar um chatbot com IA generativa (RAG) capaz de montar roteiros personalizados em linguagem natural, com base nos pontos e eventos cadastrados. | Turista | Chatbot IA | Alta | Alta |
| RF39 | Chatbot - Consideração de Critérios de Planejamento | O chatbot deve considerar custo dos ingressos, proximidade entre pontos, interesses do usuário e horários de funcionamento ao gerar o roteiro. | Turista | Chatbot IA | Alta | Alta |

## Requisitos Não Funcionais (RNF)

| ID | Requisito | Descrição | Módulo | Prioridade | Complexidade |
| --- | --- | --- | --- | --- | --- |
| RNF01 | Arquitetura de Sistema Distribuído | O sistema deve ser projetado com características fundamentais de um sistema distribuído, com componentes independentes se comunicando em rede. | Arquitetura | Alta | Alta |
| RNF02 | Arquitetura Baseada em Microsserviços | O backend deve ser estruturado em microsserviços independentes, cada um responsável por um domínio funcional específico (ex: usuários, pontos turísticos, gamificação, chatbot). | Arquitetura | Alta | Alta |
| RNF03 | API RESTful em Python | A comunicação entre os subsistemas (painel web e aplicativo mobile) deve ocorrer por meio de uma API RESTful desenvolvida em Python com FastAPI e Pydantic. | Arquitetura | Alta | Média |
| RNF04 | Painel Administrativo em React | O painel de controle deve ser desenvolvido como aplicação web utilizando React (JavaScript). | Arquitetura | Alta | Média |
| RNF05 | Aplicativo Mobile em Kotlin | A aplicação Passaporte deve ser desenvolvida em Kotlin com Jetpack Compose, consumindo os mesmos endpoints da API utilizada pelo painel administrativo. | Arquitetura | Alta | Média |
| RNF06 | Portabilidade para Outras Localidades | O sistema deve ser estruturado de forma que a adaptação para outras cidades, estados ou países exija apenas configuração de dados, sem necessidade de reestruturação da arquitetura. | Arquitetura | Média | Alta |
| RNF07 | Escalabilidade Horizontal | Os microsserviços devem poder ser escalados horizontalmente de forma independente conforme a demanda de cada domínio. | Desempenho | Média | Alta |
| RNF08 | Segurança de Dados Pessoais (LGPD) | Dados sensíveis do usuário (CPF, número de passaporte, contato) devem ser armazenados de forma criptografada, em conformidade com a LGPD. | Segurança | Alta | Média |
| RNF09 | Autenticação Baseada em Token (JWT) | O acesso à API deve ser controlado por meio de tokens de autenticação (JWT), com expiração e renovação controladas. | Segurança | Alta | Média |
| RNF10 | Criptografia de Credenciais | As senhas de administradores, funcionários e turistas devem ser armazenadas utilizando hash criptográfico (ex: bcrypt), nunca em texto plano. | Segurança | Alta | Baixa |
| RNF11 | Disponibilidade do Sistema | O sistema deve manter alta disponibilidade dos serviços essenciais (autenticação, consulta de pontos e marcação de visitação), minimizando períodos de indisponibilidade. | Confiabilidade | Média | Alta |
| RNF12 | Tempo de Resposta da API | As requisições à API para consultas simples (listagem de pontos, status de rota) devem responder em tempo hábil para uma boa experiência de uso mobile. | Desempenho | Média | Média |
| RNF13 | Usabilidade da Aplicação Mobile | A interface da aplicação Passaporte deve seguir princípios de usabilidade e acessibilidade, com navegação intuitiva para turistas de diferentes perfis e nacionalidades. | Usabilidade | Alta | Média |
| RNF14 | Precisão da Geolocalização | O cálculo de proximidade via algoritmo de Haversine deve utilizar um raio de tolerância adequado para validar a presença do usuário sem gerar falsos positivos ou negativos. | Confiabilidade | Alta | Média |
| RNF15 | Baixo Custo de Infraestrutura | Considerando o caráter acadêmico do projeto e a ausência de orçamento, a infraestrutura deve priorizar ferramentas, serviços e bibliotecas gratuitas ou de código aberto. | Infraestrutura | Alta | Baixa |
| RNF16 | Suporte Multilíngue (i18n) | A aplicação Passaporte deve oferecer suporte a múltiplos idiomas, considerando o público de turistas internacionais. | Usabilidade | Baixa | Média |
| RNF17 | Persistência de Dados | O sistema deve utilizar um banco de dados adequado para armazenamento estruturado de usuários, pontos turísticos, rotas, eventos e benefícios. | Infraestrutura | Alta | Média |
| RNF18 | Interoperabilidade com Google Maps | O sistema deve se integrar à API do Google Maps ou OSM para exibição de mapas e cálculo de rotas até os pontos turísticos. | Integração Externa | Alta | Média |
| RNF19 | Registro de Auditoria (Logs Administrativos) | Ações administrativas críticas (cadastro/edição/remoção de pontos, eventos e funcionários) devem ser registradas em log para fins de auditoria. | Segurança | Média | Baixa |
| RNF20 | Manutenibilidade do Código | O código de cada microsserviço deve seguir boas práticas de organização e documentação, facilitando manutenção e evolução futura do sistema. | Qualidade de Software | Média | Baixa |