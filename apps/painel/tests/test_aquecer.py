"""As contas da abertura ficam prontas antes de alguém pedir.

O defeito que isto cobre: a chave do cache carrega o número da importação, então cada
sincronização derruba o cache de propósito, e a conta de ~2 s sobrava para a primeira
pessoa que abrisse o sistema. Como a Visão geral é a primeira tela depois de entrar,
essa pessoa sentia isso como "o login está lento" — três vezes por dia.
"""

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.importacao.models import Importacao, ProdutoImportado
from apps.painel import aquecer as aquecer_painel, servicos


class AquecerTest(TestCase):
    def setUp(self):
        cache.clear()
        hoje = timezone.localdate()
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO,
            situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(),
            data_corte=hoje - timedelta(days=1),
            dias_abertos_12m=300,
            produtos=2,
            arquivo="C:\\backup\\DADOS-SET.FDB",
            detalhe={"vendas_mes": [[2026, 9, 90000.0, 380]], "compras_mes": []},
        )
        comum = {"importacao": self.importacao, "prazo_reposicao_dias": 7}
        ProdutoImportado.objects.create(
            codigo="1", descricao="CARVAO 10KG", custo=Decimal("10"), estoque=Decimal("60"),
            vendas_12m=Decimal("40"), compras_12m=Decimal("100"),
            receita_12m=Decimal("1200"), **comum)
        ProdutoImportado.objects.create(
            codigo="2", descricao="ACENDEDOR", custo=Decimal("2"), estoque=Decimal("0"),
            vendas_12m=Decimal("300"), vendas_90d=Decimal("80"), compras_12m=Decimal("300"),
            receita_12m=Decimal("1500"), **comum)

    def test_depois_de_aquecer_a_tela_encontra_a_conta_pronta(self):
        self.assertIsNone(servicos.painel_pronto(self.importacao))
        aquecer_painel.aquecer(self.importacao)
        self.assertIsNotNone(servicos.painel_pronto(self.importacao))

    def test_aquecer_guarda_as_tres_contas_da_abertura(self):
        aquecer_painel.aquecer(self.importacao)
        chave = servicos.chave(self.importacao)
        for rotulo, guardada in (("painel", chave), ("visão geral", "visao:" + chave),
                                 ("agenda", "agenda:" + chave)):
            self.assertIsNotNone(cache.get(guardada), f"{rotulo} não ficou no cache")

    def test_sem_importacao_nao_faz_nada_e_nao_quebra(self):
        self.assertEqual(aquecer_painel.aquecer(None), 0.0)

    def test_falha_ao_aquecer_nao_derruba_quem_chamou(self):
        """A importação já terminou e já gravou os números quando isto roda.

        Derrubá-la porque um cálculo de tela falhou trocaria uma tela lenta por uma
        loja sem dados novos.
        """
        with mock.patch.object(servicos, "painel_da_importacao",
                               side_effect=ValueError("conta quebrada")):
            with self.assertLogs("apps.painel.aquecer", level="ERROR"):
                self.assertEqual(aquecer_painel.aquecer(self.importacao), 0.0)

class AImportacaoAdiantaAContaTest(TestCase):
    """O caminho de verdade, do backup à tela: quem importa deixa a conta pronta.

    O Firebird é trocado por um dublê — o que este teste trava é o fim da importação,
    não a leitura do banco, que tem testes próprios.
    """

    def _extracao(self):
        from apps.importacao.fontes.firebird import Extracao

        hoje = timezone.localdate()
        return Extracao(
            data_corte=hoje - timedelta(days=1),
            dias_abertos_12m=300,
            dias_abertos_90d=78,
            produtos=[
                {"codigo": "1", "descricao": "CARVAO 10KG", "custo": Decimal("10"),
                 "estoque": Decimal("60"), "vendas_12m": Decimal("40"),
                 "compras_12m": Decimal("100"), "receita_12m": Decimal("1200")},
                {"codigo": "2", "descricao": "ACENDEDOR", "custo": Decimal("2"),
                 "estoque": Decimal("0"), "vendas_12m": Decimal("300"),
                 "vendas_90d": Decimal("80"), "compras_12m": Decimal("300"),
                 "receita_12m": Decimal("1500")},
            ],
            detalhe={"vendas_mes": [[hoje.year, hoje.month, 90000.0, 380]], "compras_mes": []},
        )

    def test_quem_abre_o_sistema_depois_da_sincronizacao_acha_a_tela_pronta(self):
        import tempfile
        from pathlib import Path

        from apps.importacao import servicos as importacao_servicos

        cache.clear()
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "DADOS-SET.FDB"
            caminho.write_bytes(b"x" * 4096)
            with mock.patch("apps.importacao.fontes.firebird.preparar_copia",
                            return_value=caminho), \
                 mock.patch("apps.importacao.fontes.firebird.extrair",
                            return_value=self._extracao()):
                importacao = importacao_servicos.executar(arquivo=str(caminho))

        self.assertEqual(importacao.situacao, Importacao.Situacao.CONCLUIDA)
        self.assertIsNotNone(
            servicos.painel_pronto(importacao),
            "a importação terminou sem adiantar a conta: a primeira pessoa a entrar "
            "vai pagar os ~2 s de novo")
        self.assertTrue(
            any("Contas do painel adiantadas" in linha for linha in importacao.linhas_do_log),
            "o log da importação precisa dizer que adiantou a conta")


class CacheCompartilhadoTest(TestCase):
    """O cache do servidor TEM que ser visível de outro processo.

    Quem calcula é a tarefa agendada CabanaImportacao; quem mostra a tela é o serviço
    CabanaSistema. Com cache na memória de cada processo, a conta feita pela tarefa
    nunca chega ao serviço e a pessoa espera do mesmo jeito — que era exatamente o
    defeito. Este teste existe para ninguém "simplificar" isso de volta.
    """

    def test_o_cache_de_producao_nao_e_o_de_memoria(self):
        from config.settings import base

        backend = base.CACHES["default"]["BACKEND"]
        self.assertNotIn("locmem", backend)
        self.assertIn("filebased", backend)

    def test_a_pasta_do_cache_se_configura_pelo_ambiente(self):
        """No servidor ela fica em dados\\cache, fora da pasta que a atualização troca."""
        from config.settings import base

        self.assertEqual(base.CACHES["default"]["LOCATION"], str(base.CACHE_PASTA))

    def test_os_testes_usam_memoria_de_proposito(self):
        """Em arquivo, um teste deixaria número calculado para o seguinte achar.

        Lê o módulo de teste direto, e não `settings`: um `override_settings` aqui
        dentro provaria apenas que o override funcionou, que é o que esta versão do
        teste fazia — passava mesmo se config/settings/test.py perdesse o bloco.
        """
        from config.settings import test as ajustes_de_teste

        self.assertIn("locmem", ajustes_de_teste.CACHES["default"]["BACKEND"])

    def test_a_suite_nao_escreve_na_pasta_do_servidor(self):
        """O que vale AGORA, nesta execução, e não o que um módulo declara.

        Se a suíte estiver gravando na pasta do servidor, um teste acha o número que o
        anterior deixou e a suíte passa a depender da ordem — ou pior, a execução dos
        testes derruba a conta adiantada do servidor de verdade.
        """
        from django.conf import settings

        self.assertIn("locmem", settings.CACHES["default"]["BACKEND"])


class ATarefaDeHoraEmHoraAdiantaTest(TestCase):
    """A chave do cache carrega o dia, então à meia-noite a conta de ontem deixa de servir.

    Quem abre o sistema antes da sincronização das 08:30 pagaria os ~2 s. A tarefa dos
    alertas acorda de hora em hora e é ela que passa a pagar.
    """

    def setUp(self):
        cache.clear()
        hoje = timezone.localdate()
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO,
            situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(),
            data_corte=hoje - timedelta(days=1),
            dias_abertos_12m=300,
            produtos=1,
            arquivo="C:\\backup\\DADOS-SET.FDB",
            detalhe={"vendas_mes": [[hoje.year, hoje.month, 90000.0, 380]], "compras_mes": []},
        )
        ProdutoImportado.objects.create(
            importacao=self.importacao, prazo_reposicao_dias=7,
            codigo="1", descricao="CARVAO 10KG", custo=Decimal("10"), estoque=Decimal("60"),
            vendas_12m=Decimal("40"), compras_12m=Decimal("100"), receita_12m=Decimal("1200"))

    def _rodar(self):
        from io import StringIO

        from django.core.management import call_command

        saida = StringIO()
        call_command("enviar_relatorios", stdout=saida, rotina="backup")
        return saida.getvalue()

    def test_a_tarefa_deixa_a_conta_do_dia_pronta(self):
        self.assertIsNone(servicos.painel_pronto(self.importacao))
        saida = self._rodar()
        self.assertIsNotNone(
            servicos.painel_pronto(self.importacao),
            "a tarefa de hora em hora passou sem adiantar a conta: quem entrar antes da "
            "sincronização das 08:30 vai pagar os ~2 s")
        self.assertIn("Contas da abertura adiantadas", saida)

    def test_falha_ao_adiantar_nao_derruba_os_relatorios(self):
        """Derrubar esta tarefa por causa de um cálculo de tela deixaria a loja sem aviso."""
        with mock.patch("apps.painel.aquecer.aquecer_a_foto_de_hoje",
                        side_effect=ValueError("conta quebrada")):
            with self.assertLogs(
                    "apps.alertas.management.commands.enviar_relatorios", level="ERROR"):
                self._rodar()
