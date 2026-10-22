"""Valores que sabem sair nas duas formas: texto no papel, número na planilha.

Pedido do Edson em 19/10/2026: *"FINANCEIRO, permitir exportar além do pdf para
planilha de excel ajustado no mesmo layout"*.

O problema
----------
O relatório é montado uma vez e sai nos dois formatos (apps/core/pdf.py e
apps/core/planilha.py). No papel, um valor é texto: "R$ 1.234,56" alinhado à direita.
Na planilha, o MESMO valor precisa ser número, senão a coluna não soma, não ordena e
não filtra — e uma planilha que não soma é um PDF mais feio.

Passar o texto pronto para os dois perderia o número; passar o número cru para os dois
faria o papel imprimir "1234.56". Então o que anda entre o montador e os dois formatos
são estes três envelopes: cada um sabe escrever a si mesmo como texto (`str`) e sabe
dizer que número é (`valor`) e com que cara ele se escreve na planilha (`formato`).

Texto comum continua sendo `str`, e tupla `(texto, cor)` continua pintando a célula no
papel: nada do que já existia mudou de forma.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from apps.core.templatetags.cabana import reais

# Os formatos de número, escritos como o OOXML quer (ponto decimal e vírgula de milhar
# sempre, independentemente do idioma: quem localiza na hora de mostrar é o Excel).
DINHEIRO = '"R$"\\ #,##0.00;[Red]\\-"R$"\\ #,##0.00'
INTEIRO = "#,##0"
DATA = "dd/mm/yyyy"


@dataclass(frozen=True)
class Dinheiro:
    """Um valor em reais. No papel sai "R$ 1.234,56"; na planilha, 1234.56 somável."""

    valor: Decimal | int | float | None
    vazio: str = "—"

    def __str__(self):
        return reais(self.valor, vazio=self.vazio)

    @property
    def numero(self):
        return None if self.valor is None else Decimal(str(self.valor))

    formato = DINHEIRO


@dataclass(frozen=True)
class Inteiro:
    """Uma contagem. No papel sai "1.443"; na planilha, 1443.

    O `sufixo` existe para a coluna estreita do papel, que diz "12d" e não "12 dias":
    o texto continua com a letra e a planilha continua com o número, que é o que faz a
    coluna de atraso ordenar do mais vencido para o menos.
    """

    valor: int | None
    sufixo: str = ""

    def __str__(self):
        if self.valor is None:
            return ""
        return f"{self.valor:,}".replace(",", ".") + self.sufixo

    @property
    def numero(self):
        return None if self.valor is None else int(self.valor)

    formato = INTEIRO


@dataclass(frozen=True)
class Data:
    """Uma data. No papel sai "19/10/2026"; na planilha, data de verdade, ordenável."""

    valor: date | None
    vazio: str = "sem data"

    def __str__(self):
        return self.vazio if self.valor is None else f"{self.valor:%d/%m/%Y}"

    @property
    def numero(self):
        """O número de série do Excel: dias desde 30/12/1899, que é a origem dele."""
        if self.valor is None:
            return None
        return (self.valor - date(1899, 12, 30)).days

    formato = DATA


def texto_e_cor(bruto, cor_padrao):
    """Desembrulha uma célula em (texto, cor), seja ela texto, tupla ou envelope."""
    valor, cor = bruto if isinstance(bruto, tuple) else (bruto, cor_padrao)
    return str(valor), cor


def numero_de(bruto):
    """O número de uma célula, ou None quando ela é texto puro.

    Devolve também o formato, porque na planilha número sem formato vira 46945 no
    lugar de uma data e 1234.56 no lugar de R$ 1.234,56.
    """
    valor = bruto[0] if isinstance(bruto, tuple) else bruto
    if isinstance(valor, (Dinheiro, Inteiro, Data)):
        return valor.numero, valor.formato
    return None, None
