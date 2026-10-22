"""O que mudou de uma importação para a outra.

Existe por uma pergunta do Edson: a cada sincronização o sistema soma ou
substitui? Substitui. Cada importação guarda a sua própria foto dos dados do
SET, ligada a ela pelo campo `importacao`, e toda tela filtra por essa foto —
nenhum número é acumulado de uma importação para a seguinte. Ler o código prova
isso para quem programa; esta tela prova para quem usa, mostrando lado a lado as
duas últimas importações. Importar o mesmo backup duas vezes dá exatamente os
mesmos números, e é isso que aparece aqui.

As linhas antigas não ficam para sempre: `limpar_antigas` apaga as fotos mais
velhas que as dez últimas importações concluídas.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Count, Sum

from apps.clientes.models import ClienteImportado
from apps.financeiro.models import Lancamento
from apps.fornecedores.models import FornecedorImportado

from .models import CompraImportada, Importacao, ProdutoImportado, VendaImportada

ZERO = Decimal("0")


@dataclass
class Linha:
    """Um número nas duas importações, com a diferença já calculada."""

    rotulo: str
    anterior: Decimal | int | None
    atual: Decimal | int
    # Como o número se escreve na tela: "reais", "contagem" (com ponto de milhar) ou
    # "quantidade" (unidades, que podem ter casa decimal).
    formato: str = "contagem"

    @property
    def dinheiro(self):
        return self.formato == "reais"

    @property
    def diferenca(self):
        if self.anterior is None:
            return None
        return self.atual - self.anterior

    @property
    def mudou(self):
        return self.diferenca not in (None, 0, ZERO)

    @property
    def dobrou(self):
        """Sinal de soma indevida: o número atual é o dobro (ou mais) do anterior."""
        if not self.anterior:
            return False
        return self.atual >= self.anterior * 2


@dataclass
class Comparacao:
    """As duas últimas importações concluídas, uma do lado da outra."""

    atual: Importacao | None = None
    anterior: Importacao | None = None
    linhas: list = field(default_factory=list)
    fotos_guardadas: int = 0

    @property
    def tem_com_que_comparar(self):
        return self.atual is not None and self.anterior is not None

    @property
    def mesmo_backup(self):
        """As duas leram o mesmo arquivo de backup, com a mesma data e tamanho."""
        if not self.tem_com_que_comparar:
            return False
        return (
            self.atual.arquivo == self.anterior.arquivo
            and self.atual.arquivo_modificado_em == self.anterior.arquivo_modificado_em
            and self.atual.arquivo_bytes == self.anterior.arquivo_bytes
        )

    @property
    def alguma_dobrou(self):
        return any(linha.dobrou for linha in self.linhas)

    @property
    def mudaram(self):
        return [linha for linha in self.linhas if linha.mudou]


def _numeros(importacao):
    """Conta as linhas que a importação guardou. Uma consulta por tipo de dado."""
    if importacao is None:
        return {}
    pk = importacao.pk
    produtos = ProdutoImportado.objects.filter(importacao_id=pk).aggregate(
        quantas=Count("id"), estoque=Sum("estoque"))
    vendas = VendaImportada.objects.filter(importacao_id=pk).aggregate(
        quantas=Count("id"), valor=Sum("valor"))
    compras = CompraImportada.objects.filter(importacao_id=pk).aggregate(
        quantas=Count("id"), valor=Sum("valor_total"))
    lancamentos = Lancamento.objects.filter(importacao_id=pk).aggregate(quantas=Count("id"))
    return {
        "produtos": produtos["quantas"] or 0,
        "estoque": produtos["estoque"] or ZERO,
        "vendas": vendas["quantas"] or 0,
        "faturamento": vendas["valor"] or ZERO,
        "compras": compras["quantas"] or 0,
        "valor_comprado": compras["valor"] or ZERO,
        "lancamentos": lancamentos["quantas"] or 0,
        "clientes": ClienteImportado.objects.filter(importacao_id=pk).count(),
        "fornecedores": FornecedorImportado.objects.filter(importacao_id=pk).count(),
    }


# (chave, rótulo na tela, formato)
CAMPOS = (
    ("produtos", "Produtos no cadastro", "contagem"),
    ("estoque", "Unidades em estoque", "quantidade"),
    ("vendas", "Vendas dos 12 meses", "contagem"),
    ("faturamento", "Faturamento dos 12 meses", "reais"),
    ("compras", "Compras lidas do SET", "contagem"),
    ("valor_comprado", "Valor das compras", "reais"),
    ("lancamentos", "Lançamentos do financeiro", "contagem"),
    ("clientes", "Clientes no cadastro", "contagem"),
    ("fornecedores", "Fichas de fornecedor", "contagem"),
)


def montar():
    """Compara as duas últimas importações concluídas. Sem segunda, mostra só a atual."""
    concluidas = list(
        Importacao.objects.filter(situacao=Importacao.Situacao.CONCLUIDA)
        .order_by("-iniciada_em", "-id")[:2]
    )
    comparacao = Comparacao(
        atual=concluidas[0] if concluidas else None,
        anterior=concluidas[1] if len(concluidas) > 1 else None,
        fotos_guardadas=Importacao.objects.filter(situacao=Importacao.Situacao.CONCLUIDA).count(),
    )
    if comparacao.atual is None:
        return comparacao
    agora = _numeros(comparacao.atual)
    antes = _numeros(comparacao.anterior)
    comparacao.linhas = [
        Linha(rotulo=rotulo, anterior=antes.get(chave), atual=agora[chave], formato=formato)
        for chave, rotulo, formato in CAMPOS
    ]
    return comparacao
