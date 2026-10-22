"""Ambiente de desenvolvimento local. Nunca usar em produção."""

from .base import *  # noqa: F401,F403
from .base import env_lista

DEBUG = True
ALLOWED_HOSTS = env_lista("CABANA_ALLOWED_HOSTS", "localhost,127.0.0.1")
