from django.urls import path

from . import views

app_name = "alertas"
urlpatterns = [
    path("", views.painel, name="painel"),
    path("testar/", views.testar, name="testar"),
    path("telegram/", views.configurar_telegram, name="configurar_telegram"),
    path("telegram/testar/", views.testar_telegram, name="testar_telegram"),
    path("telegram/descobrir/", views.descobrir_chat, name="descobrir_chat"),
    path("telegram/conversa/", views.usar_chat, name="usar_chat"),
    path("<str:rotina>/mandar/", views.mandar_agora, name="mandar_agora"),
    path("<str:rotina>/previa/", views.previa, name="previa"),
]
