"""Formulários de projetos, oficinas e parcelas."""

from django import forms
from django.contrib.auth import get_user_model

from .models import Oficina, Parcela, Projeto

DATA = forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})
DINHEIRO = forms.NumberInput(attrs={"step": "0.01", "min": "0", "inputmode": "decimal"})


def _pessoas():
    return get_user_model().objects.filter(is_active=True).order_by("first_name", "username")


class ProjetoForm(forms.ModelForm):
    # Campos que leem melhor na largura inteira (templates/_campos.html).
    LARGOS = ("titulo", "descricao")

    class Meta:
        model = Projeto
        fields = [
            "titulo", "cliente_nome", "cliente_telefone", "cliente_email", "descricao",
            "oficina", "responsavel", "valor_venda", "custo_oficina", "outros_custos",
            "aprovado_em", "prazo_entrega",
        ]
        widgets = {
            "descricao": forms.Textarea(attrs={"rows": 4}),
            "valor_venda": DINHEIRO, "custo_oficina": DINHEIRO, "outros_custos": DINHEIRO,
            "aprovado_em": DATA, "prazo_entrega": DATA,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        atual = self.instance.oficina_id if self.instance and self.instance.pk else None
        # Oficina desativada some da escolha, menos a que já está no projeto: senão salvar
        # o projeto de novo apagaria quem o fez.
        self.fields["oficina"].queryset = Oficina.objects.filter(
            ativa=True) | Oficina.objects.filter(pk=atual)
        self.fields["oficina"].empty_label = "Ainda não definida"
        self.fields["responsavel"].queryset = _pessoas()
        self.fields["responsavel"].label_from_instance = (
            lambda u: u.get_full_name() or u.get_username())
        self.fields["responsavel"].empty_label = "Ninguém ainda"


class OficinaForm(forms.ModelForm):
    LARGOS = ("especialidade", "observacao")

    class Meta:
        model = Oficina
        fields = ["nome", "contato", "telefone", "cidade", "especialidade", "observacao", "ativa"]
        widgets = {"observacao": forms.Textarea(attrs={"rows": 3})}


class ParcelaForm(forms.ModelForm):
    class Meta:
        model = Parcela
        fields = ["tipo", "descricao", "valor", "vencimento", "pago_em", "forma", "lancada_no_set"]
        widgets = {
            "valor": forms.NumberInput(attrs={"step": "0.01", "min": "0.01", "inputmode": "decimal"}),
            "vencimento": DATA, "pago_em": DATA,
        }
