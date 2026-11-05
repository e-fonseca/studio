"""Conferir o backup antes de ler, e forçar a leitura do mais recente.

Pedido do Edson em 10/10/2026: um botão para forçar a atualização com o último
backup e, antes de importar, conferir o tamanho, para avaliar a integridade, e a
data, para ter certeza de que é mesmo o backup mais recente -- com muito cuidado
para não somar informação, sempre sincronizar.

A parte do "não soma" está em test_comparacao.py, que é onde a prova vive; aqui
ficam a conferência, a decisão de deixar ou não importar e os dois botões.
"""

import os
import tempfile
from datetime import timedelta
from pathlib import Path

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.importacao import conferencia as conferencia_servicos
from apps.importacao import servicos
from apps.importacao.models import Importacao

UM_MEGA = 1024 * 1024


def _versao_de_agora():
    from apps.core import versao

    return versao.atual().curta[:40]


def _arquivo(pasta, nome="Set-Cabana-FULL.zip", tamanho=2 * UM_MEGA, dias_atras=0):
    """Backup de mentira: só precisa ter tamanho e data, porque é só isso que a conferência olha."""
    caminho = Path(pasta) / nome
    caminho.write_bytes(b"x" * tamanho)
    if dias_atras:
        quando = (timezone.now() - timedelta(days=dias_atras)).timestamp()
        os.utime(caminho, (quando, quando))
    return caminho


def _anterior(caminho=None, bytes_=2 * UM_MEGA, **extra):
    """A última importação concluída, que é a régua do tamanho e da data."""
    agora = timezone.now()
    dados = {
        "origem": Importacao.Origem.BANCO,
        "situacao": Importacao.Situacao.CONCLUIDA,
        "iniciada_em": agora - timedelta(days=1),
        "concluida_em": agora - timedelta(days=1),
        "data_corte": timezone.localdate() - timedelta(days=1),
        "produtos": 2,
        "arquivo_bytes": bytes_,
    }
    if caminho is not None:
        dados["arquivo"] = str(caminho)
        dados["arquivo_modificado_em"] = conferencia_servicos.momento_do_arquivo(caminho)
        dados["arquivo_bytes"] = Path(caminho).stat().st_size
    dados.update(extra)
    return Importacao.objects.create(**dados)


class ConferirTest(TestCase):
    def test_sem_pasta_configurada_diz_o_que_falta(self):
        with override_settings(IMPORTACAO_BACKUP_ORIGEM=""):
            resultado = conferencia_servicos.conferir()
        self.assertTrue(resultado.quebrado)
        self.assertFalse(resultado.achou)
        self.assertIn("STUDIO_SET_BACKUP", resultado.motivos[0].texto)

    def test_pasta_sem_backup_nenhum(self):
        with tempfile.TemporaryDirectory() as pasta:
            resultado = conferencia_servicos.conferir(pasta)
        self.assertTrue(resultado.quebrado)
        self.assertIn("não achei nenhum arquivo", resultado.motivos[0].texto)

    def test_arquivo_vazio_e_gravacao_que_nao_terminou(self):
        with tempfile.TemporaryDirectory() as pasta:
            _arquivo(pasta, tamanho=0)
            resultado = conferencia_servicos.conferir(pasta)
        self.assertTrue(resultado.quebrado)
        self.assertIn("está vazio", resultado.motivos[0].texto)

    def test_backup_de_hoje_passa_sem_ressalva(self):
        with tempfile.TemporaryDirectory() as pasta:
            _arquivo(pasta)
            resultado = conferencia_servicos.conferir(pasta)
        self.assertEqual(resultado.nivel, "ok")
        self.assertTrue(resultado.pode_importar())
        self.assertEqual(resultado.motivos, [])
        self.assertEqual(resultado.tamanho, "2,0 MB")
        self.assertIn("pronto para importar", resultado.titulo)

    def test_arquivo_pequeno_nao_tem_tamanho_de_backup(self):
        """O caso real: a importação roda enquanto o backup está sendo gravado."""
        with tempfile.TemporaryDirectory() as pasta:
            _arquivo(pasta, tamanho=800)
            with override_settings(IMPORTACAO_BACKUP_MINIMO_BYTES=UM_MEGA):
                resultado = conferencia_servicos.conferir(pasta)
        self.assertTrue(resultado.quebrado)
        self.assertIn("800 bytes", resultado.motivos[0].texto)
        self.assertFalse(resultado.pode_importar(), "importação normal não lê arquivo quebrado")
        self.assertFalse(resultado.pode_importar(forcar=True), "forçar também não lê arquivo quebrado")

    def test_arquivo_quebrado_nao_repete_o_motivo_do_tamanho(self):
        """Encolheu e não tem tamanho de backup é o mesmo assunto: um motivo basta."""
        with tempfile.TemporaryDirectory() as pasta:
            caminho = _arquivo(pasta, tamanho=800)
            _anterior(bytes_=4 * UM_MEGA)
            with override_settings(IMPORTACAO_BACKUP_MINIMO_BYTES=UM_MEGA):
                resultado = conferencia_servicos.conferir(caminho, anterior=servicos.ultima_concluida())
        self.assertEqual(len(resultado.impedimentos), 1)
        self.assertIn("800 bytes", resultado.impedimentos[0].texto)

    def test_arquivo_que_encolheu_muito_impede_e_forcar_passa(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = _arquivo(pasta, tamanho=UM_MEGA)
            _anterior(bytes_=4 * UM_MEGA)
            resultado = conferencia_servicos.conferir(caminho, anterior=servicos.ultima_concluida())
        self.assertTrue(resultado.impedido)
        self.assertFalse(resultado.quebrado)
        self.assertIn("encolheu 75%", resultado.impedimentos[0].texto)
        self.assertFalse(resultado.pode_importar())
        self.assertTrue(resultado.pode_importar(forcar=True), "é o que o botão de forçar resolve")

    def test_encolhida_pequena_so_avisa(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = _arquivo(pasta, tamanho=9 * UM_MEGA)
            _anterior(bytes_=10 * UM_MEGA)
            resultado = conferencia_servicos.conferir(caminho, anterior=servicos.ultima_concluida())
        self.assertEqual(resultado.nivel, "atencao")
        self.assertTrue(resultado.pode_importar())
        self.assertIn("encolheu 10%", resultado.avisos[0].texto)

    def test_backup_de_dias_atras_avisa_que_pode_nao_ter_rodado(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = _arquivo(pasta, dias_atras=3)
            resultado = conferencia_servicos.conferir(caminho)
        self.assertEqual(resultado.nivel, "atencao")
        self.assertTrue(resultado.pode_importar())
        self.assertIn("3 dias atrás", resultado.avisos[0].texto)

    def test_arquivo_mais_antigo_que_o_ja_importado_avisa(self):
        """Backup restaurado de uma cópia velha ou pasta trocada: importar volta no tempo."""
        with tempfile.TemporaryDirectory() as pasta:
            caminho = _arquivo(pasta, nome="DADOS-SET.FDB", dias_atras=5)
            _anterior(bytes_=2 * UM_MEGA, arquivo="C:\\backup\\outro.zip",
                      arquivo_modificado_em=timezone.now())
            resultado = conferencia_servicos.conferir(caminho, anterior=servicos.ultima_concluida())
        self.assertEqual(resultado.nivel, "atencao")
        self.assertTrue(any("mais antigo que o que já foi importado" in m.texto
                            for m in resultado.avisos))

    def test_o_mesmo_arquivo_da_anterior_e_so_uma_nota(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = _arquivo(pasta)
            _anterior(caminho=caminho)
            resultado = conferencia_servicos.conferir(caminho, anterior=servicos.ultima_concluida())
        self.assertTrue(resultado.mesmo_da_anterior)
        self.assertEqual(resultado.nivel, "ok")
        self.assertTrue(resultado.pode_importar())
        self.assertIn("Sem backup novo", resultado.notas[0].texto)

    def test_quando_o_mais_novo_da_pasta_esta_vazio_avisa_qual_vai_ler(self):
        """O zip de hoje começou a ser gravado: o de ontem é o que tem conteúdo."""
        with tempfile.TemporaryDirectory() as pasta:
            de_ontem = _arquivo(pasta, nome="Set-Cabana-FULL-01.zip", dias_atras=1)
            _arquivo(pasta, nome="Set-Cabana-FULL-02.zip", tamanho=0)
            resultado = conferencia_servicos.conferir(pasta)
        self.assertEqual(resultado.caminho, de_ontem)
        self.assertTrue(resultado.pode_importar())
        self.assertTrue(any("está vazio" in m.texto for m in resultado.avisos))

    def test_com_varios_arquivos_diz_que_pegou_o_mais_novo(self):
        with tempfile.TemporaryDirectory() as pasta:
            _arquivo(pasta, nome="Set-Cabana-FULL-01.zip", dias_atras=1)
            hoje = _arquivo(pasta, nome="Set-Cabana-FULL-02.zip")
            resultado = conferencia_servicos.conferir(pasta)
        self.assertEqual(resultado.caminho, hoje)
        self.assertEqual(resultado.nivel, "ok")
        self.assertIn("é o mais novo dos 2 arquivos", resultado.notas[0].texto)

    def test_a_conferencia_inteira_cabe_no_log(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = _arquivo(pasta)
            linhas = conferencia_servicos.conferir(caminho).linhas_para_log()
        self.assertTrue(linhas[0].startswith("Conferência do backup: Set-Cabana-FULL.zip, 2,0 MB"))
        self.assertIn("gravado em", linhas[0])


class ForcarImportacaoTest(TestCase):
    def test_sem_forcar_o_mesmo_backup_termina_sem_novidade(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = _arquivo(pasta, tamanho=2048)
            _anterior(caminho=caminho, versao_sistema=_versao_de_agora())
            resultado = servicos.executar(arquivo=str(caminho))
        self.assertEqual(resultado.situacao, Importacao.Situacao.SEM_NOVIDADE)

    def test_forcando_le_o_mesmo_backup_de_novo(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = _arquivo(pasta, tamanho=2048)
            _anterior(caminho=caminho, versao_sistema=_versao_de_agora())
            resultado = servicos.executar(arquivo=str(caminho), forcar=True)
        # Não pulou: foi ler. Para no Firebird porque o arquivo é de mentira, e o que este
        # teste trava é a decisão de reler, não a leitura.
        self.assertNotEqual(resultado.situacao, Importacao.Situacao.SEM_NOVIDADE)
        self.assertTrue(resultado.forcada)
        self.assertTrue(any("Forçada:" in linha for linha in resultado.linhas_do_log))
        self.assertTrue(any("sincroniza, não soma" in linha for linha in resultado.linhas_do_log))

    def test_forcar_nao_le_arquivo_quebrado(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = _arquivo(pasta, tamanho=500)
            with override_settings(IMPORTACAO_BACKUP_MINIMO_BYTES=UM_MEGA):
                resultado = servicos.executar(arquivo=str(caminho), forcar=True)
        self.assertEqual(resultado.situacao, Importacao.Situacao.FALHOU)
        self.assertIn("não deixou importar", resultado.mensagem)
        self.assertIn("500 bytes", resultado.mensagem)

    def test_a_conferencia_fica_registrada_no_log_da_importacao(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = _arquivo(pasta, tamanho=2048)
            resultado = servicos.executar(arquivo=str(caminho))
        self.assertTrue(any("Conferência do backup:" in linha for linha in resultado.linhas_do_log))

    def test_o_comando_aceita_forcar(self):
        from django.core.management import call_command

        with tempfile.TemporaryDirectory() as pasta:
            caminho = _arquivo(pasta, tamanho=2048)
            _anterior(caminho=caminho, versao_sistema=_versao_de_agora())
            try:
                call_command("importar_set", "--arquivo", str(caminho), "--forcar", "--sem-log")
            except Exception:  # noqa: BLE001 - para na leitura do arquivo de mentira, e tudo bem
                pass
        self.assertTrue(Importacao.objects.filter(forcada=True).exists())


class TelaDaConferenciaTest(TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.caminho = _arquivo(self.pasta.name)

    def _entrar(self, perfil=ADMINISTRACAO, nome="edson"):
        usuario(nome, perfil)
        self.client.login(username=nome, password=SENHA_TESTE)

    def test_o_quadro_mostra_o_arquivo_o_tamanho_e_a_data(self):
        self._entrar()
        with override_settings(IMPORTACAO_BACKUP_ORIGEM=self.pasta.name):
            pagina = self.client.get(reverse("importacao:historico"))
        self.assertContains(pagina, "Set-Cabana-FULL.zip")
        self.assertContains(pagina, "2,0 MB")
        self.assertContains(pagina, "Gravado em")
        self.assertContains(pagina, "Backup conferido e pronto para importar")

    def test_quem_pode_importar_ve_os_dois_botoes(self):
        self._entrar()
        with override_settings(IMPORTACAO_BACKUP_ORIGEM=self.pasta.name):
            pagina = self.client.get(reverse("importacao:historico"))
        self.assertContains(pagina, "Importar agora")
        self.assertContains(pagina, "Forçar atualização com o último backup")
        self.assertContains(pagina, 'name="forcar"')

    def test_quem_so_consulta_nao_ve_botao_de_importar(self):
        self._entrar(ADMINISTRATIVO, "fiscal")
        with override_settings(IMPORTACAO_BACKUP_ORIGEM=self.pasta.name):
            pagina = self.client.get(reverse("importacao:historico"))
        self.assertNotContains(pagina, 'name="forcar"')

    def test_arquivo_quebrado_esconde_o_botao_de_forcar(self):
        """Forçar manda ler de novo; com arquivo quebrado isso trocaria número bom por ruim."""
        self._entrar()
        with override_settings(IMPORTACAO_BACKUP_ORIGEM=self.pasta.name,
                               IMPORTACAO_BACKUP_MINIMO_BYTES=10 * UM_MEGA):
            pagina = self.client.get(reverse("importacao:historico"))
        self.assertContains(pagina, "não tem tamanho de backup")
        self.assertNotContains(pagina, 'name="forcar"')

    def test_forcar_pela_tela_dispara_a_importacao_forcada(self):
        self._entrar()
        chamadas = []
        original = servicos.executar_em_segundo_plano
        servicos.executar_em_segundo_plano = lambda **kwargs: chamadas.append(kwargs)
        try:
            with override_settings(IMPORTACAO_BACKUP_ORIGEM=self.pasta.name):
                resposta = self.client.post(
                    reverse("importacao:importar"),
                    {"forcar": "1", "voltar": "importacoes"},
                    follow=True,
                )
        finally:
            servicos.executar_em_segundo_plano = original
        self.assertEqual(len(chamadas), 1)
        self.assertTrue(chamadas[0]["forcar"])
        self.assertContains(resposta, "Importação forçada")
        self.assertContains(resposta, "Importações", msg_prefix="volta para a tela de onde veio")

    def test_importar_sem_forcar_continua_sendo_o_caminho_normal(self):
        self._entrar()
        chamadas = []
        original = servicos.executar_em_segundo_plano
        servicos.executar_em_segundo_plano = lambda **kwargs: chamadas.append(kwargs)
        try:
            with override_settings(IMPORTACAO_BACKUP_ORIGEM=self.pasta.name):
                resposta = self.client.post(reverse("importacao:importar"), follow=True)
        finally:
            servicos.executar_em_segundo_plano = original
        self.assertFalse(chamadas[0]["forcar"])
        self.assertContains(resposta, "Importação iniciada")

    def test_quando_a_conferencia_impede_a_tela_diz_o_motivo_e_nao_importa(self):
        self._entrar()
        _anterior(bytes_=10 * UM_MEGA)
        chamadas = []
        original = servicos.executar_em_segundo_plano
        servicos.executar_em_segundo_plano = lambda **kwargs: chamadas.append(kwargs)
        try:
            with override_settings(IMPORTACAO_BACKUP_ORIGEM=self.pasta.name):
                resposta = self.client.post(reverse("importacao:importar"), follow=True)
        finally:
            servicos.executar_em_segundo_plano = original
        self.assertEqual(chamadas, [], "nada foi lido")
        self.assertContains(resposta, "Não importei")
        self.assertContains(resposta, "continuam valendo")
        self.assertEqual(Importacao.objects.filter(situacao=Importacao.Situacao.FALHOU).count(), 0,
                         "recusar na tela não registra importação falhada")
