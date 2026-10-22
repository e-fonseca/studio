"""Visão geral: a tela que mostra, de relance, se a loja está sob controle.

É a tela para quem não vai abrir nenhuma outra. Por isso ela responde cinco perguntas e
mais nenhuma: quanto a loja vendeu, quanto comprou, quanto está parado na prateleira, o
que mais sai e o que não sai, e com quem a loja compra. Cada número traz a frase que
explica de onde ele veio, porque número sem explicação não convence ninguém.

Tudo vem da última importação concluída; nada é digitado. As únicas informações que a
gerência preenche à mão são o prazo e a reputação do fornecedor, e elas aparecem marcadas
como tal.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from apps.core.templatetags.cabana import reais
from apps.financeiro import servicos as financeiro
from apps.fornecedores import servicos as fornecedores

from . import ticket
from .indicadores import MESES, _meses, _porcentagem

ZERO = Decimal("0")
QUANTOS_PRODUTOS = 10
QUANTOS_FORNECEDORES = 8
QUANTOS_GRUPOS = 6
# Cores da fatia do gráfico de rosca, na ordem. São tokens do CSS, não cores soltas.
CORES_GRUPO = ("--cor-primaria", "--cor-brasa", "--cor-sucesso", "--cor-alerta", "--cor-foco", "--cor-borda-forte")


@dataclass
class Cartao:
    """Um número grande com o que ele significa embaixo."""

    chave: str
    titulo: str
    valor: Decimal
    rodape: str
    icone: str = ""
    nivel: str = "neutro"  # neutro, bom, atencao, ruim


@dataclass
class ProdutoLinha:
    descricao: str
    grupo: str
    fornecedor: str
    valor: Decimal
    unidades: Decimal
    estoque: Decimal
    ultima_venda: object = None
    largura: int = 0


@dataclass
class VisaoGeral:
    importacao: object
    cartoes: list = field(default_factory=list)
    meses: list = field(default_factory=list)
    mais_vendidos: list = field(default_factory=list)
    menos_vendidos: list = field(default_factory=list)
    sem_venda: int = 0
    grupos: list = field(default_factory=list)
    fornecedores: list = field(default_factory=list)
    sem_reputacao: int = 0
    faturamento_12m: Decimal = ZERO
    compras_12m: Decimal = ZERO
    ticket: object = None            # o recorte de 12 meses, para o cartão e o resumo
    melhor_dia: object = None        # o dia da semana que mais fatura
    melhor_forma: object = None      # a forma de pagamento com o maior ticket
    fatia_do_fim_de_semana: int = 0


def _largura(linhas):
    maior = max((linha.valor for linha in linhas), default=ZERO)
    for linha in linhas:
        linha.largura = _porcentagem(linha.valor, maior)
    return linhas


def _linha(produto, valor, unidades):
    return ProdutoLinha(
        descricao=produto.descricao or produto.codigo,
        grupo=produto.grupo,
        fornecedor=produto.fornecedor,
        valor=Decimal(valor or 0).quantize(Decimal("0.01")),
        unidades=produto.vendas_12m or ZERO,
        estoque=produto.estoque or ZERO,
        ultima_venda=produto.ultima_venda,
    )


def montar(importacao, hoje=None) -> VisaoGeral:
    if importacao is None:
        return VisaoGeral(importacao=None)

    produtos = list(importacao.itens.all())
    faturamento = sum((p.receita_12m or ZERO for p in produtos), ZERO)
    compras = sum((p.valor_compras_12m or ZERO for p in produtos), ZERO)
    # Saldo negativo vale zero, nunca dinheiro a menos: é erro de cadastro de uma loja
    # que nunca contou a prateleira. É a mesma regra do apps/compras/calculos.py e do
    # limite.py; somar o negativo tirava R$ 126 mil deste cartão e fazia a Visão geral
    # discordar do resto do sistema.
    estoque = sum((max(p.estoque or ZERO, ZERO) * (p.custo or ZERO) for p in produtos), ZERO)
    com_saldo_negativo = sum(1 for p in produtos if (p.estoque or ZERO) < ZERO)

    visao = VisaoGeral(importacao=importacao, faturamento_12m=faturamento, compras_12m=compras)

    # Produtos: o que mais sai e o que, vendendo, menos sai. Produto que nunca vendeu fica
    # fora da lista dos menos vendidos e vira uma contagem à parte, senão a lista enche de
    # item morto e esconde o que está apenas devagar.
    com_venda = [p for p in produtos if (p.receita_12m or ZERO) > ZERO]
    visao.sem_venda = sum(1 for p in produtos if (p.vendas_12m or ZERO) <= ZERO)
    por_receita = sorted(com_venda, key=lambda p: -(p.receita_12m or ZERO))
    visao.mais_vendidos = _largura(
        [_linha(p, p.receita_12m, p.vendas_12m) for p in por_receita[:QUANTOS_PRODUTOS]]
    )
    visao.menos_vendidos = _largura(
        [_linha(p, p.receita_12m, p.vendas_12m) for p in por_receita[-QUANTOS_PRODUTOS:][::-1]]
    )

    # Participação por grupo de produto, para o gráfico de rosca.
    por_grupo = {}
    for produto in produtos:
        por_grupo[produto.grupo or "SEM GRUPO"] = por_grupo.get(produto.grupo or "SEM GRUPO", ZERO) + (
            produto.receita_12m or ZERO)
    ordenados = sorted(por_grupo.items(), key=lambda item: -item[1])
    principais = ordenados[:QUANTOS_GRUPOS]
    resto = sum((valor for _, valor in ordenados[QUANTOS_GRUPOS:]), ZERO)
    if resto > ZERO:
        principais.append(("OUTROS", resto))
    inicio = Decimal("0")
    for posicao, (nome, valor) in enumerate(principais):
        fatia = (valor / faturamento * 100) if faturamento else ZERO
        # dasharray e dashoffset já saem prontos: a rosca do SVG é um círculo de
        # circunferência 100, onde cada fatia é um traço do tamanho da porcentagem. O 25 do
        # offset gira o começo para o topo, em vez das três horas.
        visao.grupos.append({
            "nome": nome.title(),
            "valor": valor.quantize(Decimal("0.01")),
            "fatia": fatia.quantize(Decimal("0.1")),
            "cor": CORES_GRUPO[posicao % len(CORES_GRUPO)],
            "traco": f"{fatia:.1f} {100 - fatia:.1f}",
            "giro": f"{25 - inicio:.1f}",
        })
        inicio += fatia

    resumos = fornecedores.resumir(importacao)
    visao.fornecedores = resumos[:QUANTOS_FORNECEDORES]
    visao.sem_reputacao = sum(1 for r in resumos if r.precisa_de_reputacao)
    visao.meses = _meses(importacao.detalhe or {})

    # Ticket médio na tela principal (pedido do Edson, 07/10/2026). A tela cheia continua
    # existindo com os filtros; aqui fica o número e as duas leituras que ele já rendeu.
    visao.ticket = ticket.calcular(importacao)
    if visao.ticket.tem_dados:
        fim_de_semana = sum((linha.faturamento for linha in visao.ticket.por_dia_da_semana
                             if linha.chave in ("0", "6")), ZERO)
        if visao.ticket.total.faturamento:
            visao.fatia_do_fim_de_semana = int(
                fim_de_semana * 100 / visao.ticket.total.faturamento)
        visao.melhor_dia = max(visao.ticket.por_dia_da_semana,
                               key=lambda l: l.faturamento, default=None)
        comparaveis = [l for l in visao.ticket.por_forma if not l.pouco_para_comparar]
        visao.melhor_forma = max(comparaveis, key=lambda l: l.ticket, default=None)

    resumo_caixa = financeiro.resumir(importacao, hoje=hoje)
    visao.cartoes = [
        Cartao("faturamento", "Vendido em 12 meses", faturamento,
               f"{importacao.dias_abertos_12m or 0} dias com venda registrada."
               + _texto_do_desconto(visao, faturamento), "venda", "bom"),
        Cartao("compras", "Comprado em 12 meses", compras,
               _comparacao(faturamento, compras), "compra",
               "ruim" if compras > faturamento else "neutro"),
        Cartao("estoque", "Parado na prateleira hoje", estoque,
               f"{_milhar(len(produtos))} produtos cadastrados, {_milhar(visao.sem_venda)} "
               "sem nenhuma venda no ano."
               + (f" {_milhar(com_saldo_negativo)} estão com saldo negativo no SET e contam "
                  "como zero." if com_saldo_negativo else ""),
               "estoque", "atencao" if visao.sem_venda else "neutro"),
        Cartao("caixa", "Já comprometido do caixa", resumo_caixa.compromisso_total,
               _texto_do_caixa(resumo_caixa), "caixa",
               "ruim" if resumo_caixa.vencidas.quantidade else "neutro"),
        Cartao("ticket", "Ticket médio da venda", visao.ticket.total.ticket,
               _texto_do_ticket(visao), "ticket", "neutro"),
    ]
    return visao


def _comparacao(faturamento, compras):
    if not faturamento:
        return "Sem venda registrada no período."
    fatia = (compras / faturamento * 100).quantize(Decimal("0.1"))
    if compras > faturamento:
        return f"Saiu mais em compra do que entrou em venda: {fatia}% do faturamento."
    return f"Equivale a {fatia}% de tudo o que a loja vendeu."


def _texto_do_caixa(resumo):
    if resumo.vencidas.quantidade:
        return (f"{resumo.vencidas.quantidade} conta"
                f"{'s' if resumo.vencidas.quantidade != 1 else ''} já vencida"
                f"{'s' if resumo.vencidas.quantidade != 1 else ''} no SET.")
    return "Nenhuma conta vencida no SET."


def _texto_do_desconto(visao, faturamento):
    """Por que este número não é igual ao Faturamento do Dashboard.

    Aqui a soma é do item da venda (o preço de tabela do que saiu da prateleira); lá é o
    total da venda, que é o que o cliente pagou depois do desconto do balcão. Os dois
    estão certos e um é maior que o outro, então a diferença fica escrita, senão as duas
    telas parecem brigar.
    """
    if visao.ticket is None or not visao.ticket.tem_dados:
        return ""
    entrou = visao.ticket.total.faturamento
    if not entrou or entrou >= faturamento:
        return ""
    return (f" É o preço dos itens vendidos; com o desconto dado no balcão, "
            f"entraram {reais(entrou)}.")


def _milhar(numero):
    """1456 vira "1.456". Número de quatro dígitos sem ponto se lê errado de relance."""
    return f"{int(numero):,}".replace(",", ".")


def _texto_do_ticket(visao):
    if visao.ticket is None or not visao.ticket.tem_dados:
        return "Sem venda registrada no período."
    quantas = _milhar(visao.ticket.total.vendas)
    if visao.fatia_do_fim_de_semana:
        return (f"{quantas} vendas em 12 meses, e {visao.fatia_do_fim_de_semana}% do "
                "faturamento sai no fim de semana.")
    return f"{quantas} vendas em 12 meses."
