"""Fluxo de caixa: o que entrou, o que saiu e o que vem pela frente, mês a mês, pelo SET.

Pedido do Edson, 05/11/2026: *"um dos objetivos é controlar o financeiro, o que entrou, o
que saiu e a projeção futura."*

A fonte é **o SET**, pela última importação: contas a receber e a pagar, pagas (o que
entrou e saiu) e em aberto (o que vem), mais os pagamentos previstos registrados aqui que
ainda não estão no SET.

Até 06/11/2026 somava também as parcelas lançadas nos projetos. Com o protótipo da
Henriett, os pedidos passaram a ter o dinheiro calculado pelas regras de cada oficina, e
essa conta mora no Planejamento (apps/planejamento). Somar os dois aqui contaria duas
vezes o que o SET também tem lançado, e não há como saber o que é a mesma conta: por isso
esta tela é a do SET e o Planejamento é a das regras do Studio.

O mês corrente aparece com o realizado e o previsto lado a lado: metade do mês já
aconteceu e metade ainda vai acontecer. O que venceu e não foi pago (dos dois lados) entra
como previsto no mês corrente, porque é dinheiro que se espera agora, e é mostrado à parte
para não passar por conta em dia.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from .models import Lancamento, PagamentoPrevisto

ZERO = Decimal("0")
MESES_ANTES = 3
MESES_DEPOIS = 6
NOMES = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")


def _somar_mes(ano, mes, quantos):
    indice = ano * 12 + (mes - 1) + quantos
    return indice // 12, indice % 12 + 1


@dataclass
class Mes:
    ano: int
    mes: int
    momento: str  # "passado", "atual" ou "futuro"
    entrou: Decimal = ZERO
    saiu: Decimal = ZERO
    vai_entrar: Decimal = ZERO
    vai_sair: Decimal = ZERO
    saldo_projetado: Decimal = ZERO  # acumulado, do mês corrente em diante

    @property
    def rotulo(self):
        return f"{NOMES[self.mes - 1]}/{self.ano}"

    @property
    def realizado(self):
        return self.entrou - self.saiu

    @property
    def previsto(self):
        return self.vai_entrar - self.vai_sair

    @property
    def resultado(self):
        """O mês inteiro: o que já aconteceu mais o que ainda vai acontecer nele."""
        return self.realizado + self.previsto


@dataclass
class Fluxo:
    meses: list = field(default_factory=list)
    atrasado_entrar: Decimal = ZERO
    atrasado_sair: Decimal = ZERO
    sem_data_sair: Decimal = ZERO
    tem_set: bool = False

    @property
    def total_vai_entrar(self):
        return sum((m.vai_entrar for m in self.meses), ZERO)

    @property
    def ultimo(self):
        return self.meses[-1] if self.meses else None

    @property
    def total_vai_sair(self):
        return sum((m.vai_sair for m in self.meses), ZERO)


def _chave(dia):
    return dia.year, dia.month


def montar(importacao, hoje=None):
    hoje = hoje or timezone.localdate()
    inicio_ano, inicio_mes = _somar_mes(hoje.year, hoje.month, -MESES_ANTES)
    fim_ano, fim_mes = _somar_mes(hoje.year, hoje.month, MESES_DEPOIS)
    primeiro_dia = date(inicio_ano, inicio_mes, 1)
    depois_do_fim = date(*_somar_mes(fim_ano, fim_mes, 1), 1)

    fluxo = Fluxo()
    por_mes = {}
    for deslocamento in range(-MESES_ANTES, MESES_DEPOIS + 1):
        ano, mes = _somar_mes(hoje.year, hoje.month, deslocamento)
        momento = "passado" if deslocamento < 0 else ("atual" if deslocamento == 0 else "futuro")
        por_mes[(ano, mes)] = Mes(ano, mes, momento)
    fluxo.meses = list(por_mes.values())
    atual = por_mes[_chave(hoje)]

    def somar(linhas, campo_data, campo_valor, atributo):
        for linha in linhas.values(campo_data).annotate(v=Sum(campo_valor)):
            dia = linha[campo_data]
            mes = por_mes.get(_chave(dia)) if dia else None
            if mes is not None:
                setattr(mes, atributo, getattr(mes, atributo) + (linha["v"] or ZERO))

    # O SET ---------------------------------------------------------------------------
    if importacao is not None:
        do_set = Lancamento.objects.filter(importacao=importacao)
        fluxo.tem_set = do_set.exists()
        pagos = do_set.filter(pagamento__gte=primeiro_dia, pagamento__lte=hoje)
        # O valor pago, e não o da conta: é ele que diz o que passou pelo caixa (desconto,
        # juros e pagamento parcial mudam o número). Conta paga sem valor pago no SET usa o
        # valor da conta, que é melhor do que contar zero.
        for tipo, atributo in ((Lancamento.Tipo.RECEBER, "entrou"), (Lancamento.Tipo.PAGAR, "saiu")):
            for linha in pagos.filter(tipo=tipo).values("pagamento", "valor", "valor_pago"):
                mes = por_mes.get(_chave(linha["pagamento"]))
                if mes is not None:
                    valor = linha["valor_pago"] or linha["valor"] or ZERO
                    setattr(mes, atributo, getattr(mes, atributo) + valor)
        abertos = do_set.filter(pagamento__isnull=True)
        for tipo, atributo in ((Lancamento.Tipo.RECEBER, "vai_entrar"), (Lancamento.Tipo.PAGAR, "vai_sair")):
            somar(abertos.filter(tipo=tipo, vencimento__gte=hoje, vencimento__lt=depois_do_fim),
                  "vencimento", "valor", atributo)
            atrasado = abertos.filter(tipo=tipo, vencimento__lt=hoje).aggregate(
                v=Sum("valor"))["v"] or ZERO
            if tipo == Lancamento.Tipo.RECEBER:
                fluxo.atrasado_entrar += atrasado
            else:
                fluxo.atrasado_sair += atrasado
        fluxo.sem_data_sair = abertos.filter(
            tipo=Lancamento.Tipo.PAGAR, vencimento__isnull=True).aggregate(v=Sum("valor"))["v"] or ZERO

    previstos = PagamentoPrevisto.objects.filter(lancado_no_set=False)
    somar(previstos.filter(vencimento__gte=hoje, vencimento__lt=depois_do_fim),
          "vencimento", "valor", "vai_sair")
    fluxo.atrasado_sair += previstos.filter(vencimento__lt=hoje).aggregate(v=Sum("valor"))["v"] or ZERO

    # O atrasado é esperado agora: entra no previsto do mês corrente.
    atual.vai_entrar += fluxo.atrasado_entrar
    atual.vai_sair += fluxo.atrasado_sair

    # O saldo projetado começa no mês corrente com o que ainda falta acontecer nele, e não
    # com o realizado: o realizado já está no banco, e a pergunta é se o que vem cabe.
    acumulado = ZERO
    for mes in fluxo.meses:
        if mes.momento == "passado":
            continue
        acumulado += mes.previsto
        mes.saldo_projetado = acumulado
    return fluxo
