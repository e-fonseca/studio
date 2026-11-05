"""Rotas. Tudo vive sob /studio (briefing, seção 4)."""

from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

admin.site.site_header = "Administração do sistema auxiliar"
admin.site.site_title = "Studio Industrial"

rotas_sistema = [
    path("", include("apps.core.urls")),
    path("", include("apps.contas.urls")),
    path("painel/", include("apps.painel.urls")),
    path("projetos/", include("apps.projetos.urls")),
    path("leads/", include("apps.leads.urls")),
    path("integracao/", include("apps.integracao.urls")),
    path("compras/", include("apps.compras.urls")),
    path("pedidos/", include("apps.pedidos.urls")),
    path("backup/", include("apps.backup.urls")),
    path("fornecedores/", include("apps.fornecedores.urls")),
    path("financeiro/", include("apps.financeiro.urls")),
    path("conciliacao/", include("apps.conciliacao.urls")),
    path("caixa/", include("apps.caixa.urls")),
    path("margem/", include("apps.margem.urls")),
    path("clientes/", include("apps.clientes.urls")),
    path("importacao/", include("apps.importacao.urls")),
    path("inventario/", include("apps.inventario.urls")),
    path("processos/", include("apps.processos.urls")),
    path("alertas/", include("apps.alertas.urls")),
    path("tempo/", include("apps.tempo.urls")),
    path("auditoria/", include("apps.auditoria.urls")),
    path("admin/", admin.site.urls),
]

# Sem permissão: a tela diz só isso, e a tentativa vai para a auditoria (1.44.0).
handler403 = "apps.core.views.negado"

urlpatterns = [
    path("studio/", include(rotas_sistema)),
    path("", RedirectView.as_view(url="/studio/", permanent=False)),
]
