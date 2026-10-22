"""A cidade da loja, que ele informou junto com os endereços em 19/10/2026.

Era o único passo que faltava para a previsão do tempo começar a funcionar sozinha, e
estava parado desde a 1.29.0 esperando alguém digitar "Embu das Artes" na tela. Com os
endereços fiscal e físico na mesma mensagem, a cidade deixou de ser pergunta: os dois
ficam em Embu das Artes.

As coordenadas continuam de fora de propósito. Quem as descobre é o próprio sistema, a
partir do nome, e o que ele encontrar fica escrito em `lugar_encontrado` para alguém
conferir que não é a cidade homônima de outro estado.
"""

from django.db import migrations

CIDADE = "Embu das Artes"


def escrever_a_cidade(apps, schema_editor):
    """Só escreve se ninguém tiver escrito antes: o que a loja digitou ganha sempre."""
    Configuracao = apps.get_model("tempo", "ConfiguracaoDoTempo")
    registro = Configuracao.objects.filter(pk=1).first()
    if registro is None:
        Configuracao.objects.create(pk=1, cidade=CIDADE)
        return
    if not (registro.cidade or "").strip():
        registro.cidade = CIDADE
        registro.save(update_fields=["cidade"])


def desfazer(apps, schema_editor):
    """Nada a desfazer: apagar a cidade só devolveria o sistema ao estado parado."""


class Migration(migrations.Migration):

    dependencies = [("tempo", "0002_previsao_e_cidade")]

    operations = [migrations.RunPython(escrever_a_cidade, desfazer)]
