"""A curva ABC num lugar só: quais produtos sustentam a loja e quais quase não vendem.

Por que isto saiu do painel
---------------------------
A regra vivia dentro de `apps/painel/dashboard.py`, que a usava só para somar as três
classes numa caixa da tela. O inventário passou a precisar da MESMA classificação, mas
produto por produto: é a classe que decide de quanto em quanto tempo cada produto é
contado (classe A todo mês, C duas vezes por ano). Duas cópias da regra seria o defeito
que a 1.34.0 consertou entre o Painel e a Visão geral — o mesmo produto sendo classe A
numa tela e B noutra, e ninguém sabendo qual acreditar.

A convenção, que é a do varejo
------------------------------
Os produtos são ordenados do que mais fatura para o que menos fatura, e o faturamento
vai sendo acumulado:

* **A** — os primeiros 80% do faturamento. São poucos produtos e não podem faltar.
* **B** — dos 80% aos 95%.
* **C** — os últimos 5%. São muitos produtos e cada peça é caixa parado.

A classe sai do acumulado **antes** do produto, não depois: quem cruza a linha dos 80%
entra em A. Sem isso, um produto que sozinho já passa dos 80% deixaria a classe A vazia.

**Produto sem faturamento nenhum nos 12 meses fica fora da curva**, e isso é de
propósito: na cópia de 20/09/2026 eram 6.483 produtos: ordenar por zero não diz nada e
jogá-los em C esconderia justamente o grupo que a loja precisa olhar separado. Quem
chama `por_produto` recebe esses produtos com a letra vazia.
"""

from decimal import Decimal

ZERO = Decimal("0")
CEM = Decimal("100")

# Onde cada faixa termina, em porcentagem do faturamento acumulado.
LIMITE_A = Decimal("80")
LIMITE_B = Decimal("95")

# O que cada letra quer dizer, em palavras de loja: a letra sozinha não diz nada a quem
# nunca ouviu falar em curva ABC. O painel já mostrava estes textos; ficam aqui para a
# tela do inventário dizer o mesmo com as mesmas palavras.
TITULOS = {
    "A": "sustentam a loja",
    "B": "ajudam",
    "C": "quase não vendem",
    "": "não venderam no ano",
}
EXPLICACOES = {
    "A": "Nunca podem faltar.",
    "B": "Os 15% seguintes. Repor com atenção ao prazo.",
    "C": "Os últimos 5%. Estoque mínimo: cada peça aqui é caixa parado.",
    "": "Nenhuma unidade vendida em 12 meses. Dinheiro parado na prateleira.",
}

LETRAS = ("A", "B", "C")


def letras(receitas):
    """Devolve a letra de cada faturamento, na ordem em que os faturamentos chegaram.

    Espera a lista já ordenada do maior para o menor, e espera que todos sejam maiores
    que zero: é assim que a curva é definida. Lista vazia ou total zero devolve vazio,
    porque sem faturamento não existe curva — e não um monte de produtos classe A.
    """
    receitas = [Decimal(valor or 0) for valor in receitas]
    total = sum(receitas, ZERO)
    if total <= ZERO:
        return []
    saida = []
    acumulado = ZERO
    for receita in receitas:
        antes = acumulado * CEM / total
        acumulado += receita
        saida.append("A" if antes < LIMITE_A else ("B" if antes < LIMITE_B else "C"))
    return saida


def por_produto(pares):
    """Recebe (código, faturamento de 12 meses) e devolve {código: letra}.

    A ordem de entrada não importa: a função ordena. Produto com faturamento zero ou
    negativo entra no resultado com letra **vazia**, e não fica de fora — quem chama
    precisa poder perguntar a classe de qualquer produto sem tratar o caso ausente.
    """
    pares = [(codigo, Decimal(receita or 0)) for codigo, receita in pares]
    com_venda = sorted(
        [(codigo, receita) for codigo, receita in pares if receita > ZERO],
        key=lambda par: par[1], reverse=True,
    )
    resultado = {codigo: "" for codigo, receita in pares if receita <= ZERO}
    for (codigo, _), letra in zip(com_venda, letras([r for _, r in com_venda])):
        resultado[codigo] = letra
    return resultado
