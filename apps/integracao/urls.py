from django.urls import path

from . import views

app_name = "integracao"
urlpatterns = [
    path("eventos/", views.eventos, name="eventos"),
    path("eventos/<int:pk>/", views.entregar, name="entregar"),
    path("projetos/", views.projetos, name="projetos"),
    path("leads/", views.receber_lead, name="receber_lead"),
]
