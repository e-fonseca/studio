"""Guardar o pedido, anexar o que voltou dele e abrir as telas.

O pedido do Edson em 14/10/2026: "nos novos pedidos permitir anexar arquivo dos
pedidos e/ou romaneios e nota fiscal (...) para controle futuros".
"""

from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import EventoAuditoria
from apps.compras import ajustes, lista_de_compra as lista_servicos
from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.importacao.models import Importacao, ProdutoImportado
from apps.pedidos import servicos
from apps.pedidos.models import AnexoDoPedido, ItemDoPedido, Pedido
from apps.pedidos.tests.test_leitura import NOTA

CORTE = date(2026, 9, 20)
LIMITE = settings.ANEXO_TAMANHO_MAXIMO


class BasePedido(TestCase):
    def setUp(self):
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO,
            situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(),
            data_corte=CORTE,
            dias_abertos_12m=360,
            produtos=0,
        )
        ProdutoImportado.objects.create(
            importacao=self.importacao, codigo="0001", descricao="CADEIRA DE VIME NATURAL",
            codigo_barras="7891234567895", grupo="MOVEL", fornecedor="VIME LENZI",
            custo=Decimal("85"), preco_venda=Decimal("190"), estoque=Decimal("0"),
            vendas_12m=Decimal("360"), receita_12m=Decimal("68400"),
        )
        self.gerente = usuario("gerente", ADMINISTRACAO)

    def bloco(self, fornecedor="VIME LENZI"):
        lista = lista_servicos.montar(self.importacao, fornecedor=fornecedor)
        return lista.fornecedores[0]

    def um_pedido(self):
        return servicos.registrar_pedido(self.gerente, self.bloco(), data_corte=CORTE)

    def entrar(self, perfil=ADMINISTRACAO, nome="edson"):
        usuario(nome, perfil)
        self.client.login(username=nome, password=SENHA_TESTE)


class RegistrarPedidoTest(BasePedido):
    def test_guarda_as_linhas_como_estavam_no_dia(self):
        pedido = self.um_pedido()
        self.assertEqual(pedido.numero, 1)
        self.assertEqual(pedido.fornecedor, "VIME LENZI")
        self.assertEqual(pedido.data_corte, CORTE)
        self.assertEqual(pedido.situacao, Pedido.Situacao.ABERTO)
        item = pedido.itens.get()
        self.assertEqual(item.codigo, "0001")
        self.assertEqual(item.codigo_barras, "7891234567895")
        self.assertEqual(item.custo, Decimal("85"))
        self.assertGreater(item.quantidade, 0)
        self.assertEqual(pedido.valor_total, item.valor)

    def test_a_sincronizacao_nao_mexe_no_pedido_guardado(self):
        """É a razão de existir da tabela: a lista de compra muda, o pedido não."""
        pedido = self.um_pedido()
        antes = pedido.itens.get().quantidade
        ProdutoImportado.objects.filter(codigo="0001").update(estoque=Decimal("999"))
        pedido.refresh_from_db()
        self.assertEqual(pedido.itens.get().quantidade, antes)

    def test_numero_cresce_e_nao_se_repete(self):
        self.um_pedido()
        ProdutoImportado.objects.create(
            importacao=self.importacao, codigo="0009", descricao="MESA",
            grupo="MOVEL", fornecedor="GERMAN", custo=Decimal("10"),
            preco_venda=Decimal("30"), estoque=Decimal("0"), vendas_12m=Decimal("360"),
            receita_12m=Decimal("10800"))
        segundo = servicos.registrar_pedido(self.gerente, self.bloco("GERMAN"), data_corte=CORTE)
        self.assertEqual(segundo.numero, 2)

    def test_reimprimir_no_mesmo_dia_nao_cria_outro_pedido(self):
        """Imprimir para conferir e imprimir para mandar não são dois pedidos."""
        primeiro = self.um_pedido()
        segundo = self.um_pedido()
        self.assertEqual(primeiro.pk, segundo.pk)
        self.assertEqual(Pedido.objects.count(), 1)

    def test_mudar_a_quantidade_faz_um_pedido_novo(self):
        primeiro = self.um_pedido()
        sugerida = primeiro.itens.get().quantidade
        ajustes.salvar(codigo="0001", a_mais="3", sugerida=sugerida)
        segundo = servicos.registrar_pedido(self.gerente, self.bloco(), data_corte=CORTE)
        self.assertNotEqual(primeiro.pk, segundo.pk)
        self.assertEqual(segundo.itens.get().quantidade, sugerida + 3)
        self.assertTrue(segundo.itens.get().escolhida_a_mao)

    def test_pedido_de_ontem_nao_e_reaproveitado(self):
        ontem = timezone.now() - timedelta(days=1)
        primeiro = self.um_pedido()
        Pedido.objects.filter(pk=primeiro.pk).update(criado_em=ontem)
        segundo = servicos.registrar_pedido(self.gerente, self.bloco(), data_corte=CORTE)
        self.assertNotEqual(primeiro.pk, segundo.pk)

    def test_tudo_em_zero_nao_vira_pedido(self):
        ajustes.salvar(codigo="0001", a_mais="", sugerida=Decimal("10"),
                       nao_comprar=True)
        with self.assertRaises(servicos.NaoDeuCerto):
            servicos.registrar_pedido(self.gerente, self.bloco(), data_corte=CORTE)

    def test_registra_na_auditoria(self):
        self.um_pedido()
        self.assertTrue(EventoAuditoria.objects.filter(acao="pedido.registrado").exists())


class AnexarTest(BasePedido):
    def arquivo(self, nome="nota.xml", dados=None):
        return SimpleUploadedFile(nome, dados if dados is not None else NOTA.encode("utf-8"))

    def test_guarda_a_nota_e_le_o_que_tem_dentro(self):
        pedido = self.um_pedido()
        anexo = servicos.anexar(self.gerente, pedido, self.arquivo(),
                                tipo=AnexoDoPedido.Tipo.NOTA_FISCAL, tamanho_maximo=LIMITE)
        self.assertEqual(anexo.documento, "nfe")
        self.assertEqual(anexo.numero_do_documento, "1234")
        self.assertEqual(anexo.emitente, "VIME LENZI INDUSTRIA LTDA")
        self.assertEqual(anexo.valor_do_documento, Decimal("1330.00"))
        self.assertEqual(len(anexo.itens_lidos), 2)
        self.assertTrue(anexo.foi_lido)

    def test_o_mesmo_arquivo_duas_vezes_e_recusado(self):
        pedido = self.um_pedido()
        servicos.anexar(self.gerente, pedido, self.arquivo(),
                        tipo=AnexoDoPedido.Tipo.NOTA_FISCAL, tamanho_maximo=LIMITE)
        with self.assertRaises(servicos.NaoDeuCerto) as erro:
            servicos.anexar(self.gerente, pedido, self.arquivo(),
                            tipo=AnexoDoPedido.Tipo.NOTA_FISCAL, tamanho_maximo=LIMITE)
        self.assertIn("já está anexado", str(erro.exception))

    def test_pdf_fica_guardado_mesmo_sem_poder_ser_lido(self):
        """Guardar é metade do pedido: o que não foi lido vira recado, não arquivo perdido."""
        pedido = self.um_pedido()
        anexo = servicos.anexar(self.gerente, pedido, self.arquivo("nota.pdf", b"%PDF-1.7\nabc"),
                                tipo=AnexoDoPedido.Tipo.NOTA_FISCAL, tamanho_maximo=LIMITE)
        self.assertEqual(anexo.itens_lidos, [])
        self.assertIn("XML", anexo.erro_de_leitura)
        self.assertTrue(anexo.arquivo.name)

    def test_tipo_inventado_e_recusado(self):
        pedido = self.um_pedido()
        with self.assertRaises(servicos.NaoDeuCerto):
            servicos.anexar(self.gerente, pedido, self.arquivo(), tipo="qualquer",
                            tamanho_maximo=LIMITE)

    def test_arquivo_que_nao_e_documento_e_recusado(self):
        pedido = self.um_pedido()
        with self.assertRaises(servicos.NaoDeuCerto):
            servicos.anexar(self.gerente, pedido, self.arquivo("vírus.exe", b"MZ"),
                            tipo=AnexoDoPedido.Tipo.NOTA_FISCAL, tamanho_maximo=LIMITE)

    def test_registra_na_auditoria(self):
        pedido = self.um_pedido()
        servicos.anexar(self.gerente, pedido, self.arquivo(),
                        tipo=AnexoDoPedido.Tipo.ROMANEIO, tamanho_maximo=LIMITE)
        self.assertTrue(EventoAuditoria.objects.filter(acao="pedido.anexo_enviado").exists())


class ContasDaTelaTest(BasePedido):
    def test_em_aberto_e_sem_documento(self):
        pedido = self.um_pedido()
        self.assertEqual(servicos.em_aberto(), 1)
        self.assertEqual(servicos.sem_documento(), 0)
        servicos.marcar_recebido(self.gerente, pedido)
        self.assertEqual(servicos.em_aberto(), 0)
        self.assertEqual(servicos.sem_documento(), 1)

    def test_recebido_com_nota_sai_da_fila_do_papel(self):
        pedido = self.um_pedido()
        servicos.marcar_recebido(self.gerente, pedido)
        servicos.anexar(self.gerente, pedido, SimpleUploadedFile("nota.xml", NOTA.encode("utf-8")),
                        tipo=AnexoDoPedido.Tipo.NOTA_FISCAL, tamanho_maximo=LIMITE)
        self.assertEqual(servicos.sem_documento(), 0)

    def test_a_folha_do_pedido_nao_conta_como_documento_do_fornecedor(self):
        """O PDF que a loja mandou é nosso; o que falta é o papel que veio com a carga."""
        pedido = self.um_pedido()
        servicos.marcar_recebido(self.gerente, pedido)
        AnexoDoPedido.objects.create(
            pedido=pedido, tipo=AnexoDoPedido.Tipo.PEDIDO, nome_original="pedido.pdf",
            extensao="pdf", tamanho=10, sha256="b" * 64)
        self.assertEqual(servicos.sem_documento(), 1)


class TelasTest(BasePedido):
    def test_a_lista_mostra_o_pedido(self):
        self.um_pedido()
        self.entrar()
        pagina = self.client.get(reverse("pedidos:lista"))
        self.assertContains(pagina, "VIME LENZI")
        self.assertContains(pagina, "esperando a mercadoria")

    def test_a_lista_vazia_explica_de_onde_vem_pedido(self):
        self.entrar()
        self.assertContains(self.client.get(reverse("pedidos:lista")), "Nenhum pedido guardado")

    def test_a_tela_do_pedido_mostra_o_que_foi_pedido(self):
        pedido = self.um_pedido()
        self.entrar()
        pagina = self.client.get(reverse("pedidos:detalhe", args=[pedido.numero]))
        self.assertContains(pagina, "CADEIRA DE VIME NATURAL")
        self.assertContains(pagina, "7891234567895")

    def test_a_conferencia_vira_cartao_no_celular(self):
        """A coluna que DECIDE é a última, e no celular ela sairia do visor.

        Mesmo defeito da lista de compra na 1.30.0: tabela de seis colunas dentro de um
        quadro que rola de lado, num visor de 390 px, mostra o nome do produto e esconde
        "O que diz" — que é a razão da tela. O conserto é de CSS; o que dá para travar
        aqui é o que o CSS procura no HTML.
        """
        pedido = self.um_pedido()
        servicos.anexar(self.gerente, pedido, SimpleUploadedFile("nota.xml", NOTA.encode("utf-8")),
                        tipo=AnexoDoPedido.Tipo.NOTA_FISCAL, tamanho_maximo=LIMITE)
        self.entrar()
        corpo = self.client.get(reverse("pedidos:detalhe", args=[pedido.numero])).content.decode()
        self.assertIn("tabela-de-conferencia", corpo)
        for rotulo in ("Produto", "Pedido", "No documento", "O que diz"):
            with self.subTest(rotulo=rotulo):
                self.assertIn(f'data-rotulo="{rotulo}"', corpo)

    def test_a_lista_de_pedidos_vira_cartao_no_celular(self):
        self.um_pedido()
        self.entrar()
        corpo = self.client.get(reverse("pedidos:lista")).content.decode()
        self.assertIn("tabela-de-pedidos", corpo)
        for rotulo in ("Pedido", "Fornecedor", "Situação", "Documentos"):
            with self.subTest(rotulo=rotulo):
                self.assertIn(f'data-rotulo="{rotulo}"', corpo)

    def test_a_tela_do_pedido_mostra_a_conferencia_da_nota(self):
        pedido = self.um_pedido()
        servicos.anexar(self.gerente, pedido, SimpleUploadedFile("nota.xml", NOTA.encode("utf-8")),
                        tipo=AnexoDoPedido.Tipo.NOTA_FISCAL, tamanho_maximo=LIMITE)
        self.entrar()
        pagina = self.client.get(reverse("pedidos:detalhe", args=[pedido.numero]))
        self.assertContains(pagina, "Conferência contra o pedido")
        self.assertContains(pagina, "VIME LENZI INDUSTRIA LTDA")
        # A nota traz 10 cadeiras e a loja pediu outra quantidade: a tela cobra.
        self.assertContains(pagina, "Confira")

    def test_anexar_pela_tela_guarda_e_avisa(self):
        pedido = self.um_pedido()
        self.entrar()
        resposta = self.client.post(reverse("pedidos:anexar", args=[pedido.numero]), {
            "arquivo": SimpleUploadedFile("nota.xml", NOTA.encode("utf-8")),
            "tipo": AnexoDoPedido.Tipo.NOTA_FISCAL,
        }, follow=True)
        self.assertEqual(pedido.anexos.count(), 1)
        self.assertContains(resposta, "nota.xml")

    def test_anexar_sem_escolher_arquivo_diz_o_que_falta(self):
        pedido = self.um_pedido()
        self.entrar()
        resposta = self.client.post(reverse("pedidos:anexar", args=[pedido.numero]), {
            "tipo": AnexoDoPedido.Tipo.NOTA_FISCAL}, follow=True)
        self.assertContains(resposta, "Escolha o arquivo")

    def test_baixar_o_anexo_registra_quem_baixou(self):
        pedido = self.um_pedido()
        anexo = servicos.anexar(self.gerente, pedido,
                                SimpleUploadedFile("nota.xml", NOTA.encode("utf-8")),
                                tipo=AnexoDoPedido.Tipo.NOTA_FISCAL, tamanho_maximo=LIMITE)
        self.entrar()
        resposta = self.client.get(reverse("pedidos:baixar", args=[pedido.numero, anexo.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["Content-Security-Policy"], "default-src 'none'")
        self.assertTrue(EventoAuditoria.objects.filter(acao="pedido.anexo_baixado").exists())

    def test_anexo_de_outro_pedido_nao_abre_pelo_endereco(self):
        primeiro = self.um_pedido()
        anexo = servicos.anexar(self.gerente, primeiro,
                                SimpleUploadedFile("nota.xml", NOTA.encode("utf-8")),
                                tipo=AnexoDoPedido.Tipo.NOTA_FISCAL, tamanho_maximo=LIMITE)
        outro = Pedido.objects.create(numero=99, fornecedor="GERMAN")
        self.entrar()
        self.assertEqual(
            self.client.get(reverse("pedidos:baixar", args=[outro.numero, anexo.pk])).status_code,
            404)

    def test_marcar_recebido_pela_tela(self):
        pedido = self.um_pedido()
        self.entrar()
        self.client.post(reverse("pedidos:receber", args=[pedido.numero]), {"recebido": "1"})
        pedido.refresh_from_db()
        self.assertEqual(pedido.situacao, Pedido.Situacao.RECEBIDO)
        self.assertIsNotNone(pedido.recebido_em)

    def test_o_administrativo_anexa_porque_e_quem_recebe_a_mercadoria(self):
        pedido = self.um_pedido()
        self.entrar(ADMINISTRATIVO, nome="moizes")
        resposta = self.client.post(reverse("pedidos:anexar", args=[pedido.numero]), {
            "arquivo": SimpleUploadedFile("nota.xml", NOTA.encode("utf-8")),
            "tipo": AnexoDoPedido.Tipo.NOTA_FISCAL,
        })
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(pedido.anexos.count(), 1)

    def test_o_vendedor_nao_entra_em_tela_nenhuma_de_pedido(self):
        pedido = self.um_pedido()
        self.entrar(VENDEDOR, nome="balcao")
        for endereco in (reverse("pedidos:lista"),
                         reverse("pedidos:detalhe", args=[pedido.numero]),
                         reverse("pedidos:anexar", args=[pedido.numero])):
            self.assertEqual(self.client.get(endereco).status_code, 403, endereco)


class DaListaDeCompraParaOPedidoTest(BasePedido):
    """O botão da lista de compra: POST faz o pedido, GET só reimprime a folha."""

    def test_post_guarda_o_pedido_com_a_folha_anexada(self):
        self.client.login(username="gerente", password=SENHA_TESTE)
        resposta = self.client.post(reverse("compras:pedido_ao_fornecedor"),
                                    {"fornecedor": "VIME LENZI"})
        self.assertEqual(resposta["Content-Type"], "application/pdf")
        pedido = Pedido.objects.get()
        self.assertEqual(pedido.fornecedor, "VIME LENZI")
        folha = pedido.anexos.get()
        self.assertEqual(folha.tipo, AnexoDoPedido.Tipo.PEDIDO)
        self.assertTrue(folha.nome_original.startswith("pedido-vime-lenzi"))

    def test_get_continua_so_reimprimindo(self):
        self.client.login(username="gerente", password=SENHA_TESTE)
        resposta = self.client.get(reverse("compras:pedido_ao_fornecedor"),
                                   {"fornecedor": "VIME LENZI"})
        self.assertEqual(resposta["Content-Type"], "application/pdf")
        self.assertEqual(Pedido.objects.count(), 0)

    def test_quem_nao_pode_registrar_pedido_ainda_leva_a_folha(self):
        """O administrativo leva o papel ao fornecedor; quem compromete dinheiro é a gerência."""
        self.entrar(ADMINISTRATIVO, nome="moizes")
        resposta = self.client.post(reverse("compras:pedido_ao_fornecedor"),
                                    {"fornecedor": "VIME LENZI"})
        self.assertEqual(resposta["Content-Type"], "application/pdf")
        self.assertEqual(Pedido.objects.count(), 0)

    def test_um_pedido_por_fornecedor_quando_sai_o_maco_inteiro(self):
        ProdutoImportado.objects.create(
            importacao=self.importacao, codigo="0009", descricao="MESA",
            grupo="MOVEL", fornecedor="GERMAN", custo=Decimal("10"),
            preco_venda=Decimal("30"), estoque=Decimal("0"), vendas_12m=Decimal("360"),
            receita_12m=Decimal("10800"))
        self.client.login(username="gerente", password=SENHA_TESTE)
        self.client.post(reverse("compras:pedido_ao_fornecedor"))
        self.assertEqual(Pedido.objects.count(), 2)
        for pedido in Pedido.objects.all():
            folha = pedido.anexos.get()
            # Cada pedido leva a folha DELE, não o maço com os dois fornecedores.
            self.assertIn(pedido.fornecedor.split()[0].lower(), folha.nome_original.lower())
