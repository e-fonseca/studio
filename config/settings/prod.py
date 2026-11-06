"""Homologação e produção: atrás de proxy reverso com HTTPS."""

from .base import *  # noqa: F401,F403
from .base import env, env_lista

from apps.core import pastas  # noqa: E402  (só constantes, sem Django)

DEBUG = False
CSRF_TRUSTED_ORIGINS = env_lista("STUDIO_CSRF_TRUSTED_ORIGINS", "https://192.168.3.254")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env("STUDIO_SSL_REDIRECT", "1") == "1"
# HSTS curto até o certificado estar validado em todos os dispositivos.
SECURE_HSTS_SECONDS = int(env("STUDIO_HSTS_SEGUNDOS", "0"))

# O backup do SET do Studio, no servidor da loja, sem precisar de nada no studio.env (2.3.0):
# a pasta, e dela sempre o arquivo mais novo. STUDIO_SET_BACKUP preenchido continua mandando;
# vazio não desliga a importação, cai nesta pasta. Fora do servidor (dev, test) continua
# vazio: lá ninguém tem C:\backup-Set, e adivinhar caminho é pior do que dizer que falta.
IMPORTACAO_BACKUP_ORIGEM = env("STUDIO_SET_BACKUP", "") or pastas.BACKUP_SET
