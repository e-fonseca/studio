"""As contas da tela de projetos: o que está andando, o que atrasou e o dinheiro de todos."""

from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from .models import Parcela, Projeto

ZERO = Decimal("0")

# Os filtros da lista, na ordem em que aparecem. O primeiro é o padrão: quem abre a tela
# quer saber o que está na oficina agora, não o que foi entregue em março.
FILTROS = (
    ("andamento", "Em andamento", "Aprovados, na oficina ou prontos para entregar."),
    ("atrasados", "Atrasados", "Passaram do prazo combinado com o cliente e não foram entregues."),
    ("orcamento", "Orçamentos", "Ainda não aprovados pelo cliente."),
    ("entregue", "Entregues", "Já estão com o cliente."),
    ("cancelado", "Cancelados", "Não seguiram."),
    ("todos", "Todos", "Todos os projetos, em qualquer etapa."),
)
FILTRO_PADRAO = "andamento"


def filtrar(filtro, hoje=None, busca=""):
    hoje = hoje or timezone.localdate()
    consulta = Projeto.objects.select_related("oficina", "responsavel")
    if filtro == "andamento":
        consulta = consulta.filter(etapa__in=Projeto.EM_ANDAMENTO)
    elif filtro == "atrasados":
        consulta = consulta.filter(etapa__in=Projeto.EM_ANDAMENTO, prazo_entrega__lt=hoje)
    elif filtro in ("orcamento", "entregue", "cancelado"):
        consulta = consulta.filter(etapa=filtro)
    if busca:
        consulta = consulta.filter(
            Q(titulo__icontains=busca) | Q(cliente_nome__icontains=busca)
            | Q(oficina__nome__icontains=busca) | Q(descricao__icontains=busca))
    if filtro in ("andamento", "atrasados"):
        return consulta.order_by("prazo_entrega", "id")
    return consulta


def contagens(hoje=None):
    hoje = hoje or timezone.localdate()
    por_etapa = dict(Projeto.objects.values_list("etapa").annotate(q=Count("id")))
    andamento = sum(por_etapa.get(e, 0) for e in Projeto.EM_ANDAMENTO)
    return {
        "andamento": andamento,
        "atrasados": Projeto.objects.filter(
            etapa__in=Projeto.EM_ANDAMENTO, prazo_entrega__lt=hoje).count(),
        "orcamento": por_etapa.get(Projeto.Etapa.ORCAMENTO, 0),
        "entregue": por_etapa.get(Projeto.Etapa.ENTREGUE, 0),
        "cancelado": por_etapa.get(Projeto.Etapa.CANCELADO, 0),
        "todos": sum(por_etapa.values()),
    }


@dataclass
class Resumo:
    a_receber: Decimal = ZERO
    a_receber_vencido: Decimal = ZERO
    a_pagar: Decimal = ZERO
    a_pagar_vencido: Decimal = ZERO
    em_producao_valor: Decimal = ZERO
    filtros: list = field(default_factory=list)


def _soma(consulta):
    return consulta.aggregate(v=Sum("valor"))["v"] or ZERO


def resumir(hoje=None):
    """Os números do topo: o que ainda entra e sai, de projetos que não foram cancelados."""
    hoje = hoje or timezone.localdate()
    abertas = Parcela.objects.filter(pago_em__isnull=True).exclude(
        projeto__etapa=Projeto.Etapa.CANCELADO)
    entradas = abertas.filter(tipo=Parcela.Tipo.RECEBER)
    saidas = abertas.filter(tipo__in=Parcela.SAIDAS)
    resumo = Resumo(
        a_receber=_soma(entradas),
        a_receber_vencido=_soma(entradas.filter(vencimento__lt=hoje)),
        a_pagar=_soma(saidas),
        a_pagar_vencido=_soma(saidas.filter(vencimento__lt=hoje)),
        em_producao_valor=Projeto.objects.filter(etapa__in=Projeto.EM_ANDAMENTO).aggregate(
            v=Sum("valor_venda"))["v"] or ZERO,
    )
    numeros = contagens(hoje)
    resumo.filtros = [
        {"chave": chave, "rotulo": rotulo, "ajuda": ajuda, "numero": numeros[chave]}
        for chave, rotulo, ajuda in FILTROS
    ]
    return resumo


def mudar_etapa(projeto, etapa, hoje=None):
    """Troca a etapa e carimba as datas que a etapa nova traz consigo.

    Aprovado sem data de aprovação ganha a de hoje; entregue ganha a data da entrega. Voltar
    para uma etapa anterior não apaga carimbo nenhum: a data em que o cliente aprovou não
    deixa de ter acontecido porque o projeto voltou para ajuste.
    """
    hoje = hoje or timezone.localdate()
    projeto.etapa = etapa
    if etapa in Projeto.EM_ANDAMENTO + (Projeto.Etapa.ENTREGUE,) and not projeto.aprovado_em:
        projeto.aprovado_em = hoje
    if etapa == Projeto.Etapa.ENTREGUE and not projeto.entregue_em:
        projeto.entregue_em = hoje
    projeto.save()
    return projeto
