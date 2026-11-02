"""Cálculo de reposição e diagnóstico de compras (briefing, seção 9).

Regras determinísticas, sem IA e sem acesso a banco: recebem números já
importados dos relatórios e devolvem o resultado com o motivo e os dados usados,
para que qualquer pessoa consiga refazer a conta.

Unidades: quantidades em unidades do produto, prazos em dias corridos,
valores em reais (Decimal). Demanda zero nunca vira divisão por zero.

Saldo negativo conta como zero na compra, e só na compra: ver o comentário dentro de
`calcular`. É a regra que mais muda o número que vai ao fornecedor.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

ZERO = Decimal("0")
UM = Decimal("1")
CENTAVO = Decimal("0.01")
DUAS_CASAS = Decimal("0.01")


def _d(valor):
    if valor is None:
        return None
    return valor if isinstance(valor, Decimal) else Decimal(str(valor))


def reais(valor):
    return None if valor is None else _d(valor).quantize(CENTAVO, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Parametros:
    """Parâmetros da política de compra. Valores padrão são ponto de partida, a aprovar pela gestão."""

    horizonte_revisao_dias: int = 7  # importação semanal: a próxima chance de comprar é daqui a 7 dias
    dias_seguranca: Decimal = Decimal("7")  # estoque de segurança expresso em dias de demanda
    excesso_cobertura_dias: int = 180  # acima disso, o item é considerado em excesso
    dias_minimos_historico: int = 28  # menos que isso: confiança baixa
    dias_dados_vencidos: int = 10  # data de corte mais antiga que isso: dados vencidos
    # Quantos dias a mais o ponto de pedido olha para a frente. Zero na lista de compra,
    # que é revista toda semana. A compra guiada (apps/compras/guiada.py) pergunta quando
    # a pessoa volta a comprar do fornecedor; se é daqui a um mês, entra também o que
    # acaba antes de a compra SEGUINTE chegar, e não só o que acaba antes desta.
    antecipar_dias: int = 0


@dataclass(frozen=True)
class Item:
    sku: str
    descricao: str
    # O saldo como o SET conta, inclusive abaixo de zero: quem recebe o número não o
    # conserta antes. Quem o trata é a conta da compra, e o resultado diz o que tratou.
    estoque_utilizavel: Decimal
    vendas_liquidas: Decimal  # unidades vendidas menos devoluções na janela
    dias_janela: int  # dias elegíveis (loja aberta) da janela de vendas
    prazo_reposicao_dias: int | None = None
    custo_unitario: Decimal | None = None
    recebimentos_pendentes: Decimal = ZERO  # pedidos confirmados ainda não recebidos
    reservas_nao_deduzidas: Decimal = ZERO  # reservas que o estoque importado ainda não descontou
    lote_minimo: Decimal = ZERO
    multiplo: Decimal = Decimal("1")
    dias_em_ruptura: int = 0  # dias da janela com estoque zerado
    comprado_na_janela: Decimal = ZERO  # unidades compradas no mesmo período
    estoque_minimo_manual: Decimal | None = None
    # Quantas vezes a média o MESMO PERÍODO do ano passado vendeu (apps/compras/estacao.py).
    # Entra só na decisão de comprar: a loja vende por estação e a média plana de doze
    # meses manda comprar de menos antes da estação e de mais depois que ela passou.
    fator_de_estacao: Decimal = Decimal("1")


@dataclass
class Resultado:
    sku: str
    descricao: str
    demanda_diaria: Decimal
    # A demanda que decidiu a compra: a diária vezes o fator do ano passado. Fica
    # separada da diária porque cobertura e excesso continuam saindo da média plana.
    demanda_do_pedido: Decimal
    fator_de_estacao: Decimal
    # O que a conta daria sem o ajuste do ano passado. Igual à sugestão quando não houve.
    compra_sem_estacao: Decimal
    cobertura_dias: Decimal | None
    cobertura_texto: str
    posicao_estoque: Decimal
    # Quanto de saldo NEGATIVO a conta de compra desprezou. Zero na esmagadora maioria
    # das linhas; quando não é, a tela tem que dizer, senão TEM -69 e COMPRAR 1 na mesma
    # linha não fecham e o número perde a confiança de quem compra.
    saldo_negativo_desprezado: Decimal
    ponto_reposicao: Decimal | None
    estoque_alvo: Decimal | None
    compra_sugerida: Decimal
    custo_compra: Decimal | None
    valor_estoque: Decimal | None
    situacao: str
    excesso_unidades: Decimal
    valor_excesso: Decimal | None
    comprado_acima_do_necessario: Decimal
    valor_comprado_acima: Decimal | None
    confianca: str
    motivo: str
    avisos: list = field(default_factory=list)
    dados_usados: dict = field(default_factory=dict)


class Situacao:
    RUPTURA = "Em falta"
    COMPRAR = "Comprar"
    SAUDAVEL = "Estoque adequado"
    EXCESSO = "Excesso"
    SEM_GIRO = "Sem venda no período"
    SEM_DADOS = "Dados insuficientes"


def _arredondar_compra(quantidade, lote_minimo, multiplo):
    if quantidade <= 0:
        return ZERO
    quantidade = max(quantidade, lote_minimo)
    multiplo = multiplo if multiplo and multiplo > 0 else Decimal("1")
    return (quantidade / multiplo).to_integral_value(rounding=ROUND_CEILING) * multiplo


def _quanto_comprar(demanda, posicao, item, p):
    """Ponto de reposição, estoque alvo e quanto comprar para uma demanda diária.

    Separado porque a conta roda duas vezes quando o ano passado mexe na demanda: uma
    com o ajuste, que é a sugestão, e outra sem, que é o número a que a tela compara.
    """
    if item.prazo_reposicao_dias is None or demanda <= 0:
        return None, None, ZERO
    seguranca = demanda * p.dias_seguranca
    ponto = demanda * (item.prazo_reposicao_dias + p.antecipar_dias) + seguranca
    alvo = demanda * (item.prazo_reposicao_dias + p.horizonte_revisao_dias) + seguranca
    if item.estoque_minimo_manual is not None:
        ponto = max(ponto, _d(item.estoque_minimo_manual))
        alvo = max(alvo, _d(item.estoque_minimo_manual))
    compra = ZERO
    if posicao <= ponto:
        compra = _arredondar_compra(alvo - posicao, _d(item.lote_minimo), _d(item.multiplo))
    return ponto.quantize(DUAS_CASAS), alvo.quantize(DUAS_CASAS), compra


def calcular(item: Item, parametros: Parametros = Parametros(), data_corte: date | None = None,
             hoje: date | None = None) -> Resultado:
    """Calcula a recomendação de um item. Não altera nada; só devolve o resultado."""
    p = parametros
    estoque = _d(item.estoque_utilizavel)
    vendas = _d(item.vendas_liquidas)
    custo = _d(item.custo_unitario)
    avisos = []

    if item.dias_janela <= 0:
        raise ValueError(f"{item.sku}: a janela de vendas precisa ter ao menos 1 dia.")

    demanda = vendas / item.dias_janela if vendas > 0 else ZERO

    # SALDO NEGATIVO NÃO É MERCADORIA A REPOR. No SET há 1.023 produtos com saldo
    # abaixo de zero, porque a loja nunca fez contagem física: saíram unidades que
    # nunca foram registradas entrando. O buraco é de LANÇAMENTO, não de prateleira,
    # e as vendas que o abriram já estão somadas em `vendas_liquidas` — ou seja, já
    # estão dentro da demanda. Somar o buraco à compra é comprar a mesma venda duas
    # vezes: medido na foto de 20/09/2026, inflava a lista inteira de R$ 95.459 para
    # R$ 184.577, e mandava comprar 16 unidades de um prato que vende 1 por ano.
    # Cobertura e valor de estoque já usavam `max(estoque, 0)`; a compra não usava,
    # e era a única das três que virava pedido ao fornecedor.
    estoque_contado = max(estoque, ZERO)
    desprezado = estoque_contado - estoque
    posicao = estoque_contado + _d(item.recebimentos_pendentes) - _d(item.reservas_nao_deduzidas)
    if desprezado > 0:
        avisos.append(
            f"Saldo de {_fmt(estoque)} no sistema da loja: impossível na prateleira, e as vendas "
            "que abriram esse buraco já estão na média. A compra conta o saldo como zero; "
            "o número real sai de uma contagem física."
        )

    if demanda > 0:
        cobertura = (max(estoque, ZERO) / demanda).quantize(DUAS_CASAS)
        cobertura_texto = f"{cobertura.quantize(Decimal('1'))} dias"
    else:
        cobertura = None
        cobertura_texto = "sem demanda suficiente"

    # A demanda que decide a compra é a dos dias que ESTE pedido vai cobrir, e não a
    # média do ano: ver apps/compras/estacao.py. Sem fator, as duas são a mesma.
    fator = _d(item.fator_de_estacao) or UM
    demanda_do_pedido = demanda * fator

    if item.prazo_reposicao_dias is None:
        avisos.append("Prazo de reposição não informado: não dá para calcular quando e quanto comprar.")
    ponto, alvo, compra = _quanto_comprar(demanda_do_pedido, posicao, item, p)
    # Quanto seria sem o ano passado. A tela mostra os dois lado a lado: quantidade que
    # muda sozinha, sem dizer de quanto para quanto, ninguém segue.
    compra_sem_estacao = (compra if fator == UM
                          else _quanto_comprar(demanda, posicao, item, p)[2])

    # Excesso: unidades acima da cobertura máxima aceita (nunca abaixo do estoque alvo).
    excesso = ZERO
    if demanda > 0:
        limite = max(alvo or ZERO, demanda * p.excesso_cobertura_dias)
        excesso = max(estoque - limite, ZERO).quantize(DUAS_CASAS)
    elif estoque > 0:
        excesso = estoque  # nada vendeu na janela: todo o estoque está parado

    # Compra acima do necessário: do que foi comprado na janela, quanto ainda sobra acima do limite.
    comprado_acima = min(_d(item.comprado_na_janela), excesso) if excesso > 0 else ZERO

    if demanda > 0 and estoque <= 0:
        situacao = Situacao.RUPTURA
    elif compra > 0:
        situacao = Situacao.COMPRAR
    elif demanda == 0 and estoque > 0:
        situacao = Situacao.SEM_GIRO
    elif excesso > 0:
        situacao = Situacao.EXCESSO
    elif demanda == 0:
        situacao = Situacao.SEM_DADOS
    else:
        situacao = Situacao.SAUDAVEL

    # Confiança: cai com pouco histórico, ruptura na janela, falta de custo ou dados vencidos.
    pontos_confianca = 3
    if item.dias_janela < p.dias_minimos_historico:
        pontos_confianca -= 1
        avisos.append(f"Só {item.dias_janela} dias de histórico; a média ainda oscila.")
    if item.dias_em_ruptura > 0:
        pontos_confianca -= 1
        avisos.append(
            f"O item ficou {item.dias_em_ruptura} dia(s) sem estoque na janela: a demanda real pode ser maior."
        )
    if custo is None:
        avisos.append("Custo não informado: impacto no caixa não calculado.")
    if data_corte and hoje and (hoje - data_corte).days > p.dias_dados_vencidos:
        pontos_confianca -= 1
        avisos.append(f"Dados de {data_corte:%d/%m/%Y}: desatualizados, refaça a importação antes de comprar.")
    confianca = {3: "alta", 2: "média"}.get(pontos_confianca, "baixa")

    motivo = _motivo(situacao, demanda, cobertura_texto, posicao, ponto, alvo, compra, excesso,
                     item, fator)

    return Resultado(
        sku=item.sku,
        descricao=item.descricao,
        demanda_diaria=demanda.quantize(Decimal("0.0001")),
        demanda_do_pedido=demanda_do_pedido.quantize(Decimal("0.0001")),
        fator_de_estacao=fator,
        compra_sem_estacao=compra_sem_estacao,
        cobertura_dias=cobertura,
        cobertura_texto=cobertura_texto,
        posicao_estoque=posicao,
        saldo_negativo_desprezado=desprezado,
        ponto_reposicao=ponto,
        estoque_alvo=alvo,
        compra_sugerida=compra,
        custo_compra=reais(compra * custo) if custo is not None else None,
        valor_estoque=reais(max(estoque, ZERO) * custo) if custo is not None else None,
        situacao=situacao,
        excesso_unidades=excesso,
        valor_excesso=reais(excesso * custo) if custo is not None else None,
        comprado_acima_do_necessario=comprado_acima,
        valor_comprado_acima=reais(comprado_acima * custo) if custo is not None else None,
        confianca=confianca,
        motivo=motivo,
        avisos=avisos,
        dados_usados={
            "estoque_utilizavel": str(estoque),
            "estoque_contado_na_compra": str(estoque_contado),
            "vendas_liquidas": str(vendas),
            "dias_janela": item.dias_janela,
            "prazo_reposicao_dias": item.prazo_reposicao_dias,
            "recebimentos_pendentes": str(item.recebimentos_pendentes),
            "reservas_nao_deduzidas": str(item.reservas_nao_deduzidas),
            "dias_seguranca": str(p.dias_seguranca),
            "fator_de_estacao": str(fator),
            "horizonte_revisao_dias": p.horizonte_revisao_dias,
            "data_corte": data_corte.isoformat() if data_corte else None,
        },
    )


def _fmt(valor):
    return f"{valor:.1f}".replace(".", ",")


def _estacao_em_palavras(fator):
    """A frase do ano passado, que entra no motivo só quando ela mudou o número."""
    if fator == UM:
        return ""
    vezes = _fmt(fator)
    if vezes.endswith(",0"):
        vezes = vezes[:-2]
    foi = "subiu" if fator > UM else "desceu"
    return (f" No ano passado este mesmo período vendeu {vezes} vezes a média do produto,"
            f" e a quantidade {foi} por isso.")


def _motivo(situacao, demanda, cobertura_texto, posicao, ponto, alvo, compra, excesso, item,
            fator=UM):
    if demanda >= 1:
        venda = f"Vende {_fmt(demanda)} por dia"
    elif demanda > 0:
        venda = f"Vende 1 a cada {(1 / demanda).quantize(Decimal('1'), rounding=ROUND_HALF_UP)} dias"
    else:
        venda = "Sem venda no período"
    if situacao == Situacao.RUPTURA:
        return f"{venda} e está sem estoque." + _estacao_em_palavras(fator)
    if situacao == Situacao.COMPRAR:
        return (f"{venda}; a posição ({_fmt(posicao)}) chegou ao ponto de reposição ({_fmt(ponto)}). "
                f"Comprar {_fmt(compra)} leva ao estoque alvo de {_fmt(alvo)} considerando "
                f"{item.prazo_reposicao_dias} dias de prazo." + _estacao_em_palavras(fator))
    if situacao == Situacao.SEM_GIRO:
        return f"Sem venda em {item.dias_janela} dias e com {_fmt(excesso)} unidade(s) paradas."
    if situacao == Situacao.EXCESSO:
        return f"{venda}; o estoque cobre {cobertura_texto}, {_fmt(excesso)} unidade(s) acima do necessário."
    if situacao == Situacao.SEM_DADOS:
        return "Sem venda e sem estoque no período: nada a decidir."
    return f"{venda}; o estoque cobre {cobertura_texto}."


@dataclass
class Resumo:
    itens: int
    valor_estoque: Decimal
    valor_excesso: Decimal
    valor_sem_giro: Decimal
    valor_comprado_acima: Decimal
    itens_em_falta: int
    itens_para_comprar: int
    valor_compra_sugerida: Decimal
    itens_sem_custo: int
    por_situacao: dict


def resumir(resultados) -> Resumo:
    """Totais do diagnóstico. Itens sem custo entram nas contagens, não nos valores."""
    soma = lambda campo, filtro=lambda r: True: sum(  # noqa: E731
        (getattr(r, campo) for r in resultados if getattr(r, campo) is not None and filtro(r)), ZERO
    )
    por_situacao = {}
    for r in resultados:
        por_situacao[r.situacao] = por_situacao.get(r.situacao, 0) + 1
    return Resumo(
        itens=len(resultados),
        valor_estoque=reais(soma("valor_estoque")),
        valor_excesso=reais(soma("valor_excesso", lambda r: r.situacao != Situacao.SEM_GIRO)),
        valor_sem_giro=reais(soma("valor_excesso", lambda r: r.situacao == Situacao.SEM_GIRO)),
        valor_comprado_acima=reais(soma("valor_comprado_acima")),
        itens_em_falta=por_situacao.get(Situacao.RUPTURA, 0),
        itens_para_comprar=por_situacao.get(Situacao.COMPRAR, 0) + por_situacao.get(Situacao.RUPTURA, 0),
        valor_compra_sugerida=reais(soma("custo_compra")),
        itens_sem_custo=sum(1 for r in resultados if r.valor_estoque is None),
        por_situacao=por_situacao,
    )


def curva_abc(valores_por_sku: dict, corte_a=Decimal("0.80"), corte_b=Decimal("0.95")) -> dict:
    """Classifica SKUs por participação acumulada no critério informado (ex.: faturamento).

    A = até 80% do total acumulado, B = até 95%, C = o resto. Itens com valor zero são C.
    """
    total = sum((_d(v) for v in valores_por_sku.values() if _d(v) > 0), ZERO)
    classes = {}
    acumulado = ZERO
    for sku, valor in sorted(valores_por_sku.items(), key=lambda kv: (-_d(kv[1]), kv[0])):
        valor = _d(valor)
        if total == 0 or valor <= 0:
            classes[sku] = "C"
            continue
        participacao_antes = acumulado / total
        acumulado += valor
        classes[sku] = "A" if participacao_antes < corte_a else ("B" if participacao_antes < corte_b else "C")
    return classes
