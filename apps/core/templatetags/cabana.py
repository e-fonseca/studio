from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django import template
from django.utils.safestring import mark_safe

from apps.core import barras

register = template.Library()


@register.filter
def reais(valor, vazio="—"):
    """Formata em reais no padrão brasileiro: R$ 1.234,56."""
    if valor is None or valor == "":
        return vazio
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return vazio
    # O sinal vem antes do R$, como se escreve em português: -R$ 335,91, nunca R$ -335,91.
    sinal = "-" if numero < 0 else ""
    texto = f"{abs(numero):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sinal}R$ {texto}"


@register.filter
def reais_redondo(valor, vazio="—"):
    """Reais redondos, sem o símbolo e sem os centavos: 122.400 em vez de R$ 122.399,52.

    Para a tabela que tem que caber inteira no celular: a do gráfico de anos de Contas a
    pagar (1.48.0) tem três anos e a variação lado a lado, e com R$ e centavos a variação,
    que é a coluna que decide, saía da tela. O valor exato continua no computador.
    """
    if valor is None or valor == "":
        return vazio
    try:
        numero = Decimal(str(valor)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return vazio
    sinal = "-" if numero < 0 else ""
    return f"{sinal}{abs(numero):,}".replace(",", ".")


@register.filter
def quantidade(valor, vazio="—"):
    """Quantidade sem casas decimais inúteis: 12 em vez de 12,000."""
    if valor is None or valor == "":
        return vazio
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return vazio
    texto = f"{numero:f}"
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return texto.replace(".", ",")


@register.filter
def com_sinal(valor, vazio=""):
    """A parcela da soma com o sinal na frente: +5, -3.

    Serve a quantidade que SOMA com outra (a da mão na lista de compra). Sem o sinal,
    "sugerida 14 · 3 à mão" não diz se são três a mais ou três a menos — e a diferença
    é um pedido errado ao fornecedor.
    """
    if valor is None or valor == "":
        return vazio
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return vazio
    if numero == 0:
        return vazio
    return f"+{quantidade(numero)}" if numero > 0 else quantidade(numero)


@register.filter
def contagem(valor, vazio="—"):
    """Número inteiro com ponto de milhar: 16.361 em vez de 16361.

    Para contagem (vendas, produtos, clientes). Dinheiro continua no `reais`, e
    quantidade com casas decimais, no `quantidade`.
    """
    if valor is None or valor == "":
        return vazio
    try:
        numero = int(Decimal(str(valor)))
    except (InvalidOperation, ValueError, TypeError):
        return vazio
    return f"{numero:,}".replace(",", ".")


@register.filter
def nome_pessoa(usuario, vazio="a definir"):
    """Nome completo, ou usuário, ou o texto para quando não há pessoa definida."""
    if usuario is None:
        return vazio
    return usuario.get_full_name() or usuario.get_username()


@register.filter
def codigo_de_barras(valor):
    """Desenha o código de barras do produto, ou devolve vazio quando não dá para desenhar.

    Número que não é um EAN-13 válido não vira desenho nenhum: um código de barras
    desenhado errado é pior do que nenhum, porque o leitor leria outra coisa.
    """
    desenho = barras.svg(valor)
    return mark_safe(desenho) if desenho else ""


@register.filter
def reais_com_sinal(valor):
    """Dinheiro que pode faltar: "+ R$ 1.200,00" ou "− R$ 300,00" (Fluxo de caixa, Studio).

    O sinal escrito, e não só a cor: o mês em que vai faltar tem de ser lido também por
    quem não distingue o vermelho, e no papel impresso em preto e branco.
    """
    if valor is None or valor == "":
        return "—"
    numero = Decimal(str(valor))
    if numero == 0:
        return reais(numero)
    return ("+ " if numero > 0 else "− ") + reais(abs(numero))


@register.filter
def percentual(fracao, casas=1):
    """Uma fração como porcentagem brasileira: 0.375 vira "37,5%" (Planejamento, Studio)."""
    if fracao is None or fracao == "":
        return "—"
    numero = (Decimal(str(fracao)) * 100).quantize(Decimal(1).scaleb(-int(casas)), rounding=ROUND_HALF_UP)
    return f"{numero}".replace(".", ",") + "%"
