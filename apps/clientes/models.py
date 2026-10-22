"""Cadastro de clientes vindo do SET, no mínimo que a loja precisa ver.

A tabela de clientes do SET tem CPF, RG, nome dos pais, renda do cônjuge e mais de cem
colunas. Nada disso é importado: ficam só nome, cidade, estado, data de cadastro e o que
a pessoa comprou, que é o que serve para a loja e é o mínimo que a LGPD pede. Quem quiser
o cadastro completo abre o próprio SET.
"""

from django.db import models

from apps.importacao.models import Importacao


class ClienteImportado(models.Model):
    importacao = models.ForeignKey(Importacao, on_delete=models.CASCADE, related_name="clientes")
    id_set = models.IntegerField("código interno no SET", default=0)
    codigo = models.CharField("código do cliente", max_length=20, blank=True)
    nome = models.CharField(max_length=200, blank=True)
    pessoa_juridica = models.BooleanField(default=False)
    cidade = models.CharField(max_length=80, blank=True)
    uf = models.CharField("estado", max_length=2, blank=True)
    cadastrado_em = models.DateField(null=True, blank=True)
    bloqueado = models.BooleanField(default=False)
    generico = models.BooleanField(
        "cliente genérico do balcão", default=False,
        help_text="CONSUMIDOR FINAL: é onde o caixa lança a venda de quem não se identifica.",
    )

    compras = models.IntegerField("vendas registradas", default=0)
    valor_comprado = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    valor_comprado_12m = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    ultima_compra = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "cliente"
        verbose_name_plural = "clientes"
        permissions = [("ver_clientes", "Pode ver o cadastro de clientes")]
        constraints = [
            models.UniqueConstraint(fields=["importacao", "id_set"], name="cliente_unico_por_importacao"),
        ]
        indexes = [models.Index(fields=["importacao", "-valor_comprado_12m"])]

    def __str__(self):
        return self.nome or self.codigo
