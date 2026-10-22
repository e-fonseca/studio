from django.urls import path

from . import views

app_name = "compras"
urlpatterns = [
    path("antes/", views.antes_de_comprar, name="antes_de_comprar"),
    path("sugestoes/", views.sugestoes, name="sugestoes"),
    path("lista/", views.lista, name="lista"),
    path("lista/arquivo/", views.lista_em_arquivo, name="lista_em_arquivo"),
    path("lista/quantidade/", views.ajustar_quantidade, name="ajustar_quantidade"),
    path("lista/regra/", views.politica, name="politica"),
    path("lista/pedido/", views.pedido_ao_fornecedor, name="pedido_ao_fornecedor"),
    path("empresa/", views.dados_da_empresa, name="dados_da_empresa"),
    path("comparar/", views.comparar_com_o_ano_passado, name="comparar"),
    path("comparar/arquivo/", views.comparacao_em_arquivo, name="comparar_em_arquivo"),
    path("equipe/", views.sugestoes_da_equipe, name="sugestoes_da_equipe"),
    path("equipe/registrar/", views.registrar_sugestao, name="registrar_sugestao"),
    path("equipe/<int:pk>/responder/", views.responder_sugestao, name="responder_sugestao"),
    path("", views.consulta_de_compras, name="consulta"),
    path("<int:id_set>/", views.compra, name="compra"),
]
