from django.urls import path

from . import views

app_name = "painel"
urlpatterns = [
    path("", views.painel, name="painel"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("geral/", views.geral, name="geral"),
    path("completo/", views.completo, name="completo"),
    path("ticket-medio/", views.ticket_medio, name="ticket_medio"),
    path("vendas-do-dia/", views.vendas_dia, name="vendas_dia"),
    path("vendas-do-dia/arquivo/", views.vendas_dia_arquivo, name="vendas_dia_arquivo"),
]
