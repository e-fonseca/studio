"""Relatório em PDF, escrito aqui mesmo, sem biblioteca de fora.

Pedido do Edson em 13/10/2026: "CONTAS A PAGAR = Campo pesquisa, gerar relatorios para
impressao pdf".

Por que não usar uma biblioteca
-------------------------------
A biblioteca mais usada para isto (fpdf2) traz junto Pillow e fonttools: cerca de 12 MB
de extensões compiladas, para desenhar uma tabela de texto. O pacote da loja é instalado
**sem internet**, a partir das rodas (`wheels/`) que vão dentro do zip, e uma roda errada
já custou uma versão inteira (a 1.22.0 parou no meio e deixou a loja sem sistema).

Um PDF de tabela é um formato simples de escrever: um cabeçalho, alguns objetos
numerados, um fluxo de texto e a tabela de posições no fim. As fontes Helvetica e
Helvetica-Bold são as 14 que todo leitor de PDF já tem, então não é preciso embutir
arquivo de fonte nenhum — só dizer qual é a codificação (WinAnsi, que é a cp1252 e cobre
todo acento do português).

O que este módulo faz, e o que não faz
--------------------------------------
Faz: página A4 em pé ou deitado, título, linhas de texto, tabela com cabeçalho repetido
a cada página, coluna alinhada à esquerda ou à direita, zebra, rodapé com "página 1 de 3"
e a data de emissão. Não faz: imagem, cor fora do cinza e do marrom da loja, quebra de
linha dentro da célula (texto que não cabe é cortado com reticências). Nada disso faz
falta num relatório de contas, e cada coisa que não existe é uma coisa que não quebra.
"""

import unicodedata
from dataclasses import dataclass
from datetime import datetime

A4_RETRATO = (595.28, 841.89)
A4_PAISAGEM = (841.89, 595.28)

MARGEM_ESQUERDA = 40
MARGEM_DIREITA = 40
MARGEM_TOPO = 48
MARGEM_RODAPE = 42

NORMAL = "F1"
NEGRITO = "F2"

# Marrom do sistema (#7a3b12) e os cinzas, já em 0..1 como o PDF quer.
MARROM = (0.478, 0.231, 0.071)
PRETO = (0.11, 0.10, 0.09)
CINZA = (0.42, 0.40, 0.38)
RISCO = (0.85, 0.83, 0.80)
ZEBRA = (0.973, 0.965, 0.953)
VERMELHO = (0.70, 0.16, 0.10)


def _tabela_de_larguras(compacta):
    """Desdobra "A667 B667 C722" na tabela de larguras de uma fonte."""
    larguras = {}
    for pedaco in compacta.split():
        larguras[pedaco[0]] = int(pedaco[1:])
    return larguras


# Larguras oficiais da Helvetica, em milésimos do tamanho da letra. São elas que fazem a
# coluna de dinheiro ficar alinhada à direita de verdade e o texto ser cortado na hora
# certa. Letra com acento tem a largura da letra sem acento, então ela não entra aqui.
_COMUM = "026 156 \"355 #556 $556 %889 &667 '191 (333 )333 *389 +584 ,278 -333 .278 /278"
_DIGITOS = "0556 1556 2556 3556 4556 5556 6556 7556 8556 9556"
_HELVETICA = _tabela_de_larguras(
    " 278 !278 \"355 #556 $556 %889 &667 '191 (333 )333 *389 +584 ,278 -333 .278 /278 "
    + _DIGITOS
    + " :278 ;278 <584 =584 >584 ?556 @1015 A667 B667 C722 D722 E667 F611 G778 H722 I278"
    " J500 K667 L556 M833 N722 O778 P667 Q778 R722 S667 T611 U722 V667 W944 X667 Y667"
    " Z611 [278 \\278 ]278 ^469 _556 a556 b556 c500 d556 e556 f278 g556 h556 i222 j222"
    " k500 l222 m833 n556 o556 p556 q556 r333 s500 t278 u556 v500 w722 x500 y500 z500"
    " {334 |260 }334 ~584"
)
_HELVETICA_NEGRITO = _tabela_de_larguras(
    " 278 !333 \"474 #556 $556 %889 &722 '238 (333 )333 *389 +584 ,278 -333 .278 /278 "
    + _DIGITOS
    + " :333 ;333 <584 =584 >584 ?611 @975 A722 B722 C722 D722 E667 F611 G778 H722 I278"
    " J556 K722 L611 M833 N722 O778 P667 Q778 R722 S667 T611 U722 V667 W944 X667 Y667"
    " Z611 [333 \\278 ]333 ^584 _556 a556 b611 c556 d611 e556 f333 g611 h611 i278 j278"
    " k556 l278 m889 n611 o611 p611 q611 r389 s556 t333 u611 v556 w778 x556 y556 z500"
    " {389 |280 }389 ~584"
)
# Sinais da WinAnsi que não são letra acentuada e por isso não herdam largura nenhuma.
_EXTRAS = _tabela_de_larguras("—1000 –556 ·278 •350 ª370 º365 °400 §556 €556 «556 »556 ’222 ‘222 “333 ”333")
_EXTRAS_NEGRITO = dict(_EXTRAS, **_tabela_de_larguras("’278 ‘278 “500 ”500"))
_LARGURA_PADRAO = 556


def _sem_acento(letra):
    """A letra sem acento, para pegar a largura certa: 'Á' mede o mesmo que 'A'."""
    decomposta = unicodedata.normalize("NFKD", letra)
    base = "".join(c for c in decomposta if not unicodedata.combining(c))
    return base or letra


def medir(texto, tamanho, fonte=NORMAL):
    """Quanto este texto ocupa em pontos, nesta fonte e neste tamanho."""
    negrito = fonte == NEGRITO
    tabela = _HELVETICA_NEGRITO if negrito else _HELVETICA
    extras = _EXTRAS_NEGRITO if negrito else _EXTRAS
    total = 0
    for letra in texto or "":
        largura = tabela.get(letra, extras.get(letra))
        if largura is None:
            largura = tabela.get(_sem_acento(letra), _LARGURA_PADRAO)
        total += largura
    return total * tamanho / 1000


def cortar(texto, largura, tamanho, fonte=NORMAL):
    """Corta o texto para caber na largura, terminando em reticências."""
    texto = texto or ""
    if medir(texto, tamanho, fonte) <= largura:
        return texto
    reticencias = medir("...", tamanho, fonte)
    cabe = ""
    for letra in texto:
        if medir(cabe + letra, tamanho, fonte) + reticencias > largura:
            break
        cabe += letra
    return cabe.rstrip() + "..."


def _escapar(texto):
    """Texto na codificação WinAnsi (cp1252), com os três caracteres que o PDF reserva."""
    limpo = []
    for letra in texto or "":
        try:
            letra.encode("cp1252")
        except UnicodeEncodeError:
            letra = _sem_acento(letra)
            try:
                letra.encode("cp1252")
            except UnicodeEncodeError:
                letra = "?"
        limpo.append(letra)
    junto = "".join(limpo)
    for de, para in (("\\", r"\\"), ("(", r"\("), (")", r"\)")):
        junto = junto.replace(de, para)
    return junto


@dataclass
class Coluna:
    """Uma coluna da tabela. A largura é em pontos; 1 cm tem 28,35 pontos."""

    titulo: str
    largura: float
    direita: bool = False


class Relatorio:
    """Monta o PDF de cima para baixo, abrindo página nova quando a folha acaba."""

    def __init__(self, titulo, subtitulo="", paisagem=False, emitido_por=""):
        self.largura, self.altura = A4_PAISAGEM if paisagem else A4_RETRATO
        self.titulo = titulo
        self.subtitulo = subtitulo
        self.emitido_por = emitido_por
        self.emitido_em = datetime.now()
        self.paginas = []
        self._pagina = None
        self._y = 0
        self._nova_pagina()

    # -- folha ------------------------------------------------------------
    @property
    def _direita(self):
        return self.largura - MARGEM_DIREITA

    def _nova_pagina(self):
        self._pagina = []
        self.paginas.append(self._pagina)
        self._y = self.altura - MARGEM_TOPO
        if len(self.paginas) == 1:
            self._cabecalho()
        else:
            self._texto(self.titulo, MARGEM_ESQUERDA, self._y, 9, NEGRITO, CINZA)
            self._y -= 16

    def _cabecalho(self):
        self._texto("Studio Industrial", MARGEM_ESQUERDA, self._y, 9, NEGRITO, MARROM)
        self._y -= 20
        self._texto(self.titulo, MARGEM_ESQUERDA, self._y, 17, NEGRITO, PRETO)
        self._y -= 16
        if self.subtitulo:
            self._texto(self.subtitulo, MARGEM_ESQUERDA, self._y, 9.5, NORMAL, CINZA)
            self._y -= 14
        self._linha(self._y + 2)
        self._y -= 12

    def _cabe(self, altura):
        # O chão é o rodapé inteiro: o risco fica 14 acima da linha de base dele.
        return self._y - altura >= MARGEM_RODAPE + 26

    # -- desenhos ---------------------------------------------------------
    def _texto(self, texto, x, y, tamanho, fonte=NORMAL, cor=PRETO):
        r, g, b = cor
        self._pagina.append(
            f"BT {r:.3f} {g:.3f} {b:.3f} rg /{fonte} {tamanho} Tf "
            f"1 0 0 1 {x:.2f} {y:.2f} Tm ({_escapar(texto)}) Tj ET"
        )

    def _texto_a_direita(self, texto, direita, y, tamanho, fonte=NORMAL, cor=PRETO):
        self._texto(texto, direita - medir(texto, tamanho, fonte), y, tamanho, fonte, cor)

    def _linha(self, y, cor=RISCO, espessura=0.7):
        r, g, b = cor
        self._pagina.append(
            f"{r:.3f} {g:.3f} {b:.3f} RG {espessura} w "
            f"{MARGEM_ESQUERDA} {y:.2f} m {self._direita:.2f} {y:.2f} l S"
        )

    def _retangulo(self, x, y, largura, altura, cor):
        r, g, b = cor
        self._pagina.append(
            f"{r:.3f} {g:.3f} {b:.3f} rg {x:.2f} {y:.2f} {largura:.2f} {altura:.2f} re f"
        )

    # -- blocos -----------------------------------------------------------
    def paragrafo(self, texto, tamanho=9.5, fonte=NORMAL, cor=PRETO, espaco=6):
        """Uma linha de texto. Texto comprido demais para a folha é cortado."""
        if not self._cabe(tamanho + espaco):
            self._nova_pagina()
        largura = self.largura - MARGEM_ESQUERDA - MARGEM_DIREITA
        self._y -= tamanho
        self._texto(cortar(texto, largura, tamanho, fonte), MARGEM_ESQUERDA, self._y,
                    tamanho, fonte, cor)
        self._y -= espaco

    def espaco(self, quanto=10):
        self._y -= quanto

    def destaques(self, pares, tamanho=10):
        """Os números do topo, lado a lado: [("Em aberto", Dinheiro(10)), ...].

        O valor pode vir como texto ou como um envelope de `apps.core.celula`: aqui
        ele sempre vira texto, e é a planilha que aproveita o número de dentro.
        """
        if not self._cabe(34):
            self._nova_pagina()
        largura = (self.largura - MARGEM_ESQUERDA - MARGEM_DIREITA) / max(len(pares), 1)
        topo = self._y
        for posicao, (rotulo, valor) in enumerate(pares):
            x = MARGEM_ESQUERDA + posicao * largura
            self._texto(cortar(str(rotulo), largura - 8, 8, NORMAL), x, topo - 9,
                        8, NORMAL, CINZA)
            self._texto(cortar(str(valor), largura - 8, 13, NEGRITO), x, topo - 25,
                        13, NEGRITO, MARROM)
        self._y = topo - 34
        self._linha(self._y + 6)
        self._y -= 8

    def tabela(self, colunas, linhas, altura_da_linha=15, tamanho=8.5, zebra=True,
               principal=False):
        """A tabela. Cada linha é uma lista de textos, de (texto, cor) ou de envelopes.

        O cabeçalho se repete em toda página: quem imprime separa as folhas.

        `principal` marca a tabela que a pessoa veio ler. No papel não muda nada — a
        folha não filtra nem ordena —, mas o mesmo montador serve a planilha, e lá é
        essa tabela que ganha o cabeçalho congelado e o filtro (apps/core/planilha.py).
        Aceitar e ignorar aqui é o que permite existir um montador só.
        """
        self._cabecalho_da_tabela(colunas, tamanho)
        for posicao, linha in enumerate(linhas):
            if not self._cabe(altura_da_linha):
                self._nova_pagina()
                self._cabecalho_da_tabela(colunas, tamanho)
                posicao = 0
            self._y -= altura_da_linha
            if zebra and posicao % 2:
                # A faixa vai embaixo do texto desta linha, nunca da linha de cima.
                self._retangulo(MARGEM_ESQUERDA - 3, self._y - 4,
                                self.largura - MARGEM_ESQUERDA - MARGEM_DIREITA + 6,
                                altura_da_linha, ZEBRA)
            self._celulas(colunas, linha, tamanho, NORMAL)
        self._linha(self._y - 2)
        self._y -= 10

    def _cabecalho_da_tabela(self, colunas, tamanho):
        if not self._cabe(26):
            self._nova_pagina()
        self._y -= 12
        self._celulas(colunas, [(c.titulo, CINZA) for c in colunas], tamanho - 0.5, NEGRITO)
        self._linha(self._y - 4, cor=RISCO, espessura=0.9)
        self._y -= 4

    def _celulas(self, colunas, linha, tamanho, fonte):
        from apps.core import celula  # noqa: PLC0415 - celula importa o reais daqui de baixo

        x = MARGEM_ESQUERDA
        for coluna, bruto in zip(colunas, linha):
            texto, cor = celula.texto_e_cor(bruto, PRETO)
            texto = cortar(texto, coluna.largura - 6, tamanho, fonte)
            if coluna.direita:
                self._texto_a_direita(texto, x + coluna.largura - 6, self._y, tamanho, fonte, cor)
            else:
                self._texto(texto, x, self._y, tamanho, fonte, cor)
            x += coluna.largura

    def pagina_nova(self):
        """Começa a folha seguinte agora, sem esperar esta encher.

        Existe para o papel que se separa e se entrega em partes: um pedido por
        fornecedor, cada um na sua folha. Quem chama é responsável por já ter escrito
        algo nesta página, senão sai uma folha em branco no meio do maço.
        """
        self._nova_pagina()

    def total(self, rotulo, valor):
        """A linha de soma, no fim da tabela. O valor pode ser texto ou envelope."""
        if not self._cabe(22):
            self._nova_pagina()
        self._y -= 16
        self._texto(str(rotulo), MARGEM_ESQUERDA, self._y, 10, NEGRITO, PRETO)
        self._texto_a_direita(str(valor), self._direita, self._y, 11, NEGRITO, MARROM)
        self._y -= 8

    # -- fechamento -------------------------------------------------------
    def _rodape_das_paginas(self):
        quantas = len(self.paginas)
        emitido = self.emitido_em.strftime("%d/%m/%Y às %H:%M")
        for numero, pagina in enumerate(self.paginas, start=1):
            self._pagina = pagina
            self._linha(MARGEM_RODAPE + 14)
            esquerda = f"Studio Industrial · sistema auxiliar ao SET · emitido em {emitido}"
            if self.emitido_por:
                esquerda += f" por {self.emitido_por}"
            self._texto(esquerda, MARGEM_ESQUERDA, MARGEM_RODAPE, 7.5, NORMAL, CINZA)
            self._texto_a_direita(f"página {numero} de {quantas}", self._direita,
                                  MARGEM_RODAPE, 7.5, NORMAL, CINZA)

    def bytes(self):
        """O arquivo PDF inteiro, pronto para ir na resposta."""
        self._rodape_das_paginas()
        objetos = []           # cada posição é o corpo de um objeto, na ordem
        total = len(self.paginas)
        # 1 catálogo, 2 árvore de páginas, 3 e 4 as fontes, depois página e conteúdo aos pares
        objetos.append("<< /Type /Catalog /Pages 2 0 R >>")
        filhos = " ".join(f"{5 + 2 * i} 0 R" for i in range(total))
        objetos.append(f"<< /Type /Pages /Count {total} /Kids [{filhos}] >>")
        for numero, nome in ((3, "Helvetica"), (4, "Helvetica-Bold")):
            objetos.append(
                f"<< /Type /Font /Subtype /Type1 /BaseFont /{nome} /Encoding /WinAnsiEncoding >>"
            )
        corpos = []
        for i, pagina in enumerate(self.paginas):
            conteudo = 6 + 2 * i
            objetos.append(
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {self.largura:.2f} {self.altura:.2f}] "
                f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {conteudo} 0 R >>"
            )
            # cp1252 e não latin-1: é a WinAnsi que a fonte declara, e é ela que tem travessão.
            fluxo = "\n".join(pagina).encode("cp1252", "replace")
            objetos.append(None)   # marcador: o fluxo entra na hora de escrever
            corpos.append(fluxo)

        saida = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        posicoes = []
        fluxo_atual = 0
        for numero, corpo in enumerate(objetos, start=1):
            posicoes.append(len(saida))
            if corpo is None:
                dados = corpos[fluxo_atual]
                fluxo_atual += 1
                saida += f"{numero} 0 obj\n<< /Length {len(dados)} >>\nstream\n".encode("latin-1")
                saida += dados
                saida += b"\nendstream\nendobj\n"
            else:
                saida += f"{numero} 0 obj\n{corpo}\nendobj\n".encode("latin-1")
        inicio_xref = len(saida)
        saida += f"xref\n0 {len(objetos) + 1}\n".encode("latin-1")
        saida += b"0000000000 65535 f \n"
        for posicao in posicoes:
            saida += f"{posicao:010d} 00000 n \n".encode("latin-1")
        saida += (
            f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\n"
            f"startxref\n{inicio_xref}\n%%EOF\n"
        ).encode("latin-1")
        return bytes(saida)


def resposta(relatorio, nome_do_arquivo):
    """A resposta HTTP que abre o PDF no navegador, de onde dá para imprimir."""
    from django.http import HttpResponse

    http = HttpResponse(relatorio.bytes(), content_type="application/pdf")
    http["Content-Disposition"] = f'inline; filename="{nome_do_arquivo}"'
    return http
