from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.shortcuts import render

from . import contexto
from .models import EventoAuditoria


@login_required
@permission_required("auditoria.ver_auditoria", raise_exception=True)
def lista(request):
    eventos = EventoAuditoria.objects.all()
    acao = request.GET.get("acao", "").strip()
    usuario = request.GET.get("usuario", "").strip()
    if acao:
        eventos = eventos.filter(acao__startswith=acao)
    if usuario:
        eventos = eventos.filter(usuario_rotulo__icontains=usuario)
    pagina = Paginator(eventos, 50).get_page(request.GET.get("pagina"))
    return render(
        request,
        "auditoria/lista.html",
        {"pagina": pagina, "acao": acao, "usuario": usuario, "titulo": "Trilha de auditoria",
         "ip_de_agora": contexto.ip_atual()},
    )
