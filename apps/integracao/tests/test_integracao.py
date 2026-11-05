"""A API do agente que opera o Trello e o Kommo (Studio, 05/11/2026)."""

import json

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.leads.models import Lead
from apps.projetos.models import Oficina, Projeto
from apps.projetos import servicos as projetos_servicos
from apps.integracao.models import ChaveDeIntegracao, Evento


class ComChave(TestCase):
    def setUp(self):
        self.registro, self.chave = ChaveDeIntegracao.criar("agente-da-casa")

    def get(self, nome, **kwargs):
        return self.client.get(reverse(f"integracao:{nome}", kwargs=kwargs),
                                HTTP_AUTHORIZATION=f"Bearer {self.chave}")

    def post(self, nome, corpo, **kwargs):
        return self.client.post(reverse(f"integracao:{nome}", kwargs=kwargs), json.dumps(corpo),
                                content_type="application/json",
                                HTTP_AUTHORIZATION=f"Bearer {self.chave}")


class ChaveTest(ComChave):
    def test_sem_chave_ou_chave_errada_ou_desligada_da_401(self):
        url = reverse("integracao:eventos")
        self.assertEqual(self.client.get(url).status_code, 401)
        self.assertEqual(self.client.get(url, HTTP_AUTHORIZATION="Bearer errada").status_code, 401)
        self.assertEqual(self.get("eventos").status_code, 200)
        self.registro.ativa = False
        self.registro.save()
        self.assertEqual(self.get("eventos").status_code, 401)

    def test_a_chave_nao_fica_guardada(self):
        self.assertNotIn(self.chave, self.registro.resumo)
        self.assertEqual(len(self.registro.resumo), 64)

    def test_login_de_pessoa_nao_abre_a_api(self):
        from apps.contas.perfis import ADMINISTRACAO
        from apps.core.fabricas import SENHA_TESTE, usuario
        usuario("edson", ADMINISTRACAO)
        self.client.login(username="edson", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("integracao:eventos")).status_code, 401)

    def test_comando_cria_e_desliga(self):
        from io import StringIO
        saida = StringIO()
        call_command("criar_chave_integracao", "outro", stdout=saida)
        chave = saida.getvalue().strip().splitlines()[-1]
        self.assertIsNotNone(ChaveDeIntegracao.conferir(chave))
        call_command("criar_chave_integracao", "outro", "--desligar", stdout=StringIO())
        self.assertIsNone(ChaveDeIntegracao.conferir(chave))


class EventosTest(ComChave):
    def test_projeto_gera_eventos_so_quando_o_cartao_muda(self):
        p = Projeto.objects.create(titulo="Mesa", cliente_nome="Ana")
        p.valor_venda = 999
        p.save()  # valor não vai para o cartão
        projetos_servicos.mudar_etapa(p, "producao")
        p.oficina = Oficina.objects.create(nome="Serralheria")
        p.save()
        tipos = list(Evento.objects.values_list("tipo", flat=True))
        self.assertEqual(tipos, ["projeto.criado", "projeto.etapa", "projeto.alterado"])

    def test_entregar_guarda_o_cartao_sem_gerar_outro_evento(self):
        p = Projeto.objects.create(titulo="Mesa", cliente_nome="Ana")
        evento = Evento.objects.get()
        lista = self.get("eventos").json()["eventos"]
        self.assertEqual(lista[0]["dados"]["codigo"], p.codigo)
        resposta = self.post("entregar", {"ok": True, "trello_cartao": "abc123"}, pk=evento.pk)
        self.assertTrue(resposta.json()["entregue"])
        p.refresh_from_db()
        self.assertEqual(p.trello_cartao, "abc123")
        self.assertEqual(Evento.objects.count(), 1)
        self.assertEqual(self.get("eventos").json()["eventos"], [])

    def test_falha_conta_tentativa_e_continua_pendente(self):
        Projeto.objects.create(titulo="Mesa", cliente_nome="Ana")
        evento = Evento.objects.get()
        self.post("entregar", {"ok": False, "erro": "Trello fora do ar"}, pk=evento.pk)
        evento.refresh_from_db()
        self.assertEqual((evento.tentativas, evento.ultimo_erro, evento.entregue_em),
                         (1, "Trello fora do ar", None))

    def test_projetos_abertos(self):
        Projeto.objects.create(titulo="A", cliente_nome="X", etapa="producao")
        Projeto.objects.create(titulo="B", cliente_nome="Y", etapa="cancelado")
        Projeto.objects.create(titulo="C", cliente_nome="Z", etapa="entregue")
        self.assertEqual([p["titulo"] for p in self.get("projetos").json()["projetos"]], ["A"])


class LeadDoKommoTest(ComChave):
    CORPO = {"kommo_id": "9001", "nome": "Paula", "telefone": "11 98888-0000",
             "interesse": "Mesa de ferro", "valor_estimado": "7500",
             "mensagens": [{"quando": 1793800000, "texto": "Oi, quero uma mesa"},
                           {"quando": 1793800600, "texto": "Pode ser 2 metros?"}]}

    def test_entra_uma_vez_e_traz_so_as_mensagens_novas(self):
        r1 = self.post("receber_lead", self.CORPO)
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r1.json()["mensagens_novas"], 2)
        corpo = dict(self.CORPO, mensagens=self.CORPO["mensagens"] + [
            {"quando": 1793801200, "texto": "Fechado o tamanho"}])
        r2 = self.post("receber_lead", corpo)
        self.assertEqual((r2.status_code, r2.json()["mensagens_novas"]), (200, 1))
        lead = Lead.objects.get()
        self.assertEqual(lead.contatos.filter(automatico=True).count(), 3)
        self.assertIsNotNone(lead.proximo_contato, "lead novo nasce com contato para hoje")

    def test_nao_apaga_o_que_o_studio_preencheu_nem_muda_a_etapa(self):
        self.post("receber_lead", self.CORPO)
        lead = Lead.objects.get()
        lead.etapa = "qualificado"
        lead.email = "paula@exemplo.com"
        lead.save()
        self.post("receber_lead", {"kommo_id": "9001", "nome": "Paula S."})
        lead.refresh_from_db()
        self.assertEqual((lead.etapa, lead.email, lead.nome), ("qualificado", "paula@exemplo.com", "Paula S."))

    def test_lead_do_kommo_nao_volta_como_evento(self):
        self.post("receber_lead", self.CORPO)
        self.assertFalse(Evento.objects.filter(recurso_tipo="lead").exists())
        lead = Lead.objects.get()
        lead.etapa = "perdido"
        lead.save()  # mudança feita no Studio: essa vai para o Kommo
        self.assertEqual(list(Evento.objects.values_list("tipo", flat=True)), ["lead.etapa"])

    def test_corpo_invalido(self):
        self.assertEqual(self.post("receber_lead", {"nome": "sem id"}).status_code, 400)
        resposta = self.client.post(reverse("integracao:receber_lead"), "isto não é json",
                                    content_type="application/json",
                                    HTTP_AUTHORIZATION=f"Bearer {self.chave}")
        self.assertEqual(resposta.status_code, 400)
