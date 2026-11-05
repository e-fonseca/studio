"""O que vira evento para o agente levar ao Trello.

Fica no sinal do modelo, e não em cada tela, para valer também para o projeto que nasce de
um lead e para o que for mudado pelo admin: o cartão do Trello não pode ficar para trás
porque a mudança veio por outro caminho.
"""

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.leads.models import Lead
from apps.projetos.models import Projeto

from .models import Evento


def dados_do_projeto(projeto):
    return {
        "codigo": projeto.codigo,
        "titulo": projeto.titulo,
        "cliente": projeto.cliente_nome,
        "etapa": projeto.etapa,
        "etapa_rotulo": projeto.get_etapa_display(),
        "oficina": projeto.oficina.nome if projeto.oficina_id else "",
        "prazo_entrega": projeto.prazo_entrega.isoformat() if projeto.prazo_entrega else None,
        "responsavel": (projeto.responsavel.get_full_name() or projeto.responsavel.get_username())
                       if projeto.responsavel_id else "",
        "trello_cartao": projeto.trello_cartao,
    }


def dados_do_lead(lead):
    return {"nome": lead.nome, "etapa": lead.etapa, "etapa_rotulo": lead.get_etapa_display(),
            "origem": lead.origem, "kommo_id": lead.kommo_id,
            "proximo_contato": lead.proximo_contato.isoformat() if lead.proximo_contato else None}


# Campos do projeto que aparecem no cartão: mudar outra coisa (o valor, por exemplo) não
# mexe no Trello, e não gera evento.
CAMPOS_DO_CARTAO = ("titulo", "cliente_nome", "oficina_id", "prazo_entrega", "responsavel_id")


@receiver(pre_save, sender=Projeto)
def _guardar_o_antes(sender, instance, **kwargs):
    instance._antes = (Projeto.objects.filter(pk=instance.pk).values(
        "etapa", *CAMPOS_DO_CARTAO).first() if instance.pk else None)


@receiver(post_save, sender=Projeto)
def _evento_do_projeto(sender, instance, created, update_fields=None, **kwargs):
    if update_fields and set(update_fields) <= {"trello_cartao"}:
        return  # é o próprio agente devolvendo o número do cartão
    antes = getattr(instance, "_antes", None)
    if created or antes is None:
        tipo = Evento.Tipo.PROJETO_CRIADO
    elif antes["etapa"] != instance.etapa:
        tipo = Evento.Tipo.PROJETO_ETAPA
    elif any(antes[campo] != getattr(instance, campo) for campo in CAMPOS_DO_CARTAO):
        tipo = Evento.Tipo.PROJETO_ALTERADO
    else:
        return
    Evento.objects.create(tipo=tipo, recurso_tipo="projeto", recurso_id=str(instance.pk),
                          dados=dados_do_projeto(instance))


@receiver(pre_save, sender=Lead)
def _guardar_a_etapa(sender, instance, **kwargs):
    instance._etapa_antes = (Lead.objects.filter(pk=instance.pk).values_list(
        "etapa", flat=True).first() if instance.pk else None)


@receiver(post_save, sender=Lead)
def _evento_do_lead(sender, instance, created, **kwargs):
    if getattr(instance, "_veio_do_kommo", False):
        return  # o agente trouxe do Kommo: devolver para lá seria um eco
    if created:
        tipo = Evento.Tipo.LEAD_CRIADO
    elif getattr(instance, "_etapa_antes", None) != instance.etapa:
        tipo = Evento.Tipo.LEAD_ETAPA
    else:
        return
    Evento.objects.create(tipo=tipo, recurso_tipo="lead", recurso_id=str(instance.pk),
                          dados=dados_do_lead(instance))
