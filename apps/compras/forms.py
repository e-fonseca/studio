"""Formulário dos dados da empresa, o cabeçalho que vai no pedido ao fornecedor.

Tudo é campo de tela e não valor escrito no código: CNPJ, endereço e telefone mudam
sem avisar, e ninguém vai esperar uma versão nova do sistema por causa de um telefone.
O que o Edson já informou vem preenchido; o que falta a tela cobra, dizendo o que o
fornecedor vai sentir falta no papel.
"""

from django import forms

from apps.compras.models import DadosDaEmpresa


# O formulário em quatro blocos, na ordem em que o pedido é lido pelo fornecedor:
# quem é a loja, para onde vai a nota, para onde vai a carga e por onde se fala com
# ela. Era uma coluna de doze campos iguais, em que ninguém via que "endereço" era o
# da nota e não o da porta (Edson, 19/10/2026: "definir um layout de formulário").
SECOES = [
    ("Quem é a loja",
     "O nome pelo qual o fornecedor conhece a loja vem primeiro; a razão social é a "
     "que ele usa para emitir a nota.",
     ["nome_fantasia", "razao_social", "documento", "inscricao_estadual"]),
    ("Endereço da nota",
     "O endereço que consta no CNPJ. É para ele que o fornecedor fatura.",
     ["endereco", "bairro", "cidade", "estado", "cep"]),
    ("Endereço da entrega",
     "Onde a mercadoria é recebida. Em branco quer dizer que a carga desce no mesmo "
     "endereço da nota, e aí o pedido imprime uma linha só.",
     ["endereco_entrega", "bairro_entrega", "cidade_entrega", "estado_entrega",
      "cep_entrega"]),
    ("Contato e recado",
     "Por onde o fornecedor responde, e o que sai escrito no pé de todo pedido.",
     ["telefone", "email", "observacao"]),
]


# Campo que ocupa a largura inteira do bloco: ou é texto comprido (endereço, e-mail,
# recado), ou é o campo que dá nome ao bloco. O resto cabe em meia largura, e assim a
# tela deixa de ser uma coluna de doze caixas iguais num monitor de 1600 px.
LARGOS = frozenset({"razao_social", "endereco", "endereco_entrega", "email", "observacao"})

# A linha do bloco já diz isto. Repetir embaixo do campo é exatamente a informação a
# mais de que ele reclamou em 19/10/2026 ("deixando os gestores confusos").
SEM_AJUDA_REPETIDA = ("nome_fantasia", "razao_social", "endereco", "endereco_entrega")


class DadosDaEmpresaForm(forms.ModelForm):
    class Meta:
        model = DadosDaEmpresa
        fields = [campo for _, _, campos in SECOES for campo in campos]
        widgets = {
            "documento": forms.TextInput(attrs={"placeholder": "00.000.000/0001-00",
                                                "inputmode": "numeric"}),
            "cep": forms.TextInput(attrs={"placeholder": "00000-000", "inputmode": "numeric"}),
            "cep_entrega": forms.TextInput(attrs={"placeholder": "00000-000",
                                                  "inputmode": "numeric"}),
            "estado": forms.TextInput(attrs={"placeholder": "SP", "maxlength": 2,
                                             "style": "text-transform:uppercase"}),
            "estado_entrega": forms.TextInput(attrs={"placeholder": "SP", "maxlength": 2,
                                                     "style": "text-transform:uppercase"}),
            "telefone": forms.TextInput(attrs={"placeholder": "(00) 00000-0000",
                                               "inputmode": "tel"}),
            "observacao": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": "Ex.: receber de segunda a sexta, das 9h às 17h.",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nome in SEM_AJUDA_REPETIDA:
            self.fields[nome].help_text = ""

    def secoes(self):
        """Os campos agrupados por assunto, para a tela desenhar um bloco por assunto.

        Sai daqui e não do template porque é a mesma lista que define `Meta.fields`:
        campo novo entra numa seção e aparece na tela, em vez de existir no modelo e
        nunca ser desenhado, que é como um campo some sem ninguém notar.
        """
        return [{"titulo": titulo, "ajuda": ajuda,
                 "campos": [self[nome] for nome in campos],
                 "largos": [nome for nome in campos if nome in LARGOS]}
                for titulo, ajuda, campos in SECOES]

    def _caixa_alta(self, campo):
        """UF em caixa alta, sempre: "sp" e "SP" são o mesmo estado."""
        return (self.cleaned_data.get(campo) or "").strip().upper()

    def clean_estado(self):
        return self._caixa_alta("estado")

    def clean_estado_entrega(self):
        return self._caixa_alta("estado_entrega")
