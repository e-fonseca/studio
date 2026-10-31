"""A data marcada para o acesso acabar, cumprida sem depender de ninguém lembrar.

Pedido do Edson em 31/10/2026, com a Cássia entrando no lugar da Bárbara: *"ficara no
lugar da barbara ate dia 12/11/2026"*. Até a 1.41.0 a única saída era alguém abrir a
tela de usuários no dia certo e clicar em Encerrar; agora a data fica na conta e o
sistema encerra sozinho no dia seguinte.

Quem cumpre a data é este middleware, e não uma tarefa agendada nova: ele roda na
primeira requisição de cada dia, de quem quer que seja — inclusive na tentativa de
entrar da própria pessoa, que chega aqui ANTES de o login conferir a senha. Então não
existe janela em que a conta vencida ainda entra, e não há mais um agendamento no
servidor da loja para instalar, vigiar e esquecer.

Uma vez por dia por processo: a conferência é uma consulta só, e o dia que já foi
conferido não volta a ser.
"""

import logging
import threading

from django.utils import timezone

from . import servicos

logger = logging.getLogger(__name__)
_trava = threading.Lock()
_conferido_em = None


def conferir_hoje(hoje=None):
    """Desliga as contas vencidas, uma vez por dia. Devolve quem foi desligado agora."""
    global _conferido_em
    hoje = hoje or timezone.localdate()
    if _conferido_em == hoje:
        return []
    with _trava:
        if _conferido_em == hoje:
            return []
        desligados = servicos.encerrar_acessos_vencidos(hoje)
        _conferido_em = hoje
    return desligados


def esquecer():
    """Faz a próxima requisição conferir de novo. É para os testes: na loja, data marcada
    nunca é de um dia que já passou, então o dia já conferido não muda de resposta."""
    global _conferido_em
    with _trava:
        _conferido_em = None


class PrazoDeAcessoMiddleware:
    """Encerra, na primeira requisição do dia, as contas que passaram da data marcada.

    Fica depois da autenticação e antes de qualquer coisa que leia `request.user`: a
    conta desligada aqui já chega desligada à conferência do usuário, e o Django trata
    conta desligada como quem não entrou.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            conferir_hoje()
        except Exception:  # noqa: BLE001 - a conferência não pode derrubar a tela de ninguém
            # O dia não fica marcado como conferido: a próxima requisição tenta de novo.
            logger.exception("Não deu para conferir as datas de acesso de hoje.")
        return self.get_response(request)
