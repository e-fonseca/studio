"""Os feriados da loja, para a meta do dia.

A meta do Edson (02/11/2026) é por tipo de dia: "Sabado/Feriado 12.000,00" e "Domingo
18.000,00" (15 mil desde 04/11/2026). O sábado e o domingo o calendário diz; o feriado,
este arquivo.

Entram sozinhos, todo ano:

- os nacionais (Lei 662/1949 e as que a mudaram): 1º de janeiro, Tiradentes, 1º de maio,
  7 de setembro, Nossa Senhora Aparecida, Finados, 15 de novembro, Natal e, desde 2024,
  20 de novembro, Dia de Zumbi e da Consciência Negra (Lei 14.759/2023);
- o de São Paulo: 9 de julho (Lei estadual 9.497/1997);
- os de Embu das Artes, onde a loja fica: o aniversário da cidade (18 de fevereiro), a
  Sexta-feira da Paixão e Corpus Christi, como estão na lista de feriados municipais do
  Tribunal de Justiça de São Paulo (publicada pela OAB-SP para 2024).

A Paixão e Corpus Christi mudam de data com a Páscoa, que a função `pascoa` calcula.
Carnaval NÃO entra: em Embu é ponto facultativo, não feriado. O que faltar (Carnaval,
um dia de evento na cidade) a gerência põe na tela de regras, em "outros feriados", e a
meta passa a valer nele.
"""

import re
from datetime import date, timedelta

# (dia, mês, nome, desde que ano vale)
FIXOS = (
    (1, 1, "Confraternização Universal", None),
    (18, 2, "Aniversário de Embu das Artes", None),
    (21, 4, "Tiradentes", None),
    (1, 5, "Dia do Trabalho", None),
    (9, 7, "Revolução Constitucionalista (SP)", None),
    (7, 9, "Independência do Brasil", None),
    (12, 10, "Nossa Senhora Aparecida", None),
    (2, 11, "Finados", None),
    (15, 11, "Proclamação da República", None),
    (20, 11, "Dia de Zumbi e da Consciência Negra", 2024),
    (25, 12, "Natal", None),
)


def pascoa(ano):
    """O domingo de Páscoa do ano (algoritmo de Meeus/Jones/Butcher, calendário gregoriano)."""
    a = ano % 19
    b, c = divmod(ano, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes, dia = divmod(h + l - 7 * m + 114, 31)
    return date(ano, mes, dia + 1)


def do_ano(ano):
    """{data: nome} com os feriados que o sistema conhece no ano."""
    feriados = {}
    for dia, mes, nome, desde in FIXOS:
        if desde is None or ano >= desde:
            feriados[date(ano, mes, dia)] = nome
    domingo_de_pascoa = pascoa(ano)
    feriados[domingo_de_pascoa - timedelta(days=2)] = "Sexta-feira da Paixão"
    feriados[domingo_de_pascoa + timedelta(days=60)] = "Corpus Christi"
    return feriados


_LINHA = re.compile(r"^\s*(\d{1,2})\s*/\s*(\d{1,2})(?:\s*/\s*(\d{4}))?\s*(?:[-–:]\s*)?(.*)$")


def ler_outros(texto):
    """Lê a lista que a gerência escreveu: uma data por linha, com o nome se quiser.

    "20/01" vale todo ano; "16/02/2027 Carnaval" vale só aquele dia. Devolve duas coisas:
    as datas entendidas, como (dia, mês, ano ou None, nome), e as linhas que não deu para
    entender, para o formulário mostrar em vez de ignorar calado.
    """
    entendidas, erradas = [], []
    for linha in (texto or "").splitlines():
        if not linha.strip():
            continue
        achou = _LINHA.match(linha)
        if not achou:
            erradas.append(linha.strip())
            continue
        dia, mes, ano, nome = achou.groups()
        try:
            date(int(ano) if ano else 2024, int(mes), int(dia))  # 2024: aceita 29/02
        except ValueError:
            erradas.append(linha.strip())
            continue
        entendidas.append((int(dia), int(mes), int(ano) if ano else None,
                           nome.strip() or "Feriado da loja"))
    return entendidas, erradas


def feriados_entre(desde, ate, outros=""):
    """{data: nome} dos feriados de `desde` a `ate`, com os que a gerência escreveu.

    O que a gerência escreveu vence o nome do sistema no mesmo dia: se ela chamou o dia de
    outro jeito, é assim que a loja fala dele.
    """
    entendidas = ler_outros(outros)[0]
    feriados = {}
    for ano in range(desde.year, ate.year + 1):
        feriados.update(do_ano(ano))
        for dia, mes, so_no_ano, nome in entendidas:
            if so_no_ano is not None and so_no_ano != ano:
                continue
            try:
                feriados[date(ano, mes, dia)] = nome
            except ValueError:  # 29/02 escrito sem ano, num ano que não é bissexto
                continue
    return {dia: nome for dia, nome in feriados.items() if desde <= dia <= ate}


def tipo_de_dia(dia, feriados):
    """("domingo" | "sabado" | "feriado" | "", nome do feriado) para a meta do dia.

    `feriados` é o que `feriados_entre` devolve. Feriado que cai no domingo vale como
    domingo: a meta do domingo é a maior, e o movimento não cai porque também é feriado.
    """
    feriado = feriados.get(dia, "")
    if dia.weekday() == 6:
        return "domingo", feriado
    if dia.weekday() == 5:
        return "sabado", feriado
    if feriado:
        return "feriado", feriado
    return "", ""
