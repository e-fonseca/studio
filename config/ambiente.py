"""Carrega as variáveis CABANA_* de um arquivo fora do código (instalação no servidor).

No servidor, o instalador grava C:\\cabana-sistema\\config\\cabana.env, legível só por
administradores e pela conta do serviço. Em desenvolvimento o arquivo não existe e nada muda.
Variáveis já definidas no ambiente têm prioridade sobre o arquivo.
"""

import os
from pathlib import Path

PADRAO = Path(__file__).resolve().parent.parent.parent / "config" / "cabana.env"


def carregar(caminho=None):
    arquivo = Path(caminho or os.environ.get("CABANA_ENV_ARQUIVO") or PADRAO)
    if not arquivo.is_file():
        return False
    for linha in arquivo.read_text(encoding="utf-8-sig").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        nome, valor = linha.split("=", 1)
        os.environ.setdefault(nome.strip(), valor.strip())
    return True
