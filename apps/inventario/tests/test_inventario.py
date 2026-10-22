"""Contagem física: achar o produto pelo leitor, somar, apurar a diferença e fechar."""

from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import EventoAuditoria
from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.importacao.models import Importacao, ProdutoImportado
from apps.inventario import servicos
from apps.inventario.models import Contagem


class BaseInventario(TestCase):
    def setUp(self):
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO,
            situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(),
            data_corte=date(2026, 9, 20),
            dias_abertos_12m=300,
            produtos=2,
        )
        self.carvao = ProdutoImportado.objects.create(
            importacao=self.importacao, codigo="1", descricao="CARVAO SACO", grupo="LENHA",
            custo=Decimal("10"), estoque=Decimal("12"), codigo_barras="0000000000024",
        )
        self.vaso = ProdutoImportado.objects.create(
            importacao=self.importacao, codigo="2", descricao="VASO CERAMICA GRANDE",
            grupo="CERAMICA", custo=Decimal("30"), estoque=Decimal("5"),
            codigo_barras="0000000000031",
        )
        self.operador = usuario("estoquista", ADMINISTRATIVO)
        self.client.login(username="estoquista", password=SENHA_TESTE)
        self.contagem = servicos.abrir("Prateleira dos tapetes", self.operador)


class TestContagem(BaseInventario):
    def test_o_leitor_acha_o_produto_pelo_codigo_de_barras(self):
        item = servicos.registrar_contagem(
            self.contagem, "0000000000024", Decimal("10"), self.operador)
        self.assertEqual(item.codigo, "1")
        self.assertEqual(item.saldo_set, Decimal("12.000"))
        self.assertEqual(item.diferenca, Decimal("-2.000"))

    def test_contar_o_mesmo_produto_duas_vezes_soma(self):
        """O produto está em dois lugares: quem conta passa o leitor nos dois."""
        servicos.registrar_contagem(self.contagem, "1", Decimal("7"), self.operador)
        item = servicos.registrar_contagem(self.contagem, "1", Decimal("5"), self.operador)
        self.assertEqual(item.quantidade, Decimal("12.000"))
        self.assertTrue(item.bate)

    def test_nome_que_casa_com_varios_produtos_nao_e_escolhido_no_chute(self):
        ProdutoImportado.objects.create(
            importacao=self.importacao, codigo="3", descricao="CARVAO CAIXA", estoque=0)
        with self.assertRaises(servicos.ErroDeContagem):
            servicos.registrar_contagem(self.contagem, "CARVAO", Decimal("1"), self.operador)

    def test_produto_que_nao_existe_devolve_recado_e_nao_grava(self):
        with self.assertRaises(servicos.ErroDeContagem):
            servicos.registrar_contagem(self.contagem, "9999999999999", Decimal("1"), self.operador)
        self.assertEqual(self.contagem.itens.count(), 0)

    def test_quantidade_aceita_virgula(self):
        self.assertEqual(servicos.quantidade_informada("2,5"), Decimal("2.500"))
        self.assertEqual(servicos.quantidade_informada("2.5"), Decimal("2.500"))
        self.assertIsNone(servicos.quantidade_informada("abc"))
        self.assertIsNone(servicos.quantidade_informada(""))

    def test_resumo_separa_o_que_falta_do_que_sobra_e_conta_em_dinheiro(self):
        servicos.registrar_contagem(self.contagem, "1", Decimal("10"), self.operador)  # faltam 2
        servicos.registrar_contagem(self.contagem, "2", Decimal("8"), self.operador)   # sobram 3
        resumo = servicos.resumir(self.contagem)
        self.assertEqual(resumo.contados, 2)
        self.assertEqual(resumo.divergentes, 2)
        self.assertEqual(resumo.faltando, Decimal("2.000"))
        self.assertEqual(resumo.sobrando, Decimal("3.000"))
        self.assertEqual(resumo.valor_da_falta, Decimal("20.00"))
        self.assertEqual(resumo.valor_da_sobra, Decimal("90.00"))
        self.assertEqual(resumo.diferenca_em_dinheiro, Decimal("70.00"))
        # Maior diferença em dinheiro primeiro: é por onde a loja ajusta.
        self.assertEqual(resumo.itens_divergentes[0].codigo, "2")

    def test_contagem_fechada_nao_aceita_mais_contagem(self):
        servicos.fechar(self.contagem, self.operador)
        with self.assertRaises(servicos.ErroDeContagem):
            servicos.registrar_contagem(self.contagem, "1", Decimal("1"), self.operador)

    def test_tudo_vai_para_a_auditoria(self):
        servicos.registrar_contagem(self.contagem, "1", Decimal("10"), self.operador)
        acoes = set(EventoAuditoria.objects.values_list("acao", flat=True))
        self.assertIn("inventario.contagem_aberta", acoes)
        self.assertIn("inventario.item_contado", acoes)

    def test_lista_de_ajustes_sai_em_texto_com_cabecalho(self):
        servicos.registrar_contagem(self.contagem, "1", Decimal("10"), self.operador)
        texto = servicos.divergencias_em_texto(self.contagem)
        self.assertTrue(texto.startswith("codigo\tproduto"))
        self.assertIn("CARVAO SACO", texto)


class TestTelasDoInventario(BaseInventario):
    def test_contar_pela_tela_grava_e_volta_para_a_contagem(self):
        resposta = self.client.post(
            reverse("inventario:contar", args=[self.contagem.pk]),
            {"produto": "0000000000024", "quantidade": "10"}, follow=True)
        self.assertContains(resposta, "CARVAO SACO")
        self.assertEqual(self.contagem.itens.count(), 1)

    def test_abrir_sem_nome_avisa_e_nao_cria(self):
        antes = Contagem.objects.count()
        resposta = self.client.post(reverse("inventario:abrir"), {"nome": " "}, follow=True)
        self.assertContains(resposta, "Dê um nome à contagem")
        self.assertEqual(Contagem.objects.count(), antes)

    def test_a_lista_de_ajustes_vem_como_arquivo(self):
        servicos.registrar_contagem(self.contagem, "1", Decimal("10"), self.operador)
        resposta = self.client.get(reverse("inventario:ajustes", args=[self.contagem.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("attachment", resposta["Content-Disposition"])

    def test_vendedor_nao_abre_o_inventario(self):
        self.client.logout()
        usuario("balcao", VENDEDOR)
        self.client.login(username="balcao", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("inventario:lista")).status_code, 403)

    def test_gerencia_abre_e_fecha(self):
        self.client.logout()
        usuario("chefia", ADMINISTRACAO)
        self.client.login(username="chefia", password=SENHA_TESTE)
        self.client.post(reverse("inventario:fechar", args=[self.contagem.pk]))
        self.contagem.refresh_from_db()
        self.assertFalse(self.contagem.aberta)
