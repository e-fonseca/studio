from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from .models import EventoAuditoria
from .servicos import registrar


@receiver(user_logged_in)
def ao_entrar(sender, request, user, **kwargs):
    # A conta técnica do servidor é exceção (prompt de controle de acesso, 02/11/2026: "uso
    # excepcional e auditado"): a entrada dela diz que foi ela, para saltar aos olhos.
    registrar("acesso.entrada", usuario=user,
              depois={"superusuario": True} if getattr(user, "is_superuser", False) else None)


@receiver(user_logged_out)
def ao_sair(sender, request, user, **kwargs):
    if user is not None:
        registrar("acesso.saida", usuario=user)


@receiver(user_login_failed)
def ao_falhar(sender, credentials, request=None, **kwargs):
    # Registra só o nome de usuário tentado; a senha nunca chega aqui.
    registrar(
        "acesso.falha",
        servico="autenticacao",
        resultado=EventoAuditoria.Resultado.FALHA,
        depois={"usuario_tentado": str(credentials.get("username", ""))[:150]},
    )
