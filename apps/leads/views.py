"""Telas do funil de leads (SDR)."""

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.auditoria.servicos import registrar

from . import servicos
from .forms import ContatoForm, LeadForm
from .models import Lead

VER = "leads.ver_leads"
TRABALHAR = "leads.trabalhar_leads"


def _foto(lead):
    return {"etapa": lead.etapa, "nome": lead.nome, "responsavel": lead.responsavel_id,
            "proximo_contato": lead.proximo_contato.isoformat() if lead.proximo_contato else None,
            "motivo_perda": lead.motivo_perda}


@login_required
@permission_required(VER, raise_exception=True)
def funil(request):
    meus = request.GET.get("meus") == "1"
    hoje = timezone.localdate()
    return render(request, "leads/funil.html", {
        "titulo": "Leads",
        "funil": servicos.montar(request.user if meus else None, hoje),
        "meus": meus,
        "hoje": hoje,
        "dias_da_conversao": servicos.DIAS_DA_CONVERSAO,
        "pode_trabalhar": request.user.has_perm(TRABALHAR),
    })


@login_required
@permission_required(VER, raise_exception=True)
def fechados(request):
    desde = timezone.now() - timedelta(days=servicos.DIAS_DA_CONVERSAO)
    leads = Lead.objects.filter(etapa__in=Lead.FECHADAS, fechado_em__gte=desde).select_related(
        "responsavel", "projeto").order_by("-fechado_em")
    return render(request, "leads/fechados.html", {
        "titulo": "Leads fechados", "leads": leads, "dias": servicos.DIAS_DA_CONVERSAO,
    })


@login_required
@permission_required(TRABALHAR, raise_exception=True)
def novo(request):
    form = LeadForm(request.POST or None, initial={
        "responsavel": request.user.pk, "proximo_contato": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        lead = form.save(commit=False)
        lead.criado_por = request.user
        lead.save()
        registrar("lead.criado", usuario=request.user, recurso=lead, depois=_foto(lead))
        messages.success(request, f"Lead {lead.nome} anotado.")
        return redirect("leads:ficha", pk=lead.pk)
    return render(request, "leads/form.html", {"titulo": "Lead novo", "form": form})


@login_required
@permission_required(TRABALHAR, raise_exception=True)
def editar(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    antes = _foto(lead)
    form = LeadForm(request.POST or None, instance=lead)
    if request.method == "POST" and form.is_valid():
        lead = form.save()
        registrar("lead.alterado", usuario=request.user, recurso=lead, antes=antes, depois=_foto(lead))
        messages.success(request, "Lead salvo.")
        return redirect("leads:ficha", pk=lead.pk)
    return render(request, "leads/form.html", {"titulo": f"Mudar {lead.nome}", "form": form, "lead": lead})


def _ficha(request, lead, form, status=200):
    hoje = timezone.localdate()
    return render(request, "leads/ficha.html", {
        "titulo": lead.nome, "lead": lead, "form": form,
        "contatos": lead.contatos.select_related("autor"),
        "atrasado": lead.atrasado(hoje),
        "pode_trabalhar": request.user.has_perm(TRABALHAR),
        "pode_converter": (request.user.has_perm(TRABALHAR)
                           and request.user.has_perm("projetos.editar_projetos")
                           and lead.aberto),
    }, status=status)


@login_required
@permission_required(VER, raise_exception=True)
def ficha(request, pk):
    lead = get_object_or_404(Lead.objects.select_related("responsavel", "projeto"), pk=pk)
    form = ContatoForm(initial={
        "etapa": Lead.Etapa.CONTATO if lead.etapa == Lead.Etapa.NOVO else lead.etapa,
        "proximo_contato": timezone.localdate() + timedelta(days=2),
    })
    return _ficha(request, lead, form)


@login_required
@permission_required(TRABALHAR, raise_exception=True)
@require_POST
def contato(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    form = ContatoForm(request.POST)
    if not form.is_valid():
        return _ficha(request, lead, form, status=400)
    antes = _foto(lead)
    servicos.registrar_contato(lead, form.cleaned_data, request.user)
    registrar("lead.contato", usuario=request.user, recurso=lead, antes=antes, depois=_foto(lead))
    messages.success(request, "Contato registrado." + (
        f" Próximo: {lead.proximo_contato:%d/%m/%Y}." if lead.proximo_contato else ""))
    return redirect("leads:ficha", pk=pk)


@login_required
@permission_required(TRABALHAR, raise_exception=True)
@require_POST
def converter(request, pk):
    if not request.user.has_perm("projetos.editar_projetos"):
        raise PermissionDenied
    lead = get_object_or_404(Lead, pk=pk)
    if not lead.aberto:
        messages.error(request, "Este lead já está fechado.")
        return redirect("leads:ficha", pk=pk)
    antes = _foto(lead)
    projeto = servicos.converter_em_projeto(lead, request.user)
    registrar("lead.convertido", usuario=request.user, recurso=lead, antes=antes,
              depois={**_foto(lead), "projeto": projeto.pk})
    registrar("projeto.criado", usuario=request.user, recurso=projeto,
              depois={"de_lead": lead.pk, "cliente": projeto.cliente_nome})
    messages.success(request, f"{lead.nome} virou o projeto {projeto.codigo}. Confira os "
                              "dados, escolha a oficina e combine o prazo.")
    return redirect("projetos:editar", pk=projeto.pk)
