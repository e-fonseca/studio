"""A variedade de produtos de cada fornecedor (pedido do Edson, 14/10/2026)."""

from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.contas.perfis import ADMINISTRACAO, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.fornecedores import catalogo as servico
from apps.importacao.models import Importacao, ProdutoImportado


class BaseCatalogo(TestCase):
    def setUp(self):
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO,
            situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(),
            data_corte=date(2026, 9, 20),
            dias_abertos_12m=360,
            produtos=0,
        )
        self.produto("1", descricao="CADEIRA DE VIME", grupo="MOVEIS", vendas_12m=Decimal("12"))
        self.produto("2", descricao="MESA DE VIME", grupo="MOVEIS", vendas_12m=Decimal("0"),
                     estoque=Decimal("4"))
        self.produto("3", descricao="LUMINÁRIA QUITÉRIA", grupo="DECORACAO",
                     vendas_12m=Decimal("3"))
        self.produto("9", descricao="DE OUTRO", grupo="MOVEIS", fornecedor="OUTRO")

    def produto(self, codigo, **campos):
        padrao = dict(
            importacao=self.importacao, codigo=codigo, descricao=f"PRODUTO {codigo}",
            grupo="MOVEIS", fornecedor="VIME LENZI", custo=Decimal("10"),
            preco_venda=Decimal("25"), estoque=Decimal("2"), vendas_12m=Decimal("5"),
            receita_12m=Decimal("100"), valor_compras_12m=Decimal("50"),
        )
        padrao.update(campos)
        return ProdutoImportado.objects.create(**padrao)

    def montar(self, **kwargs):
        return servico.montar(self.importacao, nome="VIME LENZI", **kwargs)


class OsNumerosDaVariedade(BaseCatalogo):
    def test_conta_os_produtos_do_fornecedor_e_so_dele(self):
        catalogo = self.montar()
        self.assertEqual(catalogo.produtos, 3)
        self.assertEqual(catalogo.quantos_grupos, 2)

    def test_separa_o_que_vende_do_que_esta_parado(self):
        catalogo = self.montar()
        self.assertEqual(catalogo.com_venda, 2)
        self.assertEqual(catalogo.parados, 1)

    def test_o_grupo_maior_leva_a_barra_cheia_e_a_largura_e_inteira(self):
        """Decimal dentro de style= sai localizado e o navegador joga a linha fora."""
        maior = self.montar().grupos[0]
        self.assertEqual(maior.nome, "MOVEIS")
        self.assertEqual(maior.produtos, 2)
        self.assertEqual(maior.largura, 100)
        self.assertIsInstance(maior.largura, int)

    def test_saldo_negativo_nao_vira_dinheiro_a_menos_na_prateleira(self):
        self.produto("4", estoque=Decimal("-100"), custo=Decimal("10"))
        # CADEIRA 2 x 10, MESA 4 x 10, LUMINÁRIA 2 x 10, e o negativo valendo zero.
        self.assertEqual(self.montar().estoque, Decimal("80"))

    def test_o_parado_e_o_mesmo_numero_da_lista_de_compra(self):
        """MESA DE VIME: tem saldo, não vendeu no ano, tem custo."""
        self.assertEqual(self.montar().parado_na_prateleira, Decimal("40.00"))

    def test_fornecedor_sem_produto_nao_quebra_a_tela(self):
        catalogo = servico.montar(self.importacao, nome="NINGUEM")
        self.assertEqual(catalogo.produtos, 0)
        self.assertFalse(catalogo.tem_itens)

    def test_sem_importacao_devolve_catalogo_vazio(self):
        self.assertEqual(servico.montar(None, nome="VIME LENZI").produtos, 0)


class ProcurarDentroDoFornecedor(BaseCatalogo):
    def test_acha_sem_acento(self):
        catalogo = self.montar(busca="luminaria")
        self.assertEqual(catalogo.encontrados, 1)
        self.assertEqual(catalogo.itens[0].codigo, "3")

    def test_acha_pelo_codigo(self):
        self.assertEqual(self.montar(busca="2").itens[0].codigo, "2")

    def test_filtrar_por_grupo_mostra_so_ele(self):
        catalogo = self.montar(grupo="DECORACAO")
        self.assertEqual(catalogo.encontrados, 1)
        self.assertEqual(catalogo.itens[0].grupo, "DECORACAO")

    def test_a_tela_mostra_uma_pagina_e_o_arquivo_leva_tudo(self):
        for numero in range(5):
            self.produto(f"p{numero}")
        catalogo = self.montar(quantos=3)
        self.assertEqual(catalogo.mostrados, 3)
        self.assertEqual(catalogo.encontrados, 8)
        self.assertEqual(catalogo.escondidos, 5)
        inteiro = self.montar(quantos=None)
        self.assertEqual(len(servico.em_linhas(inteiro)) - 1, 8)


class TelaDosProdutosDoFornecedor(BaseCatalogo):
    def setUp(self):
        super().setUp()
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)

    def _abrir(self, **parametros):
        parametros.setdefault("nome", "VIME LENZI")
        return self.client.get(reverse("fornecedores:produtos"), parametros)

    def test_a_tela_abre_com_a_variedade_e_os_produtos(self):
        resposta = self._abrir()
        self.assertContains(resposta, "VIME LENZI")
        self.assertContains(resposta, "CADEIRA DE VIME")
        self.assertContains(resposta, "MOVEIS")

    def test_a_tela_diz_que_o_fornecedor_e_o_da_ultima_compra(self):
        """Senão a pessoa lê isto como o mostruário do fornecedor, e não é."""
        self.assertContains(self._abrir(), "última compra")

    def test_sem_nome_a_tela_manda_escolher_em_vez_de_quebrar(self):
        resposta = self.client.get(reverse("fornecedores:produtos"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Escolha um fornecedor")

    def test_o_arquivo_sai_em_csv_com_o_nome_do_fornecedor(self):
        resposta = self.client.get(reverse("fornecedores:produtos_em_arquivo"),
                                   {"nome": "VIME LENZI"})
        self.assertIn("text/csv", resposta["Content-Type"])
        self.assertIn("produtos-vime-lenzi.csv", resposta["Content-Disposition"])
        corpo = resposta.content.decode("utf-8")
        self.assertTrue(corpo.startswith("﻿"))
        self.assertIn("CADEIRA DE VIME", corpo)
        self.assertNotIn("DE OUTRO", corpo)

    def test_o_vendedor_nao_ve_o_catalogo_com_custo(self):
        self.client.logout()
        usuario("vendedora", VENDEDOR)
        self.client.login(username="vendedora", password=SENHA_TESTE)
        self.assertEqual(self._abrir().status_code, 403)
