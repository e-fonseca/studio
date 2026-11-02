"""Aviso de atualização dos dados no topo de todas as páginas."""

from django.db import DatabaseError

from . import servicos


def estado_dados(request):
    usuario = getattr(request, "user", None)
    if not usuario or not usuario.is_authenticated:
        return {}
    # Quem vê a lista de compra também precisa saber de quando são os números (1.44.0: o
    # perfil Compras vê a lista sem ver os painéis). O link para o painel, na faixa, só
    # aparece para quem abre o painel.
    if not (usuario.has_perm("importacao.ver_painel") or usuario.has_perm("compras.ver_compras")):
        return {}
    try:
        return {"estado_dados": servicos.estado_dos_dados()}
    except DatabaseError:
        # Banco ainda sem as tabelas (antes de migrar): a página abre sem o aviso.
        return {}
