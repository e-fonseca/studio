from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "contas"
urlpatterns = [
    path("entrar/", auth_views.LoginView.as_view(template_name="contas/entrar.html",
                                                 redirect_authenticated_user=True), name="entrar"),
    path("sair/", auth_views.LogoutView.as_view(), name="sair"),
    path("senha/", views.trocar_senha, name="trocar_senha"),
    # Esqueci a minha senha (1.43.0): sem login, porque quem usa ainda não entrou.
    path("senha/esqueci/", views.esqueci_a_senha, name="esqueci_a_senha"),
    path("senha/esqueci/codigo/", views.codigo_da_senha, name="codigo_da_senha"),
    path("usuarios/", views.lista, name="usuarios"),
    path("usuarios/criar/", views.criar, name="criar_usuario"),
    path("usuarios/<int:pk>/alterar/", views.alterar, name="alterar_usuario"),
    path("usuarios/prazo/", views.prazo_de_acesso, name="prazo_de_acesso"),
    path("usuarios/email/", views.email_de_recuperacao, name="email_de_recuperacao"),
]
