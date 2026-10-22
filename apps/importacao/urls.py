from django.urls import path

from . import views

app_name = "importacao"
urlpatterns = [
    path("", views.historico, name="historico"),
    path("consulta/", views.consulta, name="consulta"),
    path("consulta/sugestoes/", views.sugestoes, name="sugestoes"),
    path("importar/", views.importar, name="importar"),
    path("<int:pk>/log/", views.log, name="log"),
]
