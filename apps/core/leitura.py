"""Ler texto, número e data de arquivo que veio de fora.

O extrato do banco (apps/conciliacao) e a nota fiscal do fornecedor (apps/pedidos)
chegam dos mesmos lugares e com as mesmas manias: gravados em cp1252 por programa
antigo, com "1.234,56" numa linha e "1,234.56" na outra, e a data em cinco formatos.

Isto ficava dentro do leitor de extrato. Virou módulo próprio quando a leitura da
nota fiscal precisou das mesmas três funções: duas cópias de "entender 1.234,56"
viram, com o tempo, duas telas discordando sobre o mesmo arquivo.
"""

import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation

# A ordem importa: utf-8-sig tira a marca de ordem de byte que o Excel põe, e cp1252 é
# o que os programas antigos de Windows gravam.
CODIFICACOES = ("utf-8-sig", "cp1252", "latin-1")

FORMATOS_DE_DATA = ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y")


def texto(dados):
    """Decodifica o arquivo tentando as codificações que esses programas usam."""
    if isinstance(dados, str):
        return dados
    for codificacao in CODIFICACOES:
        try:
            return dados.decode(codificacao)
        except UnicodeDecodeError:
            continue
    return dados.decode("latin-1", "replace")


def sem_acento(valor):
    sem = unicodedata.normalize("NFKD", valor or "")
    return "".join(letra for letra in sem if not unicodedata.combining(letra))


def numero(bruto):
    """Entende 1.234,56 (brasileiro), 1,234.56 (americano), -50,00 e R$ 50.

    Devolve None quando não é número: quem chama decide se a linha é descartada ou se
    o campo fica vazio. Nada entra "mais ou menos certo" numa conta de dinheiro.
    """
    valor = (bruto or "").strip().replace("R$", "").replace(" ", "").replace("\xa0", "")
    if not valor:
        return None
    negativo = valor.startswith("-") or valor.endswith("-") or (
        valor.startswith("(") and valor.endswith(")"))
    valor = valor.strip("-()")
    if "," in valor and "." in valor:
        # O separador decimal é o último que aparece.
        if valor.rfind(",") > valor.rfind("."):
            valor = valor.replace(".", "").replace(",", ".")
        else:
            valor = valor.replace(",", "")
    elif "," in valor:
        valor = valor.replace(".", "").replace(",", ".")
    try:
        achado = Decimal(valor)
    except InvalidOperation:
        return None
    return -achado if negativo else achado


def data(bruto):
    """A data escrita como gente escreve: 20/09/2026, 2026-09-20, 20.09.2026."""
    valor = (bruto or "").strip()[:10]
    for formato in FORMATOS_DE_DATA:
        try:
            return datetime.strptime(valor, formato).date()
        except ValueError:
            continue
    return None


def data_compacta(bruto):
    """20260920 ou 20260920120000[-3:BRT] — só os oito primeiros dígitos contam."""
    numeros = re.sub(r"\D", "", bruto or "")[:8]
    if len(numeros) != 8:
        return None
    try:
        return datetime.strptime(numeros, "%Y%m%d").date()
    except ValueError:
        return None


def so_digitos(bruto):
    """CNPJ, CPF ou código de barras sem ponto, barra, traço nem espaço."""
    return re.sub(r"\D", "", bruto or "")
