from django.apps import AppConfig


class ContasConfig(AppConfig):
    verbose_name = "Contas e perfis"
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.contas"

    def ready(self):
        from . import sinais  # noqa: F401
