"""Desenho do código de barras EAN-13, em SVG, sem depender de nada de fora.

O servidor da loja não acessa a internet, então nada de biblioteca baixada na hora nem
imagem gerada por serviço: o desenho sai daqui, em SVG, e vai direto no HTML da página.

O SET gera um EAN-13 próprio para quase todo produto e é esse número que vai impresso na
etiqueta da prateleira. Desenhar o mesmo código na tela serve para conferir a etiqueta a
olho e para o leitor ler da tela quando a etiqueta do produto está rasgada.

EAN-13 em uma frase: treze dígitos, o primeiro não é desenhado em barra nenhuma — ele é
quem escolhe, para cada um dos seis dígitos seguintes, se a codificação é a tabela L ou a
G. Os seis últimos usam sempre a tabela R. No meio e nas pontas vão as barras de guarda.
"""

# Cada dígito vira sete módulos. 1 é barra, 0 é espaço.
L = ("0001101", "0011001", "0010011", "0111101", "0100011",
     "0110001", "0101111", "0111011", "0110111", "0001011")
G = ("0100111", "0110011", "0011011", "0100001", "0011101",
     "0111001", "0000101", "0010001", "0001001", "0010111")
R = tuple("".join("1" if c == "0" else "0" for c in codigo) for codigo in L)
# Qual tabela usar em cada um dos seis dígitos da esquerda, conforme o primeiro dígito.
PARIDADE = ("LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG",
            "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL")
GUARDA = "101"
MEIO = "01010"

LARGURA_MODULO = 2
ALTURA_BARRA = 54
ALTURA_GUARDA = 60
MARGEM = 11  # a norma pede área clara dos dois lados, senão o leitor erra
ALTURA_TOTAL = 78


def digito_verificador(doze):
    """O décimo terceiro dígito do EAN-13, calculado a partir dos doze primeiros."""
    soma = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(doze))
    return str((10 - soma % 10) % 10)


def valido(codigo):
    """Verdadeiro quando o código tem treze dígitos e o verificador fecha."""
    codigo = (codigo or "").strip()
    return (
        len(codigo) == 13
        and codigo.isdigit()
        and digito_verificador(codigo[:12]) == codigo[12]
    )


def _modulos(codigo):
    primeiro, esquerda, direita = codigo[0], codigo[1:7], codigo[7:]
    paridade = PARIDADE[int(primeiro)]
    partes = [GUARDA]
    for tabela, digito in zip(paridade, esquerda):
        partes.append((L if tabela == "L" else G)[int(digito)])
    partes.append(MEIO)
    partes.extend(R[int(d)] for d in direita)
    partes.append(GUARDA)
    return "".join(partes)


def _e_guarda(posicao):
    """As barras de guarda descem um pouco mais, como na etiqueta impressa."""
    return posicao < 3 or 45 <= posicao < 50 or posicao >= 92


def svg(codigo, titulo=None):
    """O código em SVG, ou None quando o número não é um EAN-13 de verdade.

    Quem chama decide o que fazer com o None: a tela mostra só o número, porque um
    desenho errado é pior do que desenho nenhum — o leitor leria outra coisa.
    """
    codigo = (codigo or "").strip()
    if not valido(codigo):
        return None

    modulos = _modulos(codigo)
    largura = MARGEM * 2 + len(modulos) * LARGURA_MODULO
    barras = []
    for posicao, modulo in enumerate(modulos):
        if modulo != "1":
            continue
        altura = ALTURA_GUARDA if _e_guarda(posicao) else ALTURA_BARRA
        x = MARGEM + posicao * LARGURA_MODULO
        barras.append(f'<rect x="{x}" y="4" width="{LARGURA_MODULO}" height="{altura}"/>')

    # Os números vão embaixo, na mesma divisão da etiqueta: o primeiro dígito fora,
    # seis à esquerda do meio e seis à direita.
    meio_x = MARGEM + 50 * LARGURA_MODULO
    textos = [
        f'<text x="{MARGEM - 3}" y="{ALTURA_TOTAL - 4}" text-anchor="end">{codigo[0]}</text>',
        f'<text x="{MARGEM + 25 * LARGURA_MODULO}" y="{ALTURA_TOTAL - 4}" text-anchor="middle" '
        f'letter-spacing="2">{codigo[1:7]}</text>',
        f'<text x="{meio_x + 25 * LARGURA_MODULO}" y="{ALTURA_TOTAL - 4}" text-anchor="middle" '
        f'letter-spacing="2">{codigo[7:]}</text>',
    ]
    rotulo = titulo or f"Código de barras {codigo}"
    return (
        f'<svg class="codigo-de-barras" viewBox="0 0 {largura} {ALTURA_TOTAL}" '
        f'width="{largura}" height="{ALTURA_TOTAL}" role="img" aria-label="{rotulo}" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<rect class="fundo" width="{largura}" height="{ALTURA_TOTAL}"/>'
        f'<g class="barras">{"".join(barras)}</g>'
        f'<g class="numeros" font-size="13" font-family="monospace">{"".join(textos)}</g>'
        f"</svg>"
    )


def variantes(codigo):
    """Os jeitos em que o mesmo código de barras pode chegar, para procurar por todos.

    O leitor pela câmera devolve um EAN-13 que começa com zero como UPC-A de 12
    dígitos, sem o zero da frente: o código 0000000000024 do SET volta como
    000000000024. Como TODOS os códigos que o SET gerou para a loja começam com
    zero, sem esta conversão a busca pela câmera não acharia produto nenhum.

    Devolve sempre o que foi lido em primeiro lugar, e depois as variações, sem
    repetir. Texto que não é só dígito volta sozinho, porque aí não é código de
    barras e sim nome ou código do produto.
    """
    lido = (codigo or "").strip()
    if not lido:
        return []
    if not lido.isdigit():
        return [lido]
    formas = [lido]
    if len(lido) == 12:
        formas.append("0" + lido)
    elif len(lido) == 13 and lido.startswith("0"):
        formas.append(lido[1:])
    return formas
