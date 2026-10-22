"""Saber se a porta segura está mesmo de pé, e dizer isso na tela.

Por que isto existe: em 08/10/2026 o Edson disse "SSL ainda não funcionou", com a
tela aberta em http://192.168.3.254:8095. O HTTPS nunca esteve naquele endereço —
ele mora na porta 8443 — e, se o túnel não tivesse subido, o sistema também não
diria nada: a falha só ia para o log, que ninguém abre. As duas coisas eram
silenciosas, e silêncio aqui vira "não funcionou".

Então agora o sistema fala: quem entra pelo endereço sem segurança vê uma faixa com
o endereço seguro, e a tela do certificado faz o teste de verdade — abre uma conexão
TLS na porta segura, a partir do próprio servidor, e conta o que aconteceu.
"""

import logging
import os
import socket
import ssl
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

PORTA_PADRAO = 8443

# Onde fica escrito por que a porta segura não subiu. O túnel sobe numa linha de
# trabalho separada, então a falha dele não chega a quem inicia o sistema: até a
# 1.19.1 ela ia só para o log, que ninguém abre. Agora vai também para este arquivo,
# e a tela do certificado lê e conta.
ARQUIVO_FALHA = "https-ultima-falha.txt"


def ligado():
    """O HTTPS está habilitado no cabana.env? (CABANA_HTTPS=0 desliga.)"""
    return os.environ.get("CABANA_HTTPS", "1") == "1"


def porta():
    try:
        return int(os.environ.get("CABANA_PORTA_HTTPS", PORTA_PADRAO))
    except (TypeError, ValueError):
        return PORTA_PADRAO


def endereco_seguro(request):
    """O endereço https equivalente ao que a pessoa está usando agora."""
    host = (request.get_host() or "").split(":")[0]
    return f"https://{host}:{porta()}{request.path}"


def endereco_do_sistema(caminho="/sistema/"):
    """O endereço do sistema para quem não tem um request na mão.

    Quem manda relatório é uma tarefa agendada, sem navegador e sem request, e um link
    relativo numa mensagem de celular não leva a lugar nenhum. O endereço sai do
    primeiro nome que o certificado cobre (CABANA_CERTIFICADO_NOMES, que o instalador
    grava), que é o endereço pelo qual a loja abre o sistema.
    """
    from apps.core import certificado

    enderecos = [e for e in certificado.enderecos_configurados()
                 if e not in ("localhost", "127.0.0.1", "::1")]
    maquina = enderecos[0] if enderecos else "localhost"
    return f"https://{maquina}:{porta()}{caminho}"


def sem_seguranca(request):
    """Verdadeiro quando a pessoa está num endereço de rede, em HTTP puro.

    localhost não entra: o navegador já trata localhost como contexto seguro, e lá a
    câmera e o atalho funcionam sem certificado nenhum.
    """
    if request.is_secure() or not ligado():
        return False
    host = (request.get_host() or "").split(":")[0]
    return host not in ("localhost", "127.0.0.1", "::1", "")


def arquivo_de_falha():
    """O arquivo onde o motivo é gravado: na pasta do certificado, que já é gravável."""
    from apps.core import certificado as certificado_servicos

    return certificado_servicos.pasta_padrao() / ARQUIVO_FALHA


def registrar_falha(motivo):
    """Anota por que a porta segura não subiu. Nunca levanta erro: é só um aviso."""
    try:
        caminho = arquivo_de_falha()
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(f"{datetime.now():%d/%m/%Y %H:%M}\n{motivo}\n", encoding="utf-8")
    except OSError as erro:
        logger.warning("Não consegui anotar a falha do HTTPS: %s", erro)


def esquecer_falha():
    """Apaga a anotação quando a porta segura sobe, para a tela não mostrar coisa velha."""
    try:
        arquivo_de_falha().unlink(missing_ok=True)
    except OSError as erro:
        logger.warning("Não consegui apagar a anotação do HTTPS: %s", erro)


def falha_registrada():
    """(quando, motivo) da última vez que a porta segura não subiu, ou None."""
    try:
        caminho = arquivo_de_falha()
        if not caminho.is_file():
            return None
        linhas = caminho.read_text(encoding="utf-8").strip().split("\n")
    except OSError:
        return None
    if not linhas or not linhas[0]:
        return None
    return linhas[0], "\n".join(linhas[1:]).strip()


@dataclass
class Diagnostico:
    """O resultado do teste da porta segura, pronto para a tela."""

    nivel: str          # bom, atencao, ruim
    titulo: str
    detalhe: str
    porta: int = PORTA_PADRAO
    # O endereço de rede que também foi testado, quando houve um.
    endereco_rede: str = ""

    @property
    def funcionando(self):
        return self.nivel == "bom"


def _atende(endereco, numero, tempo_limite):
    """A porta aceita conexão neste endereço? Devolve None quando sim, o erro quando não."""
    try:
        with socket.create_connection((endereco, numero), timeout=tempo_limite):
            return None
    except OSError as erro:
        return erro


def conferir(tempo_limite=2.0, endereco_rede=""):
    """Abre uma conexão TLS na porta segura, do próprio servidor, e conta o que deu.

    Não confere o certificado de propósito (`CERT_NONE`): o que se quer saber aqui é
    se existe alguém falando TLS naquela porta, e não se este servidor confia em si
    mesmo. Quem confere o certificado é o navegador do aparelho.

    Com `endereco_rede` (o endereço pelo qual a pessoa chegou até aqui) o teste é
    feito duas vezes: no 127.0.0.1, que diz se o túnel subiu, e no endereço da rede,
    que diz se ele está escutando na placa de rede e não só dentro do servidor.
    """
    numero = porta()
    if not ligado():
        return Diagnostico(
            "ruim", "A porta segura está desligada",
            "No arquivo config\\cabana.env a linha CABANA_HTTPS está diferente de 1. "
            "Mude para CABANA_HTTPS=1 e reinicie o sistema.", numero)

    # Arquivo de certificado faltando explica a porta muda melhor do que "ninguém atende":
    # sem ele o túnel nem chega a subir.
    from apps.core import certificado as certificado_servicos

    pasta = certificado_servicos.pasta_padrao()
    if not (pasta / certificado_servicos.NOME_CERTIFICADO).is_file():
        return Diagnostico(
            "ruim", "O certificado do servidor não existe",
            f"Sem o certificado a porta segura não sobe. Ele deveria estar em {pasta}. "
            "Abrir esta tela já tenta criá-lo; se o aviso continuar, a conta que roda o "
            "sistema não consegue gravar nessa pasta.", numero)

    contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    contexto.check_hostname = False
    contexto.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection(("127.0.0.1", numero), timeout=tempo_limite) as crua:
            with contexto.wrap_socket(crua) as segura:
                versao_tls = segura.version() or "TLS"
    except ConnectionRefusedError:
        anotado = falha_registrada()
        if anotado:
            quando, motivo = anotado
            return Diagnostico(
                "ruim", f"A porta segura {numero} tentou subir e falhou",
                f"Em {quando} o sistema tentou abrir a porta segura e não conseguiu. "
                f"O motivo foi: {motivo}", numero)
        return Diagnostico(
            "ruim", f"Ninguém está atendendo na porta {numero}",
            "O sistema subiu sem a porta segura. Reinicie pela tarefa agendada "
            "Cabana\\CabanaSistema (no Agendador de Tarefas do Windows) ou reinicie o "
            "servidor, e confira esta tela de novo. Se continuar assim, o motivo está "
            "nas últimas linhas do arquivo logs\\sistema.log.", numero)
    except (socket.timeout, TimeoutError):
        return Diagnostico(
            "atencao", f"A porta {numero} não respondeu a tempo",
            "Pode ser o servidor ocupado. Atualize esta tela em alguns segundos.", numero)
    except ssl.SSLError as erro:
        return Diagnostico(
            "ruim", f"A porta {numero} atende, mas não fecha o TLS",
            f"O erro foi: {erro}. Normalmente é certificado ou chave corrompidos; "
            "apagar a pasta do certificado e reiniciar o sistema gera outro.", numero)
    except OSError as erro:
        return Diagnostico(
            "ruim", f"Não consegui testar a porta {numero}", str(erro), numero)
    # O túnel está de pé dentro do servidor. Falta saber se ele atende pela placa de
    # rede, que é por onde o celular chega. Endereço de rede que não atende é problema
    # de verdade; atender não garante que o firewall do Windows deixe outro aparelho
    # entrar, porque o servidor falando com ele mesmo não passa pela regra.
    rede = (endereco_rede or "").strip()
    if rede and rede not in ("localhost", "127.0.0.1", "::1"):
        erro = _atende(rede, numero, tempo_limite)
        if erro is not None:
            return Diagnostico(
                "atencao", f"A porta {numero} funciona no servidor, mas não em {rede}",
                f"Testando por {rede} o resultado foi: {erro}. A porta segura está de pé "
                "dentro do servidor, então o que falta é ela atender neste endereço: "
                "confira se o sistema está configurado para escutar em toda a rede "
                "(CABANA_HOST=0.0.0.0, em config\\cabana.env) e reinicie o sistema.",
                numero, rede)
        return Diagnostico(
            "bom", f"A porta segura {numero} está funcionando",
            f"O servidor respondeu em {versao_tls}, inclusive pelo endereço {rede}. Se o "
            f"celular ainda não abre https://{rede}:{numero}/sistema/, falta liberar a "
            f"porta {numero} no firewall do Windows (a regra se chama Cabana Sistema "
            "HTTPS); se abre com aviso, falta instalar o certificado da loja no aparelho, "
            "logo abaixo.", numero, rede)
    return Diagnostico(
        "bom", f"A porta segura {numero} está funcionando",
        f"O servidor respondeu em {versao_tls}. Se o aparelho ainda reclama, falta "
        "instalar nele o certificado da loja, logo abaixo.", numero)
