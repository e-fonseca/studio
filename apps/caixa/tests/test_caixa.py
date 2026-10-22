"""A tela de caixa: filtros, a conta do turno e quem pode abrir.

Pedido do Edson em 08/10/2026. O que estes testes travam: a conta de fechamento
(saldo inicial + entrou - saiu), o caixa esquecido aberto aparecendo fora do
período escolhido, e o vendedor continuando sem ver dinheiro.
"""

import datetime as dt
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.caixa import servicos
from apps.caixa.models import CaixaImportado, MovimentoCaixa
from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.importacao.models import Importacao

CORTE = date(2026, 9, 20)


def _hora(dia, hora, minuto=0):
    """Hora no fuso da loja: a tela mostra 09:00 porque o caixa abriu às 09:00 aqui."""
    return timezone.make_aware(dt.datetime(2026, 9, dia, hora, minuto))


def _importacao():
    return Importacao.objects.create(
        origem=Importacao.Origem.BANCO,
        situacao=Importacao.Situacao.CONCLUIDA,
        iniciada_em=_hora(21, 0, 20),
        concluida_em=_hora(21, 0, 21),
        data_corte=CORTE,
        dias_abertos_12m=300,
        produtos=1,
    )


def _caixa(importacao, id_set, dia_do_mes, **extra):
    dados = {
        "operador": "ANA BEATRIZ",
        "operador_fechamento": "ANA BEATRIZ",
        "dia": date(2026, 9, dia_do_mes),
        "aberto_em": _hora(dia_do_mes, 9),
        "fechado_em": _hora(dia_do_mes, 18, 20),
        "saldo_inicial": Decimal("379.40"),
        "recebido": Decimal("8067.50"),
        "sangrias": Decimal("266.25"),
        "saldo_final": Decimal("8180.65"),
        "situacao": CaixaImportado.Situacao.FECHADO,
        "movimentos": 40,
        "por_forma": {"PIX": "5000.00", "CARTAO DEBITO": "3067.50"},
    }
    dados.update(extra)
    return CaixaImportado.objects.create(importacao=importacao, id_set=id_set, **dados)


class ContaDoTurno(TestCase):
    """O número que a tela mostra na coluna Confere."""

    def setUp(self):
        self.importacao = _importacao()

    def test_saldo_final_do_set_igual_a_conta_do_turno(self):
        # Os valores são do caixa 970 do backup de 20/09/2026: 379,40 + 8.067,50 - 266,25.
        caixa = _caixa(self.importacao, 970, 19)
        self.assertEqual(caixa.saldo_calculado, Decimal("8180.65"))
        self.assertEqual(caixa.diferenca, Decimal("0.00"))
        self.assertTrue(caixa.confere)

    def test_centavo_de_diferenca_e_arredondamento_e_nao_erro(self):
        caixa = _caixa(self.importacao, 971, 19, saldo_final=Decimal("8180.66"))
        self.assertTrue(caixa.confere)

    def test_turno_que_nao_fecha_mostra_a_diferenca(self):
        caixa = _caixa(self.importacao, 972, 19, saldo_final=Decimal("7680.65"))
        self.assertFalse(caixa.confere)
        self.assertEqual(caixa.diferenca, Decimal("-500.00"))

    def test_caixa_aberto_nao_tem_diferenca_para_comparar(self):
        caixa = _caixa(self.importacao, 973, 19, fechado_em=None, saldo_final=None,
                       situacao=CaixaImportado.Situacao.ABERTO)
        self.assertIsNone(caixa.diferenca)
        self.assertFalse(caixa.confere)
        self.assertEqual(caixa.tempo_aberto, "")

    def test_tempo_aberto_sai_em_horas_e_minutos(self):
        caixa = _caixa(self.importacao, 974, 19)
        self.assertEqual(caixa.tempo_aberto, "9h20")


class Recorte(TestCase):
    """Período, operador e situação."""

    def setUp(self):
        self.importacao = _importacao()
        _caixa(self.importacao, 1, 19)
        _caixa(self.importacao, 2, 18, operador="MOIZES")
        # Fora dos 30 dias: a data de corte é 20/09, então julho não entra.
        _caixa(self.importacao, 3, 19, dia=date(2026, 7, 10), aberto_em=_hora(19, 9))

    def test_periodo_padrao_corta_o_que_e_antigo(self):
        tela = servicos.montar(self.importacao)
        self.assertEqual(tela.resumo.caixas, 2)
        self.assertEqual([c.id_set for c in tela.caixas], [1, 2])

    def test_tudo_traz_todos_os_turnos(self):
        tela = servicos.montar(self.importacao, periodo="tudo")
        self.assertEqual(tela.resumo.caixas, 3)

    def test_filtro_de_operador(self):
        tela = servicos.montar(self.importacao, operador="MOIZES")
        self.assertEqual([c.id_set for c in tela.caixas], [2])
        self.assertIn("ANA BEATRIZ", tela.operadores)

    def test_operador_inventado_na_url_nao_filtra_nada(self):
        tela = servicos.montar(self.importacao, operador="NINGUEM")
        self.assertEqual(tela.filtro_operador, "")
        self.assertEqual(tela.resumo.caixas, 2)

    def test_soma_recebido_e_media_por_dia(self):
        tela = servicos.montar(self.importacao)
        self.assertEqual(tela.resumo.recebido, Decimal("16135.00"))
        self.assertEqual(tela.resumo.dias, 2)
        self.assertEqual(tela.resumo.media_por_dia, Decimal("8067.50"))

    def test_sem_importacao_a_tela_vem_vazia_e_nao_estoura(self):
        tela = servicos.montar(None)
        self.assertFalse(tela.tem_dados)
        self.assertEqual(tela.resumo.caixas, 0)


class CaixaEsquecido(TestCase):
    """Caixa aberto há mais de um dia aparece seja qual for o período escolhido."""

    def setUp(self):
        self.importacao = _importacao()

    def test_aberto_hoje_nao_e_esquecido(self):
        caixa = _caixa(self.importacao, 10, 20, fechado_em=None, saldo_final=None,
                       situacao=CaixaImportado.Situacao.ABERTO)
        self.assertFalse(servicos.esta_esquecido(caixa, CORTE))
        self.assertEqual(servicos.montar(self.importacao).esquecidos, [])

    def test_aberto_desde_abril_aparece_mesmo_filtrando_30_dias(self):
        _caixa(self.importacao, 11, 19, dia=date(2026, 4, 30),
               aberto_em=timezone.make_aware(dt.datetime(2026, 4, 30, 9)),
               fechado_em=None, saldo_final=None,
               situacao=CaixaImportado.Situacao.ABERTO)
        tela = servicos.montar(self.importacao, periodo="30d")
        self.assertEqual([c.id_set for c in tela.esquecidos], [11])
        # E continua fora da tabela, porque abril não está nos 30 dias.
        self.assertEqual(tela.caixas, [])


class MovimentosDoTurno(TestCase):
    def setUp(self):
        self.importacao = _importacao()
        self.caixa = _caixa(self.importacao, 20, 19)
        MovimentoCaixa.objects.create(
            caixa=self.caixa, id_set=1, quando=_hora(19, 15), tipo=MovimentoCaixa.Tipo.SANGRIA,
            descricao="ALMOCO", valor=Decimal("266.25"), operador="ANA BEATRIZ")

    def test_formas_de_pagamento_em_ordem_de_valor_com_largura_inteira(self):
        formas = servicos.formas_do_caixa(self.caixa)
        self.assertEqual([f["nome"] for f in formas], ["PIX", "CARTAO DEBITO"])
        self.assertEqual(formas[0]["largura"], 100)
        # Largura tem que ser int: Decimal dentro de style= sai com vírgula e o CSS ignora.
        for forma in formas:
            self.assertIsInstance(forma["largura"], int)

    def test_caixa_sem_forma_de_pagamento_nao_divide_por_zero(self):
        vazio = _caixa(self.importacao, 21, 19, por_forma={})
        self.assertEqual(servicos.formas_do_caixa(vazio), [])

    def test_movimentos_vem_em_ordem_de_hora(self):
        MovimentoCaixa.objects.create(
            caixa=self.caixa, id_set=2, quando=_hora(19, 10), tipo=MovimentoCaixa.Tipo.PAGAMENTO,
            descricao="AGUA", valor=Decimal("80.00"))
        self.assertEqual([m.descricao for m in servicos.movimentos_do_caixa(self.caixa)],
                         ["AGUA", "ALMOCO"])


class Telas(TestCase):
    def setUp(self):
        self.importacao = _importacao()
        self.caixa = _caixa(self.importacao, 970, 19)
        MovimentoCaixa.objects.create(
            caixa=self.caixa, id_set=1, quando=_hora(19, 15), tipo=MovimentoCaixa.Tipo.SANGRIA,
            descricao="TROCO BALOES", valor=Decimal("266.25"), operador="ANA BEATRIZ")
        usuario("gerente-caixa", ADMINISTRACAO)
        usuario("admin-caixa", ADMINISTRATIVO)
        usuario("balcao-caixa", VENDEDOR)

    def _entrar(self, quem):
        self.assertTrue(self.client.login(username=quem, password=SENHA_TESTE))

    def test_lista_mostra_dia_horas_operador_e_valores(self):
        self._entrar("gerente-caixa")
        resposta = self.client.get(reverse("caixa:lista"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "19/09/2026")
        self.assertContains(resposta, "ANA BEATRIZ")
        self.assertContains(resposta, "09:00")
        self.assertContains(resposta, "18:20")
        self.assertContains(resposta, "8.180,65")

    def test_administrativo_tambem_ve_o_caixa(self):
        self._entrar("admin-caixa")
        self.assertEqual(self.client.get(reverse("caixa:lista")).status_code, 200)

    def test_vendedor_nao_ve_caixa(self):
        self._entrar("balcao-caixa")
        self.assertEqual(self.client.get(reverse("caixa:lista")).status_code, 403)
        self.assertEqual(self.client.get(reverse("caixa:turno", args=[970])).status_code, 403)

    def test_sem_entrar_vai_para_o_login(self):
        resposta = self.client.get(reverse("caixa:lista"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("contas:entrar"), resposta["Location"])

    def test_turno_mostra_os_movimentos_e_a_conferencia(self):
        self._entrar("gerente-caixa")
        resposta = self.client.get(reverse("caixa:turno", args=[970]))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "TROCO BALOES")
        self.assertContains(resposta, "Sangria")
        self.assertContains(resposta, "PIX")

    def test_turno_de_outra_importacao_nao_abre(self):
        # O link é pelo número do SET; se o turno não está na importação mais nova, 404.
        self._entrar("gerente-caixa")
        self.assertEqual(self.client.get(reverse("caixa:turno", args=[999])).status_code, 404)

    def test_menu_tem_caixa_para_quem_pode(self):
        self._entrar("gerente-caixa")
        resposta = self.client.get(reverse("caixa:lista"))
        self.assertContains(resposta, reverse("caixa:lista"))


class JanelaTerminaNoUltimoCaixa(TestCase):
    """Caixa aberto depois do último dia de venda não pode desaparecer da tela."""

    def test_caixa_aberto_depois_do_corte_entra_no_periodo_padrao(self):
        importacao = _importacao()
        # É o caso real do turno 971: aberto em 21/09 com data de corte em 20/09.
        _caixa(importacao, 971, 21, fechado_em=None, saldo_final=None,
               situacao=CaixaImportado.Situacao.ABERTO)
        tela = servicos.montar(importacao)
        self.assertEqual([c.id_set for c in tela.caixas], [971])
        self.assertEqual(tela.resumo.abertos, 1)
        self.assertEqual(tela.ate, date(2026, 9, 21))


class CaixaEsquecidoNaVirada(TestCase):
    """O turno da noite é o que mais engole a venda do dia seguinte, e era o que escapava.

    Achado na revisão geral de 15/10/2026. A data da abertura saía de `.date()` em cima do
    campo, que é gravado em UTC: em São Paulo (UTC-3) todo turno aberto das 21h em diante
    cai no DIA SEGUINTE em UTC. O caixa aberto às 21:30 do dia 19 e esquecido a noite
    inteira aparecia como aberto "no dia 20", igual à data da foto, e nunca era apontado.
    A loja vende nesse horário: o Dashboard tem faixa de hora até a meia-noite.
    """

    def setUp(self):
        self.importacao = _importacao()

    def _aberto_as(self, dia, hora, minuto=0):
        return _caixa(self.importacao, 77, dia, aberto_em=_hora(dia, hora, minuto),
                      fechado_em=None, saldo_final=None,
                      situacao=CaixaImportado.Situacao.ABERTO)

    def test_aberto_as_21h30_do_dia_anterior_e_esquecido(self):
        caixa = self._aberto_as(19, 21, 30)
        self.assertTrue(servicos.esta_esquecido(caixa, CORTE))
        self.assertEqual([c.id_set for c in servicos.montar(self.importacao).esquecidos], [77])

    def test_aberto_as_9h_do_dia_anterior_tambem_e_esquecido(self):
        """A mesma régua de sempre, que já funcionava: não se perde na correção."""
        self.assertTrue(servicos.esta_esquecido(self._aberto_as(19, 9), CORTE))

    def test_aberto_as_21h30_do_proprio_dia_da_foto_nao_e_esquecido(self):
        """Ainda é o turno de hoje: apontar seria cobrar o fechamento antes da hora."""
        self.assertFalse(servicos.esta_esquecido(self._aberto_as(20, 21, 30), CORTE))

    def test_caixa_fechado_nunca_e_esquecido(self):
        caixa = _caixa(self.importacao, 78, 19)
        self.assertFalse(servicos.esta_esquecido(caixa, CORTE))

    def test_a_tela_nao_promete_horas_que_nao_conta(self):
        """A conta é de dias, porque a data de corte não tem hora: a frase diz dias."""
        usuario("gerente_caixa", ADMINISTRACAO)
        self.client.login(username="gerente_caixa", password=SENHA_TESTE)
        self._aberto_as(19, 21, 30)
        corpo = self.client.get(reverse("caixa:lista")).content.decode()
        self.assertIn("de um dia para o outro", corpo)
        self.assertNotIn("mais de 24 horas", corpo)
