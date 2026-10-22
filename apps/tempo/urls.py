from django.urls import path

from . import views

app_name = "tempo"
urlpatterns = [
    path("", views.painel, name="painel"),
    path("anotar/", views.anotar, name="anotar"),
    path("configurar/", views.configurar, name="configurar"),
    path("buscar/", views.buscar_agora, name="buscar_agora"),
    path("arquivo/", views.em_arquivo, name="em_arquivo"),
]
