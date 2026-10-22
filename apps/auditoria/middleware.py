from . import contexto


class CorrelacaoMiddleware:
    """Atribui um ID de correlação a cada requisição e o devolve no cabeçalho."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # REMOTE_ADDR é o endereço visto pelo servidor de aplicação. Atrás do proxy
        # reverso, o proxy deve sobrescrever (não acrescentar) este valor.
        tokens = contexto.iniciar(ip=request.META.get("REMOTE_ADDR"))
        try:
            request.correlacao = contexto.correlacao_atual()
            resposta = self.get_response(request)
            resposta["X-Correlacao"] = str(request.correlacao)
            return resposta
        finally:
            contexto.encerrar(tokens)
