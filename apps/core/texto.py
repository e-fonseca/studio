"""Conserto de texto que foi gravado com a tabela de caracteres errada.

Acontece quando um texto em UTF-8 é lido como cp1252: "São Paulo" vira "SÃ£o Paulo".
A importação já não erra mais isso (apps/importacao/fontes/firebird.py tenta UTF-8
antes de cp1252), mas o que a gerência digitou ou salvou antes da correção continua
torto no banco, e esses registros não são refeitos por nenhuma importação.

O conserto é o caminho de volta: escrever de novo em cp1252 e ler em UTF-8. Só vale
quando dá certo e muda alguma coisa; texto certo não tem como ser remontado assim,
porque acento em cp1252 quase nunca forma UTF-8 válido.
"""

# Letras que só aparecem em texto torto; sem uma delas não há o que consertar.
MARCAS = ("Ã", "Â", "â€", "Ã‚")


def consertar(texto):
    if not texto or not any(marca in texto for marca in MARCAS):
        return texto
    try:
        arrumado = texto.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return texto
    return arrumado or texto


# ---------------------------------------------------------------------------
# Procurar sem tropeçar em acento
# ---------------------------------------------------------------------------
#
# O nome do fornecedor vem do SET como está lá: "QUITÉRIA FLOR MILHO". Quem procura
# digita "quiteria", sem acento, porque é o que se digita. Um `icontains` não acha.
#
# A saída que não acrescenta dependência nem extensão do Postgres é procurar por uma
# expressão regular em que cada letra vale por ela e pelas suas acentuadas: "quiteria"
# vira `qu[iíìîï]t[eéèêë]r[aáàâãä]`. Funciona com `iregex`, que o Postgres e o SQLite
# entendem, e aceita que a pessoa digite com ou sem acento.

_FAMILIAS = {
    "a": "aáàâãäÁÀÂÃÄ", "e": "eéèêëÉÈÊË", "i": "iíìîïÍÌÎÏ", "o": "oóòôõöÓÒÔÕÖ",
    "u": "uúùûüÚÙÛÜ", "c": "cçÇ", "n": "nñÑ", "y": "yýÿÝ",
}
# Caminho de volta: quem digitou COM acento procura a família da letra sem acento.
_SEM_ACENTO = {letra: base for base, letras in _FAMILIAS.items() for letra in letras}


def sem_acento(texto):
    """O texto em maiúsculas e sem acento, para comparar duas pontas em Python.

    `regex_sem_acento` serve à consulta no banco; esta serve quando a lista já está
    na memória — o resumo de fornecedores, por exemplo, que nasce de um agrupamento
    em Python e não de uma tabela. As duas usam a MESMA tabela de famílias de letras,
    senão a busca da tela e a do autopreenchimento discordariam sobre "QUITÉRIA".
    """
    return "".join(_SEM_ACENTO.get(letra, letra) for letra in (texto or "")).upper()


def regex_sem_acento(termo):
    """Monta a expressão regular que acha o termo com acento ou sem.

    Devolve "" quando não há o que procurar, para quem chama poder pular o filtro.
    """
    termo = (termo or "").strip()
    if not termo:
        return ""
    pedacos = []
    for letra in termo:
        base = _SEM_ACENTO.get(letra, letra.lower())
        familia = _FAMILIAS.get(base)
        if familia:
            # A maiúscula sem acento entra pelo `iregex`, que já ignora caixa.
            pedacos.append("[" + familia + base.upper() + "]")
        elif letra.isalnum():
            pedacos.append(letra)
        else:
            # Ponto, barra, hífen e espaço entram como texto, não como regra.
            pedacos.append("\\" + letra if letra in "\\^$.|?*+()[]{}" else letra)
    return "".join(pedacos)
