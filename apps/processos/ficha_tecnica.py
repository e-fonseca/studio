"""Ficha técnica: de que o sistema é feito, lida do próprio sistema em funcionamento.

O Edson perguntou em 08/10/2026 qual linguagem e qual banco o sistema usa, e em
seguida pediu para essas informações entrarem na Base de processos. O lugar está
certo: a Base de processos existe para o que está na cabeça de uma pessoa não se
perder, e quem um dia precisar manter este sistema sem ter participado de nada
disso precisa justamente dessa lista.

A regra que manda no arquivo: **nada de número digitado à mão.** Versão escrita na
tela envelhece em silêncio — basta uma atualização de dependência e a ficha passa
a mentir, e uma ficha que mente é pior do que ficha nenhuma. Então cada peça é
perguntada a quem sabe a resposta agora: o Python diz a sua versão, o Django a
dele, o PostgreSQL responde pela conexão aberta, e o motor Firebird é lido do
próprio arquivo no disco. O que não puder ser lido aparece dizendo que não pôde,
nunca um palpite.

O que é escrito à mão aqui são as DECISÕES, que não se leem de lugar nenhum: por
que o sistema é isolado, por que o Firebird só lê a cópia e por que nenhuma tela
depende da internet. Essas não envelhecem sozinhas, e são o que explica o resto.
"""

import platform
import sys
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as versao_do_pacote
from pathlib import Path

import django
from django.conf import settings
from django.db import connection

from apps.core import versao as versao_do_sistema
from apps.importacao.fontes.firebird import _arquitetura_do_pe

NAO_LIDO = "não foi possível ler agora"


@dataclass(frozen=True)
class Peca:
    """Uma linha da tabela: o que é, qual versão, para que serve."""

    nome: str
    versao: str
    para_que: str

    @property
    def lida(self):
        return self.versao != NAO_LIDO


def _pacote(nome):
    """Versão de um pacote instalado, pelo que o próprio instalador registrou."""
    try:
        return versao_do_pacote(nome)
    except PackageNotFoundError:
        return NAO_LIDO


def _postgres():
    """Versão do PostgreSQL, perguntada à conexão que o sistema já usa.

    `pg_version` vem como inteiro (160010 é o 16.10). Abrir a conexão pode falhar
    quando o banco está parado, e nesse caso a ficha diz isso em vez de inventar:
    uma tela de documentação nunca derruba o sistema por causa do que documenta.
    """
    try:
        numero = connection.pg_version
    except Exception:  # noqa: BLE001 - o backend lança tipos variados quando o banco não responde
        return NAO_LIDO
    maior, menor = divmod(numero, 10000)
    return f"{maior}.{menor}"


def _firebird():
    """O motor que lê a cópia do backup do SET: versão e arquitetura.

    Não se carrega a DLL aqui. Carregar é o que `manage.py conferir_firebird` faz, e
    é caro e capaz de falhar. A versão vem de quem instalou o motor: o instalador
    grava `CABANA_FIREBIRD_VERSAO` no `cabana.env`. A arquitetura é lida dos
    primeiros bytes do próprio arquivo, porque motor de 32 bits dentro de um Python
    de 64 já travou a importação uma vez e vale ter à vista.
    """
    caminho = str(getattr(settings, "IMPORTACAO_FIREBIRD_CLIENTE", "") or "")
    bruta = str(getattr(settings, "IMPORTACAO_FIREBIRD_VERSAO", "") or "")
    # O instalador grava "4.0.6.3221-0"; na tela basta "4.0.6".
    numero = ".".join(bruta.split("-")[0].split(".")[:3])
    arquivo = Path(caminho) if caminho else None
    arquitetura = _arquitetura_do_pe(arquivo) if arquivo and arquivo.exists() else None
    if numero and arquitetura:
        return f"{numero} ({arquitetura})", caminho
    if numero:
        return numero, caminho
    if arquitetura:
        return arquitetura, caminho
    return NAO_LIDO, caminho


def _sistema_operacional():
    nome = platform.system() or NAO_LIDO
    versao = platform.release()
    bits = 64 if sys.maxsize > 2**32 else 32
    return f"{nome} {versao} ({bits} bits)".strip()


def pecas():
    """A tabela do "de que o sistema é feito", na ordem em que uma pessoa pergunta."""
    motor_firebird, _caminho = _firebird()
    banco = settings.DATABASES["default"]
    return [
        Peca("Python", platform.python_version(),
             "A linguagem em que o sistema é escrito."),
        Peca("Django", django.get_version(),
             "O framework web: telas, banco, login e permissões. Versão LTS, de suporte estendido."),
        Peca("PostgreSQL", _postgres(),
             f"O banco de dados do sistema, na porta {banco.get('PORT') or '5432'}."),
        Peca("psycopg", _pacote("psycopg"),
             "A peça que liga o Django ao PostgreSQL."),
        Peca("Waitress", _pacote("waitress"),
             "O servidor web que entrega as telas; o HTTPS atende na porta "
             f"{getattr(settings, 'PORTA_HTTPS', '8443')}."),
        Peca("Firebird (motor de leitura)", motor_firebird,
             "Abre a cópia do backup do SET, só para ler. Nunca fala com o Firebird do SET."),
        Peca("firebird-driver", _pacote("firebird-driver"),
             "A peça que liga o Python ao motor Firebird."),
        Peca("django-axes", _pacote("django-axes"),
             "A trava de tentativas de senha."),
        Peca("openpyxl", _pacote("openpyxl"),
             "Gera as planilhas que o sistema exporta."),
        Peca("cryptography", _pacote("cryptography"),
             "Gera o certificado do HTTPS e a autoridade da loja."),
        Peca("Sistema operacional", _sistema_operacional(),
             "A máquina onde tudo isto está rodando."),
    ]


def caminhos():
    """Onde cada coisa mora no disco, para quem for mexer sem conhecer o sistema."""
    _motor, firebird = _firebird()
    return [
        ("O sistema inteiro", str(settings.BASE_DIR)),
        ("Cópia do backup do SET", str(getattr(settings, "IMPORTACAO_PASTA_TRABALHO", ""))),
        ("Onde o backup do SET é procurado", str(getattr(settings, "IMPORTACAO_BACKUP_ORIGEM", "")) or NAO_LIDO),
        ("Motor Firebird", firebird or NAO_LIDO),
        ("Anexos enviados nas telas", str(settings.MEDIA_ROOT)),
    ]


# Decisões de projeto. Estas são escritas à mão de propósito: não se leem de lugar
# nenhum, não envelhecem sozinhas, e sem elas a tabela acima é uma lista de nomes.
DECISOES = [
    ("Tudo mora dentro da pasta do sistema",
     "O Python é a versão “embeddable”, que não se instala no Windows nem mexe no PATH, e o "
     "PostgreSQL é um serviço próprio numa porta própria. Nenhum dos dois concorre com o que "
     "já estava no servidor, e desinstalar o sistema é apagar uma pasta."),
    ("O Firebird aqui só lê, e só a cópia",
     "Ele é motor embutido, não serviço: abre o arquivo do backup do SET que foi copiado para "
     "a pasta do sistema. Nunca abre o banco que o SET está usando e nunca escreve nada de "
     "volta. Foi a condição posta no começo do projeto, e é por isso que a importação não "
     "pode atrapalhar a operação da loja."),
    ("Nenhuma tela depende da internet",
     "Não há biblioteca baixada de fora: o JavaScript do sistema são arquivos próprios. Se a "
     "internet da loja cair, o sistema continua funcionando normalmente na rede local. Três "
     "coisas saem para fora, e nenhuma delas é uma tela esperando resposta: a busca do tempo "
     "do dia, que é tarefa do servidor de madrugada; a descoberta das coordenadas da cidade, "
     "que roda uma vez, ao salvar a configuração do tempo; e o backup do código no GitHub, "
     "quando a loja liga esse backup, no fim de cada atualização. Falhando qualquer uma "
     "delas, o erro fica guardado para a tela mostrar e o resto do sistema não sente."),
    ("O tempo do dia é buscado de madrugada, e pede só o nome da cidade",
     "Todo dia às 06:10 o servidor pergunta a um serviço aberto de meteorologia como foi o "
     "tempo dos últimos dias e o que vem pela frente, sem cadastro e sem mensalidade, e "
     "grava ao lado do que a loja vendeu. Para saber onde buscar basta a cidade escrita na "
     "tela: a latitude e a longitude o sistema descobre sozinho e escreve o lugar que "
     "entendeu, para alguém poder conferir que não é a cidade de mesmo nome em outro estado. "
     "Se não alcançar a internet, o erro fica guardado para aparecer na tela e mais nada no "
     "sistema é afetado. O que uma pessoa da loja anota na tela nunca é apagado pela busca: "
     "quem estava no balcão viu o que a média de um quadrado de quilômetros não vê."),
    ("Previsão não entra em conta nenhuma do sistema",
     "O sistema guarda a previsão dos próximos dias para a loja se preparar, porque é no fim "
     "de semana que ela fatura e saber na quinta que vai chover no sábado dá tempo de fazer "
     "alguma coisa. Mas dia previsto fica marcado como previsão e não entra na medida de "
     "quanto a chuva custa: essa conta é só de dia que já fechou. Média de palpite pareceria "
     "medida e não é. O dia de hoje também nasce marcado, porque às seis da manhã a chuva da "
     "tarde ainda é palpite; na busca do dia seguinte ele entra já fechado."),
    ("Tela que é recurso de outra sai do menu, mas continua existindo",
     "Duas telas saíram do menu em 14/10/2026 porque cada uma virou um quadro dentro da tela "
     "em que a decisão é tomada: a comparação com o ano passado abre pela Lista de compra e o "
     "tempo abre pela Visão geral. Menu de dezesseis linhas não é menu. As telas continuam "
     "inteiras, porque é nelas que estão a tabela produto a produto, o arquivo para o Excel e "
     "o campo de anotar o dia; o que muda é que se chega a elas pelo quadro, e cada uma traz "
     "o caminho de volta para a tela de onde abriu."),
    ("Cada importação é uma foto, e as fotos não se somam",
     "Toda informação vinda do SET carrega a importação de onde veio, e cada tela pergunta "
     "por uma importação só. Por isso importar duas vezes no mesmo dia não dobra número "
     "nenhum."),
    ("Para o GitHub sobe o código, nunca o banco",
     "O backup no GitHub guarda uma cópia do programa fora do servidor, e sobe sozinho no fim "
     "de cada atualização. Sobe só código: arquivos de programa, de tela e de documentação. O "
     "banco de dados não vai, e nem poderia — tem nome de cliente vindo do SET, extrato "
     "bancário conferido e nota fiscal de fornecedor dentro. Os anexos enviados nas telas "
     "também ficam fora. A escolha é por inclusão: arquivo que ninguém listou não sobe, "
     "porque esquecer de incluir deixa de salvar um arquivo e esquecer de excluir vaza um. O "
     "backup dos dados continua sendo o local, de madrugada, dentro do servidor."),
    ("Nota fiscal se confere pelo XML; o PDF é o retrato dela",
     "O pedido ao fornecedor fica guardado e aceita os documentos que voltam: pedido "
     "assinado, romaneio, nota fiscal. Do XML da nota o sistema lê cada item em campo próprio "
     "e confere linha por linha contra o que foi pedido. Do PDF, não: o PDF é o retrato da "
     "nota, o conteúdo dele são posições de texto numa página, e o que se tira dali é "
     "adivinhação. Numa tela que confere dinheiro, adivinhação é pior que nada, então o PDF "
     "fica guardado e à vista, que é o controle que ele serve. Foto de papel também fica "
     "guardada: ler número de foto exigiria mandar a imagem para fora."),
    ("O sistema se limpa sozinho de madrugada",
     "Guardar uma foto por sincronização, três vezes por dia, faria o disco e o banco "
     "crescerem para sempre. Todo dia às 03:40 o sistema apaga a cópia do banco do SET, que "
     "já foi lida e tem dado pessoal de cliente dentro, as fotos além das dez últimas "
     "sincronizações e os registros vencidos. O que uma pessoa digitou nunca entra nessa "
     "limpeza, e nada nela encosta no SET."),
]


def montar():
    """Tudo o que a tela da ficha técnica mostra."""
    return {
        "versao": versao_do_sistema.atual(),
        "pecas": pecas(),
        "caminhos": caminhos(),
        "decisoes": DECISOES,
    }
