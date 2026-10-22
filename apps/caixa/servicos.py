"""A conta da tela de caixa: filtrar os turnos e somar o que interessa.

O SET já guarda tudo isso; o trabalho aqui é recortar por período, operador e
situação, somar e dizer o que está estranho — caixa que não fecha pela conta dos
próprios movimentos, caixa esquecido aberto e sangria fora do normal.
"""

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from . import dinheiro as dinheiro_servicos
from .models import CaixaImportado, MovimentoCaixa

ZERO = Decimal("0")

# (valor na URL, rótulo na tela, dias para trás; None é tudo o que foi importado)
PERIODOS = (
    ("30d", "30 dias", 30),
    ("90d", "90 dias", 90),
    ("12m", "12 meses", 365),
    ("tudo", "Tudo", None),
)
PERIODO_PADRAO = "30d"
DIAS_DO_PERIODO = dict((chave, dias) for chave, _, dias in PERIODOS)
ROTULO_DO_PERIODO = dict((chave, rotulo) for chave, rotulo, _ in PERIODOS)

SITUACOES = (("aberto", "Abertos"), ("fechado", "Fechados"))

# Caixa que ficou aberto de um dia para o outro é caixa esquecido: ninguém fica com o
# turno aberto mais de um dia de trabalho, e enquanto ele está aberto a venda do dia
# seguinte entra no turno errado.
#
# A régua é de DIAS, e não de horas. O "agora" que chega em `esta_esquecido` é a data de
# corte da importação, que é uma data sem hora: a conta nunca teve como saber de horas, e
# a tela dizia "mais de 24 horas" sobre uma conta de dias.
DIAS_PARA_ESQUECIDO = 1


@dataclass
class Resumo:
    """Os números do topo da tela, já no recorte escolhido."""

    caixas: int = 0
    dias: int = 0
    recebido: Decimal = ZERO
    sangrias: Decimal = ZERO
    pagamentos: Decimal = ZERO
    entradas: Decimal = ZERO
    abertos: int = 0
    nao_fecham: int = 0

    @property
    def media_por_dia(self):
        if not self.dias:
            return ZERO
        return (self.recebido / self.dias).quantize(Decimal("0.01"))


@dataclass
class Tela:
    importacao = None
    periodo: str = PERIODO_PADRAO
    rotulo_periodo: str = ""
    desde = None
    ate = None
    filtro_operador: str = ""
    filtro_situacao: str = ""
    operadores: list = field(default_factory=list)
    caixas: list = field(default_factory=list)
    resumo: Resumo = field(default_factory=Resumo)
    # O dinheiro vivo do período: o que entrou e saiu de papel, e a gaveta do último
    # turno. Não é uma Gaveta somada, e o porquê está em dinheiro.Periodo.
    gaveta: dinheiro_servicos.Periodo = field(default_factory=dinheiro_servicos.Periodo)
    esquecidos: list = field(default_factory=list)
    tem_dados: bool = False

    @property
    def filtrou(self):
        return bool(self.filtro_operador or self.filtro_situacao
                    or self.periodo != PERIODO_PADRAO)


def _ultimo_dia(importacao):
    """O último dia com caixa, ou a data de corte se for mais recente.

    A data de corte é o último dia com VENDA. O caixa aberto agora pode ter sido
    aberto depois dela (é o caso do turno 971, aberto em 21/09 com corte em 20/09) e,
    se a janela terminasse no corte, justamente o caixa aberto — que é o que o Edson
    pediu para ver — ficaria de fora do período padrão.
    """
    ultimo = (CaixaImportado.objects.filter(importacao=importacao)
              .order_by("-dia").values_list("dia", flat=True).first())
    if ultimo is None:
        return importacao.data_corte
    return max(ultimo, importacao.data_corte)


def _janela(importacao, periodo):
    dias = DIAS_DO_PERIODO.get(periodo)
    ate = _ultimo_dia(importacao)
    if dias is None:
        return None, ate
    return ate - timedelta(days=dias - 1), ate


def esta_esquecido(caixa, agora):
    """Caixa que abriu antes do dia da foto e continua aberto.

    `agora` é a data de corte da importação. A data da abertura sai de `localtime`, e não
    de `.date()` em cima do campo: `aberto_em` é gravado em UTC, e em São Paulo (UTC-3)
    todo turno aberto das 21h em diante cai no DIA SEGUINTE em UTC. Com `.date()` direto,
    o caixa aberto às 21:30 e esquecido a noite inteira aparecia como aberto "hoje" e
    nunca era apontado — e a loja vende nesse horário (ver as faixas de hora do
    Dashboard). Era o turno que mais engole a venda do dia seguinte.
    """
    if not caixa.esta_aberto:
        return False
    abertura = timezone.localtime(caixa.aberto_em).date()
    return (agora - abertura).days >= DIAS_PARA_ESQUECIDO


def montar(importacao, periodo=PERIODO_PADRAO, operador="", situacao=""):
    """A tela inteira. Sem importação concluída, devolve a tela vazia."""
    tela = Tela()
    if importacao is None or not importacao.data_corte:
        return tela

    periodo = periodo if periodo in DIAS_DO_PERIODO else PERIODO_PADRAO
    desde, ate = _janela(importacao, periodo)
    tela.importacao = importacao
    tela.periodo = periodo
    tela.rotulo_periodo = ROTULO_DO_PERIODO[periodo]
    tela.desde, tela.ate = desde, ate
    tela.tem_dados = True

    todos = CaixaImportado.objects.filter(importacao=importacao)
    tela.operadores = sorted(
        nome for nome in todos.order_by().values_list("operador", flat=True).distinct() if nome)
    tela.filtro_operador = operador if operador in tela.operadores else ""
    tela.filtro_situacao = situacao if situacao in dict(SITUACOES) else ""

    # Caixa esquecido aberto é problema de qualquer período: a loja precisa saber
    # agora, e não só se escolher o filtro certo.
    tela.esquecidos = [caixa for caixa in todos.filter(situacao=CaixaImportado.Situacao.ABERTO)
                       if esta_esquecido(caixa, ate)]

    consulta = todos
    if desde is not None:
        consulta = consulta.filter(dia__gte=desde, dia__lte=ate)
    if tela.filtro_operador:
        consulta = consulta.filter(operador=tela.filtro_operador)
    if tela.filtro_situacao:
        consulta = consulta.filter(situacao=tela.filtro_situacao)

    tela.caixas = list(consulta)
    somas = consulta.aggregate(
        quantos=Count("id"), dias=Count("dia", distinct=True),
        recebido=Sum("recebido"), sangrias=Sum("sangrias"),
        pagamentos=Sum("pagamentos"), entradas=Sum("entradas"),
        abertos=Count("id", filter=Q(situacao=CaixaImportado.Situacao.ABERTO)),
    )
    tela.resumo = Resumo(
        caixas=somas["quantos"] or 0,
        dias=somas["dias"] or 0,
        recebido=somas["recebido"] or ZERO,
        sangrias=somas["sangrias"] or ZERO,
        pagamentos=somas["pagamentos"] or ZERO,
        entradas=somas["entradas"] or ZERO,
        abertos=somas["abertos"] or 0,
        # Conferido em Python, e não no banco, porque a conta usa seis colunas e
        # uma tolerância de centavo; são poucas linhas e sai mais claro assim.
        nao_fecham=sum(1 for caixa in tela.caixas if not caixa.esta_aberto and not caixa.confere),
    )
    # Soma sobre os turnos já carregados: o dinheiro vivo sai do por_forma de cada um,
    # que é JSON, então não há agregação no banco que o resolva.
    tela.gaveta = dinheiro_servicos.do_periodo(tela.caixas)
    return tela


def formas_do_caixa(caixa):
    """O que entrou por forma de pagamento, em ordem de valor, para a tela do turno."""
    linhas = [(nome, Decimal(valor)) for nome, valor in (caixa.por_forma or {}).items()]
    linhas.sort(key=lambda linha: -linha[1])
    maior = linhas[0][1] if linhas else ZERO
    total = sum((valor for _, valor in linhas), ZERO)
    # Mesmo formato das barras do dashboard (templates/painel/_barras.html), para a tela
    # reaproveitar o desenho em vez de inventar outro.
    return [
        {"nome": nome, "valor": valor,
         # Largura em inteiro: Decimal dentro de style= sai com vírgula e o CSS ignora.
         "largura": 0 if not maior else max(1, int(valor * 100 / maior)),
         "fatia": ZERO if not total else (valor * 100 / total).quantize(Decimal("0.1"))}
        for nome, valor in linhas
    ]


def movimentos_do_caixa(caixa):
    return MovimentoCaixa.objects.filter(caixa=caixa).order_by("quando", "id")
