"""Transforma a foto importada do SET nos números do painel.

Usa as regras de apps/compras/calculos.py, as mesmas do diagnóstico em planilha,
para que o painel na tela e o relatório entreguem o mesmo resultado.

Cada indicador diz se depende do saldo de estoque do SET. Enquanto a loja não
fizer a contagem física, o que depende do saldo é estimativa; o que vem de venda
e compra registradas vale como está. É essa diferença que o painel mostra.
"""

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from apps.compras.calculos import Parametros, Situacao, calcular, resumir
from apps.compras.calculos import Item as ItemCalculo
from apps.compras.sugestoes import e_mercadoria
from apps.fornecedores import servicos as fornecedores

ZERO = Decimal("0")
LIMITE_LISTA = 50
LIMITE_LISTA_CURTA = 15
# Produto sem entrada há mais de dois anos: ou saiu de linha, ou é dinheiro dormindo.
ANOS_PARADO = 2


@dataclass
class Indicador:
    chave: str
    titulo: str
    valor: Decimal
    itens: int
    explicacao: str
    depende_da_contagem: bool
    destaque: bool = False


@dataclass
class Linha:
    codigo: str
    descricao: str
    grupo: str
    fornecedor: str
    valor: Decimal
    estoque: Decimal
    vendas_12m: Decimal
    compras_12m: Decimal
    situacao: str
    motivo: str
    cobertura: str
    ultima_compra: object = None
    ultima_venda: object = None
    lucro_12m: Decimal = ZERO


@dataclass
class Painel:
    importacao: object
    resumo: object
    indicadores: list = field(default_factory=list)
    listas: dict = field(default_factory=dict)
    meses: list = field(default_factory=list)
    itens_sem_custo: int = 0
    itens_sem_prazo: int = 0
    itens_prazo_informado: int = 0
    itens_prazo_estimado: int = 0
    itens_com_pedido: int = 0
    entrega_no_mesmo_dia: int = 0
    compras_com_prazo: int = 0

    def indicador(self, chave):
        for i in self.indicadores:
            if i.chave == chave:
                return i
        return None


def _lucro_12m(produto):
    """Quanto o produto deu de margem em 12 meses: (venda - custo) x unidades vendidas.

    É o critério do ranking de reposição: entre os produtos que precisam ser repostos,
    primeiro os que mais trouxeram dinheiro. Sem preço ou sem custo, fica zero e o
    produto cai para o fim da lista, porque não dá para afirmar nada sobre ele.
    """
    if produto.preco_venda is None or produto.custo is None:
        return ZERO
    return ((produto.preco_venda - produto.custo) * (produto.vendas_12m or ZERO)).quantize(Decimal("0.01"))


def _item_de_calculo(produto, dias_janela, prazo_informado=None):
    return ItemCalculo(
        sku=produto.codigo,
        descricao=produto.descricao,
        estoque_utilizavel=produto.estoque,
        vendas_liquidas=produto.vendas_12m,
        dias_janela=dias_janela,
        prazo_reposicao_dias=(prazo_informado if prazo_informado is not None
                              else produto.prazo_reposicao_dias),
        custo_unitario=produto.custo,
        reservas_nao_deduzidas=produto.reservado or ZERO,
        comprado_na_janela=produto.compras_12m,
        recebimentos_pendentes=produto.pedido_em_aberto or ZERO,
    )


def _reais(valor):
    return (valor or ZERO).quantize(Decimal("0.01"))


def montar(importacao, hoje=None, parametros=None, limite=LIMITE_LISTA, prazos=None) -> Painel:
    """Calcula os indicadores da importação informada.

    O prazo de entrega informado em Fornecedores vale mais que o medido no SET: é o que
    corrige a data em que o sistema manda comprar.
    """
    parametros = parametros or Parametros()
    detalhe = importacao.detalhe or {}
    dias = importacao.dias_abertos_12m or 1
    produtos = list(importacao.itens.all())
    prazos = fornecedores.prazos_informados() if prazos is None else prazos

    resultados = []
    por_codigo = {}
    com_prazo_informado = 0
    for produto in produtos:
        informado = prazos.get((produto.fornecedor or "").strip())
        com_prazo_informado += informado is not None
        resultado = calcular(_item_de_calculo(produto, dias, informado), parametros,
                             importacao.data_corte, hoje)
        resultados.append(resultado)
        por_codigo[produto.codigo] = (produto, resultado)

    resumo = resumir(resultados)
    listas = {}

    def linha(produto, resultado, valor):
        return Linha(
            codigo=produto.codigo,
            descricao=produto.descricao,
            grupo=produto.grupo,
            fornecedor=produto.fornecedor,
            valor=_reais(valor),
            estoque=produto.estoque,
            vendas_12m=produto.vendas_12m,
            compras_12m=produto.compras_12m,
            situacao=resultado.situacao,
            motivo=resultado.motivo,
            cobertura=resultado.cobertura_texto,
            ultima_compra=produto.ultima_compra,
            ultima_venda=produto.ultima_venda,
            lucro_12m=_lucro_12m(produto),
        )

    def maior_valor(linha_):
        return (-(linha_.valor or ZERO), linha_.codigo)

    def montar_lista(chave, filtro, valor_de, ordem=maior_valor, quantas=None):
        """Uma lista do painel e o total dela, SÓ com mercadoria de revenda.

        Todo indicador daqui é juízo sobre compra — parado, excesso, comprou mais do que
        vendeu, comprar agora. O consumo próprio da loja e o DIVERSOS do balcão não são
        compra que alguém decida: entravam na conta e faziam o painel mostrar cerca de
        R$ 4,9 mil a mais em "Dinheiro parado" do que "O que fazer agora" e a tela de
        Sugestões, com o mesmo nome, na mesma tela de abertura.

        Os dois números de loja inteira do alto da tela — "Produtos cadastrados no SET" e
        "Valor parado em estoque hoje" — continuam vindo de `resumir`, sobre tudo: ali o
        consumo próprio é estoque de verdade e tirá-lo seria mentir por outro lado.
        """
        selecionadas = []
        for produto, resultado in por_codigo.values():
            if not e_mercadoria(produto.grupo, produto.descricao):
                continue
            if not filtro(produto, resultado):
                continue
            valor = valor_de(produto, resultado)
            selecionadas.append(linha(produto, resultado, valor))
        selecionadas.sort(key=ordem)
        total = sum((l.valor or ZERO for l in selecionadas), ZERO)
        listas[chave] = selecionadas[:quantas or limite]
        return _reais(total), len(selecionadas)

    # Dinheiro parado: nada vendido em 12 meses e ainda tem saldo. Produto sem custo
    # cadastrado fica de fora, como já ficava do VALOR: ele somava zero reais e mesmo
    # assim era contado, e a mesma tela de abertura dizia "1.490 produtos" no Painel e
    # "1.443 produtos" na tarefa "Pôr para girar o que está parado", para o mesmo
    # dinheiro. Quantos são eles a tela já diz, na linha dos produtos sem custo.
    valor_parado, n_parado = montar_lista(
        "parado",
        lambda p, r: r.situacao == Situacao.SEM_GIRO and (p.custo or ZERO) > ZERO,
        lambda p, r: r.valor_excesso or ZERO,
    )
    # Excesso: vende, mas o saldo cobre mais que o horizonte aceito.
    valor_excesso, n_excesso = montar_lista(
        "excesso",
        lambda p, r: r.situacao != Situacao.SEM_GIRO and (r.valor_excesso or ZERO) > 0,
        lambda p, r: r.valor_excesso or ZERO,
    )
    # Comprado acima do necessário: do que entrou no período, quanto sobra acima do limite.
    valor_acima, n_acima = montar_lista(
        "comprado_acima",
        lambda p, r: (r.valor_comprado_acima or ZERO) > 0,
        lambda p, r: r.valor_comprado_acima or ZERO,
    )
    # Falta: vendeu nos últimos 90 dias e está sem saldo. Produto que parou de vender há
    # meses e está zerado não é falta, é item que saiu de linha.
    valor_falta, n_falta = montar_lista(
        "falta",
        lambda p, r: p.estoque <= 0 and p.vendas_90d > 0,
        lambda p, r: p.receita_12m or ZERO,
    )
    # Comprou mais que vendeu: não depende do saldo, só de nota de compra e de venda.
    valor_comprou_mais, n_comprou_mais = montar_lista(
        "comprou_mais",
        lambda p, r: p.compras_12m > p.vendas_12m and p.custo is not None,
        lambda p, r: (p.compras_12m - p.vendas_12m) * p.custo,
    )
    # Comprar agora: o que o cálculo recomenda repor.
    valor_comprar, n_comprar = montar_lista(
        "comprar",
        lambda p, r: r.compra_sugerida > 0,
        lambda p, r: r.custo_compra or ZERO,
    )

    # Comprados recentemente: o que entrou por último, para conferir a compra da semana.
    montar_lista(
        "comprados_recentemente",
        lambda p, r: p.ultima_compra is not None,
        lambda p, r: p.valor_compras_12m or ZERO,
        ordem=lambda l: (-l.ultima_compra.toordinal(), l.codigo),
        quantas=LIMITE_LISTA_CURTA,
    )
    # Parados há anos: tem saldo, a última entrada é antiga e não vendeu nada em 12 meses.
    limite_antigo = importacao.data_corte - timedelta(days=365 * ANOS_PARADO)
    montar_lista(
        "comprados_ha_anos",
        lambda p, r: (p.ultima_compra is not None and p.ultima_compra <= limite_antigo
                      and p.estoque > 0 and p.vendas_12m <= 0),
        lambda p, r: r.valor_excesso or (p.estoque * (p.custo or ZERO)),
        ordem=lambda l: (l.ultima_compra.toordinal(), l.codigo),
        quantas=LIMITE_LISTA_CURTA,
    )
    # Melhores para comprar: entre os que o cálculo manda repor, os que mais deram margem.
    montar_lista(
        "melhores_para_comprar",
        lambda p, r: r.compra_sugerida > 0 and _lucro_12m(p) > 0,
        lambda p, r: r.custo_compra or ZERO,
        ordem=lambda l: (-(l.lucro_12m or ZERO), l.codigo),
        quantas=LIMITE_LISTA_CURTA,
    )

    indicadores = [
        Indicador(
            chave="comprou_mais",
            titulo="Comprou mais do que vendeu em 12 meses",
            valor=valor_comprou_mais,
            itens=n_comprou_mais,
            explicacao="Soma das notas de compra acima do que saiu em venda no mesmo período. "
                       "Vem de compra e venda registradas, então não depende da contagem do estoque.",
            depende_da_contagem=False,
            destaque=True,
        ),
        Indicador(
            chave="parado",
            titulo="Dinheiro parado sem venda em 12 meses",
            valor=valor_parado,
            itens=n_parado,
            explicacao="Produtos com saldo no SET e nenhuma venda no período, avaliados pelo custo.",
            depende_da_contagem=True,
        ),
        Indicador(
            chave="excesso",
            titulo=f"Excesso acima de {Parametros().excesso_cobertura_dias // 30} meses de venda",
            valor=valor_excesso,
            itens=n_excesso,
            explicacao="Saldo que passa do necessário para atender a venda média do próprio produto.",
            depende_da_contagem=True,
        ),
        Indicador(
            chave="comprado_acima",
            titulo="Compras acima da necessidade",
            valor=valor_acima,
            itens=n_acima,
            explicacao="Do que foi comprado nos 12 meses, a parte que ainda está parada acima do limite.",
            depende_da_contagem=True,
        ),
        Indicador(
            chave="falta",
            titulo="Venda em risco por falta de estoque",
            valor=valor_falta,
            itens=n_falta,
            explicacao="Produtos que venderam nos últimos 90 dias e estão zerados no SET. "
                       "O valor é o quanto esses itens faturaram em 12 meses.",
            depende_da_contagem=True,
        ),
        Indicador(
            chave="comprar",
            titulo="Reposição sugerida agora",
            valor=valor_comprar,
            itens=n_comprar,
            explicacao="Custo da compra que repõe os itens que chegaram ao ponto de reposição, "
                       "considerando o prazo de cada fornecedor.",
            depende_da_contagem=True,
        ),
    ]

    return Painel(
        importacao=importacao,
        resumo=resumo,
        indicadores=indicadores,
        listas=listas,
        meses=_meses(detalhe),
        itens_sem_custo=resumo.itens_sem_custo,
        itens_sem_prazo=sum(1 for p in produtos if p.prazo_reposicao_dias is None),
        itens_prazo_informado=com_prazo_informado,
        itens_prazo_estimado=sum(1 for p in produtos if p.prazo_estimado),
        itens_com_pedido=sum(1 for p in produtos if p.pedido_em_aberto),
        entrega_no_mesmo_dia=detalhe.get("compras_com_entrega_no_mesmo_dia", 0),
        compras_com_prazo=detalhe.get("compras_com_prazo_medido", 0),
    )


MESES = ["", "jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def _meses(detalhe, quantidade=12):
    """Compras e vendas lado a lado, mês a mês: é o retrato do giro de caixa.

    Cada mês leva a largura da própria barra em porcentagem do maior valor do
    período, para a tela mostrar de relance o mês em que a compra passou a venda.
    """
    vendas = {(a, m): v for a, m, v, _ in detalhe.get("vendas_mes", [])}
    compras = {(a, m): v for a, m, v, _ in detalhe.get("compras_mes", [])}
    chaves = sorted(set(vendas) | set(compras))[-quantidade:]
    linhas = []
    for ano, mes in chaves:
        venda = Decimal(str(vendas.get((ano, mes), 0))).quantize(Decimal("0.01"))
        compra = Decimal(str(compras.get((ano, mes), 0))).quantize(Decimal("0.01"))
        linhas.append({
            "rotulo": f"{MESES[mes]}/{str(ano)[2:]}",
            "venda": venda,
            "compra": compra,
            "diferenca": (venda - compra).quantize(Decimal("0.01")),
            "comprou_mais": compra > venda,
        })
    maior = max((max(linha["venda"], linha["compra"]) for linha in linhas), default=ZERO)
    for linha in linhas:
        linha["largura_venda"] = _porcentagem(linha["venda"], maior)
        linha["largura_compra"] = _porcentagem(linha["compra"], maior)
    return linhas


def _porcentagem(valor, maior):
    """Largura da barra, de 0 a 100. Valor que existe nunca some: mínimo de 1%."""
    if not maior or valor <= ZERO:
        return 0
    return max(1, int(valor * 100 / maior))
