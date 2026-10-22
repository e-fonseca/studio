"""Encerramento automático da sessão: por tempo logado e por tempo parado.

São duas travas, as duas do lado do servidor, que o navegador não consegue contornar:

1. **Tempo logado** (pedido do Edson em 07/10/2026): quatro horas contadas da entrada.
   Quem fica a tarde inteira com a tela aberta é desconectado do mesmo jeito. O
   computador da loja fica no balcão e todo mundo passa por ali.
2. **Tempo parado** (pedido do Edson em 08/10/2026): trinta minutos sem usar o sistema
   encerram a sessão. Ele fechou o navegador, abriu de novo e voltou logado, e com razão
   chamou isso de brecha. O cookie já é de sessão (`SESSION_EXPIRE_AT_BROWSER_CLOSE`),
   mas o Chrome **restaura cookie de sessão** quando está em "continuar de onde parou",
   quando reabre as abas, ou quando continua rodando em segundo plano depois de fechar a
   janela. Nada do lado do site impede isso — é decisão do navegador. O que resolve é o
   servidor não aceitar mais aquela sessão, e é isto aqui.

Os dois tempos vêm do cabana.env (CABANA_SESSAO_MAXIMA_HORAS e
CABANA_SESSAO_PARADA_MINUTOS), para mudar sem mexer no código.
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

CHAVE = "entrou_em"
VISTO = "visto_em"
# Não vale gravar a sessão a cada clique: um minuto de granularidade já conta tempo
# parado com folga e poupa uma escrita no banco por requisição.
PASSO_DO_RELOGIO = 60

AVISO = (
    "Sua sessão passou de {horas} horas e foi encerrada por segurança. "
    "Entre de novo para continuar."
)
AVISO_PARADA = (
    "Sua sessão ficou {minutos} minutos sem uso e foi encerrada por segurança. "
    "Entre de novo para continuar."
)


def marcar_entrada(sessao):
    """Guarda a hora da entrada e do último uso. Chamado no login."""
    agora = timezone.now().isoformat()
    sessao[CHAVE] = agora
    sessao[VISTO] = agora


def _limite_em_segundos():
    return int(getattr(settings, "SESSAO_MAXIMA_SEGUNDOS", 4 * 60 * 60))


def _parada_em_segundos():
    return int(getattr(settings, "SESSAO_PARADA_SEGUNDOS", 30 * 60))


def _quando(valor):
    """Lê uma hora gravada na sessão. Devolve None quando não dá para ler."""
    try:
        quando = timezone.datetime.fromisoformat(valor)
    except (TypeError, ValueError):
        return None
    if timezone.is_naive(quando):
        quando = timezone.make_aware(quando, timezone.get_current_timezone())
    return quando


class LimiteDeSessaoMiddleware:
    """Desconecta quem passou do tempo logado ou ficou tempo demais sem usar."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = getattr(request, "user", None)
        if usuario is not None and usuario.is_authenticated:
            motivo = self._motivo_para_encerrar(request)
            if motivo:
                logout(request)
                messages.info(request, motivo)
                return redirect(reverse("contas:entrar"))
            self._anotar_uso(request.session)
        return self.get_response(request)

    def _motivo_para_encerrar(self, request):
        agora = timezone.now()
        entrada = _quando(request.session.get(CHAVE))
        if entrada is None:
            # Sessão aberta antes desta versão: passa a contar de agora, em vez de
            # derrubar todo mundo na primeira vez que a atualização sobe.
            marcar_entrada(request.session)
            return ""
        if (agora - entrada).total_seconds() > _limite_em_segundos():
            return AVISO.format(horas=_limite_em_segundos() // 3600)
        visto = _quando(request.session.get(VISTO)) or entrada
        if (agora - visto).total_seconds() > _parada_em_segundos():
            return AVISO_PARADA.format(minutos=_parada_em_segundos() // 60)
        return ""

    def _anotar_uso(self, sessao):
        """Marca que a sessão foi usada agora, sem gravar a cada clique."""
        agora = timezone.now()
        visto = _quando(sessao.get(VISTO))
        if visto is None or (agora - visto).total_seconds() >= PASSO_DO_RELOGIO:
            sessao[VISTO] = agora.isoformat()
