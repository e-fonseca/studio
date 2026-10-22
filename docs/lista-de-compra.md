# A lista de compra e o "o que fazer agora"

Entraram na 1.17.0, a pedido do Edson: *"checar quantidade mínima e gerar um
relatório de compra, não deixar o produto acabar para comprar"* e *"a minha ideia
é que o sistema me diga o que eu tenho que fazer"*.

## A conta da lista de compra

Está em `apps/compras/lista_de_compra.py`, e a conta em si é a de
`apps/compras/calculos.py` — a mesma da tela "Antes de comprar". Não existem duas
contas de reposição no sistema; o que este arquivo faz é rodar aquela sobre a loja
inteira e agrupar o resultado por fornecedor.

Para cada produto:

```
venda por dia   = vendas de 12 meses / dias com a loja aberta
ponto de pedido = venda por dia x prazo do fornecedor + 7 dias de folga
                  (nunca abaixo do mínimo cadastrado no SET)
posição         = estoque (nunca abaixo de zero) + a caminho - reservas
comprar quando  posição <= ponto de pedido
quanto comprar  = venda por dia x (prazo + 7 dias até a próxima compra)
                  + folga - posição
```

Quatro pontos que não são óbvios:

- **Saldo negativo conta como zero.** São 1.023 produtos com saldo abaixo de zero no
  SET, e isso na prateleira não existe: saíram unidades que nunca foram registradas
  entrando. Explicação completa na seção do saldo negativo, mais abaixo.

- **O mínimo do SET (`PRODUTOS.QTDEMIN`) entra como piso do ponto de pedido.** A
  loja preencheu esse campo em 2.807 produtos e isso é a opinião de quem vende;
  o sistema não a contradiz para baixo.
- **O prazo vem, nesta ordem:** o informado pela gerência na ficha do fornecedor,
  o medido nas compras do SET, e por último um padrão de 15 dias. O padrão é
  chute honesto: a linha fica marcada como "prazo assumido" e vira tarefa de
  informar o prazo certo. Lembre que o SET grava a data da nota e não o prazo, por
  isso o medido quase sempre dá zero.
- **Produto que nunca vendeu e não tem mínimo cadastrado não entra.** Ele é
  assunto da tela de Sugestões ("parar de comprar", "pôr para girar"), não da
  lista de compra. Isso também é o que mantém a conta barata: dos 11.274 produtos,
  só alguns milhares são candidatos.

## Por que o corte é por fornecedor

A lista inteira dá R$ 95 mil na cópia de 20/09/2026, contra um teto de
R$ 59,8 mil por mês (eram R$ 185 mil até a 1.32.0, quando a conta ainda somava o
saldo negativo à compra — ver a seção do saldo negativo mais abaixo). Entregar duas mil linhas não é gerenciamento. Quem compra
não compra produto, compra de fornecedor: é uma ligação, um pedido, um frete.
Então o "comece por aqui" ordena os fornecedores pelo quanto a loja deixa de
vender por falta do que eles fornecem e enche o que ainda cabe no mês.

Dois cuidados na tela:

- **O contrapeso.** Cada fornecedor sugerido mostra quanto da mercadoria dele já
  está parada sem vender no ano. Sem isso o sistema mandaria comprar mais de quem
  a loja já comprou errado — que é exatamente o problema que ele existe para
  resolver.
- **Estar abaixo do teto não é motivo para comprar.** O teto é o que saiu da
  prateleira num mês médio, e a tela repete isso.

O saldo de estoque vem do SET e a loja nunca fez contagem física (1.456 produtos
com saldo negativo), então "faltando" é estimativa. A tela diz isso e aponta para
o inventário.

## A quantidade que a loja escolhe

Entrou na 1.28.0, a pedido do Edson: *"no recurso de sugestão de compra permitir
edição da quantidade, manter a sugestão, porém permitir editar a quantidade."*

Desde a 1.37.0 a linha mostra a conta inteira, a pedido dele em 20/10/2026:
*"no campo de quantidade sugerida, adicionar quantidade manual, com a soma dois
campos gera a quantidade total de cada produto por fornecedor"*.

```
sugerida 14  +  [ à mão 5 ]  =  total 19
```

Um campo editável só: o da mão. A sugestão não se edita porque não é dela que a
pessoa discorda — é do total —, e ela continua à vista porque é ela que explica
de onde veio o número. O total é o que vai no pedido, no PDF e no arquivo.

Está em `apps/compras/ajustes.py` e no modelo `AjusteDeCompra`. Quatro decisões que
valem registro:

- **O que fica guardado é a PARCELA da mão, não o total.** É a diferença que só
  aparece três horas depois. Quem acrescenta 5 unidades porque um cliente
  encomendou quer 5 a mais do que o sistema achar certo, e o sistema muda de ideia
  três vezes por dia, a cada sincronização. Com o total guardado, a conta andava de
  10 para 14 e o pedido continuava saindo com os 15 pensados para outra situação —
  número velho, calado, dentro de um papel que vai ao fornecedor. Com a parcela,
  vira 19 sozinho. `AjusteDeCompra.total_com(sugerida_de_hoje)` é essa conta; o
  campo `quantidade` guarda o total do momento, para a trilha.

- **O ajuste é preso ao código do produto, não à importação.** Se fosse uma chave
  estrangeira para a linha importada, a sincronização das 08:30 apagaria o que a
  loja digitou às 08:00 — o modelo de "cada importação é uma foto"
  ([sincronizacao-nao-soma.md](sincronizacao-nao-soma.md)) é justamente o que
  derruba qualquer dado nosso pendurado na foto. O número digitado é da loja e
  sobrevive a toda sincronização.
- **Parcela zero apaga o ajuste.** Senão o contador de "mudadas à mão" mentiria, e
  a tela diria que alguém decidiu onde ninguém decidiu nada. Parcela negativa é
  legítima e quer dizer comprar menos: quem conhece o produto às vezes sabe que a
  venda do ano passado não se repete. O total nunca desce abaixo de zero.
- **"Não comprar agora" é botão próprio**, não mais a parcela que zera. Até a
  1.36.0 era digitar 0 no total; com a soma isso deixou de funcionar, porque menos
  dez só zera enquanto a sugestão for dez. O campo `nao_comprar` tira o produto do
  pedido, deixa a linha na tela explicando o que o sistema pediu, e continua
  valendo depois da sincronização. A migração `0004` converteu sozinha o que já
  estava salvo: cada linha guardava a sugestão do seu momento, então a parcela sai
  por subtração, e total zero com sugestão positiva virou `nao_comprar`.

Quando a sugestão muda depois do ajuste (vendeu mais, chegou mercadoria), isso
deixou de ser alerta: o total acompanha a conta nova sozinho. `mudou_desde()`
continua existindo, e a linha diz de quanto era a sugestão na hora do ajuste — é
informação, não desconfiança do número escolhido.

### A quantidade sumia no celular (consertado na 1.30.0)

O campo existia desde a 1.28.0, mas quem abria a lista pelo telefone não o via. A
tabela tem sete colunas e rolava de lado (`min-width: 46rem`): num visor de 390 px
apareciam o nome do produto e um pedaço da situação, e a coluna "Comprar", que é a
razão desta tela, ficava a seis colunas de distância atrás de uma rolagem lateral que
ninguém descobre. O Edson perguntou onde a quantidade tinha ido parar, e tinha razão.

Desde a 1.30.0, no estreito (≤ 52rem) cada linha vira um **cartão**: o nome em cima, a
situação, "tem / a caminho / mínimo" numa linha só, o campo da quantidade com o botão
Salvar logo abaixo e o custo no fim. O cabeçalho da tabela some e o rótulo de cada
número vem do atributo `data-rotulo` da célula, escrito ao lado do valor. Vale para as
duas tabelas da tela, inclusive a dos outros fornecedores.

O conserto é de CSS, e CSS nenhum teste enxerga ([verificacao-geral.md](verificacao-geral.md));
o que os testes travam é o que o CSS precisa achar no HTML — a classe `tabela-de-compra`
e o `data-rotulo` de cada número (`apps/compras/tests/test_ajuste_e_pedido.py`).

## O mesmo período do ano passado dentro da sugestão (1.32.0)

Entrou a pedido do Edson em 14/10/2026: *"preciso saber a quantidade que o sistema
inteligente sugeriu para comprar, avaliando o período vigente do pedido atual com o mesmo
período do ano anterior"*.

A sugestão nascia de uma média plana: venda dos últimos doze meses dividida por dias. A
loja vende por estação, então a média plana manda comprar de menos antes de a estação
começar e de mais depois que ela passou.

A conta, em uma frase: **este pedido vai cobrir os próximos tantos dias; no ano passado,
esses mesmos dias do calendário venderam quantas vezes a média do produto?**

    fator = (unidades na mesma janela, um ano atrás) / dias da janela
            ------------------------------------------------------------
            (unidades nos doze meses anteriores àquela janela) / 365

A janela é a do pedido: prazo do fornecedor + 7 dias até a próxima compra + 7 de
segurança. Com prazo de 15 dias dá 29 dias; pedindo em 14/10/2026, o ano passado
consultado é 14/10/2025 a 11/11/2025. A venda vem somada por mês
(`VendaMensalDoProduto`), e mês que a janela pega pela metade entra pela metade, contado
em dias.

Os freios, porque fator errado vira pedido errado:

- **Menos de seis unidades no ano, sem fator.** Não é padrão, é acaso.
- **Menos de duas unidades esperadas na janela, sem fator.** Produto de doze unidades por
  ano vende zero na maioria das janelas de um mês, e esse zero é o tamanho da amostra, não
  a estação. Sem este freio, setecentos produtos de giro lento desciam para o piso de uma
  vez.
- **Diferença menor que um décimo, sem fator.** Mês de 30 contra mês de 31 não é estação.
- **O fator não passa de 2 nem fica abaixo de 0,5.** Sem o teto, uma semana boa do ano
  passado mandaria comprar quarenta vezes mais; sem o piso, um mês fraco zeraria a
  reposição de um produto que a loja vende o ano inteiro.
- **Mês pela metade na foto, sem fator** — o mesmo cuidado de
  [comparar-com-o-ano-passado.md](comparar-com-o-ano-passado.md).

O fator mexe **só no quanto comprar**. A cobertura em dias e o excesso continuam saindo da
média dos doze meses: dizer que um produto de verão está "em excesso" em julho porque a
demanda ajustada caiu seria trocar informação por palpite.

E o fator **só vale sobre base plana** (corrigido na 1.34.0). Olhe o denominador da conta:
a média do produto nos doze meses. O fator existe para consertar essa média plana, e nada
mais. Quando a pessoa escolhe 30, 90 ou 180 dias no filtro, a base já É a venda da estação
de agora — multiplicá-la pelo fator conta a estação duas vezes e, com o teto de 2, chega a
pedir o dobro ao fornecedor justamente no mês de pico. Então o fator entra só na janela de
doze meses e no produto que voltou para ela por não ter vendido nada na janela curta. A
tela diz isso embaixo do filtro, para a quantidade não mudar sem explicação.

Na tela, a linha mostra sempre **"sugestão do sistema: N"** — número solto dentro de um
campo não diz de quem é — e, quando o ano passado mexeu, **"no ano passado este período
vendeu 2x a média: de 36 para 43"**. O motivo guardado também conta.

Nos dados de 20/09/2026, 26 das 2.237 linhas mudam de quantidade por estação, metade para
cima e metade para baixo. É pouco de propósito: só produto com giro suficiente para a
janela ser amostra entra.

## Saldo negativo não é mercadoria a repor (1.33.0)

Entrou a pedido do Edson em 14/10/2026: *"a questão da sugestão inteligente ainda nao
ficou clara e nem ficou boa pra mim"*. Não estava só pouco clara: estava errada, em
R$ 89 mil.

No SET há **1.023 produtos com saldo abaixo de zero**, porque a loja nunca fez contagem
física. Saldo negativo quer dizer que saíram unidades que nunca foram registradas
entrando: o buraco é de **lançamento**, não de prateleira. Até a 1.32.0 a conta somava
esse buraco à compra, como se fossem unidades a repor — e as vendas que abriram o buraco
já estão em `vendas_12m`, ou seja, já estão dentro da demanda. O resultado era comprar a
mesma venda duas vezes.

Medido na cópia de 20/09/2026, a lista inteira caiu de **R$ 184.577 para R$ 95.459** com
o piso de zero. Os casos mais graves:

| Produto | Saldo | Vende por ano | Comprava | Compra |
|---|---|---|---|---|
| PRATO G MARAJOARA | -15 | 1 | 16 (16 anos de venda) | 1 |
| PONTAS DE CRISTAIS | -19 | 2 | 20 (10 anos) | 1 |
| BULE ESMALTADO | -16 | 2 | 17 (8,5 anos) | 1 |
| ARARA/TUCANO/PICAPAU M | -69 | 12 | 70 (5,8 anos) | 1 |
| PEDRA AMETISTA 95KG | -12 | 12 | 13 (R$ 6.500) | 1 (R$ 500) |

Dezesseis anos de venda numa compra só é exatamente o erro que a loja já comete sozinha —
R$ 227 mil parados que não venderam uma unidade no ano — e o sistema não pode ser quem o
sugere.

A mudança é de uma linha em `apps/compras/calculos.py`: a posição que decide a compra usa
`max(estoque, 0)`. **Cobertura em dias e valor de estoque já usavam esse piso**; a compra
era a única das três que não usava, e a única que vira pedido ao fornecedor.

O que NÃO muda:

- **A situação continua "Em falta".** Contar zero na compra não é dizer que tem.
- **A coluna TEM continua mostrando -69.** Esconder o número não conserta o cadastro.
- **A mercadoria a caminho continua descontando**: ela é real.

Na tela, a linha diz: *"Saldo de -69 é impossível na prateleira: a compra conta zero,
porque essas vendas já estão na média."* Sem essa frase, TEM -69 e COMPRAR 1 na mesma
linha não fecham, e o número perde a confiança de quem compra. E quem diz o número de
verdade continua sendo o [inventário](inventario.md).

## O que entrou, o que saiu, e onde o estoque foi parar (1.33.0)

Pedido do Edson: *"exiba uma sugestão de compra analisando o que foi comprado de um
determinado produto e o que foi vendido e o resultado que seria o estoque (...) levando em
consideração o que foi comprado na última compra e vendido"*. Está em
`apps/compras/movimento.py`, e são duas contas em cada linha da lista.

**Nos doze meses:** comprou X, vendeu Y, então o estoque andou X − Y. Os dois números já
vêm prontos na foto (`compras_12m`, `vendas_12m`), então esta parte não custa consulta
nenhuma. Dela sai também quanto o produto tinha um ano atrás — o estoque de hoje menos o
movimento —, que é o único jeito de ter saldo de partida sem inventário.

**Desde a última compra:** entraram N unidades no dia D, e desde D saíram M. Ancorada numa
data conhecida, ela não precisa de saldo inicial, e é a conta que o Edson descreveu. O que
ela **não** é: prova de divergência. Como o saldo anterior à compra é desconhecido, ela
fecha por construção — serve para enxergar o giro ("entraram 4 e já saíram 6"), não para
acusar perda.

Três escolhas que mudam o número:

- **Compra pendente não conta como compra feita**, aqui como em todo o resto do sistema:
  ela é mercadoria a caminho e já aparece na coluna A CAMINHO.
- **A data da compra é a da nota, e a do pedido quando não há nota** — a mesma regra que o
  importador usa para `compras_12m`. Outra data aqui faria dois números da mesma tela
  discordarem.
- **A venda desde a compra sai da venda MENSAL**, rateada por dias no mês em que a compra
  caiu, e arredondada à **unidade**: a loja vende vaso inteiro, e "vendeu 50,774" é
  precisão de mentira sobre um número que já é aproximado no mês da compra.

Duas consultas para a lista inteira, com os produtos entrando por subconsulta — nunca uma
lista de dez mil códigos dentro de um `IN`.

## A média de venda sai do período escolhido no filtro (1.33.0)

Pedido do Edson: *"faça analise do periodo definido no filtro e usar a media de vendas
nesse mesmo período e calcular a sugestao de compra"*. Está em `apps/compras/janela.py`,
e a tela ganhou o filtro **"Média de venda de"**: 12 meses (padrão), 6 meses, 3 meses,
30 dias.

```
venda por dia = unidades vendidas na janela / dias em que a loja ABRIU na janela
```

Dias de porta aberta, não dias de calendário: a Cabana não abre todo dia, e dividir por 30
um mês com 24 dias de loja aberta subestima a venda diária em 20%. É a mesma régua que a
janela de doze meses já usava (`Importacao.dias_abertos_12m`).

Doze meses continua sendo o padrão e continua saindo da foto **sem consulta nenhuma**:
quem não mexe no filtro não paga nada por este arquivo existir.

O freio: **produto que não vendeu nada na janela escolhida volta para os doze meses**, e a
linha dele diz isso. Sem esse freio, filtrar "3 meses" em junho zeraria a sugestão de todo
produto de dezembro e ele sumiria da lista de compra — que é exatamente o produto que some
da prateleira sem ninguém perceber.

A janela escolhida é dita **uma vez**, embaixo do filtro, com quantos dias de porta aberta
ela teve e quantas linhas voltaram para doze meses. Escrever "pela venda de 3 meses" em
duas mil linhas é ruído, e ruído em toda linha faz a linha que importa passar batida.

## Quanto tempo a quantidade dura, e quanto dinheiro ela prende (1.33.0)

Embaixo de cada quantidade: *"cobre 2 meses de venda e prende R$ 56,00"*. Fala da
quantidade **do pedido**, não da sugerida, então quem digita 70 no campo lê "cobre 5,8 anos
e prende R$ 1.960,00" e muda de ideia sozinho. Acima de **um ano** de venda a frase sai em
âmbar e em negrito.

Um ano não é regra contábil, é o calendário da loja: acima disso a mercadoria atravessa a
estação inteira e volta, e é dela que sai o estoque que não vende nenhuma unidade no ano.
A tela avisa; travar quem decide, não.

## O pedido ao fornecedor

Entrou na 1.28.0, a pedido do Edson: *"após análise da sugestão de compra
automático e/ou editável disponibilizar um botão para gerar o pedido para o
fornecedor(os) com layout da cabana do jacarandá e razão social da essenza,
endereço largo do jesuítas 64."*

Está em `apps/compras/pedido.py`, sobre o `apps/core/pdf.py` escrito à mão
(nenhuma biblioteca, [relatorio-em-pdf.md](relatorio-em-pdf.md)). O papel traz o
timbre da loja, o `Para: <fornecedor>`, os totais, a tabela com quantidade, custo
unitário e total, e as quantidades mudadas à mão em marrom — quem recebe o pedido
não precisa saber disso, mas quem assina antes de mandar precisa.

- **Só entra quantidade maior que zero.** Um pedido com linha zerada é um pedido
  que o fornecedor interpreta.
- **Um fornecedor por página** (`relatorio.pagina_nova()`), porque o pedido vai
  para destinatários diferentes: a folha tem que poder ser separada.
- **A razão social, o endereço e o CNPJ ficam em `DadosDaEmpresa`**, não no
  código, numa tela só de Administração (Dados da empresa). Timbre digitado no
  código envelhece sem avisar — a mesma razão da ficha técnica
  ([ficha-tecnica.md](ficha-tecnica.md)).
- **Dois endereços no timbre, desde a 1.35.0.** O da nota é o fiscal (R Claudionor
  Assis Dias, 171); a mercadoria chega no Largo dos Jesuítas, 64, que é onde a loja
  funciona. O pedido imprime `Entregar em: <endereço físico>` em marrom e em negrito
  **só quando ele é diferente do fiscal** — repetir o mesmo endereço duas vezes faz o
  fornecedor parar para comparar as duas linhas. A regra está em
  `DadosDaEmpresa.linha_da_entrega`, não no desenho do papel: quem decide se há duas
  linhas é o cadastro.
- **A view confere o filtro antes de gerar.** `lista_de_compra.montar` ignora em
  silêncio um fornecedor que não existe, e isso geraria um "pedido" com a loja
  inteira dentro; quando o fornecedor pedido não é o que a lista devolveu, a tela
  responde 404.
- **Desde a 1.31.0 o botão GRAVA o pedido** (virou formulário POST) e anexa ao
  pedido guardado a própria folha que foi para o fornecedor, para depois conferir a
  nota contra ela: [pedidos-ao-fornecedor.md](pedidos-ao-fornecedor.md). Reabrir o
  PDF pelo link (GET) só reimprime, e gerar duas vezes no mesmo dia com as mesmas
  linhas reaproveita o pedido em vez de duplicar. Por isso a linha da lista passou a
  carregar o **código de barras**: é a única ponte confiável até a linha da nota
  fiscal, onde o código do produto é o do fornecedor, não o da loja.

## Os cinco números da reposição, e o giro de 90 dias (1.36.0)

Do prompt dele de 20/10/2026. A seção 4 manda **diferenciar claramente** cinco números, e
a seção 6 pede a venda de 90 dias na tabela de sugestões.

O sistema já calculava os cinco desde a 1.4.0; a tela mostrava dois. Pior: a coluna
**"Mínimo"** é o mínimo cadastrado no SET, que é outra coisa — é a opinião de quem vende,
e entra na conta só como piso. Quem lia a tela procurando o ponto de reposição encontrava
um número que não era ele.

Agora cada linha escreve a conta, no tom suave e **depois** do motivo:

> estoque de segurança 0,02 · ponto de reposição 10 · disponível com o que está a caminho 0 · estoque-alvo 10

Serve para quem desconfia do número poder refazer a conta na calculadora sem abrir esta
documentação. A segurança sai da **mesma** demanda que decidiu a compra (a do pedido, com
o fator do ano passado dentro), senão a soma escrita na tela não fecharia com o ponto.

**Quando o estoque-alvo fica abaixo de uma unidade, a linha cala.** Um produto que vende
2 por ano tem estoque-alvo de 0,16, e a tela chegou a escrever "estoque de segurança
0,0392": número que não explica nada e faz a linha parecer defeito. Ali quem decide a
quantidade é o arredondamento para a unidade inteira, não a fórmula — e frase que não
muda o que a pessoa vai fazer é a informação a mais que ele pediu para tirar.

### A venda de 90 dias

O número vem do SET desde sempre (`ProdutoImportado.vendas_90d`) e não chegava a esta
tela. Entrou **comparado com o ritmo do ano**, porque sozinho ele não decide nada: 9
unidades em 90 dias é muito para um produto que vendeu 12 no ano e pouco para um que
vendeu 200.

- "1 em 90 dias, acima do ritmo do ano (0,25 seria o normal)" — está acelerando.
- "30 em 90 dias, abaixo do ritmo do ano (90 seria o normal)" — está parando.
- "Nada nos últimos 90 dias." — não saiu uma unidade no trimestre.

Diferença menor que um quinto não vira frase de alerta: é ruído de calendário, o mesmo
freio do fator do ano passado. E a frase vai na **linha de detalhe**, não em coluna nova:
a seção 6 pede treze informações por linha, e treze colunas no celular voltariam a
esconder o campo Comprar, que foi o defeito da 1.30.0.

## O alerta de 30% e o carro-chefe (1.40.0)

Pedido dele em 22/10/2026: alerta de 30% em cada produto, destacando o carro-chefe da
loja, e menos informação no caminho da decisão. A regra completa está no cabeçalho de
`apps/compras/politica.py`; os dois números moram em `PoliticaDeCompra`, um registro só.

- **O 100% é o estoque-alvo** da conta de reposição, não o maior estoque que o produto já
  teve (premiaria a compra exagerada) nem o mínimo do SET (vazio em quase todo o cadastro).
  Saldo negativo conta como zero, a mesma régua da compra.
- **Carro-chefe é faturamento de 12 meses**, os N primeiros (padrão 100), sem DIVERSOS e
  consumo próprio (`so_mercadoria`).
- **O alerta sozinho não decide nada nesta loja**: com o estoque nunca contado, 94% da
  lista está a 30% ou menos do ideal. Por isso a tela mostra o CRUZAMENTO no topo, e o
  alerta por produto aparece como "X% do ideal" só quando o produto ainda tem peça.
- Na tela o alerta se chama **estoque mínimo** desde a 1.40.1 (*"me refiro 30% estoque
  minimo"*), e é outro número que o mínimo do SET: o do SET continua escrito "Mínimo
  cadastrado no SET".
- O alerta não mexe na quantidade sugerida. Mudar a regra é permissão de gerência
  (`compras.ajustar_compra`), por POST, com auditoria `compras.politica_alterada` só
  quando algo mudou; número fora da faixa é trazido para dentro dela.

## A decisão vem antes da explicação (1.35.0)

O Edson disse em 19/10/2026: *"o sistema está trazendo muitas informações, deixando os
gestores confusos. precisamos que seja mais objetivos"*. O cartão "Como esta lista é
feita" abria a tela: antes de ver uma linha para comprar, quem entrava lia a conta do
teto, a regra do prazo, a do saldo negativo e o quadro do ano passado.

Ele agora é o **último bloco da página**, dentro de um `<details class="cartao
explicacao-da-lista">` que **nasce fechado**. A lista começa na primeira linha de
produto. Nada foi apagado: quem quer entender o número clica em "Como esta lista é
feita" e lê tudo o que lia antes, com o quadro do ano passado junto.

É a mesma regra do menu por assunto ([menu-por-assunto.md](menu-por-assunto.md)): o
número que decide a compra fica na frente, e a conta que o justifica fica a um clique.
Informação escondida não é informação perdida — informação empilhada na frente da
decisão é.

## Comparar com o ano passado, no meio da tela (1.29.0)

Era tela própria no menu. O Edson pediu em 14/10/2026 que virasse recurso daqui, e a
razão é boa: a estação só muda a decisão se estiver à vista na hora de fechar o
pedido. Olhar só os últimos doze meses esconde que o que sai em julho não é o que sai
em dezembro.

O quadro `#ano-passado` traz o período escolhido (3, 6 ou 12 meses fechados, ou os meses
escolhidos a dedo desde a 1.30.0) contra os mesmos meses do ano anterior, o mesmo
período ano a ano, os oito que mais subiram, os oito que mais caíram, e o botão para a
tabela produto a produto. Ele **herda o fornecedor filtrado na tela**, de modo que
filtrar um fornecedor compara esse fornecedor, e não a loja; o grupo de produto tem
filtro próprio dentro do quadro.

O detalhe inteiro, inclusive por que só mês fechado entra, está em
[comparar-com-o-ano-passado.md](comparar-com-o-ano-passado.md).

## O que fazer agora

Está em `apps/painel/tarefas.py` e aparece no alto da Visão geral. Cada tarefa:

1. Só existe se o número que a justifica for maior que zero.
2. Traz esse número na frase.
3. Termina num link para a tela onde uma pessoa decide.

A ordem é por urgência (`ruim`, `atencao`, `neutro`), não por assunto. O filtro por
permissão é aplicado depois do cálculo, em `tarefas.para`, para o resultado poder
ficar no cache uma vez por importação — é o mesmo cache do painel
(`apps.painel.servicos.agenda_da_importacao`), com a chave da importação, dos
prazos informados, do DIA e da versão do sistema.

Desde a 1.34.0 esse cache mora em arquivo (`dados\cache`) e não na memória do processo, e
é a importação que o preenche: a conta de dois segundos passou a ser paga pela tarefa
agendada em vez da primeira pessoa que abre o sistema. Ver `apps/painel/aquecer.py`.

Para acrescentar uma tarefa: escreva uma função `_alguma_coisa(...)` que acrescenta
`Tarefa(...)` à agenda quando o número existir, chame-a em `montar` e escreva o
teste em `apps/painel/tests/test_tarefas.py` provando que ela **não** aparece
quando o motivo não existe.
