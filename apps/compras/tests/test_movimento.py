"""O que entrou, o que saiu, e onde o estoque foi parar (pedido do Edson, 14/10/2026).

*"exiba uma sugestão de compra analisando o que foi comprado de um determinado produto e
o que foi vendido e o resultado que seria o estoque (...) levando em consideração o que foi
comprado na última compra e vendido"*.

Aqui se prova que a conta dos doze meses fecha, que a última compra é a última mesmo, e
que a venda desde ela sai em unidades inteiras — porque ratear mês é dividir, e divisão
de Decimal volta com 28 casas.
"""

from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.compras import movimento
from apps.importacao.models import (
    CompraImportada, Importacao, ItemCompraImportada, ProdutoImportado, VendaMensalDoProduto,
)

CORTE = date(2026, 9, 20)


class BaseMovimento(TestCase):
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
            preco_venda=Decimal("25"), estoque=Decimal("0"),
            vendas_12m=Decimal("0"), compras_12m=Decimal("0"),
        )
        padrao.update(campos)
        return ProdutoImportado.objects.create(**padrao)

    def compra(self, codigo, quando, unidades, pendente=False, pela_nota=True, numero="1"):
        """Uma compra com uma linha. `pela_nota` escolhe se a data é da nota ou do pedido."""
        cabeca = CompraImportada.objects.create(
            importacao=self.importacao, id_set=CompraImportada.objects.count() + 1,
            numero=numero, fornecedor="VIME LENZI", pendente=pendente,
            data_nota=quando if pela_nota else None,
            data_pedido=None if pela_nota else quando,
        )
        return ItemCompraImportada.objects.create(
            compra=cabeca, codigo=codigo, descricao="PRODUTO",
            quantidade=Decimal(unidades), custo_unitario=Decimal("10"),
            custo_total=Decimal(unidades) * 10,
        )

    def mes(self, codigo, ano, mes, unidades):
        VendaMensalDoProduto.objects.update_or_create(
            importacao=self.importacao, codigo=codigo, ano=ano, mes=mes,
            defaults={"unidades": Decimal(unidades), "receita": Decimal(unidades) * 25},
        )

    def movimento_de(self, codigo="1"):
        produto = ProdutoImportado.objects.get(importacao=self.importacao, codigo=codigo)
        tabela = movimento.montar(self.importacao, self.importacao.itens.all())
        return tabela.para(produto)


class ContaDosDozeMeses(BaseMovimento):
    """Comprou X, vendeu Y, então o estoque andou X − Y. Não custa consulta nenhuma."""

    def test_comprou_menos_do_que_vendeu_derruba_o_estoque(self):
        self.produto(compras_12m=Decimal("400"), vendas_12m=Decimal("1517"),
                     estoque=Decimal("-820"))
        m = self.movimento_de()
        self.assertEqual(m.andou_12m, Decimal("-1117"))
        self.assertTrue(m.comprou_menos_do_que_vendeu)
        self.assertEqual(m.quanto_caiu, Decimal("1117"))

    def test_o_saldo_de_um_ano_atras_sai_por_dedução(self):
        """A loja nunca fez inventário: o saldo de partida só se deduz do movimento."""
        self.produto(compras_12m=Decimal("400"), vendas_12m=Decimal("1517"),
                     estoque=Decimal("-820"))
        self.assertEqual(self.movimento_de().tinha_um_ano_atras, Decimal("297"))

    def test_comprou_mais_do_que_vendeu_sobe_o_estoque(self):
        self.produto(compras_12m=Decimal("50"), vendas_12m=Decimal("20"), estoque=Decimal("35"))
        m = self.movimento_de()
        self.assertEqual(m.andou_12m, Decimal("30"))
        self.assertFalse(m.comprou_menos_do_que_vendeu)
        self.assertEqual(m.quanto_caiu, Decimal("0"))
        self.assertEqual(m.tinha_um_ano_atras, Decimal("5"))

    def test_estoque_que_nao_andou(self):
        self.produto(compras_12m=Decimal("9"), vendas_12m=Decimal("9"), estoque=Decimal("0"))
        self.assertEqual(self.movimento_de().andou_12m, Decimal("0"))


class AUltimaCompra(BaseMovimento):
    def test_a_mais_nova_ganha(self):
        self.produto()
        self.compra("1", date(2024, 8, 8), 69, numero="velha")
        self.compra("1", date(2026, 7, 6), 6, numero="nova")
        m = self.movimento_de()
        self.assertEqual(m.ultima_compra_em, date(2026, 7, 6))
        self.assertEqual(m.ultima_compra_unidades, Decimal("6"))

    def test_duas_notas_no_mesmo_dia_entram_as_duas(self):
        self.produto()
        self.compra("1", date(2026, 7, 6), 6, numero="a")
        self.compra("1", date(2026, 7, 6), 4, numero="b")
        self.assertEqual(self.movimento_de().ultima_compra_unidades, Decimal("10"))

    def test_compra_pendente_nao_e_compra_feita(self):
        """Ela é mercadoria a caminho, e já aparece na coluna A CAMINHO da lista."""
        self.produto()
        self.compra("1", date(2026, 1, 10), 5, numero="feita")
        self.compra("1", date(2026, 8, 1), 90, pendente=True, numero="a-caminho")
        m = self.movimento_de()
        self.assertEqual(m.ultima_compra_em, date(2026, 1, 10))
        self.assertEqual(m.ultima_compra_unidades, Decimal("5"))

    def test_sem_nota_vale_a_data_do_pedido(self):
        """A mesma regra do importador. Outra data aqui faria dois números discordarem."""
        self.produto()
        self.compra("1", date(2026, 5, 2), 7, pela_nota=False)
        self.assertEqual(self.movimento_de().ultima_compra_em, date(2026, 5, 2))

    def test_compra_sem_data_nenhuma_fica_de_fora(self):
        self.produto()
        cabeca = CompraImportada.objects.create(
            importacao=self.importacao, id_set=99, numero="sem-data", fornecedor="VIME LENZI")
        ItemCompraImportada.objects.create(
            compra=cabeca, codigo="1", quantidade=Decimal("8"), custo_unitario=Decimal("10"))
        self.assertFalse(self.movimento_de().tem_ultima_compra)

    def test_produto_que_nunca_foi_comprado(self):
        self.produto(vendas_12m=Decimal("26"), estoque=Decimal("-34"))
        m = self.movimento_de()
        self.assertFalse(m.tem_ultima_compra)
        self.assertEqual(m.vendido_desde_a_compra, Decimal("0"))


class VendaDesdeAUltimaCompra(BaseMovimento):
    """A conta que o Edson descreveu: entraram N no dia D, e desde D saíram M."""

    def test_sobra_o_que_entrou_menos_o_que_saiu(self):
        self.produto()
        self.compra("1", date(2026, 6, 1), 10)
        self.mes("1", 2026, 6, 3)
        self.mes("1", 2026, 7, 2)
        m = self.movimento_de()
        self.assertEqual(m.vendido_desde_a_compra, Decimal("5"))
        self.assertEqual(m.sobra_da_ultima_compra, Decimal("5"))
        self.assertFalse(m.ultima_compra_ja_vendida)

    def test_quando_a_compra_toda_ja_saiu(self):
        self.produto()
        self.compra("1", date(2026, 6, 1), 4)
        self.mes("1", 2026, 6, 6)
        m = self.movimento_de()
        self.assertTrue(m.ultima_compra_ja_vendida)
        self.assertEqual(m.sobra_da_ultima_compra, Decimal("-2"))

    def test_o_mes_da_compra_entra_rateado_por_dias(self):
        """Compra no dia 16 de junho: só a metade de junho que vem DEPOIS dela conta."""
        self.produto()
        self.compra("1", date(2026, 6, 16), 10)
        self.mes("1", 2026, 6, 30)   # 15 dos 30 dias → 15 unidades
        self.assertEqual(self.movimento_de().vendido_desde_a_compra, Decimal("15"))

    def test_sai_em_unidades_inteiras(self):
        """Ratear é dividir: sem arredondar, a tela escreveria "vendeu 50,774 desde então"."""
        self.produto()
        self.compra("1", date(2026, 6, 16), 10)
        self.mes("1", 2026, 6, 31)
        vendido = self.movimento_de().vendido_desde_a_compra
        self.assertEqual(vendido, vendido.to_integral_value())
        self.assertEqual(vendido, Decimal("16"))   # 31 * 15/30 = 15,5 → 16

    def test_mes_anterior_a_compra_nao_conta(self):
        self.produto()
        self.compra("1", date(2026, 6, 1), 10)
        self.mes("1", 2026, 5, 99)
        self.mes("1", 2026, 6, 2)
        self.assertEqual(self.movimento_de().vendido_desde_a_compra, Decimal("2"))

    def test_mes_que_a_foto_nao_tem_ninguem_soma(self):
        """A janela fecha no mês mais novo da foto, e não em "hoje"."""
        self.produto()
        self.compra("1", date(2026, 6, 1), 10)
        self.mes("1", 2026, 6, 4)
        self.assertEqual(self.movimento_de().vendido_desde_a_compra, Decimal("4"))

    def test_compra_depois_do_ultimo_mes_da_foto_nao_tem_venda_a_somar(self):
        self.produto()
        self.compra("1", date(2026, 9, 18), 10)
        self.mes("1", 2026, 6, 50)
        m = self.movimento_de()
        self.assertEqual(m.vendido_desde_a_compra, Decimal("0"))
        self.assertEqual(m.sobra_da_ultima_compra, Decimal("10"))


class ListaInteiraDeUmaVez(BaseMovimento):
    def test_duas_consultas_para_a_lista_toda(self):
        """Onze mil produtos vezes uma consulta cada é a tela que não abre."""
        for i in range(1, 16):
            self.produto(str(i), vendas_12m=Decimal("10"))
            self.compra(str(i), date(2026, 6, 1), 5, numero=f"c{i}")
            self.mes(str(i), 2026, 7, 3)
        with self.assertNumQueries(2):
            tabela = movimento.montar(self.importacao, self.importacao.itens.all())
        produtos = list(self.importacao.itens.all())
        with self.assertNumQueries(0):
            movimentos = [tabela.para(p) for p in produtos]
        self.assertEqual(len(movimentos), 15)
        self.assertTrue(all(m.ultima_compra_unidades == Decimal("5") for m in movimentos))

    def test_sem_importacao_nao_quebra_e_nao_consulta(self):
        with self.assertNumQueries(0):
            vazio = movimento.montar(None, None)
        self.produto()
        produto = ProdutoImportado.objects.get(codigo="1")
        self.assertFalse(vazio.para(produto).tem_ultima_compra)
