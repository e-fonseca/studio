from django.urls import path

from . import views

app_name = "financeiro"
urlpatterns = [
    path("", views.contas_a_pagar, name="contas_a_pagar"),
    path("pdf/", views.contas_a_pagar_em_pdf, name="contas_a_pagar_em_pdf"),
    path("planilha/", views.contas_a_pagar_em_planilha,
         name="contas_a_pagar_em_planilha"),
    path("sugestoes/", views.sugestoes_da_busca, name="sugestoes_da_busca"),
    path("despesas/", views.despesas, name="despesas"),
    path("fluxo/", views.fluxo_de_caixa, name="fluxo"),
    path("receber/", views.contas_a_receber, name="contas_a_receber"),
    path("pagamentos/", views.pagamentos, name="pagamentos"),
    path("pagamentos/salvar/", views.salvar_previsto, name="salvar_previsto"),
    path("pagamentos/<int:pk>/lancado/", views.marcar_lancado, name="marcar_lancado"),
]
