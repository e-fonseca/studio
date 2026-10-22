"""A visão geral: a tela de abrir e entender, sem precisar de outra."""

from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.contas.perfis import ADMINISTRACAO, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.fornecedores.models import Fornecedor
from apps.importacao.models import Importacao, ProdutoImportado, VendaImportada
from apps.painel import visao_geral


class BaseVisao(TestCase):
    def setUp(self):
        cache.clear()
        hoje = timezone.localdate()
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO,
            situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(),
            data_corte=hoje - timedelta(days=1),
            dias_abertos_12m=300,
            produtos=3,
            detalhe={"vendas_mes": [[2026, 1, 1000.0, 10]], "compras_mes": [[2026, 1, 1500.0, 3]]},
        )
        ProdutoImportado.objects.create(
            importacao=self.importacao, codigo="1", descricao="CARVAO", grupo="LENHA",
            fornecedor="MADEIREIRA SUL", custo=Decimal("10"), preco_venda=Decimal("18"),
            estoque=Decimal("20"), vendas_12m=Decimal("300"), receita_12m=Decimal("5400"),
            compras_12m=Decimal("300"), valor_compras_12m=Decimal("3000"),
        )
        ProdutoImportado.objects.create(
            importacao=self.importacao, codigo="2", descricao="LENHA", grupo="LENHA",
            fornecedor="SITIO BOA VISTA", custo=Decimal("5"), preco_venda=Decimal("9"),
            estoque=Decimal("100"), vendas_12m=Decimal("2"), receita_12m=Decimal("18"),
            compras_12m=Decimal("10"), valor_compras_12m=Decimal("50"),
        )
        ProdutoImportado.objects.create(
            importacao=self.importacao, codigo="3", descricao="VASO PARADO", grupo="CERAMICA",
            fornecedor="CERAMICA BOA", custo=Decimal("30"), preco_venda=Decimal("50"),
            estoque=Decimal("4"), vendas_12m=Decimal("0"), receita_12m=Decimal("0"),
            compras_12m=Decimal("4"), valor_compras_12m=Decimal("120"),
        )


class MontagemTest(BaseVisao):
    def test_os_numeros_grandes_da_abertura(self):
        visao = visao_geral.montar(self.importacao)
        valores = {c.chave: c.valor for c in visao.cartoes}
        self.assertEqual(valores["faturamento"], Decimal("5418"))
        self.assertEqual(valores["compras"], Decimal("3170"))
        # 20x10 + 100x5 + 4x30 = 820 parados na prateleira.
        self.assertEqual(valores["estoque"], Decimal("820"))

    def test_diz_quanto_entrou_depois_do_desconto(self):
        """O Dashboard soma o total da venda e esta tela soma o preço dos itens.

        Os dois estão certos, e no dado real a diferença é de R$ 38 mil: o desconto do
        balcão. Sem dizer isso, as duas telas pareciam brigar.
        """
        VendaImportada.objects.create(
            importacao=self.importacao, id_set=1, numero="1",
            data=self.importacao.data_corte, hora="15:00", dia_da_semana=1,
            valor=Decimal("5000"), desconto=Decimal("418"), forma_pagamento="PIX",
        )
        visao = visao_geral.montar(self.importacao)
        cartao = next(c for c in visao.cartoes if c.chave == "faturamento")
        self.assertEqual(cartao.valor, Decimal("5418"))      # preço dos itens
        self.assertIn("R$ 5.000,00", cartao.rodape)          # o que entrou de fato

    def test_saldo_negativo_do_set_nao_desconta_do_estoque(self):
        """O SET da loja tem 1.456 produtos com saldo abaixo de zero.

        Somando o negativo, este cartão mostrava R$ 126 mil a menos do que o estoque que
        está na prateleira, e discordava do limite de compra, que sempre usou max(0).
        """
        ProdutoImportado.objects.create(
            importacao=self.importacao, codigo="4", descricao="ERRO DE SALDO", grupo="LENHA",
            fornecedor="MADEIREIRA SUL", custo=Decimal("50"), preco_venda=Decimal("90"),
            estoque=Decimal("-10"), vendas_12m=Decimal("0"), receita_12m=Decimal("0"),
        )
        visao = visao_geral.montar(self.importacao)
        valores = {c.chave: c.valor for c in visao.cartoes}
        self.assertEqual(valores["estoque"], Decimal("820"))
        cartao = next(c for c in visao.cartoes if c.chave == "estoque")
        self.assertIn("saldo negativo", cartao.rodape)

    def test_avisa_quando_comprou_mais_do_que_vendeu(self):
        ProdutoImportado.objects.filter(codigo="1").update(valor_compras_12m=Decimal("9000"))
        visao = visao_geral.montar(self.importacao)
        compras = next(c for c in visao.cartoes if c.chave == "compras")
        self.assertEqual(compras.nivel, "ruim")
        self.assertIn("Saiu mais em compra", compras.rodape)

    def test_produto_que_nunca_vendeu_fica_fora_da_lista_e_vira_contagem(self):
        """Senão a lista dos menos vendidos enche de item morto e esconde o que só está devagar."""
        visao = visao_geral.montar(self.importacao)
        self.assertEqual(visao.sem_venda, 1)
        nomes = [linha.descricao for linha in visao.menos_vendidos]
        self.assertNotIn("VASO PARADO", nomes)
        self.assertEqual(nomes[0], "LENHA")
        self.assertEqual(visao.mais_vendidos[0].descricao, "CARVAO")

    def test_rosca_fecha_em_cem_por_cento(self):
        visao = visao_geral.montar(self.importacao)
        self.assertAlmostEqual(float(sum(g["fatia"] for g in visao.grupos)), 100.0, places=0)
        self.assertEqual(visao.grupos[0]["nome"], "Lenha")

    def test_sem_importacao_devolve_tela_vazia_sem_quebrar(self):
        visao = visao_geral.montar(None)
        self.assertEqual(visao.cartoes, [])
        self.assertEqual(visao.mais_vendidos, [])


class TicketNaAberturaTest(BaseVisao):
    """O ticket médio na tela principal (pedido do Edson, 07/10/2026)."""

    def _vender(self, dia, valor, forma="PIX"):
        from apps.importacao.models import VendaImportada

        VendaImportada.objects.create(
            importacao=self.importacao, id_set=VendaImportada.objects.count() + 1,
            numero="1", data=dia, hora="10:00", dia_da_semana=(dia.weekday() + 1) % 7,
            valor=Decimal(valor), desconto=Decimal("0"), forma_pagamento=forma, vendedor="")

    def test_o_ticket_medio_virou_um_dos_numeros_grandes(self):
        hoje = self.importacao.data_corte
        self._vender(hoje, "100")
        self._vender(hoje - timedelta(days=1), "200")
        visao = visao_geral.montar(self.importacao)
        cartao = {c.chave: c for c in visao.cartoes}["ticket"]
        self.assertEqual(cartao.valor, Decimal("150.00"))
        self.assertIn("2 vendas", cartao.rodape)

    def test_sem_venda_registrada_o_cartao_diz_isso_em_vez_de_zero(self):
        cartao = {c.chave: c for c in visao_geral.montar(self.importacao).cartoes}["ticket"]
        self.assertIn("Sem venda", cartao.rodape)

    def test_a_abertura_diz_quanto_sai_no_fim_de_semana(self):
        corte = self.importacao.data_corte
        sabado = corte - timedelta(days=(corte.weekday() - 5) % 7)
        self._vender(sabado, "300")
        self._vender(sabado - timedelta(days=3), "100")
        visao = visao_geral.montar(self.importacao)
        self.assertEqual(visao.fatia_do_fim_de_semana, 75)
        self.assertEqual(visao.melhor_dia.rotulo, "Sábado")

    def test_a_tela_mostra_o_ticket_e_leva_para_a_tela_cheia(self):
        self._vender(self.importacao.data_corte, "100")
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)
        resposta = self.client.get(reverse("painel:geral"))
        self.assertContains(resposta, "Ticket médio da venda")
        self.assertContains(resposta, "R$ 100,00")
        self.assertContains(resposta, reverse("painel:ticket_medio"))


class TelaTest(BaseVisao):
    def test_gerencia_abre_e_ve_as_estrelas_do_fornecedor(self):
        Fornecedor.objects.create(nome="MADEIREIRA SUL", reputacao=5, relacao="parceiro")
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)
        resposta = self.client.get(reverse("painel:geral"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Visão geral")
        self.assertContains(resposta, "Parceiro")
        self.assertContains(resposta, "Os 10 que mais vendem")

    def test_quem_nao_ve_painel_nao_abre(self):
        usuario("balcao", VENDEDOR)
        self.client.login(username="balcao", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("painel:geral")).status_code, 403)
