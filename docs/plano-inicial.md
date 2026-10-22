# Plano inicial

Documento de partida (briefing, seção 25). Data: 05/10/2026. Atualizar a cada fase.

## 1. Resumo do entendimento

A Cabana do Jacarandá opera com o SET Sistemas como ERP, sem acesso ao banco e sem
disponibilidade do desenvolvedor. A loja virtual está na Nuvemshop, integrada ao Bling e não
ao SET. O novo sistema é **auxiliar**: roda na rede interna (servidor Windows 192.168.3.254,
só pela VPN, em `/sistema`), é alimentado por relatórios exportados do SET e não emite nota
nem substitui o ERP.

O risco mais urgente é de pessoas, não de software: a Bárbara concentra o conhecimento de
vendas e estoque e está em aviso prévio. Por isso a primeira entrega é a base de processos,
que transforma o que ela sabe em procedimentos testados por outra pessoa e validados pela gestão.

Depois vêm, nesta ordem: importação validada dos relatórios do SET com fotografias de estoque
por data de corte; catálogo e estoque com saldos separados; sugestões de compra explicáveis
(regras determinísticas, sem IA paga); cotações e pedidos com alçadas; indicadores financeiros
limitados ao que os dados sustentam; conciliação com o site; e, por último, o ponto (Stelanto).

## 2. Prioridades

Atualização de 05/10/2026: o Edson pediu para provar com números que a compra sem critério pesa no caixa. O diagnóstico de compras foi antecipado e já roda com planilha. A implantação segue as regras de [implantacao-sem-impacto.md](implantacao-sem-impacto.md).

1. **Capturar os processos da Bárbara antes da saída** (entregue a ferramenta; falta agenda real).
2. **Diagnóstico do ambiente**: servidor, intranet, VPN, certificados. Sem isso não há instalação.
3. **Amostras dos relatórios do SET**: definem o que é possível importar e calcular.
4. **Contatos de fornecedores e artesãos fora de contas pessoais** (parte do roteiro, prioridade alta).
5. Backup funcional desde a primeira instalação.
6. Só então estoque, compras e finanças, sempre com “Dados atualizados até...”.

## 3. Dados ainda necessários

| # | O que | Por que bloqueia |
|---|---|---|
| 1 | Versão do Windows, CPU/RAM/disco livre, serviços já instalados (IIS? Hyper-V? PostgreSQL?), permissões de administrador e se dá para ter homologação separada | Define implantação nativa vs. VM Linux e o proxy |
| 2 | Tecnologia e forma de login da intranet; repositório Git autorizado; contas reais de Edson, Henriett e Moizes | Define SSO (OIDC, LDAP/AD ou outro) e onde guardar o código |
| 3 | Amostras anonimizadas dos relatórios do SET (vendas, estoque, produtos, fornecedores, compras, custos, contas a pagar/receber) e horário de corte de cada um | Sem formato real não há mapeamento de importação |
| 4 | Paleta, logotipo e telas da intranet | Cores e logo atuais são provisórios |
| 5 | Último dia do aviso prévio e disponibilidade semanal da Bárbara | Define prazos do quadro e agenda das entrevistas |
| 6 | Quantidade de produtos e usuários; regras de compra e alçadas existentes | Dimensionamento e regras de aprovação |
| 7 | Como o Bling atualiza a Nuvemshop, quais estoques são compartilhados e permissões de API | Define a autoridade única do saldo do site |

A lista completa e atualizada fica em [perguntas-pendentes.md](perguntas-pendentes.md).

## 4. Arquitetura proposta

Monólito modular em **Python 3.11+ / Django 5.2 LTS** (suporte até abril de 2028) com
**PostgreSQL**, telas renderizadas no servidor (HTML simples, HTMX quando ajudar), gráficos com
Apache ECharts, ícones Lucide com rótulo. Detalhes e alternativas em [arquitetura.md](arquitetura.md).

Por que esta pilha:

- **Intranet**: Django suporta OIDC, LDAP/AD e cabeçalho de proxy confiável; a escolha final
  depende da resposta 2. Funciona sob subcaminho (`/sistema`) sem truques.
- **Windows**: roda nativo (Waitress como servidor de aplicação + IIS/ARR ou Caddy como proxy
  HTTPS + PostgreSQL para Windows como serviço) ou numa VM Linux no Hyper-V. Nenhuma das duas
  exige Docker Desktop.
- **Segurança**: CSRF, escape de saída, ORM parametrizado, sessão e permissões maduros; segue OWASP ASVS.
- **Licenças**: Django (BSD), PostgreSQL (PostgreSQL License), psycopg (LGPL), django-axes (MIT),
  ECharts (Apache 2.0), Lucide (ISC). Tudo gratuito; custos possíveis só em hospedagem
  externa, Google Drive acima da cota, WhatsApp oficial e eventual receptor externo de webhooks.
- **Manutenção**: tecnologia comum, fácil de achar quem mantenha; dados e regras de negócio
  ficam no servidor e testados.
- **Tarefas em segundo plano**: fila persistente no próprio PostgreSQL (tabela de jobs com
  `SELECT ... FOR UPDATE SKIP LOCKED`), processada por um serviço Windows; funciona em
  Windows, sem Redis nem Celery. Agendador com trava (advisory lock) e registro por execução.

Módulos: identidade e acesso; importação; catálogo; estoque; fornecedores; orçamento e
compras; finanças; indicadores; notificações; integrações; base de processos; auditoria; backup.

## 5. Plano por fases

| Fase | Entrega | Critério para fechar |
|---|---|---|
| 0 | Diagnóstico do ambiente e da intranet, amostras do SET, identidade visual, **captura urgente dos processos** | Respostas 1 a 7 recebidas; base de processos em uso com a Bárbara |
| 1 | Identidade (SSO), permissões, auditoria, **base de processos** (feito), catálogo, importação validada, snapshots, painéis com data de corte, backup | Importação repetida não duplica; restauração testada; acesso em `/sistema` no computador e celular |
| 2 | Regras de estoque, sugestões explicáveis, central de alertas, fornecedores e artesãos, cotações, aprovações, pedidos, Kanban de compras | Compra acima da alçada não vira pedido; alerta contínuo não gera mensagens repetidas |
| 3 | Fontes financeiras, relatórios e gráficos, e-mail, Telegram, backup e restauração consolidados | Indicadores marcam “estimado”/“não disponível”; falha externa não duplica envio |
| 4 | Conciliação do estoque do site, piloto com poucos SKUs e autoridade única | Conflito Bling/Nuvemshop detectado; nada sobrescrito em direções concorrentes |
| 5 | Refinamentos por uso, desempenho, integração Stelanto (ponto) | Conforme validação da gestão e da contabilidade |

## 6. Primeiro backlog Kanban

Estados do quadro de desenvolvimento: **Pronto para fazer → Fazendo → Em revisão → Em homologação → Aceito**.

| # | Item | Fase | Estado | Depende de |
|---|---|---|---|---|
| 1 | Base de processos: quadro, versões, testes, validação, anexos, busca | 1 | Em revisão | — |
| 2 | Perfis e permissões por ação; trilha de auditoria somente inclusão | 1 | Em revisão | — |
| 3 | Roteiro de entrevistas e 21 processos pré-cadastrados | 0 | Em revisão | — |
| 4 | Agendar entrevistas com datas reais e definir titulares/substitutos | 0 | Pronto para fazer | Resposta 5 |
| 5 | Levantamento do servidor Windows (checklist em arquitetura.md) | 0 | Pronto para fazer | Resposta 1 |
| 6 | Escolher integração de login com a intranet (OIDC/LDAP/proxy) | 1 | Bloqueado | Resposta 2 |
| 7 | Levar o código para o repositório autorizado | 0 | Bloqueado | Resposta 2 |
| 8 | Aplicar paleta e logotipo oficiais | 1 | Bloqueado | Resposta 4 |
| 9 | Assistente de importação (lote, hash, prévia, quarentena, publicação) | 1 | Pronto para fazer (estrutura) | Resposta 3 para os mapeamentos |
| 10 | Snapshots de estoque por data de corte e reconciliação | 1 | Pronto para fazer (estrutura) | Resposta 3 |
| 11 | Catálogo: produto, variante, unidade, mapeamentos SET/Nuvemshop/Bling | 1 | Pronto para fazer | — |
| 12 | Backup do PostgreSQL e anexos com criptografia; destino Google Drive | 1 | Pronto para fazer (local) | OAuth da conta da Cabana |
| 13 | Instalação em homologação (proxy HTTPS, serviço, `/sistema`) | 1 | Bloqueado | Respostas 1 e 2 |
| 14 | Ajuda contextual, tour guiado e F1 | 1 | Pronto para fazer | — |
| 15 | Delegações temporárias de perfil com validade | 1 | Pronto para fazer | — |
| 16 | Lockfile com hashes gerado no servidor Windows | 1 | Pronto para fazer | Resposta 1 |
| 17 | Ambiente de demonstração com dados fictícios identificados | 1 | Pronto para fazer | — |
| 18 | Diagnóstico de compras por planilha (parado, excesso, comprado acima, falta, sugestão) | 2 antecipado | Em revisão | — |
| 19 | Rodar o diagnóstico com os relatórios reais do SET e apresentar à gestão | 2 antecipado | Bloqueado | Resposta 3 |
| 20 | Tela do diagnóstico no sistema, com gráfico e detalhamento por item | 2 | Pronto para fazer | Item 19 |

## 7. Critérios de aceite da entrega 1 (base de processos)

| Critério | Como foi verificado |
|---|---|
| Um processo só chega a “Validado pela gestão” depois que outra pessoa o executa usando só a documentação | Testes automatizados `test_validar_exige_teste_aprovado_da_versao_atual`, `test_autor_e_titular_nao_testam`, `test_teste_com_ajuda_nao_conta_para_validar` |
| Só a gerência valida e aprova regras | `test_so_gerencia_valida`, `test_regra_so_pela_gerencia` |
| Mudar o procedimento exige novo teste; a versão validada anterior continua registrada | `test_nova_versao_depois_de_validado_volta_para_documentacao` |
| Duas pessoas editando ao mesmo tempo não se sobrescrevem | `test_edicao_concorrente_e_recusada` |
| Senhas e CPF não entram nos procedimentos | `test_recusa_senha`, `test_recusa_cpf`; tela conferida no navegador |
| Operador bloqueado nas telas, URLs e anexos que não pode usar | `TelasEPermissoesTest` |
| Anexo com extensão falsa, tipo não aceito, grande demais ou foto de pessoa sem autorização é recusado | `AnexosTest` |
| Ações registradas na auditoria, que não pode ser alterada nem apagada | `TrilhaSomenteInclusaoTest` (inclui gatilho no PostgreSQL) |
| Tudo funciona sob `/sistema`, inclusive login, cookies e estáticos | `PrefixoSistemaTest`; navegação no computador e no celular conferida |
| **Pendente (só com a equipe):** a Bárbara e outra pessoa usam o quadro em um processo real | Homologação na Cabana |

## 8. O que não foi feito e por quê

- **Instalação no servidor 192.168.3.254**: este ambiente de desenvolvimento não alcança a VPN.
- **Login pela intranet**: tecnologia da intranet ainda desconhecida; contas locais provisórias.
- **Importação do SET**: sem amostras reais não há mapeamento confiável.
- **Cores e logotipo oficiais**: não recebidos; a paleta atual é neutra e marcada como provisória.
- **HTMX e Lucide**: não foi possível baixar dos CDNs neste ambiente; as telas usam HTML simples
  e rótulos de texto, o que já atende ao uso. Serão incluídos localmente (sem CDN) na instalação.
