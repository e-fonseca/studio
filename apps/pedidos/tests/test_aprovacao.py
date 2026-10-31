"""O pedido da Líder de loja espera a aprovação da gerência.

Pedido do Edson em 31/10/2026, com a Cássia entrando como líder de loja ("foco sera
compras de mercadorias"), e a descrição do cargo que ele mandou junto: *"Nenhuma compra é
confirmada sem aprovação prévia"* da Direção.
"""

from decimal import Decimal
from types import SimpleNamespace

from django.core.cache import cache
from django.urls import reverse

from apps.auditoria.models import EventoAuditoria
from apps.compras.models import DadosDaEmpresa
from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO, LIDER
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.painel import tarefas
from apps.pedidos import folha, servicos
from apps.pedidos.models import AnexoDoPedido, Pedido
from apps.pedidos.tests.test_pedidos import CORTE, BasePedido

AVISO = "ESPERANDO A APROVA".encode("cp1252")


def _corpo(relatorio):
    return relatorio.bytes() if hasattr(relatorio, "bytes") else bytes(relatorio)


class BaseAprovacao(BasePedido):
    def setUp(self):
        super().setUp()
        self.lider = usuario("cassia", LIDER)

    def pedido_da_lider(self):
        return servicos.registrar_pedido(self.lider, self.bloco(), data_corte=CORTE)

    def entrar_como(self, pessoa):
        self.client.login(username=pessoa.get_username(), password=SENHA_TESTE)


class NascimentoDoPedidoTest(BaseAprovacao):
    def test_o_pedido_da_lider_nasce_esperando_a_gerencia(self):
        pedido = self.pedido_da_lider()
        self.assertEqual(pedido.situacao, Pedido.Situacao.AGUARDANDO)
        self.assertTrue(pedido.esperando_aprovacao)
        self.assertIsNone(pedido.aprovado_em)
        self.assertIsNone(pedido.aprovado_por)

    def test_o_pedido_da_gerencia_nasce_valendo_e_aprovado_por_quem_fez(self):
        pedido = self.um_pedido()
        self.assertEqual(pedido.situacao, Pedido.Situacao.ABERTO)
        self.assertEqual(pedido.aprovado_por, self.gerente)
        self.assertEqual(pedido.aprovado_em, pedido.criado_em)
        self.assertFalse(pedido.aprovado_por_outra_pessoa)

    def test_sem_usuario_o_pedido_tambem_espera(self):
        """Nada vira pedido de verdade sem uma pessoa da gerência por trás."""
        pedido = servicos.registrar_pedido(None, self.bloco(), data_corte=CORTE)
        self.assertEqual(pedido.situacao, Pedido.Situacao.AGUARDANDO)

    def test_imprimir_duas_vezes_o_pedido_da_lider_nao_vira_dois(self):
        primeiro = self.pedido_da_lider()
        segundo = self.pedido_da_lider()
        self.assertEqual(primeiro.pk, segundo.pk)
        self.assertEqual(Pedido.objects.count(), 1)

    def test_a_folha_do_pedido_esperando_diz_no_alto_que_nao_vale(self):
        pedido = self.pedido_da_lider()
        corpo = _corpo(folha.montar(pedido, DadosDaEmpresa.atual()))
        self.assertIn(AVISO, corpo)
        self.assertIn("não mande ao fornecedor".encode("cp1252"), corpo)

    def test_a_folha_do_pedido_aprovado_sai_sem_o_aviso(self):
        pedido = self.um_pedido()
        corpo = _corpo(folha.montar(pedido, DadosDaEmpresa.atual()))
        self.assertNotIn(AVISO, corpo)

    def test_o_nome_do_arquivo_tambem_diz_que_espera(self):
        esperando = self.pedido_da_lider()
        self.assertEqual(folha.nome_do_arquivo(esperando),
                         f"pedido-{esperando.numero}-vime-lenzi-esperando-aprovacao.pdf")
        servicos.aprovar_pedido(self.gerente, esperando)
        self.assertEqual(folha.nome_do_arquivo(esperando), f"pedido-{esperando.numero}-vime-lenzi.pdf")


class AprovarPedidoTest(BaseAprovacao):
    def test_a_gerencia_aprova_e_o_pedido_passa_a_valer(self):
        pedido = self.pedido_da_lider()
        servicos.aprovar_pedido(self.gerente, pedido)
        pedido.refresh_from_db()
        self.assertEqual(pedido.situacao, Pedido.Situacao.ABERTO)
        self.assertEqual(pedido.aprovado_por, self.gerente)
        self.assertIsNotNone(pedido.aprovado_em)
        self.assertTrue(pedido.aprovado_por_outra_pessoa)
        evento = EventoAuditoria.objects.get(acao="pedido.aprovado")
        self.assertEqual(evento.usuario, self.gerente)
        self.assertEqual(evento.antes["situacao"], Pedido.Situacao.AGUARDANDO)

    def test_a_lider_nao_aprova_o_proprio_pedido(self):
        pedido = self.pedido_da_lider()
        with self.assertRaises(servicos.NaoDeuCerto):
            servicos.aprovar_pedido(self.lider, pedido)
        pedido.refresh_from_db()
        self.assertTrue(pedido.esperando_aprovacao)

    def test_pedido_que_ja_vale_nao_se_aprova_de_novo(self):
        pedido = self.um_pedido()
        with self.assertRaises(servicos.NaoDeuCerto):
            servicos.aprovar_pedido(self.gerente, pedido)

    def test_a_folha_aprovada_leva_quem_montou_e_quem_aprovou(self):
        pedido = self.pedido_da_lider()
        servicos.aprovar_pedido(self.gerente, pedido)
        pedido.refresh_from_db()
        self.assertEqual(folha.quem_emite(pedido, self.gerente), "Cassia, aprovado por Gerente")

    def test_pela_tela_aprovar_anexa_a_folha_que_vale(self):
        pedido = self.pedido_da_lider()
        anexos_antes = pedido.anexos.count()
        self.entrar_como(self.gerente)
        resposta = self.client.post(reverse("pedidos:aprovar", args=[pedido.numero]), follow=True)
        self.assertContains(resposta, f"Pedido {pedido.numero} aprovado.")
        pedido.refresh_from_db()
        self.assertTrue(pedido.esta_aberto)
        self.assertEqual(pedido.anexos.count(), anexos_antes + 1)
        folha_nova = pedido.anexos.filter(tipo=AnexoDoPedido.Tipo.PEDIDO).order_by("-pk").first()
        self.assertNotIn(AVISO, folha_nova.arquivo.open("rb").read())
        # A que esperava continua na lista de anexos, com o mesmo tipo: o nome é que separa.
        self.assertNotIn("esperando-aprovacao", folha_nova.nome_original)

    def test_a_lider_leva_403_no_endereco_de_aprovar(self):
        pedido = self.pedido_da_lider()
        self.entrar_como(self.lider)
        resposta = self.client.post(reverse("pedidos:aprovar", args=[pedido.numero]))
        self.assertEqual(resposta.status_code, 403)
        pedido.refresh_from_db()
        self.assertTrue(pedido.esperando_aprovacao)

    def test_aprovar_so_aceita_post(self):
        pedido = self.pedido_da_lider()
        self.entrar_como(self.gerente)
        self.assertEqual(self.client.get(reverse("pedidos:aprovar", args=[pedido.numero])).status_code, 405)


class MexerNoPedidoTest(BaseAprovacao):
    def test_a_lider_muda_a_quantidade_enquanto_espera(self):
        pedido = self.pedido_da_lider()
        codigo = pedido.itens.get().codigo
        _, mudou = servicos.editar_pedido(self.lider, pedido, quantidades={codigo: "3"})
        self.assertTrue(mudou)
        pedido.refresh_from_db()
        self.assertTrue(pedido.esperando_aprovacao)

    def test_depois_de_aprovado_a_lider_nao_muda_nem_cancela(self):
        pedido = self.pedido_da_lider()
        servicos.aprovar_pedido(self.gerente, pedido)
        pedido.refresh_from_db()
        codigo = pedido.itens.get().codigo
        with self.assertRaisesMessage(servicos.NaoDeuCerto, "só é mudado pela gerência"):
            servicos.editar_pedido(self.lider, pedido, quantidades={codigo: "3"})
        with self.assertRaisesMessage(servicos.NaoDeuCerto, "só é cancelado pela gerência"):
            servicos.cancelar_pedido(self.lider, pedido, "mudei de ideia")
        self.assertFalse(pedido.pode_ser_mudado_por(self.lider))
        self.assertTrue(pedido.pode_ser_mudado_por(self.gerente))

    def test_a_lider_desiste_do_proprio_pedido_com_motivo(self):
        pedido = self.pedido_da_lider()
        servicos.cancelar_pedido(self.lider, pedido, "fornecedor sem estoque")
        pedido.refresh_from_db()
        self.assertTrue(pedido.foi_cancelado)

    def test_a_gerencia_recusa_cancelando_com_o_motivo(self):
        pedido = self.pedido_da_lider()
        servicos.cancelar_pedido(self.gerente, pedido, "quantidade alta para o mês")
        pedido.refresh_from_db()
        self.assertTrue(pedido.foi_cancelado)
        self.assertEqual(pedido.motivo_cancelamento, "quantidade alta para o mês")

    def test_pedido_esperando_nao_e_dado_como_recebido(self):
        pedido = self.pedido_da_lider()
        with self.assertRaisesMessage(servicos.NaoDeuCerto, "ainda espera a aprovação"):
            servicos.marcar_recebido(self.gerente, pedido)
        with self.assertRaises(servicos.NaoDeuCerto):
            servicos.marcar_recebido(self.gerente, pedido, recebido=False)
        pedido.refresh_from_db()
        self.assertTrue(pedido.esperando_aprovacao)

    def test_o_administrativo_nao_mexe_em_pedido_nenhum(self):
        pedido = self.pedido_da_lider()
        self.assertFalse(pedido.pode_ser_mudado_por(usuario("ana", ADMINISTRATIVO)))


class TelaDaAprovacaoTest(BaseAprovacao):
    def test_a_gerencia_ve_o_botao_de_aprovar(self):
        pedido = self.pedido_da_lider()
        self.entrar_como(self.gerente)
        tela = self.client.get(reverse("pedidos:detalhe", args=[pedido.numero]))
        self.assertContains(tela, "Este pedido espera a sua aprovação.")
        self.assertContains(tela, reverse("pedidos:aprovar", args=[pedido.numero]))
        # Sem o botão de mercadoria chegou: pedido sem aprovação não se recebe.
        self.assertNotContains(tela, reverse("pedidos:receber", args=[pedido.numero]))

    def test_a_lider_ve_que_espera_e_pode_mudar_a_quantidade(self):
        pedido = self.pedido_da_lider()
        self.entrar_como(self.lider)
        tela = self.client.get(reverse("pedidos:detalhe", args=[pedido.numero]))
        self.assertContains(tela, "Esperando a aprovação da gerência.")
        self.assertNotContains(tela, reverse("pedidos:aprovar", args=[pedido.numero]))
        self.assertContains(tela, reverse("pedidos:editar", args=[pedido.numero]))

    def test_depois_de_aprovado_a_lider_nao_ve_o_campo_de_quantidade(self):
        pedido = self.pedido_da_lider()
        servicos.aprovar_pedido(self.gerente, pedido)
        self.entrar_como(self.lider)
        tela = self.client.get(reverse("pedidos:detalhe", args=[pedido.numero]))
        self.assertNotContains(tela, reverse("pedidos:editar", args=[pedido.numero]))
        self.assertContains(tela, "Aprovado em")

    def test_a_lista_conta_os_que_esperam_e_filtra_por_eles(self):
        self.pedido_da_lider()
        self.entrar_como(self.gerente)
        tela = self.client.get(reverse("pedidos:lista"))
        self.assertContains(tela, "esperando a aprovação da gerência")
        filtrada = self.client.get(reverse("pedidos:lista") + "?situacao=aguardando")
        self.assertEqual(filtrada.context["quantos"], 1)

    def test_a_lider_gera_pela_tela_e_o_recado_diz_que_espera(self):
        self.entrar_como(self.lider)
        resposta = self.client.post(reverse("pedidos:gerar"), {"fornecedor": "VIME LENZI"},
                                    follow=True)
        self.assertContains(resposta, "esperando a aprovação da gerência")
        pedido = Pedido.objects.get()
        self.assertTrue(pedido.esperando_aprovacao)
        guardada = pedido.anexos.get(tipo=AnexoDoPedido.Tipo.PEDIDO)
        self.assertIn(AVISO, guardada.arquivo.open("rb").read())
        self.assertTrue(guardada.nome_original.endswith("-esperando-aprovacao.pdf"))

    def test_a_folha_que_a_lider_leva_da_lista_de_compra_tem_o_aviso(self):
        self.entrar_como(self.lider)
        resposta = self.client.post(reverse("compras:pedido_ao_fornecedor") + "?fornecedor=VIME+LENZI")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn(AVISO, b"".join(resposta.streaming_content) if resposta.streaming
                      else resposta.content)
        self.assertIn("-esperando-aprovacao.pdf", resposta["Content-Disposition"])
        self.assertTrue(Pedido.objects.get().esperando_aprovacao)

    def test_a_folha_que_a_gerencia_leva_da_lista_de_compra_nao_tem_aviso(self):
        self.entrar_como(self.gerente)
        resposta = self.client.post(reverse("compras:pedido_ao_fornecedor") + "?fornecedor=VIME+LENZI")
        self.assertNotIn(AVISO, b"".join(resposta.streaming_content) if resposta.streaming
                         else resposta.content)
        self.assertNotIn("esperando-aprovacao", resposta["Content-Disposition"])
        self.assertTrue(Pedido.objects.get().esta_aberto)


class AgendaDaAprovacaoTest(BaseAprovacao):
    def test_a_gerencia_recebe_a_tarefa_de_aprovar(self):
        pedido = self.pedido_da_lider()
        agenda = tarefas.montar(None, usuario=self.gerente)
        tarefa = next(t for t in agenda.tarefas if t.chave == "aprovar")
        self.assertEqual(tarefa.titulo, "Aprovar os pedidos da loja")
        self.assertIn("1 pedido montado na loja", tarefa.detalhe)
        self.assertIn(tarefas._reais(pedido.valor_total), tarefa.detalhe)
        self.assertEqual(tarefa.endereco, reverse("pedidos:lista") + "?situacao=aguardando")

    def test_vem_antes_das_outras_de_atencao(self):
        # Sem isto a tarefa ficava no fim da fila, entre as que "não cabem aqui".
        self.pedido_da_lider()
        semana = SimpleNamespace(vencidas=SimpleNamespace(quantidade=0, valor=Decimal("0")),
                                 por_faixa=[{"dias": 7, "valor": Decimal("100")}])
        agenda = tarefas.montar(None, resumo_financeiro=semana, usuario=self.gerente)
        chaves = [t.chave for t in agenda.tarefas]
        self.assertLess(chaves.index("aprovar"), chaves.index("prestes"))
        self.assertIn("aprovar", [t.chave for t in agenda.primeiras])

    def test_a_lider_nao_recebe_a_tarefa_de_aprovar(self):
        self.pedido_da_lider()
        agenda = tarefas.montar(None, usuario=self.lider)
        self.assertNotIn("aprovar", [t.chave for t in agenda.tarefas])

    def test_sem_pedido_esperando_nao_ha_tarefa(self):
        self.um_pedido()
        agenda = tarefas.montar(None, usuario=self.gerente)
        self.assertNotIn("aprovar", [t.chave for t in agenda.tarefas])

    def test_aprovado_o_pedido_a_tarefa_some(self):
        pedido = self.pedido_da_lider()
        servicos.aprovar_pedido(self.gerente, pedido)
        agenda = tarefas.montar(None, usuario=self.gerente)
        self.assertNotIn("aprovar", [t.chave for t in agenda.tarefas])


class AgendaGuardadaTest(BaseAprovacao):
    """A Visão geral guarda a agenda até a próxima importação; o pedido não espera por ela."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.client.login(username="gerente", password=SENHA_TESTE)

    def tearDown(self):
        cache.clear()

    def test_o_pedido_novo_aparece_sem_importacao_nova(self):
        self.assertNotContains(self.client.get(reverse("painel:geral")), "Aprovar os pedidos da loja")
        self.pedido_da_lider()
        self.assertContains(self.client.get(reverse("painel:geral")), "Aprovar os pedidos da loja")

    def test_aprovado_sai_da_visao_geral_na_hora(self):
        pedido = self.pedido_da_lider()
        self.assertContains(self.client.get(reverse("painel:geral")), "Aprovar os pedidos da loja")
        servicos.aprovar_pedido(self.gerente, pedido)
        self.assertNotContains(self.client.get(reverse("painel:geral")), "Aprovar os pedidos da loja")
