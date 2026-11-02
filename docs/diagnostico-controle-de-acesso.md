# Controle de acesso do Aux SET: o que já existe, o que falta e o plano

Resposta ao prompt "Implementação do módulo de usuários e controle de acesso", que o Edson
mandou em 02/11/2026. Conferido sobre o código da 1.43.0, que é a versão da loja desde
31/10/2026 19:09 (conferida no GitHub antes de começar).

**Situação**: a etapa 1 saiu na 1.44.0 (02/11/2026). Como ficou, regra por regra, está em
`controle-de-acesso.md`; o passo a passo da gerência, em `manual/usuarios-e-acessos.md`. As
tabelas abaixo descrevem a 1.43.0, antes da etapa 1, e ficam como registro do ponto de
partida.

Resumo: a base que o prompt pede (perfil → permissão por ação, conferida no servidor em
toda tela, auditoria que não se apaga, sessão que vence, bloqueio por tentativas,
recuperação de senha por código) já existe desde as primeiras versões. O que falta é o
que deixa a gerência **administrar** isso sem programador: perfis editáveis, vários
perfis por pessoa, a ficha da pessoa com sessões e histórico, as travas contra o último
administrador e contra quem dá a si mesmo mais acesso, a alçada de compra por valor e o
segundo fator para a administração.

## 1. O projeto hoje

| Item | Como está |
|---|---|
| Linguagem e framework | Python 3.12 no servidor, Django 5.2 LTS (suporte até 04/2028) |
| Banco e migração | PostgreSQL 16 na porta 5433; migrações do Django |
| Usuário | `User` do Django + `VinculoIdentidade` (origem, identificador externo, CPF, desligado em, último dia de acesso) |
| Perfis | Grupos do Django, definidos em `apps/contas/perfis.py` e regravados a cada instalação pelo `configurar_perfis` |
| Autenticação | Local: usuário e senha do Aux SET, senha com PBKDF2-SHA256 de 1.000.000 de voltas (o padrão do Django 5.2), mínimo de 12 caracteres, django-axes |
| Intranet | Nenhuma integração. A intranet é o site Baloes no IIS do mesmo servidor (`/intranet`, PHP 8.5); como ela confere quem entra nunca foi respondido (pergunta 2 de `perguntas-pendentes.md`) |
| Rotas | 137 (fora o admin do Django), todas sob `/sistema` |
| APIs | Autocompletar da consulta (JSON), leitor de código de barras, conferência de etiqueta |
| Uploads | Anexos de processos e de pedidos, foto da contagem, extrato do banco (OFX/CSV) |
| Exportações | CSV, XLSX, TSV e PDF em nove telas |
| Segundo plano | Tarefas do Windows: importação 3x ao dia, alertas de hora em hora, backup às 23:30, higienização às 03:40, tempo às 06:10 |
| Segurança já usada | django-axes 8.3.1, CSRF, cookies HttpOnly e SameSite=Lax no caminho `/sistema`, X-Frame-Options DENY, nosniff, referrer same-origin, anexos fora da pasta pública, auditoria somente inclusão com gatilho no PostgreSQL |
| Implantação | Windows 10 Pro; Waitress em HTTP na 8095 e túnel TLS próprio em HTTPS na 8443 (certificado da loja); `config.settings.homolog`, porque o computador do balcão ainda entra por HTTP; pacote numerado com `atualizar.ps1`, que faz backup do banco antes de migrar |

## 2. Identidade da intranet

Não há SSO, OIDC nem LDAP para usar hoje. O modelo já está pronto para o dia em que houver:
`VinculoIdentidade` guarda a origem e um identificador externo único (chave estável,
nunca o nome de exibição), e as contas de hoje estão marcadas como "conta local
provisória".

Caminhos, na ordem de preferência (detalhe em `arquitetura.md`):

1. **OIDC**, se a intranet ou um provedor (Keycloak, Entra ID) oferecer: entrada única,
   segundo fator e desligamento num lugar só.
2. **LDAP / Active Directory**, se a loja tiver domínio Windows: entra com a conta da rede.
3. **Windows Authentication no IIS**, repassando a identidade num cabeçalho confiável.
4. Se a intranet só tiver usuários num banco próprio: **não copiar senhas**; a intranet
   teria de virar provedor OIDC (mexer no PHP dela), ou o Aux SET segue com contas
   próprias.

Até a resposta, cada pessoa continua com usuário e senha do Aux SET. Nada do que está
abaixo depende dessa decisão.

## 3. Autorização

| Pedido | Hoje | Onde |
|---|---|---|
| RBAC usuário → perfil → permissão | Sim | grupos e permissões do Django |
| Conferida no servidor, não no botão | Sim, em toda tela | `permission_required` + `has_perm`; varredura automática das 137 rotas × perfis (`apps/contas/tests/test_rotas_por_perfil.py`) |
| Negar por padrão | Sim na prática (o vendedor só abre a consulta); falta o teste da pessoa **sem** perfil | etapa 1 |
| Empresa ou unidade | Não se aplica: o Aux SET lê só a Cabana (as empresas 2 e 3 do banco do SET não são lidas) | `docs/caixa.md` |
| Limite (alçada) de compra por valor | Não existe: só "a gerência aprova" | etapa 2 |
| Responsabilidade pelo registro | Pedido: quem montou muda a quantidade enquanto espera aprovação | `apps/pedidos/servicos.py` |
| Estado do processo | Pedido (esperando aprovação, feito, recebido, cancelado), processo (rascunho, validado) | |
| Solicitar × aprovar | Sim para a Líder de loja; o pedido da gerência nasce aprovado por ela | etapa 2 |
| Componente central | O Django faz a soma das permissões; as regras de pedido estão no serviço do pedido | etapa 1 junta as regras de acesso em `apps/contas/autorizacao.py` |

## 4. Perfis

Hoje são quatro, com nomes e conteúdo decididos pelo Edson (07/10 e 31/10/2026):

| Perfil de hoje | Na proposta |
|---|---|
| Administrador gerência (Edson, Henriett, Moizes) | Gerência |
| Líder de loja (Cássia) | sem equivalente: compras + estoque + parte do financeiro |
| Operador administrativo | sem equivalente |
| Operador vendedor | Operador |

- As contas de Edson, Henriett e Moizes foram criadas por migração **sem senha**: ninguém
  entra com senha padrão.
- **Não há separação** entre administrar acessos e ver dinheiro: quem administra é a
  gerência, que vê tudo.
- **Superusuário**: o instalador da primeira vez criou um (`createsuperuser`). Ele passa
  por cima de todos os perfis e entra no `/sistema/admin/` do Django. Hoje ele não aparece
  diferente na tela de usuários, e mudar as permissões de um perfil pelo admin do Django
  não fica na auditoria.
- **Grupos antigos**: os cinco perfis do começo (Gerência, Compras, Estoque, Operadores,
  Consulta e auditoria) viraram os três em 07/10. Na reinstalação por engano da 1.4.0, em
  22/10, eles voltaram vazios, com as permissões antigas, e "Compras" e "Estoque" abriam
  todos os números da loja. Ninguém está neles, mas um perfil novo com o mesmo nome
  herdaria essas permissões. A etapa 1 limpa isso.

## 5. Catálogo de permissões

São 31 permissões em uso, todas por ação e com código estável (`pedidos.aprovar_pedido`,
`financeiro.lancar_pagamento`, `inventario.fechar_contagem`...). O problema é uma só:
**`importacao.ver_painel` abre 37 pontos**, do Dashboard à margem e à lista de compra. Com
ela não dá para ter um perfil de Compras que veja a lista sem ver o lucro da loja.

Do exemplo do prompt, não se aplicam porque não existe o que proteger: cotações (não há
módulo de cotação), editar produto (o produto é do SET), publicar ou reverter importação
(a importação lê a cópia do backup e não publica nada) e restaurar backup (se faz no
servidor, fora da tela). Permissão sem efeito no servidor não entra no catálogo.

## 6. Regras de concessão

| Pedido | Hoje |
|---|---|
| Vários perfis | O Django soma; a tela só deixa escolher um |
| Bloqueio prevalece | Sim: conta desligada não abre nada |
| Exceção individual | Não usada; se alguém der pelo admin do Django, fica na auditoria |
| Não dar além da própria autoridade | Só a gerência mexe em acesso, e ela tem tudo; com um "Administrador de acessos" isso precisa de regra |
| Não aumentar o próprio acesso | Ninguém encerra o próprio acesso, mas a pessoa **pode mudar o próprio perfil** |
| Último administrador | **Sem trava**: dá para tirar o perfil do último que administra |
| Recuperação | Só pelo `createsuperuser` no servidor, sem procedimento escrito |

## 7. Telas

Hoje há uma tela, "Usuários e acessos": lista com perfil, senha e encerrar em cada linha,
mais a data para acabar, o e-mail de recuperação e "dar acesso a mais alguém". Faltam
busca, a ficha de cada pessoa, vários perfis, a matriz de permissões, as permissões
efetivas de uma pessoa, as sessões abertas, o histórico de acesso da pessoa e o estado
da integração. Situações: hoje ativo, desligado e "ainda sem senha"; falta **bloqueado**
(temporário) separado de **desligado** (saiu da empresa).

## 8. Entrada e sessão

| Pedido | Hoje |
|---|---|
| Mecanismo do framework para a senha | Sim, PBKDF2 de 1.000.000 de voltas. Argon2id: fica como está (abaixo) |
| Senha fora de log e auditoria | Sim, e há teste |
| Senha longa e gerenciador de senhas | Sim: sem teto de tamanho, campos com `autocomplete` certo |
| Sem troca periódica | Sim |
| Recuperação com código de uso único | Sim, desde a 1.43.0: 15 minutos, 5 tentativas, código guardado só como assinatura |
| Mensagem que não revela conta | Sim, na recuperação e na entrada |
| Força bruta | Sim: 5 erros bloqueiam 15 minutos (usuário + IP); limites por hora na recuperação |
| Segundo fator (MFA) para a administração | **Não existe** (decisão do Edson, etapa 3) |
| HTTPS | Sim na 8443; o balcão ainda entra por HTTP na 8095, e por isso o cookie não pode ser `Secure` |
| CSRF | Sim |
| Sessão nova ao entrar | Sim (Django); na confirmação de senha, etapa 1 |
| Tempo parado e tempo máximo, no servidor | Sim: 30 minutos e 4 horas |
| Sair invalida a sessão | Sim |
| Confirmar a senha para mexer em acesso | **Não existe** (etapa 1) |
| Nada de token no `localStorage` | Sim: ele só guarda "já vi o tour" e "já vi o lembrete" |

**Argon2id**: o Django aceita, mas precisa de uma biblioteca compilada (`argon2-cffi`). Se
ela falhar no servidor depois de as senhas terem sido convertidas, ninguém entra. O PBKDF2
de 1.000.000 de voltas está acima do que a OWASP pede (600.000). Decisão de 14/10/2026
mantida: não trocar o formato da senha de todo mundo numa máquina que não dá para
acompanhar daqui.

## 9. Bloqueio e desligamento

Desligar impede a entrada e derruba as sessões abertas na hora; a data para acabar
(1.42.0) faz isso sozinha no dia seguinte. Mudança de perfil vale na requisição seguinte:
o Django lê as permissões do banco a cada uma, não há token emitido e o cache guarda
números, não permissões. Conta não se apaga pela tela, então autoria de pedido, contagem e
importação fica. Não há conta de serviço com senha: as tarefas rodam como serviço do
Windows e assinam a auditoria pelo nome da tarefa; o token do GitHub só escreve num
repositório. Bloqueio na intranet não chega ao Aux SET, porque não há integração, e o
sistema não diz o contrário.

## 10. Proteção dos dados

URL digitada, autocompletar, anexos e exportações passam pela permissão (a varredura de
rotas cobre tudo). As telas filtram no banco; não há API que mande tudo para o navegador
filtrar. O vendedor não vê custo em lugar nenhum. Falta: custo do pedido escondido de quem
só recebe mercadoria (etapa 2) e auditoria de cinco exportações que ainda não registram
(etapa 1).

## 11. Aprovações

O pedido da Líder de loja espera a gerência. Falta a alçada por valor, a regra "quem pede
não aprova acima de tanto", o pedido aprovado voltar para aprovação quando muda o que
importa, e a trava de linha na aprovação (hoje dois gerentes aprovando ao mesmo tempo
passam os dois). Etapa 2.

## 12. Auditoria

Já registra entrada, falha de entrada, saída, perfil, senha, desligamento, data para
acabar, recuperação de senha e aprovação de pedido, com usuário ou serviço, hora, ação,
recurso, resultado, correlação, IP, antes, depois e motivo; nunca senha, token nem CPF; não
se altera nem se apaga. Falta: **tentativa negada**, mudança nas permissões de um perfil,
sessão encerrada uma a uma, entrada de superusuário marcada como tal e as exportações
acima. Retenção: a trilha fica para sempre (1.260 eventos na cópia daqui; cresce pouco), e
a higienização não toca nela.

## 13. Experiência

Paleta e componentes da Cabana, tela escura, computador e celular conferidos em print,
usuário conectado e Sair no alto, F1 com ajuda. A frase "Use seu próprio usuário. As ações
ficam registradas..." já aparece no alto de toda tela, e a de acesso negado é quase a pedida:
as duas passam ao texto do prompt na etapa 1.

## 14. Migração

O `configurar_perfis` é repetível sem duplicar, mas **regrava** os perfis a cada
atualização: perfil editado pela tela voltaria ao que está no código. Na etapa 1 ele passa
a criar o que falta e acrescentar só permissão nova, sem desfazer o que a gerência mudou.
O backup do banco já roda antes de cada atualização. Não há homologação separada: a
validação é aqui, com a cópia do banco e os testes, antes de cada pacote.

## Plano

**Etapa 1 (1.44.0, entregue): perfis de verdade, ficha da pessoa e travas.** Catálogo de
permissões com nome em português; `ver_painel` dividido para Compras e Estoque fazerem
sentido, sem ninguém perder acesso; perfis editáveis numa matriz; vários perfis por
pessoa; perfis novos prontos (Administrador de acessos, Compras, Estoque, Consulta e
auditoria); ficha da pessoa com permissões efetivas, sessões abertas e histórico;
situação bloqueado separada de desligado; confirmar a senha antes de mexer em acesso;
ninguém mexe no próprio acesso nem dá o que não tem; o último administrador não sai;
recuperação pelo servidor; tentativa negada na auditoria; relatório de impacto.

**Etapa 2: alçada de compra.** Limite por perfil e por valor; quem pede não aprova acima
do limite; pedido aprovado que muda volta para aprovação; trava de linha; custo do pedido
só para quem tem permissão de custo.

**Etapa 3: segundo fator e só HTTPS.** Código do celular (aplicativo autenticador) para a
administração, com códigos de reserva; e, depois que os computadores tiverem o
certificado, desligar o HTTP da 8095 para o cookie ser `Secure`.

**Etapa 4: intranet.** Depende de saber como a intranet confere quem entra.
