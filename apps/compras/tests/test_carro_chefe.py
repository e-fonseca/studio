"""O alerta de 30% e o carro-chefe da loja (1.40.0).

Pedido do Edson em 22/10/2026: "deixar como padrão alerta de 30% para cada produto no
estoque e destacar para os produtos mais vendidos, carro chefe da loja".
"""

from decimal import Decimal

from django.urls import reverse

from apps.auditoria.models import EventoAuditoria
from apps.compras import politica
from apps.compras.models import PoliticaDeCompra
from apps.compras.tests.test_lista_de_compra import BaseLista
from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario


def regra(alerta, carros):
    PoliticaDeCompra.objects.update_or_create(
        pk=1, defaults={"alerta_percentual": alerta, "carros_chefe": carros})


class APorcentagemDoIdeal(BaseLista):
    def test_metade_do_ideal_e_cinquenta(self):
        self.assertEqual(politica.porcentagem_do_ideal(Decimal("5"), Decimal("10")), 50)

    def test_saldo_negativo_conta_como_zero(self):
        """Na prateleira não existe -20: o alerta usa a mesma régua da compra."""
        self.assertEqual(politica.porcentagem_do_ideal(Decimal("-20"), Decimal("10")), 0)

    def test_sem_ideal_nao_tem_porcentagem(self):
        """Produto que não vende não tem 100%, e 0% de nada não é alerta."""
        self.assertIsNone(politica.porcentagem_do_ideal(Decimal("3"), Decimal("0")))
        self.assertIsNone(politica.porcentagem_do_ideal(Decimal("3"), None))

    def test_o_limite_entra_no_alerta(self):
        self.assertTrue(politica.em_alerta(30, 30))
        self.assertFalse(politica.em_alerta(31, 30))
        self.assertFalse(politica.em_alerta(None, 30))


class OPadrao(BaseLista):
    def test_nasce_com_trinta_por_cento_e_cem_carros_chefe(self):
        regra = PoliticaDeCompra.atual()
        self.assertEqual(regra.alerta_percentual, 30)
        self.assertEqual(regra.carros_chefe, 100)

    def test_existe_uma_regra_so(self):
        PoliticaDeCompra.atual()
        PoliticaDeCompra.atual()
        self.assertEqual(PoliticaDeCompra.objects.count(), 1)


class QuemEOCarroChefe(BaseLista):
    def test_e_quem_mais_faturou_e_nao_quem_mais_vendeu_em_unidades(self):
        """O dinheiro que a falta deixa de trazer é o que conta."""
        self.produto("barato", vendas_12m=Decimal("900"), receita_12m=Decimal("900"))
        self.produto("caro", vendas_12m=Decimal("10"), receita_12m=Decimal("9000"))
        self.assertEqual(politica.carros_chefe(self.importacao, 1), ["caro"])

    def test_diversos_nao_e_carro_chefe(self):
        self.produto("1", descricao="DIVERSOS", receita_12m=Decimal("99999"))
        self.produto("2", receita_12m=Decimal("10"))
        self.assertEqual(politica.carros_chefe(self.importacao, 5), ["2"])

    def test_sem_foto_nao_ha_carro_chefe(self):
        self.assertEqual(politica.carros_chefe(None, 100), [])


class NaLista(BaseLista):
    def test_o_carro_chefe_vem_primeiro_no_fornecedor_mesmo_custando_menos(self):
        regra(30, 1)
        self.produto("chefe", custo=Decimal("1"), receita_12m=Decimal("90000"))
        self.produto("caro", custo=Decimal("500"), receita_12m=Decimal("100"))
        itens = self.montar().fornecedores[0].itens
        self.assertEqual([i.codigo for i in itens], ["chefe", "caro"])
        self.assertTrue(itens[0].carro_chefe)
        self.assertFalse(itens[1].carro_chefe)

    def test_carro_chefe_zerado_esta_em_alerta_e_entra_no_cartao(self):
        self.produto("1")
        lista = self.montar()
        item = lista.fornecedores[0].itens[0]
        self.assertEqual(item.porcentagem_do_ideal, 0)
        self.assertTrue(item.em_alerta)
        self.assertEqual([i.codigo for i in lista.carros_chefe_em_alerta], ["1"])
        self.assertEqual(lista.em_alerta, 1)

    def test_o_que_esta_acima_do_alerta_nao_entra_no_cartao(self):
        """Na lista porque precisa comprar, mas ainda longe de faltar."""
        self.produto("1", estoque=Decimal("20"))
        lista = self.montar()
        item = lista.fornecedores[0].itens[0]
        self.assertGreater(item.porcentagem_do_ideal, 30)
        self.assertFalse(item.em_alerta)
        self.assertEqual(lista.carros_chefe_em_alerta, [])

    def test_mudar_o_alerta_muda_quem_entra(self):
        self.produto("1", estoque=Decimal("20"))
        porcentagem = self.montar().fornecedores[0].itens[0].porcentagem_do_ideal
        regra(min(90, porcentagem), 100)
        self.assertEqual(len(self.montar().carros_chefe_em_alerta), 1)

    def test_o_alerta_nao_muda_quanto_comprar(self):
        self.produto("1")
        antes = self.montar().fornecedores[0].itens[0].quantidade
        regra(90, 10)
        self.assertEqual(self.montar().fornecedores[0].itens[0].quantidade, antes)

    def test_o_cartao_respeita_o_filtro_de_fornecedor(self):
        self.produto("1", fornecedor="GERMAN")
        self.produto("2", fornecedor="OUTRO")
        lista = self.montar(fornecedor="OUTRO")
        self.assertEqual([i.codigo for i in lista.carros_chefe_em_alerta], ["2"])


class ATela(BaseLista):
    def setUp(self):
        super().setUp()
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)

    def test_o_cartao_vem_antes_do_comece_por(self):
        self.produto("1")
        corpo = self.client.get(reverse("compras:lista")).content.decode()
        self.assertIn("Carros-chefe no estoque mínimo", corpo)
        self.assertLess(corpo.index('id="carros-chefe"'), corpo.index("cartao-destaque"))

    def test_o_produto_do_cartao_leva_a_linha_onde_a_quantidade_muda(self):
        self.produto("1")
        corpo = self.client.get(reverse("compras:lista")).content.decode()
        self.assertIn("?fornecedor=GERMAN#produto-1", corpo)
        self.assertIn('id="produto-1"', corpo)

    def test_a_linha_do_carro_chefe_vem_marcada(self):
        self.produto("1")
        corpo = self.client.get(reverse("compras:lista")).content.decode()
        self.assertIn('class="linha-carro-chefe"', corpo)
        self.assertIn("selo-carro-chefe", corpo)

    def test_sem_carro_chefe_em_alerta_o_cartao_diz_isso(self):
        self.produto("1", estoque=Decimal("20"))
        corpo = self.client.get(reverse("compras:lista")).content.decode()
        self.assertIn("Nenhum dos 100 produtos que mais faturam", corpo)

    def test_a_gerencia_ve_onde_mudar_a_regra(self):
        self.produto("1")
        corpo = self.client.get(reverse("compras:lista")).content.decode()
        self.assertIn(reverse("compras:politica"), corpo)


class MudarARegra(BaseLista):
    def setUp(self):
        super().setUp()
        self.gerente = usuario("gerente", ADMINISTRACAO)

    def postar(self, **dados):
        return self.client.post(reverse("compras:politica"), dados)

    def test_a_gerencia_muda_e_fica_na_auditoria(self):
        self.client.login(username="gerente", password=SENHA_TESTE)
        resposta = self.postar(alerta_percentual="25", carros_chefe="50")
        self.assertRedirects(resposta, reverse("compras:lista") + "#carros-chefe",
                             fetch_redirect_response=False)
        regra = PoliticaDeCompra.atual()
        self.assertEqual((regra.alerta_percentual, regra.carros_chefe), (25, 50))
        self.assertEqual(regra.atualizado_por, self.gerente)
        evento = EventoAuditoria.objects.get(acao="compras.politica_alterada")
        self.assertEqual(evento.antes, {"alerta_percentual": 30, "carros_chefe": 100})
        self.assertEqual(evento.depois, {"alerta_percentual": 25, "carros_chefe": 50})

    def test_numero_fora_da_faixa_vem_para_dentro(self):
        self.client.login(username="gerente", password=SENHA_TESTE)
        self.postar(alerta_percentual="0", carros_chefe="99999")
        regra = PoliticaDeCompra.atual()
        self.assertEqual(regra.alerta_percentual, PoliticaDeCompra.ALERTA_MINIMO)
        self.assertEqual(regra.carros_chefe, PoliticaDeCompra.CARROS_MAXIMO)

    def test_texto_no_lugar_do_numero_mantem_o_que_estava(self):
        self.client.login(username="gerente", password=SENHA_TESTE)
        self.postar(alerta_percentual="trinta", carros_chefe="")
        regra = PoliticaDeCompra.atual()
        self.assertEqual((regra.alerta_percentual, regra.carros_chefe), (30, 100))

    def test_salvar_sem_mudar_nada_nao_suja_a_auditoria(self):
        self.client.login(username="gerente", password=SENHA_TESTE)
        self.postar(alerta_percentual="30", carros_chefe="100")
        self.assertFalse(EventoAuditoria.objects.filter(acao="compras.politica_alterada").exists())

    def test_quem_nao_muda_quantidade_nao_muda_a_regra(self):
        for nome, perfil in (("vendedor", VENDEDOR), ("operador", ADMINISTRATIVO)):
            with self.subTest(perfil=perfil):
                usuario(nome, perfil)
                self.client.login(username=nome, password=SENHA_TESTE)
                resposta = self.postar(alerta_percentual="80", carros_chefe="10")
                self.assertEqual(resposta.status_code, 403)
                self.assertEqual(PoliticaDeCompra.atual().alerta_percentual, 30)

    def test_so_por_post(self):
        self.client.login(username="gerente", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("compras:politica")).status_code, 405)
