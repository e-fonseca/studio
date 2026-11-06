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
from unittest import mock

from django.test import SimpleTestCase

from apps.core import pastas


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
