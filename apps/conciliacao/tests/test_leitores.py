"""Ler o arquivo que o banco entrega, do jeito que ele vem.

O que estes testes protegem: o OFX dos bancos é SGML velho (etiqueta que não fecha), o
CSV muda de banco para banco, e o número vem no padrão brasileiro. Errar a leitura aqui
é inventar movimento bancário, que é o pior erro possível neste módulo.
"""

from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from apps.conciliacao import leitores

OFX = """OFXHEADER:100
DATA:OFXSGML
<OFX><SIGNONMSGSRSV1><SONRS><FI><ORG>Banco do Brasil<FID>1</FI></SONRS></SIGNONMSGSRSV1>
<BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKACCTFROM><BANKID>001<BRANCHID>3062<ACCTID>12345-6</BANKACCTFROM>
<BANKTRANLIST>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260915120000[-3:BRT]<TRNAMT>-1362.00<FITID>A1<CHECKNUM>000314<MEMO>PIX QUITERIA FLOR MILHO</STMTTRN>
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20260916<TRNAMT>5000.00<FITID>A2<MEMO>CREDITO CIELO</STMTTRN>
</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>
"""


class LerOfx(SimpleTestCase):
    def test_le_o_sgml_com_etiqueta_que_nao_fecha(self):
        leitura = leitores.ler("extrato.ofx", OFX)
        self.assertEqual(leitura.formato, "ofx")
        self.assertEqual(len(leitura.movimentos), 2)
        saida = leitura.movimentos[0]
        self.assertEqual(saida.data, date(2026, 9, 15))
        self.assertEqual(saida.valor, Decimal("-1362.00"))
        self.assertEqual(saida.descricao, "PIX QUITERIA FLOR MILHO")
        self.assertEqual(saida.documento, "000314")
        self.assertEqual(saida.identificador, "A1")

    def test_traz_o_banco_a_conta_e_o_periodo(self):
        leitura = leitores.ler("extrato.ofx", OFX)
        self.assertEqual(leitura.banco, "Banco do Brasil")
        self.assertEqual(leitura.conta, "3062 / 12345-6")
        self.assertEqual(leitura.inicio, date(2026, 9, 15))
        self.assertEqual(leitura.fim, date(2026, 9, 16))

    def test_le_tambem_em_cp1252_que_e_o_que_os_bancos_mandam(self):
        bruto = OFX.replace("CREDITO CIELO", "CRÉDITO CIELO").encode("cp1252")
        leitura = leitores.ler("extrato.ofx", bruto)
        self.assertEqual(leitura.movimentos[1].descricao, "CRÉDITO CIELO")

    def test_movimento_sem_data_e_descartado_e_contado(self):
        quebrado = OFX.replace("<DTPOSTED>20260916", "<DTPOSTED>")
        leitura = leitores.ler("extrato.ofx", quebrado)
        self.assertEqual(len(leitura.movimentos), 1)
        self.assertEqual(leitura.descartadas, 1)

    def test_ofx_de_cartao_avisa_em_vez_de_dar_lista_vazia(self):
        leitura = leitores.ler("fatura.ofx", "<OFX><CREDITCARDMSGSRSV1></CREDITCARDMSGSRSV1></OFX>")
        self.assertIn("cartão", leitura.erro)
        self.assertFalse(leitura.deu_certo)


class LerCsv(SimpleTestCase):
    def test_ponto_e_virgula_acento_e_numero_brasileiro(self):
        texto = ("Data;Histórico;Valor;Documento\n"
                 "15/09/2026;PIX QUITERIA;-1.362,00;000314\n"
                 "16/09/2026;CREDITO CIELO;5.000,00;\n")
        leitura = leitores.ler("extrato.csv", texto.encode("cp1252"))
        self.assertEqual(leitura.formato, "csv")
        self.assertEqual(leitura.movimentos[0].valor, Decimal("-1362.00"))
        self.assertEqual(leitura.movimentos[0].descricao, "PIX QUITERIA")
        self.assertEqual(leitura.movimentos[1].valor, Decimal("5000.00"))

    def test_pula_as_linhas_de_apresentacao_antes_do_cabecalho(self):
        texto = ("Extrato da conta corrente\nPeríodo: 01/09/2026 a 30/09/2026\n\n"
                 "Data Lancamento,Descricao,Valor (R$)\n"
                 "2026-09-15,PAGTO FORNECEDOR,\"(1,362.00)\"\n")
        leitura = leitores.ler("extrato.csv", texto)
        self.assertEqual(len(leitura.movimentos), 1)
        # Parêntese é o jeito americano de escrever negativo.
        self.assertEqual(leitura.movimentos[0].valor, Decimal("-1362.00"))

    def test_sem_coluna_de_data_ou_de_valor_diz_o_que_fazer(self):
        leitura = leitores.ler("x.csv", "Nome;Telefone\nJoao;9999\n")
        self.assertIn("Data", leitura.erro)
        self.assertFalse(leitura.deu_certo)

    def test_linha_com_data_torta_e_descartada_e_nao_inventa_valor(self):
        texto = "Data;Valor\n15/09/2026;-10,00\nlixo;-20,00\n;\n"
        leitura = leitores.ler("x.csv", texto)
        self.assertEqual(len(leitura.movimentos), 1)
        self.assertEqual(leitura.descartadas, 2)


class LerQualquerCoisa(SimpleTestCase):
    def test_arquivo_vazio(self):
        self.assertIn("vazio", leitores.ler("x.ofx", b"").erro)

    def test_arquivo_que_nao_e_extrato(self):
        self.assertIn("OFX", leitores.ler("x.pdf", b"%PDF-1.4 qualquer coisa").erro)

    def test_a_impressao_digital_muda_com_o_conteudo_e_nao_com_o_nome(self):
        um = leitores.impressao_digital(b"abc")
        self.assertEqual(um, leitores.impressao_digital("abc"))
        self.assertNotEqual(um, leitores.impressao_digital(b"abcd"))


class Numeros(SimpleTestCase):
    def test_entende_os_jeitos_de_escrever_dinheiro(self):
        casos = {
            "1.234,56": Decimal("1234.56"), "1,234.56": Decimal("1234.56"),
            "-50,00": Decimal("-50.00"), "R$ 50,00": Decimal("50.00"),
            "(1.234,56)": Decimal("-1234.56"), "50,00-": Decimal("-50.00"),
            "1234.56": Decimal("1234.56"), "0": Decimal("0"),
        }
        for bruto, esperado in casos.items():
            with self.subTest(bruto=bruto):
                self.assertEqual(leitores._numero(bruto), esperado)

    def test_o_que_nao_e_numero_vira_nada_em_vez_de_zero(self):
        """Virar zero faria uma linha de extrato existir com valor errado."""
        for bruto in ("", "   ", "abc", "-", "R$"):
            with self.subTest(bruto=bruto):
                self.assertIsNone(leitores._numero(bruto))
