"""Aviso de atualização dos dados no topo de todas as páginas."""

from django.db import DatabaseError

from . import servicos


def estado_dados(request):
    usuario = getattr(request, "user", None)
    if not usuario or not usuario.is_authenticated or not usuario.has_perm("importacao.ver_painel"):
        return {}
    try:
        return {"estado_dados": servicos.estado_dos_dados()}
    except DatabaseError:
        # Banco ainda sem as tabelas (antes de migrar): a página abre sem o aviso.
        return {}
