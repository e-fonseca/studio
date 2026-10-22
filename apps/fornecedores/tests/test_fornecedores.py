"""O prazo de entrega informado é o que corrige a data da sugestão de compra."""

from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import EventoAuditoria
from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.fornecedores.models import Fornecedor
from apps.fornecedores import servicos
from apps.importacao.models import Importacao, ProdutoImportado
from apps.painel import indicadores


class BaseFornecedor(TestCase):
    def setUp(self):
        cache.clear()
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO,
            situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(),
            data_corte=timezone.localdate() - timedelta(days=1),
            dias_abertos_12m=300,
            produtos=2,
        )
        ProdutoImportado.objects.create(
            importacao=self.importacao, codigo="1", descricao="CARVAO 10KG", fornecedor="MADEIREIRA SUL",
            custo=Decimal("10"), preco_venda=Decimal("18"), estoque=Decimal("20"),
            vendas_12m=Decimal("300"), vendas_90d=Decimal("80"), compras_12m=Decimal("300"),
            valor_compras_12m=Decimal("3000"), prazo_reposicao_dias=0,
        )
        ProdutoImportado.objects.create(
            importacao=self.importacao, codigo="2", descricao="LENHA", fornecedor="SITIO BOA VISTA",
            custo=Decimal("5"), preco_venda=Decimal("9"), estoque=Decimal("500"),
            vendas_12m=Decimal("10"), compras_12m=Decimal("10"),
            valor_compras_12m=Decimal("50"), prazo_reposicao_dias=12,
        )


class ResumoTest(BaseFornecedor):
    def test_ordena_pelo_que_mais_custou_e_traz_o_prazo_medido(self):
        resumos = servicos.resumir(self.importacao)
        self.assertEqual([r.nome for r in resumos], ["MADEIREIRA SUL", "SITIO BOA VISTA"])
        self.assertEqual(resumos[0].valor_comprado_12m, Decimal("3000"))
        self.assertEqual(resumos[0].prazo_medido, 0)
        self.assertEqual(resumos[1].prazo_medido, 12)

    def test_prazo_zerado_e_sem_informado_pede_atencao(self):
        resumos = {r.nome: r for r in servicos.resumir(self.importacao)}
        self.assertTrue(resumos["MADEIREIRA SUL"].precisa_de_prazo)
        self.assertFalse(resumos["SITIO BOA VISTA"].precisa_de_prazo)

    def test_prazo_informado_aparece_e_vence_o_medido(self):
        Fornecedor.objects.create(nome="MADEIREIRA SUL", prazo_dias=20)
        resumo = {r.nome: r for r in servicos.resumir(self.importacao)}["MADEIREIRA SUL"]
        self.assertEqual(resumo.prazo_informado, 20)
        self.assertEqual(resumo.prazo_em_uso, 20)


class PrazoNoCalculoTest(BaseFornecedor):
    def ponto_de_reposicao(self):
        painel = indicadores.montar(self.importacao)
        return painel.indicador("comprar")

    def test_prazo_maior_antecipa_a_reposicao(self):
        sem_prazo = self.ponto_de_reposicao()
        Fornecedor.objects.create(nome="MADEIREIRA SUL", prazo_dias=45)
        com_prazo = self.ponto_de_reposicao()
        self.assertGreater(com_prazo.valor, sem_prazo.valor)

    def test_painel_conta_quantos_usam_o_prazo_informado(self):
        Fornecedor.objects.create(nome="MADEIREIRA SUL", prazo_dias=30)
        self.assertEqual(indicadores.montar(self.importacao).itens_prazo_informado, 1)


class TelaTest(BaseFornecedor):
    def entrar(self, perfil=ADMINISTRACAO):
        usuario("edson", perfil)
        self.client.login(username="edson", password=SENHA_TESTE)

    def test_lista_mostra_fornecedores_e_quanto_pesam(self):
        self.entrar()
        pagina = self.client.get(reverse("fornecedores:lista"))
        self.assertContains(pagina, "MADEIREIRA SUL")
        self.assertContains(pagina, "R$ 3.000,00")

    def test_salvar_grava_o_prazo_e_registra_na_auditoria(self):
        self.entrar()
        resposta = self.client.post(reverse("fornecedores:salvar"),
                                    {"nome": "MADEIREIRA SUL", "prazo_dias": "18"}, follow=True)
        self.assertEqual(Fornecedor.objects.get(nome="MADEIREIRA SUL").prazo_dias, 18)
        self.assertContains(resposta, "18 dias")
        self.assertTrue(EventoAuditoria.objects.filter(acao="fornecedor.prazo_alterado").exists())

    def test_prazo_em_branco_volta_a_usar_o_medido(self):
        Fornecedor.objects.create(nome="MADEIREIRA SUL", prazo_dias=18)
        self.entrar()
        self.client.post(reverse("fornecedores:salvar"), {"nome": "MADEIREIRA SUL", "prazo_dias": ""})
        self.assertIsNone(Fornecedor.objects.get(nome="MADEIREIRA SUL").prazo_dias)

    def test_prazo_absurdo_e_recusado_com_explicacao(self):
        self.entrar()
        resposta = self.client.post(reverse("fornecedores:salvar"),
                                    {"nome": "MADEIREIRA SUL", "prazo_dias": "9999"}, follow=True)
        self.assertContains(resposta, "de 0 a 365")
        self.assertFalse(Fornecedor.objects.filter(nome="MADEIREIRA SUL").exists())

    def test_administrativo_ve_e_tambem_salva(self):
        """O administrativo cuida de fornecedor: abre a tela e informa prazo e avaliação."""
        self.entrar(ADMINISTRATIVO)
        self.assertEqual(self.client.get(reverse("fornecedores:lista")).status_code, 200)
        self.client.post(reverse("fornecedores:salvar"), {"nome": "MADEIREIRA SUL", "prazo_dias": "5"})
        self.assertEqual(Fornecedor.objects.get(nome="MADEIREIRA SUL").prazo_dias, 5)

    def test_vendedor_nao_abre_a_tela_de_fornecedores(self):
        """O balcão consulta pela tela de produtos, que não mostra valor de compra."""
        self.entrar(VENDEDOR)
        self.assertEqual(self.client.get(reverse("fornecedores:lista")).status_code, 403)
        self.assertEqual(self.client.post(reverse("fornecedores:salvar"), {"nome": "X"}).status_code, 403)


class ReputacaoTest(BaseFornecedor):
    """A reputação é julgamento da gerência, não vem do SET."""

    def setUp(self):
        super().setUp()
        self.gerente = usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)

    def test_avaliar_grava_estrelas_relacao_e_auditoria(self):
        resposta = self.client.post(reverse("fornecedores:avaliar"), {
            "nome": "MADEIREIRA SUL", "reputacao": "4", "relacao": "parceiro",
        })
        self.assertRedirects(resposta, reverse("fornecedores:lista"))
        fornecedor = Fornecedor.objects.get(nome="MADEIREIRA SUL")
        self.assertEqual(fornecedor.reputacao, 4)
        self.assertEqual(fornecedor.relacao, "parceiro")
        self.assertEqual(fornecedor.estrelas, [True, True, True, True, False])
        self.assertTrue(EventoAuditoria.objects.filter(acao="fornecedor.avaliado").exists())

    def test_nota_fora_da_faixa_nao_grava(self):
        self.client.post(reverse("fornecedores:avaliar"), {
            "nome": "MADEIREIRA SUL", "reputacao": "9", "relacao": "",
        })
        self.assertFalse(Fornecedor.objects.filter(nome="MADEIREIRA SUL", reputacao=9).exists())

    def test_relacao_inventada_nao_grava(self):
        self.client.post(reverse("fornecedores:avaliar"), {
            "nome": "MADEIREIRA SUL", "reputacao": "3", "relacao": "amigo",
        })
        self.assertFalse(Fornecedor.objects.filter(nome="MADEIREIRA SUL").exists())

    def test_resumo_leva_a_reputacao_para_as_telas(self):
        Fornecedor.objects.create(nome="MADEIREIRA SUL", reputacao=5, relacao="flexivel")
        resumo = next(r for r in servicos.resumir(self.importacao) if r.nome == "MADEIREIRA SUL")
        self.assertEqual(resumo.reputacao, 5)
        self.assertEqual(resumo.relacao_rotulo, "Flexível")
        self.assertFalse(resumo.precisa_de_reputacao)


class ProcurarFornecedorTest(BaseFornecedor):
    """A busca com autopreenchimento da tela de Fornecedores (1.31.0).

    A tela listava todos os fornecedores da importação de uma vez, sem caixa de busca:
    com 2.628 nomes, achar um pelo nome era rolar a página.
    """

    def entrar(self, perfil=ADMINISTRACAO):
        usuario("edson", perfil)
        self.client.login(username="edson", password=SENHA_TESTE)

    def test_acha_sem_acento_e_no_meio_do_nome(self):
        ProdutoImportado.objects.create(
            importacao=self.importacao, codigo="3", descricao="CESTA", fornecedor="QUITÉRIA FLOR MILHO",
            custo=Decimal("8"), preco_venda=Decimal("20"), estoque=Decimal("5"),
            vendas_12m=Decimal("40"), compras_12m=Decimal("40"), valor_compras_12m=Decimal("320"),
        )
        resumos = servicos.resumir(self.importacao)
        self.assertEqual([r.nome for r in servicos.procurar(resumos, "quiteria")], ["QUITÉRIA FLOR MILHO"])
        self.assertEqual([r.nome for r in servicos.procurar(resumos, "FLOR")], ["QUITÉRIA FLOR MILHO"])
        self.assertEqual([r.nome for r in servicos.procurar(resumos, "boa")], ["SITIO BOA VISTA"])

    def test_quem_comeca_com_o_digitado_vem_antes_de_quem_vendeu_mais(self):
        """Sem a regra de parecença, "SUL" traria primeiro o fornecedor de maior valor."""
        ProdutoImportado.objects.create(
            importacao=self.importacao, codigo="4", descricao="BANCO", fornecedor="SUL ARTESANAL",
            custo=Decimal("1"), preco_venda=Decimal("2"), estoque=Decimal("1"),
            vendas_12m=Decimal("1"), compras_12m=Decimal("1"), valor_compras_12m=Decimal("10"),
        )
        achados = servicos.procurar(servicos.resumir(self.importacao), "sul")
        self.assertEqual([r.nome for r in achados], ["SUL ARTESANAL", "MADEIREIRA SUL"])

    def test_busca_vazia_devolve_a_lista_inteira_na_ordem_de_sempre(self):
        resumos = servicos.resumir(self.importacao)
        self.assertEqual([r.nome for r in servicos.procurar(resumos, "  ")],
                         [r.nome for r in resumos])

    def test_tela_filtra_e_diz_quantos_achou(self):
        self.entrar()
        pagina = self.client.get(reverse("fornecedores:lista"), {"busca": "madeireira"})
        self.assertContains(pagina, "MADEIREIRA SUL")
        self.assertNotContains(pagina, "SITIO BOA VISTA")
        self.assertContains(pagina, "1 fornecedor com")

    def test_tela_sem_achar_nada_oferece_a_lista_inteira(self):
        self.entrar()
        pagina = self.client.get(reverse("fornecedores:lista"), {"busca": "zzz"})
        self.assertContains(pagina, "Nenhum fornecedor com")
        self.assertContains(pagina, "veja a lista inteira")

    def test_pendencias_contam_a_loja_inteira_mesmo_com_busca(self):
        """"Faltam 2 prazos" é fila de trabalho: não encolhe porque alguém procurou um nome."""
        self.entrar()
        inteira = self.client.get(reverse("fornecedores:lista"))
        filtrada = self.client.get(reverse("fornecedores:lista"), {"busca": "madeireira"})
        self.assertEqual(inteira.context["sem_prazo"], filtrada.context["sem_prazo"])
        self.assertEqual(filtrada.context["quantos_ao_todo"], len(inteira.context["fornecedores"]))

    def test_sugestoes_trazem_o_nome_e_quanto_a_loja_comprou(self):
        self.entrar()
        resposta = self.client.get(reverse("fornecedores:sugestoes"), {"q": "madeireira"})
        dados = resposta.json()["itens"]
        self.assertEqual(dados[0]["descricao"], "MADEIREIRA SUL")
        self.assertIn("R$ 3.000,00", dados[0]["ajuda"])
        self.assertIn("1 produto", dados[0]["ajuda"])

    def test_sugestoes_calam_com_menos_de_duas_letras(self):
        self.entrar()
        self.assertEqual(self.client.get(reverse("fornecedores:sugestoes"), {"q": "m"}).json()["itens"], [])

    def test_sugestoes_nao_abrem_para_o_vendedor(self):
        """Nome de fornecedor com valor comprado ao lado é a mesma tela, não endereço aberto."""
        self.entrar(VENDEDOR)
        self.assertEqual(self.client.get(reverse("fornecedores:sugestoes"), {"q": "madeireira"}).status_code, 403)
