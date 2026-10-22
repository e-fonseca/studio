from django.urls import path

from . import views

app_name = "inventario"
urlpatterns = [
    path("", views.lista, name="lista"),
    path("abrir/", views.abrir, name="abrir"),
    # O plano de contagem cíclica: a folha com que se anda pela loja contando e a
    # contagem já nomeada pelo plano, para não ter o que digitar antes de começar.
    path("plano/", views.folha_de_contagem, name="folha_de_contagem"),
    path("plano/abrir/", views.abrir_sugerida, name="abrir_sugerida"),
    # Organizar a prateleira: sem etiqueta, danificados e parados.
    path("organizar/", views.organizar, name="organizar"),
    path("organizar/etiquetas/", views.etiquetas, name="etiquetas"),
    path("organizar/descarte/", views.descarte, name="descarte"),
    path("organizar/conserto/", views.conserto, name="conserto"),
    path("organizar/parados/", views.parados, name="parados"),
    path("organizar/<int:item_pk>/classificar/", views.classificar, name="classificar"),
    path("organizar/<int:item_pk>/resolver/", views.resolver, name="resolver"),
    path("<int:pk>/", views.contagem, name="contagem"),
    path("<int:pk>/contar/", views.contar, name="contar"),
    path("<int:pk>/divergencia/", views.divergencia, name="divergencia"),
    path("<int:pk>/camera/", views.camera, name="camera"),
    path("<int:pk>/camera/contar/", views.contar_pela_camera, name="contar_pela_camera"),
    path("<int:pk>/itens/<int:item_pk>/estado/", views.estado, name="estado"),
    path("<int:pk>/itens/<int:item_pk>/foto/", views.foto, name="foto"),
    path("<int:pk>/itens/<int:item_pk>/foto/guardar/", views.guardar_foto, name="guardar_foto"),
    path("<int:pk>/fechar/", views.fechar, name="fechar"),
    path("<int:pk>/ajustes/", views.ajustes, name="ajustes"),
    path("<int:pk>/itens/<int:item_pk>/remover/", views.remover, name="remover"),
]
