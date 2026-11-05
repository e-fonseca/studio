"""Homologação no servidor da loja: porta própria, rede interna, antes de entrar no IIS.

Igual à produção, exceto HTTPS: nesta fase o acesso é direto pela porta própria, só da
rede interna e da VPN (regra de firewall do instalador). Quando /studio for publicado no
IIS com HTTPS, o serviço passa a usar config.settings.prod.
"""

from .prod import *  # noqa: F401,F403
from .base import env_lista

# Duas portas respondem nesta fase: a normal em HTTP, para o computador do balcão, e a
# segura em HTTPS (servir.py), que é a única em que o navegador do celular libera a
# câmera. As duas origens precisam estar aqui, senão o envio de formulário é recusado.
CSRF_TRUSTED_ORIGINS = env_lista(
    "STUDIO_CSRF_TRUSTED_ORIGINS",
    "http://192.168.3.254:8096,https://192.168.3.254:8444,https://localhost:8444")
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False
SECURE_PROXY_SSL_HEADER = None
SECURE_HSTS_SECONDS = 0
