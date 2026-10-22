from django.urls import path

from . import views

app_name = "caixa"
urlpatterns = [
    path("", views.lista, name="lista"),
    path("<int:pk>/", views.turno, name="turno"),
]
