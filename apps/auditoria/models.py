from django.conf import settings
from django.db import models


class SomenteInclusaoQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise PermissionError("Eventos de auditoria não podem ser alterados.")

    def delete(self):
        raise PermissionError("Eventos de auditoria não podem ser apagados.")


class EventoAuditoria(models.Model):
    """Trilha de auditoria: somente inclusão.

    A aplicação não altera nem apaga eventos. No PostgreSQL, um gatilho
    (migração 0002) também recusa UPDATE e DELETE. Um administrador do banco
    ainda pode remover o gatilho; por isso a proteção é proporcional, não absoluta.
    """

    class Resultado(models.TextChoices):
        SUCESSO = "sucesso", "Sucesso"
        FALHA = "falha", "Falha"
        NEGADO = "negado", "Negado"

    momento = models.DateTimeField(auto_now_add=True, db_index=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    usuario_rotulo = models.CharField("usuário ou serviço", max_length=150)
    acao = models.CharField(max_length=80, db_index=True)
    recurso_tipo = models.CharField(max_length=80, blank=True)
    recurso_id = models.CharField(max_length=64, blank=True)
    recurso_rotulo = models.CharField(max_length=200, blank=True)
    resultado = models.CharField(max_length=10, choices=Resultado.choices, default=Resultado.SUCESSO)
    correlacao = models.UUIDField(db_index=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    antes = models.JSONField(null=True, blank=True)
    depois = models.JSONField(null=True, blank=True)
    motivo = models.TextField(blank=True)

    objects = SomenteInclusaoQuerySet.as_manager()

    class Meta:
        ordering = ["-momento", "-id"]
        verbose_name = "evento de auditoria"
        verbose_name_plural = "eventos de auditoria"
        permissions = [("ver_auditoria", "Pode consultar a trilha de auditoria")]
        indexes = [models.Index(fields=["recurso_tipo", "recurso_id"])]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionError("Eventos de auditoria não podem ser alterados.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Eventos de auditoria não podem ser apagados.")

    def __str__(self):
        return f"{self.momento:%d/%m/%Y %H:%M} {self.usuario_rotulo} {self.acao}"
