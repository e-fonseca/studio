"""Os formulários dos descontos: as regras e metas, e a aprovação do grupo."""

import re
from decimal import Decimal

from django import forms

from . import feriados
from .models import RegraDeDesconto

SECOES = [
    ("Desconto que a equipe dá sem chamar o grupo",
     "Acima disto a venda aparece em \"Fora da regra\" até alguém anotar quem aprovou. "
     "Zero quer dizer sem desconto nenhum naquela forma de pagamento.",
     ["desconto_a_vista", "desconto_no_debito", "desconto_no_credito", "parcelas_no_credito",
      "folga", "quem_autoriza"]),
    ("Metas e prêmio",
     "O prêmio é por pessoa que trabalhou no dia. Com a meta de R$ 12.000, o prêmio de "
     "R$ 30 e R$ 10 a cada R$ 1.000: vendeu R$ 13.500, cada um ganha R$ 40.",
     ["meta_sabado", "meta_domingo", "premio", "premio_a_mais", "passo"]),
    ("Feriados",
     "Feriado tem a meta do sábado; feriado no domingo fica com a do domingo.",
     ["outros_feriados"]),
]
LARGOS = {"quem_autoriza", "outros_feriados"}
PORCENTAGENS = ("desconto_a_vista", "desconto_no_debito", "desconto_no_credito")
VALORES = ("folga", "meta_sabado", "meta_domingo", "premio", "premio_a_mais", "passo")

_MILHAR = re.compile(r"^-?\d{1,3}(\.\d{3})+$")


def numero_digitado(bruto):
    """"12.000", "12.000,00", "12000" e "7,5" do jeito que se escreve em português.

    Com vírgula, ela é o centavo e o ponto é milhar. Sem vírgula, ponto seguido de três
    algarismos é milhar ("12.000" é doze mil, e é assim que a meta vai ser digitada);
    qualquer outro ponto é o centavo de quem copiou de outro lugar ("7.5").
    """
    limpo = (bruto or "").strip().replace(" ", "").replace("R$", "").replace("%", "")
    if "," in limpo:
        return limpo.replace(".", "").replace(",", ".")
    if _MILHAR.match(limpo):
        return limpo.replace(".", "")
    return limpo


class NumeroField(forms.DecimalField):
    """Campo de número com vírgula, que mostra 12.000,00 e aceita 12.000 ou 12000."""

    widget = forms.TextInput

    def widget_attrs(self, widget):
        atributos = super().widget_attrs(widget)
        atributos["inputmode"] = "decimal"
        return atributos

    def prepare_value(self, value):
        if isinstance(value, Decimal):
            texto = f"{value:,.2f}"
            return texto.replace(",", "X").replace(".", ",").replace("X", ".")
        return value

    def to_python(self, value):
        if isinstance(value, str):
            value = numero_digitado(value)
        return super().to_python(value)


class RegraDeDescontoForm(forms.ModelForm):
    class Meta:
        model = RegraDeDesconto
        fields = [campo for _, _, campos in SECOES for campo in campos]
        field_classes = {nome: NumeroField for nome in PORCENTAGENS + VALORES}
        widgets = {
            "outros_feriados": forms.Textarea(attrs={
                "rows": 4, "placeholder": "16/02/2027 Carnaval\n20/01 Dia de São Sebastião"}),
        }

    def secoes(self):
        """Os campos agrupados por assunto, como em Dados da empresa."""
        return [{"titulo": titulo, "ajuda": ajuda,
                 "campos": [self[nome] for nome in campos],
                 "largos": [nome for nome in campos if nome in LARGOS]}
                for titulo, ajuda, campos in SECOES]

    def clean(self):
        dados = super().clean()
        for nome in PORCENTAGENS:
            valor = dados.get(nome)
            if valor is not None and not Decimal("0") <= valor <= Decimal("100"):
                self.add_error(nome, "A porcentagem vai de 0 a 100.")
        for nome in ("meta_sabado", "meta_domingo", "passo"):
            valor = dados.get(nome)
            if valor is not None and valor <= 0:
                self.add_error(nome, "Tem que ser maior que zero.")
        for nome in ("premio", "premio_a_mais", "folga"):
            valor = dados.get(nome)
            if valor is not None and valor < 0:
                self.add_error(nome, "Não pode ser negativo.")
        return dados

    def clean_quem_autoriza(self):
        texto = " ".join((self.cleaned_data.get("quem_autoriza") or "").split())
        if not RegraDeDesconto(quem_autoriza=texto).nomes_de_quem_autoriza():
            raise forms.ValidationError("Escreva ao menos um nome.")
        return texto

    def clean_outros_feriados(self):
        texto = (self.cleaned_data.get("outros_feriados") or "").strip()
        _, erradas = feriados.ler_outros(texto)
        if erradas:
            raise forms.ValidationError(
                "Não entendi: " + "; ".join(erradas[:5])
                + ". Escreva uma data por linha, como 20/01 ou 16/02/2027, e o nome depois.")
        return "\n".join(linha.strip() for linha in texto.splitlines() if linha.strip())


class AprovacaoForm(forms.Form):
    """Quem do grupo aprovou a condição diferente, anotado depois da venda."""

    venda = forms.IntegerField(widget=forms.HiddenInput, min_value=1)
    autorizado_por = forms.ChoiceField(label="Quem aprovou no grupo")
    observacao = forms.CharField(label="Observação", max_length=200, required=False,
                                 widget=forms.TextInput(attrs={"placeholder": "Ex.: levou 3 peças"}))

    def __init__(self, *args, nomes=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["autorizado_por"].choices = [(nome, nome) for nome in nomes]
