"""O tempo de cada dia e o que ele faz com a venda (pedido do Edson, 14/10/2026)."""

from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.importacao.models import Importacao, VendaImportada
from apps.tempo import analise, fonte, servicos
from apps.tempo.models import ConfiguracaoDoTempo, TempoDoDia

CORTE = date(2026, 9, 20)

RESPOSTA = """{"daily": {"time": ["2026-09-18", "2026-09-19", "2026-09-20"],
  "weathercode": [0, 61, 95],
  "temperature_2m_max": [31.2, 24.0, 22.5],
  "temperature_2m_min": [21.0, 19.5, 18.0],
  "precipitation_sum": [0.0, 14.2, 38.6]}}"""


class LerOServicoDeMeteorologia(TestCase):
    def test_traduz_o_codigo_da_organizacao_meteorologica(self):
        self.assertEqual(fonte.condicao_do_codigo(0), "sol")
        self.assertEqual(fonte.condicao_do_codigo(61), "chuva")
        self.assertEqual(fonte.condicao_do_codigo(95), "tempestade")
        self.assertEqual(fonte.condicao_do_codigo(None), "")

    def test_codigo_desconhecido_nao_quebra_a_busca(self):
        self.assertEqual(fonte.condicao_do_codigo(7777), "nublado")

    def test_le_os_dias_da_resposta(self):
        dias = fonte.ler(RESPOSTA)
        self.assertEqual(len(dias), 3)
        self.assertEqual(dias[1]["data"], date(2026, 9, 19))
        self.assertEqual(dias[1]["condicao"], "chuva")
        self.assertEqual(dias[1]["chuva_mm"], Decimal("14.2"))

    def test_resposta_estragada_vira_erro_com_recado(self):
        with self.assertRaises(fonte.ErroDoTempo):
            fonte.ler("isto não é json")
        with self.assertRaises(fonte.ErroDoTempo):
            fonte.ler('{"daily": {}}')

    def test_o_endereco_pede_o_que_a_loja_precisa(self):
        endereco = fonte.montar_endereco(-22.9, -43.1, dias=5)
        self.assertIn("latitude=-22.9", endereco)
        self.assertIn("precipitation_sum", endereco)
        self.assertIn("past_days=5", endereco)
        self.assertTrue(endereco.startswith("https://"))


class GravarOTempo(TestCase):
    def test_a_busca_grava_os_dias_que_faltavam(self):
        configuracao = ConfiguracaoDoTempo.atual()
        configuracao.latitude, configuracao.longitude = Decimal("-22.9"), Decimal("-43.1")
        configuracao.save()
        novos, atualizados, respeitados = servicos.atualizar(
            configuracao, abrir=lambda endereco: RESPOSTA)
        self.assertEqual((novos, atualizados, respeitados), (3, 0, 0))
        self.assertEqual(TempoDoDia.objects.count(), 3)
        self.assertEqual(ConfiguracaoDoTempo.atual().ultimo_erro, "")

    def test_a_busca_nao_escreve_por_cima_do_que_alguem_da_loja_anotou(self):
        """Quem estava na loja viu o que a previsão de um quadrado de quilômetros não vê."""
        servicos.anotar(data=date(2026, 9, 19), condicao="sol",
                        observacao="choveu só de madrugada")
        configuracao = ConfiguracaoDoTempo.atual()
        configuracao.latitude, configuracao.longitude = Decimal("-22.9"), Decimal("-43.1")
        configuracao.save()
        _novos, _atualizados, respeitados = servicos.atualizar(
            configuracao, abrir=lambda endereco: RESPOSTA)
        self.assertEqual(respeitados, 1)
        registro = TempoDoDia.objects.get(data=date(2026, 9, 19))
        self.assertEqual(registro.condicao, "sol")
        self.assertEqual(registro.observacao, "choveu só de madrugada")

    def test_erro_na_busca_fica_guardado_para_aparecer_na_tela(self):
        configuracao = ConfiguracaoDoTempo.atual()
        configuracao.latitude, configuracao.longitude = Decimal("-22.9"), Decimal("-43.1")
        configuracao.save()

        def estourar(endereco):
            raise OSError("sem rede")

        with self.assertRaises(fonte.ErroDoTempo):
            servicos.atualizar(configuracao, abrir=estourar)
        self.assertIn("Não consegui", ConfiguracaoDoTempo.atual().ultimo_erro)

    def test_sem_coordenadas_a_busca_diz_o_que_falta(self):
        with self.assertRaises(fonte.ErroDoTempo):
            servicos.atualizar(ConfiguracaoDoTempo.atual())

    def test_numero_com_virgula_vale_e_texto_nao(self):
        registro = servicos.anotar(data=date(2026, 9, 19), condicao="chuva", chuva="14,2")
        self.assertEqual(registro.chuva_mm, Decimal("14.2"))
        with self.assertRaises(servicos.ErroDeRegistro):
            servicos.anotar(data=date(2026, 9, 18), chuva="muita")

    def test_condicao_fora_da_lista_nao_entra(self):
        with self.assertRaises(servicos.ErroDeRegistro):
            servicos.anotar(data=date(2026, 9, 18), condicao="furacao")


class QuandoContaComoChuva(TestCase):
    def test_a_condicao_escrita_manda(self):
        dia = TempoDoDia(data=date(2026, 9, 19), condicao="chuva")
        self.assertTrue(dia.choveu)
        self.assertFalse(TempoDoDia(data=date(2026, 9, 18), condicao="sol",
                                    chuva_mm=Decimal("3")).choveu)

    def test_sem_condicao_vale_o_volume_e_garoa_nao_conta(self):
        self.assertTrue(TempoDoDia(data=date(2026, 9, 17), chuva_mm=Decimal("5")).choveu)
        self.assertFalse(TempoDoDia(data=date(2026, 9, 16), chuva_mm=Decimal("0.4")).choveu)


class ACaContaDoClima(TestCase):
    def setUp(self):
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO,
            situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(), data_corte=CORTE,
            dias_abertos_12m=360, produtos=0,
        )

    def dia(self, quando, valor, condicao="", feriado=False):
        VendaImportada.objects.create(
            importacao=self.importacao, id_set=int(quando.strftime("%Y%m%d")),
            data=quando, dia_da_semana=(quando.weekday() + 1) % 7,
            valor=Decimal(valor),
        )
        if condicao or feriado:
            TempoDoDia.objects.create(data=quando, condicao=condicao, feriado=feriado)

    def test_separa_fim_de_semana_de_meio_de_semana(self):
        """Sábado de chuva contra terça de sol mediria o dia da semana, e não o tempo."""
        self.dia(date(2026, 9, 5), 10000, "sol")      # sábado
        self.dia(date(2026, 9, 12), 4000, "chuva")    # sábado
        self.dia(date(2026, 9, 8), 1000, "sol")       # terça
        self.dia(date(2026, 9, 15), 800, "chuva")     # terça
        dados = analise.montar(self.importacao)
        self.assertEqual(dados.fim_de_semana.media_sem_chuva, Decimal("10000.00"))
        self.assertEqual(dados.fim_de_semana.media_com_chuva, Decimal("4000.00"))
        self.assertEqual(dados.fim_de_semana.variacao, -60)
        self.assertEqual(dados.meio_de_semana.variacao, -20)

    def test_feriado_conta_como_fim_de_semana(self):
        """É quando a loja tem público, e foi assim que o Edson descreveu o negócio."""
        self.dia(date(2026, 9, 7), 9000, "sol", feriado=True)  # segunda, feriado
        dados = analise.montar(self.importacao)
        self.assertEqual(dados.fim_de_semana.dias_sem_chuva, 1)
        self.assertEqual(dados.meio_de_semana.dias, 0)

    def test_dia_sem_tempo_anotado_fica_fora_da_media_e_e_contado_a_parte(self):
        self.dia(date(2026, 9, 5), 10000, "sol")
        self.dia(date(2026, 9, 12), 7000)
        dados = analise.montar(self.importacao)
        self.assertEqual(dados.dias_com_tempo, 1)
        self.assertEqual(dados.dias_sem_tempo, 1)
        self.assertEqual(dados.fim_de_semana.dias, 1)

    def test_poucos_dias_nao_viram_conclusao(self):
        self.dia(date(2026, 9, 5), 10000, "sol")
        self.dia(date(2026, 9, 12), 4000, "chuva")
        self.assertFalse(analise.montar(self.importacao).da_para_concluir)

    def test_com_dias_bastante_a_conta_vale(self):
        for semana in range(analise.DIAS_PARA_CONCLUIR):
            self.dia(date(2026, 9, 5) - timedelta(days=7 * semana), 10000, "sol")
            self.dia(date(2026, 9, 6) - timedelta(days=7 * semana), 4000, "chuva")
        self.assertTrue(analise.montar(self.importacao).da_para_concluir)

    def test_a_lista_de_dias_sem_registro_ajuda_a_completar(self):
        self.dia(date(2026, 9, 19), 1000)
        self.dia(date(2026, 9, 18), 1000, "sol")
        faltando = analise.dias_sem_registro(self.importacao, ate=CORTE)
        self.assertEqual(faltando, [date(2026, 9, 19)])

    def test_sem_venda_nenhuma_nao_quebra(self):
        self.assertFalse(analise.montar(self.importacao).tem_dados)


class TelaDoTempo(TestCase):
    def setUp(self):
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)

    def test_a_tela_abre_e_pede_o_registro_do_dia(self):
        resposta = self.client.get(reverse("tempo:painel"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Anotar o tempo de um dia")

    def test_anotar_grava_e_volta_com_recado(self):
        resposta = self.client.post(reverse("tempo:anotar"), {
            "data": "2026-09-19", "condicao": "chuva_forte", "chuva": "38,6",
            "observacao": "fechou cedo", "feriado": "1",
        }, follow=True)
        registro = TempoDoDia.objects.get(data=date(2026, 9, 19))
        self.assertEqual(registro.condicao, "chuva_forte")
        self.assertTrue(registro.feriado)
        self.assertTrue(registro.escrito_a_mao)
        self.assertContains(resposta, "anotado")

    def test_data_sem_sentido_nao_grava(self):
        self.client.post(reverse("tempo:anotar"), {"data": "ontem"})
        self.assertFalse(TempoDoDia.objects.exists())

    def test_o_balcao_anota_mas_nao_configura_a_busca(self):
        self.client.logout()
        usuario("administrativa", ADMINISTRATIVO)
        self.client.login(username="administrativa", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("tempo:painel")).status_code, 200)
        resposta = self.client.post(reverse("tempo:configurar"), {"cidade": "Rio"})
        self.assertEqual(resposta.status_code, 403)

    def test_o_vendedor_nao_entra(self):
        self.client.logout()
        usuario("vendedora", VENDEDOR)
        self.client.login(username="vendedora", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("tempo:painel")).status_code, 403)

    def test_ligar_a_busca_sem_dizer_onde_e_a_loja_e_recusado_com_explicacao(self):
        """Ligada e sem lugar nenhum, a busca só adiaria o erro para a madrugada.

        A cidade já nasce preenchida desde a 1.35.0, então apagá-la é o preparo deste
        caso: o que se testa aqui é o formulário enviado em branco.
        """
        configuracao = ConfiguracaoDoTempo.atual()
        configuracao.cidade = ""
        configuracao.latitude = configuracao.longitude = None
        configuracao.save()
        resposta = self.client.post(reverse("tempo:configurar"), {"ativo": "1"})
        self.assertContains(resposta, "Escreva a cidade")
        self.assertFalse(ConfiguracaoDoTempo.atual().da_para_buscar)

    def test_a_cidade_basta_para_ligar_a_busca_e_o_sistema_descobre_o_lugar(self):
        """Era isto que mantinha a busca desligada: ela exigia as coordenadas à mão.

        Até a 1.28.0 o formulário recusava "cidade sem coordenadas" e mandava a pessoa ao
        Google Maps copiar dois números de seis casas decimais. Ninguém foi, e a busca
        nunca rodou. Agora salvar a cidade faz o caminho inteiro numa vez.
        """
        with mock.patch.object(servicos, "atualizar", return_value=(3, 0, 0)) as busca:
            resposta = self.client.post(
                reverse("tempo:configurar"),
                {"ativo": "1", "cidade": "Rio de Janeiro"}, follow=True)
        self.assertTrue(busca.called)
        configuracao = ConfiguracaoDoTempo.atual()
        self.assertTrue(configuracao.ativo)
        self.assertEqual(configuracao.cidade, "Rio de Janeiro")
        self.assertContains(resposta, "Configuração gravada")

    def test_trocar_a_cidade_esquece_as_coordenadas_da_cidade_anterior(self):
        """Senão o sistema seguiria buscando o tempo do lugar antigo, calado."""
        configuracao = ConfiguracaoDoTempo.atual()
        configuracao.cidade = "Rio de Janeiro"
        configuracao.latitude, configuracao.longitude = Decimal("-22.9"), Decimal("-43.1")
        configuracao.lugar_encontrado = "Rio de Janeiro, Rio de Janeiro, Brasil"
        configuracao.save()
        with mock.patch.object(servicos, "atualizar", return_value=(0, 0, 0)):
            # As coordenadas vão como estavam na tela: quem só trocou a cidade não
            # mexeu nelas, e é esse o caso que o código tem que pegar.
            self.client.post(reverse("tempo:configurar"),
                             {"ativo": "1", "cidade": "Sorocaba",
                              "latitude": "-22.9", "longitude": "-43.1"})
        depois = ConfiguracaoDoTempo.atual()
        self.assertEqual(depois.cidade, "Sorocaba")
        self.assertIsNone(depois.latitude)
        self.assertIsNone(depois.longitude)
        self.assertEqual(depois.lugar_encontrado, "")

    def test_quem_digitou_coordenadas_novas_fica_com_as_dele(self):
        """A loja pode ficar longe do centro da cidade; corrigir à mão tem que valer."""
        configuracao = ConfiguracaoDoTempo.atual()
        configuracao.cidade = "Rio de Janeiro"
        configuracao.latitude, configuracao.longitude = Decimal("-22.9"), Decimal("-43.1")
        configuracao.save()
        with mock.patch.object(servicos, "atualizar", return_value=(0, 0, 0)):
            self.client.post(reverse("tempo:configurar"),
                             {"ativo": "1", "cidade": "Sorocaba",
                              "latitude": "-23.501670", "longitude": "-47.458060"})
        depois = ConfiguracaoDoTempo.atual()
        self.assertEqual(depois.latitude, Decimal("-23.501670"))
        self.assertEqual(depois.longitude, Decimal("-47.458060"))

    def test_a_tela_mostra_o_lugar_que_o_sistema_entendeu(self):
        """Nome de cidade se repete no Brasil: a pessoa tem que poder ver qual entrou."""
        configuracao = ConfiguracaoDoTempo.atual()
        configuracao.cidade = "Sorocaba"
        configuracao.lugar_encontrado = "Sorocaba, São Paulo, Brasil"
        configuracao.latitude, configuracao.longitude = Decimal("-23.5"), Decimal("-47.4")
        configuracao.save()
        resposta = self.client.get(reverse("tempo:painel"))
        self.assertContains(resposta, "Sorocaba, São Paulo, Brasil")

    def test_a_tela_saiu_do_menu_e_tem_o_caminho_de_volta(self):
        resposta = self.client.get(reverse("tempo:painel"))
        self.assertContains(resposta, reverse("painel:geral") + "#tempo")

    def test_o_arquivo_sai_em_csv(self):
        resposta = self.client.get(reverse("tempo:em_arquivo"))
        self.assertIn("text/csv", resposta["Content-Type"])
        self.assertTrue(resposta.content.decode("utf-8").startswith("﻿"))
