"""Homologação e produção: atrás de proxy reverso com HTTPS."""

from .base import *  # noqa: F401,F403
from .base import env, env_lista

DEBUG = False
CSRF_TRUSTED_ORIGINS = env_lista("STUDIO_CSRF_TRUSTED_ORIGINS", "https://192.168.3.254")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env("STUDIO_SSL_REDIRECT", "1") == "1"
# HSTS curto até o certificado estar validado em todos os dispositivos.
SECURE_HSTS_SECONDS = int(env("STUDIO_HSTS_SEGUNDOS", "0"))
