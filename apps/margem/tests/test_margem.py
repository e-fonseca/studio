"""Markup e margem de lucro: as duas contas, os casos torcidos do cadastro e quem vê.

O que estes testes travam:

- markup e margem do mesmo preço nunca saem iguais, e cada um usa o seu divisor;
- a margem realizada vem do custo gravado no item da venda, e não do custo de hoje;
- produto com preço abaixo do custo, sem custo, ou com o "% de lucro" do SET
  desatualizado é encontrado e contado;
- o vendedor continua sem ver custo, preço de custo e lucro.
"""

from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.importacao.models import Importacao, ProdutoImportado
from apps.margem import servicos

CORTE = date(2026, 9, 20)


class Base(TestCase):
    def setUp(self):
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO,
            situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(),
            data_corte=CORTE,
            dias_abertos_12m=300,
            produtos=0,
        )

    def produto(self, codigo, **campos):
        padrao = dict(
            descricao=f"PRODUTO {codigo}", grupo="MADEIRA", fornecedor="LENZI",
            custo=Decimal("25"), preco_venda=Decimal("99"), markup_set=Decimal("296"),
            estoque=Decimal("4"), vendas_12m=Decimal("10"),
            receita_12m=Decimal("990"), receita_com_custo_12m=Decimal("990"),
            custo_vendido_12m=Decimal("250"),
        )
        padrao.update(campos)
        return ProdutoImportado.objects.create(importacao=self.importacao, codigo=codigo, **padrao)

    def montar(self, **filtros):
        return servicos.montar(self.importacao, **filtros)


class TestAsDuasContas(TestCase):
    """O mesmo preço, dois números: é a confusão que a tela existe para desfazer."""

    def test_markup_e_margem_do_mesmo_preco_sao_diferentes(self):
        # Custa 10, vende a 20: põe-se 100% em cima do custo e sobra 50% do preço.
        self.assertEqual(servicos.markup(Decimal("10"), Decimal("20")), Decimal("100.0"))
        self.assertEqual(servicos.margem(Decimal("10"), Decimal("20")), Decimal("50.0"))

    def test_numeros_reais_do_cadastro_da_loja(self):
        # LEÃO DE EUCALIPTO no backup de 20/09/2026: custo 25,00 e venda 99,00.
        self.assertEqual(servicos.markup(Decimal("25"), Decimal("99")), Decimal("296.0"))
        self.assertEqual(servicos.margem(Decimal("25"), Decimal("99")), Decimal("74.7"))

    def test_sem_custo_nao_ha_markup_e_sem_preco_nao_ha_margem(self):
        self.assertIsNone(servicos.markup(None, Decimal("99")))
        self.assertIsNone(servicos.markup(Decimal("0"), Decimal("99")))
        self.assertIsNone(servicos.margem(Decimal("25"), None))
        self.assertIsNone(servicos.margem(Decimal("25"), Decimal("0")))

    def test_produto_sem_preco_nao_entra_na_conta_como_markup_de_menos_cem(self):
        # Preço zerado é produto não precificado, e não produto com prejuízo total.
        self.assertIsNone(servicos.markup(Decimal("25"), Decimal("0")))

    def test_preco_abaixo_do_custo_da_numero_negativo_nos_dois(self):
        self.assertEqual(servicos.markup(Decimal("10"), Decimal("8")), Decimal("-20.0"))
        self.assertEqual(servicos.margem(Decimal("10"), Decimal("8")), Decimal("-25.0"))


class TestSituacaoDoProduto(Base):
    def test_preco_abaixo_do_custo_e_encontrado_e_a_perda_e_contada(self):
        self.produto("001", custo=Decimal("10"), preco_venda=Decimal("8"),
                     estoque=Decimal("3"), markup_set=None)
        tela = self.montar()
        linha = tela.produtos[0]
        self.assertEqual(linha.situacao, servicos.ABAIXO_DO_CUSTO)
        self.assertEqual(tela.resumo.abaixo_do_custo, 1)
        # Três na prateleira, perdendo R$ 2,00 em cada venda.
        self.assertEqual(tela.resumo.perda_abaixo_do_custo, Decimal("6.00"))

    def test_preco_igual_ao_custo_e_markup_zero(self):
        self.produto("002", custo=Decimal("30"), preco_venda=Decimal("30"), markup_set=None)
        tela = self.montar()
        self.assertEqual(tela.produtos[0].situacao, servicos.NO_CUSTO)
        self.assertEqual(tela.produtos[0].markup, Decimal("0.0"))
        self.assertEqual(tela.resumo.no_custo, 1)

    def test_produto_com_preco_e_sem_custo_e_contado_a_parte(self):
        self.produto("003", custo=None, preco_venda=Decimal("40"), markup_set=None)
        tela = self.montar()
        linha = tela.produtos[0]
        self.assertEqual(linha.situacao, servicos.SEM_CUSTO)
        self.assertIsNone(linha.markup)
        self.assertIsNone(linha.margem)
        self.assertEqual(tela.resumo.sem_custo, 1)

    def test_porcento_de_lucro_do_set_que_nao_bate_com_o_preco_e_apontado(self):
        # 006491 no backup: custo 2,00, venda 13,00 (markup 550%) e PLUCRO parado em 130%.
        self.produto("006491", custo=Decimal("2"), preco_venda=Decimal("13"),
                     markup_set=Decimal("130"))
        tela = self.montar()
        linha = tela.produtos[0]
        self.assertEqual(linha.markup, Decimal("550.0"))
        self.assertFalse(linha.markup_set_confere)
        self.assertEqual(linha.situacao, servicos.MARKUP_SET_ERRADO)
        self.assertEqual(tela.resumo.markup_set_errado, 1)

    def test_arredondamento_no_porcento_do_set_nao_conta_como_erro(self):
        # 433,33 gravado no SET contra 434,77 calculado é preço mexido; meio ponto, não.
        self.produto("004", custo=Decimal("10"), preco_venda=Decimal("51.04"),
                     markup_set=Decimal("410.0"))
        linha = self.montar().produtos[0]
        self.assertEqual(linha.markup, Decimal("410.4"))
        self.assertTrue(linha.markup_set_confere)
        self.assertEqual(linha.situacao, "")

    def test_sem_porcento_de_lucro_no_set_conta_mas_nao_vira_etiqueta(self):
        self.produto("005", markup_set=None)
        linha = self.montar().produtos[0]
        self.assertEqual(linha.situacao, servicos.SEM_MARKUP_SET)
        self.assertEqual(linha.rotulo_selo, "")
        self.assertEqual(self.montar().resumo.sem_markup_set, 1)


class TestOQueNaoEMercadoria(Base):
    """DIVERSOS é o código da venda miúda do balcão: preço de R$ 1,00 e custo sem sentido."""

    def test_diversos_nao_entra_na_lista_de_preco_abaixo_do_custo(self):
        self.produto("000001", descricao="DIVERSOS", custo=Decimal("12.50"),
                     preco_venda=Decimal("1"), markup_set=None)
        tela = self.montar()
        self.assertEqual(tela.produtos[0].situacao, "")
        self.assertFalse(tela.produtos[0].mercadoria)
        # Nem markup nem margem: -1.150% ali seria um número errado com ar de certo.
        self.assertIsNone(tela.produtos[0].markup)
        self.assertIsNone(tela.produtos[0].margem)
        self.assertEqual(tela.resumo.abaixo_do_custo, 0)
        self.assertEqual(self.montar(situacao=servicos.ABAIXO_DO_CUSTO).produtos, [])

    def test_mas_o_dinheiro_que_ele_deu_continua_na_conta_da_loja(self):
        self.produto("000001", descricao="DIVERSOS", custo=Decimal("12.50"),
                     preco_venda=Decimal("1"), markup_set=None,
                     receita_12m=Decimal("1000"), receita_com_custo_12m=Decimal("1000"),
                     custo_vendido_12m=Decimal("400"))
        resumo = self.montar().resumo
        self.assertEqual(resumo.lucro, Decimal("600.00"))
        self.assertEqual(resumo.margem_realizada, Decimal("60.0"))

    def test_consumo_proprio_tambem_fica_fora_dos_avisos(self):
        self.produto("002", grupo="CONSUMO PROPRIO", custo=Decimal("10"),
                     preco_venda=Decimal("5"), markup_set=None)
        self.assertEqual(self.montar().resumo.abaixo_do_custo, 0)


class TestMargemRealizada(Base):
    """O que a loja ganhou, e não o que o cadastro de hoje promete."""

    def test_o_lucro_de_doze_meses_usa_o_custo_do_dia_da_venda(self):
        # Vendeu 10 a R$ 99,00 com custo de R$ 25,00 na época. Depois o custo do cadastro
        # subiu para R$ 90,00: a margem realizada não pode mudar por causa disso.
        self.produto("001", custo=Decimal("90"), preco_venda=Decimal("99"),
                     receita_12m=Decimal("990"), receita_com_custo_12m=Decimal("990"),
                     custo_vendido_12m=Decimal("250"))
        tela = self.montar()
        self.assertEqual(tela.produtos[0].lucro_12m, Decimal("740.00"))
        self.assertEqual(tela.produtos[0].margem_12m, Decimal("74.7"))
        self.assertEqual(tela.resumo.margem_realizada, Decimal("74.7"))
        # E a margem da tabela de hoje, bem menor, mostra o aperto.
        self.assertEqual(tela.resumo.margem_tabela, Decimal("9.1"))

    def test_receita_sem_custo_gravado_fica_fora_da_conta_da_margem(self):
        # Metade da receita sem custo no item: a margem é calculada só sobre a outra.
        self.produto("001", receita_12m=Decimal("2000"),
                     receita_com_custo_12m=Decimal("1000"),
                     custo_vendido_12m=Decimal("400"))
        tela = self.montar()
        self.assertEqual(tela.resumo.lucro, Decimal("600.00"))
        self.assertEqual(tela.resumo.margem_realizada, Decimal("60.0"))
        self.assertEqual(tela.resumo.cobertura_do_custo, Decimal("50.0"))

    def test_markup_realizado_e_o_mesmo_lucro_contado_sobre_o_custo(self):
        self.produto("001", receita_12m=Decimal("1000"),
                     receita_com_custo_12m=Decimal("1000"),
                     custo_vendido_12m=Decimal("400"))
        resumo = self.montar().resumo
        self.assertEqual(resumo.margem_realizada, Decimal("60.0"))
        self.assertEqual(resumo.markup_realizado, Decimal("150.0"))
        self.assertEqual(resumo.vezes_o_custo, Decimal("2.5"))

    def test_produto_sem_custo_gravado_em_venda_nenhuma_fica_sem_lucro(self):
        self.produto("001", receita_12m=Decimal("500"),
                     receita_com_custo_12m=Decimal("0"), custo_vendido_12m=Decimal("0"))
        linha = self.montar().produtos[0]
        self.assertIsNone(linha.lucro_12m)
        self.assertIsNone(linha.margem_12m)


class TestResumoEGrupos(Base):
    def test_markup_mediano_e_do_produto_do_meio_e_nao_da_media(self):
        self.produto("001", custo=Decimal("10"), preco_venda=Decimal("11"))   # 10%
        self.produto("002", custo=Decimal("10"), preco_venda=Decimal("20"))   # 100%
        self.produto("003", custo=Decimal("10"), preco_venda=Decimal("110"))  # 1000%
        resumo = self.montar().resumo
        self.assertEqual(resumo.markup_mediano, Decimal("100.0"))
        self.assertEqual(resumo.com_os_dois_precos, 3)

    def test_grupos_saem_do_maior_lucro_para_o_menor(self):
        self.produto("001", grupo="CERAMICA", receita_com_custo_12m=Decimal("1000"),
                     custo_vendido_12m=Decimal("900"))
        self.produto("002", grupo="MADEIRA", receita_com_custo_12m=Decimal("1000"),
                     custo_vendido_12m=Decimal("200"))
        tela = self.montar()
        self.assertEqual([g.nome for g in tela.grupos], ["MADEIRA", "CERAMICA"])
        self.assertEqual(tela.grupos[0].lucro_12m, Decimal("800.00"))
        self.assertEqual(tela.grupos[0].margem_12m, Decimal("80.0"))
        self.assertEqual(tela.grupos[1].margem_12m, Decimal("10.0"))

    def test_sem_importacao_a_tela_avisa_em_vez_de_quebrar(self):
        tela = servicos.montar(None)
        self.assertFalse(tela.tem_dados)
        self.assertEqual(tela.produtos, [])


class TestFiltrosEOrdem(Base):
    def setUp(self):
        super().setUp()
        self.produto("001", grupo="MADEIRA", custo=Decimal("10"), preco_venda=Decimal("8"),
                     receita_com_custo_12m=Decimal("80"), custo_vendido_12m=Decimal("100"))
        self.produto("002", grupo="PALHA", custo=Decimal("10"), preco_venda=Decimal("50"),
                     receita_com_custo_12m=Decimal("500"), custo_vendido_12m=Decimal("100"))
        # Sem custo no cadastro e sem venda nenhuma: entra na contagem de "sem custo"
        # sem mexer na margem realizada do grupo.
        self.produto("003", grupo="PALHA", custo=None, preco_venda=Decimal("30"),
                     vendas_12m=Decimal("0"), receita_12m=Decimal("0"),
                     receita_com_custo_12m=Decimal("0"), custo_vendido_12m=Decimal("0"))

    def test_filtro_de_situacao_mostra_so_o_que_pede_arrumo(self):
        tela = self.montar(situacao=servicos.ABAIXO_DO_CUSTO)
        self.assertEqual([p.codigo for p in tela.produtos], ["001"])
        # O resumo continua contando a loja inteira do recorte, não só as linhas filtradas.
        self.assertEqual(tela.resumo.produtos, 3)

    def test_ordem_por_menor_margem_poe_o_prejuizo_na_frente(self):
        tela = self.montar(ordem="margem_menor")
        self.assertEqual([p.codigo for p in tela.produtos][:2], ["001", "002"])

    def test_produto_sem_margem_vai_para_o_fim_e_nao_para_o_topo(self):
        tela = self.montar(ordem="margem_menor")
        self.assertEqual([p.codigo for p in tela.produtos][-1], "003")

    def test_filtro_de_grupo_tambem_recalcula_o_resumo(self):
        tela = self.montar(grupo="PALHA")
        self.assertEqual(tela.resumo.produtos, 2)
        self.assertEqual(tela.resumo.margem_realizada, Decimal("80.0"))

    def test_busca_acha_pelo_codigo_e_pelo_nome(self):
        self.assertEqual([p.codigo for p in self.montar(busca="002").produtos], ["002"])
        self.assertEqual(len(self.montar(busca="PRODUTO").produtos), 3)


class TestArquivo(Base):
    def test_arquivo_leva_todos_e_com_virgula_decimal(self):
        for numero in range(5):
            self.produto(f"{numero:03d}")
        tela = servicos.montar(self.importacao, quantos=0)
        linhas = servicos.em_linhas(tela)
        self.assertEqual(len(linhas), 6)  # cabeçalho e os cinco produtos
        self.assertIn("Markup %", linhas[0])
        self.assertIn("296,0", linhas[1])
        self.assertIn("74,7", linhas[1])

    def test_a_tela_mostra_so_os_primeiros_mas_diz_quantos_sao(self):
        for numero in range(7):
            self.produto(f"{numero:03d}")
        tela = servicos.montar(self.importacao, quantos=3)
        self.assertEqual(tela.quantos, 7)
        self.assertEqual(tela.mostrando, 3)
        self.assertTrue(tela.tem_mais)


class TestQuemEntra(Base):
    def setUp(self):
        super().setUp()
        self.produto("001")
        self.endereco = reverse("margem:lista")

    def entrar(self, nome, *perfis):
        usuario(nome, *perfis)
        self.client.login(username=nome, password=SENHA_TESTE)

    def test_a_gerencia_ve_a_tela_com_os_dois_numeros(self):
        self.entrar("gerente-margem", ADMINISTRACAO)
        resposta = self.client.get(self.endereco)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Markup e margem não são a mesma coisa")

    def test_o_administrativo_tambem_entra(self):
        self.entrar("admin-margem", ADMINISTRATIVO)
        self.assertEqual(self.client.get(self.endereco).status_code, 200)

    def test_o_vendedor_nao_ve_custo_nem_margem(self):
        self.entrar("vendedor-margem", VENDEDOR)
        self.assertEqual(self.client.get(self.endereco).status_code, 403)
        self.assertEqual(self.client.get(reverse("margem:em_arquivo")).status_code, 403)

    def test_com_filtro_de_situacao_a_tabela_por_grupo_sai_da_frente(self):
        # Ela mostra o grupo inteiro: ao lado de uma lista de problemas, faria parecer
        # que o grupo todo está com preço abaixo do custo.
        self.entrar("gerente-margem", ADMINISTRACAO)
        self.assertContains(self.client.get(self.endereco), "Por grupo de produto")
        comfiltro = self.client.get(self.endereco, {"situacao": servicos.ABAIXO_DO_CUSTO})
        self.assertNotContains(comfiltro, "Por grupo de produto")

    def test_sem_entrar_vai_para_o_login(self):
        self.assertEqual(self.client.get(self.endereco).status_code, 302)

    def test_o_arquivo_sai_com_nome_da_data_dos_dados(self):
        self.entrar("gerente-margem", ADMINISTRACAO)
        resposta = self.client.get(reverse("margem:em_arquivo"))
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("margem-e-markup-2026-09-20.csv", resposta["Content-Disposition"])
        self.assertTrue(resposta.content.decode("utf-8").startswith("﻿"))

    def test_o_menu_leva_a_tela_para_quem_ve_painel_e_nao_para_o_vendedor(self):
        self.entrar("gerente-margem", ADMINISTRACAO)
        self.assertContains(self.client.get(self.endereco), 'href="/sistema/margem/"')
        self.client.logout()
        self.entrar("vendedor-margem", VENDEDOR)
        resposta = self.client.get(reverse("importacao:consulta"))
        self.assertNotContains(resposta, "/sistema/margem/")
