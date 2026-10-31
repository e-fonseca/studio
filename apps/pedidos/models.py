"""O pedido que a loja mandou ao fornecedor, guardado, e o que voltou dele.

Pedido do Edson em 14/10/2026: *"nos novos pedidos permitir anexar arquivo dos
pedidos e/ou romaneios e nota fiscal para os fornecedores ou artesãos que consegue
fazer emissão, para controle futuros e fazer com o sistema faça a leitura de todo o
conteúdo do arquivo também para checar se as informações estão corretas"*.

Até a 1.30.0 o pedido era só uma folha: a tela montava o PDF na hora, a partir da
lista de compra, e não sobrava registro de nada. Para anexar o romaneio que chegou
com a mercadoria o pedido precisa EXISTIR depois de impresso — e para conferir a
nota contra o que foi pedido, precisa existir **o que foi pedido**, item a item,
congelado no dia. Lista de compra de hoje não serve de prova: ela muda a cada
sincronização.

Por isso o pedido é dado NOSSO, como a ficha do fornecedor e o inventário: não tem
campo `importacao`, a sincronização não o refaz e nada volta para o SET. Guarda o
nome do fornecedor (a ligação é pelo nome, como no resto do sistema) e o código do
produto, nunca chave estrangeira para a foto do SET, que é apagada e refeita três
vezes ao dia.
"""

import hashlib
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

ZERO = Decimal("0")


class Pedido(models.Model):
    """Um pedido mandado a um fornecedor, com o que foi pedido congelado dentro."""

    class Situacao(models.TextChoices):
        # Pedido montado por quem não aprova (a Líder de loja, 1.42.0). A descrição do
        # cargo que o Edson mandou em 31/10/2026 diz: "Nenhuma compra é confirmada sem
        # aprovação prévia" da Direção. Enquanto espera, a folha sai com o aviso de que
        # não vale, e a mercadoria não pode ser dada como recebida.
        AGUARDANDO = "aguardando", "Esperando aprovação"
        ABERTO = "aberto", "Pedido feito, esperando a mercadoria"
        RECEBIDO = "recebido", "Mercadoria recebida"
        CANCELADO = "cancelado", "Cancelado"

    # Número da loja, não do fornecedor: serve para falar do pedido ao telefone.
    numero = models.PositiveIntegerField("número do pedido", unique=True)
    fornecedor = models.CharField("fornecedor", max_length=200)
    situacao = models.CharField(max_length=20, choices=Situacao.choices, default=Situacao.ABERTO)

    # De que foto do SET saíram as quantidades. Não é chave: a foto é refeita.
    data_corte = models.DateField("dados conferidos em", null=True, blank=True)
    prazo_dias = models.PositiveSmallIntegerField("prazo combinado, em dias", null=True, blank=True)
    observacao = models.CharField("observação", max_length=300, blank=True)

    criado_em = models.DateTimeField(default=timezone.now)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="pedidos_feitos",
    )
    recebido_em = models.DateTimeField(null=True, blank=True)
    recebido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="pedidos_recebidos",
    )

    # Pedido do Edson em 20/10/2026: *"permitir editar pedido ou descartar/cancelar
    # (informar motivo)"*. O motivo é obrigatório na tela, e não no banco, porque
    # `blank=True` é o que permite o pedido que nasce sem cancelamento nenhum.
    motivo_cancelamento = models.CharField("motivo do cancelamento", max_length=300, blank=True)
    cancelado_em = models.DateTimeField(null=True, blank=True)
    cancelado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="pedidos_cancelados",
    )
    # Editar é mexer no que foi mandado ao fornecedor, então a tela tem que dizer que
    # mexeram: quem confere a nota contra o pedido precisa saber que o pedido mudou.
    editado_em = models.DateTimeField(null=True, blank=True)
    editado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="pedidos_editados",
    )
    # Quem fez o pedido valer. No pedido da gerência é quem fez, no mesmo instante; no da
    # Líder de loja é quem aprovou depois. Em branco nos pedidos de antes da 1.42.0.
    aprovado_em = models.DateTimeField(null=True, blank=True)
    aprovado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="pedidos_aprovados",
    )

    class Meta:
        ordering = ["-numero"]
        verbose_name = "pedido ao fornecedor"
        verbose_name_plural = "pedidos ao fornecedor"
        indexes = [
            models.Index(fields=["fornecedor", "-numero"]),
            models.Index(fields=["situacao", "-numero"]),
        ]
        permissions = [
            ("registrar_pedido", "Registrar pedido ao fornecedor"),
            ("anexar_documento", "Anexar romaneio e nota fiscal ao pedido"),
            ("aprovar_pedido", "Aprovar o pedido montado na loja"),
        ]

    def __str__(self):
        return f"Pedido {self.numero} · {self.fornecedor}"

    @classmethod
    def proximo_numero(cls):
        """O número seguinte. Começa em 1 e não reaproveita número de pedido apagado."""
        ultimo = cls.objects.aggregate(maior=models.Max("numero"))["maior"]
        return (ultimo or 0) + 1

    @property
    def quantas_linhas(self):
        return self.itens.count()

    @property
    def valor_total(self):
        total = self.itens.aggregate(soma=models.Sum("valor"))["soma"]
        return total or ZERO

    @property
    def esta_aberto(self):
        return self.situacao == self.Situacao.ABERTO

    @property
    def foi_cancelado(self):
        return self.situacao == self.Situacao.CANCELADO

    @property
    def esperando_aprovacao(self):
        return self.situacao == self.Situacao.AGUARDANDO

    @property
    def pode_mudar(self):
        """Só pedido aberto (ou esperando aprovação) se edita ou cancela.

        Depois de recebido, mexer na quantidade apagaria justamente a prova contra a
        qual a nota fiscal é conferida; cancelado já é o fim da linha.
        """
        return self.esta_aberto or self.esperando_aprovacao

    def pode_ser_mudado_por(self, usuario):
        """Se ESTA pessoa pode editar ou cancelar o pedido agora.

        Quem não aprova mexe no pedido só enquanto ele espera a aprovação: depois de
        aprovado, mudar a quantidade seria comprar o que ninguém aprovou.
        """
        if not self.pode_mudar or usuario is None or not usuario.has_perm("pedidos.registrar_pedido"):
            return False
        return self.esperando_aprovacao or usuario.has_perm("pedidos.aprovar_pedido")

    @property
    def foi_editado(self):
        return self.editado_em is not None

    @property
    def unidades(self):
        total = self.itens.aggregate(soma=models.Sum("quantidade"))["soma"]
        return total or ZERO

    @property
    def aberto(self):
        return self.situacao == self.Situacao.ABERTO

    @property
    def quem_fez(self):
        if self.criado_por is None:
            return "usuário removido"
        return self.criado_por.get_full_name() or self.criado_por.get_username()

    @property
    def quem_aprovou(self):
        if self.aprovado_por is None:
            return ""
        return self.aprovado_por.get_full_name() or self.aprovado_por.get_username()

    @property
    def aprovado_por_outra_pessoa(self):
        """O pedido foi aprovado depois, por alguém que não é quem o fez."""
        return self.aprovado_por_id is not None and self.aprovado_por_id != self.criado_por_id


class ItemDoPedido(models.Model):
    """Uma linha do pedido, como ela estava no dia em que o pedido foi feito.

    `custo` é o da última compra registrada no SET naquele dia: é referência de
    conferência, não preço acertado. Quando a nota vem com outro, a diferença é o
    que a tela mostra — e é justamente o que ninguém conferia antes.
    """

    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="itens")
    codigo = models.CharField("código no SET", max_length=60)
    codigo_barras = models.CharField("código de barras", max_length=60, blank=True)
    descricao = models.CharField("produto", max_length=200)
    grupo = models.CharField("grupo", max_length=120, blank=True)
    quantidade = models.DecimalField(max_digits=14, decimal_places=3)
    custo = models.DecimalField("custo unitário de referência", max_digits=14, decimal_places=4,
                                null=True, blank=True)
    valor = models.DecimalField("total da linha", max_digits=14, decimal_places=2, default=ZERO)
    escolhida_a_mao = models.BooleanField("quantidade definida pela loja", default=False)

    class Meta:
        ordering = ["descricao", "codigo"]
        verbose_name = "item do pedido"
        verbose_name_plural = "itens do pedido"
        constraints = [
            models.UniqueConstraint(fields=["pedido", "codigo"], name="item_uma_vez_por_pedido"),
        ]

    def __str__(self):
        return f"{self.codigo} · {self.descricao}"


def caminho_do_anexo(instancia, nome):
    # O nome no disco é o resumo do conteúdo, nunca o nome enviado: nome de arquivo
    # que veio de fora pode trazer caminho dentro ("..\\..\\") e colidir com outro.
    return f"pedidos/{instancia.pedido_id}/{instancia.sha256[:2]}/{instancia.sha256}"


class AnexoDoPedido(models.Model):
    """Um documento do pedido: a folha que foi mandada, o romaneio ou a nota fiscal.

    O que o sistema LÊ depende do que o arquivo é, e isso é honestidade, não limite
    técnico: o XML da nota fiscal é o documento, com item, quantidade e preço em
    campo próprio, então dá para conferir linha por linha; o PDF do DANFE é o
    retrato dele, e o romaneio do artesão é uma foto de papel. Esses dois ficam
    guardados e à vista, que é o "controle futuro" pedido, e a conferência deles é
    de quem recebe a mercadoria.
    """

    class Tipo(models.TextChoices):
        PEDIDO = "pedido", "Pedido que a loja mandou"
        ROMANEIO = "romaneio", "Romaneio de entrega"
        NOTA_FISCAL = "nota_fiscal", "Nota fiscal"
        OUTRO = "outro", "Outro documento"

    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="anexos")
    tipo = models.CharField(max_length=20, choices=Tipo.choices, default=Tipo.NOTA_FISCAL)
    arquivo = models.FileField(upload_to=caminho_do_anexo, max_length=200)
    nome_original = models.CharField(max_length=200)
    extensao = models.CharField(max_length=10)
    tamanho = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    observacao = models.CharField("observação", max_length=200, blank=True)

    # O que o sistema conseguiu ler dentro do arquivo. Vazio quando o formato não se
    # lê; `erro_de_leitura` conta por que, para a tela não ficar calada.
    documento = models.CharField("tipo de documento lido", max_length=20, blank=True)
    numero_do_documento = models.CharField("número", max_length=40, blank=True)
    emitente = models.CharField("quem emitiu", max_length=200, blank=True)
    emitente_documento = models.CharField("CNPJ ou CPF de quem emitiu", max_length=24, blank=True)
    emitido_em = models.DateField("data de emissão", null=True, blank=True)
    valor_do_documento = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    # Lista de {codigo, codigo_barras, descricao, quantidade, unitario, total}, como
    # texto no JSON: a conferência é recalculada a cada abertura da tela, e não
    # gravada, para nunca mostrar divergência de um pedido que mudou depois.
    itens_lidos = models.JSONField(default=list, blank=True)
    erro_de_leitura = models.CharField(max_length=300, blank=True)

    enviado_em = models.DateTimeField(default=timezone.now)
    enviado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="anexos_de_pedido",
    )

    class Meta:
        ordering = ["-enviado_em", "-id"]
        verbose_name = "anexo do pedido"
        verbose_name_plural = "anexos do pedido"
        constraints = [
            models.UniqueConstraint(fields=["pedido", "sha256"], name="anexo_uma_vez_por_pedido"),
        ]

    def __str__(self):
        return self.nome_original

    @staticmethod
    def calcular_sha256(arquivo):
        resumo = hashlib.sha256()
        for bloco in arquivo.chunks():
            resumo.update(bloco)
        arquivo.seek(0)
        return resumo.hexdigest()

    @property
    def foi_lido(self):
        return bool(self.itens_lidos) or self.valor_do_documento is not None

    @property
    def tamanho_legivel(self):
        if self.tamanho < 1024:
            return f"{self.tamanho} bytes"
        if self.tamanho < 1024 * 1024:
            return f"{self.tamanho / 1024:.0f} KB"
        return f"{self.tamanho / (1024 * 1024):.1f} MB"
