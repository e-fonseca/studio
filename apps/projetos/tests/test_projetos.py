"""Pedidos sob medida e oficinas (Studio, 05/11/2026; regras do protótipo, 06/11/2026)."""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import EventoAuditoria
from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO, COMERCIAL, CONSULTA
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.projetos import servicos
from apps.projetos.models import Oficina, Projeto

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

    def test_custo_total_soma_frete_embalagem_rt_e_projeto(self):
        p = projeto(frete=Decimal("300"), embalagem=Decimal("80"), rt=Decimal("1000"),
                    projeto_desenho=Decimal("150"))
        self.assertEqual(p.custo_total, Decimal("7530"))

    def test_regime_vem_do_pedido_ou_da_oficina(self):
        rogerio = Oficina.objects.create(nome="Rogério", pagamento="mensal", dia_pagamento=30, dia_corte=25)
        self.assertEqual(projeto(oficina=rogerio).regime_efetivo, "mensal")
        self.assertEqual(projeto(oficina=rogerio, regime="cartao").regime_efetivo, "cartao")
        self.assertEqual(projeto().regime_efetivo, "padrao")

    def test_codigo_e_o_numero_do_card(self):
        self.assertEqual(projeto(numero="28634").codigo, "28634")
        p = projeto()
        self.assertEqual(p.codigo, f"S-{p.pk:04d}")

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

    BASE = {"valor_venda": "8000", "custo_oficina": "4000", "outros_custos": "0", "recebido": "0",
            "frete": "0", "embalagem": "0", "rt": "0", "projeto_desenho": "0", "incluir": "on",
            "etapa": "orcamento"}

    def test_criar_projeto_vai_para_a_ficha_e_audita(self):
        oficina = Oficina.objects.create(nome="Serralheria Silva")
        resposta = self.client.post(reverse("projetos:novo"), {
            **self.BASE, "numero": "28900", "titulo": "Estante industrial", "cliente_nome": "Carlos",
            "oficina": oficina.pk, "prazo_entrega": (HOJE + timedelta(days=30)).isoformat(),
        })
        p = Projeto.objects.get()
        self.assertRedirects(resposta, reverse("projetos:ficha", args=[p.pk]))
        self.assertEqual(p.oficina, oficina)
        self.assertTrue(EventoAuditoria.objects.filter(acao="projeto.criado").exists())

    def test_formulario_recusado_devolve_o_que_foi_digitado(self):
        resposta = self.client.post(reverse("projetos:novo"), {
            **self.BASE, "titulo": "Banco de ferro", "cliente_nome": "", "valor_venda": "1200",
            "arquiteto": "Luisa B.", "data_venda": "2026-10-03"})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'value="Banco de ferro"')
        self.assertContains(resposta, 'value="Luisa B."')
        self.assertContains(resposta, 'value="2026-10-03"')
        self.assertFalse(Projeto.objects.exists())

    def test_sem_titulo_e_sem_numero_recusa(self):
        resposta = self.client.post(reverse("projetos:novo"), {**self.BASE, "cliente_nome": "Ana"})
        self.assertContains(resposta, "Diga o que é o móvel ou o número do card.")
        self.assertFalse(Projeto.objects.exists())

    def test_pagar_a_primeira_e_a_segunda_parcela_e_desfazer(self):
        p = projeto(etapa="producao")
        self.client.post(reverse("projetos:pagar", args=[p.pk]), {"parcela": "pg1"})
        p.refresh_from_db()
        self.assertEqual(p.pg1_data, HOJE)
        self.client.post(reverse("projetos:pagar", args=[p.pk]), {"parcela": "pg2"})
        p.refresh_from_db()
        self.assertEqual(p.pg2_data, HOJE)
        self.client.post(reverse("projetos:pagar", args=[p.pk]), {"parcela": "pg1", "desfazer": "1"})
        p.refresh_from_db()
        self.assertIsNone(p.pg1_data)
        self.assertEqual(EventoAuditoria.objects.filter(acao="projeto.oficina_paga").count(), 3)

    def test_pagar_parcela_inventada_nao_muda_nada(self):
        p = projeto(etapa="producao")
        self.client.post(reverse("projetos:pagar", args=[p.pk]), {"parcela": "pg9"})
        p.refresh_from_db()
        self.assertIsNone(p.pg1_data)

    def test_baixar_a_lista_em_arquivo(self):
        projeto(numero="28634", etapa="producao", cliente_nome="André; Haustor")
        resposta = self.client.get(reverse("projetos:lista_em_arquivo") + "?filtro=andamento")
        texto = resposta.content.decode("utf-8")
        self.assertTrue(texto.startswith("\ufeffPedido;Cliente"))
        self.assertIn('28634;"André; Haustor"', texto)
        self.assertIn("10000,00", texto)

    def test_filtros_com_alerta_e_incompletos(self):
        baixa = projeto(numero="1", etapa="producao", valor_venda=Decimal("6000"))  # margem < 25%
        boa = projeto(numero="2", etapa="producao", valor_venda=Decimal("20000"),
                      prazo_entrega=HOJE + timedelta(days=9), pg1_data=HOJE, saldo_forma="pix",
                      oficina=Oficina.objects.create(nome="X"))
        alerta = self.client.get(reverse("projetos:lista") + "?filtro=alerta")
        self.assertContains(alerta, reverse("projetos:ficha", args=[baixa.pk]))
        self.assertNotContains(alerta, reverse("projetos:ficha", args=[boa.pk]))
        incompletos = self.client.get(reverse("projetos:lista") + "?filtro=incompletos")
        self.assertContains(incompletos, reverse("projetos:ficha", args=[baixa.pk]))
        self.assertNotContains(incompletos, reverse("projetos:ficha", args=[boa.pk]))

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
        p = projeto(oficina=oficina, etapa="producao", prazo_entrega=HOJE - timedelta(days=2),
                    custo_oficina=Decimal("2000"), pg1_data=HOJE - timedelta(days=60))
        lista = self.client.get(reverse("projetos:lista"))
        self.assertContains(lista, p.codigo)
        self.assertContains(lista, "2 dias de atraso")
        self.assertContains(self.client.get(reverse("projetos:ficha", args=[p.pk])), "Mesa de jantar")
        oficinas = self.client.get(reverse("projetos:oficinas"))
        self.assertContains(oficinas, "Serralheria Silva")
        # A 1ª parcela (cartão, 60 dias atrás) já passou; falta a 2ª, em Pix, devida hoje.
        self.assertContains(oficinas, "R$ 1.000,00")
        ficha = self.client.get(reverse("projetos:ficha", args=[p.pk]))
        self.assertContains(ficha, "2ª parcela na entrega")
        self.assertContains(self.client.get(reverse("projetos:oficina", args=[oficina.pk])), "Mesa de jantar")

    def test_oficina_nova(self):
        resposta = self.client.post(reverse("projetos:oficina_nova"), {
            "nome": "Ferro e Arte", "contato": "Zé", "telefone": "11 99999-0000", "ativa": "on",
            "pagamento": "padrao", "parcelas_mensais": "3"})
        oficina = Oficina.objects.get()
        self.assertRedirects(resposta, reverse("projetos:oficina", args=[oficina.pk]))

    def test_oficina_mensal_precisa_do_dia(self):
        resposta = self.client.post(reverse("projetos:oficina_nova"), {
            "nome": "Breno", "ativa": "on", "pagamento": "mensal", "parcelas_mensais": "3"})
        self.assertContains(resposta, "Diga o dia do mês em que esta oficina recebe.")
        self.assertFalse(Oficina.objects.exists())

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
