"""O Studio nunca abre o banco da Cabana (2.4.1).

O PostgreSQL do servidor da loja guarda as duas empresas. Da cópia veio o padrão "cabana" no
nome do banco: um studio.env sem STUDIO_DB_NOME faria o Studio migrar e gravar no da Cabana.
"""

import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

RAIZ = Path(__file__).resolve().parents[3]


def carregar_prod(modulo="config.settings.prod", **variaveis):
    """Importa config.settings.prod num processo limpo e devolve (código, saída)."""
    ambiente = {k: v for k, v in os.environ.items() if not k.startswith("STUDIO_")}
    ambiente.update({
        "STUDIO_SECRET_KEY": "chave-somente-para-testes",
        "STUDIO_ENV_ARQUIVO": str(RAIZ / "nao-existe.env"),
        "DJANGO_SETTINGS_MODULE": modulo,
    })
    ambiente.update(variaveis)
    codigo = (
        "import django; from django.conf import settings; django.setup();"
        "print(settings.DATABASES['default']['NAME'])"
    )
    feito = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, env=ambiente,
                           capture_output=True, text=True, timeout=120)
    return feito.returncode, feito.stdout + feito.stderr


class BancoDoStudioTest(SimpleTestCase):
    def test_o_padrao_fora_da_producao_e_studio_e_nao_cabana(self):
        from config.settings import base

        fonte = Path(base.__file__).read_text(encoding="utf-8")
        self.assertIn('env("STUDIO_DB_NOME", "studio")', fonte)
        self.assertIn('env("STUDIO_DB_USUARIO", "studio")', fonte)
        self.assertNotIn('"cabana")', fonte)

    def test_em_producao_sem_o_nome_do_banco_o_servico_nao_sobe(self):
        codigo, saida = carregar_prod(STUDIO_DB_USUARIO="studio")
        self.assertNotEqual(codigo, 0, saida)
        self.assertIn("STUDIO_DB_NOME", saida)

    def test_em_producao_o_banco_da_cabana_e_recusado(self):
        for nome in ("cabana", "Cabana", " cabana "):
            with self.subTest(nome=nome):
                codigo, saida = carregar_prod(STUDIO_DB_NOME=nome, STUDIO_DB_USUARIO="studio")
                self.assertNotEqual(codigo, 0, saida)
                self.assertIn("banco da Cabana", saida)

    def test_em_producao_com_o_banco_do_studio_sobe(self):
        codigo, saida = carregar_prod(STUDIO_DB_NOME="studio", STUDIO_DB_USUARIO="studio")
        self.assertEqual(codigo, 0, saida)
        self.assertEqual(saida.strip().splitlines()[-1], "studio")

    def test_a_homologacao_que_o_servir_py_usa_tambem_recusa(self):
        """O servir.py sobe em config.settings.homolog, que herda a trava de prod.py."""
        codigo, saida = carregar_prod("config.settings.homolog",
                                      STUDIO_DB_NOME="cabana", STUDIO_DB_USUARIO="studio")
        self.assertNotEqual(codigo, 0, saida)
        self.assertIn("banco da Cabana", saida)
