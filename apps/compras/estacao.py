"""O mesmo período do ano passado, aplicado à quantidade que o sistema sugere comprar.

Pedido do Edson em 14/10/2026: *"preciso saber a quantidade que o sistema inteligente
sugeriu para comprar, avaliando o período vigente do pedido atual com o mesmo período do
ano anterior"*.

O problema que isto resolve: a sugestão de compra nasce da venda dos últimos doze meses
dividida por dias, que é uma média plana. A Cabana vende por estação — o que sai em
dezembro não é o que sai em março —, então a média plana manda comprar de menos justo
antes de a estação começar e de mais depois que ela passou.

A conta, em uma frase: **este pedido vai cobrir os próximos tantos dias; no ano passado,
esses mesmos dias do calendário venderam quantas vezes a média do produto?** Esse número
é o fator, e a sugestão é multiplicada por ele.

    fator = (unidades do produto na mesma janela, um ano atrás) / dias da janela
            ------------------------------------------------------------------
            (unidades do produto nos doze meses anteriores àquela janela) / 365

Três freios, porque fator errado vira pedido errado:

- **Pouca venda não vira estação.** Produto que vendeu menos de seis unidades no ano não
  tem padrão nenhum: tem acaso. E produto que normalmente venderia menos de duas unidades
  numa janela deste tamanho também não: o zero dele é o tamanho da amostra, não a estação.
- **Diferença pequena não é estação.** Menos de um décimo para mais ou para menos é
  ruído de calendário, e fica sem fator.
- **O fator não passa de 2 nem fica abaixo de 0,5.** Sem o teto, um produto que vendeu
  tudo numa semana do ano passado mandaria comprar dez vezes mais; sem o piso, um mês
  fraco zeraria a reposição de um produto que a loja vende o ano inteiro.
- **Mês pela metade não conta.** Se a foto não guarda inteiros os meses que a conta
  precisa, não há fator: é o mesmo cuidado da comparação (docs/comparar-com-o-ano-passado.md).

O fator mexe só no QUANTO COMPRAR. A cobertura em dias e o excesso continuam saindo da
média dos doze meses: dizer que um produto de verão está "em excesso" em julho porque a
demanda ajustada caiu seria trocar uma informação por um palpite.

E o fator só vale sobre base PLANA
----------------------------------
Olhe o denominador da conta: a média do produto nos doze meses. O fator existe para
consertar essa média plana, e nada mais. Desde a 1.33.0 o filtro da tela deixa a pessoa
trocar a base pela venda dos últimos 30, 90 ou 180 dias (apps/compras/janela.py) — e essa
já É a venda da estação de agora. Multiplicá-la pelo fator contaria a estação duas vezes
e, com o TETO de 2, chegaria a pedir o dobro ao fornecedor justamente no mês de pico.
Então quem monta a lista só pede o fator quando a base é plana: a janela de doze meses, ou
o produto que voltou para ela por não ter vendido nada na janela curta.
"""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum

from apps.importacao.models import VendaMensalDoProduto

ZERO = Decimal("0")
UM = Decimal("1")
DIAS_DO_ANO = Decimal("365")

# Abaixo disto, o ano passado não é padrão: é acaso.
MINIMO_DE_UNIDADES = Decimal("6")
# E o produto ainda precisa vender o bastante para a JANELA ser amostra. Um produto de
# doze unidades por ano vende zero na maioria das janelas de um mês, e esse zero não é
# estação, é o tamanho da amostra: sem este freio, setecentos produtos de giro lento
# desceriam para o piso de uma vez.
MINIMO_NA_JANELA = Decimal("2")
PISO = Decimal("0.5")
TETO = Decimal("2")
# Diferença de menos de um décimo para mais ou para menos não é estação, é ruído de
# calendário: mês de 30 contra mês de 31, um feriado que caiu noutro dia. Mexer na
# quantidade por causa disso encheria a tela de "vendeu 1,0 vezes a média".
MARGEM = Decimal("0.1")
# Quantos meses de venda o fator precisa ter inteiros na foto: doze de base, mais os
# meses que a janela do pedido encosta.
MESES_DE_BASE = 12


@dataclass(frozen=True)
class Fator:
    """O que o ano passado diz sobre a janela deste pedido, para um produto."""

    codigo: str
    fator: Decimal
    unidades_na_janela: Decimal
    media_esperada: Decimal
    de: date
    ate: date

    @property
    def mexeu(self):
        """Mudou alguma coisa? Fator 1 existe, mas não tem o que explicar na tela."""
        return self.fator != UM

    @property
    def mais_forte(self):
        return self.fator > UM

    @property
    def vezes(self):
        """Quantas vezes a média, em texto curto para a tela: 2x, 1,4x, 0,6x."""
        return self.fator.quantize(Decimal("0.1"))


def _mes_de(dia):
    return (dia.year, dia.month)


def _meses_entre(inicio, fim):
    """Todos os (ano, mês) que a janela [inicio, fim] encosta."""
    meses, ano, mes = [], inicio.year, inicio.month
    while (ano, mes) <= _mes_de(fim):
        meses.append((ano, mes))
        ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return meses


def _meses_antes(ano, mes, quantos):
    """Os `quantos` meses imediatamente anteriores a (ano, mês), do mais velho ao mais novo."""
    meses = []
    for _ in range(quantos):
        ano, mes = (ano - 1, 12) if mes == 1 else (ano, mes - 1)
        meses.append((ano, mes))
    return list(reversed(meses))


def _um_ano_antes(dia):
    """O mesmo dia, um ano atrás. 29 de fevereiro vira 28, que é o que o calendário tem."""
    try:
        return dia.replace(year=dia.year - 1)
    except ValueError:
        return dia.replace(year=dia.year - 1, day=28)


def _parte_do_mes(ano, mes, de, ate):
    """Que fração do mês (ano, mês) cabe dentro de [de, ate], contando dias."""
    dias_no_mes = monthrange(ano, mes)[1]
    primeiro = date(ano, mes, 1)
    ultimo = date(ano, mes, dias_no_mes)
    inicio = max(primeiro, de)
    fim = min(ultimo, ate)
    if fim < inicio:
        return ZERO
    return Decimal((fim - inicio).days + 1) / Decimal(dias_no_mes)


class Estacao:
    """A venda mês a mês do ano passado, na memória, para perguntar produto a produto.

    Uma consulta só para a lista inteira: onze mil produtos vezes uma consulta cada
    seria a tela que não abre. O conjunto de produtos entra por SUBCONSULTA, nunca por
    uma lista de dez mil códigos dentro de um `IN`.
    """

    def __init__(self, por_codigo, de, ate, base):
        self._por_codigo = por_codigo
        self._de, self._ate = de, ate
        self._base = base  # os doze meses da média

    @property
    def tem_dado(self):
        return self._por_codigo is not None

    def para(self, codigo, dias_da_janela, hoje):
        """O fator deste produto para uma janela de tantos dias a partir de hoje."""
        if not self.tem_dado or dias_da_janela <= 0:
            return None
        meses = self._por_codigo.get(codigo)
        if not meses:
            return None

        vendidas_no_ano = sum((meses.get(mes, ZERO) for mes in self._base), ZERO)
        if vendidas_no_ano < MINIMO_DE_UNIDADES:
            return None

        de = _um_ano_antes(hoje)
        ate = de + timedelta(days=dias_da_janela - 1)
        if de < self._de or ate > self._ate:
            return None

        na_janela = sum(
            (meses.get(mes, ZERO) * _parte_do_mes(mes[0], mes[1], de, ate)
             for mes in _meses_entre(de, ate)),
            ZERO,
        )
        esperado = vendidas_no_ano / DIAS_DO_ANO * Decimal(dias_da_janela)
        if esperado < MINIMO_NA_JANELA:
            return None

        fator = na_janela / esperado
        if abs(fator - UM) < MARGEM:
            return None
        fator = min(max(fator, PISO), TETO)
        return Fator(codigo=codigo, fator=fator, unidades_na_janela=na_janela,
                     media_esperada=esperado, de=de, ate=ate)


# A janela mais longa que um pedido da lista de compra pede ao ano passado: prazo do
# fornecedor, mais a semana até a próxima compra e a de segurança, com folga.
DIAS_MAXIMOS = 120


def montar(importacao, consulta_de_produtos, hoje=None, dias_maximos=DIAS_MAXIMOS):
    """Lê de uma vez o que o ano passado tem a dizer sobre os produtos da consulta.

    `consulta_de_produtos` é o queryset dos candidatos da lista de compra; entra aqui
    como subconsulta de códigos.
    """
    vazia = Estacao(None, None, None, ())
    if importacao is None:
        return vazia
    hoje = hoje or date.today()

    # A janela mais longa que algum produto pode pedir, um ano atrás.
    de = _um_ano_antes(hoje)
    ate = de + timedelta(days=dias_maximos)
    base = _meses_antes(de.year, de.month, MESES_DE_BASE)
    precisa = base + _meses_entre(de, ate)

    desde = getattr(importacao, "mes_a_mes_desde", None)
    if desde is None or (desde.year, desde.month) > precisa[0]:
        # A foto não guarda inteiro o mês mais antigo de que a conta precisa. Ver
        # comparacao._limites: mês pela metade mente, e aqui mentiria na quantidade.
        return vazia

    linhas = (
        VendaMensalDoProduto.objects
        .filter(importacao=importacao, codigo__in=consulta_de_produtos.values("codigo"))
        .filter(ano__gte=precisa[0][0], ano__lte=precisa[-1][0])
        .values("codigo", "ano", "mes")
        .annotate(unidades=Sum("unidades"))
    )
    desejados = set(precisa)
    por_codigo = {}
    for linha in linhas:
        mes = (linha["ano"], linha["mes"])
        if mes not in desejados:
            continue
        por_codigo.setdefault(linha["codigo"], {})[mes] = linha["unidades"] or ZERO
    return Estacao(por_codigo, de, ate, base)
