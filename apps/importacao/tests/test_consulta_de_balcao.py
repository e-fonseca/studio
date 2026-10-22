"""A consulta do balcão: leitor de código de barras, desenho do código e autopreenchimento."""

import json
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.contas.perfis import ADMINISTRACAO, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.importacao.models import Importacao, ProdutoImportado


class BaseConsulta(TestCase):
    def setUp(self):
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO,
            situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(),
            data_corte=date(2026, 9, 20),
            dias_abertos_12m=300,
            produtos=2,
        )
        ProdutoImportado.objects.create(
            importacao=self.importacao, codigo="000123", descricao="TAPETE COURO 2X3",
            grupo="TAPETE", fornecedor="GERMAN", custo=Decimal("100"),
            preco_venda=Decimal("180"), estoque=Decimal("4"), vendas_12m=Decimal("10"),
            codigo_barras="0000000000024",
        )
        ProdutoImportado.objects.create(
            importacao=self.importacao, codigo="000124", descricao="TAPETE SISAL",
            grupo="TAPETE", estoque=Decimal("0"), codigo_barras="",
        )
        usuario("balcao", VENDEDOR)
        self.client.login(username="balcao", password=SENHA_TESTE)


class TestLeitorDeCodigoDeBarras(BaseConsulta):
    def test_o_numero_do_leitor_acha_o_produto(self):
        resposta = self.client.get(reverse("importacao:consulta"), {"produto": "0000000000024"})
        self.assertContains(resposta, "TAPETE COURO 2X3")
        self.assertNotContains(resposta, "TAPETE SISAL")

    def test_o_codigo_aparece_desenhado_ao_lado_do_produto(self):
        resposta = self.client.get(reverse("importacao:consulta"), {"produto": "0000000000024"})
        self.assertContains(resposta, "codigo-de-barras")
        self.assertContains(resposta, "aria-label=\"Código de barras 0000000000024\"")

    def test_produto_sem_codigo_no_set_diz_isso_em_vez_de_desenhar_errado(self):
        resposta = self.client.get(reverse("importacao:consulta"), {"produto": "TAPETE SISAL"})
        self.assertContains(resposta, "sem código no SET")

    def test_a_consulta_continua_achando_por_nome_e_por_codigo(self):
        por_nome = self.client.get(reverse("importacao:consulta"), {"produto": "sisal"})
        self.assertContains(por_nome, "TAPETE SISAL")
        por_codigo = self.client.get(reverse("importacao:consulta"), {"produto": "000123"})
        self.assertContains(por_codigo, "TAPETE COURO 2X3")

    def test_a_tela_do_balcao_nao_mostra_dinheiro(self):
        resposta = self.client.get(reverse("importacao:consulta"), {"produto": "tapete"})
        self.assertNotContains(resposta, "R$ 180,00")  # preço de venda
        self.assertNotContains(resposta, "R$ 100,00")  # custo


class TestAutopreenchimento(BaseConsulta):
    def _sugerir(self, termo):
        resposta = self.client.get(reverse("importacao:sugestoes"), {"q": termo})
        return json.loads(resposta.content)["itens"]

    def test_sugere_pelo_comeco_do_nome(self):
        nomes = [item["descricao"] for item in self._sugerir("tapete")]
        self.assertEqual(sorted(nomes), ["TAPETE COURO 2X3", "TAPETE SISAL"])

    def test_uma_letra_so_nao_dispara_consulta(self):
        """Com uma letra a lista viria inteira e não ajudaria ninguém."""
        self.assertEqual(self._sugerir("t"), [])

    def test_sugere_pelo_codigo_de_barras(self):
        nomes = [item["descricao"] for item in self._sugerir("00000000000")]
        self.assertEqual(nomes, ["TAPETE COURO 2X3"])

    def test_a_sugestao_nao_devolve_valor_nenhum(self):
        item = self._sugerir("tapete")[0]
        self.assertEqual(sorted(item), ["codigo", "descricao", "estoque", "grupo"])

    def test_quem_nao_pode_consultar_nao_recebe_sugestao(self):
        self.client.logout()
        resposta = self.client.get(reverse("importacao:sugestoes"), {"q": "tapete"})
        self.assertNotEqual(resposta.status_code, 200)


class TestAuditoriaMostraDeOnde(TestCase):
    def test_a_trilha_tem_coluna_de_endereco_e_diz_quem_esta_logado(self):
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)
        resposta = self.client.get(reverse("auditoria:lista"))
        self.assertContains(resposta, "De onde")
        self.assertContains(resposta, "Você está conectado como")


class TestCampoDeCodigoDeBarras(BaseConsulta):
    """O campo próprio para digitar o número da etiqueta (pedido do Edson, 1.18.0)."""

    def test_acha_o_produto_pelo_numero_digitado(self):
        resposta = self.client.get(reverse("importacao:consulta"), {"barras": "0000000000024"})
        self.assertContains(resposta, "TAPETE COURO 2X3")
        self.assertNotContains(resposta, "TAPETE SISAL")

    def test_sem_os_zeros_da_frente_tambem_acha(self):
        """O leitor devolve EAN-13 começado em zero como UPC-A de 12 dígitos."""
        resposta = self.client.get(reverse("importacao:consulta"), {"barras": "000000000024"})
        self.assertContains(resposta, "TAPETE COURO 2X3")

    def test_espaco_e_pontuacao_digitados_a_mao_nao_atrapalham(self):
        resposta = self.client.get(reverse("importacao:consulta"), {"barras": "0000 0000 00024"})
        self.assertContains(resposta, "TAPETE COURO 2X3")

    def test_a_procura_e_pelo_numero_exato_e_nao_por_parte_dele(self):
        """Senão um pedaço do número traria uma lista inteira, sem serventia no balcão."""
        resposta = self.client.get(reverse("importacao:consulta"), {"barras": "24"})
        self.assertNotContains(resposta, "TAPETE COURO 2X3")

    def test_nao_procura_pela_descricao_neste_campo(self):
        resposta = self.client.get(reverse("importacao:consulta"), {"barras": "TAPETE"})
        self.assertNotContains(resposta, "TAPETE COURO 2X3")

    def test_codigo_que_nao_existe_explica_o_que_fazer(self):
        resposta = self.client.get(reverse("importacao:consulta"), {"barras": "7899999999999"})
        self.assertContains(resposta, "Nenhum produto cadastrado com o código de barras")

    def test_o_campo_aparece_na_tela_do_vendedor(self):
        resposta = self.client.get(reverse("importacao:consulta"))
        self.assertContains(resposta, 'name="barras"')

    def test_o_campo_nao_mostra_valor_nenhum_ao_vendedor(self):
        """A regra da tela: o vendedor não vê custo, margem nem preço."""
        resposta = self.client.get(reverse("importacao:consulta"), {"barras": "0000000000024"})
        corpo = resposta.content.decode()
        for proibido in ("100,00", "180,00", "Custo", "Margem"):
            self.assertNotIn(proibido, corpo)
