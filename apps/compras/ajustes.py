"""A quantidade que a gerência acrescenta à que o sistema calculou.

Pedido do Edson em 14/10/2026: "no recurso de sugestão de compra permitir edição da
quantidade, manter a sugestão, porém permitir editar a quantidade". E em 20/10/2026,
mais preciso: *"no campo de quantidade sugerida, adicionar quantidade manual, com a
soma dois campos gera a quantidade total de cada produto por fornecedor"*. São duas
parcelas e um total, e é por isso que o que se guarda é a PARCELA, não o total.

Três decisões que valem a pena ficar escritas:

1. **O banco guarda a parcela da mão, não o total.** Quem acrescenta 5 unidades porque
   um cliente encomendou quer 5 unidades a mais do que o sistema achar certo — hoje e
   na sincronização das 19:30, quando a sugestão já tiver mudado. Guardar o total faria
   o número envelhecer calado: a conta andaria de 10 para 14 e o pedido continuaria
   saindo com os 15 pensados para outra situação.
2. **"Não comprar agora" é campo próprio, não a parcela que zera.** Antes era digitar 0
   no total; com a soma isso deixou de funcionar, porque menos 10 só zera enquanto a
   sugestão for 10. O `nao_comprar` tira a linha do pedido e continua tirando.
3. **O ajuste casa pelo código do SET**, não por chave estrangeira: a foto do SET é
   apagada e refeita a cada sincronização, e o que a gerência decidiu tem de
   sobreviver a isso.
"""

from decimal import Decimal, InvalidOperation

from apps.compras.models import AjusteDeCompra

ZERO = Decimal("0")
# Teto de sanidade, não regra de negócio: acima disto é dedo escorregando no teclado,
# e um milhão de unidades de uma peça de decoração não existe nesta loja.
MAXIMO = Decimal("999999")
CASAS = Decimal("0.001")


class ErroDeAjuste(Exception):
    """Mensagem pronta para a tela: o que está errado e o que fazer."""


def _normalizar(bruto):
    """Transforma o que a pessoa digitou no número que o Python entende.

    Em português o ponto separa milhar e a vírgula separa centavo, mas quem copia de
    outra tela traz das duas formas. A regra: vírgula presente manda, e o ponto é
    milhar; ponto sozinho é separador de casa decimal, porque esta loja não compra
    mil unidades de uma peça e "2.5" quase sempre quer dizer duas e meia.
    """
    limpo = (bruto or "").strip().replace(" ", "")
    if "," in limpo:
        return limpo.replace(".", "").replace(",", ".")
    return limpo


def quantidade_informada(bruto):
    """Aceita 12, 12,5 e 12.5; recusa texto e número fora de pé.

    É o total, e por isso não aceita negativo: usada onde a pessoa escreve quantas
    unidades vão no papel (a tela do pedido guardado). A loja digita com vírgula, e
    quem copia da tela do SET às vezes traz ponto. Os dois valem, porque recusar a
    vírgula seria recusar a forma como se escreve número em português.
    """
    limpo = _normalizar(bruto)
    if not limpo:
        raise ErroDeAjuste("Escreva quantas unidades comprar, como 12 ou 2,5. "
                           "Para voltar à sugestão do sistema, use o botão ao lado.")
    try:
        valor = Decimal(limpo)
    except (InvalidOperation, ValueError):
        raise ErroDeAjuste("A quantidade tem que ser um número, como 12 ou 2,5.")
    if valor < ZERO:
        raise ErroDeAjuste("A quantidade não pode ser negativa. Para não comprar este "
                           "produto agora, escreva 0.")
    if valor > MAXIMO:
        raise ErroDeAjuste("Essa quantidade é maior do que a loja compra de uma vez. "
                           "Confira se não sobrou um dígito.")
    return valor.quantize(CASAS)


def parcela_informada(bruto):
    """A quantidade da mão, que SOMA com a sugerida. Aceita negativo e vazio.

    Negativo é "comprar menos do que o sistema pediu" e é tão legítimo quanto o
    positivo: quem conhece o produto às vezes sabe que a venda do ano passado não se
    repete. Campo vazio é zero, porque é o que a pessoa quer dizer ao limpar o campo —
    siga a conta do sistema.
    """
    limpo = _normalizar(bruto)
    if not limpo or limpo in {"-", "+"}:
        return ZERO
    try:
        valor = Decimal(limpo)
    except (InvalidOperation, ValueError):
        raise ErroDeAjuste("A quantidade a mais tem que ser um número, como 5, 2,5 "
                           "ou -3 para comprar menos.")
    if abs(valor) > MAXIMO:
        raise ErroDeAjuste("Essa quantidade é maior do que a loja compra de uma vez. "
                           "Confira se não sobrou um dígito.")
    return valor.quantize(CASAS)


def _decimal(valor):
    """A sugestão do sistema como número, venha ela do banco ou do formulário.

    Passa pelo mesmo normalizador do campo digitado porque o Django escreve decimal
    localizado no HTML ("12,000") e o que volta no POST é texto. Valor que não dá
    número vira zero: a sugestão é só referência, e perder o ajuste por causa dela
    seria pior do que gravá-lo com a referência vazia.
    """
    if valor is None:
        return ZERO
    if isinstance(valor, Decimal):
        return valor
    try:
        return Decimal(_normalizar(str(valor)) or "0")
    except (InvalidOperation, ValueError):
        return ZERO


def total(sugerida, a_mais, nao_comprar=False):
    """A soma dos dois campos, que é o que vai no pedido. Nunca abaixo de zero.

    A mesma conta mora em `AjusteDeCompra.total_com`; esta existe para a linha SEM
    ajuste nenhum poder usar a mesma régua sem inventar um objeto no banco.
    """
    if nao_comprar:
        return ZERO
    soma = _decimal(sugerida) + _decimal(a_mais)
    return soma if soma > ZERO else ZERO


def salvar(*, codigo, a_mais, sugerida, nao_comprar=False, usuario=None, observacao=""):
    """Grava a quantidade que a mão acrescenta à sugestão de um produto.

    Devolve `(ajuste, total)`. Parcela zero sem "não comprar" APAGA o ajuste: linha que
    acrescenta nada só serviria para inflar o contador de "mudadas à mão" e fazer a
    pessoa procurar diferença onde não há.
    """
    codigo = (codigo or "").strip()
    if not codigo:
        raise ErroDeAjuste("Produto não informado.")
    parcela = parcela_informada(a_mais)
    sugerida = _decimal(sugerida)
    nao_comprar = bool(nao_comprar)
    if nao_comprar:
        parcela = ZERO
    elif parcela == ZERO:
        limpar(codigo)
        return None, sugerida
    ajuste, _ = AjusteDeCompra.objects.update_or_create(
        codigo=codigo[:60],
        defaults={
            "a_mais": parcela,
            "nao_comprar": nao_comprar,
            "quantidade": total(sugerida, parcela, nao_comprar),
            "sugerida": sugerida,
            "observacao": (observacao or "").strip()[:200],
            "ajustado_por": usuario if getattr(usuario, "is_authenticated", False) else None,
        },
    )
    return ajuste, ajuste.quantidade


def escolhida_antes(codigo):
    """O ajuste que está gravado para este produto, ou None.

    Serve para a trilha de auditoria registrar de QUE número se mudou: o ajuste é
    sobrescrito a cada edição (`update_or_create`), então quem não lê antes de gravar
    perde o valor anterior para sempre.
    """
    codigo = (codigo or "").strip()
    if not codigo:
        return None
    return AjusteDeCompra.objects.filter(codigo=codigo).first()


def limpar(codigo):
    """Tira o ajuste e devolve a linha para a conta do sistema. Devolve quantos saíram."""
    codigo = (codigo or "").strip()
    if not codigo:
        return 0
    apagados, _ = AjusteDeCompra.objects.filter(codigo=codigo).delete()
    return apagados


def quantos():
    """Quantas linhas da loja têm quantidade escolhida à mão, para a tela dizer."""
    return AjusteDeCompra.objects.count()
