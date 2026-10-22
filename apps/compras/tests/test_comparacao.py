"""Comparar um período com o mesmo período do ano passado (pedido do Edson, 14/10/2026)."""

from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.compras import comparacao
from apps.contas.perfis import ADMINISTRACAO, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.importacao.models import Importacao, ProdutoImportado, VendaMensalDoProduto

CORTE = date(2026, 9, 20)


class BaseComparacao(TestCase):
    def setUp(self):
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO,
            situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(),
            data_corte=CORTE,
            # A foto diz desde quando guarda venda mês a mês. Sem isso quem lê despreza o
            # mês mais antigo, porque nas fotos até a 1.29.0 ele era meio mês.
            mes_a_mes_desde=date(2021, 9, 1),
            dias_abertos_12m=360,
            produtos=0,
        )

    def produto(self, codigo, **campos):
        padrao = dict(
            importacao=self.importacao, codigo=codigo, descricao=f"PRODUTO {codigo}",
            grupo="MOVEIS", fornecedor="VIME LENZI", custo=Decimal("10"),
            preco_venda=Decimal("25"), estoque=Decimal("3"),
        )
        padrao.update(campos)
        return ProdutoImportado.objects.create(**padrao)

    def mes(self, codigo, ano, mes, unidades, receita):
        return VendaMensalDoProduto.objects.create(
            importacao=self.importacao, codigo=codigo, ano=ano, mes=mes,
            unidades=Decimal(unidades), receita=Decimal(receita),
        )

    def montar(self, **kwargs):
        return comparacao.montar(self.importacao, **kwargs)


class OsMesesQueEntram(TestCase):
    def test_o_mes_da_data_de_corte_fica_de_fora_quando_nao_fechou(self):
        """Meio setembro contra setembro inteiro do ano passado acusaria queda que não existe."""
        self.assertEqual(comparacao._mes_fechado(date(2026, 9, 20)), (2026, 8))

    def test_corte_no_ultimo_dia_do_mes_fecha_o_mes(self):
        self.assertEqual(comparacao._mes_fechado(date(2026, 9, 30)), (2026, 9))
        self.assertEqual(comparacao._mes_fechado(date(2026, 2, 28)), (2026, 2))

    def test_em_janeiro_o_mes_fechado_e_dezembro_do_ano_anterior(self):
        self.assertEqual(comparacao._mes_fechado(date(2026, 1, 5)), (2025, 12))

    def test_a_janela_tem_os_meses_na_ordem_e_atravessa_o_ano(self):
        self.assertEqual(comparacao._janela(2026, 2, 3), [(2025, 12), (2026, 1), (2026, 2)])

    def test_o_rotulo_fala_como_gente(self):
        self.assertEqual(comparacao._rotulo(comparacao._janela(2026, 8, 3)),
                         "junho a agosto de 2026")
        self.assertEqual(comparacao._rotulo(comparacao._janela(2026, 8, 1)), "agosto de 2026")


class OsNumerosDaComparacao(BaseComparacao):
    def setUp(self):
        super().setUp()
        self.produto("1", descricao="CADEIRA")
        self.produto("2", descricao="MESA")
        # Agosto de 2026 contra agosto de 2025, com o período de 3 meses pegando jun-ago.
        self.mes("1", 2026, 8, 10, 1000)
        self.mes("1", 2025, 8, 4, 400)
        self.mes("2", 2025, 7, 5, 500)

    def test_compara_o_mesmo_periodo_do_ano_passado(self):
        dados = self.montar(periodo="3m")
        self.assertEqual(dados.rotulo_de_agora, "junho a agosto de 2026")
        self.assertEqual(dados.rotulo_de_antes, "junho a agosto de 2025")
        self.assertEqual(dados.receita, Decimal("1000"))
        self.assertEqual(dados.receita_antes, Decimal("900"))
        self.assertEqual(dados.variacao, 11)

    def test_produto_que_vendia_e_sumiu_aparece_como_sumido_e_nao_como_queda(self):
        dados = self.montar(periodo="3m")
        mesa = next(l for l in dados.linhas if l.codigo == "2")
        self.assertTrue(mesa.sumiu)
        self.assertEqual(dados.sumiram, 1)

    def test_produto_que_nao_vendia_no_ano_passado_nao_tem_variacao(self):
        self.produto("3", descricao="BANCO")
        self.mes("3", 2026, 7, 2, 200)
        novo = next(l for l in self.montar(periodo="3m").linhas if l.codigo == "3")
        self.assertTrue(novo.novo)
        self.assertIsNone(novo.variacao)

    def test_o_mes_aberto_fica_de_fora_da_conta(self):
        """Setembro de 2026 é o mês do corte e ainda está correndo."""
        self.mes("1", 2026, 9, 99, 9900)
        dados = self.montar(periodo="3m")
        self.assertEqual(dados.receita, Decimal("1000"))
        self.assertEqual(dados.mes_de_fora, "setembro de 2026")

    def test_a_largura_da_barra_e_inteira(self):
        linha = self.montar(periodo="3m").cresceram[0]
        self.assertIsInstance(linha.largura, int)

    def test_sem_historico_do_ano_passado_a_tela_sabe_dizer(self):
        VendaMensalDoProduto.objects.filter(ano=2025).delete()
        self.assertFalse(self.montar(periodo="3m").tem_historico)

    def test_sem_importacao_nao_quebra(self):
        self.assertEqual(comparacao.montar(None).produtos, 0)

    def test_periodo_desconhecido_cai_no_padrao(self):
        self.assertEqual(self.montar(periodo="qualquer").periodo, comparacao.PERIODO_PADRAO)

    def test_o_filtro_de_grupo_e_de_fornecedor_vale(self):
        self.produto("4", descricao="LUMINARIA", grupo="DECORACAO", fornecedor="OUTRO")
        self.mes("4", 2026, 8, 1, 100)
        self.assertEqual(self.montar(periodo="3m", grupo="DECORACAO").produtos, 1)
        self.assertEqual(self.montar(periodo="3m", fornecedor="VIME LENZI").produtos, 2)

    def test_a_busca_acha_sem_acento(self):
        self.produto("5", descricao="LUMINÁRIA QUITÉRIA")
        self.mes("5", 2026, 8, 1, 100)
        dados = self.montar(periodo="3m", busca="luminaria")
        self.assertEqual(dados.produtos, 1)

    def test_o_arquivo_leva_tudo_e_a_tela_uma_pagina(self):
        for numero in range(5):
            self.produto(f"p{numero}")
            self.mes(f"p{numero}", 2026, 8, 1, 100)
        dados = self.montar(periodo="3m", quantos=3)
        self.assertEqual(dados.mostrados, 3)
        self.assertEqual(dados.encontrados, 7)
        inteiro = self.montar(periodo="3m", quantos=None)
        self.assertEqual(len(comparacao.em_linhas(inteiro)) - 1, 7)


class TelaDaComparacao(BaseComparacao):
    def setUp(self):
        super().setUp()
        self.produto("1", descricao="CADEIRA")
        self.mes("1", 2026, 8, 10, 1000)
        self.mes("1", 2025, 8, 4, 400)
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)

    def test_a_tela_abre_com_os_dois_periodos_lado_a_lado(self):
        resposta = self.client.get(reverse("compras:comparar"))
        # Com inicial maiúscula porque a tela escreve o período como título do cartão.
        self.assertContains(resposta, "Junho a agosto de 2026")
        self.assertContains(resposta, "junho a agosto de 2025")
        self.assertContains(resposta, "CADEIRA")

    def test_a_tela_diz_que_o_mes_aberto_ficou_de_fora(self):
        self.assertContains(self.client.get(reverse("compras:comparar")),
                            "ainda está correndo")

    def test_sem_historico_a_tela_explica_em_vez_de_ficar_vazia(self):
        VendaMensalDoProduto.objects.all().delete()
        resposta = self.client.get(reverse("compras:comparar"))
        self.assertContains(resposta, "Ainda não há o ano passado")
        self.assertContains(resposta, "sincroniza")

    def test_o_arquivo_sai_em_csv(self):
        resposta = self.client.get(reverse("compras:comparar_em_arquivo"), {"periodo": "3m"})
        self.assertIn("text/csv", resposta["Content-Type"])
        corpo = resposta.content.decode("utf-8")
        self.assertTrue(corpo.startswith("﻿"))
        self.assertIn("CADEIRA", corpo)
        self.assertIn("junho a agosto de 2025", corpo)

    def test_o_vendedor_nao_ve_faturamento(self):
        self.client.logout()
        usuario("vendedora", VENDEDOR)
        self.client.login(username="vendedora", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("compras:comparar")).status_code, 403)


class OQuadroDentroDaListaDeCompra(BaseComparacao):
    """A comparação virou recurso da lista de compra (pedido do Edson, 14/10/2026).

    Saiu do menu e passou a abrir junto com a lista, porque é na hora de fechar o pedido
    que saber o que o mesmo período vendeu um ano atrás muda a decisão.
    """

    def setUp(self):
        super().setUp()
        self.produto("1", descricao="CADEIRA", fornecedor="VIME LENZI")
        self.mes("1", 2026, 8, 10, 1000)
        self.mes("1", 2025, 8, 4, 400)
        self.produto("2", descricao="MESA", fornecedor="GERMAN")
        self.mes("2", 2026, 8, 2, 5000)
        self.mes("2", 2025, 8, 9, 9000)
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)

    def test_a_lista_de_compra_abre_com_o_quadro_do_ano_passado(self):
        resposta = self.client.get(reverse("compras:lista"))
        self.assertContains(resposta, "Comparar com o ano passado")
        self.assertContains(resposta, "Junho a agosto de 2026")
        self.assertContains(resposta, "junho a agosto de 2025")

    def test_o_quadro_segue_o_fornecedor_filtrado_na_tela(self):
        """Filtrando um fornecedor, a comparação é dele: é dele que se vai comprar."""
        resposta = self.client.get(reverse("compras:lista"), {"fornecedor": "GERMAN"})
        self.assertContains(resposta, "MESA")
        # A CADEIRA é de outro fornecedor e não pode entrar na conta deste quadro.
        corpo = resposta.content.decode()
        quadro = corpo[corpo.index('id="ano-passado"'):]
        self.assertNotIn("CADEIRA", quadro)

    def test_o_periodo_do_quadro_nao_perde_o_filtro_da_tela(self):
        """Trocar o período do quadro não pode zerar o fornecedor escolhido acima."""
        resposta = self.client.get(reverse("compras:lista"),
                                   {"fornecedor": "GERMAN", "periodo": "12m"})
        corpo = resposta.content.decode()
        quadro = corpo[corpo.index('id="ano-passado"'):]
        self.assertIn('name="fornecedor" value="GERMAN"', quadro)
        self.assertIn('value="12m" selected', quadro)

    def test_o_quadro_leva_para_a_tabela_produto_a_produto(self):
        resposta = self.client.get(reverse("compras:lista"))
        self.assertContains(resposta, reverse("compras:comparar"))

    def test_sem_o_ano_passado_o_quadro_explica_em_vez_de_mostrar_zero(self):
        VendaMensalDoProduto.objects.all().delete()
        resposta = self.client.get(reverse("compras:lista"))
        self.assertContains(resposta, "ainda não entrou nesta foto do SET")

    def test_a_tabela_produto_a_produto_tem_a_volta_para_a_lista_de_compra(self):
        """Ela saiu do menu: sem o link, quem abre fica sem caminho de volta."""
        resposta = self.client.get(reverse("compras:comparar"))
        self.assertContains(resposta, reverse("compras:lista") + "#ano-passado")

    def test_o_vendedor_nao_ve_nada_disso(self):
        self.client.logout()
        usuario("vendedora", VENDEDOR)
        self.client.login(username="vendedora", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("compras:lista")).status_code, 403)


class OPeriodoEscolhidoADedo(BaseComparacao):
    """"Aumentar os filtros, permitir edição por período" (pedido do Edson, 14/10/2026)."""

    def setUp(self):
        super().setUp()
        self.produto("1", descricao="CADEIRA")
        for ano in (2025, 2026):
            for mes in range(1, 9):
                self.mes("1", ano, mes, 1, 100 * mes)

    def test_os_dois_meses_escolhidos_mandam_no_periodo(self):
        dados = self.montar(periodo="livre", de="2026-03", ate="2026-05")
        self.assertEqual(dados.rotulo_de_agora, "março a maio de 2026")
        self.assertEqual(dados.rotulo_de_antes, "março a maio de 2025")
        self.assertEqual(dados.meses, 3)
        self.assertTrue(dados.escolhido_a_dedo)
        # 300 + 400 + 500, os mesmos meses de 2026 e de 2025.
        self.assertEqual(dados.receita, Decimal("1200"))
        self.assertEqual(dados.receita_antes, Decimal("1200"))

    def test_um_mes_so_vale_como_periodo(self):
        dados = self.montar(periodo="livre", de="2026-07", ate="2026-07")
        self.assertEqual(dados.rotulo_de_agora, "julho de 2026")
        self.assertEqual(dados.meses, 1)

    def test_mes_invertido_ou_sujo_cai_no_periodo_pronto(self):
        """O que vem da barra de endereço pode ser qualquer coisa e não pode derrubar a tela."""
        for de, ate in (("2026-05", "2026-03"), ("xx", "2026-05"), ("", ""),
                        ("2026-13", "2026-14"), ("2026-05", "")):
            with self.subTest(de=de, ate=ate):
                dados = self.montar(periodo="livre", de=de, ate=ate)
                self.assertEqual(dados.periodo, comparacao.PERIODO_PADRAO)
                self.assertEqual(dados.rotulo_de_agora, "junho a agosto de 2026")

    def test_o_periodo_pedido_fora_da_foto_e_aparado_para_o_que_cabe(self):
        """Pedir até dezembro de 2026 não inventa mês: para no último mês fechado."""
        dados = self.montar(periodo="livre", de="2026-06", ate="2026-12")
        self.assertEqual(dados.ate, "2026-08")

    def test_a_tela_oferece_os_meses_que_a_foto_guarda(self):
        dados = self.montar()
        self.assertEqual(dados.meses_disponiveis[0], ("2026-08", "agosto de 2026"))
        self.assertEqual(dados.meses_disponiveis[-1][0], "2021-09")
        self.assertEqual(dados.de, "2026-06")
        self.assertEqual(dados.ate, "2026-08")

    def test_e_o_botao_apertado_que_decide_qual_periodo_vale(self):
        """Dois controles, dois botões: sem isso o sistema teria que adivinhar."""
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)
        endereco = reverse("compras:comparar")
        pronto = self.client.get(endereco, {"periodo": "6m", "de": "2026-03", "ate": "2026-05"})
        self.assertContains(pronto, "Março a agosto de 2026")
        escolhido = self.client.get(endereco, {"periodo": "6m", "de": "2026-03",
                                               "ate": "2026-05", "comparar": "meses"})
        self.assertContains(escolhido, "Março a maio de 2026")
        self.assertContains(escolhido, "Meses escolhidos")


class OMesmoPeriodoAnoAAno(BaseComparacao):
    """"Trazer outro comparativo de vendas do mesmo período dos anos anteriores"."""

    def setUp(self):
        super().setUp()
        self.produto("1", descricao="CADEIRA", fornecedor="VIME LENZI")
        self.produto("2", descricao="MESA", fornecedor="GERMAN")
        for ano, receita in ((2026, 1000), (2025, 800), (2024, 500), (2023, 400)):
            self.mes("1", ano, 8, 10, receita)
            self.mes("2", ano, 8, 1, 50)

    def test_uma_linha_por_ano_do_mais_novo_para_o_mais_velho(self):
        anos = self.montar(periodo="livre", de="2026-08", ate="2026-08").anos
        self.assertEqual([linha.ano for linha in anos], [2026, 2025, 2024, 2023])
        self.assertEqual([linha.rotulo for linha in anos][0], "agosto de 2026")

    def test_a_variacao_de_cada_ano_e_em_relacao_ao_ano_de_baixo(self):
        anos = self.montar(periodo="livre", de="2026-08", ate="2026-08").anos
        # 1.050 contra 850: 24%. E 850 contra 550: 55%.
        self.assertEqual(anos[0].variacao, 24)
        self.assertEqual(anos[1].variacao, 55)
        self.assertIsNone(anos[-1].variacao, "o ano mais velho não tem com o que comparar")

    def test_o_ano_de_cima_bate_com_o_cartao_do_periodo(self):
        """Número diferente para o mesmo período, na mesma tela, é defeito."""
        dados = self.montar(periodo="livre", de="2026-08", ate="2026-08")
        self.assertEqual(dados.anos[0].receita, dados.receita)
        self.assertEqual(dados.anos[1].receita, dados.receita_antes)

    def test_o_filtro_da_tela_vale_para_o_quadro_ano_a_ano(self):
        dados = self.montar(periodo="livre", de="2026-08", ate="2026-08",
                            fornecedor="VIME LENZI")
        self.assertEqual(dados.anos[0].receita, Decimal("1000"))
        self.assertEqual(dados.anos[0].receita, dados.receita)

    def test_ano_mais_velho_sem_venda_nenhuma_nao_vira_barra_vazia(self):
        """A foto alcança 2021, mas uma fileira de "R$ 0,00" não diz nada a ninguém."""
        anos = self.montar(periodo="livre", de="2026-08", ate="2026-08").anos
        self.assertEqual(len(anos), 4)
        self.assertTrue(all(linha.receita > 0 for linha in anos))

    def test_a_barra_do_maior_ano_e_a_mais_cheia(self):
        anos = self.montar(periodo="livre", de="2026-08", ate="2026-08").anos
        self.assertEqual(anos[0].largura, 100)
        self.assertLess(anos[-1].largura, 100)

    def test_a_tela_mostra_o_quadro(self):
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)
        resposta = self.client.get(reverse("compras:lista"),
                                   {"periodo": "livre", "de": "2026-08", "ate": "2026-08",
                                    "comparar": "meses"})
        self.assertContains(resposta, "O mesmo período, ano a ano")
        self.assertContains(resposta, "Agosto de 2024")


class AFotoDizDesdeQuandoGuarda(BaseComparacao):
    """Comparar com meio mês do ano passado acusa crescimento que não existe."""

    def setUp(self):
        super().setUp()
        self.produto("1", descricao="CADEIRA")
        self.mes("1", 2026, 8, 10, 1000)
        self.mes("1", 2025, 8, 4, 400)

    def test_periodo_que_nao_cabe_inteiro_na_foto_nao_compara(self):
        self.importacao.mes_a_mes_desde = date(2025, 7, 1)
        self.importacao.save()
        dados = self.montar(periodo="12m")
        self.assertTrue(dados.falta_historico)
        self.assertFalse(dados.tem_historico)
        self.assertEqual(dados.receita_antes, Decimal("0"))
        self.assertIn("14 meses", dados.falta_historico)

    def test_foto_antiga_despreza_o_mes_mais_antigo(self):
        """Até a 1.29.0 a leitura começava no meio do mês e a foto não dizia onde."""
        self.importacao.mes_a_mes_desde = None
        self.importacao.save()
        limites = comparacao._limites(self.importacao)
        self.assertEqual(limites, ((2026, 8), (2026, 8)))

    def test_a_tela_explica_em_vez_de_mostrar_numero_errado(self):
        self.importacao.mes_a_mes_desde = date(2025, 7, 1)
        self.importacao.save()
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)
        resposta = self.client.get(reverse("compras:lista"), {"periodo": "12m"})
        self.assertContains(resposta, "Escolha um período mais curto")
        self.assertNotContains(resposta, "Diferença")
