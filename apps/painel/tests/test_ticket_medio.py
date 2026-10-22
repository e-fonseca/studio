"""Ticket médio de venda, com os filtros da gerência."""

from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.contas.perfis import ADMINISTRACAO, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.importacao.models import Importacao, VendaImportada
from apps.painel import ticket

CORTE = date(2026, 9, 20)


def _dia_da_semana(dia):
    """Mesma conta da importação: 0 é domingo."""
    return (dia.weekday() + 1) % 7


class BaseTicket(TestCase):
    def setUp(self):
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO,
            situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(),
            data_corte=CORTE,
            dias_abertos_12m=300,
            produtos=1,
        )
        self.proxima = 1

    def venda(self, dia, valor, forma="DINHEIRO", vendedor="", desconto="0"):
        self.proxima += 1
        return VendaImportada.objects.create(
            importacao=self.importacao, id_set=self.proxima, numero=str(self.proxima),
            data=dia, hora="10:00", dia_da_semana=_dia_da_semana(dia),
            valor=Decimal(valor), desconto=Decimal(desconto),
            forma_pagamento=forma, vendedor=vendedor,
        )


class TestConta(BaseTicket):
    def test_o_ticket_e_o_faturamento_dividido_pelas_vendas(self):
        self.venda(date(2026, 9, 18), "100")
        self.venda(date(2026, 9, 19), "50")
        resultado = ticket.calcular(self.importacao)
        self.assertEqual(resultado.total.vendas, 2)
        self.assertEqual(resultado.total.faturamento, Decimal("150"))
        self.assertEqual(resultado.total.ticket, Decimal("75.00"))

    def test_sem_venda_nenhuma_nao_divide_por_zero(self):
        resultado = ticket.calcular(self.importacao)
        self.assertFalse(resultado.tem_dados)
        self.assertEqual(resultado.total.ticket, Decimal("0"))

    def test_sem_importacao_a_tela_nao_quebra(self):
        resultado = ticket.calcular(None)
        self.assertFalse(resultado.tem_dados)

    def test_o_periodo_corta_pela_data_da_importacao_e_nao_pelo_dia_de_hoje(self):
        """Os dados vão até 20/09/2026; contar 7 dias de hoje devolveria lista vazia."""
        self.venda(date(2026, 9, 18), "100")
        self.venda(date(2026, 3, 1), "900")
        de_sete_dias = ticket.calcular(self.importacao, periodo="7d")
        self.assertEqual(de_sete_dias.total.vendas, 1)
        self.assertEqual(ticket.calcular(self.importacao, periodo="12m").total.vendas, 2)

    def test_periodo_inventado_na_url_cai_nos_doze_meses(self):
        resultado = ticket.calcular(self.importacao, periodo="tudo-desde-1900")
        self.assertEqual(resultado.periodo, "12m")

    def test_desconto_medio_e_maior_venda(self):
        self.venda(date(2026, 9, 18), "100", desconto="10")
        self.venda(date(2026, 9, 19), "300", desconto="0")
        resultado = ticket.calcular(self.importacao)
        self.assertEqual(resultado.desconto_medio, Decimal("5.00"))
        self.assertEqual(resultado.maior_venda, Decimal("300"))


class TestQuebras(BaseTicket):
    def test_sabado_e_domingo_aparecem_separados_com_domingo_primeiro(self):
        self.venda(date(2026, 9, 19), "100")   # sábado
        self.venda(date(2026, 9, 20), "200")   # domingo
        resultado = ticket.calcular(self.importacao)
        nomes = [linha.rotulo for linha in resultado.por_dia_da_semana]
        self.assertEqual(nomes, ["Domingo", "Sábado"])

    def test_quebra_por_forma_de_pagamento(self):
        self.venda(date(2026, 9, 18), "100", forma="PIX")
        self.venda(date(2026, 9, 18), "40", forma="DINHEIRO")
        resultado = ticket.calcular(self.importacao)
        self.assertEqual([l.rotulo for l in resultado.por_forma], ["PIX", "DINHEIRO"])

    def test_venda_sem_vendedor_sai_da_lista_e_vira_contagem_a_parte(self):
        """O SET deixa o vendedor em branco na maioria das vendas: a tela diz isso."""
        self.venda(date(2026, 9, 18), "100", vendedor="MARIA")
        self.venda(date(2026, 9, 18), "100", vendedor="")
        resultado = ticket.calcular(self.importacao)
        self.assertEqual([l.rotulo for l in resultado.por_vendedor], ["MARIA"])
        self.assertEqual(resultado.vendas_sem_vendedor, 1)

    def test_recorte_com_poucas_vendas_vem_marcado(self):
        self.venda(date(2026, 9, 18), "100", forma="PIX")
        resultado = ticket.calcular(self.importacao)
        self.assertTrue(resultado.por_forma[0].pouco_para_comparar)

    def test_mes_a_mes_vem_em_ordem_de_calendario(self):
        self.venda(date(2026, 9, 1), "100")
        self.venda(date(2026, 7, 1), "100")
        resultado = ticket.calcular(self.importacao)
        self.assertEqual([l.rotulo for l in resultado.por_mes], ["07/2026", "09/2026"])


class TestFiltros(BaseTicket):
    def setUp(self):
        super().setUp()
        self.venda(date(2026, 9, 18), "100", forma="PIX", vendedor="MARIA")
        self.venda(date(2026, 9, 19), "300", forma="DINHEIRO", vendedor="JOAO")

    def test_filtrar_por_forma_muda_os_numeros_do_topo(self):
        resultado = ticket.calcular(self.importacao, forma="PIX")
        self.assertEqual(resultado.total.vendas, 1)
        self.assertEqual(resultado.total.ticket, Decimal("100.00"))

    def test_as_opcoes_continuam_todas_na_caixa_depois_de_filtrar(self):
        """Filtrar por PIX não pode fazer DINHEIRO desaparecer da seleção."""
        resultado = ticket.calcular(self.importacao, forma="PIX")
        self.assertEqual(sorted(resultado.formas), ["DINHEIRO", "PIX"])
        self.assertEqual(sorted(resultado.vendedores), ["JOAO", "MARIA"])

    def test_filtrar_por_vendedor_e_por_dia_da_semana(self):
        self.assertEqual(ticket.calcular(self.importacao, vendedor="JOAO").total.vendas, 1)
        sabado = str(_dia_da_semana(date(2026, 9, 19)))
        self.assertEqual(ticket.calcular(self.importacao, dia=sabado).total.vendas, 1)

    def test_filtro_que_nao_existe_e_ignorado_em_vez_de_zerar_a_tela(self):
        resultado = ticket.calcular(self.importacao, forma="BOLETO BANCARIO", vendedor="NINGUEM")
        self.assertEqual(resultado.total.vendas, 2)
        self.assertEqual(resultado.filtro_forma, "")

    def test_dia_da_semana_torto_na_url_nao_quebra(self):
        self.assertEqual(ticket.calcular(self.importacao, dia="segunda").total.vendas, 2)
        self.assertEqual(ticket.calcular(self.importacao, dia="99").total.vendas, 2)


class TestTela(BaseTicket):
    def setUp(self):
        super().setUp()
        self.venda(date(2026, 9, 18), "100", forma="PIX", vendedor="MARIA")
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)

    def test_a_tela_mostra_o_ticket_e_os_filtros(self):
        resposta = self.client.get(reverse("painel:ticket_medio"))
        self.assertContains(resposta, "Ticket médio")
        self.assertContains(resposta, "R$ 100,00")
        self.assertContains(resposta, "PIX")
        self.assertContains(resposta, "Domingo")

    def test_os_filtros_da_url_chegam_na_tela(self):
        resposta = self.client.get(reverse("painel:ticket_medio"), {"forma": "PIX"})
        self.assertEqual(resposta.context["t"].filtro_forma, "PIX")

    def test_a_tela_avisa_que_o_set_nao_registra_o_vendedor_na_maioria(self):
        self.venda(date(2026, 9, 19), "50", vendedor="")
        resposta = self.client.get(reverse("painel:ticket_medio"))
        self.assertContains(resposta, "sem vendedor")

    def test_vendedor_nao_abre_o_ticket_medio(self):
        """Ticket médio é valor: a tela do balcão não mostra dinheiro."""
        self.client.logout()
        usuario("balcao", VENDEDOR)
        self.client.login(username="balcao", password=SENHA_TESTE)
        resposta = self.client.get(reverse("painel:ticket_medio"))
        self.assertEqual(resposta.status_code, 403)

    def test_a_tela_esta_no_assunto_de_vendas(self):
        """Desde a 1.35.0 o menu é por assunto: ela aparece com as outras telas de venda."""
        from apps.core import menu

        assunto = menu.grupo_de("painel:ticket_medio")
        self.assertIsNotNone(assunto, "o ticket médio saiu do menu")
        self.assertEqual(assunto.chave, "vendas")
        resposta = self.client.get(reverse("painel:dashboard"))
        self.assertContains(resposta, reverse("painel:ticket_medio"))
