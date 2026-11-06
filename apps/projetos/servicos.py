"""As contas da tela de pedidos: o que está andando, o que atrasou e o dinheiro de todos.

O dinheiro sai das regras do planejamento (apps/planejamento/regras.py): o que falta
receber em Pix e o que falta pagar às oficinas, pela regra de cada pedido.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from .models import Projeto

ZERO = Decimal("0")

# Os filtros da lista, na ordem em que aparecem. O primeiro é o padrão: quem abre a tela
# quer saber o que está na oficina agora, não o que foi entregue em março.
FILTROS = (
    ("andamento", "Em aberto", "Vendidos e ainda não entregues: em projeto, na oficina, prontos ou em manutenção."),
    ("alerta", "Com alerta", "Margem baixa, atraso, saldo depois da entrega ou oficina a pagar."),
    ("incompletos", "Cards incompletos", "Falta venda, custo, oficina, prazo, 1ª parcela ou a forma do saldo."),
    ("atrasados", "Atrasados", "Passaram do prazo combinado com o cliente e não foram entregues."),
    ("orcamento", "Orçamentos", "Ainda não aprovados pelo cliente."),
    ("entregue", "Entregues", "Já estão com o cliente."),
    ("cancelado", "Cancelados", "Não seguiram."),
    ("todos", "Todos", "Todos os pedidos, em qualquer etapa."),
)
FILTRO_PADRAO = "andamento"


def filtrar(filtro, hoje=None, busca=""):
    """A consulta do filtro. "alerta" e "incompletos" são decididos depois, em Python,
    porque dependem das regras (ver `separar`)."""
    hoje = hoje or timezone.localdate()
    consulta = Projeto.objects.select_related("oficina", "responsavel", "pg1_cartao")
    if filtro == "andamento":
        consulta = consulta.filter(etapa__in=Projeto.EM_ANDAMENTO)
    elif filtro == "atrasados":
        consulta = consulta.filter(etapa__in=Projeto.EM_ANDAMENTO, prazo_entrega__lt=hoje)
    elif filtro in ("orcamento", "entregue", "cancelado"):
        consulta = consulta.filter(etapa=filtro)
    elif filtro in ("alerta", "incompletos"):
        consulta = consulta.filter(etapa__in=Projeto.VENDIDOS)
    if busca:
        consulta = consulta.filter(
            Q(titulo__icontains=busca) | Q(cliente_nome__icontains=busca)
            | Q(numero__icontains=busca) | Q(oficina__nome__icontains=busca)
            | Q(descricao__icontains=busca) | Q(arquiteto__icontains=busca))
    if filtro in ("andamento", "atrasados", "alerta", "incompletos"):
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
    a_pagar_sem_data: Decimal = ZERO
    em_producao_valor: Decimal = ZERO
    filtros: list = field(default_factory=list)


def resumir(contexto, vendidos, alertados, incompletos):
    """Os números do topo, pelas regras: o que ainda entra em Pix e o que ainda sai."""
    from apps.planejamento import regras

    hoje = contexto.hoje
    agenda = regras.todas_as_saidas(vendidos, contexto)
    resumo = Resumo(
        a_pagar=sum((s.valor for s in agenda.saidas if s.data >= hoje), ZERO),
        a_pagar_sem_data=sum((s.valor for s in agenda.sem_data), ZERO),
        em_producao_valor=Projeto.objects.filter(etapa__in=Projeto.EM_ANDAMENTO).aggregate(
            v=Sum("valor_venda"))["v"] or ZERO,
    )
    for projeto in vendidos:
        c = regras.saldo_cliente(projeto, contexto)
        if c and c.saldo > 0:
            resumo.a_receber += c.saldo
            if c.vencido:
                resumo.a_receber_vencido += c.saldo
    numeros = contagens(hoje)
    numeros["alerta"] = len(alertados)
    numeros["incompletos"] = len(incompletos)
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
