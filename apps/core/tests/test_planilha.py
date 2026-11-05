"""A planilha do relatório: o mesmo conteúdo do papel, com número de verdade na célula.

Pedido do Edson em 19/10/2026: *"FINANCEIRO, permitir exportar além do pdf para planilha
de excel ajustado no mesmo layout"*.

O arquivo é lido aqui com `zipfile` e `xml.etree`, da biblioteca padrão, e não com uma
biblioteca de planilha: ler com a mesma ferramenta que escreveu provaria só que ela
concorda consigo mesma, e nenhuma biblioteca de planilha entra no pacote da loja.
"""

import zipfile
from datetime import date
from decimal import Decimal
from io import BytesIO
from xml.etree import ElementTree

from django.test import TestCase

from apps.core import celula, pdf, planilha

ESPACO = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def abrir(folha):
    """Devolve (células por referência, a árvore da aba, o zip) de uma planilha pronta."""
    arquivo = zipfile.ZipFile(BytesIO(folha.bytes()))
    aba = ElementTree.fromstring(arquivo.read("xl/worksheets/sheet1.xml"))
    celulas = {}
    for c in aba.iter(f"{ESPACO}c"):
        valor = c.find(f"{ESPACO}v")
        texto = c.find(f"{ESPACO}is/{ESPACO}t")
        celulas[c.get("r")] = {
            "numero": valor.text if valor is not None else None,
            "texto": texto.text if texto is not None else None,
            "estilo": int(c.get("s") or 0),
        }
    return celulas, aba, arquivo


def formato_de(arquivo, estilo):
    """O formato de número que aquele estilo aplica, lido do styles.xml."""
    estilos = ElementTree.fromstring(arquivo.read("xl/styles.xml"))
    xf = list(estilos.find(f"{ESPACO}cellXfs"))[estilo]
    identificador = xf.get("numFmtId")
    if identificador == "0":
        return ""
    for numfmt in estilos.iter(f"{ESPACO}numFmt"):
        if numfmt.get("numFmtId") == identificador:
            return numfmt.get("formatCode")
    return ""


def uma_planilha():
    folha = planilha.Planilha("Contas a pagar", "Vencidas · 2 contas", emitido_por="Edson")
    folha.destaques([("Vencidas", celula.Dinheiro(Decimal("1234.56")))])
    folha.tabela(
        [pdf.Coluna("Vencimento", 52), pdf.Coluna("Atraso", 38, direita=True),
         pdf.Coluna("Fornecedor", 167), pdf.Coluna("Valor", 73, direita=True)],
        [
            [celula.Data(date(2026, 9, 1)),
             (celula.Inteiro(48, sufixo="d"), pdf.VERMELHO),
             "VIME LENZI & CIA", (celula.Dinheiro(Decimal("-1000")), pdf.VERMELHO)],
            [celula.Data(None), "", "STARBELLA", celula.Dinheiro(Decimal("234.56"))],
        ],
        principal=True,
    )
    folha.total("Total desta lista", celula.Dinheiro(Decimal("-765.44")))
    return folha


class OArquivoEhUmaPlanilhaDeVerdade(TestCase):
    def test_tem_as_pecas_que_o_excel_exige(self):
        _, _, arquivo = abrir(uma_planilha())
        for peca in ("[Content_Types].xml", "_rels/.rels", "xl/workbook.xml",
                     "xl/_rels/workbook.xml.rels", "xl/styles.xml",
                     "xl/worksheets/sheet1.xml"):
            self.assertIn(peca, arquivo.namelist(), f"falta {peca}")

    def test_o_zip_nao_esta_corrompido(self):
        _, _, arquivo = abrir(uma_planilha())
        self.assertIsNone(arquivo.testzip())

    def test_planilha_vazia_continua_abrindo(self):
        """cellXfs vazio faz o Excel recusar o arquivo inteiro, sem dizer por quê."""
        _, _, arquivo = abrir(planilha.Planilha("Nada aqui"))
        estilos = ElementTree.fromstring(arquivo.read("xl/styles.xml"))
        self.assertGreaterEqual(int(estilos.find(f"{ESPACO}cellXfs").get("count")), 1)


class ONumeroEhNumero(TestCase):
    """O ponto inteiro de ser planilha: a coluna soma, ordena e filtra."""

    def setUp(self):
        self.celulas, self.aba, self.arquivo = abrir(uma_planilha())

    def test_dinheiro_vai_como_numero_e_nao_como_texto(self):
        valor = self.celulas["D9"]
        self.assertEqual(valor["numero"], "-1000")
        self.assertIsNone(valor["texto"], "saiu como texto: a coluna não somaria")
        self.assertIn("R$", formato_de(self.arquivo, valor["estilo"]))

    def test_data_vai_como_data_e_ordena(self):
        """Número de série do Excel: 1/9/2026 são 46266 dias desde 30/12/1899."""
        vencimento = self.celulas["A9"]
        self.assertEqual(vencimento["numero"], str((date(2026, 9, 1)
                                                    - date(1899, 12, 30)).days))
        self.assertEqual(formato_de(self.arquivo, vencimento["estilo"]), "dd/mm/yyyy")

    def test_sem_data_continua_escrito_por_extenso(self):
        self.assertEqual(self.celulas["A10"]["texto"], "sem data")

    def test_o_atraso_vermelho_continua_sendo_numero(self):
        """Foi o defeito desta versão: a cor ganhava do formato e o número virava texto.

        No papel a coluna diz "48d" e cabe em 38 pontos; na planilha precisa ser 48,
        senão não dá para ordenar do mais vencido para o menos — que é a primeira coisa
        que alguém faz com uma lista de contas vencidas.
        """
        atraso = self.celulas["B9"]
        self.assertEqual(atraso["numero"], "48")
        self.assertEqual(formato_de(self.arquivo, atraso["estilo"]), "#,##0")

    def test_a_cor_e_o_formato_convivem_na_mesma_celula(self):
        """A conta vermelha continua vermelha E continua somando."""
        vermelha = self.celulas["D9"]
        estilos = ElementTree.fromstring(self.arquivo.read("xl/styles.xml"))
        xf = list(estilos.find(f"{ESPACO}cellXfs"))[vermelha["estilo"]]
        fonte = list(estilos.find(f"{ESPACO}fonts"))[int(xf.get("fontId"))]
        self.assertEqual(fonte.find(f"{ESPACO}color").get("rgb"), "FFB32919")
        self.assertIn("R$", formato_de(self.arquivo, vermelha["estilo"]))

    def test_o_total_tambem_e_numero(self):
        """A linha de soma fecha a tabela: rótulo na primeira coluna, valor na última."""
        self.assertEqual(self.celulas["A11"]["texto"], "Total desta lista")
        self.assertEqual(self.celulas["D11"]["numero"], "-765.44")


class AFolhaSeLeComoATabelaDoPapel(TestCase):
    def setUp(self):
        self.celulas, self.aba, self.arquivo = abrir(uma_planilha())

    def test_o_cabecalho_da_tabela_fica_congelado(self):
        painel = self.aba.find(f"{ESPACO}sheetViews/{ESPACO}sheetView/{ESPACO}pane")
        self.assertIsNotNone(painel, "sem congelar, a linha 400 não diz de que coluna é")
        self.assertEqual(painel.get("state"), "frozen")

    def test_a_tabela_principal_ganha_filtro(self):
        filtro = self.aba.find(f"{ESPACO}autoFilter")
        self.assertIsNotNone(filtro)
        self.assertEqual(filtro.get("ref"), "A8:D10")

    def test_a_largura_da_coluna_sai_da_medida_do_papel(self):
        """Coluna larga no PDF é coluna larga aqui: é o que faz as duas terem a mesma cara."""
        colunas = {c.get("min"): float(c.get("width"))
                   for c in self.aba.iter(f"{ESPACO}col")}
        self.assertLess(colunas["2"], colunas["3"], "Atraso ficou mais larga que Fornecedor")

    def test_o_cabecalho_traz_quem_emitiu_e_quando(self):
        """No papel isso está no rodapé de toda folha; aqui não há folha."""
        self.assertIn("Edson", self.celulas["A1"]["texto"])
        self.assertIn("Studio Industrial", self.celulas["A1"]["texto"])

    def test_o_titulo_e_o_subtitulo_abrem_a_folha(self):
        self.assertEqual(self.celulas["A2"]["texto"], "Contas a pagar")
        self.assertEqual(self.celulas["A3"]["texto"], "Vencidas · 2 contas")


class OTextoNaoQuebraOArquivo(TestCase):
    def test_e_comercial_e_sinal_de_menor_saem_escapados(self):
        """"VIME LENZI & CIA" sem escapar deixa o arquivo ilegível, e o Excel só diz
        que o arquivo está corrompido."""
        celulas, _, _ = abrir(uma_planilha())
        self.assertEqual(celulas["C9"]["texto"], "VIME LENZI & CIA")

    def test_texto_com_marcacao_vira_texto_e_nao_etiqueta(self):
        folha = planilha.Planilha("x")
        folha.paragrafo("<b>não</b> & <i>sim</i>")
        celulas, _, _ = abrir(folha)
        escrito = [c["texto"] for c in celulas.values() if c["texto"]]
        self.assertIn("<b>não</b> & <i>sim</i>", escrito)
