# Dashboard (1.18.0, redesenhos da 1.20.1, da 1.20.2 e da 1.41.0; primeira tela na 1.43.0)

Tela em `/sistema/painel/dashboard/`, código em `apps/painel/dashboard.py`.

**Desde a 1.43.0 é a tela que abre ao entrar**, a primeira entrada do menu de cima, com a
Visão geral ao lado (pedido de 31/10/2026: *"logo quando fazer login quero que abra o
Dashboard, causa bom impacto com as informações visíveis"*). Por isso o período padrão
(12 meses, sem filtro) fica guardado como a Visão geral: a importação e a tarefa de hora em
hora deixam a conta pronta (`servicos.dashboard_da_importacao`, chamada de
`aquecer.py`), e a tela guardada abre com 36 consultas, contra 90 sem guardar. Com filtro
de grupo, de fornecedor ou outro período, a conta é feita na hora, como sempre foi. O
escuro dele virou o de todas as telas (`docs/tela-escura.md`).

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

## O jeito do Grafana (1.41.0)

Em 31/10/2026 o Edson mandou o print de um painel do Grafana (um "Datacenter, visão
geral") com o pedido: *"adaptar os recursos de grafana no dashbord / a visualização fica
bem bonita e facil de entender"*. O que veio do modelo foi o **desenho**; as contas são
as mesmas de antes e nenhum número da tela mudou.

**Por que não instalar o Grafana de verdade.** Seria um serviço novo no servidor da
loja, com login e permissões à parte (e o vendedor não pode ver dinheiro: a regra
moraria em dois lugares), as contas reescritas em SQL — e regra repetida é regra que
diverge, como o "parado" já mostrou — e um programa a mais para atualizar. O desenho cabe
no próprio sistema, na mesma tela, no mesmo endereço e no mesmo menu.

O que a tela ganhou, quadro a quadro:

| Do modelo | Na Cabana |
| --- | --- |
| Fileira de números com minigráfico | Situação da loja, Faturamento, Vendas, Ticket médio, Desconto dado e Cobertura do estoque. O número sai na cor da situação (verde bom, laranja atenção, vermelho ruim, azul neutro) e o minigráfico embaixo é o período dia a dia, ou semana a semana acima de 31 dias |
| "Status geral" | **Situação da loja**: a palavra do item mais grave de "O que fazer agora" (Urgente, Atenção ou Tudo em dia), com a contagem embaixo. Não é regra nova: é a mesma agenda da Visão geral, filtrada pela permissão de quem olha |
| Série temporal | **Faturamento mês a mês** em linha: verde este ano, laranja o mesmo mês do ano passado, o mês que ainda corre num trecho tracejado |
| Mostrador "Disponibilidade" | **Margem bruta** em meia-volta |
| Roscas de status | **Produtos que venderam no ano** (com e sem saldo no SET), **Estoque ao custo** (vendeu no ano e parado), **Forma de pagamento** e **De onde vem o faturamento** (grupos) |
| CPU, memória, disco, rede | **Dia da semana** e **Hora do dia** em colunas |
| "Problemas recentes" | **O que fazer agora**, com a gravidade escrita num selo (Urgente, Atenção, Para fazer) e o link que resolve |
| "Top 5" | Curva ABC e campeões de faturamento e de margem em barras deitadas |

Ficou de fora o **mapa** do modelo (não há equivalente numa loja só) e a **atualização a
cada 10 segundos** (os dados mudam três vezes por dia, na importação).

**As explicações foram para o "i".** Cada quadro tem um "i" no canto, como no Grafana, e
o texto que antes ficava em cima de cada bloco está inteiro lá dentro. Recolher não é
apagar (lição da 1.35.0). O valor exato de cada mês, que as barras de antes escreviam em
cima de cada coluna, está em **"Ver o valor de cada mês"**, embaixo da linha: a linha só
mostra o valor com o mouse em cima, e o celular não tem mouse.

### Onde mora cada desenho

- `Faisca`, `GraficoDeLinha`, `Rosca`/`_fatiar` e o mostrador (`margem_traco`) são feitos
  em `dashboard.py`, não no template, porque coordenada com vírgula não desenha nada e o
  Django escreve número com vírgula. Toda coordenada passa por `_coordenada` (ponto, uma
  casa).
- O minigráfico vai do menor ao maior valor **da própria série**: mostra a forma do
  período, não a escala. O número que vale é o de cima. Dia sem venda repete o ticket do
  dia anterior, em vez de desenhar uma queda de ticket que não aconteceu.
- `_serie` conta as semanas para trás a partir do corte: a última é sempre inteira, e o
  pedaço de semana que sobra no começo do ano fica fora do desenho.
- O eixo da linha termina num número redondo (`_escala`) e escreve "R$ 100 mil" e
  "R$ 1,5 mi" (`_reais_curto`). Os rótulos são texto da página, ao lado do desenho, e não
  texto dentro do SVG: o SVG é esticado (`preserveAspectRatio="none"`) e texto esticado
  sai torto. Pelo mesmo motivo as linhas usam `vector-effect: non-scaling-stroke`.
- **As faixas do eixo vertical (1.45.0)**: pedido dele em 02/11/2026, *"inserir na vertical
  mais faixas de valores 10.000 50.000 80.000 120.000 150.000 250.000"*. `_marcas` junta as
  faixas de `FAIXAS_DO_FATURAMENTO` (só as abaixo do topo da escala) às marcas redondas do
  passo. Quando dois rótulos ficariam um em cima do outro, ganha a faixa pedida, depois a
  redonda, por último o zero (o pé do gráfico já é o zero); o outro fica escrito só no gráfico
  alto (`monitor-eixo-so-no-alto`, escondido por `@container eixo-do-tempo (max-height: 25rem)`)
  ou fica só a linha. Num ano de R$ 300 mil no mês, o computador e o celular escrevem as nove:
  10, 50, 80, 100, 120, 150, 200, 250 e 300 mil.
- O tamanho do número grande é a largura do quadro dividida pelas letras dele:
  `Kpi.texto` escreve o número, `Kpi.letras` conta, e o CSS faz
  `calc(155cqi / var(--letras))`. "R$ 1.538.337,98" saía cortado no tamanho de "16.361".
- A forma de pagamento usa `nome_da_forma` de `apps/caixa/dinheiro.py`, a mesma do e-mail
  do caixa: "Cartão de crédito" e "Dinheiro", e AVISTA e DINHEIRO somam numa fatia só.
- A cor de fundo e as cores de situação (`--mon-*`) valem só dentro de
  `body.corpo-monitor`, ligado pelo bloco `classe_corpo` do template. As cores de fatia
  (`--cor-fatia-*`) são trocadas ali dentro por cores que aparecem no fundo escuro.


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

Desde a 1.41.0 é uma linha, e não mais duas barras por mês (ver "O jeito do Grafana"
acima). A regra do mês que corre não mudou: na linha ele é o trecho tracejado, e na
tabela "Ver o valor de cada mês" ele diz "até dia N". O que está abaixo sobre barras e
colunas é a história da 1.20.x, que explica por que a escala é o maior dos dois anos.

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

- **1.41.0, quatro defeitos que só o print pegou.** `.corpo-monitor a` pintou de azul o
  menu de cima, que é de todas as telas: a cor de link vale só em `.monitor a`. O
  `overflow: hidden` do quadro do número (para o minigráfico encostar nas bordas)
  cortava o texto do "i" no meio; o quadro com o "i" aberto sobe na frente dos vizinhos
  (`:has(.monitor-info[open])`). A legenda da rosca cortava o nome ("C", "Vende...") para
  caber o valor: agora o valor desce para a linha de baixo. E na Hora do dia o rótulo de
  duas linhas ("Fim do dia / 17h em diante") encurtava só a barra dele, tirando-a da
  linha de base das outras: a grade das colunas usa `subgrid`, e as três faixas
  (porcentagem, barra, nome) têm a mesma altura em todas as colunas.
- No celular, o campo do fornecedor ficava da largura do nome mais comprido e a seta saía
  da tela: `select` dentro de flex precisa de `min-width: 0`.

## Para acrescentar um número

Um `Kpi` novo entra na lista de `_kpis_da_venda` ou de `_kpis_do_estoque`, com `formato`
("reais", "porcento", "meses" ou "numero"), a `explicacao` em linguagem de loja e
`subir_e_bom=False` quando subir é piora. `Kpi.texto` escreve o número no formato (desde a
1.41.0 é ele, e não mais um template de `if`s, porque o tamanho da letra depende de
quantas letras o número tem). Número sem comparação que tem um limite escrito na
explicação leva `atencao_acima_de`, e passa a laranja acima dele, como a cobertura acima
de 3 meses. Na fileira de cima do Dashboard entram os quatro da venda e a cobertura; os
outros números do estoque são desenhados (mostrador e roscas), e um número novo do
estoque pede quadro próprio no template.

## Os mesmos desenhos em Contas a pagar (1.47.0)

Pedido dele (04/11/2026, com o print do Dashboard): *"usar esse formato de gráfico também em
contas a pagar"*. O gráfico de linha saiu do `dashboard.html` para
`templates/painel/_monitor_linha.html` (parâmetros `g`, `meses` e `o_que`), e o Dashboard o
inclui como antes: o HTML que ele gera é o mesmo, conferido linha a linha. Contas a pagar
inclui o mesmo arquivo e a mesma rosca (`_monitor_rosca.html`), dentro de
`<div class="monitor monitor-embutido">`, que traz as cores do Dashboard (`--mon-*`) para
dentro da tela escura comum. As contas estão em `apps/financeiro/quadros.py`:

- **Contas pagas mês a mês**: na 1.47.0, 13 meses com o mesmo mês do ano passado; desde a
  1.48.0, os últimos três anos de janeiro a dezembro (ver abaixo). Pagar mais é vermelho
  (`Mes.mais_e_bom`, `True` no faturamento, é `False` aqui; o gráfico de anos tem a mesma
  regra em `quadros.Coluna.sentido`). O mês que corre se compara com o mesmo pedaço do ano
  passado, do dia 1º ao dia do corte.
- **O que está em aberto**: as fatias dos filtros da lista (atrasadas, vencem em até 7 dias,
  depois, sem data), e o nome de cada fatia abre a lista dela (`Fatia.endereco`, novo).
- **Para onde vai o dinheiro**: o pago em 12 meses pela classificação do SET, a conta da tela
  Despesas; os oito maiores e o resto junto, sem o número do plano de contas no nome.

O ano passado só se compara quando o mês dele está inteiro na foto. Até a 1.46.0 a leitura do
pago começava em "corte menos 730 dias", no meio de um mês, e o primeiro mês do gráfico
compararia um mês cheio com dez dias. Na 1.47.0 a importação passou a ler o pago e o recebido
desde o dia 1º de 24 meses antes e a gravar a data (`financeiro_desde` no detalhe da
importação); foto mais antiga vale a regra antiga.

## Três anos em Contas pagas mês a mês (1.48.0)

Pedido dele (04/11/2026, com o print do gráfico da 1.47.0): *"gráfico ficou bom / nesse mesmo
gráfico do contas a pagar manter sempre os últimos 3 anos letivos"*. Ficou o mesmo quadro,
com o mês fixo embaixo (janeiro a dezembro) e uma linha para cada ano: o do corte em verde,
com a área e o mês que corre tracejado, o ano passado em laranja e o retrasado em azul. Com o
mês fixo, o mês que costuma pesar aparece nos três anos, um sobre o outro, e os meses que
ainda faltam neste ano mostram o que a loja pagou neles antes. A escolha foi para ele num
cartão, com as outras duas formas (36 meses seguidos; os 13 meses de antes com uma terceira
linha); a de janeiro a dezembro foi a recomendada.

- **Desenho**: `dashboard.GraficoDeAnos` e `dashboard.LinhaDoAno`, em
  `templates/painel/_monitor_anos.html`, com as classes da linha do tempo do Dashboard. O
  Dashboard continua com `_monitor_linha.html` e os 13 meses, sem mudança nenhuma. Mês sem
  vizinho com número vira ponto (`.monitor-tempo-ponto`): corte em 10 de janeiro, o ano de
  agora é só o pedaço de janeiro, e uma linha de um ponto não aparece.
- **Contas**: `quadros.pagas_por_ano`. A porcentagem embaixo do mês é o ano do corte contra
  o ano passado; a tabela "Ver o valor de cada mês" tem os três anos e uma última linha com
  cada ano de 1º de janeiro até o dia do corte. No celular a tabela mostra reais redondos
  (`reais_redondo`): com R$ e centavos a variação, a coluna que decide, saía da tela.
- **Leitura**: o pago entra com 36 meses inteiros (`firebird.inicio_das_pagas`), que cobrem o
  janeiro do retrasado em qualquer mês; o recebido fica em 24 (`inicio_das_recebidas`),
  porque é ele que traz o nome do cliente. A importação grava as duas datas
  (`pagas_desde` e `recebidas_desde`). Até a primeira importação depois de atualizar, o
  retrasado aparece só a partir do mês em que a foto antiga começa.
- **O começo do SET**: no backup de 20/09/2026 a primeira conta paga é de 27/02/2024 (o
  primeiro caixa é do mesmo dia). Mês de antes não é mês sem pagamento, é mês que o SET não
  tem: fica em branco, nunca em zero, e o desenho começa no primeiro mês inteiro depois da
  primeira conta (`quadros._comeco_do_lancado`). A tabela diz isso numa linha. Março e abril
  de 2024 aparecem baixos (R$ 12,7 mil e R$ 72,9 mil) porque é o que o SET tem lançado.
