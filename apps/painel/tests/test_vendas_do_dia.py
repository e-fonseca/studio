"""A relação dos produtos vendidos no dia, com custo, lucro e margem.

O que estes testes protegem, em ordem de importância:

1. **Item sem custo não vira lucro cheio.** É o erro que daria margem de 100% num dia
   inteiro e faria a gerência decidir compra olhando um lucro que a loja não teve.
2. **O total do dia não muda quando a lista é cortada.** A tela mostra os maiores; o
   faturamento tem que continuar sendo o do dia.
3. **O custo é o do dia da venda**, e não o do cadastro de hoje.
"""

from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.contas.perfis import ADMINISTRACAO, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.importacao.models import Importacao, ItemVendaImportada, VendaImportada
from apps.painel import vendas_do_dia

CORTE = date(2026, 9, 20)
ONTEM = date(2026, 9, 19)


class BaseVendas(TestCase):
    def setUp(self):
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO,
            situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(),
            data_corte=CORTE,
            dias_abertos_12m=300,
            produtos=3,
        )
        self.proxima = 0

    def venda(self, dia=CORTE, valor="0", linhas=()):
        self.proxima += 1
        cabecalho = VendaImportada.objects.create(
            importacao=self.importacao, id_set=self.proxima, numero=str(self.proxima),
            data=dia, hora="10:00", dia_da_semana=(dia.weekday() + 1) % 7,
            valor=Decimal(valor), forma_pagamento="DINHEIRO",
        )
        for linha in linhas:
            self.item(cabecalho, **linha)
        return cabecalho

    def item(self, venda, codigo="001", descricao="VASO DE VIME", grupo="VIME",
             quantidade="1", valor="100", custo=None, cadastro=None):
        """`custo` é o que o SET gravou na venda; `cadastro`, o custo do cadastro."""
        quantidade = Decimal(quantidade)
        custo_unitario = None if custo is None else Decimal(custo)
        do_cadastro = None if cadastro is None else Decimal(cadastro)
        return ItemVendaImportada.objects.create(
            venda=venda, codigo=codigo, descricao=descricao, grupo=grupo,
            quantidade=quantidade, valor_total=Decimal(valor),
            custo_unitario=custo_unitario,
            custo_total=None if custo_unitario is None else custo_unitario * quantidade,
            custo_cadastro_unitario=do_cadastro,
            custo_estimado_total=None if do_cadastro is None else do_cadastro * quantidade,
        )


class TestConta(BaseVendas):
    def test_junta_o_mesmo_produto_vendido_em_cupons_diferentes(self):
        self.venda(linhas=[{"quantidade": "2", "valor": "200", "custo": "40"}])
        self.venda(linhas=[{"quantidade": "1", "valor": "100", "custo": "40"}])
        resultado = vendas_do_dia.calcular(self.importacao)
        self.assertEqual(len(resultado.linhas), 1)
        linha = resultado.linhas[0]
        self.assertEqual(linha.quantidade, Decimal("3.000"))
        self.assertEqual(linha.valor, Decimal("300.00"))
        self.assertEqual(linha.custo, Decimal("120.00"))
        self.assertEqual(linha.lucro, Decimal("180.00"))
        self.assertEqual(linha.margem, Decimal("60.0"))
        self.assertEqual(linha.vendas, 2)

    def test_os_numeros_do_dia_saem_dos_itens(self):
        self.venda(valor="300", linhas=[
            {"codigo": "001", "quantidade": "1", "valor": "200", "custo": "80"},
            {"codigo": "002", "descricao": "CESTO", "quantidade": "1", "valor": "100", "custo": "20"},
        ])
        resultado = vendas_do_dia.calcular(self.importacao)
        self.assertEqual(resultado.faturamento, Decimal("300.00"))
        self.assertEqual(resultado.custo, Decimal("100.00"))
        self.assertEqual(resultado.lucro, Decimal("200.00"))
        self.assertEqual(resultado.margem, Decimal("66.7"))
        self.assertEqual(resultado.cupons, 1)
        self.assertEqual(resultado.itens, 2)

    def test_dia_sem_venda_nao_quebra_a_tela(self):
        self.venda(dia=ONTEM, linhas=[{"valor": "100", "custo": "50"}])
        resultado = vendas_do_dia.calcular(self.importacao, dia=CORTE)
        self.assertFalse(resultado.tem_dados)
        self.assertEqual(resultado.faturamento, Decimal("0"))
        self.assertIsNone(resultado.margem)

    def test_sem_importacao_a_tela_nao_quebra(self):
        resultado = vendas_do_dia.calcular(None)
        self.assertFalse(resultado.tem_dados)
        self.assertEqual(resultado.dias, [])
        self.assertIsNone(resultado.dia)

    def test_sem_dia_pedido_mostra_o_ultimo_com_venda(self):
        """A importação pode ser de um dia em que a loja não abriu."""
        self.venda(dia=ONTEM, linhas=[{"valor": "100", "custo": "50"}])
        resultado = vendas_do_dia.calcular(self.importacao)
        self.assertEqual(resultado.dia, ONTEM)
        self.assertTrue(resultado.tem_dados)

    def test_so_oferece_dia_que_tem_venda(self):
        self.venda(dia=ONTEM, linhas=[{"valor": "100", "custo": "50"}])
        resultado = vendas_do_dia.calcular(self.importacao)
        self.assertEqual(resultado.dias, [ONTEM])

    def test_nao_mistura_o_dia_de_outra_importacao(self):
        """Cada importação é uma foto; somar duas dobraria o dia (docs/sincronizacao-nao-soma.md)."""
        self.venda(linhas=[{"valor": "100", "custo": "50"}])
        outra = Importacao.objects.create(
            origem=Importacao.Origem.BANCO, situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(), data_corte=CORTE, dias_abertos_12m=300, produtos=3)
        velha, self.importacao = self.importacao, outra
        self.venda(linhas=[{"valor": "100", "custo": "50"}])
        self.assertEqual(vendas_do_dia.calcular(velha).faturamento, Decimal("100.00"))
        self.assertEqual(vendas_do_dia.calcular(outra).faturamento, Decimal("100.00"))


class TestSemCusto(BaseVendas):
    """1.608 dos 32.034 itens de 12 meses saíram do SET sem custo gravado."""

    def test_item_sem_custo_fica_fora_da_conta_do_lucro(self):
        self.venda(linhas=[
            {"codigo": "001", "valor": "100", "custo": "60"},
            {"codigo": "002", "descricao": "SEM CUSTO", "valor": "100", "custo": None},
        ])
        resultado = vendas_do_dia.calcular(self.importacao)
        self.assertEqual(resultado.faturamento, Decimal("200.00"))
        self.assertEqual(resultado.valor_com_custo, Decimal("100.00"))
        self.assertEqual(resultado.valor_sem_custo, Decimal("100.00"))
        self.assertEqual(resultado.lucro, Decimal("40.00"))
        # 40 sobre 100, e não 140 sobre 200: o item sem custo não entra como lucro cheio.
        self.assertEqual(resultado.margem, Decimal("40.0"))
        self.assertEqual(resultado.produtos_sem_custo, 1)
        self.assertFalse(resultado.tudo_tem_custo)

    def test_a_linha_sem_custo_aparece_marcada_e_sem_lucro(self):
        self.venda(linhas=[{"codigo": "002", "valor": "100", "custo": None}])
        linha = vendas_do_dia.calcular(self.importacao).linhas[0]
        self.assertTrue(linha.sem_custo)
        self.assertIsNone(linha.lucro)
        self.assertIsNone(linha.margem)
        self.assertIsNone(linha.custo_unitario_medio)
        self.assertFalse(linha.prejuizo)

    def test_produto_com_parte_das_unidades_sem_custo_e_marcado(self):
        """O mesmo produto pode sair duas vezes no dia, uma com custo e outra sem."""
        self.venda(linhas=[{"quantidade": "1", "valor": "100", "custo": "50"}])
        self.venda(linhas=[{"quantidade": "1", "valor": "100", "custo": None}])
        linha = vendas_do_dia.calcular(self.importacao).linhas[0]
        self.assertTrue(linha.custo_parcial)
        self.assertFalse(linha.sem_custo)
        self.assertEqual(linha.valor, Decimal("200.00"))
        self.assertEqual(linha.lucro, Decimal("50.00"))
        self.assertEqual(linha.margem, Decimal("50.0"))

    def test_dia_inteiro_sem_custo_nao_divide_por_zero(self):
        self.venda(linhas=[{"valor": "100", "custo": None}])
        resultado = vendas_do_dia.calcular(self.importacao)
        self.assertIsNone(resultado.margem)
        self.assertEqual(resultado.lucro, Decimal("0"))


class TestPrejuizo(BaseVendas):
    def test_vendido_abaixo_do_custo_aparece_como_prejuizo(self):
        self.venda(linhas=[{"valor": "30", "custo": "50"}])
        linha = vendas_do_dia.calcular(self.importacao).linhas[0]
        self.assertTrue(linha.prejuizo)
        self.assertEqual(linha.lucro, Decimal("-20.00"))
        self.assertEqual(linha.margem, Decimal("-66.7"))


class TestOrdemELimite(BaseVendas):
    def test_do_que_mais_vendeu_para_o_que_menos_vendeu(self):
        self.venda(linhas=[
            {"codigo": "001", "descricao": "MENOR", "valor": "10", "custo": "5"},
            {"codigo": "002", "descricao": "MAIOR", "valor": "500", "custo": "5"},
        ])
        linhas = vendas_do_dia.calcular(self.importacao).linhas
        self.assertEqual([l.descricao for l in linhas], ["MAIOR", "MENOR"])

    def test_cortar_a_lista_nao_muda_o_total_do_dia(self):
        self.venda(linhas=[
            {"codigo": str(n), "descricao": f"PRODUTO {n}", "valor": "100", "custo": "50"}
            for n in range(5)
        ])
        resultado = vendas_do_dia.calcular(self.importacao, limite=2)
        self.assertEqual(len(resultado.linhas), 2)
        self.assertTrue(resultado.cortou_linhas)
        self.assertEqual(resultado.faturamento, Decimal("500.00"))
        self.assertEqual(resultado.lucro, Decimal("250.00"))


class TestDescontoNoFechamento(BaseVendas):
    def test_a_diferenca_entre_o_cupom_e_os_itens_e_mostrada(self):
        """O desconto dado no fechamento não está em item nenhum, e a tela diz isso."""
        self.venda(valor="90", linhas=[{"valor": "100", "custo": "50"}])
        resultado = vendas_do_dia.calcular(self.importacao)
        self.assertEqual(resultado.faturamento, Decimal("100.00"))
        self.assertEqual(resultado.total_dos_cupons, Decimal("90.00"))
        self.assertEqual(resultado.desconto_no_fechamento, Decimal("10.00"))

    def test_sem_diferenca_nao_ha_o_que_explicar(self):
        self.venda(valor="100", linhas=[{"valor": "100", "custo": "50"}])
        self.assertEqual(vendas_do_dia.calcular(self.importacao).desconto_no_fechamento, Decimal("0"))


class TestArquivo(BaseVendas):
    def test_o_csv_leva_virgula_decimal_e_diz_quem_nao_tem_custo(self):
        self.venda(linhas=[
            {"codigo": "001", "quantidade": "3", "valor": "1500.5", "custo": "100"},
            {"codigo": "002", "descricao": "SEM CUSTO", "valor": "10", "custo": None},
        ])
        cabecalho, corpo = vendas_do_dia.linhas_do_csv(vendas_do_dia.calcular(self.importacao))
        self.assertEqual(cabecalho[0], "Código")
        self.assertIn("Base do custo", cabecalho)
        self.assertIn("Margem %", cabecalho)
        primeira = corpo[0]
        self.assertEqual(primeira[3], "3")
        self.assertEqual(primeira[4], "1.500,50")
        self.assertEqual(primeira[5], "300,00")
        self.assertEqual(primeira[6], "do dia")
        self.assertEqual(primeira[7], "1.200,50")
        segunda = corpo[1]
        self.assertEqual(segunda[5], "")
        self.assertEqual(segunda[6], "sem custo")
        self.assertEqual(segunda[7], "")


class TestTela(BaseVendas):
    def setUp(self):
        super().setUp()
        self.venda(linhas=[{"valor": "100", "custo": "40"}])

    def test_a_gerencia_ve_a_relacao_do_dia(self):
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)
        resposta = self.client.get(reverse("painel:vendas_dia"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "VASO DE VIME")
        self.assertContains(resposta, "Vendas do dia")

    def test_o_vendedor_nao_ve_custo_nem_lucro(self):
        """Condição do Edson: o vendedor tem UMA tela, sem dinheiro nenhum."""
        usuario("balcao", VENDEDOR)
        self.client.login(username="balcao", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("painel:vendas_dia")).status_code, 403)
        self.assertEqual(self.client.get(reverse("painel:vendas_dia_arquivo")).status_code, 403)

    def test_quem_nao_entrou_e_mandado_para_a_entrada(self):
        resposta = self.client.get(reverse("painel:vendas_dia"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/studio/entrar/", resposta["Location"])

    def test_o_arquivo_abre_no_excel_com_o_nome_do_dia(self):
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)
        resposta = self.client.get(reverse("painel:vendas_dia_arquivo"))
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("text/csv", resposta["Content-Type"])
        self.assertIn(f"vendas-do-dia-{CORTE:%Y-%m-%d}.csv", resposta["Content-Disposition"])
        corpo = resposta.content.decode("utf-8")
        self.assertTrue(corpo.startswith("﻿"))
        self.assertIn("VASO DE VIME", corpo)

    def test_dia_torto_na_url_nao_quebra_a_tela(self):
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)
        resposta = self.client.get(reverse("painel:vendas_dia"), {"dia": "amanha"})
        self.assertEqual(resposta.status_code, 200)

    def test_pedir_um_dia_sem_venda_diz_que_nao_houve_venda(self):
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)
        resposta = self.client.get(reverse("painel:vendas_dia"), {"dia": "2026-09-01"})
        self.assertContains(resposta, "Nenhuma venda em 01/09/2026")


class TestCustoEstimado(BaseVendas):
    """O SET parou de gravar o custo da venda em 25/08/2026.

    De lá para cá falta custo em 70% a 100% dos itens de cada dia. Sem a estimativa pelo
    cadastro, o dia que a loja abre na tela ficaria sem lucro nenhum.
    """

    def test_usa_o_custo_do_cadastro_quando_o_set_nao_gravou(self):
        self.venda(linhas=[{"valor": "100", "custo": None, "cadastro": "40"}])
        resultado = vendas_do_dia.calcular(self.importacao)
        self.assertEqual(resultado.custo, Decimal("40.00"))
        self.assertEqual(resultado.custo_do_dia, Decimal("0"))
        self.assertEqual(resultado.custo_estimado, Decimal("40.00"))
        self.assertEqual(resultado.lucro, Decimal("60.00"))
        self.assertEqual(resultado.margem, Decimal("60.0"))
        self.assertTrue(resultado.tem_estimativa)
        self.assertEqual(resultado.produtos_estimados, 1)
        self.assertEqual(resultado.produtos_sem_custo, 0)
        self.assertTrue(resultado.tudo_tem_custo)

    def test_o_custo_da_venda_ganha_do_custo_do_cadastro(self):
        """O custo da venda é o que a loja pagou; o do cadastro é o preço de hoje."""
        self.venda(linhas=[{"valor": "100", "custo": "50", "cadastro": "90"}])
        resultado = vendas_do_dia.calcular(self.importacao)
        self.assertEqual(resultado.custo, Decimal("50.00"))
        self.assertEqual(resultado.custo_estimado, Decimal("0"))
        self.assertFalse(resultado.tem_estimativa)
        self.assertEqual(resultado.linhas[0].base_do_custo, "do dia")

    def test_a_linha_estimada_aparece_marcada(self):
        self.venda(linhas=[{"valor": "100", "custo": None, "cadastro": "40"}])
        linha = vendas_do_dia.calcular(self.importacao).linhas[0]
        self.assertTrue(linha.estimado)
        self.assertTrue(linha.so_estimado)
        self.assertEqual(linha.base_do_custo, "estimado")
        self.assertEqual(linha.lucro, Decimal("60.00"))

    def test_produto_com_parte_estimada_diz_isso(self):
        self.venda(linhas=[{"valor": "100", "custo": "50"}])
        self.venda(linhas=[{"valor": "100", "custo": None, "cadastro": "60"}])
        linha = vendas_do_dia.calcular(self.importacao).linhas[0]
        self.assertTrue(linha.estimado)
        self.assertFalse(linha.so_estimado)
        self.assertEqual(linha.base_do_custo, "parte estimado")
        self.assertEqual(linha.custo, Decimal("110.00"))
        self.assertEqual(linha.lucro, Decimal("90.00"))

    def test_sem_cadastro_e_sem_venda_fica_sem_custo(self):
        """Produto que saiu do cadastro: não há de onde tirar custo nenhum."""
        self.venda(linhas=[{"valor": "100", "custo": None, "cadastro": None}])
        resultado = vendas_do_dia.calcular(self.importacao)
        self.assertEqual(resultado.produtos_sem_custo, 1)
        self.assertEqual(resultado.valor_sem_custo, Decimal("100.00"))
        self.assertFalse(resultado.tudo_tem_custo)
        self.assertIsNone(resultado.margem)
        self.assertTrue(resultado.linhas[0].sem_custo)

    def test_a_tela_diz_quanto_do_dia_e_estimativa(self):
        self.venda(linhas=[{"codigo": "001", "valor": "300", "custo": None, "cadastro": "100"},
                           {"codigo": "002", "valor": "100", "custo": "50"}])
        resultado = vendas_do_dia.calcular(self.importacao)
        self.assertEqual(resultado.fatia_estimada, Decimal("75.0"))

    def test_prejuizo_estimado_nao_e_prejuizo_confirmado(self):
        """Pedra vendida a peso tem custo de cadastro por quilo: alarme falso."""
        self.venda(linhas=[{"valor": "41", "custo": None, "cadastro": "130"}])
        linha = vendas_do_dia.calcular(self.importacao).linhas[0]
        self.assertTrue(linha.prejuizo)
        self.assertFalse(linha.prejuizo_confirmado)

    def test_prejuizo_com_o_custo_da_venda_e_confirmado(self):
        self.venda(linhas=[{"valor": "30", "custo": "50"}])
        linha = vendas_do_dia.calcular(self.importacao).linhas[0]
        self.assertTrue(linha.prejuizo_confirmado)

    def test_a_tela_avisa_a_estimativa_em_palavras(self):
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)
        self.venda(linhas=[{"valor": "100", "custo": None, "cadastro": "40"}])
        resposta = self.client.get(reverse("painel:vendas_dia"))
        self.assertContains(resposta, "não gravou o custo")
        self.assertContains(resposta, "custo do cadastro")
        self.assertContains(resposta, "estimado")
