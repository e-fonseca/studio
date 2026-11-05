"""Relatório em planilha (.xlsx), escrito aqui mesmo, sem biblioteca de fora.

Pedido do Edson em 19/10/2026: *"FINANCEIRO, permitir exportar além do pdf para planilha
de excel ajustado no mesmo layout"*.

Por que não usar uma biblioteca
-------------------------------
Pelo mesmo motivo do PDF (apps/core/pdf.py): o pacote da loja é instalado **sem
internet**, a partir das rodas que vão dentro do zip, e cada dependência nova é uma
roda a mais para dar errado numa máquina que não dá para acompanhar daqui. Um .xlsx é
um zip com meia dúzia de arquivos XML dentro, e tudo o que ele precisa — `zipfile` e
texto — já vem no Python.

O que este módulo faz, e o que não faz
--------------------------------------
Faz: uma aba, título, linhas de texto, os números do topo lado a lado, tabela com
cabeçalho congelado e filtro, coluna alinhada à esquerda ou à direita, largura de
coluna vinda da mesma medida do papel, linha de total, e **número de verdade na
célula** — dinheiro soma, data ordena, contagem filtra. Não faz: fórmula, gráfico,
mais de uma aba, imagem.

Mesmo layout que o papel, e as duas diferenças de propósito
-----------------------------------------------------------
Quem monta o relatório é uma função só, que recebe este objeto ou o `pdf.Relatorio` e
chama os mesmos blocos na mesma ordem (ver apps/financeiro/relatorio.py). Então a
ordem, as colunas e os números são os mesmos por construção, não por conferência.

Duas coisas mudam de propósito, porque planilha não é papel:
* **não há zebra.** A faixa cinza alternada ajuda o olho a seguir a linha no papel; na
  planilha ela atrapalha a leitura com filtro ligado, e o Excel já faz isso sozinho
  quando a pessoa quer.
* **não há "página 1 de 3".** A planilha não tem página; o que o papel diz no rodapé
  (quem emitiu e quando) vai para a primeira linha, antes do título.
"""

import zipfile
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO

from apps.core import celula, pdf

# Quantos pontos do papel cabem numa "largura de coluna" do Excel, que é medida em
# caracteres. Saiu de medir: 5,5 pontos por caractere deixa a coluna da planilha com a
# mesma folga da coluna do PDF, e é o que faz as duas ficarem com a mesma cara.
PONTOS_POR_CARACTERE = 5.5
LARGURA_MINIMA = 7
LARGURA_MAXIMA = 60

# As fontes, pela posição em que entram no `<fonts>` de `_estilos()`.
FONTE_PADRAO = 0
FONTE_TITULO = 1
FONTE_SUAVE = 2
FONTE_CABECALHO = 3
FONTE_CELULA = 4
FONTE_NEGRITO = 5
FONTE_DESTAQUE = 6
FONTE_ROTULO = 7
FONTE_VERMELHA = 8
FONTE_MARROM = 9

# Os formatos de número, pelo numFmtId que `_estilos()` declara. Do 0 ao 163 são os que
# o Excel já traz; os próprios começam no 164.
GERAL = 0
NUMFMT = {celula.DINHEIRO: 164, celula.INTEIRO: 165, celula.DATA: 166}

# A cor que o montador pede (as mesmas constantes do PDF) e a fonte que ela vira aqui.
CORES = {
    pdf.VERMELHO: FONTE_VERMELHA,
    pdf.MARROM: FONTE_MARROM,
    pdf.CINZA: FONTE_SUAVE,
}


class _Estilos:
    """Um estilo por combinação de fonte, formato, alinhamento e borda.

    A primeira versão disto tinha uma constante por estilo, escrita à mão, e cor e
    formato se excluíam: a célula vermelha do atraso perdia o formato de número, e uma
    célula vermelha de dinheiro teria saído como 1234.56 em vez de R$ 1.234,56. Aqui
    cada combinação pedida ganha o seu índice na hora, então as duas coisas convivem e
    nenhuma combinação nova precisa ser prevista.
    """

    def __init__(self):
        self._indices = {}
        self.combinacoes = []

    def de(self, fonte, numero=GERAL, direita=False, borda=0):
        chave = (fonte, numero, direita, borda)
        if chave not in self._indices:
            self._indices[chave] = len(self.combinacoes)
            self.combinacoes.append(chave)
        return self._indices[chave]


def _letra(coluna):
    """0 -> A, 25 -> Z, 26 -> AA. O Excel conta colunas em letras."""
    nome = ""
    coluna += 1
    while coluna:
        coluna, resto = divmod(coluna - 1, 26)
        nome = chr(ord("A") + resto) + nome
    return nome


def _escapar(texto):
    return (str(texto).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


@dataclass
class _Celula:
    """Uma célula pronta: o texto, o índice do estilo e o número, quando há um."""

    texto: str = ""
    estilo: int = 0
    numero: object = None


@dataclass
class _Tabela:
    """Onde uma tabela começou e acabou, para o filtro e o congelamento do cabeçalho."""

    cabecalho: int
    ultima: int
    colunas: int
    principal: bool = False


class Planilha:
    """Monta a aba de cima para baixo, com os mesmos blocos do `pdf.Relatorio`."""

    def __init__(self, titulo, subtitulo="", paisagem=False, emitido_por=""):
        # `paisagem` existe para a assinatura ser a mesma do papel. Planilha não tem
        # folha, então não há o que virar de lado; aceitar e ignorar é o que permite o
        # montador ser um só.
        self.titulo = titulo
        self.subtitulo = subtitulo
        self.emitido_por = emitido_por
        self.emitido_em = datetime.now()
        self._linhas = []
        self._larguras = {}
        self._tabelas = []
        self._estilos = _Estilos()
        self._cabecalho()

    # -- folha ------------------------------------------------------------
    def _escrever(self, celulas):
        self._linhas.append(celulas)
        return len(self._linhas)

    def _cabecalho(self):
        emitido = self.emitido_em.strftime("%d/%m/%Y às %H:%M")
        rodape = f"Studio Industrial · sistema auxiliar ao SET · emitido em {emitido}"
        if self.emitido_por:
            rodape += f" por {self.emitido_por}"
        self._escrever([_Celula(rodape, self._estilos.de(FONTE_SUAVE))])
        self._escrever([_Celula(self.titulo, self._estilos.de(FONTE_TITULO))])
        if self.subtitulo:
            self._escrever([_Celula(self.subtitulo, self._estilos.de(FONTE_SUAVE))])
        self._escrever([])

    def _anotar_largura(self, coluna, caracteres):
        atual = self._larguras.get(coluna, LARGURA_MINIMA)
        self._larguras[coluna] = max(atual, min(caracteres, LARGURA_MAXIMA))

    # -- blocos -----------------------------------------------------------
    def espaco(self, quanto=10):
        """Uma linha em branco. O `quanto` do papel é em pontos e aqui não se aplica."""
        self._escrever([])

    def pagina_nova(self):
        """Planilha não tem página: vira uma linha em branco, para o bloco respirar."""
        self._escrever([])

    def paragrafo(self, texto, tamanho=9.5, fonte=pdf.NORMAL, cor=pdf.PRETO, espaco=6):
        if cor == pdf.CINZA:
            letra = FONTE_SUAVE
        else:
            letra = FONTE_NEGRITO if fonte == pdf.NEGRITO else FONTE_CELULA
        self._escrever([_Celula(texto, self._estilos.de(letra))])

    def destaques(self, pares, tamanho=10):
        """Os números do topo, lado a lado: rótulo numa linha, valor na de baixo."""
        rotulos, valores = [], []
        for posicao, (rotulo, valor) in enumerate(pares):
            rotulos.append(_Celula(str(rotulo), self._estilos.de(FONTE_ROTULO)))
            numero, formato = celula.numero_de(valor)
            estilo = self._estilos.de(FONTE_DESTAQUE, NUMFMT.get(formato, GERAL))
            valores.append(_Celula(str(valor), estilo, numero))
            self._anotar_largura(posicao, len(str(rotulo)) + 2)
        self._escrever(rotulos)
        self._escrever(valores)
        self._escrever([])

    def tabela(self, colunas, linhas, altura_da_linha=15, tamanho=8.5, zebra=True,
               principal=False):
        """A tabela. Cada linha é uma lista de textos, de (texto, cor) ou de envelopes.

        `zebra` e `altura_da_linha` entram para a assinatura ser a mesma do papel.
        `principal` marca a tabela que ganha o cabeçalho congelado e o filtro: é a
        tabela que a pessoa veio ler, e numa planilha é ela que se ordena e se filtra.
        """
        cabecalho = self._escrever([
            _Celula(coluna.titulo,
                    self._estilos.de(FONTE_CABECALHO, direita=coluna.direita, borda=1))
            for coluna in colunas
        ])
        for posicao, coluna in enumerate(colunas):
            self._anotar_largura(posicao, int(coluna.largura / PONTOS_POR_CARACTERE))
        ultima = cabecalho
        for linha in linhas:
            ultima = self._escrever([
                self._uma_celula(coluna, bruto)
                for coluna, bruto in zip(colunas, linha)
            ])
        self._tabelas.append(_Tabela(cabecalho, ultima, len(colunas), principal))

    def _uma_celula(self, coluna, bruto):
        """Cor e formato convivem: o atraso sai vermelho E como número que ordena."""
        texto, cor = celula.texto_e_cor(bruto, pdf.PRETO)
        numero, formato = celula.numero_de(bruto)
        # Data fica à esquerda mesmo em coluna marcada à direita: o Excel alinha data
        # à direita por padrão e a coluna de vencimento ficaria descolada do título.
        direita = coluna.direita and formato != celula.DATA
        estilo = self._estilos.de(CORES.get(cor, FONTE_CELULA),
                                  NUMFMT.get(formato, GERAL), direita)
        return _Celula(texto, estilo, numero)

    def total(self, rotulo, valor):
        """A linha de soma, no fim da tabela: rótulo na primeira coluna, valor na última."""
        numero, formato = celula.numero_de(valor)
        colunas = self._tabelas[-1].colunas if self._tabelas else 2
        linha = [_Celula(str(rotulo), self._estilos.de(FONTE_NEGRITO))]
        linha += [_Celula("", self._estilos.de(FONTE_PADRAO))
                  for _ in range(max(colunas - 2, 0))]
        linha.append(_Celula(str(valor),
                             self._estilos.de(FONTE_DESTAQUE, NUMFMT.get(formato, GERAL),
                                              direita=True),
                             numero))
        self._escrever(linha)

    # -- fechamento -------------------------------------------------------
    @property
    def _principal(self):
        """A tabela que recebe o filtro: a marcada, ou a maior que houver."""
        marcadas = [t for t in self._tabelas if t.principal]
        if marcadas:
            return marcadas[0]
        if not self._tabelas:
            return None
        return max(self._tabelas, key=lambda t: t.ultima - t.cabecalho)

    def _aba(self):
        partes = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                  '<worksheet xmlns="http://schemas.openxmlformats.org/'
                  'spreadsheetml/2006/main">']
        principal = self._principal
        if principal is not None and principal.ultima > principal.cabecalho:
            # Congelar o cabeçalho é o que faz a tabela continuar legível na linha 400.
            primeira = principal.cabecalho + 1
            partes.append(
                f'<sheetViews><sheetView workbookViewId="0">'
                f'<pane ySplit="{principal.cabecalho}" topLeftCell="A{primeira}" '
                f'activePane="bottomLeft" state="frozen"/>'
                f'<selection pane="bottomLeft" activeCell="A{primeira}" '
                f'sqref="A{primeira}"/></sheetView></sheetViews>')
        if self._larguras:
            colunas = "".join(
                f'<col min="{n + 1}" max="{n + 1}" width="{largura}" customWidth="1"/>'
                for n, largura in sorted(self._larguras.items()))
            partes.append(f"<cols>{colunas}</cols>")
        partes.append("<sheetData>")
        for numero, linha in enumerate(self._linhas, start=1):
            if not linha:
                continue
            celulas = "".join(self._xml_da_celula(_letra(n) + str(numero), c)
                              for n, c in enumerate(linha))
            partes.append(f'<row r="{numero}">{celulas}</row>')
        partes.append("</sheetData>")
        if principal is not None and principal.ultima > principal.cabecalho:
            fim = _letra(principal.colunas - 1)
            partes.append(f'<autoFilter ref="A{principal.cabecalho}:'
                          f'{fim}{principal.ultima}"/>')
        partes.append("</worksheet>")
        return "".join(partes)

    @staticmethod
    def _xml_da_celula(referencia, dado):
        if dado.numero is not None:
            return f'<c r="{referencia}" s="{dado.estilo}"><v>{dado.numero}</v></c>'
        if not dado.texto:
            return f'<c r="{referencia}" s="{dado.estilo}"/>'
        return (f'<c r="{referencia}" s="{dado.estilo}" t="inlineStr">'
                f"<is><t>{_escapar(dado.texto)}</t></is></c>")

    def bytes(self):
        """O arquivo .xlsx inteiro, pronto para ir na resposta."""
        saida = BytesIO()
        with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as zip_do_arquivo:
            for nome, conteudo in _PECAS.items():
                zip_do_arquivo.writestr(nome, conteudo)
            zip_do_arquivo.writestr("xl/styles.xml", _estilos(self._estilos.combinacoes))
            zip_do_arquivo.writestr("xl/worksheets/sheet1.xml", self._aba())
        return saida.getvalue()


def _estilos(combinacoes):
    """As fontes, os formatos de número e a tabela de estilos que a aba pediu.

    Só entram as combinações realmente usadas, na ordem em que foram pedidas: é essa
    ordem que o `s="..."` de cada célula aponta.
    """
    fontes = [
        # FONTE_PADRAO
        '<font><sz val="11"/><color rgb="FF1B1813"/><name val="Calibri"/></font>',
        # FONTE_TITULO
        '<font><b/><sz val="16"/><color rgb="FF7A3B12"/><name val="Calibri"/></font>',
        # FONTE_SUAVE
        '<font><sz val="10"/><color rgb="FF5C5449"/><name val="Calibri"/></font>',
        # FONTE_CABECALHO
        '<font><b/><sz val="10"/><color rgb="FF5C5449"/><name val="Calibri"/></font>',
        # FONTE_CELULA
        '<font><sz val="10"/><color rgb="FF1B1813"/><name val="Calibri"/></font>',
        # FONTE_NEGRITO
        '<font><b/><sz val="10"/><color rgb="FF1B1813"/><name val="Calibri"/></font>',
        # FONTE_DESTAQUE
        '<font><b/><sz val="12"/><color rgb="FF7A3B12"/><name val="Calibri"/></font>',
        # FONTE_ROTULO
        '<font><sz val="9"/><color rgb="FF5C5449"/><name val="Calibri"/></font>',
        # FONTE_VERMELHA
        '<font><sz val="10"/><color rgb="FFB32919"/><name val="Calibri"/></font>',
        # FONTE_MARROM
        '<font><sz val="10"/><color rgb="FF7A3B12"/><name val="Calibri"/></font>',
    ]
    formatos = [(NUMFMT[celula.DINHEIRO], celula.DINHEIRO),
                (NUMFMT[celula.INTEIRO], celula.INTEIRO),
                (NUMFMT[celula.DATA], celula.DATA)]

    def xf(fonte, numero, direita, borda):
        alinhamento = '<alignment horizontal="right"/>' if direita else ""
        aplica = ' applyNumberFormat="1"' if numero else ""
        aplica += ' applyAlignment="1"' if direita else ""
        aplica += ' applyBorder="1"' if borda else ""
        return (f'<xf numFmtId="{numero}" fontId="{fonte}" fillId="0" borderId="{borda}" '
                f'xfId="0" applyFont="1"{aplica}>{alinhamento}</xf>')

    # Sempre existe o estilo 0, mesmo numa planilha sem nenhuma célula: o Excel recusa
    # o arquivo com cellXfs vazio.
    usadas = list(combinacoes) or [(FONTE_PADRAO, GERAL, False, 0)]
    estilos = [xf(*chave) for chave in usadas]
    numfmts = "".join(f'<numFmt numFmtId="{i}" formatCode="{_escapar(c)}"/>'
                      for i, c in formatos)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<numFmts count="{len(formatos)}">{numfmts}</numFmts>'
        f'<fonts count="{len(fontes)}">{"".join(fontes)}</fonts>'
        '<fills count="2"><fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill></fills>'
        '<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border>'
        '<border><left/><right/><top/>'
        '<bottom style="thin"><color rgb="FFC9BCAB"/></bottom><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>'
        '</cellStyleXfs>'
        f'<cellXfs count="{len(estilos)}">{"".join(estilos)}</cellXfs>'
        '<cellStyles count="1">'
        '<cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'
    )


# As peças fixas do arquivo. Um .xlsx é um zip: estes quatro não mudam de relatório
# para relatório, então ficam escritos uma vez só.
_PECAS = {
    "[Content_Types].xml":
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.'
        'relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
    "_rels/.rels":
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
        'relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>',
    "xl/workbook.xml":
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Relatório" sheetId="1" r:id="rId1"/></sheets></workbook>',
    "xl/_rels/workbook.xml.rels":
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
        'relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/'
        '2006/relationships/styles" Target="styles.xml"/></Relationships>',
}


def resposta(planilha, nome_do_arquivo):
    """A resposta HTTP que baixa a planilha."""
    from django.http import HttpResponse

    http = HttpResponse(
        planilha.bytes(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    http["Content-Disposition"] = f'attachment; filename="{nome_do_arquivo}"'
    return http
