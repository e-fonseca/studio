"""Contagem física do estoque.

A loja nunca fez contagem: na cópia de 20/09/2026 havia 1.456 produtos com saldo negativo
no SET, o que só acontece quando se vende o que o sistema acha que não existe. Enquanto não
houver contagem, todo número de saldo é estimativa.

O SET tem a tela de conferência de estoque e ela nunca foi usada (as tabelas estão
vazias), e de todo jeito este sistema não escreve no SET. Então a contagem acontece aqui:
a pessoa passa o leitor pela prateleira, o sistema compara com o saldo do SET e no fim
entrega a lista do que está diferente. O ajuste em si é digitado no SET por quem é da
loja, uma linha de cada vez, porque é lá que o estoque vale.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class Contagem(models.Model):
    """Uma rodada de contagem: um setor, um dia, as pessoas que contaram."""

    class Situacao(models.TextChoices):
        ABERTA = "aberta", "Em contagem"
        FECHADA = "fechada", "Fechada"

    nome = models.CharField(
        "o que está sendo contado", max_length=120,
        help_text="Por exemplo: prateleira dos tapetes, depósito, loja inteira.",
    )
    situacao = models.CharField(max_length=10, choices=Situacao.choices, default=Situacao.ABERTA)
    observacao = models.TextField(blank=True)

    aberta_em = models.DateTimeField(default=timezone.now)
    aberta_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="contagens_abertas",
    )
    fechada_em = models.DateTimeField(null=True, blank=True)
    fechada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="contagens_fechadas",
    )
    # Qual foto do SET serviu de comparação. Guardada para a divergência continuar
    # fazendo sentido depois, mesmo com importações novas por cima.
    importacao = models.ForeignKey(
        "importacao.Importacao", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="contagens",
    )

    class Meta:
        ordering = ["-aberta_em", "-id"]
        verbose_name = "contagem de estoque"
        verbose_name_plural = "contagens de estoque"
        permissions = [
            ("contar_estoque", "Pode contar o estoque e registrar a contagem"),
            ("fechar_contagem", "Pode fechar a contagem e ver a lista de ajustes"),
        ]

    def __str__(self):
        return f"{self.nome} ({self.get_situacao_display()})"

    @property
    def aberta(self):
        return self.situacao == self.Situacao.ABERTA


def caminho_da_foto(instancia, nome):
    """Nome no disco escolhido pelo sistema: nada do que o navegador manda vira caminho."""
    return f"inventario/{instancia.contagem_id}/{instancia.codigo_do_arquivo()}.jpg"


class ItemContado(models.Model):
    """Um produto contado dentro de uma contagem, com o saldo do SET ao lado.

    A quantidade é acumulada: passar o leitor duas vezes no mesmo produto soma, que é
    como a contagem acontece de verdade quando o produto está em dois lugares.
    """

    contagem = models.ForeignKey(Contagem, on_delete=models.CASCADE, related_name="itens")
    codigo = models.CharField("código do produto", max_length=60)
    descricao = models.CharField(max_length=200, blank=True)
    codigo_barras = models.CharField(max_length=40, blank=True)

    quantidade = models.DecimalField("contado na prateleira", max_digits=14, decimal_places=3, default=0)
    saldo_set = models.DecimalField("saldo no SET", max_digits=14, decimal_places=3, default=0)
    custo = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)

    # Como o produto foi ENCONTRADO na prateleira, que é outra pergunta além de quantos
    # são. Numa loja de artesanato a peça chega torta, descasca, perde a etiqueta e
    # volta da vitrine arranhada: contar sem registrar isso dá um número certo sobre
    # uma prateleira que ninguém pode vender. "Danificado" é o que a pessoa da
    # prateleira marca quando vê o defeito; quem decide entre consertar e descartar é
    # a gerência, depois, na tela Organizar — e é essa a classificação que ele pediu.
    class Estado(models.TextChoices):
        OK = "ok", "Perfeito"
        SEM_ETIQUETA = "sem_etiqueta", "Sem etiqueta"
        DANIFICADO = "danificado", "Danificado, a classificar"
        CONSERTO = "conserto", "Para conserto"
        DESCARTE = "descarte", "Para descarte"

    estado = models.CharField(
        "como o produto foi encontrado", max_length=14,
        choices=Estado.choices, default=Estado.OK, db_index=True,
    )
    estado_em = models.DateTimeField("quando o estado foi marcado", null=True, blank=True)
    estado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="+", verbose_name="quem marcou o estado",
    )
    # Quando a providência foi tomada: etiqueta refeita, peça consertada e de volta à
    # prateleira, peça descartada e a baixa digitada no SET. Sem isto a tela Organizar
    # viraria um histórico que só cresce, e no segundo mês ninguém mais acharia o que
    # ainda está esperando — que é a única coisa que ela precisa mostrar.
    resolvido_em = models.DateTimeField("quando foi resolvido", null=True, blank=True)
    resolvido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="+", verbose_name="quem resolveu",
    )

    contado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+",
    )
    contado_em = models.DateTimeField(default=timezone.now)
    observacao = models.CharField(max_length=200, blank=True)
    # Foto tirada na hora, pela câmera do celular, para o caso de a prateleira mostrar
    # algo que o número não explica: caixa avariada, produto trocado de lugar, etiqueta
    # ilegível. Fica guardada fora da pasta pública e só sai por view com permissão.
    foto = models.FileField("foto da prateleira", upload_to=caminho_da_foto,
                            max_length=200, blank=True)
    foto_em = models.DateTimeField("quando a foto foi tirada", null=True, blank=True)

    class Meta:
        ordering = ["descricao", "codigo"]
        verbose_name = "item contado"
        verbose_name_plural = "itens contados"
        constraints = [
            models.UniqueConstraint(fields=["contagem", "codigo"], name="item_unico_por_contagem"),
        ]

    def __str__(self):
        return f"{self.codigo} {self.descricao}".strip()

    def codigo_do_arquivo(self):
        """Nome de arquivo seguro, feito do código do produto e do momento da contagem."""
        limpo = "".join(c for c in (self.codigo or "") if c.isalnum())[:40] or "item"
        return f"{limpo}-{int(self.contado_em.timestamp())}"

    @property
    def diferenca(self):
        """Contado menos o que o SET diz. Positivo é sobra, negativo é falta."""
        return (self.quantidade or Decimal("0")) - (self.saldo_set or Decimal("0"))

    @property
    def bate(self):
        return self.diferenca == 0

    @property
    def valor_da_diferenca(self):
        """Quanto a diferença vale ao custo, que é o que importa para o caixa."""
        if self.custo is None:
            return None
        return (self.diferenca * self.custo).quantize(Decimal("0.01"))

    @property
    def perfeito(self):
        return self.estado == self.Estado.OK

    @property
    def a_classificar(self):
        """Danificado sem destino escolhido: é o que a tela Organizar vai cobrar."""
        return self.estado == self.Estado.DANIFICADO and not self.resolvido_em

    @property
    def resolvido(self):
        return self.resolvido_em is not None

    @property
    def esperando_providencia(self):
        """Marcado como algo além de perfeito e ainda sem providência tomada."""
        return self.estado != self.Estado.OK and not self.resolvido_em

    @property
    def valor_no_custo(self):
        """O que as unidades contadas valem ao custo.

        É esta a conta do descarte e do conserto, não a da diferença: o que se perde ao
        jogar a peça fora é a peça inteira, não o quanto ela divergia do SET.
        """
        if self.custo is None:
            return None
        return ((self.quantidade or Decimal("0")) * self.custo).quantize(Decimal("0.01"))
