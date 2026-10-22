"""Antes de comprar: o teto do mês, o que a compra virou e o veredito por produto."""

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.compras import limite
from apps.contas.perfis import ADMINISTRACAO, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.fornecedores.models import Fornecedor
from apps.importacao.models import Importacao, ProdutoImportado


class BaseCompra(TestCase):
    def setUp(self):
        self.corte = date(2026, 9, 20)
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO,
            situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(),
            data_corte=self.corte,
            dias_abertos_12m=300,
            produtos=3,
            detalhe={"compras_mes": [[2026, 8, 5000.0, 9], [2026, 9, 1200.0, 4]]},
        )
        # Gira bem: vendeu 300 a 10 de custo, sobrou pouco na prateleira.
        ProdutoImportado.objects.create(
            importacao=self.importacao, codigo="1", descricao="CARVAO SACO", grupo="LENHA",
            fornecedor="MADEIREIRA SUL", custo=Decimal("10"), preco_venda=Decimal("18"),
            estoque=Decimal("2"), vendas_12m=Decimal("300"), vendas_90d=Decimal("80"),
            receita_12m=Decimal("5400"), compras_12m=Decimal("300"),
            valor_compras_12m=Decimal("3000"), ultima_compra=self.corte - timedelta(days=30),
            ultima_venda=self.corte - timedelta(days=1),
        )
        # Comprado e nunca vendido: é o caso que a tela existe para mostrar.
        ProdutoImportado.objects.create(
            importacao=self.importacao, codigo="2", descricao="VASO CERAMICA GRANDE",
            grupo="CERAMICA", fornecedor="CERAMICA BOA", custo=Decimal("30"),
            preco_venda=Decimal("50"), estoque=Decimal("40"), vendas_12m=Decimal("0"),
            receita_12m=Decimal("0"), compras_12m=Decimal("40"),
            valor_compras_12m=Decimal("1200"), ultima_compra=self.corte - timedelta(days=200),
        )
        # Vende devagar e tem prateleira de sobra.
        ProdutoImportado.objects.create(
            importacao=self.importacao, codigo="3", descricao="TAPETE COURO", grupo="TAPETE",
            fornecedor="CERAMICA BOA", custo=Decimal("100"), preco_venda=Decimal("180"),
            estoque=Decimal("50"), vendas_12m=Decimal("5"), receita_12m=Decimal("900"),
            compras_12m=Decimal("20"), valor_compras_12m=Decimal("2000"),
            ultima_compra=self.corte - timedelta(days=60), ultima_venda=self.corte - timedelta(days=40),
        )


class TetoTest(BaseCompra):
    def test_teto_do_mes_sai_do_que_saiu_da_prateleira(self):
        """300x10 + 0x30 + 5x100 = 3.500 em 12 meses, logo 291,67 por mês."""
        dados = limite.montar(self.importacao)
        self.assertEqual(dados.teto.custo_vendido_12m, Decimal("3500.00"))
        self.assertEqual(dados.teto.mensal, Decimal("291.67"))

    def test_compra_do_mes_vem_do_mes_da_data_de_corte(self):
        dados = limite.montar(self.importacao)
        self.assertEqual(dados.teto.comprado, Decimal("1200.00"))
        self.assertEqual(dados.teto.rotulo_mes, "setembro")

    def test_estouro_fica_vermelho_e_a_diferenca_vem_positiva(self):
        dados = limite.montar(self.importacao)
        self.assertTrue(dados.teto.estourou)
        self.assertEqual(dados.teto.nivel, "ruim")
        self.assertEqual(dados.teto.diferenca, Decimal("908.33"))

    def test_mes_dentro_do_teto_fica_verde(self):
        self.importacao.detalhe = {"compras_mes": [[2026, 9, 100.0, 1]]}
        self.importacao.save(update_fields=["detalhe"])
        dados = limite.montar(self.importacao)
        self.assertFalse(dados.teto.estourou)
        self.assertEqual(dados.teto.nivel, "bom")
        self.assertEqual(dados.teto.sobra, Decimal("191.67"))

    def test_sem_importacao_nao_quebra(self):
        dados = limite.montar(None)
        self.assertEqual(dados.fornecedores, [])
        self.assertEqual(dados.teto.mensal, Decimal("0"))


class FornecedorTest(BaseCompra):
    def test_pior_fornecedor_vem_primeiro_com_o_que_nao_girou(self):
        dados = limite.montar(self.importacao)
        pior = dados.fornecedores[0]
        self.assertEqual(pior.nome, "CERAMICA BOA")
        # 40 vasos a 30 nunca venderam; o tapete girou pouco mas girou.
        self.assertEqual(pior.sem_giro, Decimal("1200.00"))
        self.assertEqual(pior.itens_sem_giro, 1)
        self.assertEqual(pior.na_prateleira, Decimal("6200.00"))

    def test_fornecedor_que_girou_tudo_nao_mostra_porcentagem(self):
        dados = limite.montar(self.importacao)
        bom = next(f for f in dados.fornecedores if f.nome == "MADEIREIRA SUL")
        # Comprou 3.000 e já vendeu 3.000 ao custo: não há sobra para apontar.
        self.assertEqual(bom.comprado, Decimal("3000.00"))
        self.assertEqual(bom.vendido, Decimal("3000.00"))
        self.assertIsNone(bom.aproveitamento)

    def test_comparacao_do_ano_diz_se_entrou_mais_do_que_saiu(self):
        """6.200 comprados contra 3.500 que saíram da prateleira: entrou 2.700 a mais."""
        dados = limite.montar(self.importacao)
        self.assertEqual(dados.comprado_12m, Decimal("6200.00"))
        self.assertTrue(dados.comprou_mais_do_que_saiu)
        self.assertEqual(dados.diferenca_do_ano, Decimal("2700.00"))

    def test_quando_saiu_mais_do_que_entrou_a_comparacao_vira(self):
        ProdutoImportado.objects.filter(codigo__in=["2", "3"]).update(valor_compras_12m=Decimal("0"))
        dados = limite.montar(self.importacao)
        # Entraram 3.000 e saíram 3.500 da prateleira: a loja tirou estoque em vez de engordar.
        self.assertFalse(dados.comprou_mais_do_que_saiu)
        self.assertEqual(dados.diferenca_do_ano, Decimal("500.00"))

    def test_sem_compra_no_periodo_nao_inventa_aproveitamento(self):
        linha = limite.CompraDoFornecedor(nome="X", comprado=Decimal("0"), vendido=Decimal("10"))
        self.assertIsNone(linha.aproveitamento)
        self.assertTrue(linha.sem_compra_no_periodo)

    def test_aproveitamento_so_aparece_quando_saiu_menos_do_que_entrou(self):
        """Vendido acima do comprado daria sempre 100% e não diria nada."""
        cheio = limite.CompraDoFornecedor(nome="X", comprado=Decimal("100"), vendido=Decimal("300"))
        self.assertIsNone(cheio.aproveitamento)
        parcial = limite.CompraDoFornecedor(nome="Y", comprado=Decimal("100"), vendido=Decimal("40"))
        self.assertEqual(parcial.aproveitamento, 40)

    def test_totais_somam_a_prateleira_e_o_que_nao_girou(self):
        dados = limite.montar(self.importacao)
        self.assertEqual(dados.total_prateleira, Decimal("6220.00"))
        self.assertEqual(dados.total_sem_giro, Decimal("1200.00"))


class VereditoTest(BaseCompra):
    def test_produto_morto_e_zerado_recebe_nao_compre_e_nao_sem_dados(self):
        """Não vendeu nada e não tem saldo: isso é resposta, não falta de dado."""
        ProdutoImportado.objects.create(
            importacao=self.importacao, codigo="9", descricao="LUMINARIA ANTIGA",
            grupo="DECORACAO", fornecedor="CERAMICA BOA", custo=Decimal("20"),
            estoque=Decimal("0"), vendas_12m=Decimal("0"), compras_12m=Decimal("0"),
        )
        item = limite.conferir(self.importacao, "LUMINARIA")[0]
        self.assertEqual(item.resposta, "nao")
        self.assertIn("zerado", item.motivo)

    def test_saldo_negativo_do_set_fica_marcado(self):
        ProdutoImportado.objects.filter(codigo="1").update(estoque=Decimal("-3"))
        item = limite.conferir(self.importacao, "CARVAO")[0]
        self.assertTrue(item.estoque_negativo)

    def test_conta_quantos_casam_mesmo_mostrando_poucos(self):
        self.assertEqual(limite.quantos_casam(self.importacao, "TAPETE"), 1)
        self.assertEqual(limite.quantos_casam(self.importacao, ""), 0)

    def test_produto_sem_venda_recebe_nao_compre(self):
        itens = limite.conferir(self.importacao, "VASO")
        self.assertEqual(len(itens), 1)
        self.assertEqual(itens[0].resposta, "nao")
        self.assertIn("Não compre", itens[0].titulo)

    def test_produto_zerado_que_vende_recebe_pode_comprar(self):
        ProdutoImportado.objects.filter(codigo="1").update(estoque=Decimal("0"))
        itens = limite.conferir(self.importacao, "CARVAO")
        self.assertEqual(itens[0].resposta, "pode")

    def test_busca_pelo_codigo_exato_encontra(self):
        itens = limite.conferir(self.importacao, "2")
        self.assertEqual(itens[0].codigo, "2")

    def test_o_que_nao_se_deve_comprar_aparece_primeiro(self):
        itens = limite.conferir(self.importacao, "a")
        self.assertEqual(itens[0].resposta, "nao")

    def test_busca_vazia_nao_lista_nada(self):
        self.assertEqual(limite.conferir(self.importacao, "   "), [])
        self.assertEqual(limite.conferir(self.importacao, "xyz nada"), [])


class TelaTest(BaseCompra):
    def test_gerencia_abre_e_ve_o_teto_e_o_fornecedor(self):
        Fornecedor.objects.create(nome="CERAMICA BOA", reputacao=2, relacao="eventual")
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)
        resposta = self.client.get(reverse("compras:antes_de_comprar"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Quanto cabe de compra em setembro")
        self.assertContains(resposta, "O que a compra do ano virou")
        self.assertContains(resposta, "Eventual")

    def test_busca_na_tela_responde_com_o_veredito(self):
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)
        resposta = self.client.get(reverse("compras:antes_de_comprar"), {"produto": "VASO"})
        self.assertContains(resposta, "Não compre")
        self.assertContains(resposta, "VASO CERAMICA GRANDE")

    def test_quem_nao_ve_painel_nao_abre(self):
        usuario("balcao", VENDEDOR)
        self.client.login(username="balcao", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("compras:antes_de_comprar")).status_code, 403)


class OTetoSemMontarATelaInteira(BaseCompra):
    """A lista de compra e o pedido só precisam do teto, e não dos onze mil produtos.

    Achado na revisão geral de 15/10/2026. As duas telas chamavam `montar`, que traz
    todos os produtos do SET para a memória e monta a tabela de todos os fornecedores,
    para depois jogar tudo fora menos o teto — uma varredura de onze mil linhas em Python
    a cada abertura da tela mais pesada do sistema. `teto_de` faz a soma no banco.
    """

    def test_da_o_mesmo_teto_que_a_tela_inteira(self):
        """Se os dois caminhos divergirem, a tela e o pedido passam a discordar."""
        inteiro = limite.montar(self.importacao).teto
        barato = limite.teto_de(self.importacao)
        for campo in ("custo_vendido_12m", "mensal", "comprado", "sobra", "usado",
                      "rotulo_mes", "dia_do_corte", "nivel", "largura"):
            self.assertEqual(getattr(barato, campo), getattr(inteiro, campo), campo)

    def test_produto_sem_custo_entra_como_zero_nos_dois_caminhos(self):
        """No banco, multiplicação com nulo é nula e não entra na soma; em Python, zero."""
        ProdutoImportado.objects.create(
            importacao=self.importacao, codigo="99", descricao="SEM CUSTO CADASTRADO",
            grupo="LENHA", custo=None, estoque=Decimal("5"), vendas_12m=Decimal("10"))
        self.assertEqual(limite.teto_de(self.importacao).custo_vendido_12m,
                         limite.montar(self.importacao).teto.custo_vendido_12m)

    def test_o_compromisso_do_caixa_continua_descontado(self):
        from apps.financeiro import servicos as financeiro

        resumo = financeiro.resumir(self.importacao, hoje=self.corte)
        self.assertEqual(limite.teto_de(self.importacao, resumo_caixa=resumo).comprometido,
                         limite.montar(self.importacao, resumo_caixa=resumo).teto.comprometido)

    def test_sem_importacao_devolve_teto_vazio_e_nao_quebra(self):
        self.assertEqual(limite.teto_de(None).mensal, Decimal("0"))

    def test_a_lista_de_compra_faz_menos_consultas_do_que_antes(self):
        """A conta é da tela de abertura: é a pessoa que espera por ela."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as consultas:
            limite.teto_de(self.importacao)
        self.assertLessEqual(len(consultas), 2, "o teto sai em uma consulta de soma")


class OVereditoDizAContaQueFaz(BaseCompra):
    """A frase da ruptura prometia uma régua de 90 dias que esta tela não usa.

    Achado na revisão geral de 15/10/2026. `conferir` monta o item com `vendas_12m` e
    `dias_abertos_12m`: a situação RUPTURA sai de "vendeu no ano e está zerado", e a frase
    dizia "vendeu nos últimos 90 dias", que é a régua da tela de Sugestões. Produto que
    vendeu duas unidades em novembro e está zerado desde então recebia "pode comprar,
    vendeu nos últimos 90 dias" — e é a única frase que a pessoa lê antes de comprar.
    """

    def test_a_frase_da_ruptura_fala_de_doze_meses(self):
        ProdutoImportado.objects.create(
            importacao=self.importacao, codigo="7", descricao="PANELA DE FERRO",
            grupo="COZINHA", fornecedor="FERRO FORTE", custo=Decimal("40"),
            preco_venda=Decimal("90"), estoque=Decimal("0"), vendas_12m=Decimal("2"),
            vendas_90d=Decimal("0"), receita_12m=Decimal("180"), compras_12m=Decimal("2"),
            prazo_reposicao_dias=10,
        )
        veredito = next(v for v in limite.conferir(self.importacao, "PANELA DE FERRO"))
        self.assertEqual(veredito.resposta, "pode")
        self.assertIn("12 meses", veredito.motivo)
        self.assertNotIn("90 dias", veredito.motivo)
