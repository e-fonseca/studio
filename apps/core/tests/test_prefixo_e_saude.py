from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from apps.contas.perfis import ADMINISTRACAO, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario


class PrefixoSistemaTest(TestCase):
    def test_rotas_ficam_sob_sistema(self):
        for nome in ["core:inicio", "core:saude", "contas:entrar", "processos:quadro", "auditoria:lista"]:
            self.assertTrue(reverse(nome).startswith("/sistema/"), nome)

    def test_raiz_redireciona_para_sistema(self):
        resposta = self.client.get("/")
        self.assertRedirects(resposta, "/sistema/", fetch_redirect_response=False)

    def test_sem_login_vai_para_entrar_sob_sistema(self):
        resposta = self.client.get("/sistema/processos/")
        self.assertRedirects(resposta, "/sistema/entrar/?next=/sistema/processos/", fetch_redirect_response=False)

    def test_estaticos_e_cookies_sob_sistema(self):
        self.assertTrue(settings.STATIC_URL.startswith("/sistema/"))
        self.assertEqual(settings.SESSION_COOKIE_PATH, "/sistema")
        self.assertEqual(settings.CSRF_COOKIE_PATH, "/sistema")

    def test_login_completo_e_cookie_no_caminho(self):
        usuario("edson", ADMINISTRACAO)
        resposta = self.client.post("/sistema/entrar/", {"username": "edson", "password": SENHA_TESTE})
        self.assertRedirects(resposta, "/sistema/", fetch_redirect_response=False)
        self.assertEqual(self.client.cookies[settings.SESSION_COOKIE_NAME]["path"], "/sistema")
        # O início encaminha para o dashboard, então aqui se segue o desvio.
        pagina = self.client.get("/sistema/", follow=True)
        self.assertContains(pagina, "Use seu próprio usuário.")
        self.assertContains(pagina, "Sair")
        self.assertContains(pagina, "/sistema/static/css/sistema.css")

    def test_tela_de_entrada_mostra_aviso(self):
        self.assertContains(self.client.get("/sistema/entrar/"), "Use seu próprio usuário.")


class SaudeTest(TestCase):
    def test_saude_responde_sem_login(self):
        resposta = self.client.get("/sistema/saude/")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), {"aplicacao": "ok", "banco": "ok"})


class NavegacaoEntreTelasTest(TestCase):
    """Setas de anterior e próxima, na ordem em que o sistema é usado."""

    def entrar(self, perfil=ADMINISTRACAO):
        usuario("edson", perfil)
        self.client.login(username="edson", password=SENHA_TESTE)

    def test_primeira_tela_so_tem_proxima(self):
        """A primeira é o Dashboard desde a 1.43.0; a Visão geral vem logo depois."""
        self.entrar()
        pagina = self.client.get(reverse("painel:dashboard"))
        self.assertContains(pagina, "Próxima")
        self.assertNotContains(pagina, "navegacao-anterior")

    def test_painel_leva_para_o_completo(self):
        self.entrar()
        pagina = self.client.get(reverse("painel:painel"))
        self.assertContains(pagina, reverse("painel:completo"))
        self.assertContains(pagina, "Anterior")

    def test_pula_a_tela_que_o_perfil_nao_pode_abrir(self):
        """Quem não vê auditoria não recebe seta para ela."""
        self.entrar(VENDEDOR)
        pagina = self.client.get(reverse("importacao:consulta"))
        self.assertNotContains(pagina, reverse("auditoria:lista"))


class LembretesDoDiaTest(TestCase):
    """Os lembretes saem de número que o sistema já calculou, nunca escritos à mão."""

    def test_sem_importacao_avisa_que_nao_ha_dados(self):
        from apps.core import lembretes

        edson = usuario("edson", ADMINISTRACAO)
        avisos = lembretes.do_dia(edson)
        self.assertTrue(avisos)
        self.assertEqual(avisos[0].nivel, "urgente")

    def test_quem_nao_ve_painel_nao_recebe_lembrete(self):
        from apps.core import lembretes

        self.assertEqual(lembretes.do_dia(usuario("ana", VENDEDOR)), [])

    def test_aviso_aparece_na_tela_escondido_ate_o_script_abrir(self):
        self.client.login(username=usuario("edson", ADMINISTRACAO).get_username(), password=SENHA_TESTE)
        pagina = self.client.get(reverse("painel:geral"))
        self.assertContains(pagina, 'id="lembretes-do-dia"')
        self.assertContains(pagina, "hidden")
