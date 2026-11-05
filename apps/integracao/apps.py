from django.apps import AppConfig


class IntegracaoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.integracao"
    verbose_name = "Integração com o agente (Trello e Kommo)"

    def ready(self):
        from . import sinais  # noqa: F401
