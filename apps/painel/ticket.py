"""Ticket médio de venda: quanto o cliente gasta por compra, com filtros.

A conta é uma só: faturamento dividido pelo número de vendas. O que muda é o
recorte — período, forma de pagamento, vendedor e dia da semana —, e é por isso
que a importação guarda venda a venda em vez de só a soma do mês.

Venda estornada já fica de fora na importação. Venda com valor zero existiria se
houvesse, e entraria na contagem: ela é uma venda que a loja fez.
"""

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Count, Max, Sum
from django.db.models.functions import TruncMonth

from apps.importacao.models import VendaImportada

ZERO = Decimal("0")

# (valor na URL, rótulo na tela, dias para trás; None é tudo o que foi importado)
PERIODOS = (
    ("12m", "12 meses", 365),
    ("90d", "90 dias", 90),
    ("30d", "30 dias", 30),
    ("7d", "7 dias", 7),
)
PERIODO_PADRAO = "12m"

DIAS_DA_SEMANA = (
    (0, "Domingo"), (1, "Segunda"), (2, "Terça"), (3, "Quarta"),
    (4, "Quinta"), (5, "Sexta"), (6, "Sábado"),
)
NOME_DO_DIA = dict(DIAS_DA_SEMANA)

# Abaixo disso o recorte não diz nada: dois ou três clientes mudam a média inteira.
MINIMO_PARA_COMPARAR = 20


@dataclass
class Recorte:
    """Um corte qualquer das vendas: o nome dele, quantas vendas e o ticket."""

    rotulo: str
    vendas: int = 0
    faturamento: Decimal = ZERO
    chave: str = ""

    @property
    def ticket(self):
        if not self.vendas:
            return ZERO
        return (self.faturamento / self.vendas).quantize(Decimal("0.01"))

    @property
    def pouco_para_comparar(self):
        return 0 < self.vendas < MINIMO_PARA_COMPARAR


@dataclass
class Resultado:
    periodo: str = PERIODO_PADRAO
    rotulo_periodo: str = ""
    desde = None
    ate = None
    total: Recorte = field(default_factory=lambda: Recorte("Tudo no período"))
    desconto_medio: Decimal = ZERO
    maior_venda: Decimal = ZERO
    por_mes: list = field(default_factory=list)
    por_dia_da_semana: list = field(default_factory=list)
    por_forma: list = field(default_factory=list)
    por_vendedor: list = field(default_factory=list)
    vendas_sem_vendedor: int = 0
    formas: list = field(default_factory=list)
    vendedores: list = field(default_factory=list)
    filtro_forma: str = ""
    filtro_vendedor: str = ""
    filtro_dia: str = ""

    @property
    def tem_dados(self):
        return self.total.vendas > 0


def _dias(periodo):
    for valor, _rotulo, dias in PERIODOS:
        if valor == periodo:
            return dias
    return 365


def _rotulo(periodo):
    for valor, rotulo, _dias in PERIODOS:
        if valor == periodo:
            return rotulo
    return "12 meses"


def _recorte(consulta, rotulo, chave=""):
    agregado = consulta.aggregate(n=Count("id"), soma=Sum("valor"))
    return Recorte(rotulo=rotulo, chave=chave,
                   vendas=agregado["n"] or 0, faturamento=agregado["soma"] or ZERO)


def calcular(importacao, periodo=PERIODO_PADRAO, forma="", vendedor="", dia=""):
    """Os números do ticket médio para o recorte pedido.

    Os filtros valem para os números do topo e para todas as quebras: olhar o ticket
    do PIX por dia da semana é exatamente o tipo de pergunta que a tela existe para
    responder. As listas de opções, porém, saem do período inteiro, senão filtrar por
    uma forma de pagamento faria as outras sumirem da caixa de seleção.
    """
    resultado = Resultado(periodo=periodo if periodo in dict((p, r) for p, r, _ in PERIODOS) else PERIODO_PADRAO)
    resultado.rotulo_periodo = _rotulo(resultado.periodo)
    if importacao is None or importacao.data_corte is None:
        return resultado

    resultado.ate = importacao.data_corte
    resultado.desde = importacao.data_corte - timedelta(days=_dias(resultado.periodo))
    do_periodo = VendaImportada.objects.filter(
        importacao=importacao, data__gt=resultado.desde, data__lte=resultado.ate)

    # As opções de filtro saem do período inteiro, antes de aplicar os filtros.
    resultado.formas = [
        linha["forma_pagamento"] for linha in
        do_periodo.exclude(forma_pagamento="").values("forma_pagamento")
        .annotate(n=Count("id")).order_by("-n")
    ]
    resultado.vendedores = [
        linha["vendedor"] for linha in
        do_periodo.exclude(vendedor="").values("vendedor").annotate(n=Count("id")).order_by("-n")
    ]

    filtradas = do_periodo
    if forma and forma in resultado.formas:
        filtradas = filtradas.filter(forma_pagamento=forma)
        resultado.filtro_forma = forma
    if vendedor and vendedor in resultado.vendedores:
        filtradas = filtradas.filter(vendedor=vendedor)
        resultado.filtro_vendedor = vendedor
    if dia != "" and str(dia).isdigit() and int(dia) in NOME_DO_DIA:
        filtradas = filtradas.filter(dia_da_semana=int(dia))
        resultado.filtro_dia = str(dia)

    resultado.total = _recorte(filtradas, "Tudo no período")
    extras = filtradas.aggregate(desconto=Avg("desconto"), maior=Max("valor"))
    resultado.desconto_medio = (extras["desconto"] or ZERO).quantize(Decimal("0.01"))
    resultado.maior_venda = extras["maior"] or ZERO

    resultado.por_mes = _quebrar_por_mes(filtradas)
    resultado.por_dia_da_semana = _quebrar(
        filtradas, "dia_da_semana", lambda v: NOME_DO_DIA.get(v, str(v)), ordenar_por_chave=True)
    resultado.por_forma = _quebrar(filtradas, "forma_pagamento", lambda v: v or "Não informada")
    resultado.por_vendedor = _quebrar(
        filtradas.exclude(vendedor=""), "vendedor", lambda v: v)
    resultado.vendas_sem_vendedor = filtradas.filter(vendedor="").count()
    return resultado


def _quebrar(consulta, campo, rotular, ordenar_por_chave=False):
    linhas = [
        Recorte(rotulo=rotular(linha[campo]), chave=str(linha[campo]),
                vendas=linha["n"], faturamento=linha["soma"] or ZERO)
        for linha in consulta.values(campo).annotate(n=Count("id"), soma=Sum("valor"))
    ]
    if ordenar_por_chave:
        return sorted(linhas, key=lambda r: int(r.chave))
    return sorted(linhas, key=lambda r: r.faturamento, reverse=True)


def _quebrar_por_mes(consulta):
    return [
        Recorte(rotulo=f"{linha['mes']:%m/%Y}", chave=f"{linha['mes']:%Y-%m}",
                vendas=linha["n"], faturamento=linha["soma"] or ZERO)
        for linha in consulta.annotate(mes=TruncMonth("data")).values("mes")
        .annotate(n=Count("id"), soma=Sum("valor")).order_by("mes")
    ]
