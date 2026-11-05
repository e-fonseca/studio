"""O aviso pelo Telegram: o robô, a conversa, a mensagem e os erros em português.

Pedido do Edson em 11/10/2026: "quero junto ao e-mail também seja enviado notificação
pelo telegram". Nada aqui fala com a internet: tudo passa por `telegram._pedir`, e é
essa função que os testes substituem.

O que estes testes protegem:

1. **O token não fica legível no banco nem volta para a tela.** Quem tem o token manda
   mensagem no nome da loja.
2. **O erro do Telegram vira frase de loja.** "Bad Request: chat not found" não diz a
   ninguém o que fazer.
3. **Os dois canais são independentes.** Telegram entregue não faz o sistema achar que
   o e-mail do dia já saiu.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.alertas import agenda, envio, relatorios, telegram
from apps.alertas.models import (Canal, ConfiguracaoDeEmail, ConfiguracaoDeTelegram,
                                 EnvioDeRelatorio, Rotina)
from apps.alertas.tests.test_alertas import configuracao_pronta, enviando_para_a_memoria
from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO
from apps.core.fabricas import SENHA_TESTE, usuario

TOKEN = "123456:abcdefghijklmnopqrstuvwxyz"


def telegram_pronto(**extra):
    """O Telegram como fica depois de alguém preencher a tela."""
    configuracao = ConfiguracaoDeTelegram.atual()
    configuracao.token = TOKEN
    configuracao.chat_id = "987654321"
    configuracao.chat_nome = "Edson"
    configuracao.ativo = True
    for campo, valor in extra.items():
        setattr(configuracao, campo, valor)
    configuracao.save()
    return configuracao


class Espiao:
    """Fica no lugar do `_pedir` e guarda o que teria sido mandado ao Telegram."""

    def __init__(self, resultado=None, erro=None):
        self.resultado = resultado if resultado is not None else {"message_id": 1}
        self.erro = erro
        self.chamadas = []

    def __call__(self, token, metodo, dados=None):
        self.chamadas.append({"token": token, "metodo": metodo, "dados": dados or {}})
        if self.erro:
            raise telegram.ErroDoTelegram(self.erro)
        return self.resultado

    @property
    def texto(self):
        return self.chamadas[-1]["dados"]["text"]


def mandando_para_o_espiao(espiao):
    return mock.patch.object(telegram, "_pedir", espiao)


class ConfiguracaoTest(TestCase):
    def test_nasce_vazia_e_dizendo_o_que_falta(self):
        configuracao = ConfiguracaoDeTelegram.atual()
        self.assertFalse(configuracao.ativo)
        self.assertFalse(configuracao.pronta)
        self.assertEqual(configuracao.o_que_falta,
                         ["o token do robô", "a conversa para onde mandar"])

    def test_e_uma_linha_so(self):
        """Duas configurações criariam a pergunta "qual delas está valendo"."""
        self.assertEqual(ConfiguracaoDeTelegram.atual().pk, 1)
        self.assertEqual(ConfiguracaoDeTelegram.atual().pk, 1)
        self.assertEqual(ConfiguracaoDeTelegram.objects.count(), 1)

    def test_o_token_nao_fica_legivel_no_banco(self):
        telegram_pronto()
        guardado = ConfiguracaoDeTelegram.objects.values_list("token_guardado", flat=True)[0]
        self.assertNotIn(TOKEN, guardado)
        self.assertEqual(ConfiguracaoDeTelegram.atual().token, TOKEN)

    def test_para_quem_diz_o_nome_e_o_numero(self):
        self.assertEqual(telegram_pronto().para_quem, "Edson (987654321)")


class MensagemTest(TestCase):
    def test_a_manchete_vem_primeiro(self):
        """É a manchete que decide se a pessoa abre o resto."""
        relatorio = relatorios.de_teste()
        texto = telegram.texto_do_relatorio(relatorio)
        linhas = [linha for linha in texto.splitlines() if linha.strip()]
        self.assertIn("Studio", linhas[0])
        self.assertIn("sistema consegue mandar e-mail", texto)

    def test_leva_o_endereco_do_sistema_inteiro(self):
        """Link relativo numa mensagem de celular não abre nada."""
        texto = telegram.texto_do_relatorio(relatorios.de_teste())
        self.assertIn("https://", texto)
        self.assertIn("/studio/alertas/", texto)

    def test_mensagem_comprida_e_cortada_antes_do_telegram_cortar(self):
        """Cortada pelo servidor, ela perde o fim, que é onde está o link."""
        relatorio = relatorios.de_teste()
        relatorio.manchete = "palavra " * 2000
        texto = telegram.texto_do_relatorio(relatorio)
        self.assertLessEqual(len(texto), telegram.MAXIMO + 100)
        self.assertIn("relatório inteiro está no sistema", texto)

    def test_vai_sem_formatacao(self):
        """Nome de produto da loja tem *, _ e ( à vontade; Markdown estragaria a mensagem."""
        espiao = Espiao()
        with mandando_para_o_espiao(espiao):
            telegram.enviar(relatorios.de_teste(), telegram_pronto())
        self.assertNotIn("parse_mode", espiao.chamadas[-1]["dados"])


class EnvioTest(TestCase):
    def test_manda_para_a_conversa_configurada_e_registra(self):
        espiao = Espiao()
        with mandando_para_o_espiao(espiao):
            registro = telegram.enviar_teste(telegram_pronto(), disparado_por="edson")
        self.assertTrue(registro.deu_certo, registro.erro)
        self.assertEqual(registro.canal, Canal.TELEGRAM)
        self.assertTrue(registro.por_telegram)
        self.assertEqual(espiao.chamadas[-1]["metodo"], "sendMessage")
        self.assertEqual(espiao.chamadas[-1]["dados"]["chat_id"], "987654321")
        self.assertEqual(espiao.chamadas[-1]["token"], TOKEN)

    def test_sem_configurar_registra_o_que_falta_e_nao_chama_o_telegram(self):
        espiao = Espiao()
        with mandando_para_o_espiao(espiao):
            registro = telegram.enviar_teste(ConfiguracaoDeTelegram.atual())
        self.assertFalse(registro.deu_certo)
        self.assertIn("o token do robô", registro.erro)
        self.assertEqual(espiao.chamadas, [])

    def test_conversa_errada_vira_frase_de_loja(self):
        espiao = Espiao(erro="Bad Request: chat not found")
        with mandando_para_o_espiao(espiao):
            registro = telegram.enviar_teste(telegram_pronto())
        self.assertFalse(registro.deu_certo)
        self.assertIn("não encontrou essa conversa", registro.erro)
        self.assertIn("chat not found", registro.erro)

    def test_token_errado_vira_frase_de_loja(self):
        espiao = Espiao(erro="Unauthorized")
        with mandando_para_o_espiao(espiao):
            registro = telegram.enviar_teste(telegram_pronto())
        self.assertIn("não reconheceu o token", registro.erro)

    def test_sem_internet_vira_frase_de_loja(self):
        espiao = Espiao(erro="[Errno -2] Name or service not known")
        with mandando_para_o_espiao(espiao):
            registro = telegram.enviar_teste(telegram_pronto())
        self.assertIn("resolver api.telegram.org", registro.erro)

    def test_erro_desconhecido_vai_cru_em_vez_de_sumir(self):
        espiao = Espiao(erro="aconteceu algo novo")
        with mandando_para_o_espiao(espiao):
            registro = telegram.enviar_teste(telegram_pronto())
        self.assertEqual(registro.erro, "aconteceu algo novo")

    def test_o_token_nunca_entra_no_registro_do_envio(self):
        espiao = Espiao(erro="Unauthorized")
        with mandando_para_o_espiao(espiao):
            registro = telegram.enviar_teste(telegram_pronto())
        texto = " ".join([registro.erro, registro.resumo, registro.destinatarios,
                          registro.assunto])
        self.assertNotIn(TOKEN, texto)

    def test_dia_sem_noticia_nao_manda_aviso_mas_deixa_registro(self):
        espiao = Espiao()
        with mandando_para_o_espiao(espiao):
            registro = telegram.enviar_rotina(Rotina.CONTAS, telegram_pronto())
        self.assertTrue(registro.sem_noticia)
        self.assertEqual(espiao.chamadas, [])
        self.assertEqual(registro.situacao, "sem novidade")

    def test_mandar_agora_avisa_mesmo_sem_noticia(self):
        espiao = Espiao()
        with mandando_para_o_espiao(espiao):
            registro = telegram.enviar_rotina(Rotina.CONTAS, telegram_pronto(), forcar=True)
        self.assertTrue(registro.deu_certo, registro.erro)
        self.assertEqual(len(espiao.chamadas), 1)


class DescobrirConversaTest(TestCase):
    def test_lista_as_conversas_que_falaram_com_o_robo(self):
        espiao = Espiao(resultado=[
            {"message": {"chat": {"id": 111, "first_name": "Edson", "username": "edson"}}},
            {"message": {"chat": {"id": -222, "title": "Studio Industrial"}}},
        ])
        with mandando_para_o_espiao(espiao):
            achados, erro = telegram.descobrir_chats(telegram_pronto())
        self.assertEqual(erro, "")
        self.assertEqual([c["id"] for c in achados], ["-222", "111"])
        self.assertEqual(achados[0]["nome"], "Studio Industrial")
        self.assertEqual(achados[1]["nome"], "Edson (@edson)")

    def test_nao_repete_a_mesma_conversa(self):
        espiao = Espiao(resultado=[
            {"message": {"chat": {"id": 111, "first_name": "Edson"}}},
            {"message": {"chat": {"id": 111, "first_name": "Edson"}}},
        ])
        with mandando_para_o_espiao(espiao):
            achados, _erro = telegram.descobrir_chats(telegram_pronto())
        self.assertEqual(len(achados), 1)

    def test_robo_que_ninguem_falou_explica_o_que_fazer(self):
        espiao = Espiao(resultado=[])
        with mandando_para_o_espiao(espiao):
            achados, erro = telegram.descobrir_chats(telegram_pronto())
        self.assertEqual(achados, [])
        self.assertIn("mande qualquer mensagem", erro)

    def test_sem_token_nao_pergunta_nada(self):
        espiao = Espiao()
        with mandando_para_o_espiao(espiao):
            achados, erro = telegram.descobrir_chats(ConfiguracaoDeTelegram.atual())
        self.assertEqual(achados, [])
        self.assertIn("grave o token", erro)
        self.assertEqual(espiao.chamadas, [])


class CanaisIndependentesTest(TestCase):
    """Telegram entregue não pode fazer o e-mail do dia deixar de sair."""

    def setUp(self):
        self.configuracao = configuracao_pronta(
            hora_diaria=time(7, 0), hora_semanal=time(7, 10))
        self.quinta = timezone.make_aware(datetime(2026, 10, 8, 8, 0))

    def test_aviso_de_telegram_nao_resolve_a_pendencia_do_email(self):
        EnvioDeRelatorio.objects.create(rotina=Rotina.CONTAS, canal=Canal.TELEGRAM,
                                        deu_certo=True, quando=self.quinta)
        devidas = agenda.devidas(self.configuracao, agora=self.quinta, canal=Canal.EMAIL)
        self.assertIn(Rotina.CONTAS, devidas)
        no_telegram = agenda.devidas(self.configuracao, agora=self.quinta, canal=Canal.TELEGRAM)
        self.assertNotIn(Rotina.CONTAS, no_telegram)

    def test_registro_antigo_sem_canal_conta_como_email(self):
        """Os envios gravados antes da 1.24.0 são todos de e-mail."""
        registro = EnvioDeRelatorio.objects.create(rotina=Rotina.CONTAS, deu_certo=True)
        self.assertEqual(registro.canal, Canal.EMAIL)

    def test_a_tarefa_manda_pelos_dois_canais_de_uma_vez(self):
        telegram_pronto()
        espiao = Espiao()
        with mandando_para_o_espiao(espiao), enviando_para_a_memoria():
            call_command("enviar_relatorios", stdout=StringIO(), rotina="contas", forcar=True)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(len(espiao.chamadas), 1)
        canais = sorted(EnvioDeRelatorio.objects.values_list("canal", flat=True))
        self.assertEqual(canais, [Canal.EMAIL, Canal.TELEGRAM])

    def test_telegram_desligado_na_tela_nao_manda_aviso(self):
        telegram_pronto(ativo=False)
        espiao = Espiao()
        with mandando_para_o_espiao(espiao), enviando_para_a_memoria():
            call_command("enviar_relatorios", stdout=StringIO(), rotina="contas", forcar=True)
        self.assertEqual(espiao.chamadas, [])
        self.assertEqual(len(mail.outbox), 1)

    def test_email_desligado_nao_impede_o_telegram(self):
        """O aviso do celular não pode depender da senha de uma caixa de e-mail."""
        configuracao_pronta(ativo=False)
        telegram_pronto()
        espiao = Espiao()
        with mandando_para_o_espiao(espiao), enviando_para_a_memoria():
            call_command("enviar_relatorios", stdout=StringIO(), rotina="contas", forcar=True)
        self.assertEqual(len(espiao.chamadas), 1)
        self.assertEqual(len(mail.outbox), 0)

    def test_os_dois_desligados_nao_mandam_nada(self):
        configuracao_pronta(ativo=False)
        espiao = Espiao()
        with mandando_para_o_espiao(espiao), enviando_para_a_memoria():
            call_command("enviar_relatorios", stdout=StringIO(), rotina="contas", forcar=True)
        self.assertEqual(espiao.chamadas, [])
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(EnvioDeRelatorio.objects.count(), 0)

    def test_o_relatorio_e_montado_uma_vez_para_os_dois(self):
        """Algumas destas contas passam por onze mil produtos."""
        telegram_pronto()
        espiao = Espiao()
        with mock.patch.object(relatorios, "montar", wraps=relatorios.montar) as montar:
            with mandando_para_o_espiao(espiao), enviando_para_a_memoria():
                call_command("enviar_relatorios", stdout=StringIO(), rotina="contas", forcar=True)
        self.assertEqual(montar.call_count, 1)


class TelaTest(TestCase):
    def setUp(self):
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)

    def test_a_tela_explica_como_criar_o_robo(self):
        resposta = self.client.get(reverse("alertas:painel"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "BotFather")
        self.assertContains(resposta, "Aviso no Telegram")

    def test_grava_o_token_e_a_conversa(self):
        resposta = self.client.post(reverse("alertas:configurar_telegram"),
                                    {"token": TOKEN, "chat_id": "987654321"})
        self.assertEqual(resposta.status_code, 302)
        configuracao = ConfiguracaoDeTelegram.atual()
        self.assertEqual(configuracao.token, TOKEN)
        self.assertEqual(configuracao.chat_id, "987654321")

    def test_campo_em_branco_mantem_o_token_que_ja_esta(self):
        telegram_pronto()
        self.client.post(reverse("alertas:configurar_telegram"),
                         {"token": "", "chat_id": "987654321", "ativo": "on"})
        self.assertEqual(ConfiguracaoDeTelegram.atual().token, TOKEN)

    def test_ligar_sem_token_e_recusado_na_tela(self):
        """Senão o erro só apareceria na madrugada seguinte."""
        resposta = self.client.post(reverse("alertas:configurar_telegram"),
                                    {"ativo": "on", "token": "", "chat_id": ""})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "falta preencher")
        self.assertFalse(ConfiguracaoDeTelegram.atual().ativo)

    def test_conversa_que_nao_e_numero_e_recusada(self):
        resposta = self.client.post(reverse("alertas:configurar_telegram"),
                                    {"token": TOKEN, "chat_id": "arroba-edson"})
        self.assertContains(resposta, "A conversa é um número")

    def test_o_botao_de_teste_manda_e_conta_o_que_aconteceu(self):
        telegram_pronto()
        espiao = Espiao()
        with mandando_para_o_espiao(espiao):
            resposta = self.client.post(reverse("alertas:testar_telegram"), follow=True)
        self.assertContains(resposta, "Confira o celular")
        self.assertEqual(len(espiao.chamadas), 1)

    def test_o_botao_de_descobrir_mostra_as_conversas(self):
        telegram_pronto()
        espiao = Espiao(resultado=[{"message": {"chat": {"id": 555, "title": "Loja"}}}])
        with mandando_para_o_espiao(espiao):
            resposta = self.client.post(reverse("alertas:descobrir_chat"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Loja")
        self.assertContains(resposta, "555")

    def test_escolher_a_conversa_grava_sem_mexer_no_resto(self):
        telegram_pronto(chat_id="111", chat_nome="antigo")
        self.client.post(reverse("alertas:usar_chat"),
                         {"chat_id": "-555", "chat_nome": "Grupo da loja"})
        configuracao = ConfiguracaoDeTelegram.atual()
        self.assertEqual(configuracao.chat_id, "-555")
        self.assertEqual(configuracao.chat_nome, "Grupo da loja")
        self.assertTrue(configuracao.ativo)
        self.assertEqual(configuracao.token, TOKEN)

    def test_o_administrativo_nao_configura_o_telegram(self):
        """A tela guarda o token do robô da loja: é da gerência, como a senha do e-mail."""
        usuario("operador", ADMINISTRATIVO)
        self.client.login(username="operador", password=SENHA_TESTE)
        for rota in ("alertas:configurar_telegram", "alertas:testar_telegram",
                     "alertas:descobrir_chat", "alertas:usar_chat"):
            self.assertEqual(self.client.post(reverse(rota)).status_code, 403, rota)
