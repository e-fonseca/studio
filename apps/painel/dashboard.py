"""Dashboard do varejo: os números da loja em gráficos, com filtros.

Pedido do Edson em 07/10/2026: uma tela de dashboard com gráficos, estatísticas e
filtros, no formato que o varejo usa. O que o varejo olha é sempre o mesmo
conjunto, e é ele que está aqui:

- faturamento, número de vendas e ticket médio, cada um comparado com o período
  anterior de igual tamanho (é a comparação que diz se melhorou ou piorou);
- margem bruta do cadastro, cobertura do estoque em meses e ruptura (produto que
  vende e está sem saldo), que é o lado do estoque;
- faturamento mês a mês com o mesmo mês do ano passado ao lado, curva ABC dos
  produtos, participação por grupo, campeões de faturamento e de margem;
- dia da semana, forma de pagamento e hora do dia.

Duas restrições do dado mandam no desenho da tela, e ela diz as duas em voz alta:

1. O SET não traz o item da venda, só a venda inteira. Então filtrar por grupo ou
   por fornecedor não mexe em faturamento, ticket, dia da semana nem forma de
   pagamento: esses blocos são sempre a loja toda. Os filtros de grupo e de
   fornecedor valem para os blocos de produto e de estoque.
2. Venda por produto é de 12 meses, calculada na importação (`receita_12m`). Por
   isso os blocos de produto não acompanham o filtro de período.

Os gráficos são SVG desenhado aqui, sem biblioteca: o sistema roda na loja e não
depende de baixar nada da internet.
"""

import calendar
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db.models import Count, F, Q, Sum
from django.db.models.functions import Substr

from apps.compras.sugestoes import so_mercadoria
from apps.core import curva_abc
from apps.importacao.models import ProdutoImportado, VendaImportada

ZERO = Decimal("0")
CEM = Decimal("100")

# (valor na URL, rótulo na tela, dias para trás)
PERIODOS = (
    ("12m", "12 meses", 365),
    ("90d", "90 dias", 90),
    ("30d", "30 dias", 30),
    ("7d", "7 dias", 7),
)
PERIODO_PADRAO = "12m"
DIAS_DO_PERIODO = dict((chave, dias) for chave, _, dias in PERIODOS)
ROTULO_DO_PERIODO = dict((chave, rotulo) for chave, rotulo, _ in PERIODOS)

DIAS_DA_SEMANA = ("Domingo", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado")
MESES_CURTOS = ("", "jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")

# Quantos meses o gráfico mostra. A importação guarda 25 meses, e 13 é o que cabe na
# tela do celular sem a barra virar risco: um ano fechado mais o mês de agora.
MESES_NO_GRAFICO = 13
# Quantas linhas as listas de campeões mostram. Dez é o costume do varejo e é o que
# alguém lê de uma vez.
QUANTOS_CAMPEOES = 10
# Quantos grupos a rosca separa antes de juntar o resto em "outros".
QUANTOS_GRUPOS = 8
# Faixas de hora do dia, no formato que a loja fala.
FAIXAS_DE_HORA = ((8, 11, "Manhã (8h-11h)"), (11, 14, "Meio-dia (11h-14h)"),
                  (14, 17, "Tarde (14h-17h)"), (17, 24, "Fim do dia (17h em diante)"))

# Cores das fatias, as mesmas variáveis que a Visão geral usa.
CORES = ("--cor-fatia-1", "--cor-fatia-2", "--cor-fatia-3", "--cor-fatia-4",
         "--cor-fatia-5", "--cor-fatia-6", "--cor-fatia-7", "--cor-fatia-8", "--cor-fatia-9")


def _decimal(valor):
    try:
        return Decimal(valor or 0)
    except (TypeError, InvalidOperation):
        return ZERO


def _milhar(numero):
    """11274 vira 11.274. Para o texto do cartão, que é lido por gente da loja."""
    return f"{int(numero):,}".replace(",", ".")


def _porcento(parte, total):
    if not total:
        return ZERO
    return (_decimal(parte) * CEM / _decimal(total)).quantize(Decimal("0.1"))


def _largura(parte, total):
    """Largura ou altura de barra, de 0 a 100, em número inteiro.

    Inteiro de propósito: isto vai dentro de um `style=` e o Django localiza número
    no template, então um Decimal sairia como "66,5%" — CSS inválido, barra com
    altura zero. Quem é texto na tela (a porcentagem ao lado) continua Decimal, que
    é justamente onde a vírgula tem que aparecer. Valor que existe nunca some: o
    mínimo é 1%, como no gráfico de compra e venda do painel.
    """
    if not total or _decimal(parte) <= ZERO:
        return 0
    return max(1, int(_decimal(parte) * CEM / _decimal(total)))


def _variacao(agora, antes):
    """Quanto o número subiu ou caiu, em porcentagem. None quando não há com que comparar."""
    if not antes:
        return None
    return ((_decimal(agora) - _decimal(antes)) * CEM / _decimal(antes)).quantize(Decimal("0.1"))


@dataclass
class Kpi:
    """Um número grande do topo, com a comparação já pronta."""

    chave: str
    rotulo: str
    valor: Decimal
    formato: str = "numero"  # numero, reais, porcento, meses
    variacao: Decimal | None = None
    comparado_com: str = ""
    explicacao: str = ""
    # Quando subir é ruim (ruptura, capital parado), o verde e o vermelho trocam.
    subir_e_bom: bool = True

    @property
    def nivel(self):
        if self.variacao is None or self.variacao == ZERO:
            return "neutro"
        subiu = self.variacao > ZERO
        return "bom" if subiu == self.subir_e_bom else "ruim"


@dataclass
class Mes:
    rotulo: str
    valor: Decimal
    vendas: int = 0
    valor_ano_passado: Decimal | None = None
    altura: int = 0
    altura_ano_passado: int | None = None
    # Mês que ainda não terminou: o do corte dos dados, quase sempre.
    parcial: bool = False
    dia_parcial: int | None = None

    @property
    def variacao(self):
        return _variacao(self.valor, self.valor_ano_passado)

    @property
    def ate_o_dia(self):
        """Texto curto para a coluna do mês que ainda está correndo."""
        return f"até dia {self.dia_parcial}" if self.parcial and self.dia_parcial else ""


@dataclass
class Fatia:
    nome: str
    valor: Decimal
    fatia: Decimal = ZERO
    cor: str = CORES[0]
    traco: str = ""
    giro: str = ""
    largura: int = 0


@dataclass
class Campeao:
    codigo: str
    descricao: str
    grupo: str
    valor: Decimal
    unidades: Decimal = ZERO
    margem: Decimal | None = None


@dataclass
class ClasseAbc:
    letra: str
    produtos: int = 0
    receita: Decimal = ZERO
    fatia_dos_produtos: Decimal = ZERO
    fatia_da_receita: Decimal = ZERO
    # O que a classe é, em três palavras de loja: a letra sozinha não diz nada a quem
    # nunca ouviu falar em curva ABC.
    titulo: str = ""
    explicacao: str = ""
    # Largura da barra, de 0 a 100, em porcentagem do faturamento. Inteiro porque vai
    # dentro de um style= e o Django localiza número no template: Decimal sairia "31,2"
    # e o CSS ignoraria a linha.
    largura_receita: int = 0


@dataclass
class Dashboard:
    importacao = None
    periodo: str = PERIODO_PADRAO
    rotulo_periodo: str = ""
    desde = None
    ate = None
    filtro_grupo: str = ""
    filtro_fornecedor: str = ""
    grupos_disponiveis: list = field(default_factory=list)
    fornecedores_disponiveis: list = field(default_factory=list)
    kpis_da_venda: list = field(default_factory=list)
    kpis_do_estoque: list = field(default_factory=list)
    meses: list = field(default_factory=list)
    grupos: list = field(default_factory=list)
    abc: list = field(default_factory=list)
    campeoes_faturamento: list = field(default_factory=list)
    campeoes_margem: list = field(default_factory=list)
    dias_da_semana: list = field(default_factory=list)
    formas: list = field(default_factory=list)
    horas: list = field(default_factory=list)
    produtos_no_filtro: int = 0
    vendas_no_periodo: int = 0
    tem_dados: bool = False

    @property
    def filtrou_produto(self):
        return bool(self.filtro_grupo or self.filtro_fornecedor)


def _janela(importacao, periodo):
    """Do que até quando. O fim é a data de corte da importação, não hoje."""
    ate = importacao.data_corte
    dias = DIAS_DO_PERIODO.get(periodo, DIAS_DO_PERIODO[PERIODO_PADRAO])
    return ate - timedelta(days=dias - 1), ate, dias


def _resumo_das_vendas(importacao, desde, ate):
    linha = VendaImportada.objects.filter(
        importacao=importacao, data__gte=desde, data__lte=ate
    ).aggregate(quantas=Count("id"), valor=Sum("valor"), desconto=Sum("desconto"))
    return {
        "vendas": linha["quantas"] or 0,
        "faturamento": _decimal(linha["valor"]),
        "desconto": _decimal(linha["desconto"]),
    }


def _kpis_da_venda(importacao, desde, ate, dias):
    """Os quatro números da venda, cada um contra o período anterior de igual tamanho."""
    agora = _resumo_das_vendas(importacao, desde, ate)
    antes = _resumo_das_vendas(importacao, desde - timedelta(days=dias), desde - timedelta(days=1))
    comparado = f"{dias} dias anteriores"

    def ticket(dados):
        if not dados["vendas"]:
            return ZERO
        return (dados["faturamento"] / dados["vendas"]).quantize(Decimal("0.01"))

    return agora, [
        Kpi("faturamento", "Faturamento", agora["faturamento"], "reais",
            _variacao(agora["faturamento"], antes["faturamento"]), comparado,
            "Soma das vendas do período, como o SET registrou: é o total da venda, já "
            "sem o desconto dado no balcão. A Visão geral soma o preço dos itens, antes "
            "do desconto, por isso o número de lá é um pouco maior."),
        Kpi("vendas", "Vendas", Decimal(agora["vendas"]), "numero",
            _variacao(agora["vendas"], antes["vendas"]), comparado,
            "Quantas vendas a loja fez, não quantas peças."),
        Kpi("ticket", "Ticket médio", ticket(agora), "reais",
            _variacao(ticket(agora), ticket(antes)), comparado,
            "Quanto o cliente gasta por compra: faturamento dividido pelo número de vendas."),
        Kpi("desconto", "Desconto dado", _porcento(agora["desconto"], agora["faturamento"]),
            "porcento",
            _variacao(_porcento(agora["desconto"], agora["faturamento"]),
                      _porcento(antes["desconto"], antes["faturamento"])),
            comparado,
            "Quanto do faturamento saiu em desconto no período.", subir_e_bom=False),
    ]


def _produtos(importacao, grupo, fornecedor):
    consulta = ProdutoImportado.objects.filter(importacao=importacao)
    if grupo:
        consulta = consulta.filter(grupo=grupo)
    if fornecedor:
        consulta = consulta.filter(fornecedor=fornecedor)
    return consulta


def _kpis_do_estoque(consulta):
    """Margem, cobertura, ruptura e capital parado: o lado do estoque, sempre 12 meses."""
    # Saldo negativo conta como zero, e não como dinheiro a menos. São 1.456 produtos no
    # SET com saldo abaixo de zero: isso é erro de cadastro de uma loja que nunca fez
    # contagem, não mercadoria devendo na prateleira. Somar o negativo tirava R$ 37 mil do
    # "parado" e R$ 127 mil do valor do estoque, e fazia esta tela discordar da Lista de
    # compra e do "Antes de comprar", que sempre filtraram saldo positivo.
    totais = consulta.aggregate(
        quantos=Count("id"),
        receita=Sum("receita_12m"),
        estoque_ao_custo=Sum(F("estoque") * F("custo"), filter=Q(estoque__gt=0)),
        custo_do_vendido=Sum(F("vendas_12m") * F("custo")),
    )
    quantos = totais["quantos"] or 0
    receita = _decimal(totais["receita"])
    estoque_ao_custo = _decimal(totais["estoque_ao_custo"])
    custo_do_vendido = _decimal(totais["custo_do_vendido"])

    margem = ZERO
    if receita:
        margem = _porcento(receita - custo_do_vendido, receita)
    cobertura = ZERO
    if custo_do_vendido:
        cobertura = (estoque_ao_custo / (custo_do_vendido / Decimal("12"))).quantize(Decimal("0.1"))

    vendem = consulta.filter(vendas_12m__gt=0)
    com_venda = vendem.count()
    sem_saldo = vendem.filter(estoque__lte=0).count()
    # so_mercadoria porque consumo próprio da loja não é dinheiro que se põe para girar:
    # sem isso esta tela dava R$ 4,9 mil a mais que o "O que fazer agora" e a Sugestões,
    # com o mesmo nome em cima do número.
    parado = _decimal(so_mercadoria(consulta.filter(vendas_12m__lte=0, estoque__gt=0)).aggregate(
        valor=Sum(F("estoque") * F("custo")))["valor"])
    negativos = consulta.filter(estoque__lt=0).count()

    return quantos, [
        Kpi("margem", "Margem bruta", margem, "porcento", None, "",
            "Quanto sobra da venda depois do custo da mercadoria, pelos valores do cadastro "
            "do SET, pesado pelo que cada produto vendeu em 12 meses."),
        Kpi("cobertura", "Cobertura do estoque", cobertura, "meses", None, "",
            "Quantos meses de venda o estoque de hoje aguenta, no ritmo dos últimos 12 meses. "
            "Acima de uns três meses, é dinheiro parado na prateleira."),
        Kpi("ruptura", "Ruptura", _porcento(sem_saldo, com_venda), "porcento", None, "",
            f"{_milhar(sem_saldo)} de {_milhar(com_venda)} produtos que venderam no ano "
            "estão sem saldo no SET. "
            "É venda perdida por falta, mas o saldo do SET é estimativa enquanto a loja não "
            "fizer a contagem física, então o número verdadeiro é menor que este.",
            subir_e_bom=False),
        Kpi("parado", "Parado sem vender", parado, "reais", None, "",
            "Dinheiro em estoque de produto que não vendeu nenhuma unidade em 12 meses."
            + (f" {_milhar(negativos)} produtos estão com saldo negativo no SET e contam "
               "como zero aqui: saldo negativo é erro de cadastro, não mercadoria."
               if negativos else ""),
            subir_e_bom=False),
    ]


def _meses(importacao):
    """Faturamento mês a mês, com o mesmo mês do ano passado ao lado.

    Vem de `detalhe["vendas_mes"]`, calculado na importação, porque ele guarda 25
    meses — a tabela de vendas guarda 12, que não daria para comparar com o ano
    passado.

    O último mês quase nunca está fechado: os dados vão até o dia do backup. Comparar
    sete dias deste mês com o mês inteiro do ano passado dava "-84%", uma queda que não
    existe — foi o que o Edson viu em 08/10/2026. Então o mês que ainda corre é comparado
    com o MESMO PEDAÇO do ano passado (`detalhe["mes_parcial"]`), do dia 1 ao mesmo dia, e
    a coluna diz "até dia 7". Importação antiga não tem esse número: aí o mês aparece sem
    comparação nenhuma, que é melhor do que uma errada.
    """
    bruto = (importacao.detalhe or {}).get("vendas_mes") or []
    por_mes = {}
    for linha in bruto:
        if len(linha) < 4:
            continue
        ano, mes, valor, vendas = int(linha[0]), int(linha[1]), _decimal(linha[2]), int(linha[3])
        por_mes[(ano, mes)] = (valor, vendas)
    chaves = sorted(por_mes)[-MESES_NO_GRAFICO:]

    corte = importacao.data_corte
    parcial = (importacao.detalhe or {}).get("mes_parcial") or []
    preparados = []
    for ano, mes in chaves:
        valor, vendas = por_mes[(ano, mes)]
        antes = por_mes.get((ano - 1, mes))
        valor_antes = antes[0] if antes else None
        e_parcial = bool(corte and (ano, mes) == (corte.year, corte.month)
                         and corte.day < calendar.monthrange(ano, mes)[1])
        if e_parcial:
            valor_antes = _ano_passado_ate_o_dia(parcial, ano, mes)
        preparados.append((ano, mes, valor, vendas, valor_antes, e_parcial))

    maior = max((p[2] for p in preparados), default=ZERO)
    for _ano, _mes, _valor, _vendas, valor_antes, _parcial in preparados:
        if valor_antes:
            maior = max(maior, valor_antes)

    meses = []
    for ano, mes, valor, vendas, valor_antes, e_parcial in preparados:
        mes_pronto = Mes(
            rotulo=f"{MESES_CURTOS[mes]}/{str(ano)[2:]}",
            valor=valor.quantize(Decimal("0.01")),
            vendas=vendas,
            valor_ano_passado=valor_antes.quantize(Decimal("0.01")) if valor_antes else None,
            altura=_largura(valor, maior),
            parcial=e_parcial,
            dia_parcial=corte.day if e_parcial and corte else None,
        )
        if valor_antes:
            mes_pronto.altura_ano_passado = _largura(valor_antes, maior)
        meses.append(mes_pronto)
    return meses


def _ano_passado_ate_o_dia(parcial, ano, mes):
    """Quanto o mesmo mês do ano passado tinha vendido até o mesmo dia.

    None quando a importação é anterior à 1.20.1 e não traz esse número, ou quando o
    ano passado não teve venda nenhuma nesse pedaço: nos dois casos é melhor não
    comparar do que comparar com o mês inteiro.
    """
    if len(parcial) < 4 or int(parcial[0]) != ano or int(parcial[1]) != mes:
        return None
    valor = _decimal(parcial[3])
    return valor if valor and valor > ZERO else None


def _grupos(consulta):
    """Participação de cada grupo no faturamento de 12 meses, em rosca."""
    linhas = list(
        consulta.exclude(receita_12m__lte=0)
        .values("grupo")
        .annotate(valor=Sum("receita_12m"))
        .order_by("-valor")
    )
    total = sum((_decimal(linha["valor"]) for linha in linhas), ZERO)
    if not total:
        return []
    principais = linhas[:QUANTOS_GRUPOS]
    resto = sum((_decimal(linha["valor"]) for linha in linhas[QUANTOS_GRUPOS:]), ZERO)
    fatias = [
        Fatia(nome=(linha["grupo"] or "sem grupo"), valor=_decimal(linha["valor"]))
        for linha in principais
    ]
    if resto:
        fatias.append(Fatia(nome=f"outros {len(linhas) - QUANTOS_GRUPOS} grupos", valor=resto))
    giro = Decimal("25")  # o traço começa no topo da rosca, como na Visão geral
    for posicao, fatia in enumerate(fatias):
        fatia.fatia = _porcento(fatia.valor, total)
        fatia.cor = CORES[posicao % len(CORES)]
        fatia.traco = f"{fatia.fatia} {CEM - fatia.fatia}"
        fatia.giro = str(giro)
        giro = giro - fatia.fatia
        if giro < ZERO:
            giro += CEM
    return fatias


def _abc(consulta):
    """Curva ABC: A são os produtos que fazem os primeiros 80% do faturamento.

    O que o varejo faz com ela: A nunca pode faltar, C não merece estoque.

    O desenho já mudou duas vezes em 08/10/2026, as duas a pedido do Edson. Era a curva
    de Pareto, uma linha subindo num quadro sem números; virou duas faixas repartidas em
    A, B e C, que ele também achou confusa. Agora é a mesma lista de barras horizontais
    das outras caixas da tela (dia da semana, forma de pagamento): uma linha por classe,
    com o nome do grupo em palavras, quantos produtos são e quanto do faturamento fazem.
    O contraste que é a curva ABC fica escrito em uma frase acima da lista, que é como
    ele próprio conta a história para o sogro.
    """
    receitas = [
        _decimal(valor)
        for valor in consulta.exclude(receita_12m__lte=0)
        .order_by("-receita_12m").values_list("receita_12m", flat=True)
    ]
    total = sum(receitas, ZERO)
    if not total:
        return []
    # A regra de onde cada faixa termina mora em apps/core/curva_abc.py, porque o
    # inventário usa a MESMA classificação para decidir de quanto em quanto tempo
    # contar cada produto. Duas cópias da regra seria o mesmo produto sendo classe A
    # numa tela e B noutra.
    classes = {
        letra: ClasseAbc(letra, titulo=curva_abc.TITULOS[letra],
                         explicacao=curva_abc.EXPLICACOES[letra])
        for letra in curva_abc.LETRAS
    }
    for receita, letra in zip(receitas, curva_abc.letras(receitas)):
        classe = classes[letra]
        classe.produtos += 1
        classe.receita += receita
    for classe in classes.values():
        classe.fatia_dos_produtos = _porcento(classe.produtos, len(receitas))
        classe.fatia_da_receita = _porcento(classe.receita, total)
        # O mínimo de 1 que o _largura devolve deixa visível a barra da classe pequena.
        classe.largura_receita = _largura(classe.receita, total)
        classe.receita = classe.receita.quantize(Decimal("0.01"))
    return [classes["A"], classes["B"], classes["C"]]


def _campeoes(consulta):
    """Os dez maiores de faturamento e os dez maiores de margem em reais."""
    por_faturamento = [
        Campeao(codigo=p.codigo, descricao=p.descricao, grupo=p.grupo,
                valor=_decimal(p.receita_12m).quantize(Decimal("0.01")),
                unidades=_decimal(p.vendas_12m))
        for p in consulta.exclude(receita_12m__lte=0).order_by("-receita_12m")[:QUANTOS_CAMPEOES]
    ]
    por_margem = [
        Campeao(codigo=p["codigo"], descricao=p["descricao"], grupo=p["grupo"],
                valor=_decimal(p["ganho"]).quantize(Decimal("0.01")),
                unidades=_decimal(p["vendas_12m"]),
                margem=_porcento(_decimal(p["ganho"]), _decimal(p["receita_12m"])))
        for p in consulta.exclude(receita_12m__lte=0).filter(custo__gt=0)
        .annotate(ganho=F("receita_12m") - F("vendas_12m") * F("custo"))
        .values("codigo", "descricao", "grupo", "ganho", "receita_12m", "vendas_12m")
        .order_by("-ganho")[:QUANTOS_CAMPEOES]
    ]
    return por_faturamento, por_margem


def _barras(linhas, rotulo_de):
    """Transforma linhas agregadas em barras com largura em porcentagem."""
    maior = max((_decimal(linha["valor"]) for linha in linhas), default=ZERO)
    total = sum((_decimal(linha["valor"]) for linha in linhas), ZERO)
    fatias = []
    for posicao, linha in enumerate(linhas):
        valor = _decimal(linha["valor"]).quantize(Decimal("0.01"))
        fatias.append(Fatia(
            nome=rotulo_de(linha),
            valor=valor,
            fatia=_porcento(valor, total),
            largura=_largura(valor, maior),
            cor=CORES[posicao % len(CORES)],
        ))
    return fatias


def _recortes_da_venda(importacao, desde, ate):
    """Dia da semana, forma de pagamento e hora do dia, no período escolhido."""
    vendas = VendaImportada.objects.filter(importacao=importacao, data__gte=desde, data__lte=ate)

    por_dia = {linha["dia_da_semana"]: linha for linha in vendas.values("dia_da_semana")
               .annotate(valor=Sum("valor"), quantas=Count("id"))}
    dias = _barras(
        [{"valor": por_dia.get(numero, {}).get("valor") or ZERO,
          "quantas": por_dia.get(numero, {}).get("quantas") or 0, "nome": nome}
         for numero, nome in enumerate(DIAS_DA_SEMANA)],
        lambda linha: linha["nome"],
    )

    formas = _barras(
        list(vendas.exclude(forma_pagamento="").values("forma_pagamento")
             .annotate(valor=Sum("valor"), quantas=Count("id")).order_by("-valor")),
        lambda linha: linha["forma_pagamento"],
    )

    # A hora vem como texto "HH:MM:SS" do SET; os dois primeiros dígitos bastam.
    cru = (vendas.exclude(hora="").annotate(hh=Substr("hora", 1, 2)).values("hh")
           .annotate(valor=Sum("valor"), quantas=Count("id")))
    somas = {}
    for linha in cru:
        try:
            hora = int(linha["hh"])
        except (TypeError, ValueError):
            continue
        for comeco, fim, nome in FAIXAS_DE_HORA:
            if comeco <= hora < fim:
                atual = somas.setdefault(nome, {"valor": ZERO, "quantas": 0, "nome": nome})
                atual["valor"] += _decimal(linha["valor"])
                atual["quantas"] += linha["quantas"]
                break
    horas = _barras(
        [somas[nome] for _, _, nome in FAIXAS_DE_HORA if nome in somas],
        lambda linha: linha["nome"],
    )
    return dias, formas, horas


def montar(importacao, periodo=PERIODO_PADRAO, grupo="", fornecedor=""):
    """Monta o dashboard inteiro. Sem importação concluída, devolve a tela vazia."""
    painel = Dashboard()
    if importacao is None or not importacao.data_corte:
        return painel

    periodo = periodo if periodo in DIAS_DO_PERIODO else PERIODO_PADRAO
    desde, ate, dias = _janela(importacao, periodo)
    painel.importacao = importacao
    painel.periodo = periodo
    painel.rotulo_periodo = ROTULO_DO_PERIODO[periodo]
    painel.desde, painel.ate = desde, ate
    painel.tem_dados = True

    todos = ProdutoImportado.objects.filter(importacao=importacao)
    # order_by() vazio de propósito: o modelo ordena por código, e com a ordenação de pé
    # o DISTINCT passa a ser por (grupo, código) — a lista vinha com os onze mil produtos
    # em vez dos trinta e cinco grupos.
    painel.grupos_disponiveis = sorted(
        nome for nome in todos.exclude(grupo="").order_by().values_list("grupo", flat=True).distinct()
        if nome)
    painel.fornecedores_disponiveis = sorted(
        nome for nome in todos.exclude(fornecedor="").order_by()
        .values_list("fornecedor", flat=True).distinct()
        if nome)
    painel.filtro_grupo = grupo if grupo in painel.grupos_disponiveis else ""
    painel.filtro_fornecedor = fornecedor if fornecedor in painel.fornecedores_disponiveis else ""

    resumo, painel.kpis_da_venda = _kpis_da_venda(importacao, desde, ate, dias)
    painel.vendas_no_periodo = resumo["vendas"]

    consulta = _produtos(importacao, painel.filtro_grupo, painel.filtro_fornecedor)
    painel.produtos_no_filtro, painel.kpis_do_estoque = _kpis_do_estoque(consulta)

    painel.meses = _meses(importacao)
    painel.grupos = _grupos(consulta)
    painel.abc = _abc(consulta)
    painel.campeoes_faturamento, painel.campeoes_margem = _campeoes(consulta)
    painel.dias_da_semana, painel.formas, painel.horas = _recortes_da_venda(importacao, desde, ate)
    return painel
