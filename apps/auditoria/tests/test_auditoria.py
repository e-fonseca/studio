from django.db import DatabaseError, connection, transaction
from django.test import TestCase

from apps.auditoria.models import EventoAuditoria
from apps.auditoria.servicos import registrar
from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario


class TrilhaSomenteInclusaoTest(TestCase):
    def test_orm_nao_altera_nem_apaga(self):
        evento = registrar("teste.acao", servico="teste")
        evento.acao = "outra"
        with self.assertRaises(PermissionError):
            evento.save()
        with self.assertRaises(PermissionError):
            evento.delete()
        with self.assertRaises(PermissionError):
            EventoAuditoria.objects.all().update(acao="x")
        with self.assertRaises(PermissionError):
            EventoAuditoria.objects.all().delete()

    def test_banco_recusa_update_e_delete(self):
        evento = registrar("teste.acao", servico="teste")
        for sql in [
            "UPDATE auditoria_eventoauditoria SET acao = 'x' WHERE id = %s",
            "DELETE FROM auditoria_eventoauditoria WHERE id = %s",
        ]:
            with self.assertRaises(DatabaseError), transaction.atomic(), connection.cursor() as c:
                c.execute(sql, [evento.pk])
        self.assertEqual(EventoAuditoria.objects.get(pk=evento.pk).acao, "teste.acao")

    def test_campos_sensiveis_sao_omitidos(self):
        evento = registrar("teste.acao", servico="teste", depois={"senha": "x", "token": "y", "nome": "ok"})
        self.assertEqual(evento.depois, {"senha": "[omitido]", "token": "[omitido]", "nome": "ok"})


class AcessoAuditadoTest(TestCase):
    def test_entrada_e_falha_registradas_sem_senha(self):
        usuario("ana", VENDEDOR)
        self.client.post("/sistema/entrar/", {"username": "ana", "password": "errada-123"})
        self.client.post("/sistema/entrar/", {"username": "ana", "password": SENHA_TESTE})
        falha = EventoAuditoria.objects.get(acao="acesso.falha")
        self.assertEqual(falha.depois, {"usuario_tentado": "ana"})
        self.assertNotIn("errada", str(falha.depois))
        self.assertTrue(EventoAuditoria.objects.filter(acao="acesso.entrada", usuario_rotulo="ana").exists())

    def test_correlacao_volta_no_cabecalho_e_fica_no_evento(self):
        usuario("ana", VENDEDOR)
        resposta = self.client.post("/sistema/entrar/", {"username": "ana", "password": SENHA_TESTE})
        evento = EventoAuditoria.objects.get(acao="acesso.entrada")
        self.assertEqual(resposta["X-Correlacao"], str(evento.correlacao))
        self.assertEqual(evento.ip, "127.0.0.1")


class ConsultaAuditoriaTest(TestCase):
    def test_operador_nao_ve_auditoria(self):
        usuario("op", VENDEDOR)
        self.client.login(username="op", password=SENHA_TESTE)
        self.assertEqual(self.client.get("/sistema/auditoria/").status_code, 403)

    def test_administrativo_nao_ve_auditoria(self):
        """Auditoria é da gerência: quem lança conta não audita o próprio lançamento."""
        usuario("adm", ADMINISTRATIVO)
        self.client.login(username="adm", password=SENHA_TESTE)
        self.assertEqual(self.client.get("/sistema/auditoria/").status_code, 403)

    def test_gerencia_ve_auditoria(self):
        usuario("aud", ADMINISTRACAO)
        self.client.login(username="aud", password=SENHA_TESTE)
        self.assertEqual(self.client.get("/sistema/auditoria/").status_code, 200)
