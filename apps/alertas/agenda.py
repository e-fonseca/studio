"""Quando cada relatório sai, e o que ainda está devendo.

A pergunta que este arquivo responde é a mais chata do recurso: **o relógio é do
Windows, e o horário é da tela**. Registrar as tarefas agendadas nos horários gravados
no banco funcionaria no dia da instalação e passaria a mentir na primeira vez que
alguém mudasse a hora na tela, sem nada avisando.

Então a tarefa do Windows não sabe a hora de nada: ela acorda de hora em hora e
pergunta aqui o que já passou da hora e ainda não saiu. Quem decide continua sendo a
tela, e a tela continua sendo verdade. De graça vêm três coisas:

- servidor desligado às 7h entrega o relatório quando ligar, em vez de pular o dia;
- mudança de horário na tela vale no mesmo dia, sem reinstalar nada;
- falha do servidor de e-mail pode ser tentada de novo, mas poucas vezes (ver TENTATIVAS_POR_DIA):
  insistir de hora em hora é a melhor forma de a conta da loja ser bloqueada.
"""

from datetime import datetime, timedelta

from django.utils import timezone

from apps.alertas.models import DIARIAS, SEMANAIS, Canal, EnvioDeRelatorio

# Quantas vezes por dia o sistema tenta a mesma rotina quando o envio falha.
TENTATIVAS_POR_DIA = 3


def proximo_envio(configuracao, agora=None):
    """Quando sai o próximo e-mail, para a tela dizer em vez de a pessoa calcular."""
    agora = agora or timezone.localtime()
    hoje = agora.date()
    diario = datetime.combine(hoje, configuracao.hora_diaria)
    if diario.time() <= agora.time():
        diario = datetime.combine(hoje + timedelta(days=1), configuracao.hora_diaria)
    dias_para_o_semanal = (configuracao.dia_semanal - hoje.weekday()) % 7
    semanal = datetime.combine(hoje + timedelta(days=dias_para_o_semanal), configuracao.hora_semanal)
    if dias_para_o_semanal == 0 and semanal.time() <= agora.time():
        semanal = datetime.combine(hoje + timedelta(days=7), configuracao.hora_semanal)
    return {"diario": diario, "semanal": semanal}


def _do_dia(rotina, agora, canal=Canal.EMAIL):
    """Os registros de hoje daquela rotina naquele canal, do mais novo para o mais velho.

    Por canal, e não por rotina: desde a 1.24.0 o mesmo relatório sai por e-mail e por
    Telegram. Sem separar, um aviso de Telegram entregue faria o sistema achar que o
    e-mail do dia já saiu, e ele nunca sairia.
    """
    inicio = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    return list(EnvioDeRelatorio.objects.filter(rotina=rotina, canal=canal, quando__gte=inicio))


def pendencia(rotina, agora, canal=Canal.EMAIL):
    """Esta rotina está devendo envio agora, neste canal? Devolve o motivo de sim ou não."""
    registros = _do_dia(rotina, agora, canal)
    if any(r.deu_certo or r.sem_noticia for r in registros):
        return None  # já resolvida hoje: entregue, ou sem notícia para mandar
    if len(registros) >= TENTATIVAS_POR_DIA:
        return None  # falhou demais hoje; o erro está na tela, insistir piora
    return "primeira" if not registros else f"tentativa {len(registros) + 1}"


def na_hora(configuracao, agora=None):
    """As rotinas cuja hora já passou hoje, sem olhar o que já saiu.

    O horário é um só para os dois canais: é a hora em que a loja quer saber, não a hora
    de um meio de entrega.
    """
    agora = agora or timezone.localtime()
    pendentes = []
    if agora.time() >= configuracao.hora_diaria:
        pendentes += [r.value for r in DIARIAS]
    if agora.weekday() == configuracao.dia_semanal and agora.time() >= configuracao.hora_semanal:
        pendentes += [r.value for r in SEMANAIS]
    return pendentes


def devidas(configuracao, agora=None, canal=Canal.EMAIL):
    """As rotinas que já passaram da hora de hoje e ainda não saíram neste canal.

    É o que a tarefa de hora em hora pergunta. A semanal só é devida no dia da semana
    escolhido na tela: num dia qualquer ela simplesmente não está na lista.
    """
    agora = agora or timezone.localtime()
    return [rotina for rotina in na_hora(configuracao, agora)
            if pendencia(rotina, agora, canal)]
