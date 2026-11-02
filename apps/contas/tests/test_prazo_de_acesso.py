"""A data marcada para o acesso acabar, cumprida pelo sistema no dia seguinte.

Pedido do Edson em 31/10/2026, com a Cássia entrando no lugar da Bárbara: *"ficara no
lugar da barbara ate dia 12/11/2026"*.
"""

from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import EventoAuditoria
from apps.contas import prazo, servicos
from apps.contas.models import VinculoIdentidade
from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO
from apps.core.fabricas import SENHA_TESTE, confirmar_senha, usuario


class BasePrazo(TestCase):
    def setUp(self):
        prazo.esquecer()
        self.hoje = timezone.localdate()
        self.gerente = usuario("edson", ADMINISTRACAO)
        self.barbara = usuario("barbara", ADMINISTRATIVO)

    def tearDown(self):
        prazo.esquecer()

    def vencer(self, pessoa, dias=1):
        """Põe a data no passado direto no banco: pela tela, data que passou é recusada."""
        vinculo, _ = VinculoIdentidade.objects.get_or_create(usuario=pessoa)
        vinculo.acesso_ate = self.hoje - timedelta(days=dias)
        vinculo.save(update_fields=["acesso_ate"])


class DefinirDataTest(BasePrazo):
    def test_marca_e_registra_na_auditoria(self):
        data = self.hoje + timedelta(days=12)
        self.assertTrue(servicos.definir_acesso_ate(self.barbara, data, responsavel=self.gerente))
        self.assertEqual(self.barbara.vinculo.acesso_ate, data)
        evento = EventoAuditoria.objects.get(acao="acesso.prazo_definido")
        self.assertEqual(evento.usuario, self.gerente)
        self.assertEqual(evento.depois["acesso_ate"], data.isoformat())

    def test_data_que_ja_passou_e_recusada(self):
        with self.assertRaisesMessage(ValueError, "use Encerrar"):
            servicos.definir_acesso_ate(self.barbara, self.hoje - timedelta(days=1))
        self.assertTrue(get_user_model().objects.get(pk=self.barbara.pk).is_active)

    def test_hoje_vale_e_hoje_ainda_entra(self):
        servicos.definir_acesso_ate(self.barbara, self.hoje)
        self.assertEqual(servicos.encerrar_acessos_vencidos(self.hoje), [])

    def test_sem_data_tira_a_data(self):
        servicos.definir_acesso_ate(self.barbara, self.hoje + timedelta(days=3))
        self.assertTrue(servicos.definir_acesso_ate(self.barbara, None))
        self.barbara.vinculo.refresh_from_db()
        self.assertIsNone(self.barbara.vinculo.acesso_ate)

    def test_a_mesma_data_de_novo_nao_muda_nada(self):
        data = self.hoje + timedelta(days=3)
        servicos.definir_acesso_ate(self.barbara, data)
        self.assertFalse(servicos.definir_acesso_ate(self.barbara, data))
        self.assertEqual(EventoAuditoria.objects.filter(acao="acesso.prazo_definido").count(), 1)


class EncerrarVencidosTest(BasePrazo):
    def test_no_dia_seguinte_a_conta_se_desliga_sozinha(self):
        self.vencer(self.barbara)
        desligados = servicos.encerrar_acessos_vencidos(self.hoje)
        self.assertEqual([u.pk for u in desligados], [self.barbara.pk])
        barbara = get_user_model().objects.get(pk=self.barbara.pk)
        self.assertFalse(barbara.is_active)
        self.assertIsNotNone(barbara.vinculo.desligado_em)
        evento = EventoAuditoria.objects.get(acao="acesso.usuario_desligado")
        self.assertEqual(evento.usuario_rotulo, "data marcada para o acesso acabar")
        self.assertIn("Acesso combinado até", evento.motivo)

    def test_quem_nao_tem_data_continua(self):
        self.vencer(self.barbara)
        servicos.encerrar_acessos_vencidos(self.hoje)
        self.assertTrue(get_user_model().objects.get(pk=self.gerente.pk).is_active)

    def test_a_sessao_aberta_cai_junto(self):
        self.client.login(username="barbara", password=SENHA_TESTE)
        self.assertTrue(Session.objects.exists())
        self.vencer(self.barbara)
        servicos.encerrar_acessos_vencidos(self.hoje)
        resposta = self.client.get(reverse("painel:geral"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("contas:entrar"), resposta["Location"])

    def test_quem_ja_foi_desligado_nao_e_desligado_de_novo(self):
        self.vencer(self.barbara)
        servicos.encerrar_acessos_vencidos(self.hoje)
        self.assertEqual(servicos.encerrar_acessos_vencidos(self.hoje), [])
        self.assertEqual(EventoAuditoria.objects.filter(acao="acesso.usuario_desligado").count(), 1)

    def test_liberar_de_novo_tira_a_data_que_acabou(self):
        self.vencer(self.barbara)
        servicos.encerrar_acessos_vencidos(self.hoje)
        servicos.reativar_usuario(get_user_model().objects.get(pk=self.barbara.pk), responsavel=self.gerente)
        barbara = get_user_model().objects.get(pk=self.barbara.pk)
        self.assertTrue(barbara.is_active)
        self.assertIsNone(barbara.vinculo.acesso_ate)
        self.assertEqual(servicos.encerrar_acessos_vencidos(self.hoje), [])


class SemNinguemLembrarTest(BasePrazo):
    """A data é cumprida na primeira requisição do dia, de quem quer que seja."""

    def test_a_propria_pessoa_nao_entra_depois_da_data(self):
        self.vencer(self.barbara)
        resposta = self.client.post(reverse("contas:entrar"),
                                    {"username": "barbara", "password": SENHA_TESTE})
        self.assertEqual(resposta.status_code, 200)  # a tela de entrada volta, com o recado
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertFalse(get_user_model().objects.get(pk=self.barbara.pk).is_active)

    def test_qualquer_tela_aberta_por_outra_pessoa_ja_cumpre(self):
        self.vencer(self.barbara)
        self.client.login(username="edson", password=SENHA_TESTE)
        self.client.get(reverse("painel:geral"))
        self.assertFalse(get_user_model().objects.get(pk=self.barbara.pk).is_active)

    def test_se_a_conferencia_falha_a_tela_abre_e_tenta_de_novo(self):
        self.vencer(self.barbara)
        with mock.patch.object(servicos, "encerrar_acessos_vencidos", side_effect=RuntimeError("banco")), \
                self.assertLogs("apps.contas.prazo", level="ERROR"):
            self.assertEqual(self.client.get(reverse("contas:entrar")).status_code, 200)
        self.client.get(reverse("contas:entrar"))
        self.assertFalse(get_user_model().objects.get(pk=self.barbara.pk).is_active)

    def test_confere_uma_vez_por_dia(self):
        self.client.get(reverse("contas:entrar"))
        self.vencer(self.barbara)
        # Data no passado só nasce assim, no teste: na loja ela é recusada. O dia já
        # conferido não volta a ser conferido.
        self.client.get(reverse("contas:entrar"))
        self.assertTrue(get_user_model().objects.get(pk=self.barbara.pk).is_active)
        self.assertEqual(len(prazo.conferir_hoje(self.hoje + timedelta(days=1))), 1)


class TelaDeUsuariosTest(BasePrazo):
    """A data se marca na ficha da pessoa desde a 1.44.0 (antes, num formulário na lista)."""

    def setUp(self):
        super().setUp()
        self.client.login(username="edson", password=SENHA_TESTE)
        confirmar_senha(self.client)

    def _marcar(self, pessoa_pk, texto, **extra):
        return self.client.post(reverse("contas:alterar_usuario", args=[pessoa_pk]),
                                {"acao": "prazo", "acesso_ate": texto}, **extra)

    def test_marca_a_data_pela_tela(self):
        data = self.hoje + timedelta(days=12)
        resposta = self._marcar(self.barbara.pk, data.isoformat(), follow=True)
        self.assertContains(resposta, f"vai até {data:%d/%m/%Y}")
        self.assertContains(resposta, f"{data:%d/%m/%Y}, e no dia seguinte a conta se desliga sozinha")
        self.barbara.vinculo.refresh_from_db()
        self.assertEqual(self.barbara.vinculo.acesso_ate, data)
        lista = self.client.get(reverse("contas:usuarios"))
        self.assertContains(lista, f"acesso até {data:%d/%m/%Y}")

    def test_data_que_nao_se_le_vira_recado(self):
        resposta = self._marcar(self.barbara.pk, "12/11/2026", follow=True)
        self.assertContains(resposta, "Não deu para ler a data")

    def test_pessoa_que_nao_existe_e_404_e_nao_erro(self):
        resposta = self._marcar(987654, self.hoje.isoformat())
        self.assertEqual(resposta.status_code, 404)

    def test_ninguem_marca_data_no_proprio_acesso(self):
        resposta = self._marcar(self.gerente.pk, self.hoje.isoformat(), follow=True)
        self.assertContains(resposta, "Ninguém muda o próprio acesso")
        self.assertIsNone(VinculoIdentidade.objects.filter(usuario=self.gerente)
                          .values_list("acesso_ate", flat=True).first())

    def test_a_propria_ficha_nao_oferece_a_data(self):
        propria = self.client.get(reverse("contas:ficha", args=[self.gerente.pk]))
        self.assertNotContains(propria, 'name="acesso_ate"')
        outra = self.client.get(reverse("contas:ficha", args=[self.barbara.pk]))
        self.assertContains(outra, 'name="acesso_ate"')

    def test_a_conta_nova_ja_nasce_com_a_data(self):
        data = self.hoje + timedelta(days=30)
        self.client.post(reverse("contas:criar_usuario"), {
            "apelido": "temporaria", "nome": "Temporária", "perfis": [ADMINISTRATIVO],
            "acesso_ate": data.isoformat(),
        })
        criada = get_user_model().objects.get(username="temporaria")
        self.assertEqual(criada.vinculo.acesso_ate, data)

    def test_o_vendedor_nao_marca_data_de_ninguem(self):
        self.client.logout()
        from apps.contas.perfis import VENDEDOR  # noqa: PLC0415
        usuario("balcao", VENDEDOR)
        self.client.login(username="balcao", password=SENHA_TESTE)
        resposta = self._marcar(self.barbara.pk, self.hoje.isoformat())
        self.assertEqual(resposta.status_code, 403)
