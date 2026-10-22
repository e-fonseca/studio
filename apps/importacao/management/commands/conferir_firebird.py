"""Confere o motor Firebird que lê a cópia do backup do SET.

A importação só começa depois de carregar o `fbclient.dll` próprio do sistema. Quando
esse carregamento falha, o erro que o Windows devolve é críptico ("[WinError 193] %1 não
é um aplicativo Win32 válido", "[WinError 126] módulo não encontrado") e não diz qual
arquivo está faltando. Este comando confere peça por peça e escreve em português o que
está certo e o que falta, para a conferência aparecer já na instalação.
"""

import ctypes
import sys
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.importacao.fontes.firebird import _arquitetura_do_pe

# Peças que o motor embutido precisa ter ao lado do fbclient.dll.
ACOMPANHAMENTOS = [
    ("plugins/engine13.dll", "o motor que abre o arquivo do banco"),
    ("firebird.msg", "as mensagens de erro do Firebird"),
    ("intl/fbintl.dll", "o tratamento de acentuação"),
]


class Command(BaseCommand):
    help = "Confere se o motor Firebird do sistema consegue ser carregado."

    def add_arguments(self, parser):
        parser.add_argument("--falhar", action="store_true",
                            help="Termina com erro quando o motor não serve (usado pelo instalador).")

    def handle(self, *args, **opcoes):
        problemas = []
        caminho = str(getattr(settings, "IMPORTACAO_FIREBIRD_CLIENTE", "") or "")
        if not caminho:
            problemas.append("O sistema não sabe onde está o motor: CABANA_FIREBIRD_DLL está vazio no cabana.env.")
            return self._terminar(problemas, opcoes)

        arquivo = Path(caminho)
        self.stdout.write(f"Motor Firebird: {arquivo}")
        if not arquivo.exists():
            problemas.append(f"O arquivo {arquivo} não existe. Rode a atualização de novo para montar o motor.")
            return self._terminar(problemas, opcoes)

        bits = 64 if sys.maxsize > 2**32 else 32
        arquitetura = _arquitetura_do_pe(arquivo)
        if arquitetura:
            self.stdout.write(f"Arquitetura: {arquitetura} (o sistema é de {bits} bits)")
            if arquitetura != f"{bits} bits":
                problemas.append(
                    f"O motor é de {arquitetura} e o sistema é de {bits} bits; o Windows não carrega um "
                    "dentro do outro. A atualização troca o motor por um de 64 bits."
                )

        for relativo, para_que in ACOMPANHAMENTOS:
            if not (arquivo.parent / relativo).exists():
                problemas.append(f"Falta {relativo} na pasta do motor ({para_que}).")

        try:
            ctypes.CDLL(str(arquivo))
            self.stdout.write("O Windows carregou o motor.")
        except OSError as erro:
            problemas.append(f"O Windows recusou carregar o motor: {erro}")

        return self._terminar(problemas, opcoes)

    def _terminar(self, problemas, opcoes):
        if not problemas:
            self.stdout.write("Motor Firebird conferido: a importação consegue abrir a cópia do banco.")
            return
        self.stdout.write("O MOTOR FIREBIRD NÃO ESTÁ PRONTO:")
        for problema in problemas:
            self.stdout.write(f"  - {problema}")
        if opcoes["falhar"]:
            raise SystemExit(1)
