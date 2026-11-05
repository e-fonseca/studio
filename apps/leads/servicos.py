"""As contas do funil: o que fazer hoje, o que está esquecido e quanto vira venda."""

from dataclasses import dataclass, field
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from apps.projetos.models import Projeto

from .models import Contato, Lead

DIAS_DA_CONVERSAO = 90


@dataclass
class Funil:
    para_hoje: list = field(default_factory=list)
    sem_data: list = field(default_factory=list)
    colunas: list = field(default_factory=list)
    abertos: int = 0
    novos_7_dias: int = 0
    ganhos: int = 0
    perdidos: int = 0

    @property
    def conversao(self):
        """Ganhos sobre os fechados nos últimos 90 dias, em %. Sem fechado, sem número."""
        fechados = self.ganhos + self.perdidos
        return round(100 * self.ganhos / fechados) if fechados else None


def montar(usuario=None, hoje=None):
    """O funil inteiro, ou só o de quem cuida (`usuario`)."""
    hoje = hoje or timezone.localdate()
    base = Lead.objects.select_related("responsavel")
    if usuario is not None:
        base = base.filter(responsavel=usuario)
    abertos = base.filter(etapa__in=Lead.ABERTAS)

    funil = Funil()
    funil.abertos = abertos.count()
    funil.para_hoje = list(abertos.filter(proximo_contato__lte=hoje).order_by("proximo_contato", "id"))
    funil.sem_data = list(abertos.filter(proximo_contato__isnull=True).order_by("criado_em"))
    for etapa in Lead.ABERTAS:
        rotulo = Lead.Etapa(etapa).label
        cartoes = [lead for lead in abertos if lead.etapa == etapa]
        funil.colunas.append({"etapa": etapa, "rotulo": rotulo, "cartoes": cartoes})

    desde = timezone.now() - timedelta(days=DIAS_DA_CONVERSAO)
    fechados = base.filter(fechado_em__gte=desde).aggregate(
        g=Count("id", filter=Q(etapa=Lead.Etapa.GANHO)),
        p=Count("id", filter=Q(etapa=Lead.Etapa.PERDIDO)))
    funil.ganhos, funil.perdidos = fechados["g"], fechados["p"]
    funil.novos_7_dias = base.filter(criado_em__gte=timezone.now() - timedelta(days=7)).count()
    return funil


def mudar_etapa(lead, etapa, motivo_perda=""):
    """Troca a etapa e carimba quando o lead fechou, ganho ou perdido."""
    lead.etapa = etapa
    if etapa in Lead.FECHADAS:
        lead.fechado_em = lead.fechado_em or timezone.now()
        lead.proximo_contato = None
    else:
        lead.fechado_em = None
    lead.motivo_perda = motivo_perda.strip() if etapa == Lead.Etapa.PERDIDO else ""
    return lead


def registrar_contato(lead, dados, autor):
    contato = Contato.objects.create(
        lead=lead, canal=dados["canal"], resumo=dados["resumo"].strip(), autor=autor)
    mudar_etapa(lead, dados["etapa"], dados.get("motivo_perda") or "")
    if lead.aberto:
        lead.proximo_contato = dados.get("proximo_contato")
    lead.save()
    return contato


def converter_em_projeto(lead, usuario):
    """O lead fechou: nasce o projeto com os dados do cliente, e o lead fica ganho."""
    projeto = Projeto.objects.create(
        titulo=(lead.interesse.strip().splitlines() or ["Projeto de " + lead.nome])[0][:160],
        cliente_nome=lead.nome, cliente_telefone=lead.telefone, cliente_email=lead.email,
        descricao=lead.interesse, valor_venda=lead.valor_estimado or 0,
        responsavel=lead.responsavel or usuario, criado_por=usuario,
    )
    mudar_etapa(lead, Lead.Etapa.GANHO)
    lead.projeto = projeto
    lead.save()
    return projeto
