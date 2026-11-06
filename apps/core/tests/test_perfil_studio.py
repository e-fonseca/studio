"""O perfil Studio Industrial: o menu sem compras e sem estoque (pedido de 05/11/2026)."""

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.contas.perfis import ADMINISTRACAO, COMERCIAL
from apps.core import menu
from apps.core.fabricas import SENHA_TESTE, usuario


@override_settings(ASSUNTOS_DESLIGADOS=("compras", "estoque"))
class MenuDoStudioTest(TestCase):
    def setUp(self):
        usuario("edson", ADMINISTRACAO)
        self.client.login(username="edson", password=SENHA_TESTE)

    def test_o_topo_nao_tem_compras_nem_estoque(self):
        pagina = self.client.get(reverse("projetos:lista"))
        topo = [grupo.rotulo for grupo in menu.ativos()]
        self.assertEqual(topo, ["Dashboard", "Visão geral", "Leads", "Pedidos", "Vendas",
                                "Dinheiro", "Sistema"])
        self.assertNotContains(pagina, 'href="/studio/compras/lista/"')
        self.assertNotContains(pagina, 'href="/studio/importacao/consulta/"')
        self.assertContains(pagina, 'href="/studio/leads/"')

    def test_as_setas_nao_passam_pelas_telas_escondidas(self):
        rotas = [tela.rota for tela in menu.telas()]
        self.assertNotIn("compras:lista", rotas)
        self.assertNotIn("inventario:lista", rotas)
        self.assertIn("projetos:lista", rotas)

    def test_dinheiro_abre_pelo_planejamento(self):
        """Desde o protótipo da Henriett (06/11/2026) Dinheiro cai no Planejamento, e o
        Fluxo de caixa do SET vem logo depois."""
        dinheiro = next(g for g in menu.ativos() if g.chave == "dinheiro")
        self.assertEqual([t.rota for t in dinheiro.telas[:2]], ["planejamento:visao", "financeiro:fluxo"])

    def test_a_tela_escondida_continua_pedindo_permissao(self):
        """Esconder do menu não é trancar: quem tranca é a permissão de cada tela."""
        usuario("sdr", COMERCIAL)
        self.client.login(username="sdr", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("compras:lista")).status_code, 403)

    def test_o_comercial_entra_pelo_funil_e_nao_ve_dinheiro(self):
        usuario("sdr2", COMERCIAL)
        self.client.login(username="sdr2", password=SENHA_TESTE)
        resposta = self.client.get(reverse("core:inicio"))
        self.assertRedirects(resposta, reverse("leads:funil"), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("projetos:lista")).status_code, 403)
        self.assertEqual(self.client.get(reverse("financeiro:fluxo")).status_code, 403)
        self.assertEqual(self.client.get(reverse("planejamento:visao")).status_code, 403)


class PadraoDoStudioTest(TestCase):
    def test_o_padrao_do_studio_desliga_compras_e_estoque(self):
        """Sem nada no studio.env, a instalação nasce sem os dois assuntos."""
        import importlib
        import os

        from config.settings import base
        antes = os.environ.pop("STUDIO_ASSUNTOS_DESLIGADOS", None)
        try:
            self.assertEqual(importlib.reload(base).ASSUNTOS_DESLIGADOS, ("compras", "estoque"))
        finally:
            if antes is not None:
                os.environ["STUDIO_ASSUNTOS_DESLIGADOS"] = antes
