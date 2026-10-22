# Regras de negócio da Cabana

Loja de decoração e utilidades. O dono compra "no olhômetro" e aperta o caixa; o sistema
existe para trocar palpite por número. Os doze meses lidos da cópia de 20/09/2026:

| O que | Quanto |
|---|---|
| Vendido | R$ 1,58 milhão |
| Comprado | R$ 519 mil |
| Na prateleira (ao custo) | R$ 742 mil |
| Parado, sem vender uma unidade no ano | R$ 227 mil |
| Despesa | R$ 119 mil/mês |

A conclusão que o sistema inteiro defende: **o problema é a escolha, não o volume.**

## Teto mensal de compra

`soma(vendas_12m × custo) / 12` — o que SAIU da prateleira num mês médio
(R$ 59.799,80), e não a média do que foi comprado. A tela diz, com essas palavras, que
estar abaixo do limite não é motivo para comprar.

O corte do mês é **por fornecedor**, não por item, e cada fornecedor mostra o
**contrapeso**: quanto dele está parado sem vender no ano. Sem isso o sistema mandaria
comprar mais de quem a loja já comprou errado.

## Custo: três custos diferentes, e eles não se misturam

| Qual | Onde | Para que serve |
|---|---|---|
| Custo de hoje | `ProdutoImportado.custo` (PRODUTOS.PRECOCUSTO) | repor, teto de compra, valor da prateleira |
| Custo do dia da venda | `ItemVendaImportada.custo_unitario` (IVENDAS.PRECOCUSTO) | lucro realizado do dia |
| Custo da última compra | `ItemCompraImportada.custo_unitario` | conferir se o fornecedor subiu o preço |

Usar o custo de hoje para calcular o lucro de ontem é o erro clássico: se o fornecedor
subiu o preço depois, o dia passa a parecer pior do que foi.

## Item sem custo gravado

1.608 dos 32.034 itens vendidos em 12 meses saíram do SET sem `PRECOCUSTO`. A regra, em
toda tela e todo relatório:

- custo vazio **não** é zero;
- o item fica de fora da conta do lucro e da margem;
- a tela diz quantos são e quanto de venda eles representam.

Tratar vazio como zero daria margem de 100% e um lucro que a loja não teve.

## Margem e markup

- Margem = (venda − custo) / venda. Markup = venda / custo.
- Margem realizada do período = `(receita − custo_do_vendido) / receita`, só sobre a
  parte com custo conhecido.
- `DIVERSOS` e `CONSUMO PROPRIO` não são mercadoria de revenda: ficam fora de markup,
  margem e "parado" (`sugestoes.so_mercadoria` / `e_mercadoria`). `DIVERSOS` é venda
  miúda a R$ 1,00 e daria −1.150%. O dinheiro deles continua no total da loja.

## Estoque

A loja nunca fez contagem física: 1.456 itens com saldo negativo. Saldo é **estimativa**,
aparece marcado como tal, e é daí que vem a tela de inventário.

## Lista de compra

Roda o mesmo `calculos.py` do "Antes de comprar" sobre a loja inteira, com `QTDEMIN`
como piso, mercadoria a caminho descontada, e prazo = informado > medido > 15 dias.
Produto sem venda em 12 meses e sem estoque vira `Situacao.SEM_DADOS` ("só repor se for
pedido de cliente").

## Tarefas ("O que fazer agora")

Tarefa só existe se o número que a justifica for > 0, traz o número na frase e termina
num link. A permissão filtra DEPOIS do cálculo (`tarefas.para`), e o vendedor não vê
nenhuma.
