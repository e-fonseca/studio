"""Conserta o texto digitado nos pagamentos previstos.

É o único dado financeiro que nasce no sistema e não é refeito pela importação, então
o que foi digitado antes da 1.12.0 pode ter vindo torto de um nome de fornecedor
colado da tela.
"""

from django.db import migrations

from apps.core.texto import consertar


def arrumar(apps, schema_editor):
    Previsto = apps.get_model("financeiro", "PagamentoPrevisto")
    for pagamento in Previsto.objects.all():
        campos = {
            "descricao": consertar(pagamento.descricao),
            "fornecedor": consertar(pagamento.fornecedor),
            "observacao": consertar(pagamento.observacao),
        }
        mudou = [nome for nome, valor in campos.items() if valor != getattr(pagamento, nome)]
        if not mudou:
            continue
        for nome, valor in campos.items():
            setattr(pagamento, nome, valor)
        pagamento.save(update_fields=mudou)


class Migration(migrations.Migration):
    dependencies = [("financeiro", "0001_initial")]
    operations = [migrations.RunPython(arrumar, migrations.RunPython.noop)]
