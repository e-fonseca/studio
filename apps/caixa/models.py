"""O caixa da loja como o SET registra: quem abriu, quando fechou e com quanto.

Pedido do Edson em 08/10/2026: "menu caixa = caixas aberto e fechados, valores, hora
abertura, hora fechamento, dia, operador".

O SET guarda isso em duas tabelas. CAIXA é o turno inteiro (abertura, fechamento,
saldo inicial, saldo final, quem abriu, quem fechou) e ICAIXA é cada movimento
dentro dele. São 969 turnos e 49.597 movimentos na cópia de 20/09/2026.

Dos movimentos, 43.945 são recebimento de venda — que o sistema já guarda em
VendaImportada — e por isso entram aqui só somados. O que entra linha a linha são os
3.975 movimentos que NÃO são venda: sangria, pagamento feito pelo caixa e entrada de
dinheiro. É justamente o que alguém abre o caixa para conferir, e é pouco.
"""

from decimal import Decimal

from django.db import models

from apps.importacao.models import Importacao

ZERO = Decimal("0")


class CaixaImportado(models.Model):
    """Um turno de caixa do SET, com os movimentos dele já somados."""

    class Situacao(models.TextChoices):
        ABERTO = "aberto", "Aberto"
        FECHADO = "fechado", "Fechado"

    importacao = models.ForeignKey(Importacao, on_delete=models.CASCADE, related_name="caixas")
    id_set = models.IntegerField("número do caixa no SET", default=0)
    operador = models.CharField("quem abriu", max_length=200, blank=True)
    operador_fechamento = models.CharField("quem fechou", max_length=200, blank=True)

    # O dia é o da abertura. Caixa que vira a noite (e há vários) continua sendo do dia
    # em que abriu, que é como a loja fala dele.
    dia = models.DateField("dia da abertura")
    aberto_em = models.DateTimeField("abertura")
    fechado_em = models.DateTimeField("fechamento", null=True, blank=True)

    saldo_inicial = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    saldo_final = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    situacao = models.CharField(max_length=10, choices=Situacao.choices, default=Situacao.FECHADO)
    tipo = models.CharField("tipo de caixa no SET", max_length=50, blank=True)
    observacao = models.CharField(max_length=255, blank=True)

    # Somas dos movimentos do turno, feitas na importação para a tela não ter que
    # percorrer cinquenta mil linhas a cada filtro.
    recebido = models.DecimalField("recebimentos do turno", max_digits=14, decimal_places=2, default=0)
    entradas = models.DecimalField("entradas de dinheiro", max_digits=14, decimal_places=2, default=0)
    sangrias = models.DecimalField("retiradas do caixa", max_digits=14, decimal_places=2, default=0)
    pagamentos = models.DecimalField("pagamentos feitos pelo caixa", max_digits=14, decimal_places=2, default=0)
    estornado = models.DecimalField("movimentos estornados", max_digits=14, decimal_places=2, default=0)
    movimentos = models.IntegerField("quantos movimentos o turno teve", default=0)
    # {"PIX": "1881.00", "CARTAO DEBITO": "2055.50", ...}: quanto entrou por forma de
    # pagamento. Fica em JSON porque a lista de formas é do SET e muda sem avisar.
    por_forma = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-aberto_em", "-id_set"]
        verbose_name = "caixa"
        verbose_name_plural = "caixas"
        permissions = [("ver_caixa", "Pode ver os caixas abertos e fechados da loja")]
        constraints = [
            models.UniqueConstraint(fields=["importacao", "id_set"], name="caixa_unico_por_importacao"),
        ]
        indexes = [models.Index(fields=["importacao", "-aberto_em"])]

    def __str__(self):
        return f"Caixa {self.id_set} de {self.dia:%d/%m/%Y}"

    @property
    def esta_aberto(self):
        return self.situacao == self.Situacao.ABERTO

    @property
    def saldo_calculado(self):
        """O que o saldo final deveria ser, pelos movimentos do próprio turno."""
        return (self.saldo_inicial + self.recebido + self.entradas
                - self.sangrias - self.pagamentos)

    @property
    def diferenca(self):
        """Quanto o saldo final do SET se afasta da soma dos movimentos. None se aberto."""
        if self.saldo_final is None:
            return None
        return self.saldo_final - self.saldo_calculado

    @property
    def confere(self):
        """Diferença de até um centavo é arredondamento, não erro."""
        diferenca = self.diferenca
        return diferenca is not None and abs(diferenca) <= Decimal("0.01")

    @property
    def minutos_aberto(self):
        if self.fechado_em is None:
            return None
        return int((self.fechado_em - self.aberto_em).total_seconds() // 60)

    @property
    def tempo_aberto(self):
        """"7h20" para a tela, em vez de 440 minutos."""
        minutos = self.minutos_aberto
        if minutos is None:
            return ""
        return f"{minutos // 60}h{minutos % 60:02d}"


class MovimentoCaixa(models.Model):
    """Um movimento do turno que não é recebimento de venda.

    Sangria é dinheiro tirado do caixa (troco de outra loja, almoço, adiantamento);
    pagamento é conta paga direto pelo caixa; entrada é dinheiro colocado dentro dele.
    São esses três que alguém confere quando o caixa não fecha, e por isso são os que
    vêm linha a linha.
    """

    class Tipo(models.TextChoices):
        ENTRADA = "entrada", "Entrada de dinheiro"
        SANGRIA = "sangria", "Sangria"
        PAGAMENTO = "pagamento", "Pagamento"

    caixa = models.ForeignKey(CaixaImportado, on_delete=models.CASCADE, related_name="lancamentos")
    id_set = models.IntegerField("código do movimento no SET", default=0)
    quando = models.DateTimeField()
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    descricao = models.CharField(max_length=150, blank=True)
    grupo = models.CharField("classificação no plano de contas do SET", max_length=100, blank=True)
    valor = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    operador = models.CharField(max_length=50, blank=True)
    forma_pagamento = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ["quando", "id"]
        verbose_name = "movimento de caixa"
        verbose_name_plural = "movimentos de caixa"
        indexes = [models.Index(fields=["caixa", "quando"])]

    def __str__(self):
        return f"{self.get_tipo_display()} de {self.valor}"
