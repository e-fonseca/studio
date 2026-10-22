"""Regras das sugestões de compra escritas pela equipe."""

from decimal import Decimal, InvalidOperation

from django.utils import timezone

from apps.auditoria.servicos import registrar

from .models import SugestaoDeCompra


class ErroDeSugestao(Exception):
    """Mensagem pronta para a tela."""


def quantidade_informada(bruto):
    """Aceita 3, 3,5 e vazio. Quantidade é opcional: nem sempre quem sugere sabe."""
    limpo = (bruto or "").strip().replace(" ", "").replace(",", ".")
    if not limpo:
        return None
    try:
        valor = Decimal(limpo)
    except (InvalidOperation, ValueError):
        raise ErroDeSugestao("A quantidade tem que ser um número, como 3 ou 2,5. "
                             "Se não souber, deixe em branco.")
    if valor <= 0 or valor > Decimal("999999"):
        raise ErroDeSugestao("A quantidade tem que ser maior que zero.")
    return valor.quantize(Decimal("0.001"))


def registrar_sugestao(*, produto, usuario, codigo="", quantidade=None, motivo="",
                       observacao="", fornecedor=""):
    produto = (produto or "").strip()
    if not produto:
        raise ErroDeSugestao("Escreva qual é o produto. Sem isso a gerência não tem o que comprar.")
    if motivo not in SugestaoDeCompra.Motivo.values:
        motivo = SugestaoDeCompra.Motivo.CLIENTE_PEDIU
    sugestao = SugestaoDeCompra.objects.create(
        produto=produto[:200],
        codigo=(codigo or "").strip()[:60],
        quantidade=quantidade,
        motivo=motivo,
        observacao=(observacao or "").strip(),
        fornecedor=(fornecedor or "").strip()[:200],
        criada_por=usuario,
    )
    registrar("compras.sugestao_registrada", usuario=usuario, recurso=sugestao,
              recurso_rotulo=sugestao.produto[:200],
              depois={"produto": sugestao.produto, "motivo": sugestao.motivo})
    return sugestao


def responder(sugestao, *, situacao, resposta, usuario):
    if situacao not in SugestaoDeCompra.Situacao.values:
        raise ErroDeSugestao("Escolha o que foi feito com a sugestão.")
    antes = {"situacao": sugestao.situacao, "resposta": sugestao.resposta}
    sugestao.situacao = situacao
    sugestao.resposta = (resposta or "").strip()
    sugestao.respondida_em = timezone.now()
    sugestao.respondida_por = usuario
    sugestao.save(update_fields=["situacao", "resposta", "respondida_em", "respondida_por"])
    registrar("compras.sugestao_respondida", usuario=usuario, recurso=sugestao,
              recurso_rotulo=sugestao.produto[:200], antes=antes,
              depois={"situacao": sugestao.situacao, "resposta": sugestao.resposta})
    return sugestao


def listar(situacao="", quantas=60):
    consulta = SugestaoDeCompra.objects.select_related("criada_por", "respondida_por")
    if situacao in SugestaoDeCompra.Situacao.values:
        consulta = consulta.filter(situacao=situacao)
    return list(consulta[:quantas])


def contagem_por_situacao():
    from django.db.models import Count

    por_valor = dict(
        SugestaoDeCompra.objects.values_list("situacao").annotate(n=Count("id"))
    )
    return [(rotulo, valor, por_valor.get(valor, 0))
            for valor, rotulo in SugestaoDeCompra.Situacao.choices]
