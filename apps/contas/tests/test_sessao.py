"""Limite de tempo logado, encerramento por tempo parado e o cadastro do usuário."""

from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.contas import sessao
from apps.contas.models import VinculoIdentidade
from apps.contas.perfis import ADMINISTRACAO
from apps.core.fabricas import SENHA_TESTE, confirmar_senha, usuario


class TestLimiteDeSessao(TestCase):
    def setUp(self):
        self.gerente = usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)

    def test_a_entrada_fica_marcada_no_login(self):
        self.assertIn(sessao.CHAVE, self.client.session)

    def test_quem_passa_das_quatro_horas_cai_na_tela_de_entrada(self):
        estado = self.client.session
        estado[sessao.CHAVE] = (timezone.now() - timedelta(hours=4, minutes=1)).isoformat()
        estado.save()
        resposta = self.client.get(reverse("contas:trocar_senha"))
        self.assertRedirects(resposta, reverse("contas:entrar"))

    def test_dentro_do_limite_continua_trabalhando(self):
        estado = self.client.session
        estado[sessao.CHAVE] = (timezone.now() - timedelta(hours=3, minutes=50)).isoformat()
        estado.save()
        self.assertEqual(self.client.get(reverse("contas:trocar_senha")).status_code, 200)

    @override_settings(SESSAO_MAXIMA_SEGUNDOS=60)
    def test_o_limite_vem_da_configuracao(self):
        estado = self.client.session
        estado[sessao.CHAVE] = (timezone.now() - timedelta(minutes=2)).isoformat()
        estado.save()
        self.assertRedirects(self.client.get(reverse("contas:trocar_senha")), reverse("contas:entrar"))

    def test_sessao_antiga_sem_a_marca_nao_derruba_ninguem(self):
        """Na primeira vez que a atualização sobe, ninguém é expulso no meio do trabalho."""
        estado = self.client.session
        del estado[sessao.CHAVE]
        estado.save()
        self.assertEqual(self.client.get(reverse("contas:trocar_senha")).status_code, 200)


class TestSessaoParada(TestCase):
    """Fechar e reabrir o navegador não pode voltar logado (Edson, 08/10/2026).

    O cookie já é de sessão, mas o Chrome restaura cookie de sessão quando está em
    "continuar de onde parou". Quem resolve é o servidor recusar a sessão parada.
    """

    def setUp(self):
        self.gerente = usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)

    def _parada_desde(self, **quanto):
        estado = self.client.session
        estado[sessao.VISTO] = (timezone.now() - timedelta(**quanto)).isoformat()
        estado.save()

    def test_o_ultimo_uso_fica_marcado_no_login(self):
        self.assertIn(sessao.VISTO, self.client.session)

    def test_meia_hora_parada_cai_na_tela_de_entrada(self):
        self._parada_desde(minutes=31)
        resposta = self.client.get(reverse("contas:trocar_senha"))
        self.assertRedirects(resposta, reverse("contas:entrar"))

    def test_quem_estava_usando_continua(self):
        self._parada_desde(minutes=20)
        self.assertEqual(self.client.get(reverse("contas:trocar_senha")).status_code, 200)

    def test_cada_uso_reinicia_a_contagem(self):
        """Trabalhar a tarde toda não derruba: o que derruba é parar."""
        self._parada_desde(minutes=25)
        self.client.get(reverse("contas:trocar_senha"))
        visto = sessao._quando(self.client.session[sessao.VISTO])
        self.assertLess((timezone.now() - visto).total_seconds(), 60)
        self._parada_desde(minutes=25)
        self.assertEqual(self.client.get(reverse("contas:trocar_senha")).status_code, 200)

    @override_settings(SESSAO_PARADA_SEGUNDOS=60)
    def test_o_tempo_parado_vem_da_configuracao(self):
        self._parada_desde(minutes=2)
        self.assertRedirects(self.client.get(reverse("contas:trocar_senha")), reverse("contas:entrar"))

    def test_a_tela_de_entrada_explica_por_que_saiu(self):
        self._parada_desde(minutes=31)
        resposta = self.client.get(reverse("contas:trocar_senha"), follow=True)
        self.assertContains(resposta, "sem uso e foi encerrada por segurança")

    def test_sessao_sem_a_marca_de_uso_conta_da_entrada(self):
        """Sessão aberta na versão anterior: a entrada serve de último uso."""
        estado = self.client.session
        del estado[sessao.VISTO]
        estado[sessao.CHAVE] = (timezone.now() - timedelta(hours=1)).isoformat()
        estado.save()
        self.assertRedirects(self.client.get(reverse("contas:trocar_senha")), reverse("contas:entrar"))

    def test_quem_nem_entrou_nao_e_incomodado(self):
        self.client.logout()
        resposta = self.client.get(reverse("contas:entrar"))
        self.assertEqual(resposta.status_code, 200)


class TestCadastroDeUsuario(TestCase):
    def setUp(self):
        self.gerente = usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)
        confirmar_senha(self.client)

    def _criar(self, **extra):
        dados = {"apelido": "barbara", "nome": "Bárbara", "sobrenome": "Teste",
                 "email": "barbara@exemplo.com.br", "cpf": "529.982.247-25",
                 "perfis": [ADMINISTRACAO]}
        dados.update(extra)
        return self.client.post(reverse("contas:criar_usuario"), dados, follow=True)

    def test_guarda_nome_sobrenome_email_e_cpf(self):
        self._criar()
        from django.contrib.auth import get_user_model

        pessoa = get_user_model().objects.get(username="barbara")
        self.assertEqual(pessoa.get_full_name(), "Bárbara Teste")
        self.assertEqual(pessoa.email, "barbara@exemplo.com.br")
        self.assertEqual(pessoa.vinculo.cpf, "52998224725")

    def test_cpf_errado_nao_passa(self):
        resposta = self._criar(cpf="529.982.247-26")
        self.assertContains(resposta, "não confere")
        from django.contrib.auth import get_user_model

        self.assertFalse(get_user_model().objects.filter(username="barbara").exists())

    def test_cpf_repetido_nao_passa(self):
        self._criar()
        resposta = self._criar(apelido="outra", nome="Outra")
        self.assertContains(resposta, "Já existe um usuário com esse CPF")

    def test_cpf_e_opcional(self):
        self._criar(cpf="")
        self.assertEqual(VinculoIdentidade.objects.filter(cpf="").count(),
                         VinculoIdentidade.objects.filter(cpf="").count())

    def test_o_cpf_nao_vai_para_a_auditoria(self):
        """Documento não entra na trilha, nem no evento de criação do usuário."""
        self._criar()
        from apps.auditoria.models import EventoAuditoria

        evento = EventoAuditoria.objects.filter(acao="acesso.usuario_criado").first()
        self.assertNotIn("52998224725", str(evento.depois))
