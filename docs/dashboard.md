# Dashboard (1.18.0, redesenhos da 1.20.1 e da 1.20.2)

Tela em `/sistema/painel/dashboard/`, código em `apps/painel/dashboard.py`.

## Por que ela existe

O Edson pediu, em 07/10/2026, "um menu chamado dashboard com gráficos e estatísticas
e filtros, aplicar modelos de dashboard mais usados mercado de varejo". O que o varejo
olha é sempre o mesmo conjunto, e é esse conjunto que está aqui — não gráfico por
gráfico bonito, mas os números que mudam uma decisão de compra.

## As duas restrições do dado, que mandam no desenho

1. **O SET não traz o item da venda.** A tabela `VENDAS` tem a venda inteira; não há
   `IVENDAS` utilizável. Então filtrar por grupo ou por fornecedor **não pode** mexer em
   faturamento, ticket, dia da semana, forma de pagamento ou hora. Esses blocos são
   sempre a loja toda, e a tela escreve isso em cima deles. Há teste que falha se alguém
   fizer o filtro de grupo mexer no faturamento.
2. **Venda por produto é de 12 meses.** `ProdutoImportado.receita_12m` e `vendas_12m` são
   calculados na importação, sobre uma janela fixa. Por isso os blocos de produto (curva
   ABC, grupos, campeões, margem, cobertura, ruptura) não acompanham o filtro de período.

## O que cada número é

| Número | Conta |
| --- | --- |
| Faturamento | soma de `VendaImportada.valor` no período |
| Vendas | quantas vendas, não quantas peças |
| Ticket médio | faturamento ÷ vendas |
| Desconto dado | soma dos descontos ÷ faturamento |
| Margem bruta | (receita 12m − vendas 12m × custo) ÷ receita 12m |
| Cobertura | estoque ao custo ÷ (custo do vendido em 12m ÷ 12) |
| Ruptura | produtos que venderam em 12m e estão com estoque ≤ 0, sobre os que venderam |
| Parado | estoque ao custo das mercadorias sem nenhuma venda em 12m |

Os quatro primeiros comparam com o período anterior de igual tamanho; os quatro últimos
não têm com que comparar, porque a importação só guarda a janela de 12 meses.

Dois números invertem o verde e o vermelho (`subir_e_bom=False`): desconto, ruptura e
parado subindo é piora.

### Saldo negativo e consumo próprio (correções da 1.20.2)

Duas contas de estoque estavam erradas e a verificação geral pegou as duas.

**Saldo negativo contava como dinheiro a menos.** A loja nunca fez contagem física e
1.456 produtos estão com saldo negativo no SET. `Sum(F("estoque") * F("custo"))` somava
esses negativos, e cada um descontava do valor do estoque um dinheiro que não existe:
saldo negativo não é prateleira devendo mercadoria, é erro de cadastro. Agora as duas
telas que somam estoque (`dashboard.py` e `visao_geral.py`) tratam saldo negativo como
zero — `filter=Q(estoque__gt=0)` no Dashboard, `max(estoque, 0)` na Visão geral — e dizem
no pé do cartão quantos produtos estão nessa situação. **O estoque subiu de R$ 615.032,91
para R$ 741.845,19** e a cobertura de 10,3 para 12,4 meses, que é o número certo e o
mesmo que o diagnóstico em planilha dava.

**"Parado sem vender" misturava consumo próprio.** O Dashboard somava todo produto sem
venda, inclusive DIVERSOS e CONSUMO PROPRIO, que não são mercadoria de revenda — e por
isso "O que fazer agora" e o Dashboard mostravam valores diferentes para a mesma coisa.
O filtro `so_mercadoria` de `apps/compras/sugestoes.py` (era `_mercadoria`, privado)
passou a valer nas duas telas. **Parado foi de R$ 194.473,44 para R$ 227.005,64**, agora
igual ao da tela de tarefas.

## Curva ABC (desenho refeito na 1.20.2)

A, B e C são os cortes de sempre: 80%, 95% e 100% do faturamento acumulado, com uma
diferença desde a 1.20.1 — **o produto que cruza a linha dos 80% fica em A**, que é a
convenção do varejo. Pela regra antiga, uma loja cujo maior produto passasse dos 80%
sozinho mostraria a classe A vazia na tela. Na Cabana isso muda um produto: 1.489 em A,
31,1% do cadastro que vendeu, fazendo 80,0% do faturamento.

O desenho mudou duas vezes em 08/10/2026, as duas porque o Edson não entendeu a tela.
Era a curva de Pareto, uma linha subindo num quadro sem números: diz tudo para quem já
sabe o que é curva ABC e nada para quem não sabe. Virou duas faixas repartidas em A, B e
C, uma do cadastro e uma do dinheiro — e ele respondeu "confuso e difícil entendimento".

O terceiro desenho não inventa nada: é **a mesma lista de barras horizontais** das outras
caixas da tela, dia da semana e forma de pagamento, das quais ele nunca reclamou. Uma
linha por classe, e cada linha traz o nome da classe em palavras ("A — sustentam a
loja"), quantos produtos são, que fatia do cadastro e do faturamento eles fazem, o que
fazer com eles e o valor em reais na ponta. Sem desenho novo, sem legenda para decorar e
sem texto dentro de barra — era daí que vinham os dois problemas anteriores, porque CSS
não sabe medir texto e o número não cabia na faixa de 310px do celular.

O que ficou de código: `ClasseAbc` guarda `letra`, `produtos`, `receita`,
`fatia_dos_produtos`, `fatia_da_receita`, `titulo`, `explicacao` e `largura_receita` — um
inteiro de 0 a 100, porque Decimal dentro de `style=` sai localizado ("66,5%") e o CSS
ignora. O mínimo de 1 que o `_largura` devolve deixa visível a barra da classe pequena.
A frase acima da lista continua sendo a história que ele conta para o sogro: **1.489
produtos (31,1% dos que venderam no ano) fazem 80,0% do faturamento**.

## Mês a mês

Vem de `importacao.detalhe["vendas_mes"]`, e não da tabela de vendas, porque o detalhe
guarda 25 meses e a tabela 12 — sem os 25 não daria para comparar com o mesmo mês do ano
passado, que é a comparação que o varejo usa. A tela mostra 13 meses: um ano fechado mais
o mês corrente, que é o que cabe na largura do celular.

### O mês que ainda está correndo (1.20.1)

Os dados vão até o dia do backup, então o último mês do gráfico quase nunca está fechado.
Comparar sete dias de outubro com outubro inteiro do ano passado dava **-84%**, uma queda
que não existe — foi o que o Edson viu em 08/10/2026 e chamou de gráfico bugado.

A importação passou a trazer `detalhe["mes_parcial"] = [ano, mês, dia, valor]`, onde o
valor é quanto o **mesmo mês do ano passado** tinha vendido **até o mesmo dia**. É com
esse pedaço que a comparação é feita. Importação anterior à 1.20.1 não tem esse número:
aí o mês aparece sem comparação nenhuma, que é melhor do que uma errada.

Na tela o mês aberto é listrado e leva um "até dia N" embaixo do rótulo. Esse rótulo é
reservado em **todas** as colunas, mesmo vazio: as colunas são alinhadas por baixo, e uma
linha a mais só na coluna do mês parcial levantava o trilho dela 14px, tirando a barra da
linha de base das outras. No celular a coluna tem 2,6rem e o texto ocupa duas linhas, daí
o `min-height` dobrado na faixa de até 40rem.

### O gráfico truncado, e por que ele era truncado (1.20.2)

Depois da 1.20.1 o Edson mandou outro print: "o gráfico continua truncado". Estava certo,
e o motivo é de escala, não de CSS. Medindo o print dele, **nenhuma barra chegava ao topo
do trilho**: a maior, jul/26, parava em 74,3% da altura. A escala era o maior número do
gráfico **incluindo o do ano passado**, e o do ano passado era desenhado só como um risco
tracejado atravessando a coluna. O maior valor do gráfico era mai/25, um mês do ano
passado; a barra mais alta deste ano valia três quartos dele, e o gráfico parecia cortado
porque a altura que faltava pertencia a um número que não era barra nenhuma.

Duas saídas havia: tirar o ano passado da escala, ou dar barra a ele. Tirar da escala
mentiria no risco tracejado (ele sairia acima do trilho). Então agora **cada mês tem duas
barras, lado a lado, na mesma escala**: a cheia é este ano, a clara é o mesmo mês do ano
passado, com legenda em palavras em cima do gráfico. Alguma delas sempre encosta no topo,
porque a escala é o maior dos dois conjuntos. Mês sem número do ano passado mostra um
traço fino no lugar da segunda barra, com o motivo no `title`.

Conferido no navegador, com as alturas medidas em pixel: trilho de 144px, maior barra
deste ano 107px (jul/26), maior do ano passado 144px (mai/26, encostando no topo), e as
26 barras na mesma linha de base. O que torna isso frágil é só uma coisa: duas barras
dentro do mesmo trilho precisam de `gap` e `padding` no `.coluna-trilho`, senão no celular
elas se colam e parecem uma barra larga só.

## Armadilhas que já morderam

- `values_list("grupo", flat=True).distinct()` devolvia os 11.274 produtos, e não os 37
  grupos: o modelo ordena por código e, com a ordenação de pé, o `DISTINCT` passa a ser
  por (grupo, código). Daí o `.order_by()` vazio antes do `distinct()`.
- A hora vem como texto do SET e pode vir estragada; `_recortes_da_venda` ignora o que
  não converte para número em vez de derrubar o gráfico.
- Cor de gráfico tem token próprio (`--cor-fatia-1` a `--cor-fatia-9`). Reaproveitar
  `--cor-sucesso` numa participação por grupo faria o leitor achar que a fatia verde é a
  boa.
- Uma caixa que soma dinheiro de estoque e outra que soma a mesma coisa numa tela
  diferente têm que usar a **mesma função de filtro**, não duas cópias da mesma regra:
  foi assim que o "parado" do Dashboard e o de "O que fazer agora" passaram meses
  discordando. Regra de negócio repetida é regra que vai divergir.
- A coluna do gráfico se chamava `.coluna`, o mesmo nome da coluna do quadro de processos,
  que tem fundo cinza e recheio de cartão. As duas regras valiam juntas: cada mês virava
  uma caixa cinza do tamanho do trilho e a barra parecia solta no meio do nada. Era o
  "gráfico bugado" do print de 08/10/2026 — a barra e o risco sempre estiveram no lugar
  certo, conferidos em pixel. Hoje a coluna do gráfico é `.coluna-mes`. Classe nova pede
  nome próprio: o arquivo é um só e quem repete nome herda estilo sem pedir.

## Para acrescentar um número

Um `Kpi` novo entra na lista de `_kpis_da_venda` ou de `_kpis_do_estoque`, com `formato`
("reais", "porcento", "meses" ou "numero"), a `explicacao` em linguagem de loja e
`subir_e_bom=False` quando subir é piora. O template não precisa mudar: ele percorre a
lista e `templates/painel/_valor_kpi.html` resolve o formato.
