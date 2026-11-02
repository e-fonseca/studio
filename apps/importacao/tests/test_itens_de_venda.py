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


class PrecoDeTabelaEPagamentoTest(TestCase):
    """O que a 1.46.0 traz do SET para o controle de desconto (pedido de 02/11/2026)."""

    def test_o_preco_de_tabela_do_item_e_o_do_cadastro_quando_o_set_nao_gravou(self):
        from apps.importacao.fontes import firebird

        def linhas(sql, parametros):
            return [(10, "001", 1, 40.0, 20.0, 40.0, 50.0),   # o SET gravou a tabela
                    (10, "002", 2, 60.0, 10.0, 30.0, None)]   # não gravou: vale o cadastro
        produtos = {"001": {"descricao": "VASO", "preco_venda": Decimal("55")},
                    "002": {"descricao": "CESTO", "preco_venda": Decimal("35")}}
        itens = firebird._ler_itens_de_venda(linhas, CORTE, produtos)[10]
        self.assertEqual((itens[0]["preco_tabela"], itens[0]["preco_tabela_do_cadastro"]),
                         (Decimal("50.0"), False))
        self.assertEqual((itens[1]["preco_tabela"], itens[1]["preco_tabela_do_cadastro"]),
                         (Decimal("35"), True))
        self.assertEqual(itens[1]["preco_unitario"], Decimal("30.0"))

    def test_quem_recebeu_e_as_partes_do_pagamento(self):
        from apps.importacao.fontes import firebird

        def linhas(sql, parametros):
            texto = sql.lower()
            if "from icaixa" in texto:
                return [(10, "CAIXA TESTE "), (10, "OUTRA PESSOA TESTE")]
            if "from fatvendas" in texto:
                return [(10, "PIX", 50.0), (10, "CARTAO CREDITO", 43.0), (10, "PIX", 7.0)]
            return [(10, "10.12", CORTE, "15:00:00", 100.0, 7.0, "PIX", "", 107.0)]
        venda = firebird._ler_vendas(linhas, CORTE)[0]
        self.assertEqual(venda["recebido_por"], "CAIXA TESTE")  # o primeiro recebimento
        self.assertEqual(venda["formas_pagas"], {"PIX": "57.0", "CARTAO CREDITO": "43.0"})
        self.assertEqual(venda["total_produtos"], Decimal("107.0"))

    def test_a_consulta_nova_nao_le_campo_que_pode_ter_nome_de_cliente(self):
        """ICAIXA.CLIFORNE e FATVENDAS.OBSERVACAO podem ter nome de cliente: não são lidos."""
        import inspect
        import re

        from apps.importacao.fontes import firebird

        codigo = inspect.getsource(firebird._ler_vendas)
        selects = " ".join(re.findall(r"select\b.*?from\b.*?(?=\"\"\")", codigo,
                                      re.IGNORECASE | re.DOTALL)).upper()
        self.assertIn("FROM ICAIXA", selects)
        self.assertIn("FROM FATVENDAS", selects)
        for proibida in ("CLIFORNE", "OBSERVACAO", "NOMECLI", "COMPRADOR"):
            self.assertNotIn(proibida, selects)


class PrecoDoCadastroPassaAdianteTest(TestCase):
    """O preço do cadastro fica o da primeira importação que viu a venda.

    Senão o aumento de preço da semana seguinte faria a venda da semana passada parecer
    vendida com desconto (na cópia de 20/09/2026: 235 "cortes" em junho onde houve 73).
    """

    def _importacao(self):
        return Importacao.objects.create(
            origem=Importacao.Origem.BANCO, situacao=Importacao.Situacao.CONCLUIDA,
            iniciada_em=timezone.now(), concluida_em=timezone.now(), data_corte=CORTE,
            dias_abertos_12m=300, produtos=1,
        )

    def _linha(self, tabela, do_cadastro=True):
        linha = _linha("001", valor="40")
        linha.update({"preco_unitario": Decimal("40"), "preco_tabela": Decimal(tabela),
                      "preco_tabela_do_cadastro": do_cadastro})
        return linha

    def test_o_preco_da_importacao_anterior_vale_na_seguinte(self):
        servicos._gravar_vendas(self._importacao(), [_venda(10, "10", [self._linha("50")])])
        nova = self._importacao()
        servicos._gravar_vendas(nova, [_venda(10, "10", [self._linha("60")])])
        item = ItemVendaImportada.objects.get(venda__importacao=nova)
        self.assertEqual(item.preco_tabela, Decimal("50"))

    def test_preco_gravado_pelo_set_nao_e_trocado(self):
        servicos._gravar_vendas(self._importacao(), [_venda(10, "10", [self._linha("50")])])
        nova = self._importacao()
        servicos._gravar_vendas(nova, [_venda(10, "10", [self._linha("60", do_cadastro=False)])])
        self.assertEqual(ItemVendaImportada.objects.get(venda__importacao=nova).preco_tabela,
                         Decimal("60"))

    def test_venda_nova_fica_com_o_cadastro_de_agora(self):
        servicos._gravar_vendas(self._importacao(), [_venda(10, "10", [self._linha("50")])])
        nova = self._importacao()
        servicos._gravar_vendas(nova, [_venda(11, "11", [self._linha("60")])])
        self.assertEqual(ItemVendaImportada.objects.get(venda__importacao=nova).preco_tabela,
                         Decimal("60"))
