"""A busca do tempo se configurando sozinha, e a previsão dos próximos dias.

Pedido do Edson em 14/10/2026: "configurar api de previsão do tempo automática,
armazenar informações diárias e usar como indicador".

Nenhum teste daqui fala com a internet: todos passam a função `abrir` de mentira. As
respostas abaixo são a forma do que os dois serviços do Open-Meteo devolvem de verdade.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils.html import strip_tags
from django.utils import timezone

from apps.contas.perfis import ADMINISTRACAO
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.importacao.models import Importacao, VendaImportada
from apps.tempo import analise, fonte, indicador, lugar, servicos
from apps.tempo.models import ConfiguracaoDoTempo, TempoDoDia

# Duas cidades com o mesmo nome, de propósito: a de São Paulo, grande, e um distrito
# homônimo de Santa Catarina. Mais uma de outro país, que não pode entrar.
CIDADES = """{"results": [
  {"id": 1, "name": "Sorocaba", "latitude": -27.22057, "longitude": -48.80002,
   "country": "Brasil", "country_code": "BR", "admin1": "Santa Catarina"},
  {"id": 2, "name": "Sorocaba", "latitude": -23.50167, "longitude": -47.45806,
   "country": "Brasil", "country_code": "BR", "admin1": "São Paulo", "population": 687357},
  {"id": 3, "name": "Sorocaba", "latitude": 40.0, "longitude": -3.0,
   "country": "Espanha", "country_code": "ES", "admin1": "Madri", "population": 9000000}
]}"""

SEM_CIDADE = '{"generationtime_ms": 0.5}'


def resposta_com_previsao(hoje):
    """Três dias fechados, hoje e três à frente, como o serviço devolve de verdade."""
    dias = [hoje - timedelta(days=3), hoje - timedelta(days=2), hoje - timedelta(days=1),
            hoje, hoje + timedelta(days=1), hoje + timedelta(days=2)]
    datas = ", ".join(f'"{dia:%Y-%m-%d}"' for dia in dias)
    return ('{"daily": {"time": [' + datas + '],'
            ' "weathercode": [0, 0, 61, 1, 61, 95],'
            ' "temperature_2m_max": [30.0, 29.0, 24.0, 28.0, 23.0, 22.0],'
            ' "temperature_2m_min": [20.0, 19.0, 18.0, 19.0, 18.0, 17.0],'
            ' "precipitation_sum": [0.0, 0.0, 12.0, 0.0, 18.0, 40.0]}}')


class DescobrirACidade(TestCase):
    def test_escolhe_a_cidade_brasileira_de_maior_populacao(self):
        """"Sorocaba" é a de São Paulo, não o distrito homônimo de Canelinha."""
        achados = lugar.ler(CIDADES)
        self.assertEqual(len(achados), 2)
        self.assertEqual(achados[0].estado, "São Paulo")
        self.assertEqual(achados[0].latitude, Decimal("-23.501670"))

    def test_cidade_de_outro_pais_fica_fora(self):
        """Senão a chuva da Espanha entraria na conta do movimento da loja."""
        self.assertNotIn("Espanha", [achado.pais for achado in lugar.ler(CIDADES)])

    def test_o_que_o_servico_entendeu_sai_escrito_para_alguem_conferir(self):
        self.assertEqual(lugar.ler(CIDADES)[0].escrito, "Sorocaba, São Paulo, Brasil")

    def test_nome_que_nao_existe_vira_erro_com_frase_pronta(self):
        with self.assertRaises(fonte.ErroDoTempo) as erro:
            lugar.primeiro("Xpto", abrir=lambda endereco: SEM_CIDADE)
        self.assertIn("não achou nenhuma cidade", str(erro.exception))

    def test_nome_em_branco_nao_sai_perguntando_nada(self):
        with self.assertRaises(fonte.ErroDoTempo):
            lugar.primeiro("   ", abrir=lambda endereco: CIDADES)

    def test_o_endereco_leva_o_acento_codificado(self):
        endereco = lugar.montar_endereco("São Paulo")
        self.assertIn("name=S%C3%A3o%20Paulo", endereco)
        self.assertTrue(endereco.startswith("https://"))

    def test_resposta_estragada_vira_erro_com_recado(self):
        with self.assertRaises(fonte.ErroDoTempo):
            lugar.ler("isto não é json")


class OSistemaSeConfiguraSozinho(TestCase):
    def test_a_cidade_vira_coordenadas_e_o_lugar_fica_guardado(self):
        configuracao = ConfiguracaoDoTempo.atual()
        configuracao.cidade = "Sorocaba"
        configuracao.save()
        servicos.descobrir_o_lugar(configuracao, abrir=lambda endereco: CIDADES)
        salva = ConfiguracaoDoTempo.atual()
        self.assertEqual(salva.latitude, Decimal("-23.501670"))
        self.assertEqual(salva.longitude, Decimal("-47.458060"))
        self.assertEqual(salva.lugar_encontrado, "Sorocaba, São Paulo, Brasil")

    def test_a_busca_de_todo_dia_descobre_o_lugar_na_mesma_rodada(self):
        """Quem escreveu a cidade às 08:00 não espera as 06:10 do dia seguinte."""
        configuracao = ConfiguracaoDoTempo.atual()
        configuracao.cidade = "Sorocaba"
        configuracao.save()
        novos, _atualizados, _respeitados = servicos.atualizar(
            configuracao,
            abrir=lambda endereco: resposta_com_previsao(date.today()),
            abrir_lugar=lambda endereco: CIDADES,
        )
        self.assertEqual(novos, 6)
        self.assertTrue(ConfiguracaoDoTempo.atual().tem_lugar)

    def _apagar_a_cidade(self):
        """Desde a 1.35.0 a cidade já nasce preenchida (Embu das Artes, que ele informou).

        Estes dois casos são sobre o que acontece QUANDO ela está em branco, então
        apagá-la é parte do preparo do teste, e não um detalhe de arrumação.
        """
        configuracao = ConfiguracaoDoTempo.atual()
        configuracao.cidade = ""
        configuracao.latitude = configuracao.longitude = None
        configuracao.save()
        return configuracao

    def test_sem_cidade_e_sem_coordenadas_e_pendencia_e_nao_falha(self):
        """A tarefa do Windows não pode ficar vermelha por causa de campo em branco."""
        with self.assertRaises(fonte.FaltaOLugar) as erro:
            servicos.atualizar(self._apagar_a_cidade())
        self.assertIn("cidade da loja", str(erro.exception))

    def test_o_comando_do_windows_termina_bem_quando_so_falta_a_cidade(self):
        from io import StringIO

        from django.core.management import call_command

        self._apagar_a_cidade()
        saida = StringIO()
        call_command("buscar_tempo", stdout=saida)
        self.assertIn("cidade da loja", saida.getvalue())

    def test_cidade_que_nao_existe_fica_guardada_como_erro_para_a_tela(self):
        configuracao = ConfiguracaoDoTempo.atual()
        configuracao.cidade = "Xpto"
        configuracao.save()
        with self.assertRaises(fonte.ErroDoTempo):
            servicos.atualizar(configuracao, abrir_lugar=lambda endereco: SEM_CIDADE)
        self.assertIn("não achou nenhuma cidade", ConfiguracaoDoTempo.atual().ultimo_erro)

    def test_a_busca_automatica_nasce_ligada(self):
        """Antes nascia desligada e ninguém ligava, porque ligar exigia o Google Maps."""
        self.assertTrue(ConfiguracaoDoTempo.atual().ativo)


class APrevisaoDosProximosDias(TestCase):
    def test_o_endereco_pede_os_dias_fechados_e_a_previsao(self):
        endereco = fonte.montar_endereco(-23.5, -47.4, dias=5, dias_de_previsao=7)
        self.assertIn("past_days=5", endereco)
        self.assertIn("forecast_days=7", endereco)

    def test_hoje_e_os_dias_a_frente_saem_marcados_como_previsao(self):
        """Às 06:10 da manhã o dia de hoje não fechou: a chuva da tarde é palpite."""
        hoje = date(2026, 10, 14)
        dias = fonte.ler(resposta_com_previsao(hoje), hoje=hoje)
        marcados = {dia["data"]: dia["previsao"] for dia in dias}
        self.assertFalse(marcados[hoje - timedelta(days=1)])
        self.assertTrue(marcados[hoje])
        self.assertTrue(marcados[hoje + timedelta(days=2)])

    def test_a_previsao_de_ontem_e_substituida_pelo_dia_fechado(self):
        """A busca do dia seguinte traz o mesmo dia já medido, e a marca cai sozinha."""
        ontem = date.today() - timedelta(days=1)
        servicos.guardar_dias([{"data": ontem, "condicao": "chuva", "chuva_mm": Decimal("8"),
                                "temperatura_minima": None, "temperatura_maxima": None,
                                "previsao": True}])
        self.assertTrue(TempoDoDia.objects.get(data=ontem).previsao)
        servicos.guardar_dias([{"data": ontem, "condicao": "sol", "chuva_mm": Decimal("0"),
                                "temperatura_minima": None, "temperatura_maxima": None,
                                "previsao": False}])
        registro = TempoDoDia.objects.get(data=ontem)
        self.assertFalse(registro.previsao)
        self.assertEqual(registro.condicao, "sol")

    def test_quem_anota_na_tela_apaga_a_marca_de_previsao(self):
        """Quem estava na loja viu o dia; não é mais palpite."""
        hoje = date.today()
        TempoDoDia.objects.create(data=hoje, condicao="sol", previsao=True)
        registro = servicos.anotar(data=hoje, condicao="chuva_forte", chuva="40")
        self.assertFalse(registro.previsao)
        self.assertTrue(registro.escrito_a_mao)


class APrevisaoNaoEntraNaConta(TestCase):
    """Média de palpite não mede nada: a conta do custo da chuva é só de dia fechado."""

    def setUp(self):
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO,
            situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(), data_corte=date(2026, 9, 20),
            dias_abertos_12m=360, produtos=0,
        )

    def dia(self, quando, valor, condicao="", previsao=False):
        VendaImportada.objects.create(
            importacao=self.importacao, id_set=int(quando.strftime("%Y%m%d")),
            data=quando, dia_da_semana=(quando.weekday() + 1) % 7, valor=Decimal(valor),
        )
        if condicao:
            TempoDoDia.objects.create(data=quando, condicao=condicao, previsao=previsao)

    def test_dia_previsto_fica_fora_da_media(self):
        self.dia(date(2026, 9, 5), 10000, "sol")                    # sábado medido
        self.dia(date(2026, 9, 12), 4000, "chuva")                  # sábado medido
        self.dia(date(2026, 9, 19), 1, "chuva", previsao=True)      # sábado previsto
        dados = analise.montar(self.importacao)
        self.assertEqual(dados.fim_de_semana.dias_com_chuva, 1)
        self.assertEqual(dados.fim_de_semana.media_com_chuva, Decimal("4000.00"))

    def test_dia_previsto_continua_na_lista_do_que_falta_anotar(self):
        """A previsão da véspera não dispensa alguém de dizer como o dia foi."""
        self.dia(date(2026, 9, 19), 500, "chuva", previsao=True)
        self.assertIn(date(2026, 9, 19), analise.dias_sem_registro(self.importacao))


class OIndicadorDaVisaoGeral(TestCase):
    def setUp(self):
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO,
            situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(), data_corte=date(2026, 9, 20),
            dias_abertos_12m=360, produtos=0,
        )
        self.configurar()

    def configurar(self):
        """Previsão guardada só existe depois de o lugar da loja estar sabido."""
        configuracao = ConfiguracaoDoTempo.atual()
        configuracao.cidade = "Sorocaba"
        configuracao.lugar_encontrado = "Sorocaba, São Paulo, Brasil"
        configuracao.latitude, configuracao.longitude = Decimal("-23.5"), Decimal("-47.4")
        configuracao.save()

    def proximo(self, dia_da_semana, condicao, chuva=None, a_partir_de=None):
        """Grava a previsão do próximo dia da semana pedido (0 = domingo, 6 = sábado)."""
        hoje = a_partir_de or date(2026, 10, 14)   # uma quarta-feira
        for passo in range(7):
            quando = hoje + timedelta(days=passo)
            if (quando.weekday() + 1) % 7 == dia_da_semana:
                return TempoDoDia.objects.create(
                    data=quando, condicao=condicao, chuva_mm=chuva, previsao=True)
        raise AssertionError("dia da semana não caiu na janela")

    def test_chuva_no_proximo_fim_de_semana_e_o_que_o_indicador_lidera(self):
        self.proximo(6, "chuva", Decimal("18"))      # sábado
        self.proximo(0, "sol")                       # domingo
        dados = indicador.montar(self.importacao, hoje=date(2026, 10, 14))
        self.assertTrue(dados.chuva_no_fim_de_semana)
        self.assertEqual(len(dados.fim_de_semana), 2)
        self.assertEqual(dados.nivel, "ruim")

    def test_sem_chuva_no_fim_de_semana_o_quadro_fica_verde(self):
        self.proximo(6, "sol")
        self.proximo(0, "nublado")
        dados = indicador.montar(self.importacao, hoje=date(2026, 10, 14))
        self.assertFalse(dados.chuva_no_fim_de_semana)
        self.assertEqual(dados.nivel, "bom")

    def test_chuva_de_terca_nao_pinta_o_quadro_de_vermelho(self):
        """O que muda o faturamento é o fim de semana; terça-feira é quase nada."""
        self.proximo(2, "tempestade", Decimal("50"))   # terça
        self.proximo(6, "sol")
        self.proximo(0, "sol")
        dados = indicador.montar(self.importacao, hoje=date(2026, 10, 14))
        self.assertFalse(dados.chuva_no_fim_de_semana)
        self.assertEqual(dados.nivel, "bom")

    def test_na_janela_que_pega_dois_fins_de_semana_vale_o_proximo(self):
        """Começando num domingo, sete dias alcançam o sábado seguinte também.

        Somar os dois diria "chuva no fim de semana" por causa de um sábado a seis dias
        de distância, e a loja não se prepara para isso hoje.
        """
        domingo = date(2026, 10, 18)
        TempoDoDia.objects.create(data=domingo, condicao="sol", previsao=True)
        TempoDoDia.objects.create(data=date(2026, 10, 24), condicao="sol", previsao=True)
        TempoDoDia.objects.create(data=date(2026, 10, 25), condicao="chuva",
                                  chuva_mm=Decimal("30"), previsao=True)
        dados = indicador.montar(self.importacao, hoje=domingo)
        self.assertEqual([dia.data for dia in dados.fim_de_semana], [domingo])
        self.assertFalse(dados.chuva_no_fim_de_semana)

    def test_sem_dias_guardados_o_indicador_nao_conclui_nada(self):
        self.proximo(6, "chuva", Decimal("12"))
        dados = indicador.montar(self.importacao, hoje=date(2026, 10, 14))
        self.assertFalse(dados.da_para_concluir)
        self.assertIsNone(dados.custo_da_chuva)

    def test_sem_cidade_o_indicador_pede_a_cidade_e_mais_nada(self):
        ConfiguracaoDoTempo.objects.all().delete()
        dados = indicador.montar(self.importacao, hoje=date(2026, 10, 14))
        self.assertFalse(dados.configurada)
        self.assertEqual(dados.o_que_falta, ["a cidade da loja"])
        self.assertEqual(dados.nivel, "atencao")


class OQuadroNaVisaoGeral(TestCase):
    def setUp(self):
        usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)

    def test_a_visao_geral_traz_o_quadro_do_tempo(self):
        resposta = self.client.get(reverse("painel:geral"))
        self.assertContains(resposta, "O tempo e a venda")

    def test_o_quadro_nao_pede_mais_a_cidade_porque_ela_ja_esta_escrita(self):
        """Ele informou Embu das Artes em 19/10/2026; o sistema parou de perguntar."""
        resposta = self.client.get(reverse("painel:geral"))
        self.assertNotContains(resposta, "Escreva a cidade da loja")

    def test_sem_cidade_o_quadro_volta_a_pedi_la(self):
        configuracao = ConfiguracaoDoTempo.atual()
        configuracao.cidade = ""
        configuracao.latitude = configuracao.longitude = None
        configuracao.save()
        resposta = self.client.get(reverse("painel:geral"))
        self.assertContains(resposta, "cidade da loja")

    def test_o_quadro_leva_para_a_tela_do_tempo_que_saiu_do_menu(self):
        resposta = self.client.get(reverse("painel:geral"))
        self.assertContains(resposta, reverse("tempo:painel"))

    def test_a_frase_do_quadro_sai_com_espaco_entre_as_duas_sentencas(self):
        """O spaceless come o espaço ENTRE etiquetas, e já saiu "sábado.Num fim de semana"."""
        importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO, situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(), data_corte=date(2026, 9, 20),
            dias_abertos_12m=360, produtos=0,
        )
        configuracao = ConfiguracaoDoTempo.atual()
        configuracao.cidade = "Sorocaba"
        configuracao.latitude, configuracao.longitude = Decimal("-23.5"), Decimal("-47.4")
        configuracao.save()

        # Vinte fins de semana medidos, metade com chuva: é o mínimo para a conta valer.
        sabado = date(2026, 5, 2)
        for semana in range(20):
            quando = sabado + timedelta(days=7 * semana)
            chove = semana % 2 == 0
            VendaImportada.objects.create(
                importacao=importacao, id_set=int(quando.strftime("%Y%m%d")), data=quando,
                dia_da_semana=(quando.weekday() + 1) % 7,
                valor=Decimal("4000") if chove else Decimal("10000"),
            )
            TempoDoDia.objects.create(data=quando, condicao="chuva" if chove else "sol")

        # E a previsão de chuva para o sábado que vem.
        hoje = date.today()
        for passo in range(7):
            quando = hoje + timedelta(days=passo)
            if (quando.weekday() + 1) % 7 == 6:
                TempoDoDia.objects.create(data=quando, condicao="chuva",
                                          chuva_mm=Decimal("20"), previsao=True)
                break

        corpo = self.client.get(reverse("painel:geral")).content.decode()
        self.assertIn("Chuva prevista para", corpo)
        self.assertIn("a menos", corpo)
        # Sem as etiquetas, que é como a frase chega aos olhos de quem lê a tela.
        lido = " ".join(strip_tags(corpo).split())
        self.assertIn("sábado. Num fim de semana de chuva a loja vende", lido)

    def test_a_previsao_guardada_aparece_no_quadro(self):
        hoje = date.today()
        TempoDoDia.objects.create(data=hoje, condicao="chuva_forte",
                                  chuva_mm=Decimal("22"), previsao=True)
        configuracao = ConfiguracaoDoTempo.atual()
        configuracao.cidade = "Sorocaba"
        configuracao.latitude, configuracao.longitude = Decimal("-23.5"), Decimal("-47.4")
        configuracao.save()
        resposta = self.client.get(reverse("painel:geral"))
        self.assertContains(resposta, "Chuva forte")
        self.assertContains(resposta, "previsão")
