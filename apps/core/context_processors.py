from apps.core import https, lembretes, menu, navegacao, versao


def sistema(request):
    anterior, proxima = navegacao.vizinhas(request)
    assuntos, telas_do_assunto = menu.para(request)
    return {
        # A primeira fileira do topo são os seis assuntos; a segunda, só as telas do
        # assunto aberto. Quem monta as duas é apps/core/menu.py.
        "menu_assuntos": assuntos,
        "menu_telas_do_assunto": telas_do_assunto,
        "nome_sistema": "Sistema auxiliar da Cabana do Jacarandá",
        "aviso_usuario": "Use seu próprio usuário. As ações ficam registradas para conferência e organização do trabalho.",
        "versao_sistema": versao.atual(),
        "tela_anterior": anterior,
        "tela_proxima": proxima,
        "lembretes_do_dia": _lembretes(request),
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
