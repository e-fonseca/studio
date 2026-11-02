"""Tela de markup e margem de lucro, e o mesmo recorte em arquivo.

A permissão é própria desde a 1.44.0 (`importacao.ver_margem`); até ali era a mesma dos
painéis, e quem tinha a dos painéis ganhou esta na atualização. Isto é custo, preço e
lucro, então é assunto da gerência e do administrativo. O perfil de vendedor não tem
essa permissão e nunca vê esta tela, que é a condição que o Edson pôs desde o começo.
"""

from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponse
from django.shortcuts import render

from apps.auditoria.servicos import registrar_arquivo
from apps.importacao import servicos as importacao_servicos

from . import servicos

PERMISSAO = "importacao.ver_margem"


def _recorte(request, quantos):
    estado = importacao_servicos.estado_dos_dados()
    tela = servicos.montar(
        estado.importacao,
        grupo=(request.GET.get("grupo") or "").strip(),
        fornecedor=(request.GET.get("fornecedor") or "").strip(),
        situacao=(request.GET.get("situacao") or "").strip(),
        busca=(request.GET.get("busca") or "").strip(),
        ordem=(request.GET.get("ordem") or servicos.ORDEM_PADRAO).strip(),
        quantos=quantos,
    )
    return estado, tela


@login_required
@permission_required(PERMISSAO, raise_exception=True)
def lista(request):
    estado, tela = _recorte(request, servicos.QUANTOS_NA_TELA)
    return render(request, "margem/lista.html", {
        "titulo": "Margem e markup",
        "estado": estado,
        "t": tela,
        "situacoes": servicos.SITUACOES,
        "ordens": servicos.ORDENS,
        "quantos_na_tela": servicos.QUANTOS_NA_TELA,
        "tolerancia": servicos.TOLERANCIA_MARKUP_SET,
    })


@login_required
@permission_required(PERMISSAO, raise_exception=True)
def em_arquivo(request):
    """O recorte inteiro, não só os primeiros da tela, para abrir no Excel.

    Ponto e vírgula e BOM porque é assim que o Excel em português abre sem perguntar
    nada a ninguém.
    """
    import csv
    import io as entrada_e_saida

    _estado, tela = _recorte(request, quantos=0)
    buffer = entrada_e_saida.StringIO()
    escritor = csv.writer(buffer, delimiter=";")
    escritor.writerows(servicos.em_linhas(tela))
    corpo = "﻿" + buffer.getvalue()
    nome = (f"margem-e-markup-{tela.data_corte:%Y-%m-%d}.csv" if tela.data_corte
            else "margem-e-markup.csv")
    resposta = HttpResponse(corpo, content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = f'attachment; filename="{nome}"'
    registrar_arquivo(request, nome)
    return resposta
