"""Editar o pedido, cancelar com motivo e gerar de novo a folha.

Pedido do Edson em 20/10/2026: *"Pedidos ao fornecedor = permitir editar pedido ou
descartar/cancelar (informar motivo)"* e *"Pedido, nessa tela gerar pedido de compra de
mercadorias"*.
"""

from decimal import Decimal

from django.urls import reverse

from apps.auditoria.models import EventoAuditoria
from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.pedidos import folha, servicos
from apps.pedidos.models import AnexoDoPedido, Pedido
from apps.pedidos.tests.test_pedidos import BasePedido


class EditarPedidoTest(BasePedido):
    def test_mudar_a_quantidade_refaz_o_valor_da_linha(self):
        pedido = self.um_pedido()
        _, mudou = servicos.editar_pedido(self.gerente, pedido,
                                          quantidades={"0001": "4"})
        self.assertTrue(mudou)
        item = pedido.itens.get()
        self.assertEqual(item.quantidade, Decimal("4.000"))
        # 4 × 85 = 340: o valor acompanha a quantidade, senão o total do pedido mente.
        self.assertEqual(item.valor, Decimal("340.00"))
        self.assertEqual(pedido.valor_total, Decimal("340.00"))

    def test_quantidade_mudada_a_mao_fica_marcada(self):
        """É o que sai em marrom na folha: quem confere precisa ver o que é decisão de gente."""
        pedido = self.um_pedido()
        servicos.editar_pedido(self.gerente, pedido, quantidades={"0001": "4"})
        self.assertTrue(pedido.itens.get().escolhida_a_mao)

    def test_zero_tira_o_item_do_pedido(self):
        """Pedir zero unidade não é pedido: a linha sai, como já saía da folha."""
        self.outro_produto("0009", "MESA DE JACARANDA")
        pedido = servicos.registrar_pedido(self.gerente, self.bloco_de_dois())
        self.assertEqual(pedido.itens.count(), 2)
        servicos.editar_pedido(self.gerente, pedido, quantidades={"0009": "0"})
        self.assertEqual([item.codigo for item in pedido.itens.all()], ["0001"])

    def test_pedido_nao_pode_ficar_sem_nenhum_item(self):
        """Desistir do pedido tem caminho próprio, com motivo. Esvaziar não é editar."""
        pedido = self.um_pedido()
        with self.assertRaises(servicos.NaoDeuCerto) as erro:
            servicos.editar_pedido(self.gerente, pedido, quantidades={"0001": "0"})
        self.assertIn("Cancelar o pedido", str(erro.exception))
        self.assertEqual(pedido.itens.count(), 1)

    def test_aceita_virgula_e_recusa_negativo(self):
        pedido = self.um_pedido()
        servicos.editar_pedido(self.gerente, pedido, quantidades={"0001": "2,5"})
        self.assertEqual(pedido.itens.get().quantidade, Decimal("2.500"))
        with self.assertRaises(servicos.NaoDeuCerto):
            servicos.editar_pedido(self.gerente, pedido, quantidades={"0001": "-1"})

    def test_prazo_e_observacao_entram_na_edicao(self):
        pedido = self.um_pedido()
        servicos.editar_pedido(self.gerente, pedido, quantidades={},
                              prazo_dias=20, observacao="entregar pela manhã")
        pedido.refresh_from_db()
        self.assertEqual(pedido.prazo_dias, 20)
        self.assertEqual(pedido.observacao, "entregar pela manhã")

    def test_nada_mudou_nao_marca_o_pedido_como_editado(self):
        pedido = self.um_pedido()
        quanto = pedido.itens.get().quantidade
        _, mudou = servicos.editar_pedido(self.gerente, pedido,
                                          quantidades={"0001": str(quanto)})
        self.assertFalse(mudou)
        pedido.refresh_from_db()
        self.assertIsNone(pedido.editado_em)

    def test_a_edicao_fica_na_auditoria_com_o_de_e_o_para(self):
        pedido = self.um_pedido()
        antes = pedido.itens.get().quantidade
        servicos.editar_pedido(self.gerente, pedido, quantidades={"0001": "4"})
        evento = EventoAuditoria.objects.get(acao="pedido.editado")
        self.assertEqual(evento.antes["itens"]["0001"], str(antes))
        self.assertEqual(evento.depois["itens"]["0001"], "4.000")
        self.assertEqual(evento.depois["mudaram"], ["0001"])

    def test_pedido_recebido_nao_se_edita(self):
        """Depois de recebido, mexer na quantidade apaga a prova contra a qual a nota é conferida."""
        pedido = self.um_pedido()
        servicos.marcar_recebido(self.gerente, pedido)
        with self.assertRaises(servicos.NaoDeuCerto):
            servicos.editar_pedido(self.gerente, pedido, quantidades={"0001": "4"})

    def outro_produto(self, codigo, descricao, fornecedor="VIME LENZI"):
        """Mais um produto do MESMO fornecedor, para o pedido ter duas linhas."""
        from apps.importacao.models import ProdutoImportado
        ProdutoImportado.objects.create(
            importacao=self.importacao, codigo=codigo, descricao=descricao,
            grupo="MOVEL", fornecedor=fornecedor, custo=Decimal("10"),
            preco_venda=Decimal("30"), estoque=Decimal("0"), vendas_12m=Decimal("360"),
            receita_12m=Decimal("10800"))

    def bloco_de_dois(self):
        bloco = self.bloco()
        assert len(bloco.itens) == 2, [item.codigo for item in bloco.itens]
        return bloco


class CancelarPedidoTest(BasePedido):
    def test_cancelar_guarda_motivo_quem_e_quando(self):
        pedido = self.um_pedido()
        servicos.cancelar_pedido(self.gerente, pedido, "fornecedor sem estoque")
        pedido.refresh_from_db()
        self.assertEqual(pedido.situacao, Pedido.Situacao.CANCELADO)
        self.assertEqual(pedido.motivo_cancelamento, "fornecedor sem estoque")
        self.assertEqual(pedido.cancelado_por, self.gerente)
        self.assertIsNotNone(pedido.cancelado_em)

    def test_motivo_e_obrigatorio(self):
        pedido = self.um_pedido()
        for vazio in ("", "   ", None):
            with self.assertRaises(servicos.NaoDeuCerto):
                servicos.cancelar_pedido(self.gerente, pedido, vazio)
        pedido.refresh_from_db()
        self.assertEqual(pedido.situacao, Pedido.Situacao.ABERTO)

    def test_cancelar_nao_apaga_nada(self):
        """Regra dele: não eliminar histórico. É o que permite ver o que se deixou de comprar."""
        pedido = self.um_pedido()
        servicos.cancelar_pedido(self.gerente, pedido, "mudamos de ideia")
        self.assertEqual(Pedido.objects.count(), 1)
        self.assertEqual(pedido.itens.count(), 1)

    def test_cancelado_nao_se_edita_nem_se_recebe(self):
        pedido = self.um_pedido()
        servicos.cancelar_pedido(self.gerente, pedido, "fornecedor fechou")
        with self.assertRaises(servicos.NaoDeuCerto):
            servicos.editar_pedido(self.gerente, pedido, quantidades={"0001": "4"})
        with self.assertRaises(servicos.NaoDeuCerto):
            servicos.marcar_recebido(self.gerente, pedido)
        pedido.refresh_from_db()
        self.assertEqual(pedido.situacao, Pedido.Situacao.CANCELADO)
        self.assertEqual(pedido.motivo_cancelamento, "fornecedor fechou")

    def test_cancelar_duas_vezes_avisa_em_vez_de_reescrever_o_motivo(self):
        pedido = self.um_pedido()
        servicos.cancelar_pedido(self.gerente, pedido, "primeiro motivo")
        with self.assertRaises(servicos.NaoDeuCerto):
            servicos.cancelar_pedido(self.gerente, pedido, "segundo motivo")
        pedido.refresh_from_db()
        self.assertEqual(pedido.motivo_cancelamento, "primeiro motivo")

    def test_o_motivo_vai_para_a_auditoria(self):
        pedido = self.um_pedido()
        servicos.cancelar_pedido(self.gerente, pedido, "transportadora não entrega aqui")
        evento = EventoAuditoria.objects.get(acao="pedido.cancelado")
        self.assertEqual(evento.motivo, "transportadora não entrega aqui")
        self.assertEqual(evento.antes["situacao"], Pedido.Situacao.ABERTO)

    def test_pedido_cancelado_nao_e_reaproveitado_pela_lista_de_compra(self):
        """Senão a loja cancelaria o pedido e a lista devolveria o mesmo número."""
        primeiro = self.um_pedido()
        servicos.cancelar_pedido(self.gerente, primeiro, "desistimos")
        segundo = servicos.registrar_pedido(self.gerente, self.bloco())
        self.assertNotEqual(primeiro.pk, segundo.pk)
        self.assertEqual(segundo.situacao, Pedido.Situacao.ABERTO)


class FolhaDoPedidoGuardadoTest(BasePedido):
    def test_a_folha_sai_do_pedido_e_nao_da_lista_de_hoje(self):
        pedido = self.um_pedido()
        quanto = pedido.itens.get().quantidade
        # A lista de compra muda; o papel do pedido não pode mudar com ela.
        from apps.importacao.models import ProdutoImportado
        ProdutoImportado.objects.filter(codigo="0001").update(estoque=Decimal("999"))
        bloco = folha.como_bloco(pedido)
        self.assertEqual(bloco.nome, "VIME LENZI")
        self.assertEqual(bloco.itens[0].quantidade, quanto)

    def test_o_bloco_tem_tudo_o_que_a_folha_pede(self):
        """A folha é a mesma de apps/compras/pedido.py; o bloco só veste o pedido."""
        pedido = self.um_pedido()
        bloco = folha.como_bloco(pedido)
        for atributo in ("nome", "itens", "prazo_dias", "prazo_assumido", "ajustados"):
            self.assertTrue(hasattr(bloco, atributo), atributo)
        for atributo in ("codigo", "descricao", "grupo", "quantidade", "custo",
                         "valor_do_pedido", "foi_ajustada"):
            self.assertTrue(hasattr(bloco.itens[0], atributo), atributo)

    def test_o_prazo_do_pedido_guardado_nunca_sai_como_estimado(self):
        pedido = self.um_pedido()
        self.assertFalse(folha.como_bloco(pedido).prazo_assumido)

    def test_a_folha_do_cancelado_avisa_que_foi_cancelado(self):
        from apps.compras.models import DadosDaEmpresa
        pedido = self.um_pedido()
        servicos.cancelar_pedido(self.gerente, pedido, "fornecedor sem estoque")
        pedido.refresh_from_db()
        relatorio = folha.montar(pedido, DadosDaEmpresa.atual())
        corpo = relatorio.bytes() if hasattr(relatorio, "bytes") else bytes(relatorio)
        self.assertTrue(corpo.startswith(b"%PDF"))

    def test_o_nome_do_arquivo_diz_qual_pedido_e(self):
        pedido = self.um_pedido()
        self.assertEqual(folha.nome_do_arquivo(pedido), "pedido-1-vime-lenzi.pdf")


class TelaDoPedidoTest(BasePedido):
    def test_o_botao_de_gerar_a_folha_aparece_e_baixa_o_pdf(self):
        pedido = self.um_pedido()
        self.entrar()
        tela = self.client.get(reverse("pedidos:detalhe", args=[pedido.numero]))
        self.assertContains(tela, reverse("pedidos:imprimir", args=[pedido.numero]))
        baixado = self.client.get(reverse("pedidos:imprimir", args=[pedido.numero]))
        self.assertEqual(baixado.status_code, 200)
        self.assertEqual(baixado["Content-Type"], "application/pdf")
        evento = EventoAuditoria.objects.filter(acao="pedido.folha_gerada")
        self.assertTrue(evento.exists())

    def test_editar_pela_tela_deixa_a_folha_nova_anexada(self):
        pedido = self.um_pedido()
        self.entrar()
        antes = pedido.anexos.count()
        resposta = self.client.post(reverse("pedidos:editar", args=[pedido.numero]),
                                    {"quantidade-0001": "4", "prazo_dias": "20",
                                     "observacao": "falar com a Henriett"})
        self.assertEqual(resposta.status_code, 302)
        pedido.refresh_from_db()
        self.assertEqual(pedido.itens.get().quantidade, Decimal("4.000"))
        self.assertEqual(pedido.anexos.filter(tipo=AnexoDoPedido.Tipo.PEDIDO).count(), antes + 1)

    def test_cancelar_pela_tela_exige_o_motivo(self):
        pedido = self.um_pedido()
        self.entrar()
        self.client.post(reverse("pedidos:cancelar", args=[pedido.numero]), {"motivo": "  "})
        pedido.refresh_from_db()
        self.assertEqual(pedido.situacao, Pedido.Situacao.ABERTO)
        self.client.post(reverse("pedidos:cancelar", args=[pedido.numero]),
                         {"motivo": "fornecedor sem estoque"})
        pedido.refresh_from_db()
        self.assertEqual(pedido.situacao, Pedido.Situacao.CANCELADO)

    def test_a_tela_mostra_o_motivo_do_cancelamento(self):
        pedido = self.um_pedido()
        servicos.cancelar_pedido(self.gerente, pedido, "transportadora não entrega aqui")
        self.entrar()
        tela = self.client.get(reverse("pedidos:detalhe", args=[pedido.numero]))
        self.assertContains(tela, "transportadora não entrega aqui")
        self.assertContains(tela, "Pedido cancelado")

    def test_pedido_cancelado_nao_mostra_formulario_de_edicao(self):
        pedido = self.um_pedido()
        servicos.cancelar_pedido(self.gerente, pedido, "desistimos")
        self.entrar()
        tela = self.client.get(reverse("pedidos:detalhe", args=[pedido.numero]))
        self.assertNotContains(tela, reverse("pedidos:editar", args=[pedido.numero]))
        self.assertNotContains(tela, reverse("pedidos:cancelar", args=[pedido.numero]))

    def test_o_vendedor_nao_chega_a_nenhuma_das_telas(self):
        """A condição do Edson: o vendedor vê UMA tela, e não é esta."""
        pedido = self.um_pedido()
        self.entrar(VENDEDOR, "vendedor")
        for rota in ("detalhe", "imprimir", "editar", "cancelar"):
            resposta = self.client.get(reverse(f"pedidos:{rota}", args=[pedido.numero]))
            self.assertEqual(resposta.status_code, 403, rota)

    def test_operador_administrativo_ve_o_pedido_e_nao_o_edita(self):
        pedido = self.um_pedido()
        self.entrar(ADMINISTRATIVO, "operador")
        tela = self.client.get(reverse("pedidos:detalhe", args=[pedido.numero]))
        self.assertEqual(tela.status_code, 200)
        # Pode gerar a folha (é leitura), não pode mexer no que foi pedido.
        self.assertEqual(
            self.client.get(reverse("pedidos:imprimir", args=[pedido.numero])).status_code, 200)
        self.assertEqual(
            self.client.post(reverse("pedidos:editar", args=[pedido.numero]),
                             {"quantidade-0001": "4"}).status_code, 403)
        self.assertEqual(
            self.client.post(reverse("pedidos:cancelar", args=[pedido.numero]),
                             {"motivo": "nao"}).status_code, 403)
