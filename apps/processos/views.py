from datetime import date

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Count, Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.auditoria.servicos import registrar

from . import ficha_tecnica as ficha, regras
from .forms import AfirmacaoForm, AnexoForm, MotivoForm, ProcessoForm, TesteForm, VersaoForm
from .models import Anexo, Area, Processo, VersaoProcesso

ver = permission_required("processos.view_processo", raise_exception=True)


def _executar(request, processo, acao, *args, **kwargs):
    """Executa uma regra e converte a recusa em mensagem para a pessoa."""
    try:
        resultado = acao(request.user, processo, *args, **kwargs)
    except regras.RegraViolada as erro:
        messages.error(request, str(erro))
        return None
    return resultado


@login_required
@ver
def quadro(request):
    processos = Processo.objects.select_related("titular", "substituto", "versao_atual")
    busca = request.GET.get("q", "").strip()
    area = request.GET.get("area", "")
    criticidade = request.GET.get("criticidade", "")
    if busca:
        processos = processos.filter(
            Q(titulo__icontains=busca)
            | Q(fonte_conhecimento__icontains=busca)
            | Q(versao_atual__objetivo__icontains=busca)
            | Q(versao_atual__passos__icontains=busca)
            | Q(afirmacoes__texto__icontains=busca)
        ).distinct()
    if area in Area.values:
        processos = processos.filter(area=area)
    if criticidade in Processo.Criticidade.values:
        processos = processos.filter(criticidade=criticidade)
    ordem = {Processo.Criticidade.ALTA: 0, Processo.Criticidade.MEDIA: 1, Processo.Criticidade.BAIXA: 2}
    processos = sorted(processos, key=lambda p: (ordem[p.criticidade], p.prazo_coleta or date.max, p.titulo))
    colunas = [
        {"estado": valor, "rotulo": rotulo, "cartoes": [p for p in processos if p.estado == valor]}
        for valor, rotulo in Processo.Estado.choices
    ]
    return render(request, "processos/quadro.html", {
        "titulo": "Base de processos",
        "colunas": colunas,
        "busca": busca,
        "area": area,
        "criticidade": criticidade,
        "areas": Area.choices,
        "criticidades": Processo.Criticidade.choices,
        "total": sum(len(c["cartoes"]) for c in colunas),
        "transferencia": _transferencia_de_conhecimento(),
    })


def _transferencia_de_conhecimento():
    """Quanto do conhecimento da loja já está documentado e validado.

    O Edson pediu que a transferência de conhecimento se concentrasse aqui (antes
    isso estava na tela de início). O número que interessa é um só: de todo
    processo que a loja tem, quanto já está escrito de um jeito que outra pessoa
    conseguiu executar. Conta sobre TODOS os processos, não sobre o filtro da
    tela, senão o progresso muda de valor conforme quem está olhando.
    """
    por_estado = dict(Processo.objects.values_list("estado").annotate(n=Count("id")))
    total = sum(por_estado.values())
    validados = por_estado.get(Processo.Estado.VALIDADO, 0)
    return {
        "total": total,
        "validados": validados,
        "porcentagem": round(validados * 100 / total) if total else 0,
        "criticos_sem_validacao": Processo.objects.filter(
            criticidade=Processo.Criticidade.ALTA).exclude(estado=Processo.Estado.VALIDADO).count(),
        "estados": [(rotulo, valor, por_estado.get(valor, 0))
                    for valor, rotulo in Processo.Estado.choices],
    }


@login_required
@ver
def ficha_tecnica(request):
    """De que o sistema é feito, para quem um dia precisar mantê-lo.

    Entra na Base de processos porque é a mesma pergunta que ela responde: o que
    uma pessoa sabe tem que estar escrito em algum lugar que outra pessoa alcance.
    Os números são lidos do sistema em funcionamento (apps/processos/ficha_tecnica.py),
    não digitados, senão a ficha envelhece na primeira atualização.
    """
    return render(request, "processos/ficha_tecnica.html",
                  {"titulo": "Ficha técnica do sistema", **ficha.montar()})


@login_required
@ver
def detalhe(request, pk):
    processo = get_object_or_404(
        Processo.objects.select_related("titular", "substituto", "versao_atual", "versao_validada"), pk=pk
    )
    return render(request, "processos/detalhe.html", {
        "titulo": str(processo),
        "processo": processo,
        "versao": processo.versao_atual,
        "afirmacoes": processo.afirmacoes.select_related("registrado_por", "aprovado_por"),
        "testes": processo.testes.select_related("executor", "versao"),
        "anexos": processo.anexos.select_related("enviado_por"),
        "versoes": processo.versoes.select_related("autor"),
        "pendencias": regras.pendencias_para_teste(processo),
        "form_teste": TesteForm(),
        "form_afirmacao": AfirmacaoForm(),
        "form_anexo": AnexoForm(),
        "form_motivo": MotivoForm(),
    })


@login_required
@permission_required("processos.documentar_processo", raise_exception=True)
def novo(request):
    form = ProcessoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            processo = regras.criar_processo(request.user, **form.cleaned_data)
        except regras.RegraViolada as erro:
            form.add_error(None, str(erro))
        else:
            messages.success(request, "Processo cadastrado. Agora escreva a primeira versão do procedimento.")
            return redirect("processos:editar_procedimento", pk=processo.pk)
    return render(request, "processos/form_processo.html", {"titulo": "Novo processo", "form": form})


@login_required
@permission_required("processos.documentar_processo", raise_exception=True)
def editar_cadastro(request, pk):
    processo = get_object_or_404(Processo, pk=pk)
    form = ProcessoForm(request.POST or None, instance=Processo.objects.get(pk=pk))
    if request.method == "POST" and form.is_valid():
        try:
            regras.atualizar_cadastro(request.user, processo, **form.cleaned_data)
        except regras.RegraViolada as erro:
            form.add_error(None, str(erro))
        else:
            messages.success(request, "Cadastro atualizado.")
            return redirect(processo)
    return render(request, "processos/form_processo.html",
                  {"titulo": f"Editar cadastro de {processo}", "form": form, "processo": processo})


@login_required
@permission_required("processos.documentar_processo", raise_exception=True)
def editar_procedimento(request, pk):
    processo = get_object_or_404(Processo.objects.select_related("versao_atual"), pk=pk)
    atual = processo.versao_atual
    inicial = {"versao_base": atual.numero if atual else 0, "resumo_mudanca": ""}
    if atual:
        inicial.update({campo: getattr(atual, campo) for campo in VersaoProcesso.CAMPOS_CONTEUDO})
    else:
        inicial["resumo_mudanca"] = "Primeira versão."
    form = VersaoForm(request.POST or None, initial=inicial)
    if request.method == "POST" and form.is_valid():
        dados = dict(form.cleaned_data)
        try:
            versao = regras.salvar_versao(request.user, processo, **dados)
        except regras.RegraViolada as erro:
            form.add_error(None, str(erro))
        else:
            messages.success(request, f"Versão {versao.numero} salva.")
            return redirect(processo)
    return render(request, "processos/form_procedimento.html", {
        "titulo": f"Procedimento de {processo}", "form": form, "processo": processo, "versao_atual": atual,
    })


@login_required
@ver
def versao(request, pk, numero):
    v = get_object_or_404(VersaoProcesso.objects.select_related("processo", "autor"), processo_id=pk, numero=numero)
    return render(request, "processos/versao.html", {"titulo": str(v), "versao": v, "processo": v.processo})


@login_required
@require_POST
def enviar_para_teste(request, pk):
    processo = get_object_or_404(Processo, pk=pk)
    if _executar(request, processo, regras.enviar_para_teste):
        messages.success(request, "Processo enviado para teste. Peça a outra pessoa para executá-lo usando só esta página.")
    return redirect(processo)


@login_required
@require_POST
def registrar_teste(request, pk):
    processo = get_object_or_404(Processo, pk=pk)
    form = TesteForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Preencha o resultado do teste.")
    elif _executar(request, processo, regras.registrar_teste, **form.cleaned_data):
        messages.success(request, "Teste registrado. Obrigado pelo retorno.")
    return redirect(processo)


@login_required
@require_POST
def validar(request, pk):
    processo = get_object_or_404(Processo, pk=pk)
    if _executar(request, processo, regras.validar, request.POST.get("observacao", "")):
        messages.success(request, "Processo validado pela gestão.")
    return redirect(processo)


@login_required
@require_POST
def devolver(request, pk):
    processo = get_object_or_404(Processo, pk=pk)
    form = MotivoForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Informe o motivo da devolução.")
    elif _executar(request, processo, regras.devolver, form.cleaned_data["motivo"]):
        messages.success(request, "Processo devolvido para documentação.")
    return redirect(processo)


@login_required
@require_POST
def nova_afirmacao(request, pk):
    processo = get_object_or_404(Processo, pk=pk)
    form = AfirmacaoForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Preencha tipo, texto e quem disse ou observou.")
    elif _executar(request, processo, regras.registrar_afirmacao, **form.cleaned_data):
        messages.success(request, "Registro incluído.")
    return redirect(processo)


@login_required
@require_POST
def enviar_anexo(request, pk):
    processo = get_object_or_404(Processo, pk=pk)
    form = AnexoForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Escolha um arquivo e descreva o que ele mostra.")
    elif _executar(request, processo, regras.anexar, tamanho_maximo=settings.ANEXO_TAMANHO_MAXIMO,
                   **form.cleaned_data):
        messages.success(request, "Anexo enviado.")
    return redirect(processo)


@login_required
@permission_required("processos.ver_anexo", raise_exception=True)
def baixar_anexo(request, pk, anexo_id):
    anexo = get_object_or_404(Anexo, pk=anexo_id, processo_id=pk)
    registrar("processo.anexo_baixado", usuario=request.user, recurso=anexo.processo,
              depois={"anexo_id": anexo.pk, "nome": anexo.nome_original})
    resposta = FileResponse(anexo.arquivo.open("rb"), as_attachment=True, filename=anexo.nome_original)
    resposta["Content-Security-Policy"] = "default-src 'none'"
    return resposta
