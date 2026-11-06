"""Homologação e produção: atrás de proxy reverso com HTTPS."""

from .base import *  # noqa: F401,F403
from .base import env, env_lista

from apps.core import pastas  # noqa: E402  (só constantes, sem Django)

DEBUG = False

# O banco do Studio nunca é o da Cabana (2.4.1). O PostgreSQL do servidor guarda os dois; sem
# STUDIO_DB_NOME no studio.env, ou com o nome da Cabana nele, o serviço não sobe, em vez de
# migrar e gravar por cima dos dados da outra empresa.
NOMES_DA_CABANA = {"cabana", "cabana_sistema", "cabana-sistema", "sistema"}
DATABASES["default"]["NAME"] = env("STUDIO_DB_NOME", obrigatorio=True)  # noqa: F405
DATABASES["default"]["USER"] = env("STUDIO_DB_USUARIO", obrigatorio=True)  # noqa: F405
if DATABASES["default"]["NAME"].strip().lower() in NOMES_DA_CABANA:  # noqa: F405
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured(
        f"STUDIO_DB_NOME={DATABASES['default']['NAME']!r} é o banco da Cabana. "  # noqa: F405
        "O Studio usa o banco dele (studio)."
    )
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
