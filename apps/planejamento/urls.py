from django.urls import path

from . import views

app_name = "planejamento"
urlpatterns = [
    path("", views.visao, name="visao"),
    path("a-pagar/", views.pagar, name="pagar"),
    path("a-receber/", views.receber, name="receber"),
    path("fechamento/", views.fechamento, name="fechamento"),
    path("entre-empresas/", views.entre_empresas, name="entre_empresas"),
    path("entre-empresas/<int:pk>/cancelar/", views.cancelar_movimento, name="cancelar_movimento"),
    path("ajustes/", views.ajustes, name="ajustes"),
]
