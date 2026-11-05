"""A versão instalada precisa aparecer na tela: é por ela que se relata problema."""

from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.contas.perfis import ADMINISTRACAO, VENDEDOR
from apps.core import versao
from apps.core.fabricas import SENHA_TESTE, usuario


def ler(conteudo):
    with TemporaryDirectory() as pasta:
        arquivo = Path(pasta) / versao.ARQUIVO
        arquivo.write_text(conteudo, encoding="utf-8")
        with override_settings(BASE_DIR=pasta):
            versao.atual.cache_clear()
            try:
                return versao.atual()
            finally:
                versao.atual.cache_clear()


class LeituraDaVersaoTest(TestCase):
    def test_pacote_do_servidor_traz_numero_commit_e_data(self):
        lida = ler("1.4.0\ncommit=abc1234\ndata=2026-10-06\n")
        self.assertEqual(lida.numero, "1.4.0")
        self.assertEqual(lida.commit, "abc1234")
        self.assertEqual(str(lida), "1.4.0 (2026-10-06, abc1234)")
        self.assertEqual(lida.curta, "1.4.0+abc1234")

    def test_copia_de_desenvolvimento_tem_so_o_numero(self):
        lida = ler("1.4.0\n")
        self.assertEqual(str(lida), "1.4.0")
        self.assertEqual(lida.curta, "1.4.0")

    def test_sem_arquivo_nao_quebra_a_tela(self):
        with TemporaryDirectory() as pasta:
            with override_settings(BASE_DIR=pasta):
                versao.atual.cache_clear()
                try:
                    self.assertEqual(versao.atual().numero, versao.DESCONHECIDA)
                finally:
                    versao.atual.cache_clear()

    def test_arquivo_do_repositorio_tem_numero_valido(self):
        versao.atual.cache_clear()
        try:
            self.assertRegex(versao.atual().numero, r"^\d+\.\d+\.\d+$")
        finally:
            versao.atual.cache_clear()


class VersaoNaTelaTest(TestCase):
    """A versão fica no topo e só no topo (pedido do Edson, 07/10/2026)."""

    def test_versao_aparece_no_topo(self):
        from apps.contas.perfis import ADMINISTRACAO

        usuario("edson", ADMINISTRACAO)
        self.client.login(username="edson", password=SENHA_TESTE)
        pagina = self.client.get(reverse("painel:geral"))
        self.assertContains(pagina, "versao-topo")
        self.assertContains(pagina, versao.atual().numero)

    def test_rodape_nao_repete_a_versao(self):
        from apps.contas.perfis import ADMINISTRACAO

        usuario("edson", ADMINISTRACAO)
        self.client.login(username="edson", password=SENHA_TESTE)
        pagina = self.client.get(reverse("painel:geral"))
        self.assertNotContains(pagina, 'class="versao"')

    def test_tela_de_entrada_ainda_mostra_a_versao(self):
        """Ali não existe topo, e é onde se confere a versão antes de entrar."""
        pagina = self.client.get(reverse("contas:entrar"))
        self.assertContains(pagina, versao.atual().numero)


class ConferirBancoTest(TestCase):
    """O comando que o instalador usa para não deixar coluna faltando passar batido."""

    def test_banco_em_dia_nao_reclama(self):
        from io import StringIO

        from django.core.management import call_command

        saida = StringIO()
        call_command("conferir_banco", stdout=saida)
        self.assertIn("todas as colunas esperadas existem", saida.getvalue())

    def test_coluna_faltando_aparece_na_saida(self):
        from io import StringIO

        from django.core.management import call_command
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("alter table importacao_importacao drop column etapa")
        saida = StringIO()
        try:
            call_command("conferir_banco", stdout=saida)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("alter table importacao_importacao add column etapa varchar(60) not null default ''")
        self.assertIn("importacao_importacao.etapa", saida.getvalue())


class HistoricoDeAtualizacoesTest(TestCase):
    """O Edson pediu em 06/10/2026 para ver no sistema o que já foi atualizado."""

    def historico_com(self, conteudo):
        from apps.core import atualizacoes

        pasta = TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        arquivo = Path(pasta.name) / "atualizacoes.tsv"
        arquivo.write_text(conteudo, encoding="utf-8")
        with override_settings(ATUALIZACOES_HISTORICO=arquivo):
            return atualizacoes.historico()

    def test_mais_recente_primeiro(self):
        lidas = self.historico_com(
            "05/10/2026 22:10\t1.3.0\tf0206f1\tstudio-sistema-pacote-1.3.0.zip\tok\n"
            "06/10/2026 23:40\t1.7.0\tff59648\tstudio-sistema-pacote-1.7.0.zip\tok\n"
        )
        self.assertEqual([a.numero for a in lidas], ["1.7.0", "1.3.0"])
        self.assertEqual(lidas[0].pacote, "studio-sistema-pacote-1.7.0.zip")
        self.assertTrue(lidas[0].deu_certo)

    def test_linha_estranha_nao_derruba_a_tela(self):
        lidas = self.historico_com("linha sem colunas\n\n06/10/2026 23:40\t1.7.0\n")
        self.assertEqual(len(lidas), 1)
        self.assertEqual(lidas[0].numero, "1.7.0")
        self.assertEqual(lidas[0].pacote, "")

    def test_sem_arquivo_devolve_lista_vazia(self):
        from apps.core import atualizacoes

        with override_settings(ATUALIZACOES_HISTORICO=Path("/nao/existe/atualizacoes.tsv")):
            self.assertEqual(atualizacoes.historico(), [])

    def test_mudancas_vem_do_arquivo_do_projeto(self):
        from apps.core import atualizacoes

        lista = atualizacoes.mudancas()
        self.assertTrue(lista)
        self.assertRegex(lista[0].numero, r"^\d+\.\d+\.\d+$")
        self.assertTrue(lista[0].itens)
        self.assertNotIn("**", " ".join(lista[0].itens))

    def test_toda_versao_do_arquivo_tem_o_que_mostrar(self):
        """Versão sem item de lista aparece na tela como título vazio.

        Aconteceu com a 1.30.0: a entrada foi escrita em parágrafos com negrito no
        começo, em vez da lista com "- " que o resto do arquivo usa, e o leitor
        (`atualizacoes.mudancas`) só recolhe linha de lista. O teste antigo olhava
        apenas a versão mais nova, então o defeito passou. Regra que vale para o
        arquivo inteiro se confere no arquivo inteiro.
        """
        from apps.core import atualizacoes

        vazias = [m.numero for m in atualizacoes.mudancas(limite=200) if not m.itens]
        self.assertEqual(vazias, [], f"versões sem item de lista em docs/mudancas.md: {vazias}")

    def test_tela_mostra_versao_atualizacoes_e_mudancas(self):
        from apps.core import atualizacoes

        # Desde a 1.24.1 o histórico é tela de dinheiro: ele cita o faturamento e o
        # lucro que cada versão consertou, então pede importacao.ver_painel.
        usuario("edson", ADMINISTRACAO)
        self.client.login(username="edson", password=SENHA_TESTE)
        pasta = TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        arquivo = Path(pasta.name) / "atualizacoes.tsv"
        arquivo.write_text("06/10/2026 23:40\t1.7.0\tff59648\tstudio-sistema-pacote-1.7.0.zip\tok\n", encoding="utf-8")
        with override_settings(ATUALIZACOES_HISTORICO=arquivo):
            pagina = self.client.get(reverse("core:versoes"))
        self.assertContains(pagina, "studio-sistema-pacote-1.7.0.zip")
        self.assertContains(pagina, "O que mudou em cada versão")
        self.assertContains(pagina, atualizacoes.mudancas()[0].numero)

    def test_rodape_leva_para_a_tela_de_versoes(self):
        # A entrada encaminha cada perfil para a primeira tela dele, por isso follow:
        # o que se confere é que o número no alto é link para quem pode abrir.
        usuario("edson", ADMINISTRACAO)
        self.client.login(username="edson", password=SENHA_TESTE)
        pagina = self.client.get(reverse("core:inicio"), follow=True)
        self.assertContains(pagina, reverse("core:versoes"))

    def test_o_vendedor_ve_o_numero_da_versao_mas_nao_o_historico(self):
        """A versão é como se confere se a atualização entrou: fica à vista de todos.

        O histórico é que é guardado, porque conta quanto a loja fatura. Antes da
        1.24.1 o vendedor abria o ano inteiro de faturamento digitando o endereço.
        """
        usuario("barbara", VENDEDOR)
        self.client.login(username="barbara", password=SENHA_TESTE)

        self.assertEqual(self.client.get(reverse("core:versoes")).status_code, 403)

        # O número continua no alto da tela dele, só que sem link.
        tela = self.client.get(reverse("importacao:consulta"))
        self.assertContains(tela, f"versão {versao.atual().numero}")
        self.assertNotContains(tela, reverse("core:versoes"))

    def test_so_quem_entrou_ve(self):
        pagina = self.client.get(reverse("core:versoes"))
        self.assertEqual(pagina.status_code, 302)


class ConferirFirebirdTest(TestCase):
    """O erro do Windows ao carregar o motor não diz nada; o comando traduz."""

    def chamar(self, **override):
        from io import StringIO

        from django.core.management import call_command

        saida = StringIO()
        with override_settings(**override):
            call_command("conferir_firebird", stdout=saida)
        return saida.getvalue()

    def test_sem_caminho_configurado_avisa(self):
        saida = self.chamar(IMPORTACAO_FIREBIRD_CLIENTE="")
        self.assertIn("STUDIO_FIREBIRD_DLL", saida)

    def test_arquivo_inexistente_manda_rodar_a_atualizacao(self):
        saida = self.chamar(IMPORTACAO_FIREBIRD_CLIENTE="/nao/existe/fbclient.dll")
        self.assertIn("não existe", saida)
        self.assertIn("atualização", saida)


class VersaoNoTopoTest(TestCase):
    """O Edson pediu em 06/10/2026 a versão à vista no menu superior."""

    def test_topo_mostra_a_versao_e_leva_para_a_tela(self):
        usuario("edson")
        self.client.login(username="edson", password=SENHA_TESTE)
        pagina = self.client.get(reverse("core:inicio"))
        self.assertContains(pagina, "versao-topo")
        self.assertContains(pagina, f"versão {versao.atual().numero}")

    def test_tela_de_entrada_nao_mostra_menu(self):
        pagina = self.client.get(reverse("contas:entrar"))
        self.assertContains(pagina, "Entrar")
        self.assertNotContains(pagina, "Menu principal")
        self.assertContains(pagina, "marca-entrada")
