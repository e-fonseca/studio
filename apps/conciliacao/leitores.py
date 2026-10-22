"""Ler o extrato que o banco entrega, sem biblioteca de fora.

Dois formatos, que é o que os bancos brasileiros dão para baixar:

- **OFX** — o banco costuma chamar de "arquivo para o gerenciador financeiro", "Money",
  "OFX" ou "extrato para conciliação". É o melhor formato: vem com a data, o valor, a
  descrição e um identificador único de cada lançamento (FITID), que é o que impede o
  mesmo pagamento de entrar duas vezes.
- **CSV** — a planilha que todo banco também oferece. Não tem identificador, as colunas
  mudam de banco para banco e o separador quase sempre é ponto e vírgula.

Por que não usar uma biblioteca de OFX
--------------------------------------
As bibliotecas de OFX tratam o formato inteiro: investimento, cartão, fatura, saldo de
aplicação. Aqui só interessam as linhas de movimento da conta corrente, que são quatro
campos. O arquivo OFX dos bancos é SGML velho — etiqueta aberta sem fechar — e nenhum
analisador de XML lê isso sem apanhar; as bibliotecas existem justamente para contornar
esse detalhe, que aqui cabe em vinte linhas. E o pacote da loja é instalado sem
internet: cada dependência a mais é uma roda a mais para dar errado.

O que é lido, e o que é ignorado de propósito
---------------------------------------------
Lê: data, valor, descrição, documento e identificador de cada movimento. Ignora: saldo,
investimento, cartão e qualquer outra seção. Linha sem data ou sem valor é descartada, e
o leitor diz quantas descartou — nada entra "mais ou menos certo" num confronto de
dinheiro.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from apps.core import leitura

CODIFICACOES = leitura.CODIFICACOES


@dataclass
class Movimento:
    data: date
    valor: Decimal
    descricao: str = ""
    documento: str = ""
    identificador: str = ""


@dataclass
class Leitura:
    """O que saiu do arquivo, e o que não deu para ler."""

    formato: str = ""
    banco: str = ""
    conta: str = ""
    movimentos: list = field(default_factory=list)
    descartadas: int = 0
    erro: str = ""

    @property
    def deu_certo(self):
        return bool(self.movimentos) and not self.erro

    @property
    def inicio(self):
        return min((m.data for m in self.movimentos), default=None)

    @property
    def fim(self):
        return max((m.data for m in self.movimentos), default=None)


_texto = leitura.texto
_sem_acento = leitura.sem_acento


def ler(nome_do_arquivo, dados):
    """Lê o extrato e devolve uma `Leitura`. Escolhe o formato pelo conteúdo, não pelo nome."""
    texto = _texto(dados)
    if not texto.strip():
        return Leitura(erro="O arquivo está vazio.")
    if "<OFX" in texto.upper() or "<STMTTRN" in texto.upper():
        return ler_ofx(texto)
    if "," in texto or ";" in texto or "\t" in texto:
        return ler_csv(texto)
    return Leitura(erro="Não reconheci o arquivo como OFX nem como CSV. Baixe de novo pelo "
                        "site do banco, escolhendo OFX ou CSV.")


# ---------------------------------------------------------------- OFX
_ETIQUETA = re.compile(r"<([A-Z0-9.]+)>([^<\r\n]*)", re.IGNORECASE)


def _campos(bloco):
    """Todas as etiquetas de um pedaço de OFX, mesmo as que não fecham."""
    achados = {}
    for nome, valor in _ETIQUETA.findall(bloco):
        nome = nome.upper()
        valor = valor.strip()
        if valor and nome not in achados:
            achados[nome] = valor
    return achados


_data_ofx = leitura.data_compacta


def ler_ofx(texto):
    leitura = Leitura(formato="ofx")
    cabecalho = _campos(texto.split("<STMTTRN>")[0])
    leitura.banco = (cabecalho.get("ORG") or cabecalho.get("BANKID") or "").strip()
    conta = cabecalho.get("ACCTID", "")
    ramo = cabecalho.get("BRANCHID", "")
    leitura.conta = f"{ramo} / {conta}".strip(" /") if (ramo or conta) else ""

    blocos = re.split(r"<STMTTRN>", texto, flags=re.IGNORECASE)[1:]
    if not blocos:
        leitura.erro = ("O arquivo é OFX mas não tem movimento nenhum de conta corrente. "
                        "Pode ser extrato de cartão ou de investimento.")
        return leitura
    for bloco in blocos:
        bloco = re.split(r"</STMTTRN>", bloco, flags=re.IGNORECASE)[0]
        campos = _campos(bloco)
        quando = _data_ofx(campos.get("DTPOSTED") or campos.get("DTUSER", ""))
        valor = _numero(campos.get("TRNAMT", ""))
        if quando is None or valor is None:
            leitura.descartadas += 1
            continue
        leitura.movimentos.append(Movimento(
            data=quando, valor=valor,
            descricao=(campos.get("MEMO") or campos.get("NAME") or "").strip(),
            documento=(campos.get("CHECKNUM") or campos.get("REFNUM") or "").strip(),
            identificador=(campos.get("FITID") or "").strip(),
        ))
    if not leitura.movimentos:
        leitura.erro = "Nenhum movimento do arquivo tinha data e valor legíveis."
    return leitura


# ---------------------------------------------------------------- CSV
# Como cada banco chama a coluna. A comparação é sem acento e em minúsculas.
COLUNAS_DATA = ("data", "data lancamento", "data do lancamento", "data mov", "dt", "date",
                "data movimento", "data da movimentacao", "data compra")
COLUNAS_VALOR = ("valor", "valor (r$)", "valor r$", "montante", "amount", "valor do lancamento",
                 "credito/debito", "vlr")
COLUNAS_DESCRICAO = ("descricao", "historico", "lancamento", "detalhe", "memo", "titulo",
                     "descricao do lancamento", "transacao", "estabelecimento")
COLUNAS_DOCUMENTO = ("documento", "doc", "numero do documento", "num doc", "identificador",
                     "n documento", "nr documento")


def _achar_coluna(cabecalho, nomes):
    limpo = [_sem_acento(c or "").strip().lower() for c in cabecalho]
    for posicao, nome in enumerate(limpo):
        if nome in nomes:
            return posicao
    for posicao, nome in enumerate(limpo):
        if any(nome.startswith(n) for n in nomes):
            return posicao
    return None


_numero = leitura.numero
_data_csv = leitura.data


def ler_csv(texto):
    leitura = Leitura(formato="csv")
    linhas = [linha for linha in texto.splitlines() if linha.strip()]
    if not linhas:
        return Leitura(formato="csv", erro="O arquivo está vazio.")
    separador = max((";", ",", "\t"), key=lambda s: linhas[0].count(s) + linhas[-1].count(s))

    # Alguns bancos põem duas ou três linhas de apresentação antes do cabeçalho de verdade.
    cabecalho, resto = None, []
    leitor = list(csv.reader(linhas, delimiter=separador))
    for posicao, campos in enumerate(leitor):
        if _achar_coluna(campos, COLUNAS_DATA) is not None and _achar_coluna(campos, COLUNAS_VALOR) is not None:
            cabecalho, resto = campos, leitor[posicao + 1:]
            break
    if cabecalho is None:
        leitura.erro = ("Não achei as colunas de data e de valor. O arquivo precisa ter uma "
                        "linha de títulos com, pelo menos, 'Data' e 'Valor'.")
        return leitura

    onde_data = _achar_coluna(cabecalho, COLUNAS_DATA)
    onde_valor = _achar_coluna(cabecalho, COLUNAS_VALOR)
    onde_descricao = _achar_coluna(cabecalho, COLUNAS_DESCRICAO)
    onde_documento = _achar_coluna(cabecalho, COLUNAS_DOCUMENTO)
    for campos in resto:
        if len(campos) <= max(onde_data, onde_valor):
            continue
        quando = _data_csv(campos[onde_data])
        valor = _numero(campos[onde_valor])
        if quando is None or valor is None:
            leitura.descartadas += 1
            continue
        leitura.movimentos.append(Movimento(
            data=quando, valor=valor,
            descricao=(campos[onde_descricao].strip() if onde_descricao is not None
                       and len(campos) > onde_descricao else ""),
            documento=(campos[onde_documento].strip() if onde_documento is not None
                       and len(campos) > onde_documento else ""),
        ))
    if not leitura.movimentos:
        leitura.erro = ("Nenhuma linha tinha data e valor legíveis. Confira se a data está "
                        "como 20/09/2026 e o valor como 1.234,56.")
    return leitura


def impressao_digital(dados):
    """A impressão digital do conteúdo, para não importar o mesmo arquivo duas vezes."""
    import hashlib

    if isinstance(dados, str):
        dados = dados.encode("utf-8", "replace")
    return hashlib.sha256(dados).hexdigest()
