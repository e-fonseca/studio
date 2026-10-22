"""Ler o documento que o fornecedor mandou, sem biblioteca de fora.

O que o Edson pediu em 14/10/2026 foi "fazer com o sistema faça a leitura de todo o
conteúdo do arquivo também para checar se as informações estão corretas". O que dá
para ler, e o que não dá, depende do arquivo — e isso é do documento, não do sistema:

- **XML da nota fiscal (NF-e)** é o documento de verdade. Traz cada item em campo
  próprio: código, descrição, código de barras, quantidade, valor unitário e total,
  mais o emitente e o total da nota. Dá para conferir linha por linha, e é o que a
  conferência usa.
- **PDF (o DANFE)** é o RETRATO da nota. O conteúdo não está em campo nenhum: são
  posições de texto numa página, com fonte embutida. Lê-se o que dá e o que sai
  disso é adivinhação — e adivinhação numa tela que confere dinheiro é pior que
  nada. Fica guardado e à vista, que é o controle futuro pedido.
- **CSV ou TXT** é o romaneio em planilha, que vários fornecedores mandam. Tem
  cabeçalho e colunas, então lê-se item a item como o XML.
- **Foto e imagem** ficam guardadas. Ninguém lê número de foto de papel sem mandar a
  imagem para fora, e nada aqui sai do servidor da loja.

Cuidado com arquivo que veio de fora: XML com `<!DOCTYPE>` é recusado antes de
qualquer análise. É por ali que entra a "bomba de bilhões de risadas" — um punhado de
entidades que se multiplicam e comem a memória do servidor. Nota fiscal de verdade
nunca traz DOCTYPE.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from xml.etree import ElementTree

from apps.core import leitura

# O que a tela aceita. A assinatura é o começo do arquivo: extensão mentida é o jeito
# mais velho de fazer um sistema abrir o que não devia.
TIPOS = {
    "xml": None,
    "pdf": [b"%PDF-"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
    "csv": None,
    "txt": None,
}

# Nome da etiqueta sem a parte do espaço de nomes: a NF-e vem com
# {http://www.portalfiscal.inf.br/nfe}infNFe e ninguém precisa disso para ler.
_SEM_ESPACO = re.compile(r"\{[^}]*\}")

COLUNAS_CODIGO = ("codigo", "cod", "codigo do produto", "cod produto", "produto codigo",
                  "referencia", "ref", "sku", "item")
COLUNAS_DESCRICAO = ("descricao", "produto", "mercadoria", "nome", "item descricao", "especificacao")
COLUNAS_QUANTIDADE = ("quantidade", "qtd", "qtde", "qt", "quant", "unidades", "volume")
COLUNAS_UNITARIO = ("valor unitario", "unitario", "preco unitario", "preco", "valor un",
                    "vl unitario", "custo", "custo unitario")
COLUNAS_TOTAL = ("valor total", "total", "total do item", "vl total", "subtotal", "valor")
COLUNAS_BARRAS = ("codigo de barras", "barras", "ean", "gtin", "codigo barras")


@dataclass
class ItemLido:
    codigo: str = ""
    codigo_barras: str = ""
    descricao: str = ""
    quantidade: Decimal | None = None
    unitario: Decimal | None = None
    total: Decimal | None = None

    def como_dicionario(self):
        """Tudo como texto: vai para JSONField, e Decimal não atravessa JSON inteiro."""
        return {
            "codigo": self.codigo,
            "codigo_barras": self.codigo_barras,
            "descricao": self.descricao,
            "quantidade": str(self.quantidade) if self.quantidade is not None else "",
            "unitario": str(self.unitario) if self.unitario is not None else "",
            "total": str(self.total) if self.total is not None else "",
        }


@dataclass
class Documento:
    """O que o sistema conseguiu entender do arquivo."""

    formato: str = ""
    numero: str = ""
    emitente: str = ""
    emitente_documento: str = ""
    emitido_em: date | None = None
    valor: Decimal | None = None
    itens: list = field(default_factory=list)
    # Por que não foi lido. Não é erro de sistema: é o formato não ter o que ler.
    aviso: str = ""

    @property
    def tem_itens(self):
        return bool(self.itens)


def ler(nome_do_arquivo, dados):
    """Lê o documento e devolve o que entendeu. Escolhe pelo conteúdo, não pelo nome."""
    extensao = (nome_do_arquivo or "").rsplit(".", 1)[-1].lower()
    if isinstance(dados, bytes) and dados[:5] == b"%PDF-":
        return Documento(formato="pdf", aviso=AVISO_PDF)
    if extensao in ("png", "jpg", "jpeg"):
        return Documento(formato="imagem", aviso=AVISO_IMAGEM)
    conteudo = leitura.texto(dados)
    if not conteudo.strip():
        return Documento(aviso="O arquivo está vazio.")
    if "<" in conteudo[:4096] and ">" in conteudo[:4096]:
        return ler_nota_fiscal(conteudo)
    return ler_planilha(conteudo)


AVISO_PDF = ("PDF é o retrato da nota, não a nota: o número e a quantidade de cada item "
             "não estão em campo nenhum dentro dele. O arquivo fica guardado aqui; para a "
             "conferência automática, peça ao fornecedor o XML da nota fiscal.")
AVISO_IMAGEM = ("Imagem fica guardada para consulta. Ler número de foto de papel exigiria "
                "mandar a imagem para fora do servidor da loja, e nada daqui sai.")


# ---------------------------------------------------------------- NF-e (XML)
def _nome(etiqueta):
    return _SEM_ESPACO.sub("", etiqueta)


def _achar(no, caminho):
    """O primeiro descendente com este nome, ignorando o espaço de nomes."""
    for filho in no.iter():
        if _nome(filho.tag) == caminho:
            return filho
    return None


def _valor(no, nome, padrao=""):
    achado = _achar(no, nome) if no is not None else None
    if achado is None or achado.text is None:
        return padrao
    return achado.text.strip()


def ler_nota_fiscal(conteudo):
    """O XML da NF-e: emitente, número, data, total e cada item.

    Serve tanto o arquivo do portal (`<nfeProc>` com protocolo em volta) quanto o
    XML solto da nota (`<NFe>`), que é o que a maioria dos emissores manda por
    e-mail.
    """
    if "<!DOCTYPE" in conteudo[:4096].upper() or "<!ENTITY" in conteudo[:4096].upper():
        return Documento(formato="xml", aviso="O XML traz DOCTYPE e não foi aberto. "
                                              "Nota fiscal de verdade não tem DOCTYPE.")
    try:
        raiz = ElementTree.fromstring(conteudo)
    except ElementTree.ParseError as erro:
        return Documento(formato="xml", aviso=f"Não consegui abrir o XML: {erro}.")

    informacoes = _achar(raiz, "infNFe")
    if informacoes is None:
        return Documento(formato="xml",
                         aviso="O XML não parece ser de nota fiscal: não achei a parte infNFe.")

    documento = Documento(formato="nfe")
    identificacao = _achar(informacoes, "ide")
    documento.numero = _valor(identificacao, "nNF")
    documento.emitido_em = (leitura.data(_valor(identificacao, "dhEmi")[:10])
                            or leitura.data(_valor(identificacao, "dEmi")[:10]))

    emitente = _achar(informacoes, "emit")
    documento.emitente = _valor(emitente, "xNome")
    documento.emitente_documento = (leitura.so_digitos(_valor(emitente, "CNPJ"))
                                    or leitura.so_digitos(_valor(emitente, "CPF")))

    totais = _achar(informacoes, "ICMSTot")
    documento.valor = leitura.numero(_valor(totais, "vNF"))

    for det in informacoes.iter():
        if _nome(det.tag) != "det":
            continue
        produto = _achar(det, "prod")
        if produto is None:
            continue
        barras = leitura.so_digitos(_valor(produto, "cEAN"))
        documento.itens.append(ItemLido(
            codigo=_valor(produto, "cProd"),
            # "SEM GTIN" é o que o emissor escreve quando o produto não tem código de
            # barras; guardar isso como código levaria a casar item errado.
            codigo_barras=barras if barras and barras not in ("0", "00") else "",
            descricao=_valor(produto, "xProd"),
            quantidade=leitura.numero(_valor(produto, "qCom")),
            unitario=leitura.numero(_valor(produto, "vUnCom")),
            total=leitura.numero(_valor(produto, "vProd")),
        ))
    if not documento.itens:
        documento.aviso = "Li a nota, mas não achei item nenhum dentro dela."
    return documento


# ---------------------------------------------------------------- romaneio (CSV/TXT)
def _achar_coluna(cabecalho, nomes):
    limpos = [leitura.sem_acento(campo or "").strip().lower() for campo in cabecalho]
    for nome in nomes:
        if nome in limpos:
            return limpos.index(nome)
    for posicao, campo in enumerate(limpos):
        if any(campo.startswith(nome) for nome in nomes):
            return posicao
    return None


def _campo(campos, posicao):
    if posicao is None or posicao >= len(campos):
        return ""
    return (campos[posicao] or "").strip()


def ler_planilha(conteudo):
    """O romaneio em CSV: uma linha de títulos e uma linha por item.

    Exige, no mínimo, uma coluna que diga o produto (código ou descrição) e uma de
    quantidade. Sem as duas não há o que conferir, e a tela diz isso em vez de
    apresentar uma lista pela metade como se estivesse completa.
    """
    documento = Documento(formato="csv")
    linhas = [linha for linha in conteudo.splitlines() if linha.strip()]
    if not linhas:
        return Documento(formato="csv", aviso="O arquivo está vazio.")
    separador = max((";", ",", "\t"), key=lambda s: linhas[0].count(s) + linhas[-1].count(s))
    leitor = list(csv.reader(linhas, delimiter=separador))

    cabecalho, resto = None, []
    for posicao, campos in enumerate(leitor):
        tem_produto = (_achar_coluna(campos, COLUNAS_CODIGO) is not None
                       or _achar_coluna(campos, COLUNAS_DESCRICAO) is not None)
        if tem_produto and _achar_coluna(campos, COLUNAS_QUANTIDADE) is not None:
            cabecalho, resto = campos, leitor[posicao + 1:]
            break
    if cabecalho is None:
        documento.aviso = ("Não achei as colunas do romaneio. O arquivo precisa ter uma linha "
                           "de títulos com, pelo menos, o produto (código ou descrição) e a "
                           "quantidade.")
        return documento

    onde = {
        "codigo": _achar_coluna(cabecalho, COLUNAS_CODIGO),
        "barras": _achar_coluna(cabecalho, COLUNAS_BARRAS),
        "descricao": _achar_coluna(cabecalho, COLUNAS_DESCRICAO),
        "quantidade": _achar_coluna(cabecalho, COLUNAS_QUANTIDADE),
        "unitario": _achar_coluna(cabecalho, COLUNAS_UNITARIO),
        "total": _achar_coluna(cabecalho, COLUNAS_TOTAL),
    }
    for campos in resto:
        quantidade = leitura.numero(_campo(campos, onde["quantidade"]))
        codigo = _campo(campos, onde["codigo"])
        descricao = _campo(campos, onde["descricao"])
        if quantidade is None or not (codigo or descricao):
            continue
        documento.itens.append(ItemLido(
            codigo=codigo,
            codigo_barras=leitura.so_digitos(_campo(campos, onde["barras"])),
            descricao=descricao,
            quantidade=quantidade,
            unitario=leitura.numero(_campo(campos, onde["unitario"])),
            total=leitura.numero(_campo(campos, onde["total"])),
        ))
    if not documento.itens:
        documento.aviso = "Achei os títulos das colunas, mas nenhuma linha de item com quantidade."
    else:
        documento.valor = sum((item.total for item in documento.itens if item.total is not None),
                              Decimal("0")) or None
    return documento


def validar(arquivo, tamanho_maximo):
    """O nome e a extensão do arquivo, ou uma explicação do que está errado.

    Devolve (nome, extensao, erro). Confere o começo do conteúdo contra a extensão:
    um .xml que começa com %PDF- é PDF com nome trocado, e tratá-lo como XML daria
    um "não consegui abrir" sem explicação nenhuma para quem mandou.
    """
    nome = (arquivo.name or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    extensao = nome.rsplit(".", 1)[-1].lower() if "." in nome else ""
    if extensao not in TIPOS:
        return nome[:200], extensao, ("Tipo de arquivo não aceito. Mande o XML da nota, o PDF, "
                                      "uma foto (PNG ou JPG) ou o romaneio em CSV.")
    if arquivo.size > tamanho_maximo:
        limite = tamanho_maximo // (1024 * 1024)
        return nome[:200], extensao, f"O arquivo passa do limite de {limite} MB."
    if not arquivo.size:
        return nome[:200], extensao, "O arquivo está vazio."
    inicio = arquivo.read(16)
    arquivo.seek(0)
    assinaturas = TIPOS[extensao]
    if assinaturas is None:
        if b"\x00" in inicio:
            return nome[:200], extensao, "O conteúdo não parece ser texto. Confira o arquivo."
    elif not any(inicio.startswith(assinatura) for assinatura in assinaturas):
        return nome[:200], extensao, ("O conteúdo do arquivo não corresponde à extensão. "
                                      "Confira o arquivo.")
    return nome[:200], extensao, ""


def ler_do_envio(arquivo, nome):
    """Lê o arquivo que acabou de ser enviado, sem deixar a tela cair por causa dele.

    Leitura de arquivo de fora é a parte que mais quebra: o anexo precisa ficar
    guardado mesmo quando a leitura não dá certo, porque guardar é metade do pedido.
    """
    dados = arquivo.read()
    arquivo.seek(0)
    try:
        return ler(nome, dados)
    except Exception as erro:  # noqa: BLE001 - arquivo de fora não derruba a tela
        return Documento(aviso=f"Não consegui ler o conteúdo deste arquivo: {erro}.")
