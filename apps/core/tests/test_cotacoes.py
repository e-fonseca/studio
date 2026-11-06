"""A faixa do topo (1.50.0): o que vem da internet, o que a tela mostra, e a sessão parada
que continua acabando mesmo com a tela pedindo o dólar a cada minuto."""

from datetime import datetime, timedelta, timezone as fuso
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.contas import sessao
from apps.contas.perfis import ADMINISTRACAO, VENDEDOR
from apps.core import cotacoes
from apps.core.fabricas import SENHA_TESTE, usuario

AGORA = datetime(2026, 11, 6, 13, 0, tzinfo=fuso.utc)  # 10:00 em São Paulo


def dolar(ask="5.4231", variacao="0.31", quando=AGORA):
    return {"USDBRL": {"code": "USD", "codein": "BRL", "bid": "5.4225", "ask": ask,
                       "pctChange": variacao, "timestamp": str(int(quando.timestamp()))}}


def acao(preco, variacao, quando="2026-11-06T12:30:00.000Z"):
    return {"results": [{"regularMarketPrice": preco, "regularMarketChangePercent": variacao,
                         "regularMarketTime": quando}]}


class Internet:
    """Faz as vezes da internet: responde pelo endereço e falha no que não conhece."""

    def __init__(self, respostas):
        self.respostas, self.pedidos = respostas, []

    def __call__(self, endereco):
        self.pedidos.append(endereco)
        if endereco not in self.respostas:
            raise OSError("sem internet")
        return self.respostas[endereco]


def internet_inteira():
    respostas = {cotacoes.ENDERECO_DO_DOLAR: dolar()}
    precos = {"PETR4": (38.1, -0.5), "VALE3": (61.2, 2.1), "ITUB4": (40, 0), "MGLU3": (9.87, -3.2)}
    for codigo, (preco, variacao) in precos.items():
        respostas[cotacoes.ENDERECO_DA_ACAO.format(codigo=codigo)] = acao(preco, variacao)
    return Internet(respostas)


class LeituraTest(SimpleTestCase):
    def test_o_dolar_comercial_e_o_preco_de_venda(self):
        lido = cotacoes.ler_dolar(dolar())
        self.assertEqual((lido["valor"], lido["variacao"]), ("5.4231", "0.31"))
        self.assertEqual(lido["hora"], AGORA.isoformat())

    def test_resposta_estranha_nunca_vira_cotacao(self):
        for dados in ({}, [], None, {"USDBRL": {"ask": "abc"}}, {"USDBRL": {"ask": "0"}},
                      {"status": 429, "message": "limite de pedidos"}):
            self.assertIsNone(cotacoes.ler_dolar(dados))
        for dados in ({}, {"results": []}, {"error": True, "message": "token"}, acao(None, 1), acao(10, None)):
            self.assertIsNone(cotacoes.ler_acao(dados, "PETR4", "Petrobras"))


class AtualizarTest(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_guarda_o_dolar_e_as_quatro_acoes(self):
        internet = internet_inteira()
        guardado = cotacoes.atualizar(abrir=internet, agora=AGORA)
        self.assertEqual(guardado["dolar"]["valor"], "5.4231")
        self.assertEqual([a["codigo"] for a in guardado["acoes"]], ["PETR4", "VALE3", "ITUB4", "MGLU3"])
        self.assertEqual(len(internet.pedidos), 5)

    def test_antes_do_prazo_nao_volta_a_internet(self):
        cotacoes.atualizar(abrir=internet_inteira(), agora=AGORA)
        internet = internet_inteira()
        cotacoes.atualizar(abrir=internet, agora=AGORA + timedelta(seconds=30))
        self.assertEqual(internet.pedidos, [])
        cotacoes.atualizar(abrir=internet, agora=AGORA + timedelta(minutes=2))
        self.assertEqual(internet.pedidos, [cotacoes.ENDERECO_DO_DOLAR])

    def test_sem_internet_fica_o_ultimo_valor(self):
        cotacoes.atualizar(abrir=internet_inteira(), agora=AGORA)
        guardado = cotacoes.atualizar(abrir=Internet({}), agora=AGORA + timedelta(hours=1))
        self.assertEqual(guardado["dolar"]["valor"], "5.4231")
        self.assertEqual(len(guardado["acoes"]), 4)


class TelaTest(SimpleTestCase):
    def test_altas_e_quedas_em_grupos_com_a_hora_do_preco(self):
        cache.clear()
        tela = cotacoes.para_tela(cotacoes.atualizar(abrir=internet_inteira(), agora=AGORA), agora=AGORA)
        self.assertEqual(tela["dolar"]["valor"], "R$ 5,42")
        self.assertEqual((tela["dolar"]["variacao"], tela["dolar"]["seta"], tela["dolar"]["sentido"]),
                         ("+0,31%", "▲", "alta"))
        self.assertEqual(tela["dolar"]["hora"], "às 10:00")
        grupos = {g["titulo"]: [a["codigo"] for a in g["acoes"]] for g in tela["grupos"]}
        self.assertEqual(grupos, {"Em alta": ["VALE3"], "Em queda": ["MGLU3", "PETR4"], "Sem mudança": ["ITUB4"]})
        self.assertEqual(tela["hora_das_acoes"], "às 09:30")

    def test_preco_de_outro_dia_diz_o_dia(self):
        tela = cotacoes.para_tela({"dolar": {"valor": "5.42", "variacao": "-0.1",
                                             "hora": "2026-11-05T20:59:00+00:00"}}, agora=AGORA)
        self.assertEqual((tela["dolar"]["hora"], tela["dolar"]["sentido"]), ("em 05/11 às 17:59", "queda"))

    def test_sem_nada_guardado_fica_so_o_relogio(self):
        self.assertEqual(cotacoes.para_tela({}, agora=AGORA), {"dolar": None, "grupos": [], "hora_das_acoes": ""})


class SegundoPlanoTest(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @override_settings(COTACOES_NA_INTERNET=True)
    def test_a_tela_nunca_espera_a_internet_e_busca_uma_vez_so(self):
        with mock.patch.object(cotacoes.threading, "Thread") as fio:
            cotacoes.faixa(agora=AGORA)
            cotacoes.faixa(agora=AGORA)
        self.assertEqual(fio.call_count, 1)
        fio.return_value.start.assert_called_once_with()

    def test_nos_testes_ninguem_vai_a_internet(self):
        with mock.patch.object(cotacoes.threading, "Thread") as fio:
            cotacoes.faixa(agora=AGORA)
        fio.assert_not_called()


class TopoTest(TestCase):
    def setUp(self):
        cache.clear()
        cotacoes.atualizar(abrir=internet_inteira(), agora=timezone.now())

    def entrar(self, perfil=ADMINISTRACAO):
        usuario("teste", perfil)
        self.client.login(username="teste", password=SENHA_TESTE)

    def test_o_topo_tem_relogio_dolar_e_acoes_para_quem_entrou(self):
        self.entrar()
        html = self.client.get(reverse("contas:trocar_senha")).content.decode()
        for trecho in ('id="cotacao-faixa"', 'id="cotacao-relogio"', "Dólar comercial", "R$ 5,42", "Vale",
                       "Em queda", "js/cotacoes.js"):
            self.assertIn(trecho, html)

    def test_o_vendedor_fica_so_com_o_relogio(self):
        """A tela do vendedor não mostra R$ nenhum (condição do Edson), nem o do dólar."""
        self.entrar(VENDEDOR)
        html = self.client.get(reverse("contas:trocar_senha")).content.decode()
        self.assertIn('id="cotacao-relogio"', html)
        self.assertNotIn("Dólar comercial", html)
        self.assertNotIn("data-endereco", html)
        self.assertEqual(self.client.get(reverse("core:cotacoes")).status_code, 403)

    def test_a_entrada_nao_tem_faixa(self):
        self.assertNotIn("cotacao-faixa", self.client.get(reverse("contas:entrar")).content.decode())

    def marcar(self, minutos):
        guardada = self.client.session
        quando = (timezone.now() - timedelta(minutes=minutos)).isoformat()
        guardada[sessao.CHAVE] = quando
        guardada[sessao.VISTO] = quando
        guardada.save()
        return quando

    def test_o_pedido_da_tela_traz_o_trecho_e_nao_conta_como_uso(self):
        self.entrar()
        visto = self.marcar(10)
        resposta = self.client.get(reverse("core:cotacoes"))
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("Dólar comercial", resposta.json()["html"])
        self.assertEqual(self.client.session[sessao.VISTO], visto)

    def test_sessao_parada_responde_401_para_a_tela_ir_para_a_entrada(self):
        self.entrar()
        self.marcar(31)
        resposta = self.client.get(reverse("core:cotacoes"))
        self.assertEqual(resposta.status_code, 401)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_sem_entrar_nao_ha_cotacao(self):
        self.assertEqual(self.client.get(reverse("core:cotacoes")).status_code, 302)
