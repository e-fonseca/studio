"""O que cada fornecedor vende para a loja: a variedade, e não só o que a loja comprou.

Pedido do Edson em 14/10/2026: "exibir produtos dos fornecedores, assim temos
visibilidade da variedade de produtos de cada fornecedor".

A ficha do fornecedor já mostrava os vinte produtos que mais custaram no ano. Isso
responde "onde foi o dinheiro", e não "o que este fornecedor tem". Variedade é outra
pergunta: quantos produtos, de quantos tipos, quanto disso gira e quanto está parado.

Um aviso que a tela precisa dar, porque o dado engana: `ProdutoImportado.fornecedor` é
o fornecedor da ÚLTIMA COMPRA daquele produto no SET, não um cadastro de quem fornece
o quê. Produto que a loja nunca comprou pelo SET fica sem fornecedor, e produto comprado
de dois fica com o último. Então isto é o catálogo que a loja montou comprando, que é o
que ela tem como memória — e a tela diz isso em vez de deixar a pessoa achar que é o
mostruário do fornecedor.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Case, Count, DecimalField, ExpressionWrapper, F, Q, Sum, When

from apps.compras.sugestoes import so_mercadoria
from apps.core import procura

ZERO = Decimal("0")
# Quantas linhas a tela abre. O resto sai no arquivo: o maior fornecedor da loja tem
# mais de mil produtos, e tabela de mil linhas não é visibilidade, é rolagem.
POR_PAGINA = 100


@dataclass
class GrupoDoFornecedor:
    nome: str
    produtos: int = 0
    com_venda: int = 0
    estoque: Decimal = ZERO
    largura: int = 0

    @property
    def parados(self):
        return self.produtos - self.com_venda


@dataclass
class Catalogo:
    nome: str = ""
    produtos: int = 0
    com_venda: int = 0
    parados: int = 0
    sem_estoque: int = 0
    estoque: Decimal = ZERO
    parado_na_prateleira: Decimal = ZERO
    comprado_12m: Decimal = ZERO
    vendido_12m: Decimal = ZERO
    grupos: list = field(default_factory=list)
    itens: list = field(default_factory=list)
    mostrados: int = 0
    busca: str = ""
    filtro_grupo: str = ""
    nomes_de_grupo: list = field(default_factory=list)
    encontrados: int = 0

    @property
    def tem_itens(self):
        return bool(self.itens)

    @property
    def escondidos(self):
        return max(self.encontrados - self.mostrados, 0)

    @property
    def quantos_grupos(self):
        return len(self.grupos)

    @property
    def filtrando(self):
        return bool(self.busca or self.filtro_grupo)


def _valor_do_estoque():
    """Estoque vezes custo, com o saldo negativo valendo zero.

    Mesma regra do resto do sistema: saldo negativo do SET é erro de cadastro, não
    prateleira devendo dinheiro.
    """
    return ExpressionWrapper(
        Case(When(estoque__gt=0, then=F("estoque") * F("custo")), default=ZERO),
        output_field=DecimalField(max_digits=16, decimal_places=2),
    )


def _grupos(consulta):
    """Os tipos de produto que vêm deste fornecedor, do maior para o menor."""
    linhas = (
        consulta.values("grupo")
        .annotate(
            produtos=Count("id"),
            com_venda=Count("id", filter=Q(vendas_12m__gt=0)),
            estoque=Sum(_valor_do_estoque()),
        )
        .order_by("-produtos", "grupo")
    )
    grupos = [
        GrupoDoFornecedor(
            nome=linha["grupo"] or "Sem grupo no SET",
            produtos=linha["produtos"],
            com_venda=linha["com_venda"],
            estoque=linha["estoque"] or ZERO,
        )
        for linha in linhas
    ]
    maior = max((g.produtos for g in grupos), default=0)
    for grupo in grupos:
        # Inteiro, e não decimal: decimal dentro de style= sai localizado ("66,5%") e o
        # navegador joga a linha fora inteira.
        grupo.largura = int(round(grupo.produtos * 100 / maior)) if maior else 0
    return grupos


def montar(importacao, nome, busca="", grupo="", quantos=POR_PAGINA) -> Catalogo:
    """O catálogo de um fornecedor: os números do conjunto e a lista dos produtos."""
    catalogo = Catalogo(nome=nome, busca=busca, filtro_grupo=grupo)
    if importacao is None or not nome:
        return catalogo

    todos = importacao.itens.filter(fornecedor=nome)
    resumo = todos.aggregate(
        produtos=Count("id"),
        com_venda=Count("id", filter=Q(vendas_12m__gt=0)),
        sem_estoque=Count("id", filter=Q(estoque__lte=0)),
        estoque=Sum(_valor_do_estoque()),
        comprado=Sum("valor_compras_12m"),
        vendido=Sum("receita_12m"),
    )
    catalogo.produtos = resumo["produtos"] or 0
    catalogo.com_venda = resumo["com_venda"] or 0
    catalogo.parados = catalogo.produtos - catalogo.com_venda
    catalogo.sem_estoque = resumo["sem_estoque"] or 0
    catalogo.estoque = resumo["estoque"] or ZERO
    catalogo.comprado_12m = resumo["comprado"] or ZERO
    catalogo.vendido_12m = resumo["vendido"] or ZERO
    if not catalogo.produtos:
        return catalogo

    # O mesmo número que a lista de compra mostra como contrapeso deste fornecedor. Dois
    # números com o mesmo nome e valores diferentes em telas vizinhas é o que faz o dono
    # do sistema parar de confiar nos dois.
    parado = so_mercadoria(todos.filter(estoque__gt=0, vendas_12m__lte=0, custo__gt=0))
    catalogo.parado_na_prateleira = (parado.aggregate(v=Sum(_valor_do_estoque()))["v"] or ZERO)

    catalogo.grupos = _grupos(todos)
    catalogo.nomes_de_grupo = sorted({g.nome for g in catalogo.grupos})

    achados = todos
    if grupo:
        achados = (achados.filter(grupo="") if grupo == "Sem grupo no SET"
                   else achados.filter(grupo=grupo))
    if busca:
        achados = achados.filter(
            procura.filtro(busca, "descricao", "grupo")
            | Q(codigo__istartswith=busca)
            | Q(codigo_barras__istartswith=busca)
        )
    catalogo.encontrados = achados.count()
    achados = procura.por_relevancia(achados, busca, "descricao", "codigo",
                                     desempate=("-receita_12m", "descricao"))
    # `quantos=None` é o arquivo: ele leva tudo o que o filtro achou, como o CSV da
    # lista de compra já fazia.
    catalogo.itens = list(achados if quantos is None else achados[:quantos])
    catalogo.mostrados = len(catalogo.itens)
    return catalogo


def em_linhas(catalogo):
    """O catálogo inteiro em linhas, para o arquivo que se abre no Excel."""
    cabecalho = ("Fornecedor", "Código", "Produto", "Grupo", "Na prateleira",
                 "Custo", "Preço de venda", "Vendeu em 12 meses", "Faturou em 12 meses",
                 "Última venda", "Última compra")
    linhas = [cabecalho]
    for item in catalogo.itens:
        linhas.append((
            catalogo.nome, item.codigo, item.descricao, item.grupo, item.estoque,
            item.custo if item.custo is not None else "",
            item.preco_venda if item.preco_venda is not None else "",
            item.vendas_12m, item.receita_12m,
            item.ultima_venda.strftime("%d/%m/%Y") if item.ultima_venda else "",
            item.ultima_compra.strftime("%d/%m/%Y") if item.ultima_compra else "",
        ))
    return linhas
