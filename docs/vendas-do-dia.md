# Vendas do dia

> Pedido do Edson em 11/10/2026: "quero que gera uma relação de todos os produtos
> vendidos do dia, preço de custo e valor de venda com porcentual de lucro e valor".

A tela fica em **Vendas do dia** (`/sistema/painel/vendas-do-dia/`) e responde a pergunta
mais simples que a loja faz: *o que eu vendi e quanto sobrou disso*. O mesmo número sai
todo dia por e-mail e, se estiver ligado, por Telegram.

## O que a tela mostra

Quatro números no topo, para o dia escolhido:

| Número | O que é |
|---|---|
| Vendido no dia | a soma dos produtos que saíram |
| Custo do que saiu | o que esses produtos custaram à loja |
| Sobrou no dia | vendido menos custo, antes das despesas da loja |
| Margem do dia | quanto de cada R$ 100 vendidos ficou na loja |

Embaixo, uma linha por produto: quantidade, valor vendido, custo, lucro em reais e
margem. O mesmo produto vendido em cupons diferentes aparece somado numa linha só, com
"em N vendas" ao lado do código. O botão **Baixar para o Excel** leva a relação inteira,
com uma coluna a mais dizendo de onde saiu o custo.

A caixa de seleção oferece os dias **que tiveram venda** na última importação, do mais
novo para o mais velho. Dia sem venda não aparece na lista: ofereceria uma tela vazia.

## De onde vem o custo, e por que às vezes ele é estimado

O SET grava, em cada item vendido (`IVENDAS.PRECOCUSTO`), quanto aquele produto custava
**no dia da venda**. É esse o custo certo para a conta do dia: se o fornecedor subiu o
preço depois, o dia continua valendo o que valia.

**Só que o SET parou de gravar esse campo.** Na cópia de 20/09/2026:

| Período | Itens sem o custo da venda |
|---|---|
| até 24/08/2026 | 0,5% |
| de 25/08/2026 em diante | de 70% a 100%, todo dia |

Alguma coisa mudou no SET em 25/08/2026 — vale perguntar à SET Sistemas o que foi, porque
é o dado que torna a margem do dia exata. Enquanto isso, o sistema usa a melhor
informação que tem, nesta ordem:

1. **custo do dia**: o que o SET gravou na venda;
2. **custo estimado**: o custo do cadastro do produto no momento da importação, que cobre
   90% dos itens sem custo da venda. A linha aparece marcada como `estimado`, e a tela
   diz quantos produtos e quanto do dia estão nessa situação;
3. **sem custo**: o produto não está mais no cadastro. A linha aparece marcada e **fica
   de fora** da conta do lucro.

Tratar custo vazio como zero daria margem de 100% e um lucro que a loja não teve; por
isso o terceiro caso sai da conta em vez de entrar como lucro cheio.

A conferência é fácil de fazer: a margem do dia 20/09/2026 deu 56,7% com a estimativa, e
a margem de 12 meses da loja inteira é 54,5%. Se a estimativa estivesse errada, a
diferença seria grande.

## Vendido abaixo do custo

Produto que saiu por menos do que custou aparece com a linha destacada e a frase "vendeu
abaixo do custo", e ganha um bloco próprio no e-mail. **Só com o custo da venda**: quando
o custo é estimado, a tela diz "o custo estimado ficou acima da venda" e o e-mail não
manda alarme nenhum. O motivo é prático: pedra e geodo são vendidos a peso, o cadastro
guarda o custo do quilo e a venda é de uma fração dele, então a estimativa apareceria como
prejuízo sem a loja ter perdido nada.

## O caixa do dia, no e-mail (1.40.4, corrigido na 1.40.5)

Pedidos do Edson: em 28/10/2026, *"inserir o valor de caixa inicial e final junto com o
operador que abriu e fechou o caixa"*; em 29/10/2026, corrigindo, *"inicio do caixa em
dinheiro, final do dia caixa em dinheiro, pagamento por pix, pagamento por cartao de
debito"* e de crédito. Logo depois do resumo do dia, o bloco **Caixa do dia** traz, para
cada caixa aberto naquele dia:

1. **Início do caixa em dinheiro**, com quem abriu e a hora (`CAIXA.SALDOINICIAL`).
2. **Final do dia em dinheiro**, com quem fechou e a hora, e a conta embaixo: início +
   vendas em dinheiro + entradas − sangrias − pagamentos pelo caixa. É a mesma conta da
   tela Caixa (`apps/caixa/dinheiro.py:do_turno`).
3. **PIX**, **Cartão de débito** e **Cartão de crédito**, pelo que o SET gravou por forma
   no turno. Forma que não apareceu no dia não aparece; forma que o sistema não conhece
   aparece com o nome do SET, avisando que ficou fora da conta do dinheiro.

Por último vem o **Total de vendas do dia** (1.40.6, pedido de 29/10/2026: *"somando
tudo (dinheiro + pix + cartão de debito + cartão de credito)"*): a soma das formas de
todos os caixas do dia. É o que os clientes pagaram, por isso pode ficar abaixo do
"vendeu" da manchete, que soma o preço dos produtos antes do desconto no fechamento do
cupom; a linha diz o desconto quando é isso. Na cópia de 20/09/2026, 48 dos últimos 57
dias com caixa batem com os cupons. Os outros 9 têm venda a prazo (não passa no caixa),
recebimento estornado no caixa com a venda mantida, ou PIX recebido sem venda no dia; a
linha mostra o total dos cupons e manda conferir na tela Caixa.

**Por que não o `SALDOFINAL` do SET:** ele soma PIX e cartão. A 1.40.4 usava esse número
e mostrava R$ 8.180,65 de fechamento no dia 20/09/2026, quando a gaveta tinha R$ 867,65.

- O dia do caixa é o da abertura (`CaixaImportado.dia`). Caixa que virou a noite mostra a
  data junto da hora de fechamento ("21/09 09:44").
- Caixa ainda aberto na hora da importação diz "caixa ainda aberto", e o dinheiro é o de
  até a importação.
- Operador em branco no SET aparece como "sem operador no SET".
- O bloco não é cortado em 12 linhas como os outros: cortar deixaria um caixa sem o final.

## O cupom e os produtos podem não bater

A relação soma os **produtos**. O cupom pode ter desconto dado no fechamento, que não fica
em produto nenhum. Quando os dois números diferem, a tela mostra a diferença e explica o
que ela é. Em 20/09/2026 foram R$ 132,50 de desconto no fechamento sobre R$ 8.200,00 de
produtos.

## Quem vê

Administrador gerência e Operador administrativo (`importacao.ver_painel`). O **Operador
vendedor não abre esta tela**, nem o arquivo para o Excel: ele continua com uma tela só,
sem custo e sem valor.

## Por dentro

- `apps/importacao/fontes/firebird.py:_ler_itens_de_venda` lê `IVENDAS` junto do
  cabeçalho da venda e já traz o custo do cadastro como estimativa.
- `apps/importacao/models.py:ItemVendaImportada` guarda o item na foto da importação. Como
  todo o resto, ele tem `importacao` pelo cabeçalho da venda e **não soma** entre
  importações ([sincronizacao-nao-soma.md](sincronizacao-nao-soma.md)).
- `apps/painel/vendas_do_dia.py:calcular` é a conta, e é a MESMA função que o e-mail
  chama. São 32 mil itens por foto, ~190 no dia mais movimentado.
- `apps/alertas/relatorios.py:vendas_do_dia` monta o relatório a partir dela.
