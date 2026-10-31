# O menu por assunto (1.35.0)

Pedido do Edson em 19/10/2026:

> *"no meu entendimento o sistema está ficando com muitos menus, acaba dificultando o
> acesso e a tomada de decisões rápidas. Objetivo do sistema seja uma ferramenta para
> auxiliar os gestores de forma rápida com informações assertivas. Reformular os menus,
> manter os mais importantes em destaque. Imagine os gestores em viagem, precisando
> tomar uma decisão rápida para comprar, como se fosse uma bolsa de valores, tem momento
> exato para comprar, precisamos de facilidade. Estudar para tentar viabilizar incorporar
> os demais menus nos menus mais importantes (...) os menus precisam se conectarem com o
> mesmo assunto."*

## O que era, e por que incomodava

Vinte e sete telas, em duas fileiras, todas à vista ao mesmo tempo. A fileira de cima
tinha dez; a de baixo, dezessete. As duas fileiras foram uma melhoria quando entraram
(07/10/2026, quando eram catorze telas numa fileira só), mas o sistema continuou
crescendo e a conta voltou.

O problema não é o número de telas: é que **todas disputavam a atenção na mesma tela**.
Quem abre o sistema no celular, na estrada, para decidir uma compra, lê vinte e sete
rótulos antes de chegar no único que importa naquele minuto.

## O que é agora

Sete entradas no topo desde a 1.43.0 (eram seis na 1.35.0; ver "O Dashboard na frente",
abaixo), cada uma um assunto:

| Assunto | O que tem dentro |
|---|---|
| **Dashboard** | A loja em quadros: venda, margem, estoque e o que pede atenção (desde a 1.43.0) |
| **Visão geral** | Como a loja está hoje, e o que fazer agora |
| **Compras** | Lista de compra, Pedidos, Fornecedores, Indicadores de compra (desde a 1.40.1; Antes de comprar, Sugestões, Sugestões da equipe e Últimas compras abrem pela fileira "Também em Compras", logo abaixo do título da Lista) |
| **Vendas** | Vendas do dia, Margem, Ticket médio, Clientes (o Dashboard morava aqui até a 1.42.0) |
| **Estoque** | Consulta, Inventário |
| **Dinheiro** | Financeiro, Caixa, Conciliação |
| **Sistema** | Importações, Dados da empresa, Base de processos, Usuários, Alertas, Backup, Certificado, Auditoria |

A segunda fileira do topo mostra **só as telas do assunto aberto**. Então a pessoa vê
sete rótulos mais os cinco ou seis do assunto em que está, nunca os vinte e sete juntos.

**Nenhuma tela foi apagada.** As vinte e sete continuam existindo, com o mesmo endereço
e o mesmo conteúdo; o que mudou é como se chega a elas.

## As três decisões que valem a pena saber

**Clicar no assunto cai na tela que decide, não num índice.** "Compras" abre a Lista de
compra; "Dinheiro" abre o Financeiro. Uma página intermediária que só oferece links
custaria um clique a mais justamente a quem está com pressa, que é o pedido inteiro.

**Compras vem logo depois da Visão geral**, e a primeira tela dela é a Lista de compra.
A ordem do menu é a ordem da decisão: ele disse que comprar é o que precisa ser decidido
rápido, e a Lista de compra é onde a quantidade é escolhida e o pedido sai.

**Assunto sem nenhuma tela aberta some do topo.** O operador vendedor enxerga um assunto
só — Estoque, com a Consulta —, e por isso não recebe segunda fileira nenhuma. Mostrar
"Dinheiro" para quem não pode abrir nada de dinheiro é oferecer uma porta trancada.

## O Dashboard na frente (1.43.0)

Pedido dele em 31/10/2026: *"logo quando fazer login quero que abra o Dashboard, causa bom
impacto com as informações visíveis. no mesmo menu (principal) colocar ao lado como segunda
opção a visão geral."*

- **O Dashboard virou a primeira entrada do topo**, e a Visão geral a segunda, ao lado. Saiu
  de dentro de Vendas, para não aparecer em dois lugares.
- **Entrar abre o Dashboard**: a primeira tela de cada um é a primeira entrada do menu que o
  perfil abre (`primeira_tela`), então a regra é a ordem do menu, sem exceção escrita à
  parte. Quem não vê o Dashboard (o vendedor) continua caindo na Consulta.
- **Abrir rápido sendo a primeira tela**: o Dashboard do período padrão fica guardado depois
  de cada importação e a cada hora, como a Visão geral (`painel/aquecer.py`,
  `servicos.dashboard_da_importacao`). Guardado, abre com 36 consultas em cerca de 0,13 s
  na máquina de desenvolvimento; sem guardar eram 90 consultas e 1,3 s. Com filtro de grupo
  ou fornecedor, a conta é feita na hora, como antes.

## Onde isto mora

`apps/core/menu.py` é a única lista: os assuntos, as telas de cada um, a permissão de
cada tela e as rotas irmãs que a deixam acesa. `apps/core/navegacao.py` lê a mesma
ordem para as setas de "anterior" e "próxima" do pé da página, então menu e setas nunca
saem de sincronia. O desenho está em `templates/base.html` e no `.menu-principal` /
`.menu-apoio` do `static/css/sistema.css`, que não mudaram: as duas fileiras já
existiam, o que mudou foi o que entra em cada uma.

Tela que é recurso de outra (a comparação com o ano passado, dentro da Lista de compra;
o tempo, dentro da Visão geral) continua fora do menu, e acende o assunto de onde ela
abre — senão o topo apagaria justamente quando a pessoa foi mais fundo no assunto.

## Como conferir que continua valendo

`apps/core/tests/test_menu_e_inicio.py` trava: que são seis assuntos e nenhuma tela
aparece em dois; que a segunda fileira traz só o assunto aberto (na tela de compra não
se lê Auditoria nem Clientes); que clicar no assunto cai na tela que decide; que o
vendedor vê um assunto só; e que toda rota escrita no menu existe de verdade.
