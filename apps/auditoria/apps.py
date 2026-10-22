from django.apps import AppConfig


class AuditoriaConfig(AppConfig):
    verbose_name = "Auditoria"
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.auditoria"

    def ready(self):
        from . import sinais  # noqa: F401
