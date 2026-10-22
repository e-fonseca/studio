"""Conferir o documento do fornecedor contra o que a loja pediu.

É a parte do pedido do Edson que diz "para checar se as informações estão corretas".
O que se checa, exatamente:

1. **Veio o que foi pedido?** Item da nota que não está no pedido, e item do pedido
   que não veio na nota.
2. **Veio quanto foi pedido?** Quantidade a mais ou a menos, com a diferença escrita.
3. **Veio pelo preço de referência?** O custo da última compra contra o unitário da
   nota. Preço não é erro — é negociação —, mas aumento que ninguém combinou só
   aparece quando alguém compara, e é isso que nunca acontecia.
4. **O total fecha?** O total do documento contra a soma do pedido.

O nó é **casar a linha da nota com a linha do pedido**. O código do produto na nota
é o código DO FORNECEDOR (`cProd`), não o do SET: só por sorte os dois são iguais. O
que serve de ponte, nesta ordem:

- **código de barras** (`cEAN` na nota, `codigo_barras` no nosso item). É o mesmo
  número nos dois lados do balcão quando existe, e é a ponte mais confiável;
- **código igual**, para o fornecedor que usa o código da loja ou para o romaneio em
  planilha que a própria loja mandou;
- **descrição**, sem acento e sem as palavras de embalagem, quando as duas pontas
  escrevem o mesmo produto de jeitos parecidos.

Casamento por descrição vem MARCADO na tela. Conferência de dinheiro que não diz como
chegou ao resultado é um palpite com cara de conta.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal

from apps.core.texto import sem_acento

ZERO = Decimal("0")

# Quanto o unitário pode subir sem a tela chamar atenção. Preço de compra varia por
# frete, lote e câmbio; o que interessa é o salto, não o centavo.
TOLERANCIA_PRECO = Decimal("0.02")

# Palavra que não distingue um produto de outro e só estorva o casamento por nome.
_RUIDO = ("unidade", "unidades", "un", "cx", "caixa", "pct", "pacote", "kg", "g", "ml",
          "l", "pc", "peca", "pecas", "com", "de", "do", "da", "e")


class Como:
    """Como a linha da nota foi casada com a linha do pedido."""

    BARRAS = "barras"
    CODIGO = "codigo"
    DESCRICAO = "descricao"

    ROTULOS = {
        BARRAS: "pelo código de barras",
        CODIGO: "pelo código",
        DESCRICAO: "pela descrição (confira)",
    }


def _chave_do_nome(texto):
    """O nome reduzido ao que distingue: sem acento, sem pontuação, sem palavra de embalagem."""
    limpo = re.sub(r"[^0-9A-Z ]+", " ", sem_acento(texto))
    palavras = [p for p in limpo.split() if p and p.lower() not in _RUIDO]
    return " ".join(sorted(palavras))


@dataclass
class Linha:
    """Uma linha da conferência: o que a nota diz e o que o pedido dizia."""

    descricao: str = ""
    codigo: str = ""
    como: str = ""
    quantidade_pedida: Decimal | None = None
    quantidade_lida: Decimal | None = None
    custo_pedido: Decimal | None = None
    unitario_lido: Decimal | None = None

    @property
    def rotulo_do_casamento(self):
        return Como.ROTULOS.get(self.como, "")

    @property
    def casou(self):
        return self.quantidade_pedida is not None and self.quantidade_lida is not None

    @property
    def diferenca_de_quantidade(self):
        if not self.casou:
            return None
        return self.quantidade_lida - self.quantidade_pedida

    @property
    def quantidade_bate(self):
        diferenca = self.diferenca_de_quantidade
        return diferenca is not None and diferenca == ZERO

    @property
    def diferenca_de_preco(self):
        """Quanto o unitário da nota passa do custo de referência, em porcentagem."""
        if self.custo_pedido in (None, ZERO) or self.unitario_lido is None:
            return None
        return (self.unitario_lido - self.custo_pedido) / self.custo_pedido * 100

    @property
    def preco_subiu(self):
        diferenca = self.diferenca_de_preco
        return diferenca is not None and diferenca > TOLERANCIA_PRECO * 100

    @property
    def situacao(self):
        """A palavra que a tela mostra na linha, do pior caso para o melhor."""
        if self.quantidade_pedida is None:
            return "veio sem ter sido pedido"
        if self.quantidade_lida is None:
            return "pedido e não veio"
        diferenca = self.diferenca_de_quantidade
        if diferenca > ZERO:
            return "veio mais do que o pedido"
        if diferenca < ZERO:
            return "veio menos do que o pedido"
        if self.preco_subiu:
            return "quantidade certa, preço acima da referência"
        return "confere"

    @property
    def confere(self):
        return self.situacao == "confere"


@dataclass
class Conferencia:
    """O resultado da conferência de um documento contra um pedido."""

    linhas: list = field(default_factory=list)
    valor_do_documento: Decimal | None = None
    valor_do_pedido: Decimal = ZERO
    aviso: str = ""

    @property
    def tem_resultado(self):
        return bool(self.linhas)

    @property
    def divergentes(self):
        return [linha for linha in self.linhas if not linha.confere]

    @property
    def quantas_conferem(self):
        return sum(1 for linha in self.linhas if linha.confere)

    @property
    def tudo_confere(self):
        return bool(self.linhas) and not self.divergentes and self.valor_bate

    @property
    def diferenca_de_valor(self):
        if self.valor_do_documento is None:
            return None
        return self.valor_do_documento - self.valor_do_pedido

    @property
    def valor_bate(self):
        """O total do documento contra o do pedido, com um centavo de folga.

        Um centavo porque a nota arredonda cada linha e o pedido arredonda o total:
        acusar divergência de R$ 0,01 treinaria a gerência a ignorar o aviso.
        """
        diferenca = self.diferenca_de_valor
        if diferenca is None:
            return True
        return abs(diferenca) <= Decimal("0.01")

    @property
    def resumo(self):
        """Uma frase para o alto da tela, dizendo o que a conferência achou."""
        if self.aviso and not self.linhas:
            return self.aviso
        if not self.linhas:
            return "Não há o que conferir neste documento."
        if self.tudo_confere:
            return f"As {len(self.linhas)} linhas conferem com o pedido."
        partes = []
        faltando = sum(1 for l in self.linhas if l.quantidade_lida is None)
        sobrando = sum(1 for l in self.linhas if l.quantidade_pedida is None)
        diferentes = sum(1 for l in self.linhas if l.casou and not l.quantidade_bate)
        caros = sum(1 for l in self.linhas if l.casou and l.quantidade_bate and l.preco_subiu)
        if faltando:
            partes.append(f"{faltando} pedido{'s' if faltando != 1 else ''} e não veio")
        if sobrando:
            partes.append(f"{sobrando} veio sem ter sido pedido")
        if diferentes:
            partes.append(f"{diferentes} com quantidade diferente")
        if caros:
            partes.append(f"{caros} com preço acima da referência")
        if not self.valor_bate:
            partes.append("total diferente do pedido")
        return "Confira: " + ", ".join(partes) + "."


def _indice(itens):
    """Três mapas de busca (barras, código, nome) sobre as linhas do pedido.

    Nome repetido não entra em mapa nenhum: dois produtos com a mesma descrição
    reduzida casariam no primeiro que aparecesse, e um palpite silencioso é o que esta
    tela existe para não fazer.
    """
    por_barras, por_codigo, por_nome = {}, {}, {}
    repetidos = set()
    for item in itens:
        if item.codigo_barras:
            por_barras.setdefault(item.codigo_barras, item)
        por_codigo.setdefault((item.codigo or "").strip().upper(), item)
        chave = _chave_do_nome(item.descricao)
        if chave:
            if chave in por_nome:
                repetidos.add(chave)
            por_nome.setdefault(chave, item)
    for chave in repetidos:
        por_nome.pop(chave, None)
    return por_barras, por_codigo, por_nome


def conferir(pedido, anexo):
    """Compara o que foi lido no anexo com os itens do pedido."""
    itens = list(pedido.itens.all())
    conferencia = Conferencia(
        valor_do_documento=anexo.valor_do_documento,
        valor_do_pedido=pedido.valor_total,
        aviso=anexo.erro_de_leitura,
    )
    lidos = anexo.itens_lidos or []
    if not lidos:
        return conferencia

    por_barras, por_codigo, por_nome = _indice(itens)
    usados = {}
    for lido in lidos:
        barras = (lido.get("codigo_barras") or "").strip()
        codigo = (lido.get("codigo") or "").strip().upper()
        descricao = (lido.get("descricao") or "").strip()
        item, como = None, ""
        if barras and barras in por_barras:
            item, como = por_barras[barras], Como.BARRAS
        elif codigo and codigo in por_codigo:
            item, como = por_codigo[codigo], Como.CODIGO
        else:
            chave = _chave_do_nome(descricao)
            if chave and chave in por_nome:
                item, como = por_nome[chave], Como.DESCRICAO

        quantidade = _decimal(lido.get("quantidade"))
        unitario = _decimal(lido.get("unitario"))
        if item is None:
            conferencia.linhas.append(Linha(
                descricao=descricao or codigo or "(item sem nome na nota)",
                codigo=lido.get("codigo") or "",
                quantidade_lida=quantidade, unitario_lido=unitario,
            ))
            continue
        # A nota pode trazer o mesmo produto em duas linhas (lote, validade): o que
        # confere contra o pedido é a soma delas, não cada uma contra o total.
        if item.codigo in usados:
            linha = usados[item.codigo]
            if quantidade is not None:
                linha.quantidade_lida = (linha.quantidade_lida or ZERO) + quantidade
            continue
        linha = Linha(
            descricao=item.descricao, codigo=item.codigo, como=como,
            quantidade_pedida=item.quantidade, quantidade_lida=quantidade,
            custo_pedido=item.custo, unitario_lido=unitario,
        )
        usados[item.codigo] = linha
        conferencia.linhas.append(linha)

    for item in itens:
        if item.codigo not in usados:
            conferencia.linhas.append(Linha(
                descricao=item.descricao, codigo=item.codigo,
                quantidade_pedida=item.quantidade, custo_pedido=item.custo,
            ))
    # Divergência em cima, que é o que se age: linha que confere é só confirmação.
    conferencia.linhas.sort(key=lambda linha: (linha.confere, linha.descricao))
    return conferencia


def _decimal(bruto):
    if bruto in (None, ""):
        return None
    try:
        return Decimal(str(bruto))
    except (ArithmeticError, ValueError):
        return None
