from django.contrib import admin

from .models import Importacao, ProdutoImportado


@admin.register(Importacao)
class ImportacaoAdmin(admin.ModelAdmin):
    list_display = ("iniciada_em", "origem", "situacao", "data_corte", "produtos", "automatica")
    list_filter = ("situacao", "origem", "automatica")
    date_hierarchy = "iniciada_em"
    readonly_fields = [campo.name for campo in Importacao._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(ProdutoImportado)
class ProdutoImportadoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "descricao", "grupo", "estoque", "vendas_12m", "compras_12m", "custo")
    search_fields = ("codigo", "descricao")
    list_filter = ("importacao",)
    readonly_fields = [campo.name for campo in ProdutoImportado._meta.fields]

    def has_add_permission(self, request):
        return False
