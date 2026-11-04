"""A ficha técnica diz de que o sistema é feito, lendo do próprio sistema.

O risco que estes testes guardam é um só: alguém, um dia, achar mais simples escrever
"PostgreSQL 16.10" na tela do que perguntar ao banco. No dia seguinte à atualização a
ficha estaria mentindo e ninguém saberia. Por isso há teste de que o número da tela é o
número que o sistema responde agora, e teste de que a tela não quebra quando a resposta
não vem.
"""

from unittest import mock

import django
from django.test import TestCase
from django.urls import reverse

from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO, VENDEDOR
from apps.core.fabricas import usuario
from apps.processos import ficha_tecnica


class FichaTecnica(TestCase):
    def setUp(self):
        self.gerente = usuario("edson", ADMINISTRACAO)
        self.endereco = reverse("processos:ficha_tecnica")

    def test_diz_a_linguagem_e_o_banco(self):
        """São as duas perguntas que o Edson fez; têm que estar na tela, com versão."""
        self.client.force_login(self.gerente)
        corpo = self.client.get(self.endereco).content.decode()
        self.assertIn("Python", corpo)
        self.assertIn(django.get_version(), corpo)
        self.assertIn("PostgreSQL", corpo)

    def test_a_versao_do_banco_vem_do_banco(self):
        """Não vale escrever o número na tela: ele é o que a conexão aberta responde."""
        with mock.patch("apps.processos.ficha_tecnica.connection") as conexao:
            conexao.pg_version = 160010
            self.assertEqual(ficha_tecnica._postgres(), "16.10")

    def test_numero_que_nao_pode_ser_lido_aparece_como_nao_lido(self):
        """Palpite na ficha é pior do que ficha nenhuma: o que não se leu, se diz."""
        with mock.patch("apps.processos.ficha_tecnica.connection") as conexao:
            type(conexao).pg_version = mock.PropertyMock(side_effect=RuntimeError("banco parado"))
            self.assertEqual(ficha_tecnica._postgres(), ficha_tecnica.NAO_LIDO)

    def test_banco_parado_nao_derruba_a_tela(self):
        """Uma tela de documentação nunca pode cair por causa do que documenta."""
        self.client.force_login(self.gerente)
        with mock.patch("apps.processos.ficha_tecnica._postgres", return_value=ficha_tecnica.NAO_LIDO):
            resposta = self.client.get(self.endereco)
        self.assertEqual(resposta.status_code, 200)
        self.assertIn(ficha_tecnica.NAO_LIDO, resposta.content.decode())

    def test_traz_as_decisoes_que_nao_se_leem_do_sistema(self):
        """Sem elas a tabela é uma lista de nomes: por que isolado, por que só leitura."""
        self.client.force_login(self.gerente)
        corpo = self.client.get(self.endereco).content.decode()
        self.assertIn("só lê", corpo)
        self.assertIn("internet", corpo)

    def test_o_quadro_leva_para_a_ficha(self):
        """Ela mora na Base de processos; quem abre o quadro tem que achar."""
        self.client.force_login(self.gerente)
        corpo = self.client.get(reverse("processos:quadro")).content.decode()
        self.assertIn(self.endereco, corpo)

    def test_o_administrativo_tambem_ve(self):
        """Quem documenta processo é o administrativo: a ficha é material de trabalho dele."""
        self.client.force_login(usuario("barbara", ADMINISTRATIVO))
        self.assertEqual(self.client.get(self.endereco).status_code, 200)

    def test_o_vendedor_nao_ve(self):
        """O perfil de balcão tem uma tela só, e não é esta."""
        self.client.force_login(usuario("vendedor", VENDEDOR))
        self.assertEqual(self.client.get(self.endereco).status_code, 403)

    def test_sem_login_nao_abre(self):
        resposta = self.client.get(self.endereco)
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("contas:entrar"), resposta.url)

    def test_os_dois_comandos_do_servidor_aparecem_juntos(self):
        """Pedido dele em 19/10/2026: nunca mostrar um comando sem o outro.

        Quem abre o PowerShell no servidor faz as duas coisas na mesma visita; procurar
        o outro comando em outro ponto da página é o que ele não quer fazer.
        """
        self.client.force_login(self.gerente)
        corpo = self.client.get(self.endereco).content.decode()
        bloco = corpo[corpo.index("Os comandos do servidor"):]
        # Da mesma pasta, onde o zip chega, desde a 1.47.1 (pedido dele em 04/11/2026).
        self.assertIn(r"C:\instalacao\pacote\atualizar.ps1", bloco)
        self.assertIn(r"C:\instalacao\pacote\higienizar.ps1", bloco)
        self.assertIn("-Conferir", bloco)
        self.assertNotIn(r"C:\instalacao\atualizar.ps1", bloco)
        self.assertNotIn(r"C:\cabana-sistema\scripts\higienizar.ps1", bloco)

    def test_quem_atualiza_salva_o_zip_na_pasta_do_pacote(self):
        self.client.force_login(self.gerente)
        corpo = self.client.get(self.endereco).content.decode()
        self.assertIn(r"salva esse arquivo em <code>C:\instalacao\pacote</code>", corpo)

    def test_o_leia_me_do_pacote_tambem_traz_os_dois(self):
        """O mesmo pedido, no papel que vai dentro do zip. Pulado fora do repositório."""
        from pathlib import Path

        leia_me = Path(__file__).resolve().parents[3] / "implantacao" / "LEIA-ME.txt"
        if not leia_me.exists():  # o pacote instalado no servidor não leva implantacao/
            self.skipTest("LEIA-ME.txt só existe no repositório")
        texto = leia_me.read_text(encoding="utf-8")
        bloco = texto[texto.index("HIGIENIZAÇÃO"):]
        self.assertIn(r"C:\instalacao\pacote\atualizar.ps1", bloco)
        self.assertIn(r"C:\instalacao\pacote\higienizar.ps1", bloco)

    def test_o_motor_firebird_mostra_o_que_o_instalador_gravou(self):
        """Carregar a DLL só para perguntar a versão é caro: quem sabe é quem instalou."""
        with self.settings(IMPORTACAO_FIREBIRD_VERSAO="4.0.6.3221-0", IMPORTACAO_FIREBIRD_CLIENTE=""):
            versao, _caminho = ficha_tecnica._firebird()
        self.assertEqual(versao, "4.0.6")

    def test_sem_motor_instalado_a_ficha_nao_inventa(self):
        with self.settings(IMPORTACAO_FIREBIRD_VERSAO="", IMPORTACAO_FIREBIRD_CLIENTE=""):
            versao, _caminho = ficha_tecnica._firebird()
        self.assertEqual(versao, ficha_tecnica.NAO_LIDO)
