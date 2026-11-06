"""Os alertas do Studio saem e chegam pela queroindustrial@gmail.com (2.4.1)."""

from importlib import import_module

from django.apps import apps
from django.test import TestCase

from apps.alertas.models import ConfiguracaoDeEmail

migracao = import_module("apps.alertas.migrations.0007_caixa_do_studio")


class CaixaDoStudioTest(TestCase):
    def test_a_linha_parada_com_a_caixa_da_cabana_passa_para_a_do_studio(self):
        ConfiguracaoDeEmail.objects.create(
            pk=1, servidor="smtp.hostinger.com", porta=465,
            usuario="naoresponder@cabanadojacaranda.com.br",
            destinatarios="cabanadojacaranda@gmail.com",
        )
        migracao.caixa_do_studio(apps, None)
        linha = ConfiguracaoDeEmail.objects.get(pk=1)
        self.assertEqual((linha.servidor, linha.porta, linha.usar_tls),
                         ("smtp.gmail.com", 587, True))
        self.assertEqual(linha.usuario, "queroindustrial@gmail.com")
        self.assertEqual(linha.lista_de_destinatarios, ["queroindustrial@gmail.com"])

    def test_a_linha_com_senha_gravada_fica_como_esta(self):
        ConfiguracaoDeEmail.objects.create(
            pk=1, servidor="smtp.exemplo.com", porta=465, usuario="outra@exemplo.com",
            senha_guardada="cifrada", destinatarios="outra@exemplo.com",
        )
        migracao.caixa_do_studio(apps, None)
        linha = ConfiguracaoDeEmail.objects.get(pk=1)
        self.assertEqual(linha.usuario, "outra@exemplo.com")
        self.assertEqual(linha.servidor, "smtp.exemplo.com")

    def test_nenhum_padrao_da_tela_aponta_para_a_cabana(self):
        nova = ConfiguracaoDeEmail()
        for campo in ("servidor", "usuario", "destinatarios"):
            with self.subTest(campo=campo):
                self.assertNotIn("cabana", getattr(nova, campo).lower())
                self.assertNotIn("hostinger", getattr(nova, campo).lower())
