from django.contrib import admin

from .models import VinculoIdentidade


@admin.register(VinculoIdentidade)
class VinculoIdentidadeAdmin(admin.ModelAdmin):
    list_display = ["usuario", "origem", "identificador_externo", "desligado_em"]
    list_filter = ["origem"]
