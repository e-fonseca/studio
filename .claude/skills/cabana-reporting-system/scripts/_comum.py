"""Liga o Django para os scripts de conferência. Nada aqui grava no banco.

Rodar da raiz do repositório, com as variáveis STUDIO_* do ambiente (ver .env.exemplo).
No servidor da loja, o studio.env já as tem; numa máquina de desenvolvimento, exportar
antes de chamar.
"""

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[4]


def _parar(titulo_do_erro, *o_que_fazer):
    """Explica o problema em português e sai, em vez de despejar um traceback.

    Estes scripts são a ferramenta de quem confere o sistema, e as duas falhas mais
    comuns são o banco parado e as variáveis não exportadas. Em 11/10/2026 as duas
    saíam como quarenta linhas de Python, que não dizem o que fazer a ninguém.
    """
    print()
    print(titulo_do_erro)
    for passo in o_que_fazer:
        print(f"  - {passo}")
    print()
    raise SystemExit(2)


def ligar():
    """Prepara o Django e devolve a raiz do projeto."""
    import django

    sys.path.insert(0, str(RAIZ))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    try:
        django.setup()
    except Exception as erro:  # noqa: BLE001
        _parar(
            f"Não consegui ligar o sistema: {erro}",
            "Rode da raiz do repositório (a pasta que tem o manage.py).",
            "Confira as variáveis STUDIO_* do ambiente — veja o .env.exemplo.",
        )
    _conferir_banco()
    return RAIZ


def _conferir_banco():
    """Pergunta ao banco se ele está no ar, antes de qualquer consulta."""
    from django.db import OperationalError, connection

    try:
        connection.cursor().execute("SELECT 1")
    except OperationalError as erro:
        primeira = str(erro).strip().splitlines()[0]
        _parar(
            f"O banco de dados não respondeu: {primeira}",
            "No servidor da loja: confira se o serviço do PostgreSQL está rodando.",
            "Confira STUDIO_DB_HOST, STUDIO_DB_PORTA, STUDIO_DB_USUARIO e STUDIO_DB_NOME.",
            "Isto não é defeito do sistema nem da importação: é o banco fora do ar.",
        )
    except Exception as erro:  # noqa: BLE001
        _parar(f"Não consegui falar com o banco: {erro}")


def titulo(texto):
    print()
    print(texto)
    print("-" * len(texto))


def linha(rotulo, valor):
    print(f"  {rotulo}: {valor}")


class Placar:
    """Conta o que passou e o que não passou, e decide o código de saída."""

    def __init__(self):
        self.falhas = []

    def conferir(self, condicao, descricao, detalhe=""):
        marca = "ok  " if condicao else "FALHA"
        print(f"  [{marca}] {descricao}" + (f" — {detalhe}" if detalhe else ""))
        if not condicao:
            self.falhas.append(descricao)
        return condicao

    def avisar(self, descricao, detalhe=""):
        print(f"  [aviso] {descricao}" + (f" — {detalhe}" if detalhe else ""))

    def fechar(self):
        print()
        if self.falhas:
            print(f"{len(self.falhas)} conferência(s) falharam:")
            for falha in self.falhas:
                print(f"  - {falha}")
            return 1
        print("Tudo conferido.")
        return 0


def reais(valor):
    texto = f"{(valor or 0):,.2f}"
    return "R$ " + texto.replace(",", "·").replace(".", ",").replace("·", ".")
