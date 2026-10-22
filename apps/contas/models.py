from django.conf import settings
from django.db import models


class VinculoIdentidade(models.Model):
    """Liga o usuário deste sistema à sua identidade de origem.

    Enquanto a integração com a intranet não estiver definida, as contas são
    locais e marcadas como provisórias. Quando houver SSO (ex.: OIDC), o
    identificador externo passa a ser a chave, nunca o nome digitado.
    """

    class Origem(models.TextChoices):
        LOCAL_PROVISORIA = "local_provisoria", "Conta local provisória"
        INTRANET = "intranet", "Intranet"

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="vinculo"
    )
    origem = models.CharField(max_length=20, choices=Origem.choices, default=Origem.LOCAL_PROVISORIA)
    identificador_externo = models.CharField(max_length=200, blank=True)
    # CPF de quem usa o sistema, só os onze dígitos. Serve para a gerência saber quem é
    # quem quando dois funcionários têm nome parecido, e para o dia em que a entrada
    # passar pela intranet. Nunca vai para a trilha de auditoria (apps/auditoria/servicos.py
    # omite a chave "cpf") e não aparece em tela nenhuma fora de Usuários.
    cpf = models.CharField("CPF", max_length=11, blank=True)
    desligado_em = models.DateTimeField(null=True, blank=True)
    observacao = models.TextField(blank=True)

    class Meta:
        verbose_name = "vínculo de identidade"
        verbose_name_plural = "vínculos de identidade"
        permissions = [("gerenciar_usuarios", "Pode criar, editar e desligar usuários")]
        constraints = [
            models.UniqueConstraint(
                fields=["origem", "identificador_externo"],
                condition=~models.Q(identificador_externo=""),
                name="identidade_externa_unica",
            ),
            models.UniqueConstraint(
                fields=["cpf"], condition=~models.Q(cpf=""), name="cpf_unico",
            ),
        ]

    def __str__(self):
        return f"{self.usuario} ({self.get_origem_display()})"
