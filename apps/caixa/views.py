"""Telas do caixa: a lista de turnos e o detalhe de um turno.

Pedido do Edson em 08/10/2026. São duas telas porque a lista responde "como foram os
caixas" e o detalhe responde "por que este não fechou" — misturar as duas daria uma
página de cinquenta mil linhas.
"""

from django.contrib.auth.decorators import login_required, permission_required
from django.http import Http404
from django.shortcuts import render

from apps.importacao import servicos as importacao_servicos

from . import dinheiro, servicos
from .models import CaixaImportado

PERMISSAO = "caixa.ver_caixa"


def _base(titulo):
    estado = importacao_servicos.estado_dos_dados()
    return {"titulo": titulo, "estado": estado, "importacao": estado.importacao}


@login_required
@permission_required(PERMISSAO, raise_exception=True)
def lista(request):
    estado = importacao_servicos.estado_dos_dados()
    tela = servicos.montar(
        estado.importacao,
        periodo=request.GET.get("periodo", servicos.PERIODO_PADRAO),
        operador=(request.GET.get("operador") or "").strip(),
        situacao=(request.GET.get("situacao") or "").strip(),
    )
    contexto = _base("Caixa")
    contexto.update({
        "t": tela,
        "periodos": servicos.PERIODOS,
        "situacoes": servicos.SITUACOES,
        "dias_para_esquecido": servicos.DIAS_PARA_ESQUECIDO,
    })
    return render(request, "caixa/lista.html", contexto)


@login_required
@permission_required(PERMISSAO, raise_exception=True)
def turno(request, pk):
    """Um turno com os movimentos que não são venda e o que entrou por forma de pagamento.

    Procurado pelo número do SET dentro da última importação, e não pela chave do nosso
    banco: a cada importação as linhas são refeitas, então a chave muda e o link que
    alguém guardou deixaria de abrir.
    """
    estado = importacao_servicos.estado_dos_dados()
    if estado.importacao is None:
        raise Http404("Ainda não há importação concluída.")
    caixa = CaixaImportado.objects.filter(importacao=estado.importacao, id_set=pk).first()
    if caixa is None:
        raise Http404("Esse caixa não está na última importação do SET.")
    contexto = _base(f"Caixa {caixa.id_set}")
    contexto.update({
        "caixa": caixa,
        "formas": servicos.formas_do_caixa(caixa),
        # O dinheiro vivo deste turno: o que deveria estar na gaveta no fechamento.
        "gaveta": dinheiro.do_turno(caixa),
        "movimentos": servicos.movimentos_do_caixa(caixa),
        "esquecido": servicos.esta_esquecido(caixa, estado.importacao.data_corte),
        "dias_para_esquecido": servicos.DIAS_PARA_ESQUECIDO,
    })
    return render(request, "caixa/turno.html", contexto)
