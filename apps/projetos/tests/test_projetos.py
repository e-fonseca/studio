"""Projetos sob medida, oficinas e parcelas (Studio, 05/11/2026)."""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import EventoAuditoria
from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO, COMERCIAL, CONSULTA
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.projetos import servicos
from apps.projetos.models import Oficina, Parcela, Projeto

HOJE = timezone.localdate()


def projeto(**extra):
    dados = {"titulo": "Mesa de jantar", "cliente_nome": "Mariana", "valor_venda": Decimal("10000"),
             "custo_oficina": Decimal("5500"), "outros_custos": Decimal("500")}
    dados.update(extra)
    return Projeto.objects.create(**dados)


class ContasDoProjetoTest(TestCase):
    def test_margem_e_percentual(self):
        p = projeto()
        self.assertEqual(p.margem, Decimal("4000"))
        self.assertEqual(p.margem_percentual, Decimal("40.0"))

    def test_sem_venda_nao_ha_percentual(self):
        self.assertIsNone(projeto(valor_venda=0).margem_percentual)

    def test_parcelas_somam_o_que_entrou_saiu_e_falta(self):
        p = projeto()
        Parcela.objects.create(projeto=p, tipo="receber", valor=5000, vencimento=HOJE, pago_em=HOJE)
        Parcela.objects.create(projeto=p, tipo="receber", valor=3000, vencimento=HOJE + timedelta(days=30))
        Parcela.objects.create(projeto=p, tipo="oficina", valor=2750, vencimento=HOJE, pago_em=HOJE)
        Parcela.objects.create(projeto=p, tipo="oficina", valor=2750, vencimento=HOJE + timedelta(days=20))
        Parcela.objects.create(projeto=p, tipo="outro", valor=500, vencimento=HOJE + timedelta(days=20))
        self.assertEqual(p.recebido, Decimal("5000"))
        self.assertEqual(p.a_receber, Decimal("3000"))
        self.assertEqual(p.pago, Decimal("2750"))
        self.assertEqual(p.a_pagar, Decimal("3250"))
        # 10.000 vendidos, 8.000 em parcela: 2.000 que ninguém agendou.
        self.assertEqual(p.sem_parcela, Decimal("2000"))

    def test_atraso_so_conta_para_o_que_esta_andando(self):
        atrasado = projeto(etapa="producao", prazo_entrega=HOJE - timedelta(days=4))
        entregue = projeto(etapa="entregue", prazo_entrega=HOJE - timedelta(days=4))
        self.assertEqual(atrasado.dias_de_atraso(HOJE), 4)
        self.assertEqual(entregue.dias_de_atraso(HOJE), 0)

    def test_mudar_etapa_carimba_aprovacao_e_entrega(self):
        p = projeto()
        servicos.mudar_etapa(p, "producao", HOJE)
        self.assertEqual(p.aprovado_em, HOJE)
        servicos.mudar_etapa(p, "entregue", HOJE + timedelta(days=10))
        self.assertEqual(p.entregue_em, HOJE + timedelta(days=10))
        self.assertEqual(p.aprovado_em, HOJE, "voltar ou seguir não apaga a aprovação")

    def test_filtro_atrasados(self):
        a = projeto(etapa="producao", prazo_entrega=HOJE - timedelta(days=1))
        projeto(etapa="producao", prazo_entrega=HOJE + timedelta(days=5))
        projeto(etapa="orcamento", prazo_entrega=HOJE - timedelta(days=1))
        self.assertEqual(list(servicos.filtrar("atrasados", HOJE)), [a])


class TelasTest(TestCase):
    def setUp(self):
        usuario("edson", ADMINISTRACAO)
        self.client.login(username="edson", password=SENHA_TESTE)

    def test_criar_projeto_vai_para_a_ficha_e_audita(self):
        oficina = Oficina.objects.create(nome="Serralheria Silva")
        resposta = self.client.post(reverse("projetos:novo"), {
            "titulo": "Estante industrial", "cliente_nome": "Carlos", "oficina": oficina.pk,
            "valor_venda": "8000", "custo_oficina": "4000", "outros_custos": "0",
            "prazo_entrega": (HOJE + timedelta(days=30)).isoformat(),
        })
        p = Projeto.objects.get()
        self.assertRedirects(resposta, reverse("projetos:ficha", args=[p.pk]))
        self.assertEqual(p.oficina, oficina)
        self.assertTrue(EventoAuditoria.objects.filter(acao="projeto.criado").exists())

    def test_formulario_recusado_devolve_o_que_foi_digitado(self):
        resposta = self.client.post(reverse("projetos:novo"), {
            "titulo": "Banco de ferro", "cliente_nome": "", "valor_venda": "1200",
            "custo_oficina": "0", "outros_custos": "0"})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'value="Banco de ferro"')
        self.assertFalse(Projeto.objects.exists())

    def test_lancar_parcela_e_baixar(self):
        p = projeto()
        self.client.post(reverse("projetos:nova_parcela", args=[p.pk]), {
            "tipo": "receber", "descricao": "Sinal", "valor": "5000",
            "vencimento": HOJE.isoformat()})
        parcela = Parcela.objects.get()
        self.assertIsNone(parcela.pago_em)
        self.client.post(reverse("projetos:baixar_parcela", args=[parcela.pk]))
        parcela.refresh_from_db()
        self.assertEqual(parcela.pago_em, HOJE)
        self.client.post(reverse("projetos:baixar_parcela", args=[parcela.pk]), {"desfazer": "1"})
        parcela.refresh_from_db()
        self.assertIsNone(parcela.pago_em)

    def test_parcela_invalida_volta_preenchida(self):
        p = projeto()
        resposta = self.client.post(reverse("projetos:nova_parcela", args=[p.pk]), {
            "tipo": "receber", "descricao": "Saldo na entrega", "valor": "0",
            "vencimento": HOJE.isoformat()})
        self.assertEqual(resposta.status_code, 400)
        self.assertContains(resposta, 'value="Saldo na entrega"', status_code=400)
        self.assertFalse(Parcela.objects.exists())

    def test_mudar_etapa_pela_tela(self):
        p = projeto()
        self.client.post(reverse("projetos:mudar_etapa", args=[p.pk]), {"etapa": "producao"})
        p.refresh_from_db()
        self.assertEqual(p.etapa, "producao")
        self.client.post(reverse("projetos:mudar_etapa", args=[p.pk]), {"etapa": "inventada"})
        p.refresh_from_db()
        self.assertEqual(p.etapa, "producao")

    def test_lista_ficha_e_oficinas_abrem(self):
        oficina = Oficina.objects.create(nome="Serralheria Silva")
        p = projeto(oficina=oficina, etapa="producao", prazo_entrega=HOJE - timedelta(days=2))
        Parcela.objects.create(projeto=p, tipo="oficina", valor=1000, vencimento=HOJE)
        lista = self.client.get(reverse("projetos:lista"))
        self.assertContains(lista, p.codigo)
        self.assertContains(lista, "2 dias de atraso")
        self.assertContains(self.client.get(reverse("projetos:ficha", args=[p.pk])), "Mesa de jantar")
        oficinas = self.client.get(reverse("projetos:oficinas"))
        self.assertContains(oficinas, "Serralheria Silva")
        self.assertContains(oficinas, "R$ 1.000,00")
        self.assertContains(self.client.get(reverse("projetos:oficina", args=[oficina.pk])), "Mesa de jantar")

    def test_oficina_nova(self):
        resposta = self.client.post(reverse("projetos:oficina_nova"), {
            "nome": "Ferro e Arte", "contato": "Zé", "telefone": "11 99999-0000", "ativa": "on"})
        oficina = Oficina.objects.get()
        self.assertRedirects(resposta, reverse("projetos:oficina", args=[oficina.pk]))

    def test_oficina_desativada_some_da_escolha_mas_nao_do_projeto_dela(self):
        velha = Oficina.objects.create(nome="Antiga", ativa=False)
        Oficina.objects.create(nome="Nova")
        p = projeto(oficina=velha)
        pagina = self.client.get(reverse("projetos:editar", args=[p.pk]))
        self.assertContains(pagina, "Antiga")
        pagina = self.client.get(reverse("projetos:novo"))
        self.assertNotContains(pagina, "Antiga")


class PermissaoTest(TestCase):
    def test_comercial_nao_ve_projetos(self):
        usuario("sdr", COMERCIAL)
        self.client.login(username="sdr", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("projetos:lista")).status_code, 403)

    def test_consulta_nao_entra(self):
        usuario("auditor", CONSULTA)
        self.client.login(username="auditor", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("projetos:lista")).status_code, 403)

    def test_administrativo_ve_e_edita(self):
        usuario("adm", ADMINISTRATIVO)
        self.client.login(username="adm", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("projetos:novo")).status_code, 200)

    def test_quem_so_ve_nao_muda(self):
        from django.contrib.auth.models import Permission
        u = usuario("so_ve")
        u.user_permissions.add(Permission.objects.get(codename="ver_projetos"))
        self.client.login(username="so_ve", password=SENHA_TESTE)
        p = projeto()
        self.assertEqual(self.client.get(reverse("projetos:ficha", args=[p.pk])).status_code, 200)
        self.assertEqual(self.client.post(reverse("projetos:mudar_etapa", args=[p.pk]),
                                          {"etapa": "producao"}).status_code, 403)
        self.assertNotContains(self.client.get(reverse("projetos:ficha", args=[p.pk])), "Mudar a etapa")
