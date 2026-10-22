"""Contas a pagar e a receber, como o SET as guarda, mais o que a loja prevê pagar.

O SET já tem o financeiro lançado e classificado no plano de contas dele: a importação
copia isso e não inventa categoria nenhuma. O único dado que nasce aqui é o pagamento
previsto, para a projeção de caixa poder contar com o que ainda não foi lançado no SET.
Nada volta para o SET: este sistema é só leitura (docs/leitura-firebird.md).
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.importacao.models import Importacao


class Lancamento(models.Model):
    """Uma parcela de conta a pagar ou a receber, na foto de uma importação."""

    class Tipo(models.TextChoices):
        PAGAR = "pagar", "A pagar"
        RECEBER = "receber", "A receber"

    importacao = models.ForeignKey(Importacao, on_delete=models.CASCADE, related_name="lancamentos")
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    id_set = models.IntegerField("código no SET", default=0)

    descricao = models.CharField(max_length=200, blank=True)
    documento = models.CharField("número do documento", max_length=60, blank=True)
    parcela = models.CharField(max_length=20, blank=True)
    situacao_set = models.CharField("situação no SET", max_length=40, blank=True)
    grupo = models.CharField("classificação no plano de contas do SET", max_length=120, blank=True)
    tipo_plano = models.CharField("tipo no plano de contas", max_length=40, blank=True)
    contraparte = models.CharField("fornecedor ou cliente", max_length=200, blank=True)
    forma_pagamento = models.CharField(max_length=40, blank=True)

    cadastrado_em = models.DateField(null=True, blank=True)
    vencimento = models.DateField(null=True, blank=True)
    pagamento = models.DateField("data do pagamento ou recebimento", null=True, blank=True)
    valor = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    valor_pago = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    origem_set = models.IntegerField("compra ou venda que gerou", default=0)

    class Meta:
        ordering = ["vencimento", "id"]
        verbose_name = "lançamento financeiro"
        verbose_name_plural = "lançamentos financeiros"
        permissions = [("ver_financeiro", "Pode ver contas a pagar, a receber e o caixa")]
        indexes = [
            models.Index(fields=["importacao", "tipo", "vencimento"]),
            models.Index(fields=["importacao", "tipo", "pagamento"]),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()}: {self.descricao or self.documento}"

    @property
    def em_aberto(self):
        return self.pagamento is None

    def dias_de_atraso(self, hoje=None):
        """Dias vencidos hoje. Zero quando ainda não venceu ou já foi pago."""
        if self.pagamento or not self.vencimento:
            return 0
        return max(0, ((hoje or timezone.localdate()) - self.vencimento).days)


class PagamentoPrevisto(models.Model):
    """Pagamento que a loja sabe que vem e ainda não está lançado no SET.

    Serve só para a projeção de caixa não ficar otimista. Fica marcado como previsto na
    tela, separado do que veio do SET, e sai da projeção quando a pessoa marca como
    lançado.
    """

    descricao = models.CharField(max_length=200)
    fornecedor = models.CharField(max_length=200, blank=True)
    valor = models.DecimalField(max_digits=14, decimal_places=2)
    vencimento = models.DateField("quando vence")
    observacao = models.TextField(blank=True)
    lancado_no_set = models.BooleanField("já lançado no SET", default=False)

    criado_em = models.DateTimeField(default=timezone.now)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="pagamentos_previstos",
    )

    class Meta:
        ordering = ["vencimento", "id"]
        verbose_name = "pagamento previsto"
        verbose_name_plural = "pagamentos previstos"
        permissions = [("lancar_pagamento", "Pode registrar pagamento previsto a fornecedor")]

    def __str__(self):
        return f"{self.descricao} em {self.vencimento:%d/%m/%Y}"
