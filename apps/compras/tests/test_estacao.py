"""O mesmo período do ano passado entrando na quantidade sugerida (pedido do Edson, 14/10/2026).

A loja vende por estação. A sugestão nascia de uma média plana de doze meses, que manda
comprar de menos antes de a estação começar e de mais depois que ela passou. Aqui se
prova que o ajuste existe, que ele tem freio, e que ele não mexe no resto da tela.
"""

import re
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.compras import calculos, estacao, lista_de_compra
from apps.importacao.models import Importacao, ProdutoImportado, VendaMensalDoProduto

CORTE = date(2026, 9, 20)
# O dia em que o pedido está sendo feito, em todos os testes.
HOJE = date(2026, 10, 14)


class PedacoDeMes(TestCase):
    """A venda vem somada por mês; a janela do pedido começa no meio de um."""

    def test_o_mes_inteiro_dentro_da_janela_conta_inteiro(self):
        self.assertEqual(estacao._parte_do_mes(2025, 11, date(2025, 10, 1), date(2025, 12, 31)),
                         Decimal("1"))

    def test_metade_de_outubro_conta_pela_metade(self):
        parte = estacao._parte_do_mes(2025, 10, date(2025, 10, 17), date(2025, 10, 31))
        self.assertEqual(parte, Decimal(15) / Decimal(31))

    def test_mes_fora_da_janela_nao_conta(self):
        self.assertEqual(estacao._parte_do_mes(2025, 8, date(2025, 10, 1), date(2025, 10, 31)),
                         Decimal("0"))

    def test_29_de_fevereiro_recua_para_28(self):
        """Ano bissexto: 29/02/2028 um ano antes não existe, e o calendário manda."""
        self.assertEqual(estacao._um_ano_antes(date(2028, 2, 29)), date(2027, 2, 28))
        self.assertEqual(estacao._um_ano_antes(date(2026, 10, 14)), date(2025, 10, 14))

    def test_a_base_sao_os_doze_meses_anteriores(self):
        base = estacao._meses_antes(2025, 10, 12)
        self.assertEqual(base[0], (2024, 10))
        self.assertEqual(base[-1], (2025, 9))
        self.assertEqual(len(base), 12)


class BaseEstacao(TestCase):
    def setUp(self):
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO,
            situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(),
            data_corte=CORTE,
            mes_a_mes_desde=date(2021, 9, 1),
            dias_abertos_12m=360,
            produtos=0,
        )

    def produto(self, codigo="1", **campos):
        padrao = dict(
            importacao=self.importacao, codigo=codigo, descricao=f"PRODUTO {codigo}",
            grupo="MOVEIS", fornecedor="VIME LENZI", custo=Decimal("10"),
            preco_venda=Decimal("25"), estoque=Decimal("0"), vendas_12m=Decimal("120"),
        )
        padrao.update(campos)
        return ProdutoImportado.objects.create(**padrao)

    def mes(self, codigo, ano, mes, unidades):
        """Grava (ou regrava) a venda daquele mês: os testes mexem em meses da base."""
        linha, _ = VendaMensalDoProduto.objects.update_or_create(
            importacao=self.importacao, codigo=codigo, ano=ano, mes=mes,
            defaults={"unidades": Decimal(unidades), "receita": Decimal(unidades) * 25},
        )
        return linha

    def ano_inteiro(self, codigo, por_mes):
        """Os doze meses da base (out/2024 a set/2025) com a mesma venda todo mês."""
        for ano, mes in estacao._meses_antes(2025, 10, 12):
            self.mes(codigo, ano, mes, por_mes)

    def fator_de(self, codigo="1", dias=29):
        tabela = estacao.montar(self.importacao, self.importacao.itens.all(), hoje=HOJE)
        return tabela.para(codigo, dias, HOJE)


class OFator(BaseEstacao):
    def test_periodo_igual_a_media_nao_mexe_em_nada(self):
        """Vendeu o mesmo todo mês: o ano passado não tem nada a dizer, e cala."""
        self.produto()
        self.ano_inteiro("1", 10)
        self.mes("1", 2025, 10, 10)
        self.mes("1", 2025, 11, 10)
        self.assertIsNone(self.fator_de())

    def test_diferenca_pequena_nao_vira_estacao(self):
        """Mês de 30 contra mês de 31 não é estação; sem isto a tela viveria avisando."""
        self.produto()
        self.ano_inteiro("1", 10)
        self.mes("1", 2025, 10, 11)
        self.mes("1", 2025, 11, 10)
        self.assertIsNone(self.fator_de())

    def test_estacao_forte_no_ano_passado_sobe_a_quantidade(self):
        """Dez por mês o ano inteiro e quinze nesta época: o pedido de outubro sobe."""
        self.produto()
        self.ano_inteiro("1", 10)
        self.mes("1", 2025, 10, 15)
        self.mes("1", 2025, 11, 15)
        fator = self.fator_de()
        self.assertTrue(fator.mais_forte)
        self.assertEqual(fator.vezes, Decimal("1.5"))
        self.assertLess(fator.fator, estacao.TETO)   # é a conta, não o freio

    def test_periodo_mais_fraco_desce_a_quantidade_sem_chegar_ao_piso(self):
        """O caso mais comum no dado real da loja: a época foi um pouco mais fraca."""
        self.produto()
        self.ano_inteiro("1", 10)
        self.mes("1", 2025, 10, 7)
        self.mes("1", 2025, 11, 7)
        fator = self.fator_de()
        self.assertFalse(fator.mais_forte)
        self.assertEqual(fator.vezes, Decimal("0.7"))
        self.assertGreater(fator.fator, estacao.PISO)

    def test_estacao_fraca_no_ano_passado_desce_a_quantidade(self):
        """Vendeu tudo no verão e nada agora: o teto do mês vale mais em outro produto."""
        self.produto()
        self.ano_inteiro("1", 1)
        self.mes("1", 2025, 1, 200)
        self.mes("1", 2025, 10, 0)
        self.mes("1", 2025, 11, 0)
        fator = self.fator_de()
        self.assertEqual(fator.fator, estacao.PISO)
        self.assertFalse(fator.mais_forte)

    def test_o_fator_nunca_passa_do_teto(self):
        """Sem freio, uma semana boa do ano passado mandaria comprar trinta vezes mais."""
        self.produto()
        self.ano_inteiro("1", 10)       # cento e vinte unidades no ano
        self.mes("1", 2025, 10, 500)    # e quinhentas na janela: 30x sem o teto
        self.assertEqual(self.fator_de().fator, estacao.TETO)

    def test_produto_de_giro_lento_nao_ganha_fator_pela_janela(self):
        """O freio que faltava, achado no dado real da loja.

        Doze unidades no ano vendem zero na maioria das janelas de um mês, e esse zero
        é o tamanho da amostra, não a estação: sem este freio, setecentos produtos de
        giro lento desciam juntos para o piso e a lista mandava comprar menos de tudo.
        """
        self.produto()
        self.ano_inteiro("1", 1)        # doze no ano: menos de duas esperadas na janela
        self.mes("1", 2025, 10, 0)
        self.assertIsNone(self.fator_de())
        # O mesmo produto vendendo dez vezes mais já tem amostra, e aí o zero vale.
        self.ano_inteiro("1", 10)
        self.assertEqual(self.fator_de().fator, estacao.PISO)

    def test_base_zerada_nao_vira_fator_infinito(self):
        """Dividir por uma média de zero não dá estação, dá divisão por zero."""
        self.produto()
        self.ano_inteiro("1", 0)
        self.mes("1", 2025, 10, 500)
        self.assertIsNone(self.fator_de())

    def test_produto_de_pouca_venda_nao_ganha_fator(self):
        """Cinco unidades no ano não são padrão, são acaso."""
        self.produto()
        self.ano_inteiro("1", 0)
        self.mes("1", 2025, 3, 5)
        self.assertIsNone(self.fator_de())

    def test_produto_sem_venda_nenhuma_no_ano_passado_nao_ganha_fator(self):
        self.produto()
        self.assertIsNone(self.fator_de())

    def test_foto_que_nao_guarda_os_meses_inteiros_nao_ganha_fator(self):
        """Mesmo cuidado da comparação: mês pela metade mente, e aqui mentiria na quantidade."""
        self.produto()
        self.ano_inteiro("1", 10)
        self.importacao.mes_a_mes_desde = date(2025, 6, 1)
        self.importacao.save(update_fields=["mes_a_mes_desde"])
        self.assertIsNone(self.fator_de())

    def test_foto_antiga_sem_o_campo_nao_ganha_fator(self):
        self.produto()
        self.ano_inteiro("1", 10)
        self.importacao.mes_a_mes_desde = None
        self.importacao.save(update_fields=["mes_a_mes_desde"])
        self.assertIsNone(self.fator_de())

    def test_a_janela_do_fator_comeca_um_ano_antes_do_dia_do_pedido(self):
        self.produto()
        self.ano_inteiro("1", 10)
        fator = self.fator_de(dias=29)
        self.assertEqual(fator.de, date(2025, 10, 14))
        self.assertEqual(fator.ate, date(2025, 11, 11))

    def test_uma_consulta_so_para_a_lista_inteira(self):
        """Onze mil produtos vezes uma consulta cada seria a tela que não abre."""
        for codigo in ("1", "2", "3"):
            self.produto(codigo)
            self.ano_inteiro(codigo, 10)
        with self.assertNumQueries(1):
            estacao.montar(self.importacao, self.importacao.itens.all(), hoje=HOJE)


class ACompraComEstacao(TestCase):
    """O fator chegando onde importa: na quantidade que o sistema sugere."""

    def _item(self, fator="1"):
        return calculos.Item(
            sku="1", descricao="CADEIRA", estoque_utilizavel=Decimal("0"),
            vendas_liquidas=Decimal("360"), dias_janela=360,
            prazo_reposicao_dias=15, custo_unitario=Decimal("10"),
            fator_de_estacao=Decimal(fator),
        )

    def test_sem_fator_a_conta_e_a_de_sempre(self):
        resultado = calculos.calcular(self._item())
        self.assertEqual(resultado.fator_de_estacao, Decimal("1"))
        self.assertEqual(resultado.compra_sugerida, resultado.compra_sem_estacao)

    def test_fator_dois_dobra_a_quantidade(self):
        simples = calculos.calcular(self._item())
        dobrado = calculos.calcular(self._item("2"))
        self.assertEqual(dobrado.compra_sugerida, simples.compra_sugerida * 2)
        # E a tela consegue dizer de quanto para quanto.
        self.assertEqual(dobrado.compra_sem_estacao, simples.compra_sugerida)

    def test_o_motivo_conta_que_o_ano_passado_mexeu(self):
        resultado = calculos.calcular(self._item("2"))
        self.assertIn("No ano passado este mesmo período vendeu 2 vezes", resultado.motivo)

    def test_a_cobertura_e_o_excesso_continuam_na_media_do_ano(self):
        """Produto de verão não pode virar "excesso" em julho por causa do ajuste."""
        simples = calculos.calcular(self._item())
        ajustado = calculos.calcular(self._item("0.5"))
        self.assertEqual(ajustado.demanda_diaria, simples.demanda_diaria)
        self.assertEqual(ajustado.cobertura_dias, simples.cobertura_dias)
        self.assertEqual(ajustado.excesso_unidades, simples.excesso_unidades)


class ANaListaDeCompra(BaseEstacao):
    def test_a_lista_sugere_mais_de_quem_vende_nesta_epoca(self):
        self.produto(codigo="1", estoque=Decimal("0"), vendas_12m=Decimal("120"))
        self.ano_inteiro("1", 10)
        self.mes("1", 2025, 10, 60)
        self.mes("1", 2025, 11, 60)
        lista = lista_de_compra.montar(self.importacao, hoje=HOJE)
        item = lista.fornecedores[0].itens[0]
        self.assertTrue(item.estacao_mexeu)
        self.assertEqual(item.estacao_vezes, Decimal("2.0"))
        self.assertGreater(item.comprar, item.comprar_sem_estacao)

    def test_a_tela_escreve_a_sugestao_com_o_nome_dela(self):
        """Número solto dentro de um campo não diz de quem é (pedido dele, 14/10/2026).

        Desde 20/10/2026 a sugestão é a primeira parcela da soma, e o nome dela está no
        rótulo em cima do número — não mais numa frase embaixo do campo.
        """
        from django.urls import reverse

        from apps.contas.perfis import ADMINISTRACAO
        from apps.core.fabricas import SENHA_TESTE, usuario
        from apps.core.templatetags.cabana import quantidade

        self.produto(codigo="1", estoque=Decimal("0"), vendas_12m=Decimal("120"))
        self.ano_inteiro("1", 10)
        self.mes("1", 2025, 10, 60)
        self.mes("1", 2025, 11, 60)
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)
        corpo = self.client.get(reverse("compras:lista")).content.decode()
        # O texto como o olho lê, sem as quebras de linha do template no meio da frase.
        texto = re.sub(r"\s+", " ", corpo)
        self.assertIn("rotulo-da-parcela\">sugerida</span>", texto)

        item = lista_de_compra.montar(self.importacao, hoje=HOJE).fornecedores[0].itens[0]
        mudanca = f"de {quantidade(item.comprar_sem_estacao)} para {quantidade(item.comprar)}:"
        self.assertIn(mudanca, texto)
        # A MUDANÇA vem antes do MOTIVO: o fator sozinho promete mais do que entrega
        # quando o estoque está muito negativo, porque aí o grosso da compra é tapar o
        # buraco e a estação mexe só no resto.
        trecho = texto[texto.index("linha-detalhe estacao"):][:400]
        self.assertLess(trecho.index(mudanca),
                        trecho.index("no ano passado este período vendeu"))

    def test_sem_dado_do_ano_passado_a_lista_nao_inventa_fator(self):
        self.produto(codigo="1", estoque=Decimal("0"), vendas_12m=Decimal("120"))
        lista = lista_de_compra.montar(self.importacao, hoje=HOJE)
        item = lista.fornecedores[0].itens[0]
        self.assertFalse(item.estacao_mexeu)
        self.assertEqual(item.comprar, item.comprar_sem_estacao)


class AEstacaoNaoContaDuasVezes(BaseEstacao):
    """O fator do ano passado vale sobre base PLANA, e só.

    O fator conserta uma distorção só: a média de doze meses não sabe de estação. Quando
    a pessoa escolhe 30 dias no filtro, a média JÁ é a venda da estação de agora —
    multiplicar outra vez pelo fator conta a estação duas vezes e, com o teto de 2, chega
    a pedir o dobro ao fornecedor justamente no mês de pico.
    """

    def _vender(self, quando, codigo, unidades):
        from apps.importacao.models import ItemVendaImportada, VendaImportada

        quantos = VendaImportada.objects.count() + 1
        cabeca = VendaImportada.objects.create(
            importacao=self.importacao, id_set=quantos, numero=str(quantos), data=quando,
            dia_da_semana=(quando.weekday() + 1) % 7, valor=Decimal(unidades) * 25,
        )
        ItemVendaImportada.objects.create(
            venda=cabeca, codigo=codigo, descricao="PRODUTO",
            quantidade=Decimal(unidades), valor_total=Decimal(unidades) * 25)

    def _produto_de_estacao_forte(self):
        """Dez por mês o ano inteiro, sessenta nesta época: o fator bate no teto de 2."""
        self.produto(codigo="1", estoque=Decimal("0"), vendas_12m=Decimal("120"))
        self.ano_inteiro("1", 10)
        self.mes("1", 2025, 10, 60)
        self.mes("1", 2025, 11, 60)

    def test_na_media_de_doze_meses_o_fator_entra(self):
        """A régua: é este caso que o fator existe para consertar."""
        self._produto_de_estacao_forte()
        item = lista_de_compra.montar(self.importacao, hoje=HOJE).fornecedores[0].itens[0]
        self.assertTrue(item.estacao_mexeu)
        self.assertGreater(item.comprar, item.comprar_sem_estacao)

    def test_na_janela_curta_o_fator_nao_entra(self):
        self._produto_de_estacao_forte()
        # Venda de verdade dentro dos 30 dias que terminam na data de corte, para a
        # janela curta ter base própria e não cair de volta nos doze meses.
        for dias in range(0, 28, 2):
            self._vender(CORTE - timedelta(days=dias), "1", 5)

        item = lista_de_compra.montar(self.importacao, media="30",
                                      hoje=HOJE).fornecedores[0].itens[0]
        self.assertFalse(item.janela_voltou_para_12m,
                         "a janela de 30 dias tinha venda: não devia voltar para 12 meses")
        self.assertFalse(item.estacao_mexeu,
                         "com a média já saindo da estação de agora, o fator do ano "
                         "passado contaria a estação duas vezes")
        self.assertEqual(item.comprar, item.comprar_sem_estacao)

    def test_quem_volta_para_doze_meses_continua_recebendo_o_fator(self):
        """A base dele voltou a ser plana, então o fator volta a fazer sentido."""
        self._produto_de_estacao_forte()
        item = lista_de_compra.montar(self.importacao, media="30",
                                      hoje=HOJE).fornecedores[0].itens[0]
        self.assertTrue(item.janela_voltou_para_12m)
        self.assertTrue(item.estacao_mexeu)
        self.assertGreater(item.comprar, item.comprar_sem_estacao)
