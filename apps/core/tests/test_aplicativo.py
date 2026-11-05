"""O atalho na tela inicial do celular (PWA): manifesto, operário e as marcas no HTML."""

import json

from django.test import TestCase
from django.urls import reverse

from apps.contas.perfis import ADMINISTRACAO, VENDEDOR
from apps.core import versao
from apps.core.fabricas import SENHA_TESTE, usuario


class TestManifesto(TestCase):
    def setUp(self):
        self.resposta = self.client.get(reverse("core:manifesto"))
        self.manifesto = json.loads(self.resposta.content)

    def test_abre_sem_login(self):
        """O navegador busca o manifesto sem mandar o cookie da sessão."""
        self.assertEqual(self.resposta.status_code, 200)

    def test_e_servido_como_manifesto_e_nao_como_json_qualquer(self):
        self.assertIn("application/manifest+json", self.resposta["Content-Type"])

    def test_abre_em_tela_cheia_dentro_do_sistema(self):
        self.assertEqual(self.manifesto["display"], "standalone")
        self.assertEqual(self.manifesto["start_url"], "/studio/")
        self.assertEqual(self.manifesto["scope"], "/studio/")

    def test_tem_o_nome_e_as_cores_da_loja(self):
        self.assertIn("Studio Industrial", self.manifesto["name"])
        self.assertEqual(self.manifesto["short_name"], "Studio")
        self.assertEqual(self.manifesto["lang"], "pt-BR")
        # Escuras desde a 1.43.0, as do topo e do fundo das telas: a barra do celular
        # e a tela de abertura não piscam claro antes do sistema escuro.
        self.assertEqual(self.manifesto["theme_color"], "#242729")
        self.assertEqual(self.manifesto["background_color"], "#13110f")

    def test_tem_icone_de_192_de_512_e_o_recortavel_do_android(self):
        por_tamanho = {}
        for icone in self.manifesto["icons"]:
            por_tamanho.setdefault(icone["sizes"], []).append(icone["purpose"])
        self.assertIn("192x192", por_tamanho)
        self.assertIn("maskable", por_tamanho["512x512"])
        self.assertIn("any", por_tamanho["512x512"])

    def test_os_icones_sao_servidos_pelo_proprio_sistema(self):
        for icone in self.manifesto["icons"]:
            self.assertTrue(icone["src"].startswith("/studio/static/"), icone["src"])

    def test_os_atalhos_do_toque_longo_apontam_para_telas_que_existem(self):
        enderecos = [atalho["url"] for atalho in self.manifesto["shortcuts"]]
        self.assertIn(reverse("importacao:consulta"), enderecos)
        self.assertIn(reverse("inventario:lista"), enderecos)
        for endereco in enderecos:
            self.assertEqual(self.client.get(endereco).status_code, 302)  # pede login


class TestOperario(TestCase):
    def setUp(self):
        self.resposta = self.client.get(reverse("core:operario"))
        self.codigo = self.resposta.content.decode()

    def test_responde_dentro_de_sistema_para_poder_cuidar_das_telas(self):
        """O navegador só deixa o operário cuidar da pasta dele e do que está abaixo."""
        self.assertEqual(reverse("core:operario"), "/studio/operario.js")

    def test_e_servido_como_javascript(self):
        self.assertEqual(self.resposta.status_code, 200)
        self.assertIn("javascript", self.resposta["Content-Type"])

    def test_o_deposito_leva_a_versao_para_a_atualizacao_chegar_aos_celulares(self):
        self.assertIn(f'DEPOSITO = "cabana-{versao.atual().numero}"', self.codigo)

    def test_o_proprio_operario_nunca_fica_guardado_no_navegador(self):
        self.assertIn("no-store", self.resposta["Cache-Control"])

    def test_guarda_o_visual_e_o_leitor_de_codigo(self):
        self.assertIn("/static/css/sistema.css", self.codigo)
        self.assertIn("/static/js/leitor/zxing.min.js", self.codigo)

    def test_numero_da_loja_nunca_sai_do_deposito(self):
        """Saldo velho na tela é pior do que tela nenhuma: só o visual é guardado."""
        self.assertIn('endereco.pathname.indexOf("/static/")', self.codigo)
        self.assertIn("apaga o antigo", self.codigo)

    def test_apaga_o_deposito_das_versoes_antigas(self):
        self.assertIn("caches.delete", self.codigo)


class TestMarcasNoHtml(TestCase):
    def setUp(self):
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)

    def _pagina(self):
        return self.client.get(reverse("core:versoes"))

    def test_a_pagina_aponta_para_o_manifesto_e_para_os_icones(self):
        resposta = self._pagina()
        self.assertContains(resposta, reverse("core:manifesto"))
        self.assertContains(resposta, "apple-touch-icon")
        self.assertContains(resposta, "apple-mobile-web-app-capable")

    def test_o_operario_so_e_registrado_no_endereco_seguro(self):
        """Fora do https o navegador recusa; tentar só encheria o console de erro."""
        resposta = self._pagina()
        self.assertContains(resposta, "window.isSecureContext")
        self.assertContains(resposta, reverse("core:operario"))

    def test_o_vendedor_tambem_leva_o_atalho_no_celular(self):
        """A consulta do balcão é justamente a tela que se usa com o celular na mão."""
        self.client.logout()
        usuario("balcao", VENDEDOR)
        self.client.login(username="balcao", password=SENHA_TESTE)
        resposta = self.client.get(reverse("importacao:consulta"))
        self.assertContains(resposta, reverse("core:manifesto"))
