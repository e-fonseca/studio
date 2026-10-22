"""Testes da higienização: o que sai, o que NÃO sai e o que explica por que não saiu."""

from datetime import timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path
import tempfile

from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.alertas.models import Canal, EnvioDeRelatorio
from apps.auditoria.models import EventoAuditoria
from apps.auditoria.servicos import registrar
from apps.caixa.models import CaixaImportado, MovimentoCaixa
from apps.core import higiene
from apps.financeiro.models import Lancamento
from apps.importacao import servicos as importacao_servicos
from apps.importacao.models import Importacao, ProdutoImportado


def importacao(dias_atras=0, situacao=Importacao.Situacao.CONCLUIDA):
    agora = timezone.now()
    return Importacao.objects.create(
        origem=Importacao.Origem.BANCO,
        situacao=situacao,
        iniciada_em=agora - timedelta(days=dias_atras),
        concluida_em=agora - timedelta(days=dias_atras),
        data_corte=timezone.localdate() - timedelta(days=dias_atras),
    )


def turno(imp, id_set=1):
    agora = timezone.now()
    caixa = CaixaImportado.objects.create(
        importacao=imp, id_set=id_set, dia=timezone.localdate(), aberto_em=agora,
        fechado_em=agora, recebido=Decimal("100"), situacao=CaixaImportado.Situacao.FECHADO,
    )
    MovimentoCaixa.objects.create(
        caixa=caixa, quando=agora, tipo=MovimentoCaixa.Tipo.SANGRIA, valor=Decimal("100"),
    )
    return caixa


class FotosDoCaixaTest(TestCase):
    """O bug que originou a higienização: o caixa ficava fora da limpeza."""

    def test_a_limpeza_leva_as_fotos_do_caixa(self):
        for dias in range(4):
            turno(importacao(dias_atras=dias), id_set=dias + 1)
        self.assertEqual(CaixaImportado.objects.count(), 4)
        importacao_servicos.limpar_antigas(manter=2)
        self.assertEqual(CaixaImportado.objects.count(), 2, "turno além do limite tem que sair")
        self.assertEqual(MovimentoCaixa.objects.count(), 2, "o movimento sai pela cascata")

    def test_o_que_sobra_e_o_mais_novo(self):
        velha = importacao(dias_atras=9)
        nova = importacao(dias_atras=0)
        turno(velha, id_set=1)
        turno(nova, id_set=2)
        importacao_servicos.limpar_antigas(manter=1)
        self.assertEqual([c.importacao_id for c in CaixaImportado.objects.all()], [nova.pk])


class ConferirSemApagarTest(TestCase):
    def test_conferir_nao_apaga_nada(self):
        imp = importacao(dias_atras=5)
        ProdutoImportado.objects.create(importacao=imp, codigo="P1", estoque=Decimal("1"))
        turno(imp)
        Session.objects.create(
            session_key="vencida", session_data="x",
            expire_date=timezone.now() - timedelta(days=1),
        )
        with override_settings(IMPORTACAO_MANTER=0):
            resultado = higiene.levantar(fazer=False)
        self.assertTrue(resultado.tem_o_que_limpar)
        self.assertEqual(ProdutoImportado.objects.count(), 1)
        self.assertEqual(CaixaImportado.objects.count(), 1)
        self.assertEqual(Session.objects.count(), 1)
        self.assertFalse(any(t.feito for t in resultado.tarefas))


class SessoesTest(TestCase):
    def test_sai_a_vencida_e_fica_a_valida(self):
        Session.objects.create(session_key="velha", session_data="x",
                               expire_date=timezone.now() - timedelta(hours=1))
        Session.objects.create(session_key="nova", session_data="x",
                               expire_date=timezone.now() + timedelta(hours=1))
        tarefa = higiene.sessoes_vencidas(fazer=True)
        self.assertEqual(tarefa.quantidade, 1)
        self.assertTrue(tarefa.feito)
        self.assertEqual([s.session_key for s in Session.objects.all()], ["nova"])


class EnviosTest(TestCase):
    def test_guarda_os_recentes_e_apaga_os_antigos(self):
        for dias in (1, 30, 200):
            registro = EnvioDeRelatorio.objects.create(
                rotina="contas", canal=Canal.EMAIL, deu_certo=True,
                destinatarios="cabanadojacaranda@gmail.com",
            )
            EnvioDeRelatorio.objects.filter(pk=registro.pk).update(
                quando=timezone.now() - timedelta(days=dias)
            )
        tarefa = higiene.envio_de_relatorios(fazer=True)
        self.assertEqual(tarefa.quantidade, 1, "só o de 200 dias passa dos 90")
        self.assertEqual(EnvioDeRelatorio.objects.count(), 2)


class SincronizacoesSemDadosTest(TestCase):
    def test_sai_a_antiga_sem_dados_e_fica_a_concluida(self):
        # Mais de 60 porque a tela mostra as 60 últimas e elas nunca saem: só a
        # partir da 61ª é que a limpeza tem o que apagar.
        velhas_vazias = [
            importacao(dias_atras=200 + i, situacao=Importacao.Situacao.SEM_NOVIDADE)
            for i in range(62)
        ]
        velha_boa = importacao(dias_atras=300, situacao=Importacao.Situacao.CONCLUIDA)
        tarefa = higiene.sincronizacoes_sem_dados(fazer=True)
        self.assertEqual(tarefa.quantidade, 2, "as 2 mais velhas sem dados; a concluída não conta")
        restantes = set(Importacao.objects.values_list("pk", flat=True))
        self.assertIn(velha_boa.pk, restantes, "sincronização que trouxe dados nunca sai daqui")
        self.assertNotIn(velhas_vazias[-1].pk, restantes, "a mais velha sem dados sai")
        self.assertEqual(Importacao.objects.count(), 61, "as 60 da tela mais a que trouxe dados")

    def test_as_sessenta_da_tela_nunca_saem(self):
        for _ in range(3):
            importacao(dias_atras=300, situacao=Importacao.Situacao.FALHOU)
        tarefa = higiene.sincronizacoes_sem_dados(fazer=True)
        self.assertEqual(tarefa.quantidade, 0, "a tela mostra as 60 últimas, e elas ficam")
        self.assertEqual(Importacao.objects.count(), 3)


class CopiaDoSetTest(TestCase):
    def test_apaga_a_copia_e_conta_o_tamanho(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "set.fdb"
            caminho.write_bytes(b"x" * 2048)
            with override_settings(IMPORTACAO_PASTA_TRABALHO=pasta):
                tarefa = higiene.copia_do_set(fazer=True)
            self.assertEqual(tarefa.quantidade, 1)
            self.assertEqual(tarefa.bytes, 2048)
            self.assertTrue(tarefa.feito)
            self.assertFalse(caminho.exists())

    def test_com_sincronizacao_rodando_a_copia_fica(self):
        Importacao.objects.create(
            origem=Importacao.Origem.BANCO, situacao=Importacao.Situacao.EM_ANDAMENTO,
            iniciada_em=timezone.now(),
        )
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "set.fdb"
            caminho.write_bytes(b"x")
            with override_settings(IMPORTACAO_PASTA_TRABALHO=pasta):
                tarefa = higiene.copia_do_set(fazer=True)
            self.assertTrue(caminho.exists(), "não se apaga arquivo que a importação está lendo")
            self.assertFalse(tarefa.feito)
            self.assertIn("sincronização rodando", tarefa.aviso)

    def test_pasta_que_nao_existe_nao_e_erro(self):
        with override_settings(IMPORTACAO_PASTA_TRABALHO="/nao/existe/mesmo"):
            tarefa = higiene.copia_do_set(fazer=True)
        self.assertEqual(tarefa.quantidade, 0)
        self.assertEqual(tarefa.aviso, "")


class AnexosOrfaosTest(TestCase):
    def test_apaga_o_arquivo_sem_registro(self):
        with tempfile.TemporaryDirectory() as pasta:
            orfao = Path(pasta) / "processos" / "9" / "ab"
            orfao.mkdir(parents=True)
            arquivo = orfao / "abcdef"
            arquivo.write_bytes(b"conteudo")
            with override_settings(MEDIA_ROOT=pasta):
                tarefa = higiene.anexos_orfaos(fazer=True)
            self.assertEqual(tarefa.quantidade, 1)
            self.assertFalse(arquivo.exists())


class NaoEncostaNoQueENossoTest(TestCase):
    """A promessa que o comando faz na tela: o que é nosso não sai nunca."""

    def test_auditoria_e_dado_nosso_ficam(self):
        from apps.fornecedores.models import Fornecedor

        imp = importacao(dias_atras=200)
        ProdutoImportado.objects.create(importacao=imp, codigo="P1", estoque=Decimal("1"))
        Lancamento.objects.create(
            importacao=imp, tipo=Lancamento.Tipo.PAGAR, contraparte="FORNECEDOR",
            valor=Decimal("10"), vencimento=timezone.localdate(),
        )
        Fornecedor.objects.create(nome="VIME LENZI", prazo_dias=10)
        registrar("teste.da.higiene", servico="teste")
        with override_settings(IMPORTACAO_MANTER=0):
            higiene.levantar(fazer=True, arrumar=False)
        self.assertEqual(ProdutoImportado.objects.count(), 0, "a foto do SET sai")
        self.assertEqual(Lancamento.objects.count(), 0, "a foto das contas sai")
        self.assertEqual(Fornecedor.objects.count(), 1, "a ficha que a gerência preencheu fica")
        self.assertEqual(
            EventoAuditoria.objects.filter(acao="teste.da.higiene").count(), 1, "auditoria fica",
        )


class ComandoTest(TestCase):
    def test_conferir_mostra_o_que_tem_e_nao_apaga(self):
        imp = importacao(dias_atras=200)
        ProdutoImportado.objects.create(importacao=imp, codigo="P1", estoque=Decimal("1"))
        saida = StringIO()
        with override_settings(IMPORTACAO_MANTER=0):
            call_command("higienizar", stdout=saida)
        texto = saida.getvalue()
        self.assertIn("Conferindo", texto)
        self.assertIn("Fotos antigas do SET", texto)
        self.assertIn("Nada aqui toca no SET", texto)
        self.assertEqual(ProdutoImportado.objects.count(), 1)

    def test_fazer_limpa_e_registra_na_auditoria(self):
        imp = importacao(dias_atras=200)
        ProdutoImportado.objects.create(importacao=imp, codigo="P1", estoque=Decimal("1"))
        saida = StringIO()
        with override_settings(IMPORTACAO_MANTER=0):
            call_command("higienizar", "--fazer", "--sem-arrumar", stdout=saida)
        self.assertIn("Limpeza concluída", saida.getvalue())
        self.assertEqual(ProdutoImportado.objects.count(), 0)
        self.assertTrue(EventoAuditoria.objects.filter(acao="sistema.higienizado").exists())

    def test_sistema_limpo_diz_que_nao_achou_nada(self):
        saida = StringIO()
        call_command("higienizar", stdout=saida)
        self.assertIn("Sistema limpo", saida.getvalue())


class TextoTest(TestCase):
    def test_tamanho_em_portugues(self):
        self.assertEqual(higiene.quanto(512), "512,0 B")
        self.assertEqual(higiene.quanto(382 * 1024 * 1024), "382,0 MB")

    def test_numero_com_ponto_de_milhar(self):
        self.assertEqual(higiene.numero(11274), "11.274")

    def test_singular_e_plural_na_palavra(self):
        self.assertEqual(higiene.Tarefa("x", "y", quantidade=1, unidade="arquivo").quantos, "1 arquivo")
        self.assertEqual(higiene.Tarefa("x", "y", quantidade=4, unidade="arquivo").quantos, "4 arquivos")
