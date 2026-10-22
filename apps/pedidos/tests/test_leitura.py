"""Ler o documento que o fornecedor mandou: o XML da nota e o romaneio em planilha."""

from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from apps.pedidos import leitura

NOTA = """<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe>
    <infNFe Id="NFe35261012345678000190550010000012341234567890" versao="4.00">
      <ide>
        <cUF>35</cUF><nNF>1234</nNF><serie>1</serie>
        <dhEmi>2026-10-10T09:15:00-03:00</dhEmi>
      </ide>
      <emit>
        <CNPJ>12.345.678/0001-90</CNPJ>
        <xNome>VIME LENZI INDUSTRIA LTDA</xNome>
      </emit>
      <det nItem="1">
        <prod>
          <cProd>VL-100</cProd>
          <cEAN>7891234567895</cEAN>
          <xProd>CADEIRA DE VIME NATURAL</xProd>
          <qCom>10.0000</qCom>
          <vUnCom>85.0000</vUnCom>
          <vProd>850.00</vProd>
        </prod>
      </det>
      <det nItem="2">
        <prod>
          <cProd>VL-200</cProd>
          <cEAN>SEM GTIN</cEAN>
          <xProd>MESA DE VIME</xProd>
          <qCom>2.0000</qCom>
          <vUnCom>240.0000</vUnCom>
          <vProd>480.00</vProd>
        </prod>
      </det>
      <total><ICMSTot><vNF>1330.00</vNF></ICMSTot></total>
    </infNFe>
  </NFe>
</nfeProc>
"""


class LerNotaFiscalTest(SimpleTestCase):
    def test_le_o_cabecalho_e_cada_item(self):
        documento = leitura.ler("nota.xml", NOTA.encode("utf-8"))
        self.assertEqual(documento.formato, "nfe")
        self.assertEqual(documento.numero, "1234")
        self.assertEqual(documento.emitente, "VIME LENZI INDUSTRIA LTDA")
        self.assertEqual(documento.emitente_documento, "12345678000190")
        self.assertEqual(documento.emitido_em.isoformat(), "2026-10-10")
        self.assertEqual(documento.valor, Decimal("1330.00"))
        self.assertEqual(len(documento.itens), 2)
        primeiro = documento.itens[0]
        self.assertEqual(primeiro.codigo, "VL-100")
        self.assertEqual(primeiro.codigo_barras, "7891234567895")
        self.assertEqual(primeiro.quantidade, Decimal("10.0000"))
        self.assertEqual(primeiro.unitario, Decimal("85.0000"))
        self.assertEqual(primeiro.total, Decimal("850.00"))

    def test_sem_gtin_nao_vira_codigo_de_barras(self):
        """"SEM GTIN" é o que o emissor escreve quando não há código; casaria item errado."""
        documento = leitura.ler("nota.xml", NOTA.encode("utf-8"))
        self.assertEqual(documento.itens[1].codigo_barras, "")

    def test_le_a_nota_solta_sem_o_protocolo_em_volta(self):
        solta = NOTA.replace("<nfeProc xmlns=\"http://www.portalfiscal.inf.br/nfe\" versao=\"4.00\">", "")
        solta = solta.replace("</nfeProc>", "")
        solta = solta.replace("<NFe>", "<NFe xmlns=\"http://www.portalfiscal.inf.br/nfe\">")
        documento = leitura.ler("nota.xml", solta.encode("utf-8"))
        self.assertEqual(documento.formato, "nfe")
        self.assertEqual(len(documento.itens), 2)

    def test_xml_com_doctype_e_recusado_antes_de_abrir(self):
        """É por aí que entra a bomba de entidades que come a memória do servidor."""
        bomba = ('<?xml version="1.0"?><!DOCTYPE nfe [<!ENTITY a "aaaaaaaaaa">]>'
                 '<nfeProc><infNFe><ide><nNF>1</nNF></ide></infNFe></nfeProc>')
        documento = leitura.ler("nota.xml", bomba.encode("utf-8"))
        self.assertEqual(documento.itens, [])
        self.assertIn("DOCTYPE", documento.aviso)

    def test_xml_que_nao_e_nota_diz_o_que_faltou(self):
        documento = leitura.ler("coisa.xml", b"<?xml version='1.0'?><algo><outro>1</outro></algo>")
        self.assertEqual(documento.itens, [])
        self.assertIn("infNFe", documento.aviso)

    def test_xml_quebrado_nao_derruba_a_tela(self):
        documento = leitura.ler("nota.xml", b"<?xml version='1.0'?><nfeProc><infNFe>")
        self.assertIn("Não consegui abrir o XML", documento.aviso)

    def test_nota_sem_item_dentro_avisa(self):
        vazia = ('<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"><NFe><infNFe>'
                 '<ide><nNF>9</nNF></ide></infNFe></NFe></nfeProc>')
        documento = leitura.ler("nota.xml", vazia.encode("utf-8"))
        self.assertEqual(documento.itens, [])
        self.assertIn("não achei item nenhum", documento.aviso)


class LerRomaneioTest(SimpleTestCase):
    def test_le_o_csv_com_codigo_quantidade_e_valor(self):
        csv = ("Codigo;Descricao;Quantidade;Valor unitario;Valor total\n"
               "0001;CADEIRA DE VIME;10;85,00;850,00\n"
               "0002;MESA DE VIME;2;240,00;480,00\n")
        documento = leitura.ler("romaneio.csv", csv.encode("cp1252"))
        self.assertEqual(documento.formato, "csv")
        self.assertEqual(len(documento.itens), 2)
        self.assertEqual(documento.itens[0].codigo, "0001")
        self.assertEqual(documento.itens[0].quantidade, Decimal("10"))
        self.assertEqual(documento.itens[0].unitario, Decimal("85.00"))
        self.assertEqual(documento.valor, Decimal("1330.00"))

    def test_pula_as_linhas_de_apresentacao_antes_do_cabecalho(self):
        csv = ("ROMANEIO DE ENTREGA\nFornecedor: VIME LENZI\n\n"
               "Produto;Qtde\nCADEIRA DE VIME;10\n")
        documento = leitura.ler("romaneio.csv", csv.encode("utf-8"))
        self.assertEqual(len(documento.itens), 1)
        self.assertEqual(documento.itens[0].descricao, "CADEIRA DE VIME")

    def test_linha_sem_quantidade_nao_entra(self):
        csv = "Codigo;Quantidade\n0001;10\n0002;\n;5\n"
        documento = leitura.ler("romaneio.csv", csv.encode("utf-8"))
        self.assertEqual([item.codigo for item in documento.itens], ["0001"])

    def test_sem_as_colunas_necessarias_explica_em_vez_de_mostrar_meia_lista(self):
        documento = leitura.ler("romaneio.csv", b"alguma coisa;outra\n1;2\n")
        self.assertEqual(documento.itens, [])
        self.assertIn("colunas do romaneio", documento.aviso)

    def test_arquivo_vazio(self):
        self.assertIn("vazio", leitura.ler("romaneio.csv", b"   ").aviso)


class LerPdfEImagemTest(SimpleTestCase):
    def test_pdf_fica_guardado_e_diz_por_que_nao_foi_lido(self):
        documento = leitura.ler("nota.pdf", b"%PDF-1.7\n1 0 obj\n")
        self.assertEqual(documento.formato, "pdf")
        self.assertEqual(documento.itens, [])
        self.assertIn("XML", documento.aviso)

    def test_pdf_com_extensao_trocada_continua_sendo_pdf(self):
        """Confiar na extensão daria "não consegui abrir o XML" sem explicação."""
        documento = leitura.ler("nota.xml", b"%PDF-1.7\n")
        self.assertEqual(documento.formato, "pdf")

    def test_imagem_fica_guardada(self):
        documento = leitura.ler("romaneio.jpg", b"\xff\xd8\xff\xe0abc")
        self.assertEqual(documento.formato, "imagem")
        self.assertIn("nada daqui sai", documento.aviso)


class ValidarTest(SimpleTestCase):
    def enviar(self, nome, dados):
        return SimpleUploadedFile(nome, dados)

    def test_aceita_os_tipos_da_tela(self):
        for nome, dados in (("nota.xml", b"<nfe/>"), ("nota.pdf", b"%PDF-1.7"),
                            ("foto.jpg", b"\xff\xd8\xff"), ("romaneio.csv", b"a;b")):
            _, _, erro = leitura.validar(self.enviar(nome, dados), 10 * 1024 * 1024)
            self.assertEqual(erro, "", nome)

    def test_recusa_tipo_que_nao_e_documento(self):
        _, _, erro = leitura.validar(self.enviar("coisa.exe", b"MZ"), 10 * 1024 * 1024)
        self.assertIn("não aceito", erro)

    def test_recusa_arquivo_grande_dizendo_o_limite(self):
        _, _, erro = leitura.validar(self.enviar("nota.pdf", b"%PDF-" + b"x" * 200), 100)
        self.assertIn("limite", erro)

    def test_recusa_conteudo_que_nao_corresponde_a_extensao(self):
        _, _, erro = leitura.validar(self.enviar("nota.pdf", b"nao sou pdf"), 10 * 1024 * 1024)
        self.assertIn("não corresponde", erro)

    def test_recusa_arquivo_vazio(self):
        _, _, erro = leitura.validar(self.enviar("nota.xml", b""), 10 * 1024 * 1024)
        self.assertIn("vazio", erro)

    def test_nome_com_caminho_dentro_fica_so_com_o_nome(self):
        nome, extensao, erro = leitura.validar(
            self.enviar("..\\..\\windows\\nota.xml", b"<nfe/>"), 10 * 1024 * 1024)
        self.assertEqual(nome, "nota.xml")
        self.assertEqual(extensao, "xml")
        self.assertEqual(erro, "")
