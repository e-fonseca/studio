"""Conferir o documento do fornecedor contra o que a loja pediu."""

from decimal import Decimal

from django.test import TestCase

from apps.pedidos import conferencia as conferir
from apps.pedidos.models import AnexoDoPedido, ItemDoPedido, Pedido


def item_lido(**campos):
    base = {"codigo": "", "codigo_barras": "", "descricao": "",
            "quantidade": "", "unitario": "", "total": ""}
    base.update({chave: str(valor) for chave, valor in campos.items()})
    return base


class BaseConferencia(TestCase):
    def setUp(self):
        self.pedido = Pedido.objects.create(numero=1, fornecedor="VIME LENZI")
        ItemDoPedido.objects.create(
            pedido=self.pedido, codigo="0001", codigo_barras="7891234567895",
            descricao="CADEIRA DE VIME NATURAL", quantidade=Decimal("10"),
            custo=Decimal("85"), valor=Decimal("850"))
        ItemDoPedido.objects.create(
            pedido=self.pedido, codigo="0002", descricao="MESA DE VIME",
            quantidade=Decimal("2"), custo=Decimal("240"), valor=Decimal("480"))

    def anexo(self, itens, valor=None):
        return AnexoDoPedido(
            pedido=self.pedido, tipo=AnexoDoPedido.Tipo.NOTA_FISCAL,
            nome_original="nota.xml", extensao="xml", tamanho=100, sha256="a" * 64,
            documento="nfe", itens_lidos=itens, valor_do_documento=valor)


class CasarALinhaTest(BaseConferencia):
    """O código do produto na nota é o DO FORNECEDOR: a ponte é o código de barras."""

    def test_casa_pelo_codigo_de_barras_mesmo_com_codigo_diferente(self):
        anexo = self.anexo([item_lido(codigo="VL-100", codigo_barras="7891234567895",
                                      descricao="CADEIRA VIME", quantidade=10, unitario=85)])
        resultado = conferir.conferir(self.pedido, anexo)
        linha = next(l for l in resultado.linhas if l.codigo == "0001")
        self.assertEqual(linha.como, conferir.Como.BARRAS)
        self.assertTrue(linha.confere)

    def test_casa_pelo_codigo_quando_o_fornecedor_usa_o_da_loja(self):
        anexo = self.anexo([item_lido(codigo="0002", descricao="MESA", quantidade=2, unitario=240)])
        linha = next(l for l in conferir.conferir(self.pedido, anexo).linhas if l.codigo == "0002")
        self.assertEqual(linha.como, conferir.Como.CODIGO)
        self.assertTrue(linha.confere)

    def test_casa_pela_descricao_e_marca_que_foi_por_ela(self):
        anexo = self.anexo([item_lido(codigo="X9", descricao="mesa de vime",
                                      quantidade=2, unitario=240)])
        linha = next(l for l in conferir.conferir(self.pedido, anexo).linhas if l.codigo == "0002")
        self.assertEqual(linha.como, conferir.Como.DESCRICAO)
        self.assertIn("confira", linha.rotulo_do_casamento)

    def test_descricao_repetida_no_pedido_nao_casa_por_nome(self):
        """Dois produtos com o mesmo nome casariam no primeiro: palpite calado, não."""
        ItemDoPedido.objects.create(pedido=self.pedido, codigo="0003",
                                    descricao="MESA DE VIME", quantidade=Decimal("1"),
                                    custo=Decimal("240"), valor=Decimal("240"))
        anexo = self.anexo([item_lido(codigo="X9", descricao="MESA DE VIME", quantidade=2)])
        resultado = conferir.conferir(self.pedido, anexo)
        sobrando = [l for l in resultado.linhas if l.quantidade_pedida is None]
        self.assertEqual(len(sobrando), 1)

    def test_duas_linhas_da_nota_para_o_mesmo_produto_somam(self):
        """Nota com lote ou validade repete o produto; o que confere é a soma."""
        anexo = self.anexo([
            item_lido(codigo_barras="7891234567895", descricao="CADEIRA", quantidade=6, unitario=85),
            item_lido(codigo_barras="7891234567895", descricao="CADEIRA", quantidade=4, unitario=85),
        ])
        linha = next(l for l in conferir.conferir(self.pedido, anexo).linhas if l.codigo == "0001")
        self.assertEqual(linha.quantidade_lida, Decimal("10"))
        self.assertTrue(linha.quantidade_bate)


class OQueADivergenciaDizTest(BaseConferencia):
    def test_quantidade_a_mais_e_a_menos(self):
        anexo = self.anexo([
            item_lido(codigo_barras="7891234567895", quantidade=12, unitario=85),
            item_lido(codigo="0002", quantidade=1, unitario=240),
        ])
        resultado = conferir.conferir(self.pedido, anexo)
        por_codigo = {l.codigo: l for l in resultado.linhas}
        self.assertEqual(por_codigo["0001"].situacao, "veio mais do que o pedido")
        self.assertEqual(por_codigo["0001"].diferenca_de_quantidade, Decimal("2"))
        self.assertEqual(por_codigo["0002"].situacao, "veio menos do que o pedido")
        self.assertIn("2 com quantidade diferente", resultado.resumo)

    def test_item_pedido_que_nao_veio_na_nota(self):
        anexo = self.anexo([item_lido(codigo="0002", quantidade=2, unitario=240)])
        resultado = conferir.conferir(self.pedido, anexo)
        linha = next(l for l in resultado.linhas if l.codigo == "0001")
        self.assertEqual(linha.situacao, "pedido e não veio")
        self.assertIn("1 pedido e não veio", resultado.resumo)

    def test_item_na_nota_que_ninguem_pediu(self):
        anexo = self.anexo([
            item_lido(codigo_barras="7891234567895", quantidade=10, unitario=85),
            item_lido(codigo="0002", quantidade=2, unitario=240),
            item_lido(codigo="VL-999", descricao="BANCO QUE NINGUEM PEDIU", quantidade=3, unitario=50),
        ])
        resultado = conferir.conferir(self.pedido, anexo)
        linha = next(l for l in resultado.linhas if l.descricao == "BANCO QUE NINGUEM PEDIU")
        self.assertEqual(linha.situacao, "veio sem ter sido pedido")
        self.assertIn("1 veio sem ter sido pedido", resultado.resumo)

    def test_preco_acima_da_referencia_aparece_com_a_porcentagem(self):
        anexo = self.anexo([
            item_lido(codigo_barras="7891234567895", quantidade=10, unitario=100),
            item_lido(codigo="0002", quantidade=2, unitario=240),
        ])
        resultado = conferir.conferir(self.pedido, anexo)
        linha = next(l for l in resultado.linhas if l.codigo == "0001")
        self.assertTrue(linha.preco_subiu)
        self.assertEqual(round(linha.diferenca_de_preco), Decimal("18"))
        self.assertIn("preço acima da referência", resultado.resumo)

    def test_centavo_de_preco_nao_vira_divergencia(self):
        """Tolerância existe para a gerência não aprender a ignorar o aviso."""
        anexo = self.anexo([
            item_lido(codigo_barras="7891234567895", quantidade=10, unitario="85.50"),
            item_lido(codigo="0002", quantidade=2, unitario=240),
        ])
        resultado = conferir.conferir(self.pedido, anexo)
        self.assertTrue(all(l.confere for l in resultado.linhas))

    def test_tudo_certo_diz_que_confere(self):
        anexo = self.anexo([
            item_lido(codigo_barras="7891234567895", quantidade=10, unitario=85),
            item_lido(codigo="0002", quantidade=2, unitario=240),
        ], valor=Decimal("1330"))
        resultado = conferir.conferir(self.pedido, anexo)
        self.assertTrue(resultado.tudo_confere)
        self.assertEqual(resultado.resumo, "As 2 linhas conferem com o pedido.")

    def test_divergencia_vem_em_cima_da_lista(self):
        anexo = self.anexo([
            item_lido(codigo_barras="7891234567895", quantidade=10, unitario=85),
            item_lido(codigo="0002", quantidade=5, unitario=240),
        ])
        resultado = conferir.conferir(self.pedido, anexo)
        self.assertFalse(resultado.linhas[0].confere)


class OTotalDoDocumentoTest(BaseConferencia):
    def test_total_diferente_entra_no_resumo(self):
        anexo = self.anexo([
            item_lido(codigo_barras="7891234567895", quantidade=10, unitario=85),
            item_lido(codigo="0002", quantidade=2, unitario=240),
        ], valor=Decimal("1500"))
        resultado = conferir.conferir(self.pedido, anexo)
        self.assertFalse(resultado.valor_bate)
        self.assertEqual(resultado.diferenca_de_valor, Decimal("170"))
        self.assertIn("total diferente do pedido", resultado.resumo)

    def test_um_centavo_de_arredondamento_nao_e_divergencia(self):
        anexo = self.anexo([
            item_lido(codigo_barras="7891234567895", quantidade=10, unitario=85),
            item_lido(codigo="0002", quantidade=2, unitario=240),
        ], valor=Decimal("1330.01"))
        self.assertTrue(conferir.conferir(self.pedido, anexo).valor_bate)

    def test_documento_sem_total_nao_inventa_divergencia(self):
        anexo = self.anexo([item_lido(codigo="0002", quantidade=2, unitario=240)])
        self.assertTrue(conferir.conferir(self.pedido, anexo).valor_bate)


class SemNadaParaConferirTest(BaseConferencia):
    def test_documento_que_nao_foi_lido_devolve_o_aviso(self):
        anexo = self.anexo([])
        anexo.erro_de_leitura = "PDF é o retrato da nota."
        resultado = conferir.conferir(self.pedido, anexo)
        self.assertFalse(resultado.tem_resultado)
        self.assertEqual(resultado.resumo, "PDF é o retrato da nota.")
