"""CPF: limpeza, conferência dos dígitos e formatação.

Conferir o CPF aqui evita o erro bobo de digitação no cadastro de quem usa o sistema.
Não é consulta a lugar nenhum: é a conta dos dois dígitos verificadores, que é o que dá
para fazer sem internet e é o que pega quase todo engano de quem digita.
"""

import re

SO_NUMEROS = re.compile(r"\D")


def limpar(cpf):
    return SO_NUMEROS.sub("", cpf or "")


def _digito(numeros, peso_inicial):
    soma = sum(int(d) * peso for d, peso in zip(numeros, range(peso_inicial, 1, -1)))
    resto = soma * 10 % 11
    return "0" if resto == 10 else str(resto)


def valido(cpf):
    numeros = limpar(cpf)
    if len(numeros) != 11 or numeros == numeros[0] * 11:
        return False
    return numeros[9] == _digito(numeros[:9], 10) and numeros[10] == _digito(numeros[:10], 11)


def formatar(cpf):
    numeros = limpar(cpf)
    if len(numeros) != 11:
        return cpf or ""
    return f"{numeros[:3]}.{numeros[3:6]}.{numeros[6:9]}-{numeros[9:]}"
