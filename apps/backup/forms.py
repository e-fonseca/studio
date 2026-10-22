"""O formulário do backup. O token entra e não volta: a tela nunca o mostra."""

from django import forms

from .models import ConfiguracaoDeBackup


class ConfiguracaoDeBackupForm(forms.ModelForm):
    token = forms.CharField(
        label="Token de acesso do GitHub", required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        help_text="Cole aqui o token. Depois de gravado ele não aparece mais nesta tela; "
                  "deixar em branco mantém o que já está guardado.",
    )
    apagar_token = forms.BooleanField(label="Apagar o token guardado", required=False)

    class Meta:
        model = ConfiguracaoDeBackup
        fields = ["repositorio", "ramo", "ativo"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.tem_token:
            # Não há o que apagar antes de haver token guardado, e campo que não faz
            # nada na primeira vez que se abre a tela é só mais uma coisa para entender.
            self.fields.pop("apagar_token")
            # E o automático já nasce marcado. Quem cola um token de backup está
            # ligando o backup; deixar a marca para um segundo passo só produzia a
            # situação em que o token está lá, tudo está certo, e nada sobe.
            self.initial["ativo"] = True
        # O token vem ANTES da marca do automático: a marca fala do que acontece depois
        # que o token existe, e lida antes dele é uma promessa sem lastro.
        self.order_fields(["repositorio", "ramo", "token", "ativo", "apagar_token"])

    def clean(self):
        dados = super().clean()
        bruto = (dados.get("repositorio") or "").strip()
        if bruto:
            provisorio = ConfiguracaoDeBackup(repositorio=bruto)
            dono, repositorio = provisorio.dono_e_repositorio
            if not (dono and repositorio):
                self.add_error("repositorio", "Escreva no formato dono/repositório, ou cole o "
                                              "endereço do repositório no GitHub.")
        if dados.get("ativo") and not (bruto and (dados.get("token") or self.instance.tem_token)):
            self.add_error("ativo", "Para ligar o envio automático, preencha o repositório e o token.")
        return dados

    def save(self, commit=True, usuario=None):
        configuracao = super().save(commit=False)
        if self.cleaned_data.get("apagar_token"):
            configuracao.token_guardado = ""
        elif self.cleaned_data.get("token"):
            configuracao.token = self.cleaned_data["token"].strip()
        if usuario is not None and usuario.is_authenticated:
            configuracao.atualizado_por = usuario
        if commit:
            configuracao.save()
        return configuracao
