"""Confrontar o extrato com as contas pagas, e registrar quem conferiu o quê."""

from datetime import date, timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import EventoAuditoria
from apps.conciliacao import conferencia, servicos
from apps.conciliacao.models import ExtratoImportado, LinhaExtrato
from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.financeiro.models import Lancamento
from apps.importacao.models import Importacao

DIA = date(2026, 9, 15)


def _ofx(movimentos):
    linhas = "".join(
        f"<STMTTRN><DTPOSTED>{quando:%Y%m%d}<TRNAMT>{valor}<FITID>{i}<MEMO>{memo}</STMTTRN>"
        for i, (quando, valor, memo) in enumerate(movimentos, start=1)
    )
    return ("OFXHEADER:100\n<OFX><SIGNONMSGSRSV1><SONRS><FI><ORG>Banco Teste</FI></SONRS>"
            "</SIGNONMSGSRSV1><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKTRANLIST>"
            + linhas + "</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>")


def _arquivo(conteudo, nome="extrato.ofx"):
    return SimpleUploadedFile(nome, conteudo.encode("cp1252"), content_type="text/plain")


class BaseConciliacao(TestCase):
    def setUp(self):
        self.importacao = Importacao.objects.create(
            situacao=Importacao.Situacao.CONCLUIDA, data_corte=DIA)
        self.gerente = usuario("gerente_banco", ADMINISTRACAO)
        self.conta = self._conta(1001, "Pedido de Compra 000314", "QUITÉRIA FLOR MILHO",
                                 Decimal("1362.00"), DIA)

    def _conta(self, id_set, descricao, quem, valor, pagamento, importacao=None):
        return Lancamento.objects.create(
            importacao=importacao or self.importacao, tipo=Lancamento.Tipo.PAGAR,
            id_set=id_set, descricao=descricao, contraparte=quem, valor=valor,
            valor_pago=valor, vencimento=pagamento, pagamento=pagamento,
        )

    def _extrato(self, movimentos, nome="extrato.ofx"):
        return servicos.importar(_arquivo(_ofx(movimentos), nome), self.gerente)


class AcharAConta(BaseConciliacao):
    def test_mesmo_valor_e_data_perto_e_a_conta_certa(self):
        extrato = self._extrato([(DIA, "-1362.00", "PIX QUITERIA FLOR MILHO")])
        confrontos = conferencia.confrontar(extrato, self.importacao)
        self.assertEqual(confrontos[0].situacao, "uma")
        self.assertEqual(confrontos[0].unica.conta, self.conta)

    def test_valor_diferente_por_um_centavo_nao_e_a_mesma_conta(self):
        """Aproximar valor num confronto de dinheiro seria inventar."""
        extrato = self._extrato([(DIA, "-1362.01", "PIX QUITERIA")])
        self.assertEqual(conferencia.confrontar(extrato, self.importacao)[0].situacao, "nenhuma")

    def test_data_longe_demais_fica_de_fora(self):
        longe = DIA + timedelta(days=conferencia.DIAS_DE_FOLGA + 1)
        extrato = self._extrato([(longe, "-1362.00", "PIX QUITERIA")])
        self.assertEqual(conferencia.confrontar(extrato, self.importacao)[0].situacao, "nenhuma")

    def test_o_banco_baixa_no_dia_seguinte_e_continua_sendo_a_mesma_conta(self):
        extrato = self._extrato([(DIA - timedelta(days=1), "-1362.00", "PIX QUITERIA")])
        self.assertEqual(conferencia.confrontar(extrato, self.importacao)[0].situacao, "uma")

    def test_duas_contas_do_mesmo_valor_viram_escolha_e_o_nome_desempata(self):
        outra = self._conta(1002, "Pedido de Compra 000999", "MINAS ARTES",
                            Decimal("1362.00"), DIA)
        extrato = self._extrato([(DIA, "-1362.00", "PIX ENVIADO QUITERIA FLOR MILHO")])
        confronto = conferencia.confrontar(extrato, self.importacao)[0]
        self.assertEqual(confronto.situacao, "varias")
        self.assertEqual(len(confronto.candidatas), 2)
        # A primeira é a que o nome do banco aponta, mesmo com a outra no mesmo dia.
        self.assertEqual(confronto.candidatas[0].conta, self.conta)
        self.assertIn(outra, [c.conta for c in confronto.candidatas])

    def test_entrada_de_dinheiro_fica_fora_do_confronto(self):
        """Crédito é venda e cartão: conta a pagar não tem nada a ver com ele."""
        extrato = self._extrato([(DIA, "5000.00", "CREDITO CIELO")])
        confronto = conferencia.confrontar(extrato, self.importacao)[0]
        self.assertEqual(confronto.situacao, "entrada")
        self.assertEqual(confronto.candidatas, [])

    def test_conta_em_aberto_no_set_nao_e_candidata(self):
        """O banco confirma o que foi pago; conta não baixada não pode casar."""
        Lancamento.objects.filter(pk=self.conta.pk).update(pagamento=None)
        extrato = self._extrato([(DIA, "-1362.00", "PIX QUITERIA")])
        self.assertEqual(conferencia.confrontar(extrato, self.importacao)[0].situacao, "nenhuma")

    def test_conta_ja_marcada_em_outra_linha_aparece_avisada(self):
        extrato = self._extrato([(DIA, "-1362.00", "PIX QUITERIA"),
                                 (DIA, "-1362.00", "PIX QUITERIA DE NOVO")])
        primeira, segunda = extrato.linhas.all()
        servicos.conferir(primeira, self.conta.id_set, self.gerente, self.importacao)
        confronto = conferencia.confrontar(extrato, self.importacao)[1]
        self.assertEqual(confronto.situacao, "uma")
        self.assertTrue(confronto.candidatas[0].ja_usada)

    def test_parecencia_ignora_as_palavras_que_todo_banco_escreve(self):
        """'PIX', 'TED' e 'LTDA' aparecem em tudo e não identificam ninguém."""
        self.assertEqual(conferencia.parecencia("PIX TED PAGAMENTO LTDA", "COMERCIO LTDA"), 0)
        self.assertGreater(conferencia.parecencia("PIX ENVIADO MINAS ARTES", "MINAS ARTES"), 0.9)
        self.assertEqual(conferencia.parecencia("PIX QUITERIA", "QUITÉRIA"), 1.0)


class ImportarOExtrato(BaseConciliacao):
    def test_guarda_o_arquivo_com_banco_periodo_e_linhas(self):
        extrato = self._extrato([(DIA, "-1362.00", "PIX QUITERIA"),
                                 (DIA + timedelta(days=2), "5000.00", "CREDITO")])
        self.assertEqual(extrato.banco, "Banco Teste")
        self.assertEqual(extrato.formato, "ofx")
        self.assertEqual(extrato.periodo_inicio, DIA)
        self.assertEqual(extrato.periodo_fim, DIA + timedelta(days=2))
        self.assertEqual(extrato.linhas.count(), 2)
        self.assertEqual(extrato.importado_por, self.gerente)

    def test_o_mesmo_arquivo_duas_vezes_e_recusado_mesmo_renomeado(self):
        """Importar de novo dobraria o extrato e cada saída contaria duas vezes."""
        movimentos = [(DIA, "-1362.00", "PIX QUITERIA")]
        self._extrato(movimentos)
        with self.assertRaises(servicos.ExtratoRecusado) as recusa:
            self._extrato(movimentos, nome="outro-nome.ofx")
        self.assertIn("já foi importado", str(recusa.exception))

    def test_arquivo_vazio_e_arquivo_sem_movimento_sao_recusados_com_explicacao(self):
        with self.assertRaises(servicos.ExtratoRecusado):
            servicos.importar(SimpleUploadedFile("x.ofx", b""), self.gerente)
        with self.assertRaises(servicos.ExtratoRecusado) as recusa:
            servicos.importar(_arquivo("nada disso é extrato", "x.txt"), self.gerente)
        self.assertIn("OFX", str(recusa.exception))

    def test_arquivo_grande_demais_e_recusado_antes_de_ser_lido(self):
        grande = SimpleUploadedFile("x.ofx", b"a" * (servicos.TAMANHO_MAXIMO + 1))
        with self.assertRaises(servicos.ExtratoRecusado) as recusa:
            servicos.importar(grande, self.gerente)
        self.assertIn("limite", str(recusa.exception))

    def test_fica_na_trilha_de_auditoria(self):
        self._extrato([(DIA, "-1362.00", "PIX QUITERIA")])
        evento = EventoAuditoria.objects.filter(acao="conciliacao.extrato_importado").first()
        self.assertIsNotNone(evento)
        self.assertEqual(evento.depois["movimentos"], 1)


class ConferirELimpar(BaseConciliacao):
    def setUp(self):
        super().setUp()
        self.extrato = self._extrato([(DIA, "-1362.00", "PIX QUITERIA")])
        self.linha = self.extrato.linhas.first()

    def test_conferir_guarda_quem_conferiu_e_o_que_foi_conferido(self):
        servicos.conferir(self.linha, self.conta.id_set, self.gerente, self.importacao)
        self.linha.refresh_from_db()
        self.assertEqual(self.linha.situacao, LinhaExtrato.Situacao.CONFERIDA)
        self.assertEqual(self.linha.lancamento_id_set, 1001)
        self.assertIn("QUITÉRIA", self.linha.lancamento_rotulo)
        self.assertEqual(self.linha.conferida_por, self.gerente)
        self.assertIsNotNone(self.linha.conferida_em)

    def test_a_conferencia_sobrevive_a_uma_sincronizacao_nova(self):
        """É a razão de guardar o código do SET em vez de uma chave estrangeira.

        A cada importação os lançamentos são apagados e gravados de novo. Uma chave
        estrangeira levaria junto a conferência que alguém fez à mão.
        """
        servicos.conferir(self.linha, self.conta.id_set, self.gerente, self.importacao)
        rotulo = LinhaExtrato.objects.get(pk=self.linha.pk).lancamento_rotulo
        Lancamento.objects.all().delete()
        self.importacao.delete()
        guardada = LinhaExtrato.objects.get(pk=self.linha.pk)
        self.assertEqual(guardada.situacao, LinhaExtrato.Situacao.CONFERIDA)
        self.assertEqual(guardada.lancamento_id_set, 1001)
        self.assertEqual(guardada.lancamento_rotulo, rotulo)

    def test_conta_que_nao_existe_na_sincronizacao_e_recusada(self):
        with self.assertRaises(servicos.ExtratoRecusado):
            servicos.conferir(self.linha, 999999, self.gerente, self.importacao)

    def test_marcar_sem_conta_guarda_a_anotacao(self):
        servicos.marcar_sem_conta(self.linha, self.gerente, "tarifa do banco")
        self.linha.refresh_from_db()
        self.assertEqual(self.linha.situacao, LinhaExtrato.Situacao.SEM_CONTA)
        self.assertEqual(self.linha.observacao, "tarifa do banco")

    def test_desfazer_volta_a_linha_para_pendente(self):
        servicos.conferir(self.linha, self.conta.id_set, self.gerente, self.importacao)
        servicos.desfazer(self.linha, self.gerente)
        self.linha.refresh_from_db()
        self.assertEqual(self.linha.situacao, LinhaExtrato.Situacao.PENDENTE)
        self.assertEqual(self.linha.lancamento_id_set, 0)
        self.assertEqual(self.linha.lancamento_rotulo, "")

    def test_conferir_as_obvias_so_pega_as_que_tem_uma_conta_so(self):
        self._conta(1002, "Pedido 2", "MINAS ARTES", Decimal("500.00"), DIA)
        self._conta(1003, "Pedido 3", "PAU BRASIL", Decimal("500.00"), DIA)
        extrato = self._extrato(
            [(DIA, "-500.00", "PIX DUVIDOSO"), (DIA, "-77.00", "PIX SEM CONTA")],
            nome="segundo.ofx")
        self.assertEqual(servicos.conferir_as_obvias(extrato, self.importacao, self.gerente), 0)
        self.assertEqual(servicos.conferir_as_obvias(self.extrato, self.importacao, self.gerente), 1)

    def test_apagar_leva_as_linhas_junto(self):
        servicos.apagar(self.extrato, self.gerente)
        self.assertEqual(ExtratoImportado.objects.count(), 0)
        self.assertEqual(LinhaExtrato.objects.count(), 0)


class ResumoDaTela(BaseConciliacao):
    def test_conta_cada_situacao_e_o_dinheiro_de_cada_lado(self):
        extrato = self._extrato([
            (DIA, "-1362.00", "PIX QUITERIA"),      # tem conta
            (DIA, "-89.90", "TARIFA DO BANCO"),     # não tem
            (DIA, "5000.00", "CREDITO CIELO"),      # entrada
        ])
        resumo = conferencia.resumir(conferencia.confrontar(extrato, self.importacao))
        self.assertEqual(resumo.linhas, 3)
        self.assertEqual(resumo.saidas, 2)
        self.assertEqual(resumo.entradas, 1)
        self.assertEqual(resumo.com_uma, 1)
        self.assertEqual(resumo.sem_par, 1)
        self.assertEqual(resumo.valor_saidas, Decimal("1451.90"))
        self.assertEqual(resumo.valor_entradas, Decimal("5000.00"))
        self.assertEqual(resumo.valor_a_conferir, Decimal("1451.90"))
        self.assertFalse(resumo.tudo_conferido)

    def test_depois_de_conferir_tudo_o_resumo_diz_que_acabou(self):
        extrato = self._extrato([(DIA, "-1362.00", "PIX QUITERIA")])
        servicos.conferir_as_obvias(extrato, self.importacao, self.gerente)
        resumo = conferencia.resumir(conferencia.confrontar(extrato, self.importacao))
        self.assertTrue(resumo.tudo_conferido)
        self.assertEqual(resumo.valor_conferido, Decimal("1362.00"))
        self.assertEqual(resumo.valor_a_conferir, Decimal("0"))


class TelasDaConciliacao(BaseConciliacao):
    def test_a_tela_abre_e_mostra_o_extrato(self):
        extrato = self._extrato([(DIA, "-1362.00", "PIX QUITERIA")])
        self.client.login(username="gerente_banco", password=SENHA_TESTE)
        corpo = self.client.get(reverse("conciliacao:lista")).content.decode()
        self.assertIn("Banco Teste", corpo)
        pagina = self.client.get(reverse("conciliacao:extrato", args=[extrato.pk]))
        self.assertEqual(pagina.status_code, 200)
        self.assertIn("QUITÉRIA FLOR MILHO", pagina.content.decode())

    def test_importar_pela_tela_e_depois_conferir_pela_tela(self):
        self.client.login(username="gerente_banco", password=SENHA_TESTE)
        resposta = self.client.post(reverse("conciliacao:importar"), {
            "extrato": _arquivo(_ofx([(DIA, "-1362.00", "PIX QUITERIA")])), "banco": "Sicoob",
        }, follow=True)
        self.assertEqual(resposta.status_code, 200)
        linha = LinhaExtrato.objects.get()
        self.assertEqual(linha.extrato.banco, "Sicoob")
        self.client.post(reverse("conciliacao:conferir", args=[linha.pk]),
                         {"conta": self.conta.id_set}, follow=True)
        linha.refresh_from_db()
        self.assertEqual(linha.situacao, LinhaExtrato.Situacao.CONFERIDA)

    def test_arquivo_recusado_volta_com_a_explicacao_na_tela(self):
        self.client.login(username="gerente_banco", password=SENHA_TESTE)
        resposta = self.client.post(reverse("conciliacao:importar"), {
            "extrato": _arquivo("isto não é extrato nenhum", "x.txt"),
        }, follow=True)
        self.assertContains(resposta, "OFX")
        self.assertEqual(ExtratoImportado.objects.count(), 0)

    def test_o_administrativo_concilia_e_o_vendedor_nao_entra(self):
        usuario("adm_banco", ADMINISTRATIVO)
        self.client.login(username="adm_banco", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("conciliacao:lista")).status_code, 200)
        self.client.logout()

        usuario("vendedora_banco", VENDEDOR)
        self.client.login(username="vendedora_banco", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("conciliacao:lista")).status_code, 403)

    def test_as_telas_que_mudam_coisa_so_aceitam_post(self):
        extrato = self._extrato([(DIA, "-1362.00", "PIX QUITERIA")])
        linha = extrato.linhas.first()
        self.client.login(username="gerente_banco", password=SENHA_TESTE)
        for rota, argumento in (("conciliacao:importar", None),
                                ("conciliacao:apagar", extrato.pk),
                                ("conciliacao:conferir", linha.pk),
                                ("conciliacao:desfazer", linha.pk)):
            endereco = reverse(rota, args=[argumento] if argumento else None)
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(endereco).status_code, 405)


class UmaContaPagaUmaSaida(BaseConciliacao):
    """Duas saídas iguais no banco com UMA conta no SET não são duas conferências.

    Achado na revisão geral de 15/10/2026. As candidatas de todas as linhas são lidas de
    uma vez, antes do laço, e uma conta já usada só perdia pontos na ordenação em vez de
    sair da lista. Então as duas linhas apareciam como "uma conta só bate" e o botão
    "conferir as óbvias" amarrava as duas na mesma conta. O resumo somava o mesmo
    dinheiro duas vezes, os pendentes zeravam e a tela declarava o extrato inteiro
    conferido — enquanto uma retirada de verdade não tinha lançamento nenhum no SET, que
    é exatamente o que a conciliação existe para encontrar.
    """

    def _duas_saidas_iguais(self):
        return self._extrato([(DIA, "-1362.00", "PIX QUITERIA FLOR MILHO"),
                              (DIA + timedelta(days=1), "-1362.00", "PIX QUITERIA FLOR MILHO")])

    def test_conferir_as_obvias_amarra_uma_linha_so(self):
        extrato = self._duas_saidas_iguais()
        quantas = servicos.conferir_as_obvias(extrato, self.importacao, self.gerente)
        self.assertEqual(quantas, 1)
        amarradas = extrato.linhas.filter(situacao=LinhaExtrato.Situacao.CONFERIDA)
        self.assertEqual(amarradas.count(), 1)

    def test_a_outra_linha_continua_pendente_e_o_extrato_nao_se_diz_conferido(self):
        extrato = self._duas_saidas_iguais()
        servicos.conferir_as_obvias(extrato, self.importacao, self.gerente)
        resumo = conferencia.resumir(conferencia.confrontar(extrato, self.importacao))
        self.assertEqual(resumo.pendentes, 1)
        self.assertFalse(resumo.tudo_conferido)
        self.assertEqual(resumo.valor_conferido, Decimal("1362.00"))

    def test_marcar_a_mao_a_mesma_conta_na_outra_linha_e_recusado_com_explicacao(self):
        extrato = self._duas_saidas_iguais()
        servicos.conferir_as_obvias(extrato, self.importacao, self.gerente)
        pendente = extrato.linhas.filter(situacao=LinhaExtrato.Situacao.PENDENTE).get()
        with self.assertRaises(servicos.ExtratoRecusado) as recusa:
            servicos.conferir(pendente, self.conta.id_set, self.gerente, self.importacao)
        self.assertIn("já está marcada", str(recusa.exception))
        pendente.refresh_from_db()
        self.assertEqual(pendente.situacao, LinhaExtrato.Situacao.PENDENTE)

    def test_desfazer_a_primeira_libera_a_conta_para_a_outra(self):
        """Errar a conferência é normal: a conta tem que voltar a ficar disponível."""
        extrato = self._duas_saidas_iguais()
        servicos.conferir_as_obvias(extrato, self.importacao, self.gerente)
        conferida = extrato.linhas.filter(situacao=LinhaExtrato.Situacao.CONFERIDA).get()
        pendente = extrato.linhas.filter(situacao=LinhaExtrato.Situacao.PENDENTE).get()
        servicos.desfazer(conferida, self.gerente)
        servicos.conferir(pendente, self.conta.id_set, self.gerente, self.importacao)
        pendente.refresh_from_db()
        self.assertEqual(pendente.situacao, LinhaExtrato.Situacao.CONFERIDA)

    def test_reconferir_a_mesma_linha_na_mesma_conta_continua_valendo(self):
        """Clicar duas vezes em "É esta" não pode virar recusa."""
        extrato = self._extrato([(DIA, "-1362.00", "PIX QUITERIA FLOR MILHO")])
        linha = extrato.linhas.get()
        servicos.conferir(linha, self.conta.id_set, self.gerente, self.importacao)
        servicos.conferir(linha, self.conta.id_set, self.gerente, self.importacao)
        linha.refresh_from_db()
        self.assertEqual(linha.situacao, LinhaExtrato.Situacao.CONFERIDA)

    def test_a_tela_nao_chama_de_obvia_a_conta_ja_marcada(self):
        extrato = self._duas_saidas_iguais()
        servicos.conferir_as_obvias(extrato, self.importacao, self.gerente)
        self.client.login(username="gerente_banco", password=SENHA_TESTE)
        corpo = self.client.get(reverse("conciliacao:extrato", args=[extrato.pk])).content.decode()
        self.assertIn("já está marcada em outra saída", corpo)
