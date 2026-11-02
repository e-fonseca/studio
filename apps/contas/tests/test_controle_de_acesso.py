"""As regras de quem pode mexer no acesso de quem, a senha de novo e o 403 registrado (1.44.0).

Cada teste é uma frase do prompt de controle de acesso (02/11/2026) que virou regra no
servidor: "impedir autoconcessão de privilégios", "proteger o último administrador",
"reautenticação para operações administrativas sensíveis", "registrar tentativas negadas",
"nunca registrar senhas". As regras rodam na hora de gravar, com o que está no banco; por
isso quase todo teste chama o serviço direto ou manda um POST montado à mão, como faria
quem tenta passar por cima da tela.
"""

import datetime
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.sessions.models import Session
from django.core.management import CommandError, call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import EventoAuditoria
from apps.contas import autorizacao, confirmacao, servicos
from apps.contas.autorizacao import NaoPode
from apps.contas.models import VinculoIdentidade
from apps.contas.perfis import ADMIN_ACESSOS, ADMINISTRACAO, LIDER, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, entrar_na_area_de_acessos, usuario

SENHA_NOVA = "Jacaranda-Teste-Senha-2026"


def _sessoes_de(pessoa):
    return [s for s in Session.objects.all() if str(s.get_decoded().get("_auth_user_id")) == str(pessoa.pk)]


def _entrar_em_outro_aparelho(pessoa):
    outro = Client()
    outro.login(username=pessoa.get_username(), password=SENHA_TESTE)
    return outro


class PremissaTest(TestCase):
    def test_nas_contas_de_teste_so_quem_tem_senha_administra(self):
        """As contas da gerência vêm da migração sem senha; a conta sem senha não conta como
        administrador (não consegue entrar para administrar). Os testes abaixo dependem disso."""
        edson = usuario("edson", ADMINISTRACAO)
        self.assertEqual(autorizacao.administradores(), [edson])


class NinguemMexeNoProprioAcessoTest(TestCase):
    def setUp(self):
        self.edson = usuario("edson", ADMINISTRACAO)
        self.henriett = usuario("henriett", ADMINISTRACAO)

    def test_nem_perfil_nem_bloqueio_nem_desligamento_nem_data(self):
        tentativas = {
            "perfis": lambda: servicos.definir_perfis(self.edson, [VENDEDOR], responsavel=self.edson),
            "bloquear": lambda: servicos.bloquear_usuario(self.edson, motivo="x", responsavel=self.edson),
            "desligar": lambda: servicos.desligar_usuario(self.edson, motivo="x", responsavel=self.edson),
            "data": lambda: servicos.definir_acesso_ate(self.edson, timezone.localdate(),
                                                        responsavel=self.edson),
            "senha": lambda: servicos.definir_senha(self.edson, SENHA_NOVA, responsavel=self.edson),
        }
        for nome, tentativa in tentativas.items():
            with self.subTest(nome), self.assertRaisesMessage(NaoPode, "Ninguém muda o próprio acesso"):
                tentativa()
        self.edson.refresh_from_db()
        self.assertTrue(self.edson.is_active)
        self.assertTrue(self.edson.check_password(SENHA_TESTE))
        self.assertEqual(servicos.perfis_do_usuario(self.edson), [ADMINISTRACAO])

    def test_as_proprias_sessoes_ele_encerra(self):
        """Sair dos outros aparelhos não aumenta acesso nenhum: esse passa."""
        _entrar_em_outro_aparelho(self.edson)
        self.assertEqual(servicos.encerrar_todas_as_sessoes(self.edson, responsavel=self.edson), 1)

    def test_pela_tela_o_post_montado_a_mao_nao_passa(self):
        entrar_na_area_de_acessos(self.client, "edson")
        resposta = self.client.post(reverse("contas:alterar_usuario", args=[self.edson.pk]),
                                    {"acao": "bloquear", "motivo": "teste"}, follow=True)
        self.assertContains(resposta, "Ninguém muda o próprio acesso")
        self.edson.refresh_from_db()
        self.assertTrue(self.edson.is_active)


class NinguemDaOQueNaoTemTest(TestCase):
    """O Administrador de acessos cuida de contas sem ver número da loja."""

    def setUp(self):
        self.edson = usuario("edson", ADMINISTRACAO)
        self.acessos = usuario("acessos", ADMIN_ACESSOS)
        self.balcao = usuario("balcao", VENDEDOR)

    def test_cria_conta_de_vendedor(self):
        nova = servicos.criar_usuario(apelido="teste", nome="Teste", perfis=[VENDEDOR],
                                      responsavel=self.acessos)
        self.assertEqual(servicos.perfis_do_usuario(nova), [VENDEDOR])

    def test_nao_cria_conta_com_perfil_que_ve_dinheiro(self):
        for perfil in (ADMINISTRACAO, LIDER):
            with self.subTest(perfil), self.assertRaises(NaoPode):
                servicos.criar_usuario(apelido=f"teste{len(perfil)}", nome="Teste", perfis=[perfil],
                                       responsavel=self.acessos)
        self.assertFalse(get_user_model().objects.filter(username__startswith="teste").exists())

    def test_nao_promove_o_vendedor(self):
        with self.assertRaises(NaoPode):
            servicos.definir_perfis(self.balcao, [VENDEDOR, LIDER], responsavel=self.acessos)
        self.assertEqual(servicos.perfis_do_usuario(self.balcao), [VENDEDOR])

    def test_nao_mexe_na_conta_de_quem_tem_mais_acesso(self):
        """Definir a senha da gerência seria entrar como a gerência."""
        tentativas = {
            "senha": lambda: servicos.definir_senha(self.edson, SENHA_NOVA, responsavel=self.acessos),
            "bloquear": lambda: servicos.bloquear_usuario(self.edson, motivo="x", responsavel=self.acessos),
            "perfis": lambda: servicos.definir_perfis(self.edson, [ADMIN_ACESSOS], responsavel=self.acessos),
            "sessoes": lambda: servicos.encerrar_todas_as_sessoes(self.edson, responsavel=self.acessos),
        }
        for nome, tentativa in tentativas.items():
            with self.subTest(nome), self.assertRaisesMessage(NaoPode, "tem acesso que você não tem"):
                tentativa()
        self.edson.refresh_from_db()
        self.assertTrue(self.edson.check_password(SENHA_TESTE))
        self.assertTrue(self.edson.is_active)

    def test_mexe_na_conta_do_vendedor(self):
        servicos.definir_senha(self.balcao, SENHA_NOVA, responsavel=self.acessos)
        servicos.bloquear_usuario(self.balcao, motivo="férias", responsavel=self.acessos)
        self.balcao.refresh_from_db()
        self.assertFalse(self.balcao.is_active)

    def test_pela_tela_o_post_montado_a_mao_tambem_nao_passa(self):
        entrar_na_area_de_acessos(self.client, "acessos")
        resposta = self.client.post(reverse("contas:alterar_usuario", args=[self.balcao.pk]),
                                    {"acao": "perfis", "perfis": [ADMINISTRACAO]}, follow=True)
        self.assertContains(resposta, "Você não pode dar nem tirar o perfil")
        self.assertEqual(servicos.perfis_do_usuario(self.balcao), [VENDEDOR])

    def test_a_ficha_da_gerencia_abre_mas_sem_os_botoes(self):
        entrar_na_area_de_acessos(self.client, "acessos")
        resposta = self.client.get(reverse("contas:ficha", args=[self.edson.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, 'value="bloquear"')
        self.assertNotContains(resposta, 'value="senha"')

    def test_superusuario_so_e_mexido_por_superusuario(self):
        tecnico = get_user_model().objects.create_superuser("tecnico", password=SENHA_TESTE)
        with self.assertRaisesMessage(NaoPode, "conta técnica do servidor"):
            servicos.definir_senha(tecnico, SENHA_NOVA, responsavel=self.edson)
        with self.assertRaisesMessage(NaoPode, "conta técnica do servidor"):
            servicos.bloquear_usuario(tecnico, motivo="x", responsavel=self.edson)
        outro = get_user_model().objects.create_superuser("tecnico2", password=SENHA_TESTE)
        servicos.definir_senha(tecnico, SENHA_NOVA, responsavel=outro)


class SempreFicaUmAdministradorTest(TestCase):
    def setUp(self):
        self.edson = usuario("edson", ADMINISTRACAO)

    def _continua_administrando(self):
        self.edson.refresh_from_db()
        self.assertTrue(self.edson.is_active)
        self.assertEqual(servicos.perfis_do_usuario(self.edson), [ADMINISTRACAO])
        self.assertEqual(autorizacao.administradores(), [self.edson])

    def test_o_ultimo_nao_sai_por_nenhum_caminho(self):
        grupo = Group.objects.get(name=ADMINISTRACAO)
        sem_perfis = autorizacao.permissoes_do_perfil(grupo) - {autorizacao.EDITAR_PERFIS}
        tentativas = {
            "perfis": lambda: servicos.definir_perfis(self.edson, [LIDER]),
            "bloquear": lambda: servicos.bloquear_usuario(self.edson, motivo="x"),
            "desligar": lambda: servicos.desligar_usuario(self.edson, motivo="x"),
            "editar o perfil": lambda: servicos.editar_perfil(grupo, sem_perfis, motivo="x"),
        }
        for nome, tentativa in tentativas.items():
            with self.subTest(nome), self.assertRaisesMessage(NaoPode, "ninguém mais administraria"):
                tentativa()
            self._continua_administrando()
        self.assertFalse(EventoAuditoria.objects.filter(
            acao__in=["acesso.usuario_desligado", "acesso.usuario_bloqueado"]).exists())

    def test_com_outra_pessoa_administrando_sai(self):
        henriett = usuario("henriett", ADMINISTRACAO)
        servicos.desligar_usuario(self.edson, motivo="teste", responsavel=henriett)
        self.edson.refresh_from_db()
        self.assertFalse(self.edson.is_active)
        self.assertEqual(autorizacao.administradores(), [henriett])

    def test_a_data_marcada_nao_desliga_o_ultimo(self):
        """A data para acabar roda sozinha de madrugada; o último administrador fica, e a
        auditoria diz o porquê."""
        VinculoIdentidade.objects.update_or_create(
            usuario=self.edson, defaults={"acesso_ate": timezone.localdate() - datetime.timedelta(days=1)})
        balcao = usuario("balcao", VENDEDOR)
        VinculoIdentidade.objects.update_or_create(
            usuario=balcao, defaults={"acesso_ate": timezone.localdate() - datetime.timedelta(days=1)})
        desligados = servicos.encerrar_acessos_vencidos()
        self.assertEqual([p.username for p in desligados], ["balcao"])
        self._continua_administrando()
        evento = EventoAuditoria.objects.get(acao="acesso.prazo_nao_cumprido")
        self.assertEqual(evento.recurso_rotulo, "edson")
        self.assertEqual(evento.resultado, "negado")

    def test_nem_a_conta_tecnica_tira_o_ultimo(self):
        henriett = usuario("henriett", ADMINISTRACAO)
        servicos.bloquear_usuario(self.edson, motivo="férias", responsavel=henriett)
        # A henriett é a última agora: o edson, bloqueado, não conta. Nem a conta técnica
        # do servidor tira o perfil dela, porque a regra vale para todo mundo.
        tecnico = get_user_model().objects.create_superuser("tecnico", password=SENHA_TESTE)
        with self.assertRaises(NaoPode):
            servicos.definir_perfis(henriett, [], responsavel=tecnico)
        self.assertEqual(autorizacao.administradores(), [henriett])


class SessoesTest(TestCase):
    def setUp(self):
        self.edson = usuario("edson", ADMINISTRACAO)
        self.balcao = usuario("balcao", VENDEDOR)
        self.cassia = usuario("cassia", LIDER)

    def test_a_chave_de_outra_pessoa_nao_derruba_nada(self):
        """Trocar o número da pessoa no endereço e mandar a chave da sessão de outra."""
        _entrar_em_outro_aparelho(self.cassia)
        chave_da_cassia = _sessoes_de(self.cassia)[0].session_key
        self.assertFalse(servicos.encerrar_sessao(self.balcao, chave_da_cassia, responsavel=self.edson))
        entrar_na_area_de_acessos(self.client, "edson")
        resposta = self.client.post(reverse("contas:alterar_usuario", args=[self.balcao.pk]),
                                    {"acao": "encerrar_sessao", "chave": chave_da_cassia}, follow=True)
        self.assertContains(resposta, "Essa sessão já tinha acabado.")
        self.assertEqual(len(_sessoes_de(self.cassia)), 1)

    def test_encerrar_uma_sessao_derruba_so_aquela(self):
        celular = _entrar_em_outro_aparelho(self.balcao)
        computador = _entrar_em_outro_aparelho(self.balcao)
        chave = celular.session.session_key
        self.assertTrue(servicos.encerrar_sessao(self.balcao, chave, responsavel=self.edson))
        self.assertEqual(celular.get(reverse("importacao:consulta")).status_code, 302)
        self.assertEqual(computador.get(reverse("importacao:consulta")).status_code, 200)
        self.assertTrue(EventoAuditoria.objects.filter(acao="acesso.sessao_encerrada",
                                                       recurso_rotulo="balcao").exists())

    def test_a_ficha_lista_a_sessao_com_o_aparelho(self):
        # Pela tela de entrada, e não pelo client.login, que não passa pelo navegador.
        outro = Client(HTTP_USER_AGENT="Mozilla/5.0 (Linux; Android 14) Chrome/130.0 Mobile Safari/537.36",
                       REMOTE_ADDR="192.168.3.40")
        outro.post(reverse("contas:entrar"), {"username": "balcao", "password": SENHA_TESTE})
        self.assertEqual(outro.get(reverse("importacao:consulta")).status_code, 200)
        entrar_na_area_de_acessos(self.client, "edson")
        resposta = self.client.get(reverse("contas:ficha", args=[self.balcao.pk]))
        self.assertContains(resposta, "Chrome no Android")
        self.assertContains(resposta, "rede da loja")

    def test_a_propria_sessao_nao_se_encerra_pela_ficha(self):
        entrar_na_area_de_acessos(self.client, "edson")
        chave = self.client.session.session_key
        resposta = self.client.post(reverse("contas:alterar_usuario", args=[self.edson.pk]),
                                    {"acao": "encerrar_sessao", "chave": chave}, follow=True)
        self.assertContains(resposta, "é a sessão que você está usando agora")
        self.assertTrue(Session.objects.filter(session_key=chave).exists())

    def test_sair_dos_outros_aparelhos_fica_neste(self):
        _entrar_em_outro_aparelho(self.edson)
        entrar_na_area_de_acessos(self.client, "edson")
        resposta = self.client.post(reverse("contas:alterar_usuario", args=[self.edson.pk]),
                                    {"acao": "encerrar_sessoes"}, follow=True)
        self.assertContains(resposta, "Você saiu dos outros aparelhos")
        self.assertEqual([s.session_key for s in _sessoes_de(self.edson)], [self.client.session.session_key])


class BloquearTest(TestCase):
    def setUp(self):
        self.edson = usuario("edson", ADMINISTRACAO)
        self.balcao = usuario("balcao", VENDEDOR)

    def test_bloqueio_derruba_as_sessoes_e_o_desbloqueio_devolve_tudo(self):
        aparelho = _entrar_em_outro_aparelho(self.balcao)
        self.assertEqual(servicos.bloquear_usuario(self.balcao, motivo="férias", responsavel=self.edson), 1)
        self.assertEqual(aparelho.get(reverse("importacao:consulta")).status_code, 302)
        self.assertFalse(Client().login(username="balcao", password=SENHA_TESTE))
        self.balcao.refresh_from_db()
        self.assertEqual(servicos.situacao(self.balcao), "bloqueado")

        servicos.desbloquear_usuario(self.balcao, responsavel=self.edson)
        self.balcao.refresh_from_db()
        self.assertEqual(servicos.situacao(self.balcao), "ativo")
        self.assertEqual(servicos.perfis_do_usuario(self.balcao), [VENDEDOR])
        self.assertTrue(Client().login(username="balcao", password=SENHA_TESTE))

    def test_bloqueio_sem_motivo_nao_passa(self):
        with self.assertRaises(ValueError):
            servicos.bloquear_usuario(self.balcao, motivo="  ", responsavel=self.edson)

    def test_encerrar_pela_tela_pede_o_motivo(self):
        entrar_na_area_de_acessos(self.client, "edson")
        resposta = self.client.post(reverse("contas:alterar_usuario", args=[self.balcao.pk]),
                                    {"acao": "desligar", "motivo": ""}, follow=True)
        self.assertContains(resposta, "Diga o motivo do encerramento")
        self.balcao.refresh_from_db()
        self.assertTrue(self.balcao.is_active)

    def test_desligado_e_bloqueado_sao_coisas_diferentes(self):
        servicos.desligar_usuario(self.balcao, motivo="saiu da empresa", responsavel=self.edson)
        self.balcao.refresh_from_db()
        self.assertEqual(servicos.situacao(self.balcao), "desligado")
        with self.assertRaisesMessage(ValueError, "não está bloqueado"):
            servicos.desbloquear_usuario(self.balcao, responsavel=self.edson)


class ConfirmarASenhaTest(TestCase):
    def setUp(self):
        self.edson = usuario("edson", ADMINISTRACAO)
        self.balcao = usuario("balcao", VENDEDOR)
        self.client.login(username="edson", password=SENHA_TESTE)
        self.confirmar = reverse("contas:confirmar_senha")

    def test_a_area_pede_a_senha_e_volta_para_onde_ia(self):
        ficha = reverse("contas:ficha", args=[self.balcao.pk])
        resposta = self.client.get(ficha)
        self.assertRedirects(resposta, f"{self.confirmar}?proximo={ficha.replace('/', '%2F')}",
                             fetch_redirect_response=False)
        resposta = self.client.post(self.confirmar, {"senha": SENHA_TESTE, "proximo": ficha})
        self.assertRedirects(resposta, ficha)
        self.assertEqual(self.client.get(ficha).status_code, 200)
        self.assertTrue(EventoAuditoria.objects.filter(acao="acesso.senha_confirmada",
                                                       usuario=self.edson).exists())

    def test_confirmar_troca_a_chave_da_sessao(self):
        antes = self.client.session.session_key
        self.client.post(self.confirmar, {"senha": SENHA_TESTE})
        self.assertNotEqual(self.client.session.session_key, antes)
        self.assertFalse(Session.objects.filter(session_key=antes).exists())

    def test_senha_errada_conta_e_a_quinta_encerra_a_sessao(self):
        for tentativa in range(1, confirmacao.MAXIMO_DE_ERROS):
            resposta = self.client.post(self.confirmar, {"senha": "nao-e-esta"})
            self.assertContains(resposta, "A senha não confere")
        self.assertEqual(EventoAuditoria.objects.filter(acao="acesso.confirmacao_falhou").count(),
                         confirmacao.MAXIMO_DE_ERROS - 1)
        resposta = self.client.post(self.confirmar, {"senha": "nao-e-esta"})
        self.assertRedirects(resposta, reverse("contas:entrar"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_a_senha_certa_zera_as_erradas(self):
        self.client.post(self.confirmar, {"senha": "nao-e-esta"})
        self.client.post(self.confirmar, {"senha": SENHA_TESTE})
        self.assertNotIn(confirmacao.ERROS, self.client.session)

    def test_nao_redireciona_para_fora(self):
        for fora in ("https://exemplo.invalido/", "//exemplo.invalido/", "javascript:alert(1)"):
            with self.subTest(fora):
                self.client.login(username="edson", password=SENHA_TESTE)
                resposta = self.client.post(self.confirmar, {"senha": SENHA_TESTE, "proximo": fora})
                self.assertRedirects(resposta, reverse("contas:usuarios"), fetch_redirect_response=False)

    def test_mudanca_enviada_sem_a_senha_nao_e_aplicada(self):
        ficha = reverse("contas:ficha", args=[self.balcao.pk])
        resposta = self.client.post(reverse("contas:alterar_usuario", args=[self.balcao.pk]),
                                    {"acao": "bloquear", "motivo": "teste"}, HTTP_REFERER=ficha)
        self.assertTrue(resposta["Location"].startswith(self.confirmar))
        self.balcao.refresh_from_db()
        self.assertTrue(self.balcao.is_active)

    def test_a_janela_fecha_com_quinze_minutos_parada(self):
        sessao = self.client.session
        sessao[confirmacao.CHAVE] = (timezone.now() - datetime.timedelta(minutes=16)).isoformat()
        sessao.save()
        resposta = self.client.get(reverse("contas:usuarios"))
        self.assertTrue(resposta["Location"].startswith(self.confirmar))

    @override_settings(ACESSO_CONFIRMADO_SEGUNDOS=60)
    def test_o_uso_empurra_a_janela(self):
        sessao = self.client.session
        sessao[confirmacao.CHAVE] = (timezone.now() - datetime.timedelta(seconds=50)).isoformat()
        sessao.save()
        self.assertEqual(self.client.get(reverse("contas:usuarios")).status_code, 200)
        quando = datetime.datetime.fromisoformat(self.client.session[confirmacao.CHAVE])
        self.assertLess((timezone.now() - quando).total_seconds(), 5)

    def test_quem_nao_administra_nem_ve_a_tela_da_senha(self):
        """Pedir a senha a quem vai receber o 403 de todo jeito só faz a pessoa digitar."""
        self.client.logout()
        self.client.login(username="balcao", password=SENHA_TESTE)
        self.assertEqual(self.client.get(self.confirmar).status_code, 403)
        self.assertEqual(self.client.get(reverse("contas:perfis")).status_code, 403)
        self.assertEqual(self.client.get(reverse("contas:usuarios")).status_code, 403)


class NegadoTest(TestCase):
    def setUp(self):
        self.balcao = usuario("balcao", VENDEDOR)
        self.client.login(username="balcao", password=SENHA_TESTE)

    def test_o_403_diz_so_para_procurar_a_gerencia(self):
        resposta = self.client.get(reverse("caixa:lista"))
        self.assertEqual(resposta.status_code, 403)
        self.assertContains(resposta, autorizacao.NEGADO, status_code=403)

    def test_a_tentativa_vai_para_a_auditoria_uma_vez_por_minuto(self):
        self.client.get(reverse("caixa:lista"))
        self.client.get(reverse("caixa:lista"))
        eventos = EventoAuditoria.objects.filter(acao="acesso.negado", usuario=self.balcao)
        self.assertEqual(eventos.count(), 1)
        self.assertEqual(eventos.get().recurso_rotulo, reverse("caixa:lista"))
        self.assertEqual(eventos.get().resultado, EventoAuditoria.Resultado.NEGADO)
        self.client.get(reverse("contas:usuarios"))
        self.assertEqual(eventos.count(), 2)

    def test_a_ficha_mostra_o_negado(self):
        self.client.get(reverse("caixa:lista"))
        usuario("edson", ADMINISTRACAO)
        gerencia = Client()
        entrar_na_area_de_acessos(gerencia, "edson")
        resposta = gerencia.get(reverse("contas:ficha", args=[self.balcao.pk]))
        self.assertContains(resposta, reverse("caixa:lista"))


class SenhaNuncaNaAuditoriaTest(TestCase):
    def test_nem_a_definida_nem_a_errada(self):
        usuario("edson", ADMINISTRACAO)
        entrar_na_area_de_acessos(self.client, "edson")
        self.client.post(reverse("contas:criar_usuario"),
                         {"apelido": "teste", "nome": "Teste", "perfis": [VENDEDOR]})
        nova = get_user_model().objects.get(username="teste")
        self.client.post(reverse("contas:alterar_usuario", args=[nova.pk]),
                         {"acao": "senha", "senha": SENHA_NOVA})
        nova.refresh_from_db()
        self.assertTrue(nova.check_password(SENHA_NOVA))

        outro = Client()
        outro.login(username="edson", password=SENHA_TESTE)
        outro.post(reverse("contas:confirmar_senha"), {"senha": "Senha-Errada-Teste-77"})

        texto = " ".join(f"{e.antes} {e.depois} {e.motivo} {e.recurso_rotulo}"
                         for e in EventoAuditoria.objects.all())
        self.assertNotIn(SENHA_NOVA, texto)
        self.assertNotIn("Senha-Errada-Teste-77", texto)
        self.assertNotIn(SENHA_TESTE, texto)


class ComandosDoServidorTest(TestCase):
    def setUp(self):
        self.edson = usuario("edson", ADMINISTRACAO)

    def test_recuperar_o_administrador_bloqueado_com_senha_nova(self):
        henriett = usuario("henriett", ADMINISTRACAO)
        servicos.bloquear_usuario(self.edson, motivo="por engano", responsavel=henriett)
        servicos.definir_perfis(self.edson, [VENDEDOR], responsavel=henriett)
        with mock.patch("apps.contas.management.commands.recuperar_administrador.getpass.getpass",
                        side_effect=[SENHA_NOVA, SENHA_NOVA]):
            call_command("recuperar_administrador", "edson", motivo="bloqueado por engano",
                         senha=True, stdout=StringIO())
        self.edson.refresh_from_db()
        self.assertTrue(self.edson.is_active)
        self.assertTrue(self.edson.check_password(SENHA_NOVA))
        self.assertIn(ADMINISTRACAO, servicos.perfis_do_usuario(self.edson))
        self.assertEqual(servicos.situacao(self.edson), "ativo")
        evento = EventoAuditoria.objects.get(acao="acesso.administrador_recuperado")
        self.assertEqual(evento.motivo, "bloqueado por engano")
        self.assertNotIn(SENHA_NOVA, f"{evento.antes} {evento.depois}")

    def test_recuperar_sem_motivo_ou_com_senhas_diferentes_nao_muda_nada(self):
        with self.assertRaises(CommandError):
            call_command("recuperar_administrador", "edson", motivo="   ")
        with mock.patch("apps.contas.management.commands.recuperar_administrador.getpass.getpass",
                        side_effect=["Uma-Senha-Comprida-1", "Outra-Senha-Comprida-2"] * 3), \
                self.assertRaises(CommandError):
            call_command("recuperar_administrador", "edson", motivo="teste", senha=True,
                         stdout=StringIO(), stderr=StringIO())
        self.edson.refresh_from_db()
        self.assertTrue(self.edson.check_password(SENHA_TESTE))
        with self.assertRaises(CommandError):
            call_command("recuperar_administrador", "ninguem", motivo="teste")

    def test_relatorio_de_acessos(self):
        saida = StringIO()
        call_command("relatorio_de_acessos", stdout=saida)
        texto = saida.getvalue()
        for titulo in ("PESSOAS", "PERFIS", "O QUE PEDE ATENÇÃO"):
            self.assertIn(titulo, texto)
        self.assertIn("edson", texto)
        self.assertIn("Bom ter pelo menos duas pessoas", texto)

    def test_desligar_pelo_comando_respeita_o_ultimo_administrador(self):
        with self.assertRaisesMessage(CommandError, "ninguém mais administraria"):
            call_command("desligar_usuario", "edson", motivo="teste", stdout=StringIO())
        self.edson.refresh_from_db()
        self.assertTrue(self.edson.is_active)


class ArquivoBaixadoNaAuditoriaTest(TestCase):
    """O prompt pediu as exportações na trilha: quem tirou dado da loja, quando e qual."""

    ARQUIVOS = (
        "compras:lista_em_arquivo",
        "compras:comparar_em_arquivo",
        "fornecedores:produtos_em_arquivo",
        "margem:em_arquivo",
        "painel:vendas_dia_arquivo",
        "inventario:folha_de_contagem",
    )

    def test_cada_arquivo_baixado_fica_registrado_com_o_nome(self):
        edson = usuario("edson", ADMINISTRACAO)
        self.client.login(username="edson", password=SENHA_TESTE)
        for nome_da_rota in self.ARQUIVOS:
            with self.subTest(nome_da_rota):
                antes = EventoAuditoria.objects.filter(acao="dados.arquivo_baixado").count()
                resposta = self.client.get(reverse(nome_da_rota))
                self.assertEqual(resposta.status_code, 200)
                evento = EventoAuditoria.objects.filter(acao="dados.arquivo_baixado").order_by("-pk").first()
                self.assertEqual(EventoAuditoria.objects.filter(acao="dados.arquivo_baixado").count(), antes + 1)
                self.assertEqual(evento.usuario, edson)
                self.assertIn(evento.depois["arquivo"], resposta["Content-Disposition"])
                self.assertEqual(evento.depois["endereco"], reverse(nome_da_rota))

    def test_quem_nao_pode_baixar_nao_gera_arquivo_so_o_negado(self):
        usuario("balcao", VENDEDOR)
        self.client.login(username="balcao", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("margem:em_arquivo")).status_code, 403)
        self.assertFalse(EventoAuditoria.objects.filter(acao="dados.arquivo_baixado").exists())
        self.assertTrue(EventoAuditoria.objects.filter(acao="acesso.negado").exists())
