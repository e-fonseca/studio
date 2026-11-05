"""Projetos de móveis sob medida, as oficinas parceiras que os fazem e o dinheiro de cada um.

Por que existe (pedido do Edson, 05/11/2026)
--------------------------------------------
*"tem muitos projetos de moveis estilo industrial sob medida (...) temos parcerias com
oficinas de serralherias onde são desenvolvidos os projetos (...) um dos objetivos é
controlar o financeiro, o que entrou, o que saiu e a projeção futura."*

O SET não tem nada disso: ele guarda a venda depois que ela vira nota, e não o projeto
que leva semanas entre o orçamento e a entrega, nem qual oficina está fazendo, nem quanto
falta pagar a ela. Este módulo nasce aqui e não lê nem escreve no SET.

O dinheiro do projeto mora nas **parcelas**: cada entrada do cliente e cada pagamento à
oficina é uma linha com valor, vencimento e o dia em que foi pago. É delas que sai o
"quanto entrou, quanto saiu e quanto ainda vem" do projeto e do Fluxo de caixa.

Parcela que já está lançada no SET é marcada como tal e sai das somas do Fluxo de caixa,
que já conta o que veio do SET: sem a marca, a mesma conta entraria duas vezes.
"""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

ZERO = Decimal("0")


class Oficina(models.Model):
    """Oficina parceira (serralheria, marcenaria) que executa os projetos."""

    nome = models.CharField("nome da oficina", max_length=120, unique=True)
    contato = models.CharField("pessoa de contato", max_length=120, blank=True)
    telefone = models.CharField("telefone ou WhatsApp", max_length=40, blank=True)
    cidade = models.CharField(max_length=80, blank=True)
    especialidade = models.CharField(
        max_length=200, blank=True,
        help_text="O que ela faz melhor. Ex.: serralheria, solda, pintura eletrostática.",
    )
    observacao = models.TextField("observação", blank=True)
    ativa = models.BooleanField(
        default=True,
        help_text="Oficina que não trabalha mais com o Studio sai das escolhas, mas fica "
                  "no histórico dos projetos que fez.",
    )
    criado_em = models.DateTimeField(default=timezone.now)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-ativa", "nome"]
        verbose_name = "oficina parceira"
        verbose_name_plural = "oficinas parceiras"

    def __str__(self):
        return self.nome


class Projeto(models.Model):
    """Um móvel (ou um conjunto) sob medida, do orçamento à entrega."""

    class Etapa(models.TextChoices):
        # A ordem é a do caminho do projeto: é nela que a lista e os filtros aparecem.
        ORCAMENTO = "orcamento", "Orçamento"
        APROVADO = "aprovado", "Aprovado"
        PRODUCAO = "producao", "Em produção na oficina"
        PRONTO = "pronto", "Pronto para entregar"
        ENTREGUE = "entregue", "Entregue"
        CANCELADO = "cancelado", "Cancelado"

    # Etapas em que o projeto ainda está andando: entram no "em andamento" e no atraso.
    EM_ANDAMENTO = (Etapa.APROVADO, Etapa.PRODUCAO, Etapa.PRONTO)

    titulo = models.CharField(
        "o que é", max_length=160,
        help_text="Ex.: Mesa de jantar 2,20 m em ferro e madeira de demolição.",
    )
    cliente_nome = models.CharField("cliente", max_length=160)
    cliente_telefone = models.CharField("telefone ou WhatsApp do cliente", max_length=40, blank=True)
    cliente_email = models.EmailField("e-mail do cliente", blank=True)
    descricao = models.TextField(
        "descrição e medidas", blank=True,
        help_text="Medidas, materiais, acabamento e o que foi combinado com o cliente.",
    )
    etapa = models.CharField(max_length=20, choices=Etapa.choices, default=Etapa.ORCAMENTO)
    oficina = models.ForeignKey(
        Oficina, null=True, blank=True, on_delete=models.PROTECT, related_name="projetos",
        verbose_name="oficina parceira",
    )
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="projetos_responsavel", verbose_name="responsável no Studio",
    )

    valor_venda = models.DecimalField(
        "valor de venda (R$)", max_digits=12, decimal_places=2, default=ZERO,
        validators=[MinValueValidator(ZERO)],
        help_text="O que o cliente paga pelo projeto inteiro.",
    )
    custo_oficina = models.DecimalField(
        "custo da oficina (R$)", max_digits=12, decimal_places=2, default=ZERO,
        validators=[MinValueValidator(ZERO)],
        help_text="O que foi combinado de pagar à oficina.",
    )
    outros_custos = models.DecimalField(
        "outros custos (R$)", max_digits=12, decimal_places=2, default=ZERO,
        validators=[MinValueValidator(ZERO)],
        help_text="Frete, montagem, vidro, madeira comprada à parte.",
    )

    aprovado_em = models.DateField("aprovado pelo cliente em", null=True, blank=True)
    prazo_entrega = models.DateField("prazo de entrega combinado", null=True, blank=True)
    entregue_em = models.DateField(null=True, blank=True)

    # Integrações feitas pelo agente da casa do Edson (apps/integracao): o sistema guarda o
    # identificador do outro lado para atualizar o mesmo cartão, e não criar outro.
    trello_cartao = models.CharField("cartão no Trello", max_length=64, blank=True)

    criado_em = models.DateTimeField(default=timezone.now)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="projetos_criados",
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em", "-id"]
        verbose_name = "projeto"
        verbose_name_plural = "projetos"
        permissions = [
            ("ver_projetos", "Pode ver os projetos, as oficinas e os valores de cada um"),
            ("editar_projetos", "Pode cadastrar e mudar projetos, oficinas e parcelas"),
        ]

    def __str__(self):
        return f"{self.codigo} {self.titulo}"

    @property
    def codigo(self):
        return f"P-{self.pk:04d}" if self.pk else "P-novo"

    @property
    def custo_total(self):
        return (self.custo_oficina or ZERO) + (self.outros_custos or ZERO)

    @property
    def margem(self):
        """O que sobra para o Studio: venda menos oficina menos os outros custos."""
        return (self.valor_venda or ZERO) - self.custo_total

    @property
    def margem_percentual(self):
        if not self.valor_venda:
            return None
        return (self.margem / self.valor_venda * 100).quantize(Decimal("0.1"))

    @property
    def em_andamento(self):
        return self.etapa in self.EM_ANDAMENTO

    def dias_de_atraso(self, hoje=None):
        """Dias além do prazo combinado. Zero para o que já foi entregue ou não tem prazo."""
        if not self.em_andamento or not self.prazo_entrega:
            return 0
        return max(0, ((hoje or timezone.localdate()) - self.prazo_entrega).days)

    # O dinheiro do projeto, somado das parcelas -------------------------------------------
    def _soma(self, tipos, pagas):
        consulta = self.parcelas.filter(tipo__in=tipos, pago_em__isnull=not pagas)
        return consulta.aggregate(v=models.Sum("valor"))["v"] or ZERO

    @property
    def recebido(self):
        return self._soma([Parcela.Tipo.RECEBER], pagas=True)

    @property
    def a_receber(self):
        return self._soma([Parcela.Tipo.RECEBER], pagas=False)

    @property
    def pago(self):
        return self._soma(Parcela.SAIDAS, pagas=True)

    @property
    def a_pagar(self):
        return self._soma(Parcela.SAIDAS, pagas=False)

    @property
    def sem_parcela(self):
        """Quanto da venda ainda não virou parcela: o que foi vendido e ninguém agendou."""
        return max(ZERO, (self.valor_venda or ZERO) - self.recebido - self.a_receber)


class Parcela(models.Model):
    """Uma entrada do cliente ou uma saída para a oficina, com data e valor."""

    class Tipo(models.TextChoices):
        RECEBER = "receber", "Entrada do cliente"
        OFICINA = "oficina", "Pagamento à oficina"
        OUTRO = "outro", "Outro custo do projeto"

    SAIDAS = (Tipo.OFICINA, Tipo.OUTRO)

    projeto = models.ForeignKey(Projeto, on_delete=models.CASCADE, related_name="parcelas")
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    descricao = models.CharField(
        "descrição", max_length=160, blank=True,
        help_text="Ex.: sinal de 50%, saldo na entrega, adiantamento da oficina.",
    )
    valor = models.DecimalField(
        "valor (R$)", max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    vencimento = models.DateField("vence em")
    pago_em = models.DateField("pago em", null=True, blank=True)
    forma = models.CharField("forma de pagamento", max_length=40, blank=True)
    lancada_no_set = models.BooleanField(
        "já está lançada no SET", default=False,
        help_text="Marque quando esta conta também estiver no financeiro do SET. Aí o Fluxo "
                  "de caixa conta só a do SET, para não somar a mesma conta duas vezes.",
    )
    criado_em = models.DateTimeField(default=timezone.now)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="parcelas_criadas",
    )

    class Meta:
        ordering = ["vencimento", "id"]
        verbose_name = "parcela do projeto"
        verbose_name_plural = "parcelas do projeto"

    def __str__(self):
        return f"{self.get_tipo_display()} de {self.valor} em {self.vencimento:%d/%m/%Y}"

    @property
    def entrada(self):
        return self.tipo == self.Tipo.RECEBER

    @property
    def em_aberto(self):
        return self.pago_em is None

    def dias_de_atraso(self, hoje=None):
        if self.pago_em:
            return 0
        return max(0, ((hoje or timezone.localdate()) - self.vencimento).days)
