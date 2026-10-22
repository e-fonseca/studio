# Comparar com o mesmo período do ano passado

Entrou na 1.28.0, a pedido do Edson: *"análise de sugestão de compra de mercadorias
precisa além dos últimos meses com filtros, também permitir comparar com o mesmo
período do ano anterior."*

Está em `apps/compras/comparacao.py`.

Na **1.29.0** ela mudou de lugar, a pedido dele: *"remover do menu COMPARAR COM O ANO
PASSADO, virar recurso dentro da sugestão de compra mercadoria."* Então:

- **O quadro mora na lista de compra** (`/sistema/compras/lista/`, âncora `#ano-passado`),
  que é a tela onde se decide o que comprar e de quem. Traz o resumo, quem subiu e
  quem caiu, e **herda o fornecedor filtrado na tela**: filtrando um fornecedor, a
  comparação passa a ser dele.
- **A tela `/sistema/compras/comparar/` saiu do menu** e continua inteira, com a tabela
  produto a produto, o filtro por grupo, a busca por nome e o arquivo para o Excel.
  Abre pelo botão "Abrir produto a produto", no fim do quadro.

O fornecedor que o quadro usa é o **pedido na tela**, e não o que a lista de compra
validou: a lista só conhece quem tem produto abaixo do ponto de pedido, e quem não tem
nada para comprar hoje cai fora dela. Comparando a loja inteira enquanto a tela diz
estar filtrada por um fornecedor, o número estaria certo no lugar errado.

Na **1.30.0** ela ganhou o que ele pediu em 14/10/2026: *"comparação, aumentar os
filtros, permitir edição por período e trazer outro comparativo de vendas do mesmo
período dos anos anteriores."*

- **Mais filtro no quadro da lista de compra:** além do período, o grupo de produto. O
  fornecedor continua vindo do filtro da própria tela.
- **Período escolhido a dedo:** dois campos, *De* e *Até*, com todo mês fechado que a
  foto guarda. São dois caminhos no mesmo formulário, cada um com o SEU botão —
  "Comparar" usa o período pronto do seletor, "Ver estes meses" usa os dois campos.
  Com um botão só o sistema teria que adivinhar em qual dos dois a pessoa mexeu, e
  adivinharia errado metade das vezes. Quando vale o período escolhido, o seletor passa
  a mostrar "Meses escolhidos", para a tela nunca dizer um período e mostrar outro.
- **O mesmo período, ano a ano:** uma linha por ano, do mais novo para o mais velho, com
  as unidades e a variação em relação ao ano de baixo. Serve para separar "caiu este
  ano" de "vem caindo há três anos". Ano mais antigo sem venda nenhuma não vira barra
  vazia, e o quadro só aparece com dois anos ou mais.

## Cinco anos, e por que o mês mais antigo não conta

A venda mês a mês vem na foto do SET (`VendaMensalDoProduto`). Até a 1.29.0 a leitura
pegava **730 dias** para trás, contados do dia do corte — e essa data cai no meio de um
mês. O mês mais antigo da foto era, portanto, meio mês, e a comparação de 12 meses o
usava como mês inteiro: comparava outubro cheio com meio outubro e acusava um
crescimento que não existe.

Desde a 1.30.0:

- a leitura começa **no dia 1º**, e são **61 meses** (`JANELA_COMPARACAO_MESES`), o que dá
  cinco janelas de 12 meses, uma por ano;
- a foto **grava onde o histórico começa** (`Importacao.mes_a_mes_desde`), então quem lê
  não precisa adivinhar;
- numa foto antiga, sem esse campo, o mês mais antigo é desprezado, porque lá ele é o
  pedaço de mês;
- período cujo ano anterior não cabe inteiro na foto **não é comparado**: a tela diz
  quantos meses ela guarda e quantos aquele período pede, e manda escolher um período
  mais curto. Número errado é pior que número nenhum numa tela que informa compra.

Os cinco anos custam ~56 mil linhas por foto (contra ~27 mil de dois anos) e cerca de
dois segundos a mais na sincronização.

## O que a tela responde

Para cada produto, quanto saiu nos últimos 3, 6 ou 12 meses **fechados** (ou nos meses escolhidos a dedo) e quanto
saiu nos mesmos meses do ano anterior, com a variação em unidades e em reais. Com
filtro por fornecedor, por grupo e por nome — e o nome usa a mesma busca sem acento
de todas as telas (`apps/core/procura.py`).

Serve para a pergunta que a lista de compra não responde: aquele produto está
vendendo menos porque o ano está fraco, ou porque sempre vende menos neste mês?

## A armadilha dos meses abertos, e como ela é evitada

O corte da última sincronização cai no meio de um mês. Comparar "setembro parcial"
com "setembro inteiro do ano passado" devolveria uma queda de 84% que não existe —
e numa tela que informa compra, isso faria a loja deixar de comprar o que vende.

Então `_mes_fechado(corte)` descarta o mês do corte e a janela começa no último mês
**completo**. A tela escreve qual mês ficou de fora, com o nome dele, para ninguém
procurar o número que falta.

## De onde vem o número

De uma tabela nova, `VendaMensalDoProduto`, gravada pela própria sincronização:
produto, ano, mês, unidades e receita. A consulta no Firebird agrupa por
`extract(year ...)` e `extract(month ...)` sobre `IVENDAS` + `VENDAS` e vai até
**61 meses** (`JANELA_COMPARACAO_MESES`, era 730 dias até a 1.29.0), a partir do dia 1º
daquele mês: comparar 12 meses com os 12 anteriores exige dois anos de histórico, e
comparar cinco anos exige cinco.

Isso muda uma coisa importante na sincronização: a janela de leitura das vendas
por produto passou a ser de cinco anos, não de um. É leitura da cópia do backup,
como todo o resto ([leitura-firebird.md](leitura-firebird.md)), e não encosta no
banco em uso pelo SET.

A tabela entrou na lista de `fotos_fora_do_limite` da higienização
([higienizacao.md](higienizacao.md)) **na mesma versão em que nasceu**: é uma
linha por produto por mês por sincronização, três vezes ao dia. Sem isso, cresceria
para sempre — foi exatamente o esquecimento que a 1.26.0 teve que corrigir no
caixa.

## A tela até a primeira sincronização

A tabela é preenchida pela sincronização, então até a loja sincronizar depois de
instalar esta versão a tela mostra "ainda não há o ano passado para comparar". Não
é erro: é a tela dizendo que o dado ainda não existe, em vez de mostrar zeros que
alguém leria como queda.

## Decisões menores que valem registro

- **Produto novo e produto que sumiu aparecem marcados**, não como "+100%" ou
  "-100%". `LinhaComparada.novo` e `.sumiu` existem porque a conta de variação não
  tem sentido quando um dos lados é zero.
- **Só mercadoria entra**, pelo mesmo `so_mercadoria(...)` da lista de compra:
  serviço, taxa e frete não se comparam a prateleira.
- **As larguras das barras são inteiras.** Decimal dentro de `style=` sai
  localizado com vírgula e o navegador descarta a linha — a armadilha já custou
  uma tela no projeto.
