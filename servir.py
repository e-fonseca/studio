"""Inicia o sistema com o Waitress (usado pela tarefa agendada no servidor Windows).

Sobe duas portas: a normal, em HTTP, que é por onde o computador do balcão entra, e
uma segura, em HTTPS, com certificado feito pelo próprio servidor. A porta segura
existe porque o navegador do celular só libera a câmera em página segura, e é por
ela que a contagem de inventário pelo celular funciona.
"""

import logging
import os

from config.ambiente import carregar

carregar()
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.homolog")

from waitress import serve  # noqa: E402

from config.wsgi import application  # noqa: E402


def _subir_https(porta_http):
    """Liga a porta HTTPS, se estiver habilitada. Falha aqui nunca derruba o HTTP."""
    if os.environ.get("STUDIO_HTTPS", "1") != "1":
        return
    porta = int(os.environ.get("STUDIO_PORTA_HTTPS", "8444"))
    try:
        from apps.core import certificado, tunel_tls

        # A pasta e os endereços vêm do próprio módulo, porque a tela
        # /studio/certificado/ precisa achar os mesmos arquivos.
        pasta = certificado.pasta_padrao()
        arquivo, chave = certificado.garantir(pasta, certificado.enderecos_configurados())
        tunel_tls.em_segundo_plano(porta, ("127.0.0.1", porta_http), arquivo, chave)
    except Exception as erro:  # noqa: BLE001
        logging.getLogger(__name__).exception(
            "HTTPS não subiu; o sistema segue em HTTP e a câmera do celular não vai funcionar.")
        try:
            from apps.core import https

            https.registrar_falha(f"{type(erro).__name__}: {erro}")
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    formato = "%(asctime)s %(levelname)s %(name)s %(message)s"
    arquivo_log = os.environ.get("STUDIO_LOG_ARQUIVO")
    if arquivo_log:
        from logging.handlers import RotatingFileHandler

        saida = RotatingFileHandler(arquivo_log, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
        logging.basicConfig(level=logging.INFO, format=formato, handlers=[saida])
    else:
        logging.basicConfig(level=logging.INFO, format=formato)
    host = os.environ.get("STUDIO_HOST", "0.0.0.0")
    porta = int(os.environ.get("STUDIO_PORTA", "8096"))
    _subir_https(porta)
    serve(application, host=host, port=porta,
          threads=int(os.environ.get("STUDIO_THREADS", "4")), ident="studio")
