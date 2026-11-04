"""Descontos e metas (1.46.0): cada venda contra as regras da loja, e a meta do fim de semana.

Pedido do Edson em 02/11/2026, com as regras que a gerência passa à equipe: Pix e dinheiro
com até 7%, crédito em até 3x sem desconto, o resto só com aprovação do grupo; meta de
R$ 12.000 no sábado e no feriado e de R$ 18.000 no domingo (R$ 15.000 desde 04/11/2026,
1.47.0), com R$ 30 por pessoa e R$ 10
a cada R$ 1.000 acima. "A ideia é controlar os descontos para que os funcionários não
deem desconto sem parâmetros só objetivando a premiação."

Os nomes de quem estava no caixa são de mentira ("CAIXA TESTE"): nome de funcionário não
entra em teste.
"""

from datetime import date, datetime
from decimal import Decimal

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import EventoAuditoria
from apps.caixa import descontos, feriados
from apps.caixa.forms import numero_digitado
from apps.caixa.models import CaixaImportado, DescontoAprovado, RegraDeDesconto
from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.importacao.models import Importacao, ItemVendaImportada, VendaImportada

# 19/09/2026 é sábado e 20/09/2026, domingo: o fim de semana da cópia do SET.
SABADO = date(2026, 9, 19)
DOMINGO = date(2026, 9, 20)
SEGUNDA = date(2026, 9, 14)


def _venda(valor, desconto="0", forma="PIX", formas=None, produtos=None, numero="1", data=SABADO,
           quem="CAIXA TESTE"):
    """Uma venda em memória, como a importação grava. `produtos` é o total antes do desconto."""
    valor, desconto = Decimal(valor), Decimal(desconto)
    return VendaImportada(
        id_set=int(numero), numero=numero, data=data, hora="15:00:00", valor=valor,
        desconto=desconto, forma_pagamento=forma, recebido_por=quem,
        total_produtos=Decimal(produtos) if produtos is not None else valor + desconto,
        formas_pagas=formas or {},
    )


def _item(cobrado, tabela=None, descricao="VASO DE CERAMICA", quantidade="1", custo=None,
          do_cadastro=False, codigo="001"):
    return ItemVendaImportada(
        codigo=codigo, descricao=descricao, quantidade=Decimal(quantidade),
        valor_total=Decimal(cobrado), preco_tabela=Decimal(tabela) if tabela else None,
        preco_tabela_do_cadastro=do_cadastro,
        custo_unitario=Decimal(custo) if custo else None,
        custo_total=Decimal(custo) * Decimal(quantidade) if custo else None,
    )


class FormaDePagamentoTest(SimpleTestCase):
    def test_cada_forma_do_set_cai_na_sua_regra(self):
        self.assertEqual(descontos.categoria("PIX"), descontos.A_VISTA)
        self.assertEqual(descontos.categoria("AVISTA"), descontos.A_VISTA)
        self.assertEqual(descontos.categoria("Dinheiro"), descontos.A_VISTA)
        self.assertEqual(descontos.categoria("CARTAO DEBITO"), descontos.DEBITO)
        self.assertEqual(descontos.categoria("CARTÃO DE CRÉDITO"), descontos.CREDITO)
        self.assertEqual(descontos.categoria("PRAZO"), descontos.OUTRA)
        self.assertEqual(descontos.categoria(""), "")

    def test_vendido_a_peso_pela_descricao(self):
        for descricao in ("PIRITA NOVA  357KG", "GEODO DE AGATA COLORIDO KG 130,00",
                          "AMETISTA BRUTA 95 KL"):
            self.assertTrue(descontos.vendido_a_peso(descricao), descricao)
        for descricao in ("VASO KGB", "TAPETE M PALHA", "BOLSA KILIM"):
            self.assertFalse(descontos.vendido_a_peso(descricao), descricao)


class RegraDaVendaTest(SimpleTestCase):
    """A conta de uma venda contra a regra, sem banco."""

    def setUp(self):
        self.regra = RegraDeDesconto()

    def avaliar(self, venda, *itens):
        return descontos.avaliar(venda, self.regra, list(itens))

    def test_sete_por_cento_no_pix_esta_dentro_da_regra(self):
        venda = self.avaliar(_venda("93", "7"))
        self.assertEqual(venda.permitido, Decimal("7.00"))
        self.assertEqual(venda.percentual, Decimal("7.0"))
        self.assertFalse(venda.fora)

    def test_o_mesmo_no_dinheiro(self):
        self.assertFalse(self.avaliar(_venda("93", "7", forma="AVISTA")).fora)

    def test_passar_um_pouco_por_arredondar_nao_conta(self):
        """R$ 107,90 fechado em R$ 100,00 no Pix: 7,3%, R$ 0,45 além dos 7%."""
        self.assertFalse(self.avaliar(_venda("100", "7.90")).fora)

    def test_passar_da_folga_e_fora_da_regra(self):
        venda = self.avaliar(_venda("91", "9"))
        self.assertTrue(venda.fora)
        self.assertEqual(venda.passou, Decimal("2.00"))
        self.assertIn("Passou R$ 2,00 da regra", venda.regra_texto)
        self.assertIn("no Pix ela deixa até 7%", venda.regra_texto)

    def test_desconto_no_credito_e_fora_da_regra(self):
        venda = self.avaliar(_venda("95", "5", forma="CARTAO CREDITO"))
        self.assertTrue(venda.fora)
        self.assertEqual(venda.permitido, Decimal("0"))
        self.assertIn("no cartão de crédito ela é sem desconto", venda.regra_texto)

    def test_desconto_no_debito_e_fora_da_regra(self):
        self.assertTrue(self.avaliar(_venda("95", "5", forma="CARTAO DEBITO")).fora)

    def test_cartao_sem_desconto_esta_dentro(self):
        self.assertFalse(self.avaliar(_venda("100", forma="CARTAO CREDITO")).fora)

    def test_a_prazo_e_condicao_diferente_mesmo_sem_desconto(self):
        venda = self.avaliar(_venda("100", forma="PRAZO"))
        self.assertTrue(venda.fora)
        self.assertIn("condição fora das regras", venda.regra_texto)

    def test_venda_dividida_so_tem_desconto_na_parte_do_pix(self):
        """107 de tabela, metade no Pix e metade no crédito: deixa 7% de 53,50."""
        venda = self.avaliar(_venda("100", "7", formas={"PIX": "50.00", "CARTAO CREDITO": "50.00"}))
        self.assertEqual(venda.permitido, Decimal("3.74"))
        self.assertTrue(venda.fora)
        self.assertIn("só na parte paga no Pix", venda.regra_texto)

    def test_preco_mudado_no_caixa_conta_como_desconto(self):
        """O SET mostra desconto zero; o produto saiu de R$ 50,00 por R$ 40,00."""
        venda = self.avaliar(_venda("40", produtos="40"), _item("40", tabela="50"))
        self.assertEqual(venda.desconto_no_fechamento, Decimal("0"))
        self.assertEqual(venda.corte_nos_itens, Decimal("10.00"))
        self.assertEqual(venda.tabela, Decimal("50.00"))
        self.assertEqual(venda.percentual, Decimal("20.0"))
        self.assertTrue(venda.fora)
        self.assertIn("preço mudado no caixa (1 produto)", venda.corte_texto)

    def test_preco_do_cadastro_aparece_como_comparado_ao_cadastro(self):
        venda = self.avaliar(_venda("40", produtos="40"), _item("40", tabela="50", do_cadastro=True))
        self.assertTrue(venda.tabela_estimada)
        self.assertIn("comparado ao preço do cadastro", venda.corte_texto)

    def test_produto_a_peso_nao_tem_o_preco_comparado(self):
        """O caixa digita o preço do pedaço; o cadastro tem o preço do quilo."""
        venda = self.avaliar(_venda("41", produtos="41"),
                             _item("41", tabela="357", descricao="PIRITA NOVA  357KG"))
        self.assertEqual(venda.corte_nos_itens, Decimal("0"))
        self.assertFalse(venda.fora)
        self.assertEqual(venda.itens[0].sem_comparar, "vendido a peso")

    def test_diversos_nao_tem_o_preco_comparado(self):
        venda = self.avaliar(_venda("0.50", produtos="0.50"),
                             _item("0.50", tabela="1", descricao="DIVERSOS"))
        self.assertEqual(venda.corte_nos_itens, Decimal("0"))

    def test_preco_acima_da_tabela_nao_vira_desconto_negativo(self):
        venda = self.avaliar(_venda("60", produtos="60"), _item("60", tabela="50"))
        self.assertEqual(venda.corte_nos_itens, Decimal("0"))
        self.assertFalse(venda.fora)

    def test_desconto_do_fechamento_dividido_entre_os_produtos(self):
        venda = self.avaliar(_venda("90", "10", produtos="100"),
                             _item("75", codigo="001"), _item("25", codigo="002"))
        self.assertEqual([item.rateio for item in venda.itens], [Decimal("7.50"), Decimal("2.50")])
        self.assertEqual(sum(item.rateio for item in venda.itens), Decimal("10"))

    def test_rateio_que_nao_divide_redondo_fecha_no_ultimo(self):
        venda = self.avaliar(_venda("90", "10", produtos="100"),
                             *[_item("33.33", codigo=f"00{n}") for n in range(2)], _item("33.34", codigo="009"))
        self.assertEqual(sum(item.rateio for item in venda.itens), Decimal("10"))

    def test_abaixo_do_custo(self):
        venda = self.avaliar(_venda("40", "10", produtos="50"), _item("50", custo="45"))
        self.assertTrue(venda.abaixo_do_custo)
        self.assertTrue(venda.itens[0].abaixo_do_custo)

    def test_a_regra_mudada_vale_na_hora(self):
        self.regra.desconto_a_vista = Decimal("10")
        self.assertFalse(self.avaliar(_venda("91", "9")).fora)

    def test_o_motivo_do_email_tem_forma_porcentagem_e_regra(self):
        venda = self.avaliar(_venda("85", "15", forma="CARTAO CREDITO"))
        self.assertIn("Cartão de crédito, 15% de desconto", venda.motivo)
        self.assertIn("ela é sem desconto", venda.motivo)


class NomesQueAutorizamTest(SimpleTestCase):
    def test_os_nomes_saem_da_frase(self):
        regra = RegraDeDesconto(quem_autoriza="Miranda, Henriett ou Edson")
        self.assertEqual(regra.nomes_de_quem_autoriza(), ["Miranda", "Henriett", "Edson"])


class NumeroDigitadoTest(SimpleTestCase):
    def test_como_se_escreve_em_portugues(self):
        self.assertEqual(numero_digitado("12.000"), "12000")
        self.assertEqual(numero_digitado("12.000,00"), "12000.00")
        self.assertEqual(numero_digitado("R$ 1.500,50"), "1500.50")
        self.assertEqual(numero_digitado("7,5"), "7.5")
        self.assertEqual(numero_digitado("7.5"), "7.5")
        self.assertEqual(numero_digitado("7%"), "7")


class FeriadosTest(SimpleTestCase):
    def test_pascoa_e_os_feriados_que_dependem_dela(self):
        self.assertEqual(feriados.pascoa(2026), date(2026, 4, 5))
        self.assertEqual(feriados.pascoa(2027), date(2027, 3, 28))
        do_ano = feriados.do_ano(2026)
        self.assertEqual(do_ano[date(2026, 4, 3)], "Sexta-feira da Paixão")
        self.assertEqual(do_ano[date(2026, 6, 4)], "Corpus Christi")

    def test_os_de_sao_paulo_e_de_embu(self):
        do_ano = feriados.do_ano(2026)
        self.assertIn(date(2026, 7, 9), do_ano)
        self.assertEqual(do_ano[date(2026, 2, 18)], "Aniversário de Embu das Artes")

    def test_consciencia_negra_so_desde_2024(self):
        self.assertIn(date(2024, 11, 20), feriados.do_ano(2024))
        self.assertNotIn(date(2023, 11, 20), feriados.do_ano(2023))

    def test_carnaval_nao_e_feriado_sozinho(self):
        self.assertNotIn(date(2026, 2, 17), feriados.do_ano(2026))

    def test_feriado_escrito_pela_gerencia(self):
        texto = "16/02/2027 Carnaval\n20/01 - São Sebastião"
        em_2027 = feriados.feriados_entre(date(2027, 1, 1), date(2027, 12, 31), texto)
        self.assertEqual(em_2027[date(2027, 2, 16)], "Carnaval")
        self.assertEqual(em_2027[date(2027, 1, 20)], "São Sebastião")
        em_2026 = feriados.feriados_entre(date(2026, 1, 1), date(2026, 12, 31), texto)
        self.assertNotIn(date(2026, 2, 16), em_2026)
        self.assertIn(date(2026, 1, 20), em_2026)

    def test_linha_que_nao_e_data_volta_como_erro(self):
        entendidas, erradas = feriados.ler_outros("20/01\n31/02\nCarnaval")
        self.assertEqual(len(entendidas), 1)
        self.assertEqual(erradas, ["31/02", "Carnaval"])

    def test_tipo_do_dia(self):
        do_ano = feriados.do_ano(2026)
        self.assertEqual(feriados.tipo_de_dia(date(2026, 11, 2), do_ano), ("feriado", "Finados"))
        self.assertEqual(feriados.tipo_de_dia(date(2026, 11, 15), do_ano),
                         ("domingo", "Proclamação da República"))
        self.assertEqual(feriados.tipo_de_dia(SABADO, do_ano), ("sabado", ""))
        self.assertEqual(feriados.tipo_de_dia(SEGUNDA, do_ano), ("", ""))


class PremioTest(SimpleTestCase):
    def dia(self, vendido):
        return descontos.DiaDeMeta(dia=SABADO, tipo="sabado", feriado="", meta=Decimal("12000"),
                                   vendido=Decimal(vendido), premio_base=Decimal("30"),
                                   premio_a_mais=Decimal("10"), passo=Decimal("1000"))

    def test_a_tabela_do_premio(self):
        self.assertEqual(self.dia("11999.99").premio, Decimal("0"))
        self.assertEqual(self.dia("12000").premio, Decimal("30"))
        self.assertEqual(self.dia("12999.99").premio, Decimal("30"))
        self.assertEqual(self.dia("13500").premio, Decimal("40"))
        self.assertEqual(self.dia("14000").premio, Decimal("50"))


class ComDados(TestCase):
    """Uma importação com um fim de semana de vendas."""

    def setUp(self):
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO, situacao=Importacao.Situacao.CONCLUIDA,
            iniciada_em=timezone.now(), concluida_em=timezone.now(), data_corte=DOMINGO,
            dias_abertos_12m=300, produtos=1,
        )
        self.numero = 100

    def venda(self, data, valor, desconto="0", forma="PIX", quem="CAIXA TESTE", itens=()):
        self.numero += 1
        valor, desconto = Decimal(valor), Decimal(desconto)
        venda = VendaImportada.objects.create(
            importacao=self.importacao, id_set=self.numero, numero=f"{self.numero}.12", data=data,
            hora="15:00:00", dia_da_semana=(data.weekday() + 1) % 7, valor=valor, desconto=desconto,
            forma_pagamento=forma, total_produtos=valor + desconto, recebido_por=quem,
            formas_pagas={forma: str(valor)},
        )
        for codigo, cobrado, tabela in itens:
            ItemVendaImportada.objects.create(
                venda=venda, codigo=codigo, descricao=f"PRODUTO {codigo}", quantidade=Decimal("1"),
                valor_total=Decimal(cobrado), preco_tabela=Decimal(tabela))
        return venda


class MetaTest(ComDados):
    def test_meta_que_so_bateu_com_venda_fora_da_regra(self):
        self.venda(SABADO, "11900")
        self.venda(SABADO, "600", "100", forma="CARTAO CREDITO")  # fora da regra
        tela = descontos.montar(self.importacao)
        sabado = next(dia for dia in tela.metas if dia.dia == SABADO)
        self.assertTrue(sabado.bateu)
        self.assertEqual(sabado.premio, Decimal("30"))
        self.assertEqual(sabado.vendido_sem_fora, Decimal("11900"))
        self.assertTrue(sabado.dependeu_de_fora)
        self.assertEqual(tela.metas_que_dependeram, [sabado])

    def test_venda_aprovada_nao_pesa_contra_a_meta(self):
        self.venda(SABADO, "11900")
        fora = self.venda(SABADO, "600", "100", forma="CARTAO CREDITO")
        DescontoAprovado.objects.create(id_venda=fora.id_set, numero=fora.numero, dia=SABADO,
                                        autorizado_por="Edson")
        tela = descontos.montar(self.importacao)
        sabado = next(dia for dia in tela.metas if dia.dia == SABADO)
        self.assertFalse(sabado.dependeu_de_fora)
        self.assertEqual(len(tela.aprovadas), 1)
        self.assertEqual(tela.sem_aprovacao, [])

    def test_domingo_tem_a_meta_do_domingo_e_dia_de_semana_nao_tem_meta(self):
        self.venda(DOMINGO, "15500")
        self.venda(SEGUNDA, "30000")
        tela = descontos.montar(self.importacao)
        self.assertEqual([dia.dia for dia in tela.metas], [DOMINGO])
        # R$ 15 mil desde 04/11/2026 (1.47.0); era R$ 18 mil.
        self.assertEqual(tela.metas[0].meta, Decimal("15000"))
        self.assertEqual(tela.metas[0].premio, Decimal("30"))

    def test_quem_trabalhou_vem_do_caixa_e_de_quem_recebeu(self):
        self.venda(SABADO, "100", quem="CAIXA TESTE")
        CaixaImportado.objects.create(
            importacao=self.importacao, id_set=1, operador="OUTRA PESSOA TESTE", dia=SABADO,
            aberto_em=timezone.make_aware(datetime(2026, 9, 19, 9)))
        sabado = descontos.montar(self.importacao).metas[0]
        self.assertEqual(sabado.quem, ["Caixa Teste", "Outra Pessoa Teste"])

    def test_a_meta_mudada_pela_gerencia_vale_na_tela(self):
        regra = RegraDeDesconto.atual()
        regra.meta_sabado = Decimal("10000")
        regra.save()
        self.venda(SABADO, "11000")
        self.assertTrue(descontos.montar(self.importacao).metas[0].bateu)

    def test_feriado_escrito_pela_gerencia_vira_dia_de_meta(self):
        regra = RegraDeDesconto.atual()
        regra.outros_feriados = "14/09/2026 Dia de teste"
        regra.save()
        self.venda(SEGUNDA, "100")
        metas = descontos.montar(self.importacao).metas
        self.assertEqual([(dia.dia, dia.rotulo) for dia in metas], [(SEGUNDA, "Dia de teste")])


class TelaTest(ComDados):
    def setUp(self):
        super().setUp()
        self.gerente = usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)

    def test_quem_nao_e_da_gerencia_nao_abre(self):
        for nome, perfil in (("balcao", VENDEDOR), ("ana", ADMINISTRATIVO)):
            usuario(nome, perfil)
            self.client.login(username=nome, password=SENHA_TESTE)
            for rota in ("caixa:descontos", "caixa:regras_de_desconto"):
                with self.subTest(nome=nome, rota=rota):
                    self.assertEqual(self.client.get(reverse(rota)).status_code, 403)
            resposta = self.client.post(reverse("caixa:aprovar_desconto"), {"venda": 1})
            self.assertEqual(resposta.status_code, 403)

    def test_a_tela_mostra_a_venda_fora_da_regra_com_os_produtos(self):
        self.venda(SABADO, "40", itens=[("001", "40", "50")])
        pagina = self.client.get(reverse("caixa:descontos"))
        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, "Fora da regra, esperando aprovação")
        self.assertContains(pagina, "Venda 101.12")
        self.assertContains(pagina, "foi preço mudado no caixa")
        self.assertContains(pagina, "PRODUTO 001")

    def test_sem_importacao_a_tela_avisa(self):
        Importacao.objects.all().delete()
        self.assertContains(self.client.get(reverse("caixa:descontos")), "Ainda não há vendas importadas")

    def test_importacao_antiga_avisa_que_a_proxima_completa(self):
        VendaImportada.objects.create(importacao=self.importacao, id_set=1, numero="1", data=SABADO,
                                      valor=Decimal("100"), forma_pagamento="PIX")
        self.assertContains(self.client.get(reverse("caixa:descontos")),
                            "A próxima importação completa esta tela")

    def test_filtrar_por_quem_recebeu(self):
        self.venda(SABADO, "95", "5", forma="CARTAO CREDITO", quem="CAIXA UM TESTE")
        self.venda(SABADO, "95", "5", forma="CARTAO CREDITO", quem="CAIXA DOIS TESTE")
        tela = descontos.montar(self.importacao, quem="Caixa Um Teste")
        self.assertEqual([venda.quem for venda in tela.fora], ["Caixa Um Teste"])
        # Nome que não está no período não filtra nada (e não quebra a tela).
        self.assertEqual(len(descontos.montar(self.importacao, quem="Ninguém").fora), 2)

    def test_anotar_a_aprovacao_tira_a_venda_da_lista_e_fica_na_auditoria(self):
        venda = self.venda(SABADO, "85", "15", forma="CARTAO CREDITO")
        resposta = self.client.post(reverse("caixa:aprovar_desconto"), {
            "venda": venda.id_set, "autorizado_por": "Henriett", "observacao": "cliente antigo",
            "periodo": "30d", "quem": ""})
        self.assertRedirects(resposta, reverse("caixa:descontos") + "?periodo=30d",
                             fetch_redirect_response=False)
        aprovacao = DescontoAprovado.objects.get()
        self.assertEqual((aprovacao.autorizado_por, aprovacao.observacao, aprovacao.registrado_por),
                         ("Henriett", "cliente antigo", self.gerente))
        self.assertEqual(aprovacao.desconto, Decimal("15"))
        self.assertTrue(EventoAuditoria.objects.filter(acao="caixa.desconto_aprovado").exists())
        tela = descontos.montar(self.importacao)
        self.assertEqual(tela.sem_aprovacao, [])
        self.assertEqual(len(tela.aprovadas), 1)

    def test_so_quem_esta_na_regra_pode_ter_aprovado(self):
        venda = self.venda(SABADO, "85", "15", forma="CARTAO CREDITO")
        self.client.post(reverse("caixa:aprovar_desconto"),
                         {"venda": venda.id_set, "autorizado_por": "Fulano"})
        self.assertFalse(DescontoAprovado.objects.exists())

    def test_aprovar_duas_vezes_nao_duplica(self):
        venda = self.venda(SABADO, "85", "15", forma="CARTAO CREDITO")
        self.client.post(reverse("caixa:aprovar_desconto"),
                         {"venda": venda.id_set, "autorizado_por": "Edson"})
        # A segunda (a outra pessoa que anotou no mesmo segundo) bate na regra do banco e
        # volta para a tela com o aviso, sem tela de erro.
        segunda = self.client.post(reverse("caixa:aprovar_desconto"),
                                   {"venda": venda.id_set, "autorizado_por": "Miranda"}, follow=True)
        self.assertContains(segunda, "já estava com a aprovação anotada")
        self.assertEqual(DescontoAprovado.objects.get().autorizado_por, "Edson")

    def test_venda_que_nao_esta_na_importacao_nao_e_anotada(self):
        self.client.post(reverse("caixa:aprovar_desconto"), {"venda": 999, "autorizado_por": "Edson"})
        self.assertFalse(DescontoAprovado.objects.exists())

    def test_desfazer_devolve_a_venda_para_a_lista_e_nao_apaga_nada(self):
        venda = self.venda(SABADO, "85", "15", forma="CARTAO CREDITO")
        self.client.post(reverse("caixa:aprovar_desconto"),
                         {"venda": venda.id_set, "autorizado_por": "Edson"})
        aprovacao = DescontoAprovado.objects.get()
        self.client.post(reverse("caixa:desfazer_aprovacao", args=[aprovacao.pk]))
        aprovacao.refresh_from_db()
        self.assertIsNotNone(aprovacao.desfeito_em)
        self.assertEqual(aprovacao.desfeito_por, self.gerente)
        self.assertEqual(len(descontos.montar(self.importacao).sem_aprovacao), 1)
        self.assertTrue(EventoAuditoria.objects.filter(acao="caixa.aprovacao_desfeita").exists())
        # E dá para anotar de novo: a desfeita fica como história.
        self.client.post(reverse("caixa:aprovar_desconto"),
                         {"venda": venda.id_set, "autorizado_por": "Miranda"})
        self.assertEqual(DescontoAprovado.objects.count(), 2)

    def test_a_tela_de_regras_salva_e_registra_o_antes_e_o_depois(self):
        dados = {
            "desconto_a_vista": "8,5", "desconto_no_debito": "0", "desconto_no_credito": "0",
            "parcelas_no_credito": "3", "folga": "1,00", "quem_autoriza": "Miranda, Henriett ou Edson",
            "meta_sabado": "12.000", "meta_domingo": "15.000,00", "premio": "30", "premio_a_mais": "10",
            "passo": "1.000", "outros_feriados": "16/02/2027 Carnaval",
        }
        resposta = self.client.post(reverse("caixa:regras_de_desconto"), dados)
        self.assertRedirects(resposta, reverse("caixa:descontos"), fetch_redirect_response=False)
        regra = RegraDeDesconto.atual()
        self.assertEqual(regra.desconto_a_vista, Decimal("8.5"))
        self.assertEqual(regra.meta_sabado, Decimal("12000"))
        self.assertEqual(regra.passo, Decimal("1000"))
        self.assertEqual(regra.atualizada_por, self.gerente)
        evento = EventoAuditoria.objects.get(acao="caixa.regras_de_desconto_mudadas")
        self.assertEqual(evento.antes["desconto_a_vista"], "7.00")
        self.assertEqual(evento.depois["desconto_a_vista"], "8.50")
        self.assertNotIn("meta_sabado", evento.depois)  # não mudou, não aparece

    def test_regra_errada_nao_salva(self):
        pagina = self.client.post(reverse("caixa:regras_de_desconto"), {
            "desconto_a_vista": "150", "desconto_no_debito": "0", "desconto_no_credito": "0",
            "parcelas_no_credito": "3", "folga": "1", "quem_autoriza": "Edson",
            "meta_sabado": "12000", "meta_domingo": "15000", "premio": "30", "premio_a_mais": "10",
            "passo": "1000", "outros_feriados": "31/02 dia que não existe",
        })
        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, "A porcentagem vai de 0 a 100.")
        self.assertContains(pagina, "Não entendi: 31/02 dia que não existe")
        self.assertEqual(RegraDeDesconto.atual().desconto_a_vista, Decimal("7.00"))
