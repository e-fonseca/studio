from django.contrib import admin

from .models import EventoAuditoria


@admin.register(EventoAuditoria)
class EventoAuditoriaAdmin(admin.ModelAdmin):
    list_display = ["momento", "usuario_rotulo", "acao", "recurso_tipo", "recurso_id", "resultado"]
    list_filter = ["resultado", "acao"]
    search_fields = ["usuario_rotulo", "acao", "recurso_rotulo", "correlacao"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("auditoria.ver_auditoria")
