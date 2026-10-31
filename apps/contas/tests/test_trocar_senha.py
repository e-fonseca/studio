"""Cada pessoa troca a própria senha (1.42.0).

A tela de usuários manda "peça para ela trocar na primeira entrada" desde a 1.4.0, e até
aqui não havia onde trocar. Com a Cássia entrando (31/10/2026), a senha que a gerência
escolhe para ela é a primeira coisa a trocar.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.auditoria.models import EventoAuditoria
from apps.contas.perfis import LIDER, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario

NOVA = "uma frase longa de senha 31"


class TrocarSenhaTest(TestCase):
    def setUp(self):
        self.pessoa = usuario("cassia", LIDER)
        self.client.login(username="cassia", password=SENHA_TESTE)

    def trocar(self, atual=SENHA_TESTE, nova=NOVA, repetida=None):
        return self.client.post(reverse("contas:trocar_senha"), {
            "old_password": atual, "new_password1": nova,
            "new_password2": nova if repetida is None else repetida,
        }, follow=True)

    def test_troca_e_continua_dentro(self):
        resposta = self.trocar()
        self.assertContains(resposta, "Senha trocada.")
        pessoa = get_user_model().objects.get(pk=self.pessoa.pk)
        self.assertTrue(pessoa.check_password(NOVA))
        self.assertEqual(self.client.get(reverse("painel:geral")).status_code, 200)

    def test_o_outro_aparelho_cai(self):
        celular = Client()
        celular.login(username="cassia", password=SENHA_TESTE)
        self.trocar()
        resposta = celular.get(reverse("painel:geral"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("contas:entrar"), resposta["Location"])

    def test_sem_a_senha_de_agora_nao_troca(self):
        resposta = self.trocar(atual="senha-errada-qualquer")
        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, "Senha trocada.")
        self.assertTrue(get_user_model().objects.get(pk=self.pessoa.pk).check_password(SENHA_TESTE))

    def test_senha_curta_e_recusada_pela_mesma_regra_da_gerencia(self):
        resposta = self.trocar(nova="curta")
        self.assertNotContains(resposta, "Senha trocada.")
        self.assertTrue(get_user_model().objects.get(pk=self.pessoa.pk).check_password(SENHA_TESTE))

    def test_as_duas_senhas_novas_tem_que_bater(self):
        self.trocar(repetida="outra frase longa de senha")
        self.assertTrue(get_user_model().objects.get(pk=self.pessoa.pk).check_password(SENHA_TESTE))

    def test_a_auditoria_registra_sem_a_senha(self):
        self.trocar()
        evento = EventoAuditoria.objects.get(acao="acesso.senha_trocada")
        self.assertEqual(evento.usuario, self.pessoa)
        self.assertNotIn(NOVA, str(evento.antes) + str(evento.depois) + evento.motivo)

    def test_o_nome_no_alto_da_tela_abre_a_troca(self):
        tela = self.client.get(reverse("painel:geral"))
        self.assertContains(tela, f'href="{reverse("contas:trocar_senha")}"')


class QuemAbreTest(TestCase):
    def test_o_vendedor_tambem_troca_a_dele(self):
        usuario("balcao", VENDEDOR)
        self.client.login(username="balcao", password=SENHA_TESTE)
        tela = self.client.get(reverse("contas:trocar_senha"))
        self.assertEqual(tela.status_code, 200)
        self.assertContains(tela, "Senha de agora")
        # E a tela não traz número nenhum da loja: só o formulário.
        self.assertNotContains(tela, "R$")

    def test_quem_nao_entrou_vai_para_a_entrada(self):
        resposta = self.client.get(reverse("contas:trocar_senha"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("contas:entrar"), resposta["Location"])
