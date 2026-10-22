"""O extrato do banco, como ele veio, e o que já foi conferido contra as contas.

Pedido do Edson em 13/10/2026: "CRIAR MODULO CONCILIAÇÃO BANCARIA, importar extratos dos
bancos e confrontar com a lista de pagamentos do contas a pagar".

Estes dados são **nossos**, não do SET: ao contrário de quase tudo no sistema, eles não
têm campo `importacao` e não são refeitos a cada sincronização. Um extrato importado em
outubro continua lá em dezembro, com o que foi conferido.

Por que a ligação é pelo `id_set`, e não por chave estrangeira
--------------------------------------------------------------
A conta a pagar (`financeiro.Lancamento`) vive dentro da foto de uma importação: a cada
sincronização as linhas são apagadas e gravadas de novo, com chaves novas. Uma chave
estrangeira para ela se perderia na primeira sincronização, levando junto a conferência
que alguém fez à mão. Então o que fica guardado é o **código do lançamento no SET**
(`id_set`), que é do SET e não muda, mais um rótulo do que foi conferido, para a tela
continuar legível mesmo se aquela conta sumir do SET.
"""

from django.conf import settings
from django.db import models


class ExtratoImportado(models.Model):
    """Um arquivo de extrato que alguém trouxe do banco."""

    class Formato(models.TextChoices):
        OFX = "ofx", "OFX (o que o banco chama de 'arquivo para o gerenciador financeiro')"
        CSV = "csv", "CSV ou texto separado por ponto e vírgula"

    banco = models.CharField(max_length=80, blank=True)
    conta = models.CharField("agência e conta", max_length=60, blank=True)
    arquivo = models.CharField("nome do arquivo", max_length=200)
    formato = models.CharField(max_length=10, choices=Formato.choices)
    periodo_inicio = models.DateField(null=True, blank=True)
    periodo_fim = models.DateField(null=True, blank=True)
    importado_em = models.DateTimeField(auto_now_add=True)
    importado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="extratos_importados",
    )
    # O mesmo arquivo trazido duas vezes dobraria o extrato na tela. A impressão digital
    # é do conteúdo, então renomear o arquivo não engana.
    impressao_digital = models.CharField(max_length=64, unique=True)

    class Meta:
        ordering = ["-periodo_fim", "-importado_em"]
        verbose_name = "extrato importado"
        verbose_name_plural = "extratos importados"
        permissions = [("conciliar_banco", "Pode importar extrato do banco e conferir contas")]

    def __str__(self):
        return f"{self.banco or 'Extrato'} {self.periodo_inicio} a {self.periodo_fim}"


class LinhaExtrato(models.Model):
    """Um lançamento do banco. Valor negativo é dinheiro saindo da conta."""

    class Situacao(models.TextChoices):
        PENDENTE = "pendente", "Ainda não conferida"
        CONFERIDA = "conferida", "Conferida com uma conta"
        SEM_CONTA = "sem_conta", "Marcada como sem conta no SET"

    extrato = models.ForeignKey(ExtratoImportado, on_delete=models.CASCADE, related_name="linhas")
    data = models.DateField()
    valor = models.DecimalField(max_digits=14, decimal_places=2)
    descricao = models.CharField(max_length=300, blank=True)
    documento = models.CharField(max_length=60, blank=True)
    # Identificador do próprio banco (FITID no OFX): é ele que diz que duas linhas iguais
    # em data e valor são dois pagamentos, e não o mesmo lido duas vezes.
    identificador = models.CharField(max_length=120, blank=True)

    situacao = models.CharField(max_length=12, choices=Situacao.choices, default=Situacao.PENDENTE)
    lancamento_id_set = models.IntegerField("código da conta no SET", default=0)
    lancamento_rotulo = models.CharField(max_length=300, blank=True)
    conferida_em = models.DateTimeField(null=True, blank=True)
    conferida_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="linhas_conferidas",
    )
    observacao = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["data", "id"]
        verbose_name = "linha de extrato"
        verbose_name_plural = "linhas de extrato"
        indexes = [models.Index(fields=["extrato", "situacao"])]

    def __str__(self):
        return f"{self.data} {self.valor} {self.descricao[:40]}"

    @property
    def saiu(self):
        """Dinheiro saindo da conta: é o que se confronta com contas a pagar."""
        return self.valor < 0

    @property
    def valor_absoluto(self):
        return -self.valor if self.saiu else self.valor
