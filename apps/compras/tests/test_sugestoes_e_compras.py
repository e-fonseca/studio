"""Compras por fornecedor e as sugestões calculadas em cima dos números da loja."""

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.compras import historico, sugestoes
from apps.contas.perfis import ADMINISTRACAO, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.importacao.models import (
    CompraImportada,
    Importacao,
    ItemCompraImportada,
    ProdutoImportado,
)


class BaseDeCompras(TestCase):
    def setUp(self):
        self.corte = date(2026, 9, 20)
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO,
            situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(),
            data_corte=self.corte,
            dias_abertos_12m=300,
            produtos=4,
        )
        # Zerado e vendendo: tem que aparecer em "repor agora".
        ProdutoImportado.objects.create(
            importacao=self.importacao, codigo="1", descricao="CARVAO SACO", grupo="LENHA",
            fornecedor="MADEIREIRA SUL", custo=Decimal("10"), preco_venda=Decimal("18"),
            estoque=Decimal("0"), vendas_12m=Decimal("300"), vendas_90d=Decimal("80"),
            receita_12m=Decimal("5400"), compras_12m=Decimal("300"),
            valor_compras_12m=Decimal("3000"), codigo_barras="0000000000024",
        )
        # Comprado no ano e nunca vendido: "parar de comprar" e "conversar com o fornecedor".
        ProdutoImportado.objects.create(
            importacao=self.importacao, codigo="2", descricao="VASO CERAMICA GRANDE",
            grupo="CERAMICA", fornecedor="CERAMICA BOA", custo=Decimal("30"),
            preco_venda=Decimal("50"), estoque=Decimal("40"), vendas_12m=Decimal("0"),
            compras_12m=Decimal("40"), valor_compras_12m=Decimal("1200"),
        )
        # Vende e tem margem: "empurrar na venda".
        ProdutoImportado.objects.create(
            importacao=self.importacao, codigo="3", descricao="TAPETE COURO", grupo="TAPETE",
            fornecedor="MADEIREIRA SUL", custo=Decimal("100"), preco_venda=Decimal("180"),
            estoque=Decimal("12"), vendas_12m=Decimal("40"), vendas_90d=Decimal("10"),
            receita_12m=Decimal("7200"),
        )
        # Zerado mas com pedido a caminho: não entra em "repor", senão compra em dobro.
        ProdutoImportado.objects.create(
            importacao=self.importacao, codigo="4", descricao="BANCO MADEIRA", grupo="MOVEL",
            fornecedor="MADEIREIRA SUL", custo=Decimal("50"), preco_venda=Decimal("90"),
            estoque=Decimal("0"), vendas_12m=Decimal("20"), vendas_90d=Decimal("6"),
            receita_12m=Decimal("1800"), pedido_em_aberto=Decimal("10"),
        )

        self.compra = CompraImportada.objects.create(
            importacao=self.importacao, id_set=10, numero="000010",
            fornecedor="MADEIREIRA SUL", comprador="MOISES", situacao="Entregue / Faturado",
            data_pedido=self.corte - timedelta(days=10), data_nota=self.corte - timedelta(days=10),
            data_entrega=self.corte - timedelta(days=8), valor_total=Decimal("800"), itens=1,
        )
        ItemCompraImportada.objects.create(
            compra=self.compra, codigo="1", descricao="CARVAO SACO",
            quantidade=Decimal("80"), custo_unitario=Decimal("10"), custo_total=Decimal("800"),
        )
        self.antiga = CompraImportada.objects.create(
            importacao=self.importacao, id_set=5, numero="000005", fornecedor="CERAMICA BOA",
            situacao="Entregue / Faturado", data_nota=self.corte - timedelta(days=200),
            valor_total=Decimal("1200"), itens=0,
        )
        self.gerente = usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)


class TestUltimaCompraPorFornecedor(BaseDeCompras):
    def test_lista_um_fornecedor_por_linha_com_a_compra_mais_nova(self):
        linhas = historico.ultima_de_cada_fornecedor(self.importacao, hoje=self.corte)
        por_nome = {linha.nome: linha for linha in linhas}
        self.assertEqual(sorted(por_nome), ["CERAMICA BOA", "MADEIREIRA SUL"])
        self.assertEqual(por_nome["MADEIREIRA SUL"].compra.numero, "000010")
        self.assertEqual(por_nome["MADEIREIRA SUL"].dias_sem_comprar, 10)

    def test_quem_comprou_mais_recentemente_vem_primeiro(self):
        linhas = historico.ultima_de_cada_fornecedor(self.importacao, hoje=self.corte)
        self.assertEqual(linhas[0].nome, "MADEIREIRA SUL")

    def test_a_tela_mostra_a_compra_e_o_detalhe_dela(self):
        resposta = self.client.get(reverse("compras:consulta"))
        self.assertContains(resposta, "MADEIREIRA SUL")
        self.assertContains(resposta, "000010")
        detalhe = self.client.get(reverse("compras:compra", args=[self.compra.id_set]))
        self.assertContains(detalhe, "CARVAO SACO")
        self.assertContains(detalhe, "MOISES")

    def test_compra_de_outra_importacao_nao_abre(self):
        resposta = self.client.get(reverse("compras:compra", args=[99999]))
        self.assertEqual(resposta.status_code, 404)

    def test_vendedor_nao_abre_as_compras(self):
        self.client.logout()
        usuario("balcao", VENDEDOR)
        self.client.login(username="balcao", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("compras:consulta")).status_code, 403)


class TestSugestoes(BaseDeCompras):
    def setUp(self):
        super().setUp()
        self.blocos = {b.chave: b for b in sugestoes.montar(self.importacao).blocos}

    def test_repor_traz_o_que_zerou_e_continua_vendendo(self):
        codigos = [linha.codigo for linha in self.blocos["repor"].linhas]
        self.assertEqual(codigos, ["1"])

    def test_repor_ignora_o_que_ja_vem_a_caminho(self):
        """Senão a loja compra de novo o que já está no caminhão."""
        codigos = [linha.codigo for linha in self.blocos["repor"].linhas]
        self.assertNotIn("4", codigos)

    def test_parar_de_comprar_soma_o_que_entrou_e_nao_saiu(self):
        bloco = self.blocos["parar"]
        self.assertEqual([linha.codigo for linha in bloco.linhas], ["2"])
        self.assertEqual(bloco.total, Decimal("1200.00"))

    def test_por_para_girar_mostra_o_dinheiro_parado_e_o_preco_minimo(self):
        bloco = self.blocos["destravar"]
        self.assertEqual([linha.codigo for linha in bloco.linhas], ["2"])
        # 40 unidades a 30 de custo.
        self.assertEqual(bloco.linhas[0].valor, Decimal("1200.00"))
        self.assertIn("R$ 34,50", bloco.linhas[0].detalhe)

    def test_empurrar_na_venda_ordena_pelo_lucro_dos_90_dias(self):
        bloco = self.blocos["empurrar"]
        codigos = [linha.codigo for linha in bloco.linhas]
        # Tapete: 10 x 80 = 800 de lucro. Carvão está zerado e fica de fora.
        self.assertEqual(codigos[0], "3")
        self.assertNotIn("1", codigos)

    def test_renegociar_agrupa_por_fornecedor(self):
        bloco = self.blocos["renegociar"]
        self.assertEqual([linha.fornecedor for linha in bloco.linhas], ["CERAMICA BOA"])
        self.assertEqual(bloco.linhas[0].valor, Decimal("1200.00"))

    def test_a_tela_explica_de_onde_saem_os_numeros(self):
        resposta = self.client.get(reverse("compras:sugestoes"))
        self.assertContains(resposta, "Repor agora")
        self.assertContains(resposta, "Regra:")
        self.assertContains(resposta, "CARVAO SACO")

    def test_o_que_nao_e_mercadoria_fica_de_fora(self):
        """CONSUMO PROPRIO é o que a loja usa e DIVERSOS é a venda avulsa do caixa:
        nenhum dos dois é decisão de compra, e sujariam todas as listas."""
        ProdutoImportado.objects.create(
            importacao=self.importacao, codigo="90", descricao="CONSUMO PROPRIO - CESTO/PAPEL",
            grupo="CONSUMO PROPRIO", custo=Decimal("5"), estoque=Decimal("100"),
            vendas_12m=Decimal("0"), compras_12m=Decimal("100"),
            valor_compras_12m=Decimal("500"),
        )
        ProdutoImportado.objects.create(
            importacao=self.importacao, codigo="91", descricao="DIVERSOS", grupo="CERAMICA",
            custo=Decimal("5"), estoque=Decimal("100"), vendas_12m=Decimal("0"),
            compras_12m=Decimal("100"), valor_compras_12m=Decimal("500"),
        )
        blocos = {b.chave: b for b in sugestoes.montar(self.importacao).blocos}
        for chave in ("parar", "destravar"):
            codigos = [linha.codigo for linha in blocos[chave].linhas]
            self.assertNotIn("90", codigos, chave)
            self.assertNotIn("91", codigos, chave)

    def test_sem_importacao_a_tela_nao_quebra(self):
        self.assertEqual(sugestoes.montar(None).blocos, [])
