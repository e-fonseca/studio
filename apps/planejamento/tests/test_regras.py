"""As regras do protótipo da Henriett, uma por uma (06/11/2026).

Os números do protótipo foram conferidos contra o painel original com os 60 pedidos de
05/11/2026 (caixa em 30 dias de −121.269,23, Rogério de 42.211,78 em 30/11, Breno de
14.938,33 em 15/11): bateram ao centavo. Aqui ficam casos inventados, sem dado de cliente.
"""

import json
import os
import tempfile
from datetime import date
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase

from apps.planejamento import regras
from apps.planejamento.models import (Avulso, Cartao, CustoFixo, Divida, MovimentoEntreEmpresas,
                                      Parametros)
from apps.projetos.models import Oficina, Projeto

HOJE = date(2026, 11, 5)


def contexto(hoje=HOJE):
    return regras.Contexto.carregar(hoje)


def pedido(**extra):
    dados = {"numero": "1", "cliente_nome": "Cliente", "etapa": "producao",
             "valor_venda": Decimal("10000"), "custo_oficina": Decimal("5000")}
    dados.update(extra)
    return Projeto.objects.create(**dados)


class CartoesTest(TestCase):
    def setUp(self):
        self.xp = Cartao.objects.create(nome="XP", vencimento=1, fecha_dias_antes=8)
        self.bradesco = Cartao.objects.create(nome="Bradesco", vencimento=10, fecha_dias_antes=6)
        self.itau = Cartao.objects.create(nome="Itaú", vencimento=20, fecha_dias_antes=9)

    def test_compra_antes_do_fechamento_cai_na_fatura_do_mes(self):
        # XP vence dia 1 e fecha 8 dias antes: a fatura de 01/11 fecha em 24/10.
        self.assertEqual(regras.primeira_fatura(date(2026, 10, 15), self.xp), date(2026, 11, 1))
        self.assertEqual(regras.primeira_fatura(date(2026, 10, 24), self.xp), date(2026, 11, 1))

    def test_compra_depois_do_fechamento_cai_na_seguinte(self):
        self.assertEqual(regras.primeira_fatura(date(2026, 10, 25), self.xp), date(2026, 12, 1))

    def test_bradesco_de_06_10_cai_em_10_11(self):
        """O caso conferido na fatura real: MP*DOUGLAS em 06/10, fatura do Bradesco de 10/11."""
        self.assertEqual(regras.primeira_fatura(date(2026, 10, 6), self.bradesco), date(2026, 11, 10))

    def test_itau_fecha_nove_dias_antes(self):
        self.assertEqual(regras.primeira_fatura(date(2026, 11, 11), self.itau), date(2026, 11, 20))
        self.assertEqual(regras.primeira_fatura(date(2026, 11, 12), self.itau), date(2026, 12, 20))

    def test_parcelas_no_cartao_fecham_o_total(self):
        parcelas = regras.parcelas_no_cartao(date(2026, 10, 15), self.xp, 3, Decimal("1000"))
        self.assertEqual([p[0] for p in parcelas], [date(2026, 11, 1), date(2026, 12, 1), date(2027, 1, 1)])
        self.assertEqual([p[1] for p in parcelas], [Decimal("333.33"), Decimal("333.33"), Decimal("333.34")])
        self.assertEqual(sum(p[1] for p in parcelas), Decimal("1000"))


class DatasTest(TestCase):
    def test_mes_curto_paga_no_ultimo_dia(self):
        self.assertEqual(regras.data_no_mes(2027, 1, 30), date(2027, 2, 28))
        self.assertEqual(regras.data_no_mes(2028, 1, 30), date(2028, 2, 29))

    def test_mes_passa_do_ano(self):
        self.assertEqual(regras.data_no_mes(2026, 13, 15), date(2027, 2, 15))
        self.assertEqual(regras.data_no_mes(2026, -1, 15), date(2025, 12, 15))

    def test_dividir_fecha_o_total(self):
        self.assertEqual(regras.dividir(Decimal("10"), 3), [Decimal("3.33"), Decimal("3.33"), Decimal("3.34")])
        self.assertEqual(sum(regras.dividir(Decimal("42211.78") * 3, 3)), Decimal("126635.34"))


class OficinaMensalTest(TestCase):
    def setUp(self):
        self.rogerio = Oficina.objects.create(nome="Rogério", pagamento="mensal", parcelas_mensais=3,
                                              dia_pagamento=30, dia_corte=25)
        self.breno = Oficina.objects.create(nome="Breno", pagamento="mensal", parcelas_mensais=3,
                                            dia_pagamento=15, dia_corte=10)

    def datas(self, oficina, repasse):
        p = pedido(oficina=oficina, repasse=repasse, custo_oficina=Decimal("9000"))
        return [(s.data, s.valor) for s in regras.agenda_oficina(p, contexto()).saidas]

    def test_rogerio_repassado_ate_o_dia_25_entra_no_mes(self):
        self.assertEqual(self.datas(self.rogerio, date(2026, 10, 25)), [
            (date(2026, 10, 30), Decimal("3000")), (date(2026, 11, 30), Decimal("3000")),
            (date(2026, 12, 30), Decimal("3000"))])

    def test_rogerio_depois_do_corte_vai_para_o_mes_seguinte_e_fevereiro_e_dia_28(self):
        self.assertEqual([d for d, _ in self.datas(self.rogerio, date(2026, 11, 26))],
                         [date(2026, 12, 30), date(2027, 1, 30), date(2027, 2, 28)])

    def test_breno_corte_no_dia_10(self):
        self.assertEqual([d for d, _ in self.datas(self.breno, date(2026, 11, 10))][0], date(2026, 11, 15))
        self.assertEqual([d for d, _ in self.datas(self.breno, date(2026, 11, 11))][0], date(2026, 12, 15))

    def test_sem_repasse_conta_como_hoje_e_fica_previsto(self):
        p = pedido(oficina=self.rogerio)
        saidas = regras.agenda_oficina(p, contexto()).saidas
        self.assertEqual(saidas[0].data, date(2026, 11, 30))
        self.assertTrue(all(s.previsto for s in saidas))


class PadraoTest(TestCase):
    def setUp(self):
        self.xp = Cartao.objects.create(nome="XP", vencimento=1, fecha_dias_antes=8)
        p = Parametros.atual()
        p.cartao_padrao = self.xp
        p.save()

    def test_metade_no_cartao_em_duas_e_metade_em_pix_na_entrega(self):
        p = pedido(pg1_data=date(2026, 10, 15), pg1_cartao=self.xp, pg1_parcelas=2,
                   prazo_entrega=date(2026, 11, 20))
        saidas = regras.agenda_oficina(p, contexto()).saidas
        self.assertEqual([(s.data, s.valor, s.tipo) for s in saidas], [
            (date(2026, 11, 1), Decimal("1250.00"), "cartao"),
            (date(2026, 12, 1), Decimal("1250.00"), "cartao"),
            (date(2026, 11, 20), Decimal("2500.00"), "pix")])

    def test_primeira_parcela_com_outro_percentual(self):
        p = pedido(pg1_data=date(2026, 10, 15), primeira_percentual=Decimal("30"), pg1_parcelas=1,
                   prazo_entrega=date(2026, 11, 20))
        saidas = regras.agenda_oficina(p, contexto()).saidas
        self.assertEqual([s.valor for s in saidas], [Decimal("1500.00"), Decimal("3500.00")])

    def test_sem_data_de_entrega_vai_para_sem_data(self):
        agenda = regras.agenda_oficina(pedido(pg1_data=date(2026, 10, 15)), contexto())
        self.assertEqual(len(agenda.sem_data), 1)
        self.assertEqual(agenda.sem_data[0].valor, Decimal("2500.00"))

    def test_prazo_vencido_cobra_hoje(self):
        p = pedido(pg1_data=date(2026, 10, 15), prazo_entrega=date(2026, 10, 1))
        self.assertEqual(regras.agenda_oficina(p, contexto()).saidas[-1].data, HOJE)

    def test_entregue_sem_data_cobra_hoje(self):
        """No protótipo esta 2ª parcela sumia das contas; aqui ela é devida agora."""
        p = pedido(etapa="entregue", pg1_data=date(2026, 10, 15))
        self.assertEqual(regras.agenda_oficina(p, contexto()).saidas[-1].data, HOJE)

    def test_segunda_paga_fica_na_data_paga(self):
        p = pedido(pg1_data=date(2026, 9, 1), pg2_data=date(2026, 10, 7), etapa="entregue")
        self.assertEqual(regras.agenda_oficina(p, contexto()).saidas[-1].descricao, "2ª parcela paga")

    def test_fora_das_contas_orcamento_e_cancelado_nao_pagam(self):
        for extra in ({"incluir": False}, {"etapa": "orcamento"}, {"etapa": "cancelado"}, {"custo_oficina": 0}):
            agenda = regras.agenda_oficina(pedido(**extra), contexto())
            self.assertEqual((agenda.saidas, agenda.sem_data), ([], []), extra)

    def test_tudo_no_cartao(self):
        p = pedido(regime="cartao", pg1_data=date(2026, 10, 15), pg1_parcelas=4)
        saidas = regras.agenda_oficina(p, contexto()).saidas
        self.assertEqual(len(saidas), 4)
        self.assertEqual(sum(s.valor for s in saidas), Decimal("5000"))


class ClienteEMargemTest(TestCase):
    def test_saldo_em_pix_e_venda_menos_recebido(self):
        c = regras.saldo_cliente(pedido(recebido=Decimal("4000"), saldo_forma="pix",
                                        prazo_entrega=date(2026, 11, 20)), contexto())
        self.assertEqual((c.saldo, c.data, c.vencido), (Decimal("6000"), date(2026, 11, 20), False))

    def test_cartao_e_quitado_nao_esperam_nada(self):
        for forma in ("cartao", "quitado"):
            self.assertEqual(regras.saldo_cliente(pedido(saldo_forma=forma), contexto()).saldo, 0)

    def test_saldo_pix_informado_vale_mais_que_a_conta(self):
        c = regras.saldo_cliente(pedido(recebido=Decimal("1000"), saldo_pix=Decimal("2650")), contexto())
        self.assertEqual(c.saldo, Decimal("2650"))
        self.assertTrue(c.a_confirmar)

    def test_entregue_com_saldo_esta_vencido(self):
        c = regras.saldo_cliente(pedido(etapa="entregue", recebido=Decimal("9000"), saldo_forma="pix"), contexto())
        self.assertTrue(c.vencido)

    def test_margem_de_lucro_com_taxa_estimada(self):
        # 10.000 de venda, 5.000 de oficina, 50% no cartão a 15%: 750 de taxa.
        m = regras.margem(pedido(), contexto())
        self.assertEqual((m.taxa, m.lucro, m.percentual, m.estimada),
                         (Decimal("750.00"), Decimal("4250.00"), Decimal("42.5"), True))

    def test_margem_com_o_que_entrou_no_cartao(self):
        m = regras.margem(pedido(venda_cartao=Decimal("2000"), frete=Decimal("250")), contexto())
        self.assertEqual((m.taxa, m.lucro, m.estimada), (Decimal("300.00"), Decimal("4450.00"), False))

    def test_card_incompleto(self):
        falta = regras.faltando(pedido(valor_venda=0))
        self.assertIn("valor de venda", falta)
        self.assertIn("oficina", falta)
        self.assertIn("data prevista de entrega", falta)
        self.assertIn("pagamento da 1ª parcela (data e cartão)", falta)
        self.assertEqual(regras.faltando(pedido(incluir=False)), [])


class CaixaTest(TestCase):
    def setUp(self):
        Cartao.objects.create(nome="XP", vencimento=1, fecha_dias_antes=8)
        p = Parametros.atual()
        p.saldo_inicial = Decimal("1000")
        p.save()

    def test_projecao_soma_entradas_e_saidas_dia_a_dia(self):
        CustoFixo.objects.create(nome="Aluguel", valor=Decimal("4500"), dia=10)
        Divida.objects.create(nome="Conta garantida", saldo=Decimal("10000"), taxa_mensal=Decimal("7"), dia=22)
        Avulso.objects.create(nome="Saldo Rogério", valor=Decimal("2000"), data=date(2026, 11, 15))
        Avulso.objects.create(nome="Já pago", valor=Decimal("9999"), data=date(2026, 11, 16), pago=True)
        pedido(recebido=Decimal("5000"), saldo_forma="pix", prazo_entrega=date(2026, 11, 8),
               pg1_data=date(2026, 9, 1))
        lista = regras.pedidos()
        proj = regras.projecao(lista, contexto(), 30)
        # entra 5.000 (cliente) e sai 2.500 (2ª da oficina) em 08/11; aluguel 4.500 em 10/11;
        # 2.000 em 15/11; juros de 700 em 22/11. O aluguel de 10/12 fica fora: a janela vai até 05/12.
        self.assertEqual(proj.entradas, Decimal("5000"))
        self.assertEqual(proj.saidas, Decimal("2500") + Decimal("4500") + Decimal("2000") + Decimal("700"))
        self.assertEqual(proj.final, Decimal("1000") + Decimal("5000") - proj.saidas)
        self.assertEqual(proj.minimo, Decimal("-3700"))
        self.assertEqual(proj.dia_minimo, date(2026, 11, 22))
        avisos = regras.alertas(lista, contexto(), proj)
        self.assertEqual(avisos[0].tipo, "Caixa negativo nos próximos 30 dias")

    def test_alertas_de_atraso_e_depois_da_entrega(self):
        pedido(numero="A", prazo_entrega=date(2026, 10, 20))  # 16 dias, passa dos 10
        pedido(numero="B", prazo_entrega=date(2026, 10, 30))  # 6 dias, ainda não
        pedido(numero="C", etapa="entregue", saldo_forma="pix", recebido=Decimal("5000"),
               pg1_data=date(2026, 9, 1))
        tipos = {(a.tipo, a.projeto.numero) for a in regras.alertas(regras.pedidos(), contexto()) if a.projeto}
        self.assertIn(("Pedido atrasado", "A"), tipos)
        self.assertNotIn(("Pedido atrasado", "B"), tipos)
        self.assertIn(("Cliente com saldo depois da entrega", "C"), tipos)
        self.assertIn(("Oficina a pagar depois da entrega", "C"), tipos)

    def test_fechamento_competencia_e_caixa(self):
        CustoFixo.objects.create(nome="Folha", valor=Decimal("14800"), dia=5)
        pedido(data_venda=date(2026, 11, 3), venda_cartao=Decimal("0"), saldo_forma="pix",
               prazo_entrega=date(2026, 11, 25), pg1_data=date(2026, 11, 3))
        pedido(numero="2", data_venda=date(2026, 10, 3))
        MovimentoEntreEmpresas.objects.create(data=date(2026, 11, 10), tipo="prolabore", empresa="studio",
                                              valor=Decimal("1200"))
        f = regras.fechar(2026, 11, regras.pedidos(), contexto())
        self.assertEqual((f.competencia.pedidos, f.competencia.vendas, f.competencia.margem),
                         (1, Decimal("10000"), Decimal("5000")))
        self.assertEqual(f.competencia.resultado, Decimal("5000") - Decimal("14800"))
        # Só o pedido com data de entrega: o outro está em produção sem data.
        self.assertEqual(f.caixa.entradas, Decimal("10000"))
        self.assertEqual(f.caixa.prolabore, Decimal("1200"))
        self.assertEqual(f.caixa.fixos, Decimal("14800"))


class EntreEmpresasTest(TestCase):
    def test_saldo_acumulado_e_cancelado_fora(self):
        MovimentoEntreEmpresas.objects.create(data=date(2026, 10, 1), tipo="cartao", sentido="cabana_deve",
                                              valor=Decimal("10322.11"))
        MovimentoEntreEmpresas.objects.create(data=date(2026, 11, 2), tipo="transferencia",
                                              sentido="studio_deve", valor=Decimal("2000"))
        errado = MovimentoEntreEmpresas.objects.create(data=date(2026, 11, 3), tipo="transferencia",
                                                       sentido="studio_deve", valor=Decimal("999"))
        errado.cancelado_em = errado.criado_em
        errado.save()
        MovimentoEntreEmpresas.objects.create(data=date(2026, 10, 20), tipo="prolabore", empresa="studio",
                                              valor=Decimal("11995.23"))
        meses, saldo, prolabore = regras.entre_empresas()
        self.assertEqual(saldo, Decimal("8322.11"))
        self.assertEqual([m.rotulo for m in meses], ["nov/2026", "out/2026"])
        self.assertEqual(meses[1].acumulado, Decimal("10322.11"))
        self.assertEqual(prolabore["studio"], Decimal("11995.23"))


class ImportarPrototipoTest(TestCase):
    DADOS = {
        "pedidos": {
            "100": {"p": "100", "cliente": "Cliente A", "oficina": "Rogério", "regime": "Rogério",
                    "custo": 9000, "repasse": "2026-10-25", "status": "producao", "incluir": True,
                    "venda": 15000, "recebido": 7500, "saldoForma": "Pix"},
            "101": {"p": "101", "cliente": "Cliente B", "oficina": "Douglas", "regime": "Padrão",
                    "custo": 4000, "pg1Data": "2026-10-06", "pg1Cartao": "Bradesco", "pg1Parcelas": 2,
                    "entregaPrevista": "2026-11-18", "status": "projeto", "incluir": True, "pct1": 0.5},
            "estoque": {"p": "Armário estoque", "cliente": "Estoque", "oficina": "?", "regime": "Cartão",
                        "custo": 500, "status": "entregue", "incluir": False},
        },
        "interco": {"2026-10-01-xp": "2026-10-01",
                    "ok": {"data": "2026-10-09", "tipo": "transferencia", "sentido": "cabana_deve",
                           "valor": 500, "descricao": "Pix"}},
        "config": {"geral": {
            "margemMin": 0.25, "atrasoDias": 10, "taxaAntecip": 0.15, "pctCartao": 0.5, "pct1": 0.5,
            "parcelasPadrao": 2, "cartaoPadrao": "XP", "saldoInicial": -5363.36,
            "cartoes": [{"nome": "XP", "venc": 1, "fecha": 8}, {"nome": "Bradesco", "venc": 10, "fecha": 6}],
            "rogerio": {"corte": 25, "dia": 30}, "breno": {"corte": 10, "dia": 15},
            "fixos": [{"nome": "Aluguel", "valor": 4500, "dia": 10},
                      {"nome": "Capital de giro Itaú (parcela 14/48)", "valor": 733.99, "dia": 2}],
            "dividas": [{"nome": "Conta garantida", "saldo": 55358, "taxa": 0.07, "dia": 22}],
            "avulsos": [{"nome": "Saldo Rogério", "valor": 20504.21, "data": "2026-11-15"}],
        }},
    }

    def importar(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(self.DADOS, f)
        try:
            call_command("importar_prototipo", f.name, stdout=open(os.devnull, "w"))
        finally:
            os.unlink(f.name)

    def test_importa_e_roda_de_novo_sem_duplicar(self):
        self.importar()
        self.importar()
        self.assertEqual(Projeto.objects.count(), 3)
        self.assertEqual(Cartao.objects.count(), 2)
        self.assertEqual(CustoFixo.objects.count(), 2)
        self.assertEqual(MovimentoEntreEmpresas.objects.count(), 1, "o movimento só com data não entra")
        rogerio = Oficina.objects.get(nome="Rogério")
        self.assertEqual((rogerio.pagamento, rogerio.dia_pagamento, rogerio.dia_corte), ("mensal", 30, 25))
        self.assertEqual(CustoFixo.objects.get(nome__startswith="Capital").tipo, "emprestimo")
        p = Parametros.atual()
        self.assertEqual((p.margem_minima, p.saldo_inicial, p.cartao_padrao.nome),
                         (Decimal("25.00"), Decimal("-5363.36"), "XP"))
        self.assertEqual(Divida.objects.get().taxa_mensal, Decimal("7.000"))

    def test_pedidos_entram_com_as_regras_certas(self):
        self.importar()
        a = Projeto.objects.get(numero="100")
        self.assertEqual((a.regime, a.etapa, a.saldo_forma), ("mensal", "producao", "pix"))
        saidas = regras.agenda_oficina(a, contexto()).saidas
        self.assertEqual([s.data for s in saidas], [date(2026, 10, 30), date(2026, 11, 30), date(2026, 12, 30)])
        b = Projeto.objects.get(numero="101")
        self.assertEqual((b.etapa, b.pg1_cartao.nome, b.primeira_percentual), ("aprovado", "Bradesco", Decimal("50.00")))
        self.assertEqual(regras.agenda_oficina(b, contexto()).saidas[0].data, date(2026, 11, 10))
        estoque = Projeto.objects.get(numero="Armário estoque")
        self.assertEqual((estoque.titulo, estoque.incluir, estoque.oficina), ("Armário estoque", False, None))
