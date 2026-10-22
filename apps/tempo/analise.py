"""Cruzar o tempo que fez com o que a loja vendeu no dia.

A pergunta do Edson é "quanto o clima pesa no negócio", e ela só tem resposta honesta se
o fim de semana for separado do meio de semana. A loja faz 76% do faturamento no sábado
e no domingo: misturar um sábado de chuva com uma terça de sol mediria o dia da semana,
não o tempo, e devolveria um número que parece análise e não é.

Então a conta é sempre dentro do mesmo tipo de dia: fim de semana e feriado de um lado,
meio de semana do outro, e dentro de cada um a média do que a loja vendeu nos dias de
chuva contra a média dos dias sem chuva.

Dia sem registro de tempo fica de fora da média e é contado à parte, para a tela poder
dizer em quantos dias a conta se apoia. Média de três dias não é conclusão, e a tela diz
isso em vez de deixar alguém decidir compra por ela.

Dia marcado como PREVISÃO também fica de fora, e isso não é detalhe: desde a 1.29.0 a
busca guarda os próximos dias para a loja se preparar, e hoje mesmo nasce como previsão
às 06:10 da manhã. Entrar na média, a previsão mediria palpite contra medição. Ela tem
lugar próprio, no indicador da Visão geral (apps/tempo/indicador.py).
"""

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum

from apps.tempo.models import TempoDoDia

ZERO = Decimal("0")
# Abaixo disto a média é curiosidade, não medida. A tela avisa em vez de calar.
DIAS_PARA_CONCLUIR = 8
# Quantos dias a tabela da tela abre. O resto está no arquivo.
DIAS_NA_TABELA = 45


@dataclass
class Grupo:
    """Um tipo de dia (fim de semana ou meio de semana), com chuva e sem chuva."""

    nome: str
    dias_com_chuva: int = 0
    dias_sem_chuva: int = 0
    venda_com_chuva: Decimal = ZERO
    venda_sem_chuva: Decimal = ZERO

    @property
    def media_com_chuva(self):
        if not self.dias_com_chuva:
            return None
        return (self.venda_com_chuva / self.dias_com_chuva).quantize(Decimal("0.01"))

    @property
    def media_sem_chuva(self):
        if not self.dias_sem_chuva:
            return None
        return (self.venda_sem_chuva / self.dias_sem_chuva).quantize(Decimal("0.01"))

    @property
    def diferenca(self):
        """Quanto a loja deixa de vender, em média, num dia de chuva deste tipo."""
        com, sem = self.media_com_chuva, self.media_sem_chuva
        if com is None or sem is None:
            return None
        return com - sem

    @property
    def variacao(self):
        com, sem = self.media_com_chuva, self.media_sem_chuva
        if com is None or sem is None or sem <= ZERO:
            return None
        return int(round((com - sem) * 100 / sem))

    @property
    def dias(self):
        return self.dias_com_chuva + self.dias_sem_chuva

    @property
    def da_para_concluir(self):
        return min(self.dias_com_chuva, self.dias_sem_chuva) >= DIAS_PARA_CONCLUIR

    @property
    def largura_com_chuva(self):
        return self._largura(self.media_com_chuva)

    @property
    def largura_sem_chuva(self):
        return self._largura(self.media_sem_chuva)

    def _largura(self, valor):
        """Inteiro: decimal em style= sai localizado e o navegador ignora a linha."""
        maior = max(filter(None, (self.media_com_chuva, self.media_sem_chuva)), default=None)
        if not maior or valor is None:
            return 0
        return int(round(valor * 100 / maior))


@dataclass
class DiaNaTabela:
    data: object
    dia_da_semana: str
    fim_de_semana: bool
    tempo: object = None
    venda: Decimal = ZERO
    vendas: int = 0

    @property
    def tem_tempo(self):
        return self.tempo is not None


@dataclass
class Analise:
    fim_de_semana: Grupo = field(default_factory=lambda: Grupo("Fim de semana e feriado"))
    meio_de_semana: Grupo = field(default_factory=lambda: Grupo("Meio de semana"))
    dias_com_venda: int = 0
    dias_com_tempo: int = 0
    dias_sem_tempo: int = 0
    primeiro_dia: object = None
    ultimo_dia: object = None
    tabela: list = field(default_factory=list)

    @property
    def grupos(self):
        return [self.fim_de_semana, self.meio_de_semana]

    @property
    def tem_dados(self):
        return self.dias_com_tempo > 0

    @property
    def da_para_concluir(self):
        return any(grupo.da_para_concluir for grupo in self.grupos)

    @property
    def falta_quanto(self):
        """Quantos dias de registro ainda faltam para a conta começar a valer."""
        faltas = [DIAS_PARA_CONCLUIR - min(g.dias_com_chuva, g.dias_sem_chuva)
                  for g in self.grupos]
        return max(min(faltas), 0)


DIAS_DA_SEMANA = ("Domingo", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado")


def _vendas_por_dia(importacao):
    """Quanto a loja vendeu em cada dia da foto, numa consulta só."""
    if importacao is None:
        return {}
    linhas = (
        importacao.vendas.values("data", "dia_da_semana")
        .annotate(total=Sum("valor"), quantas=Count("id"))
        .order_by("data")
    )
    return {
        linha["data"]: (linha["total"] or ZERO, linha["quantas"], linha["dia_da_semana"])
        for linha in linhas
    }


def montar(importacao, dias_na_tabela=DIAS_NA_TABELA) -> Analise:
    """A conta do clima contra a venda, separada por tipo de dia."""
    analise = Analise()
    vendas = _vendas_por_dia(importacao)
    if not vendas:
        return analise

    analise.dias_com_venda = len(vendas)
    analise.primeiro_dia = min(vendas)
    analise.ultimo_dia = max(vendas)
    tempos = {
        registro.data: registro
        for registro in TempoDoDia.objects.filter(
            data__gte=analise.primeiro_dia, data__lte=analise.ultimo_dia)
        .exclude(previsao=True)
    }

    for data in sorted(vendas, reverse=True):
        total, quantas, dia_da_semana = vendas[data]
        tempo = tempos.get(data)
        # Sábado e domingo valem como fim de semana; o feriado entra junto porque é
        # quando a loja tem público, e foi assim que o Edson descreveu o negócio.
        fim_de_semana = dia_da_semana in (0, 6) or bool(tempo and tempo.feriado)
        if tempo is None:
            analise.dias_sem_tempo += 1
        else:
            analise.dias_com_tempo += 1
            grupo = analise.fim_de_semana if fim_de_semana else analise.meio_de_semana
            if tempo.choveu:
                grupo.dias_com_chuva += 1
                grupo.venda_com_chuva += total
            else:
                grupo.dias_sem_chuva += 1
                grupo.venda_sem_chuva += total
        if len(analise.tabela) < dias_na_tabela:
            analise.tabela.append(DiaNaTabela(
                data=data, dia_da_semana=DIAS_DA_SEMANA[dia_da_semana],
                fim_de_semana=fim_de_semana, tempo=tempo, venda=total, vendas=quantas,
            ))
    return analise


def dias_sem_registro(importacao, quantos=14, ate=None):
    """Os últimos dias com venda que ainda não têm o tempo anotado.

    É o que a tela usa para pedir o registro de um jeito que dá para responder: uma lista
    curta de datas com um campo cada, em vez de um calendário em branco.
    """
    if importacao is None:
        return []
    ate = ate or importacao.data_corte
    if ate is None:
        return []
    desde = ate - timedelta(days=quantos * 3)
    datas = list(
        importacao.vendas.filter(data__gte=desde, data__lte=ate)
        .values_list("data", flat=True).distinct().order_by("-data")
    )
    # A previsão da véspera não conta como registro: o dia continua precisando do que
    # aconteceu de verdade, e é justamente isso que esta lista vai pedir.
    com_registro = set(
        TempoDoDia.objects.filter(data__in=datas).exclude(previsao=True)
        .values_list("data", flat=True)
    )
    return [data for data in datas if data not in com_registro][:quantos]


def em_linhas(analise):
    """A tabela do tempo e da venda, dia a dia, para o arquivo."""
    cabecalho = ("Data", "Dia da semana", "Tipo de dia", "Condição", "Chuva (mm)",
                 "Temperatura mínima", "Temperatura máxima", "Feriado", "Observação",
                 "Vendas", "Faturamento")
    linhas = [cabecalho]
    for dia in analise.tabela:
        tempo = dia.tempo
        linhas.append((
            dia.data.strftime("%d/%m/%Y"), dia.dia_da_semana,
            "Fim de semana" if dia.fim_de_semana else "Meio de semana",
            tempo.get_condicao_display() if tempo and tempo.condicao else "",
            tempo.chuva_mm if tempo else "",
            tempo.temperatura_minima if tempo else "",
            tempo.temperatura_maxima if tempo else "",
            "sim" if tempo and tempo.feriado else "",
            tempo.observacao if tempo else "",
            dia.vendas, dia.venda,
        ))
    return linhas
