"""O que fazer agora: a lista de tarefas que o sistema monta sozinho."""

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.compras import lista_de_compra, limite
from apps.compras.equipe import registrar_sugestao
from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.financeiro import servicos as financeiro
from apps.financeiro.models import Lancamento
from apps.importacao import servicos as importacao_servicos
from apps.importacao.models import Importacao, ProdutoImportado
from apps.painel import tarefas

CORTE = date(2026, 9, 20)


class BaseTarefas(TestCase):
    def setUp(self):
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO,
            situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(),
            data_corte=timezone.localdate(),
            dias_abertos_12m=360,
            produtos=0,
        )
        self.pessoa = usuario("gerente", ADMINISTRACAO)

    def produto(self, codigo, **campos):
        padrao = dict(
            importacao=self.importacao, codigo=codigo, descricao=f"PRODUTO {codigo}",
            grupo="TAPETE", fornecedor="GERMAN", custo=Decimal("10"),
            preco_venda=Decimal("25"), estoque=Decimal("0"), vendas_12m=Decimal("360"),
            receita_12m=Decimal("9000"),
        )
        padrao.update(campos)
        return ProdutoImportado.objects.create(**padrao)

    def agenda(self, usuario_=None):
        estado = importacao_servicos.estado_dos_dados()
        resumo = financeiro.resumir(self.importacao)
        lista = lista_de_compra.priorizar(
            lista_de_compra.montar(self.importacao),
            limite.montar(self.importacao, resumo_caixa=resumo).teto)
        return tarefas.montar(estado, self.importacao, resumo, lista,
                              usuario=usuario_ or self.pessoa)

    def chaves(self, **kwargs):
        return [t.chave for t in self.agenda(**kwargs).tarefas]


class TestQuandoCadaTarefaAparece(BaseTarefas):
    def test_loja_sem_pendencia_nenhuma_nao_inventa_tarefa(self):
        """Tarefa sem número por trás é ruído: se a conta dá zero, a linha não existe."""
        self.assertEqual(self.chaves(), [])

    def test_produto_faltando_vira_tarefa_de_fechar_pedido(self):
        self.produto("1")
        agenda = self.agenda()
        tarefa = next(t for t in agenda.tarefas if t.chave == "faltando")
        self.assertEqual(tarefa.nivel, tarefas.URGENTE)
        self.assertIn("1 produtos", tarefa.detalhe)
        self.assertEqual(tarefa.endereco, reverse("compras:lista"))

    def test_abaixo_do_minimo_vira_tarefa_propria_com_o_filtro_pronto(self):
        self.produto("1", estoque=Decimal("30"), estoque_minimo_set=Decimal("100"))
        tarefa = next(t for t in self.agenda().tarefas if t.chave == "minimo")
        self.assertIn("situacao=abaixo_do_minimo", tarefa.endereco)

    def test_conta_vencida_vira_tarefa_urgente(self):
        Lancamento.objects.create(
            importacao=self.importacao, tipo=Lancamento.Tipo.PAGAR, id_set=1,
            descricao="ENERGIA", valor=Decimal("500"),
            vencimento=timezone.localdate() - timedelta(days=5))
        tarefa = next(t for t in self.agenda().tarefas if t.chave == "vencidas")
        self.assertEqual(tarefa.nivel, tarefas.URGENTE)
        self.assertIn("R$ 500,00", tarefa.detalhe)

    def test_mercadoria_parada_vira_tarefa_de_por_para_girar(self):
        self.produto("parado", estoque=Decimal("10"), vendas_12m=Decimal("0"),
                     receita_12m=Decimal("0"), custo=Decimal("30"))
        tarefa = next(t for t in self.agenda().tarefas if t.chave == "parado")
        self.assertIn("R$ 300,00", tarefa.detalhe)

    def test_sugestao_da_equipe_sem_resposta_vira_tarefa(self):
        registrar_sugestao(produto="CARVAO", usuario=self.pessoa)
        tarefa = next(t for t in self.agenda().tarefas if t.chave == "equipe")
        self.assertIn("1 sugestão", tarefa.detalhe)
        self.assertEqual(tarefa.endereco, reverse("compras:sugestoes_da_equipe"))

    def test_estoque_negativo_vira_convite_a_contar(self):
        self.produto("1", estoque=Decimal("-4"))
        tarefa = next(t for t in self.agenda().tarefas if t.chave == "negativos")
        self.assertIn("estimativa", tarefa.detalhe)

    def test_dados_velhos_viram_a_primeira_tarefa_de_todas(self):
        self.importacao.data_corte = timezone.localdate() - timedelta(days=30)
        self.importacao.save(update_fields=["data_corte"])
        self.produto("1")
        agenda = self.agenda()
        self.assertEqual(agenda.tarefas[0].chave, "importar")


class TestOrdemEPermissao(BaseTarefas):
    def setUp(self):
        super().setUp()
        self.produto("1")
        self.produto("parado", estoque=Decimal("10"), vendas_12m=Decimal("0"),
                     receita_12m=Decimal("0"), custo=Decimal("30"))

    def test_o_urgente_vem_antes_do_resto(self):
        niveis = [t.nivel for t in self.agenda().tarefas]
        self.assertEqual(niveis, sorted(niveis, key=lambda n: tarefas.PESO[n]))

    def test_o_vendedor_nao_ve_tarefa_nenhuma(self):
        """Ele só tem a consulta do balcão; tarefa que termina em acesso negado é pior que nada."""
        self.assertEqual(self.chaves(usuario_=usuario("balcao", VENDEDOR)), [])

    def test_o_operador_administrativo_ve_o_que_ele_resolve(self):
        chaves = self.chaves(usuario_=usuario("ana", ADMINISTRATIVO))
        self.assertIn("faltando", chaves)
        self.assertNotIn("equipe", chaves)  # responder sugestão é da gerência

    def test_a_abertura_mostra_as_cinco_primeiras_e_conta_o_resto(self):
        agenda = self.agenda()
        self.assertLessEqual(len(agenda.primeiras), tarefas.QUANTAS_NA_ABERTURA)
        self.assertEqual(agenda.restantes,
                         max(len(agenda.tarefas) - tarefas.QUANTAS_NA_ABERTURA, 0))


class TestNaTelaDeAbertura(BaseTarefas):
    def setUp(self):
        super().setUp()
        self.produto("1")
        self.client.login(username="gerente", password=SENHA_TESTE)

    def test_a_visao_geral_abre_com_o_que_fazer_agora(self):
        resposta = self.client.get(reverse("painel:geral"))
        self.assertContains(resposta, "O que fazer agora")
        self.assertContains(resposta, "Fechar o pedido do que está faltando")

    def test_cada_tarefa_leva_para_a_tela_que_resolve(self):
        resposta = self.client.get(reverse("painel:geral"))
        self.assertContains(resposta, reverse("compras:lista"))

    def test_sem_importacao_nenhuma_a_tela_nao_quebra(self):
        Importacao.objects.all().delete()
        resposta = self.client.get(reverse("painel:geral"))
        self.assertEqual(resposta.status_code, 200)
