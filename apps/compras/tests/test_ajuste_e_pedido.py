"""Quantidade escolhida à mão na lista de compra, e o pedido que vai ao fornecedor.

Os dois pedidos do Edson de 14/10/2026: "permitir edição da quantidade, manter a
sugestão" e "disponibilizar um botão para gerar o pedido para o fornecedor(es) com
layout do Studio Industrial e razão social da Essenza".
"""

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import EventoAuditoria
from apps.compras import ajustes, lista_de_compra as lista_servicos, pedido
from apps.compras.models import AjusteDeCompra, DadosDaEmpresa
from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.importacao.models import Importacao, ProdutoImportado
from apps.pedidos.models import Pedido

CORTE = date(2026, 9, 20)


class BaseAjuste(TestCase):
    def setUp(self):
        self.importacao = self.nova_importacao()

    def nova_importacao(self):
        return Importacao.objects.create(
            origem=Importacao.Origem.BANCO,
            situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(),
            data_corte=CORTE,
            dias_abertos_12m=360,
            produtos=0,
        )

    def produto(self, codigo, importacao=None, **campos):
        padrao = dict(
            importacao=importacao or self.importacao, codigo=codigo,
            descricao=f"PRODUTO {codigo}", grupo="TAPETE", fornecedor="GERMAN",
            custo=Decimal("10"), preco_venda=Decimal("25"), estoque=Decimal("0"),
            vendas_12m=Decimal("360"), receita_12m=Decimal("9000"),
        )
        padrao.update(campos)
        return ProdutoImportado.objects.create(**padrao)

    def montar(self, importacao=None, **kwargs):
        return lista_servicos.montar(importacao or self.importacao, **kwargs)

    def um_item(self, **kwargs):
        return self.montar(**kwargs).fornecedores[0].itens[0]


class NumeroQueAPessoaDigita(TestCase):
    """O campo aceita o jeito brasileiro de escrever número, e recusa o resto."""

    def test_aceita_inteiro_e_virgula(self):
        self.assertEqual(ajustes.quantidade_informada("12"), Decimal("12.000"))
        self.assertEqual(ajustes.quantidade_informada("12,5"), Decimal("12.500"))
        self.assertEqual(ajustes.quantidade_informada(" 12 "), Decimal("12.000"))

    def test_ponto_sozinho_e_casa_decimal_e_com_virgula_e_milhar(self):
        """Quem copia de outra tela traz das duas formas; esta loja não compra mil peças."""
        self.assertEqual(ajustes.quantidade_informada("12.5"), Decimal("12.500"))
        self.assertEqual(ajustes.quantidade_informada("1.250,5"), Decimal("1250.500"))

    def test_zero_vale_e_quer_dizer_nao_comprar_agora(self):
        self.assertEqual(ajustes.quantidade_informada("0"), Decimal("0.000"))

    def test_recusa_texto_vazio_e_negativo(self):
        for ruim in ("", "   ", "doze", "-3"):
            with self.assertRaises(ajustes.ErroDeAjuste):
                ajustes.quantidade_informada(ruim)

    def test_recusa_numero_que_so_pode_ser_dedo_escorregando(self):
        with self.assertRaises(ajustes.ErroDeAjuste):
            ajustes.quantidade_informada("1000000")


class ParcelaQueAPessoaDigita(TestCase):
    """O campo da mão SOMA com a sugestão, então aceita negativo e aceita vazio.

    Pedido dele em 20/10/2026: "no campo de quantidade sugerida, adicionar quantidade
    manual, com a soma dois campos gera a quantidade total".
    """

    def test_aceita_inteiro_virgula_e_negativo(self):
        self.assertEqual(ajustes.parcela_informada("5"), Decimal("5.000"))
        self.assertEqual(ajustes.parcela_informada("2,5"), Decimal("2.500"))
        self.assertEqual(ajustes.parcela_informada("-3"), Decimal("-3.000"))

    def test_campo_vazio_e_zero_e_nao_erro(self):
        """Limpar o campo quer dizer "siga a conta do sistema", não "erro de digitação"."""
        for nada in ("", "   ", None, "-"):
            self.assertEqual(ajustes.parcela_informada(nada), Decimal("0"))

    def test_recusa_texto_e_numero_fora_de_pe(self):
        for ruim in ("doze", "1000000", "-1000000"):
            with self.assertRaises(ajustes.ErroDeAjuste):
                ajustes.parcela_informada(ruim)


class ASomaDasDuasParcelas(TestCase):
    """sugerida + à mão = total, e o total nunca desce abaixo de zero."""

    def test_soma_as_duas(self):
        self.assertEqual(ajustes.total(Decimal("14"), Decimal("5")), Decimal("19"))

    def test_parcela_negativa_tira_do_total(self):
        self.assertEqual(ajustes.total(Decimal("14"), Decimal("-4")), Decimal("10"))

    def test_negativo_maior_que_a_sugestao_para_em_zero(self):
        """"Menos 20" numa sugestão de 14 quer dizer não comprar, não comprar ao contrário."""
        self.assertEqual(ajustes.total(Decimal("14"), Decimal("-20")), Decimal("0"))

    def test_nao_comprar_zera_qualquer_soma(self):
        self.assertEqual(
            ajustes.total(Decimal("14"), Decimal("5"), nao_comprar=True), Decimal("0"))


class GravarEDesfazer(BaseAjuste):
    def test_grava_a_parcela_da_mao_e_o_total_do_momento(self):
        ajuste, total = ajustes.salvar(codigo="1", a_mais="5", sugerida=Decimal("14"))
        self.assertEqual(total, Decimal("19.000"))
        self.assertEqual(ajuste.a_mais, Decimal("5.000"))
        self.assertEqual(ajuste.quantidade, Decimal("19.000"))
        self.assertEqual(ajuste.sugerida, Decimal("14.000"))

    def test_o_que_vale_e_a_parcela_quando_a_sugestao_muda(self):
        """O defeito que o total guardado teria: "+5" pensado para 14 virando 15 fixo.

        Quem acrescenta 5 unidades porque um cliente encomendou quer 5 a mais do que o
        sistema achar certo — e o sistema muda de ideia três vezes por dia, a cada
        sincronização.
        """
        ajuste, _ = ajustes.salvar(codigo="1", a_mais="5", sugerida=Decimal("14"))
        self.assertEqual(ajuste.total_com(Decimal("20")), Decimal("25"))

    def test_parcela_zero_nao_cria_ajuste(self):
        """Linha "mudada à mão" que acrescenta nada só serviria para confundir."""
        ajuste, total = ajustes.salvar(codigo="1", a_mais="0", sugerida=Decimal("12.000"))
        self.assertIsNone(ajuste)
        self.assertEqual(total, Decimal("12.000"))
        self.assertFalse(AjusteDeCompra.objects.exists())

    def test_zerar_a_parcela_apaga_um_ajuste_que_existia(self):
        ajustes.salvar(codigo="1", a_mais="8", sugerida=Decimal("12"))
        ajustes.salvar(codigo="1", a_mais="", sugerida=Decimal("12"))
        self.assertFalse(AjusteDeCompra.objects.exists())

    def test_salvar_de_novo_troca_a_parcela_em_vez_de_criar_outra_linha(self):
        ajustes.salvar(codigo="1", a_mais="8", sugerida=Decimal("12"))
        ajustes.salvar(codigo="1", a_mais="18", sugerida=Decimal("12"))
        self.assertEqual(AjusteDeCompra.objects.count(), 1)
        self.assertEqual(AjusteDeCompra.objects.get().a_mais, Decimal("18.000"))

    def test_nao_comprar_grava_sem_parcela_e_com_total_zero(self):
        ajuste, total = ajustes.salvar(codigo="1", a_mais="5", sugerida=Decimal("14"),
                                       nao_comprar=True)
        self.assertTrue(ajuste.nao_comprar)
        self.assertEqual(ajuste.a_mais, Decimal("0.000"))
        self.assertEqual(total, Decimal("0.000"))

    def test_a_sugestao_chega_do_formulario_como_texto_localizado(self):
        """O Django escreve 12,000 no HTML; o que volta no POST é isso, e não um número."""
        ajuste, _ = ajustes.salvar(codigo="1", a_mais="8", sugerida="12,000")
        self.assertEqual(ajuste.sugerida, Decimal("12.000"))

    def test_limpar_devolve_a_linha_para_a_conta_do_sistema(self):
        ajustes.salvar(codigo="1", a_mais="8", sugerida=Decimal("12"))
        self.assertEqual(ajustes.limpar("1"), 1)
        self.assertFalse(AjusteDeCompra.objects.exists())


class OQueAListaFazComOAjuste(BaseAjuste):
    def setUp(self):
        super().setUp()
        self.produto("1")
        self.sugerida = self.um_item().comprar

    def test_a_tela_mostra_a_soma_das_duas_parcelas(self):
        ajustes.salvar(codigo="1", a_mais="5", sugerida=self.sugerida)
        item = self.um_item()
        self.assertEqual(item.comprar, self.sugerida)
        self.assertEqual(item.a_mais, Decimal("5.000"))
        self.assertEqual(item.quantidade, self.sugerida + 5)
        self.assertTrue(item.foi_ajustada)

    def test_sem_ajuste_a_quantidade_e_a_do_sistema(self):
        item = self.um_item()
        self.assertFalse(item.foi_ajustada)
        self.assertEqual(item.quantidade, item.comprar)

    def test_parcela_negativa_compra_menos_sem_tirar_da_lista(self):
        ajustes.salvar(codigo="1", a_mais="-2", sugerida=self.sugerida)
        item = self.um_item()
        self.assertEqual(item.quantidade, self.sugerida - 2)
        self.assertTrue(item.foi_ajustada)

    def test_o_valor_do_pedido_segue_o_total(self):
        ajustes.salvar(codigo="1", a_mais="5", sugerida=self.sugerida)
        item = self.um_item()
        self.assertEqual(item.valor_do_pedido, (self.sugerida + 5) * 10)

    def test_o_total_do_fornecedor_e_da_lista_somam_o_que_vai_no_pedido(self):
        """Total que ainda mostrasse a conta do sistema depois do ajuste estaria mentindo."""
        ajustes.salvar(codigo="1", a_mais="5", sugerida=self.sugerida)
        esperado = (self.sugerida + 5) * 10
        lista = self.montar()
        self.assertEqual(lista.fornecedores[0].valor, esperado)
        self.assertEqual(lista.valor, esperado)
        self.assertEqual(lista.ajustados, 1)
        self.assertEqual(lista.fornecedores[0].ajustados, 1)

    def test_nao_comprar_tira_o_produto_do_pedido_mas_nao_da_tela(self):
        ajustes.salvar(codigo="1", a_mais="", sugerida=self.sugerida, nao_comprar=True)
        lista = self.montar()
        self.assertEqual(lista.quantos, 1)
        self.assertEqual(lista.valor, Decimal("0.00"))
        self.assertEqual(pedido.itens_do_pedido(lista.fornecedores[0]), [])

    def test_nao_comprar_continua_valendo_quando_a_conta_muda(self):
        """Era o defeito do "digitar 0": menos dez só zera enquanto a sugestão for dez."""
        ajustes.salvar(codigo="1", a_mais="", sugerida=self.sugerida, nao_comprar=True)
        outra = self.nova_importacao()
        self.produto("1", importacao=outra, vendas_12m=Decimal("720"))
        item = self.um_item(importacao=outra)
        self.assertEqual(item.quantidade, Decimal("0"))

    def test_o_ajuste_sobrevive_a_sincronizacao(self):
        """A foto do SET é refeita toda vez; o que a gerência decidiu não pode ir junto."""
        ajustes.salvar(codigo="1", a_mais="5", sugerida=self.sugerida)
        outra = self.nova_importacao()
        self.produto("1", importacao=outra)
        item = self.um_item(importacao=outra)
        self.assertTrue(item.foi_ajustada)
        self.assertEqual(item.a_mais, Decimal("5.000"))

    def test_quando_a_conta_muda_depois_a_tela_diz_de_quanto_era(self):
        ajustes.salvar(codigo="1", a_mais="5", sugerida=self.sugerida + 5)
        item = self.um_item()
        self.assertTrue(item.ajuste_desatualizado)
        self.assertEqual(item.sugerida_no_ajuste, self.sugerida + 5)

    def test_conta_igual_a_do_ajuste_nao_gera_aviso(self):
        ajustes.salvar(codigo="1", a_mais="5", sugerida=self.sugerida)
        self.assertFalse(self.um_item().ajuste_desatualizado)

    def test_o_arquivo_leva_o_total_a_sugerida_e_a_parcela_lado_a_lado(self):
        pessoa = usuario("gerente_csv", ADMINISTRACAO)
        ajustes.salvar(codigo="1", a_mais="5", sugerida=self.sugerida, usuario=pessoa)
        cabecalho, linha = lista_servicos.em_linhas(self.montar())
        self.assertEqual(cabecalho[9], "Comprar")
        self.assertEqual(cabecalho[10], "Sugerido pelo sistema")
        self.assertEqual(cabecalho[11], "Quantidade a mais")
        self.assertEqual(linha[9], self.sugerida + 5)
        self.assertEqual(linha[10], self.sugerida)
        self.assertEqual(linha[11], Decimal("5.000"))
        self.assertEqual(linha[12], pessoa.get_full_name() or pessoa.get_username())


class TelaDaLista(BaseAjuste):
    def setUp(self):
        super().setUp()
        self.produto("1")
        self.sugerida = self.um_item().comprar
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)

    def _ajustar(self, **campos):
        dados = {"codigo": "1", "descricao": "PRODUTO 1",
                 "sugerida": str(self.sugerida), "a_mais": "7"}
        dados.update(campos)
        return self.client.post(reverse("compras:ajustar_quantidade"), dados)

    def test_a_tela_traz_a_soma_das_duas_parcelas_e_o_total(self):
        """A conta dele escrita como conta: sugerida + à mão = total."""
        corpo = self.client.get(reverse("compras:lista")).content.decode()
        self.assertIn('name="a_mais"', corpo)
        self.assertIn('name="sugerida"', corpo)
        self.assertIn("sugerida", corpo)
        self.assertIn("à mão", corpo)
        self.assertIn("total", corpo)
        self.assertIn("Gerar o pedido de GERMAN em PDF", corpo)

    def test_a_tela_traz_o_botao_de_nao_comprar_agora(self):
        """Com a soma, digitar 0 deixou de querer dizer "este não": o caminho é próprio."""
        corpo = self.client.get(reverse("compras:lista")).content.decode()
        self.assertIn('name="nao_comprar"', corpo)
        self.assertIn("não comprar agora", corpo)

    def test_salvar_grava_e_volta_para_a_lista(self):
        resposta = self._ajustar()
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("compras:lista"), resposta["Location"])
        self.assertEqual(AjusteDeCompra.objects.get().a_mais, Decimal("7.000"))
        self.assertEqual(AjusteDeCompra.objects.get().quantidade, self.sugerida + 7)

    def test_nao_comprar_agora_pela_tela(self):
        resposta = self.client.post(
            reverse("compras:ajustar_quantidade"),
            {"codigo": "1", "descricao": "PRODUTO 1", "sugerida": str(self.sugerida),
             "nao_comprar": "1"}, follow=True)
        self.assertTrue(AjusteDeCompra.objects.get().nao_comprar)
        self.assertContains(resposta, "fica fora do pedido")

    def test_volta_para_a_mesma_lista_filtrada_e_para_a_linha_do_produto(self):
        resposta = self._ajustar(fornecedor="GERMAN", situacao="faltando")
        destino = resposta["Location"]
        self.assertIn("fornecedor=GERMAN", destino)
        self.assertIn("situacao=faltando", destino)
        self.assertIn("#produto-1", destino)

    def test_numero_impossivel_volta_com_recado_e_nao_grava(self):
        resposta = self.client.post(
            reverse("compras:ajustar_quantidade"),
            {"codigo": "1", "descricao": "PRODUTO 1", "sugerida": str(self.sugerida),
             "a_mais": "doze"}, follow=True)
        self.assertFalse(AjusteDeCompra.objects.exists())
        self.assertContains(resposta, "tem que ser um número")

    def test_voltar_a_sugestao_apaga_o_ajuste(self):
        self._ajustar()
        self.client.post(reverse("compras:ajustar_quantidade"),
                         {"codigo": "1", "descricao": "PRODUTO 1", "voltar_a_sugestao": "1"})
        self.assertFalse(AjusteDeCompra.objects.exists())

    def test_fica_na_trilha_de_auditoria(self):
        self._ajustar()
        evento = EventoAuditoria.objects.filter(acao="compras.quantidade_ajustada").first()
        self.assertIsNotNone(evento)
        self.assertEqual(evento.depois["a_mais"], "7.000")
        self.assertEqual(Decimal(evento.depois["quantidade"]), self.sugerida + 7)

    def test_a_trilha_guarda_a_justificativa_que_a_pessoa_escreveu(self):
        """Pedido dele em 20/10/2026, seção 11: registrar a justificativa do ajuste.

        A justificativa ficava só no registro do ajuste, que a edição seguinte
        sobrescreve: o POR QUÊ se perdia e a trilha guardava só o número.
        """
        self._ajustar(observacao="cliente pediu, pagamento adiantado")
        evento = EventoAuditoria.objects.filter(acao="compras.quantidade_ajustada").first()
        self.assertEqual(evento.depois["observacao"], "cliente pediu, pagamento adiantado")
        self.assertEqual(evento.motivo, "cliente pediu, pagamento adiantado")

    def test_a_trilha_diz_de_que_numero_se_mudou(self):
        """"Quem mudou de 7 para 3" é a pergunta de três meses depois, não "qual era a conta"."""
        self._ajustar(a_mais="7", observacao="primeiro palpite")
        self._ajustar(a_mais="3", observacao="fornecedor só tem 3")
        eventos = list(EventoAuditoria.objects
                       .filter(acao="compras.quantidade_ajustada").order_by("momento", "id"))
        self.assertEqual(eventos[0].antes["a_mais"], "")
        self.assertEqual(eventos[1].antes["a_mais"], "7.000")
        self.assertEqual(eventos[1].antes["observacao"], "primeiro palpite")
        self.assertEqual(eventos[1].depois["a_mais"], "3.000")

    def test_voltar_a_sugestao_registra_o_numero_que_foi_desfeito(self):
        self._ajustar(a_mais="7", observacao="combinado por telefone")
        self.client.post(reverse("compras:ajustar_quantidade"),
                         {"codigo": "1", "descricao": "PRODUTO 1", "voltar_a_sugestao": "1"})
        evento = EventoAuditoria.objects.get(acao="compras.quantidade_restaurada")
        self.assertEqual(Decimal(evento.antes["escolhida"]), self.sugerida + 7)
        self.assertEqual(evento.antes["observacao"], "combinado por telefone")

    def test_parcela_zero_fica_registrada_como_seguindo_a_sugestao(self):
        """Sem isto, o evento parece um ajuste comum e o contador da tela não bate."""
        self._ajustar(a_mais="0")
        evento = EventoAuditoria.objects.filter(acao="compras.quantidade_ajustada").first()
        self.assertTrue(evento.depois["seguiu_a_sugestao"])

    def test_quem_nao_pode_ajustar_ve_o_numero_e_nao_o_campo(self):
        """Campo que recusa o clique é promessa quebrada na cara de quem clicou."""
        self.client.logout()
        usuario("administrativa", ADMINISTRATIVO)
        self.client.login(username="administrativa", password=SENHA_TESTE)
        corpo = self.client.get(reverse("compras:lista")).content.decode()
        self.assertNotIn('name="a_mais"', corpo)
        self.assertNotIn('name="nao_comprar"', corpo)
        self.assertIn("Gerar o pedido de GERMAN em PDF", corpo)

    def test_o_administrativo_nao_muda_a_quantidade_pelo_endereco(self):
        self.client.logout()
        usuario("administrativa2", ADMINISTRATIVO)
        self.client.login(username="administrativa2", password=SENHA_TESTE)
        self.assertEqual(self._ajustar().status_code, 403)

    def test_so_aceita_post(self):
        self.assertEqual(self.client.get(reverse("compras:ajustar_quantidade")).status_code, 405)


class PedidoEmPdf(BaseAjuste):
    def setUp(self):
        super().setUp()
        self.produto("1")
        self.produto("2", fornecedor="VIME LENZI", descricao="CADEIRA DE VIME")
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)

    def _baixar(self, **parametros):
        return self.client.get(reverse("compras:pedido_ao_fornecedor"), parametros)

    def test_sai_um_pdf_de_verdade_com_nome_do_fornecedor_no_arquivo(self):
        resposta = self._baixar(fornecedor="VIME LENZI")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["Content-Type"], "application/pdf")
        self.assertIn("pedido-vime-lenzi", resposta["Content-Disposition"])
        self.assertTrue(resposta.content.startswith(b"%PDF-"))
        self.assertTrue(resposta.content.rstrip().endswith(b"%%EOF"))

    def test_o_papel_traz_a_razao_social_o_endereco_e_o_fornecedor(self):
        """Layout do Studio Industrial, razão social da Essenza e o fornecedor."""
        corpo = self._baixar(fornecedor="VIME LENZI").content
        self.assertIn(b"Studio Industrial", corpo)
        self.assertIn(b"ESSENZA DECOR DESIGN E DECORACAO LTDA", corpo)
        self.assertIn(b"48.634.542/0001-42", corpo)
        self.assertIn(b"VIME LENZI", corpo)
        self.assertIn(b"CADEIRA DE VIME", corpo)

    def test_o_papel_diz_onde_a_carga_desce_quando_nao_e_o_endereco_da_nota(self):
        """O CNPJ está na Claudionor Assis Dias e a loja fica no Largo dos Jesuítas.

        Sem esta linha o fornecedor manda a carga para o endereço fiscal, que é o
        único que o papel trazia até a 1.34.0.
        """
        corpo = self._baixar(fornecedor="VIME LENZI").content
        self.assertIn("R. Claudionor Assis Dias, 171".encode("cp1252"), corpo)
        self.assertIn("Entregar em: Largo dos Jesuítas, 64".encode("cp1252"), corpo)

    def test_sem_endereco_de_entrega_o_papel_nao_repete_o_da_nota(self):
        empresa = DadosDaEmpresa.atual()
        empresa.endereco_entrega = ""
        empresa.save(update_fields=["endereco_entrega"])
        corpo = self._baixar(fornecedor="VIME LENZI").content
        self.assertNotIn("Entregar em".encode("cp1252"), corpo)

    def test_o_pedido_de_um_fornecedor_nao_leva_produto_de_outro(self):
        corpo = self._baixar(fornecedor="VIME LENZI").content
        self.assertNotIn(b"PRODUTO 1", corpo)

    def test_o_papel_usa_a_quantidade_escolhida_a_mao(self):
        ajustes.salvar(codigo="2", a_mais="3", sugerida=Decimal("999"))
        corpo = self._baixar(fornecedor="VIME LENZI").content
        self.assertIn("definidas pela loja".encode("cp1252"), corpo)

    def test_produto_marcado_para_nao_comprar_fica_fora_do_papel(self):
        self.produto("3", fornecedor="VIME LENZI", descricao="BANCO DE VIME")
        ajustes.salvar(codigo="3", a_mais="", sugerida=Decimal("10"), nao_comprar=True)
        corpo = self._baixar(fornecedor="VIME LENZI").content
        self.assertNotIn(b"BANCO DE VIME", corpo)
        self.assertIn("ficaram fora deste pedido".encode("cp1252"), corpo)

    def test_sem_fornecedor_saem_os_do_comeco_da_lista_um_por_folha(self):
        relatorio = pedido.montar(self.montar().fornecedores, DadosDaEmpresa.atual())
        self.assertEqual(len(relatorio.paginas), 2)

    def test_fornecedor_que_nao_esta_na_lista_nao_vira_pedido_da_loja_inteira(self):
        """Nome errado no endereço não pode devolver um pedido com todo mundo dentro."""
        self.assertEqual(self._baixar(fornecedor="NAO EXISTE").status_code, 404)

    def test_fica_na_trilha_de_auditoria(self):
        self._baixar(fornecedor="VIME LENZI")
        evento = EventoAuditoria.objects.filter(acao="compras.pedido_gerado").first()
        self.assertIsNotNone(evento)
        self.assertEqual(evento.depois["fornecedores"], 1)

    def test_o_vendedor_nao_tira_pedido(self):
        self.client.logout()
        usuario("vendedora", VENDEDOR)
        self.client.login(username="vendedora", password=SENHA_TESTE)
        self.assertEqual(self._baixar(fornecedor="VIME LENZI").status_code, 403)


class TelaDosDadosDaEmpresa(TestCase):
    """O formulário que ele pediu em 19/10/2026, com os dados que mandou na mesma mensagem."""

    TUDO = {
        "nome_fantasia": "Studio Industrial",
        "razao_social": "ESSENZA DECOR DESIGN E DECORACAO LTDA",
        "documento": "48.634.542/0001-42", "inscricao_estadual": "298.589.161.112",
        "endereco": "R. Claudionor Assis Dias, 171", "bairro": "Centro",
        "cidade": "Embu das Artes", "estado": "SP", "cep": "06803-320",
        "endereco_entrega": "Largo dos Jesuítas, 64", "bairro_entrega": "Centro",
        "cidade_entrega": "Embu das Artes", "estado_entrega": "SP",
        "cep_entrega": "06803-360",
        "telefone": "(11) 4704-7991", "email": "cabanadojacaranda@gmail.com",
        "observacao": "",
    }

    def setUp(self):
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)

    def test_a_tela_ja_abre_com_os_dados_que_ele_mandou(self):
        """Ele mandou tudo por mensagem: pedir que digite de novo seria desperdiçar o recado."""
        resposta = self.client.get(reverse("compras:dados_da_empresa"))
        self.assertContains(resposta, "48.634.542/0001-42")
        self.assertContains(resposta, "ESSENZA DECOR DESIGN E DECORACAO LTDA")
        self.assertContains(resposta, "Embu das Artes")
        self.assertContains(resposta, "298.589.161.112")

    def test_nao_falta_mais_nada_para_o_fornecedor(self):
        self.assertEqual(DadosDaEmpresa.atual().falta_preencher, [])

    def test_o_nome_fantasia_aparece_em_destaque_com_o_logotipo(self):
        """Pedido dele: evidenciar o nome fantasia e pôr o logotipo da loja."""
        corpo = self.client.get(reverse("compras:dados_da_empresa")).content.decode()
        timbre = corpo[corpo.index("empresa-timbre"):corpo.index("empresa-secao")]
        self.assertIn("img/logo", timbre)
        self.assertIn('class="empresa-nome">Studio Industrial', timbre)
        # A razão social aparece, mas abaixo e em segundo plano: o papel dela é a nota.
        self.assertLess(timbre.index("empresa-nome"), timbre.index("empresa-razao"))

    def test_o_formulario_vem_em_blocos_por_assunto(self):
        corpo = self.client.get(reverse("compras:dados_da_empresa")).content.decode()
        for titulo in ("Quem é a loja", "Endereço da nota", "Endereço da entrega",
                       "Contato e recado"):
            self.assertIn(titulo, corpo)

    def test_a_ajuda_do_bloco_nao_se_repete_embaixo_do_campo(self):
        """Ele reclamou de informação demais: a linha do bloco já diz o que o campo é.

        O texto continua no modelo, para quem lê o cadastro pelo admin; o que sai é a
        repetição na tela, embaixo do campo, logo abaixo da frase que diz o mesmo.
        """
        corpo = self.client.get(reverse("compras:dados_da_empresa")).content.decode()
        self.assertIn("O endereço que consta no CNPJ", corpo)  # a linha do bloco fica
        self.assertNotIn("É para ele que a nota é emitida", corpo)
        self.assertNotIn("quando não é o mesmo da nota", corpo)
        self.assertNotIn("É o que aparece grande no pedido", corpo)

    def test_campo_comprido_ocupa_a_largura_inteira_da_grade(self):
        """Endereço e e-mail não cabem em meia coluna; bairro, UF e CEP sobram nela."""
        corpo = self.client.get(reverse("compras:dados_da_empresa")).content.decode()
        self.assertIn("campos-em-grade", corpo)

        def caixa_do(campo):
            """Do <div> que abre o campo até o próprio campo: a classe está no <div>."""
            fim = corpo.index(f'name="{campo}"')
            return corpo[corpo.rindex('<div class="campo', 0, fim):fim]

        self.assertIn("campo-largo", caixa_do("endereco"))
        self.assertIn("campo-largo", caixa_do("email"))
        self.assertNotIn("campo-largo", caixa_do("bairro"))
        self.assertNotIn("campo-largo", caixa_do("cep"))

    def test_os_dois_enderecos_aparecem_separados(self):
        """O da nota e o da entrega não são o mesmo, e confundir é mandar a carga errado."""
        empresa = DadosDaEmpresa.atual()
        self.assertIn("Claudionor", empresa.linha_do_endereco)
        self.assertIn("Jesuítas", empresa.linha_da_entrega)

    def test_entrega_em_branco_quer_dizer_no_mesmo_endereco(self):
        """Sem isto o pedido imprimiria o mesmo endereço duas vezes, com dois rótulos."""
        empresa = DadosDaEmpresa.atual()
        empresa.endereco_entrega = ""
        empresa.save(update_fields=["endereco_entrega"])
        self.assertEqual(DadosDaEmpresa.atual().linha_da_entrega, "")

    def test_entrega_igual_a_nota_tambem_nao_vira_segunda_linha(self):
        empresa = DadosDaEmpresa.atual()
        empresa.endereco_entrega = empresa.endereco
        empresa.bairro_entrega = empresa.bairro
        empresa.cidade_entrega = empresa.cidade
        empresa.estado_entrega = empresa.estado
        empresa.cep_entrega = empresa.cep
        empresa.save()
        self.assertEqual(DadosDaEmpresa.atual().linha_da_entrega, "")

    def test_grava_e_o_pedido_passa_a_sair_com_os_dados(self):
        dados = dict(self.TUDO, documento="00.000.000/0001-00", estado="rj",
                     estado_entrega="rj")
        resposta = self.client.post(reverse("compras:dados_da_empresa"), dados)
        self.assertEqual(resposta.status_code, 302)
        empresa = DadosDaEmpresa.atual()
        self.assertEqual(empresa.documento, "00.000.000/0001-00")
        self.assertEqual(empresa.estado, "RJ")
        self.assertEqual(empresa.estado_entrega, "RJ")
        self.assertEqual(empresa.falta_preencher, [])

    def test_fica_na_trilha_de_auditoria(self):
        self.client.post(reverse("compras:dados_da_empresa"),
                         dict(self.TUDO, documento="11.111.111/0001-11"))
        self.assertTrue(EventoAuditoria.objects.filter(acao="compras.empresa_configurada").exists())

    def test_o_administrativo_nao_mexe_no_documento_da_empresa(self):
        self.client.logout()
        usuario("administrativa3", ADMINISTRATIVO)
        self.client.login(username="administrativa3", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("compras:dados_da_empresa")).status_code, 403)

    def test_todo_campo_do_modelo_esta_em_algum_bloco(self):
        """Campo que não entra numa seção existe no banco e nunca aparece na tela."""
        from apps.compras.forms import SECOES

        nos_blocos = {campo for _, _, campos in SECOES for campo in campos}
        do_modelo = {c.name for c in DadosDaEmpresa._meta.fields
                     if c.name not in {"id", "atualizado_em"}}
        self.assertEqual(do_modelo - nos_blocos, set())


class ACidadeDaLojaJaVemEscrita(TestCase):
    """O passo que estava parado desde a 1.29.0 esperando alguém digitar a cidade.

    Ele informou os dois endereços em 19/10/2026 e os dois ficam em Embu das Artes, então
    a cidade deixou de ser pergunta: a previsão do tempo passa a funcionar sem ninguém
    abrir a tela.
    """

    def test_a_configuracao_do_tempo_ja_sabe_a_cidade(self):
        from apps.tempo.models import ConfiguracaoDoTempo

        configuracao = ConfiguracaoDoTempo.atual()
        self.assertEqual(configuracao.cidade, "Embu das Artes")
        self.assertTrue(configuracao.da_para_buscar)
        self.assertEqual(configuracao.o_que_falta, [])


class AQuantidadeNoCelular(BaseAjuste):
    """A coluna "Comprar" ficava fora do visor no celular (achado em 14/10/2026).

    A tabela rolava de lado (min-width: 46rem) e, num visor de 390 px, quem abria a lista
    de compra pelo telefone via o nome do produto e mais nada: o campo da quantidade, que
    é a razão da tela, estava a seis colunas de distância atrás de uma rolagem lateral que
    ninguém descobre. O Edson perguntou onde a quantidade tinha ido parar.

    O conserto é de CSS — cada linha vira um cartão no estreito —, e CSS teste nenhum
    enxerga. O que dá para travar aqui é o que o CSS precisa encontrar no HTML: a classe
    que liga o cartão e o rótulo de cada número, que no cartão vem escrito ao lado do
    valor porque o cabeçalho da tabela não aparece.
    """

    def setUp(self):
        super().setUp()
        self.produto("1")
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)

    def test_a_tabela_esta_marcada_para_virar_cartao_no_estreito(self):
        corpo = self.client.get(reverse("compras:lista")).content.decode()
        self.assertIn("tabela-de-compra", corpo)

    def test_cada_numero_leva_o_seu_rotulo_junto(self):
        corpo = self.client.get(reverse("compras:lista")).content.decode()
        # A caminho e Mínimo saíram da tabela na 1.40.0 ("muita informação para tomada de
        # decisão rápida") e moram em "Por que este número", dentro do nome.
        for rotulo in ("Tem", "Comprar", "Custo"):
            with self.subTest(rotulo=rotulo):
                self.assertIn(f'data-rotulo="{rotulo}"', corpo)

    def test_a_soma_inteira_cabe_na_mesma_celula(self):
        """Rótulo numa célula e campo em outra, no cartão, viram duas linhas soltas.

        A soma de 20/10/2026 tem três números e um campo: se qualquer parte dela sair da
        célula, no celular ela vira linha solta sem dizer de que produto é.
        """
        corpo = self.client.get(reverse("compras:lista")).content.decode()
        celula = corpo.split('celula-comprar" data-rotulo="Comprar"')[1].split("</td>")[0]
        self.assertIn('name="a_mais"', celula)
        self.assertIn("sugerida", celula)
        self.assertIn("total", celula)
        self.assertIn("Salvar", celula)


class OBotaoDeCimaRespeitaOFiltro(BaseAjuste):
    """Com a tela filtrada por um fornecedor, o botão de cima pedia a lista inteira.

    Achado em 14/10/2026, ao gerar o primeiro pedido pela tela: a tela estava filtrada em
    VIME LENZI, o botão dizia "Gerar o pedido deste fornecedor" (porque conta o que está
    à vista) e o endereço dele não levava o fornecedor. O pedido saía com os fornecedores
    do começo da lista. Até a 1.30.0 isso era uma folha errada; desde a 1.31.0 o botão
    GRAVA, então seriam quatro pedidos de verdade no sistema por um clique.
    """

    def setUp(self):
        super().setUp()
        self.produto("1")
        self.produto("2", fornecedor="VIME LENZI", descricao="CADEIRA DE VIME")
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)

    def _acao_do_botao_de_cima(self, **filtros):
        corpo = self.client.get(reverse("compras:lista"), filtros).content.decode()
        return corpo.split('class="acoes-da-lista"')[1].split('action="')[1].split('"')[0]

    def test_o_endereco_do_botao_leva_o_fornecedor_filtrado(self):
        acao = self._acao_do_botao_de_cima(fornecedor="VIME LENZI")
        self.assertIn("fornecedor=VIME", acao)

    def test_sem_filtro_o_botao_continua_pedindo_o_comeco_da_lista(self):
        acao = self._acao_do_botao_de_cima()
        self.assertIn("fornecedor=&amp;", acao)

    def test_clicar_filtrado_grava_so_o_pedido_daquele_fornecedor(self):
        self.client.post(reverse("compras:pedido_ao_fornecedor"), {}, QUERY_STRING="fornecedor=VIME LENZI")
        self.assertEqual([p.fornecedor for p in Pedido.objects.all()], ["VIME LENZI"])


class OPedidoSaiComAJanelaDaTela(BaseAjuste):
    """O número do papel tem que ser o número da tela, inclusive a janela da média.

    Achado na revisão geral de 15/10/2026. A tela deixa escolher de que período sai a
    média de venda (12 meses, 6 meses, 3 meses, 30 dias). Os dois botões de gerar o
    pedido levavam no endereço o fornecedor e a situação, e não a janela — então a gente
    filtrava por 30 dias, lia COMPRAR 4 na linha, clicava, e saía uma folha de 12 meses
    dizendo COMPRAR 1. Desde a 1.31.0 esse clique não é só uma folha: é pedido gravado no
    sistema, com a folha errada anexada.
    """

    def setUp(self):
        super().setUp()
        # Um por dia nos doze meses; cinco por dia nos últimos trinta.
        self.produto("2", fornecedor="VIME LENZI", descricao="CADEIRA DE VIME",
                     vendas_12m=Decimal("360"), receita_12m=Decimal("9000"))
        for dias in range(0, 28, 2):
            self._vender(CORTE - timedelta(days=dias), "2", 10)
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)

    def _vender(self, quando, codigo, unidades):
        from apps.importacao.models import ItemVendaImportada, VendaImportada

        quantos = VendaImportada.objects.count() + 1
        cabeca = VendaImportada.objects.create(
            importacao=self.importacao, id_set=quantos, numero=str(quantos), data=quando,
            dia_da_semana=(quando.weekday() + 1) % 7, valor=Decimal(unidades) * 25,
        )
        ItemVendaImportada.objects.create(
            venda=cabeca, codigo=codigo, descricao="CADEIRA DE VIME",
            quantidade=Decimal(unidades), valor_total=Decimal(unidades) * 25)

    def _quantidade_na_tela(self, media):
        lista = self.montar(fornecedor="VIME LENZI", media=media)
        return lista.fornecedores[0].itens[0].comprar

    def test_a_janela_curta_muda_mesmo_a_quantidade_da_tela(self):
        """A régua do teste: sem diferença entre as duas janelas ele não provaria nada."""
        self.assertGreater(self._quantidade_na_tela("30"), self._quantidade_na_tela(""))

    def test_o_endereco_dos_dois_botoes_leva_a_janela_escolhida(self):
        corpo = self.client.get(reverse("compras:lista"),
                                {"fornecedor": "VIME LENZI", "media": "30"}).content.decode()
        caminho = reverse("compras:pedido_ao_fornecedor")
        enderecos = [pedaco.split('"')[0] for pedaco in corpo.split('action="')[1:]
                     if pedaco.startswith(caminho)]
        self.assertEqual(len(enderecos), 2, "a tela tem o botão de cima e o do bloco")
        for endereco in enderecos:
            self.assertIn("media=30", endereco)

    def test_o_pedido_gravado_leva_a_quantidade_da_janela_escolhida(self):
        self.client.post(reverse("compras:pedido_ao_fornecedor"), {},
                         QUERY_STRING="fornecedor=VIME LENZI&media=30")
        item = Pedido.objects.get().itens.get(codigo="2")
        self.assertEqual(item.quantidade, self._quantidade_na_tela("30"))
        self.assertNotEqual(item.quantidade, self._quantidade_na_tela(""))


class VoltarDoAjusteGuardaOFiltro(BaseAjuste):
    """Depois de mudar uma quantidade, a pessoa volta para a MESMA lista.

    O formulário do ajuste já mandava a janela num campo escondido, e o redirecionamento
    jogava fora: quem ajustava olhando a média de 30 dias voltava para a lista de doze
    meses, com a linha mostrando outra sugestão — e, como o ajuste guarda a sugestão da
    janela em que foi feito, toda linha ajustada passava a aparecer como "ajuste
    desatualizado".
    """

    def setUp(self):
        super().setUp()
        self.produto("1")
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)

    def test_o_redirecionamento_leva_a_janela_de_volta(self):
        resposta = self.client.post(reverse("compras:ajustar_quantidade"), {
            "codigo": "1", "descricao": "PRODUTO 1", "quantidade": "7",
            "sugerida": "3", "fornecedor": "GERMAN", "situacao": "", "media": "30",
        })
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("media=30", resposta["Location"])
        self.assertIn("fornecedor=GERMAN", resposta["Location"])
