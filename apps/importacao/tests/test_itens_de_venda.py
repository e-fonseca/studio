"""O item da venda: o produto que saiu, por quanto, e quanto custava no dia.

Importado desde a 1.24.0, para a relação de vendas do dia (pedido do Edson em
11/10/2026). O que estes testes protegem é a ligação: o item tem que ficar pendurado
na venda certa, e o custo tem que ficar vazio quando o SET não gravou — não zerado.
"""

from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.importacao import servicos
from apps.importacao.models import Importacao, ItemVendaImportada, VendaImportada

CORTE = date(2026, 9, 20)


def _venda(id_set, numero, linhas):
    return {
        "id_set": id_set, "numero": numero, "data": CORTE, "hora": "10:00",
        "dia_da_semana": (CORTE.weekday() + 1) % 7, "valor": Decimal("100"),
        "desconto": Decimal("0"), "forma_pagamento": "PIX", "vendedor": "",
        "linhas": linhas,
    }


def _linha(codigo, valor="100", custo="40", quantidade="1"):
    custo_unitario = None if custo is None else Decimal(custo)
    quantidade = Decimal(quantidade)
    return {
        "codigo": codigo, "descricao": f"PRODUTO {codigo}", "grupo": "VIME",
        "quantidade": quantidade, "valor_total": Decimal(valor),
        "custo_unitario": custo_unitario,
        "custo_total": None if custo_unitario is None else custo_unitario * quantidade,
    }


class GravarVendasTest(TestCase):
    def setUp(self):
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO, situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(), data_corte=CORTE, dias_abertos_12m=300, produtos=2,
        )

    def test_cada_item_fica_na_sua_venda(self):
        servicos._gravar_vendas(self.importacao, [
            _venda(10, "10", [_linha("001"), _linha("002")]),
            _venda(11, "11", [_linha("003")]),
        ])
        dez = VendaImportada.objects.get(importacao=self.importacao, id_set=10)
        onze = VendaImportada.objects.get(importacao=self.importacao, id_set=11)
        self.assertEqual(sorted(dez.itens.values_list("codigo", flat=True)), ["001", "002"])
        self.assertEqual(list(onze.itens.values_list("codigo", flat=True)), ["003"])

    def test_venda_sem_item_nao_atrapalha_as_outras(self):
        """Venda sem item existe no SET: cupom de serviço, de troca, de ajuste."""
        servicos._gravar_vendas(self.importacao, [
            _venda(10, "10", []),
            _venda(11, "11", [_linha("003")]),
        ])
        self.assertEqual(ItemVendaImportada.objects.count(), 1)
        self.assertEqual(ItemVendaImportada.objects.get().venda.id_set, 11)

    def test_id_do_set_fora_de_ordem_nao_pendura_item_na_venda_errada(self):
        """O casamento é pela ORDEM da lista, e o SET não devolve venda ordenada."""
        servicos._gravar_vendas(self.importacao, [
            _venda(20, "20", [_linha("001")]),
            _venda(10, "10", [_linha("002")]),
            _venda(15, "15", [_linha("003")]),
        ])
        por_numero = {v.numero: list(v.itens.values_list("codigo", flat=True))
                      for v in VendaImportada.objects.filter(importacao=self.importacao)}
        self.assertEqual(por_numero, {"20": ["001"], "10": ["002"], "15": ["003"]})

    def test_custo_que_o_set_nao_gravou_fica_vazio_e_nao_zero(self):
        """Zero diria "custou nada", e o lucro do dia sairia inteiro em cima disso."""
        servicos._gravar_vendas(self.importacao, [
            _venda(10, "10", [_linha("001", custo=None)]),
        ])
        item = ItemVendaImportada.objects.get()
        self.assertIsNone(item.custo_unitario)
        self.assertIsNone(item.custo_total)
        self.assertFalse(item.tem_custo)
        self.assertIsNone(item.lucro)

    def test_o_lucro_do_item_e_valor_menos_custo(self):
        servicos._gravar_vendas(self.importacao, [
            _venda(10, "10", [_linha("001", valor="250", custo="40", quantidade="2")]),
        ])
        item = ItemVendaImportada.objects.get()
        self.assertEqual(item.custo_total, Decimal("80.00"))
        self.assertEqual(item.lucro, Decimal("170.00"))
