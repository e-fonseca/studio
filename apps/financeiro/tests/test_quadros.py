"""Os quadros do Dashboard em Contas a pagar (1.47.0).

Pedido do Edson em 04/11/2026, com o print do Dashboard: "usar esse formato de gráfico
também em contas a pagar". O que estes testes protegem:

1. **A comparação é justa.** O mês que corre se compara com o mesmo pedaço do ano
   passado, e o ano passado só entra quando o mês dele está inteiro na foto do SET.
2. **A cor é a do caixa.** No faturamento, mais é bom; nas contas pagas, mais é ruim.
3. **As fatias da rosca são os filtros da lista**, e o nome de cada uma abre a lista dela.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.core.cache import cache
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
            detalhe={"financeiro_desde": "2024-09-01"},
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


class PagasMesAMesTest(BaseQuadros):
    def setUp(self):
        super().setUp()
        self.paga(date(2026, 9, 5), "1000")
        self.paga(date(2025, 9, 10), "800")
        self.paga(date(2025, 9, 25), "500")    # depois do dia 20: fora do pedaço comparado
        self.paga(date(2025, 10, 15), "2000")
        self.paga(date(2024, 10, 15), "1000")
        self.paga(date(2025, 11, 3), "300")
        self.paga(date(2024, 11, 3), "600")
        self.paga(date(2026, 9, 6), "9000", tipo=Lancamento.Tipo.RECEBER)  # recebimento não é conta paga

    def mes(self, rotulo):
        return next(mes for mes in quadros.pagas_mes_a_mes(self.importacao) if mes.rotulo == rotulo)

    def test_sao_treze_meses_terminando_no_do_corte(self):
        meses = quadros.pagas_mes_a_mes(self.importacao)
        self.assertEqual(len(meses), 13)
        self.assertEqual((meses[0].rotulo, meses[-1].rotulo), ("set/25", "set/26"))

    def test_o_mes_que_corre_se_compara_com_o_mesmo_pedaco_do_ano_passado(self):
        setembro = self.mes("set/26")
        self.assertTrue(setembro.parcial)
        self.assertEqual(setembro.dia_parcial, 20)
        self.assertEqual(setembro.valor, Decimal("1000.00"))
        self.assertEqual(setembro.valor_ano_passado, Decimal("800.00"))

    def test_mes_inteiro_contra_o_mes_inteiro_do_ano_passado(self):
        outubro = self.mes("out/25")
        self.assertFalse(outubro.parcial)
        self.assertEqual(outubro.valor, Decimal("2000.00"))
        self.assertEqual(outubro.valor_ano_passado, Decimal("1000.00"))

    def test_pagar_mais_que_no_ano_passado_e_vermelho(self):
        self.assertEqual(self.mes("out/25").sentido, "ruim")
        self.assertEqual(self.mes("nov/25").sentido, "bom")
        # No faturamento a mesma subida é verde.
        self.assertEqual(dashboard.Mes("Out/25", Decimal("2000"), valor_ano_passado=Decimal("1000")).sentido, "bom")

    def test_foto_antiga_nao_compara_o_mes_que_ela_tem_pela_metade(self):
        """Até a 1.46.0 a leitura começava em "corte menos 730 dias", no meio de setembro."""
        self.importacao.detalhe = {}
        self.importacao.save()
        self.assertIsNone(self.mes("set/25").valor_ano_passado)
        self.assertEqual(self.mes("out/25").valor_ano_passado, Decimal("1000.00"))

    def test_foto_nova_compara_desde_o_primeiro_mes(self):
        self.assertEqual(self.mes("set/25").valor_ano_passado, Decimal("0.00"))

    def test_sem_importacao_nao_ha_mes(self):
        self.assertEqual(quadros.pagas_mes_a_mes(None), [])


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
        self.paga(timezone.localdate() - timedelta(days=3), "1000")
        self.aberta(timezone.localdate() - timedelta(days=2), "300")
        self.importacao.data_corte = timezone.localdate() - timedelta(days=1)
        self.importacao.save()
        pagina = self.client.get(reverse("financeiro:contas_a_pagar"))
        self.assertContains(pagina, "Contas pagas mês a mês")
        self.assertContains(pagina, "O que está em aberto")
        self.assertContains(pagina, "Para onde vai o dinheiro")
        self.assertContains(pagina, 'class="monitor monitor-embutido"')
        self.assertContains(pagina, "?filtro=atrasados")

    def test_sem_importacao_a_tela_abre_sem_os_quadros(self):
        Importacao.objects.all().delete()
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)
        pagina = self.client.get(reverse("financeiro:contas_a_pagar"))
        self.assertEqual(pagina.status_code, 200)
        self.assertNotContains(pagina, "Contas pagas mês a mês")


class JanelaDaLeituraTest(SimpleTestCase):
    """Desde a 1.47.0 o pago e o recebido se leem em meses inteiros, do dia 1º."""

    def test_a_leitura_comeca_no_dia_primeiro_de_24_meses_antes(self):
        self.assertEqual(firebird.inicio_do_financeiro(date(2026, 9, 20)), date(2024, 9, 1))
        self.assertEqual(firebird.inicio_do_financeiro(date(2026, 1, 31)), date(2024, 1, 1))

    def test_a_consulta_do_set_usa_essa_data(self):
        consultas = []

        def linhas(sql, parametros):
            consultas.append((sql, parametros))
            return []

        firebird._ler_financeiro(linhas, date(2026, 9, 20))
        self.assertEqual(len(consultas), 2)  # a pagar e a receber
        for sql, parametros in consultas:
            self.assertIn("c.datapag >= ?", sql)
            self.assertEqual(parametros[1], date(2024, 9, 1))
