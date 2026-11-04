"""Formulário da tela de alertas.

A senha é o único campo que não volta para a tela. Mostrar de volta a senha gravada
seria entregá-la a quem abrir a página num computador do balcão; e o campo em branco
num formulário de edição costuma ser lido como "apagar", então aqui ele significa
explicitamente "deixar a que já está", e a tela escreve isso ao lado.
"""

from django import forms

from apps.alertas.models import ConfiguracaoDeEmail, ConfiguracaoDeTelegram


class ConfiguracaoForm(forms.ModelForm):
    senha = forms.CharField(
        label="Senha da caixa de e-mail",
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        help_text="A senha da caixa que envia, a mesma de quem entra no webmail dela.",
    )

    # A senha é declarada fora do Meta e iria para o fim do formulário, longe do
    # usuário a que ela pertence. Quem preenche lê os dois juntos.
    field_order = ["ativo", "servidor", "porta", "usar_tls", "usuario", "senha",
                   "remetente", "destinatarios", "hora_diaria", "dia_semanal", "hora_semanal"]

    class Meta:
        model = ConfiguracaoDeEmail
        fields = [
            "ativo", "servidor", "porta", "usar_tls", "usuario", "remetente",
            "destinatarios", "hora_diaria", "dia_semanal", "hora_semanal",
        ]
        widgets = {
            "destinatarios": forms.Textarea(attrs={"rows": 3, "placeholder": "cabanadojacaranda@gmail.com"}),
            "hora_diaria": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "hora_semanal": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "usuario": forms.EmailInput(attrs={"autocomplete": "off"}),
        }

    def clean_destinatarios(self):
        """Um e-mail por linha, conferido antes de gravar.

        Endereço errado não dá erro na hora do envio: o servidor aceita e devolve a
        recusa depois, fora da vista. Melhor recusar aqui, onde a pessoa ainda está
        olhando o campo.
        """
        bruto = self.cleaned_data.get("destinatarios") or ""
        validar = forms.EmailField()
        limpos, ruins = [], []
        for linha in bruto.splitlines():
            endereco = linha.strip()
            if not endereco:
                continue
            try:
                limpos.append(validar.clean(endereco))
            except forms.ValidationError:
                ruins.append(endereco)
        if ruins:
            raise forms.ValidationError(
                "Não parece e-mail: " + ", ".join(ruins) + ". Escreva um endereço por linha."
            )
        return "\n".join(limpos)

    def clean(self):
        """Ligar o envio sem o que ele precisa só adiaria o erro para a madrugada."""
        dados = super().clean()
        if not dados.get("ativo"):
            return dados
        senha_nova = (dados.get("senha") or "").strip()
        faltas = []
        if not dados.get("servidor"):
            faltas.append("o servidor de saída")
        if not dados.get("usuario"):
            faltas.append("o e-mail que envia")
        if not senha_nova and not self.instance.tem_senha:
            faltas.append("a senha da caixa de e-mail")
        if not (dados.get("destinatarios") or "").strip():
            faltas.append("para quem mandar")
        if faltas:
            raise forms.ValidationError(
                "Para ligar o envio falta preencher: " + ", ".join(faltas) + "."
            )
        return dados

    def save(self, commit=True):
        configuracao = super().save(commit=False)
        senha_nova = (self.cleaned_data.get("senha") or "").strip()
        if senha_nova:
            configuracao.senha = senha_nova
        if commit:
            configuracao.save()
        return configuracao


class TelegramForm(forms.ModelForm):
    """O token e a conversa do Telegram. Mesmo cuidado da senha: o token não volta.

    Quem tem o token manda mensagem no nome da loja, então ele é tratado como senha:
    gravado cifrado, nunca mostrado de volta, e campo em branco significa "deixa o que
    já está", com a tela escrevendo isso ao lado.
    """

    token = forms.CharField(
        label="Token do robô",
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        help_text="O código que o BotFather do Telegram dá quando o robô é criado.",
    )

    field_order = ["ativo", "token", "chat_id"]

    class Meta:
        model = ConfiguracaoDeTelegram
        fields = ["ativo", "chat_id"]
        widgets = {
            "chat_id": forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "off"}),
        }

    def clean_chat_id(self):
        """O chat é um número (negativo em grupo). Texto aqui viraria erro na madrugada."""
        bruto = (self.cleaned_data.get("chat_id") or "").strip()
        if not bruto:
            return ""
        if not bruto.lstrip("-").isdigit():
            raise forms.ValidationError(
                "A conversa é um número, como 123456789 (em grupo começa com -). Use o "
                "botão \"Descobrir a conversa\" para preencher sem errar."
            )
        return bruto

    def clean(self):
        dados = super().clean()
        if not dados.get("ativo"):
            return dados
        faltas = []
        if not (dados.get("token") or "").strip() and not self.instance.tem_token:
            faltas.append("o token do robô")
        if not (dados.get("chat_id") or "").strip():
            faltas.append("a conversa para onde mandar")
        if faltas:
            raise forms.ValidationError(
                "Para ligar o aviso no Telegram falta preencher: " + ", ".join(faltas) + "."
            )
        return dados

    def save(self, commit=True):
        configuracao = super().save(commit=False)
        token_novo = (self.cleaned_data.get("token") or "").strip()
        if token_novo:
            configuracao.token = token_novo
        if commit:
            configuracao.save()
        return configuracao


class MetasNoTelegramForm(forms.ModelForm):
    """O grupo das metas (1.47.0): o interruptor e o número do grupo.

    O robô é o mesmo dos relatórios, então o token não aparece aqui: ele se grava no
    formulário de cima. O número do grupo se preenche pelo botão "Usar para as metas" da
    lista de conversas; o campo existe para quem já sabe o número, e confere o formato.
    """

    field_order = ["metas_ativo", "metas_chat_id"]

    class Meta:
        model = ConfiguracaoDeTelegram
        fields = ["metas_ativo", "metas_chat_id"]
        widgets = {
            "metas_chat_id": forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "off"}),
        }

    def clean_metas_chat_id(self):
        bruto = (self.cleaned_data.get("metas_chat_id") or "").strip()
        if bruto and not bruto.lstrip("-").isdigit():
            raise forms.ValidationError(
                "O grupo é um número que começa com - (como -1001234567890). Use o botão "
                "\"Usar para as metas\" da lista de conversas para preencher sem errar."
            )
        return bruto

    def clean(self):
        dados = super().clean()
        if not dados.get("metas_ativo"):
            return dados
        faltas = []
        if not self.instance.tem_token:
            faltas.append("o token do robô (no Aviso no Telegram, acima)")
        if not (dados.get("metas_chat_id") or "").strip():
            faltas.append("o grupo das metas")
        if faltas:
            raise forms.ValidationError(
                "Para ligar o aviso das metas falta preencher: " + ", ".join(faltas) + "."
            )
        return dados

    def save(self, commit=True):
        configuracao = super().save(commit=False)
        # Número digitado à mão é outro grupo: o nome que a lista tinha dado já não vale.
        if "metas_chat_id" in self.changed_data:
            configuracao.metas_chat_nome = ""
        if commit:
            configuracao.save()
        return configuracao
