# Markup e margem de lucro

Pedido do Edson em 08/10/2026: *"buscar no set se temos o valor de custo e a margem de
lucro dos produtos para calcular o Markup e a Margem de Lucro individuais por produto e
geral"*.

Temos. Este documento diz o que o SET guarda, o que o sistema calcula com isso e onde
estão as armadilhas.

## As duas contas, e por que elas não são a mesma

```
markup = (preço ÷ custo − 1) × 100      quanto se põe EM CIMA DO CUSTO
margem = (preço − custo) ÷ preço × 100  quanto sobra DO PREÇO DE VENDA
```

Um produto que custa R$ 10,00 e vende a R$ 20,00 tem **100% de markup** e **50% de
margem**. É o mesmo lucro, contado de dois jeitos. Confundir os dois é o erro mais caro do
varejo: quem acha que tem 120% de margem dá um desconto de 40% achando que ainda sobra
muito, quando a margem real é 54,5% e o desconto come quase tudo.

Na loja inteira, em 12 meses até 20/09/2026: **markup de 119,9%** é a **margem de 54,5%**.

## O que o SET tem

| Onde | Campo | O que é | Preenchimento |
| --- | --- | --- | --- |
| `PRODUTOS` | `PRECOCUSTO` | custo do cadastro | 11.096 de 11.274 |
| `PRODUTOS` | `PRECOCOMPRA` | custo da última compra | 10.593; usado quando `PRECOCUSTO` está zerado |
| `PRODUTOS` | `PRECOVENDA` | preço de venda | 11.266 |
| `PRODUTOS` | `PLUCRO` | o campo "% de lucro" | 10.766; **é markup, não margem** |
| `IVENDAS` | `PRECOCUSTO` | custo do produto **no dia da venda** | 30.426 dos 32.034 itens de 12 meses |

Os campos `CUSTO_IPI` e `CUSTO_ST` existem e estão todos zerados; `CUSTO_FRETE` tem valor
em 41 produtos e `COMISSAO` é sempre nulo. Ou seja, **não há custo de chegada** (frete,
imposto) no SET: o custo é o da nota, e a margem calculada aqui é margem bruta sobre a
mercadoria, antes de despesa, imposto e salário.

### O `PLUCRO` é markup

Confere com `(PRECOVENDA / PRECOCUSTO − 1) × 100` em **10.759 dos 10.764** produtos que têm
os três campos preenchidos. Os cinco que não conferem são preço que mudou sem o campo
acompanhar — por exemplo o `006491`, custo R$ 2,00 e venda R$ 13,00 (markup de 550%) com
`PLUCRO` parado em 130%. A tela aponta esses cinco.

Por isso a coluna da tela se chama **"% no SET"** e não "margem": ela mostra o campo como
está lá, para dar para comparar com o que o preço de hoje realmente rende.

## As duas margens da tela

- **Realizada (12 meses).** Receita menos o custo gravado no item no dia da venda. É o que a
  loja de fato ganhou: **54,5%**, R$ 818.075,84 de lucro bruto. Em 1.608 dos 32.034 itens
  o custo do dia está vazio no SET; esses itens ficam fora dos dois lados da conta, que é
  feita sobre os 95,2% do faturamento que têm custo. Sem isso a margem sairia otimista.
- **Da tabela de hoje.** Custo e preço do cadastro de agora, pesados pelo que cada produto
  vendeu em 12 meses: **58,3% de margem, 140,9% de markup**. É o que a loja ganharia
  vendendo o mesmo do ano passado com os preços de hoje.

A tabela promete mais do que a loja realizou. A diferença são descontos no balcão e o mix
real de venda, que puxa para produto de margem menor. Grupo em que a margem da tabela é
**menor** que a realizada é grupo que apertou o preço depois.

## O que a tela aponta no cadastro (20/09/2026)

| Aviso | Quantos | O que é |
| --- | --- | --- |
| Preço abaixo do custo | 127 | vender tudo o que está na prateleira custaria R$ 1.284,50 do próprio bolso |
| Preço igual ao custo | 149 | markup zero |
| Preço sem custo no cadastro | 164 | não dá para saber se dá lucro |
| "% de lucro" do SET desatualizado | 5 | o preço mudou e o campo ficou para trás |
| Sem "% de lucro" no SET | 60 | não atrapalha: a conta daqui sai do custo e do preço |

Nada disso é corrigido pelo sistema: a correção é no cadastro do SET, que é quem manda no
preço. O sistema só lê.

### O que fica de fora

`DIVERSOS` e `CONSUMO PROPRIO` não recebem markup nem margem (`apps.compras.sugestoes
.e_mercadoria`, a mesma regra da lista de compra). `DIVERSOS` é o código em que o balcão
lança a venda miúda, a R$ 1,00, com um custo de cadastro que não quer dizer nada: marcá-lo
como "preço abaixo do custo" mandaria a gerência arrumar um preço que não existe. O
faturamento e o lucro dele continuam na conta da loja, porque o dinheiro entrou.

## Onde está no código

- `apps/margem/servicos.py` — as contas, a situação de cada produto e os totais.
- `apps/margem/views.py` — a tela (`/sistema/margem/`) e o arquivo para o Excel.
- `apps/importacao/models.py` — `markup_set`, `custo_vendido_12m` e `receita_com_custo_12m`
  no `ProdutoImportado` (migração `0008`).
- `apps/importacao/fontes/firebird.py` — de onde cada um vem.

A permissão é `importacao.ver_painel`, a mesma dos painéis: gerência e administrativo. O
perfil de vendedor não a tem e nunca vê esta tela, que é toda custo e lucro.
