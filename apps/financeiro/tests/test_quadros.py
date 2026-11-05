"""Os quadros do Dashboard em Contas a pagar (1.47.0), com três anos no gráfico (1.48.0).

Pedidos do Edson em 04/11/2026: "usar esse formato de gráfico também em contas a pagar", e
depois "nesse mesmo gráfico do contas a pagar manter sempre os últimos 3 anos". O que estes
testes protegem:

1. **Os três anos são os do corte**, de janeiro a dezembro, e a importação lê o pago de
   três anos inteiros (o recebido, que traz nome de cliente, continua em 24 meses).
2. **A comparação é justa.** O mês que corre se compara com o mesmo pedaço do ano
   passado, e mês que a foto do SET não tem inteiro fica em branco, nunca em zero.
3. **A cor é a do caixa.** No faturamento, mais é bom; nas contas pagas, mais é ruim.
4. **As fatias da rosca são os filtros da lista**, e o nome de cada uma abre a lista dela.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.core.cache import cache
from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.contas.perfis import ADMINISTRACAO
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.financeiro import quadros
from apps.financeiro.models import Lancamento
from apps.importacao.fontes import firebird
from apps.importacao.models import Importacao
from apps.painel import dashboard

CORTE = date(2026, 9, 20)
HOJE = date(2026, 9, 21)


class BaseQuadros(TestCase):
    def setUp(self):
        cache.clear()
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO, situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(), data_corte=CORTE,
            detalhe={"pagas_desde": "2023-09-01", "recebidas_desde": "2024-09-01"},
        )

    def paga(self, dia, valor, grupo="1.01.05 - Aluguel", tipo=Lancamento.Tipo.PAGAR):
        return Lancamento.objects.create(
            importacao=self.importacao, tipo=tipo, descricao="CONTA", contraparte="FORNECEDOR",
            grupo=grupo, vencimento=dia, pagamento=dia, valor=Decimal(valor), valor_pago=Decimal(valor),
        )

    def aberta(self, vencimento, valor):
        return Lancamento.objects.create(
            importacao=self.importacao, tipo=Lancamento.Tipo.PAGAR, descricao="CONTA",
            contraparte="FORNECEDOR", grupo="1.01.05 - Aluguel", vencimento=vencimento,
            valor=Decimal(valor),
        )


class PagasPorAnoTest(BaseQuadros):
    def setUp(self):
        super().setUp()
        self.paga(date(2026, 9, 5), "1000")
        self.paga(date(2025, 9, 10), "800")
        self.paga(date(2025, 9, 25), "500")    # depois do dia 20: fora do pedaço comparado
        self.paga(date(2026, 8, 15), "2000")
        self.paga(date(2025, 8, 15), "1000")
        self.paga(date(2026, 7, 3), "300")
        self.paga(date(2025, 7, 3), "600")
        self.paga(date(2025, 10, 15), "4000")
        self.paga(date(2024, 1, 10), "700")
        self.paga(date(2024, 12, 20), "900")
        self.paga(date(2023, 12, 20), "5000")  # antes do retrasado: fora do gráfico
        self.paga(date(2026, 9, 6), "9000", tipo=Lancamento.Tipo.RECEBER)  # recebimento não é conta paga

    def pagas(self):
        return quadros.pagas_por_ano(self.importacao)

    def mes(self, rotulo):
        return next(mes for mes in self.pagas().meses if mes.rotulo == rotulo)

    def valores(self, rotulo):
        return [celula.valor for celula in self.mes(rotulo).celulas]

    def test_sao_os_tres_anos_do_corte_de_janeiro_a_dezembro(self):
        pagas = self.pagas()
        self.assertEqual(pagas.anos, [2026, 2025, 2024])
        self.assertEqual([mes.rotulo for mes in pagas.meses],
                         ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"])
        self.assertEqual([linha.ano for linha in pagas.grafico.legenda], [2026, 2025, 2024])
        self.assertEqual([linha.papel for linha in pagas.grafico.legenda], ["agora", "antes", "retrasado"])

    def test_o_retrasado_vem_inteiro(self):
        self.assertEqual(self.valores("jan"), [Decimal("0.00"), Decimal("0.00"), Decimal("700.00")])
        self.assertEqual(self.valores("dez"), [None, Decimal("0.00"), Decimal("900.00")])

    def test_o_mes_que_corre_se_compara_com_o_mesmo_pedaco_do_ano_passado(self):
        setembro = self.mes("set")
        self.assertTrue(setembro.parcial)
        self.assertEqual(setembro.dia_parcial, 20)
        self.assertEqual(setembro.ate_o_dia, "até dia 20")
        # 2025 aparece com o mês inteiro, que é o que a linha do ano desenha...
        self.assertEqual(self.valores("set"), [Decimal("1000.00"), Decimal("1300.00"), Decimal("0.00")])
        # ...mas a porcentagem compara do dia 1º ao dia 20 nos dois anos.
        self.assertEqual(setembro.antes_no_pedaco, Decimal("800.00"))
        self.assertEqual(setembro.variacao, Decimal("25.0"))
        self.assertTrue(setembro.celulas[0].parcial)
        self.assertFalse(setembro.celulas[1].parcial)
        self.assertEqual(self.pagas().mes_que_corre.rotulo, "set")

    def test_mes_inteiro_contra_o_mes_inteiro_do_ano_passado(self):
        agosto = self.mes("ago")
        self.assertFalse(agosto.parcial)
        self.assertEqual(agosto.variacao, Decimal("100.0"))

    def test_pagar_mais_que_no_ano_passado_e_vermelho(self):
        self.assertEqual(self.mes("ago").sentido, "ruim")
        self.assertEqual(self.mes("jul").sentido, "bom")
        self.assertEqual(self.mes("jan").sentido, "neutro")
        # No faturamento a mesma subida é verde.
        self.assertEqual(dashboard.Mes("Out/25", Decimal("2000"), valor_ano_passado=Decimal("1000")).sentido, "bom")

    def test_o_mes_que_ainda_nao_chegou_fica_em_branco_e_os_anos_passados_mostram_o_que_vem(self):
        outubro = self.mes("out")
        self.assertEqual(self.valores("out"), [None, Decimal("4000.00"), Decimal("0.00")])
        self.assertIsNone(outubro.variacao)
        self.assertEqual(outubro.sentido, "neutro")
        self.assertTrue(self.pagas().tem_buraco)

    def test_a_soma_de_cada_ano_vai_ate_o_dia_do_corte(self):
        pagas = self.pagas()
        total = pagas.ate_o_corte
        self.assertEqual(pagas.dia_do_corte, "20/set")
        self.assertEqual(total.rotulo, "Até 20/set")
        # 2025 sem o 25/09 nem outubro; 2024 sem dezembro.
        self.assertEqual([c.valor for c in total.celulas],
                         [Decimal("3300.00"), Decimal("2400.00"), Decimal("700.00")])
        self.assertEqual(total.variacao, Decimal("37.5"))
        self.assertEqual(total.sentido, "ruim")

    def test_foto_da_1_47_nao_desenha_o_que_ela_nao_traz_inteiro(self):
        """Na 1.47.x o pago vinha de 24 meses: em setembro de 2026, desde 01/09/2024."""
        self.importacao.detalhe = {"financeiro_desde": "2024-09-01"}
        self.importacao.save()
        self.assertEqual(self.valores("jan"), [Decimal("0.00"), Decimal("0.00"), None])
        self.assertEqual(self.valores("set")[2], Decimal("0.00"))
        self.assertIsNone(self.pagas().ate_o_corte.celulas[2].valor)

    def test_foto_antiga_nao_desenha_o_mes_que_ela_tem_pela_metade(self):
        """Até a 1.46.0 a leitura começava em "corte menos 730 dias", no meio de setembro."""
        self.importacao.detalhe = {}
        self.importacao.save()
        self.assertIsNone(self.valores("set")[2])
        self.assertEqual(self.valores("out")[2], Decimal("0.00"))

    def test_mes_fechado_nao_tem_tracejado(self):
        self.importacao.data_corte = date(2026, 9, 30)
        self.importacao.save()
        pagas = self.pagas()
        self.assertIsNone(pagas.mes_que_corre)
        self.assertEqual(self.mes("set").variacao, Decimal("-23.1"))   # 1000 contra 1300
        agora = pagas.grafico.legenda[0]
        self.assertEqual(agora.parcial, "")
        self.assertEqual(agora.caminho.count("L"), 8)                   # janeiro a setembro

    def test_29_de_fevereiro_vira_28_no_ano_que_nao_e_bissexto(self):
        self.assertEqual(quadros._ate_o_dia_do_corte(2027, 2, date(2028, 2, 29)), date(2027, 2, 28))

    def test_sem_importacao_nao_ha_grafico(self):
        pagas = quadros.pagas_por_ano(None)
        self.assertEqual((pagas.anos, pagas.meses), ([], []))
        self.assertFalse(pagas.grafico.tem)


class ComecoDoSetTest(BaseQuadros):
    """No backup de 20/09/2026 a primeira conta paga do SET é de 27/02/2024: antes disso a
    loja não usava o financeiro do SET. Mês de antes não é mês em que a loja não pagou."""

    def setUp(self):
        super().setUp()
        self.paga(date(2024, 2, 27), "96")
        self.paga(date(2024, 3, 10), "12000")
        self.paga(date(2024, 5, 10), "120000")
        self.paga(date(2025, 3, 10), "100000")

    def valores_de_2024(self, pagas):
        return [mes.celulas[2].valor for mes in pagas.meses[:5]]

    def test_o_mes_que_o_set_nao_tem_fica_em_branco_e_nao_em_zero(self):
        pagas = quadros.pagas_por_ano(self.importacao)
        self.assertEqual(self.valores_de_2024(pagas),
                         [None, None, Decimal("12000.00"), Decimal("0.00"), Decimal("120000.00")])
        self.assertIsNone(pagas.ate_o_corte.celulas[2].valor)
        self.assertEqual(pagas.lancado_desde, date(2024, 2, 27))
        self.assertEqual(pagas.comeca_em, "mar/2024")

    def test_a_tela_diz_de_quando_o_set_tem_lancamento(self):
        html = render_to_string("painel/_monitor_anos.html",
                                {"pagas": quadros.pagas_por_ano(self.importacao), "o_que": "Contas pagas"})
        self.assertIn("O SET só tem conta paga lançada desde 27/02/2024: antes de mar/2024", html)

    def test_primeira_conta_no_dia_primeiro_conta_o_mes_dela(self):
        Lancamento.objects.filter(pagamento=date(2024, 2, 27)).update(pagamento=date(2024, 2, 1))
        pagas = quadros.pagas_por_ano(self.importacao)
        self.assertEqual(self.valores_de_2024(pagas)[:2], [None, Decimal("96.00")])
        self.assertEqual(pagas.comeca_em, "fev/2024")

    def test_quando_quem_corta_e_a_leitura_a_tela_nao_fala_do_set(self):
        Lancamento.objects.filter(pagamento__lt=date(2024, 9, 1)).delete()
        self.paga(date(2024, 9, 3), "500")
        self.importacao.detalhe = {"financeiro_desde": "2024-09-01"}
        self.importacao.save()
        pagas = quadros.pagas_por_ano(self.importacao)
        self.assertIsNone(pagas.lancado_desde)
        self.assertEqual(pagas.meses[8].celulas[2].valor, Decimal("500.00"))
        html = render_to_string("painel/_monitor_anos.html", {"pagas": pagas, "o_que": "Contas pagas"})
        self.assertNotIn("O SET só tem conta paga", html)

    def test_o_comeco_do_lancado(self):
        leitura = date(2023, 9, 1)
        self.assertEqual(quadros._comeco_do_lancado(None, leitura), leitura)
        self.assertEqual(quadros._comeco_do_lancado(date(2023, 9, 5), leitura), leitura)
        self.assertEqual(quadros._comeco_do_lancado(date(2024, 2, 27), leitura), date(2024, 3, 1))
        self.assertEqual(quadros._comeco_do_lancado(date(2024, 3, 1), leitura), date(2024, 3, 1))
        self.assertEqual(quadros._comeco_do_lancado(date(2024, 12, 15), leitura), date(2025, 1, 1))


class EmAbertoTest(BaseQuadros):
    def test_as_fatias_sao_os_filtros_da_lista(self):
        self.aberta(date(2026, 9, 10), "300")
        self.aberta(date(2026, 9, 25), "200")
        self.aberta(date(2026, 10, 30), "500")
        self.aberta(None, "100")
        rosca, total = quadros.rosca_do_que_esta_em_aberto(self.importacao, hoje=HOJE)
        self.assertEqual(total, Decimal("1100.00"))
        lista = reverse("financeiro:contas_a_pagar")
        self.assertEqual([(f.nome, f.valor, f.endereco) for f in rosca.fatias], [
            ("Atrasadas", Decimal("300.00"), f"{lista}?filtro=atrasados"),
            ("Vencem em até 7 dias", Decimal("200.00"), f"{lista}?filtro=prestes"),
            ("Vencem depois de 7 dias", Decimal("500.00"), f"{lista}?filtro=futura"),
            ("Sem data no SET", Decimal("100.00"), ""),
        ])
        self.assertEqual((rosca.centro, rosca.centro_legenda), ("27,3%", "atrasado"))

    def test_sem_conta_em_aberto_nao_ha_rosca(self):
        self.paga(date(2026, 9, 5), "1000")
        rosca, total = quadros.rosca_do_que_esta_em_aberto(self.importacao, hoje=HOJE)
        self.assertFalse(rosca.tem)
        self.assertEqual(total, Decimal("0"))


class ParaOndeVaiTest(BaseQuadros):
    def test_o_numero_do_plano_de_contas_sai_do_nome(self):
        self.paga(date(2026, 9, 5), "1000", grupo="1.07.01 - Compra p/ Revenda")
        self.paga(date(2026, 9, 6), "500", grupo="1.01.05 - Aluguel")
        rosca = quadros.rosca_de_para_onde_vai(self.importacao)
        self.assertEqual([f.nome for f in rosca.fatias], ["Compra p/ Revenda", "Aluguel"])

    def test_os_oito_maiores_e_o_resto_junto(self):
        for numero in range(1, 11):
            self.paga(date(2026, 9, numero), str(1000 + numero), grupo=f"1.01.{numero:02d} - Grupo {numero}")
        nomes = [f.nome for f in quadros.rosca_de_para_onde_vai(self.importacao).fatias]
        self.assertEqual(len(nomes), 9)
        self.assertEqual(nomes[0], "Grupo 10")
        self.assertEqual(nomes[-1], "outras 2 classificações")

    def test_sobrando_uma_ela_entra_pelo_nome(self):
        """ "outras 1 classificações" não diz nada a quem lê."""
        for numero in range(1, 10):
            self.paga(date(2026, 9, numero), str(1000 + numero), grupo=f"1.01.{numero:02d} - Grupo {numero}")
        nomes = [f.nome for f in quadros.rosca_de_para_onde_vai(self.importacao).fatias]
        self.assertEqual(len(nomes), 9)
        self.assertNotIn("outras", " ".join(nomes))


class TelaTest(BaseQuadros):
    def test_a_tela_mostra_os_tres_quadros(self):
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)
        # Pago 40 dias antes, e não 3: nos primeiros dias do mês, 3 dias atrás ainda é o mês
        # que corre, e o gráfico não tem mês fechado para desenhar (falhava todo começo de mês).
        self.paga(timezone.localdate() - timedelta(days=40), "1000")
        self.aberta(timezone.localdate() - timedelta(days=2), "300")
        self.importacao.data_corte = timezone.localdate() - timedelta(days=1)
        self.importacao.save()
        pagina = self.client.get(reverse("financeiro:contas_a_pagar"))
        self.assertContains(pagina, "Contas pagas mês a mês")
        self.assertContains(pagina, "O que está em aberto")
        self.assertContains(pagina, "Para onde vai o dinheiro")
        self.assertContains(pagina, 'class="monitor monitor-embutido"')
        self.assertContains(pagina, "?filtro=atrasados")

    def test_o_grafico_mostra_os_tres_anos(self):
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)
        corte = timezone.localdate() - timedelta(days=1)
        ano = corte.year
        self.paga(date(ano - 2, 1, 1), "500")
        self.paga(corte - timedelta(days=2), "1000")
        self.importacao.data_corte = corte
        self.importacao.detalhe = {"pagas_desde": f"{ano - 3}-01-01"}
        self.importacao.save()
        pagina = self.client.get(reverse("financeiro:contas_a_pagar")).content.decode()
        for papel, numero in (("agora", ano), ("antes", ano - 1), ("retrasado", ano - 2)):
            self.assertIn(f'<i class="monitor-traco-{papel}" aria-hidden="true"></i> {numero}', pagina)
        self.assertIn(f'<th scope="col" class="numerico">{ano - 2}</th>', pagina)
        self.assertIn('class="monitor-tempo-retrasado"', pagina)
        self.assertIn("os últimos três anos, de janeiro a dezembro", pagina)

    def test_sem_importacao_a_tela_abre_sem_os_quadros(self):
        Importacao.objects.all().delete()
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)
        pagina = self.client.get(reverse("financeiro:contas_a_pagar"))
        self.assertEqual(pagina.status_code, 200)
        self.assertNotContains(pagina, "Contas pagas mês a mês")


class JanelaDaLeituraTest(SimpleTestCase):
    """Meses inteiros, do dia 1º (1.47.0): o pago de três anos (1.48.0), o recebido de 24 meses."""

    def test_as_pagas_comecam_no_dia_primeiro_de_36_meses_antes(self):
        self.assertEqual(firebird.inicio_das_pagas(date(2026, 9, 20)), date(2023, 9, 1))
        self.assertEqual(firebird.inicio_das_pagas(date(2026, 1, 31)), date(2023, 1, 1))

    def test_em_qualquer_mes_o_janeiro_do_retrasado_esta_na_foto(self):
        for mes in range(1, 13):
            corte = date(2026, mes, 28)
            with self.subTest(mes=mes):
                self.assertLessEqual(firebird.inicio_das_pagas(corte), date(2024, 1, 1))

    def test_as_recebidas_continuam_em_24_meses(self):
        """É o recebido que traz o nome do cliente: ele não cresce junto com o pago."""
        self.assertEqual(firebird.inicio_das_recebidas(date(2026, 9, 20)), date(2024, 9, 1))
        self.assertEqual(firebird.inicio_das_recebidas(date(2026, 1, 31)), date(2024, 1, 1))

    def test_a_consulta_do_set_usa_essas_datas(self):
        consultas = []

        def linhas(sql, parametros):
            consultas.append((sql, parametros))
            return []

        firebird._ler_financeiro(linhas, date(2026, 9, 20))
        self.assertEqual(len(consultas), 2)  # a pagar e a receber
        (sql_pagar, param_pagar), (sql_receber, param_receber) = consultas
        self.assertIn("from contaspag c", sql_pagar)
        self.assertIn("from contasrec c", sql_receber)
        for sql in (sql_pagar, sql_receber):
            self.assertIn("c.datapag >= ?", sql)
        self.assertEqual(param_pagar[1], date(2023, 9, 1))
        self.assertEqual(param_receber[1], date(2024, 9, 1))
