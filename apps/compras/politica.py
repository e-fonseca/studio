"""O alerta de 30% e o carro-chefe da loja: o que não pode faltar, e quando ele está perto.

Pedido do Edson em 22/10/2026: *"deixar como padrão alerta de 30% para cada produto no
estoque e destacar para os produtos mais vendidos, carro chefe da loja"*. Os dois números
moram em `models.PoliticaDeCompra`, que a gerência muda na própria Lista de compra.

A régua do alerta
-----------------
"30% do estoque" precisa de um 100%, e o 100% aqui é o **estoque ideal**: o estoque-alvo
da conta de reposição (`calculos.py`), que é o que o produto vende no prazo do
fornecedor mais a semana até a próxima compra e a margem de segurança. Ele já é a régua
da lista, então o alerta não inventa um número novo: diz quanto do ideal o produto ainda
tem, contando o que está a caminho.

Não se usou o estoque máximo que o produto já teve, nem o mínimo do SET: o primeiro
premia a compra exagerada de um ano (produto que encalhou 200 unidades ficaria em
"alerta" com 50 na prateleira), e o segundo está vazio em quase todo o cadastro.

O alerta não muda QUANTO comprar. A conta já manda comprar no ponto de reposição, que
fica perto de três quartos do ideal; 30% é o ponto em que o produto deixou de ser
"precisa comprar" e virou "vai faltar antes de o pedido chegar".

O carro-chefe
-------------
São os N produtos que mais faturaram em doze meses, N = 100 por padrão. Faturamento, e não
unidades, porque é o dinheiro que a falta deixa de trazer: na foto de 20/09/2026 o
primeiro em unidades era um jogo americano de R$ 31, e o primeiro em faturamento a pele
natural G, R$ 35 mil no ano. Só mercadoria de revenda (`sugestoes.so_mercadoria`): DIVERSOS
é venda miúda a R$ 1,00 e não é produto.
"""

from decimal import Decimal

from .sugestoes import so_mercadoria

ZERO = Decimal("0")
CEM = Decimal("100")


def carros_chefe(importacao, quantos):
    """Os códigos dos `quantos` produtos que mais faturaram, em ordem. Lista vazia sem foto."""
    if importacao is None or not quantos:
        return []
    return list(
        so_mercadoria(importacao.itens.filter(receita_12m__gt=0))
        .order_by("-receita_12m", "codigo")
        .values_list("codigo", flat=True)[:quantos]
    )


def porcentagem_do_ideal(posicao, alvo):
    """Quanto do estoque ideal o produto tem, de 0 a 100 ou mais. None sem ideal.

    Produto que não vende não tem estoque ideal, e "0% de nada" não é alerta: é
    assunto da tela de Sugestões. Saldo a caminho conta, porque já foi comprado.
    """
    if alvo is None or alvo <= 0:
        return None
    posicao = max(Decimal(posicao or 0), ZERO)
    return int((posicao * CEM / Decimal(alvo)).to_integral_value())


def em_alerta(porcentagem, limite):
    return porcentagem is not None and porcentagem <= limite
