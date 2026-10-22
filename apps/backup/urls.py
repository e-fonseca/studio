from django.urls import path

from . import views

app_name = "backup"
urlpatterns = [
    path("", views.painel, name="painel"),
    path("enviar/", views.enviar_agora, name="enviar_agora"),
]
