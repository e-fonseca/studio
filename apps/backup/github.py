"""Falar com o GitHub pela API, sem git instalado no servidor e sem biblioteca de fora.

Por que não `git push`
---------------------
O servidor da loja não tem git, e não vai ter: o programa roda num Python embutido,
baixado e descompactado pelo instalador, e cada coisa a mais para instalar é uma coisa
a mais para dar errado na mão de quem não é técnico. Baixar um git portátil de 50 MB em
cada servidor para mandar 460 arquivos de texto é caro demais pelo que resolve.

A API de dados do git faz exatamente o que o `push` faz, em quatro chamadas: cria o
conteúdo (blob), monta a árvore, faz o commit e move o ramo. O que chega ao GitHub é
commit de verdade, com histórico de verdade, que se clona com `git clone`.

O que faz este módulo não repetir trabalho
------------------------------------------
O nome de um arquivo no git é o resumo SHA-1 do conteúdo dele — a mesma conta,
calculada aqui. Então o envio compara o resumo de cada arquivo local com o que a árvore
do GitHub já tem e só manda o que mudou: o primeiro envio sobe o sistema inteiro, os
seguintes sobem os três arquivos da versão nova.

O token NUNCA entra em linha de comando. Vai em cabeçalho HTTP, dentro do processo:
linha de comando é visível na lista de processos do Windows, e seria o jeito mais fácil
de vazar o que dá acesso de escrita ao repositório.
"""

import base64
import hashlib
import json
import socket
from dataclasses import dataclass, field
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API = "https://api.github.com"
TEMPO_LIMITE = 30
# Modo de arquivo comum no git. O sistema não guarda link nem executável.
MODO_ARQUIVO = "100644"
# Quanto vai em cada pedido de árvore. O primeiro envio é o sistema inteiro (~500
# arquivos, ~3 MB de texto): um pedido por arquivo esbarrava no limite do GitHub de
# escritas por minuto e por hora, e prendia a tela em "Enviando…" por minutos (22/10/2026).
# Texto vai DENTRO da árvore, em lotes; só o binário (logo, ícones) pede blob próprio.
LOTE_DE_BYTES = 700_000
LOTE_DE_ARQUIVOS = 150


class NaoDeuCerto(Exception):
    """O que impediu o envio, numa frase que serve de recado na tela."""


@dataclass
class Arquivo:
    """Um arquivo a enviar: o caminho dentro do repositório e o conteúdo."""

    caminho: str
    dados: bytes

    @property
    def resumo(self):
        return resumo_de_blob(self.dados)


@dataclass
class Resultado:
    enviou: bool = False
    commit: str = ""
    enviados: int = 0
    apagados: int = 0
    ao_todo: int = 0
    mensagem: str = ""
    novos_caminhos: list = field(default_factory=list)


def resumo_de_blob(dados):
    """O SHA-1 como o git calcula: "blob <tamanho>\\0" na frente do conteúdo."""
    cabecalho = f"blob {len(dados)}".encode("ascii") + b"\x00"
    return hashlib.sha1(cabecalho + dados).hexdigest()  # noqa: S324 - é o formato do git


class GitHub:
    """O pedaço da API de que o backup precisa."""

    def __init__(self, dono, repositorio, token, abrir=None):
        self.dono = dono
        self.repositorio = repositorio
        self.token = token
        # Injetado nos testes: nenhum teste fala com a internet.
        self._abrir = abrir or _abrir

    def _pedir(self, metodo, caminho, corpo=None):
        endereco = f"{API}/repos/{self.dono}/{self.repositorio}{caminho}"
        dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
        pedido = Request(endereco, data=dados, method=metodo, headers={
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "studio-sistema",
            "Content-Type": "application/json",
        })
        return self._abrir(pedido)

    # ---------------------------------------------------------------- leitura
    def ramo(self, nome):
        """O commit em que o ramo está, ou None quando o ramo ainda não existe."""
        resposta = self._pedir("GET", f"/git/ref/heads/{nome}")
        if not isinstance(resposta, dict):
            # None é repositório vazio ou ramo que não existe. Lista é o GitHub
            # devolvendo os ramos PARECIDOS quando o pedido não casa exatamente —
            # nenhum deles é o que foi pedido.
            return None
        return resposta.get("object", {}).get("sha") or None

    def arvore_do_commit(self, commit):
        resposta = self._pedir("GET", f"/git/commits/{commit}")
        return resposta.get("tree", {}).get("sha", "")

    def arquivos_da_arvore(self, arvore):
        """{caminho: resumo} do que já está lá. Pasta não entra, só arquivo."""
        resposta = self._pedir("GET", f"/git/trees/{arvore}?recursive=1")
        if resposta is None:
            return {}
        if resposta.get("truncated"):
            raise NaoDeuCerto(
                "O repositório tem arquivos demais para o GitHub listar de uma vez. "
                "Use um repositório só para o backup do sistema.")
        return {
            item["path"]: item["sha"]
            for item in resposta.get("tree", [])
            if item.get("type") == "blob"
        }

    # ---------------------------------------------------------------- escrita
    def criar_blob(self, dados):
        resposta = self._pedir("POST", "/git/blobs", {
            "content": base64.b64encode(dados).decode("ascii"),
            "encoding": "base64",
        })
        return resposta["sha"]

    def criar_arvore(self, entradas, base=None):
        corpo = {"tree": entradas}
        if base:
            corpo["base_tree"] = base
        return self._pedir("POST", "/git/trees", corpo)["sha"]

    def criar_commit(self, mensagem, arvore, pais):
        corpo = {"message": mensagem, "tree": arvore, "parents": pais}
        return self._pedir("POST", "/git/commits", corpo)["sha"]

    def mover_ramo(self, nome, commit, criar=False):
        if criar:
            self._pedir("POST", "/git/refs", {"ref": f"refs/heads/{nome}", "sha": commit})
        else:
            self._pedir("PATCH", f"/git/refs/heads/{nome}", {"sha": commit})

    # ---------------------------------------------------------------- o envio
    def enviar(self, arquivos, ramo, mensagem):
        """Manda o que mudou e devolve o que foi feito.

        Nada muda no GitHub quando nenhum arquivo mudou: um commit vazio por
        atualização encheria o histórico de ruído e esconderia o que de fato mudou.
        """
        arquivos = list(arquivos)
        if not arquivos:
            raise NaoDeuCerto("Não achei arquivo nenhum do sistema para enviar.")

        commit_atual = self.ramo(ramo)
        arvore_atual = self.arvore_do_commit(commit_atual) if commit_atual else ""
        existentes = self.arquivos_da_arvore(arvore_atual) if arvore_atual else {}

        entradas, enviados, novos = [], 0, []
        locais = {arquivo.caminho for arquivo in arquivos}
        for arquivo in arquivos:
            resumo = arquivo.resumo
            if existentes.get(arquivo.caminho) == resumo:
                continue
            if arquivo.caminho not in existentes:
                novos.append(arquivo.caminho)
            entrada = {"path": arquivo.caminho, "mode": MODO_ARQUIVO, "type": "blob"}
            texto = _como_texto(arquivo.dados)
            if texto is None:
                entrada["sha"] = self.criar_blob(arquivo.dados)
            else:
                # O GitHub grava o texto em UTF-8, os mesmos bytes daqui: o resumo do
                # próximo envio bate e o arquivo não sobe de novo.
                entrada["content"] = texto
            entradas.append(entrada)
            enviados += 1

        apagados = 0
        for caminho in existentes:
            if caminho not in locais:
                # sha nulo na árvore é como o git apaga um arquivo.
                entradas.append({"path": caminho, "mode": MODO_ARQUIVO, "type": "blob",
                                 "sha": None})
                apagados += 1

        if not entradas:
            return Resultado(enviou=False, commit=commit_atual or "", ao_todo=len(arquivos),
                             mensagem="Nada mudou desde o último envio.")

        arvore = arvore_atual or None
        for lote in _em_lotes(entradas):
            # Cada lote parte da árvore do anterior: o resultado é um commit só.
            arvore = self.criar_arvore(lote, base=arvore)
        commit = self.criar_commit(mensagem, arvore, [commit_atual] if commit_atual else [])
        self.mover_ramo(ramo, commit, criar=not commit_atual)
        return Resultado(
            enviou=True, commit=commit, enviados=enviados, apagados=apagados,
            ao_todo=len(arquivos), novos_caminhos=novos,
            mensagem=(f"{enviados} arquivo{'s' if enviados != 1 else ''} enviado"
                      f"{'s' if enviados != 1 else ''}"
                      + (f" e {apagados} apagado{'s' if apagados != 1 else ''}" if apagados else "")
                      + f", commit {commit[:7]}."),
        )


def _como_texto(dados):
    """O conteúdo como texto, ou None quando é binário (precisa ir como blob)."""
    if b"\x00" in dados:
        return None
    try:
        return dados.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _em_lotes(entradas):
    """Reparte as entradas da árvore em pedidos de tamanho que o GitHub aceita bem."""
    lote, tamanho = [], 0
    for entrada in entradas:
        peso = len((entrada.get("content") or "").encode("utf-8"))
        if lote and (tamanho + peso > LOTE_DE_BYTES or len(lote) >= LOTE_DE_ARQUIVOS):
            yield lote
            lote, tamanho = [], 0
        lote.append(entrada)
        tamanho += peso
    if lote:
        yield lote


def validade_do_token(dono, repositorio, token, abrir=None):
    """Até quando o token vale, para avisar ANTES de o backup parar.

    O GitHub manda `github-authentication-token-expiration` em toda resposta autenticada
    com token de escopo fino. Lido aqui, ele vira aviso dez dias antes em vez de uma
    descoberta no dia em que a cópia de fora do servidor já não existe mais.

    Devolve (respondeu, data). `respondeu` separa "o GitHub disse que este token não
    vence" de "não consegui perguntar": sem essa diferença, um minuto sem internet
    apagaria a validade já conhecida e o aviso de vencimento desapareceria calado.
    A data é None quando o token não tem prazo — o clássico pode não ter.

    Não levanta erro: isto é vigia, e vigia que derruba o envio é pior que vigia nenhum.
    Quem reporta recusa de token é o envio.
    """
    pedido = Request(f"{API}/repos/{dono}/{repositorio}", method="GET", headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "studio-sistema",
    })
    try:
        cabecalhos = (abrir or _cabecalhos)(pedido)
    except (HTTPError, URLError, OSError, socket.timeout, TimeoutError):
        return False, None
    bruto = (cabecalhos or {}).get("github-authentication-token-expiration") or ""
    # Vem como "2026-12-31 17:00:00 UTC" ou "2026-12-31T17:00:00Z"; só a data interessa.
    bruto = bruto.strip().replace("T", " ")
    try:
        return True, date.fromisoformat(bruto[:10])
    except ValueError:
        return True, None


def _cabecalhos(pedido):
    """Os cabeçalhos da resposta, em minúsculas. Separado para o teste poder trocar."""
    with urlopen(pedido, timeout=TEMPO_LIMITE) as resposta:  # noqa: S310 - https fixo
        return {chave.lower(): valor for chave, valor in resposta.headers.items()}


def _abrir(pedido):
    """Faz o pedido e devolve o JSON. None quando ainda não há nada para ler.

    "Ainda não há nada para ler" tem DUAS respostas diferentes, e as duas são esperadas:

    * **404** quando o ramo não existe num repositório que já tem commits;
    * **409 "Git Repository is empty."** quando o repositório não tem commit nenhum.

    O segundo caso é justamente o do repositório recém-criado, que é como TODO primeiro
    envio começa. Tratá-lo como erro travava o backup exatamente na primeira vez em que
    alguém o usava, com um recado que mandava tentar de novo — e tentar de novo dava no
    mesmo, para sempre. Medido contra a API de verdade em 14/10/2026: `GET
    /git/ref/heads/main` num repositório vazio responde 409, não 404.

    Só a LEITURA é perdoada assim. Escrever (criar blob, árvore, commit e ramo) funciona
    normalmente em repositório vazio, então um 409 vindo de uma escrita é conflito de
    verdade — dois envios ao mesmo tempo — e continua sendo erro.
    """
    try:
        with urlopen(pedido, timeout=TEMPO_LIMITE) as resposta:  # noqa: S310 - https fixo
            corpo = resposta.read()
            return json.loads(corpo) if corpo else {}
    except HTTPError as erro:
        if erro.code == 404:
            return None
        if erro.code == 409 and pedido.get_method() == "GET" and _esta_vazio(erro):
            return None
        raise NaoDeuCerto(_explicar(erro)) from erro
    except (URLError, socket.timeout, TimeoutError) as erro:
        raise NaoDeuCerto(
            "Não consegui falar com o GitHub. O servidor da loja precisa de internet "
            f"para este envio ({erro})."
        ) from erro
    except json.JSONDecodeError as erro:
        raise NaoDeuCerto(f"O GitHub respondeu algo que não entendi ({erro}).") from erro


def _detalhe(erro):
    """A frase que o GitHub mandou no corpo do erro, lida UMA vez.

    O corpo de um HTTPError é um fluxo: quem lê primeiro leva tudo, e o segundo a ler
    recebe vazio. Como a mesma resposta é olhada duas vezes — para saber se é
    repositório vazio e para explicar o erro na tela —, a leitura fica guardada aqui.
    """
    guardado = getattr(erro, "_detalhe_lido", None)
    if guardado is None:
        try:
            guardado = json.loads(erro.read() or b"{}").get("message", "")
        except (ValueError, OSError):
            guardado = ""
        erro._detalhe_lido = guardado  # noqa: SLF001 - é o próprio objeto de erro
    return guardado


def _esta_vazio(erro):
    """O 409 é "o repositório não tem commit nenhum"? A resposta vem no corpo."""
    return "empty" in _detalhe(erro).lower()


def _explicar(erro):
    """A resposta do GitHub em português, e não "HTTP Error 401"."""
    detalhe = _detalhe(erro)
    if erro.code in (403, 429) and "rate limit" in detalhe.lower():
        return ("O GitHub pediu para esperar: foram muitos envios em pouco tempo. O token "
                "está certo e nada se perdeu; o sistema tenta de novo sozinho.")
    if erro.code == 401:
        return ("O GitHub recusou o token (401). Gere um token novo e cole de novo na tela.")
    if erro.code == 403:
        return ("O GitHub recusou o acesso (403). Confira se o token tem permissão de "
                "escrita no conteúdo deste repositório." + (f" {detalhe}" if detalhe else ""))
    if erro.code == 409:
        # Repositório vazio não chega mais aqui: a leitura já trata isso como "ainda
        # não há nada lá". O que sobra é o ramo ter se mexido no meio do envio.
        return ("O ramo mudou no GitHub enquanto o envio acontecia, então o sistema "
                "parou para não passar por cima. Tente de novo." +
                (f" {detalhe}" if detalhe else ""))
    if erro.code == 422:
        return f"O GitHub não aceitou o envio (422). {detalhe}".strip()
    return f"O GitHub respondeu {erro.code}. {detalhe}".strip()
