"""Dashboard do varejo: os números, os gráficos e o que os filtros podem e não podem.

O que estes testes travam, além da conta: as duas restrições do dado. Filtrar por
grupo não pode mexer no faturamento (o SET não traz o item da venda) e o vendedor
não pode chegar nesta tela (ela é toda valor de dinheiro).
"""

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.contas.perfis import ADMINISTRACAO, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.importacao.models import Importacao, ProdutoImportado, VendaImportada
from apps.painel import dashboard

CORTE = date(2026, 9, 20)


class BaseDashboard(TestCase):
    def setUp(self):
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO,
            situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(),
            data_corte=CORTE,
            dias_abertos_12m=300,
            produtos=3,
            detalhe={"vendas_mes": [
                [2025, 8, 1000.0, 10], [2025, 9, 2000.0, 20],
                [2026, 8, 1500.0, 15], [2026, 9, 1000.0, 10],
            ]},
        )
        self.proxima = 0

    def produto(self, codigo, **campos):
        padrao = dict(
            descricao=f"PRODUTO {codigo}", grupo="TAPETE", fornecedor="GERMAN",
            custo=Decimal("100"), preco_venda=Decimal("200"), estoque=Decimal("10"),
            vendas_12m=Decimal("10"), receita_12m=Decimal("2000"),
        )
        padrao.update(campos)
        return ProdutoImportado.objects.create(importacao=self.importacao, codigo=codigo, **padrao)

    def venda(self, dia, valor, forma="PIX", hora="15:00", desconto="0"):
        self.proxima += 1
        return VendaImportada.objects.create(
            importacao=self.importacao, id_set=self.proxima, numero=str(self.proxima),
            data=dia, hora=hora, dia_da_semana=(dia.weekday() + 1) % 7,
            valor=Decimal(valor), desconto=Decimal(desconto), forma_pagamento=forma,
        )


class TestNumerosDaVenda(BaseDashboard):
    def test_faturamento_vendas_e_ticket_do_periodo(self):
        self.venda(CORTE, "300")
        self.venda(CORTE - timedelta(days=1), "100")
        d = dashboard.montar(self.importacao, periodo="30d")
        numeros = {k.chave: k.valor for k in d.kpis_da_venda}
        self.assertEqual(numeros["faturamento"], Decimal("400"))
        self.assertEqual(numeros["vendas"], Decimal("2"))
        self.assertEqual(numeros["ticket"], Decimal("200.00"))

    def test_compara_com_o_periodo_anterior_de_igual_tamanho(self):
        self.venda(CORTE, "200")                       # dentro dos 7 dias
        self.venda(CORTE - timedelta(days=10), "100")  # nos 7 dias anteriores
        d = dashboard.montar(self.importacao, periodo="7d")
        faturamento = next(k for k in d.kpis_da_venda if k.chave == "faturamento")
        self.assertEqual(faturamento.variacao, Decimal("100.0"))
        self.assertEqual(faturamento.nivel, "bom")

    def test_queda_aparece_como_ruim(self):
        self.venda(CORTE, "50")
        self.venda(CORTE - timedelta(days=10), "100")
        d = dashboard.montar(self.importacao, periodo="7d")
        faturamento = next(k for k in d.kpis_da_venda if k.chave == "faturamento")
        self.assertEqual(faturamento.nivel, "ruim")

    def test_desconto_subindo_e_ruim_e_nao_bom(self):
        """Mais desconto não é melhoria: o verde e o vermelho trocam neste número."""
        self.venda(CORTE, "100", desconto="20")
        self.venda(CORTE - timedelta(days=10), "100", desconto="5")
        d = dashboard.montar(self.importacao, periodo="7d")
        desconto = next(k for k in d.kpis_da_venda if k.chave == "desconto")
        self.assertGreater(desconto.variacao, 0)
        self.assertEqual(desconto.nivel, "ruim")

    def test_sem_periodo_anterior_nao_inventa_comparacao(self):
        self.venda(CORTE, "100")
        d = dashboard.montar(self.importacao, periodo="7d")
        faturamento = next(k for k in d.kpis_da_venda if k.chave == "faturamento")
        self.assertIsNone(faturamento.variacao)

    def test_sem_venda_nenhuma_nao_divide_por_zero(self):
        d = dashboard.montar(self.importacao, periodo="7d")
        ticket = next(k for k in d.kpis_da_venda if k.chave == "ticket")
        self.assertEqual(ticket.valor, Decimal("0"))


class TestNumerosDoEstoque(BaseDashboard):
    def test_margem_cobertura_ruptura_e_parado(self):
        self.produto("1")  # vende 10 a 2000 de receita, custo 100, estoque 10
        self.produto("2", vendas_12m=Decimal("0"), receita_12m=Decimal("0"),
                     estoque=Decimal("5"))
        self.produto("3", estoque=Decimal("0"))
        d = dashboard.montar(self.importacao)
        numeros = {k.chave: k.valor for k in d.kpis_do_estoque}
        # receita 4000, custo do vendido 2000 -> metade sobra
        self.assertEqual(numeros["margem"], Decimal("50.0"))
        # dois dos produtos venderam; um deles está sem saldo
        self.assertEqual(numeros["ruptura"], Decimal("50.0"))
        # o que não vendeu: 5 unidades a 100
        self.assertEqual(numeros["parado"], Decimal("500"))
        self.assertGreater(numeros["cobertura"], Decimal("0"))

    def test_sem_custo_no_cadastro_nao_quebra(self):
        self.produto("1", custo=None)
        d = dashboard.montar(self.importacao)
        self.assertEqual(len(d.kpis_do_estoque), 4)

    def test_saldo_negativo_do_set_conta_como_zero(self):
        """Saldo negativo é erro de cadastro, não mercadoria devendo na prateleira.

        São 1.456 produtos assim no SET da loja, que nunca fez contagem. Somando o
        negativo, o "parado" desta tela saía R$ 37 mil menor que o da Lista de compra e o
        do "Antes de comprar", que sempre filtraram saldo positivo.
        """
        self.produto("1", vendas_12m=Decimal("0"), receita_12m=Decimal("0"),
                     estoque=Decimal("5"))      # 5 x 100 = 500 parados
        self.produto("2", vendas_12m=Decimal("0"), receita_12m=Decimal("0"),
                     estoque=Decimal("-8"))     # erro de cadastro: vale zero
        d = dashboard.montar(self.importacao)
        numeros = {k.chave: k.valor for k in d.kpis_do_estoque}
        self.assertEqual(numeros["parado"], Decimal("500"))
        parado = next(k for k in d.kpis_do_estoque if k.chave == "parado")
        self.assertIn("saldo negativo", parado.explicacao)

    def test_saldo_negativo_nao_encolhe_a_cobertura(self):
        self.produto("1", estoque=Decimal("12"))     # 12 x 100 de estoque, vende 10 no ano
        d = dashboard.montar(self.importacao)
        sozinho = {k.chave: k.valor for k in d.kpis_do_estoque}["cobertura"]
        self.produto("2", vendas_12m=Decimal("0"), receita_12m=Decimal("0"),
                     estoque=Decimal("-40"))
        d = dashboard.montar(self.importacao)
        self.assertEqual({k.chave: k.valor for k in d.kpis_do_estoque}["cobertura"], sozinho)


class TestFiltros(BaseDashboard):
    def setUp(self):
        super().setUp()
        self.produto("1", grupo="TAPETE", fornecedor="GERMAN")
        self.produto("2", grupo="CERAMICA", fornecedor="STARBELLA")
        self.venda(CORTE, "500")

    def test_o_filtro_de_grupo_recorta_os_blocos_de_produto(self):
        d = dashboard.montar(self.importacao, grupo="CERAMICA")
        self.assertEqual(d.produtos_no_filtro, 1)
        self.assertEqual([g.nome for g in d.grupos], ["CERAMICA"])

    def test_o_filtro_de_grupo_nao_mexe_no_faturamento(self):
        """O SET não traz o item da venda, então a venda é sempre da loja toda."""
        sem_filtro = dashboard.montar(self.importacao)
        com_filtro = dashboard.montar(self.importacao, grupo="CERAMICA")
        def fat(d):
            return next(k.valor for k in d.kpis_da_venda if k.chave == "faturamento")
        self.assertEqual(fat(sem_filtro), fat(com_filtro))

    def test_o_filtro_de_fornecedor_recorta_os_produtos(self):
        d = dashboard.montar(self.importacao, fornecedor="STARBELLA")
        self.assertEqual(d.produtos_no_filtro, 1)

    def test_filtro_que_nao_existe_e_ignorado_em_vez_de_zerar_a_tela(self):
        d = dashboard.montar(self.importacao, grupo="NAO EXISTE")
        self.assertEqual(d.filtro_grupo, "")
        self.assertEqual(d.produtos_no_filtro, 2)

    def test_periodo_invalido_cai_no_padrao(self):
        d = dashboard.montar(self.importacao, periodo="tudo")
        self.assertEqual(d.periodo, dashboard.PERIODO_PADRAO)

    def test_a_lista_de_grupos_tem_cada_grupo_uma_vez(self):
        """O modelo ordena por código, e com a ordenação de pé o DISTINCT falha."""
        self.produto("3", grupo="TAPETE")
        d = dashboard.montar(self.importacao)
        self.assertEqual(d.grupos_disponiveis, ["CERAMICA", "TAPETE"])


class TestGraficos(BaseDashboard):
    def test_mes_a_mes_traz_o_mesmo_mes_do_ano_passado(self):
        d = dashboard.montar(self.importacao)
        agosto = d.meses[-2]
        self.assertEqual(agosto.rotulo, "ago/26")
        self.assertEqual(agosto.valor, Decimal("1500.00"))
        self.assertEqual(agosto.valor_ano_passado, Decimal("1000.00"))
        self.assertGreater(agosto.variacao, 0)
        self.assertFalse(agosto.parcial)

    def test_mes_que_ainda_corre_compara_com_o_mesmo_pedaco_do_ano_passado(self):
        """O que o Edson viu: sete dias deste mês contra o mês inteiro do ano passado.

        Com o corte em 20/09, setembro ainda está correndo. A comparação tem que ser
        com o dia 1 ao dia 20 do ano passado, não com setembro inteiro.
        """
        self.importacao.detalhe["mes_parcial"] = [2026, 9, 20, 1200.0]
        self.importacao.save(update_fields=["detalhe"])
        d = dashboard.montar(self.importacao)
        setembro = d.meses[-1]
        self.assertEqual(setembro.rotulo, "set/26")
        self.assertTrue(setembro.parcial)
        self.assertEqual(setembro.dia_parcial, 20)
        self.assertEqual(setembro.ate_o_dia, "até dia 20")
        self.assertEqual(setembro.valor_ano_passado, Decimal("1200.00"))
        self.assertLess(setembro.variacao, 0)

    def test_sem_o_pedaco_do_ano_passado_o_mes_que_corre_nao_compara(self):
        """Importação antiga não traz esse número: melhor sem comparação que com uma errada."""
        d = dashboard.montar(self.importacao)
        setembro = d.meses[-1]
        self.assertTrue(setembro.parcial)
        self.assertIsNone(setembro.valor_ano_passado)
        self.assertIsNone(setembro.variacao)

    def test_sem_vendas_mes_no_detalhe_o_grafico_fica_vazio_sem_quebrar(self):
        self.importacao.detalhe = {}
        self.importacao.save(update_fields=["detalhe"])
        d = dashboard.montar(self.importacao)
        self.assertEqual(d.meses, [])

    def test_a_curva_abc_separa_oitenta_quinze_e_cinco(self):
        for numero in range(1, 21):
            # Um produto grande e dezenove pequenos: a curva sobe rápido, como no varejo.
            receita = Decimal("8000") if numero == 1 else Decimal("100")
            self.produto(str(numero), receita_12m=receita)
        d = dashboard.montar(self.importacao)
        letras = {c.letra: c for c in d.abc}
        self.assertEqual(set(letras), {"A", "B", "C"})
        # Quem cruza a linha dos 80% fica em A: aqui o produto grande sozinho já passa
        # dos 80%, e antes disso a classe A saía vazia na tela.
        self.assertEqual(letras["A"].produtos, 1)
        self.assertGreaterEqual(letras["A"].fatia_da_receita, Decimal("80"))
        self.assertEqual(sum(c.produtos for c in d.abc), 20)
        # Cada classe vira uma linha com barra: classe que tem produto nunca fica com
        # barra zerada, e a de A é a maior das três.
        self.assertTrue(all(c.largura_receita > 0 for c in d.abc if c.produtos))
        self.assertGreater(letras["A"].largura_receita, letras["B"].largura_receita)
        self.assertGreater(letras["B"].largura_receita, letras["C"].largura_receita)

    def test_cada_classe_tem_nome_em_palavras(self):
        """A letra sozinha não diz nada a quem nunca ouviu falar em curva ABC."""
        self.produto("1")
        d = dashboard.montar(self.importacao)
        self.assertTrue(all(c.titulo and c.explicacao for c in d.abc))

    def test_produto_sem_venda_fica_fora_da_curva(self):
        self.produto("1")
        self.produto("2", receita_12m=Decimal("0"), vendas_12m=Decimal("0"))
        d = dashboard.montar(self.importacao)
        self.assertEqual(sum(c.produtos for c in d.abc), 1)

    def test_as_fatias_do_grupo_somam_cem(self):
        self.produto("1", grupo="TAPETE", receita_12m=Decimal("3000"))
        self.produto("2", grupo="CERAMICA", receita_12m=Decimal("1000"))
        d = dashboard.montar(self.importacao)
        self.assertEqual(sum(g.fatia for g in d.grupos), Decimal("100.0"))

    def test_campeao_de_faturamento_e_de_margem_sao_listas_diferentes(self):
        self.produto("1", receita_12m=Decimal("5000"), vendas_12m=Decimal("10"),
                     custo=Decimal("490"))   # vende muito, deixa pouco
        self.produto("2", receita_12m=Decimal("1000"), vendas_12m=Decimal("10"),
                     custo=Decimal("10"))    # vende menos, deixa mais
        d = dashboard.montar(self.importacao)
        self.assertEqual(d.campeoes_faturamento[0].codigo, "1")
        self.assertEqual(d.campeoes_margem[0].codigo, "2")

    def test_dia_da_semana_pagamento_e_hora(self):
        self.venda(date(2026, 9, 20), "300", forma="PIX", hora="10:30")      # domingo
        self.venda(date(2026, 9, 19), "100", forma="CARTAO", hora="16:00")   # sábado
        d = dashboard.montar(self.importacao, periodo="30d")
        self.assertEqual(sum(b.valor for b in d.dias_da_semana), Decimal("400"))
        self.assertEqual([b.nome for b in d.formas][0], "PIX")
        self.assertEqual(sum(b.valor for b in d.horas), Decimal("400"))

    def test_hora_estragada_no_set_nao_derruba_o_grafico(self):
        self.venda(CORTE, "100", hora="--:--")
        d = dashboard.montar(self.importacao, periodo="30d")
        self.assertEqual(d.horas, [])


class TestTela(BaseDashboard):
    def setUp(self):
        super().setUp()
        self.produto("1")
        self.venda(CORTE, "500")

    def test_a_gerencia_abre_a_tela(self):
        usuario("gerencia", ADMINISTRACAO)
        self.client.login(username="gerencia", password=SENHA_TESTE)
        resposta = self.client.get(reverse("painel:dashboard"))
        self.assertContains(resposta, "Dashboard")
        self.assertContains(resposta, "Quais produtos sustentam a loja")
        self.assertContains(resposta, "Faturamento mês a mês")

    def test_o_vendedor_nao_entra(self):
        """A tela é dinheiro de ponta a ponta; o vendedor tem uma tela só."""
        usuario("balcao", VENDEDOR)
        self.client.login(username="balcao", password=SENHA_TESTE)
        resposta = self.client.get(reverse("painel:dashboard"))
        self.assertEqual(resposta.status_code, 403)

    def test_a_tela_diz_que_o_filtro_de_produto_nao_mexe_na_venda(self):
        usuario("gerencia", ADMINISTRACAO)
        self.client.login(username="gerencia", password=SENHA_TESTE)
        resposta = self.client.get(reverse("painel:dashboard"))
        self.assertContains(resposta, "não mexe neles")

    def test_sem_importacao_a_tela_explica_em_vez_de_quebrar(self):
        Importacao.objects.all().delete()
        usuario("gerencia", ADMINISTRACAO)
        self.client.login(username="gerencia", password=SENHA_TESTE)
        resposta = self.client.get(reverse("painel:dashboard"))
        self.assertContains(resposta, "Ainda não há dados")

    def test_o_dashboard_esta_no_assunto_de_vendas(self):
        from apps.core import menu

        assunto = menu.grupo_de("painel:dashboard")
        self.assertIsNotNone(assunto, "o dashboard saiu do menu")
        self.assertEqual(assunto.chave, "vendas")
