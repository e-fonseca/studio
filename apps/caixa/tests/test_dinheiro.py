"""O dinheiro vivo do caixa: o que deveria estar na gaveta.

O que estes testes protegem: a gaveta não pode somar PIX nem cartão, e forma de
pagamento que o sistema não conhece não pode entrar calada na conta.
"""

from datetime import date, datetime, timezone as tz
from decimal import Decimal

from django.test import TestCase

from apps.caixa import dinheiro, servicos
from apps.caixa.models import CaixaImportado
from apps.importacao.models import Importacao


def _caixa(importacao, **campos):
    padrao = dict(
        id_set=1, operador="BARBARA", dia=date(2026, 9, 20),
        aberto_em=datetime(2026, 9, 20, 8, 0, tzinfo=tz.utc),
        fechado_em=datetime(2026, 9, 20, 18, 0, tzinfo=tz.utc),
        situacao=CaixaImportado.Situacao.FECHADO,
        saldo_inicial=Decimal("200.00"), saldo_final=Decimal("0"),
        recebido=Decimal("0"), entradas=Decimal("0"),
        sangrias=Decimal("0"), pagamentos=Decimal("0"), por_forma={},
    )
    padrao.update(campos)
    return CaixaImportado.objects.create(importacao=importacao, **padrao)


class ClassificarForma(TestCase):
    def test_avista_e_dinheiro(self):
        """É assim que o SET da Cabana chama o dinheiro."""
        self.assertEqual(dinheiro.classificar("AVISTA"), "dinheiro")
        self.assertEqual(dinheiro.classificar("A VISTA"), "dinheiro")
        self.assertEqual(dinheiro.classificar("Dinheiro"), "dinheiro")

    def test_acento_e_espaco_nao_atrapalham(self):
        self.assertEqual(dinheiro.classificar(" espécie "), "dinheiro")
        self.assertEqual(dinheiro.classificar("EM ESPÉCIE"), "dinheiro")

    def test_pix_e_cartao_nao_sao_dinheiro(self):
        for nome in ("PIX", "CARTAO DEBITO", "CARTAO CREDITO", "Cheque", "PRAZO"):
            with self.subTest(nome=nome):
                self.assertEqual(dinheiro.classificar(nome), "outra")

    def test_nome_composto_cai_pelo_comeco(self):
        self.assertEqual(dinheiro.classificar("CARTAO MASTER 2X"), "outra")
        self.assertEqual(dinheiro.classificar("PIX LOJA"), "outra")

    def test_forma_nova_fica_desconhecida_e_nao_vira_dinheiro(self):
        """Chutar que uma forma nova é dinheiro faria a gaveta faltar sem explicação."""
        self.assertEqual(dinheiro.classificar("VOUCHER REFEICAO"), "desconhecida")
        self.assertEqual(dinheiro.classificar(""), "desconhecida")

    def test_nome_da_forma_e_o_da_loja(self):
        """O e-mail do caixa e o Dashboard escrevem a forma do mesmo jeito (1.41.0)."""
        self.assertEqual(dinheiro.nome_da_forma("AVISTA"), "Dinheiro")
        self.assertEqual(dinheiro.nome_da_forma("dinheiro"), "Dinheiro")
        self.assertEqual(dinheiro.nome_da_forma("CARTAO CREDITO"), "Cartão de crédito")
        self.assertEqual(dinheiro.nome_da_forma("Cartão Débito"), "Cartão de débito")
        self.assertEqual(dinheiro.nome_da_forma("PIX"), "PIX")
        self.assertEqual(dinheiro.nome_da_forma("PRAZO"), "A prazo")
        # Forma que a loja não conhece sai com o nome do SET, sem chute.
        self.assertEqual(dinheiro.nome_da_forma("VOUCHER REFEICAO"), "VOUCHER REFEICAO")
        self.assertEqual(dinheiro.nome_da_forma(""), "sem forma gravada")


class GavetaDoTurno(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.importacao = Importacao.objects.create(
            situacao=Importacao.Situacao.CONCLUIDA, data_corte=date(2026, 9, 20))

    def test_so_o_dinheiro_entra_na_gaveta(self):
        caixa = _caixa(self.importacao, por_forma={
            "AVISTA": "300.00", "PIX": "500.00", "CARTAO DEBITO": "1000.00"})
        g = dinheiro.do_turno(caixa)
        self.assertEqual(g.recebido, Decimal("300.00"))
        self.assertEqual(g.outras_formas, Decimal("1500.00"))
        # 200 de abertura + 300 recebidos em papel
        self.assertEqual(g.saldo, Decimal("500.00"))

    def test_a_conta_da_gaveta(self):
        caixa = _caixa(
            self.importacao, saldo_inicial=Decimal("100.00"),
            entradas=Decimal("50.00"), sangrias=Decimal("80.00"),
            pagamentos=Decimal("30.00"),
            por_forma={"AVISTA": "400.00", "PIX": "900.00"})
        g = dinheiro.do_turno(caixa)
        self.assertEqual(g.entrou, Decimal("450.00"))   # 400 de venda + 50 de entrada
        self.assertEqual(g.saiu, Decimal("110.00"))     # 80 de sangria + 30 de pagamento
        self.assertEqual(g.saldo, Decimal("440.00"))    # 100 + 450 − 110

    def test_saldo_negativo_aparece_em_vez_de_virar_zero(self):
        """Saiu mais do que entrou é erro de lançamento, e a tela tem que mostrar."""
        caixa = _caixa(self.importacao, saldo_inicial=Decimal("10.00"),
                       sangrias=Decimal("500.00"))
        self.assertEqual(dinheiro.do_turno(caixa).saldo, Decimal("-490.00"))

    def test_forma_desconhecida_fica_de_fora_e_avisa(self):
        caixa = _caixa(self.importacao, por_forma={
            "AVISTA": "100.00", "VOUCHER": "70.00"})
        g = dinheiro.do_turno(caixa)
        self.assertEqual(g.recebido, Decimal("100.00"))
        self.assertEqual(g.nao_classificado, Decimal("70.00"))
        self.assertEqual(g.formas_desconhecidas, ["VOUCHER"])
        self.assertTrue(g.tem_duvida)
        # 200 de abertura + 100 em papel: o voucher NÃO entrou.
        self.assertEqual(g.saldo, Decimal("300.00"))

    def test_fatia_em_dinheiro(self):
        caixa = _caixa(self.importacao, por_forma={"AVISTA": "250.00", "PIX": "750.00"})
        self.assertEqual(dinheiro.do_turno(caixa).fatia_em_dinheiro, Decimal("25.0"))

    def test_turno_sem_recebimento_nao_divide_por_zero(self):
        self.assertEqual(dinheiro.do_turno(_caixa(self.importacao)).fatia_em_dinheiro, Decimal("0"))


class GavetaDoPeriodo(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.importacao = Importacao.objects.create(
            situacao=Importacao.Situacao.CONCLUIDA, data_corte=date(2026, 9, 20))

    def test_soma_o_que_entrou_e_o_que_saiu(self):
        _caixa(self.importacao, id_set=1, por_forma={"AVISTA": "100.00"},
               sangrias=Decimal("40.00"))
        _caixa(self.importacao, id_set=2, por_forma={"AVISTA": "200.00", "PIX": "90.00"})
        g = dinheiro.do_periodo(CaixaImportado.objects.filter(importacao=self.importacao))
        self.assertEqual(g.turnos, 2)
        self.assertEqual(g.recebido, Decimal("300.00"))
        self.assertEqual(g.outras_formas, Decimal("90.00"))
        self.assertEqual(g.saiu, Decimal("40.00"))
        self.assertEqual(g.sobrou, Decimal("260.00"))     # 300 que entraram − 40 que saíram

    def test_o_periodo_nao_soma_saldo_de_abertura(self):
        """Somar a abertura de cada turno contaria o mesmo dinheiro muitas vezes.

        Nesta loja a abertura nem sequer é o fecho do turno anterior: no backup de
        20/09/2026 isso falha em 642 dos 949 turnos.
        """
        _caixa(self.importacao, id_set=1, saldo_inicial=Decimal("500.00"))
        _caixa(self.importacao, id_set=2, saldo_inicial=Decimal("500.00"))
        g = dinheiro.do_periodo(CaixaImportado.objects.filter(importacao=self.importacao))
        self.assertFalse(hasattr(g, "inicio"), "o período não pode ter saldo de abertura somado")
        self.assertEqual(g.entrou, Decimal("0"))

    def test_o_periodo_traz_a_gaveta_do_turno_mais_recente(self):
        _caixa(self.importacao, id_set=1, dia=date(2026, 9, 19),
               aberto_em=datetime(2026, 9, 19, 8, 0, tzinfo=tz.utc),
               por_forma={"AVISTA": "1000.00"})
        _caixa(self.importacao, id_set=2, dia=date(2026, 9, 20),
               aberto_em=datetime(2026, 9, 20, 8, 0, tzinfo=tz.utc),
               saldo_inicial=Decimal("50.00"), por_forma={"AVISTA": "30.00"})
        g = dinheiro.do_periodo(CaixaImportado.objects.filter(importacao=self.importacao))
        self.assertEqual(g.ultimo_turno.id_set, 2)
        self.assertEqual(g.ultima.saldo, Decimal("80.00"))   # 50 de abertura + 30 em papel

    def test_a_tela_traz_o_dinheiro_do_periodo(self):
        _caixa(self.importacao, por_forma={"AVISTA": "100.00", "CARTAO CREDITO": "900.00"})
        tela = servicos.montar(self.importacao, periodo="tudo")
        self.assertEqual(tela.gaveta.recebido, Decimal("100.00"))
        self.assertEqual(tela.gaveta.ultima.saldo, Decimal("300.00"))
        # O resumo antigo continua somando TUDO: são perguntas diferentes.
        self.assertEqual(tela.gaveta.outras_formas, Decimal("900.00"))
        self.assertEqual(tela.resumo.recebido, Decimal("0"))

    def test_sem_importacao_o_dinheiro_vem_zerado_sem_quebrar(self):
        tela = servicos.montar(None)
        self.assertEqual(tela.gaveta.entrou, Decimal("0"))
        self.assertEqual(tela.gaveta.ultima.saldo, Decimal("0"))
        self.assertFalse(tela.gaveta.tem_duvida)
