"""Formulários dos Ajustes e do lançamento entre empresas."""

from django import forms

from .models import (Avulso, Cartao, CustoFixo, Divida, MovimentoEntreEmpresas,
                     Parametros)

DATA = forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})
DINHEIRO = forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal"})
PERCENTUAL = forms.NumberInput(attrs={"step": "0.01", "min": "0", "max": "100", "inputmode": "decimal"})


class ParametrosForm(forms.ModelForm):
    class Meta:
        model = Parametros
        fields = ["saldo_inicial", "saldo_em", "margem_minima", "atraso_dias", "taxa_antecipacao",
                  "pct_cartao", "pct_primeira", "parcelas_padrao", "cartao_padrao", "markup_alvo"]
        widgets = {
            "saldo_inicial": DINHEIRO, "saldo_em": DATA,
            "margem_minima": PERCENTUAL, "taxa_antecipacao": PERCENTUAL, "pct_cartao": PERCENTUAL,
            "pct_primeira": PERCENTUAL,
            "markup_alvo": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cartao_padrao"].queryset = Cartao.objects.filter(ativo=True)
        self.fields["cartao_padrao"].empty_label = "Nenhum"


def _conjunto(modelo, campos, widgets=None):
    # Sem "apagar": item que não vale mais é desligado (ativo) ou marcado como pago.
    return forms.modelformset_factory(modelo, fields=campos, extra=1, can_delete=False,
                                      widgets=widgets or {})


CartoesFormSet = _conjunto(Cartao, ["nome", "vencimento", "fecha_dias_antes", "observacao", "ativo"])
FixosFormSet = _conjunto(CustoFixo, ["nome", "tipo", "valor", "dia", "ativo"],
                         {"valor": DINHEIRO})
DividasFormSet = _conjunto(Divida, ["nome", "saldo", "taxa_mensal", "dia", "ativa"],
                           {"saldo": DINHEIRO,
                            "taxa_mensal": forms.NumberInput(attrs={"step": "0.001", "min": "0"})})
AvulsosFormSet = _conjunto(Avulso, ["nome", "valor", "data", "pago"],
                           {"valor": DINHEIRO, "data": DATA})


class MovimentoForm(forms.ModelForm):
    class Meta:
        model = MovimentoEntreEmpresas
        fields = ["data", "tipo", "sentido", "empresa", "valor", "descricao"]
        widgets = {"data": DATA, "valor": DINHEIRO}

    def clean(self):
        dados = super().clean()
        tipo = dados.get("tipo")
        if tipo == MovimentoEntreEmpresas.Tipo.PROLABORE:
            if not dados.get("empresa"):
                self.add_error("empresa", "Diga qual empresa pagou o pró-labore.")
            dados["sentido"] = ""
        elif tipo:
            if not dados.get("sentido"):
                self.add_error("sentido", "Diga quem deve a quem.")
            dados["empresa"] = ""
        return dados
