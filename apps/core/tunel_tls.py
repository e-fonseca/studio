"""Porta HTTPS do sistema: recebe em TLS e repassa para o Waitress, em texto, no 127.0.0.1.

O Waitress não fala TLS e trocar o servidor inteiro por causa disso seria mexer no
que já funciona. Então o HTTPS entra assim: este túnel escuta na porta segura, faz
o TLS com o navegador e repassa os bytes para o Waitress na porta normal, que
continua escutando como sempre. O computador do balcão segue entrando por HTTP; o
celular, que precisa de página segura para liberar a câmera, entra por HTTPS.

É só um encaminhador de bytes: não lê, não reescreve e não guarda nada do que passa.
"""

import logging
import socket
import ssl
import threading

logger = logging.getLogger(__name__)

PEDACO = 64 * 1024
ESPERA_SEGUNDOS = 300  # conexão parada é fechada; o navegador reabre quando precisar


def _repassar(origem, destino):
    """Copia de um lado para o outro até acabar, e avisa o outro lado que acabou."""
    try:
        while True:
            dados = origem.recv(PEDACO)
            if not dados:
                break
            destino.sendall(dados)
    except (OSError, ssl.SSLError):
        pass
    finally:
        for lado in (origem, destino):
            try:
                lado.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def _sem_espera(meia):
    """Desliga o Nagle: o encaminhador não pode guardar bytes esperando encher o pacote.

    O Nagle junta escritas pequenas antes de mandar e, combinado com o "ACK atrasado"
    do outro lado, custa até 40 ms por troca. Num encaminhador é o pior dos mundos: o
    cabeçalho da resposta chega numa escrita e o corpo noutra, e o túnel segura o
    primeiro esperando o segundo. Numa página com uma dezena de arquivos, são dezenas
    desses atrasos somados — e nada disso aparece para quem entra por HTTP, que não
    passa por aqui. Falhar aqui não derruba a conexão: Nagle ligado é lento, não quebrado.
    """
    try:
        meia.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except OSError:
        logger.debug("Não consegui desligar o Nagle nesta conexão.")


def _atender(cliente, destino):
    porta_interna = destino
    try:
        with socket.create_connection(porta_interna, timeout=10) as interno:
            _sem_espera(interno)
            cliente.settimeout(ESPERA_SEGUNDOS)
            interno.settimeout(ESPERA_SEGUNDOS)
            ida = threading.Thread(target=_repassar, args=(cliente, interno), daemon=True)
            ida.start()
            _repassar(interno, cliente)
            ida.join(timeout=5)
    except (OSError, ssl.SSLError) as erro:
        logger.debug("Conexão HTTPS encerrada: %s", erro)
    finally:
        try:
            cliente.close()
        except OSError:
            pass


def servir(porta, destino, certificado, chave, host="0.0.0.0"):
    """Escuta em `porta` com TLS e repassa para `destino` (host, porta). Não retorna."""
    contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    contexto.load_cert_chain(certfile=str(certificado), keyfile=str(chave))
    contexto.minimum_version = ssl.TLSVersion.TLSv1_2
    ouvinte = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ouvinte.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    ouvinte.bind((host, porta))
    ouvinte.listen(32)
    logger.info("HTTPS ouvindo em %s:%s e repassando para %s:%s", host, porta, *destino)
    # Subiu: apaga a anotação da falha anterior, senão a tela do certificado fica
    # mostrando um motivo que já não existe.
    from apps.core import https

    https.esquecer_falha()
    while True:
        try:
            crua, _ = ouvinte.accept()
        except OSError as erro:
            logger.warning("Falha ao aceitar conexão HTTPS: %s", erro)
            continue
        _sem_espera(crua)
        try:
            cliente = contexto.wrap_socket(crua, server_side=True)
        except (ssl.SSLError, OSError) as erro:
            # Navegador que desistiu do aviso de certificado, ou alguém falando HTTP
            # na porta HTTPS. Não é motivo para derrubar o túnel.
            logger.debug("Aperto de mão TLS não concluído: %s", erro)
            try:
                crua.close()
            except OSError:
                pass
            continue
        threading.Thread(target=_atender, args=(cliente, destino), daemon=True).start()


def em_segundo_plano(porta, destino, certificado, chave, host="0.0.0.0"):
    """Sobe o túnel numa linha de trabalho separada, para o Waitress seguir na principal.

    Se o túnel falhar (porta ocupada, certificado ilegível), o sistema continua
    respondendo em HTTP: a loja não pode parar por causa do HTTPS.
    """
    def alvo():
        try:
            servir(porta, destino, certificado, chave, host)
        except Exception as erro:  # noqa: BLE001
            logger.exception("A porta HTTPS não subiu; o sistema segue só em HTTP.")
            # O erro acontece aqui dentro, numa linha de trabalho separada: quem
            # iniciou o sistema já seguiu em frente e nunca vai vê-lo. Por isso ele
            # fica escrito num arquivo, que a tela do certificado mostra.
            from apps.core import https

            https.registrar_falha(f"{type(erro).__name__}: {erro}")

    linha = threading.Thread(target=alvo, name="cabana-https", daemon=True)
    linha.start()
    return linha
