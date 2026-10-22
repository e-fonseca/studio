"""Ordem das telas, para as setas de "anterior" e "próxima".

A ordem é a do menu (apps/core/menu.py): assunto por assunto, e dentro de cada um a
ordem em que as telas aparecem na segunda fileira. Mantendo uma lista só, a seta nunca
manda para uma tela que saiu do menu nem pula uma que entrou.
"""

from apps.core import menu


def vizinhas(request):
    """A tela anterior e a próxima, em relação à que está aberta."""
    usuario = getattr(request, "user", None)
    if usuario is None or not usuario.is_authenticated:
        return None, None
    telas = (menu.permitidos(menu.telas(), usuario)
             + menu.permitidos(menu.FORA_DO_MENU, usuario))
    atual = getattr(getattr(request, "resolver_match", None), "view_name", None)

    # Tela que é recurso de outra (a comparação com o ano passado, dentro da lista de
    # compra; o tempo, dentro da Visão geral) não é parada do caminho: ela sai do
    # vaivém e devolve só a volta para a tela de onde se abre. Sem isso, quem entrasse
    # nela ficaria sem caminho de volta, porque ela não está mais no menu.
    aberta = next((tela for tela in telas if tela.acende_em(atual)), None)
    if aberta is not None and aberta.dentro_de:
        origem = menu.de_rota(aberta.dentro_de)
        if origem is not None and (origem.permissao is None
                                   or usuario.has_perm(origem.permissao)):
            return origem, None
        return None, None

    telas = [tela for tela in telas if not tela.dentro_de]
    posicoes = [i for i, tela in enumerate(telas) if tela.acende_em(atual)]
    if not posicoes:
        return None, None
    i = posicoes[0]
    return (telas[i - 1] if i > 0 else None,
            telas[i + 1] if i + 1 < len(telas) else None)
