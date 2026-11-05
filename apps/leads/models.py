"""Leads: quem demonstrou interesse e ainda não virou projeto (o trabalho do SDR).

Pedido do Edson, 05/11/2026: *"sistema de SDR para controlar os leads"*.

SDR é quem recebe o interesse, faz o primeiro contato, descobre se a pessoa é cliente de
verdade (qualifica) e passa adiante o que vale um orçamento. O que mata um lead quase
nunca é o "não" do cliente: é ninguém ter voltado a falar com ele. Por isso a regra deste
módulo é que **todo lead em aberto tem um próximo contato marcado**, e a tela abre pelo
que vence hoje.

O lead vem de qualquer canal; o do WhatsApp chega pelo Kommo, trazido pelo agente da casa
do Edson (apps/integracao), e guarda o número dele lá para não entrar duas vezes. Quando
fecha, vira um projeto (apps/projetos) e o lead fica ligado a ele.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class Lead(models.Model):
    class Origem(models.TextChoices):
        WHATSAPP = "whatsapp", "WhatsApp (Kommo)"
        INSTAGRAM = "instagram", "Instagram"
        SITE = "site", "Site"
        INDICACAO = "indicacao", "Indicação"
        LOJA = "loja", "Visita à loja"
        ARQUITETO = "arquiteto", "Arquiteto ou decorador"
        OUTRO = "outro", "Outro"

    class Etapa(models.TextChoices):
        # A ordem é a do funil, e é nela que as colunas aparecem.
        NOVO = "novo", "Novo"
        CONTATO = "contato", "Em contato"
        QUALIFICADO = "qualificado", "Qualificado"
        PROPOSTA = "proposta", "Orçamento enviado"
        GANHO = "ganho", "Ganho"
        PERDIDO = "perdido", "Perdido"

    ABERTAS = (Etapa.NOVO, Etapa.CONTATO, Etapa.QUALIFICADO, Etapa.PROPOSTA)
    FECHADAS = (Etapa.GANHO, Etapa.PERDIDO)

    nome = models.CharField(max_length=160)
    telefone = models.CharField("telefone ou WhatsApp", max_length=40, blank=True)
    email = models.EmailField("e-mail", blank=True)
    origem = models.CharField(max_length=20, choices=Origem.choices, default=Origem.WHATSAPP)
    interesse = models.TextField(
        "o que a pessoa quer", blank=True,
        help_text="Ex.: mesa de jantar em ferro para 8 lugares, apartamento novo, entrega em março.",
    )
    valor_estimado = models.DecimalField(
        "valor estimado (R$)", max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Quanto o projeto deve valer, se der para estimar. Serve para priorizar.",
    )
    etapa = models.CharField(max_length=20, choices=Etapa.choices, default=Etapa.NOVO)
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="leads", verbose_name="quem cuida",
    )
    proximo_contato = models.DateField(
        "próximo contato", null=True, blank=True,
        help_text="Quando falar com a pessoa de novo. Lead sem data é lead esquecido.",
    )
    motivo_perda = models.CharField("por que perdemos", max_length=200, blank=True)
    projeto = models.ForeignKey(
        "projetos.Projeto", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="leads", verbose_name="projeto que virou",
    )
    kommo_id = models.CharField("número no Kommo", max_length=40, blank=True, db_index=True)

    criado_em = models.DateTimeField(default=timezone.now)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="leads_criados",
    )
    atualizado_em = models.DateTimeField(auto_now=True)
    fechado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["proximo_contato", "-criado_em"]
        verbose_name = "lead"
        verbose_name_plural = "leads"
        permissions = [
            ("ver_leads", "Pode ver o funil de leads"),
            ("trabalhar_leads", "Pode cadastrar leads, registrar contatos e mudar a etapa"),
        ]
        constraints = [
            # Um lead do Kommo entra uma vez só, por mais que o agente mande de novo.
            models.UniqueConstraint(
                fields=["kommo_id"], condition=~models.Q(kommo_id=""), name="lead_kommo_unico",
            ),
        ]

    def __str__(self):
        return self.nome

    @property
    def aberto(self):
        return self.etapa in self.ABERTAS

    def atrasado(self, hoje=None):
        return bool(self.aberto and self.proximo_contato
                    and self.proximo_contato < (hoje or timezone.localdate()))

    def para_hoje(self, hoje=None):
        return bool(self.aberto and self.proximo_contato
                    and self.proximo_contato <= (hoje or timezone.localdate()))


class Contato(models.Model):
    """Uma conversa com o lead: o que foi falado, por onde, e por quem."""

    class Canal(models.TextChoices):
        WHATSAPP = "whatsapp", "WhatsApp"
        LIGACAO = "ligacao", "Ligação"
        EMAIL = "email", "E-mail"
        PRESENCIAL = "presencial", "Na loja"
        OUTRO = "outro", "Outro"

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="contatos")
    quando = models.DateTimeField(default=timezone.now)
    canal = models.CharField(max_length=20, choices=Canal.choices, default=Canal.WHATSAPP)
    resumo = models.TextField("o que foi falado")
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="contatos_com_leads",
    )
    # Contato que chegou pelo agente (o histórico do Kommo) é marcado: não foi alguém do
    # Studio que digitou, e a tela diz isso.
    automatico = models.BooleanField(default=False)

    class Meta:
        ordering = ["-quando", "-id"]
        verbose_name = "contato com o lead"
        verbose_name_plural = "contatos com o lead"

    def __str__(self):
        return f"{self.get_canal_display()} em {self.quando:%d/%m/%Y}"
