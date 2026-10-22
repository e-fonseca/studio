"""As telas da conciliação bancária: a lista de extratos e um extrato aberto."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.importacao import servicos as importacao_servicos

from . import conferencia, servicos
from .models import ExtratoImportado, LinhaExtrato

PERMISSAO = "conciliacao.conciliar_banco"


def _base(titulo):
    estado = importacao_servicos.estado_dos_dados()
    return estado, {"titulo": titulo, "estado": estado, "importacao": estado.importacao}


@login_required
@permission_required(PERMISSAO, raise_exception=True)
def lista(request):
    estado, contexto = _base("Conciliação bancária")
    extratos = list(ExtratoImportado.objects.all()[:50])
    # Quantas linhas de cada extrato ainda esperam alguém: é o que decide qual abrir.
    for extrato in extratos:
        extrato.pendentes = extrato.linhas.filter(
            situacao=LinhaExtrato.Situacao.PENDENTE, valor__lt=0).count()
        extrato.total_de_linhas = extrato.linhas.count()
    contexto.update({"extratos": extratos})
    return render(request, "conciliacao/lista.html", contexto)


@login_required
@permission_required(PERMISSAO, raise_exception=True)
@require_POST
def importar(request):
    try:
        extrato = servicos.importar(
            request.FILES.get("extrato"), request.user, banco=request.POST.get("banco", ""))
    except servicos.ExtratoRecusado as recusa:
        messages.error(request, str(recusa))
        return redirect("conciliacao:lista")
    descartadas = getattr(extrato, "descartadas", 0)
    aviso = f"Extrato importado: {extrato.linhas.count()} movimentos."
    if descartadas:
        aviso += (f" {descartadas} linha{'s' if descartadas > 1 else ''} do arquivo "
                  f"não tinha{'m' if descartadas > 1 else ''} data ou valor e ficou"
                  f"{'ram' if descartadas > 1 else ''} de fora.")
    messages.success(request, aviso)
    return redirect("conciliacao:extrato", pk=extrato.pk)


@login_required
@permission_required(PERMISSAO, raise_exception=True)
def extrato(request, pk):
    registro = get_object_or_404(ExtratoImportado, pk=pk)
    estado, contexto = _base(f"Extrato {registro.periodo_inicio:%d/%m/%Y}"
                             if registro.periodo_inicio else "Extrato")
    confrontos = conferencia.confrontar(registro, estado.importacao)
    contexto.update({
        "extrato": registro,
        "confrontos": confrontos,
        "resumo": conferencia.resumir(confrontos),
        "dias_de_folga": conferencia.DIAS_DE_FOLGA,
    })
    return render(request, "conciliacao/extrato.html", contexto)


def _voltar(linha):
    return redirect("conciliacao:extrato", pk=linha.extrato_id)


@login_required
@permission_required(PERMISSAO, raise_exception=True)
@require_POST
def conferir(request, pk):
    linha = get_object_or_404(LinhaExtrato, pk=pk)
    estado = importacao_servicos.estado_dos_dados()
    try:
        id_set = int(request.POST.get("conta") or 0)
    except ValueError:
        id_set = 0
    try:
        servicos.conferir(linha, id_set, request.user, estado.importacao)
    except servicos.ExtratoRecusado as recusa:
        messages.error(request, str(recusa))
    else:
        messages.success(request, f"Conferido: {linha.lancamento_rotulo}")
    return _voltar(linha)


@login_required
@permission_required(PERMISSAO, raise_exception=True)
@require_POST
def sem_conta(request, pk):
    linha = get_object_or_404(LinhaExtrato, pk=pk)
    servicos.marcar_sem_conta(linha, request.user, request.POST.get("observacao", ""))
    messages.success(request, "Marcada como saída sem conta no SET.")
    return _voltar(linha)


@login_required
@permission_required(PERMISSAO, raise_exception=True)
@require_POST
def desfazer(request, pk):
    linha = get_object_or_404(LinhaExtrato, pk=pk)
    servicos.desfazer(linha, request.user)
    messages.success(request, "A linha voltou para a lista do que falta conferir.")
    return _voltar(linha)


@login_required
@permission_required(PERMISSAO, raise_exception=True)
@require_POST
def conferir_as_obvias(request, pk):
    registro = get_object_or_404(ExtratoImportado, pk=pk)
    estado = importacao_servicos.estado_dos_dados()
    quantas = servicos.conferir_as_obvias(registro, estado.importacao, request.user)
    if quantas:
        messages.success(request, f"{quantas} linha{'s' if quantas > 1 else ''} "
                                  f"conferida{'s' if quantas > 1 else ''}.")
    else:
        messages.info(request, "Nenhuma linha tinha uma conta só para conferir sozinha.")
    return redirect("conciliacao:extrato", pk=registro.pk)


@login_required
@permission_required(PERMISSAO, raise_exception=True)
@require_POST
def apagar(request, pk):
    registro = get_object_or_404(ExtratoImportado, pk=pk)
    rotulo = servicos.apagar(registro, request.user)
    messages.success(request, f"Extrato apagado: {rotulo}.")
    return redirect("conciliacao:lista")
