"""A tela de alertas, o formulário da senha e a identificação na tela de entrada."""

from unittest import mock

from django.core import mail
from django.test import TestCase
from django.urls import reverse

from apps.alertas import envio
from apps.alertas.forms import ConfiguracaoForm
from apps.alertas.models import ConfiguracaoDeEmail, EnvioDeRelatorio, Rotina
from apps.alertas.tests.test_alertas import configuracao_pronta, enviando_para_a_memoria
from apps.auditoria.models import EventoAuditoria
from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.core.versao import atual as versao_atual

SENHA_DA_CAIXA = "senha-secreta-da-caixa"


class AcessoTest(TestCase):
    """Quem pode configurar o envio de e-mail da loja: só a gerência."""

    def test_vendedor_nao_entra(self):
        usuario("vendedor", VENDEDOR)
        self.client.login(username="vendedor", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("alertas:painel")).status_code, 403)

    def test_operador_administrativo_nao_entra(self):
        usuario("operador", ADMINISTRATIVO)
        self.client.login(username="operador", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("alertas:painel")).status_code, 403)

    def test_gerencia_entra(self):
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("alertas:painel")).status_code, 200)

    def test_sem_entrar_vai_para_a_tela_de_entrada(self):
        resposta = self.client.get(reverse("alertas:painel"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("contas:entrar"), resposta.url)

    def test_o_menu_nao_mostra_alertas_para_quem_nao_pode_configurar(self):
        usuario("vendedor", VENDEDOR)
        self.client.login(username="vendedor", password=SENHA_TESTE)
        corpo = self.client.get(reverse("importacao:consulta")).content.decode()
        self.assertNotIn(reverse("alertas:painel"), corpo)


class PainelTest(TestCase):
    def setUp(self):
        self.gerente = usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)

    def test_a_tela_diz_o_que_falta_antes_de_qualquer_coisa(self):
        corpo = self.client.get(reverse("alertas:painel")).content.decode()
        self.assertIn("Falta preencher para o envio funcionar", corpo)
        self.assertIn("a senha da caixa de e-mail", corpo)
        self.assertNotIn("Enviar e-mail de teste", corpo)  # sem configuração não há o que testar

    def test_preenchida_a_tela_diz_quando_sai_o_proximo(self):
        configuracao_pronta()
        corpo = self.client.get(reverse("alertas:painel")).content.decode()
        self.assertIn("Envio ligado", corpo)
        self.assertIn("cabanadojacaranda@gmail.com", corpo)
        self.assertIn("Enviar e-mail de teste", corpo)

    def test_os_tres_relatorios_aparecem_com_a_previa(self):
        corpo = self.client.get(reverse("alertas:painel")).content.decode()
        for rotina in (Rotina.CONTAS, Rotina.ESTOQUE, Rotina.COMPRA):
            self.assertIn(reverse("alertas:previa", args=[rotina.value]), corpo)
        for nome in ("Contas a pagar", "Estoque da loja", "Sugestão de compra"):
            self.assertIn(nome, corpo)
        self.assertIn("Todo dia", corpo)
        self.assertIn("Toda semana", corpo)

    def test_mandar_agora_so_aparece_quando_da_para_mandar(self):
        """Botão que não funciona é pior do que botão que não existe."""
        # Pelo endereço do botão, e não pelo texto: "Mandar agora" também aparece na
        # ajuda do F1, que está na página o tempo todo.
        endereco = reverse("alertas:mandar_agora", args=[Rotina.CONTAS.value])
        self.assertNotIn(endereco, self.client.get(reverse("alertas:painel")).content.decode())
        configuracao_pronta()
        self.assertIn(endereco, self.client.get(reverse("alertas:painel")).content.decode())

    def test_gravar_a_configuracao_guarda_a_senha_e_nao_a_devolve(self):
        resposta = self.client.post(reverse("alertas:painel"), {
            "servidor": "smtp.hostinger.com", "porta": "465", "usar_tls": "on",
            "usuario": "naoresponder@cabanadojacaranda.com.br", "senha": SENHA_DA_CAIXA,
            "remetente": "Sistema da Cabana",
            "destinatarios": "cabanadojacaranda@gmail.com",
            "hora_diaria": "07:00", "dia_semanal": "0", "hora_semanal": "07:10",
            "ativo": "on",
        })
        self.assertRedirects(resposta, reverse("alertas:painel"))
        configuracao = ConfiguracaoDeEmail.atual()
        self.assertTrue(configuracao.ativo)
        self.assertEqual(configuracao.senha, SENHA_DA_CAIXA)
        corpo = self.client.get(reverse("alertas:painel")).content.decode()
        self.assertNotIn(SENHA_DA_CAIXA, corpo)

    def test_a_senha_nao_entra_na_auditoria(self):
        self.client.post(reverse("alertas:painel"), {
            "servidor": "smtp.hostinger.com", "porta": "465", "usar_tls": "on",
            "usuario": "naoresponder@cabanadojacaranda.com.br", "senha": SENHA_DA_CAIXA,
            "remetente": "Sistema da Cabana", "destinatarios": "cabanadojacaranda@gmail.com",
            "hora_diaria": "07:00", "dia_semanal": "0", "hora_semanal": "07:10", "ativo": "on",
        })
        evento = EventoAuditoria.objects.filter(acao="alertas.configurado").get()
        self.assertNotIn(SENHA_DA_CAIXA, str(evento.depois) + str(evento.antes))
        self.assertTrue(evento.depois["tem_senha"])

    def test_botao_de_teste_manda_e_registra(self):
        configuracao_pronta()
        with enviando_para_a_memoria():
            resposta = self.client.post(reverse("alertas:testar"), follow=True)
        self.assertEqual(len(mail.outbox), 1)
        self.assertContains(resposta, "E-mail de teste enviado")
        self.assertTrue(EnvioDeRelatorio.objects.get(rotina=Rotina.TESTE).deu_certo)
        self.assertTrue(EventoAuditoria.objects.filter(acao="alertas.teste").exists())

    def test_erro_de_envio_aparece_em_portugues_na_tela(self):
        configuracao_pronta()

        def recusar(_configuracao):
            raise OSError("Connection refused")

        with mock.patch.object(envio, "_conexao", recusar):
            resposta = self.client.post(reverse("alertas:testar"), follow=True)
        self.assertContains(resposta, "Confira a porta")

    def test_mandar_agora_manda_mesmo_sem_noticia(self):
        configuracao_pronta()
        with enviando_para_a_memoria():
            resposta = self.client.post(
                reverse("alertas:mandar_agora", args=[Rotina.CONTAS.value]), follow=True
            )
        self.assertEqual(len(mail.outbox), 1)
        self.assertContains(resposta, "enviado para cabanadojacaranda@gmail.com")

    def test_rotina_desconhecida_nao_estoura(self):
        resposta = self.client.post(reverse("alertas:mandar_agora", args=["mensal"]), follow=True)
        self.assertContains(resposta, "Relatório desconhecido")

    def test_previa_mostra_o_e_mail_sem_mandar(self):
        resposta = self.client.get(reverse("alertas:previa", args=[Rotina.CONTAS.value]))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Cabana do Jacarandá")
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(EnvioDeRelatorio.objects.count(), 0)

    def test_a_tela_abre_depois_de_um_envio_que_falhou(self):
        """A lista de últimos envios é o que responde "não recebi o e-mail de ontem"."""
        EnvioDeRelatorio.objects.create(
            rotina=Rotina.CONTAS, deu_certo=False, erro="O Gmail recusou o usuário e a senha.",
            destinatarios="cabanadojacaranda@gmail.com", disparado_por="tarefa diaria",
        )
        resposta = self.client.get(reverse("alertas:painel"))
        self.assertContains(resposta, "não saiu")
        self.assertContains(resposta, "O Gmail recusou")


class FormularioTest(TestCase):
    def dados(self, **extra):
        base = {
            "servidor": "smtp.hostinger.com", "porta": "465", "usar_tls": "on",
            "usuario": "naoresponder@cabanadojacaranda.com.br", "remetente": "Sistema da Cabana",
            "destinatarios": "cabanadojacaranda@gmail.com",
            "hora_diaria": "07:00", "dia_semanal": "0", "hora_semanal": "07:10",
        }
        base.update(extra)
        return base

    def test_endereco_errado_e_recusado_na_hora_e_nao_na_madrugada(self):
        form = ConfiguracaoForm(self.dados(destinatarios="cabanadojacaranda"),
                                instance=ConfiguracaoDeEmail.atual())
        self.assertFalse(form.is_valid())
        self.assertIn("Não parece e-mail", str(form.errors))

    def test_varios_enderecos_um_por_linha(self):
        form = ConfiguracaoForm(
            self.dados(destinatarios=" a@exemplo.com \n\n b@exemplo.com "),
            instance=ConfiguracaoDeEmail.atual(),
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["destinatarios"], "a@exemplo.com\nb@exemplo.com")

    def test_ligar_o_envio_sem_senha_e_recusado(self):
        form = ConfiguracaoForm(self.dados(ativo="on"), instance=ConfiguracaoDeEmail.atual())
        self.assertFalse(form.is_valid())
        self.assertIn("a senha da caixa de e-mail", str(form.errors))

    def test_campo_em_branco_mantem_a_senha_que_ja_estava(self):
        configuracao = configuracao_pronta()
        form = ConfiguracaoForm(self.dados(ativo="on"), instance=configuracao)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().senha, "senha-da-caixa")

    def test_senha_nova_troca_a_antiga(self):
        configuracao = configuracao_pronta()
        form = ConfiguracaoForm(self.dados(ativo="on", senha=SENHA_DA_CAIXA), instance=configuracao)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().senha, SENHA_DA_CAIXA)

    def test_desligado_pode_ficar_pela_metade(self):
        """Dá para gravar o servidor hoje e a senha quando ela existir."""
        form = ConfiguracaoForm(self.dados(usuario="", destinatarios=""),
                                instance=ConfiguracaoDeEmail.atual())
        self.assertTrue(form.is_valid(), form.errors)


class TelaDeEntradaTest(TestCase):
    """Pedido do Edson em 08/10/2026: versão, servidor e IP perto do campo de entrada."""

    def test_a_versao_aparece_na_tela_de_entrada(self):
        resposta = self.client.get(reverse("contas:entrar"))
        self.assertContains(resposta, versao_atual().numero)
        self.assertContains(resposta, "identificacao-entrada")

    def test_diz_o_servidor_e_o_ip_de_quem_esta_acessando(self):
        resposta = self.client.get(reverse("contas:entrar"), REMOTE_ADDR="192.168.3.45")
        corpo = resposta.content.decode()
        self.assertIn("192.168.3.45", corpo)
        self.assertIn("testserver", corpo)
        self.assertIn("Seu acesso", corpo)

    def test_o_ip_mostrado_e_o_mesmo_que_a_auditoria_grava(self):
        """É o que faz a tela de entrada servir de conferência: o que ela mostra é o
        endereço que vai ficar registrado em cada ação daquela máquina."""
        usuario("gerente", ADMINISTRACAO)
        corpo = self.client.get(reverse("contas:entrar"),
                                REMOTE_ADDR="192.168.3.45").content.decode()
        self.client.login(username="gerente", password=SENHA_TESTE)
        self.client.post(reverse("alertas:testar"), REMOTE_ADDR="192.168.3.45")
        evento = EventoAuditoria.objects.filter(acao="alertas.teste").get()
        self.assertIn("192.168.3.45", corpo)
        self.assertEqual(evento.ip, "192.168.3.45")

    def test_a_versao_saiu_do_rodape(self):
        """Pedido antigo dele: a versão fica no menu de cima, não repetida embaixo."""
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)
        corpo = self.client.get(reverse("painel:painel")).content.decode()
        rodape = corpo[corpo.rfind("<footer"):]
        self.assertNotIn("Versão", rodape)
