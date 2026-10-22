"""A busca do tempo passa a se configurar sozinha, e a previsão ganha lugar próprio.

Pedido do Edson em 14/10/2026: "configurar api de previsão do tempo automática,
armazenar informações diárias e usar como indicador".

Três mudanças:

- `TempoDoDia.previsao` separa o dia que ainda não fechou do dia medido. A conta de
  quanto a chuva custa continua saindo só de dia fechado.
- `ConfiguracaoDoTempo.lugar_encontrado` guarda o que o serviço de geografia entendeu
  pelo nome da cidade ("Sorocaba, São Paulo, Brasil"), para alguém poder ver que não é a
  cidade homônima de outro estado.
- A busca automática nasce LIGADA, e a linha que já existe no servidor é ligada aqui. O
  valor antigo era desligado e ninguém nunca ligou, porque ligar exigia antes dois
  números de seis casas decimais pegos no Google Maps. Agora basta o nome da cidade, e
  enquanto ela não for escrita a tarefa da madrugada não faz nada e a tela diz o que
  falta — nada é buscado e nada quebra.
"""

from django.db import migrations, models


def ligar_a_busca(apps, schema_editor):
    """Liga a busca na configuração que já existe; a nova já nasce ligada pelo default."""
    Configuracao = apps.get_model("tempo", "ConfiguracaoDoTempo")
    Configuracao.objects.filter(ativo=False).update(ativo=True)


def desligar_a_busca(apps, schema_editor):
    Configuracao = apps.get_model("tempo", "ConfiguracaoDoTempo")
    Configuracao.objects.update(ativo=False)


class Migration(migrations.Migration):

    dependencies = [
        ("tempo", "0001_tempo_do_dia"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracaodotempo",
            name="lugar_encontrado",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="tempododia",
            name="previsao",
            field=models.BooleanField(
                default=False, verbose_name="é previsão, o dia ainda não fechou"
            ),
        ),
        migrations.AlterField(
            model_name="configuracaodotempo",
            name="ativo",
            field=models.BooleanField(
                default=True,
                help_text="Desligado, o tempo só entra pelo que alguém escrever na tela.",
                verbose_name="buscar o tempo sozinho, todo dia",
            ),
        ),
        migrations.AlterField(
            model_name="configuracaodotempo",
            name="cidade",
            field=models.CharField(
                blank=True,
                help_text="Só o nome da cidade. O sistema descobre as coordenadas a partir dela.",
                max_length=120,
                verbose_name="cidade da loja",
            ),
        ),
        migrations.RunPython(ligar_a_busca, desligar_a_busca),
    ]
