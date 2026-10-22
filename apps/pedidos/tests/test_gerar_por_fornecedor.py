"""Gerar o pedido de cada fornecedor pela tela de Pedidos.

Pedido dele em 20/10/2026: *"na tela pedidos, gerar automaticamente pedidos de compra
mercadorias por fornecedor, com a quantidade sugerida pelo formula informada
anteriormente aqui"*. E, no mesmo prompt, a regra que limita o "automaticamente":
*"Não aprovar nem emitir pedidos automaticamente"*.
"""

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.auditoria.models import EventoAuditoria
from apps.compras import ajustes
from apps.contas.perfis import ADMINISTRATIVO, VENDEDOR
from apps.importacao.models import ProdutoImportado
from apps.pedidos import geracao
from apps.pedidos.models import AnexoDoPedido, Pedido
from apps.pedidos.tests.test_pedidos import CORTE, BasePedido


class BaseGerar(BasePedido):
    def outro_produto(self, codigo="0009", fornecedor="GERMAN", **campos):
        padrao = dict(
            importacao=self.importacao, codigo=codigo, descricao=f"PRODUTO {codigo}",
            grupo="TAPETE", fornecedor=fornecedor, custo=Decimal("10"),
            preco_venda=Decimal("30"), estoque=Decimal("0"), vendas_12m=Decimal("360"),
            receita_12m=Decimal("10800"),
        )
        padrao.update(campos)
        return ProdutoImportado.objects.create(**padrao)


class OQueATelaPrevê(BaseGerar):
    def test_um_previsto_por_fornecedor_com_itens_unidades_e_valor(self):
        self.outro_produto()
        previstos, lista = geracao.previstos(self.importacao)
        self.assertEqual({p.nome for p in previstos}, {"VIME LENZI", "GERMAN"})
        for previsto in previstos:
            with self.subTest(fornecedor=previsto.nome):
                self.assertEqual(previsto.quantos, 1)
                self.assertGreater(previsto.unidades, 0)
                self.assertGreater(previsto.valor, 0)
                self.assertFalse(previsto.ja_foi_pedido)

    def test_o_previsto_usa_a_soma_da_sugerida_com_a_da_mao(self):
        """É a conta dele de 20/10/2026: o que vai no pedido é a soma das duas parcelas."""
        antes, _ = geracao.previstos(self.importacao)
        sugerida = antes[0].unidades
        ajustes.salvar(codigo="0001", a_mais="5", sugerida=sugerida)
        depois, _ = geracao.previstos(self.importacao)
        self.assertEqual(depois[0].unidades, sugerida + 5)
        self.assertEqual(depois[0].ajustados, 1)

    def test_fornecedor_marcado_para_nao_comprar_sai_da_previsao(self):
        """Pedido sem linha nenhuma não é pedido, e um botão que não faz nada confunde."""
        _, lista = geracao.previstos(self.importacao)
        ajustes.salvar(codigo="0001", a_mais="", sugerida=lista.fornecedores[0].valor,
                       nao_comprar=True)
        previstos, _ = geracao.previstos(self.importacao)
        self.assertEqual(previstos, [])

    def test_produto_sem_fornecedor_nao_vira_pedido(self):
        """Não há a quem mandar a folha; o cadastro se conserta na lista de compra."""
        self.outro_produto(codigo="0010", fornecedor="")
        previstos, _ = geracao.previstos(self.importacao)
        self.assertEqual({p.nome for p in previstos}, {"VIME LENZI"})

    def test_quem_passa_do_teto_do_mes_aparece_marcado_e_no_fim(self):
        """O teto é informação, não trava: "Não ultrapassar o orçamento sem autorização"."""
        from apps.compras import limite

        self.outro_produto()
        teto = limite.Teto(mensal=Decimal("100"), sobra=Decimal("100"))
        previstos, _ = geracao.previstos(self.importacao, teto=teto)
        self.assertTrue(previstos[0].cabe_no_mes)
        self.assertFalse(previstos[-1].cabe_no_mes)

    def test_pedido_feito_hoje_aparece_como_feito_em_vez_de_botao(self):
        pedido = self.um_pedido()
        previstos, _ = geracao.previstos(self.importacao)
        previsto = geracao.um(previstos, "VIME LENZI")
        self.assertTrue(previsto.ja_foi_pedido)
        self.assertEqual(previsto.ja_pedido.pk, pedido.pk)


class ATelaDosPedidos(BaseGerar):
    def setUp(self):
        super().setUp()
        self.entrar()

    def test_a_tela_mostra_o_quadro_de_gerar_com_o_fornecedor(self):
        corpo = self.client.get(reverse("pedidos:lista")).content.decode()
        self.assertIn("Gerar os pedidos de hoje", corpo)
        self.assertIn("VIME LENZI", corpo)
        self.assertIn("Gerar o pedido", corpo)

    def test_gerar_grava_o_pedido_com_a_folha_anexada(self):
        resposta = self.client.post(reverse("pedidos:gerar"), {"fornecedor": "VIME LENZI"})
        pedido = Pedido.objects.get()
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("pedidos:detalhe", args=[pedido.numero]), resposta["Location"])
        self.assertEqual(pedido.fornecedor, "VIME LENZI")
        self.assertEqual(pedido.data_corte, CORTE)
        self.assertEqual(pedido.anexos.get().tipo, AnexoDoPedido.Tipo.PEDIDO)

    def test_a_folha_anexada_e_a_do_proprio_fornecedor(self):
        """Anexar o maço inteiro a cada pedido é erro que só aparece quando a carga chega."""
        self.outro_produto()
        self.client.post(reverse("pedidos:gerar"))
        for pedido in Pedido.objects.all():
            with self.subTest(fornecedor=pedido.fornecedor):
                folha = pedido.anexos.get()
                self.assertIn(pedido.fornecedor.lower().replace(" ", "-"),
                              folha.nome_original)

    def test_gerar_todos_faz_um_pedido_por_fornecedor(self):
        self.outro_produto()
        self.client.post(reverse("pedidos:gerar"))
        self.assertEqual(Pedido.objects.count(), 2)
        self.assertEqual({p.fornecedor for p in Pedido.objects.all()},
                         {"VIME LENZI", "GERMAN"})

    def test_gerar_de_novo_no_mesmo_dia_nao_duplica(self):
        """Reaproveita o pedido de hoje: a nota do fornecedor conferiria contra o dobro."""
        self.client.post(reverse("pedidos:gerar"), {"fornecedor": "VIME LENZI"})
        self.client.post(reverse("pedidos:gerar"), {"fornecedor": "VIME LENZI"})
        self.assertEqual(Pedido.objects.count(), 1)

    def test_fornecedor_que_saiu_da_lista_volta_com_recado(self):
        resposta = self.client.post(reverse("pedidos:gerar"),
                                    {"fornecedor": "QUEM NAO EXISTE"}, follow=True)
        self.assertFalse(Pedido.objects.exists())
        self.assertContains(resposta, "não está mais na lista de compra de hoje")

    def test_fica_na_trilha_de_auditoria(self):
        self.client.post(reverse("pedidos:gerar"), {"fornecedor": "VIME LENZI"})
        evento = EventoAuditoria.objects.filter(acao="pedido.gerado_da_tela").first()
        self.assertIsNotNone(evento)
        self.assertEqual(evento.depois["guardados"], 1)
        self.assertEqual(evento.depois["numeros"], [1])

    def test_so_aceita_post(self):
        self.assertEqual(self.client.get(reverse("pedidos:gerar")).status_code, 405)


class QuemPodeGerar(BaseGerar):
    def test_o_administrativo_ve_a_tela_e_nao_o_botao(self):
        """Campo ou botão que recusa o clique é promessa quebrada na cara de quem clicou."""
        self.entrar(perfil=ADMINISTRATIVO, nome="administrativa")
        corpo = self.client.get(reverse("pedidos:lista")).content.decode()
        self.assertIn("VIME LENZI", corpo)
        self.assertNotIn("Gerar o pedido", corpo)

    def test_o_administrativo_nao_gera_pelo_endereco(self):
        self.entrar(perfil=ADMINISTRATIVO, nome="administrativa2")
        resposta = self.client.post(reverse("pedidos:gerar"), {"fornecedor": "VIME LENZI"})
        self.assertEqual(resposta.status_code, 403)
        self.assertFalse(Pedido.objects.exists())

    def test_o_vendedor_nao_entra_na_tela(self):
        self.entrar(perfil=VENDEDOR, nome="vendedor")
        self.assertEqual(self.client.get(reverse("pedidos:lista")).status_code, 403)
        self.assertEqual(self.client.post(reverse("pedidos:gerar")).status_code, 403)
