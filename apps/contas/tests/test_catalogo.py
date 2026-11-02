"""O catálogo de permissões amarrado ao código (1.44.0).

Pedido do prompt de controle de acesso (02/11/2026): "Não criar permissões sem aplicação
efetiva no backend." E o outro lado: permissão conferida por alguma tela e que não está no
catálogo não aparece na matriz, e a gerência não teria como dá-la nem tirá-la.

Os dois testes leem o código-fonte, e não uma lista digitada aqui: tela nova que confere
permissão nova entra na conferência no dia em que nasce.
"""

import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import Permission
from django.test import TestCase

from apps.contas import catalogo
from apps.contas.perfis import PADRAO

RAIZ = Path(settings.BASE_DIR)
# Onde o catálogo é DEFINIDO, e não conferido: não conta como uso.
DEFINICOES = {"apps/contas/catalogo.py", "apps/contas/perfis.py"}
TEXTO_DE_PERMISSAO = re.compile(r"""["']([a-z_]+)\.([a-z_]+)["']""")
NO_TEMPLATE = re.compile(r"perms\.([a-z_]+)\.([a-z_]+)")


def _existentes():
    return {f"{p.content_type.app_label}.{p.codename}"
            for p in Permission.objects.select_related("content_type")}


def _usadas():
    """Toda permissão que aparece no código das telas (fora testes, migrações e o catálogo)."""
    existentes = _existentes()
    achadas = set()
    for arquivo in (RAIZ / "apps").rglob("*.py"):
        relativo = arquivo.relative_to(RAIZ).as_posix()
        if "/tests/" in relativo or "/migrations/" in relativo or relativo in DEFINICOES:
            continue
        for app, codigo in TEXTO_DE_PERMISSAO.findall(arquivo.read_text(encoding="utf-8")):
            if f"{app}.{codigo}" in existentes:
                achadas.add(f"{app}.{codigo}")
    for arquivo in (RAIZ / "templates").rglob("*.html"):
        for app, codigo in NO_TEMPLATE.findall(arquivo.read_text(encoding="utf-8")):
            achadas.add(f"{app}.{codigo}")
    return achadas


class CatalogoTest(TestCase):
    def test_toda_permissao_do_catalogo_existe_no_banco(self):
        faltam = set(catalogo.CODIGOS) - _existentes()
        self.assertEqual(faltam, set(), "permissão no catálogo sem migração que a crie")

    def test_toda_permissao_conferida_pelas_telas_esta_no_catalogo(self):
        fora = _usadas() - set(catalogo.CODIGOS)
        self.assertEqual(fora, set(), "estas permissões protegem alguma tela e a gerência não "
                                      "as vê na matriz: entrem no catálogo")

    def test_toda_permissao_do_catalogo_protege_alguma_coisa(self):
        sem_uso = set(catalogo.CODIGOS) - _usadas()
        self.assertEqual(sem_uso, set(), "permissão que nenhuma tela confere não protege nada")

    def test_codigos_unicos_e_modulos_conhecidos(self):
        self.assertEqual(len(catalogo.CODIGOS), len(catalogo.CATALOGO))
        for permissao in catalogo.CATALOGO:
            self.assertIn(permissao.modulo, catalogo.MODULOS, permissao.codigo)
            self.assertTrue(permissao.nome and permissao.abre, permissao.codigo)

    def test_o_padrao_de_cada_perfil_so_usa_o_catalogo(self):
        for nome, codigos in PADRAO.items():
            self.assertEqual(set(codigos) - set(catalogo.CODIGOS), set(), nome)

    def test_o_vendedor_nao_tem_nada_de_dinheiro(self):
        """A condição do Edson desde o começo, agora escrita contra as marcas do catálogo."""
        from apps.contas.perfis import VENDEDOR  # noqa: PLC0415

        self.assertEqual(set(PADRAO[VENDEDOR]) & catalogo.MARCADAS, set())

    def test_quem_so_administra_pessoas_nao_ve_dinheiro(self):
        from apps.contas.perfis import ADMIN_ACESSOS  # noqa: PLC0415

        dinheiro = {p.codigo for p in catalogo.CATALOGO if p.dinheiro}
        self.assertEqual(set(PADRAO[ADMIN_ACESSOS]) & dinheiro, set())
