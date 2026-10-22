"""Contexto da requisição atual (correlação, IP, usuário) para a trilha de auditoria."""

import contextvars
import uuid

_correlacao = contextvars.ContextVar("cabana_correlacao", default=None)
_ip = contextvars.ContextVar("cabana_ip", default=None)


def iniciar(ip=None, correlacao=None):
    tokens = (
        _correlacao.set(correlacao or uuid.uuid4()),
        _ip.set(ip),
    )
    return tokens


def encerrar(tokens):
    _correlacao.reset(tokens[0])
    _ip.reset(tokens[1])


def correlacao_atual():
    valor = _correlacao.get()
    if valor is None:
        valor = uuid.uuid4()
        _correlacao.set(valor)
    return valor


def ip_atual():
    return _ip.get()
