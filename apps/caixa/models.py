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

from django.conf import settings
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


class RegraDeDesconto(models.Model):
    """As regras de pagamento e as metas da loja, como a gerência passou à equipe.

    Pedido do Edson em 02/11/2026, com a mensagem que vai para o grupo da loja: no Pix ou
    no dinheiro, 7% de desconto; no crédito, até 3x sem desconto; "qualquer condição
    diferente precisa de aprovação no grupo antes de ser confirmada ao cliente", e quem
    autoriza é Miranda, Henriett ou Edson. A meta do sábado e do feriado é R$ 12.000, a do
    domingo R$ 15.000 (era R$ 18.000 até 04/11/2026, quando ele baixou, na 1.47.0); batida,
    cada funcionário que trabalhou no dia ganha R$ 30, e mais R$ 10 a cada R$ 1.000 acima.

    Fica no banco, e não no código, porque é a gerência que muda: a porcentagem, a meta e
    o prêmio mudam com a estação, e quem muda não pode depender de programador. É uma
    linha só (`atual`). A tela de descontos confere cada venda contra o que está aqui.
    """

    desconto_a_vista = models.DecimalField(
        "desconto no Pix ou no dinheiro (%)", max_digits=5, decimal_places=2, default=Decimal("7.00"))
    desconto_no_debito = models.DecimalField(
        "desconto no cartão de débito (%)", max_digits=5, decimal_places=2, default=Decimal("0"),
        help_text="As regras não falam do débito: com zero, débito com desconto precisa de aprovação.")
    desconto_no_credito = models.DecimalField(
        "desconto no cartão de crédito (%)", max_digits=5, decimal_places=2, default=Decimal("0"))
    parcelas_no_credito = models.PositiveSmallIntegerField(
        "parcelas no crédito sem aprovação", default=3,
        help_text="O SET não grava em quantas vezes o cartão foi passado: este número vai na regra, mas a tela não o confere.")
    folga = models.DecimalField(
        "folga para arredondar (R$)", max_digits=7, decimal_places=2, default=Decimal("1.00"),
        help_text="Desconto que passa da regra por até este valor é arredondamento, não conta.")
    quem_autoriza = models.CharField(
        "quem pode autorizar", max_length=120, default="Miranda, Henriett ou Edson",
        help_text="Os nomes separados por vírgula ou por \"ou\". São as opções de quem aprovou.")

    meta_sabado = models.DecimalField(
        "meta do sábado e do feriado (R$)", max_digits=12, decimal_places=2, default=Decimal("12000"))
    meta_domingo = models.DecimalField(
        "meta do domingo (R$)", max_digits=12, decimal_places=2, default=Decimal("15000"))
    premio = models.DecimalField(
        "prêmio de quem trabalhou, meta batida (R$)", max_digits=9, decimal_places=2,
        default=Decimal("30"))
    premio_a_mais = models.DecimalField(
        "a mais por pessoa a cada passo acima da meta (R$)", max_digits=9, decimal_places=2,
        default=Decimal("10"))
    passo = models.DecimalField(
        "o passo acima da meta (R$)", max_digits=12, decimal_places=2, default=Decimal("1000"))
    outros_feriados = models.TextField(
        "feriados da cidade e outros dias de meta", blank=True,
        help_text="Um por linha: 20/01 vale todo ano, 16/02/2027 vale só aquele dia. "
                  "Os nacionais, o de São Paulo e os de Embu das Artes o sistema já sabe.")

    atualizada_em = models.DateTimeField("mudada em", auto_now=True)
    atualizada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name="mudada por")

    class Meta:
        verbose_name = "regra de desconto e meta"
        verbose_name_plural = "regras de desconto e metas"
        permissions = [("controlar_descontos",
                        "Pode ver os descontos de cada venda, registrar a aprovação do grupo "
                        "e mudar as regras de desconto e as metas")]

    def __str__(self):
        return "Regras de desconto e metas"

    @classmethod
    def atual(cls):
        """A linha única das regras; na primeira vez nasce com as do Edson de 02/11/2026."""
        regra, _ = cls.objects.get_or_create(pk=1)
        return regra

    def nomes_de_quem_autoriza(self):
        """["Miranda", "Henriett", "Edson"] a partir de "Miranda, Henriett ou Edson"."""
        texto = self.quem_autoriza.replace(";", ",").replace(" ou ", ",").replace(" e ", ",")
        nomes = [nome.strip() for nome in texto.split(",")]
        return [nome for nome in dict.fromkeys(nomes) if nome]


class DescontoAprovado(models.Model):
    """A aprovação do grupo para uma venda que saiu da regra, anotada no sistema.

    A regra do Edson é que a condição diferente seja aprovada no grupo ANTES de ser
    confirmada ao cliente. O SET não tem onde guardar isso; aqui fica quem aprovou, para a
    venda sair da lista do que ninguém autorizou. A venda é a do SET (IDVENDA), que não
    muda de uma importação para a outra.

    Nada se apaga: desfazer marca a linha como desfeita e a venda volta para a lista. A
    auditoria guarda quem anotou e quem desfez.
    """

    id_venda = models.IntegerField("número interno da venda no SET")
    numero = models.CharField("número da venda", max_length=40, blank=True)
    dia = models.DateField("dia da venda")
    valor_da_venda = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    desconto = models.DecimalField("desconto na hora da aprovação", max_digits=14, decimal_places=2,
                                   default=0)
    autorizado_por = models.CharField("quem autorizou", max_length=60)
    observacao = models.CharField("observação", max_length=200, blank=True)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name="anotado por")
    registrado_em = models.DateTimeField("anotado em", auto_now_add=True)
    desfeito_em = models.DateTimeField("desfeito em", null=True, blank=True)
    desfeito_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name="desfeito por")

    class Meta:
        ordering = ["-registrado_em"]
        verbose_name = "desconto aprovado"
        verbose_name_plural = "descontos aprovados"
        constraints = [
            # Uma aprovação valendo por venda; as desfeitas ficam como histórico.
            models.UniqueConstraint(fields=["id_venda"], condition=models.Q(desfeito_em__isnull=True),
                                    name="uma_aprovacao_valendo_por_venda"),
        ]

    def __str__(self):
        return f"Venda {self.numero or self.id_venda} aprovada por {self.autorizado_por}"
