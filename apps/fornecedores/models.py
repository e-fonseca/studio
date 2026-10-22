"""Fornecedores e o prazo de entrega de cada um.

O SET grava na compra a data da nota, não a data em que o pedido foi feito: em
195 das 328 compras do histórico a entrega sai no mesmo dia do pedido. Com isso
o prazo medido dá zero e o sistema sugere comprar tarde demais. O prazo que a
gerência informa aqui vale mais que o medido e corrige a sugestão de reposição.
"""

from django.conf import settings
from django.core.validators import MaxValueValidator
from django.db import models

PRAZO_MAXIMO = 365
REPUTACAO_MAXIMA = 5


class Fornecedor(models.Model):
    class Relacao(models.TextChoices):
        """Como a loja trabalha com este fornecedor. Quem define é a gerência.

        O SET não guarda nada parecido: é julgamento de quem negocia, e muda a decisão
        de compra tanto quanto o preço (um parceiro aceita prazo, um eventual não).
        """

        SEM_CLASSIFICACAO = "", "Ainda não classificado"
        PARCEIRO = "parceiro", "Parceiro"
        FLEXIVEL = "flexivel", "Flexível"
        EVENTUAL = "eventual", "Eventual"

    class Documento(models.TextChoices):
        """Que papel o fornecedor emite na venda para a loja.

        Muda o que a loja consegue creditar e o que o contador aceita, então entra na
        decisão de comprar tanto quanto o preço. O SET não guarda isso em lugar nenhum:
        quem sabe é quem recebe a mercadoria.
        """

        SEM_INFORMACAO = "", "Ainda não informado"
        NOTA_COMPLETA = "nota_completa", "Nota fiscal completa"
        NOTA_PARCIAL = "nota_parcial", "Nota fiscal parcial"
        ROMANEIO = "romaneio", "Só recibo ou romaneio"

    nome = models.CharField("fornecedor", max_length=200, unique=True)
    documento_fiscal = models.CharField(
        "documento que emite", max_length=20, choices=Documento.choices, blank=True, default="",
        help_text="Nota completa, nota parcial ou só recibo e romaneio. Informado pela gerência.",
    )
    reputacao = models.PositiveSmallIntegerField(
        "reputação, de 1 a 5 estrelas", null=True, blank=True,
        validators=[MaxValueValidator(REPUTACAO_MAXIMA)],
        help_text="Entrega no prazo, qualidade e negociação. Vazio quando ainda não foi avaliado.",
    )
    relacao = models.CharField(
        "relação com a loja", max_length=20, choices=Relacao.choices, blank=True, default="",
    )
    prazo_dias = models.PositiveSmallIntegerField(
        "prazo de entrega, em dias",
        null=True,
        blank=True,
        validators=[MaxValueValidator(PRAZO_MAXIMO)],
        help_text="Dias entre fazer o pedido e a mercadoria chegar na loja.",
    )
    observacao = models.CharField("observação", max_length=300, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="fornecedores_atualizados",
    )

    class Meta:
        verbose_name = "fornecedor"
        verbose_name_plural = "fornecedores"
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    @property
    def estrelas(self):
        """Lista de 5 posições, cheia ou vazia, para a tela desenhar as estrelinhas."""
        nota = self.reputacao or 0
        return [posicao <= nota for posicao in range(1, REPUTACAO_MAXIMA + 1)]


class FornecedorImportado(models.Model):
    """Ficha cadastral do fornecedor, como está no SET, na foto de cada importação.

    Diferente do cliente, aqui o CNPJ e a inscrição estadual entram: é com eles que se
    confere a nota fiscal da compra, que é justamente o que o campo "documento que emite"
    do cadastro acima serve para antecipar. Dado de pessoa física (RG, data de nascimento,
    nome dos pais) não é importado, pelo mesmo motivo do cadastro de clientes.
    """

    importacao = models.ForeignKey(
        "importacao.Importacao", on_delete=models.CASCADE, related_name="fornecedores"
    )
    id_set = models.IntegerField("código interno no SET", default=0)
    codigo = models.CharField("código do fornecedor", max_length=20, blank=True)
    razao = models.CharField("razão social", max_length=200, blank=True)
    fantasia = models.CharField("nome fantasia", max_length=200, blank=True)
    pessoa_juridica = models.BooleanField(default=True)
    cnpj_cpf = models.CharField("CNPJ ou CPF", max_length=25, blank=True)
    inscricao_estadual = models.CharField("inscrição estadual", max_length=30, blank=True)

    telefone = models.CharField(max_length=60, blank=True)
    telefone_2 = models.CharField("outro telefone", max_length=60, blank=True)
    email = models.CharField("e-mail", max_length=150, blank=True)
    site = models.CharField(max_length=150, blank=True)
    contato = models.CharField("pessoa de contato", max_length=120, blank=True)
    contato_telefone = models.CharField("telefone do contato", max_length=60, blank=True)

    endereco = models.CharField("endereço", max_length=200, blank=True)
    numero = models.CharField("número", max_length=20, blank=True)
    bairro = models.CharField(max_length=100, blank=True)
    cidade = models.CharField(max_length=80, blank=True)
    uf = models.CharField("estado", max_length=2, blank=True)
    cep = models.CharField(max_length=15, blank=True)

    situacao = models.CharField("situação no SET", max_length=30, blank=True)
    observacoes = models.TextField("observações do SET", blank=True)

    class Meta:
        ordering = ["razao"]
        verbose_name = "ficha de fornecedor"
        verbose_name_plural = "fichas de fornecedor"
        constraints = [
            models.UniqueConstraint(fields=["importacao", "id_set"], name="fornecedor_unico_por_importacao"),
        ]
        indexes = [models.Index(fields=["importacao", "razao"])]

    def __str__(self):
        return self.razao or self.codigo

    @property
    def endereco_completo(self):
        """Uma linha só, pulando o que o SET não tem preenchido."""
        rua = ", ".join(parte for parte in (self.endereco, self.numero) if parte)
        municipio = "/".join(parte for parte in (self.cidade, self.uf) if parte)
        return " · ".join(parte for parte in (rua, self.bairro, municipio, self.cep) if parte)

    @property
    def documento_rotulo(self):
        return "CNPJ" if self.pessoa_juridica else "CPF"
