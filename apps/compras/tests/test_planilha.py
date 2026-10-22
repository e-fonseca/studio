import csv
import tempfile
from decimal import Decimal as D
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from openpyxl import Workbook

from apps.auditoria.models import EventoAuditoria
from apps.compras.planilha import ErroPlanilha, ler, numero

CSV_OK = (
    "Código;Descrição;Estoque atual;Custo unitário;Vendas qtd;Devoluções qtd;Comprado qtd;Prazo reposição dias\n"
    "A1;Cesto de palha;10;20,00;62;2;0;14\n"
    "B2;Vaso de barro;150;1.234,50;15;;80;30\n"
    "C3;=CMD|' /C calc'!A0;5;;0;;;\n"
)


class Base(TestCase):
    def setUp(self):
        self.pasta = Path(tempfile.mkdtemp())

    def arquivo(self, nome, conteudo):
        caminho = self.pasta / nome
        caminho.write_bytes(conteudo if isinstance(conteudo, bytes) else conteudo.encode("utf-8"))
        return caminho


class LeituraTest(Base):
    def test_numeros_brasileiros(self):
        self.assertEqual(numero("1.234,56"), D("1234.56"))
        self.assertEqual(numero("R$ 10,5"), D("10.5"))
        self.assertEqual(numero("12"), D("12"))
        self.assertIsNone(numero(""))
        with self.assertRaises(ValueError):
            numero("abc")
        with self.assertRaises(ValueError):
            numero("NaN")

    def test_le_csv_com_cabecalho_flexivel(self):
        itens, erros = ler(self.arquivo("p.csv", CSV_OK))
        self.assertEqual(erros, [])
        self.assertEqual([i.sku for i in itens], ["A1", "B2", "C3"])
        self.assertEqual(itens[0].vendas_liquidas, D("60"))
        self.assertEqual(itens[1].custo_unitario, D("1234.50"))
        self.assertIsNone(itens[2].custo_unitario)

    def test_le_cp1252(self):
        itens, _ = ler(self.arquivo("p.csv", CSV_OK.encode("cp1252", errors="replace")))
        self.assertEqual(len(itens), 3)

    def test_linhas_invalidas_vao_para_erros(self):
        conteudo = "sku;descricao;estoque;vendas;prazo\nA;x;1;-2;10\nA2;x;1;2;10\nA2;y;1;2;10\n;z;1;1;1\nB;w;abc;1;1\n"
        itens, erros = ler(self.arquivo("p.csv", conteudo))
        self.assertEqual([i.sku for i in itens], ["A2"])
        mensagens = " ".join(m for _, m in erros)
        for trecho in ["vendas negativas", "SKU repetido", "SKU vazio", "não é um número"]:
            self.assertIn(trecho, mensagens)

    def test_estoque_negativo_vira_zero_com_aviso(self):
        itens, erros = ler(self.arquivo("p.csv", "sku;descricao;estoque;vendas\nA;x;-3;5\n"))
        self.assertEqual(itens[0].estoque_utilizavel, 0)
        self.assertTrue(erros[0][1].startswith("aviso:"))

    def test_coluna_obrigatoria_faltando(self):
        with self.assertRaisesMessage(ErroPlanilha, "vendas_qtd"):
            ler(self.arquivo("p.csv", "sku;descricao;estoque\nA;x;1\n"))

    def test_xlsx_le_valores_e_nao_formulas(self):
        livro = Workbook()
        aba = livro.active
        aba.append(["SKU", "Descrição", "Estoque", "Vendas", "Custo"])
        aba.append(["A1", "Cesto", 10, 60, 20.5])
        aba.append(["A2", "Fórmula", "=1+1", 1, None])
        caminho = self.pasta / "p.xlsx"
        livro.save(caminho)
        itens, erros = ler(caminho)
        self.assertEqual(itens[0].custo_unitario, D("20.5"))
        self.assertEqual(len(itens), 1)  # a fórmula não é calculada: vira valor ausente
        self.assertIn("obrigatórios", erros[0][1])

    def test_recusa_extensao_e_conteudo_falso(self):
        with self.assertRaises(ErroPlanilha):
            ler(self.arquivo("p.exe", "x"))
        with self.assertRaises(ErroPlanilha):
            ler(self.arquivo("p.xlsx", "não é zip"))


class ComandoTest(Base):
    def test_gera_relatorio_e_resumo(self):
        entrada = self.arquivo("p.csv", CSV_OK)
        saida = self.pasta / "relatorio.csv"
        out = StringIO()
        call_command("diagnostico_compras", str(entrada), "--dias", "30", "--data-corte", "2026-10-04",
                     "--saida", str(saida), stdout=out, stderr=StringIO())
        texto = out.getvalue()
        self.assertIn("Itens analisados: 3 (1 sem custo informado", texto)
        self.assertIn("Comprado no período e ainda sobrando: R$ 74.070,00", texto)  # 60 un. × 1.234,50
        with open(saida, encoding="utf-8-sig") as f:
            linhas = list(csv.reader(f, delimiter=";"))
        self.assertEqual(linhas[0][0], "SKU")
        self.assertEqual(linhas[1][2], "Comprar")
        self.assertTrue(linhas[3][1].startswith("'="))  # injeção de fórmula neutralizada
        self.assertTrue(EventoAuditoria.objects.filter(acao="compras.diagnostico_gerado").exists())

    def test_recusa_parcial_sem_autorizacao(self):
        entrada = self.arquivo("p.csv", "sku;descricao;estoque;vendas\nA;x;1;abc\nB;y;1;1\n")
        with self.assertRaisesMessage(CommandError, "1 linha(s) recusada(s)"):
            call_command("diagnostico_compras", str(entrada), "--dias", "30", "--data-corte", "2026-10-04",
                         "--saida", str(self.pasta / "r.csv"), stdout=StringIO(), stderr=StringIO())
        out = StringIO()
        call_command("diagnostico_compras", str(entrada), "--dias", "30", "--data-corte", "2026-10-04",
                     "--saida", str(self.pasta / "r.csv"), "--aceitar-com-erros", stdout=out, stderr=StringIO())
        self.assertIn("relatório parcial", out.getvalue())
