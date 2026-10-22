"""Sugestões de compra escritas pela equipe: quem viu a prateleira vazia escreve."""

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.auditoria.models import EventoAuditoria
from apps.compras import equipe
from apps.compras.models import SugestaoDeCompra
from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario


class TestRegistro(TestCase):
    def setUp(self):
        self.pessoa = usuario("ana", ADMINISTRATIVO)

    def test_guarda_produto_motivo_e_quem_escreveu_com_data_e_hora(self):
        sugestao = equipe.registrar_sugestao(
            produto="TAPETE SISAL 2X3", motivo=SugestaoDeCompra.Motivo.ACABOU,
            quantidade=Decimal("4"), usuario=self.pessoa)
        self.assertEqual(sugestao.situacao, SugestaoDeCompra.Situacao.ABERTA)
        self.assertEqual(sugestao.criada_por, self.pessoa)
        self.assertIsNotNone(sugestao.criada_em)
        self.assertEqual(sugestao.quem_escreveu, "Ana")

    def test_sem_produto_nao_grava(self):
        with self.assertRaises(equipe.ErroDeSugestao):
            equipe.registrar_sugestao(produto="  ", usuario=self.pessoa)
        self.assertEqual(SugestaoDeCompra.objects.count(), 0)

    def test_motivo_inventado_cai_no_padrao_em_vez_de_recusar(self):
        sugestao = equipe.registrar_sugestao(produto="CARVAO", motivo="porque-eu-quis",
                                             usuario=self.pessoa)
        self.assertEqual(sugestao.motivo, SugestaoDeCompra.Motivo.CLIENTE_PEDIU)

    def test_o_registro_entra_na_auditoria(self):
        equipe.registrar_sugestao(produto="CARVAO", usuario=self.pessoa)
        self.assertTrue(
            EventoAuditoria.objects.filter(acao="compras.sugestao_registrada").exists())


class TestQuantidade(TestCase):
    def test_aceita_virgula_e_ponto(self):
        self.assertEqual(equipe.quantidade_informada("2,5"), Decimal("2.500"))
        self.assertEqual(equipe.quantidade_informada("3"), Decimal("3.000"))

    def test_em_branco_e_valido_porque_nem_sempre_se_sabe_quanto(self):
        self.assertIsNone(equipe.quantidade_informada(""))
        self.assertIsNone(equipe.quantidade_informada(None))

    def test_recusa_texto_e_zero(self):
        for errado in ("muitos", "0", "-2"):
            with self.assertRaises(equipe.ErroDeSugestao):
                equipe.quantidade_informada(errado)


class TestResposta(TestCase):
    def setUp(self):
        self.pessoa = usuario("ana", ADMINISTRATIVO)
        self.gerente = usuario("gerente", ADMINISTRACAO)
        self.sugestao = equipe.registrar_sugestao(produto="CARVAO", usuario=self.pessoa)

    def test_a_gerencia_marca_o_que_foi_feito(self):
        equipe.responder(self.sugestao, situacao=SugestaoDeCompra.Situacao.COMPRADA,
                         resposta="Entrou na compra da semana.", usuario=self.gerente)
        self.sugestao.refresh_from_db()
        self.assertEqual(self.sugestao.situacao, SugestaoDeCompra.Situacao.COMPRADA)
        self.assertEqual(self.sugestao.respondida_por, self.gerente)
        self.assertIsNotNone(self.sugestao.respondida_em)

    def test_situacao_invalida_nao_passa(self):
        with self.assertRaises(equipe.ErroDeSugestao):
            equipe.responder(self.sugestao, situacao="talvez", resposta="", usuario=self.gerente)

    def test_a_resposta_entra_na_auditoria_com_o_antes_e_o_depois(self):
        equipe.responder(self.sugestao, situacao=SugestaoDeCompra.Situacao.DESCARTADA,
                         resposta="Tem no estoque.", usuario=self.gerente)
        evento = EventoAuditoria.objects.filter(acao="compras.sugestao_respondida").first()
        self.assertIn("aberta", str(evento.antes))
        self.assertIn("descartada", str(evento.depois))


class TestLista(TestCase):
    def setUp(self):
        self.pessoa = usuario("ana", ADMINISTRATIVO)
        self.aberta = equipe.registrar_sugestao(produto="CARVAO", usuario=self.pessoa)
        self.fechada = equipe.registrar_sugestao(produto="LENHA", usuario=self.pessoa)
        equipe.responder(self.fechada, situacao=SugestaoDeCompra.Situacao.COMPRADA,
                         resposta="", usuario=self.pessoa)

    def test_filtra_por_situacao(self):
        abertas = equipe.listar(SugestaoDeCompra.Situacao.ABERTA)
        self.assertEqual([s.produto for s in abertas], ["CARVAO"])

    def test_sem_filtro_vem_tudo_com_a_mais_nova_primeiro(self):
        self.assertEqual([s.produto for s in equipe.listar()], ["LENHA", "CARVAO"])

    def test_filtro_torto_na_url_devolve_tudo_em_vez_de_nada(self):
        self.assertEqual(len(equipe.listar("inventada")), 2)

    def test_conta_quantas_em_cada_situacao(self):
        por_situacao = dict((valor, n) for _rotulo, valor, n in equipe.contagem_por_situacao())
        self.assertEqual(por_situacao[SugestaoDeCompra.Situacao.ABERTA], 1)
        self.assertEqual(por_situacao[SugestaoDeCompra.Situacao.COMPRADA], 1)


class TestTela(TestCase):
    def setUp(self):
        self.pessoa = usuario("ana", ADMINISTRATIVO)
        self.client.login(username="ana", password=SENHA_TESTE)

    def test_o_formulario_abre_para_quem_trabalha_na_loja(self):
        resposta = self.client.get(reverse("compras:sugestoes_da_equipe"))
        self.assertContains(resposta, "formulario-sugestao")

    def test_registrar_pela_tela_grava_e_avisa(self):
        resposta = self.client.post(reverse("compras:registrar_sugestao"), {
            "produto": "TAPETE SISAL", "quantidade": "2",
            "motivo": SugestaoDeCompra.Motivo.CLIENTE_PEDIU,
            "observacao": "Cliente volta sexta.",
        }, follow=True)
        self.assertContains(resposta, "registrada")
        self.assertContains(resposta, "TAPETE SISAL")
        self.assertEqual(SugestaoDeCompra.objects.count(), 1)

    def test_erro_volta_em_linguagem_simples_e_nao_grava(self):
        resposta = self.client.post(reverse("compras:registrar_sugestao"),
                                    {"produto": ""}, follow=True)
        self.assertContains(resposta, "Escreva qual é o produto")
        self.assertEqual(SugestaoDeCompra.objects.count(), 0)

    def test_quem_escreveu_e_quando_aparecem_na_lista(self):
        equipe.registrar_sugestao(produto="CARVAO", usuario=self.pessoa)
        resposta = self.client.get(reverse("compras:sugestoes_da_equipe"))
        self.assertContains(resposta, "Ana")
        self.assertContains(resposta, "CARVAO")

    def test_quem_so_sugere_nao_responde_a_propria_sugestao(self):
        """Responder é decisão de compra, e isso é da gerência."""
        sugestao = equipe.registrar_sugestao(produto="CARVAO", usuario=self.pessoa)
        resposta = self.client.post(
            reverse("compras:responder_sugestao", args=[sugestao.pk]),
            {"situacao": SugestaoDeCompra.Situacao.COMPRADA})
        self.assertEqual(resposta.status_code, 403)
        sugestao.refresh_from_db()
        self.assertEqual(sugestao.situacao, SugestaoDeCompra.Situacao.ABERTA)

    def test_a_gerencia_responde_pela_tela(self):
        sugestao = equipe.registrar_sugestao(produto="CARVAO", usuario=self.pessoa)
        self.client.logout()
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)
        resposta = self.client.post(
            reverse("compras:responder_sugestao", args=[sugestao.pk]),
            {"situacao": SugestaoDeCompra.Situacao.COMPRAR, "resposta": "Vai no próximo pedido."},
            follow=True)
        self.assertContains(resposta, "respondida")
        sugestao.refresh_from_db()
        self.assertEqual(sugestao.situacao, SugestaoDeCompra.Situacao.COMPRAR)

    def test_vendedor_nao_entra_na_tela_de_sugestoes(self):
        """O vendedor vê uma tela só, a consulta do balcão (condição do Edson)."""
        self.client.logout()
        usuario("balcao", VENDEDOR)
        self.client.login(username="balcao", password=SENHA_TESTE)
        resposta = self.client.get(reverse("compras:sugestoes_da_equipe"))
        self.assertEqual(resposta.status_code, 403)

    def test_a_tela_nao_aceita_leitura_pela_barra_de_endereco_no_registro(self):
        resposta = self.client.get(reverse("compras:registrar_sugestao"))
        self.assertEqual(resposta.status_code, 405)
