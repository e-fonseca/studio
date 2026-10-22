from django.contrib import admin

from .models import Processo


@admin.register(Processo)
class ProcessoAdmin(admin.ModelAdmin):
    """Somente leitura no admin: alterações passam pelas telas, que aplicam as regras."""

    list_display = ["codigo", "titulo", "area", "criticidade", "estado", "titular", "prazo_coleta"]
    list_filter = ["estado", "area", "criticidade"]
    search_fields = ["titulo"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
