"""A senha de novo antes de mexer em acesso (1.44.0).

O prompt de controle de acesso (02/11/2026) pediu "reautenticação para operações
administrativas sensíveis" e "rotação de sessão na autenticação e na elevação de
privilégio". Aqui está o jeito mais simples que cobre os dois:

- Para abrir a área de acessos (Usuários, a ficha de cada pessoa, Perfis e permissões), a
  pessoa digita a própria senha outra vez. Vale por **15 minutos desde o último uso** da
  área: quem está arrumando acessos não digita a senha a cada clique, e quem largou o
  computador aberto no balcão não deixa a área aberta para o próximo.
- Ao confirmar, a sessão troca de chave (`cycle_key`): um cookie copiado antes não serve
  para o que vem depois.
- Cinco senhas erradas seguidas encerram a sessão. Quem pegou o computador aberto não
  fica tentando.

Tudo do lado do servidor, gravado na sessão (banco). O navegador não guarda nada disso.
"""

import functools
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from . import sessao

CHAVE = "acesso_confirmado_em"
ERROS = "acesso_confirmacao_erros"
MAXIMO_DE_ERROS = 5


def _janela_em_segundos():
    return int(getattr(settings, "ACESSO_CONFIRMADO_SEGUNDOS", 15 * 60))


def confirmada(request):
    """Se a senha foi confirmada há menos de 15 minutos (contados do último uso)."""
    quando = sessao._quando(request.session.get(CHAVE))  # noqa: SLF001 - mesmo app
    if quando is None:
        return False
    return (timezone.now() - quando).total_seconds() <= _janela_em_segundos()


def marcar(request):
    """A senha conferiu: abre a janela e troca a chave da sessão."""
    request.session.cycle_key()
    request.session[CHAVE] = timezone.now().isoformat()
    request.session.pop(ERROS, None)


def renovar(request):
    """Cada uso da área conta como uso: a janela anda junto."""
    request.session[CHAVE] = timezone.now().isoformat()


def fechar(request):
    request.session.pop(CHAVE, None)


def contar_erro(request):
    """Mais uma senha errada. Devolve quantas já foram."""
    erros = int(request.session.get(ERROS, 0)) + 1
    request.session[ERROS] = erros
    return erros


def exigir(view):
    """Decorador das telas de acesso: sem a senha confirmada, pede a senha antes.

    GET vai para a tela da senha e volta para onde ia. POST (o envio de um formulário
    depois que a janela fechou) não é refeito sozinho: volta para a tela de onde veio,
    com o recado de confirmar a senha e fazer de novo, para ninguém aplicar sem querer uma
    mudança que digitou há meia hora.
    """

    @functools.wraps(view)
    def envolvida(request, *args, **kwargs):
        if confirmada(request):
            renovar(request)
            return view(request, *args, **kwargs)
        if request.method == "POST":
            messages.info(request, "Por segurança, confirme a sua senha e faça a mudança de novo.")
            destino = request.META.get("HTTP_REFERER") or reverse("contas:usuarios")
        else:
            destino = request.get_full_path()
        return redirect(f"{reverse('contas:confirmar_senha')}?{urlencode({'proximo': destino})}")

    return envolvida
