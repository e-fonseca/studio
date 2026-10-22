"""Gerar de novo a folha de um pedido JÁ GUARDADO.

Pedido do Edson em 20/10/2026: *"Pedido, nessa tela gerar pedido de compra de
mercadorias"*. Até aqui a folha só nascia na lista de compra: quem abria um pedido
guardado conseguia baixar o PDF anexado, mas não gerar um novo — e depois de editar o
pedido o anexo antigo passa a mostrar quantidade que já não é a do pedido.

A folha é a MESMA de `apps/compras/pedido.py`, não uma segunda versão dela: o papel que
o fornecedor lê não pode depender de por qual tela foi impresso. Aquele módulo monta a
folha a partir de um "bloco" da lista de compra, e nunca soube o que é um `Pedido` — ele
só conta com `.nome`, `.itens`, `.prazo_dias`, `.prazo_assumido` e `.ajustados`. Este
arquivo veste o pedido guardado com essa roupa, e é todo o custo de reaproveitar a folha.
"""

from dataclasses import dataclass
from decimal import Decimal

from apps.compras import pedido as folha_do_pedido

ZERO = Decimal("0")


@dataclass
class _Linha:
    """Uma linha do pedido guardado com os nomes que a folha espera."""

    codigo: str
    descricao: str
    grupo: str
    quantidade: Decimal
    custo: object
    valor_do_pedido: Decimal
    foi_ajustada: bool


@dataclass
class _Bloco:
    """O pedido guardado vestido de bloco da lista de compra."""

    nome: str
    itens: list
    prazo_dias: object
    # O prazo do pedido guardado é o que foi combinado no dia, então nunca é "estimado":
    # "(estimado)" no papel significa "o sistema não sabia o prazo deste fornecedor", e
    # aqui ele sabe — está gravado no pedido.
    prazo_assumido: bool = False

    @property
    def ajustados(self):
        return sum(1 for item in self.itens if item.foi_ajustada)


def como_bloco(pedido):
    """O pedido guardado, pronto para `apps.compras.pedido.montar`."""
    return _Bloco(
        nome=pedido.fornecedor,
        itens=[
            _Linha(
                codigo=item.codigo,
                descricao=item.descricao,
                grupo=item.grupo or "",
                quantidade=item.quantidade or ZERO,
                custo=item.custo,
                valor_do_pedido=item.valor or ZERO,
                foi_ajustada=item.escolhida_a_mao,
            )
            for item in pedido.itens.all()
        ],
        prazo_dias=pedido.prazo_dias,
    )


def montar(pedido, empresa, emitido_por=""):
    """A folha de UM pedido guardado, com o timbre da loja e o aviso do cancelamento."""
    observacao = pedido.observacao
    if pedido.foi_cancelado:
        # Folha de pedido cancelado existe para o arquivo e para mandar ao fornecedor
        # avisando. Sair igual à do pedido válido faria a loja imprimir um cancelamento
        # e o fornecedor entender um pedido.
        aviso = f"PEDIDO CANCELADO. Motivo: {pedido.motivo_cancelamento}"
        observacao = f"{aviso}\n{observacao}" if observacao else aviso
    return folha_do_pedido.montar(
        [como_bloco(pedido)], empresa,
        data_corte=pedido.data_corte, emitido_por=emitido_por, observacao=observacao,
    )


def nome_do_arquivo(pedido):
    """Nome que diz qual pedido é, porque o da lista de compra diz só o fornecedor."""
    import re

    limpo = re.sub(r"[^a-zA-Z0-9]+", "-", pedido.fornecedor).strip("-").lower()[:40]
    return f"pedido-{pedido.numero}-{limpo or 'fornecedor'}.pdf"
