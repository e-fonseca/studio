"""Configuração comum a todos os ambientes.

Valores sensíveis e dependentes do ambiente vêm de variáveis de ambiente
(ver .env.exemplo). Nada de segredo neste arquivo.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env(nome, padrao=None, obrigatorio=False):
    valor = os.environ.get(nome, padrao)
    if obrigatorio and not valor:
        raise ImproperlyConfigured(f"Variável de ambiente {nome} não definida.")
    return valor


def env_lista(nome, padrao=""):
    return [item.strip() for item in env(nome, padrao).split(",") if item.strip()]


SECRET_KEY = env("CABANA_SECRET_KEY", obrigatorio=True)
DEBUG = False
ALLOWED_HOSTS = env_lista("CABANA_ALLOWED_HOSTS", "192.168.3.254")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "axes",
    "apps.core",
    "apps.contas",
    "apps.auditoria",
    "apps.processos",
    "apps.compras",
    "apps.pedidos",
    "apps.importacao",
    "apps.painel",
    "apps.fornecedores",
    "apps.financeiro",
    "apps.conciliacao",
    "apps.clientes",
    "apps.inventario",
    "apps.caixa",
    "apps.margem",
    "apps.alertas",
    "apps.backup",
    "apps.tempo",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Serve os arquivos estáticos pelo próprio processo (sem depender do IIS).
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.auditoria.middleware.CorrelacaoMiddleware",
    # A data marcada para o acesso acabar (1.42.0): antes de qualquer coisa ler
    # request.user, para a conta vencida já chegar desligada à conferência.
    "apps.contas.prazo.PrazoDeAcessoMiddleware",
    # Teto de tempo logado: o computador fica no balcão e a conta não pode
    # ficar aberta sozinha a tarde inteira.
    "apps.contas.sessao.LimiteDeSessaoMiddleware",
    "axes.middleware.AxesMiddleware",
]

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.sistema",
                "apps.importacao.context_processors.estado_dados",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("CABANA_DB_NOME", "cabana"),
        "USER": env("CABANA_DB_USUARIO", "cabana"),
        "PASSWORD": env("CABANA_DB_SENHA", ""),
        "HOST": env("CABANA_DB_HOST", "127.0.0.1"),
        "PORT": env("CABANA_DB_PORTA", "5432"),
        "CONN_MAX_AGE": 60,
        "ATOMIC_REQUESTS": True,
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True  # grava em UTC, exibe em America/Sao_Paulo

# Toda a aplicação vive sob /sistema (rotas, estáticos, cookies e redirecionamentos).
# O prefixo fica nas próprias rotas (config/urls.py), sem FORCE_SCRIPT_NAME, para
# funcionar igual com o proxy repassando o caminho intacto e no servidor de testes.
PREFIXO = "/sistema"
STATIC_URL = f"{PREFIXO}/static/"
STATIC_ROOT = Path(env("CABANA_STATIC_ROOT", BASE_DIR / "var" / "static"))
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_ROOT = Path(env("CABANA_MEDIA_ROOT", BASE_DIR / "var" / "anexos"))
# Anexos nunca são servidos diretamente: passam por view com checagem de permissão.
MEDIA_URL = f"{PREFIXO}/anexos-nao-publicos/"

# O cache do painel em ARQUIVO, e não na memória do processo, porque quem CALCULA e
# quem MOSTRA são processos diferentes: a importação é a tarefa agendada CabanaImportacao
# e as telas são o serviço CabanaSistema. Com o cache na memória, a conta feita às 08:30
# pela tarefa não chegava ao serviço, e a primeira pessoa a abrir o sistema depois de
# cada sincronização pagava a conta inteira esperando — três vezes por dia. Em arquivo,
# os dois processos leem o mesmo, e a conta também sobrevive ao reinício da atualização.
# Medido em 14/10/2026: montar custa 2,2 s, ler de volta custa 1,3 ms.
CACHE_PASTA = Path(env("CABANA_CACHE", BASE_DIR / "var" / "cache"))
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": str(CACHE_PASTA),
        # Trinta e seis horas, o mesmo prazo de apps/painel/servicos.py, que é quem
        # grava e manda o prazo em cada gravação. Este aqui vale para quem gravar sem
        # dizer o prazo: sem ele o padrão do Django seriam cinco minutos, e a conta
        # adiantada pela tarefa venceria antes de alguém chegar.
        "TIMEOUT": 60 * 60 * 36,
        # Cada importação guarda três entradas por dia, e são três sincronizações por
        # dia: cerca de nove arquivos ao dia. O teto demora um mês para ser atingido.
        # Ao atingir, o Django APAGA UM TERÇO DOS ARQUIVOS SORTEADOS — não os mais
        # velhos — e pode levar justamente a conta que está valendo. Está de bom
        # tamanho: a tarefa de hora em hora refaz a conta do dia, então o custo é no
        # máximo uma tela lenta para quem entrar antes da volta seguinte.
        "OPTIONS": {"MAX_ENTRIES": 300},
    }
}

LOGIN_URL = "contas:entrar"
LOGIN_REDIRECT_URL = "core:inicio"
LOGOUT_REDIRECT_URL = "contas:entrar"

SESSION_COOKIE_PATH = PREFIXO
CSRF_COOKIE_PATH = PREFIXO
SESSION_COOKIE_NAME = "cabana_sessao"
CSRF_COOKIE_NAME = "cabana_csrf"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 8 * 60 * 60  # uma jornada
# Quanto tempo uma pessoa pode ficar logada, contado da entrada (pedido do Edson,
# 07/10/2026). Quem passa disso cai na tela de entrada e precisa entrar de novo.
SESSAO_MAXIMA_SEGUNDOS = int(env("CABANA_SESSAO_MAXIMA_HORAS", 4)) * 60 * 60
# Tempo PARADO que encerra a sessão (pedido do Edson, 08/10/2026: fechar e reabrir o
# navegador voltava logado). O cookie já é de sessão, mas o Chrome restaura cookie de
# sessão quando está configurado para "continuar de onde parou" ou quando segue rodando
# em segundo plano — nada do lado do site impede isso. Quem impede é esta trava no
# servidor: passou do tempo sem usar, a sessão acaba, com navegador aberto ou fechado.
SESSAO_PARADA_SEGUNDOS = int(env("CABANA_SESSAO_PARADA_MINUTOS", 30)) * 60
# Porta segura (HTTPS). O sistema só precisa dela para montar o endereço que a tela de
# contagem pelo celular indica: a câmera do navegador não liga fora de https. Quem
# atende nessa porta é o túnel do servir.py, não o Django.
PORTA_HTTPS = env("CABANA_PORTA_HTTPS", "8443")
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

# Histórico das atualizações aplicadas: o instalar.ps1 acrescenta uma linha a cada
# atualização e o sistema mostra na tela de versões.
ATUALIZACOES_HISTORICO = Path(env("CABANA_HISTORICO_ATUALIZACOES", BASE_DIR / "var" / "atualizacoes.tsv"))

# Importação dos dados do SET (plano A: cópia do backup do banco; plano B: relatórios).
# CABANA_SET_BACKUP aponta para o arquivo ou a pasta onde o backup do SET é salvo.
IMPORTACAO_BACKUP_ORIGEM = env("CABANA_SET_BACKUP", "")
IMPORTACAO_PASTA_TRABALHO = Path(env("CABANA_COPIA_SET", BASE_DIR / "var" / "copia-set"))
IMPORTACAO_FIREBIRD_CLIENTE = env("CABANA_FIREBIRD_DLL", "")
IMPORTACAO_FIREBIRD_GBAK = env("CABANA_FIREBIRD_GBAK", "")
# Qual motor o instalador montou, só para a ficha técnica mostrar: carregar a DLL para
# perguntar a versão é caro e capaz de falhar, e quem sabe a resposta é quem instalou.
IMPORTACAO_FIREBIRD_VERSAO = env("CABANA_FIREBIRD_VERSAO", "")
# Abaixo deste tamanho o arquivo não é backup do SET, é gravação interrompida: a
# conferência impede a leitura e os números que estão na tela continuam valendo.
IMPORTACAO_BACKUP_MINIMO_BYTES = 1024 * 1024
IMPORTACAO_MANTER = 10  # fotos de produtos guardadas; o registro das execuções fica todo
IMPORTACAO_DIAS_ATENCAO = 2  # dados com esta idade já recebem aviso
# Horários da tarefa automática, só para mostrar na tela: a tarefa agendada do Windows é
# que manda de verdade. Desde a 1.25.0 são vários, separados por vírgula — o Edson pediu
# 08:30, 12:30 e 19:30, para a tela acompanhar o dia em vez de parar no backup da noite.
# CABANA_IMPORTACAO_HORA (singular) continua valendo para instalação antiga que só tem ele.
def _horarios_da_importacao():
    varias = env("CABANA_IMPORTACAO_HORAS", "")
    uma = env("CABANA_IMPORTACAO_HORA", "")
    bruto = varias or uma or "08:30,12:30,19:30"
    horas = []
    for pedaco in bruto.replace(";", ",").split(","):
        hora = pedaco.strip()
        if hora and hora not in horas:
            horas.append(hora)
    return horas


IMPORTACAO_HORARIOS = _horarios_da_importacao()
IMPORTACAO_HORA = IMPORTACAO_HORARIOS[0] if IMPORTACAO_HORARIOS else ""
IMPORTACAO_DIAS_VENCIDO = 4  # a partir daqui o aviso é vermelho: não decidir compra por eles

# Uploads
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
ANEXO_TAMANHO_MAXIMO = 10 * 1024 * 1024

# Proteção contra força bruta (django-axes)
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 0.25  # horas
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = "contas/bloqueado.html"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "padrao": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        # Na saída padrão, e não na de erro: no PowerShell, tudo que vai para a saída de
        # erro aparece como erro em vermelho, e uma linha informativa assusta quem instala.
        "console": {"class": "logging.StreamHandler", "formatter": "padrao",
                    "stream": "ext://sys.stdout"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}
