"""Os quadros de Contas a pagar no formato do Dashboard (1.47.0).

Pedido do Edson em 04/11/2026, com o print do Dashboard: *"usar esse formato de gráfico
também em contas a pagar"*. São os mesmos desenhos, do mesmo arquivo
(apps/painel/dashboard.py e templates/painel/_monitor_*.html), com os números do
financeiro. Três quadros, nenhum número que a tela já não tivesse:

- **Contas pagas mês a mês**: o que a loja pagou em cada mês, de janeiro a dezembro, uma
  linha para cada um dos últimos três anos (1.48.0): o de agora em verde, o ano passado em
  laranja, o retrasado em azul. Aqui a cor da porcentagem é a do caixa: pagar mais que no
  ano passado é vermelho, pagar menos é verde.
- **O que está em aberto**: a rosca das contas em aberto no SET, nas mesmas fatias dos
  filtros da lista (atrasadas, as que vencem em até 7 dias, as de depois e as sem data).
  O nome de cada fatia abre a lista dela.
- **Para onde vai o dinheiro**: a rosca do que foi pago em 12 meses pela classificação do
  plano de contas do SET, a mesma conta da tela Despesas.

O mês que ainda corre é comparado com o MESMO PEDAÇO do ano passado (do dia 1º ao dia do
corte), como no faturamento: sete dias contra o mês inteiro acusariam uma economia que não
existe. E um mês só entra no desenho quando está inteiro na foto: até a 1.46.0 a leitura do
SET começava no meio de um mês, e até a 1.47.1 ela não chegava ao janeiro do retrasado (ver
`_inteiro_desde`). Mês que a foto não tem inteiro fica em branco, nunca em zero.

Por que de janeiro a dezembro, e não os 13 meses que andam, como no Dashboard: pedido do
Edson em 04/11/2026, *"nesse mesmo gráfico do contas a pagar manter sempre os últimos 3
anos"*. Com o mês fixo embaixo, cada ano é uma linha inteira, o mês que costuma pesar
aparece nos três anos, um sobre o outro, e os meses que ainda faltam neste ano mostram o
que a loja pagou neles antes, que é o que vem pela frente.
"""

import calendar
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Min, Q, Sum
from django.urls import reverse
from django.utils import timezone

from apps.painel import dashboard

from . import servicos
from .models import Lancamento

ZERO = Decimal("0")
# O ano do corte e os dois anteriores, um por linha, nas cores do dashboard.PAPEIS_DOS_ANOS.
ANOS_NO_GRAFICO = len(dashboard.PAPEIS_DOS_ANOS)
QUANTOS_GRUPOS = dashboard.QUANTOS_GRUPOS
# Até a 1.46.0 a importação lia o que foi pago DEPOIS de "corte menos 730 dias", sem
# gravar de quando. Foto dessa época vale a regra antiga (apps/importacao/fontes/firebird.py).
DIAS_DA_LEITURA_ANTIGA = 730
# "1.07.01 - Compra p/ Revenda": o número é do plano de contas e não diz nada a quem lê a
# rosca. O nome inteiro continua na tela Despesas.
CODIGO_DO_PLANO = re.compile(r"^\s*[\d.]+\s*-\s*")


@dataclass
class QuadrosDasContas:
    pagas: dashboard.TresAnos = field(default_factory=dashboard.TresAnos)
    em_aberto: dashboard.Rosca = field(default_factory=dashboard.Rosca)
    total_em_aberto: Decimal = ZERO
    destino: dashboard.Rosca = field(default_factory=dashboard.Rosca)

    @property
    def tem(self):
        return self.pagas.grafico.tem or self.em_aberto.tem or self.destino.tem


def _inteiro_desde(importacao):
    """O primeiro dia a partir do qual TODO o pago do SET está na foto.

    Desde a 1.48.0 a importação grava a data do pago (`pagas_desde`, três anos); na 1.47.x
    era uma data só para o pago e o recebido (`financeiro_desde`, 24 meses); antes disso,
    nenhuma, e vale a conta da leitura antiga.
    """
    detalhe = importacao.detalhe or {}
    for chave in ("pagas_desde", "financeiro_desde"):
        try:
            return date.fromisoformat(detalhe[chave])
        except (KeyError, TypeError, ValueError):
            continue
    return importacao.data_corte - timedelta(days=DIAS_DA_LEITURA_ANTIGA - 1)


def _comeco_do_lancado(primeira, inteiro_desde):
    """O primeiro dia em que o pago está inteiro na foto E lançado no SET.

    A leitura traz três anos, mas no backup de 20/09/2026 a primeira conta paga do SET é de
    27/02/2024, o mesmo dia do primeiro caixa: antes disso a loja não usava o financeiro do
    SET. Janeiro de 2024 não é mês em que a loja não pagou nada, é mês que o SET não tem, e
    em zero ele diria o contrário. Por isso o desenho começa no primeiro mês inteiro depois
    da primeira conta lançada (o próprio mês dela, só se ela for do dia 1º). Quando a
    primeira conta cai no primeiro mês da leitura, quem manda é a leitura.
    """
    if primeira is None:
        return inteiro_desde
    mes_da_primeira = primeira.replace(day=1)
    if mes_da_primeira <= inteiro_desde:
        return inteiro_desde
    if primeira.day == 1:
        return mes_da_primeira
    return (mes_da_primeira + timedelta(days=31)).replace(day=1)


def _ate_o_dia_do_corte(ano, mes, corte):
    """O dia do corte naquele mês daquele ano: 29/02 vira 28/02 no ano que não é bissexto."""
    return date(ano, mes, min(corte.day, calendar.monthrange(ano, mes)[1]))


def pagas_por_ano(importacao):
    """O que a loja pagou em cada mês do ano do corte e dos dois anteriores."""
    if importacao is None or importacao.data_corte is None:
        return dashboard.TresAnos()
    corte = importacao.data_corte
    anos = [corte.year - atras for atras in range(ANOS_NO_GRAFICO)]
    pagas = Lancamento.objects.filter(importacao=importacao, tipo=Lancamento.Tipo.PAGAR,
                                      pagamento__isnull=False, pagamento__lte=corte)
    por_mes = {
        (linha["pagamento__year"], linha["pagamento__month"]): linha["valor"] or ZERO
        for linha in pagas.filter(pagamento__gte=date(anos[-1], 1, 1))
        .values("pagamento__year", "pagamento__month")
        .annotate(valor=Sum("valor_pago"))
    }
    # O mês do corte do dia 1º ao dia do corte, em cada ano passado: é com ele que o mês
    # que corre se compara, e é ele que fecha o "Até 3/nov". Uma consulta só para todos.
    pedacos = pagas.aggregate(
        primeira=Min("pagamento"),
        **{f"ano_{ano}": Sum("valor_pago", filter=Q(
            pagamento__gte=date(ano, corte.month, 1),
            pagamento__lte=_ate_o_dia_do_corte(ano, corte.month, corte))) for ano in anos[1:]},
    )
    comeco_da_leitura = _inteiro_desde(importacao)
    inteiro_desde = _comeco_do_lancado(pedacos["primeira"], comeco_da_leitura)
    tres = dashboard.tres_anos(
        corte, por_mes, {ano: pedacos[f"ano_{ano}"] or ZERO for ano in anos[1:]},
        inteiro_desde, mais_e_bom=False)
    # A tela diz de quando o SET tem conta lançada só quando foi isso, e não a leitura, que
    # deixou mês do gráfico em branco.
    if inteiro_desde > comeco_da_leitura and inteiro_desde > date(anos[-1], 1, 1):
        tres.lancamento = "conta paga"
        tres.lancado_desde = pedacos["primeira"]
        tres.comeca_em = f"{dashboard.MESES_CURTOS[inteiro_desde.month]}/{inteiro_desde.year}"
    return tres


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
    quadros.pagas = pagas_por_ano(importacao)
    quadros.em_aberto, quadros.total_em_aberto = rosca_do_que_esta_em_aberto(importacao, hoje)
    quadros.destino = rosca_de_para_onde_vai(importacao)
    return quadros
