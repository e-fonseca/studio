from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "contas"
urlpatterns = [
    path("entrar/", auth_views.LoginView.as_view(template_name="contas/entrar.html",
                                                 redirect_authenticated_user=True), name="entrar"),
    path("sair/", auth_views.LogoutView.as_view(), name="sair"),
    path("usuarios/", views.lista, name="usuarios"),
    path("usuarios/criar/", views.criar, name="criar_usuario"),
    path("usuarios/<int:pk>/alterar/", views.alterar, name="alterar_usuario"),
]
