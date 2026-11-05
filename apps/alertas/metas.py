"""O aviso de meta batida no grupo das metas, pelo Telegram (1.47.0).

Pedido do Edson em 04/11/2026: *"enviar notificação de telegram meta batida feriado
12mil, sábado 12 mil reais e domingo 15 mil reais"*, no grupo METAS. A conta é a da tela
Descontos e metas (`caixa.descontos.do_dia`): a meta do dia, o vendido e o prêmio por
pessoa saem de lá, com as metas e o prêmio da tela Regras e metas. Nada aqui calcula meta
de novo, para o grupo e a tela nunca dizerem números diferentes.

Decisões que este arquivo carrega:

- **Sai quando o dado chega, não numa hora marcada.** O SET não avisa ninguém: o sistema
  só sabe que o sábado bateu a meta quando a importação traz as vendas do sábado. A tarefa
  de hora em hora (`enviar_relatorios`) pergunta aqui, e o aviso sai na primeira volta
  depois da importação que trouxe o dia. Com o backup do SET feito uma vez por noite, o
  sábado chega no domingo de manhã, e o aviso também. Por isso o aviso diz até que hora
  há venda na conta.
- **Uma vez por dia de meta, e de novo só se o prêmio subir.** Com o backup feito mais
  de uma vez por dia, a importação do meio-dia traz meia jornada: a meta bate de tarde e
  de noite o prêmio já subiu um degrau. O degrau novo é notícia; repetir o mesmo número a
  cada importação seria ruído, e o grupo deixaria de ler.
- **Só os últimos dias** (`DIAS_PARA_TRAS`). Meta da semana passada não é notícia, e
  ligar o aviso não pode despejar no grupo os fins de semana que a foto do SET guarda.
- **Sem nome de ninguém.** O aviso vai para um grupo. Quando a meta só bateu (ou o prêmio
  só subiu) por causa de venda com desconto fora da regra que ainda não tem aprovação
  anotada, o aviso diz isso numa linha, com quantas vendas e quanto, como o e-mail do dia;
  quem passou cada venda é assunto da tela Descontos e metas.
- **Falha não derruba a tarefa, e insiste pouco**: três tentativas por dia de meta em cada
  dia (`agenda.TENTATIVAS_POR_DIA`), como os relatórios.
"""

from dataclasses import dataclass
from datetime import timedelta

from django.db.models import Max
from django.utils import timezone

from apps.alertas import agenda, telegram
from apps.alertas.models import Canal, ConfiguracaoDeTelegram, EnvioDeRelatorio, Rotina
from apps.caixa import descontos
from apps.caixa import feriados as calendario
from apps.caixa.models import RegraDeDesconto
from apps.core.templatetags.cabana import reais
from apps.importacao import servicos as importacao_servicos
from apps.importacao.models import VendaImportada

# Um feriado na sexta emendado no fim de semana chega na segunda com três dias de meta
# para trás. Mais que isso já não é notícia: a tela Descontos e metas continua mostrando.
DIAS_PARA_TRAS = 3


@dataclass
class Aviso:
    """Um dia que bateu a meta e ainda não foi avisado com este prêmio."""

    meta: object          # caixa.descontos.DiaDeMeta
    ate: str = ""         # a hora da última venda do dia na foto, "17:56"
    subiu: bool = False   # já foi avisado antes, com prêmio menor

    @property
    def dia(self):
        return self.meta.dia

    @property
    def titulo(self):
        """A primeira linha, que é a que aparece na notificação do celular."""
        # "Sábado", "Domingo", "Finados" ou "Sábado, Finados", como a tela de descontos.
        quando = f"{self.meta.rotulo}, {self.dia:%d/%m/%Y}"
        return f"O prêmio subiu! {quando}" if self.subiu else f"Meta batida! {quando}"

    @property
    def resumo(self):
        meta = self.meta
        return (f"{meta.rotulo} {self.dia:%d/%m}: vendeu {reais(meta.vendido)} de "
                f"{reais(meta.meta)}, prêmio de {reais(meta.premio)} por pessoa")[:300]

    @property
    def texto(self):
        meta = self.meta
        linhas = [f"\N{PARTY POPPER} {self.titulo}", ""]
        linhas.append(f"Vendido: {reais(meta.vendido)}" + (f" (vendas até {self.ate})" if self.ate else ""))
        linhas.append(f"Meta do dia: {reais(meta.meta)}")
        linhas.append(f"Prêmio: {reais(meta.premio)} para cada pessoa que trabalhou no dia.")
        degrau = meta.proximo_degrau
        if degrau is not None:
            alvo, premio = degrau
            linhas.append(f"O próximo degrau é {reais(alvo)} vendidos: {reais(premio)} por pessoa.")
        if meta.dependeu_de_fora:
            frase = (f"Atenção: {meta.fora} venda(s) deste dia com desconto fora da regra ainda "
                     f"não têm aprovação anotada ({reais(meta.vendido_fora)}). Sem elas, o dia "
                     f"ficaria em {reais(meta.vendido_sem_fora)}")
            frase += (f" e o prêmio seria {reais(meta.premio_sem_fora)} por pessoa." if meta.premio_sem_fora
                      else " e a meta não teria sido batida.")
            linhas += ["", frase]
        return "\n".join(linhas)


def dias_de_meta(importacao, hoje):
    """Os sábados, domingos e feriados dos últimos dias que já estão na foto do SET."""
    if importacao is None or importacao.data_corte is None:
        return []
    inicio = hoje - timedelta(days=DIAS_PARA_TRAS)
    fim = min(importacao.data_corte, hoje)
    if fim < inicio:
        return []
    conhecidos = calendario.feriados_entre(inicio, fim, RegraDeDesconto.atual().outros_feriados)
    dias, dia = [], inicio
    while dia <= fim:
        if calendario.tipo_de_dia(dia, conhecidos)[0]:
            dias.append(dia)
        dia += timedelta(days=1)
    return dias


def _ja_avisados(dias):
    """Os registros de aviso de cada dia, para saber o que já saiu e o que falhou."""
    registros = {}
    for registro in EnvioDeRelatorio.objects.filter(rotina=Rotina.METAS, canal=Canal.TELEGRAM,
                                                     dia_da_meta__in=dias):
        registros.setdefault(registro.dia_da_meta, []).append(registro)
    return registros


def devidos(importacao=None, hoje=None):
    """Os avisos que faltam mandar agora, do dia mais antigo para o mais novo."""
    importacao = importacao or importacao_servicos.ultima_concluida()
    hoje = hoje or timezone.localdate()
    dias = dias_de_meta(importacao, hoje)
    if not dias:
        return []
    registros = _ja_avisados(dias)
    # As tentativas contam do começo do dia de hoje, como os relatórios (agenda._do_dia).
    comeco_de_hoje = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    avisos = []
    for dia in dias:
        _fora, meta, _regra = descontos.do_dia(importacao, dia)
        if meta is None or not meta.bateu:
            continue
        do_dia = registros.get(dia, [])
        avisados = [r.premio_avisado for r in do_dia if r.deu_certo and r.premio_avisado is not None]
        if avisados and meta.premio <= max(avisados):
            continue
        falhas_de_hoje = [r for r in do_dia if not r.deu_certo and r.quando >= comeco_de_hoje]
        if len(falhas_de_hoje) >= agenda.TENTATIVAS_POR_DIA:
            continue
        ultima = (VendaImportada.objects.filter(importacao=importacao, data=dia)
                  .aggregate(hora=Max("hora"))["hora"] or "")
        avisos.append(Aviso(meta=meta, ate=ultima[:5], subiu=bool(avisados)))
    return avisos


def avisar(configuracao=None, importacao=None, hoje=None, disparado_por="tarefa"):
    """Manda no grupo das metas cada aviso devido e devolve os registros, deu certo ou não.

    Desligado na tela, ou sem o robô e o grupo, não faz nada: quem chama é a tarefa de
    hora em hora, e ela só escreve no log o que faltou.
    """
    configuracao = configuracao or ConfiguracaoDeTelegram.atual()
    if not (configuracao.metas_ativo and configuracao.metas_pronta):
        return []
    registros = []
    for aviso in devidos(importacao, hoje):
        registro = EnvioDeRelatorio(
            rotina=Rotina.METAS, canal=Canal.TELEGRAM, assunto=aviso.titulo[:250],
            resumo=aviso.resumo, destinatarios=configuracao.metas_para_quem,
            disparado_por=disparado_por[:60], dia_da_meta=aviso.dia,
            premio_avisado=aviso.meta.premio,
        )
        try:
            telegram.mandar_texto(configuracao.token, configuracao.metas_chat_id, aviso.texto)
        except telegram.ErroDoTelegram as erro:
            registro.erro = telegram.explicar(erro)
        else:
            registro.deu_certo = True
        registro.save()
        registros.append(registro)
    return registros


def texto_de_teste(regra=None):
    """O teste do grupo já explica a regra, para quem lê no grupo saber o que vai chegar."""
    regra = regra or RegraDeDesconto.atual()
    return "\n".join([
        "Studio · Teste do aviso de metas",
        "",
        "Quando o sábado, o domingo ou um feriado bater a meta, o aviso chega aqui, com o "
        "vendido e o prêmio por pessoa.",
        "",
        f"Sábado e feriado: {reais(regra.meta_sabado)}",
        f"Domingo: {reais(regra.meta_domingo)}",
        f"Prêmio: {reais(regra.premio)} para cada pessoa que trabalhou no dia, e mais "
        f"{reais(regra.premio_a_mais)} a cada {reais(regra.passo)} acima da meta.",
    ])


def enviar_teste(configuracao=None, disparado_por=""):
    """Manda o teste no grupo das metas e devolve o registro."""
    configuracao = configuracao or ConfiguracaoDeTelegram.atual()
    registro = EnvioDeRelatorio(
        rotina=Rotina.TESTE, canal=Canal.TELEGRAM, assunto="Teste do aviso de metas",
        resumo="Teste do aviso de metas, com as metas e o prêmio da tela Regras e metas.",
        destinatarios=configuracao.metas_para_quem, disparado_por=disparado_por[:60],
    )
    faltas = configuracao.metas_o_que_falta
    if faltas:
        registro.erro = "Falta preencher na tela de alertas: " + ", ".join(faltas) + "."
        registro.save()
        return registro
    try:
        telegram.mandar_texto(configuracao.token, configuracao.metas_chat_id, texto_de_teste())
    except telegram.ErroDoTelegram as erro:
        registro.erro = telegram.explicar(erro)
    else:
        registro.deu_certo = True
    registro.save()
    return registro
