"""A lista de compra: o que comprar antes de faltar, e de quem."""

from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.compras import lista_de_compra as lista_servicos
from apps.compras.lista_de_compra import Urgencia
from apps.compras.limite import Teto
from apps.contas.perfis import ADMINISTRACAO, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.fornecedores.models import Fornecedor
from apps.importacao.models import Importacao, ProdutoImportado

CORTE = date(2026, 9, 20)


class BaseLista(TestCase):
    def setUp(self):
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO,
            situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(),
            data_corte=CORTE,
            dias_abertos_12m=360,
            produtos=0,
        )

    def produto(self, codigo, **campos):
        padrao = dict(
            importacao=self.importacao, codigo=codigo, descricao=f"PRODUTO {codigo}",
            grupo="TAPETE", fornecedor="GERMAN", custo=Decimal("10"),
            preco_venda=Decimal("25"), estoque=Decimal("0"), vendas_12m=Decimal("360"),
            receita_12m=Decimal("9000"),
        )
        padrao.update(campos)
        return ProdutoImportado.objects.create(**padrao)

    def montar(self, **kwargs):
        return lista_servicos.montar(self.importacao, **kwargs)


class TestQuemEntraNaLista(BaseLista):
    def test_produto_zerado_que_vende_entra_e_vem_marcado_como_faltando(self):
        self.produto("1")
        lista = self.montar()
        item = lista.fornecedores[0].itens[0]
        self.assertEqual(item.urgencia, Urgencia.FALTANDO)
        self.assertEqual(lista.faltando, 1)

    def test_estoque_cheio_nao_entra(self):
        """Um ano de estoque na prateleira não é assunto da lista de compra."""
        self.produto("1", estoque=Decimal("400"))
        self.assertFalse(self.montar().tem_itens)

    def test_mercadoria_a_caminho_tira_o_produto_da_lista(self):
        """Compra Pendente no SET já vem vindo: mandar comprar de novo seria comprar dobrado."""
        self.produto("1", pedido_em_aberto=Decimal("200"))
        self.assertFalse(self.montar().tem_itens)

    def test_o_minimo_cadastrado_no_set_puxa_o_ponto_de_pedido_para_cima(self):
        """A loja preencheu o mínimo: o sistema nunca sugere comprar abaixo dele."""
        sem_minimo = self.montar()
        self.produto("1", estoque=Decimal("30"), estoque_minimo_set=Decimal("100"))
        com_minimo = self.montar()
        self.assertFalse(sem_minimo.tem_itens)
        self.assertTrue(com_minimo.tem_itens)
        item = com_minimo.fornecedores[0].itens[0]
        self.assertEqual(item.urgencia, Urgencia.ABAIXO_DO_MINIMO)
        self.assertGreaterEqual(item.ponto_de_pedido, Decimal("100"))

    def test_produto_que_nunca_vendeu_e_sem_minimo_fica_fora(self):
        """Produto morto é assunto da tela de Sugestões, não da lista de compra."""
        self.produto("1", vendas_12m=Decimal("0"), receita_12m=Decimal("0"),
                     estoque=Decimal("0"))
        self.assertFalse(self.montar().tem_itens)

    def test_consumo_proprio_e_diversos_ficam_de_fora(self):
        self.produto("1", grupo="CONSUMO PROPRIO")
        self.produto("2", descricao="DIVERSOS")
        self.assertFalse(self.montar().tem_itens)

    def test_quanto_comprar_desconta_o_que_ja_esta_na_loja_e_o_que_vem_a_caminho(self):
        self.produto("1", estoque=Decimal("5"), pedido_em_aberto=Decimal("5"))
        item = self.montar().fornecedores[0].itens[0]
        sozinho = self.produto("2", estoque=Decimal("5"))
        del sozinho
        outro = [i for i in self.montar().fornecedores[0].itens if i.codigo == "2"][0]
        self.assertLess(item.comprar, outro.comprar)


class TestPrazo(BaseLista):
    def test_usa_o_prazo_que_a_gerencia_informou_na_ficha(self):
        Fornecedor.objects.create(nome="GERMAN", prazo_dias=30)
        self.produto("1")
        bloco = self.montar().fornecedores[0]
        self.assertEqual(bloco.prazo_dias, 30)
        self.assertFalse(bloco.prazo_assumido)

    def test_sem_prazo_informado_usa_o_medido_do_set(self):
        self.produto("1", prazo_reposicao_dias=4)
        bloco = self.montar().fornecedores[0]
        self.assertEqual(bloco.prazo_dias, 4)
        self.assertFalse(bloco.prazo_assumido)

    def test_sem_prazo_nenhum_assume_um_e_diz_que_assumiu(self):
        """O SET grava a data da nota, não o prazo, então o medido quase sempre dá zero."""
        self.produto("1", prazo_reposicao_dias=0)
        bloco = self.montar().fornecedores[0]
        self.assertEqual(bloco.prazo_dias, lista_servicos.PRAZO_PADRAO_DIAS)
        self.assertTrue(bloco.prazo_assumido)
        self.assertEqual(self.montar().sem_prazo_informado, 1)

    def test_prazo_maior_manda_comprar_mais(self):
        self.produto("1", estoque=Decimal("20"))
        curto = self.montar().fornecedores[0].itens[0].comprar
        Fornecedor.objects.create(nome="GERMAN", prazo_dias=60)
        longo = self.montar().fornecedores[0].itens[0].comprar
        self.assertGreater(longo, curto)


class TestAgrupamentoEOrdem(BaseLista):
    def test_agrupa_por_fornecedor_e_soma_o_custo(self):
        self.produto("1", fornecedor="GERMAN", custo=Decimal("10"))
        self.produto("2", fornecedor="VIME LENZI", custo=Decimal("5"))
        lista = self.montar()
        nomes = [bloco.nome for bloco in lista.fornecedores]
        self.assertEqual(sorted(nomes), ["GERMAN", "VIME LENZI"])
        self.assertEqual(lista.valor, sum(b.valor for b in lista.fornecedores))

    def test_produto_sem_fornecedor_vai_para_um_bloco_proprio(self):
        self.produto("1", fornecedor="")
        lista = self.montar()
        self.assertEqual(lista.fornecedores[0].nome, lista_servicos.SEM_FORNECEDOR)
        self.assertEqual(lista.sem_fornecedor, 1)

    def test_dentro_do_fornecedor_o_que_falta_vem_antes(self):
        self.produto("1", estoque=Decimal("30"), estoque_minimo_set=Decimal("100"),
                     receita_12m=Decimal("90000"))
        self.produto("2", estoque=Decimal("0"), receita_12m=Decimal("10"))
        itens = self.montar().fornecedores[0].itens
        self.assertEqual(itens[0].codigo, "2")


class TestOComecoDaLista(BaseLista):
    def _teto(self, sobra):
        return Teto(mensal=Decimal("60000"), comprado=Decimal("0"), sobra=Decimal(sobra))

    def test_enche_o_que_cabe_no_mes_e_deixa_o_resto_para_depois(self):
        for numero in range(1, 6):
            self.produto(str(numero), fornecedor=f"FORNECEDOR {numero}",
                         estoque=Decimal("0"), vendas_12m=Decimal("360"),
                         receita_12m=Decimal(10000 - numero))
        lista = lista_servicos.priorizar(self.montar(), self._teto("1000"))
        self.assertGreaterEqual(len(lista.primeiro), 1)
        self.assertLessEqual(lista.valor_primeiro, Decimal("1000") + lista.primeiro[0].valor)
        self.assertEqual(lista.resto, len(lista.fornecedores) - len(lista.primeiro))

    def test_o_fornecedor_que_tapa_o_maior_buraco_vem_primeiro(self):
        self.produto("1", fornecedor="POUCO", receita_12m=Decimal("100"))
        self.produto("2", fornecedor="MUITO", receita_12m=Decimal("90000"))
        lista = lista_servicos.priorizar(self.montar(), self._teto("50000"))
        self.assertEqual(lista.primeiro[0].nome, "MUITO")

    def test_quem_nao_tem_fornecedor_no_set_nunca_entra_no_comece_por_aqui(self):
        """Não dá para ligar para um fornecedor que não existe."""
        self.produto("1", fornecedor="", receita_12m=Decimal("90000"))
        self.produto("2", fornecedor="GERMAN", receita_12m=Decimal("100"))
        lista = lista_servicos.priorizar(self.montar(), self._teto("50000"))
        self.assertEqual([b.nome for b in lista.primeiro], ["GERMAN"])

    def test_mes_estourado_marca_a_lista_e_mostra_so_o_que_falta(self):
        self.produto("1")
        lista = lista_servicos.priorizar(self.montar(), self._teto("-500"))
        self.assertTrue(lista.estourou_o_mes)
        self.assertEqual(lista.cabe_no_mes, Decimal("0"))

    def test_o_contrapeso_diz_quanto_ja_esta_parado_daquele_fornecedor(self):
        """O sistema não manda comprar mais de quem a loja já comprou errado sem dizer."""
        self.produto("1", fornecedor="GERMAN")
        self.produto("parado", fornecedor="GERMAN", estoque=Decimal("10"),
                     vendas_12m=Decimal("0"), receita_12m=Decimal("0"), custo=Decimal("30"))
        lista = lista_servicos.priorizar(self.montar(), self._teto("50000"))
        bloco = lista.primeiro[0]
        self.assertEqual(bloco.parado_na_prateleira, Decimal("300.00"))
        self.assertEqual(bloco.itens_parados, 1)

    def test_sem_teto_nenhum_a_lista_continua_de_pe(self):
        self.produto("1")
        lista = lista_servicos.priorizar(self.montar(), None)
        self.assertEqual(lista.cabe_no_mes, Decimal("0"))


class TestFiltros(BaseLista):
    def setUp(self):
        super().setUp()
        self.produto("1", fornecedor="GERMAN")
        self.produto("2", fornecedor="VIME LENZI", estoque=Decimal("30"),
                     estoque_minimo_set=Decimal("100"))

    def test_filtra_por_fornecedor(self):
        lista = self.montar(fornecedor="GERMAN")
        self.assertEqual([b.nome for b in lista.fornecedores], ["GERMAN"])
        self.assertEqual(lista.filtro_fornecedor, "GERMAN")

    def test_filtra_por_situacao(self):
        lista = self.montar(urgencia=Urgencia.ABAIXO_DO_MINIMO)
        self.assertEqual(lista.quantos, 1)
        self.assertEqual(lista.fornecedores[0].itens[0].codigo, "2")

    def test_filtro_inventado_e_ignorado_em_vez_de_zerar_a_tela(self):
        self.assertEqual(self.montar(fornecedor="NINGUEM").quantos, 2)
        self.assertEqual(self.montar(urgencia="urgentissimo").quantos, 2)

    def test_a_caixa_de_fornecedores_lista_todos_mesmo_com_filtro(self):
        lista = self.montar(fornecedor="GERMAN")
        self.assertEqual(lista.nomes_de_fornecedor, ["GERMAN", "VIME LENZI"])


class TestArquivo(BaseLista):
    def test_o_arquivo_tem_cabecalho_e_uma_linha_por_produto(self):
        self.produto("1")
        self.produto("2")
        linhas = lista_servicos.em_linhas(self.montar())
        self.assertEqual(linhas[0][0], "Fornecedor")
        self.assertEqual(len(linhas), 3)

    def test_o_arquivo_leva_a_lista_inteira_e_nao_so_o_que_a_tela_mostra(self):
        for numero in range(lista_servicos.POR_FORNECEDOR + 5):
            self.produto(f"p{numero}")
        lista = self.montar()
        self.assertEqual(len(lista.fornecedores[0].mostrados), lista_servicos.POR_FORNECEDOR)
        self.assertEqual(len(lista_servicos.em_linhas(lista)) - 1,
                         lista_servicos.POR_FORNECEDOR + 5)


class TestTela(BaseLista):
    def setUp(self):
        super().setUp()
        self.produto("1")
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)

    def test_a_tela_abre_com_o_comece_por_aqui(self):
        """Com um fornecedor só, o título vai no singular: "estes 1 fornecedores" é desleixo."""
        resposta = self.client.get(reverse("compras:lista"))
        self.assertContains(resposta, "Comece por este fornecedor")
        self.assertContains(resposta, "Gerar o pedido deste fornecedor")
        self.assertContains(resposta, "GERMAN")

    def test_com_mais_de_um_fornecedor_o_titulo_vai_no_plural(self):
        self.produto("2", fornecedor="OUTRO FORNECEDOR")
        resposta = self.client.get(reverse("compras:lista"))
        self.assertContains(resposta, "Comece por estes 2 fornecedores")
        self.assertContains(resposta, "Gerar os pedidos destes 2 fornecedores")

    def test_a_tela_explica_que_o_saldo_e_estimativa(self):
        """A loja nunca fez contagem física: o número de estoque não pode ser vendido como certo."""
        resposta = self.client.get(reverse("compras:lista"))
        self.assertContains(resposta, "estimativa")

    def test_o_arquivo_sai_em_csv_para_abrir_no_excel(self):
        resposta = self.client.get(reverse("compras:lista_em_arquivo"))
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("text/csv", resposta["Content-Type"])
        self.assertIn("attachment", resposta["Content-Disposition"])
        corpo = resposta.content.decode("utf-8")
        self.assertTrue(corpo.startswith("﻿"))
        self.assertIn("Fornecedor;", corpo)
        self.assertIn("PRODUTO 1", corpo)

    def test_o_arquivo_respeita_o_filtro_da_tela(self):
        self.produto("2", fornecedor="OUTRO")
        resposta = self.client.get(reverse("compras:lista_em_arquivo"), {"fornecedor": "OUTRO"})
        corpo = resposta.content.decode("utf-8")
        self.assertIn("PRODUTO 2", corpo)
        self.assertNotIn("PRODUTO 1", corpo)

    def test_vendedor_nao_abre_a_lista_de_compra(self):
        self.client.logout()
        usuario("balcao", VENDEDOR)
        self.client.login(username="balcao", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("compras:lista")).status_code, 403)
        self.assertEqual(self.client.get(reverse("compras:lista_em_arquivo")).status_code, 403)

    def test_sem_importacao_a_tela_nao_quebra(self):
        Importacao.objects.all().delete()
        resposta = self.client.get(reverse("compras:lista"))
        self.assertContains(resposta, "Nada para comprar")

    def test_a_lista_esta_no_menu(self):
        resposta = self.client.get(reverse("painel:painel"))
        self.assertContains(resposta, reverse("compras:lista"))


class TestOEstoqueExplicado(BaseLista):
    """A conta do estoque na linha, pedida pelo Edson em 14/10/2026.

    *"exiba uma sugestão de compra analisando o que foi comprado de um determinado produto
    e o que foi vendido e o resultado que seria o estoque"*. Antes a linha mostrava TEM, A
    CAMINHO, MÍNIMO e COMPRAR, e nenhum desses números explicava o outro.
    """

    def setUp(self):
        super().setUp()
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)

    def test_a_linha_diz_o_que_entrou_o_que_saiu_e_onde_parou(self):
        self.produto("1", compras_12m=Decimal("50"), vendas_12m=Decimal("360"),
                     estoque=Decimal("-20"))
        corpo = self.client.get(reverse("compras:lista")).content.decode("utf-8")
        self.assertIn("Em 12 meses comprou 50", corpo)
        self.assertIn("vendeu 360", corpo)
        self.assertIn("o estoque caiu 310", corpo)

    def test_a_linha_explica_que_a_compra_conta_o_saldo_negativo_como_zero(self):
        """TEM -20 e COMPRAR pouco na mesma linha não fecham sem esta frase."""
        self.produto("1", estoque=Decimal("-20"))
        corpo = self.client.get(reverse("compras:lista")).content.decode("utf-8")
        self.assertIn("conta como zero na compra", corpo)
        self.assertIn("já estão na média", corpo)

    def test_a_tela_conta_quantas_linhas_tem_saldo_negativo(self):
        self.produto("1", estoque=Decimal("-20"))
        self.produto("2", estoque=Decimal("-5"))
        self.produto("3")
        resposta = self.client.get(reverse("compras:lista"))
        self.assertEqual(resposta.context["lista"].com_saldo_negativo, 2)
        self.assertContains(resposta, "comprar a mesma venda duas vezes")

    def test_sem_saldo_negativo_a_tela_nao_diz_nada_disso(self):
        self.produto("1")
        resposta = self.client.get(reverse("compras:lista"))
        self.assertEqual(resposta.context["lista"].com_saldo_negativo, 0)
        self.assertNotContains(resposta, "conta como zero na compra")

    def test_a_linha_diz_quanto_tempo_a_quantidade_cobre_e_quanto_prende(self):
        """A frase que julga o número: quem digitou 70 lê quantos anos isso cobre."""
        self.produto("1")
        corpo = self.client.get(reverse("compras:lista")).content.decode("utf-8")
        self.assertIn("cobre", corpo)
        self.assertIn("de venda", corpo)
        self.assertIn("prende", corpo)

    def test_quantidade_que_cobre_mais_de_um_ano_vem_marcada(self):
        item = lista_servicos.ItemDaLista(
            codigo="1", descricao="PRATO", grupo="", fornecedor="GERMAN",
            urgencia=Urgencia.FALTANDO, estoque=Decimal("0"), a_caminho=Decimal("0"),
            comprar=Decimal("16"), demanda_diaria=Decimal("1") / Decimal("356"),
            custo=Decimal("70"))
        self.assertTrue(item.quantidade_cobre_mais_de_um_ano)
        self.assertEqual(item.quanto_tempo_a_quantidade_dura, "15,6 anos")

    def test_quantidade_normal_sai_em_dias_e_nao_vem_marcada(self):
        item = lista_servicos.ItemDaLista(
            codigo="1", descricao="TAPETE", grupo="", fornecedor="GERMAN",
            urgencia=Urgencia.FALTANDO, estoque=Decimal("0"), a_caminho=Decimal("0"),
            comprar=Decimal("30"), demanda_diaria=Decimal("1"), custo=Decimal("10"))
        self.assertFalse(item.quantidade_cobre_mais_de_um_ano)
        self.assertEqual(item.quanto_tempo_a_quantidade_dura, "30 dias")

    def test_sem_venda_nenhuma_nao_ha_o_que_dizer_sobre_duracao(self):
        item = lista_servicos.ItemDaLista(
            codigo="1", descricao="TAPETE", grupo="", fornecedor="GERMAN",
            urgencia=Urgencia.FALTANDO, estoque=Decimal("0"), a_caminho=Decimal("0"),
            comprar=Decimal("2"))
        self.assertEqual(item.quanto_tempo_a_quantidade_dura, "")
        self.assertFalse(item.quantidade_cobre_mais_de_um_ano)

    def test_a_duracao_fala_da_quantidade_escolhida_e_nao_da_sugerida(self):
        """Quem muda o número no campo tem que ver a frase mudar com ele."""
        item = lista_servicos.ItemDaLista(
            codigo="1", descricao="TAPETE", grupo="", fornecedor="GERMAN",
            urgencia=Urgencia.FALTANDO, estoque=Decimal("0"), a_caminho=Decimal("0"),
            comprar=Decimal("2"), a_mais=Decimal("118"), demanda_diaria=Decimal("1"),
            custo=Decimal("10"))
        self.assertEqual(item.quanto_tempo_a_quantidade_dura, "4 meses")
        self.assertEqual(item.valor_do_pedido, Decimal("1200.00"))


class TestAMediaDoPeriodoNaTela(BaseLista):
    """O filtro de período que o Edson pediu em 14/10/2026, visto da tela."""

    def setUp(self):
        super().setUp()
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)

    def test_a_tela_oferece_as_quatro_janelas(self):
        self.produto("1")
        resposta = self.client.get(reverse("compras:lista"))
        self.assertContains(resposta, "Média de venda de")
        for rotulo in ("12 meses", "6 meses", "3 meses", "30 dias"):
            self.assertContains(resposta, rotulo)

    def test_a_janela_escolhida_e_dita_uma_vez_e_nao_em_cada_linha(self):
        """Escrever "pela venda de 3 meses" em duas mil linhas é ruído."""
        self.produto("1")
        self.produto("2")
        corpo = self.client.get(reverse("compras:lista"), {"media": "90"}).content.decode("utf-8")
        self.assertEqual(corpo.count("A quantidade sugerida saiu da venda"), 1)

    def test_doze_meses_nao_escreve_nada_na_tela(self):
        self.produto("1")
        corpo = self.client.get(reverse("compras:lista")).content.decode("utf-8")
        self.assertNotIn("A quantidade sugerida saiu da venda", corpo)

    def test_a_linha_avisa_quando_a_conta_voltou_para_doze_meses(self):
        """Sem venda no período a quantidade cairia sem explicação; a linha explica."""
        self.produto("1")
        resposta = self.client.get(reverse("compras:lista"), {"media": "90"})
        self.assertContains(resposta, "a conta voltou para 12 meses")
        self.assertEqual(resposta.context["lista"].voltaram_para_12m, 1)

    def test_a_janela_entra_no_link_do_arquivo_e_nos_formularios(self):
        """Mudar o filtro e baixar o arquivo tem que dar o mesmo número da tela."""
        self.produto("1")
        corpo = self.client.get(reverse("compras:lista"), {"media": "90"}).content.decode("utf-8")
        self.assertIn("media=90", corpo)
        self.assertIn('name="media" value="90"', corpo)

    def test_janela_inventada_na_url_nao_zera_a_tela(self):
        self.produto("1")
        resposta = self.client.get(reverse("compras:lista"), {"media": "3650"})
        self.assertEqual(resposta.context["lista"].filtro_media, "")
        self.assertContains(resposta, "PRODUTO 1")


class OPrazoDoBlocoVaiImpressoNoPedido(BaseLista):
    """O prazo do bloco é o do fornecedor, não o da primeira linha que caiu nele.

    Achado na revisão geral de 15/10/2026. Sem prazo na ficha, cada produto cai no prazo
    MEDIDO no SET, que é diferente de produto para produto; o bloco copiava o da primeira
    linha iterada, e esse número sai impresso no pedido que o fornecedor recebe
    ("Prazo de entrega: 3 dias" num fornecedor cujas outras linhas mediram 21). O bloco
    SEM FORNECEDOR, que junta produtos de origens diferentes, era o que mais sofria.
    """

    def test_sem_prazo_na_ficha_o_bloco_usa_o_maior_prazo_medido(self):
        self.produto("1", prazo_reposicao_dias=3)
        self.produto("2", prazo_reposicao_dias=21)
        bloco = self.montar().fornecedores[0]
        self.assertEqual(bloco.prazo_dias, 21,
                         "o pedido só está completo quando a última caixa chega")
        self.assertFalse(bloco.prazo_assumido, "os dois prazos foram medidos no SET")

    def test_uma_linha_estimada_deixa_o_bloco_marcado_como_estimado(self):
        """Senão a folha afirma um prazo que o sistema chutou, sem dizer que chutou."""
        self.produto("1", prazo_reposicao_dias=3)
        self.produto("2", prazo_reposicao_dias=None)
        bloco = self.montar().fornecedores[0]
        self.assertTrue(bloco.prazo_assumido)
        self.assertEqual(bloco.prazo_dias, lista_servicos.PRAZO_PADRAO_DIAS)

    def test_prazo_informado_na_ficha_manda_em_todas_as_linhas(self):
        """O caminho normal: a ficha preenchida vale mais que o medido, e nada muda aqui."""
        Fornecedor.objects.create(nome="GERMAN", prazo_dias=12)
        self.produto("1", prazo_reposicao_dias=3)
        self.produto("2", prazo_reposicao_dias=21)
        bloco = self.montar().fornecedores[0]
        self.assertEqual(bloco.prazo_dias, 12)
        self.assertFalse(bloco.prazo_assumido)

    def test_o_papel_do_pedido_leva_o_prazo_do_bloco(self):
        self.produto("1", prazo_reposicao_dias=3)
        self.produto("2", prazo_reposicao_dias=21)
        bloco = self.montar().fornecedores[0]
        self.assertIn(f"{bloco.prazo_dias} dias", f"{bloco.prazo_dias} dias")
        self.assertEqual(bloco.prazo_dias, max(i.prazo_dias for i in bloco.itens))


class ADecisaoVemAntesDaExplicacao(BaseLista):
    """Pedido do Edson em 19/10/2026, sobre o sistema inteiro.

    *"o sistema está trazendo muitas informações, deixando os gestores confusos.
    precisamos que seja mais objetivos (...) imagine os gestores em viagem, precisando
    tomar uma decisão rápida para comprar."*

    "Como esta lista é feita" ficava ENTRE o cartão que diz por onde começar e a lista
    em si: quem abria a tela para comprar atravessava trinta linhas de regra antes de
    chegar na tabela. A explicação continua inteira, fechada e no fim.
    """

    def setUp(self):
        super().setUp()
        self.produto("1", fornecedor="VIME LENZI", descricao="CADEIRA DE VIME")
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)

    def _corpo(self):
        return self.client.get(reverse("compras:lista")).content.decode()

    def test_a_explicacao_fica_depois_da_lista(self):
        corpo = self._corpo()
        self.assertLess(corpo.index("Comece por est"), corpo.index("Lista completa"))
        self.assertLess(corpo.index("Lista completa"), corpo.index("Como esta lista é feita"))

    def test_a_explicacao_nasce_fechada(self):
        """Fechada quer dizer <details> sem `open`: continua lá, não ocupa a tela."""
        corpo = self._corpo()
        bloco = corpo[corpo.index("explicacao-da-lista"):]
        abertura = bloco[:bloco.index(">") + 1]
        self.assertNotIn("open", abertura)

    def test_a_explicacao_continua_inteira(self):
        """Recolher não é apagar: quem quer entender a regra abre e lê o mesmo texto."""
        corpo = self._corpo()
        self.assertIn("ponto de pedido", corpo)
        self.assertIn("nunca fez contagem física", corpo.replace("&#x27;", "'"))


class TestOGiroDos90Dias(BaseLista):
    """Pedido dele em 20/10/2026, seção 6: "Vendas em 90 dias | Avaliação do giro".

    O número já vinha importado do SET e não chegava a esta tela. A frase compara com o
    ritmo do ano porque "9 em 90 dias" sozinho não diz se é muito ou pouco.
    """

    def linha(self, **campos):
        self.produto("0001", **campos)
        return self.montar().fornecedores[0].itens[0]

    def test_no_ritmo_do_ano_quando_os_90_dias_sao_um_quarto_do_ano(self):
        linha = self.linha(vendas_12m=Decimal("360"), vendas_90d=Decimal("90"))
        self.assertIn("no ritmo do ano", linha.giro_dos_90_dias)

    def test_acima_do_ritmo_quando_acelerou_mais_de_um_quinto(self):
        linha = self.linha(vendas_12m=Decimal("360"), vendas_90d=Decimal("150"))
        self.assertIn("acima do ritmo do ano", linha.giro_dos_90_dias)
        self.assertIn("90", linha.giro_dos_90_dias)  # o que seria o normal

    def test_abaixo_do_ritmo_quando_parou(self):
        linha = self.linha(vendas_12m=Decimal("360"), vendas_90d=Decimal("30"))
        self.assertIn("abaixo do ritmo do ano", linha.giro_dos_90_dias)

    def test_diferenca_pequena_e_ruido_de_calendario_e_nao_vira_frase_de_alerta(self):
        """Um quinto é o mesmo freio do fator do ano passado: abaixo disso é calendário."""
        linha = self.linha(vendas_12m=Decimal("360"), vendas_90d=Decimal("100"))
        self.assertIn("no ritmo do ano", linha.giro_dos_90_dias)

    def test_nada_em_90_dias_e_dito_com_todas_as_letras(self):
        linha = self.linha(vendas_12m=Decimal("360"), vendas_90d=Decimal("0"))
        self.assertEqual(linha.giro_dos_90_dias, "nada nos últimos 90 dias")

    def test_sem_venda_no_ano_e_sem_venda_nos_90_dias_nao_ha_frase_a_dizer(self):
        linha = lista_servicos.ItemDaLista(
            codigo="0001", descricao="PRODUTO", grupo="TAPETE", fornecedor="GERMAN",
            urgencia=Urgencia.VAI_FALTAR, estoque=Decimal("0"), a_caminho=Decimal("0"))
        self.assertEqual(linha.giro_dos_90_dias, "")

    def test_a_frase_aparece_na_tela(self):
        self.produto("0001", vendas_12m=Decimal("360"), vendas_90d=Decimal("30"))
        usuario("edson", ADMINISTRACAO)
        self.client.login(username="edson", password=SENHA_TESTE)
        tela = self.client.get(reverse("compras:lista"))
        self.assertContains(tela, "abaixo do ritmo do ano")


class TestAContaDaReposicaoNaTela(BaseLista):
    """Pedido dele em 20/10/2026, seção 4: "diferenciar claramente" os cinco números.

    O sistema calculava os cinco e a tela mostrava dois — a coluna "Mínimo" é o mínimo
    do SET, que é outra coisa.
    """

    def test_os_tres_numeros_que_faltavam_chegam_na_linha(self):
        self.produto("0001", vendas_12m=Decimal("360"))
        linha = self.montar().fornecedores[0].itens[0]
        self.assertGreater(linha.estoque_seguranca, 0)
        self.assertGreater(linha.ponto_de_pedido, 0)
        self.assertIsNotNone(linha.estoque_alvo)
        self.assertGreater(linha.estoque_alvo, linha.ponto_de_pedido)

    def test_alvo_abaixo_de_uma_unidade_nao_escreve_conta_nenhuma(self):
        """Produto que vende 2 por ano tinha "estoque de segurança 0,0392" na tela.

        Número assim não explica nada e faz a linha parecer defeito. Nesse caso quem
        decide a quantidade é o arredondamento para a unidade inteira, não a fórmula:
        a linha cala, em vez de gastar três linhas dizendo o que não muda a decisão.
        """
        self.produto("0001", vendas_12m=Decimal("2"))
        linha = self.montar().fornecedores[0].itens[0]
        self.assertLess(linha.estoque_alvo, 1)
        self.assertEqual(linha.conta_da_reposicao, "")
        self.assertEqual(linha.comprar, Decimal("1"))

    def test_a_conta_nao_joga_quatro_casas_decimais_na_tela(self):
        self.produto("0001", vendas_12m=Decimal("360"))
        frase = self.montar().fornecedores[0].itens[0].conta_da_reposicao
        for pedaco in frase.split(" · "):
            numero = pedaco.rsplit(" ", 1)[-1]
            if "," in numero:
                self.assertLessEqual(len(numero.split(",")[1]), 2, frase)

    def test_a_frase_traz_os_quatro_rotulos_e_fecha_a_conta(self):
        self.produto("0001", vendas_12m=Decimal("360"))
        linha = self.montar().fornecedores[0].itens[0]
        for rotulo in ("estoque de segurança", "ponto de reposição",
                       "disponível com o que está a caminho", "estoque-alvo"):
            self.assertIn(rotulo, linha.conta_da_reposicao)
        # alvo − disponível é a quantidade sugerida, arredondada para cima.
        self.assertEqual(
            linha.comprar,
            (linha.estoque_alvo - linha.posicao_estoque).to_integral_value(rounding="ROUND_CEILING"))

    def test_a_seguranca_sai_da_mesma_demanda_que_decidiu_a_compra(self):
        """Senão a soma escrita na tela não fecha com o ponto de reposição."""
        self.produto("0001", vendas_12m=Decimal("360"), prazo_reposicao_dias=10)
        linha = self.montar().fornecedores[0].itens[0]
        demanda = linha.demanda_diaria * linha.fator_de_estacao
        self.assertEqual(linha.ponto_de_pedido,
                         (demanda * 10 + linha.estoque_seguranca).quantize(Decimal("0.01")))

    def test_produto_sem_demanda_nao_inventa_conta(self):
        """Linha sem demanda nem entra na lista; se entrasse, não escreveria conta nenhuma."""
        linha = lista_servicos.ItemDaLista(
            codigo="0001", descricao="PRODUTO", grupo="TAPETE", fornecedor="GERMAN",
            urgencia=Urgencia.VAI_FALTAR, estoque=Decimal("0"), a_caminho=Decimal("0"))
        self.assertEqual(linha.conta_da_reposicao, "")
        self.assertEqual(linha.giro_dos_90_dias, "")

    def test_a_conta_aparece_na_tela(self):
        self.produto("0001", vendas_12m=Decimal("360"))
        usuario("edson", ADMINISTRACAO)
        self.client.login(username="edson", password=SENHA_TESTE)
        tela = self.client.get(reverse("compras:lista"))
        self.assertContains(tela, "ponto de reposição")
        self.assertContains(tela, "estoque-alvo")
