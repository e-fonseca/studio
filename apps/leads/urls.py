from django.urls import path

from . import views

app_name = "leads"
urlpatterns = [
    path("", views.funil, name="funil"),
    path("fechados/", views.fechados, name="fechados"),
    path("novo/", views.novo, name="novo"),
    path("<int:pk>/", views.ficha, name="ficha"),
    path("<int:pk>/mudar/", views.editar, name="editar"),
    path("<int:pk>/contato/", views.contato, name="contato"),
    path("<int:pk>/projeto/", views.converter, name="converter"),
]
