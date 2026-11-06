"""Telas de pedidos sob medida e de oficinas parceiras."""

import csv
from decimal import Decimal

from django.contrib import messages
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.auditoria.servicos import registrar

from apps.planejamento import regras

from . import servicos
from .forms import ProjetoForm, OficinaForm
from .models import Oficina, Projeto

VER = "projetos.ver_projetos"
EDITAR = "projetos.editar_projetos"


def _foto(projeto):
    """O que vai para o "antes" e o "depois" da auditoria."""
    return {
        "etapa": projeto.etapa, "titulo": projeto.titulo, "cliente": projeto.cliente_nome,
        "oficina": projeto.oficina.nome if projeto.oficina_id else "",
        "valor_venda": str(projeto.valor_venda), "custo_oficina": str(projeto.custo_oficina),
        "outros_custos": str(projeto.outros_custos), "numero": projeto.numero,
        "recebido": str(projeto.recebido), "saldo_forma": projeto.saldo_forma,
        "regime": projeto.regime, "incluir": projeto.incluir,
        **{campo: (getattr(projeto, campo).isoformat() if getattr(projeto, campo) else None)
           for campo in ("prazo_entrega", "entregue_em", "data_venda", "repasse", "pg1_data", "pg2_data")},
    }


def _anotar(projetos, contexto):
    """Põe em cada pedido o que a lista e a ficha mostram: atraso, margem, saldo, pendências."""
    for projeto in projetos:
        projeto.atraso = projeto.dias_de_atraso(contexto.hoje)
        projeto.m = regras.margem(projeto, contexto)
        projeto.saldo = regras.saldo_cliente(projeto, contexto)
        projeto.falta = regras.faltando(projeto) if projeto.vendido else []
    return projetos


def _listar(request):
    filtro = request.GET.get("filtro") or servicos.FILTRO_PADRAO
    if filtro not in {chave for chave, _, _ in servicos.FILTROS}:
        filtro = servicos.FILTRO_PADRAO
    busca = (request.GET.get("busca") or "").strip()[:80]
    contexto = regras.Contexto.carregar()
    vendidos = regras.pedidos()
    avisos = regras.alertas(vendidos, contexto)
    alertados = {a.projeto.pk for a in avisos if a.projeto and a.gravidade != "info"}
    incompletos = {p.pk for p in vendidos if p.incluir and regras.faltando(p)}
    projetos = list(servicos.filtrar(filtro, contexto.hoje, busca)[:400])
    if filtro == "alerta":
        projetos = [p for p in projetos if p.pk in alertados]
    elif filtro == "incompletos":
        projetos = [p for p in projetos if p.pk in incompletos]
    _anotar(projetos, contexto)
    for projeto in projetos:
        projeto.com_alerta = projeto.pk in alertados
    return filtro, busca, contexto, projetos, servicos.resumir(contexto, vendidos, alertados, incompletos)


@login_required
@permission_required(VER, raise_exception=True)
def lista(request):
    filtro, busca, contexto, projetos, resumo = _listar(request)
    return render(request, "projetos/lista.html", {
        "titulo": "Pedidos",
        "resumo": resumo,
        "projetos": projetos,
        "filtro": filtro,
        "busca": busca,
        "margem_minima": contexto.parametros.margem_minima,
        "pode_editar": request.user.has_perm(EDITAR),
    })


def _br(valor):
    if valor is None:
        return ""
    return f"{valor:.2f}".replace(".", ",")


@login_required
@permission_required(VER, raise_exception=True)
def lista_em_arquivo(request):
    """A lista do filtro aberto, em CSV para o Excel em português (ponto e vírgula, BOM)."""
    filtro, _, contexto, projetos, _ = _listar(request)
    resposta = HttpResponse(content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = (
        f'attachment; filename="pedidos-{filtro}-{contexto.hoje:%Y-%m-%d}.csv"')
    resposta.write("\ufeff")
    escritor = csv.writer(resposta, delimiter=";")
    escritor.writerow(["Pedido", "Cliente", "Oficina", "Regra", "Etapa", "Entrega prevista",
                       "Entregue em", "Venda", "Recebido", "Saldo do cliente (Pix)",
                       "Forma do saldo", "Custo oficina", "Margem %", "Pendências do card",
                       "Observação"])
    for p in projetos:
        escritor.writerow([
            p.codigo, p.cliente_nome, p.oficina.nome if p.oficina_id else "",
            Projeto.Regime(p.regime_efetivo).label, p.get_etapa_display(),
            p.prazo_entrega.strftime("%d/%m/%Y") if p.prazo_entrega else "",
            p.entregue_em.strftime("%d/%m/%Y") if p.entregue_em else "",
            _br(p.valor_venda), _br(p.recebido), _br(p.saldo.saldo) if p.saldo else "",
            p.get_saldo_forma_display(), _br(p.custo_oficina),
            _br(p.m.percentual) if p.m else "", ", ".join(p.falta), p.observacao,
        ])
    return resposta


@login_required
@permission_required(EDITAR, raise_exception=True)
def novo(request):
    form = ProjetoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        projeto = form.save(commit=False)
        projeto.criado_por = request.user
        projeto.save()
        registrar("projeto.criado", usuario=request.user, recurso=projeto, depois=_foto(projeto))
        messages.success(request, f"Pedido {projeto.codigo} criado.")
        return redirect("projetos:ficha", pk=projeto.pk)
    return render(request, "projetos/form_pedido.html", {
        "titulo": "Pedido novo", "form": form, "voltar": "projetos:lista",
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
        messages.success(request, f"Pedido {projeto.codigo} salvo.")
        return redirect("projetos:ficha", pk=projeto.pk)
    return render(request, "projetos/form_pedido.html", {
        "titulo": f"Mudar {projeto.codigo}", "form": form, "projeto": projeto,
    })


@login_required
@permission_required(VER, raise_exception=True)
def ficha(request, pk):
    projeto = get_object_or_404(
        Projeto.objects.select_related("oficina", "responsavel", "pg1_cartao"), pk=pk)
    contexto = regras.Contexto.carregar()
    _anotar([projeto], contexto)
    agenda = regras.agenda_oficina(projeto, contexto)
    avisos = [a for a in regras.alertas([projeto], contexto, proj=_sem_caixa(contexto))
              if a.projeto is not None]
    return render(request, "projetos/ficha.html", {
        "titulo": (f"{projeto.codigo} · {projeto.titulo}"
                   if projeto.titulo and projeto.titulo != projeto.codigo
                   else f"{projeto.codigo} · {projeto.cliente_nome}"),
        "projeto": projeto,
        "atraso": projeto.atraso,
        "agenda": agenda,
        "total_oficina": sum((s.valor for s in agenda.saidas + agenda.sem_data), Decimal("0")),
        "avisos": avisos,
        "hoje": contexto.hoje,
        "etapas": Projeto.Etapa.choices,
        "pode_editar": request.user.has_perm(EDITAR),
        "leads": projeto.leads.all(),
    })


def _sem_caixa(contexto):
    """Uma projeção vazia: na ficha de um pedido o alerta de caixa não é dele."""
    return regras.Projecao([], [], Decimal("0"), contexto.hoje, Decimal("0"), Decimal("0"), Decimal("0"))


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
def pagar(request, pk):
    """Marca a 1ª ou a 2ª parcela da oficina como paga hoje, ou desfaz a marca."""
    projeto = get_object_or_404(Projeto, pk=pk)
    qual = request.POST.get("parcela")
    if qual not in ("pg1", "pg2"):
        messages.error(request, "Escolha a 1ª ou a 2ª parcela.")
        return redirect("projetos:ficha", pk=pk)
    campo = f"{qual}_data"
    antes = _foto(projeto)
    hoje = timezone.localdate()
    if request.POST.get("desfazer"):
        setattr(projeto, campo, None)
        aviso = "Parcela voltou para em aberto."
    else:
        setattr(projeto, campo, hoje)
        aviso = ("1ª parcela paga hoje, no cartão " + (str(projeto.pg1_cartao) if projeto.pg1_cartao_id
                                                       else "padrão") + "." if qual == "pg1"
                 else "2ª parcela paga hoje em Pix.")
    projeto.save(update_fields=[campo, "atualizado_em"])
    registrar("projeto.oficina_paga", usuario=request.user, recurso=projeto,
              antes=antes, depois=_foto(projeto))
    messages.success(request, aviso)
    return redirect("projetos:ficha", pk=pk)


# Oficinas ------------------------------------------------------------------------------

@login_required
@permission_required(VER, raise_exception=True)
def oficinas(request):
    lista_ = list(Oficina.objects.annotate(
        em_andamento=Count("projetos", filter=Q(projetos__etapa__in=Projeto.EM_ANDAMENTO),
                           distinct=True),
        entregues=Count("projetos", filter=Q(projetos__etapa=Projeto.Etapa.ENTREGUE), distinct=True),
    ))
    contexto = regras.Contexto.carregar()
    a_pagar = {}
    agenda = regras.todas_as_saidas(regras.pedidos(), contexto)
    for saida in agenda.saidas + agenda.sem_data:
        if saida.data is None or saida.data >= contexto.hoje:
            chave = saida.projeto.oficina_id
            a_pagar[chave] = a_pagar.get(chave, Decimal("0")) + saida.valor
    for oficina_ in lista_:
        oficina_.a_pagar = a_pagar.get(oficina_.pk)
    return render(request, "projetos/oficinas.html", {
        "titulo": "Oficinas parceiras", "oficinas": lista_,
        "pode_editar": request.user.has_perm(EDITAR),
    })


@login_required
@permission_required(VER, raise_exception=True)
def oficina(request, pk):
    oficina_ = get_object_or_404(Oficina, pk=pk)
    hoje = timezone.localdate()
    projetos = list(oficina_.projetos.select_related("responsavel", "oficina", "pg1_cartao").order_by("-criado_em"))
    for projeto in projetos:
        projeto.atraso = projeto.dias_de_atraso(hoje)
    contexto = regras.Contexto.carregar()
    agenda = regras.todas_as_saidas([p for p in projetos if p.vendido], contexto)
    proximas = sorted((s for s in agenda.saidas if s.data >= hoje), key=lambda s: s.data)
    return render(request, "projetos/oficina.html", {
        "titulo": oficina_.nome, "oficina": oficina_, "projetos": projetos,
        "pago": sum((s.valor for s in agenda.saidas if s.data < hoje), Decimal("0")),
        "a_pagar": sum((s.valor for s in proximas + agenda.sem_data), Decimal("0")),
        "proximas": proximas, "sem_data": agenda.sem_data,
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
                  recurso=oficina_, depois={"nome": oficina_.nome, "ativa": oficina_.ativa,
                                            "pagamento": oficina_.pagamento,
                                            "dia_pagamento": oficina_.dia_pagamento,
                                            "dia_corte": oficina_.dia_corte})
        messages.success(request, f"Oficina {oficina_.nome} salva.")
        return redirect("projetos:oficina", pk=oficina_.pk)
    return render(request, "projetos/form.html", {
        "titulo": "Oficina nova" if oficina_ is None else f"Mudar {oficina_.nome}",
        "form": form, "voltar": "projetos:oficinas",
    })
