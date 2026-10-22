# Inventário: contar, classificar e acertar o SET

O que esta ficha cobre: o padrão de contagem que o varejo usa e que entrou na 1.39.0, a
classificação do que se acha na prateleira e os quatro relatórios que saem daí. A tela da
câmera e o leitor de código de barras têm ficha própria em `docs/https-e-camera.md`.

Pedido do Edson, 22/10/2026:

> controle inventario padrão aplicado no mercado varejo produtos de artesanatos, utilizar
> as melhores praticas, estipular prazos de tempos em tempos realizar o inventario.
> Precisamos organizar os produtos sem etiqueta, danificados, produtos muito tempo
> parados. Fazer relatório comparando o que o set sistema apresenta e o que o nosso
> sistema fez de leitura do inventario (...) planejar relatório de descartes de produtos
> sem aproveitamento, planejar relatório de produtos para conserto/reparo, realizar
> classificação desses produtos.

## O ponto de partida: a loja nunca contou

Na cópia de 20/09/2026 havia **1.456 produtos com saldo negativo** no SET, o que só
acontece quando se vende o que o sistema acha que não existe. São **5.617 produtos com
peça na prateleira**, R$ 741 mil ao custo, e nenhum deles jamais passou por uma contagem.
Enquanto isso não mudar, todo saldo do sistema é estimativa — e é por isso que a tela diz
isso em vez de fingir precisão.

## Contagem cíclica, que é o padrão do varejo

Parar a loja para contar doze mil produtos é o que ninguém faz duas vezes: leva dias, erra
no fim do segundo dia e só acontece uma vez por ano, quando acontece. O padrão é contar um
pedaço por vez, sempre, e escolher o pedaço pela **curva ABC**:

| Classe | O que é | Contar a cada |
|---|---|---|
| A | os primeiros 80% do faturamento | 30 dias |
| B | dos 80% aos 95% | 90 dias |
| C | os últimos 5% | 180 dias |
| sem venda | nenhuma unidade em 12 meses | 180 dias |

E, por cima, a **contagem geral uma vez por ano** (365 dias), que é a que fecha o ano para
a contabilidade.

Numa loja de artesanato a classe A é pequena e muito valiosa: peça de vime, cerâmica e
tecido sai de lugar, vai para a vitrine, volta arranhada e é vendida sem baixa. É aí que o
saldo descola, e é por isso que ela é contada todo mês e não uma vez por ano. "Sem venda"
fica com o prazo de C, e não com um prazo maior, de propósito: é a prateleira que ninguém
mexe, e prateleira que ninguém mexe é onde a falta demora mais a aparecer.

**Produto com saldo zero no SET não entra no plano.** Contar o que está zerado não acha
divergência nenhuma e afogaria a lista.

**A curva sai de TODOS os produtos da foto, não só dos que têm peça na prateleira.** É a
mesma população do painel, e tem de ser: calcular a curva só entre os que têm estoque
faria o mesmo produto ser classe A no inventário e B no painel. A regra mora num lugar só,
`apps/core/curva_abc.py`, e um teste compara as duas telas (`test_o_painel_e_o_plano_classificam_igual`).

**"Quando foi contado" é a última contagem FECHADA** em que o código apareceu. Contagem
aberta não conta porque ainda não é resultado — a pessoa está no meio dela.

### Como isso aparece na tela

A tela **Inventário** abre com o plano: uma linha por classe, com o prazo, quantos
produtos, quantos estão em dia e quantos esperam contagem, com o valor ao custo do que
está vencido. Dois botões fecham o cartão:

- **Abrir a contagem sugerida** — abre uma contagem já nomeada ("Contagem cíclica da
  classe A · 22/10"), para não ter o que digitar antes de começar;
- **Folha de contagem**, em PDF ou planilha — os 50 produtos da frente, classe mais
  urgente primeiro e, dentro dela, o maior dinheiro na prateleira. É com ela que se anda
  pela loja.

## A classificação do que se acha na prateleira

Contar responde *quantos*. A prateleira também responde *como está*, e são coisas
diferentes: a peça pode bater com o SET e estar torta, descascada ou sem etiqueta.

Os estados de `ItemContado.estado`:

| Estado | Quem marca | Onde |
|---|---|---|
| Perfeita | ninguém, é o padrão | — |
| Sem etiqueta | quem conta | contagem e câmera |
| Danificada, a classificar | quem conta | contagem e câmera |
| Para conserto | a gerência | tela Organizar |
| Para descarte | a gerência | tela Organizar |

**A classificação é em dois tempos, e isso é a decisão desta entrega.** Quem está na
prateleira marca só "danificada": na hora da contagem não se decide se uma luminária de
vime descascada vale um conserto ou vai para o lixo, e obrigar a decidir ali faria a
pessoa marcar o que for mais rápido. Quem decide é a gerência, depois, com o custo da peça
à vista. Por isso "Danificados, a classificar" é um grupo próprio: ele é a fila de
decisão. O servidor recusa `conserto` e `descarte` vindos da tela de contagem
(`views.NA_PRATELEIRA`), e não só esconde os botões.

**Nada sai das listas sozinho.** Sai quando alguém diz que a providência foi tomada —
etiqueta refeita, peça de volta da oficina, peça descartada com a baixa digitada no SET —
e isso fica na auditoria com o nome e a hora (`resolvido_em`, `resolvido_por`). Sem isso a
tela seria um histórico que só cresce, e no segundo mês ninguém mais acharia o que ainda
está esperando.

### Parados

O terceiro grupo não vem da contagem: vem da venda. Ninguém vê olhando a peça, porque a
peça está perfeita — o que está errado é que ela não sai. Entra na lista o produto com
peça na prateleira e **nenhuma unidade vendida há mais de 6 meses**; a partir de 12 meses,
ou nunca vendido, a linha sai em vermelho.

Seis meses, e não três: abaixo disso ainda cabe sazonalidade, e esta loja tem produto de
estação — peça de Natal não vende em março e nem por isso está encalhada.

**Só mercadoria de revenda entra.** Sem o filtro `so_mercadoria` a lista traz "CONSUMO
PROPRIO - CESTO/PAPEL ETC", que nunca vendeu porque nunca foi para vender. Já foi defeito
uma vez, entre o "Parado sem vender" do painel e a lista de compra, e a definição de
mercadoria mora num lugar só (`apps/compras/sugestoes.py`).

### A folha de etiquetas

A peça sem etiqueta precisa de uma nova, e o desenho do código de barras já existe
(`apps/core/barras.py`) — o mesmo que a tela de consulta mostra e que o leitor da loja já
lê. Então a folha é uma página que o navegador imprime, e não um PDF com um segundo
desenho: dois desenhos seriam dois lugares onde a etiqueta pode sair errada, e **etiqueta
errada o leitor lê como outro produto**.

Peça sem código de barras no cadastro do SET não tem etiqueta para refazer; a tela as
lista à parte. O número precisa nascer no SET primeiro, e isso não é coisa que este
sistema faça.

## O SET contra a nossa leitura

Este sistema **não escreve no SET**, e isso não é limitação de implementação: é regra do
próprio Edson, de 05/10/2026 — *"o sistema vigente set sistemas, nao permite nenhuma
integração"* — e a razão pela qual a leitura acontece sobre uma cópia do backup do dia,
nunca sobre o banco em uso. As tabelas de conferência de estoque do SET
(`CONFERENCIA_ESTOQUE`, `ICONFERENCIA_ESTOQUE`) existem e estão vazias: a loja nunca usou
aquela tela.

Então o acerto do saldo é digitado no SET por uma pessoa, uma linha por vez, porque é lá
que o estoque vale. O que o sistema faz são as duas pontas disso:

1. **entrega a lista**, ordenada pelo dinheiro — em PDF, em planilha e no arquivo de texto
   que já existia, para abrir ao lado do SET;
2. **confere sozinho se o que foi digitado entrou**, e é aqui que "através do backup"
   fecha o laço. A importação roda três vezes por dia sobre o backup novo; na primeira que
   acontecer depois da digitação, o saldo do SET ou passou a ser o contado, ou não.
   Ninguém precisa voltar na lista nem lembrar de conferir.

### Por que são três respostas e não duas

Entre a contagem e a importação seguinte a loja vendeu e recebeu mercadoria. Um saldo
diferente do contado não quer dizer que o ajuste não foi digitado — pode ter sido digitado
e o produto ter vendido duas unidades depois.

| Resposta | Quando | O que significa |
|---|---|---|
| Ajuste entrou no SET | saldo de hoje = contado | digitado |
| Ainda não entrou no SET | saldo de hoje = saldo de antes | ninguém digitou |
| Mudou, mas não para o contado | nenhum dos dois | venda, compra ou ajuste parcial |

O terceiro caso o sistema não afirma: diz o que viu e deixa para alguém olhar. Produto que
saiu do cadastro do SET entre a contagem e agora sai da conta, e a tela diz quantos foram.

A conferência só aparece quando existe foto do SET **mais nova** que a usada na contagem.
Comparar com a mesma foto não responderia nada, só repetiria a divergência.

## Os quatro relatórios

Todos saem em PDF e em planilha, montados pela **mesma** função
(`apps/inventario/relatorio.py`). Dois montadores separados começariam iguais e
divergiriam na primeira correção — é o defeito que a 1.34.0 consertou entre o Painel e a
Visão geral.

| Relatório | De onde | Para quê |
|---|---|---|
| Plano de inventário | tela Inventário | a folha com que se anda pela loja contando |
| SET contra a contagem | tela da contagem | o que digitar no SET, e o que já entrou |
| Descarte de produtos | tela Organizar | a perda ao custo, para a baixa e a contabilidade |
| Produtos para conserto | tela Organizar | o que está na oficina e o que se recupera |
| Produtos parados | tela Organizar | o dinheiro parado, para liquidar ou devolver |

No descarte e no conserto o valor da coluna é o **custo da peça inteira**, não a diferença
contra o SET: o que se perde ao jogar a peça fora é a peça, não o quanto ela divergia. No
conserto, esse custo é o que se recupera ao consertar — não é o preço do reparo, que o
sistema não tem.

## Quem vê o quê

| Tela | Permissão |
|---|---|
| Inventário, contagem, câmera | `inventario.contar_estoque` |
| Marcar sem etiqueta / danificada | `inventario.contar_estoque` |
| Organizar, classificar, resolver, os relatórios | `inventario.fechar_contagem` |

O **Operador vendedor não chega em nenhuma das duas**: a tela Organizar e os relatórios
mostram custo e valor da peça, e o vendedor vê uma tela só, sem dinheiro. Há teste para
isso. A classificação fica com quem conta (administrativo e gerência) pela mesma razão
que fechar a contagem: é trabalho de quem está na loja com a peça na mão, não da gerência
de longe.

## Onde cada coisa mora

| Arquivo | O que faz |
|---|---|
| `apps/core/curva_abc.py` | a curva ABC, usada pelo painel e pelo plano |
| `apps/inventario/plano.py` | prazos por classe, o que está vencido, o que contar agora |
| `apps/inventario/organizar.py` | os cinco grupos, marcar, classificar, resolver, parados |
| `apps/inventario/conferencia.py` | o ajuste entrou no SET? |
| `apps/inventario/relatorio.py` | os relatórios, em papel e em planilha |
| `apps/inventario/servicos.py` | a contagem em si, de antes |

## O que ainda não existe

- **Nenhum pedido de etiqueta nova ao SET**: peça sem código de barras no cadastro fica
  esperando alguém criar o número lá.
- **Nenhum custo de reparo**: o relatório de conserto diz o que a peça vale, não o que o
  conserto custa. Para ter isso, a loja teria que registrar o orçamento da oficina.
- **Nenhum arquivo de importação para o SET**: se o SET tiver tela de importação de
  conferência de estoque, dá para gerar o arquivo no layout dela — hoje a lista é para
  digitar.
