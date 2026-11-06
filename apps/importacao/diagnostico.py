"""Explicação dos erros de importação, em linguagem de loja.

Quando a importação falha, a mensagem técnica sozinha não resolve nada para quem
está na gerência. Aqui cada erro conhecido vira: o que aconteceu, por que, e o
que fazer, na ordem. Erro desconhecido cai na explicação geral, que também diz o
que enviar para quem for olhar.
"""

import re
from dataclasses import dataclass, field

from apps.core import pastas


@dataclass
class Explicacao:
    titulo: str
    o_que_aconteceu: str
    como_resolver: list = field(default_factory=list)
    conhecido: bool = True


# Ordem importa: a primeira que casar é a usada.
CAUSAS = [
    (
        r"A conferência do backup não deixou importar",
        Explicacao(
            titulo="O arquivo de backup não passou na conferência",
            o_que_aconteceu="Antes de ler, o sistema confere o tamanho e a data do arquivo de backup. "
                            "Desta vez alguma coisa não bateu e ele parou ali, sem trocar os números "
                            "da tela. O motivo está escrito na própria mensagem, acima.",
            como_resolver=[
                "Abra a pasta do backup no servidor e veja se o arquivo mais novo terminou de ser gravado: "
                "backup pela metade tem tamanho muito menor que o de ontem.",
                "Se o backup do SET não rodou, o problema é lá: não existe arquivo mais novo para o "
                "sistema ler, e os números da tela continuam sendo os da última importação boa.",
                "Com o arquivo certo na pasta, clique em Importar agora na tela de Importações.",
                "Se o arquivo está certo e a conferência só estranhou o tamanho ter mudado, use o botão "
                "Forçar atualização com o último backup, na mesma tela.",
            ],
        ),
    ),
    (
        r"está compactado, mas não tem nenhum arquivo",
        Explicacao(
            titulo="O arquivo compactado não tem o banco do SET dentro",
            o_que_aconteceu="O sistema abriu o .zip mais recente da pasta do backup, mas lá dentro não há "
                            "nenhum arquivo .FDB nem .FBK, que é o banco do SET.",
            como_resolver=[
                "Abra a pasta do backup e confira o que o programa de backup está gravando.",
                "Se o backup do banco for gerado em outra pasta, informe a pasta certa rodando: "
                f"powershell -ExecutionPolicy Bypass -File {pastas.ATUALIZAR} "
                "-PastaBackupSet \"CAMINHO\\DA\\PASTA\"",
                "Depois clique em Importar agora.",
            ],
        ),
    ),
    (
        r"Não consegui abrir o backup compactado",
        Explicacao(
            titulo="O backup compactado está incompleto",
            o_que_aconteceu="O .zip do backup não abriu. Normalmente é porque a importação pegou o arquivo "
                            "enquanto ele ainda estava sendo gravado, ou a gravação do backup falhou.",
            como_resolver=[
                "Confira na pasta do backup se o arquivo mais novo terminou de ser gravado.",
                "Clique em Importar agora para tentar de novo.",
                "Se repetir, veja se o programa que gera o backup do SET terminou sem erro.",
            ],
        ),
    ),
    (
        r"Não sei onde está o backup",
        Explicacao(
            titulo="O sistema não sabe onde fica o backup do SET",
            o_que_aconteceu="A configuração STUDIO_SET_BACKUP está vazia, então não há pasta para procurar.",
            como_resolver=[
                "No servidor, rode como administrador: powershell -ExecutionPolicy Bypass -File "
                f"{pastas.ATUALIZAR} -PastaBackupSet \"C:\\backup-Set\\Studio\\Set-Studio\"",
                "Ou abra C:\\studio-sistema\\config\\studio.env e escreva o caminho na linha "
                "STUDIO_SET_BACKUP, depois reinicie a tarefa \\Studio\\StudioSistema.",
                "Em seguida clique em Importar agora.",
            ],
        ),
    ),
    (
        r"Não encontrei o arquivo de origem|não achei nenhum backup",
        Explicacao(
            titulo="A pasta do backup existe, mas não tem backup para ler",
            o_que_aconteceu="O caminho configurado não tem nenhum arquivo .FDB ou .FBK com conteúdo. "
                            "Pode ser que o backup do SET não tenha rodado, ou que esteja em outra pasta.",
            como_resolver=[
                "Abra a pasta no servidor e confirme que existe um arquivo .FDB ou .FBK recente.",
                "Se o backup estiver em outro lugar, rode o atualizar.ps1 com -PastaBackupSet apontando "
                "para a pasta certa.",
                "Se a pasta estiver vazia, o problema é no backup do SET, não aqui.",
            ],
        ),
    ),
    (
        r"Acesso negado|Permission denied|Errno 13|WinError 5",
        Explicacao(
            titulo="O sistema não tem permissão para ler o backup",
            o_que_aconteceu="A importação roda com a conta SERVIÇO DE REDE do Windows, e essa conta não "
                            "consegue abrir a pasta do backup. É comum quando o backup fica em disco "
                            "externo, pasta de rede ou pasta de outro usuário.",
            como_resolver=[
                "Prefira uma pasta local do próprio servidor, como C:\\backup-Set.",
                "Se precisar manter o lugar atual, dê permissão de leitura à conta SERVIÇO DE REDE "
                "nessa pasta.",
                "Pasta de rede não funciona para essa conta: nesse caso, copie o backup para o disco "
                "do servidor antes da importação.",
            ],
        ),
    ),
    (
        r"firebird-driver não está instalada",
        Explicacao(
            titulo="Falta a biblioteca que lê o banco do SET",
            o_que_aconteceu="A instalação não colocou a biblioteca firebird-driver no servidor.",
            como_resolver=[
                "Rode a atualização de novo com o pacote completo: powershell -ExecutionPolicy Bypass "
                f"-File {pastas.ATUALIZAR}",
                f"Se repetir, envie o log de {pastas.LOGS}.",
            ],
        ),
    ),
    (
        r"WinError 193|aplicativo Win32|é de 32 bits|é de 64 bits",
        Explicacao(
            titulo="O motor que lê o banco do SET está na versão errada",
            o_que_aconteceu="Para ler a cópia do backup o sistema usa um motor Firebird próprio, e o "
                            "que está instalado é de 32 bits, enquanto o sistema é de 64. O Windows "
                            "recusa abrir um dentro do outro, então a leitura nem começa. O backup "
                            "está certo e nada disso afeta o SET.",
            como_resolver=[
                "No servidor, rode como administrador: powershell -ExecutionPolicy Bypass -File "
                f"{pastas.ATUALIZAR}",
                "A atualização troca o motor por um de 64 bits (ela baixa o Firebird 4 x64 se o "
                "servidor não tiver um) e já faz a importação no fim.",
                "Se o servidor estiver sem internet, baixe o zip Firebird-4.0.6.3221-0-x64.zip do "
                f"site firebirdsql.org, salve em {pastas.DOWNLOADS} e rode a atualização.",
            ],
        ),
    ),
    (
        r"Não consegui abrir a cópia|fbclient|engine13|Firebird",
        Explicacao(
            titulo="A cópia do backup não abriu",
            o_que_aconteceu="O motor Firebird próprio do sistema não conseguiu abrir o arquivo. Ou o "
                            "motor não foi instalado, ou o arquivo não é um banco do SET, ou a cópia "
                            "veio incompleta.",
            como_resolver=[
                "Confira se existe a pasta C:\\studio-sistema\\firebird com o arquivo fbclient.dll.",
                "Confira se o arquivo do backup abre normalmente (tamanho compatível com os anteriores).",
                "Rode a atualização de novo: ela monta o motor Firebird quando ele está faltando.",
            ],
        ),
    ),
    (
        r"gbak",
        Explicacao(
            titulo="O backup está em .FBK e falta a ferramenta que restaura",
            o_que_aconteceu="Arquivos .FBK precisam ser restaurados pelo gbak antes da leitura, e ele "
                            "não foi encontrado no servidor.",
            como_resolver=[
                "Rode a atualização de novo: ela procura o gbak junto do Firebird do servidor.",
                "Se o SET também gera um .FDB, aponte a pasta desse arquivo, que é lido direto.",
            ],
        ),
    ),
    (
        r"No space left|espaço em disco|WinError 112",
        Explicacao(
            titulo="Faltou espaço em disco",
            o_que_aconteceu="A importação copia o backup para C:\\studio-sistema\\dados\\copia-set e não "
                            "coube.",
            como_resolver=[
                "Libere espaço no disco C: do servidor.",
                "Confira a pasta de backups antigos, que costuma ser a que mais cresce.",
            ],
        ),
    ),
    (
        r"nenhuma venda registrada",
        Explicacao(
            titulo="O arquivo lido não parece ser o banco da loja",
            o_que_aconteceu="A cópia abriu, mas não tem vendas da empresa 1. Provavelmente é o backup de "
                            "outro sistema ou de outra empresa.",
            como_resolver=[
                "Confirme com quem cuida do backup qual arquivo é o do SET do Studio.",
                "Aponte a pasta desse arquivo com -PastaBackupSet.",
            ],
        ),
    ),
    (
        r"could not connect|connection refused|OperationalError",
        Explicacao(
            titulo="O banco do próprio sistema não respondeu",
            o_que_aconteceu="O PostgreSQL do sistema auxiliar estava fora do ar durante a importação.",
            como_resolver=[
                "Nos Serviços do Windows, confira o serviço cabana-postgres e inicie se estiver parado.",
                "Depois clique em Importar agora.",
            ],
        ),
    ),
]

GERAL = Explicacao(
    titulo="A importação parou com um erro não previsto",
    o_que_aconteceu="A mensagem abaixo veio do próprio sistema e não está no manual ainda.",
    como_resolver=[
        "Clique em Importar agora para tentar de novo: falhas de momento costumam passar.",
        "Se repetir, envie a mensagem do erro junto com o arquivo "
        "C:\\studio-sistema\\logs\\importacao.log.",
        "Enquanto isso, os números da última importação que deu certo continuam valendo.",
    ],
    conhecido=False,
)


def explicar(mensagem):
    """Devolve a explicação do erro. Sempre devolve algo: na dúvida, a geral."""
    if not mensagem:
        return None
    for padrao, explicacao in CAUSAS:
        if re.search(padrao, mensagem, re.IGNORECASE):
            return explicacao
    return GERAL
