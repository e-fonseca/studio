"""Juntar os arquivos do sistema e mandá-los para o GitHub.

A lista é montada por **inclusão**: entra o que é código do sistema, e só isso. Regra
de exclusão esquecida manda o arquivo que não devia; regra de inclusão esquecida apenas
deixa de mandar um arquivo, e aí alguém nota.

No servidor, o programa fica em `C:\\cabana-sistema\\app` e os dados ficam em pastas
IRMÃS (`dados`, `logs`, `backups`, `config`), então banco, anexo e segredo já estão
fora do alcance desta varredura. As exclusões abaixo existem para o computador de
desenvolvimento, onde `var/` fica dentro da pasta do projeto, e como cinto de
segurança para instalação antiga.
"""

import os
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.auditoria.servicos import registrar

from .github import Arquivo, GitHub, NaoDeuCerto, Resultado
from .models import ConfiguracaoDeBackup

# O que é código do sistema. Imagem entra porque o logo e os ícones são do programa.
EXTENSOES = {
    ".py", ".html", ".css", ".js", ".json", ".md", ".txt", ".svg", ".ico", ".png",
    ".webmanifest", ".ps1", ".sh", ".cfg", ".toml",
}
# Arquivo sem ponto no nome que ainda é do sistema.
NOMES = {"VERSAO", "LEIA-ME.txt", ".gitignore"}

# Pasta que nunca entra, esteja onde estiver.
PASTAS_FORA = {
    "__pycache__", ".git", ".pytest_cache", ".ruff_cache", "node_modules",
    # Dados e sobras: num servidor antigo, ou no computador de desenvolvimento, estas
    # pastas podem estar dentro da pasta do programa.
    "var", "dados", "logs", "backups", "wheels", "downloads", "firebird",
    "anexos", "anexos-teste", "copia-set", "certificado", "staticfiles",
}

# Um arquivo de código não passa disto. O que passar é dado disfarçado de código.
TAMANHO_MAXIMO = 2 * 1024 * 1024
# Teto do envio inteiro, para um erro de configuração não virar repositório de 1 GB.
TAMANHO_TOTAL_MAXIMO = 60 * 1024 * 1024


def _proibidas():
    """As pastas de dados pelo caminho de verdade, lido das configurações.

    Não basta o nome: CABANA_MEDIA_ROOT pode apontar para qualquer lugar, e se um dia
    apontar para dentro da pasta do programa, os anexos de nota fiscal entrariam no
    envio por não se chamarem "anexos".
    """
    caminhos = []
    for chave in ("MEDIA_ROOT", "STATIC_ROOT"):
        valor = getattr(settings, chave, "")
        if valor:
            caminhos.append(Path(valor).resolve())
    return caminhos


def caminhos_do_sistema(raiz=None):
    """Os arquivos que vão no backup: [(caminho no disco, caminho no repositório)].

    Anda com `os.walk` e PODA a pasta na descida, em vez de listar tudo e filtrar
    depois: `.git` sozinho tem mais arquivos do que o sistema inteiro, e numa pasta
    de rede a diferença é entre um segundo e um minuto e meio. Isto é lido pela tela,
    que só precisa da contagem, então não pode ser caro.
    """
    raiz = Path(raiz or settings.BASE_DIR).resolve()
    proibidas = _proibidas()
    achados, total = [], 0
    for pasta, subpastas, arquivos in os.walk(raiz, followlinks=False):
        atual = Path(pasta)
        # Poda: a lista é alterada no lugar, e o os.walk não desce no que saiu dela.
        subpastas[:] = sorted(
            nome for nome in subpastas
            if nome not in PASTAS_FORA
            and not any(_dentro(atual / nome, proibida) for proibida in proibidas)
        )
        for nome in sorted(arquivos):
            caminho = atual / nome
            if caminho.is_symlink() or not caminho.is_file():
                continue
            if nome not in NOMES and caminho.suffix.lower() not in EXTENSOES:
                continue
            tamanho = caminho.stat().st_size
            if tamanho > TAMANHO_MAXIMO:
                continue
            total += tamanho
            if total > TAMANHO_TOTAL_MAXIMO:
                raise NaoDeuCerto(
                    "A pasta do sistema passa do tamanho que o backup manda. Confira se "
                    "não há arquivo de dados dentro dela.")
            achados.append((caminho, caminho.relative_to(raiz).as_posix()))
    achados.sort(key=lambda par: par[1])
    return achados


def quantos_arquivos(raiz=None):
    """A contagem, sem ler o conteúdo de nada. É o que a tela mostra."""
    return len(caminhos_do_sistema(raiz))


def arquivos_do_sistema(raiz=None):
    """Os mesmos arquivos, já com o conteúdo lido, prontos para enviar."""
    return [Arquivo(caminho=relativo, dados=caminho.read_bytes())
            for caminho, relativo in caminhos_do_sistema(raiz)]


def _dentro(caminho, pasta):
    try:
        Path(caminho).resolve().relative_to(pasta)
    except (ValueError, OSError):
        return False
    return True


def mensagem_do_commit(versao, quando=None):
    quando = quando or timezone.localtime()
    return f"versão {versao} no servidor da loja · {quando:%d/%m/%Y %H:%M}"


def enviar(usuario=None, configuracao=None, cliente=None, raiz=None):
    """Manda o código para o GitHub e guarda o resultado na configuração.

    Devolve o `Resultado`. Levanta `NaoDeuCerto` com a frase que a tela mostra: quem
    chama decide se isso é recado na tela ou linha no log da atualização.
    """
    from apps.core import versao as versao_do_sistema  # noqa: PLC0415

    configuracao = configuracao or ConfiguracaoDeBackup.atual()
    faltando = configuracao.falta_preencher
    if faltando:
        raise NaoDeuCerto("Antes de enviar, preencha " + " e ".join(faltando) + ".")

    dono, repositorio = configuracao.dono_e_repositorio
    github = cliente or GitHub(dono, repositorio, configuracao.token)
    arquivos = arquivos_do_sistema(raiz)
    versao = versao_do_sistema.atual().numero
    try:
        resultado = github.enviar(arquivos, configuracao.ramo or "main",
                                  mensagem_do_commit(versao))
    except NaoDeuCerto as erro:
        _guardar(configuracao, deu_certo=False, mensagem=str(erro))
        registrar("backup.envio_falhou", usuario=usuario, recurso=configuracao,
                  recurso_rotulo=configuracao.repositorio[:200],
                  depois={"erro": str(erro)[:300]})
        raise

    _guardar(configuracao, deu_certo=True, mensagem=resultado.mensagem,
             commit=resultado.commit, arquivos=resultado.ao_todo)
    registrar("backup.enviado", usuario=usuario, recurso=configuracao,
              recurso_rotulo=configuracao.repositorio[:200],
              depois={"commit": resultado.commit, "enviados": resultado.enviados,
                      "apagados": resultado.apagados, "ao_todo": resultado.ao_todo,
                      "versao": versao})
    return resultado


def _guardar(configuracao, *, deu_certo, mensagem, commit="", arquivos=0):
    agora = timezone.now()
    configuracao.ultimo_envio_em = agora
    configuracao.ultimo_deu_certo = deu_certo
    configuracao.ultimo_resultado = mensagem[:300]
    campos = ["ultimo_envio_em", "ultimo_deu_certo", "ultimo_resultado", "ultimo_commit",
              "ultimos_arquivos"]
    if deu_certo:
        # A data que importa para saber se a loja está coberta: a última tentativa pode
        # ser de hoje e ter falhado em todas as de três meses.
        configuracao.ultimo_sucesso_em = agora
        campos.append("ultimo_sucesso_em")
    if commit:
        configuracao.ultimo_commit = commit[:40]
    if arquivos:
        configuracao.ultimos_arquivos = arquivos
    configuracao.save(update_fields=campos)
