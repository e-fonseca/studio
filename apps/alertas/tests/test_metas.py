"""O aviso de meta batida no grupo das metas, pelo Telegram (1.47.0).

Pedido do Edson em 04/11/2026: "enviar notificação de telegram meta batida feriado 12mil,
sábado 12 mil reais e domingo 15 mil reais", no grupo METAS. Nada aqui fala com a
internet: tudo passa por `telegram._pedir`, que o Espiao substitui.

O que estes testes protegem:

1. **O aviso sai uma vez por dia de meta**, e de novo só quando o prêmio sobe de degrau.
   Repetir o mesmo número a cada importação faria o grupo deixar de ler.
2. **Vai para o grupo das metas, não para a conversa dos relatórios**, e os relatórios
   desligados não calam a meta batida.
3. **Ninguém é nomeado.** O aviso vai para um grupo; o nome de quem passou a venda fora
   da regra é assunto da tela Descontos e metas. Os nomes do caixa são de mentira.
4. **Falha insiste pouco** e nunca derruba a tarefa, nem um emoji no nome do grupo.
"""

import io
from datetime import date
from decimal import Decimal
from importlib import import_module
from io import StringIO
from unittest import mock

from django.apps import apps as registro_de_apps
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.alertas import metas, telegram
from apps.alertas.models import Canal, ConfiguracaoDeEmail, ConfiguracaoDeTelegram, EnvioDeRelatorio, Rotina
from apps.alertas.tests.test_telegram import TOKEN, Espiao, mandando_para_o_espiao
from apps.auditoria.models import EventoAuditoria
from apps.caixa.descontos import DiaDeMeta
from apps.caixa.models import DescontoAprovado, RegraDeDesconto
from apps.contas.perfis import ADMINISTRACAO
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.importacao.models import Importacao, VendaImportada

# 19/09/2026 é sábado e 20/09/2026, domingo: o fim de semana da cópia do SET.
SABADO = date(2026, 9, 19)
DOMINGO = date(2026, 9, 20)
SEGUNDA = date(2026, 9, 21)
GRUPO = "-1001234567890"


def grupo_pronto(**extra):
    """O robô gravado e o grupo das metas escolhido, com o aviso ligado."""
    configuracao = ConfiguracaoDeTelegram.atual()
    configuracao.token = TOKEN
    configuracao.chat_id = "987654321"
    configuracao.metas_chat_id = GRUPO
    configuracao.metas_chat_nome = "METAS"
    configuracao.metas_ativo = True
    for campo, valor in extra.items():
        setattr(configuracao, campo, valor)
    configuracao.save()
    return configuracao


class ComVendas(TestCase):
    def setUp(self):
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO, situacao=Importacao.Situacao.CONCLUIDA,
            iniciada_em=timezone.now(), concluida_em=timezone.now(), data_corte=DOMINGO,
            dias_abertos_12m=300, produtos=1,
        )
        self.numero = 100

    def venda(self, data, valor, desconto="0", forma="PIX", hora="15:00:00"):
        self.numero += 1
        valor, desconto = Decimal(valor), Decimal(desconto)
        return VendaImportada.objects.create(
            importacao=self.importacao, id_set=self.numero, numero=f"{self.numero}.12", data=data,
            hora=hora, dia_da_semana=(data.weekday() + 1) % 7, valor=valor, desconto=desconto,
            forma_pagamento=forma, total_produtos=valor + desconto, recebido_por="CAIXA TESTE",
            formas_pagas={forma: str(valor)},
        )

    def avisar(self, espiao, hoje=SEGUNDA):
        with mandando_para_o_espiao(espiao):
            return metas.avisar(importacao=self.importacao, hoje=hoje)


class QuaisDiasTest(ComVendas):
    def test_so_os_dias_de_meta_dos_ultimos_dias_e_ate_o_corte(self):
        self.assertEqual(metas.dias_de_meta(self.importacao, date(2026, 9, 22)), [SABADO, DOMINGO])
        # Três dias para trás a partir da quinta: o sábado já ficou de fora.
        self.assertEqual(metas.dias_de_meta(self.importacao, date(2026, 9, 23)), [DOMINGO])
        self.assertEqual(metas.dias_de_meta(self.importacao, date(2026, 9, 30)), [])

    def test_o_feriado_entra_com_o_fim_de_semana_emendado(self):
        """07/09/2026 é segunda e é feriado nacional: três dias de meta seguidos."""
        self.importacao.data_corte = date(2026, 9, 7)
        self.assertEqual(metas.dias_de_meta(self.importacao, date(2026, 9, 8)),
                         [date(2026, 9, 5), date(2026, 9, 6), date(2026, 9, 7)])

    def test_sem_importacao_nao_ha_dia(self):
        self.assertEqual(metas.dias_de_meta(None, SEGUNDA), [])


class AvisoTest(ComVendas):
    def setUp(self):
        super().setUp()
        grupo_pronto()

    def test_meta_batida_vai_para_o_grupo_das_metas_uma_vez(self):
        self.venda(SABADO, "12000")
        self.venda(SABADO, "500", hora="17:56:12")
        espiao = Espiao()
        registros = self.avisar(espiao)
        self.assertEqual(len(registros), 1)
        self.assertTrue(registros[0].deu_certo)
        self.assertEqual(espiao.chamadas[0]["dados"]["chat_id"], GRUPO)
        texto = espiao.texto
        self.assertEqual(texto.splitlines()[0], "\N{PARTY POPPER} Meta batida! Sábado, 19/09/2026")
        self.assertIn("Vendido: R$ 12.500,00 (vendas até 17:56)", texto)
        self.assertIn("Meta do dia: R$ 12.000,00", texto)
        self.assertIn("Prêmio: R$ 30,00 para cada pessoa que trabalhou no dia.", texto)
        self.assertIn("O próximo degrau é R$ 13.000,00 vendidos: R$ 40,00 por pessoa.", texto)
        self.assertNotIn("Atenção", texto)
        registro = EnvioDeRelatorio.objects.get()
        self.assertEqual((registro.rotina, registro.canal), (Rotina.METAS, Canal.TELEGRAM))
        self.assertEqual(registro.dia_da_meta, SABADO)
        self.assertEqual(registro.premio_avisado, Decimal("30"))
        self.assertEqual(registro.destinatarios, f"METAS ({GRUPO})")
        # A volta seguinte da tarefa não repete o aviso.
        self.assertEqual(self.avisar(espiao), [])
        self.assertEqual(len(espiao.chamadas), 1)

    def test_o_domingo_tem_a_meta_de_15_mil(self):
        self.venda(DOMINGO, "14999.99")
        self.assertEqual(self.avisar(Espiao()), [])
        self.venda(DOMINGO, "0.01")
        espiao = Espiao()
        self.assertEqual(len(self.avisar(espiao)), 1)
        self.assertIn("Meta batida! Domingo, 20/09/2026", espiao.texto)
        self.assertIn("Meta do dia: R$ 15.000,00", espiao.texto)

    def test_avisa_de_novo_so_quando_o_premio_sobe(self):
        """Com o backup feito de dia, a importação da noite traz o resto do sábado."""
        self.venda(SABADO, "12500")
        espiao = Espiao()
        self.avisar(espiao)
        self.venda(SABADO, "400")
        self.assertEqual(self.avisar(espiao), [])  # R$ 12.900: o mesmo prêmio
        self.venda(SABADO, "600")
        self.assertEqual(len(self.avisar(espiao)), 1)  # R$ 13.500: subiu um degrau
        self.assertIn("O prêmio subiu! Sábado, 19/09/2026", espiao.texto)
        self.assertIn("Prêmio: R$ 40,00", espiao.texto)
        self.assertEqual(len(espiao.chamadas), 2)

    def test_meta_que_nao_bateu_nao_vai_para_o_grupo(self):
        self.venda(SABADO, "11999")
        espiao = Espiao()
        self.assertEqual(self.avisar(espiao), [])
        self.assertEqual(espiao.chamadas, [])

    def test_meta_antiga_nao_vai_para_o_grupo(self):
        """Ligar o aviso não pode despejar no grupo os fins de semana que a foto guarda."""
        self.venda(SABADO, "20000")
        espiao = Espiao()
        self.assertEqual(self.avisar(espiao, hoje=date(2026, 9, 30)), [])
        self.assertEqual(espiao.chamadas, [])

    def test_venda_fora_da_regra_que_fez_a_meta_aparece_sem_nome(self):
        self.venda(SABADO, "11900")
        self.venda(SABADO, "600", "100", forma="CARTAO CREDITO")  # desconto no crédito
        espiao = Espiao()
        self.avisar(espiao)
        self.assertIn("Atenção: 1 venda(s) deste dia com desconto fora da regra ainda não têm "
                      "aprovação anotada (R$ 600,00). Sem elas, o dia ficaria em R$ 11.900,00 e a "
                      "meta não teria sido batida.", espiao.texto)
        self.assertNotIn("CAIXA TESTE", espiao.texto.upper())

    def test_venda_aprovada_tira_o_aviso_de_atencao(self):
        self.venda(SABADO, "11900")
        fora = self.venda(SABADO, "600", "100", forma="CARTAO CREDITO")
        DescontoAprovado.objects.create(id_venda=fora.id_set, numero=fora.numero, dia=SABADO,
                                        autorizado_por="Edson")
        espiao = Espiao()
        self.avisar(espiao)
        self.assertNotIn("Atenção", espiao.texto)

    def test_falha_insiste_tres_vezes_no_dia_e_explica(self):
        self.venda(SABADO, "13000")
        espiao = Espiao(erro="Bad Request: chat not found")
        for _ in range(4):
            self.avisar(espiao)
        self.assertEqual(len(espiao.chamadas), 3)
        registros = EnvioDeRelatorio.objects.filter(rotina=Rotina.METAS)
        self.assertEqual(registros.count(), 3)
        self.assertFalse(registros.filter(deu_certo=True).exists())
        self.assertIn("não encontrou essa conversa", registros.first().erro)

    def test_desligado_ou_sem_grupo_nao_manda(self):
        self.venda(SABADO, "13000")
        espiao = Espiao()
        grupo_pronto(metas_ativo=False)
        self.assertEqual(self.avisar(espiao), [])
        grupo_pronto(metas_chat_id="")
        self.assertEqual(self.avisar(espiao), [])
        self.assertEqual(espiao.chamadas, [])


class ProximoDegrauTest(TestCase):
    def dia(self, vendido, **extra):
        valores = {"dia": SABADO, "tipo": "sabado", "feriado": "", "meta": Decimal("12000"),
                   "vendido": Decimal(vendido), "premio_base": Decimal("30"),
                   "premio_a_mais": Decimal("10")}
        valores.update(extra)
        return DiaDeMeta(**valores)

    def test_o_degrau_seguinte_e_o_premio_de_la(self):
        self.assertEqual(self.dia("11000").proximo_degrau, (Decimal("12000"), Decimal("30")))
        self.assertEqual(self.dia("12000").proximo_degrau, (Decimal("13000"), Decimal("40")))
        self.assertEqual(self.dia("13999.99").proximo_degrau, (Decimal("14000"), Decimal("50")))

    def test_sem_premio_a_mais_nao_ha_degrau(self):
        self.assertIsNone(self.dia("12500", premio_a_mais=Decimal("0")).proximo_degrau)


class TarefaTest(ComVendas):
    """A tarefa de hora em hora manda o aviso, mesmo com os relatórios desligados."""

    def setUp(self):
        super().setUp()
        self.venda(SABADO, "12500")
        # Os dois canais dos relatórios desligados: a meta batida tem o seu interruptor.
        ConfiguracaoDeEmail.objects.update_or_create(pk=1, defaults={"ativo": False})

    def rodar(self, espiao, saida=None, **opcoes):
        saida = saida or StringIO()
        with mandando_para_o_espiao(espiao), \
                mock.patch.object(metas.timezone, "localdate", return_value=SEGUNDA):
            call_command("enviar_relatorios", stdout=saida, **opcoes)
        return saida

    def test_relatorios_desligados_nao_calam_a_meta(self):
        grupo_pronto(ativo=False)
        espiao = Espiao()
        saida = self.rodar(espiao).getvalue()
        self.assertEqual(len(espiao.chamadas), 1)
        self.assertEqual(espiao.chamadas[0]["dados"]["chat_id"], GRUPO)
        self.assertIn("Telegram · Grupo das metas: enviado para METAS", saida)
        self.assertIn("Nada foi enviado", saida)

    def test_rotina_metas_faz_so_o_aviso(self):
        grupo_pronto()
        espiao = Espiao()
        self.rodar(espiao, rotina="metas")
        self.assertEqual(len(espiao.chamadas), 1)
        self.assertEqual(list(EnvioDeRelatorio.objects.values_list("rotina", flat=True)), [Rotina.METAS])

    def test_rodar_um_relatorio_a_mao_nao_avisa_o_grupo(self):
        """Quem confere um e-mail no servidor não quer mensagem caindo no grupo."""
        grupo_pronto(ativo=False)
        espiao = Espiao()
        self.rodar(espiao, rotina="contas", forcar=True)
        self.assertEqual(espiao.chamadas, [])

    def test_emoji_no_nome_do_grupo_nao_derruba_a_tarefa(self):
        """O cano da tarefa do Windows não é UTF-8; o aviso já saiu quando o log escreve."""
        grupo_pronto(ativo=False, metas_chat_nome="METAS \N{DIRECT HIT}")
        cano = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        self.rodar(Espiao(), saida=cano)
        cano.flush()
        escrito = cano.buffer.getvalue().decode("cp1252")
        self.assertIn("enviado para METAS ?", escrito)

    def test_erro_no_aviso_nao_derruba_os_relatorios(self):
        grupo_pronto(ativo=False)
        with mock.patch.object(metas, "avisar", side_effect=RuntimeError("quebrou")), \
                self.assertLogs("apps.alertas.management.commands.enviar_relatorios", "ERROR"):
            saida = self.rodar(Espiao()).getvalue()
        self.assertIn("Nada foi enviado", saida)


class TelaTest(TestCase):
    def setUp(self):
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)

    def test_a_tela_mostra_as_metas_da_regra_e_como_por_o_robo_no_grupo(self):
        resposta = self.client.get(reverse("alertas:painel"))
        self.assertContains(resposta, "Grupo das metas")
        self.assertContains(resposta, "R$ 12.000,00")
        self.assertContains(resposta, "R$ 15.000,00")
        self.assertContains(resposta, "Adicionar membro")
        self.assertContains(resposta, "O link de convite do grupo não serve")

    def test_descobrir_pelo_grupo_das_metas_mostra_o_botao_das_metas(self):
        configuracao = ConfiguracaoDeTelegram.atual()
        configuracao.token = TOKEN
        configuracao.save()
        espiao = Espiao(resultado=[{"update_id": 1, "my_chat_member": {
            "chat": {"id": int(GRUPO), "title": "METAS", "type": "supergroup"}}}])
        with mandando_para_o_espiao(espiao):
            resposta = self.client.post(reverse("alertas:descobrir_chat"), {"para": "metas"})
        self.assertContains(resposta, "Usar para as metas")
        self.assertContains(resposta, GRUPO)
        self.assertNotContains(resposta, "Usar esta")

    def test_usar_para_as_metas_nao_mexe_na_conversa_dos_relatorios(self):
        grupo_pronto(metas_chat_id="", metas_chat_nome="", metas_ativo=False)
        self.client.post(reverse("alertas:usar_chat"),
                         {"para": "metas", "chat_id": GRUPO, "chat_nome": "METAS"})
        configuracao = ConfiguracaoDeTelegram.atual()
        self.assertEqual(configuracao.metas_chat_id, GRUPO)
        self.assertEqual(configuracao.metas_chat_nome, "METAS")
        self.assertEqual(configuracao.chat_id, "987654321")
        self.assertTrue(EventoAuditoria.objects.filter(acao="alertas.telegram_configurado").exists())

    def test_ligar_sem_robo_e_recusado(self):
        resposta = self.client.post(reverse("alertas:configurar_metas"),
                                    {"metas_ativo": "on", "metas_chat_id": GRUPO})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Para ligar o aviso das metas falta preencher: o token do robô")
        self.assertFalse(ConfiguracaoDeTelegram.atual().metas_ativo)

    def test_liga_e_grava_o_numero_digitado(self):
        grupo_pronto(metas_ativo=False)
        resposta = self.client.post(reverse("alertas:configurar_metas"),
                                    {"metas_ativo": "on", "metas_chat_id": "-100999"})
        self.assertEqual(resposta.status_code, 302)
        configuracao = ConfiguracaoDeTelegram.atual()
        self.assertTrue(configuracao.metas_ativo)
        self.assertEqual(configuracao.metas_chat_id, "-100999")
        self.assertEqual(configuracao.metas_chat_nome, "")  # outro grupo: o nome antigo não vale

    def test_numero_de_grupo_com_letra_e_recusado(self):
        grupo_pronto(metas_ativo=False)
        resposta = self.client.post(reverse("alertas:configurar_metas"), {"metas_chat_id": "METAS"})
        self.assertContains(resposta, "O grupo é um número que começa com -")

    def test_o_teste_vai_ao_grupo_e_explica_a_regra(self):
        grupo_pronto()
        espiao = Espiao()
        with mandando_para_o_espiao(espiao):
            resposta = self.client.post(reverse("alertas:testar_metas"))
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(espiao.chamadas[0]["dados"]["chat_id"], GRUPO)
        self.assertIn("Domingo: R$ 15.000,00", espiao.texto)
        self.assertIn("Sábado e feriado: R$ 12.000,00", espiao.texto)
        registro = EnvioDeRelatorio.objects.get()
        self.assertEqual(registro.rotina, Rotina.TESTE)
        self.assertTrue(registro.deu_certo)

    def test_ligado_mostra_os_ultimos_avisos(self):
        grupo_pronto()
        EnvioDeRelatorio.objects.create(
            rotina=Rotina.METAS, canal=Canal.TELEGRAM, deu_certo=True, dia_da_meta=SABADO,
            premio_avisado=Decimal("30"),
            resumo="Sábado 19/09: vendeu R$ 12.500,00 de R$ 12.000,00, prêmio de R$ 30,00 por pessoa")
        resposta = self.client.get(reverse("alertas:painel"))
        self.assertContains(resposta, "Aviso das metas ligado")
        self.assertContains(resposta, "Sábado 19/09: vendeu R$ 12.500,00")


class TraducaoTest(TestCase):
    def test_grupo_que_virou_supergrupo_pede_para_escolher_de_novo(self):
        frase = telegram.explicar("Bad Request: group chat was upgraded to a supergroup chat")
        self.assertIn("Descobrir a conversa", frase)


class MigracaoDaMetaDoDomingoTest(TestCase):
    """caixa 0003: os R$ 18 mil da 1.46.0 viram R$ 15 mil; outro valor é da gerência."""

    def _migracao(self):
        return import_module("apps.caixa.migrations.0003_meta_do_domingo_15_mil")

    def test_a_meta_de_18_mil_vira_15_mil_com_auditoria(self):
        RegraDeDesconto.objects.create(pk=1, meta_domingo=Decimal("18000"))
        self._migracao().baixar_a_meta_do_domingo(registro_de_apps, None)
        self.assertEqual(RegraDeDesconto.atual().meta_domingo, Decimal("15000"))
        evento = EventoAuditoria.objects.get(acao="caixa.regras_de_desconto_mudadas")
        self.assertEqual(evento.usuario_rotulo, "atualização 1.47.0")
        self.assertEqual(evento.antes, {"meta_domingo": "18000.00"})
        self.assertEqual(evento.depois, {"meta_domingo": "15000.00"})

    def test_meta_que_a_gerencia_mudou_fica_como_esta(self):
        RegraDeDesconto.objects.create(pk=1, meta_domingo=Decimal("16000"))
        self._migracao().baixar_a_meta_do_domingo(registro_de_apps, None)
        self.assertEqual(RegraDeDesconto.atual().meta_domingo, Decimal("16000"))
        self.assertFalse(EventoAuditoria.objects.filter(acao="caixa.regras_de_desconto_mudadas").exists())

    def test_regra_nova_ja_nasce_com_15_mil(self):
        self.assertEqual(RegraDeDesconto.atual().meta_domingo, Decimal("15000"))
