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

from apps.compras.equipe import registrar_sugestao
from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO, VENDEDOR
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


class TestQuadrosDoGrafana(BaseDashboard):
    """A geometria dos quadros no jeito do Grafana (1.41.0).

    O template só copia estes textos para dentro do SVG. Por isso o que importa aqui é
    o desenho dizer a mesma coisa que o número: a ponta alta é o maior valor, o mês que
    ainda corre não aparece como tombo, e coordenada nunca sai com vírgula (o Django
    escreveria "66,5" e o navegador não desenharia nada).
    """

    def test_o_minigrafico_vai_do_menor_ao_maior_da_propria_serie(self):
        faisca = dashboard._faisca([10, 20, 30])
        self.assertTrue(faisca.tem)
        self.assertEqual(faisca.pontos, 3)
        self.assertEqual(faisca.linha, "M0.0 31.0 L50.0 17.0 L100.0 3.0")
        self.assertTrue(faisca.area.startswith(faisca.linha))
        self.assertTrue(faisca.area.endswith("Z"))

    def test_minigrafico_de_um_ponto_so_nao_desenha(self):
        self.assertFalse(dashboard._faisca([5]).tem)
        self.assertFalse(dashboard._faisca([]).tem)

    def test_serie_reta_fica_no_meio_do_quadro(self):
        """Sem diferença nenhuma entre os dias, a linha não pode grudar no chão nem no teto."""
        self.assertEqual(dashboard._faisca([7, 7, 7]).linha, "M0.0 17.0 L50.0 17.0 L100.0 17.0")

    def test_coordenada_nunca_tem_virgula(self):
        faisca = dashboard._faisca([Decimal("1.5"), Decimal("2.25"), Decimal("0.75")])
        self.assertNotIn(",", faisca.linha + faisca.area)

    def test_um_ponto_por_dia_ate_trinta_e_um_dias(self):
        self.venda(CORTE, "300")
        self.venda(CORTE, "100")
        self.venda(CORTE - timedelta(days=29), "50")
        self.venda(CORTE - timedelta(days=30), "999")  # 31 dias antes: fora dos 30
        pontos, por = dashboard._serie(self.importacao, CORTE, 30)
        self.assertEqual(por, "dia")
        self.assertEqual(len(pontos), 30)
        self.assertEqual(pontos[-1]["faturamento"], Decimal("400"))
        self.assertEqual(pontos[-1]["vendas"], 2)
        self.assertEqual(pontos[0]["faturamento"], Decimal("50"))

    def test_o_minigrafico_soma_o_mesmo_que_o_numero_de_cima(self):
        self.venda(CORTE, "300")
        self.venda(CORTE - timedelta(days=12), "120")
        self.venda(CORTE - timedelta(days=29), "80")
        d = dashboard.montar(self.importacao, periodo="30d")
        faturamento = next(k for k in d.kpis_da_venda if k.chave == "faturamento")
        pontos, _ = dashboard._serie(self.importacao, d.ate, 30)
        self.assertEqual(sum(p["faturamento"] for p in pontos), faturamento.valor)
        self.assertTrue(all(k.faisca.tem for k in d.kpis_da_venda))

    def test_periodo_longo_vira_semana_contada_do_corte(self):
        self.venda(CORTE, "100")
        self.venda(CORTE - timedelta(days=6), "10")   # mesma semana do corte
        self.venda(CORTE - timedelta(days=7), "1")    # semana anterior
        pontos, por = dashboard._serie(self.importacao, CORTE, 365)
        self.assertEqual(por, "semana")
        self.assertEqual(len(pontos), 52)
        self.assertEqual(pontos[-1]["faturamento"], Decimal("110"))
        self.assertEqual(pontos[-2]["faturamento"], Decimal("1"))

    def test_dia_sem_venda_repete_o_ticket_em_vez_de_cair_a_zero(self):
        pontos = [
            {"faturamento": Decimal("100"), "vendas": 2, "desconto": Decimal("0")},
            {"faturamento": Decimal("0"), "vendas": 0, "desconto": Decimal("0")},
            {"faturamento": Decimal("90"), "vendas": 1, "desconto": Decimal("0")},
        ]
        ticket = dashboard._faiscas_da_venda(pontos, "dia")["ticket"].linha.split(" L")
        # Ticket 50, (nada), 90: o dia vazio fica na altura do anterior.
        self.assertEqual(ticket[0].split()[1], ticket[1].split()[1])

    def test_o_mes_que_corre_sai_da_linha_cheia_e_vira_tracejado(self):
        """O tombo do mês que ainda corre é falta de dias, não queda de venda."""
        self.importacao.detalhe["mes_parcial"] = [2026, 9, 20, 1200.0]
        self.importacao.save(update_fields=["detalhe"])
        d = dashboard.montar(self.importacao)
        linha = d.linha_dos_meses
        self.assertTrue(linha.tem)
        self.assertEqual(linha.colunas, len(d.meses))
        self.assertTrue(linha.parcial)
        self.assertEqual(linha.agora.count("L") + 1, len(d.meses) - 1)
        self.assertNotIn(",", linha.agora + linha.agora_area + linha.parcial + linha.antes)

    def test_mes_fechado_fica_todo_na_linha_cheia(self):
        self.importacao.data_corte = date(2026, 9, 30)
        self.importacao.save(update_fields=["data_corte"])
        linha = dashboard.montar(self.importacao).linha_dos_meses
        self.assertEqual(linha.parcial, "")
        self.assertEqual(linha.agora.count("L") + 1, linha.colunas)

    def test_o_ano_passado_com_buraco_para_e_recomeca(self):
        meses = [dashboard.Mes(rotulo=str(n), valor=Decimal("100"), valor_ano_passado=antes)
                 for n, antes in enumerate([Decimal("90"), Decimal("80"), None,
                                            Decimal("70"), Decimal("60")])]
        linha = dashboard._grafico_de_linha(meses)
        self.assertEqual(linha.antes.count("M"), 2)

    def test_o_eixo_termina_num_numero_redondo(self):
        self.assertEqual(dashboard._escala(228153), (300000.0, 100000.0))
        self.assertEqual(dashboard._escala(170000), (200000.0, 50000.0))
        self.assertEqual(dashboard._escala(0), (1.0, 0.25))

    def test_o_eixo_escreve_mil_e_milhao_por_extenso(self):
        self.assertEqual(dashboard._reais_curto(0), "R$ 0")
        self.assertEqual(dashboard._reais_curto(100000), "R$ 100 mil")
        self.assertEqual(dashboard._reais_curto(2500), "R$ 2,5 mil")
        self.assertEqual(dashboard._reais_curto(1500000), "R$ 1,5 mi")
        self.assertEqual(dashboard._reais_curto(2000000), "R$ 2 mi")

    def test_as_marcas_do_eixo_vao_do_zero_ao_topo(self):
        meses = [dashboard.Mes(rotulo="a", valor=Decimal("228153")),
                 dashboard.Mes(rotulo="b", valor=Decimal("100000"))]
        marcas = dashboard._grafico_de_linha(meses).marcas
        self.assertEqual([m.rotulo for m in marcas], ["R$ 0", "R$ 100 mil", "R$ 200 mil", "R$ 300 mil"])
        self.assertEqual([m.altura for m in marcas], [0, 33, 67, 100])
        self.assertEqual(marcas[0].y, "300.0")
        self.assertEqual(marcas[-1].y, "0.0")

    def test_as_fatias_da_rosca_somam_o_circulo_e_comecam_no_topo(self):
        fatias = dashboard._fatiar([dashboard.Fatia("a", Decimal("75")),
                                    dashboard.Fatia("b", Decimal("25"))], Decimal("100"))
        self.assertEqual(sum(f.fatia for f in fatias), Decimal("100"))
        self.assertEqual(fatias[0].giro, "25")
        self.assertEqual(fatias[0].traco, "75.0 25.0")
        self.assertEqual(fatias[1].giro, "50.0")

    def test_forma_de_pagamento_com_o_nome_da_loja(self):
        """AVISTA e DINHEIRO são a mesma forma: uma fatia só, chamada Dinheiro."""
        self.venda(CORTE, "200", forma="CARTAO CREDITO")
        self.venda(CORTE, "100", forma="AVISTA")
        self.venda(CORTE, "50", forma="DINHEIRO")
        d = dashboard.montar(self.importacao, periodo="30d")
        self.assertEqual([(f.nome, f.valor) for f in d.formas],
                         [("Cartão de crédito", Decimal("200")), ("Dinheiro", Decimal("150"))])
        self.assertEqual([f.nome for f in d.rosca_das_formas.fatias],
                         ["Cartão de crédito", "Dinheiro"])

    def test_rosca_da_ruptura_e_do_estoque_parado(self):
        self.produto("1", estoque=Decimal("10"), custo=Decimal("100"))
        self.produto("2", estoque=Decimal("10"), custo=Decimal("100"))
        self.produto("3", estoque=Decimal("0"))
        self.produto("4", estoque=Decimal("5"), custo=Decimal("100"),
                     vendas_12m=Decimal("0"), receita_12m=Decimal("0"))
        d = dashboard.montar(self.importacao)
        ruptura = d.rosca_da_ruptura
        self.assertEqual([f.quantos for f in ruptura.fatias], [2, 1])
        self.assertEqual(ruptura.centro, "33,3%")
        estoque = d.rosca_do_estoque
        self.assertEqual([f.valor for f in estoque.fatias], [Decimal("2000.00"), Decimal("500.00")])
        self.assertEqual(estoque.centro, "20,0%")

    def test_o_mostrador_da_margem_fica_entre_zero_e_cem(self):
        self.produto("1", custo=Decimal("100"), receita_12m=Decimal("2000"))
        d = dashboard.montar(self.importacao)
        self.assertEqual(d.margem, Decimal("50.0"))
        self.assertEqual(d.margem_traco, "50.0 100")
        self.produto("2", custo=Decimal("900"), receita_12m=Decimal("10"))
        self.assertEqual(dashboard.montar(self.importacao).margem_traco, "0 100")

    def test_o_numero_do_quadro_e_o_que_a_tela_escreve(self):
        Kpi = dashboard.Kpi
        self.assertEqual(Kpi("f", "F", Decimal("1538337.98"), "reais").texto, "R$ 1.538.337,98")
        self.assertEqual(Kpi("v", "V", Decimal("16361"), "numero").texto, "16.361")
        self.assertEqual(Kpi("d", "D", Decimal("2.44"), "porcento").texto, "2,4%")
        self.assertEqual(Kpi("d", "D", Decimal("54.0"), "porcento").texto, "54%")
        self.assertEqual(Kpi("c", "C", Decimal("12.4"), "meses").texto, "12,4 meses")
        self.assertEqual(Kpi("c", "C", Decimal("1.0"), "meses").texto, "1 mês")
        # O tamanho da letra sai daqui: o faturamento tem quase três vezes as letras das vendas.
        self.assertEqual(Kpi("f", "F", Decimal("1538337.98"), "reais").letras, 15)
        self.assertEqual(Kpi("v", "V", Decimal("16361"), "numero").letras, 6)

    def test_cobertura_acima_de_tres_meses_pede_atencao(self):
        cobertura = dashboard.Kpi("cobertura", "Cobertura", Decimal("12.4"), "meses",
                                  atencao_acima_de=dashboard.COBERTURA_DE_ATENCAO)
        self.assertEqual(cobertura.nivel, "atencao")
        cobertura.valor = Decimal("3")
        self.assertEqual(cobertura.nivel, "neutro")


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

    def test_o_quadro_de_problemas_e_a_lista_da_visao_geral(self):
        """O "Problemas recentes" do modelo é a MESMA agenda, com a gravidade escrita."""
        usuario("gerencia", ADMINISTRACAO)
        self.client.login(username="gerencia", password=SENHA_TESTE)
        resposta = self.client.get(reverse("painel:dashboard"))
        agenda = resposta.context["agenda"]
        self.assertTrue(agenda.tem_tarefas)
        self.assertContains(resposta, "O que fazer agora")
        for tarefa in agenda.tarefas:
            self.assertContains(resposta, tarefa.titulo)
            self.assertContains(resposta, f'monitor-selo-{tarefa.nivel}">{tarefa.gravidade}<')
        # Dados de 20/09 abertos semanas depois: importar é urgente, e a loja fica em Urgente.
        self.assertEqual(resposta.context["situacao"].palavra, "Urgente")

    def test_cada_perfil_ve_no_quadro_so_o_que_ele_abre(self):
        """Responder a equipe é da gerência: o administrativo não vê a tarefa nem a conta dela."""
        gerente = usuario("gerencia", ADMINISTRACAO)
        registrar_sugestao(produto="CARVAO", usuario=gerente)
        usuario("ana", ADMINISTRATIVO)
        self.client.login(username="gerencia", password=SENHA_TESTE)
        self.assertContains(self.client.get(reverse("painel:dashboard")), "Responder a equipe")
        self.client.login(username="ana", password=SENHA_TESTE)
        resposta = self.client.get(reverse("painel:dashboard"))
        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, "Responder a equipe")
        self.assertNotIn("equipe", [t.chave for t in resposta.context["agenda"].tarefas])

    def test_o_numero_grande_leva_o_tamanho_da_letra(self):
        usuario("gerencia", ADMINISTRACAO)
        self.client.login(username="gerencia", password=SENHA_TESTE)
        resposta = self.client.get(reverse("painel:dashboard"))
        self.assertContains(resposta, 'style="--letras: 9">R$ 500,00<')

    def test_o_valor_de_cada_mes_continua_na_tela(self):
        """A linha só mostra o valor no mouse; o celular não tem mouse. A tabela recolhida tem."""
        usuario("gerencia", ADMINISTRACAO)
        self.client.login(username="gerencia", password=SENHA_TESTE)
        resposta = self.client.get(reverse("painel:dashboard"))
        self.assertContains(resposta, "Ver o valor de cada mês")
        self.assertContains(resposta, "R$ 1.500,00")   # agosto de 2026, do detalhe da importação

    def test_o_dashboard_esta_no_assunto_de_vendas(self):
        from apps.core import menu

        assunto = menu.grupo_de("painel:dashboard")
        self.assertIsNotNone(assunto, "o dashboard saiu do menu")
        self.assertEqual(assunto.chave, "vendas")
