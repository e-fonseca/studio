"""Configuração usada pela suíte de testes."""

import os

os.environ.setdefault("STUDIO_SECRET_KEY", "chave-somente-para-testes")

from .base import *  # noqa: E402,F401,F403
from .base import BASE_DIR  # noqa: E402

ALLOWED_HOSTS = ["testserver"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
# Cache na memória do processo, e não em arquivo como no servidor: em arquivo um teste
# deixaria número calculado para o seguinte achar, e a suíte passaria a depender da ordem.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
MEDIA_ROOT = BASE_DIR / "var" / "anexos-teste"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
# Desligado por padrão para os testes poderem usar client.login();
# o teste de força bruta liga de novo com override_settings.
AXES_ENABLED = False
# Os testes importam backup de mentira, de alguns bytes; o piso de tamanho de verdade
# tem o seu próprio teste, que o liga de novo com override_settings.
IMPORTACAO_BACKUP_MINIMO_BYTES = 1

# Nenhum teste fala com a internet. Três partes do sistema saem para fora — a busca do
# tempo, a descoberta da cidade e o aviso pelo Telegram — e todas recebem a função de
# abrir a conexão por parâmetro, justamente para o teste passar uma de mentira. Quando
# alguém esquece de passar, o teste ficava vinte segundos esperando a rede e podia até
# passar na máquina de quem tem internet e falhar na do servidor. Aqui a tentativa morre
# na hora e diz qual é.
import urllib.request as _urllib_request  # noqa: E402


def _nada_de_internet(*_args, **_criterios):
    raise AssertionError(
        "Um teste tentou abrir uma conexão com a internet. Passe a função `abrir` de "
        "mentira (como em apps/tempo/tests/test_tempo.py) ou troque a chamada por um "
        "mock; teste que depende de rede falha na máquina de quem não tem."
    )


_urllib_request.urlopen = _nada_de_internet

# A suíte herdada do sistema da Cabana confere as telas de compras e estoque pelo menu;
# o Studio as esconde por configuração, e o teste dele liga isso com override_settings.
ASSUNTOS_DESLIGADOS = ()
