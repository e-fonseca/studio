"""Sugestões de compra e de venda, calculadas a partir dos números da própria loja.

O que isto é: cinco listas curtas, cada uma com uma regra escrita em uma linha, saindo
dos dados da última importação. O que isto não é: adivinhação. O servidor da loja não
acessa a internet e não existe palpite vindo de fora; tudo aqui sai de venda, compra,
estoque, custo e preço que já estão no SET.

Por que cinco listas e não uma nota só: a decisão de comprar e a de vender são
diferentes. Uma diz o que repor e o que parar de comprar; a outra diz o que empurrar na
venda e o que precisa sair da prateleira porque está segurando dinheiro.
"""

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum

from apps.fornecedores import servicos as fornecedores

ZERO = Decimal("0")
QUANTOS = 10
# Fora das sugestões: o que não é mercadoria de revenda. CONSUMO PROPRIO é o que a loja
# usa (sacola, papel, café) e DIVERSOS é o produto genérico em que o caixa lança a venda
# avulsa. Os dois sujariam todas as listas com coisa que ninguém decide comprar.
GRUPOS_FORA = ("CONSUMO PROPRIO",)
DESCRICOES_FORA = ("DIVERSOS", "CONSUMO PROPRIO")
# Produto parado: tem na prateleira e não vendeu nenhuma unidade em 12 meses. Não é
# opinião, é o ano inteiro sem uma saída.
MESES_DA_JANELA = 12
# Desconto que o sistema sugere para destravar o que está parado. Não é promoção
# automática: é o quanto dá para tirar do preço e ainda cobrir o custo com folga.
FOLGA_SOBRE_O_CUSTO = Decimal("1.15")

DINHEIRO = DecimalField(max_digits=16, decimal_places=2)


@dataclass
class Linha:
    codigo: str
    descricao: str
    grupo: str = ""
    fornecedor: str = ""
    numero: Decimal = ZERO       # o número que ordena a lista
    valor: Decimal = ZERO        # em reais, quando a linha fala de dinheiro
    detalhe: str = ""            # a frase que explica esta linha
    prazo: int = None


@dataclass
class Bloco:
    chave: str
    titulo: str
    pergunta: str
    regra: str
    acao: str
    coluna: str = "Em dinheiro"   # o que a coluna de dinheiro significa neste bloco
    # A frase do resumo vem partida porque o valor entra no meio dela, em negrito:
    # "<quantos> <antes> <R$ total> <depois>".
    frase_antes: str = ""
    frase_depois: str = ""
    linhas: list = field(default_factory=list)
    total: Decimal = ZERO
    quantos: int = 0

    @property
    def vazio(self):
        return not self.linhas


@dataclass
class Sugestoes:
    blocos: list = field(default_factory=list)
    data_corte: object = None
    produtos: int = 0


def so_mercadoria(consulta):
    """Tira da consulta o que não é mercadoria de revenda.

    Público porque o Dashboard precisa da mesma definição: sem ela, o "Parado sem vender"
    de lá contava o consumo próprio da loja e dava R$ 4,9 mil a mais que o "O que fazer
    agora" e a tela de Sugestões, para o mesmo nome.
    """
    for grupo in GRUPOS_FORA:
        consulta = consulta.exclude(grupo__startswith=grupo)
    for descricao in DESCRICOES_FORA:
        consulta = consulta.exclude(descricao__startswith=descricao)
    return consulta


def e_mercadoria(grupo, descricao):
    """A mesma regra do `so_mercadoria`, para quem já tem a linha na mão.

    Existe porque a tela de margem calcula produto a produto em Python, e precisa da
    mesma definição de "é mercadoria de revenda" que a lista de compra usa no banco.
    """
    grupo = (grupo or "").upper()
    descricao = (descricao or "").upper()
    return not (any(grupo.startswith(fora) for fora in GRUPOS_FORA)
                or any(descricao.startswith(fora) for fora in DESCRICOES_FORA))


def _reais(valor):
    return (valor or ZERO).quantize(Decimal("0.01"))


def _dinheiro(valor):
    """R$ 1.234,56, que é como se escreve dinheiro aqui. O filtro reais faz o mesmo no template."""
    texto = f"{(valor or ZERO):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def _quantidade(valor):
    texto = f"{(valor or ZERO):f}".rstrip("0").rstrip(".")
    return (texto or "0").replace(".", ",")


def _repor(importacao, prazos):
    """Zerou e continua vendendo: é venda que a loja está perdendo todo dia."""
    bloco = Bloco(
        chave="repor",
        titulo="Repor agora",
        pergunta="O que a loja está deixando de vender por falta?",
        regra="Produtos que estão zerados (ou negativos) no SET, não têm pedido a caminho e "
              "venderam nos últimos 90 dias.",
        acao="Comece por estes no próximo pedido ao fornecedor.",
        coluna="Vendeu em 12 meses",
        frase_antes="produtos zerados que continuam vendendo. No último ano eles venderam",
        frase_depois=".",
    )
    consulta = so_mercadoria(
        importacao.itens.filter(vendas_90d__gt=0, estoque__lte=0, pedido_em_aberto__lte=0)
    )
    for produto in consulta.order_by("-receita_12m")[:QUANTOS]:
        prazo = prazos.get((produto.fornecedor or "").strip()) or produto.prazo_reposicao_dias
        bloco.linhas.append(Linha(
            codigo=produto.codigo,
            descricao=produto.descricao,
            grupo=produto.grupo,
            fornecedor=produto.fornecedor,
            numero=produto.vendas_90d,
            valor=_reais(produto.receita_12m),
            prazo=prazo,
            detalhe=f"Vendeu {_quantidade(produto.vendas_90d)} nos últimos 90 dias e está zerado.",
        ))
    bloco.quantos = consulta.count()
    bloco.total = _reais(consulta.aggregate(v=Sum("receita_12m"))["v"] or ZERO)
    return bloco


def _parar_de_comprar(importacao):
    """Entrou no ano e não saiu nenhuma unidade: é o dinheiro que a compra errou."""
    bloco = Bloco(
        chave="parar",
        titulo="Parar de comprar",
        pergunta="Que compra do último ano não virou venda nenhuma?",
        regra="Produtos comprados nos últimos 12 meses que não venderam uma única unidade "
              "no mesmo período.",
        acao="Não repor nenhum destes sem um pedido de cliente na mão.",
        coluna="Custou à loja",
        frase_antes="produtos entraram no ano e não venderam nada. Comprá-los custou",
        frase_depois=".",
    )
    consulta = so_mercadoria(importacao.itens.filter(valor_compras_12m__gt=0, vendas_12m__lte=0))
    for produto in consulta.order_by("-valor_compras_12m")[:QUANTOS]:
        bloco.linhas.append(Linha(
            codigo=produto.codigo,
            descricao=produto.descricao,
            grupo=produto.grupo,
            fornecedor=produto.fornecedor,
            numero=produto.compras_12m,
            valor=_reais(produto.valor_compras_12m),
            detalhe=(f"Entraram {_quantidade(produto.compras_12m)} no ano e saiu zero."
                     + (f" Último fornecedor: {produto.fornecedor}." if produto.fornecedor else "")),
        ))
    bloco.quantos = consulta.count()
    bloco.total = _reais(consulta.aggregate(v=Sum("valor_compras_12m"))["v"] or ZERO)
    return bloco


def _destravar(importacao):
    """Tem na prateleira, não vende e está segurando dinheiro: é promoção ou devolução."""
    bloco = Bloco(
        chave="destravar",
        titulo="Pôr para girar",
        pergunta="Que mercadoria está parada segurando dinheiro?",
        regra="Produtos com saldo na prateleira e nenhuma venda em 12 meses, do que vale "
              "mais dinheiro parado para o que vale menos.",
        acao="Promoção, vitrine ou combinação com o que vende. O preço mínimo está na coluna do meio.",
        coluna="Parado ao custo",
        frase_antes="produtos parados na prateleira, segurando",
        frase_depois="ao custo.",
    )
    parado = ExpressionWrapper(F("estoque") * F("custo"), output_field=DINHEIRO)
    consulta = (
        so_mercadoria(importacao.itens.filter(estoque__gt=0, vendas_12m__lte=0, custo__gt=0))
        .annotate(valor_parado=parado)
    )
    for produto in consulta.order_by("-valor_parado")[:QUANTOS]:
        minimo = _reais((produto.custo or ZERO) * FOLGA_SOBRE_O_CUSTO)
        preco = produto.preco_venda
        if preco and preco > 0:
            detalhe = (f"{_quantidade(produto.estoque)} parados. Hoje a {_dinheiro(preco)}; "
                       f"dá para vender a partir de {_dinheiro(minimo)} e ainda cobrir o custo.")
        else:
            detalhe = f"{_quantidade(produto.estoque)} parados, sem preço de venda no SET."
        bloco.linhas.append(Linha(
            codigo=produto.codigo,
            descricao=produto.descricao,
            grupo=produto.grupo,
            fornecedor=produto.fornecedor,
            numero=produto.estoque,
            valor=_reais(produto.valor_parado),
            detalhe=detalhe,
        ))
    bloco.quantos = consulta.count()
    bloco.total = _reais(consulta.aggregate(v=Sum("valor_parado"))["v"] or ZERO)
    return bloco


def _empurrar_na_venda(importacao):
    """O que já vende e ainda tem margem: é onde o esforço de venda rende mais."""
    bloco = Bloco(
        chave="empurrar",
        titulo="Empurrar na venda",
        pergunta="Onde o esforço do balcão rende mais?",
        regra="Produtos que venderam nos últimos 90 dias e têm boa margem, ordenados pelo "
              "lucro que a venda de 90 dias já trouxe.",
        acao="É o que vale oferecer primeiro e deixar à vista.",
        coluna="Lucro em 90 dias",
    )
    lucro = ExpressionWrapper(
        (F("preco_venda") - F("custo")) * F("vendas_90d"), output_field=DINHEIRO
    )
    consulta = (
        so_mercadoria(importacao.itens.filter(vendas_90d__gt=0, custo__gt=0, preco_venda__gt=0,
                                            estoque__gt=0))
        .filter(preco_venda__gt=F("custo"))
        .annotate(lucro_90d=lucro)
    )
    for produto in consulta.order_by("-lucro_90d")[:QUANTOS]:
        margem = produto.preco_venda - produto.custo
        porcento = int(margem / produto.custo * 100) if produto.custo else 0
        bloco.linhas.append(Linha(
            codigo=produto.codigo,
            descricao=produto.descricao,
            grupo=produto.grupo,
            fornecedor=produto.fornecedor,
            numero=produto.vendas_90d,
            valor=_reais(produto.lucro_90d),
            detalhe=(f"{_quantidade(produto.vendas_90d)} vendidos em 90 dias, "
                     f"margem de {porcento}% sobre o custo, {_quantidade(produto.estoque)} na prateleira."),
        ))
    bloco.quantos = consulta.count()
    return bloco


def _renegociar(importacao):
    """Fornecedor de quem entrou muito e vendeu pouco: é com quem a conversa precisa mudar."""
    bloco = Bloco(
        chave="renegociar",
        titulo="Conversar com o fornecedor",
        pergunta="De quem a loja comprou e não conseguiu vender?",
        regra="Soma, por fornecedor, do que entrou nos últimos 12 meses e não vendeu "
              "nenhuma unidade.",
        acao="Pedir devolução, troca ou prazo maior antes do próximo pedido.",
        coluna="Comprado sem venda",
        frase_antes="fornecedores venderam à loja mercadoria que não saiu, somando",
        frase_depois=".",
    )
    por_fornecedor = (
        so_mercadoria(importacao.itens.filter(valor_compras_12m__gt=0, vendas_12m__lte=0))
        .exclude(fornecedor="")
        .values("fornecedor")
        .annotate(parado=Sum("valor_compras_12m"), itens=Sum("compras_12m"))
        .order_by("-parado")
    )
    prazos = fornecedores.prazos_informados()
    for linha in por_fornecedor[:QUANTOS]:
        bloco.linhas.append(Linha(
            codigo="",
            descricao=linha["fornecedor"],
            fornecedor=linha["fornecedor"],
            numero=linha["itens"] or ZERO,
            valor=_reais(linha["parado"]),
            prazo=prazos.get(linha["fornecedor"]),
            detalhe=f"{_quantidade(linha['itens'])} unidades compradas dele no ano sem nenhuma venda.",
        ))
    # A conta é de todos os fornecedores, não só dos dez que aparecem.
    todos = list(por_fornecedor)
    bloco.quantos = len(todos)
    bloco.total = _reais(sum((linha["parado"] or ZERO for linha in todos), ZERO))
    return bloco


def montar(importacao):
    """As cinco listas, na ordem em que a gerência decide: comprar, parar, girar, vender, cobrar."""
    sugestoes = Sugestoes()
    if importacao is None:
        return sugestoes
    sugestoes.data_corte = importacao.data_corte
    sugestoes.produtos = importacao.produtos
    prazos = fornecedores.prazos_informados()
    sugestoes.blocos = [
        _repor(importacao, prazos),
        _parar_de_comprar(importacao),
        _destravar(importacao),
        _empurrar_na_venda(importacao),
        _renegociar(importacao),
    ]
    return sugestoes
