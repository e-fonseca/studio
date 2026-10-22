"""Conserto de texto gravado com a tabela de caracteres errada."""

from decimal import Decimal
from importlib import import_module

from django.test import TestCase
from django.urls import reverse

from apps.contas.perfis import ADMINISTRACAO
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.core.templatetags.cabana import reais
from apps.core.texto import consertar
from apps.fornecedores.models import Fornecedor


class ConsertarTest(TestCase):
    def test_desfaz_utf8_lido_como_cp1252(self):
        self.assertEqual(consertar("SÃ£o Paulo"), "São Paulo")
        self.assertEqual(consertar("ARTIGOS P/ DECORAÃ‡ÃƒO"), "ARTIGOS P/ DECORAÇÃO")

    def test_nao_mexe_em_texto_que_ja_esta_certo(self):
        for certo in ("São Paulo", "CONGREGAÇÃO RELIGIOSA", "MADEIREIRA SUL", "Belém", ""):
            self.assertEqual(consertar(certo), certo)

    def test_texto_vazio_ou_nulo_nao_quebra(self):
        self.assertEqual(consertar(""), "")
        self.assertIsNone(consertar(None))


class IconeTest(TestCase):
    def test_pagina_declara_o_icone_da_aba(self):
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)
        resposta = self.client.get(reverse("painel:geral"))
        self.assertContains(resposta, 'rel="icon"')
        self.assertContains(resposta, "icone.ico")
        self.assertContains(resposta, "logo.png")

    def test_tela_de_entrada_tambem_tem_icone(self):
        """Quem não entrou ainda vê a aba; o ícone não pode depender de estar logado."""
        self.assertContains(self.client.get(reverse("contas:entrar")), 'rel="icon"')


class FichaDoFornecedorTest(TestCase):
    def test_nome_torto_vira_nome_certo_e_mantem_a_avaliacao(self):
        """Se a ficha ficasse presa ao nome torto, prazo e estrelas sumiriam da tela."""
        Fornecedor.objects.create(nome="DECORAÃ‡ÃƒO LTDA", prazo_dias=7, reputacao=4)
        arrumar_fornecedores()
        ficha = Fornecedor.objects.get()
        self.assertEqual(ficha.nome, "DECORAÇÃO LTDA")
        self.assertEqual(ficha.prazo_dias, 7)
        self.assertEqual(ficha.reputacao, 4)

    def test_duplicata_do_nome_certo_e_removida(self):
        Fornecedor.objects.create(nome="DECORAÇÃO LTDA", prazo_dias=5)
        Fornecedor.objects.create(nome="DECORAÃ‡ÃƒO LTDA", prazo_dias=7)
        arrumar_fornecedores()
        self.assertEqual(Fornecedor.objects.count(), 1)
        self.assertEqual(Fornecedor.objects.get().prazo_dias, 5)


class ApenasFornecedor:
    """A migração recebe o registro histórico; para este modelo o atual serve igual."""

    def get_model(self, app, modelo):
        return Fornecedor


def arrumar_fornecedores():
    """Roda a função da migração 0003, que é o que de fato conserta o nome no servidor."""
    migracao = import_module("apps.fornecedores.migrations.0003_consertar_acentuacao")
    migracao.arrumar(ApenasFornecedor(), None)


class DinheiroEmPortugues(TestCase):
    """O sinal de menos vem antes do R$, como se escreve em português."""

    def test_valor_negativo_traz_o_sinal_antes_do_cifrao(self):
        self.assertEqual(reais(Decimal("-335.91")), "-R$ 335,91")

    def test_valor_positivo_nao_muda(self):
        self.assertEqual(reais(Decimal("1234.50")), "R$ 1.234,50")
        self.assertEqual(reais(0), "R$ 0,00")

    def test_sem_valor_continua_travessao(self):
        self.assertEqual(reais(None), "—")
