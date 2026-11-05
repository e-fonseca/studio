"""A configuração do envio, a cifra da senha, o agendamento e o caminho do e-mail."""

from datetime import datetime, time, timedelta
from io import StringIO
from unittest import mock

from django.core import mail
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.alertas import agenda, cifra, envio, relatorios
from apps.alertas.models import ConfiguracaoDeEmail, EnvioDeRelatorio, Rotina

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"


def configuracao_pronta(**extra):
    """A configuração como fica depois de alguém preencher a tela."""
    configuracao = ConfiguracaoDeEmail.atual()
    configuracao.servidor = "smtp.hostinger.com"
    configuracao.porta = 465
    configuracao.usuario = "naoresponder@cabanadojacaranda.com.br"
    configuracao.senha = "senha-da-caixa"
    configuracao.destinatarios = "cabanadojacaranda@gmail.com"
    configuracao.ativo = True
    for campo, valor in extra.items():
        setattr(configuracao, campo, valor)
    configuracao.save()
    return configuracao


def enviando_para_a_memoria():
    """Troca o SMTP real pelo backend de memória, sem mexer na configuração da tela.

    O envio monta a conexão a partir do que está gravado (servidor, porta, senha), e
    não do EMAIL_BACKEND das settings — é isso que permite trocar o servidor de e-mail
    sem reiniciar o sistema. Em teste, então, quem tem de ser trocada é a função que
    abre a conexão.
    """
    return mock.patch.object(envio, "_conexao", lambda c: mail.get_connection(LOCMEM))


class CifraTest(TestCase):
    def test_ida_e_volta(self):
        guardado = cifra.cifrar("senha-de-aplicativo")
        self.assertNotIn("senha-de-aplicativo", guardado)
        self.assertEqual(cifra.decifrar(guardado), "senha-de-aplicativo")

    def test_vazio_continua_vazio(self):
        """Senão o modelo não sabe distinguir "sem senha" de "com senha"."""
        self.assertEqual(cifra.cifrar(""), "")
        self.assertEqual(cifra.decifrar(""), "")

    def test_campo_estragado_devolve_vazio_em_vez_de_estourar(self):
        """É o que acontece se a SECRET_KEY for trocada depois de gravar a senha."""
        self.assertEqual(cifra.decifrar("isto-não-é-nosso"), "")

    def test_senha_nao_fica_legivel_no_banco(self):
        configuracao = configuracao_pronta()
        guardado = ConfiguracaoDeEmail.objects.values_list("senha_guardada", flat=True).get(pk=1)
        self.assertNotIn("senha-da-caixa", guardado)
        self.assertEqual(configuracao.senha, "senha-da-caixa")


class ConfiguracaoTest(TestCase):
    def test_e_sempre_a_mesma_linha(self):
        primeira = ConfiguracaoDeEmail.atual()
        segunda = ConfiguracaoDeEmail.atual()
        self.assertEqual(primeira.pk, segunda.pk)
        self.assertEqual(ConfiguracaoDeEmail.objects.count(), 1)

    def test_a_hora_padrao_nasce_como_hora_e_nao_como_texto(self):
        """get_or_create não relê do banco: texto aqui estouraria em quem faz conta."""
        configuracao = ConfiguracaoDeEmail.atual()
        self.assertIsInstance(configuracao.hora_diaria, time)
        self.assertIsInstance(configuracao.hora_semanal, time)
        self.assertIsNotNone(agenda.proximo_envio(configuracao))

    def test_so_falta_a_senha_porque_o_resto_ja_vem_preenchido(self):
        """Servidor, porta, quem envia e para quem já são os da loja (10/10/2026)."""
        configuracao = ConfiguracaoDeEmail.atual()
        self.assertEqual(configuracao.servidor, "smtp.hostinger.com")
        self.assertEqual(configuracao.porta, 465)
        self.assertEqual(configuracao.usuario, "naoresponder@cabanadojacaranda.com.br")
        self.assertEqual(configuracao.lista_de_destinatarios, ["cabanadojacaranda@gmail.com"])
        self.assertEqual(configuracao.o_que_falta, ["a senha da caixa de e-mail"])
        self.assertFalse(configuracao.pronta)

    def test_a_porta_465_pede_ssl_e_a_587_pede_tls(self):
        """Trocar um pelo outro não dá erro de senha: dá conexão travada."""
        configuracao = ConfiguracaoDeEmail.atual()
        self.assertTrue(configuracao.porta_de_ssl)
        configuracao.porta = 587
        self.assertFalse(configuracao.porta_de_ssl)

    def test_preenchida_fica_pronta(self):
        configuracao = configuracao_pronta()
        self.assertEqual(configuracao.o_que_falta, [])
        self.assertTrue(configuracao.pronta)

    def test_destinatarios_um_por_linha_sem_sobra(self):
        configuracao = configuracao_pronta(
            destinatarios="  cabanadojacaranda@gmail.com \n\n  edson@exemplo.com\n"
        )
        self.assertEqual(
            configuracao.lista_de_destinatarios,
            ["cabanadojacaranda@gmail.com", "edson@exemplo.com"],
        )


class ProximoEnvioTest(TestCase):
    def setUp(self):
        self.configuracao = ConfiguracaoDeEmail.atual()
        self.configuracao.hora_diaria = time(7, 0)
        self.configuracao.hora_semanal = time(7, 10)
        self.configuracao.dia_semanal = ConfiguracaoDeEmail.DiaDaSemana.SEGUNDA

    def test_antes_da_hora_sai_hoje(self):
        agora = datetime(2026, 10, 8, 6, 0)  # quinta
        self.assertEqual(
            agenda.proximo_envio(self.configuracao, agora=agora)["diario"],
            datetime(2026, 10, 8, 7, 0),
        )

    def test_depois_da_hora_sai_amanha(self):
        agora = datetime(2026, 10, 8, 9, 0)
        self.assertEqual(
            agenda.proximo_envio(self.configuracao, agora=agora)["diario"],
            datetime(2026, 10, 9, 7, 0),
        )

    def test_semanal_cai_na_proxima_segunda(self):
        agora = datetime(2026, 10, 8, 9, 0)  # quinta
        self.assertEqual(
            agenda.proximo_envio(self.configuracao, agora=agora)["semanal"],
            datetime(2026, 10, 12, 7, 10),
        )

    def test_na_propria_segunda_depois_da_hora_pula_uma_semana(self):
        agora = datetime(2026, 10, 12, 9, 0)  # segunda
        self.assertEqual(
            agenda.proximo_envio(self.configuracao, agora=agora)["semanal"],
            datetime(2026, 10, 19, 7, 10),
        )


class ConexaoTest(TestCase):
    """Como a conexão é aberta. Não conecta: get_connection só monta o objeto."""

    def test_a_porta_465_abre_direto_em_ssl(self):
        conexao = envio._conexao(configuracao_pronta())
        self.assertEqual((conexao.host, conexao.port), ("smtp.hostinger.com", 465))
        self.assertTrue(conexao.use_ssl)
        self.assertFalse(conexao.use_tls)

    def test_a_porta_587_sobe_para_tls(self):
        conexao = envio._conexao(configuracao_pronta(porta=587))
        self.assertTrue(conexao.use_tls)
        self.assertFalse(conexao.use_ssl)

    def test_a_senha_gravada_cifrada_chega_decifrada_na_conexao(self):
        conexao = envio._conexao(configuracao_pronta())
        self.assertEqual(conexao.password, "senha-da-caixa")
        self.assertEqual(conexao.username, "naoresponder@cabanadojacaranda.com.br")


class ExplicarErroTest(TestCase):
    def test_senha_recusada_vira_frase_sobre_a_senha_da_caixa(self):
        frase = envio._explicar("(535, b'5.7.8 Username and Password not accepted')")
        self.assertIn("a senha é a da caixa que envia", frase)
        self.assertIn("5.7.8", frase)  # o original continua ali, para quem souber ler

    def test_porta_trocada_vira_frase_sobre_a_porta(self):
        """465 com TLS ou 587 com SSL dá erro de SSL, que não diz nada a ninguém."""
        frase = envio._explicar("[SSL: WRONG_VERSION_NUMBER] wrong version number")
        self.assertIn("é a porta trocada", frase)
        self.assertIn("465", frase)

    def test_erro_desconhecido_vai_cru(self):
        """Erro que ninguém previu escondido é pior do que erro feio."""
        self.assertEqual(envio._explicar("coisa nunca vista"), "coisa nunca vista")


class EnvioTest(TestCase):
    def test_sem_configuracao_registra_o_que_falta_e_nao_manda(self):
        registro = envio.enviar(relatorios.de_teste(), ConfiguracaoDeEmail.atual())
        self.assertFalse(registro.deu_certo)
        self.assertIn("a senha da caixa de e-mail", registro.erro)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(EnvioDeRelatorio.objects.count(), 1)

    def test_teste_de_configuracao_sai_com_assunto_e_com_as_duas_versoes(self):
        configuracao = configuracao_pronta()
        with enviando_para_a_memoria():
            registro = envio.enviar_teste(configuracao, disparado_por="edson")
        self.assertTrue(registro.deu_certo, registro.erro)
        self.assertEqual(len(mail.outbox), 1)
        mensagem = mail.outbox[0]
        self.assertTrue(mensagem.subject.startswith("[Studio] Teste de envio"))
        self.assertEqual(mensagem.to, ["cabanadojacaranda@gmail.com"])
        self.assertIn("Sistema do Studio", mensagem.from_email)
        self.assertIn("sistema consegue mandar e-mail", mensagem.body)
        tipos = [tipo for _corpo, tipo in mensagem.alternatives]
        self.assertEqual(tipos, ["text/html"])
        self.assertIn("Studio Industrial", mensagem.alternatives[0][0])

    def test_falha_do_servidor_vira_frase_de_loja_no_registro(self):
        import smtplib

        configuracao = configuracao_pronta()

        def recusar(_configuracao):
            raise smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted")

        with mock.patch.object(envio, "_conexao", recusar):
            registro = envio.enviar_teste(configuracao)
        self.assertFalse(registro.deu_certo)
        self.assertIn("a senha é a da caixa que envia", registro.erro)
        self.assertEqual(len(mail.outbox), 0)

    def test_a_senha_nunca_entra_no_registro_do_envio(self):
        configuracao = configuracao_pronta()
        with enviando_para_a_memoria():
            registro = envio.enviar_teste(configuracao, disparado_por="edson")
        texto = " ".join([registro.assunto, registro.erro, registro.resumo, registro.destinatarios])
        self.assertNotIn("senha-da-caixa", texto)

    def test_dia_sem_noticia_nao_gera_email_mas_gera_registro(self):
        """O diário só vale a pena abrir se não chegar em dia que não tem nada."""
        configuracao = configuracao_pronta()
        with enviando_para_a_memoria():
            registro = envio.enviar_rotina(Rotina.CONTAS, configuracao, disparado_por="tarefa diaria")
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(registro.deu_certo)
        self.assertTrue(registro.sem_noticia)
        self.assertEqual(registro.erro, "")
        self.assertEqual(registro.situacao, "sem novidade")

    def test_mandar_agora_manda_mesmo_sem_noticia(self):
        configuracao = configuracao_pronta()
        with enviando_para_a_memoria():
            registro = envio.enviar_rotina(
                Rotina.CONTAS, configuracao, disparado_por="edson", forcar=True
            )
        self.assertTrue(registro.deu_certo, registro.erro)
        self.assertEqual(len(mail.outbox), 1)

    def test_a_tela_ve_o_ultimo_envio_de_cada_relatorio(self):
        EnvioDeRelatorio.objects.create(rotina=Rotina.CONTAS, deu_certo=True, resumo="antigo",
                                        quando=timezone.now() - timedelta(days=2))
        recente = EnvioDeRelatorio.objects.create(rotina=Rotina.CONTAS, deu_certo=True, resumo="novo")
        ultimos = envio.ultimo_de_cada_rotina()
        self.assertEqual(ultimos[Rotina.CONTAS].pk, recente.pk)
        self.assertIsNone(ultimos[Rotina.ESTOQUE.value])


@override_settings(EMAIL_BACKEND=LOCMEM)
class ComandoTest(TestCase):
    """O comando é o que a tarefa agendada do Windows chama de madrugada."""

    def test_rotina_que_nao_existe_e_erro_de_uso(self):
        with self.assertRaises(CommandError):
            call_command("enviar_relatorios", stdout=StringIO(), rotina="mensal")

    def test_desligado_na_tela_nao_manda_nada(self):
        configuracao_pronta(ativo=False)
        with enviando_para_a_memoria():
            call_command("enviar_relatorios", stdout=StringIO(), rotina="diaria")
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(EnvioDeRelatorio.objects.count(), 0)

    def test_sem_nada_devido_nao_manda_nada(self):
        """O modo da tarefa de hora em hora: às 3h da manhã não há nada devido."""
        configuracao_pronta(hora_diaria=time(7, 0))
        with mock.patch.object(agenda, "devidas", lambda c, agora=None, canal=None: []):
            with enviando_para_a_memoria():
                call_command("enviar_relatorios", stdout=StringIO())
        self.assertEqual(EnvioDeRelatorio.objects.count(), 0)

    def test_diaria_forcada_manda_contas_vendas_do_dia_e_o_vigia_do_backup(self):
        """Três desde a 1.33.0. Forçada: sem --forcar o backup em dia não manda nada."""
        configuracao_pronta()
        with enviando_para_a_memoria():
            call_command("enviar_relatorios", stdout=StringIO(), rotina="diaria", forcar=True)
        self.assertEqual(len(mail.outbox), 3)
        self.assertEqual(
            sorted(EnvioDeRelatorio.objects.values_list("rotina", flat=True)),
            [Rotina.BACKUP, Rotina.CONTAS, Rotina.VENDAS],
        )

    def test_semanal_forcada_manda_estoque_e_compra(self):
        configuracao_pronta()
        with enviando_para_a_memoria():
            call_command("enviar_relatorios", stdout=StringIO(), rotina="semanal", forcar=True)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(
            sorted(EnvioDeRelatorio.objects.values_list("rotina", flat=True)),
            [Rotina.COMPRA, Rotina.ESTOQUE],
        )

    def test_falha_de_envio_nao_derruba_a_tarefa_agendada(self):
        """Tarefa "com erro" no Windows não avisa ninguém; o erro tem de ir para a tela."""
        configuracao_pronta()

        def recusar(_configuracao):
            raise OSError("Name or service not known")

        with mock.patch.object(envio, "_conexao", recusar):
            call_command("enviar_relatorios", stdout=StringIO(), rotina="contas", forcar=True)
        registro = EnvioDeRelatorio.objects.get()
        self.assertFalse(registro.deu_certo)
        self.assertIn("não foi encontrado pelo nome", registro.erro)


class AgendaTest(TestCase):
    """O que a tarefa de hora em hora pergunta: o que já passou da hora e não saiu."""

    def setUp(self):
        self.configuracao = configuracao_pronta(
            hora_diaria=time(7, 0), hora_semanal=time(7, 10),
            dia_semanal=ConfiguracaoDeEmail.DiaDaSemana.SEGUNDA,
        )
        self.quinta = timezone.make_aware(datetime(2026, 10, 8, 8, 0))
        self.segunda = timezone.make_aware(datetime(2026, 10, 12, 8, 0))

    def test_antes_da_hora_nada_e_devido(self):
        madrugada = timezone.make_aware(datetime(2026, 10, 8, 3, 0))
        self.assertEqual(agenda.devidas(self.configuracao, agora=madrugada), [])

    def test_depois_da_hora_o_diario_e_devido(self):
        """Três diárias desde a 1.33.0: contas, vendas do dia e o vigia do backup.

        O vigia é devido todo dia como os outros, mas só MANDA quando tem notícia: dia
        de backup em dia não gera e-mail nenhum (ver test_backup).
        """
        self.assertEqual(agenda.devidas(self.configuracao, agora=self.quinta),
                         [Rotina.CONTAS, Rotina.VENDAS, Rotina.BACKUP])

    def test_os_semanais_so_no_dia_escolhido_na_tela(self):
        self.assertNotIn(Rotina.ESTOQUE, agenda.devidas(self.configuracao, agora=self.quinta))
        devidas = agenda.devidas(self.configuracao, agora=self.segunda)
        self.assertEqual(devidas, [Rotina.CONTAS, Rotina.VENDAS, Rotina.BACKUP,
                                   Rotina.ESTOQUE, Rotina.COMPRA])

    def test_o_que_ja_saiu_hoje_nao_sai_de_novo(self):
        EnvioDeRelatorio.objects.create(rotina=Rotina.CONTAS, deu_certo=True, quando=self.quinta)
        self.assertNotIn(Rotina.CONTAS, agenda.devidas(self.configuracao, agora=self.quinta))

    def test_dia_sem_noticia_tambem_conta_como_resolvido(self):
        """Senão a tarefa montaria o mesmo relatório vazio a cada hora até meia-noite."""
        EnvioDeRelatorio.objects.create(rotina=Rotina.CONTAS, sem_noticia=True, quando=self.quinta)
        self.assertNotIn(Rotina.CONTAS, agenda.devidas(self.configuracao, agora=self.quinta))

    def test_falha_pode_ser_tentada_de_novo(self):
        EnvioDeRelatorio.objects.create(rotina=Rotina.CONTAS, erro="servidor recusou", quando=self.quinta)
        self.assertIn(Rotina.CONTAS, agenda.devidas(self.configuracao, agora=self.quinta))

    def test_mas_nao_a_cada_hora_do_dia(self):
        """Insistir de hora em hora é como a caixa de e-mail da loja é bloqueada."""
        for _ in range(agenda.TENTATIVAS_POR_DIA):
            EnvioDeRelatorio.objects.create(rotina=Rotina.CONTAS, erro="servidor recusou",
                                            quando=self.quinta)
        self.assertNotIn(Rotina.CONTAS, agenda.devidas(self.configuracao, agora=self.quinta))

    def test_o_de_ontem_nao_segura_o_de_hoje(self):
        ontem = self.quinta - timedelta(days=1)
        EnvioDeRelatorio.objects.create(rotina=Rotina.CONTAS, deu_certo=True, quando=ontem)
        self.assertIn(Rotina.CONTAS, agenda.devidas(self.configuracao, agora=self.quinta))

    def test_servidor_ligado_tarde_entrega_o_relatorio_do_dia(self):
        """Pular o dia porque o servidor estava desligado às 7h é perder a conta vencida."""
        tarde = timezone.make_aware(datetime(2026, 10, 8, 19, 0))
        self.assertIn(Rotina.CONTAS, agenda.devidas(self.configuracao, agora=tarde))
