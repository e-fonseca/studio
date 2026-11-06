from apps.core import cotacoes, https, lembretes, menu, navegacao, versao


def sistema(request):
    anterior, proxima = navegacao.vizinhas(request)
    assuntos, telas_do_assunto = menu.para(request)
    return {
        # A primeira fileira do topo são os seis assuntos; a segunda, só as telas do
        # assunto aberto. Quem monta as duas é apps/core/menu.py.
        "menu_assuntos": assuntos,
        "menu_telas_do_assunto": telas_do_assunto,
        "nome_sistema": "Sistema auxiliar do Studio Industrial",
        "aviso_usuario": "Use seu próprio usuário. As ações ficam registradas para controle e organização do trabalho.",
        "versao_sistema": versao.atual(),
        "tela_anterior": anterior,
        "tela_proxima": proxima,
        "lembretes_do_dia": _lembretes(request),
        # A faixa do topo com o dólar e as ações (1.50.0), lida do cache.
        "cotacoes": _cotacoes(request),
        # Quem entra pelo endereço sem segurança não tem como adivinhar que existe
        # outro com cadeado; a faixa no topo leva ele para lá.
        "endereco_seguro": https.endereco_seguro(request) if https.sem_seguranca(request) else "",
    }


def _lembretes(request):
    """Nunca derruba a tela: lembrete é enfeite, o conteúdo da página é o que importa."""
    usuario = getattr(request, "user", None)
    if usuario is None or not usuario.is_authenticated:
        return []
    try:
        return lembretes.do_dia(usuario)
    except Exception:  # noqa: BLE001 - qualquer falha aqui vira "sem lembretes"
        return []


def _cotacoes(request):
    """Também nunca derruba a tela: sem cotação, a faixa fica só com o relógio. Quem não vê
    número da loja (o vendedor) fica só com o relógio: a tela dele não mostra R$ nenhum."""
    usuario = getattr(request, "user", None)
    if usuario is None or not usuario.is_authenticated or not usuario.has_perm("importacao.ver_painel"):
        return None
    try:
        return cotacoes.faixa()
    except Exception:  # noqa: BLE001 - cotação é enfeite
        return None
