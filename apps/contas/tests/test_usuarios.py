"""Tela de usuários: quem entra no sistema e o que cada um pode abrir."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.auditoria.models import EventoAuditoria
from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO, VENDEDOR
from apps.contas.servicos import criar_usuario, perfis_do_usuario
from apps.core.fabricas import SENHA_TESTE, usuario

SENHA_BOA = "cabana-jacaranda-2026"


class AcessosDaGerenciaTest(TestCase):
    def test_migracao_criou_os_tres_administradores_sem_senha(self):
        """Conta sem senha utilizável não entra: não há senha provisória circulando."""
        Usuario = get_user_model()
        for apelido in ("edson", "henriett", "moizes"):
            pessoa = Usuario.objects.get(username=apelido)
            self.assertFalse(pessoa.has_usable_password())
            self.assertIn(ADMINISTRACAO, perfis_do_usuario(pessoa))

    def test_perfis_antigos_sairam_do_caminho(self):
        from django.contrib.auth.models import Group

        self.assertFalse(Group.objects.filter(name__in=["Gerência", "Compras", "Estoque"]).exists())


class CriarUsuarioTest(TestCase):
    def test_conta_nasce_sem_senha_e_com_perfil(self):
        pessoa = criar_usuario(apelido="Vanda", nome="Vanda", perfil=VENDEDOR)
        self.assertEqual(pessoa.get_username(), "vanda")
        self.assertFalse(pessoa.has_usable_password())
        self.assertEqual(perfis_do_usuario(pessoa), [VENDEDOR])
        self.assertTrue(EventoAuditoria.objects.filter(acao="acesso.usuario_criado").exists())

    def test_nome_repetido_nao_passa(self):
        criar_usuario(apelido="vanda", nome="Vanda")
        with self.assertRaises(ValueError):
            criar_usuario(apelido="VANDA", nome="Outra")

    def test_perfil_inventado_nao_passa(self):
        with self.assertRaises(ValueError):
            criar_usuario(apelido="x", nome="X", perfil="Dono do mundo")


class TelaDeUsuariosTest(TestCase):
    def setUp(self):
        self.admin = usuario("chefe", ADMINISTRACAO)
        self.client.login(username="chefe", password=SENHA_TESTE)

    def test_so_administracao_abre(self):
        self.client.logout()
        usuario("balcao", VENDEDOR)
        self.client.login(username="balcao", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("contas:usuarios")).status_code, 403)

    def test_lista_mostra_quem_esta_sem_senha(self):
        resposta = self.client.get(reverse("contas:usuarios"))
        self.assertContains(resposta, "henriett")
        self.assertContains(resposta, "ainda sem senha")

    def test_criar_pela_tela(self):
        self.client.post(reverse("contas:criar_usuario"),
                         {"apelido": "vanda", "nome": "Vanda", "perfil": ADMINISTRATIVO})
        pessoa = get_user_model().objects.get(username="vanda")
        self.assertEqual(perfis_do_usuario(pessoa), [ADMINISTRATIVO])

    def test_definir_senha_deixa_a_pessoa_entrar(self):
        alvo = get_user_model().objects.get(username="henriett")
        self.client.post(reverse("contas:alterar_usuario", args=[alvo.pk]),
                         {"acao": "senha", "senha": SENHA_BOA})
        self.client.logout()
        self.assertTrue(self.client.login(username="henriett", password=SENHA_BOA))

    def test_senha_fraca_e_recusada_e_nao_entra_na_auditoria(self):
        alvo = get_user_model().objects.get(username="moizes")
        resposta = self.client.post(reverse("contas:alterar_usuario", args=[alvo.pk]),
                                    {"acao": "senha", "senha": "123"}, follow=True)
        self.assertContains(resposta, "curta")
        alvo.refresh_from_db()
        self.assertFalse(alvo.has_usable_password())
        self.assertFalse(EventoAuditoria.objects.filter(acao="acesso.senha_definida").exists())

    def test_trocar_perfil_e_auditado(self):
        alvo = get_user_model().objects.get(username="moizes")
        self.client.post(reverse("contas:alterar_usuario", args=[alvo.pk]),
                         {"acao": "perfil", "perfil": VENDEDOR})
        self.assertEqual(perfis_do_usuario(alvo), [VENDEDOR])
        evento = EventoAuditoria.objects.filter(acao="acesso.perfil_definido").last()
        self.assertEqual(evento.depois["perfis"], [VENDEDOR])

    def test_nao_da_para_desligar_o_proprio_acesso(self):
        resposta = self.client.post(reverse("contas:alterar_usuario", args=[self.admin.pk]),
                                    {"acao": "desligar", "motivo": "teste"}, follow=True)
        self.assertContains(resposta, "não pode desligar o seu próprio")
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_desligar_e_religar(self):
        alvo = get_user_model().objects.get(username="henriett")
        self.client.post(reverse("contas:alterar_usuario", args=[alvo.pk]),
                         {"acao": "desligar", "motivo": "Saiu da loja"})
        alvo.refresh_from_db()
        self.assertFalse(alvo.is_active)
        self.client.post(reverse("contas:alterar_usuario", args=[alvo.pk]), {"acao": "reativar"})
        alvo.refresh_from_db()
        self.assertTrue(alvo.is_active)


class ConsultaDeBalcaoTest(TestCase):
    def test_vendedor_abre_a_consulta_e_nada_mais(self):
        usuario("balcao", VENDEDOR)
        self.client.login(username="balcao", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("importacao:consulta")).status_code, 200)
        for rota in ("painel:painel", "painel:geral", "financeiro:contas_a_pagar",
                     "fornecedores:lista", "clientes:lista", "compras:antes_de_comprar"):
            self.assertEqual(self.client.get(reverse(rota)).status_code, 403, rota)
