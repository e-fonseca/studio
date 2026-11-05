"""O repositório que o Edson indicou já vem preenchido na tela.

Ele mandou em 14/10/2026: "fazer conexão com o diretório sistema, destinado para este
projeto no github". Só o token continua sendo dele para colar — e tem que ser, porque
token nenhum pode vir escrito no programa.

A linha que já existe só é preenchida se estiver VAZIA: endereço digitado por alguém
vale mais que o nosso padrão.
"""

from django.db import migrations, models

PADRAO = "e-fonseca/studio"


def preencher(apps, schema_editor):
    Configuracao = apps.get_model("backup", "ConfiguracaoDeBackup")
    Configuracao.objects.filter(repositorio="").update(repositorio=PADRAO)


def desfazer(apps, schema_editor):
    Configuracao = apps.get_model("backup", "ConfiguracaoDeBackup")
    Configuracao.objects.filter(repositorio=PADRAO).update(repositorio="")


class Migration(migrations.Migration):

    dependencies = [("backup", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="configuracaodebackup",
            name="repositorio",
            field=models.CharField(
                blank=True, default=PADRAO,
                help_text="No formato dono/repositório, ou cole o endereço: "
                          "https://github.com/dono/repositorio",
                max_length=200, verbose_name="repositório no GitHub"),
        ),
        migrations.RunPython(preencher, desfazer),
    ]
