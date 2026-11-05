"""Certificado próprio e porta HTTPS: é o que libera a câmera do celular."""

import datetime as dt
import http.client
import os
import socket
import shutil
import ssl
import tempfile
import threading
from pathlib import Path
from unittest import mock
from wsgiref.simple_server import make_server

from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.contas.perfis import ADMINISTRACAO, VENDEDOR
from apps.core import certificado, https, tunel_tls
from apps.core.fabricas import SENHA_TESTE, usuario


class TestCertificado(SimpleTestCase):
    def test_cria_certificado_e_chave_quando_nao_existem(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo, chave = certificado.garantir(Path(pasta), ["192.168.3.254", "localhost"])
            self.assertTrue(arquivo.is_file())
            self.assertTrue(chave.is_file())
            self.assertIn(b"BEGIN CERTIFICATE", arquivo.read_bytes())
            self.assertIn(b"PRIVATE KEY", chave.read_bytes())

    def test_vale_para_o_ip_e_para_o_nome_da_maquina(self):
        """O navegador confere o endereço digitado contra a lista do certificado."""
        from cryptography import x509

        with tempfile.TemporaryDirectory() as pasta:
            arquivo, _ = certificado.garantir(Path(pasta), ["192.168.3.254", "cabana-srv"])
            lido = x509.load_pem_x509_certificate(arquivo.read_bytes())
            nomes = lido.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            self.assertIn("cabana-srv", nomes.get_values_for_type(x509.DNSName))
            self.assertEqual(str(nomes.get_values_for_type(x509.IPAddress)[0]), "192.168.3.254")

    def test_nao_refaz_o_certificado_a_cada_vez(self):
        """Refazer trocaria a impressão digital e o celular pediria o aviso de novo."""
        with tempfile.TemporaryDirectory() as pasta:
            arquivo, _ = certificado.garantir(Path(pasta), ["localhost"])
            antes = arquivo.read_bytes()
            certificado.garantir(Path(pasta), ["localhost"])
            self.assertEqual(arquivo.read_bytes(), antes)

    def test_refaz_quando_esta_perto_de_vencer(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo, _ = certificado.garantir(Path(pasta), ["localhost"])
            antes = arquivo.read_bytes()
            certificado.garantir(Path(pasta), ["localhost"], refazer=True)
            self.assertNotEqual(arquivo.read_bytes(), antes)

    def test_comeca_a_valer_ontem_e_nao_passa_do_limite_da_apple(self):
        """Relógio adiantado não invalida; e acima de 825 dias o iPhone recusa."""
        from cryptography import x509

        with tempfile.TemporaryDirectory() as pasta:
            arquivo, _ = certificado.garantir(Path(pasta), ["localhost"])
            lido = x509.load_pem_x509_certificate(arquivo.read_bytes())
            agora = dt.datetime.now(dt.timezone.utc)
            self.assertLess(lido.not_valid_before_utc, agora)
            self.assertGreater(lido.not_valid_after_utc, agora + dt.timedelta(days=180))
            self.assertLess(lido.not_valid_after_utc, agora + dt.timedelta(days=825))

    def test_a_autoridade_nasce_junto_e_vale_muito_mais(self):
        """Ela é instalada à mão em cada aparelho, então não pode vencer toda hora."""
        from cryptography import x509

        with tempfile.TemporaryDirectory() as pasta:
            certificado.garantir(Path(pasta), ["localhost"])
            raiz = x509.load_pem_x509_certificate(
                (Path(pasta) / certificado.NOME_AUTORIDADE).read_bytes())
            agora = dt.datetime.now(dt.timezone.utc)
            self.assertGreater(raiz.not_valid_after_utc, agora + dt.timedelta(days=5 * 365))
            basicas = raiz.extensions.get_extension_for_class(x509.BasicConstraints).value
            self.assertTrue(basicas.ca)

    def test_o_certificado_do_servidor_e_assinado_pela_autoridade(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo, _ = certificado.garantir(Path(pasta), ["localhost"])
            raiz = Path(pasta) / certificado.NOME_AUTORIDADE
            self.assertTrue(certificado._assinada_pela_autoridade(arquivo, raiz))

    def test_declara_uso_de_servidor_tls_que_o_iphone_exige(self):
        from cryptography import x509
        from cryptography.x509.oid import ExtendedKeyUsageOID

        with tempfile.TemporaryDirectory() as pasta:
            arquivo, _ = certificado.garantir(Path(pasta), ["localhost"])
            lido = x509.load_pem_x509_certificate(arquivo.read_bytes())
            usos = lido.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
            self.assertIn(ExtendedKeyUsageOID.SERVER_AUTH, list(usos))

    def test_certificado_antigo_assinado_por_ele_mesmo_e_trocado(self):
        """Quem atualiza da 1.17.0 tem um certificado sem autoridade; ele tem que sair."""
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        with tempfile.TemporaryDirectory() as pasta:
            pasta = Path(pasta)
            pasta.mkdir(parents=True, exist_ok=True)
            privada = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
            agora = dt.datetime.now(dt.timezone.utc)
            antigo = (
                x509.CertificateBuilder().subject_name(nome).issuer_name(nome)
                .public_key(privada.public_key()).serial_number(1)
                .not_valid_before(agora - dt.timedelta(days=1))
                .not_valid_after(agora + dt.timedelta(days=700))
                .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
                .sign(privada, hashes.SHA256())
            )
            (pasta / certificado.NOME_CERTIFICADO).write_bytes(
                antigo.public_bytes(serialization.Encoding.PEM))
            (pasta / certificado.NOME_CHAVE).write_bytes(privada.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()))

            arquivo, _ = certificado.garantir(pasta, ["localhost"])
            self.assertTrue(certificado._assinada_pela_autoridade(
                arquivo, pasta / certificado.NOME_AUTORIDADE))

    def test_nao_refaz_so_porque_a_autoridade_ja_existe(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo, _ = certificado.garantir(Path(pasta), ["localhost"])
            antes = arquivo.read_bytes()
            raiz_antes = (Path(pasta) / certificado.NOME_AUTORIDADE).read_bytes()
            certificado.garantir(Path(pasta), ["localhost"])
            self.assertEqual(arquivo.read_bytes(), antes)
            self.assertEqual((Path(pasta) / certificado.NOME_AUTORIDADE).read_bytes(), raiz_antes)

    def test_endereco_novo_no_cabana_env_refaz_o_certificado(self):
        """Senão acrescentar um endereço não teria efeito e o navegador recusaria."""
        with tempfile.TemporaryDirectory() as pasta:
            arquivo, _ = certificado.garantir(Path(pasta), ["localhost"])
            antes = arquivo.read_bytes()
            certificado.garantir(Path(pasta), ["localhost", "192.168.3.254"])
            self.assertNotEqual(arquivo.read_bytes(), antes)

    def test_descrever_mostra_validade_e_impressao_digital(self):
        with tempfile.TemporaryDirectory() as pasta:
            certificado.garantir(Path(pasta), ["localhost"])
            ficha = certificado.descrever(Path(pasta))
            self.assertIsNotNone(ficha["autoridade"])
            self.assertIsNotNone(ficha["servidor"])
            self.assertGreater(ficha["autoridade"]["dias"], ficha["servidor"]["dias"])
            self.assertEqual(len(ficha["servidor"]["impressao"].split(" ")), 32)

    def test_a_chave_da_autoridade_nunca_sai_no_arquivo_entregue(self):
        """A tela entrega só o .crt; a chave assina e fica no servidor."""
        with tempfile.TemporaryDirectory() as pasta:
            certificado.garantir(Path(pasta), ["localhost"])
            entregue = (Path(pasta) / certificado.NOME_AUTORIDADE).read_bytes()
            self.assertIn(b"BEGIN CERTIFICATE", entregue)
            self.assertNotIn(b"PRIVATE KEY", entregue)

    def test_arquivo_estragado_e_refeito_em_vez_de_derrubar_o_sistema(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo, chave = certificado.garantir(Path(pasta), ["localhost"])
            arquivo.write_bytes(b"isto nao e um certificado")
            certificado.garantir(Path(pasta), ["localhost"])
            self.assertIn(b"BEGIN CERTIFICATE", arquivo.read_bytes())


def _aplicacao(environ, iniciar):
    iniciar("200 OK", [("Content-Type", "text/plain; charset=utf-8")])
    return [b"ola do sistema"]


class TestTunelHttps(SimpleTestCase):
    """O túnel recebe em TLS e entrega ao servidor de dentro sem mexer no conteúdo."""

    def test_pagina_servida_em_http_chega_igual_por_https(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo, chave = certificado.garantir(Path(pasta), ["localhost", "127.0.0.1"])
            interno = make_server("127.0.0.1", 0, _aplicacao)
            porta_interna = interno.server_address[1]
            threading.Thread(target=interno.serve_forever, daemon=True).start()
            porta_segura = _porta_livre()
            tunel_tls.em_segundo_plano(porta_segura, ("127.0.0.1", porta_interna), arquivo, chave)
            _esperar(porta_segura)
            # O cliente confia na autoridade da loja, não no certificado do servidor:
            # é exatamente o que o celular faz depois de instalar a autoridade.
            contexto = ssl.create_default_context(
                cafile=str(Path(pasta) / certificado.NOME_AUTORIDADE))
            ligacao = http.client.HTTPSConnection("localhost", porta_segura, context=contexto, timeout=10)
            try:
                ligacao.request("GET", "/studio/")
                resposta = ligacao.getresponse()
                self.assertEqual(resposta.status, 200)
                self.assertEqual(resposta.read(), b"ola do sistema")
            finally:
                ligacao.close()
                interno.shutdown()

    def test_o_tls_do_cliente_nunca_e_usado_por_duas_linhas_ao_mesmo_tempo(self):
        """A página cortada no celular (corrigida na 1.43.0).

        Até a 1.42.0 o túnel tinha uma linha lendo o navegador e outra escrevendo nele, as
        duas no mesmo objeto TLS do OpenSSL, que não aguenta isso: 2 a 11 de cada 400
        páginas chegavam sem o fim. A falha em si é rara e depende da carga da máquina; o
        que este teste trava é a causa, que acontecia em TODA página: a leitura parada à
        espera do pedido seguinte enquanto a resposta era escrita.
        """
        with tempfile.TemporaryDirectory() as pasta:
            arquivo, chave = certificado.garantir(Path(pasta), ["localhost", "127.0.0.1"])
            interno = make_server("127.0.0.1", 0, _aplicacao)
            threading.Thread(target=interno.serve_forever, daemon=True).start()
            do_servidor = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            do_servidor.load_cert_chain(certfile=str(arquivo), keyfile=str(chave))
            ouvinte = socket.create_server(("127.0.0.1", 0))
            vigias = []

            def aceitar():
                crua, _ = ouvinte.accept()
                vigia = _VigiaDoTls(do_servidor.wrap_socket(crua, server_side=True))
                vigias.append(vigia)
                tunel_tls._atender(vigia, ("127.0.0.1", interno.server_address[1]))

            linha = threading.Thread(target=aceitar, daemon=True)
            linha.start()
            contexto = ssl.create_default_context(
                cafile=str(Path(pasta) / certificado.NOME_AUTORIDADE))
            ligacao = http.client.HTTPSConnection(
                "localhost", ouvinte.getsockname()[1], context=contexto, timeout=10)
            try:
                ligacao.request("GET", "/studio/")
                self.assertEqual(ligacao.getresponse().read(), b"ola do sistema")
            finally:
                ligacao.close()
                interno.shutdown()
                ouvinte.close()
            linha.join(timeout=10)
            self.assertEqual(vigias[0].mais_de_uma_vez, 1,
                             "duas linhas dentro do TLS do cliente ao mesmo tempo")

    def test_porta_ocupada_nao_derruba_o_sistema(self):
        """A loja não pode parar porque o HTTPS não subiu."""
        import socket

        with tempfile.TemporaryDirectory() as pasta:
            arquivo, chave = certificado.garantir(Path(pasta), ["localhost"])
            ocupada = socket.socket()
            ocupada.bind(("127.0.0.1", 0))
            ocupada.listen(1)
            porta = ocupada.getsockname()[1]
            try:
                with mock.patch.dict(os.environ, {"STUDIO_CERTIFICADO_PASTA": pasta}):
                    linha = tunel_tls.em_segundo_plano(
                        porta, ("127.0.0.1", 1), arquivo, chave, host="127.0.0.1")
                    linha.join(timeout=5)
                self.assertFalse(linha.is_alive())
            finally:
                ocupada.close()


class _VigiaDoTls:
    """Embrulha o TLS do cliente e anota quantas linhas estiveram dentro dele de uma vez."""

    def __init__(self, real):
        self._real = real
        self._trava = threading.Lock()
        self._dentro = 0
        self.mais_de_uma_vez = 0

    def _contar(self, metodo, *args):
        with self._trava:
            self._dentro += 1
            self.mais_de_uma_vez = max(self.mais_de_uma_vez, self._dentro)
        try:
            return metodo(*args)
        finally:
            with self._trava:
                self._dentro -= 1

    def recv(self, tamanho):
        return self._contar(self._real.recv, tamanho)

    def sendall(self, dados):
        return self._contar(self._real.sendall, dados)

    def __getattr__(self, nome):  # settimeout, pending, fileno, shutdown, close
        return getattr(self._real, nome)


def _porta_livre():
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _esperar(porta, tentativas=50):
    import socket
    import time

    for _ in range(tentativas):
        try:
            with socket.create_connection(("127.0.0.1", porta), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.05)
    return False


class TestTelaDoCertificado(TestCase):
    """A tela que entrega a autoridade da loja e ensina a instalar no aparelho."""

    def setUp(self):
        self.pasta = Path(tempfile.mkdtemp())
        certificado.garantir(self.pasta, ["192.168.3.254", "localhost"])

    def tearDown(self):
        shutil.rmtree(self.pasta, ignore_errors=True)

    def _entrar(self, nome, perfil):
        usuario(nome, perfil)
        self.client.login(username=nome, password=SENHA_TESTE)

    def test_a_tela_ensina_o_passo_a_passo_de_cada_aparelho(self):
        self._entrar("gerencia", ADMINISTRACAO)
        with mock.patch.object(certificado, "pasta_padrao", return_value=self.pasta):
            resposta = self.client.get(reverse("core:certificado"))
        self.assertContains(resposta, "Android")
        self.assertContains(resposta, "iPhone")
        self.assertContains(resposta, "Windows")
        # O passo que quase todo mundo esquece no iPhone.
        self.assertContains(resposta, "Confiança de Certificado")

    def test_mostra_a_impressao_digital_para_conferir_na_instalacao(self):
        self._entrar("gerencia", ADMINISTRACAO)
        with mock.patch.object(certificado, "pasta_padrao", return_value=self.pasta):
            resposta = self.client.get(reverse("core:certificado"))
        ficha = certificado.descrever(self.pasta)
        self.assertContains(resposta, ficha["autoridade"]["impressao"])

    def test_o_arquivo_baixado_e_a_autoridade_e_nao_a_chave(self):
        self._entrar("gerencia", ADMINISTRACAO)
        with mock.patch.object(certificado, "pasta_padrao", return_value=self.pasta):
            resposta = self.client.get(reverse("core:certificado_autoridade"))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["Content-Type"], "application/x-x509-ca-cert")
        corpo = b"".join(resposta.streaming_content)
        self.assertIn(b"BEGIN CERTIFICATE", corpo)
        self.assertNotIn(b"PRIVATE KEY", corpo)

    def test_o_vendedor_tambem_consegue_instalar_no_celular_dele(self):
        """A tela não mostra nada da loja, e quem instala é a pessoa no aparelho dela."""
        self._entrar("balcao", VENDEDOR)
        with mock.patch.object(certificado, "pasta_padrao", return_value=self.pasta):
            resposta = self.client.get(reverse("core:certificado"))
        self.assertEqual(resposta.status_code, 200)

    def test_mas_a_tela_nao_entra_no_menu_do_vendedor(self):
        """Ele tem uma tela só; esta entra pelo link que a gerência passa."""
        from apps.core import menu

        pessoa = usuario("balcao2", VENDEDOR)
        rotas = [item.rota for item in menu.permitidos(menu.telas(), pessoa)]
        self.assertNotIn("core:certificado", rotas)
        self.assertEqual(rotas, ["importacao:consulta"])

    def test_sem_login_nao_baixa(self):
        with mock.patch.object(certificado, "pasta_padrao", return_value=self.pasta):
            resposta = self.client.get(reverse("core:certificado_autoridade"))
        self.assertEqual(resposta.status_code, 302)

    def test_pasta_vazia_a_tela_gera_na_hora_em_vez_de_mandar_esperar(self):
        """Antes da 1.19.1 a tela dizia "ainda não foram gerados" e o download dava 404.

        Quem abre esta tela quer instalar o certificado agora, no aparelho que está na
        mão. Então a tela cria o que falta e entrega, em vez de mandar voltar depois.
        """
        self._entrar("gerencia", ADMINISTRACAO)
        vazia = Path(tempfile.mkdtemp())
        try:
            with mock.patch.object(certificado, "pasta_padrao", return_value=vazia):
                resposta = self.client.get(reverse("core:certificado"))
                self.assertEqual(resposta.status_code, 200)
                self.assertEqual(
                    self.client.get(reverse("core:certificado_autoridade")).status_code, 200)
            self.assertTrue((vazia / certificado.NOME_AUTORIDADE).is_file())
        finally:
            shutil.rmtree(vazia, ignore_errors=True)


# Os endereços de verdade da loja: o teste precisa pedir a página como o celular pede,
# pelo IP, senão o Django recusa o host antes de a faixa ser decidida.
@override_settings(ALLOWED_HOSTS=["192.168.3.254", "localhost", "testserver"])
class TestAvisoDeEnderecoSemSeguranca(TestCase):
    """O Edson abriu o endereço sem cadeado e concluiu que o SSL não funcionava.

    Era verdade na tela dele: nada no sistema dizia que existia outro endereço. Estes
    testes travam a faixa que diz, e o autodiagnóstico que responde se a porta segura
    está mesmo de pé.
    """

    def setUp(self):
        usuario("gerente-https", ADMINISTRACAO)
        self.client.login(username="gerente-https", password=SENHA_TESTE)

    def test_a_faixa_aparece_no_endereco_de_rede_em_http(self):
        resposta = self.client.get(reverse("core:certificado"), HTTP_HOST="192.168.3.254:8095")
        self.assertContains(resposta, "faixa-sem-seguranca")
        self.assertContains(resposta, "https://192.168.3.254:8443")

    def test_nao_aparece_em_localhost_porque_la_a_camera_ja_funciona(self):
        resposta = self.client.get(reverse("core:certificado"), HTTP_HOST="localhost:8095")
        self.assertNotContains(resposta, "faixa-sem-seguranca")

    def test_nao_aparece_quando_a_pessoa_ja_esta_no_https(self):
        resposta = self.client.get(reverse("core:certificado"), secure=True,
                                   HTTP_HOST="192.168.3.254:8443")
        self.assertNotContains(resposta, "faixa-sem-seguranca")

    def test_o_endereco_sugerido_leva_para_a_mesma_pagina(self):
        pedido = RequestFactory().get("/studio/painel/dashboard/", HTTP_HOST="192.168.3.254:8095")
        self.assertEqual(https.endereco_seguro(pedido),
                         "https://192.168.3.254:8443/studio/painel/dashboard/")

    def test_com_https_desligado_no_cabana_env_nao_promete_endereco_que_nao_existe(self):
        pedido = RequestFactory().get("/studio/", HTTP_HOST="192.168.3.254:8095")
        with mock.patch.dict(os.environ, {"STUDIO_HTTPS": "0"}):
            self.assertFalse(https.sem_seguranca(pedido))
            self.assertEqual(https.conferir().nivel, "ruim")

    def test_porta_sem_ninguem_atendendo_e_diagnostico_ruim_com_o_que_fazer(self):
        # Pasta própria para o teste: sem certificado o diagnóstico seria outro, e uma
        # anotação de falha deixada por outro teste mudaria a mensagem.
        with tempfile.TemporaryDirectory() as pasta:
            certificado.garantir(Path(pasta), ["localhost", "127.0.0.1"])
            with mock.patch.dict(os.environ, {
                    "STUDIO_CERTIFICADO_PASTA": pasta,
                    "STUDIO_PORTA_HTTPS": str(_porta_livre())}):
                resultado = https.conferir(tempo_limite=0.5)
        self.assertEqual(resultado.nivel, "ruim")
        self.assertFalse(resultado.funcionando)
        self.assertIn("StudioSistema", resultado.detalhe)

    def test_porta_com_tls_de_pe_e_diagnostico_bom(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo, chave = certificado.garantir(Path(pasta), ["localhost", "127.0.0.1"])
            interno = make_server("127.0.0.1", 0, _aplicacao)
            threading.Thread(target=interno.serve_forever, daemon=True).start()
            porta = _porta_livre()
            tunel_tls.em_segundo_plano(porta, ("127.0.0.1", interno.server_address[1]),
                                       arquivo, chave)
            _esperar(porta)
            try:
                with mock.patch.dict(os.environ, {"STUDIO_PORTA_HTTPS": str(porta)}):
                    resultado = https.conferir(tempo_limite=2.0)
            finally:
                interno.shutdown()
        self.assertEqual(resultado.nivel, "bom")
        self.assertTrue(resultado.funcionando)
        self.assertIn("TLS", resultado.detalhe)

    def test_a_tela_do_certificado_mostra_o_resultado_do_teste(self):
        resposta = self.client.get(reverse("core:certificado"), HTTP_HOST="192.168.3.254:8095")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("diagnostico", resposta.context)
        self.assertContains(resposta, "estado-" + resposta.context["diagnostico"].nivel)



class TestPastaDoCertificado(SimpleTestCase):
    """Onde o certificado nasce quando a pasta configurada não aceita escrita.

    No servidor da loja a pasta configurada era config\\certificado, e a conta que roda o
    sistema só tem leitura em config: o certificado nunca foi criado, a porta segura
    nunca subiu e o download da autoridade dava 404 — tudo em silêncio (08/10/2026).
    """

    def test_usa_a_pasta_configurada_quando_da_para_gravar(self):
        with tempfile.TemporaryDirectory() as pasta:
            with mock.patch.dict(os.environ, {"STUDIO_CERTIFICADO_PASTA": pasta}):
                self.assertEqual(certificado.pasta_padrao(), Path(pasta))

    def test_pasta_so_de_leitura_cai_para_outra_que_aceita_escrita(self):
        # A conta do serviço no Windows é quem não escreve ali; aqui o teste roda como
        # root, que escreve em qualquer pasta, então a recusa é simulada.
        with tempfile.TemporaryDirectory() as raiz:
            trancada = Path(raiz) / "config" / "certificado"
            trancada.mkdir(parents=True)
            recusar = lambda pasta: pasta != trancada  # noqa: E731
            with mock.patch.object(certificado, "_da_para_gravar", side_effect=recusar), \
                    mock.patch.dict(os.environ, {"STUDIO_CERTIFICADO_PASTA": str(trancada)}):
                escolhida = certificado.pasta_padrao()
            self.assertNotEqual(escolhida, trancada)
            # E a escolhida serve mesmo: o certificado nasce nela.
            arquivo, chave = certificado.garantir(escolhida, ["localhost"])
            self.assertTrue(arquivo.is_file() and chave.is_file())

    def test_pasta_que_nao_da_para_criar_e_recusada(self):
        with tempfile.NamedTemporaryFile() as arquivo:
            # Pasta "dentro" de um arquivo: o sistema operacional recusa criar.
            self.assertFalse(certificado._da_para_gravar(Path(arquivo.name) / "certificado"))

    def test_certificado_que_ja_existe_na_pasta_configurada_continua_valendo(self):
        """Pasta sem escrita mas com o certificado dentro: ler basta, não muda de lugar."""
        with tempfile.TemporaryDirectory() as pasta:
            certificado.garantir(Path(pasta), ["localhost"])
            Path(pasta).chmod(0o500)
            try:
                with mock.patch.dict(os.environ, {"STUDIO_CERTIFICADO_PASTA": pasta}):
                    self.assertEqual(certificado.pasta_padrao(), Path(pasta))
            finally:
                Path(pasta).chmod(0o700)

    def test_o_tunel_e_a_tela_escolhem_sempre_a_mesma_pasta(self):
        """Se as duas discordassem, a tela entregaria uma autoridade que o túnel não usa."""
        with tempfile.TemporaryDirectory() as pasta:
            with mock.patch.dict(os.environ, {"STUDIO_CERTIFICADO_PASTA": pasta}):
                self.assertEqual(certificado.pasta_padrao(), certificado.pasta_padrao())


class TestDownloadDaAutoridade(TestCase):
    def setUp(self):
        usuario("gerente-autoridade", ADMINISTRACAO)
        self.client.login(username="gerente-autoridade", password=SENHA_TESTE)

    def test_a_tela_cria_o_certificado_na_hora_se_ele_nao_existe(self):
        with tempfile.TemporaryDirectory() as pasta:
            with mock.patch.dict(os.environ, {"STUDIO_CERTIFICADO_PASTA": pasta}):
                resposta = self.client.get(reverse("core:certificado"))
            self.assertEqual(resposta.status_code, 200)
            self.assertIsNone(resposta.context["erro_ao_gerar"])
            self.assertTrue((Path(pasta) / certificado.NOME_AUTORIDADE).is_file())

    def test_download_funciona_logo_depois_de_instalar_sem_ter_subido_o_https(self):
        with tempfile.TemporaryDirectory() as pasta:
            with mock.patch.dict(os.environ, {"STUDIO_CERTIFICADO_PASTA": pasta}):
                resposta = self.client.get(reverse("core:certificado_autoridade"))
            self.assertEqual(resposta.status_code, 200)
            self.assertEqual(resposta["Content-Type"], "application/x-x509-ca-cert")

    def test_quando_nao_da_para_criar_a_tela_explica_em_vez_de_dar_404(self):
        with mock.patch.object(certificado, "garantir", side_effect=PermissionError("negado")), \
                tempfile.TemporaryDirectory() as pasta:
            with mock.patch.dict(os.environ, {"STUDIO_CERTIFICADO_PASTA": pasta}):
                resposta = self.client.get(reverse("core:certificado_autoridade"))
        self.assertEqual(resposta.status_code, 503)
        self.assertContains(resposta, "PermissionError", status_code=503)
        self.assertContains(resposta, "Não consegui entregar o certificado", status_code=503)

    def test_o_motivo_da_falha_aparece_na_tela_do_certificado(self):
        with mock.patch.object(certificado, "garantir", side_effect=PermissionError("negado")), \
                tempfile.TemporaryDirectory() as pasta:
            with mock.patch.dict(os.environ, {"STUDIO_CERTIFICADO_PASTA": pasta}):
                resposta = self.client.get(reverse("core:certificado"))
        self.assertContains(resposta, "PermissionError")
        self.assertContains(resposta, "não foi criado neste servidor")

    def test_sem_certificado_o_diagnostico_diz_isso_e_nao_so_que_a_porta_esta_muda(self):
        with tempfile.TemporaryDirectory() as pasta:
            with mock.patch.dict(os.environ, {"STUDIO_CERTIFICADO_PASTA": pasta,
                                              "STUDIO_PORTA_HTTPS": str(_porta_livre())}):
                resultado = https.conferir(tempo_limite=0.5)
        self.assertEqual(resultado.nivel, "ruim")
        self.assertIn("certificado", resultado.titulo.lower())


class TestFalhaDoTunelAnotada(SimpleTestCase):
    """O motivo de a porta segura não subir tem que chegar à tela, não só ao log.

    O túnel sobe numa linha de trabalho separada, então o erro dele nunca volta para
    quem iniciou o sistema: até a 1.19.1 ia só para logs\\sistema.log. Era por isso que
    "SSL não funcionou" não tinha explicação em lugar nenhum.
    """

    def test_anota_o_motivo_e_devolve_com_a_data(self):
        with tempfile.TemporaryDirectory() as pasta:
            with mock.patch.dict(os.environ, {"STUDIO_CERTIFICADO_PASTA": pasta}):
                https.registrar_falha("OSError: endereço já em uso")
                quando, motivo = https.falha_registrada()
        self.assertIn("/", quando)
        self.assertEqual(motivo, "OSError: endereço já em uso")

    def test_quando_a_porta_sobe_a_anotacao_e_apagada(self):
        with tempfile.TemporaryDirectory() as pasta:
            with mock.patch.dict(os.environ, {"STUDIO_CERTIFICADO_PASTA": pasta}):
                https.registrar_falha("PermissionError: sem permissão de gravar")
                https.esquecer_falha()
                self.assertIsNone(https.falha_registrada())

    def test_sem_anotacao_nenhuma_nao_inventa_motivo(self):
        with tempfile.TemporaryDirectory() as pasta:
            with mock.patch.dict(os.environ, {"STUDIO_CERTIFICADO_PASTA": pasta}):
                self.assertIsNone(https.falha_registrada())

    def test_o_diagnostico_conta_o_motivo_anotado_em_vez_do_texto_generico(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta)
            certificado.garantir(caminho, ["localhost", "127.0.0.1"])
            with mock.patch.dict(os.environ, {
                    "STUDIO_CERTIFICADO_PASTA": pasta,
                    "STUDIO_PORTA_HTTPS": str(_porta_livre())}):
                https.registrar_falha("FileNotFoundError: chave do certificado")
                resultado = https.conferir(tempo_limite=0.5)
        self.assertEqual(resultado.nivel, "ruim")
        self.assertIn("chave do certificado", resultado.detalhe)

    def test_tunel_que_nao_consegue_subir_anota_o_motivo_sozinho(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo, chave = certificado.garantir(Path(pasta), ["localhost", "127.0.0.1"])
            ocupada = socket.socket()
            ocupada.bind(("127.0.0.1", 0))
            ocupada.listen(1)
            porta = ocupada.getsockname()[1]
            try:
                with mock.patch.dict(os.environ, {"STUDIO_CERTIFICADO_PASTA": pasta}):
                    linha = tunel_tls.em_segundo_plano(porta, ("127.0.0.1", 1), arquivo, chave)
                    linha.join(timeout=5)
                    anotado = https.falha_registrada()
            finally:
                ocupada.close()
        self.assertIsNotNone(anotado)
        self.assertIn("Error", anotado[1])


class TestPortaPelaRede(SimpleTestCase):
    """A porta pode estar de pé dentro do servidor e não atender pelo endereço da rede."""

    def test_de_pe_no_servidor_e_fechada_na_rede_e_aviso_com_o_que_conferir(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo, chave = certificado.garantir(Path(pasta), ["localhost", "127.0.0.1"])
            interno = make_server("127.0.0.1", 0, _aplicacao)
            threading.Thread(target=interno.serve_forever, daemon=True).start()
            porta = _porta_livre()
            tunel_tls.em_segundo_plano(porta, ("127.0.0.1", interno.server_address[1]),
                                       arquivo, chave, host="127.0.0.1")
            _esperar(porta)
            try:
                with mock.patch.dict(os.environ, {
                        "STUDIO_CERTIFICADO_PASTA": pasta,
                        "STUDIO_PORTA_HTTPS": str(porta)}), \
                        mock.patch.object(https, "_atende",
                                          return_value=OSError("tempo esgotado")):
                    resultado = https.conferir(tempo_limite=0.5,
                                               endereco_rede="192.168.3.254")
            finally:
                interno.shutdown()
        self.assertEqual(resultado.nivel, "atencao")
        self.assertIn("192.168.3.254", resultado.titulo)
        self.assertIn("STUDIO_HOST", resultado.detalhe)

    def test_atendendo_nos_dois_a_tela_diz_o_que_falta_no_aparelho(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo, chave = certificado.garantir(Path(pasta), ["localhost", "127.0.0.1"])
            interno = make_server("127.0.0.1", 0, _aplicacao)
            threading.Thread(target=interno.serve_forever, daemon=True).start()
            porta = _porta_livre()
            tunel_tls.em_segundo_plano(porta, ("127.0.0.1", interno.server_address[1]),
                                       arquivo, chave)
            _esperar(porta)
            try:
                with mock.patch.dict(os.environ, {
                        "STUDIO_CERTIFICADO_PASTA": pasta,
                        "STUDIO_PORTA_HTTPS": str(porta)}):
                    resultado = https.conferir(tempo_limite=2.0, endereco_rede="127.0.0.1")
            finally:
                interno.shutdown()
        # 127.0.0.1 não é endereço de rede: o teste da rede é pulado, sem inventar erro.
        self.assertEqual(resultado.nivel, "bom")
        self.assertEqual(resultado.endereco_rede, "")

    def test_localhost_nao_vira_teste_de_rede(self):
        with mock.patch.object(https, "_atende") as atende:
            with mock.patch.dict(os.environ, {"STUDIO_PORTA_HTTPS": str(_porta_livre())}):
                https.conferir(tempo_limite=0.2, endereco_rede="localhost")
        atende.assert_not_called()


@override_settings(ALLOWED_HOSTS=["192.168.3.254", "localhost", "testserver"])
class TestTelaMostraAFalhaDoTunel(TestCase):
    def setUp(self):
        usuario("gerente-falha-https", ADMINISTRACAO)
        self.client.login(username="gerente-falha-https", password=SENHA_TESTE)

    def test_o_cartao_com_o_motivo_aparece_quando_a_porta_nao_esta_de_pe(self):
        with tempfile.TemporaryDirectory() as pasta:
            with mock.patch.dict(os.environ, {
                    "STUDIO_CERTIFICADO_PASTA": pasta,
                    "STUDIO_PORTA_HTTPS": str(_porta_livre())}):
                https.registrar_falha("PermissionError: [Errno 13] config\\certificado")
                resposta = self.client.get(reverse("core:certificado"),
                                           HTTP_HOST="192.168.3.254:8095")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "O que o servidor registrou na última tentativa")
        self.assertContains(resposta, "PermissionError")
