from django.urls import path

from . import views

app_name = "conciliacao"
urlpatterns = [
    path("", views.lista, name="lista"),
    path("importar/", views.importar, name="importar"),
    path("<int:pk>/", views.extrato, name="extrato"),
    path("<int:pk>/conferir-as-obvias/", views.conferir_as_obvias, name="conferir_as_obvias"),
    path("<int:pk>/apagar/", views.apagar, name="apagar"),
    path("linha/<int:pk>/conferir/", views.conferir, name="conferir"),
    path("linha/<int:pk>/sem-conta/", views.sem_conta, name="sem_conta"),
    path("linha/<int:pk>/desfazer/", views.desfazer, name="desfazer"),
]
