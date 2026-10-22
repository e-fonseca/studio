"""De que pedaço de calendário sai a média de venda que vira sugestão de compra.

Pedido do Edson em 14/10/2026: *"faça analise do periodo definido no filtro e usar a
media de vendas nesse mesmo período e calcular a sugestao de compra"*.

Até a 1.32.0 a média era sempre a mesma: unidades vendidas em doze meses divididas
pelos dias em que a loja abriu. É uma régua estável, e é justamente esse o problema
quando a loja quer olhar o momento — doze meses demoram um ano para registrar que um
produto parou de vender, ou que começou.

A conta de cada janela
----------------------
    venda por dia = unidades vendidas na janela / dias em que a loja ABRIU na janela

Dias em que a loja abriu, não dias de calendário: a Cabana não abre todo dia, e dividir
por 30 um mês com 24 dias de porta aberta subestima a venda diária em 20%. É a mesma
régua que a janela de doze meses já usava (`Importacao.dias_abertos_12m`).

O freio
-------
Produto que não vendeu NADA na janela escolhida volta para os doze meses, e a linha diz
que foi isso que aconteceu. Sem isso, filtrar "últimos 3 meses" em junho zeraria a
sugestão de todo produto de dezembro, e ele sumiria da lista de compra — que é
exatamente o produto que some da prateleira sem ninguém perceber. Quem decidiu assim
foi o Edson, no card de 14/10/2026.

A janela de doze meses continua sendo a padrão, e continua saindo da foto sem consulta
nenhuma: quem não mexe no filtro não paga nada por este arquivo existir.
"""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum

from apps.importacao.models import ItemVendaImportada, VendaImportada

ZERO = Decimal("0")

# Doze meses é o padrão e não tem janela própria: é o que a foto já traz pronto.
DOZE_MESES = ""
PERIODOS = (
    (DOZE_MESES, "12 meses", 365),
    ("180", "6 meses", 180),
    ("90", "3 meses", 90),
    ("30", "30 dias", 30),
)
_POR_CHAVE = {chave: (rotulo, dias) for chave, rotulo, dias in PERIODOS}


def rotulo_de(chave):
    return _POR_CHAVE.get(chave or DOZE_MESES, _POR_CHAVE[DOZE_MESES])[0]


def valida(chave):
    """A chave do filtro, ou a padrão quando vier qualquer outra coisa pela URL."""
    return chave if chave in _POR_CHAVE else DOZE_MESES


@dataclass(frozen=True)
class Venda:
    """Quanto um produto vendeu na janela, e em quantos dias de porta aberta."""

    unidades: Decimal
    dias_abertos: int


class Janela:
    """A venda de cada produto dentro da janela escolhida, lida de uma vez só."""

    def __init__(self, chave=DOZE_MESES, por_codigo=None, dias_abertos=0, de=None, ate=None):
        self.chave = chave
        self.de, self.ate = de, ate
        self.dias_abertos = dias_abertos
        self._por_codigo = por_codigo

    @property
    def e_a_padrao(self):
        """A janela de doze meses, que vem pronta na foto e não muda conta nenhuma."""
        return self._por_codigo is None

    @property
    def rotulo(self):
        return rotulo_de(self.chave)

    def para(self, produto, padrao_unidades, padrao_dias):
        """A venda deste produto na janela, ou a dos doze meses quando ela não serve.

        Devolve (venda, usou_a_padrao): o segundo diz à tela que o produto não vendeu
        nada na janela e a conta caiu de volta para os doze meses.
        """
        if self.e_a_padrao:
            return Venda(padrao_unidades, padrao_dias), False
        unidades = self._por_codigo.get(produto.codigo, ZERO)
        if unidades <= ZERO or self.dias_abertos <= 0:
            return Venda(padrao_unidades, padrao_dias), True
        return Venda(unidades, self.dias_abertos), False


def montar(importacao, consulta_de_produtos, chave=DOZE_MESES):
    """Lê de uma vez quanto cada produto da consulta vendeu na janela escolhida."""
    chave = valida(chave)
    if importacao is None or chave == DOZE_MESES or importacao.data_corte is None:
        return Janela(DOZE_MESES)

    dias = _POR_CHAVE[chave][1]
    ate = importacao.data_corte
    de = ate - timedelta(days=dias - 1)

    # Dias em que a loja abriu dentro da janela: dias distintos com venda registrada.
    dias_abertos = (
        VendaImportada.objects
        .filter(importacao=importacao, data__gte=de, data__lte=ate)
        .values("data").distinct().count()
    )

    # Uma consulta para a lista inteira, com os produtos entrando por SUBCONSULTA.
    # A soma é de `quantidade` do item da venda, a mesma coluna de onde o importador
    # tira `vendas_12m`: se as duas viessem de fontes diferentes, trocar o filtro de
    # 12 meses para 12 meses mudaria o número.
    por_codigo = {
        linha["codigo"]: linha["unidades"] or ZERO
        for linha in (
            ItemVendaImportada.objects
            .filter(venda__importacao=importacao, venda__data__gte=de, venda__data__lte=ate,
                    codigo__in=consulta_de_produtos.values("codigo"))
            .values("codigo")
            .annotate(unidades=Sum("quantidade"))
            .order_by()
        )
    }
    return Janela(chave, por_codigo, dias_abertos, de, ate)
