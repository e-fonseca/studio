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
    # Último dia em que a pessoa entra no sistema (1.42.0). Pedido do Edson em 31/10/2026,
    # com a Cássia chegando e a Bárbara saindo: "ficara no lugar da barbara ate dia
    # 12/11/2026". No dia seguinte a conta se desliga sozinha, com o mesmo efeito do
    # Encerrar da tela de usuários. É o "registrar delegações temporárias, bloquear
    # desligados e invalidar sessões" do briefing de 05/10/2026.
    acesso_ate = models.DateField("último dia de acesso", null=True, blank=True)
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


class CodigoDeRecuperacao(models.Model):
    """O código de seis números que vai ao e-mail cadastrado para criar uma senha nova.

    Pedido do Edson em 31/10/2026: "adotar recurso de recuperar senha por e-mail cadastrado
    via confirmação de código, senão tiver cadastro informe que não é possível, procure o
    administrador do sistema". O caminho inteiro está em apps/contas/recuperacao.py.

    O código em si não fica guardado: fica o `resumo`, uma assinatura feita com a chave
    secreta do sistema, que confere o código digitado sem permitir lê-lo de volta. Quem
    abrir o banco não acha código nenhum para usar.
    """

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    resumo = models.CharField(max_length=128)
    criado_em = models.DateTimeField(db_index=True)
    vale_ate = models.DateTimeField()
    # Errou o código esta quantidade de vezes. Na quinta o código é anulado.
    tentativas = models.PositiveSmallIntegerField(default=0)
    # Usado para criar a senha nova: não vale mais.
    usado_em = models.DateTimeField(null=True, blank=True)
    # Anulado sem uso: chegou outro código depois dele, ou erraram demais.
    anulado_em = models.DateTimeField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        verbose_name = "código de recuperação de senha"
        verbose_name_plural = "códigos de recuperação de senha"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Código para {self.usuario} de {self.criado_em:%d/%m/%Y %H:%M}"

    @property
    def aberto(self):
        """Ainda serve: não foi usado, não foi anulado e não venceu."""
        from django.utils import timezone  # noqa: PLC0415 - o módulo de modelos é carregado cedo

        return self.usado_em is None and self.anulado_em is None and timezone.now() <= self.vale_ate
