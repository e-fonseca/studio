r"""O backup do SET do Studio, no servidor da loja (2.3.0).

Pedido do Edson em 06/11/2026: *"conectar na base backup do servidor 192.168.3.254
C:\backup-Set\Studio\Set-Studio utilizar sempre a ultima versão do backup"*.

Até a 2.2.0 o caminho só existia na documentação, e o código esperava o instalador escrever
STUDIO_SET_BACKUP no studio.env: sem ele, a importação dizia "não sei onde está o backup do
SET". Agora o servidor (config.settings.homolog, que herda de prod) já nasce olhando a pasta
do Studio, e "sempre a última versão" é a regra que a importação já tinha para pasta: o
arquivo mais novo com conteúdo, inclusive em subpastas por data (LocalizarBackupTest, em
test_importacao.py, cobre essa parte).
"""

import importlib
import os
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from apps.core import pastas
from apps.importacao import conferencia
from apps.importacao.fontes.firebird import preparar_copia


def origem_no_servidor(**ambiente):
    """O IMPORTACAO_BACKUP_ORIGEM que o servidor da loja teria com este ambiente."""
    with mock.patch.dict(os.environ, ambiente):
        if "STUDIO_SET_BACKUP" not in ambiente:
            os.environ.pop("STUDIO_SET_BACKUP", None)
        import config.settings.homolog as homolog
        import config.settings.prod as prod

        importlib.reload(prod)
        return importlib.reload(homolog).IMPORTACAO_BACKUP_ORIGEM


class BackupDoSetDoStudioTest(SimpleTestCase):
    def test_sem_nada_no_studio_env_o_servidor_le_a_pasta_do_studio(self):
        self.assertEqual(origem_no_servidor(), r"C:\backup-Set\Studio\Set-Studio")

    def test_linha_vazia_no_studio_env_nao_desliga_a_importacao(self):
        self.assertEqual(origem_no_servidor(STUDIO_SET_BACKUP=""), pastas.BACKUP_SET)

    def test_studio_set_backup_preenchido_continua_mandando(self):
        self.assertEqual(origem_no_servidor(STUDIO_SET_BACKUP=r"D:\outro\lugar"), r"D:\outro\lugar")

    def test_e_a_pasta_e_nao_um_arquivo_para_valer_sempre_o_mais_novo(self):
        """Um arquivo fixo seria lido para sempre, mesmo com backup novo do lado."""
        self.assertEqual(os.path.splitext(pastas.BACKUP_SET)[1], "")

    def test_nunca_a_pasta_da_cabana(self):
        self.assertIn("\\Studio\\", pastas.BACKUP_SET)
        self.assertFalse(pastas.BACKUP_SET.lower().startswith(pastas.BACKUP_SET_DA_CABANA.lower()))

    def test_a_documentacao_diz_a_mesma_pasta(self):
        from pathlib import Path

        doc = (Path(__file__).resolve().parents[3] / "docs" / "studio.md").read_text(encoding="utf-8")
        self.assertIn(f"`{pastas.BACKUP_SET}`", doc)


class ComoEstaNoServidorTest(SimpleTestCase):
    r"""A pasta do jeito que o Edson mostrou no print de 06/11/2026: em
    C:\backup-Set\Studio\Set-Studio, só o Set-Studio001.zip (103.973 KB, gravado às 23:00).

    Pedido do mesmo dia: *"usar a mesma estrutura de importação da base de dados backup do
    set sistemas da empresa Cabana do Jacarandá"*. É a mesma: o localizar_backup, o conferir
    e o preparar_copia que leem o Set-Cabana-FULL.zip da Cabana (BackupCompactadoTest, em
    test_importacao.py) leem este, e só a pasta muda. O nome do banco lá dentro não importa:
    vale o maior .FDB ou .FBK do zip.
    """

    def setUp(self):
        self.raiz = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.pasta = self.raiz / "backup-Set" / "Studio" / "Set-Studio"
        self.pasta.mkdir(parents=True)
        hoje = timezone.localdate()
        self.ontem_23h = timezone.make_aware(datetime.combine(hoje - timedelta(days=1), datetime.min.time())) \
            + timedelta(hours=23)

    def backup(self, nome, banco, quando):
        arquivo = self.pasta / nome
        with zipfile.ZipFile(arquivo, "w") as pacote:
            pacote.writestr("DADOS-SET.FDB", banco)
        os.utime(arquivo, (quando.timestamp(), quando.timestamp()))
        return arquivo

    def test_acha_o_set_studio001_confere_e_tira_o_banco_de_dentro(self):
        arquivo = self.backup("Set-Studio001.zip", b"banco do studio", self.ontem_23h)
        with override_settings(IMPORTACAO_BACKUP_ORIGEM=str(self.pasta)):
            achado = conferencia.localizar_backup()
            conferido = conferencia.conferir(agora=self.ontem_23h + timedelta(hours=9, minutes=30))
        self.assertEqual(achado, arquivo)
        self.assertEqual(conferido.nome, "Set-Studio001.zip")
        self.assertFalse(conferido.impedido, [m.texto for m in conferido.motivos])

        copia = preparar_copia(achado, self.raiz / "dados" / "copia-set")
        self.assertEqual(copia, self.raiz / "dados" / "copia-set" / "set.fdb")
        self.assertEqual(copia.read_bytes(), b"banco do studio")
        self.assertTrue(arquivo.is_file(), "a origem é só lida: o zip do SET continua lá")

    def test_o_zip_da_noite_seguinte_passa_na_frente(self):
        """Sempre a última versão do backup, venha com outro número ou por cima do mesmo."""
        self.backup("Set-Studio001.zip", b"de anteontem", self.ontem_23h - timedelta(days=1))
        novo = self.backup("Set-Studio002.zip", b"de ontem", self.ontem_23h)
        with override_settings(IMPORTACAO_BACKUP_ORIGEM=str(self.pasta)):
            self.assertEqual(conferencia.localizar_backup(), novo)

    def test_zip_ainda_sendo_gravado_fica_para_depois(self):
        """Às 23:00 o SET começa a gravar: o zip vazio da noite não passa na frente do de ontem."""
        de_ontem = self.backup("Set-Studio001.zip", b"de ontem", self.ontem_23h)
        gravando = self.pasta / "Set-Studio002.zip"
        gravando.touch()
        with override_settings(IMPORTACAO_BACKUP_ORIGEM=str(self.pasta)):
            self.assertEqual(conferencia.localizar_backup(), de_ontem)
