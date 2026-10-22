"""De que pedaço de calendário sai a média que vira sugestão (pedido do Edson, 14/10/2026).

*"faça analise do periodo definido no filtro e usar a media de vendas nesse mesmo período
e calcular a sugestao de compra"*.

Aqui se prova que a janela soma só o que caiu dentro dela, que o divisor é dia de porta
ABERTA e não dia de calendário, e que produto sem venda na janela volta para os doze meses
em vez de sumir da lista.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.compras import janela as janelas
from apps.importacao.models import (
    Importacao, ItemVendaImportada, ProdutoImportado, VendaImportada,
)

CORTE = date(2026, 9, 20)


class BaseJanela(TestCase):
    def setUp(self):
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO,
            situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(),
            data_corte=CORTE,
            mes_a_mes_desde=date(2021, 9, 1),
            dias_abertos_12m=356,
            produtos=0,
        )

    def produto(self, codigo="1", **campos):
        padrao = dict(
            importacao=self.importacao, codigo=codigo, descricao=f"PRODUTO {codigo}",
            grupo="MOVEIS", fornecedor="VIME LENZI", custo=Decimal("10"),
            preco_venda=Decimal("25"), estoque=Decimal("0"), vendas_12m=Decimal("120"),
        )
        padrao.update(campos)
        return ProdutoImportado.objects.create(**padrao)

    def venda(self, quando, *linhas):
        """Uma venda no dia `quando` com (código, unidades) em cada linha."""
        cabeca = VendaImportada.objects.create(
            importacao=self.importacao, id_set=VendaImportada.objects.count() + 1,
            numero=str(VendaImportada.objects.count() + 1), data=quando,
            dia_da_semana=(quando.weekday() + 1) % 7, valor=Decimal("100"),
        )
        for codigo, unidades in linhas:
            ItemVendaImportada.objects.create(
                venda=cabeca, codigo=codigo, descricao="PRODUTO",
                quantidade=Decimal(unidades), valor_total=Decimal(unidades) * 25)
        return cabeca

    def janela_de(self, chave):
        return janelas.montar(self.importacao, self.importacao.itens.all(), chave)

    def venda_de(self, chave, codigo="1", padrao_unidades=Decimal("120"), padrao_dias=356):
        produto = ProdutoImportado.objects.get(importacao=self.importacao, codigo=codigo)
        return self.janela_de(chave).para(produto, padrao_unidades, padrao_dias)


class ChaveDoFiltro(TestCase):
    def test_a_padrao_e_doze_meses(self):
        self.assertEqual(janelas.valida(""), janelas.DOZE_MESES)
        self.assertEqual(janelas.rotulo_de(""), "12 meses")

    def test_chave_inventada_na_url_cai_na_padrao(self):
        """A chave vem da URL, e URL é texto que qualquer um escreve."""
        self.assertEqual(janelas.valida("3650"), janelas.DOZE_MESES)
        self.assertEqual(janelas.valida("'; drop table"), janelas.DOZE_MESES)

    def test_as_janelas_oferecidas(self):
        self.assertEqual([c for c, _r, _d in janelas.PERIODOS], ["", "180", "90", "30"])


class JanelaPadrao(BaseJanela):
    def test_doze_meses_vem_pronto_da_foto_e_nao_consulta_nada(self):
        """Quem não mexe no filtro não paga nada por este arquivo existir."""
        self.produto()
        with self.assertNumQueries(0):
            janela = janelas.montar(self.importacao, self.importacao.itens.all(), "")
        self.assertTrue(janela.e_a_padrao)
        produto = ProdutoImportado.objects.get(codigo="1")
        with self.assertNumQueries(0):
            venda, voltou = janela.para(produto, Decimal("120"), 356)
        self.assertEqual(venda.unidades, Decimal("120"))
        self.assertEqual(venda.dias_abertos, 356)
        self.assertFalse(voltou)

    def test_sem_data_de_corte_nao_da_para_montar_janela(self):
        self.importacao.data_corte = None
        self.importacao.save(update_fields=["data_corte"])
        self.assertTrue(self.janela_de("90").e_a_padrao)

    def test_sem_importacao_nao_quebra(self):
        self.assertTrue(janelas.montar(None, None, "90").e_a_padrao)


class ASomaDaJanela(BaseJanela):
    def test_soma_so_o_que_caiu_dentro(self):
        self.produto()
        self.venda(CORTE - timedelta(days=10), ("1", 4))
        self.venda(CORTE - timedelta(days=80), ("1", 6))
        self.venda(CORTE - timedelta(days=200), ("1", 999))   # fora dos 90 dias
        venda, voltou = self.venda_de("90")
        self.assertEqual(venda.unidades, Decimal("10"))
        self.assertFalse(voltou)

    def test_a_janela_fecha_na_data_de_corte_e_nao_em_hoje(self):
        """A foto é de 20/09; venda de depois dela não existe para o sistema."""
        self.produto()
        self.venda(CORTE, ("1", 5))
        self.venda(CORTE + timedelta(days=3), ("1", 50))
        self.assertEqual(self.venda_de("90")[0].unidades, Decimal("5"))

    def test_o_primeiro_dia_da_janela_conta(self):
        """Trinta dias são trinta, e o mais antigo deles entra inteiro."""
        self.produto()
        self.venda(CORTE - timedelta(days=29), ("1", 3))
        self.venda(CORTE - timedelta(days=30), ("1", 7))
        self.assertEqual(self.venda_de("30")[0].unidades, Decimal("3"))

    def test_o_divisor_e_dia_de_porta_aberta(self):
        """A Cabana não abre todo dia: dividir por 30 um mês de 24 subestima em 20%."""
        self.produto()
        for dias in (2, 5, 9, 20):
            self.venda(CORTE - timedelta(days=dias), ("1", 1))
        venda, _voltou = self.venda_de("30")
        self.assertEqual(venda.dias_abertos, 4)
        self.assertEqual(venda.unidades, Decimal("4"))

    def test_duas_vendas_no_mesmo_dia_sao_um_dia_aberto(self):
        self.produto()
        self.venda(CORTE - timedelta(days=3), ("1", 1))
        self.venda(CORTE - timedelta(days=3), ("1", 2))
        venda, _voltou = self.venda_de("30")
        self.assertEqual(venda.dias_abertos, 1)
        self.assertEqual(venda.unidades, Decimal("3"))

    def test_a_loja_abriu_conta_mesmo_sem_vender_este_produto(self):
        """O dia aberto é da LOJA; a venda do produto é que é dele."""
        self.produto("1")
        self.produto("2")
        self.venda(CORTE - timedelta(days=2), ("2", 9))
        self.venda(CORTE - timedelta(days=4), ("1", 3))
        venda, _voltou = self.venda_de("30", "1")
        self.assertEqual(venda.dias_abertos, 2)
        self.assertEqual(venda.unidades, Decimal("3"))


class OFreio(BaseJanela):
    """Produto que não vendeu nada na janela volta para os doze meses, e a linha diz."""

    def test_sem_venda_na_janela_a_conta_volta_para_doze_meses(self):
        """Filtrar "3 meses" em junho zeraria todo produto de dezembro, e ele sumiria
        da lista — que é exatamente o produto que some da prateleira sem ninguém ver."""
        self.produto()
        self.venda(CORTE - timedelta(days=300), ("1", 50))
        self.venda(CORTE - timedelta(days=5), ("2", 1))   # a loja abriu, o produto não saiu
        venda, voltou = self.venda_de("90")
        self.assertTrue(voltou)
        self.assertEqual(venda.unidades, Decimal("120"))
        self.assertEqual(venda.dias_abertos, 356)

    def test_loja_sem_nenhum_dia_aberto_na_janela_tambem_volta(self):
        """Sem dia aberto não há divisor, e dividir por zero não é média: é erro."""
        self.produto()
        venda, voltou = self.venda_de("30")
        self.assertTrue(voltou)
        self.assertEqual(venda.dias_abertos, 356)


class ListaInteiraDeUmaVez(BaseJanela):
    def test_duas_consultas_para_a_lista_toda(self):
        for i in range(1, 13):
            self.produto(str(i))
            self.venda(CORTE - timedelta(days=i), (str(i), 2))
        with self.assertNumQueries(2):
            janela = self.janela_de("90")
        produtos = list(self.importacao.itens.all())
        with self.assertNumQueries(0):
            vendas = [janela.para(p, Decimal("120"), 356) for p in produtos]
        self.assertEqual(len(vendas), 12)
        self.assertTrue(all(v.unidades == Decimal("2") for v, _voltou in vendas))
        self.assertEqual(janela.rotulo, "3 meses")
