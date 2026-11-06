"""O que o planejamento financeiro do Studio precisa saber além dos pedidos.

Veio do protótipo que rodava no Claude do perfil da Henriett, trazido pelo Edson em
06/11/2026 ("importei um protótipo que rodava dentro do claude do perfil da henriett").
Lá estas coisas moravam num documento de configuração só; aqui cada uma é uma tabela,
para cada mudança deixar rastro na auditoria e para o formulário não perder nada.

- **Parametros**: o saldo em conta, a margem mínima, o atraso que vira alerta, a taxa de
  antecipação, o % das vendas no cartão, o % da 1ª parcela e o cartão padrão. Uma linha só.
- **Cartao**: os cartões em que o Studio paga oficina (XP, Bradesco, Itaú), com o dia do
  vencimento e quantos dias antes a fatura fecha. É o fechamento que diz em que fatura
  cai uma compra: conferido com as faturas reais de outubro e novembro/26.
- **CustoFixo**: folha, aluguel, Simples, tráfego, gerais e as parcelas de empréstimo.
- **Divida**: limite e conta garantida, com o saldo usado e a taxa ao mês. O juro do mês
  é saldo × taxa, e entra como saída no dia de cada uma.
- **Avulso**: a saída que acontece uma vez (o saldo da parcela do Rogério até 15/11).
- **MovimentoEntreEmpresas**: o que passa entre Studio e Cabana (Essenza), que não é
  receita nem despesa, e o pró-labore pago por cada empresa.

Porcentagens são guardadas como se lê: 25 quer dizer 25%.
"""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

ZERO = Decimal("0")
CEM = Decimal("100")
DIA = [MinValueValidator(1), MaxValueValidator(31)]
PERCENTUAL = [MinValueValidator(ZERO), MaxValueValidator(CEM)]


class Cartao(models.Model):
    nome = models.CharField(max_length=40, unique=True)
    vencimento = models.PositiveSmallIntegerField(
        "vence todo dia", validators=DIA,
        help_text="Mês curto vence no último dia.")
    fecha_dias_antes = models.PositiveSmallIntegerField(
        "fecha quantos dias antes", validators=[MaxValueValidator(28)],
        help_text="Compra feita até o fechamento cai nesta fatura; depois dele, na seguinte.")
    observacao = models.CharField(
        "como é pago", max_length=160, blank=True,
        help_text="Ex.: boleto da conta do Studio; débito na conta do Henry.")
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["vencimento", "nome"]
        verbose_name = "cartão"
        verbose_name_plural = "cartões"

    def __str__(self):
        return self.nome


class Parametros(models.Model):
    """As regras gerais, numa linha só (pk=1). Use `Parametros.atual()`."""

    saldo_inicial = models.DecimalField(
        "saldo em conta hoje (R$)", max_digits=12, decimal_places=2, default=ZERO,
        help_text="De onde o caixa projetado começa. Negativo quando a conta está no limite.")
    saldo_em = models.DateField(
        "saldo conferido em", null=True, blank=True,
        help_text="O dia em que o saldo acima foi olhado no banco.")
    margem_minima = models.DecimalField(
        "margem mínima (%)", max_digits=5, decimal_places=2, default=Decimal("25"),
        validators=PERCENTUAL, help_text="Pedido abaixo disto aparece nos alertas.")
    atraso_dias = models.PositiveSmallIntegerField(
        "atraso vira alerta depois de (dias)", default=10)
    taxa_antecipacao = models.DecimalField(
        "taxa de antecipação do cartão (%)", max_digits=5, decimal_places=2,
        default=Decimal("15"), validators=PERCENTUAL,
        help_text="MDR mais antecipação. Na Rede, em out/26, deu perto de 12%; 15% é a "
                  "média conservadora.")
    pct_cartao = models.DecimalField(
        "% das vendas no cartão (quando não se sabe)", max_digits=5, decimal_places=2,
        default=Decimal("50"), validators=PERCENTUAL)
    pct_primeira = models.DecimalField(
        "% do custo na 1ª parcela da oficina", max_digits=5, decimal_places=2,
        default=Decimal("50"), validators=PERCENTUAL)
    parcelas_padrao = models.PositiveSmallIntegerField(
        "parcelas no cartão (padrão)", default=2,
        validators=[MinValueValidator(1), MaxValueValidator(24)])
    cartao_padrao = models.ForeignKey(
        Cartao, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="cartão padrão")
    markup_alvo = models.DecimalField(
        "markup alvo sobre a oficina (%)", max_digits=6, decimal_places=2,
        default=Decimal("80"), validators=[MinValueValidator(ZERO)],
        help_text="Usado no ponto de equilíbrio enquanto não há pedido com margem calculada.")
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "parâmetros do planejamento"
        verbose_name_plural = "parâmetros do planejamento"

    def __str__(self):
        return "Parâmetros do planejamento"

    @classmethod
    def atual(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class CustoFixo(models.Model):
    class Tipo(models.TextChoices):
        FIXO = "fixo", "Custo fixo"
        EMPRESTIMO = "emprestimo", "Parcela de empréstimo"

    nome = models.CharField(max_length=160)
    tipo = models.CharField(max_length=12, choices=Tipo.choices, default=Tipo.FIXO)
    valor = models.DecimalField(
        "valor (R$)", max_digits=12, decimal_places=2, validators=[MinValueValidator(ZERO)])
    dia = models.PositiveSmallIntegerField("dia do pagamento", default=10, validators=DIA)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["tipo", "dia", "nome"]
        verbose_name = "custo fixo"
        verbose_name_plural = "custos fixos"

    def __str__(self):
        return self.nome


class Divida(models.Model):
    nome = models.CharField("conta", max_length=160)
    saldo = models.DecimalField(
        "saldo usado (R$)", max_digits=12, decimal_places=2, validators=[MinValueValidator(ZERO)])
    taxa_mensal = models.DecimalField(
        "taxa ao mês (%)", max_digits=6, decimal_places=3, validators=PERCENTUAL)
    dia = models.PositiveSmallIntegerField("dia em que o juro cai", default=1, validators=DIA)
    ativa = models.BooleanField(default=True)

    class Meta:
        ordering = ["dia", "nome"]
        verbose_name = "dívida"
        verbose_name_plural = "dívidas"

    def __str__(self):
        return self.nome

    @property
    def juros_mes(self):
        return ((self.saldo or ZERO) * (self.taxa_mensal or ZERO) / CEM).quantize(Decimal("0.01"))


class Avulso(models.Model):
    nome = models.CharField("o que é", max_length=200)
    valor = models.DecimalField(
        "valor (R$)", max_digits=12, decimal_places=2, validators=[MinValueValidator(ZERO)])
    data = models.DateField("vence em")
    pago = models.BooleanField("já foi pago", default=False)

    class Meta:
        ordering = ["data", "id"]
        verbose_name = "saída avulsa"
        verbose_name_plural = "saídas avulsas"

    def __str__(self):
        return self.nome


class MovimentoEntreEmpresas(models.Model):
    """Dinheiro entre Studio e Cabana (Essenza), ou pró-labore pago por uma delas.

    Não é receita nem despesa: a tela mostra quem deve a quem, mês a mês. Lançamento
    errado não se apaga, se cancela, e o cancelado sai das contas.
    """

    class Tipo(models.TextChoices):
        TRANSFERENCIA = "transferencia", "Transferência"
        CARTAO = "cartao", "Cartão em comum"
        PROLABORE = "prolabore", "Pró-labore"

    class Sentido(models.TextChoices):
        CABANA_DEVE = "cabana_deve", "A Cabana deve ao Studio"
        STUDIO_DEVE = "studio_deve", "O Studio deve à Cabana"

    class Empresa(models.TextChoices):
        STUDIO = "studio", "Studio"
        CABANA = "cabana", "Cabana"

    data = models.DateField()
    tipo = models.CharField(max_length=15, choices=Tipo.choices)
    sentido = models.CharField(
        "quem deve", max_length=15, choices=Sentido.choices, blank=True,
        help_text="Para transferência e cartão.")
    empresa = models.CharField(
        "empresa que pagou", max_length=10, choices=Empresa.choices, blank=True,
        help_text="Para pró-labore.")
    valor = models.DecimalField(
        "valor (R$)", max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    descricao = models.CharField(
        "descrição", max_length=200, blank=True,
        help_text="Ex.: parte da Cabana na fatura Itaú de 20/11.")
    criado_em = models.DateTimeField(default=timezone.now)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    cancelado_em = models.DateTimeField(null=True, blank=True)
    cancelado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["data", "id"]
        verbose_name = "movimento entre empresas"
        verbose_name_plural = "movimentos entre empresas"
        permissions = [
            ("ver_planejamento", "Pode ver o planejamento financeiro do Studio"),
            ("editar_planejamento", "Pode mudar os ajustes e lançar movimentos entre empresas"),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} de {self.valor} em {self.data:%d/%m/%Y}"

    @property
    def sinal(self):
        """+1 quando a Cabana deve ao Studio, -1 quando o Studio deve à Cabana."""
        return 1 if self.sentido == self.Sentido.CABANA_DEVE else -1
