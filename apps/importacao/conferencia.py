"""Conferência do backup antes de ler: é o arquivo mais novo, e está inteiro?

Pedido do Edson em 10/10/2026: antes de importar, conferir o tamanho do arquivo,
para avaliar a integridade, e a data, para ter certeza de que é mesmo o backup
mais recente. A conferência só olha o nome, o tamanho e a data do arquivo no
disco -- não abre o banco, não chama o Firebird e não toca em nada do SET.

Ela roda em dois momentos. Na tela de importações, antes de alguém clicar, para
a gerência olhar e decidir; e dentro da importação, de novo, porque entre olhar
a tela e clicar o arquivo pode ter mudado e o que vale é o que está no disco na
hora da leitura.

O que ela NÃO faz é dizer que o banco lá dentro está bom: isso só a leitura diz.
Ela separa o que dá para saber de fora -- arquivo sem tamanho de backup, arquivo
que encolheu de repente, arquivo mais velho do que o que já foi importado -- do
que precisa abrir o banco para descobrir.

Dois níveis de reprovação, e a diferença importa:

* **quebrado**: o arquivo não tem tamanho de backup do SET. Forçar não passa por
  cima disso, porque trocaria número bom por número pela metade.
* **impedido**: o arquivo é suspeito (encolheu muito). A importação normal para,
  e aí sim o botão de forçar manda ler do mesmo jeito, com o motivo no log.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone as tz
from pathlib import Path

from django.conf import settings
from django.utils import timezone

# .zip porque o backup da Cabana é gerado compactado, com o banco dentro.
EXTENSOES_BACKUP = (".fdb", ".fbk", ".zip")

# Abaixo disto não é backup do SET, é gravação interrompida: o backup da Cabana
# tem dezenas de megabytes, então um megabyte é piso folgado. Em setting para o
# teste poder baixar o piso e usar arquivo de mentira.
MINIMO_BYTES_PADRAO = 1024 * 1024

# Quanto o arquivo pode encolher de um backup para o outro. Backup do SET só
# cresce, porque a loja só acrescenta movimento; encolher é sinal de gravação
# interrompida. Uma folga pequena existe porque o zip comprime cada dia de um
# jeito um pouco diferente.
ENCOLHEU_IMPEDE = 30  # por cento
ENCOLHEU_AVISA = 5

# A partir de quantos dias de idade o arquivo deixa de ser "o backup de hoje".
DIAS_AVISO = 2


def _conf(nome, padrao=None):
    return getattr(settings, nome, padrao)


def tamanho_legivel(bytes_):
    """Tamanho como a gerência lê: bytes quando é pouco, MB quando é backup."""
    if bytes_ is None:
        return "—"
    if bytes_ < 1024:
        return f"{bytes_} bytes"
    if bytes_ < 1024 * 1024:
        return f"{bytes_ / 1024:.0f} KB"
    return f"{bytes_ / 1048576:.1f} MB".replace(".", ",")


def momento_do_arquivo(caminho):
    """Data e hora de gravação do arquivo, com fuso, do jeito que o banco guarda."""
    return datetime.fromtimestamp(Path(caminho).stat().st_mtime, tz=tz.utc)


def candidatos(origem):
    """Todo arquivo com cara de backup na pasta, de qualquer tamanho.

    Inclui o vazio e o pela metade de propósito: é olhando para eles que a
    conferência percebe que o arquivo mais novo da pasta não serve e que vai ser
    lido o de ontem.
    """
    caminho = Path(origem)
    if caminho.is_file():
        return [caminho]
    if not caminho.is_dir():
        return []
    # Nas subpastas também, porque o backup costuma ser guardado em pasta por data.
    return [
        arquivo for arquivo in caminho.rglob("*")
        if arquivo.is_file() and arquivo.suffix.lower() in EXTENSOES_BACKUP
    ]


def localizar_backup(origem=None):
    """Descobre qual arquivo importar: sempre o backup mais recente com conteúdo.

    Aceita o caminho de um arquivo ou de uma pasta. Arquivo vazio é ignorado: é
    backup ainda sendo gravado ou que falhou. Devolve None quando não há nada
    configurado ou nada para ler.
    """
    origem = origem or _conf("IMPORTACAO_BACKUP_ORIGEM")
    if not origem:
        return None
    caminho = Path(origem)
    if caminho.is_file():
        return caminho
    com_conteudo = [a for a in candidatos(origem) if a.stat().st_size > 0]
    if not com_conteudo:
        return None
    return max(com_conteudo, key=lambda a: (a.stat().st_mtime, a.name))


@dataclass
class Motivo:
    """Uma coisa que a conferência achou, já escrita para a tela.

    nível: "quebrado" (nem forçando), "impedido" (só forçando), "atencao" (passa,
    mas fica avisado) ou "nota" (só informação).
    """

    nivel: str
    texto: str


@dataclass
class Conferencia:
    """O que a conferência achou do arquivo que seria importado agora."""

    pasta: str = ""
    caminho: Path | None = None
    bytes: int | None = None
    modificado_em: object = None
    arquivos_na_pasta: int = 0
    anterior: object = None
    mesmo_da_anterior: bool = False
    motivos: list = field(default_factory=list)

    @property
    def achou(self):
        return self.caminho is not None

    @property
    def nome(self):
        return self.caminho.name if self.caminho else ""

    @property
    def tamanho(self):
        return tamanho_legivel(self.bytes)

    @property
    def tamanho_anterior(self):
        """O tamanho do arquivo que a importação anterior leu, que é a régua do tamanho."""
        return tamanho_legivel(getattr(self.anterior, "arquivo_bytes", None))

    @property
    def quebrado(self):
        """Arquivo que não é backup. Nem o botão de forçar passa por cima."""
        return any(m.nivel == "quebrado" for m in self.motivos)

    @property
    def impedido(self):
        """A importação normal para aqui."""
        return any(m.nivel in ("quebrado", "impedido") for m in self.motivos)

    @property
    def nivel(self):
        """Como a tela pinta o quadro: as mesmas cores dos avisos de dados do painel."""
        if self.impedido:
            return "vencido"
        if any(m.nivel == "atencao" for m in self.motivos):
            return "atencao"
        return "ok"

    @property
    def titulo(self):
        if not self.achou:
            return "Nenhum backup para importar"
        if self.quebrado:
            return "O arquivo não tem tamanho de backup"
        if self.impedido:
            return "O backup está diferente do esperado"
        if any(m.nivel == "atencao" for m in self.motivos):
            return "Backup encontrado, com uma ressalva"
        return "Backup conferido e pronto para importar"

    @property
    def impedimentos(self):
        return [m for m in self.motivos if m.nivel in ("quebrado", "impedido")]

    @property
    def avisos(self):
        return [m for m in self.motivos if m.nivel == "atencao"]

    @property
    def notas(self):
        return [m for m in self.motivos if m.nivel == "nota"]

    def pode_importar(self, forcar=False):
        """Se a leitura pode começar. Forçar passa pelo suspeito, não pelo quebrado."""
        if self.quebrado:
            return False
        return forcar or not self.impedido

    def por_que_nao(self, forcar=False):
        """O primeiro motivo que impede, para virar a mensagem da falha."""
        if self.pode_importar(forcar):
            return ""
        for motivo in self.motivos:
            if motivo.nivel == "quebrado" or (not forcar and motivo.nivel == "impedido"):
                return motivo.texto
        return ""

    def linhas_para_log(self):
        """A conferência inteira no log da importação, para depois dar para conferir."""
        if not self.achou:
            return [f"Conferência do backup: {self.titulo}."]
        if self.modificado_em:
            quando = timezone.localtime(self.modificado_em)
            primeira = (f"Conferência do backup: {self.nome}, {self.tamanho}, "
                        f"gravado em {quando:%d/%m/%Y %H:%M}.")
        else:
            primeira = f"Conferência do backup: {self.nome}, {self.tamanho}."
        linhas = [primeira]
        linhas.extend(f"Conferência: {motivo.texto}" for motivo in self.motivos)
        if not self.motivos:
            linhas.append("Conferência: tamanho e data conferidos, nada a estranhar.")
        return linhas


def conferir(origem=None, anterior=None, agora=None):
    """Olha o backup que seria importado agora e devolve o que achou dele.

    `anterior` é a última importação concluída, que é a régua: o tamanho dela diz
    se o arquivo encolheu e a data dela diz se este arquivo é mais novo mesmo.
    """
    agora = agora or timezone.now()
    origem_conf = origem or _conf("IMPORTACAO_BACKUP_ORIGEM")
    resultado = Conferencia(pasta=str(origem_conf or ""), anterior=anterior)

    if not origem_conf:
        resultado.motivos.append(Motivo(
            "quebrado",
            "não sei onde está o backup do SET: a pasta não está configurada "
            "(STUDIO_SET_BACKUP).",
        ))
        return resultado

    todos = candidatos(origem_conf)
    resultado.arquivos_na_pasta = len(todos)
    caminho = localizar_backup(origem_conf)
    if caminho is None:
        vazios = [a for a in todos if a.stat().st_size == 0]
        if vazios:
            resultado.motivos.append(Motivo(
                "quebrado",
                f"o único arquivo da pasta ({vazios[0].name}) está vazio: o backup do SET "
                "começou e não terminou de gravar.",
            ))
        else:
            resultado.motivos.append(Motivo(
                "quebrado",
                f"não achei nenhum arquivo .FDB, .FBK ou .ZIP em {origem_conf}.",
            ))
        return resultado

    resultado.caminho = caminho
    resultado.bytes = caminho.stat().st_size
    resultado.modificado_em = momento_do_arquivo(caminho)

    # 1. Tamanho: o arquivo tem tamanho de backup do SET?
    minimo = _conf("IMPORTACAO_BACKUP_MINIMO_BYTES", MINIMO_BYTES_PADRAO)
    sem_tamanho_de_backup = resultado.bytes < minimo
    if sem_tamanho_de_backup:
        resultado.motivos.append(Motivo(
            "quebrado",
            f"o arquivo tem {resultado.tamanho}, e o backup do SET tem dezenas de MB: "
            "isto é gravação interrompida, não backup.",
        ))

    # 2. A data: este arquivo é mesmo o mais novo da pasta?
    if len(todos) > 1:
        mais_novo = max(todos, key=lambda a: (a.stat().st_mtime, a.name))
        if mais_novo != caminho:
            resultado.motivos.append(Motivo(
                "atencao",
                f"o arquivo mais novo da pasta é {mais_novo.name} "
                f"({tamanho_legivel(mais_novo.stat().st_size)}, de "
                f"{timezone.localtime(momento_do_arquivo(mais_novo)):%d/%m/%Y %H:%M}), "
                f"mas ele está vazio: vai ser lido o {caminho.name}, o mais novo com "
                "conteúdo. O backup do SET pode estar sendo gravado agora.",
            ))
        else:
            resultado.motivos.append(Motivo(
                "nota",
                f"é o mais novo dos {len(todos)} arquivos de backup da pasta.",
            ))

    # 3. A idade: o backup do SET rodou?
    idade = (agora - resultado.modificado_em).days
    if idade >= DIAS_AVISO:
        resultado.motivos.append(Motivo(
            "atencao",
            f"o backup foi gravado {idade} dias atrás "
            f"({timezone.localtime(resultado.modificado_em):%d/%m/%Y %H:%M}). "
            "Confira no servidor se o backup do SET continua rodando: não existe backup "
            "mais novo que este para importar.",
        ))

    # 4. A régua da importação anterior: encolheu? é mais antigo? é o mesmo?
    if anterior is not None and anterior.arquivo_bytes:
        if anterior.arquivo == str(caminho)[:500] and \
                anterior.arquivo_modificado_em == resultado.modificado_em and \
                anterior.arquivo_bytes == resultado.bytes:
            resultado.mesmo_da_anterior = True
            resultado.motivos.append(Motivo(
                "nota",
                "é o mesmo arquivo da importação anterior, com a mesma data e o mesmo "
                "tamanho: sem forçar, a importação termina como Sem backup novo.",
            ))
        elif not sem_tamanho_de_backup:
            # Arquivo que já foi reprovado pelo tamanho não precisa ouvir de novo que
            # encolheu: é o mesmo assunto, e dois motivos para a mesma coisa confundem.
            diferenca = resultado.bytes - anterior.arquivo_bytes
            if diferenca < 0:
                encolheu = abs(diferenca) * 100 / anterior.arquivo_bytes
                texto = (
                    f"o arquivo encolheu {encolheu:.0f}% desde a importação anterior "
                    f"({tamanho_legivel(anterior.arquivo_bytes)} para {resultado.tamanho}). "
                    "Backup do SET só cresce, porque a loja só acrescenta movimento"
                )
                if encolheu >= ENCOLHEU_IMPEDE:
                    resultado.motivos.append(Motivo(
                        "impedido",
                        texto + ": provavelmente a gravação parou no meio.",
                    ))
                elif encolheu >= ENCOLHEU_AVISA:
                    resultado.motivos.append(Motivo("atencao", texto + "."))
        if anterior.arquivo_modificado_em and \
                resultado.modificado_em < anterior.arquivo_modificado_em and \
                not resultado.mesmo_da_anterior:
            resultado.motivos.append(Motivo(
                "atencao",
                "este arquivo é mais antigo que o que já foi importado "
                f"({timezone.localtime(anterior.arquivo_modificado_em):%d/%m/%Y %H:%M}): "
                "importar agora troca os números por dados mais velhos.",
            ))
    return resultado
