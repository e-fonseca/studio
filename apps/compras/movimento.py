"""O que entrou, o que saiu, e onde o estoque foi parar — produto a produto.

Pedido do Edson em 14/10/2026: *"exiba uma sugestão de compra analisando o que foi
comprado de um determinado produto e o que foi vendido e o resultado que seria o
estoque (...) levando em consideração o que foi comprado na última compra e vendido"*.

O problema que isto resolve: a lista de compra mostrava TEM, A CAMINHO, MÍNIMO e
COMPRAR, e nenhum desses números explica o outro. Um produto que vendeu 8 no ano e
outro que vendeu 1 recebiam a mesma sugestão — porque a conta dá menos de uma unidade
nos dois casos e arredonda para cima —, e a tela não dava como desconfiar disso.

As duas contas que esta tela passa a mostrar
--------------------------------------------
**Nos doze meses:** comprou X, vendeu Y, então o estoque andou X − Y. Os dois números
já vêm prontos na foto da importação (`compras_12m` e `vendas_12m`), então esta parte
não custa consulta nenhuma. Dela sai também quanto o produto tinha um ano atrás, que é
o estoque de hoje menos esse movimento — o único jeito de ter saldo de partida sem
inventário, que a loja nunca fez.

**Desde a última compra:** entraram N unidades no dia D, e desde D saíram M. É a conta
que o Edson descreveu, e ela tem uma vantagem contábil real: ancorada numa data
conhecida, não precisa de saldo inicial. O que ela NÃO é: prova de divergência. Como o
saldo anterior à compra é desconhecido, a conta sempre fecha por construção — ela serve
para enxergar o giro ("entraram 4 e já saíram 6"), não para acusar perda.

O que fica de fora, e por quê
-----------------------------
- **Compra pendente não conta como compra feita**, aqui como em todo o resto do sistema:
  ela é mercadoria a caminho e já aparece na coluna A CAMINHO.
- **A data da compra é a da nota, e o pedido quando não há nota** — a mesma regra que o
  importador usa para somar `compras_12m` (ver fontes/firebird.py). Usar outra data aqui
  faria dois números da mesma tela discordarem.
- **A venda desde a compra sai da venda MENSAL**, rateada por dias no mês em que a compra
  caiu. A alternativa seria ler item de venda, que só existe para 12 meses e pesa muito
  mais; o erro desta escolha cabe dentro de um mês do próprio produto.
"""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import F, Sum
from django.db.models.functions import Coalesce

# As duas contas de calendário são as mesmas da estação, e de propósito: ratear mês
# por dias de um jeito aqui e de outro lá faria a mesma tela dizer dois números.
from apps.compras.estacao import _meses_entre, _parte_do_mes
from apps.importacao.models import ItemCompraImportada, VendaMensalDoProduto

ZERO = Decimal("0")
UMA_UNIDADE = Decimal("1")


@dataclass(frozen=True)
class Movimento:
    """O caminho do estoque de um produto, para a linha da lista de compra."""

    codigo: str
    comprado_12m: Decimal
    vendido_12m: Decimal
    estoque: Decimal
    ultima_compra_em: date | None = None
    ultima_compra_unidades: Decimal = ZERO
    vendido_desde_a_compra: Decimal = ZERO

    @property
    def andou_12m(self):
        """Quanto o estoque subiu (ou desceu) nos doze meses: comprou menos vendeu."""
        return self.comprado_12m - self.vendido_12m

    @property
    def tinha_um_ano_atras(self):
        """O saldo de partida, deduzido: o de hoje, desfazendo o movimento do ano."""
        return self.estoque - self.andou_12m

    @property
    def comprou_menos_do_que_vendeu(self):
        return self.andou_12m < ZERO

    @property
    def quanto_caiu(self):
        """De quanto o estoque caiu, sem o sinal: a tela já diz "caiu" com palavra."""
        return -self.andou_12m if self.andou_12m < ZERO else ZERO

    @property
    def tem_ultima_compra(self):
        return self.ultima_compra_em is not None and self.ultima_compra_unidades > ZERO

    @property
    def sobra_da_ultima_compra(self):
        """Das unidades que entraram na última compra, quantas ainda não saíram."""
        return self.ultima_compra_unidades - self.vendido_desde_a_compra

    @property
    def ultima_compra_ja_vendida(self):
        """A última compra já saiu inteira: o produto repõe mais rápido do que compra."""
        return self.tem_ultima_compra and self.sobra_da_ultima_compra <= ZERO


class Movimentos:
    """As compras e as vendas da lista inteira, na memória, para perguntar produto a produto.

    Duas consultas para a lista toda, como em apps/compras/estacao.py, e o conjunto de
    produtos entra por SUBCONSULTA — nunca uma lista de dez mil códigos dentro de um `IN`.
    """

    def __init__(self, ultima_compra=None, vendas_por_mes=None):
        self._ultima_compra = ultima_compra or {}
        self._vendas = vendas_por_mes or {}

    def para(self, produto):
        """O movimento deste produto, a partir da linha que já veio da foto."""
        comprado = produto.compras_12m or ZERO
        vendido = produto.vendas_12m or ZERO
        estoque = produto.estoque or ZERO
        quando, unidades = self._ultima_compra.get(produto.codigo, (None, ZERO))
        desde = self._vendido_desde(produto.codigo, quando) if quando else ZERO
        return Movimento(
            codigo=produto.codigo, comprado_12m=comprado, vendido_12m=vendido,
            estoque=estoque, ultima_compra_em=quando, ultima_compra_unidades=unidades,
            vendido_desde_a_compra=desde,
        )

    def _vendido_desde(self, codigo, quando):
        """Unidades vendidas de `quando` até hoje, pela venda mensal rateada por dias.

        O mês da compra entra pela fração que vem DEPOIS dela; os meses seguintes entram
        inteiros. Quem fecha a janela é o mês mais novo que a foto guarda, não "hoje":
        mês que a foto não tem é mês que ninguém pode somar.
        """
        meses = self._vendas.get(codigo)
        if not meses:
            return ZERO
        fim = max(meses)
        ate = date(fim[0], fim[1], monthrange(fim[0], fim[1])[1])
        if ate < quando:
            return ZERO
        vendido = sum(
            (meses.get(mes, ZERO) * _parte_do_mes(mes[0], mes[1], quando, ate)
             for mes in _meses_entre(quando, ate)),
            ZERO,
        )
        # Ratear é dividir, e divisão de Decimal volta com 28 casas. Quem arredonda é
        # quem calcula, e a casa certa aqui é a UNIDADE: a loja vende tapete e vaso
        # inteiros, e "vendeu 50,774" sobre um número que já é aproximado no mês da
        # compra é precisão de mentira. Unidade inteira também deixa a sobra inteira.
        return vendido.quantize(UMA_UNIDADE, rounding=ROUND_HALF_UP)


def montar(importacao, consulta_de_produtos):
    """Lê de uma vez a última compra e a venda mensal dos produtos da consulta."""
    if importacao is None:
        return Movimentos()

    codigos = consulta_de_produtos.values("codigo")

    # A última compra de cada produto. Agrupar por (código, data) e escolher a data mais
    # nova no Python sai mais barato que uma subconsulta correlacionada por produto, e o
    # resultado é pequeno: são as linhas de compra da loja inteira, não as vendas.
    ultima_compra = {}
    linhas = (
        ItemCompraImportada.objects
        .filter(compra__importacao=importacao, compra__pendente=False, codigo__in=codigos)
        .annotate(quando=Coalesce(F("compra__data_nota"), F("compra__data_pedido")))
        .filter(quando__isnull=False, quantidade__gt=0)
        .values("codigo", "quando")
        .annotate(unidades=Sum("quantidade"))
        .order_by()
    )
    for linha in linhas:
        quando, unidades = linha["quando"], linha["unidades"] or ZERO
        atual = ultima_compra.get(linha["codigo"])
        if atual is None or quando > atual[0]:
            ultima_compra[linha["codigo"]] = (quando, unidades)
        elif quando == atual[0]:
            # Duas notas no mesmo dia: entraram as duas.
            ultima_compra[linha["codigo"]] = (quando, atual[1] + unidades)

    mais_antiga = min((quando for quando, _ in ultima_compra.values()), default=None)
    vendas_por_mes = {}
    if mais_antiga is not None:
        mensais = (
            VendaMensalDoProduto.objects
            .filter(importacao=importacao, codigo__in=codigos)
            .filter(ano__gte=mais_antiga.year)
            .values("codigo", "ano", "mes")
            .annotate(unidades=Sum("unidades"))
            .order_by()
        )
        for linha in mensais:
            vendas_por_mes.setdefault(linha["codigo"], {})[(linha["ano"], linha["mes"])] = (
                linha["unidades"] or ZERO)

    return Movimentos(ultima_compra, vendas_por_mes)
