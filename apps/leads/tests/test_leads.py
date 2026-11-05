"""O funil de leads do SDR (Studio, 05/11/2026)."""

from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.contas.perfis import ADMINISTRACAO, COMERCIAL
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.leads import servicos
from apps.leads.models import Contato, Lead
from apps.projetos.models import Projeto

HOJE = timezone.localdate()


def lead(**extra):
    dados = {"nome": "Paula", "telefone": "11 98888-7777", "interesse": "Mesa de centro em ferro"}
    dados.update(extra)
    return Lead.objects.create(**dados)


class FunilTest(TestCase):
    def test_para_hoje_inclui_atrasado_e_nao_o_futuro(self):
        a = lead(nome="Atrasado", etapa="contato", proximo_contato=HOJE - timedelta(days=2))
        h = lead(nome="Hoje", etapa="novo", proximo_contato=HOJE)
        lead(nome="Depois", etapa="novo", proximo_contato=HOJE + timedelta(days=3))
        lead(nome="Ganho", etapa="ganho", proximo_contato=HOJE - timedelta(days=1))
        funil = servicos.montar(hoje=HOJE)
        self.assertEqual(funil.para_hoje, [a, h])
        self.assertEqual(funil.abertos, 3)

    def test_lead_sem_data_aparece_como_esquecido(self):
        s = lead(nome="Sem data")
        self.assertEqual(servicos.montar(hoje=HOJE).sem_data, [s])

    def test_conversao(self):
        for etapa in ("ganho", "ganho", "perdido"):
            servicos.mudar_etapa(lead(), etapa, "caro").save()
        self.assertEqual(servicos.montar(hoje=HOJE).conversao, 67)

    def test_so_os_meus(self):
        eu = usuario("ana", COMERCIAL)
        outro = usuario("bia", COMERCIAL)
        lead(nome="Meu", responsavel=eu)
        lead(nome="Dela", responsavel=outro)
        self.assertEqual([l.nome for col in servicos.montar(eu).colunas for l in col["cartoes"]], ["Meu"])

    def test_o_mesmo_lead_do_kommo_nao_entra_duas_vezes(self):
        lead(kommo_id="123")
        lead(kommo_id="")
        lead(kommo_id="")  # vazio pode repetir: é lead que não veio do Kommo
        with self.assertRaises(IntegrityError):
            lead(kommo_id="123")


class TelasTest(TestCase):
    def setUp(self):
        self.sdr = usuario("sdr", COMERCIAL)
        self.client.login(username="sdr", password=SENHA_TESTE)

    def test_funil_abre(self):
        lead(nome="Paula", proximo_contato=HOJE)
        pagina = self.client.get(reverse("leads:funil"))
        self.assertContains(pagina, "Falar hoje")
        self.assertContains(pagina, "Paula")

    def test_lead_novo_precisa_de_como_falar(self):
        resposta = self.client.post(reverse("leads:novo"), {"nome": "Sem contato", "origem": "loja"})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "telefone ou o e-mail")
        self.assertContains(resposta, 'value="Sem contato"')
        resposta = self.client.post(reverse("leads:novo"), {
            "nome": "Roberto", "telefone": "11 97777", "origem": "instagram",
            "proximo_contato": HOJE.isoformat()})
        novo = Lead.objects.get()
        self.assertRedirects(resposta, reverse("leads:ficha", args=[novo.pk]))
        self.assertEqual(novo.criado_por, self.sdr)

    def test_registrar_contato_exige_proximo_passo(self):
        l = lead()
        resposta = self.client.post(reverse("leads:contato", args=[l.pk]), {
            "canal": "whatsapp", "resumo": "Mandei fotos", "etapa": "contato"})
        self.assertEqual(resposta.status_code, 400)
        self.assertContains(resposta, "Lead em aberto sem data", status_code=400)
        self.assertContains(resposta, "Mandei fotos", status_code=400)
        self.assertFalse(Contato.objects.exists())

        self.client.post(reverse("leads:contato", args=[l.pk]), {
            "canal": "whatsapp", "resumo": "Mandei fotos", "etapa": "qualificado",
            "proximo_contato": (HOJE + timedelta(days=2)).isoformat()})
        l.refresh_from_db()
        self.assertEqual(l.etapa, "qualificado")
        self.assertEqual(l.proximo_contato, HOJE + timedelta(days=2))
        self.assertEqual(l.contatos.get().autor, self.sdr)

    def test_perder_exige_motivo_e_limpa_a_data(self):
        l = lead(proximo_contato=HOJE)
        resposta = self.client.post(reverse("leads:contato", args=[l.pk]), {
            "canal": "ligacao", "resumo": "Achou caro", "etapa": "perdido"})
        self.assertEqual(resposta.status_code, 400)
        self.client.post(reverse("leads:contato", args=[l.pk]), {
            "canal": "ligacao", "resumo": "Achou caro", "etapa": "perdido", "motivo_perda": "Preço"})
        l.refresh_from_db()
        self.assertEqual((l.etapa, l.motivo_perda, l.proximo_contato), ("perdido", "Preço", None))
        self.assertIsNotNone(l.fechado_em)

    def test_comercial_nao_converte_em_projeto(self):
        l = lead()
        self.assertNotContains(self.client.get(reverse("leads:ficha", args=[l.pk])), "virar projeto")
        self.assertEqual(self.client.post(reverse("leads:converter", args=[l.pk])).status_code, 403)
        self.assertFalse(Projeto.objects.exists())


class ConverterTest(TestCase):
    def test_gerencia_converte_e_o_lead_fica_ganho(self):
        usuario("edson", ADMINISTRACAO)
        self.client.login(username="edson", password=SENHA_TESTE)
        l = lead(valor_estimado=Decimal("7500"))
        resposta = self.client.post(reverse("leads:converter", args=[l.pk]))
        p = Projeto.objects.get()
        self.assertRedirects(resposta, reverse("projetos:editar", args=[p.pk]))
        l.refresh_from_db()
        self.assertEqual((l.etapa, l.projeto), ("ganho", p))
        self.assertEqual((p.cliente_nome, p.cliente_telefone, p.valor_venda, p.titulo),
                         ("Paula", "11 98888-7777", Decimal("7500"), "Mesa de centro em ferro"))
        # Converter de novo não cria outro projeto.
        self.client.post(reverse("leads:converter", args=[l.pk]))
        self.assertEqual(Projeto.objects.count(), 1)
