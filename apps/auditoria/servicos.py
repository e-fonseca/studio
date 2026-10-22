from . import contexto
from .models import EventoAuditoria

# Chaves que nunca vão para a trilha, mesmo que alguém passe por engano.
CAMPOS_PROIBIDOS = {"senha", "password", "token", "segredo", "cpf", "conta_bancaria"}


def _limpar(valores):
    if not valores:
        return valores
    return {k: ("[omitido]" if k.lower() in CAMPOS_PROIBIDOS else v) for k, v in valores.items()}


def registrar(
    acao,
    *,
    usuario=None,
    servico=None,
    recurso=None,
    recurso_rotulo="",
    resultado=EventoAuditoria.Resultado.SUCESSO,
    antes=None,
    depois=None,
    motivo="",
):
    """Grava um evento na trilha de auditoria e o devolve."""
    if usuario is not None and not getattr(usuario, "is_authenticated", False):
        usuario = None
    rotulo = usuario.get_username() if usuario else (servico or "anônimo")
    recurso_tipo = recurso_id = ""
    if recurso is not None:
        recurso_tipo = recurso._meta.label_lower
        recurso_id = str(recurso.pk)
        recurso_rotulo = recurso_rotulo or str(recurso)[:200]
    return EventoAuditoria.objects.create(
        usuario=usuario,
        usuario_rotulo=rotulo,
        acao=acao,
        recurso_tipo=recurso_tipo,
        recurso_id=recurso_id,
        recurso_rotulo=recurso_rotulo,
        resultado=resultado,
        correlacao=contexto.correlacao_atual(),
        ip=contexto.ip_atual(),
        antes=_limpar(antes),
        depois=_limpar(depois),
        motivo=motivo,
    )
