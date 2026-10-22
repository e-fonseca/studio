"""Consulta das compras: a última de cada fornecedor e o que veio em cada uma.

A pergunta que isto responde é a da gerência olhando o fornecedor na frente: "quando
foi a última vez que compramos dele, quanto foi e o que veio na nota". O painel soma
doze meses; aqui a compra aparece inteira, uma a uma, do jeito que foi lançada no SET.

Compra com situação Pendente no SET é mercadoria a caminho, não compra feita. Ela
aparece separada, porque confundir as duas faz a loja comprar de novo o que já vem.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.db.models import Count, F, Q, Sum
from django.db.models.functions import Coalesce

from apps.importacao.models import CompraImportada

ZERO = Decimal("0")
QUANTAS_COMPRAS = 60


@dataclass
class UltimaDoFornecedor:
    """O resumo de um fornecedor na tela: a última compra e o acumulado dele."""

    nome: str
    compra: CompraImportada = None
    compras: int = 0
    total: Decimal = ZERO
    pendentes: int = 0
    dias_sem_comprar: int = None

    @property
    def nunca_comprado(self):
        return self.compra is None


@dataclass
class Resultado:
    fornecedores: list = field(default_factory=list)
    compras: list = field(default_factory=list)
    total_de_compras: int = 0
    procurado: str = ""
    fornecedor: str = ""


def _consulta(importacao):
    return CompraImportada.objects.filter(importacao=importacao)


def ultima_de_cada_fornecedor(importacao, hoje=None):
    """Um registro por fornecedor, do que comprou mais recentemente para o mais parado."""
    if importacao is None:
        return []
    hoje = hoje or date.today()
    resumos = (
        _consulta(importacao)
        .exclude(fornecedor="")
        .values("fornecedor")
        .annotate(
            compras=Count("id"),
            total=Sum("valor_total"),
            pendentes=Count("id", filter=Q(pendente=True)),
        )
    )
    # A compra mais nova de cada fornecedor, pela data que vale.
    todas = list(
        _consulta(importacao)
        .exclude(fornecedor="")
        .annotate(quando=Coalesce("data_nota", "data_pedido"))
    )
    ultimas = {}
    for compra in todas:
        atual = ultimas.get(compra.fornecedor)
        if atual is None or (compra.quando or date.min) > (atual.quando or date.min):
            ultimas[compra.fornecedor] = compra
    linhas = []
    for resumo in resumos:
        compra = ultimas.get(resumo["fornecedor"])
        linha = UltimaDoFornecedor(
            nome=resumo["fornecedor"],
            compra=compra,
            compras=resumo["compras"],
            total=resumo["total"] or ZERO,
            pendentes=resumo["pendentes"],
        )
        if compra is not None and compra.data:
            linha.dias_sem_comprar = (hoje - compra.data).days
        linhas.append(linha)
    # Sem data a compra vai para o fim: é registro antigo e não ajuda a decidir nada.
    linhas.sort(key=lambda l: (l.dias_sem_comprar is None, l.dias_sem_comprar or 0))
    return linhas


def compras(importacao, fornecedor="", procurado="", quantas=QUANTAS_COMPRAS):
    """As compras em si, da mais nova para a mais velha, com filtro por fornecedor."""
    if importacao is None:
        return [], 0
    consulta = _consulta(importacao)
    if fornecedor:
        consulta = consulta.filter(fornecedor__iexact=fornecedor)
    if procurado:
        consulta = consulta.filter(
            Q(fornecedor__icontains=procurado)
            | Q(numero__icontains=procurado)
            | Q(nota_fiscal__icontains=procurado)
        )
    total = consulta.count()
    # Pela data que a loja reconhece (a da nota, senão a do pedido), e não pelo id: o SET
    # lança compra atrasada, então o id mais alto nem sempre é a compra mais nova.
    consulta = consulta.annotate(quando=Coalesce("data_nota", "data_pedido"))
    return list(consulta.order_by(F("quando").desc(nulls_last=True), "-id_set")[:quantas]), total


def uma(importacao, id_set):
    """Uma compra com os itens dela, para a tela de detalhe."""
    if importacao is None:
        return None
    return (
        _consulta(importacao)
        .filter(id_set=id_set)
        .prefetch_related("linhas")
        .first()
    )


def montar(importacao, fornecedor="", procurado="", hoje=None):
    lista, total = compras(importacao, fornecedor=fornecedor, procurado=procurado)
    return Resultado(
        fornecedores=ultima_de_cada_fornecedor(importacao, hoje=hoje),
        compras=lista,
        total_de_compras=total,
        procurado=procurado,
        fornecedor=fornecedor,
    )
