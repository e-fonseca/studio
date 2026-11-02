"""Esqueci a minha senha: o código no e-mail cadastrado (1.43.0, pedido de 31/10/2026).

"adotar recurso de recuperar senha por e-mail cadastrado via confirmação de código, senão
tiver cadastro informe que não é possível, procure o administrador do sistema."
"""

import re
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.alertas import envio
from apps.alertas.models import ConfiguracaoDeEmail
from apps.auditoria.models import EventoAuditoria
from apps.contas import recuperacao
from apps.contas.models import CodigoDeRecuperacao
from apps.contas.perfis import ADMINISTRACAO, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, entrar_na_area_de_acessos, usuario

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"
SENHA_NOVA = "uma frase comprida de teste"


def _sem_smtp():
    """O e-mail vai para a caixa de mentira do Django, e não para a Hostinger."""
    return mock.patch.object(envio, "_conexao", lambda configuracao: mail.get_connection(LOCMEM))


def _configurar_email():
    configuracao = ConfiguracaoDeEmail.atual()
    configuracao.senha = "senha-da-caixa"
    configuracao.save()
    return configuracao


def _codigo_do_email(mensagem):
    return re.search(r"O código é: (\d{6})", mensagem.body).group(1)


class TelaDeEntradaTest(TestCase):
    def test_a_entrada_tem_o_esqueci_a_minha_senha(self):
        resposta = self.client.get(reverse("contas:entrar"))
        self.assertContains(resposta, "Esqueci a minha senha")
        self.assertContains(resposta, reverse("contas:esqueci_a_senha"))

    def test_o_esqueci_abre_sem_login_e_sem_menu(self):
        resposta = self.client.get(reverse("contas:esqueci_a_senha"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Usuário ou e-mail cadastrado")
        self.assertNotContains(resposta, "Assuntos do sistema")

    def test_o_codigo_sem_ter_pedido_volta_para_o_comeco(self):
        self.assertRedirects(self.client.get(reverse("contas:codigo_da_senha")),
                             reverse("contas:esqueci_a_senha"))


class SemCadastroTest(TestCase):
    """Sem e-mail cadastrado: não é possível, procure o administrador do sistema."""

    def setUp(self):
        _configurar_email()

    def pedir(self, texto):
        with _sem_smtp():
            return self.client.post(reverse("contas:esqueci_a_senha"), {"identificacao": texto})

    def assertNaoEPossivel(self, resposta):
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Não é possível recuperar a senha por aqui")
        self.assertContains(resposta, "Procure o administrador do sistema")
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(CodigoDeRecuperacao.objects.exists())

    def test_usuario_sem_email(self):
        usuario("semmail", VENDEDOR)
        self.assertNaoEPossivel(self.pedir("semmail"))

    def test_usuario_que_nao_existe_recebe_a_mesma_frase(self):
        """Frase diferente diria a quem testa nomes quais contas existem."""
        self.assertNaoEPossivel(self.pedir("ninguem"))

    def test_conta_desligada_nao_recupera(self):
        conta = usuario("saiu", VENDEDOR, email="saiu@exemplo.com.br")
        conta.is_active = False
        conta.save()
        self.assertNaoEPossivel(self.pedir("saiu"))

    def test_conta_ainda_sem_senha_nao_recupera(self):
        """A primeira senha continua sendo da gerência, na tela de usuários."""
        conta = usuario("novata", VENDEDOR, email="novata@exemplo.com.br")
        conta.set_unusable_password()
        conta.save()
        self.assertNaoEPossivel(self.pedir("novata"))

    def test_o_pedido_que_nao_deu_vai_para_a_auditoria(self):
        self.pedir("ninguem")
        evento = EventoAuditoria.objects.get(acao="acesso.codigo_pedido")
        self.assertEqual(evento.resultado, EventoAuditoria.Resultado.FALHA)
        self.assertEqual(evento.depois["usuario_tentado"], "ninguem")

    def test_email_digitado_vai_para_a_auditoria_com_o_meio_escondido(self):
        self.pedir("alguem.de.fora@gmail.com")
        evento = EventoAuditoria.objects.get(acao="acesso.codigo_pedido")
        self.assertEqual(evento.depois["usuario_tentado"], "al•••@gmail.com")

    def test_sem_o_envio_configurado_diz_que_nao_da_agora(self):
        ConfiguracaoDeEmail.objects.all().delete()
        usuario("edson", ADMINISTRACAO, email="edson@exemplo.com.br")
        resposta = self.pedir("edson")
        self.assertContains(resposta, "o envio de e-mail do sistema ainda não está configurado")
        self.assertContains(resposta, "Procure o administrador do sistema")
        self.assertEqual(len(mail.outbox), 0)


class CodigoPeloEmailTest(TestCase):
    def setUp(self):
        _configurar_email()
        self.conta = usuario("edson", ADMINISTRACAO, email="edson.loja@exemplo.com.br")

    def pedir(self, texto="edson"):
        with _sem_smtp():
            return self.client.post(reverse("contas:esqueci_a_senha"), {"identificacao": texto})

    def mandar(self, codigo, senha=SENHA_NOVA, de_novo=None):
        with _sem_smtp():
            return self.client.post(reverse("contas:codigo_da_senha"), {
                "codigo": codigo, "new_password1": senha, "new_password2": de_novo or senha})

    def test_o_codigo_vai_ao_email_cadastrado(self):
        resposta = self.pedir()
        self.assertRedirects(resposta, reverse("contas:codigo_da_senha"))
        self.assertEqual(len(mail.outbox), 1)
        mensagem = mail.outbox[0]
        self.assertEqual(mensagem.to, ["edson.loja@exemplo.com.br"])
        self.assertIn("Código para criar a senha nova", mensagem.subject)
        self.assertRegex(mensagem.body, r"O código é: \d{6}")
        tela = self.client.get(reverse("contas:codigo_da_senha"))
        self.assertContains(tela, "ed•••@exemplo.com.br")
        self.assertNotContains(tela, "edson.loja@exemplo.com.br")
        # A tela já abre dizendo para onde foi; o quadro verde repetia a mesma frase.
        self.assertContains(tela, "Mandamos um código", count=1)

    def test_da_para_pedir_pelo_email_tambem(self):
        self.assertRedirects(self.pedir("Edson.Loja@exemplo.com.br"), reverse("contas:codigo_da_senha"))
        self.assertEqual(mail.outbox[0].to, ["edson.loja@exemplo.com.br"])

    def test_email_de_duas_contas_pede_o_usuario(self):
        usuario("henriett", ADMINISTRACAO, email="edson.loja@exemplo.com.br")
        resposta = self.pedir("edson.loja@exemplo.com.br")
        self.assertContains(resposta, "Digite o seu usuário de acesso")
        self.assertEqual(len(mail.outbox), 0)

    def test_o_codigo_nao_fica_guardado_nem_na_auditoria(self):
        self.pedir()
        codigo = _codigo_do_email(mail.outbox[0])
        guardado = CodigoDeRecuperacao.objects.get()
        self.assertNotIn(codigo, guardado.resumo)
        for evento in EventoAuditoria.objects.all():
            self.assertNotIn(codigo, f"{evento.antes} {evento.depois} {evento.motivo}")
        enviado = EventoAuditoria.objects.get(acao="acesso.codigo_pedido")
        self.assertEqual(enviado.depois["para"], "ed•••@exemplo.com.br")

    def test_codigo_certo_e_senha_boa_criam_a_senha_nova(self):
        self.pedir()
        codigo = _codigo_do_email(mail.outbox[0])
        resposta = self.mandar(codigo)
        self.assertRedirects(resposta, reverse("contas:entrar"), fetch_redirect_response=False)
        self.assertContains(self.client.get(reverse("contas:entrar")), "Senha nova salva")
        self.conta.refresh_from_db()
        self.assertTrue(self.conta.check_password(SENHA_NOVA))
        self.assertTrue(self.client.login(username="edson", password=SENHA_NOVA))
        # O aviso de que a senha foi trocada, para quem não pediu ficar sabendo.
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("A sua senha foi trocada", mail.outbox[1].subject)
        self.assertTrue(EventoAuditoria.objects.filter(acao="acesso.senha_recuperada").exists())

    def test_o_codigo_serve_uma_vez(self):
        self.pedir()
        codigo = _codigo_do_email(mail.outbox[0])
        self.mandar(codigo)
        # A sessão da recuperação acabou: a segunda tela manda pedir de novo.
        self.assertRedirects(self.client.get(reverse("contas:codigo_da_senha")),
                             reverse("contas:esqueci_a_senha"))
        self.assertIsNone(recuperacao.codigo_aberto(self.conta))
        self.assertTrue(CodigoDeRecuperacao.objects.get().usado_em)

    def test_codigo_errado_conta_tentativa(self):
        self.pedir()
        codigo = _codigo_do_email(mail.outbox[0])
        errado = "000000" if codigo != "000000" else "111111"
        resposta = self.mandar(errado)
        self.assertContains(resposta, "O código não confere")
        self.assertContains(resposta, "Restam 4 tentativas")
        self.conta.refresh_from_db()
        self.assertTrue(self.conta.check_password(SENHA_TESTE))

    def test_cinco_erros_e_o_codigo_deixa_de_valer(self):
        self.pedir()
        codigo = _codigo_do_email(mail.outbox[0])
        errado = "000000" if codigo != "000000" else "111111"
        for _ in range(recuperacao.TENTATIVAS):
            resposta = self.mandar(errado)
        self.assertContains(resposta, "deixou de valer")
        resposta = self.mandar(codigo)
        self.assertContains(resposta, "não vale mais")
        self.conta.refresh_from_db()
        self.assertTrue(self.conta.check_password(SENHA_TESTE))

    def test_codigo_vencido_nao_vale(self):
        self.pedir()
        codigo = _codigo_do_email(mail.outbox[0])
        CodigoDeRecuperacao.objects.update(vale_ate=timezone.now() - timedelta(seconds=1))
        self.assertContains(self.mandar(codigo), "não vale mais")

    def test_senha_fraca_nao_gasta_o_codigo(self):
        self.pedir()
        codigo = _codigo_do_email(mail.outbox[0])
        resposta = self.mandar(codigo, senha="123")
        self.assertEqual(resposta.status_code, 200)
        self.assertIsNotNone(recuperacao.codigo_aberto(self.conta))
        self.assertRedirects(self.mandar(codigo), reverse("contas:entrar"))

    def test_senhas_diferentes_nao_gastam_o_codigo(self):
        self.pedir()
        codigo = _codigo_do_email(mail.outbox[0])
        resposta = self.mandar(codigo, de_novo="outra frase comprida qualquer")
        self.assertEqual(resposta.status_code, 200)
        self.assertIsNotNone(recuperacao.codigo_aberto(self.conta))

    def test_pedir_de_novo_logo_em_seguida_nao_manda_outro_email(self):
        """Quem clica de novo achando que não chegou não anula o código que está chegando."""
        self.pedir()
        resposta = self.pedir()
        self.assertRedirects(resposta, reverse("contas:codigo_da_senha"), fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 1)
        self.assertContains(self.client.get(reverse("contas:codigo_da_senha")), "ainda vale")

    def test_codigo_novo_anula_o_anterior(self):
        self.pedir()
        primeiro = _codigo_do_email(mail.outbox[0])
        CodigoDeRecuperacao.objects.update(criado_em=timezone.now() - timedelta(minutes=2))
        self.pedir()
        segundo = _codigo_do_email(mail.outbox[1])
        if primeiro != segundo:
            self.assertContains(self.mandar(primeiro), "O código não confere")
        self.assertRedirects(self.mandar(segundo), reverse("contas:entrar"))

    def test_mandar_outro_codigo_pela_segunda_tela(self):
        self.pedir()
        CodigoDeRecuperacao.objects.update(criado_em=timezone.now() - timedelta(minutes=2))
        with _sem_smtp():
            resposta = self.client.post(reverse("contas:codigo_da_senha"), {"acao": "outro"})
        self.assertRedirects(resposta, reverse("contas:codigo_da_senha"), fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 2)
        self.assertContains(self.client.get(reverse("contas:codigo_da_senha")), "Mandamos outro código")

    def test_no_maximo_cinco_codigos_por_hora(self):
        for _ in range(recuperacao.CODIGOS_POR_HORA):
            self.pedir()
            CodigoDeRecuperacao.objects.update(criado_em=timezone.now() - timedelta(minutes=2))
        resposta = self.pedir()
        self.assertContains(resposta, "muitos pedidos de código")
        self.assertEqual(len(mail.outbox), recuperacao.CODIGOS_POR_HORA)

    def test_no_maximo_dez_pedidos_por_hora_do_mesmo_endereco(self):
        """Inclusive os que não deram em nada: é o que impede de testar nomes à vontade."""
        for numero in range(recuperacao.PEDIDOS_POR_HORA_POR_ENDERECO):
            self.pedir(f"tentativa{numero}")
        resposta = self.pedir("edson")
        self.assertContains(resposta, "muitos pedidos de código")
        self.assertEqual(len(mail.outbox), 0)

    def test_email_que_nao_sai_diz_para_tentar_depois(self):
        def recusar(configuracao):
            raise OSError("Connection refused")

        with mock.patch.object(envio, "_conexao", recusar):
            resposta = self.client.post(reverse("contas:esqueci_a_senha"), {"identificacao": "edson"})
        self.assertContains(resposta, "O e-mail com o código não saiu")
        self.assertIsNone(recuperacao.codigo_aberto(self.conta))

    def test_a_senha_nova_derruba_as_sessoes_abertas_em_outro_aparelho(self):
        celular = self.client_class()
        celular.login(username="edson", password=SENHA_TESTE)
        self.assertEqual(celular.get(reverse("painel:dashboard")).status_code, 200)
        self.pedir()
        self.mandar(_codigo_do_email(mail.outbox[0]))
        resposta = celular.get(reverse("painel:dashboard"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("contas:entrar"), resposta["Location"])


@override_settings(AXES_ENABLED=True)
class BloqueioSaiComASenhaNovaTest(TestCase):
    def test_quem_foi_bloqueado_entra_com_a_senha_nova(self):
        _configurar_email()
        usuario("alvo", VENDEDOR, email="alvo@exemplo.com.br")
        for _ in range(5):
            self.client.post(reverse("contas:entrar"), {"username": "alvo", "password": "errada"})
        bloqueado = self.client.post(reverse("contas:entrar"), {"username": "alvo", "password": SENHA_TESTE})
        self.assertContains(bloqueado, "Esqueci a minha senha", status_code=429)
        with _sem_smtp():
            self.client.post(reverse("contas:esqueci_a_senha"), {"identificacao": "alvo"})
            codigo = _codigo_do_email(mail.outbox[0])
            self.client.post(reverse("contas:codigo_da_senha"), {
                "codigo": codigo, "new_password1": SENHA_NOVA, "new_password2": SENHA_NOVA})
        resposta = self.client.post(reverse("contas:entrar"), {"username": "alvo", "password": SENHA_NOVA})
        self.assertEqual(resposta.status_code, 302)


class EmailCadastradoTest(TestCase):
    """Onde o e-mail de recuperação se grava: a gerência em Usuários, a pessoa na própria senha."""

    def _gravar(self, alvo, email, **extra):
        return self.client.post(reverse("contas:alterar_usuario", args=[alvo.pk]),
                                {"acao": "email", "email": email}, **extra)

    def test_a_gerencia_grava_o_email_de_alguem(self):
        gerente = usuario("edson", ADMINISTRACAO)
        vendedora = usuario("ana", VENDEDOR)
        entrar_na_area_de_acessos(self.client, "edson")
        resposta = self._gravar(vendedora, "ana.loja@exemplo.com.br", follow=True)
        self.assertContains(resposta, "o código vai para ana.loja@exemplo.com.br")
        vendedora.refresh_from_db()
        self.assertEqual(vendedora.email, "ana.loja@exemplo.com.br")
        evento = EventoAuditoria.objects.get(acao="acesso.email_definido")
        self.assertEqual(evento.usuario, gerente)
        self.assertEqual(evento.depois, {"email": "an•••@exemplo.com.br"})

    def test_email_torto_e_recusado(self):
        usuario("edson", ADMINISTRACAO)
        vendedora = usuario("ana", VENDEDOR)
        entrar_na_area_de_acessos(self.client, "edson")
        resposta = self._gravar(vendedora, "ana.loja", follow=True)
        self.assertContains(resposta, "Esse e-mail não parece certo")
        vendedora.refresh_from_db()
        self.assertEqual(vendedora.email, "")

    def test_a_tela_de_usuarios_mostra_quem_nao_recupera_sozinho(self):
        usuario("edson", ADMINISTRACAO)
        ana = usuario("ana", VENDEDOR)
        entrar_na_area_de_acessos(self.client, "edson")
        resposta = self.client.get(reverse("contas:usuarios"))
        self.assertContains(resposta, "sem e-mail: não recupera a senha sozinho")
        ficha = self.client.get(reverse("contas:ficha", args=[ana.pk]))
        self.assertContains(ficha, "E-mail para recuperar a senha")

    def test_o_vendedor_nao_grava_email_de_ninguem(self):
        usuario("balcao", VENDEDOR)
        outra = usuario("ana", VENDEDOR)
        self.client.login(username="balcao", password=SENHA_TESTE)
        resposta = self._gravar(outra, "meu@exemplo.com.br")
        self.assertEqual(resposta.status_code, 403)

    def test_quem_so_administra_pessoas_nao_troca_o_email_da_gerencia(self):
        """Quem troca o e-mail de uma conta pede o código e toma a senha dela: o e-mail de
        quem tem mais acesso só muda pela mão de quem tem o mesmo acesso (1.44.0)."""
        from apps.contas.perfis import ADMIN_ACESSOS  # noqa: PLC0415

        gerente = usuario("edson", ADMINISTRACAO)
        usuario("rh", ADMIN_ACESSOS)
        entrar_na_area_de_acessos(self.client, "rh")
        resposta = self._gravar(gerente, "rh.pessoal@exemplo.com.br", follow=True)
        self.assertContains(resposta, "tem acesso que você não tem")
        gerente.refresh_from_db()
        self.assertEqual(gerente.email, "")

    def test_a_pessoa_grava_o_proprio_email_com_a_senha_de_agora(self):
        conta = usuario("balcao", VENDEDOR)
        self.client.login(username="balcao", password=SENHA_TESTE)
        resposta = self.client.post(reverse("contas:trocar_senha"), {
            "acao": "email", "email": "balcao@exemplo.com.br", "senha_atual": SENHA_TESTE}, follow=True)
        self.assertContains(resposta, "E-mail salvo")
        conta.refresh_from_db()
        self.assertEqual(conta.email, "balcao@exemplo.com.br")

    def test_sem_a_senha_de_agora_o_email_nao_muda(self):
        """Quem achar o computador aberto não põe o próprio e-mail na conta de outra pessoa."""
        conta = usuario("balcao", VENDEDOR)
        self.client.login(username="balcao", password=SENHA_TESTE)
        resposta = self.client.post(reverse("contas:trocar_senha"), {
            "acao": "email", "email": "intruso@exemplo.com.br", "senha_atual": "chute"}, follow=True)
        self.assertContains(resposta, "A senha de agora não confere")
        conta.refresh_from_db()
        self.assertEqual(conta.email, "")


class MascararTest(TestCase):
    def test_esconde_o_meio_do_email(self):
        self.assertEqual(recuperacao.mascarar("edson@gmail.com"), "ed•••@gmail.com")
        self.assertEqual(recuperacao.mascarar("ana@gmail.com"), "a•••@gmail.com")
        self.assertEqual(recuperacao.mascarar("sem-arroba"), "•••")
