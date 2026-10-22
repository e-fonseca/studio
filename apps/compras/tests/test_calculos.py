from datetime import date
from decimal import Decimal as D

from django.test import SimpleTestCase

from apps.compras.calculos import Item, Parametros, Situacao, calcular, curva_abc, resumir


def item(**kw):
    base = dict(sku="A1", descricao="Cesto de palha", estoque_utilizavel=D("10"), vendas_liquidas=D("60"),
                dias_janela=30, prazo_reposicao_dias=14, custo_unitario=D("20.00"))
    base.update(kw)
    return Item(**base)


class FormulasTest(SimpleTestCase):
    def test_formulas_do_briefing(self):
        # demanda 2/dia; segurança 7 dias = 14; ponto = 2*14 + 14 = 42; alvo = 2*(14+7) + 14 = 56
        r = calcular(item())
        self.assertEqual(r.demanda_diaria, D("2"))
        self.assertEqual(r.ponto_reposicao, D("42.00"))
        self.assertEqual(r.estoque_alvo, D("56.00"))
        self.assertEqual(r.cobertura_texto, "5 dias")
        self.assertEqual(r.compra_sugerida, D("46"))  # 56 - 10
        self.assertEqual(r.custo_compra, D("920.00"))
        self.assertEqual(r.situacao, Situacao.COMPRAR)
        self.assertIn("ponto de reposição", r.motivo)

    def test_posicao_soma_pedidos_e_tira_reservas_uma_vez(self):
        r = calcular(item(recebimentos_pendentes=D("30"), reservas_nao_deduzidas=D("4")))
        self.assertEqual(r.posicao_estoque, D("36"))
        self.assertEqual(r.compra_sugerida, D("20"))

    def test_acima_do_ponto_nao_compra(self):
        r = calcular(item(estoque_utilizavel=D("50")))
        self.assertEqual(r.compra_sugerida, 0)
        self.assertEqual(r.situacao, Situacao.SAUDAVEL)

    def test_lote_minimo_e_multiplo(self):
        self.assertEqual(calcular(item(estoque_utilizavel=D("40"), lote_minimo=D("24"))).compra_sugerida, D("24"))
        self.assertEqual(calcular(item(multiplo=D("12"))).compra_sugerida, D("48"))

    def test_demanda_zero_sem_divisao(self):
        r = calcular(item(vendas_liquidas=D("0")))
        self.assertIsNone(r.cobertura_dias)
        self.assertEqual(r.cobertura_texto, "sem demanda suficiente")
        self.assertEqual(r.compra_sugerida, 0)
        self.assertEqual(r.situacao, Situacao.SEM_GIRO)
        self.assertEqual(r.valor_excesso, D("200.00"))

    def test_ruptura(self):
        r = calcular(item(estoque_utilizavel=D("0"), dias_em_ruptura=5))
        self.assertEqual(r.situacao, Situacao.RUPTURA)
        self.assertEqual(r.confianca, "média")
        self.assertTrue(any("demanda real pode ser maior" in a for a in r.avisos))

    def test_excesso_e_compra_acima_do_necessario(self):
        # 0,5/dia; limite de 180 dias = 90 un.; estoque 150 → 60 em excesso; comprou 80 → 60 sobrando
        r = calcular(item(vendas_liquidas=D("15"), estoque_utilizavel=D("150"), comprado_na_janela=D("80")))
        self.assertEqual(r.situacao, Situacao.EXCESSO)
        self.assertEqual(r.excesso_unidades, D("60.00"))
        self.assertEqual(r.valor_excesso, D("1200.00"))
        self.assertEqual(r.comprado_acima_do_necessario, D("60.00"))
        self.assertEqual(r.valor_comprado_acima, D("1200.00"))

    def test_sem_prazo_nao_sugere_compra(self):
        r = calcular(item(prazo_reposicao_dias=None))
        self.assertEqual(r.compra_sugerida, 0)
        self.assertTrue(any("Prazo de reposição não informado" in a for a in r.avisos))

    def test_sem_custo(self):
        r = calcular(item(custo_unitario=None))
        self.assertIsNone(r.custo_compra)
        self.assertEqual(r.compra_sugerida, D("46"))

    def test_dados_vencidos_reduzem_confianca(self):
        r = calcular(item(), data_corte=date(2026, 9, 1), hoje=date(2026, 10, 5))
        self.assertEqual(r.confianca, "média")
        self.assertTrue(any("desatualizados" in a for a in r.avisos))

    def test_reproduzivel(self):
        self.assertEqual(calcular(item()), calcular(item()))

    def test_minimo_manual_prevalece(self):
        r = calcular(item(estoque_utilizavel=D("50"), estoque_minimo_manual=D("80")))
        self.assertEqual(r.compra_sugerida, D("30"))

    def test_parametros(self):
        r = calcular(item(), Parametros(dias_seguranca=D("0"), horizonte_revisao_dias=0))
        self.assertEqual(r.estoque_alvo, D("28.00"))


class SaldoNegativoTest(SimpleTestCase):
    """Saldo abaixo de zero não é mercadoria a repor (mudou em 14/10/2026).

    No SET há 1.023 produtos com saldo negativo, porque a loja nunca fez contagem física:
    saíram unidades que nunca foram registradas entrando. Somar esse buraco à compra é
    comprar a mesma venda duas vezes, porque as vendas que o abriram já estão na demanda.
    Medido na foto de 20/09/2026: a lista inteira caía de R$ 184.577 para R$ 95.459.
    """

    def test_o_buraco_nao_entra_na_quantidade(self):
        # 2/dia, alvo 56. Com saldo -40, a conta antiga comprava 96; agora compra 56.
        r = calcular(item(estoque_utilizavel=D("-40")))
        self.assertEqual(r.estoque_alvo, D("56.00"))
        self.assertEqual(r.compra_sugerida, D("56"))
        self.assertEqual(r.posicao_estoque, D("0"))

    def test_a_tela_recebe_de_quanto_era_o_buraco(self):
        """Sem este número, TEM -40 e COMPRAR 56 na mesma linha não fecham."""
        r = calcular(item(estoque_utilizavel=D("-40")))
        self.assertEqual(r.saldo_negativo_desprezado, D("40"))
        self.assertTrue(any("conta o saldo como zero" in a for a in r.avisos))
        self.assertEqual(r.dados_usados["estoque_utilizavel"], "-40")
        self.assertEqual(r.dados_usados["estoque_contado_na_compra"], "0")

    def test_saldo_positivo_passa_intacto_e_sem_aviso(self):
        r = calcular(item())
        self.assertEqual(r.saldo_negativo_desprezado, D("0"))
        self.assertEqual(r.posicao_estoque, D("10"))
        self.assertFalse(any("conta o saldo como zero" in a for a in r.avisos))

    def test_o_que_ja_esta_a_caminho_continua_contando(self):
        """O pedido em aberto é mercadoria de verdade: ele desconta, o buraco não."""
        r = calcular(item(estoque_utilizavel=D("-40"), recebimentos_pendentes=D("20")))
        self.assertEqual(r.posicao_estoque, D("20"))
        self.assertEqual(r.compra_sugerida, D("36"))

    def test_o_produto_continua_em_falta(self):
        """Contar zero na compra não é dizer que tem: a situação segue sendo ruptura."""
        r = calcular(item(estoque_utilizavel=D("-40")))
        self.assertEqual(r.situacao, Situacao.RUPTURA)

    def test_produto_de_giro_lento_nao_vira_pedido_de_anos(self):
        """O caso real: PRATO MARAJOARA, 1 por ano, saldo -15, pedia 16 unidades.

        Dezesseis anos de venda numa compra só. É o erro que a loja já comete sozinha,
        e o sistema não pode ser quem o sugere.
        """
        r = calcular(item(vendas_liquidas=D("1"), dias_janela=356, estoque_utilizavel=D("-15"),
                          prazo_reposicao_dias=15))
        self.assertEqual(r.compra_sugerida, D("1"))

    def test_cobertura_e_valor_de_estoque_ja_tratavam_o_negativo(self):
        """As outras duas contas sempre usaram max(estoque, 0); a compra era a exceção."""
        r = calcular(item(estoque_utilizavel=D("-40")))
        self.assertEqual(r.cobertura_dias, D("0.00"))
        self.assertEqual(r.valor_estoque, D("0.00"))


class ResumoTest(SimpleTestCase):
    def test_totais(self):
        resultados = [
            calcular(item(sku="1")),  # comprar, estoque 10*20 = 200
            calcular(item(sku="2", vendas_liquidas=D("0"))),  # sem giro, 200 parado
            calcular(item(sku="3", vendas_liquidas=D("15"), estoque_utilizavel=D("150"), comprado_na_janela=D("80"))),
            calcular(item(sku="4", estoque_utilizavel=D("0"))),  # falta
            calcular(item(sku="5", custo_unitario=None)),
        ]
        r = resumir(resultados)
        self.assertEqual(r.valor_estoque, D("3400.00"))
        self.assertEqual(r.valor_sem_giro, D("200.00"))
        self.assertEqual(r.valor_excesso, D("1200.00"))
        self.assertEqual(r.valor_comprado_acima, D("1200.00"))
        self.assertEqual(r.itens_em_falta, 1)
        self.assertEqual(r.itens_para_comprar, 3)
        self.assertEqual(r.itens_sem_custo, 1)


class CurvaABCTest(SimpleTestCase):
    def test_classes(self):
        classes = curva_abc({"a": 700, "b": 150, "c": 100, "d": 50, "e": 0})
        self.assertEqual(classes, {"a": "A", "b": "A", "c": "B", "d": "C", "e": "C"})
