"""Formulários do funil de leads."""

from django import forms
from django.contrib.auth import get_user_model

from .models import Contato, Lead

DATA = forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})


class LeadForm(forms.ModelForm):
    LARGOS = ("interesse",)

    class Meta:
        model = Lead
        fields = ["nome", "telefone", "email", "origem", "interesse", "valor_estimado",
                  "responsavel", "proximo_contato"]
        widgets = {
            "interesse": forms.Textarea(attrs={"rows": 3}),
            "valor_estimado": forms.NumberInput(attrs={"step": "0.01", "min": "0", "inputmode": "decimal"}),
            "proximo_contato": DATA,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["responsavel"].queryset = get_user_model().objects.filter(
            is_active=True).order_by("first_name", "username")
        self.fields["responsavel"].label_from_instance = (
            lambda u: u.get_full_name() or u.get_username())
        self.fields["responsavel"].empty_label = "Ninguém ainda"

    def clean(self):
        dados = super().clean()
        if not dados.get("telefone") and not dados.get("email"):
            raise forms.ValidationError(
                "Anote o telefone ou o e-mail: lead sem como falar com ele não vira cliente.")
        return dados


class ContatoForm(forms.Form):
    """Registrar uma conversa e dizer o que vem depois dela."""

    canal = forms.ChoiceField(choices=Contato.Canal.choices, initial=Contato.Canal.WHATSAPP)
    resumo = forms.CharField(
        label="O que foi falado", widget=forms.Textarea(attrs={"rows": 3}), max_length=4000)
    etapa = forms.ChoiceField(label="Etapa depois desta conversa", choices=Lead.Etapa.choices)
    proximo_contato = forms.DateField(label="Próximo contato", required=False, widget=DATA)
    motivo_perda = forms.CharField(label="Por que perdemos", required=False, max_length=200,
                                   help_text="Só quando a etapa for Perdido.")

    def clean(self):
        dados = super().clean()
        etapa = dados.get("etapa")
        if etapa in Lead.ABERTAS and not dados.get("proximo_contato"):
            # A regra do módulo inteiro: lead em aberto sem data é lead esquecido.
            self.add_error("proximo_contato",
                           "Marque quando falar de novo. Lead em aberto sem data é lead esquecido.")
        if etapa == Lead.Etapa.PERDIDO and not (dados.get("motivo_perda") or "").strip():
            self.add_error("motivo_perda", "Diga por que perdemos: é isso que ensina a vender melhor.")
        return dados
