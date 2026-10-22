"""Como o sistema procura texto digitado: sem acento, e com o mais provável em cima.

O Edson pediu em 14/10/2026 "a melhor tecnologia de auto completar no campo de
procurar", citando Algolia e Luigi's Box. São serviços de nuvem: mandam o texto
procurado para fora, cobram por busca e exigem internet na hora em que a pessoa
digita. Nada disso serve aqui — o nome do fornecedor e do cliente não sai do
servidor da loja, e nenhuma tela deste sistema depende da internet.

O que faz diferença numa loja com 11.274 produtos e 2.628 fornecedores não é o
tamanho do motor, é **a ordem**. Quem digita "cad" quer CADEIRA, não
PORTA-CADERNO; quem digita "qui" quer QUITÉRIA, mesmo sem o acento. Então:

1. **sem acento nos dois sentidos** — `quiteria` acha `QUITÉRIA`, pelo mesmo
   `regex_sem_acento` que a busca de contas já usa;
2. **começo vale mais que meio** — o que COMEÇA com o que foi digitado vem antes
   do que começa uma palavra no meio, que vem antes do que só contém;
3. **desempate por quem vende** — entre dois produtos igualmente parecidos, o que
   saiu da prateleira no ano aparece primeiro. É quem quase sempre se procura.

Isso roda no PostgreSQL da própria loja, numa consulta, sem extensão a instalar.
`pg_trgm` (que daria tolerância a erro de digitação) foi considerado e ficou de
fora: `CREATE EXTENSION` exige superusuário, o papel `cabana_app` não é, e mexer
no instalador para isso custa mais do que a tolerância vale com 11 mil linhas.
"""

from django.db.models import Case, IntegerField, Q, When

from apps.core.texto import regex_sem_acento

# Quantas sugestões a lista mostra. Mais do que isto não cabe na tela do celular e
# ninguém lê: a pessoa prefere digitar mais uma letra a rolar uma lista.
QUANTAS = 8

# Letra ou número, na gramática de expressão regular do PostgreSQL. Serve para achar
# começo de palavra sem depender de \b, que o Postgres escreve de outro jeito.
_NAO_E_LETRA = "[^[:alnum:]]"


def filtro(termo, *campos):
    """O `Q` que acha o termo em qualquer um dos campos, com acento ou sem."""
    padrao = regex_sem_acento(termo)
    if not padrao:
        return Q()
    procura = Q()
    for campo in campos:
        procura |= Q(**{f"{campo}__iregex": padrao})
    return procura


def por_relevancia(consulta, termo, *campos, desempate=()):
    """Ordena a consulta pondo na frente o que COMEÇA com o que foi digitado.

    Sem isto a lista sai em ordem alfabética e o que a pessoa procura aparece no
    meio dela — com "cad", CADEIRA fica abaixo de BANCO PORTA-CADERNO.

    `desempate` são campos de ordenação para quando a parecença empata; na busca de
    produto é `-vendas_12m`, o que de fato sai da prateleira.
    """
    padrao = regex_sem_acento(termo)
    if not padrao:
        return consulta.order_by(*desempate) if desempate else consulta
    casos = []
    for campo in campos:
        casos.append(When(**{f"{campo}__iregex": f"^{padrao}"}, then=0))
    for campo in campos:
        casos.append(When(**{f"{campo}__iregex": f"{_NAO_E_LETRA}{padrao}"}, then=1))
    return consulta.annotate(
        perto=Case(*casos, default=2, output_field=IntegerField())
    ).order_by("perto", *desempate)
