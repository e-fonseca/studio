"""O tempo como indicador da Visão geral.

Pedido do Edson em 14/10/2026: "remover do menu TEMPO E VENDA, virar recurso dentro de
visão geral, configurar api de previsão do tempo automática, armazenar informações
diárias e usar como indicador".

"Usar como indicador" é o que este módulo faz, e indicador aqui não é um número bonito:
é uma frase que muda o que a loja faz nesta semana. A loja fatura a maior parte no fim de
semana, então o indicador olha para frente — o que está previsto para o próximo fim de
semana — e põe ao lado o que a própria loja já pagou por isso: a média do que ela vende
num fim de semana de chuva contra um sem chuva, medida nos dias guardados.

Duas coisas que ele nunca faz:

- **Não mistura previsão com medição.** A previsão diz o que vem; a conta do custo sai só
  de dia fechado (apps/tempo/analise.py tira os dias marcados como previsão).
- **Não conclui com três dias.** Abaixo do mínimo de dias registrados, o indicador diz o
  que está previsto e admite que ainda não sabe quanto custa, em vez de inventar um
  número que alguém usaria para decidir compra.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from apps.tempo import analise as servico_de_analise
from apps.tempo.models import ConfiguracaoDoTempo, TempoDoDia

ZERO = Decimal("0")
# Quantos dias para frente o indicador mostra. Sete alcança sempre o próximo fim de
# semana, qualquer que seja o dia de hoje.
DIAS_A_FRENTE = 7
DIAS_DA_SEMANA = servico_de_analise.DIAS_DA_SEMANA


@dataclass
class DiaPrevisto:
    data: date
    tempo: object
    fim_de_semana: bool

    @property
    def dia_da_semana(self):
        return DIAS_DA_SEMANA[(self.data.weekday() + 1) % 7]

    @property
    def choveu(self):
        return bool(self.tempo and self.tempo.choveu)

    @property
    def resumo(self):
        return self.tempo.resumo if self.tempo else "sem registro"


@dataclass
class Indicador:
    configurada: bool = False       # dá para buscar: há cidade ou coordenadas
    ligada: bool = False            # e a busca automática está ligada
    o_que_falta: list = field(default_factory=list)
    ultimo_erro: str = ""
    ultima_busca: object = None
    cidade: str = ""
    lugar_encontrado: str = ""
    proximos: list = field(default_factory=list)
    fim_de_semana: list = field(default_factory=list)
    grupo: object = None            # o fim de semana da análise, com chuva e sem chuva
    dias_registrados: int = 0
    dias_sem_registro: int = 0
    falta_quanto: int = 0

    @property
    def tem_previsao(self):
        return bool(self.proximos)

    @property
    def chuva_no_fim_de_semana(self):
        return any(dia.choveu for dia in self.fim_de_semana)

    @property
    def dias_de_chuva_no_fim_de_semana(self):
        return [dia for dia in self.fim_de_semana if dia.choveu]

    @property
    def da_para_concluir(self):
        return self.grupo is not None and self.grupo.da_para_concluir

    @property
    def custo_da_chuva(self):
        """Quanto a loja deixa de vender, em média, num fim de semana de chuva."""
        if self.grupo is None:
            return None
        return self.grupo.diferenca

    @property
    def chuva_custa(self):
        """A chuva tira dinheiro do caixa, que é o caso esperado e quase sempre o real."""
        custo = self.custo_da_chuva
        return custo is not None and custo < ZERO

    @property
    def quanto_a_chuva_mexe(self):
        """O tamanho da diferença, sem sinal: o sinal vira palavra na frase da tela.

        "vende, em média, -R$ 312,32 em relação a um sem chuva" é um número certo numa
        frase que ninguém fala. O que se fala é "vende R$ 312,32 a menos".
        """
        custo = self.custo_da_chuva
        return None if custo is None else abs(custo)

    @property
    def variacao(self):
        return None if self.grupo is None else self.grupo.variacao

    @property
    def nivel(self):
        """A cor do quadro: o que importa é a chuva no fim de semana, não a de terça."""
        if not self.configurada or self.ultimo_erro:
            return "atencao"
        if self.chuva_no_fim_de_semana:
            return "ruim"
        if self.tem_previsao:
            return "bom"
        return "neutro"

    @property
    def tem_algo_a_dizer(self):
        return self.tem_previsao or self.dias_registrados > 0 or not self.configurada


def _e_fim_de_semana(dia, registro):
    # Sábado e domingo valem como fim de semana; o feriado entra junto porque é quando a
    # loja tem público. É a mesma regra da análise, de propósito.
    return (dia.weekday() + 1) % 7 in (0, 6) or bool(registro and registro.feriado)


def _primeiro_bloco(dias):
    """Só o próximo fim de semana, e não o seguinte também.

    Numa janela de sete dias que começa num domingo cabem dois fins de semana: este
    domingo e o sábado que vem. Somar os dois diria "chuva no fim de semana" por causa de
    um sábado a seis dias de distância, e a loja não se prepara para isso hoje.
    """
    bloco = []
    for dia in dias:
        if bloco and (dia.data - bloco[-1].data) > timedelta(days=1):
            break
        bloco.append(dia)
    return bloco


def montar(importacao, hoje=None) -> Indicador:
    """O que vem por aí e o que a chuva custa, para o quadro da Visão geral."""
    hoje = hoje or date.today()
    configuracao = ConfiguracaoDoTempo.atual()
    indicador = Indicador(
        configurada=configuracao.da_para_buscar,
        ligada=configuracao.pronta,
        o_que_falta=configuracao.o_que_falta,
        ultimo_erro=configuracao.ultimo_erro,
        ultima_busca=configuracao.ultima_busca,
        cidade=configuracao.cidade,
        lugar_encontrado=configuracao.lugar_encontrado,
    )

    previstos = TempoDoDia.objects.filter(
        previsao=True, data__gte=hoje, data__lte=hoje + timedelta(days=DIAS_A_FRENTE - 1)
    ).order_by("data")
    indicador.proximos = [
        DiaPrevisto(data=registro.data, tempo=registro,
                    fim_de_semana=_e_fim_de_semana(registro.data, registro))
        for registro in previstos
    ]
    indicador.fim_de_semana = _primeiro_bloco(
        [dia for dia in indicador.proximos if dia.fim_de_semana])

    analise = servico_de_analise.montar(importacao)
    indicador.dias_registrados = analise.dias_com_tempo
    indicador.dias_sem_registro = analise.dias_sem_tempo
    indicador.falta_quanto = analise.falta_quanto
    # O fim de semana é o grupo que decide: é lá que está o faturamento da loja.
    if analise.fim_de_semana.dias:
        indicador.grupo = analise.fim_de_semana
    return indicador
