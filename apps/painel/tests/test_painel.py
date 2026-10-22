from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.contas.perfis import ADMINISTRACAO
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.importacao.models import Importacao, ProdutoImportado
from apps.painel import indicadores


class PainelTest(TestCase):
    def setUp(self):
        cache.clear()
        hoje = timezone.localdate()
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO,
            situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(),
            data_corte=hoje - timedelta(days=1),
            dias_abertos_12m=300,
            dias_abertos_90d=78,
            produtos=4,
            arquivo="C:\\backup\\DADOS-SET.FDB",
            detalhe={
                "vendas_mes": [[2026, 8, 100000.0, 400], [2026, 9, 90000.0, 380]],
                "compras_mes": [[2026, 8, 70000.0, 20], [2026, 9, 120000.0, 25]],
            },
        )
        comum = {"importacao": self.importacao, "prazo_reposicao_dias": 7}
        # Comprou 100 e vendeu 40 em 12 meses: sobra comprada, não depende da contagem.
        ProdutoImportado.objects.create(
            codigo="1", descricao="CARVAO 10KG", custo=Decimal("10"), estoque=Decimal("60"),
            vendas_12m=Decimal("40"), compras_12m=Decimal("100"), receita_12m=Decimal("1200"), **comum,
        )
        # Nada vendido em 12 meses, com saldo: dinheiro parado.
        ProdutoImportado.objects.create(
            codigo="2", descricao="LEAO DE EUCALIPTO", custo=Decimal("50"), estoque=Decimal("4"),
            vendas_12m=Decimal("0"), compras_12m=Decimal("0"), **comum,
        )
        # Vende agora e está zerado: venda em risco.
        ProdutoImportado.objects.create(
            codigo="3", descricao="ACENDEDOR", custo=Decimal("2"), estoque=Decimal("0"),
            vendas_12m=Decimal("300"), vendas_90d=Decimal("80"), compras_12m=Decimal("300"),
            receita_12m=Decimal("1500"), **comum,
        )
        # Zerado, mas não vende há meses: item que saiu de linha, não é falta.
        ProdutoImportado.objects.create(
            codigo="5", descricao="BRINDE ANTIGO", custo=Decimal("3"), estoque=Decimal("0"),
            vendas_12m=Decimal("10"), vendas_90d=Decimal("0"), compras_12m=Decimal("10"),
            receita_12m=Decimal("90"), **comum,
        )
        # Equilibrado: nem falta nem excesso.
        ProdutoImportado.objects.create(
            codigo="4", descricao="SAL GROSSO", custo=Decimal("8"), estoque=Decimal("30"),
            vendas_12m=Decimal("300"), compras_12m=Decimal("300"), receita_12m=Decimal("4800"), **comum,
        )

    def test_comprou_mais_que_vendeu_nao_depende_da_contagem(self):
        painel = indicadores.montar(self.importacao)
        indicador = painel.indicador("comprou_mais")
        self.assertFalse(indicador.depende_da_contagem)
        self.assertTrue(indicador.destaque)
        # (100 - 40) unidades x R$ 10
        self.assertEqual(indicador.valor, Decimal("600.00"))
        self.assertEqual(indicador.itens, 1)

    def test_dinheiro_parado_soma_o_que_nao_vendeu(self):
        painel = indicadores.montar(self.importacao)
        parado = painel.indicador("parado")
        self.assertEqual(parado.valor, Decimal("200.00"))  # 4 x R$ 50
        self.assertTrue(parado.depende_da_contagem)
        self.assertEqual(painel.listas["parado"][0].codigo, "2")

    def test_venda_em_risco_so_conta_quem_vendeu_nos_ultimos_90_dias(self):
        painel = indicadores.montar(self.importacao)
        falta = painel.indicador("falta")
        self.assertEqual(falta.itens, 1, "o item zerado que não vende há meses não é falta")
        self.assertEqual(falta.valor, Decimal("1500.00"))
        self.assertEqual(painel.listas["falta"][0].codigo, "3")

    def test_mes_a_mes_marca_quando_a_compra_passa_a_venda(self):
        painel = indicadores.montar(self.importacao)
        self.assertEqual(len(painel.meses), 2)
        agosto, setembro = painel.meses
        self.assertFalse(agosto["comprou_mais"])
        self.assertTrue(setembro["comprou_mais"])
        self.assertEqual(setembro["diferenca"], Decimal("-30000.00"))

    def test_todos_os_indicadores_tem_explicacao(self):
        painel = indicadores.montar(self.importacao)
        for indicador in painel.indicadores:
            self.assertTrue(indicador.explicacao.strip(), indicador.chave)
            self.assertIn(indicador.chave, painel.listas)


class TelaDoPainelTest(TestCase):
    def setUp(self):
        cache.clear()

    def test_painel_exige_permissao(self):
        usuario("operador")
        self.client.login(username="operador", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("painel:painel")).status_code, 403)

    def test_sem_importacao_o_painel_explica_o_que_falta(self):
        usuario("edson", ADMINISTRACAO)
        self.client.login(username="edson", password=SENHA_TESTE)
        pagina = self.client.get(reverse("painel:painel"))
        self.assertContains(pagina, "Nenhum dado importado ainda")
        self.assertContains(pagina, "Importar agora")

    def test_com_importacao_mostra_valores_e_aviso_da_contagem(self):
        importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO, situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(), data_corte=timezone.localdate() - timedelta(days=1),
            dias_abertos_12m=300, produtos=1, arquivo="DADOS-SET.FDB",
        )
        ProdutoImportado.objects.create(
            importacao=importacao, codigo="1", descricao="CARVAO 10KG", custo=Decimal("10"),
            estoque=Decimal("60"), vendas_12m=Decimal("40"), compras_12m=Decimal("100"),
            prazo_reposicao_dias=7,
        )
        usuario("edson", ADMINISTRACAO)
        self.client.login(username="edson", password=SENHA_TESTE)
        pagina = self.client.get(reverse("painel:completo"))
        self.assertContains(pagina, "R$ 600,00")
        self.assertContains(pagina, "Não depende da contagem")
        self.assertContains(pagina, "contagem física")
        self.assertContains(pagina, "CARVAO 10KG")

    def test_lista_escolhida_pelo_endereco(self):
        importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO, situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(), data_corte=timezone.localdate(), dias_abertos_12m=300, produtos=1,
        )
        ProdutoImportado.objects.create(
            importacao=importacao, codigo="2", descricao="LEAO DE EUCALIPTO", custo=Decimal("50"),
            estoque=Decimal("4"), vendas_12m=Decimal("0"),
        )
        usuario("edson", ADMINISTRACAO)
        self.client.login(username="edson", password=SENHA_TESTE)
        pagina = self.client.get(reverse("painel:completo"), {"lista": "parado"})
        self.assertContains(pagina, "Dinheiro parado sem venda em 12 meses")
        self.assertContains(pagina, "LEAO DE EUCALIPTO")


class PedidoEmAbertoTest(TestCase):
    """Mercadoria a caminho não pode ser comprada de novo."""

    def setUp(self):
        cache.clear()
        hoje = timezone.localdate()
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO,
            situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(),
            data_corte=hoje - timedelta(days=1),
            dias_abertos_12m=300,
            dias_abertos_90d=78,
            produtos=1,
            detalhe={"compras_com_prazo_medido": 328, "compras_com_entrega_no_mesmo_dia": 195},
        )

    def produto(self, codigo, pedido):
        return ProdutoImportado.objects.create(
            importacao=self.importacao, codigo=codigo, descricao="CARVAO 10KG",
            custo=Decimal("10"), estoque=Decimal("0"), vendas_12m=Decimal("300"),
            vendas_90d=Decimal("80"), compras_12m=Decimal("300"), receita_12m=Decimal("3000"),
            prazo_reposicao_dias=7, pedido_em_aberto=pedido,
        )

    def test_pedido_a_caminho_reduz_o_que_falta_comprar(self):
        self.produto("1", Decimal("0"))
        sem_pedido = indicadores.montar(self.importacao).indicador("comprar").valor
        ProdutoImportado.objects.all().delete()
        cache.clear()
        self.produto("1", Decimal("500"))
        com_pedido = indicadores.montar(self.importacao).indicador("comprar").valor
        self.assertGreater(sem_pedido, com_pedido)

    def test_painel_conta_os_produtos_com_pedido_em_aberto(self):
        self.produto("1", Decimal("500"))
        self.produto("2", Decimal("0"))
        painel = indicadores.montar(self.importacao)
        self.assertEqual(painel.itens_com_pedido, 1)

    def test_tela_avisa_que_o_prazo_de_entrega_do_set_e_o_da_nota(self):
        self.produto("1", Decimal("500"))
        usuario("edson", ADMINISTRACAO)
        self.client.login(username="edson", password=SENHA_TESTE)
        pagina = self.client.get(reverse("painel:completo"))
        self.assertContains(pagina, "pedido de compra")
        self.assertContains(pagina, "entrega no mesmo dia do pedido")


class OPainelFalaOMesmoNumeroQueAsOutrasTelas(TestCase):
    """O mesmo nome tem que mostrar o mesmo número na mesma tela de abertura.

    Achado na revisão geral de 15/10/2026. O consumo próprio da loja e o DIVERSOS do
    balcão não são compra que alguém decida, e todas as telas de compra os tiram da conta
    — Dashboard, Sugestões, "O que fazer agora", a lista de compra e o catálogo do
    fornecedor. O Painel não tirava: o "Dinheiro parado sem venda em 12 meses" dele
    contava o consumo próprio e dava mais que a tarefa "Pôr para girar o que está parado"
    da Visão geral, com a mesma definição e lado a lado.

    O que NÃO muda: "Produtos cadastrados no SET" e "Valor parado em estoque hoje", que
    são números de loja inteira. Ali o consumo próprio é estoque de verdade.
    """

    def setUp(self):
        cache.clear()
        hoje = timezone.localdate()
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO,
            situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(),
            data_corte=hoje - timedelta(days=1),
            dias_abertos_12m=300, dias_abertos_90d=78, produtos=2,
            arquivo="C:\\backup\\DADOS-SET.FDB",
            detalhe={"vendas_mes": [[2026, 9, 90000.0, 380]], "compras_mes": []},
        )
        comum = {"importacao": self.importacao, "prazo_reposicao_dias": 7}
        # Mercadoria parada: entra na conta de "dinheiro parado".
        ProdutoImportado.objects.create(
            codigo="1", descricao="LEAO DE EUCALIPTO", grupo="DECORACAO",
            custo=Decimal("50"), estoque=Decimal("4"), vendas_12m=Decimal("0"), **comum)
        # Consumo próprio da loja, igualmente parado: NÃO é decisão de compra.
        ProdutoImportado.objects.create(
            codigo="2", descricao="PAPEL HIGIENICO", grupo="CONSUMO PROPRIO",
            custo=Decimal("25"), estoque=Decimal("4"), vendas_12m=Decimal("0"), **comum)

    def test_o_dinheiro_parado_nao_conta_o_consumo_proprio(self):
        painel = indicadores.montar(self.importacao)
        parado = next(i for i in painel.indicadores if i.chave == "parado")
        self.assertEqual(parado.valor, Decimal("200.00"))  # 4 x 50, e não 4 x 50 + 4 x 25
        self.assertEqual(parado.itens, 1)
        self.assertNotIn("PAPEL HIGIENICO", [l.descricao for l in painel.listas["parado"]])

    def test_o_numero_bate_com_a_tarefa_da_visao_geral(self):
        """Lado a lado na abertura, com a mesma definição: tem que ser o mesmo número."""
        from apps.painel import tarefas

        painel = indicadores.montar(self.importacao)
        parado = next(i for i in painel.indicadores if i.chave == "parado")
        agenda = tarefas.montar(None, self.importacao)
        girar = next((t for t in agenda.tarefas if t.chave == "parado"), None)
        self.assertIsNotNone(girar, "a tarefa de pôr para girar não apareceu")
        # A tarefa escreve o valor em reais no texto dela; o indicador mostra o número.
        self.assertIn("R$ 200,00", girar.detalhe)
        self.assertEqual(parado.valor, Decimal("200.00"))
        self.assertIn("1 produtos", girar.detalhe)
        self.assertEqual(parado.itens, 1)

    def test_a_contagem_tambem_bate_com_a_tarefa(self):
        """Produto sem custo somava zero reais e mesmo assim era contado no Painel.

        Nos dados da loja isso dava "1.490 produtos" no Painel e "1.443 produtos" na
        tarefa, para o mesmo dinheiro, na mesma tela de abertura. Quantos são os produtos
        sem custo a tela já diz, na linha que fica embaixo dos números.
        """
        from apps.painel import tarefas

        ProdutoImportado.objects.create(
            importacao=self.importacao, prazo_reposicao_dias=7,
            codigo="3", descricao="BRINDE SEM CUSTO", grupo="DECORACAO",
            custo=None, estoque=Decimal("9"), vendas_12m=Decimal("0"))

        painel = indicadores.montar(self.importacao)
        parado = next(i for i in painel.indicadores if i.chave == "parado")
        girar = next(t for t in tarefas.montar(None, self.importacao).tarefas
                     if t.chave == "parado")
        self.assertEqual(parado.itens, 1)
        self.assertIn("1 produtos", girar.detalhe)
        self.assertEqual(parado.valor, Decimal("200.00"))

    def test_o_estoque_da_loja_inteira_continua_inteiro(self):
        """4 x 50 + 4 x 25: tirar o consumo próprio daqui seria mentir por outro lado."""
        painel = indicadores.montar(self.importacao)
        self.assertEqual(painel.resumo.valor_estoque, Decimal("300.00"))
        self.assertEqual(painel.resumo.itens, 2)
