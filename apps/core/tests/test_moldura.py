"""Só a intranet pode mostrar o sistema dentro de uma página (2.2.0).

Pedido do Edson em 06/11/2026: o sistema abre ao lado do menu da intranet, num quadro.
Quem decide quem pode emoldurar é este sistema, pelo cabeçalho de cada resposta; um site
qualquer continua sem poder (é o que impede alguém de esconder o sistema por baixo de um
botão dele). Ver apps/core/moldura.py.
"""

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.core.moldura import MolduraMiddleware, politica

INTRANET = "https://192.168.3.254"


class APoliticaTest(SimpleTestCase):
    def test_sem_intranet_ninguem_emoldura(self):
        self.assertEqual(politica([]), "frame-ancestors 'none'")

    def test_com_intranet_so_ela_e_o_proprio_sistema(self):
        self.assertEqual(politica([INTRANET]), f"frame-ancestors 'self' {INTRANET}")


class OCabecalhoTest(SimpleTestCase):
    def passar(self, resposta, **ajustes):
        with override_settings(**ajustes):
            meio = MolduraMiddleware(lambda request: resposta)
            return meio(RequestFactory().get("/studio/"))

    def test_a_intranet_pode_e_o_deny_nao_sai(self):
        resposta = self.passar(HttpResponse("ok"), INTRANET_ORIGENS=[INTRANET])
        self.assertEqual(resposta["Content-Security-Policy"], f"frame-ancestors 'self' {INTRANET}")
        self.assertTrue(resposta.xframe_options_exempt)

    def test_sem_intranet_configurada_volta_tudo_como_era(self):
        resposta = self.passar(HttpResponse("ok"), INTRANET_ORIGENS=[])
        self.assertEqual(resposta["Content-Security-Policy"], "frame-ancestors 'none'")
        self.assertFalse(getattr(resposta, "xframe_options_exempt", False))

    def test_a_politica_do_anexo_continua_e_ganha_a_moldura(self):
        """Anexo sai com default-src 'none'; a moldura se soma a ela, não a substitui."""
        anexo = HttpResponse("pdf")
        anexo["Content-Security-Policy"] = "default-src 'none'"
        resposta = self.passar(anexo, INTRANET_ORIGENS=[INTRANET])
        self.assertEqual(resposta["Content-Security-Policy"],
                         f"default-src 'none'; frame-ancestors 'self' {INTRANET}")

    def test_quem_ja_disse_frame_ancestors_nao_e_contrariado(self):
        propria = HttpResponse("x")
        propria["Content-Security-Policy"] = "frame-ancestors 'none'"
        resposta = self.passar(propria, INTRANET_ORIGENS=[INTRANET])
        self.assertEqual(resposta["Content-Security-Policy"], "frame-ancestors 'none'")


class NaTelaDeVerdadeTest(TestCase):
    """Pela pilha inteira de middlewares, na ordem das configurações."""

    def test_a_tela_de_entrada_pode_abrir_na_intranet(self):
        resposta = self.client.get(reverse("contas:entrar"))
        self.assertEqual(resposta.status_code, 200)
        self.assertIn(f"frame-ancestors 'self' {INTRANET}", resposta["Content-Security-Policy"])
        self.assertNotIn("X-Frame-Options", resposta)

    @override_settings(INTRANET_ORIGENS=[])
    def test_sem_a_intranet_o_deny_de_antes_volta(self):
        resposta = self.client.get(reverse("contas:entrar"))
        self.assertEqual(resposta["X-Frame-Options"], "DENY")
        self.assertIn("frame-ancestors 'none'", resposta["Content-Security-Policy"])

    def test_os_cookies_tem_o_nome_do_studio(self):
        """cabana_sessao era o nome do outro sistema, que mora no mesmo servidor."""
        from django.conf import settings

        self.assertEqual(settings.SESSION_COOKIE_NAME, "studio_sessao")
        self.assertEqual(settings.CSRF_COOKIE_NAME, "studio_csrf")
        self.assertEqual(settings.SESSION_COOKIE_PATH, settings.CSRF_COOKIE_PATH)
        self.assertTrue(settings.SESSION_COOKIE_PATH.startswith("/studio"))
