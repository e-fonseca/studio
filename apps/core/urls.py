from django.urls import path

from . import aplicativo, views

app_name = "core"
urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("versoes/", views.versoes, name="versoes"),
    path("cotacoes/", views.cotacoes, name="cotacoes"),
    path("saude/", views.saude, name="saude"),
    path("certificado/", views.certificado, name="certificado"),
    path("certificado/autoridade.crt", views.certificado_autoridade, name="certificado_autoridade"),
    # O atalho na tela inicial do celular. Os dois abrem sem login: o navegador
    # busca o manifesto sem mandar o cookie da sessão, e os dois só dizem nome,
    # ícone e cor, nada da loja. O operário tem que responder em /studio/ para
    # poder cuidar das telas do sistema.
    path("manifesto.webmanifest", aplicativo.manifesto, name="manifesto"),
    path("operario.js", aplicativo.operario, name="operario"),
]
