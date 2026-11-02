from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from apps.auditoria.servicos import registrar

from . import sessao
from .servicos import mudando_pela_tela

User = get_user_model()


@receiver(m2m_changed, sender=User.groups.through)
def perfis_alterados(sender, instance, action, pk_set, **kwargs):
    if action not in ("post_add", "post_remove", "post_clear") or not isinstance(instance, User):
        return
    if mudando_pela_tela.get():
        return
    registrar(
        "permissao.perfis_alterados",
        servico="sistema",
        recurso=instance,
        recurso_rotulo=instance.get_username(),
        depois={"operacao": action, "perfis_ids": sorted(pk_set or []),
                "perfis_atuais": sorted(instance.groups.values_list("name", flat=True))},
    )


@receiver(m2m_changed, sender=User.user_permissions.through)
def permissoes_alteradas(sender, instance, action, pk_set, **kwargs):
    if action not in ("post_add", "post_remove", "post_clear") or not isinstance(instance, User):
        return
    registrar(
        "permissao.permissoes_individuais_alteradas",
        servico="sistema",
        recurso=instance,
        recurso_rotulo=instance.get_username(),
        depois={"operacao": action, "permissoes_ids": sorted(pk_set or [])},
    )


@receiver(m2m_changed, sender=Group.permissions.through)
def permissoes_do_perfil_alteradas(sender, instance, action, pk_set, **kwargs):
    """Mudança no que um perfil pode, feita por fora da tela (o admin do Django, um script).

    Pela tela, `servicos.editar_perfil` registra o evento completo, com o motivo, e este
    fica quieto (`mudando_pela_tela`). Até a 1.43.0 esta mudança não deixava rastro.
    """
    if action not in ("post_add", "post_remove", "post_clear") or not isinstance(instance, Group):
        return
    if mudando_pela_tela.get():
        return
    registrar(
        "permissao.perfil_alterado_por_fora",
        servico="sistema",
        recurso=instance,
        recurso_rotulo=instance.name,
        depois={"operacao": action, "permissoes_ids": sorted(pk_set or []),
                "pessoas_no_perfil": instance.user_set.count()},
    )


@receiver(user_logged_in)
def marcar_hora_da_entrada(sender, request, user, **kwargs):
    """Guarda quando a pessoa entrou, para o limite de horas logado saber contar, e de onde
    e com que aparelho, para a ficha dela listar as sessões abertas."""
    if request is not None and hasattr(request, "session"):
        sessao.marcar_entrada(request.session)
        sessao.marcar_aparelho(request.session, request)
