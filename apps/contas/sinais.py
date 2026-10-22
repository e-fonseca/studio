from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from apps.auditoria.servicos import registrar

from . import sessao

User = get_user_model()


@receiver(m2m_changed, sender=User.groups.through)
def perfis_alterados(sender, instance, action, pk_set, **kwargs):
    if action not in ("post_add", "post_remove", "post_clear") or not isinstance(instance, User):
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


@receiver(user_logged_in)
def marcar_hora_da_entrada(sender, request, user, **kwargs):
    """Guarda quando a pessoa entrou, para o limite de horas logado saber contar."""
    if request is not None and hasattr(request, "session"):
        sessao.marcar_entrada(request.session)
