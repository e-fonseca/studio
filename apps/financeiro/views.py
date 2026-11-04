"""Telas do financeiro: contas a pagar, despesas, contas a receber e pagamentos.

Os números vêm da última importação concluída. Quando a importação da noite falha, valem
os da anterior, e o aviso de idade dos dados aparece no topo como em todas as telas.
"""

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.auditoria.servicos import registrar
from apps.core import leitura, pdf, planilha
from apps.core.templatetags.cabana import reais
from apps.financeiro import relatorio as relatorio_das_contas
from apps.importacao import servicos as importacao_servicos

from . import quadros, servicos
from .models import PagamentoPrevisto

VALOR_MAXIMO = Decimal("9999999.99")


def _base(titulo):
    estado = importacao_servicos.estado_dos_dados()
    return estado, {"titulo": titulo, "estado": estado, "importacao": estado.importacao}


def _lista_pedida(request):
    """O filtro, a busca e as contas que a tela e o PDF mostram — os mesmos nos dois.

    É ajudante das duas telas, e não tela: quem fecha a porta é o `permission_required`
    de cada uma. Decorar isto aqui deixaria `contas_a_pagar` sem decorador nenhum e, para
    quem não entrou, devolveria um redirecionamento onde a tela espera cinco valores.
    """
    estado = importacao_servicos.estado_dos_dados()
    hoje = timezone.localdate()
    escolhido = (request.GET.get("filtro") or servicos.FILTRO_PADRAO).strip()
    if escolhido not in {chave for chave, _, _ in servicos.FILTROS}:
        escolhido = servicos.FILTRO_PADRAO
    busca = (request.GET.get("busca") or "").strip()[:80]
    contas = servicos.contas_a_pagar(estado.importacao, hoje=hoje, filtro=escolhido, busca=busca)
    return estado, hoje, escolhido, busca, contas


@login_required
@permission_required("financeiro.ver_financeiro", raise_exception=True)
def contas_a_pagar(request):
    estado, contexto = _base("Contas a pagar")
    estado, hoje, escolhido, busca, contas = _lista_pedida(request)
    contexto.update({
        "resumo": servicos.resumir(estado.importacao, hoje=hoje),
        "contas": contas,
        "total_da_lista": servicos.somar(contas),
        "vencidas": [c for c in contas if c.atraso],
        "previstos": servicos.previstos_em_aberto(),
        "filtros": servicos.filtros_de_contas(estado.importacao, hoje=hoje, busca=busca),
        "filtro": escolhido,
        # O nome da lista escolhida, para o botão do PDF dizer o que vai sair no papel.
        "rotulo_do_filtro": servicos.rotulo_do_filtro(escolhido),
        "busca": busca,
        # Os gráficos no formato do Dashboard (1.47.0). Sempre a loja toda: a busca e o
        # filtro mexem na lista de baixo, não no retrato de cima.
        "quadros": quadros.montar(estado.importacao, hoje=hoje),
    })
    return render(request, "financeiro/contas_a_pagar.html", contexto)


def _relatorio_pedido(request):
    """Os dados do relatório, iguais para o papel e para a planilha.

    Sai do mesmo `_lista_pedida` da tela: o que estiver filtrado e procurado na tela é
    o que sai no arquivo, e os dois nunca mostram contas diferentes.
    """
    estado, hoje, escolhido, busca, contas = _lista_pedida(request)
    return {
        "estado": estado,
        "hoje": hoje,
        "escolhido": escolhido,
        "busca": busca,
        "contas": contas,
        "resumo": servicos.resumir(estado.importacao, hoje=hoje),
        "filtros": servicos.filtros_de_contas(estado.importacao, hoje=hoje, busca=busca),
    }


def _registrar_a_saida(request, formato, dados):
    """Fica na trilha porque é uma lista do que a loja deve, com nome de fornecedor,
    que sai impressa do sistema: vale saber quem tirou, quando e em que formato."""
    registrar(f"financeiro.contas_a_pagar_em_{formato}", usuario=request.user,
              servico="financeiro",
              depois={"filtro": dados["escolhido"], "busca": dados["busca"],
                      "contas": len(dados["contas"])})


@login_required
@permission_required("financeiro.ver_financeiro", raise_exception=True)
def contas_a_pagar_em_pdf(request):
    """A mesma lista da tela, em PDF, para imprimir e levar para a reunião."""
    dados = _relatorio_pedido(request)
    relatorio = pdf.Relatorio(
        "Contas a pagar",
        relatorio_das_contas.subtitulo_de(dados["escolhido"], dados["contas"],
                                          dados["estado"]),
        emitido_por=request.user.get_full_name() or request.user.get_username(),
    )
    relatorio_das_contas.montar(relatorio, **dados)
    _registrar_a_saida(request, "pdf", dados)
    return pdf.resposta(relatorio, "contas-a-pagar.pdf")


@login_required
@permission_required("financeiro.ver_financeiro", raise_exception=True)
def contas_a_pagar_em_planilha(request):
    """A mesma lista, em planilha, para somar e cruzar no Excel.

    Pedido do Edson em 19/10/2026. Não é o PDF convertido: é o MESMO relatório, montado
    pela mesma função (apps/financeiro/relatorio.py), com os números em células de
    número de verdade — dinheiro soma, data ordena, atraso filtra do mais vencido para
    o menos. Converter o papel daria uma tabela de texto que não faz nada disso.
    """
    dados = _relatorio_pedido(request)
    folha = planilha.Planilha(
        "Contas a pagar",
        relatorio_das_contas.subtitulo_de(dados["escolhido"], dados["contas"],
                                          dados["estado"]),
        emitido_por=request.user.get_full_name() or request.user.get_username(),
    )
    relatorio_das_contas.montar(folha, **dados)
    _registrar_a_saida(request, "planilha", dados)
    return planilha.resposta(folha, "contas-a-pagar.xlsx")


@login_required
@permission_required("financeiro.ver_financeiro", raise_exception=True)
def sugestoes_da_busca(request):
    """O que oferecer enquanto a pessoa digita na busca de contas a pagar.

    Fica atrás da mesma permissão da tela: o nome do fornecedor e o valor que a loja
    deve a ele não são coisa de endereço aberto, e o vendedor não entra aqui.
    """
    estado = importacao_servicos.estado_dos_dados()
    termo = (request.GET.get("q") or "").strip()[:60]
    achados = servicos.sugestoes_da_busca(estado.importacao, termo, hoje=timezone.localdate())
    return JsonResponse({"itens": [
        {
            "descricao": achado["texto"],
            "ajuda": f"{achado['quantas']} conta{'s' if achado['quantas'] != 1 else ''}"
                     f" · {reais(achado['valor'])}",
        }
        for achado in achados
    ]})


@login_required
@permission_required("financeiro.ver_financeiro", raise_exception=True)
def despesas(request):
    estado, contexto = _base("Despesas")
    contexto.update({
        "grupos": servicos.despesas_por_grupo(estado.importacao),
        "meses": servicos.despesas_por_mes(estado.importacao),
        "resumo": servicos.resumir(estado.importacao),
    })
    return render(request, "financeiro/despesas.html", contexto)


@login_required
@permission_required("financeiro.ver_financeiro", raise_exception=True)
def contas_a_receber(request):
    estado, contexto = _base("Contas a receber")
    contexto.update({
        "contas": servicos.contas_a_receber(estado.importacao),
        "meses": servicos.despesas_por_mes(estado.importacao),
        "resumo": servicos.resumir(estado.importacao),
    })
    return render(request, "financeiro/contas_a_receber.html", contexto)


@login_required
@permission_required("financeiro.ver_financeiro", raise_exception=True)
def pagamentos(request):
    estado, contexto = _base("Pagamentos a fornecedores")
    contexto.update({
        "fornecedores": servicos.pagamentos_a_fornecedores(estado.importacao, quantas=30),
        "recentes": servicos.pagamentos_recentes(estado.importacao),
        "previstos": PagamentoPrevisto.objects.all()[:50],
        "hoje": timezone.localdate(),
    })
    return render(request, "financeiro/pagamentos.html", contexto)


def _valor_informado(bruto):
    """Aceita 1.234,56 e 1234.56, que é como as pessoas digitam valor em real."""
    limpo = (bruto or "").strip().replace("R$", "").replace(" ", "")
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    try:
        valor = Decimal(limpo)
    except (InvalidOperation, ValueError):
        return None
    if valor <= 0 or valor > VALOR_MAXIMO:
        return None
    return valor.quantize(Decimal("0.01"))


@login_required
@permission_required("financeiro.lancar_pagamento", raise_exception=True)
def salvar_previsto(request):
    """Registra um pagamento que a loja sabe que vem e ainda não está no SET."""
    if request.method != "POST":
        return redirect("financeiro:pagamentos")

    descricao = (request.POST.get("descricao") or "").strip()[:200]
    valor = _valor_informado(request.POST.get("valor"))
    # A data passa por `leitura.data` pelo mesmo motivo que o valor passa por
    # `_valor_informado`: ela ia crua para o campo do banco, e qualquer coisa que não
    # fosse o que o calendário do navegador escreve — 2026-13-45, 14/10/2026, um POST
    # remontado à mão — estourava na hora de gravar e a pessoa levava uma tela de erro
    # num formulário de dinheiro que já tem recado pronto para todo o resto. De brinde,
    # agora aceita a data escrita como gente escreve (20/09/2026, 20.09.2026).
    vencimento = leitura.data(request.POST.get("vencimento"))
    if not descricao or valor is None or vencimento is None:
        messages.error(
            request,
            "Para registrar um pagamento previsto preencha a descrição, o valor em reais e a "
            "data de vencimento (dia/mês/ano).",
        )
        return redirect("financeiro:pagamentos")

    previsto = PagamentoPrevisto.objects.create(
        descricao=descricao,
        fornecedor=(request.POST.get("fornecedor") or "").strip()[:200],
        valor=valor,
        vencimento=vencimento,
        observacao=(request.POST.get("observacao") or "").strip()[:500],
        criado_por=request.user,
    )
    registrar("financeiro.pagamento_previsto", usuario=request.user, recurso=previsto,
              recurso_rotulo=previsto.descricao,
              depois={"valor": str(previsto.valor), "vencimento": str(previsto.vencimento)})
    messages.success(request, f"{descricao} entrou na projeção de caixa. "
                              "Quando for lançado no SET, marque como lançado para não contar duas vezes.")
    return redirect("financeiro:pagamentos")


@login_required
@permission_required("financeiro.lancar_pagamento", raise_exception=True)
def marcar_lancado(request, pk):
    """Tira o previsto da projeção porque agora ele veio do SET, e não se conta duas vezes."""
    if request.method != "POST":
        return redirect("financeiro:pagamentos")
    previsto = PagamentoPrevisto.objects.filter(pk=pk).first()
    if previsto is None:
        messages.error(request, "Esse pagamento previsto não existe mais.")
        return redirect("financeiro:pagamentos")
    previsto.lancado_no_set = True
    previsto.save(update_fields=["lancado_no_set"])
    registrar("financeiro.previsto_lancado", usuario=request.user, recurso=previsto,
              recurso_rotulo=previsto.descricao)
    messages.success(request, f"{previsto.descricao} saiu da projeção: agora ele vem do SET.")
    return redirect("financeiro:pagamentos")
