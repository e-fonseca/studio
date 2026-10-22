from django.urls import path

from . import views

app_name = "processos"
urlpatterns = [
    path("", views.quadro, name="quadro"),
    path("ficha-tecnica/", views.ficha_tecnica, name="ficha_tecnica"),
    path("novo/", views.novo, name="novo"),
    path("<int:pk>/", views.detalhe, name="detalhe"),
    path("<int:pk>/cadastro/", views.editar_cadastro, name="editar_cadastro"),
    path("<int:pk>/procedimento/", views.editar_procedimento, name="editar_procedimento"),
    path("<int:pk>/versoes/<int:numero>/", views.versao, name="versao"),
    path("<int:pk>/enviar-para-teste/", views.enviar_para_teste, name="enviar_para_teste"),
    path("<int:pk>/testes/", views.registrar_teste, name="registrar_teste"),
    path("<int:pk>/validar/", views.validar, name="validar"),
    path("<int:pk>/devolver/", views.devolver, name="devolver"),
    path("<int:pk>/afirmacoes/", views.nova_afirmacao, name="nova_afirmacao"),
    path("<int:pk>/anexos/", views.enviar_anexo, name="enviar_anexo"),
    path("<int:pk>/anexos/<int:anexo_id>/", views.baixar_anexo, name="baixar_anexo"),
]
