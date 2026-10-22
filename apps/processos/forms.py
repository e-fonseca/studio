from django import forms
from django.contrib.auth import get_user_model

from .models import Afirmacao, ExecucaoTeste, Processo, VersaoProcesso


class SelecaoUsuario(forms.ModelChoiceField):
    def label_from_instance(self, usuario):
        return usuario.get_full_name() or usuario.get_username()


def _usuarios_ativos():
    return get_user_model().objects.filter(is_active=True).order_by("first_name", "username")


class ProcessoForm(forms.ModelForm):
    titular = SelecaoUsuario(queryset=_usuarios_ativos(), required=False, label="Responsável titular")
    substituto = SelecaoUsuario(queryset=_usuarios_ativos(), required=False)

    class Meta:
        model = Processo
        fields = ["titulo", "area", "criticidade", "fonte_conhecimento", "titular", "substituto", "prazo_coleta"]
        widgets = {"prazo_coleta": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["titular"].queryset = _usuarios_ativos()
        self.fields["substituto"].queryset = _usuarios_ativos()

    def clean(self):
        dados = super().clean()
        if dados.get("titular") and dados.get("titular") == dados.get("substituto"):
            self.add_error("substituto", "O substituto precisa ser uma pessoa diferente do titular.")
        return dados


class VersaoForm(forms.ModelForm):
    versao_base = forms.IntegerField(widget=forms.HiddenInput, min_value=0)

    class Meta:
        model = VersaoProcesso
        fields = VersaoProcesso.CAMPOS_CONTEUDO + ["resumo_mudanca"]
        widgets = {
            campo: forms.Textarea(attrs={"rows": 3})
            for campo in VersaoProcesso.CAMPOS_CONTEUDO
            if campo not in ("frequencia", "tela_origem")
        }
        widgets["passos"] = forms.Textarea(attrs={"rows": 10})


class TesteForm(forms.ModelForm):
    class Meta:
        model = ExecucaoTeste
        fields = ["resultado", "usou_somente_documentacao", "dificuldades"]
        widgets = {"resultado": forms.RadioSelect, "dificuldades": forms.Textarea(attrs={"rows": 4})}


class AfirmacaoForm(forms.ModelForm):
    class Meta:
        model = Afirmacao
        fields = ["tipo", "texto", "fonte"]
        widgets = {"texto": forms.Textarea(attrs={"rows": 3})}


class AnexoForm(forms.Form):
    arquivo = forms.FileField()
    descricao = forms.CharField(label="Descrição", max_length=200)
    contem_imagem_de_pessoa = forms.BooleanField(
        label="A imagem ou gravação mostra pessoas ou dados pessoais", required=False
    )
    autorizacao_registrada = forms.BooleanField(label="A autorização de uso foi registrada", required=False)


class MotivoForm(forms.Form):
    motivo = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), max_length=1000)
