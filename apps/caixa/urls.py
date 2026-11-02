from django.urls import path

from . import views

app_name = "caixa"
urlpatterns = [
    path("", views.lista, name="lista"),
    path("<int:pk>/", views.turno, name="turno"),
    path("descontos/", views.descontos_e_metas, name="descontos"),
    path("descontos/regras/", views.regras_de_desconto, name="regras_de_desconto"),
    path("descontos/aprovar/", views.aprovar_desconto, name="aprovar_desconto"),
    path("descontos/aprovacao/<int:pk>/desfazer/", views.desfazer_aprovacao, name="desfazer_aprovacao"),
]
