"""Conserta o nome do fornecedor gravado com a tabela de caracteres errada.

Até a 1.11.0 a importação lia tudo como cp1252, então nome vindo em UTF-8 entrava
torto ("SÃ£o" no lugar de "São"). A importação seguinte traz o nome certo, mas a ficha
do fornecedor (prazo de entrega, estrelas, relação) é digitada pela gerência e fica
guardada pelo nome: sem esta migração, a ficha ficaria presa ao nome torto e o prazo e
as estrelas sumiriam da tela depois da primeira importação corrigida.
"""

from django.db import migrations

from apps.core.texto import consertar


def arrumar(apps, schema_editor):
    Fornecedor = apps.get_model("fornecedores", "Fornecedor")
    existentes = set(Fornecedor.objects.values_list("nome", flat=True))
    for fornecedor in Fornecedor.objects.all():
        nome = consertar(fornecedor.nome)
        observacao = consertar(fornecedor.observacao)
        if nome == fornecedor.nome and observacao == fornecedor.observacao:
            continue
        # O nome é único: se a ficha certa já existe, esta aqui é duplicata e sai.
        if nome != fornecedor.nome and nome in existentes:
            fornecedor.delete()
            continue
        existentes.discard(fornecedor.nome)
        existentes.add(nome)
        fornecedor.nome = nome
        fornecedor.observacao = observacao
        fornecedor.save(update_fields=["nome", "observacao"])


class Migration(migrations.Migration):
    dependencies = [("fornecedores", "0002_fornecedor_relacao_fornecedor_reputacao")]
    # Sem volta: o texto torto não tem por que ser recriado.
    operations = [migrations.RunPython(arrumar, migrations.RunPython.noop)]
