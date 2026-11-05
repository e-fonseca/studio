from django.urls import path

from . import views

app_name = "projetos"
urlpatterns = [
    path("", views.lista, name="lista"),
    path("novo/", views.novo, name="novo"),
    path("<int:pk>/", views.ficha, name="ficha"),
    path("<int:pk>/mudar/", views.editar, name="editar"),
    path("<int:pk>/etapa/", views.mudar_etapa, name="mudar_etapa"),
    path("<int:pk>/parcela/", views.nova_parcela, name="nova_parcela"),
    path("parcela/<int:pk>/baixar/", views.baixar_parcela, name="baixar_parcela"),
    path("oficinas/", views.oficinas, name="oficinas"),
    path("oficinas/nova/", views.oficina_form, name="oficina_nova"),
    path("oficinas/<int:pk>/", views.oficina, name="oficina"),
    path("oficinas/<int:pk>/mudar/", views.oficina_form, name="oficina_editar"),
]
