from django.urls import path

from . import views

app_name = "pedidos"
urlpatterns = [
    path("", views.lista, name="lista"),
    path("gerar/", views.gerar, name="gerar"),
    path("<int:numero>/", views.detalhe, name="detalhe"),
    path("<int:numero>/anexar/", views.anexar, name="anexar"),
    path("<int:numero>/receber/", views.receber, name="receber"),
    path("<int:numero>/editar/", views.editar, name="editar"),
    path("<int:numero>/cancelar/", views.cancelar, name="cancelar"),
    path("<int:numero>/imprimir/", views.imprimir, name="imprimir"),
    path("<int:numero>/anexo/<int:anexo_id>/", views.baixar, name="baixar"),
]
