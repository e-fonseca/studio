"""Contagem pelo celular: a tela da câmera e o registro sem recarregar a página."""

import json
from datetime import date
from decimal import Decimal

from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.contas.perfis import ADMINISTRATIVO, VENDEDOR
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.importacao.models import Importacao, ProdutoImportado
from apps.inventario import servicos


class BaseCamera(TestCase):
    def setUp(self):
        self.importacao = Importacao.objects.create(
            origem=Importacao.Origem.BANCO,
            situacao=Importacao.Situacao.CONCLUIDA,
            concluida_em=timezone.now(),
            data_corte=date(2026, 9, 20),
            dias_abertos_12m=300,
            produtos=1,
        )
        ProdutoImportado.objects.create(
            importacao=self.importacao, codigo="1", descricao="CARVAO SACO", grupo="LENHA",
            custo=Decimal("10"), estoque=Decimal("12"), codigo_barras="0000000000024",
        )
        self.operador = usuario("estoquista", ADMINISTRATIVO)
        self.client.login(username="estoquista", password=SENHA_TESTE)
        self.contagem = servicos.abrir("Prateleira dos tapetes", self.operador)


class TestTelaDaCamera(BaseCamera):
    def test_a_tela_abre_com_o_video_e_o_formulario(self):
        resposta = self.client.get(reverse("inventario:camera", args=[self.contagem.pk]))
        self.assertContains(resposta, "camera-video")
        self.assertContains(resposta, "formulario-camera")
        self.assertContains(resposta, "js/camera-codigo.js")

    @override_settings(PORTA_HTTPS="8443")
    def test_indica_o_endereco_seguro_com_a_porta_certa(self):
        """Trocar http por https não basta: a porta segura é outra."""
        resposta = self.client.get(reverse("inventario:camera", args=[self.contagem.pk]))
        self.assertContains(resposta, "https://testserver:8443/studio/inventario/")

    def test_o_aviso_de_https_nasce_escondido(self):
        """Quem abriu pelo endereço seguro não pode ver um aviso que não é dele."""
        resposta = self.client.get(reverse("inventario:camera", args=[self.contagem.pk]))
        corpo = resposta.content.decode()
        bloco = corpo[corpo.index('id="aviso-sem-https"'):]
        self.assertTrue(bloco[:bloco.index(">")].strip().endswith("hidden"))

    def test_contagem_fechada_nao_oferece_camera(self):
        servicos.fechar(self.contagem, self.operador)
        resposta = self.client.get(reverse("inventario:camera", args=[self.contagem.pk]))
        self.assertContains(resposta, "está fechada")
        self.assertNotContains(resposta, "camera-video")

    def test_vendedor_nao_abre_a_camera(self):
        self.client.logout()
        usuario("balcao", VENDEDOR)
        self.client.login(username="balcao", password=SENHA_TESTE)
        resposta = self.client.get(reverse("inventario:camera", args=[self.contagem.pk]))
        self.assertEqual(resposta.status_code, 403)

    def test_a_tela_do_inventario_leva_para_a_camera(self):
        resposta = self.client.get(reverse("inventario:lista"))
        self.assertContains(resposta, reverse("inventario:camera", args=[self.contagem.pk]))


class TestRegistroSemRecarregar(BaseCamera):
    def _contar(self, produto, quantidade):
        resposta = self.client.post(
            reverse("inventario:contar_pela_camera", args=[self.contagem.pk]),
            {"produto": produto, "quantidade": quantidade})
        self.assertEqual(resposta.status_code, 200)
        return json.loads(resposta.content)

    def test_leitura_boa_devolve_o_produto_e_a_diferenca(self):
        corpo = self._contar("0000000000024", "10")
        self.assertTrue(corpo["ok"])
        self.assertEqual(corpo["produto"]["descricao"], "CARVAO SACO")
        self.assertEqual(corpo["produto"]["saldo_set"], "12.000")
        self.assertEqual(corpo["produto"]["diferenca"], "-2.000")
        self.assertIn("faltam", corpo["produto"]["recado"])
        self.assertEqual(corpo["resumo"]["contados"], 1)

    def test_codigo_que_nao_existe_volta_com_recado_e_nao_grava(self):
        corpo = self._contar("9999999999999", "1")
        self.assertFalse(corpo["ok"])
        self.assertTrue(corpo["erro"])
        self.assertEqual(self.contagem.itens.count(), 0)

    def test_quantidade_errada_volta_com_recado(self):
        corpo = self._contar("0000000000024", "abc")
        self.assertFalse(corpo["ok"])

    def test_ler_duas_vezes_soma_como_na_tela_do_computador(self):
        self._contar("1", "7")
        corpo = self._contar("1", "5")
        self.assertEqual(corpo["produto"]["contado"], "12.000")
        self.assertTrue(corpo["produto"]["bate"])

    def test_contagem_fechada_recusa_a_leitura(self):
        servicos.fechar(self.contagem, self.operador)
        self.assertFalse(self._contar("1", "1")["ok"])

    def test_vendedor_nao_registra_leitura(self):
        self.client.logout()
        usuario("balcao", VENDEDOR)
        self.client.login(username="balcao", password=SENHA_TESTE)
        resposta = self.client.post(
            reverse("inventario:contar_pela_camera", args=[self.contagem.pk]),
            {"produto": "1", "quantidade": "1"})
        self.assertEqual(resposta.status_code, 403)

    def test_so_aceita_envio_e_nao_leitura_pela_barra_de_endereco(self):
        resposta = self.client.get(
            reverse("inventario:contar_pela_camera", args=[self.contagem.pk]))
        self.assertEqual(resposta.status_code, 405)


class TestFotoDaPrateleira(BaseCamera):
    """A foto serve para documentar o que não deu para resolver na hora da contagem."""

    def setUp(self):
        super().setUp()
        self.item = servicos.registrar_contagem(
            self.contagem, "1", Decimal("10"), self.operador)

    def _foto(self, conteudo=b"corpo-de-jpeg", tipo="image/jpeg", nome="prateleira.jpg"):
        from django.core.files.uploadedfile import SimpleUploadedFile

        return SimpleUploadedFile(nome, conteudo, content_type=tipo)

    def _enviar(self, **kwargs):
        resposta = self.client.post(
            reverse("inventario:guardar_foto", args=[self.contagem.pk, self.item.pk]),
            {"foto": self._foto(**kwargs)})
        self.assertEqual(resposta.status_code, 200)
        return json.loads(resposta.content)

    def test_a_foto_fica_guardada_no_item_com_a_hora(self):
        corpo = self._enviar()
        self.assertTrue(corpo["ok"])
        self.item.refresh_from_db()
        self.assertTrue(self.item.foto)
        self.assertIsNotNone(self.item.foto_em)

    def test_o_nome_do_arquivo_leva_o_codigo_do_produto(self):
        self._enviar()
        self.item.refresh_from_db()
        self.assertIn("1", self.item.foto.name)
        self.assertTrue(self.item.foto.name.endswith(".jpg"))

    def test_tirar_outra_foto_substitui_em_vez_de_acumular(self):
        """A última foto é a que vale, e o arquivo antigo sai do disco."""
        self._enviar()
        self.item.refresh_from_db()
        self._enviar(conteudo=b"outra-foto")
        self.item.refresh_from_db()
        self.assertEqual(self.item.foto.read(), b"outra-foto")
        _pastas, arquivos = default_storage.listdir(f"inventario/{self.contagem.pk}")
        self.assertEqual(len(arquivos), 1)

    def test_arquivo_que_nao_e_foto_da_camera_e_recusado(self):
        corpo = self._enviar(conteudo=b"%PDF-1.4", tipo="application/pdf", nome="nota.pdf")
        self.assertFalse(corpo["ok"])
        self.item.refresh_from_db()
        self.assertFalse(self.item.foto)

    def test_foto_grande_demais_e_recusada_com_recado(self):
        grande = b"x" * (servicos.TAMANHO_MAXIMO_DA_FOTO + 1)
        corpo = self._enviar(conteudo=grande)
        self.assertFalse(corpo["ok"])
        self.assertIn("grande demais", corpo["erro"])

    def test_sem_arquivo_nenhum_volta_com_recado(self):
        resposta = self.client.post(
            reverse("inventario:guardar_foto", args=[self.contagem.pk, self.item.pk]), {})
        self.assertFalse(json.loads(resposta.content)["ok"])

    def test_contagem_fechada_nao_recebe_foto(self):
        servicos.fechar(self.contagem, self.operador)
        self.assertFalse(self._enviar()["ok"])

    def test_a_foto_sai_pelo_sistema_e_nao_pela_pasta(self):
        """Foto de dentro da loja não pode ficar aberta para quem não entrou no sistema."""
        self._enviar()
        endereco = reverse("inventario:foto", args=[self.contagem.pk, self.item.pk])
        resposta = self.client.get(endereco)
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["Content-Type"], "image/jpeg")
        self.client.logout()
        self.assertNotEqual(self.client.get(endereco).status_code, 200)

    def test_item_sem_foto_devolve_nao_encontrado(self):
        resposta = self.client.get(
            reverse("inventario:foto", args=[self.contagem.pk, self.item.pk]))
        self.assertEqual(resposta.status_code, 404)

    def test_vendedor_nao_envia_foto(self):
        self.client.logout()
        usuario("balcao", VENDEDOR)
        self.client.login(username="balcao", password=SENHA_TESTE)
        resposta = self.client.post(
            reverse("inventario:guardar_foto", args=[self.contagem.pk, self.item.pk]),
            {"foto": self._foto()})
        self.assertEqual(resposta.status_code, 403)

    def test_a_resposta_da_leitura_diz_para_onde_mandar_a_foto(self):
        resposta = self.client.post(
            reverse("inventario:contar_pela_camera", args=[self.contagem.pk]),
            {"produto": "1", "quantidade": "2"})
        corpo = json.loads(resposta.content)
        self.assertIn("foto", corpo["produto"])
        self.assertIn("/foto/guardar/", corpo["produto"]["foto"])


class TestLeituraDoCodigoDeDozeDigitos(BaseCamera):
    def test_o_codigo_sem_o_zero_da_frente_acha_o_produto(self):
        """O leitor devolve EAN-13 que começa com zero como UPC-A de 12 dígitos."""
        resposta = self.client.post(
            reverse("inventario:contar_pela_camera", args=[self.contagem.pk]),
            {"produto": "000000000024", "quantidade": "3"})
        corpo = json.loads(resposta.content)
        self.assertTrue(corpo["ok"])
        self.assertEqual(corpo["produto"]["descricao"], "CARVAO SACO")


class TestOQueFazAEtiquetaSerLida(BaseCamera):
    """O que o Edson sentiu em 21/10/2026: a câmera não leu uma etiqueta sequer.

    *"a câmera foi habilitada e nao leu nenhuma etiqueta de código de barras, precisa
    ajustar melhor para fazer a leitura rápida para fazer sentido o modulo."*

    A causa foi medida com a câmera de mentira do Chromium e a etiqueta real da loja:
    era a RESOLUÇÃO. O pedido era de 1280, e aí um EAN-13 visto de um palmo fica com
    pouco mais de três pixels por barra. Trocando só isso por 1920, a mesma cena que
    não era lida em quinze segundos passou a ser lida na hora.

    Estes testes não leem código de barras — para isso é preciso navegador de verdade.
    Eles prendem as três coisas que, se alguém desfizer sem perceber, devolvem o defeito
    exatamente como ele era.
    """

    def ler_arquivo(self, caminho):
        from pathlib import Path  # noqa: PLC0415

        from django.conf import settings  # noqa: PLC0415

        return (Path(settings.BASE_DIR) / caminho).read_text(encoding="utf-8")

    def test_a_camera_e_pedida_em_1920(self):
        """Foi ESTA linha. A 1280 a etiqueta da prateleira não é legível por leitor nenhum."""
        import re  # noqa: PLC0415

        codigo = self.ler_arquivo("static/js/camera-codigo.js")
        # Dentro do objeto que vai ao getUserMedia, e não em qualquer lugar do arquivo:
        # o comentário do topo cita o 1280 antigo para explicar o defeito.
        pedido = re.search(r"var pedido = \{(.+?)\n    \};", codigo, re.S)
        self.assertIsNotNone(pedido, "o pedido da câmera mudou de forma")
        largura = re.search(r"width:\s*\{\s*ideal:\s*(\d+)", pedido.group(1))
        self.assertIsNotNone(largura, "o pedido da câmera precisa dizer a largura desejada")
        self.assertGreaterEqual(int(largura.group(1)), 1920)

    def test_o_leitor_do_aparelho_vem_antes_do_nosso(self):
        """O Chrome do Android tem o leitor do Google; usar só o nosso é jogar fora o melhor."""
        codigo = self.ler_arquivo("static/js/camera-codigo.js")
        self.assertIn("BarcodeDetector", codigo)
        self.assertLess(codigo.index("function leitorDoNavegador"),
                        codigo.index("function leitorDaBiblioteca"))

    def test_a_faixa_da_tela_e_a_faixa_que_o_leitor_analisa(self):
        """Faixa desenhada num lugar e leitura em outro faz a pessoa mirar no vazio.

        São dois arquivos, um CSS e um JavaScript, com os mesmos quatro números. É
        exatamente o tipo de par que se desencontra numa mudança de layout meses depois,
        e o desencontro é invisível: a imagem continua bonita na tela.
        """
        import re  # noqa: PLC0415

        codigo = self.ler_arquivo("static/js/camera-codigo.js")
        folha = self.ler_arquivo("static/css/sistema.css")
        alvo = re.search(r"var ALVO = \{([^}]+)\}", codigo).group(1)
        numeros = dict(re.findall(r"(\w+):\s*([\d.]+)", alvo))
        regra = re.search(r"\.camera-alvo \{([^}]+)\}", folha).group(1)
        css = dict(re.findall(r"(left|right|top|height):\s*([\d.]+)%", regra))
        self.assertEqual(float(css["left"]) / 100, float(numeros["esquerda"]))
        self.assertEqual(float(css["top"]) / 100, float(numeros["topo"]))
        self.assertEqual(float(css["height"]) / 100, float(numeros["altura"]))
        # right é a distância até a borda: a largura é o que sobra dos dois lados.
        largura = 1 - float(css["left"]) / 100 - float(css["right"]) / 100
        self.assertAlmostEqual(largura, float(numeros["largura"]), places=4)

    def test_a_tela_oferece_lanterna_e_aproximar_escondidos(self):
        """Etiqueta pequena em peça escura: são os dois botões que salvam a leitura.

        Nascem escondidos porque nem todo aparelho tem os recursos, e botão que não faz
        nada é promessa quebrada na cara de quem clicou.
        """
        corpo = self.client.get(
            reverse("inventario:camera", args=[self.contagem.pk])).content.decode()
        for identificador in ("camera-lanterna", "camera-aproximar"):
            with self.subTest(botao=identificador):
                bloco = corpo[corpo.index('id="%s"' % identificador):]
                self.assertTrue(bloco[:bloco.index(">")].strip().endswith("hidden"))

    def test_a_tela_manda_encostar_na_etiqueta(self):
        """A distância é o que mais faz falhar, e é a única parte que o código não resolve."""
        resposta = self.client.get(reverse("inventario:camera", args=[self.contagem.pk]))
        self.assertContains(resposta, "Encoste a câmera quase na etiqueta")
