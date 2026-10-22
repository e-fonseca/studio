"""Formulário do lugar da loja, que é o que a busca automática precisa saber."""

from django import forms

from apps.tempo.models import ConfiguracaoDoTempo


class ConfiguracaoForm(forms.ModelForm):
    class Meta:
        model = ConfiguracaoDoTempo
        fields = ["ativo", "cidade", "latitude", "longitude"]
        widgets = {
            "cidade": forms.TextInput(attrs={"placeholder": "Rio de Janeiro"}),
            "latitude": forms.TextInput(attrs={"placeholder": "-22.906847", "inputmode": "decimal"}),
            "longitude": forms.TextInput(attrs={"placeholder": "-43.172896", "inputmode": "decimal"}),
        }

    def clean(self):
        """Ligar a busca sem saber onde é a loja só adiaria o erro para a madrugada.

        Desde a 1.29.0 o nome da cidade basta: o sistema descobre a latitude e a
        longitude a partir dele. Então o que o formulário cobra é a CIDADE, e não dois
        números de seis casas decimais — era essa a exigência que mantinha a busca
        desligada, porque ninguém ia ao Google Maps buscá-los.
        """
        dados = super().clean()
        self._esquecer_o_lugar_antigo(dados)
        tem_coordenadas = (dados.get("latitude") is not None
                           and dados.get("longitude") is not None)
        if dados.get("ativo") and not (dados.get("cidade") or "").strip() and not tem_coordenadas:
            raise forms.ValidationError(
                "Para buscar o tempo sozinho o sistema precisa saber onde fica a loja. "
                "Escreva a cidade: ele descobre as coordenadas a partir dela."
            )
        return dados

    def _esquecer_o_lugar_antigo(self, dados):
        """Cidade nova limpa as coordenadas antigas, para o sistema descobri-las de novo.

        Sem isto, trocar a cidade deixaria no cadastro as coordenadas da cidade anterior
        e o sistema seguiria buscando o tempo do lugar errado, calado. Quem digitou
        coordenadas nesta mesma gravação continua com as suas: `changed_data` separa o
        campo que a pessoa mexeu do que só veio preenchido na tela.
        """
        cidade = (dados.get("cidade") or "").strip()
        anterior = (self.instance.cidade or "").strip()
        if not cidade or cidade.casefold() == anterior.casefold():
            return
        if "latitude" in self.changed_data or "longitude" in self.changed_data:
            return
        dados["latitude"] = None
        dados["longitude"] = None
        self.instance.lugar_encontrado = ""
