from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.auditoria.models import EventoAuditoria
from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO, VENDEDOR, PERFIS
from apps.contas.servicos import configurar_perfis, desligar_usuario
from apps.core.fabricas import SENHA_TESTE, usuario


class PerfisTest(TestCase):
    def test_configurar_perfis_e_idempotente(self):
        configurar_perfis()
        configurar_perfis()
        self.assertEqual(Group.objects.count(), len(PERFIS))
        self.assertEqual(Group.objects.get(name=ADMINISTRACAO).permissions.count(), len(PERFIS[ADMINISTRACAO]))

    def test_so_gerencia_valida_processo(self):
        self.assertTrue(usuario("g", ADMINISTRACAO).has_perm("processos.validar_processo"))
        for nome, perfil in [("c", ADMINISTRATIVO), ("o", VENDEDOR)]:
            self.assertFalse(usuario(nome, perfil).has_perm("processos.validar_processo"))

    def test_mudanca_de_perfil_e_auditada(self):
        u = usuario("x")
        u.groups.add(Group.objects.get(name=ADMINISTRATIVO))
        evento = EventoAuditoria.objects.filter(acao="permissao.perfis_alterados", recurso_id=str(u.pk)).last()
        self.assertIn(ADMINISTRATIVO, evento.depois["perfis_atuais"])


class DesligamentoTest(TestCase):
    def test_desligado_perde_sessao_e_nao_entra_mais(self):
        u = usuario("barbara", VENDEDOR)
        self.client.login(username="barbara", password=SENHA_TESTE)
        tela = reverse("importacao:consulta")
        self.assertEqual(self.client.get(tela).status_code, 200)
        sessoes = desligar_usuario(u, motivo="Fim do aviso prévio")
        self.assertEqual(sessoes, 1)
        self.assertEqual(self.client.get(tela).status_code, 302)
        self.assertFalse(self.client.login(username="barbara", password=SENHA_TESTE))
        evento = EventoAuditoria.objects.get(acao="acesso.usuario_desligado")
        self.assertEqual(evento.motivo, "Fim do aviso prévio")

    def test_desligamento_exige_motivo(self):
        u = usuario("y")
        with self.assertRaises(ValueError):
            desligar_usuario(u, motivo=" ")

    def test_comando(self):
        usuario("z")
        call_command("desligar_usuario", "z", "--motivo", "teste")
        self.assertFalse(get_user_model().objects.get(username="z").is_active)


@override_settings(AXES_ENABLED=True)
class ForcaBrutaTest(TestCase):
    def test_bloqueia_apos_cinco_falhas(self):
        usuario("alvo")
        for _ in range(5):
            self.client.post("/sistema/entrar/", {"username": "alvo", "password": "errada"})
        resposta = self.client.post("/sistema/entrar/", {"username": "alvo", "password": SENHA_TESTE})
        self.assertContains(resposta, "Acesso bloqueado", status_code=429)
