from django.urls import path

from . import views, views_guiada

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
    # A compra guiada (1.45.0): perguntas, uma de cada vez, que montam o pedido de um
    # fornecedor. Cada pergunta é um endereço, e a resposta fica gravada a cada passo.
    path("guiada/", views_guiada.abertura, name="guiada"),
    path("guiada/comecar/", views_guiada.comecar, name="guiada_comecar"),
    path("guiada/<int:pk>/", views_guiada.continuar, name="guiada_continuar"),
    path("guiada/<int:pk>/folha/", views_guiada.folha, name="guiada_folha"),
    path("guiada/<int:pk>/pronto/", views_guiada.pronto, name="guiada_pronto"),
    path("guiada/<int:pk>/deixar/", views_guiada.deixar, name="guiada_deixar"),
    path("guiada/<int:pk>/<slug:passo>/", views_guiada.passo, name="guiada_passo"),
    path("", views.consulta_de_compras, name="consulta"),
    path("<int:id_set>/", views.compra, name="compra"),
]
