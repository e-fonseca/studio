"""Formulários de pedidos (projetos) e oficinas."""

from django import forms
from django.contrib.auth import get_user_model

from .models import Oficina, Projeto

DATA = forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})
DINHEIRO = forms.NumberInput(attrs={"step": "0.01", "min": "0", "inputmode": "decimal"})

# Os blocos do formulário do pedido, na ordem do card no Trello. É esta lista que define
# os campos (Meta.fields): campo novo entra num bloco e aparece na tela.
SECOES = (
    ("O pedido", "O número do card, o cliente e quem vendeu.",
     ["numero", "titulo", "cliente_nome", "cliente_telefone", "cliente_email", "vendedor",
      "arquiteto", "responsavel", "data_venda", "aprovado_em", "descricao"]),
    ("Venda e cliente", "Cartão do cliente entra antecipado: só o saldo em Pix entra na "
                        "previsão de recebimento.",
     ["valor_venda", "recebido", "venda_cartao", "saldo_forma", "saldo_pix"]),
    ("Oficina", "Pela regra da oficina o sistema calcula as parcelas e em que fatura de "
                "cartão cada uma cai.",
     ["oficina", "regime", "custo_oficina", "repasse", "primeira_percentual", "incluir"]),
    ("Pagamentos à oficina", "Preencha quando pagar. Sem a data da 1ª parcela, ela entra "
                             "prevista para hoje e o card aparece como incompleto.",
     ["pg1_data", "pg1_cartao", "pg1_parcelas", "pg2_data"]),
    ("Entrega e outros custos", "O prazo do card nem sempre é a entrega real: confirme com "
                                "a produção antes de contar com o Pix.",
     ["prazo_entrega", "entregue_em", "frete", "embalagem", "rt", "projeto_desenho",
      "outros_custos", "observacao"]),
)
LARGOS = frozenset({"titulo", "descricao", "observacao"})


def _pessoas():
    return get_user_model().objects.filter(is_active=True).order_by("first_name", "username")


class ProjetoForm(forms.ModelForm):
    LARGOS = LARGOS

    class Meta:
        model = Projeto
        fields = [campo for _, _, campos in SECOES for campo in campos]
        widgets = {
            "descricao": forms.Textarea(attrs={"rows": 3}),
            "observacao": forms.Textarea(attrs={"rows": 3}),
            **{nome: DINHEIRO for nome in (
                "valor_venda", "custo_oficina", "outros_custos", "recebido", "venda_cartao",
                "saldo_pix", "frete", "embalagem", "rt", "projeto_desenho")},
            "primeira_percentual": forms.NumberInput(attrs={"step": "0.01", "min": "0", "max": "100"}),
            **{nome: DATA for nome in ("aprovado_em", "prazo_entrega", "entregue_em",
                                       "data_venda", "repasse", "pg1_data", "pg2_data")},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.planejamento.models import Cartao

        atual = self.instance.oficina_id if self.instance and self.instance.pk else None
        # Oficina desativada some da escolha, menos a que já está no pedido: senão salvar
        # o pedido de novo apagaria quem o fez.
        self.fields["oficina"].queryset = Oficina.objects.filter(
            ativa=True) | Oficina.objects.filter(pk=atual)
        self.fields["oficina"].empty_label = "Ainda não definida"
        cartao = self.instance.pg1_cartao_id if self.instance and self.instance.pk else None
        self.fields["pg1_cartao"].queryset = Cartao.objects.filter(
            ativo=True) | Cartao.objects.filter(pk=cartao)
        self.fields["pg1_cartao"].empty_label = "O cartão padrão"
        self.fields["responsavel"].queryset = _pessoas()
        self.fields["responsavel"].label_from_instance = (
            lambda u: u.get_full_name() or u.get_username())
        self.fields["responsavel"].empty_label = "Ninguém ainda"
        self.fields["titulo"].help_text = "Ex.: Mesa de jantar 2,20 m em ferro e madeira."

    def clean(self):
        dados = super().clean()
        if not dados.get("titulo") and not dados.get("numero") and not self.errors.get("titulo"):
            self.add_error("titulo", "Diga o que é o móvel ou o número do card.")
        return dados

    def secoes(self):
        return [{"titulo": titulo, "ajuda": ajuda,
                 "campos": [self[nome] for nome in campos],
                 "largos": [nome for nome in campos if nome in LARGOS]}
                for titulo, ajuda, campos in SECOES]


class OficinaForm(forms.ModelForm):
    LARGOS = ("especialidade", "observacao")

    class Meta:
        model = Oficina
        fields = ["nome", "contato", "telefone", "cidade", "especialidade", "pagamento",
                  "parcelas_mensais", "dia_pagamento", "dia_corte", "observacao", "ativa"]
        widgets = {"observacao": forms.Textarea(attrs={"rows": 3})}

    def clean(self):
        dados = super().clean()
        if dados.get("pagamento") == Oficina.Pagamento.MENSAL and not dados.get("dia_pagamento"):
            self.add_error("dia_pagamento", "Diga o dia do mês em que esta oficina recebe.")
        return dados
