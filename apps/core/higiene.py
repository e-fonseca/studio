"""Limpeza do que o sistema acumula sozinho, sem tocar no SET nem no que é nosso.

Existe por três coisas que crescem sem parar e ninguém olha:

* a cópia do banco do SET, 382 MB parados em ``dados\\copia-set`` depois que a
  importação já leu tudo, com nome e CPF de cliente dentro;
* as fotos dos dados do SET além das últimas dez importações;
* o registro de sessões, de acesso e de envio de relatório, uma linha por
  entrada de usuário e por e-mail mandado.

Desde a 1.25.0 a sincronização roda três vezes por dia, então tudo isso cresce
três vezes mais rápido do que quando era uma.

A regra é a mesma do resto do sistema: **nada daqui apaga o que é nosso** (ficha
de fornecedor, pagamento previsto, inventário, extrato conferido, auditoria) e
nada daqui encosta no SET. Sai só o que o sistema sabe refazer sozinho na
próxima sincronização, e sai só com ``--fazer``.
"""

from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.utils import timezone

# Quanto tempo de histórico de acesso e de envio de relatório fica guardado. É o
# mesmo prazo dos logs de instalação, para não ter dois prazos para decorar.
DIAS = 90


@dataclass
class Tarefa:
    """Uma coisa para limpar: o que é, quanto tem e se foi limpa."""

    nome: str
    explicacao: str
    quantidade: int = 0
    # No singular: a palavra ganha o "s" quando é mais de um ("1 arquivo", "4 arquivos").
    unidade: str = "registro"
    bytes: int = 0
    detalhe: str = ""
    feito: bool = False
    # Quando a limpeza não pôde acontecer agora (importação rodando, arquivo em
    # uso). Não é erro: é motivo, e a tela ou o log mostra em português.
    aviso: str = ""

    @property
    def tem_o_que_limpar(self):
        return self.quantidade > 0

    @property
    def quantos(self):
        """O número com a palavra certa: "1 arquivo", "706 registros"."""
        palavra = self.unidade if self.quantidade == 1 else f"{self.unidade}s"
        return f"{numero(self.quantidade)} {palavra}"


@dataclass
class Resultado:
    """O que o sistema achou e o que fez, para o comando e o log mostrarem igual."""

    tarefas: list = field(default_factory=list)
    fez: bool = False
    banco_antes: int = 0
    banco_depois: int = 0
    aviso_do_banco: str = ""

    @property
    def total_de_registros(self):
        return sum(t.quantidade for t in self.tarefas if t.unidade == "registro")

    @property
    def total_de_bytes(self):
        return sum(t.bytes for t in self.tarefas)

    @property
    def tem_o_que_limpar(self):
        return any(t.tem_o_que_limpar for t in self.tarefas)

    @property
    def avisos(self):
        return [t for t in self.tarefas if t.aviso]


def numero(quantidade):
    """Número do jeito que se escreve em português: 1.234, e não 1,234."""
    return f"{quantidade:,}".replace(",", ".")


def quanto(bytes_):
    """Tamanho em português, do jeito que se lê: 382,0 MB, 1,2 GB."""
    valor = float(bytes_)
    for unidade in ("B", "KB", "MB", "GB"):
        if valor < 1024 or unidade == "GB":
            texto = f"{valor:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
            return f"{texto} {unidade}"
        valor /= 1024
    return ""


def _apagar(consulta):
    """Apaga e devolve quantas linhas saíram, contando o que foi pela cascata."""
    quantidade, _ = consulta.delete()
    return quantidade


# ------------------------------------------------------------------ as tarefas


def copia_do_set(fazer=False):
    """A cópia do banco do SET que a importação deixou em dados\\copia-set.

    A importação copia o backup para ler num Firebird próprio e nunca reaproveita
    a cópia: a sincronização seguinte copia de novo, do zero. Depois de ler, o
    arquivo é só um banco do SET de 382 MB parado no disco, com dado pessoal de
    cliente dentro. Por isso esta é a primeira tarefa da lista.
    """
    tarefa = Tarefa(
        "Cópia do banco do SET",
        "A importação copia o backup para ler; depois de ler, a cópia não serve para mais nada.",
        unidade="arquivo",
    )
    pasta = getattr(settings, "IMPORTACAO_PASTA_TRABALHO", "")
    if not pasta:
        return tarefa
    pasta = Path(pasta)
    if not pasta.is_dir():
        return tarefa
    arquivos = sorted(caminho for caminho in pasta.iterdir() if caminho.is_file())
    tarefa.quantidade = len(arquivos)
    tarefa.bytes = sum(caminho.stat().st_size for caminho in arquivos)
    if not arquivos:
        return tarefa
    tarefa.detalhe = ", ".join(f"{c.name} ({quanto(c.stat().st_size)})" for c in arquivos[:4])

    from apps.importacao import servicos as importacao_servicos

    andando = importacao_servicos.em_andamento()
    if andando:
        tarefa.aviso = "Tem sincronização rodando agora; a cópia fica onde está até ela terminar."
        return tarefa
    if not fazer:
        return tarefa
    for caminho in arquivos:
        try:
            caminho.unlink()
        except OSError as erro:  # arquivo em uso pelo Firebird, por exemplo
            tarefa.aviso = f"Não consegui apagar {caminho.name}: {erro}"
            return tarefa
    tarefa.feito = True
    return tarefa


def fotos_do_set(fazer=False):
    """As fotos dos dados do SET além do limite de importações guardadas."""
    from apps.importacao import servicos as importacao_servicos

    manter = getattr(settings, "IMPORTACAO_MANTER", 10)
    tarefa = Tarefa(
        "Fotos antigas do SET",
        f"Cada sincronização guarda uma foto inteira dos dados; ficam as {manter} últimas.",
    )
    _, fora = importacao_servicos.fotos_fora_do_limite()
    contagens = [(rotulo, consulta.count()) for rotulo, consulta in fora]
    tarefa.quantidade = sum(quantidade for _, quantidade in contagens)
    tarefa.detalhe = ", ".join(
        f"{rotulo} {numero(quantidade)}" for rotulo, quantidade in contagens if quantidade
    )
    if fazer and tarefa.quantidade:
        for _, consulta in fora:
            consulta.delete()
        tarefa.feito = True
    return tarefa


def sessoes_vencidas(fazer=False):
    """As sessões cujo prazo já passou: ninguém volta a usar, e ninguém as apaga."""
    from django.contrib.sessions.models import Session

    tarefa = Tarefa(
        "Sessões vencidas",
        "Cada entrada no sistema guarda uma sessão; depois do prazo ela só ocupa espaço.",
    )
    vencidas = Session.objects.filter(expire_date__lt=timezone.now())
    tarefa.quantidade = vencidas.count()
    if fazer and tarefa.quantidade:
        _apagar(vencidas)
        tarefa.feito = True
    return tarefa


def registro_de_acesso(fazer=False):
    """O histórico de entradas e de senhas erradas mais velho que o prazo.

    O bloqueio por senha errada NÃO sai daqui: ele mora em outra tabela, a que o
    sistema consulta para saber quem está bloqueado agora.
    """
    from axes.models import AccessFailureLog, AccessLog

    tarefa = Tarefa(
        "Registro de acesso antigo",
        f"Quem entrou e quem errou a senha, guardado por {DIAS} dias.",
    )
    limite = timezone.now() - timedelta(days=DIAS)
    consultas = [
        AccessLog.objects.filter(attempt_time__lt=limite),
        AccessFailureLog.objects.filter(attempt_time__lt=limite),
    ]
    tarefa.quantidade = sum(consulta.count() for consulta in consultas)
    if fazer and tarefa.quantidade:
        for consulta in consultas:
            _apagar(consulta)
        tarefa.feito = True
    return tarefa


def envio_de_relatorios(fazer=False):
    """O histórico de e-mail e de Telegram mandados, mais velho que o prazo.

    A tela de Alertas mostra os últimos envios e a agenda só olha o dia e a
    semana corrente, então o que é antigo não faz falta a ninguém.
    """
    from apps.alertas.models import EnvioDeRelatorio

    tarefa = Tarefa(
        "Envios de relatório antigos",
        f"Um registro por e-mail e por mensagem de Telegram mandados, guardado por {DIAS} dias.",
    )
    limite = timezone.now() - timedelta(days=DIAS)
    antigos = EnvioDeRelatorio.objects.filter(quando__lt=limite)
    tarefa.quantidade = antigos.count()
    if fazer and tarefa.quantidade:
        _apagar(antigos)
        tarefa.feito = True
    return tarefa


def sincronizacoes_sem_dados(fazer=False):
    """Sincronizações que não trouxeram nada: sem backup novo ou que falharam.

    Com três por dia, isso virou a linha que mais aparece no histórico. As que
    a tela mostra (as 60 últimas) nunca saem, aconteça o que acontecer.
    """
    from apps.importacao.models import Importacao

    tarefa = Tarefa(
        "Sincronizações sem dados",
        f"Tentativas sem backup novo ou que falharam, guardadas por {DIAS} dias.",
    )
    limite = timezone.now() - timedelta(days=DIAS)
    na_tela = list(Importacao.objects.values_list("id", flat=True)[:60])
    antigas = Importacao.objects.filter(
        situacao__in=(Importacao.Situacao.SEM_NOVIDADE, Importacao.Situacao.FALHOU),
        iniciada_em__lt=limite,
    ).exclude(pk__in=na_tela)
    tarefa.quantidade = antigas.count()
    if fazer and tarefa.quantidade:
        _apagar(antigas)
        tarefa.feito = True
    return tarefa


def anexos_orfaos(fazer=False):
    """Arquivo de anexo no disco cujo registro no banco não existe mais.

    Apagar o anexo na tela tira a linha do banco e deixa o arquivo; é assim que
    o Django funciona. Só sai do disco o arquivo que NENHUM registro aponta.
    """
    from apps.processos.models import Anexo

    tarefa = Tarefa(
        "Anexos órfãos",
        "Arquivo guardado na Base de processos que já não pertence a nenhum processo.",
        unidade="arquivo",
    )
    raiz = getattr(settings, "MEDIA_ROOT", "")
    if not raiz:
        return tarefa
    raiz = Path(raiz)
    if not raiz.is_dir():
        return tarefa
    guardados = {nome for nome in Anexo.objects.values_list("arquivo", flat=True) if nome}
    orfaos = [
        caminho
        for caminho in raiz.rglob("*")
        if caminho.is_file() and caminho.relative_to(raiz).as_posix() not in guardados
    ]
    tarefa.quantidade = len(orfaos)
    tarefa.bytes = sum(caminho.stat().st_size for caminho in orfaos)
    if fazer and orfaos:
        for caminho in orfaos:
            try:
                caminho.unlink()
            except OSError as erro:
                tarefa.aviso = f"Não consegui apagar {caminho.name}: {erro}"
                return tarefa
        tarefa.feito = True
    return tarefa


TAREFAS = (
    copia_do_set,
    fotos_do_set,
    sessoes_vencidas,
    registro_de_acesso,
    envio_de_relatorios,
    sincronizacoes_sem_dados,
    anexos_orfaos,
)


# ------------------------------------------------------------------ o banco em si


def tamanho_do_banco():
    """Quanto o banco do sistema ocupa, em bytes. Zero quando não dá para saber."""
    if connection.vendor != "postgresql":
        return 0
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_database_size(current_database())")
        (tamanho,) = cursor.fetchone()
    return int(tamanho)


def arrumar_o_banco():
    """Avisa o PostgreSQL do que saiu, para o espaço voltar a ser usado.

    Apagar linha no PostgreSQL não devolve espaço na hora: o lugar fica marcado
    como livre e é reaproveitado na gravação seguinte. O VACUUM é o que faz essa
    marcação acontecer agora, e o ANALYZE refaz as contas que o banco usa para
    escolher como buscar. Sem FULL de propósito: FULL trava a tabela inteira, e
    o sistema fica no ar enquanto isso roda.
    """
    if connection.vendor != "postgresql":
        return "Só o PostgreSQL tem VACUUM; aqui não há o que arrumar."
    try:
        with connection.cursor() as cursor:
            cursor.execute("VACUUM (ANALYZE)")
    except Exception as erro:  # noqa: BLE001
        # VACUUM não roda dentro de transação. Se acontecer, a limpeza já
        # funcionou: o espaço só volta a ser usado mais tarde, pelo próprio
        # PostgreSQL. Vira aviso, nunca falha da higienização.
        return f"Não consegui arrumar o banco agora: {erro}"
    return ""


def levantar(fazer=False, arrumar=True):
    """Confere tudo (e limpa, com fazer=True). Devolve o que achou e o que fez."""
    resultado = Resultado(fez=fazer)
    resultado.banco_antes = tamanho_do_banco()
    for tarefa in TAREFAS:
        resultado.tarefas.append(tarefa(fazer=fazer))
    if fazer and arrumar and any(t.feito for t in resultado.tarefas):
        resultado.aviso_do_banco = arrumar_o_banco()
    resultado.banco_depois = tamanho_do_banco() if fazer else resultado.banco_antes
    return resultado
