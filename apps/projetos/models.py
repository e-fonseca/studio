"""Projetos de móveis sob medida, as oficinas parceiras que os fazem e o dinheiro de cada um.

Por que existe (pedido do Edson, 05/11/2026)
--------------------------------------------
*"tem muitos projetos de moveis estilo industrial sob medida (...) temos parcerias com
oficinas de serralherias onde são desenvolvidos os projetos (...) um dos objetivos é
controlar o financeiro, o que entrou, o que saiu e a projeção futura."*

O SET não tem nada disso: ele guarda a venda depois que ela vira nota, e não o projeto
que leva semanas entre o orçamento e a entrega, nem qual oficina está fazendo, nem quanto
falta pagar a ela. Este módulo nasce aqui e não lê nem escreve no SET.

As regras do dinheiro vieram do protótipo da Henriett (06/11/2026)
-----------------------------------------------------------------
O Edson trouxe o painel financeiro que já rodava no Claude do perfil da Henriett, com 60
pedidos conferidos contra Trello, Kommo, faturas e extratos. As regras dele são as do
dia a dia do Studio e passaram a ser as daqui:

- o pedido não guarda parcela lançada à mão: o pagamento à oficina **sai da regra**.
  No padrão, 50% do custo no cartão (a fatura é achada pelo fechamento de cada cartão)
  e 50% em Pix na entrega. Oficina com parcelas mensais (o Rogério em 3x todo dia 30,
  com corte no dia 25; o Breno em 3x todo dia 15, com corte no dia 10) paga pela regra
  dela. E há o pedido pago todo no cartão;
- do cliente, guarda-se o valor da venda, o que já foi recebido e como vem o saldo.
  Cartão do cliente entra antecipado, então só o saldo em Pix entra na previsão;
- margem é de lucro, não markup: venda menos oficina, frete, embalagem, RT, projeto e a
  taxa de antecipação do cartão, dividido pela venda.

As contas ficam em apps/planejamento/regras.py, num lugar só.
"""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
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

    class Pagamento(models.TextChoices):
        PADRAO = "padrao", "Padrão: metade no cartão, metade em Pix na entrega"
        MENSAL = "mensal", "Parcelas mensais em dia fixo"
        CARTAO = "cartao", "Tudo no cartão"

    pagamento = models.CharField(
        "como a oficina recebe", max_length=10, choices=Pagamento.choices,
        default=Pagamento.PADRAO,
        help_text="Vale para os pedidos desta oficina que não disserem outra coisa.",
    )
    parcelas_mensais = models.PositiveSmallIntegerField(
        "quantas parcelas mensais", default=3,
        validators=[MinValueValidator(1), MaxValueValidator(24)],
        help_text="Só para quem recebe em parcelas mensais. Ex.: 3.",
    )
    dia_pagamento = models.PositiveSmallIntegerField(
        "paga todo dia", null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        help_text="Ex.: 30 para o Rogério, 15 para o Breno. Mês curto paga no último dia.",
    )
    dia_corte = models.PositiveSmallIntegerField(
        "corte no dia", null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        help_text="Pedido repassado até este dia entra no mesmo mês; depois dele, no "
                  "seguinte. Ex.: 25 para o Rogério, 10 para o Breno.",
    )
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
        APROVADO = "aprovado", "Vendido, em projeto"
        PRODUCAO = "producao", "Em produção na oficina"
        PRONTO = "pronto", "Pronto para entregar"
        ENTREGUE = "entregue", "Entregue"
        MANUTENCAO = "manutencao", "Em manutenção"
        CANCELADO = "cancelado", "Cancelado"

    # Etapas em que o projeto ainda está andando: entram no "em andamento" e no atraso.
    # Manutenção também: a peça voltou e tem conserto a fazer, com prazo e custo.
    EM_ANDAMENTO = (Etapa.APROVADO, Etapa.PRODUCAO, Etapa.PRONTO, Etapa.MANUTENCAO)
    # Etapas de pedido vendido: é o que entra no dinheiro. Orçamento não vendeu nada.
    VENDIDOS = EM_ANDAMENTO + (Etapa.ENTREGUE,)

    class Regime(models.TextChoices):
        OFICINA = "", "Como a oficina recebe"
        PADRAO = "padrao", "Padrão: 1ª no cartão, 2ª em Pix na entrega"
        MENSAL = "mensal", "Parcelas mensais da oficina"
        CARTAO = "cartao", "Tudo no cartão"

    class SaldoForma(models.TextChoices):
        A_CONFIRMAR = "", "A confirmar"
        PIX = "pix", "Pix na entrega"
        CARTAO = "cartao", "Cartão (já entrou antecipado)"
        QUITADO = "quitado", "Quitado"

    numero = models.CharField(
        "número do pedido (P)", max_length=40, blank=True, db_index=True,
        help_text="O número do card no Trello. Ex.: 28634, ou 28764/86/96 quando são vários.",
    )

    titulo = models.CharField(
        "o que é", max_length=160, blank=True,
        help_text="Ex.: Mesa de jantar 2,20 m em ferro e madeira de demolição.",
    )
    cliente_nome = models.CharField("cliente", max_length=160)
    vendedor = models.CharField(max_length=80, blank=True)
    arquiteto = models.CharField("arquiteto ou decorador", max_length=120, blank=True)
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
        help_text="Montagem, vidro, madeira comprada à parte.",
    )
    frete = models.DecimalField(
        "frete pago pelo Studio (R$)", max_digits=12, decimal_places=2, default=ZERO,
        validators=[MinValueValidator(ZERO)])
    embalagem = models.DecimalField(
        "embalagem (R$)", max_digits=12, decimal_places=2, default=ZERO,
        validators=[MinValueValidator(ZERO)])
    rt = models.DecimalField(
        "RT do arquiteto (R$)", max_digits=12, decimal_places=2, default=ZERO,
        validators=[MinValueValidator(ZERO)])
    projeto_desenho = models.DecimalField(
        "projeto e desenho (R$)", max_digits=12, decimal_places=2, default=ZERO,
        validators=[MinValueValidator(ZERO)],
        help_text="De R$ 80 a 120 conforme a dificuldade, mais R$ 30 de intermediação.",
    )

    # O cliente -----------------------------------------------------------------------
    data_venda = models.DateField(
        "data da venda", null=True, blank=True,
        help_text="É ela que põe o pedido no mês do Fechamento por competência.",
    )
    recebido = models.DecimalField(
        "já recebido do cliente (R$)", max_digits=12, decimal_places=2, default=ZERO,
        validators=[MinValueValidator(ZERO)],
    )
    venda_cartao = models.DecimalField(
        "quanto entrou no cartão (R$)", max_digits=12, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(ZERO)],
        help_text="Para a taxa de antecipação da margem. Em branco, a conta usa o % de "
                  "vendas no cartão dos Ajustes e a margem aparece como estimada.",
    )
    saldo_forma = models.CharField(
        "como vem o saldo do cliente", max_length=10, choices=SaldoForma.choices,
        default=SaldoForma.A_CONFIRMAR, blank=True,
    )
    saldo_pix = models.DecimalField(
        "saldo em Pix, se for outro (R$)", max_digits=12, decimal_places=2, null=True,
        blank=True, validators=[MinValueValidator(ZERO)],
        help_text="Em branco, o saldo é a venda menos o já recebido.",
    )

    # A oficina -----------------------------------------------------------------------
    regime = models.CharField(
        "como a oficina recebe neste pedido", max_length=10, choices=Regime.choices,
        default=Regime.OFICINA, blank=True,
    )
    repasse = models.DateField(
        "repassado à oficina em", null=True, blank=True,
        help_text="Para oficina de parcelas mensais: é esta data, contra o dia de corte, "
                  "que diz o mês da 1ª parcela.",
    )
    primeira_percentual = models.DecimalField(
        "% do custo na 1ª parcela", max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(ZERO), MaxValueValidator(Decimal("100"))],
        help_text="Em branco, vale o dos Ajustes (50%).",
    )
    incluir = models.BooleanField(
        "entra nas contas a pagar", default=True,
        help_text="Desmarque quando o custo já foi pago fora daqui (bloco antigo da "
                  "oficina, por exemplo). O pedido some das contas e dos alertas.",
    )
    pg1_data = models.DateField("1ª parcela paga em", null=True, blank=True)
    pg1_cartao = models.ForeignKey(
        "planejamento.Cartao", null=True, blank=True, on_delete=models.PROTECT,
        related_name="pedidos", verbose_name="no cartão",
    )
    pg1_parcelas = models.PositiveSmallIntegerField(
        "em quantas vezes no cartão", null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(24)],
    )
    pg2_data = models.DateField("2ª parcela (Pix) paga em", null=True, blank=True)
    observacao = models.TextField("observação", blank=True)

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
        return f"{self.codigo} {self.titulo or self.cliente_nome}"

    @property
    def codigo(self):
        """O número do Trello quando há; senão, o do sistema."""
        if self.numero:
            return self.numero
        return f"S-{self.pk:04d}" if self.pk else "novo"

    @property
    def custo_total(self):
        return sum((v or ZERO for v in (self.custo_oficina, self.outros_custos, self.frete,
                                         self.embalagem, self.rt, self.projeto_desenho)), ZERO)

    @property
    def vendido(self):
        return self.etapa in self.VENDIDOS

    @property
    def regime_efetivo(self):
        """A regra que vale: a do pedido, ou a da oficina, ou a padrão."""
        if self.regime:
            return self.regime
        if self.oficina_id and self.oficina.pagamento:
            return self.oficina.pagamento
        return self.Regime.PADRAO

    @property
    def margem(self):
        """O que sobra antes da taxa do cartão. A margem com a taxa está em
        apps/planejamento/regras.py, porque depende dos Ajustes."""
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
