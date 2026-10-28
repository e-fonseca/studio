"""O vigia do backup: reenviar sozinho e falar antes de quebrar (1.33.0).

Pedido do Edson em 14/10/2026: *"Acessar de forma automática o github, sem ação humana,
método automatizado"*. O envio já era automático; o que faltava era ele não poder parar
em silêncio, e não depender de uma atualização acontecer.

Nenhum teste aqui fala com a internet.
"""

from datetime import date, timedelta
from io import StringIO
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.alertas import relatorios
from apps.backup import github, vigia
from apps.backup.models import ConfiguracaoDeBackup

AGORA = timezone.make_aware(timezone.datetime(2026, 10, 14, 10, 0))


def configurada(**campos):
    configuracao = ConfiguracaoDeBackup.atual()
    configuracao.repositorio = "e-fonseca/sistema"
    configuracao.ativo = True
    configuracao.token = "token-de-teste"
    for nome, valor in campos.items():
        setattr(configuracao, nome, valor)
    configuracao.save()
    return configuracao


class ALeituraDaValidade(TestCase):
    """O cabeçalho que o GitHub manda em toda resposta autenticada."""

    def test_le_a_data_do_cabecalho(self):
        respondeu, validade = github.validade_do_token(
            "dono", "repo", "x",
            abrir=lambda _p: {"github-authentication-token-expiration": "2026-12-31 17:00:00 UTC"})
        self.assertTrue(respondeu)
        self.assertEqual(validade, date(2026, 12, 31))

    def test_aceita_a_data_no_outro_formato(self):
        _r, validade = github.validade_do_token(
            "dono", "repo", "x",
            abrir=lambda _p: {"github-authentication-token-expiration": "2027-01-05T09:00:00Z"})
        self.assertEqual(validade, date(2027, 1, 5))

    def test_token_sem_prazo_responde_sem_data(self):
        """O token clássico pode não vencer. Respondeu, e a resposta é "não vence"."""
        respondeu, validade = github.validade_do_token("dono", "repo", "x", abrir=lambda _p: {})
        self.assertTrue(respondeu)
        self.assertIsNone(validade)

    def test_sem_internet_nao_respondeu(self):
        def cair(_pedido):
            raise OSError("sem rede")

        respondeu, validade = github.validade_do_token("dono", "repo", "x", abrir=cair)
        self.assertFalse(respondeu)
        self.assertIsNone(validade)

    def test_o_token_vai_no_cabecalho_e_nao_no_endereco(self):
        """Token em linha de comando ou em URL vaza; em cabeçalho, não."""
        vistos = {}

        def espiar(pedido):
            vistos["url"] = pedido.full_url
            vistos["auth"] = pedido.get_header("Authorization")
            return {}

        github.validade_do_token("dono", "repo", "segredo", abrir=espiar)
        self.assertNotIn("segredo", vistos["url"])
        self.assertEqual(vistos["auth"], "Bearer segredo")


class AnotarAValidade(TestCase):
    def test_guarda_o_que_o_github_disse(self):
        configurada()
        validade = vigia.anotar_validade_do_token(
            agora=AGORA, consultar=lambda *_a: (True, date(2026, 12, 31)))
        self.assertEqual(validade, date(2026, 12, 31))
        configuracao = ConfiguracaoDeBackup.atual()
        self.assertEqual(configuracao.token_validade, date(2026, 12, 31))
        self.assertEqual(configuracao.token_validade_lida_em, AGORA)

    def test_sem_internet_nao_apaga_a_validade_que_ja_estava_de_pe(self):
        """Um minuto sem rede apagaria o aviso de vencimento, e ninguém saberia."""
        configurada(token_validade=date(2026, 10, 20),
                    token_validade_lida_em=AGORA - timedelta(days=5))
        vigia.anotar_validade_do_token(agora=AGORA, consultar=lambda *_a: (False, None))
        self.assertEqual(ConfiguracaoDeBackup.atual().token_validade, date(2026, 10, 20))

    def test_nao_pergunta_mais_de_uma_vez_por_dia(self):
        """É chamada de rede dentro de tarefa que acorda de hora em hora."""
        configurada(token_validade=date(2026, 12, 31),
                    token_validade_lida_em=AGORA - timedelta(hours=2))
        chamou = []

        def contar(*_a):
            chamou.append(1)
            return True, date(2027, 1, 1)

        vigia.anotar_validade_do_token(agora=AGORA, consultar=contar)
        self.assertEqual(chamou, [])

    def test_sem_token_nao_pergunta_nada(self):
        chamou = []
        vigia.anotar_validade_do_token(agora=AGORA,
                                       consultar=lambda *_a: chamou.append(1) or (True, None))
        self.assertEqual(chamou, [])


class ASituacao(TestCase):
    def test_sem_token_a_loja_esta_descoberta(self):
        estado = vigia.situacao(agora=AGORA)
        self.assertEqual(estado.gravidade, vigia.Gravidade.ERRO)
        self.assertTrue(estado.precisa_de_voce)
        self.assertIn("token", estado.frase)

    def test_configurado_mas_desligado(self):
        configurada(ativo=False)
        estado = vigia.situacao(agora=AGORA)
        self.assertEqual(estado.gravidade, vigia.Gravidade.ATENCAO)
        self.assertTrue(estado.precisa_de_voce)

    def test_em_dia(self):
        configurada(ultimo_sucesso_em=AGORA - timedelta(hours=3), ultimo_deu_certo=True,
                    ultimos_arquivos=500)
        estado = vigia.situacao(agora=AGORA)
        self.assertTrue(estado.ok)
        self.assertFalse(estado.tem_noticia)
        self.assertFalse(estado.precisa_de_voce)

    def test_em_dia_diz_que_e_o_programa_e_que_so_sobe_com_alteracao(self):
        """27/10/2026: "a nomenclatura deixa a entender outra coisa". A data parada de 22/10
        parecia backup atrasado; era a data da última versão."""
        from apps.core import versao  # noqa: PLC0415

        configurada(ultimo_sucesso_em=AGORA - timedelta(days=5), ultimo_deu_certo=True,
                    ultimos_arquivos=535)
        estado = vigia.situacao(agora=AGORA)
        self.assertIn("cópia do programa", estado.titulo.lower())
        self.assertIn(f"versão {versao.atual().numero}", estado.frase)
        self.assertIn("só muda quando há alteração ou implementação", estado.frase)

    def test_token_vencendo_avisa_antes(self):
        configurada(ultimo_sucesso_em=AGORA, ultimo_deu_certo=True,
                    token_validade=(AGORA + timedelta(days=4)).date())
        estado = vigia.situacao(agora=AGORA)
        self.assertEqual(estado.gravidade, vigia.Gravidade.ATENCAO)
        self.assertIn("vence em 4 dias", estado.titulo)
        self.assertTrue(estado.precisa_de_voce)

    def test_token_vencido_e_erro(self):
        configurada(ultimo_sucesso_em=AGORA, ultimo_deu_certo=True,
                    token_validade=(AGORA - timedelta(days=1)).date())
        estado = vigia.situacao(agora=AGORA)
        self.assertEqual(estado.gravidade, vigia.Gravidade.ERRO)
        self.assertIn("venceu", estado.titulo)

    def test_token_com_prazo_longo_nao_vira_aviso(self):
        configurada(ultimo_sucesso_em=AGORA, ultimo_deu_certo=True,
                    token_validade=(AGORA + timedelta(days=200)).date())
        self.assertTrue(vigia.situacao(agora=AGORA).ok)

    def test_copia_velha_e_erro_e_diz_de_quando_e_a_ultima(self):
        configurada(ultimo_sucesso_em=AGORA - timedelta(days=40), ultimo_deu_certo=True)
        estado = vigia.situacao(agora=AGORA)
        self.assertEqual(estado.gravidade, vigia.Gravidade.ERRO)
        self.assertIn("40 dias", estado.titulo)

    def test_copia_velha_com_falha_pede_gente_copia_velha_sem_falha_nao(self):
        """Falha do GitHub é recado para alguém; atraso que o sistema vai retentar não é."""
        configurada(ultimo_sucesso_em=AGORA - timedelta(days=40),
                    ultimo_envio_em=AGORA, ultimo_deu_certo=False,
                    ultimo_resultado="O GitHub recusou o token (401).")
        self.assertTrue(vigia.situacao(agora=AGORA).precisa_de_voce)
        configurada(ultimo_sucesso_em=AGORA - timedelta(days=40), ultimo_deu_certo=True)
        self.assertFalse(vigia.situacao(agora=AGORA).precisa_de_voce)

    def test_nunca_enviou_ainda(self):
        configurada()
        estado = vigia.situacao(agora=AGORA)
        self.assertEqual(estado.gravidade, vigia.Gravidade.ATENCAO)
        self.assertIn("Nenhuma cópia subiu", estado.titulo)

    def test_a_primeira_tentativa_falhando_mostra_o_motivo(self):
        """Dizer "nenhuma cópia subiu ainda" esconderia o 401, que é o que se conserta."""
        configurada(ultimo_envio_em=AGORA, ultimo_deu_certo=False,
                    ultimo_resultado="O GitHub recusou o token (401).")
        estado = vigia.situacao(agora=AGORA)
        self.assertEqual(estado.gravidade, vigia.Gravidade.ERRO)
        self.assertIn("401", estado.frase)
        self.assertTrue(estado.precisa_de_voce)

    def test_uma_falha_recente_com_copia_nova_e_so_atencao(self):
        configurada(ultimo_sucesso_em=AGORA - timedelta(days=2), ultimo_envio_em=AGORA,
                    ultimo_deu_certo=False, ultimo_resultado="Não consegui falar com o GitHub.")
        estado = vigia.situacao(agora=AGORA)
        self.assertEqual(estado.gravidade, vigia.Gravidade.ATENCAO)
        self.assertIn("tenta de novo sozinho", estado.frase)


class ReenviarSozinho(TestCase):
    """O que cobre o mês sem atualização nenhuma e a atualização que falhou no meio."""

    def test_copia_velha_dispara_o_envio(self):
        configurada(ultimo_sucesso_em=AGORA - timedelta(days=30),
                    ultimo_envio_em=AGORA - timedelta(days=30), ultimo_deu_certo=True)
        chamou = []
        vigia.reenviar_se_atrasado(agora=AGORA, enviar=lambda **_k: chamou.append(1))
        self.assertEqual(chamou, [1])

    def test_copia_nova_nao_dispara_nada(self):
        configurada(ultimo_sucesso_em=AGORA - timedelta(days=2),
                    ultimo_envio_em=AGORA - timedelta(days=2), ultimo_deu_certo=True)
        chamou = []
        vigia.reenviar_se_atrasado(agora=AGORA, enviar=lambda **_k: chamou.append(1))
        self.assertEqual(chamou, [])

    def test_nao_tenta_mais_de_uma_vez_por_dia(self):
        """A tarefa acorda de hora em hora, e o GitHub trata insistência como abuso."""
        configurada(ultimo_sucesso_em=AGORA - timedelta(days=30),
                    ultimo_envio_em=AGORA - timedelta(hours=3), ultimo_deu_certo=False)
        chamou = []
        vigia.reenviar_se_atrasado(agora=AGORA, enviar=lambda **_k: chamou.append(1))
        self.assertEqual(chamou, [])

    def test_desligado_nao_envia(self):
        configurada(ativo=False, ultimo_sucesso_em=AGORA - timedelta(days=30))
        chamou = []
        vigia.reenviar_se_atrasado(agora=AGORA, enviar=lambda **_k: chamou.append(1))
        self.assertEqual(chamou, [])

    def test_falha_do_github_nao_derruba_a_tarefa(self):
        """Ela está no caminho dos alertas: cair aqui deixaria a loja sem os relatórios."""
        configurada(ultimo_sucesso_em=AGORA - timedelta(days=30),
                    ultimo_envio_em=AGORA - timedelta(days=30), ultimo_deu_certo=True)

        def recusar(**_k):
            raise github.NaoDeuCerto("O GitHub recusou o token (401).")

        self.assertIsNone(vigia.reenviar_se_atrasado(agora=AGORA, enviar=recusar))


class ORelatorioDoVigia(TestCase):
    def test_backup_em_dia_nao_tem_noticia(self):
        """Aviso que chega todo dia dizendo "está tudo certo" é aviso que ninguém abre."""
        configurada(ultimo_sucesso_em=AGORA, ultimo_deu_certo=True)
        relatorio = relatorios.montar("backup", agora=AGORA)
        self.assertFalse(relatorio.tem_noticia)
        self.assertEqual(relatorio.blocos, [])

    def test_problema_vira_relatorio_com_a_frase_e_o_link(self):
        configurada(ultimo_sucesso_em=AGORA - timedelta(days=40), ultimo_deu_certo=True)
        relatorio = relatorios.montar("backup", agora=AGORA)
        self.assertTrue(relatorio.tem_noticia)
        self.assertIn("40 dias", relatorio.manchete)
        self.assertEqual(relatorio.caminho, "/sistema/backup/")

    def test_quando_precisa_de_gente_o_relatorio_explica_por_que(self):
        relatorio = relatorios.montar("backup", agora=AGORA)
        self.assertTrue(relatorio.tem_noticia)
        self.assertTrue(any("única parte" in b.frase or "único passo" in b.frase
                            for b in relatorio.blocos))

    def test_a_tarefa_de_hora_em_hora_nao_manda_nada_com_o_backup_em_dia(self):
        """O caminho inteiro, da tarefa do Windows até a caixa de entrada vazia."""
        from apps.alertas.tests.test_alertas import configuracao_pronta, enviando_para_a_memoria

        configuracao_pronta()
        configurada(ultimo_sucesso_em=timezone.now(), ultimo_deu_certo=True)
        with (enviando_para_a_memoria(),
              mock.patch("apps.backup.vigia.validade_do_token",
                         return_value=(True, date(2027, 1, 1))) as consulta):
            call_command("enviar_relatorios", stdout=StringIO(), rotina="backup")
        self.assertEqual(len(mail.outbox), 0)
        # E a tarefa perguntou a validade do token de passagem, que é o outro lado do vigia.
        self.assertTrue(consulta.called)
        self.assertEqual(ConfiguracaoDeBackup.atual().token_validade, date(2027, 1, 1))
