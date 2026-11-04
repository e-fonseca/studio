"""Os quadros de Contas a pagar no formato do Dashboard (1.47.0).

Pedido do Edson em 04/11/2026, com o print do Dashboard: *"usar esse formato de gráfico
também em contas a pagar"*. São os mesmos desenhos, do mesmo arquivo
(apps/painel/dashboard.py e templates/painel/_monitor_*.html), com os números do
financeiro. Três quadros, nenhum número que a tela já não tivesse:

- **Contas pagas mês a mês**: o que a loja pagou em cada mês, na linha verde, e o mesmo
  mês do ano passado, na laranja. Aqui a cor da porcentagem é a do caixa: pagar mais que
  no ano passado é vermelho, pagar menos é verde.
- **O que está em aberto**: a rosca das contas em aberto no SET, nas mesmas fatias dos
  filtros da lista (atrasadas, as que vencem em até 7 dias, as de depois e as sem data).
  O nome de cada fatia abre a lista dela.
- **Para onde vai o dinheiro**: a rosca do que foi pago em 12 meses pela classificação do
  plano de contas do SET, a mesma conta da tela Despesas.

O mês que ainda corre é comparado com o MESMO PEDAÇO do ano passado (do dia 1º ao dia do
corte), como no faturamento: sete dias contra o mês inteiro acusariam uma economia que não
existe. E o ano passado só entra quando o mês dele está inteiro na foto: até a 1.46.0 a
leitura do SET começava no meio de um mês, e o primeiro mês do gráfico compararia um mês
cheio com dez dias (ver `_inteiro_desde`).
"""

import calendar
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.urls import reverse
from django.utils import timezone

from apps.painel import dashboard

from . import servicos
from .models import Lancamento

ZERO = Decimal("0")
MESES_NO_GRAFICO = dashboard.MESES_NO_GRAFICO
QUANTOS_GRUPOS = dashboard.QUANTOS_GRUPOS
# Até a 1.46.0 a importação lia o que foi pago DEPOIS de "corte menos 730 dias", sem
# gravar de quando. Foto dessa época vale a regra antiga (apps/importacao/fontes/firebird.py).
DIAS_DA_LEITURA_ANTIGA = 730
# "1.07.01 - Compra p/ Revenda": o número é do plano de contas e não diz nada a quem lê a
# rosca. O nome inteiro continua na tela Despesas.
CODIGO_DO_PLANO = re.compile(r"^\s*[\d.]+\s*-\s*")


@dataclass
class QuadrosDasContas:
    meses: list = field(default_factory=list)
    linha: dashboard.GraficoDeLinha = field(default_factory=dashboard.GraficoDeLinha)
    em_aberto: dashboard.Rosca = field(default_factory=dashboard.Rosca)
    total_em_aberto: Decimal = ZERO
    destino: dashboard.Rosca = field(default_factory=dashboard.Rosca)

    @property
    def tem(self):
        return self.linha.tem or self.em_aberto.tem or self.destino.tem


def _inteiro_desde(importacao):
    """O primeiro dia a partir do qual TODO o pago do SET está na foto."""
    texto = (importacao.detalhe or {}).get("financeiro_desde")
    if texto:
        try:
            return date.fromisoformat(texto)
        except (TypeError, ValueError):
            pass
    return importacao.data_corte - timedelta(days=DIAS_DA_LEITURA_ANTIGA - 1)


def _treze_meses(corte):
    """(ano, mês) dos 13 meses do gráfico, do mais antigo ao do corte."""
    total = corte.year * 12 + corte.month - 1
    return [((total - atras) // 12, (total - atras) % 12 + 1)
            for atras in range(MESES_NO_GRAFICO - 1, -1, -1)]


def _pago(consulta):
    return consulta.aggregate(v=Sum("valor_pago"))["v"] or ZERO


def pagas_mes_a_mes(importacao):
    """O que a loja pagou em cada um dos 13 meses, com o mesmo mês do ano passado."""
    if importacao is None or importacao.data_corte is None:
        return []
    corte = importacao.data_corte
    chaves = _treze_meses(corte)
    pagas = Lancamento.objects.filter(importacao=importacao, tipo=Lancamento.Tipo.PAGAR,
                                      pagamento__isnull=False, pagamento__lte=corte)
    desde = date(chaves[0][0] - 1, chaves[0][1], 1)
    por_mes = {
        (linha["pagamento__year"], linha["pagamento__month"]): (linha["valor"] or ZERO, linha["quantas"])
        for linha in pagas.filter(pagamento__gte=desde)
        .values("pagamento__year", "pagamento__month")
        .annotate(valor=Sum("valor_pago"), quantas=Count("id"))
    }
    inteiro_desde = _inteiro_desde(importacao)
    corre = corte.day < calendar.monthrange(corte.year, corte.month)[1]

    meses = []
    for ano, mes in chaves:
        valor, quantas = por_mes.get((ano, mes), (ZERO, 0))
        parcial = corre and (ano, mes) == (corte.year, corte.month)
        if date(ano - 1, mes, 1) < inteiro_desde:
            antes = None
        elif parcial:
            ultimo = min(corte.day, calendar.monthrange(ano - 1, mes)[1])
            antes = _pago(pagas.filter(pagamento__gte=date(ano - 1, mes, 1),
                                       pagamento__lte=date(ano - 1, mes, ultimo)))
        else:
            antes = por_mes.get((ano - 1, mes), (ZERO, 0))[0]
        meses.append(dashboard.Mes(
            rotulo=f"{dashboard.MESES_CURTOS[mes]}/{str(ano)[2:]}",
            valor=valor.quantize(Decimal("0.01")),
            vendas=quantas,
            valor_ano_passado=antes.quantize(Decimal("0.01")) if antes is not None else None,
            parcial=parcial,
            dia_parcial=corte.day if parcial else None,
            mais_e_bom=False,
        ))
    return meses


def rosca_do_que_esta_em_aberto(importacao, hoje=None):
    """As contas em aberto no SET nas fatias dos filtros da lista, e o total delas."""
    if importacao is None:
        return dashboard.Rosca(), ZERO
    hoje = hoje or timezone.localdate()
    semana = hoje + timedelta(days=servicos.DIAS_PRESTES_A_VENCER)
    abertas = Lancamento.objects.filter(importacao=importacao, tipo=Lancamento.Tipo.PAGAR,
                                        pagamento__isnull=True)
    somas = abertas.aggregate(
        atrasadas=Sum("valor", filter=Q(vencimento__lt=hoje)),
        semana=Sum("valor", filter=Q(vencimento__gte=hoje, vencimento__lte=semana)),
        depois=Sum("valor", filter=Q(vencimento__gt=semana)),
        sem_data=Sum("valor", filter=Q(vencimento__isnull=True)),
    )
    lista = reverse("financeiro:contas_a_pagar")
    pedacos = (
        ("Atrasadas", somas["atrasadas"], "--mon-vermelho", f"{lista}?filtro=atrasados"),
        (f"Vencem em até {servicos.DIAS_PRESTES_A_VENCER} dias", somas["semana"], "--mon-laranja",
         f"{lista}?filtro=prestes"),
        (f"Vencem depois de {servicos.DIAS_PRESTES_A_VENCER} dias", somas["depois"], "--mon-azul",
         f"{lista}?filtro=futura"),
        ("Sem data no SET", somas["sem_data"], "--cor-fatia-9", ""),
    )
    fatias = [dashboard.Fatia(nome, (valor or ZERO).quantize(Decimal("0.01")), cor=cor, endereco=endereco)
              for nome, valor, cor, endereco in pedacos if valor and valor > ZERO]
    total = sum((fatia.valor for fatia in fatias), ZERO)
    if not total:
        return dashboard.Rosca(), ZERO
    atrasadas = somas["atrasadas"] or ZERO
    return dashboard.Rosca(
        fatias=dashboard.fatiar(fatias, total),
        centro=f"{dashboard.porcento(atrasadas, total)}%".replace(".", ","),
        centro_legenda="atrasado",
    ), total


def rosca_de_para_onde_vai(importacao):
    """O pago em 12 meses pela classificação do SET: os oito maiores e o resto junto."""
    grupos = servicos.despesas_por_grupo(importacao)
    total = sum((grupo["valor"] for grupo in grupos), ZERO)
    if not total:
        return dashboard.Rosca()
    # Sobrando uma só, ela entra pelo nome: "outras 1 classificações" não diz nada.
    principais = grupos if len(grupos) <= QUANTOS_GRUPOS + 1 else grupos[:QUANTOS_GRUPOS]
    fatias = [
        dashboard.Fatia(CODIGO_DO_PLANO.sub("", grupo["grupo"]) or grupo["grupo"], grupo["valor"],
                        cor=dashboard.CORES[posicao % len(dashboard.CORES)])
        for posicao, grupo in enumerate(principais)
    ]
    resto = sum((grupo["valor"] for grupo in grupos[len(principais):]), ZERO)
    if resto:
        fatias.append(dashboard.Fatia(f"outras {len(grupos) - len(principais)} classificações",
                                      resto, cor=dashboard.CORES[len(fatias) % len(dashboard.CORES)]))
    return dashboard.Rosca(fatias=dashboard.fatiar(fatias, total))


def montar(importacao, hoje=None):
    """Os três quadros do alto de Contas a pagar."""
    quadros = QuadrosDasContas()
    if importacao is None:
        return quadros
    quadros.meses = pagas_mes_a_mes(importacao)
    quadros.linha = dashboard.grafico_de_linha(quadros.meses)
    quadros.em_aberto, quadros.total_em_aberto = rosca_do_que_esta_em_aberto(importacao, hoje)
    quadros.destino = rosca_de_para_onde_vai(importacao)
    return quadros
