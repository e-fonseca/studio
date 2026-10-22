from django.urls import path

from . import views

app_name = "fornecedores"
urlpatterns = [
    path("", views.lista, name="lista"),
    path("sugestoes/", views.sugestoes, name="sugestoes"),
    path("salvar/", views.salvar, name="salvar"),
    path("avaliar/", views.avaliar, name="avaliar"),
    path("ficha/", views.ficha, name="ficha"),
    path("produtos/", views.produtos, name="produtos"),
    path("produtos/arquivo/", views.produtos_em_arquivo, name="produtos_em_arquivo"),
    path("documento/", views.documento, name="documento"),
]
