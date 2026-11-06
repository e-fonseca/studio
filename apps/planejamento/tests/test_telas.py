"""As telas do planejamento abrem, guardam e recusam como devem."""

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import EventoAuditoria
from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO, COMERCIAL
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.planejamento.models import Cartao, CustoFixo, MovimentoEntreEmpresas, Parametros
from apps.projetos.models import Oficina, Projeto

HOJE = timezone.localdate()
TELAS = ("planejamento:visao", "planejamento:pagar", "planejamento:receber", "planejamento:fechamento",
         "planejamento:entre_empresas", "planejamento:ajustes")


class TelasTest(TestCase):
    def setUp(self):
        usuario("edson", ADMINISTRACAO)
        self.client.login(username="edson", password=SENHA_TESTE)
        self.xp = Cartao.objects.create(nome="XP", vencimento=1, fecha_dias_antes=8)
        rogerio = Oficina.objects.create(nome="Rogério", pagamento="mensal", dia_pagamento=30, dia_corte=25)
        self.pedido = Projeto.objects.create(
            numero="28634", cliente_nome="André", etapa="producao", valor_venda=Decimal("43000"),
            custo_oficina=Decimal("9000"), oficina=rogerio, repasse=HOJE, recebido=Decimal("33000"),
            saldo_forma="pix", prazo_entrega=HOJE + timedelta(days=5), data_venda=HOJE)
        CustoFixo.objects.create(nome="Aluguel", valor=Decimal("4500"), dia=10)

    def test_todas_as_abas_abrem(self):
        for rota in TELAS:
            resposta = self.client.get(reverse(rota))
            self.assertEqual(resposta.status_code, 200, rota)
            self.assertContains(resposta, "Caixa em 30 dias")  # a fileira de abas

    def test_visao_mostra_grafico_e_saldo_a_conferir(self):
        pagina = self.client.get(reverse("planejamento:visao"))
        self.assertContains(pagina, "<svg")
        self.assertContains(pagina, "Confira o saldo em conta")
        self.assertContains(pagina, "Saldo projetado")

    def test_a_pagar_e_a_receber_mostram_o_pedido(self):
        mes = f"?mes={HOJE.year}-{HOJE.month:02d}"
        pagar = self.client.get(reverse("planejamento:pagar") + mes)
        self.assertContains(pagar, "Rogério (parcelas mensais)")
        self.assertContains(pagar, "28634")
        receber = self.client.get(reverse("planejamento:receber"))
        self.assertContains(receber, "R$ 10.000,00")

    def test_mes_invalido_cai_no_mes_de_hoje(self):
        self.assertEqual(self.client.get(reverse("planejamento:fechamento") + "?mes=2026-13").status_code, 200)
        self.assertEqual(self.client.get(reverse("planejamento:pagar") + "?mes=abc").status_code, 200)

    def test_ajustes_salva_e_audita(self):
        resposta = self.client.post(reverse("planejamento:ajustes"), {
            "bloco": "parametros", "parametros-saldo_inicial": "-5363.36",
            "parametros-saldo_em": HOJE.isoformat(), "parametros-margem_minima": "25",
            "parametros-atraso_dias": "10", "parametros-taxa_antecipacao": "12",
            "parametros-pct_cartao": "50", "parametros-pct_primeira": "50",
            "parametros-parcelas_padrao": "2", "parametros-cartao_padrao": self.xp.pk,
            "parametros-markup_alvo": "80"})
        self.assertRedirects(resposta, reverse("planejamento:ajustes"))
        p = Parametros.atual()
        self.assertEqual((p.saldo_inicial, p.taxa_antecipacao), (Decimal("-5363.36"), Decimal("12")))
        self.assertTrue(EventoAuditoria.objects.filter(acao="planejamento.ajustes").exists())

    def test_ajustes_recusado_devolve_o_que_foi_digitado(self):
        resposta = self.client.post(reverse("planejamento:ajustes"), {
            "bloco": "parametros", "parametros-saldo_inicial": "1234.56", "parametros-margem_minima": "250",
            "parametros-atraso_dias": "10", "parametros-taxa_antecipacao": "15",
            "parametros-pct_cartao": "50", "parametros-pct_primeira": "50",
            "parametros-parcelas_padrao": "2", "parametros-markup_alvo": "80"})
        self.assertEqual(resposta.status_code, 400)
        self.assertContains(resposta, 'value="1234.56"', status_code=400)
        self.assertContains(resposta, 'value="250"', status_code=400)
        self.assertEqual(Parametros.atual().saldo_inicial, 0)

    def test_incluir_cartao_pela_linha_nova(self):
        resposta = self.client.post(reverse("planejamento:ajustes"), {
            "bloco": "cartoes", "cartoes-TOTAL_FORMS": "2", "cartoes-INITIAL_FORMS": "1",
            "cartoes-MIN_NUM_FORMS": "0", "cartoes-MAX_NUM_FORMS": "1000",
            "cartoes-0-id": self.xp.pk, "cartoes-0-nome": "XP", "cartoes-0-vencimento": "1",
            "cartoes-0-fecha_dias_antes": "8", "cartoes-0-ativo": "on",
            "cartoes-1-nome": "Bradesco", "cartoes-1-vencimento": "10", "cartoes-1-fecha_dias_antes": "6",
            "cartoes-1-ativo": "on"})
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(sorted(Cartao.objects.values_list("nome", flat=True)), ["Bradesco", "XP"])

    def test_lancar_e_cancelar_movimento_entre_empresas(self):
        self.client.post(reverse("planejamento:entre_empresas"), {
            "data": "2026-10-31", "tipo": "cartao", "sentido": "cabana_deve", "valor": "10322.11",
            "descricao": "Parte da Cabana nas faturas de outubro"})
        mov = MovimentoEntreEmpresas.objects.get()
        pagina = self.client.get(reverse("planejamento:entre_empresas"))
        self.assertContains(pagina, "A Cabana deve ao Studio")
        self.assertContains(pagina, "R$ 10.322,11")
        self.client.post(reverse("planejamento:cancelar_movimento", args=[mov.pk]))
        mov.refresh_from_db()
        self.assertIsNotNone(mov.cancelado_em)
        self.assertContains(self.client.get(reverse("planejamento:entre_empresas")), "Nenhum movimento")

    def test_prolabore_sem_empresa_volta_preenchido(self):
        resposta = self.client.post(reverse("planejamento:entre_empresas"), {
            "data": "2026-10-20", "tipo": "prolabore", "valor": "11995.23", "descricao": "Cartões do Henry"})
        self.assertEqual(resposta.status_code, 400)
        self.assertContains(resposta, "Diga qual empresa pagou", status_code=400)
        self.assertContains(resposta, 'value="Cartões do Henry"', status_code=400)
        self.assertFalse(MovimentoEntreEmpresas.objects.exists())


class PermissaoTest(TestCase):
    def test_comercial_e_administrativo_nao_entram(self):
        """Pró-labore e entre empresas são da gerência."""
        for nome, perfil in (("sdr", COMERCIAL), ("adm", ADMINISTRATIVO)):
            usuario(nome, perfil)
            self.client.login(username=nome, password=SENHA_TESTE)
            for rota in TELAS:
                self.assertEqual(self.client.get(reverse(rota)).status_code, 403, (nome, rota))

    def test_quem_so_ve_nao_muda(self):
        from django.contrib.auth.models import Permission
        u = usuario("so_ve")
        u.user_permissions.add(Permission.objects.get(codename="ver_planejamento"))
        self.client.login(username="so_ve", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("planejamento:ajustes")).status_code, 200)
        self.assertNotContains(self.client.get(reverse("planejamento:ajustes")), "Salvar as regras")
        resposta = self.client.post(reverse("planejamento:ajustes"), {"bloco": "parametros"})
        self.assertEqual(resposta.status_code, 403)
        resposta = self.client.post(reverse("planejamento:entre_empresas"), {
            "data": "2026-10-20", "tipo": "transferencia", "sentido": "cabana_deve", "valor": "10"})
        self.assertEqual(resposta.status_code, 403)
        self.assertFalse(MovimentoEntreEmpresas.objects.exists())
