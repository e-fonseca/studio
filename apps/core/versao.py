"""Versão do sistema, para saber na tela qual pacote está rodando no servidor.

O número fica no arquivo VERSAO da raiz, escrito à mão a cada entrega. O
montador do pacote acrescenta nesse mesmo arquivo o commit e a data da
geração, então o que está instalado no servidor sempre diz de onde veio:

    1.4.0
    commit=f0206f1
    data=2026-10-06

Numa cópia de desenvolvimento só existe a primeira linha, e aí o commit e a
data ficam vazios.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from django.conf import settings

ARQUIVO = "VERSAO"
DESCONHECIDA = "não informada"


@dataclass(frozen=True)
class Versao:
    numero: str
    commit: str = ""
    data: str = ""

    def __str__(self):
        if self.commit and self.data:
            return f"{self.numero} ({self.data}, {self.commit})"
        if self.commit:
            return f"{self.numero} ({self.commit})"
        return self.numero

    @property
    def curta(self):
        """O que vai no registro de cada importação: número e commit, sem a data."""
        return f"{self.numero}+{self.commit}" if self.commit else self.numero


def _ler(caminho):
    numero, commit, data = "", "", ""
    linhas = [linha.strip() for linha in caminho.read_text(encoding="utf-8-sig").splitlines()]
    for linha in linhas:
        if not linha:
            continue
        if linha.startswith("commit="):
            commit = linha.split("=", 1)[1].strip()
        elif linha.startswith("data="):
            data = linha.split("=", 1)[1].strip()
        elif not numero:
            numero = linha
    return Versao(numero=numero or DESCONHECIDA, commit=commit, data=data)


@lru_cache(maxsize=1)
def atual():
    """Lê o arquivo uma vez por processo: a versão não muda sem reiniciar o serviço."""
    caminho = Path(settings.BASE_DIR) / ARQUIVO
    try:
        return _ler(caminho)
    except OSError:
        return Versao(numero=DESCONHECIDA)
