"""Telas de projetos sob medida e de oficinas parceiras."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.auditoria.servicos import registrar

from . import servicos
from .forms import OficinaForm, ParcelaForm, ProjetoForm
from .models import Oficina, Parcela, Projeto

VER = "projetos.ver_projetos"
EDITAR = "projetos.editar_projetos"


def _foto(projeto):
    """O que vai para o "antes" e o "depois" da auditoria."""
    return {
        "etapa": projeto.etapa, "titulo": projeto.titulo, "cliente": projeto.cliente_nome,
        "oficina": projeto.oficina.nome if projeto.oficina_id else "",
        "valor_venda": str(projeto.valor_venda), "custo_oficina": str(projeto.custo_oficina),
        "outros_custos": str(projeto.outros_custos),
        "prazo_entrega": projeto.prazo_entrega.isoformat() if projeto.prazo_entrega else None,
    }


@login_required
@permission_required(VER, raise_exception=True)
def lista(request):
    filtro = request.GET.get("filtro") or servicos.FILTRO_PADRAO
    if filtro not in {chave for chave, _, _ in servicos.FILTROS}:
        filtro = servicos.FILTRO_PADRAO
    busca = (request.GET.get("busca") or "").strip()[:80]
    hoje = timezone.localdate()
    projetos = list(servicos.filtrar(filtro, hoje, busca)[:300])
    for projeto in projetos:
        projeto.atraso = projeto.dias_de_atraso(hoje)
    return render(request, "projetos/lista.html", {
        "titulo": "Projetos",
        "resumo": servicos.resumir(hoje),
        "projetos": projetos,
        "filtro": filtro,
        "busca": busca,
        "pode_editar": request.user.has_perm(EDITAR),
    })


@login_required
@permission_required(EDITAR, raise_exception=True)
def novo(request):
    form = ProjetoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        projeto = form.save(commit=False)
        projeto.criado_por = request.user
        projeto.save()
        registrar("projeto.criado", usuario=request.user, recurso=projeto, depois=_foto(projeto))
        messages.success(request, f"Projeto {projeto.codigo} criado. Agora lance as parcelas: "
                                  "a entrada do cliente e o pagamento da oficina.")
        return redirect("projetos:ficha", pk=projeto.pk)
    return render(request, "projetos/form.html", {
        "titulo": "Projeto novo", "form": form, "voltar": "projetos:lista",
    })


@login_required
@permission_required(EDITAR, raise_exception=True)
def editar(request, pk):
    projeto = get_object_or_404(Projeto, pk=pk)
    antes = _foto(projeto)
    form = ProjetoForm(request.POST or None, instance=projeto)
    if request.method == "POST" and form.is_valid():
        projeto = form.save()
        registrar("projeto.alterado", usuario=request.user, recurso=projeto,
                  antes=antes, depois=_foto(projeto))
        messages.success(request, f"Projeto {projeto.codigo} salvo.")
        return redirect("projetos:ficha", pk=projeto.pk)
    return render(request, "projetos/form.html", {
        "titulo": f"Mudar {projeto.codigo}", "form": form, "projeto": projeto,
    })


@login_required
@permission_required(VER, raise_exception=True)
def ficha(request, pk):
    projeto = get_object_or_404(Projeto.objects.select_related("oficina", "responsavel"), pk=pk)
    hoje = timezone.localdate()
    parcelas = list(projeto.parcelas.all())
    for parcela in parcelas:
        parcela.atraso = parcela.dias_de_atraso(hoje)
    form_parcela = ParcelaForm(initial={"tipo": Parcela.Tipo.RECEBER, "vencimento": hoje})
    return render(request, "projetos/ficha.html", {
        "titulo": f"{projeto.codigo} · {projeto.titulo}",
        "projeto": projeto,
        "atraso": projeto.dias_de_atraso(hoje),
        "parcelas": parcelas,
        "form_parcela": form_parcela,
        "etapas": Projeto.Etapa.choices,
        "pode_editar": request.user.has_perm(EDITAR),
        "leads": projeto.leads.all(),
    })


@login_required
@permission_required(EDITAR, raise_exception=True)
@require_POST
def mudar_etapa(request, pk):
    projeto = get_object_or_404(Projeto, pk=pk)
    etapa = request.POST.get("etapa") or ""
    if etapa not in Projeto.Etapa.values:
        messages.error(request, "Escolha uma das etapas da lista.")
        return redirect("projetos:ficha", pk=pk)
    antes = _foto(projeto)
    servicos.mudar_etapa(projeto, etapa)
    registrar("projeto.etapa", usuario=request.user, recurso=projeto, antes=antes, depois=_foto(projeto))
    messages.success(request, f"{projeto.codigo} agora está em: {projeto.get_etapa_display()}.")
    return redirect("projetos:ficha", pk=pk)


@login_required
@permission_required(EDITAR, raise_exception=True)
@require_POST
def nova_parcela(request, pk):
    projeto = get_object_or_404(Projeto, pk=pk)
    form = ParcelaForm(request.POST)
    if form.is_valid():
        parcela = form.save(commit=False)
        parcela.projeto = projeto
        parcela.criado_por = request.user
        parcela.save()
        registrar("projeto.parcela_criada", usuario=request.user, recurso=projeto,
                  depois={"tipo": parcela.tipo, "valor": str(parcela.valor),
                          "vencimento": parcela.vencimento.isoformat(),
                          "pago_em": parcela.pago_em.isoformat() if parcela.pago_em else None})
        messages.success(request, f"{parcela.get_tipo_display()} lançada.")
        return redirect("projetos:ficha", pk=pk)
    # O formulário não perde o que foi digitado: a ficha volta com ele preenchido e o erro.
    hoje = timezone.localdate()
    parcelas = list(projeto.parcelas.all())
    for parcela in parcelas:
        parcela.atraso = parcela.dias_de_atraso(hoje)
    return render(request, "projetos/ficha.html", {
        "titulo": f"{projeto.codigo} · {projeto.titulo}",
        "projeto": projeto, "atraso": projeto.dias_de_atraso(hoje),
        "parcelas": parcelas, "form_parcela": form, "etapas": Projeto.Etapa.choices,
        "pode_editar": True, "leads": projeto.leads.all(), "abrir_parcela": True,
    }, status=400)


@login_required
@permission_required(EDITAR, raise_exception=True)
@require_POST
def baixar_parcela(request, pk):
    """Marca a parcela como paga (ou recebida) hoje, ou desfaz a marca."""
    parcela = get_object_or_404(Parcela.objects.select_related("projeto"), pk=pk)
    antes = {"pago_em": parcela.pago_em.isoformat() if parcela.pago_em else None}
    if request.POST.get("desfazer"):
        parcela.pago_em = None
        aviso = "Parcela voltou para em aberto."
    else:
        parcela.pago_em = timezone.localdate()
        aviso = ("Entrada recebida hoje." if parcela.entrada else "Pagamento feito hoje.")
    parcela.save(update_fields=["pago_em"])
    registrar("projeto.parcela_baixada", usuario=request.user, recurso=parcela.projeto,
              antes=antes, depois={"parcela": parcela.pk,
                                   "pago_em": parcela.pago_em.isoformat() if parcela.pago_em else None})
    messages.success(request, aviso)
    return redirect("projetos:ficha", pk=parcela.projeto_id)


# Oficinas ------------------------------------------------------------------------------

@login_required
@permission_required(VER, raise_exception=True)
def oficinas(request):
    abertas = Q(projetos__parcelas__pago_em__isnull=True,
                projetos__parcelas__tipo=Parcela.Tipo.OFICINA)
    lista_ = Oficina.objects.annotate(
        em_andamento=Count("projetos", filter=Q(projetos__etapa__in=Projeto.EM_ANDAMENTO),
                           distinct=True),
        entregues=Count("projetos", filter=Q(projetos__etapa=Projeto.Etapa.ENTREGUE), distinct=True),
        a_pagar=Sum("projetos__parcelas__valor", filter=abertas),
    )
    return render(request, "projetos/oficinas.html", {
        "titulo": "Oficinas parceiras", "oficinas": lista_,
        "pode_editar": request.user.has_perm(EDITAR),
    })


@login_required
@permission_required(VER, raise_exception=True)
def oficina(request, pk):
    oficina_ = get_object_or_404(Oficina, pk=pk)
    hoje = timezone.localdate()
    projetos = list(oficina_.projetos.select_related("responsavel").order_by("-criado_em"))
    for projeto in projetos:
        projeto.atraso = projeto.dias_de_atraso(hoje)
    pagamentos = Parcela.objects.filter(projeto__oficina=oficina_, tipo=Parcela.Tipo.OFICINA)
    return render(request, "projetos/oficina.html", {
        "titulo": oficina_.nome, "oficina": oficina_, "projetos": projetos,
        "pago": pagamentos.filter(pago_em__isnull=False).aggregate(v=Sum("valor"))["v"],
        "a_pagar": pagamentos.filter(pago_em__isnull=True).aggregate(v=Sum("valor"))["v"],
        "pode_editar": request.user.has_perm(EDITAR),
    })


@login_required
@permission_required(EDITAR, raise_exception=True)
def oficina_form(request, pk=None):
    oficina_ = get_object_or_404(Oficina, pk=pk) if pk else None
    form = OficinaForm(request.POST or None, instance=oficina_)
    if request.method == "POST" and form.is_valid():
        nova = oficina_ is None
        oficina_ = form.save()
        registrar("oficina.criada" if nova else "oficina.alterada", usuario=request.user,
                  recurso=oficina_, depois={"nome": oficina_.nome, "ativa": oficina_.ativa})
        messages.success(request, f"Oficina {oficina_.nome} salva.")
        return redirect("projetos:oficina", pk=oficina_.pk)
    return render(request, "projetos/form.html", {
        "titulo": "Oficina nova" if oficina_ is None else f"Mudar {oficina_.nome}",
        "form": form, "voltar": "projetos:oficinas",
    })
