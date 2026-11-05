"""Fluxo de caixa do Studio: SET e projetos juntos, sem contar nada duas vezes."""

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.contas.perfis import ADMINISTRACAO, COMERCIAL
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.financeiro import fluxo
from apps.financeiro.models import Lancamento, PagamentoPrevisto
from apps.importacao.models import Importacao
from apps.projetos.models import Parcela, Projeto

HOJE = date(2026, 11, 5)


def mes(resultado, ano, numero):
    return next(m for m in resultado.meses if (m.ano, m.mes) == (ano, numero))


class FluxoTest(TestCase):
    def setUp(self):
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO, situacao=Importacao.Situacao.CONCLUIDA,
            data_corte=date(2026, 11, 4))
        self.projeto = Projeto.objects.create(titulo="Mesa", cliente_nome="Ana", valor_venda=10000)

    def lanca(self, tipo, valor, vencimento, pagamento=None, valor_pago=None):
        return Lancamento.objects.create(
            importacao=self.importacao, tipo=tipo, valor=Decimal(valor), vencimento=vencimento,
            pagamento=pagamento, valor_pago=Decimal(valor_pago if valor_pago is not None else (valor if pagamento else 0)))

    def parcela(self, tipo, valor, vencimento, pago_em=None, no_set=False, projeto=None):
        return Parcela.objects.create(projeto=projeto or self.projeto, tipo=tipo, valor=Decimal(valor),
                                      vencimento=vencimento, pago_em=pago_em, lancada_no_set=no_set)

    def test_janela_de_tres_meses_para_tras_e_seis_para_frente(self):
        r = fluxo.montar(self.importacao, HOJE)
        self.assertEqual([m.rotulo for m in r.meses][0], "ago/2026")
        self.assertEqual([m.rotulo for m in r.meses][-1], "mai/2027")
        self.assertEqual([m.momento for m in r.meses].count("atual"), 1)

    def test_realizado_vem_do_set_e_dos_projetos(self):
        self.lanca("receber", "1000", date(2026, 9, 10), pagamento=date(2026, 9, 12))
        self.lanca("pagar", "400", date(2026, 9, 10), pagamento=date(2026, 9, 11), valor_pago="420")
        self.parcela("receber", "5000", date(2026, 9, 1), pago_em=date(2026, 9, 2))
        self.parcela("oficina", "2000", date(2026, 9, 1), pago_em=date(2026, 9, 3))
        setembro = mes(fluxo.montar(self.importacao, HOJE), 2026, 9)
        self.assertEqual(setembro.entrou, Decimal("6000"))
        # O valor pago (com juros), e não o da conta.
        self.assertEqual(setembro.saiu, Decimal("2420"))

    def test_parcela_lancada_no_set_conta_uma_vez(self):
        self.lanca("receber", "3000", date(2026, 12, 10))
        self.parcela("receber", "3000", date(2026, 12, 10), no_set=True)
        self.assertEqual(mes(fluxo.montar(self.importacao, HOJE), 2026, 12).vai_entrar, Decimal("3000"))

    def test_previsto_e_projecao_acumulada(self):
        self.lanca("pagar", "1000", date(2026, 12, 5))
        self.parcela("receber", "4000", date(2026, 12, 20))
        self.parcela("oficina", "1500", date(2027, 1, 10))
        PagamentoPrevisto.objects.create(descricao="Aluguel", valor=Decimal("2000"), vencimento=date(2027, 1, 5))
        r = fluxo.montar(self.importacao, HOJE)
        self.assertEqual(mes(r, 2026, 12).previsto, Decimal("3000"))
        self.assertEqual(mes(r, 2027, 1).previsto, Decimal("-3500"))
        self.assertEqual(mes(r, 2027, 1).saldo_projetado, Decimal("-500"))

    def test_atrasado_entra_no_mes_corrente_e_aparece_a_parte(self):
        self.lanca("pagar", "700", date(2026, 10, 20))
        self.parcela("receber", "900", date(2026, 10, 30))
        r = fluxo.montar(self.importacao, HOJE)
        self.assertEqual((r.atrasado_sair, r.atrasado_entrar), (Decimal("700"), Decimal("900")))
        atual = mes(r, 2026, 11)
        self.assertEqual((atual.vai_sair, atual.vai_entrar), (Decimal("700"), Decimal("900")))
        self.assertEqual(mes(r, 2026, 10).vai_sair, Decimal("0"), "o passado não projeta")

    def test_projeto_cancelado_nao_projeta(self):
        cancelado = Projeto.objects.create(titulo="X", cliente_nome="Y", etapa="cancelado")
        self.parcela("receber", "800", date(2026, 12, 1), projeto=cancelado)
        self.assertEqual(mes(fluxo.montar(self.importacao, HOJE), 2026, 12).vai_entrar, Decimal("0"))

    def test_sem_importacao_so_projetos(self):
        self.parcela("receber", "800", date(2026, 12, 1))
        r = fluxo.montar(None, HOJE)
        self.assertFalse(r.tem_set)
        self.assertEqual(mes(r, 2026, 12).vai_entrar, Decimal("800"))


class TelaTest(TestCase):
    def test_a_tela_abre_e_mostra_o_sinal(self):
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)
        projeto = Projeto.objects.create(titulo="Mesa", cliente_nome="Ana")
        Parcela.objects.create(projeto=projeto, tipo="oficina", valor=Decimal("1234.50"),
                               vencimento=timezone.localdate() + timedelta(days=40))
        pagina = self.client.get(reverse("financeiro:fluxo"))
        self.assertContains(pagina, "Fluxo de caixa")
        self.assertContains(pagina, "Projetado acumulado")
        # O último mês do período, e o saldo dele com sinal escrito (era "até ," em branco).
        self.assertContains(pagina, "− R$ 1.234,50</span>")

    def test_quem_nao_ve_dinheiro_nao_entra(self):
        usuario("sdr", COMERCIAL)
        self.client.login(username="sdr", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("financeiro:fluxo")).status_code, 403)
