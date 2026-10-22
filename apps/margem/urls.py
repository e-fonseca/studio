from django.urls import path

from . import views

app_name = "margem"
urlpatterns = [
    path("", views.lista, name="lista"),
    path("arquivo/", views.em_arquivo, name="em_arquivo"),
]
