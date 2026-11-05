"""Histórico das atualizações aplicadas no servidor, para ver na tela.

Cada vez que o `instalar.ps1` termina, ele acrescenta uma linha num arquivo de
texto (uma coluna separada por tabulação), em `C:\\studio-sistema\\logs`:

    2026-10-06T23:40:11   1.7.0   ff59648   studio-sistema-pacote-1.7.0-...zip   ok

Assim a gerência vê na tela qual pacote entrou, quando e se deu certo, sem
precisar abrir log nenhum no servidor. O que mudou em cada versão vem do
`docs/mudancas.md`, que viaja dentro do pacote.
"""

from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings

COLUNAS = 5
SEPARADOR = "\t"


@dataclass(frozen=True)
class Aplicacao:
    """Uma atualização aplicada no servidor."""

    quando: str
    numero: str
    commit: str = ""
    pacote: str = ""
    resultado: str = "ok"

    @property
    def deu_certo(self):
        return self.resultado.lower().startswith("ok")


@dataclass
class Mudanca:
    """O que entrou numa versão, como está escrito em docs/mudancas.md."""

    numero: str
    data: str = ""
    itens: list = field(default_factory=list)


def _caminho_historico():
    return Path(getattr(settings, "ATUALIZACOES_HISTORICO", "") or "")


def historico(limite=30):
    """Lê o arquivo de histórico, da atualização mais nova para a mais antiga.

    Linha estranha é ignorada em silêncio: um histórico com defeito não pode
    derrubar a tela nem esconder as linhas boas.
    """
    caminho = _caminho_historico()
    if not caminho or not caminho.exists():
        return []
    aplicacoes = []
    for linha in caminho.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        campos = [campo.strip() for campo in linha.split(SEPARADOR)]
        if len(campos) < 2 or not campos[0] or not campos[1]:
            continue
        campos = (campos + [""] * COLUNAS)[:COLUNAS]
        aplicacoes.append(Aplicacao(*campos[:4], resultado=campos[4] or "ok"))
    return list(reversed(aplicacoes))[:limite]


def mudancas(limite=12):
    """Lê docs/mudancas.md e devolve uma lista por versão, da mais nova para a mais antiga."""
    caminho = Path(settings.BASE_DIR) / "docs" / "mudancas.md"
    try:
        texto = caminho.read_text(encoding="utf-8")
    except OSError:
        return []
    lista = []
    for linha in texto.splitlines():
        if linha.startswith("## "):
            titulo = linha[3:].strip()
            numero, _, data = titulo.partition("—")
            lista.append(Mudanca(numero=numero.strip(), data=data.strip()))
            continue
        if not lista:
            continue
        if linha.startswith("- "):
            lista[-1].itens.append(_sem_marcacao(linha[2:].strip()))
        elif linha.startswith("  ") and linha.strip() and lista[-1].itens:
            # Continuação do item anterior, que no arquivo é quebrado em várias linhas.
            lista[-1].itens[-1] += " " + _sem_marcacao(linha.strip())
    return lista[:limite]


def _sem_marcacao(texto):
    """Tira o negrito e o código do markdown: a tela mostra texto corrido."""
    return texto.replace("**", "").replace("`", "")
