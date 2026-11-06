"""As telas do planejamento: visão do caixa, a pagar, a receber, fechamento, entre
empresas e ajustes. As mesmas abas do protótipo da Henriett, sem a de pedidos, que é a
tela de Pedidos (apps/projetos)."""

from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.auditoria.servicos import registrar

from . import regras
from .forms import (AvulsosFormSet, CartoesFormSet, DividasFormSet, FixosFormSet,
                    MovimentoForm, ParametrosForm)
from .models import Avulso, Cartao, CustoFixo, Divida, MovimentoEntreEmpresas, Parametros

VER = "planejamento.ver_planejamento"
EDITAR = "planejamento.editar_planejamento"
ZERO = Decimal("0")

ABAS = (
    ("planejamento:visao", "Caixa em 30 dias"),
    ("planejamento:pagar", "A pagar"),
    ("planejamento:receber", "A receber"),
    ("planejamento:fechamento", "Fechamento"),
    ("planejamento:entre_empresas", "Entre empresas"),
    ("planejamento:ajustes", "Ajustes"),
)


def _base(request, aba, titulo, **extra):
    return {"titulo": titulo, "abas": ABAS, "aba": aba,
            "pode_editar": request.user.has_perm(EDITAR), **extra}


def _mes_pedido(request, hoje):
    """O mês da tela, de ?mes=AAAA-MM; sem ele, ou inválido, o mês de hoje."""
    try:
        ano, mes = (int(x) for x in (request.GET.get("mes") or "").split("-"))
        date(ano, mes, 1)
        return ano, mes
    except ValueError:
        return hoje.year, hoje.month


def _opcoes_de_mes(hoje, antes, depois, escolhido, desde=(2026, 1)):
    opcoes = []
    for i in range(-antes, depois + 1):
        d = regras.data_no_mes(hoje.year, hoje.month - 1 + i, 1)
        if (d.year, d.month) < desde:
            continue
        opcoes.append({"valor": f"{d.year}-{d.month:02d}", "rotulo": regras.rotulo_mes(d.year, d.month),
                       "escolhido": (d.year, d.month) == escolhido})
    return opcoes


def grafico(pontos, largura=720, altura=220):
    """O saldo dia a dia em degraus, para o SVG da tela. Tudo calculado aqui."""
    esq, dir_, topo, base = 78, 12, 12, 26
    valores = [float(v) for _, v in pontos] or [0.0]
    baixo, alto = min(0.0, *valores), max(0.0, *valores)
    if alto == baixo:
        alto += 1
    folga = (alto - baixo) * 0.08
    baixo, alto = baixo - folga, alto + folga
    n = max(1, len(pontos) - 1)

    def x(i):
        return esq + (largura - esq - dir_) * i / n

    def y(v):
        return topo + (altura - topo - base) * (1 - (v - baixo) / (alto - baixo))

    caminho = f"M{x(0):.1f},{y(valores[0]):.1f}"
    for i in range(1, len(valores)):
        caminho += f" H{x(i):.1f} V{y(valores[i]):.1f}"
    area = caminho + f" V{y(baixo):.1f} H{x(0):.1f} Z"
    # Tudo vira texto com ponto aqui: número com casa decimal passado ao template sairia
    # com vírgula (pt-br) e quebraria as coordenadas do SVG.
    def t(v):
        return f"{v:.1f}"

    linhas = []
    for k in range(5):
        v = baixo + (alto - baixo) * k / 4
        linhas.append({"y": t(y(v)), "rotulo": _reais_curto(v)})
    passo = max(1, -(-len(pontos) // 6))
    datas = [{"x": t(x(i)), "rotulo": f"{d:%d/%m}"} for i, (d, _) in enumerate(pontos) if i % passo == 0]
    ultimo = valores[-1]
    return {"largura": str(largura), "altura": str(altura), "esq": str(esq), "rotulo_x": str(esq - 6),
            "dir": str(largura - dir_), "caminho": caminho, "area": area, "linhas": linhas,
            "datas": datas, "zero": t(y(0)), "rotulo_y": str(altura - 8),
            "fim_x": t(x(len(valores) - 1)), "fim_y": t(y(ultimo)), "negativo": ultimo < 0}


def _reais_curto(v):
    v = round(v / 100) * 100
    texto = f"{abs(v):,.0f}".replace(",", ".")
    return ("−" if v < 0 else "") + "R$ " + texto


# -----------------------------------------------------------------------------------

@login_required
@permission_required(VER, raise_exception=True)
def visao(request):
    contexto = regras.Contexto.carregar()
    lista = regras.pedidos()
    proj = regras.projecao(lista, contexto, 30)
    avisos = regras.alertas(lista, contexto, proj)
    fech = regras.fechar(contexto.hoje.year, contexto.hoje.month, lista, contexto)
    graves = [a for a in avisos if a.gravidade != "info"]
    p = contexto.parametros
    saldo_velho = p.saldo_em is None or (contexto.hoje - p.saldo_em).days > 7
    return render(request, "planejamento/visao.html", _base(
        request, "planejamento:visao", "Caixa em 30 dias",
        proj=proj, grafico=grafico(proj.pontos), avisos=graves[:14], mais=len(graves) - 14,
        incompletos=sum(1 for a in avisos if a.gravidade == "info"),
        fech=fech, parametros=p, saldo_velho=saldo_velho, pedidos=len(lista),
        ponto=regras.ponto_de_equilibrio(lista, contexto),
        margem_media=regras.margem_media(lista, contexto),
        fixos_mes=regras.fixos_por_mes(contexto),
    ))


@login_required
@permission_required(VER, raise_exception=True)
def pagar(request):
    contexto = regras.Contexto.carregar()
    ano, mes = _mes_pedido(request, contexto.hoje)
    inicio, fim = regras.limites_do_mes(ano, mes)
    agenda = regras.todas_as_saidas(regras.pedidos(), contexto)
    itens = [s for s in agenda.saidas if inicio <= s.data <= fim] + regras.saidas_fixas(inicio, fim, contexto)
    itens.sort(key=lambda s: (s.data, s.grupo))
    grupos = {}
    for s in itens:
        grupos[s.grupo] = grupos.get(s.grupo, ZERO) + s.valor
    total = sum(grupos.values(), ZERO)
    maior = max(grupos.values(), default=ZERO) or Decimal("1")
    barras = [{"nome": k, "valor": v, "largura": f"{float(v / maior * 100):.1f}"}
              for k, v in sorted(grupos.items(), key=lambda kv: -kv[1])]
    return render(request, "planejamento/pagar.html", _base(
        request, "planejamento:pagar", "A pagar",
        itens=itens, barras=barras, total=total, rotulo=regras.rotulo_mes(ano, mes),
        sem_data=agenda.sem_data, total_sem_data=sum((s.valor for s in agenda.sem_data), ZERO),
        meses=_opcoes_de_mes(contexto.hoje, 2, 6, (ano, mes)), hoje=contexto.hoje,
    ))


@login_required
@permission_required(VER, raise_exception=True)
def receber(request):
    contexto = regras.Contexto.carregar()
    saldos = [c for c in (regras.saldo_cliente(p, contexto) for p in regras.pedidos()) if c and c.saldo > 0]
    vencidos = [c for c in saldos if c.vencido]
    sem_data = [c for c in saldos if c.sem_data]
    previstos = sorted((c for c in saldos if not c.vencido and not c.sem_data), key=lambda c: c.data)

    def total(lista):
        return sum((c.saldo for c in lista), ZERO)

    return render(request, "planejamento/receber.html", _base(
        request, "planejamento:receber", "A receber",
        vencidos=vencidos, previstos=previstos, sem_data=sem_data, hoje=contexto.hoje,
        total_vencidos=total(vencidos), total_previstos=total(previstos), total_sem_data=total(sem_data),
    ))


@login_required
@permission_required(VER, raise_exception=True)
def fechamento(request):
    contexto = regras.Contexto.carregar()
    ano, mes = _mes_pedido(request, contexto.hoje)
    fech = regras.fechar(ano, mes, regras.pedidos(), contexto)
    return render(request, "planejamento/fechamento.html", _base(
        request, "planejamento:fechamento", "Fechamento",
        fech=fech, meses=_opcoes_de_mes(contexto.hoje, 10, 3, (ano, mes)),
        margem_minima=contexto.parametros.margem_minima,
    ))


@login_required
@permission_required(VER, raise_exception=True)
def entre_empresas(request):
    form = MovimentoForm(request.POST or None, initial={"data": timezone.localdate()})
    if request.method == "POST":
        if not request.user.has_perm(EDITAR):
            return render(request, "403.html", status=403)
        if form.is_valid():
            mov = form.save(commit=False)
            mov.criado_por = request.user
            mov.save()
            registrar("planejamento.entre_empresas", usuario=request.user, recurso=mov,
                      depois={"data": mov.data.isoformat(), "tipo": mov.tipo, "sentido": mov.sentido,
                              "empresa": mov.empresa, "valor": str(mov.valor), "descricao": mov.descricao})
            messages.success(request, "Movimento lançado.")
            return redirect("planejamento:entre_empresas")
    meses, saldo, prolabore = regras.entre_empresas()
    return render(request, "planejamento/entre_empresas.html", _base(
        request, "planejamento:entre_empresas", "Entre empresas",
        form=form, meses=meses, saldo=saldo, saldo_abs=abs(saldo), prolabore=prolabore,
    ), status=400 if request.method == "POST" else 200)


@login_required
@permission_required(EDITAR, raise_exception=True)
@require_POST
def cancelar_movimento(request, pk):
    mov = get_object_or_404(MovimentoEntreEmpresas, pk=pk, cancelado_em__isnull=True)
    mov.cancelado_em = timezone.now()
    mov.cancelado_por = request.user
    mov.save(update_fields=["cancelado_em", "cancelado_por"])
    registrar("planejamento.entre_empresas_cancelado", usuario=request.user, recurso=mov,
              antes={"valor": str(mov.valor), "data": mov.data.isoformat()})
    messages.success(request, "Movimento cancelado. Ele sai das contas e fica no histórico da auditoria.")
    return redirect("planejamento:entre_empresas")


BLOCOS = {
    "cartoes": (CartoesFormSet, Cartao, "Cartões"),
    "fixos": (FixosFormSet, CustoFixo, "Custos fixos e empréstimos"),
    "dividas": (DividasFormSet, Divida, "Dívidas e juros"),
    "avulsos": (AvulsosFormSet, Avulso, "Saídas avulsas"),
}


@login_required
@permission_required(VER, raise_exception=True)
def ajustes(request):
    """Cinco blocos, cada um com o seu botão de salvar: o bloco com erro volta preenchido,
    e os outros continuam como estão no banco."""
    parametros = Parametros.atual()
    bloco = request.POST.get("bloco") if request.method == "POST" else None
    if bloco and not request.user.has_perm(EDITAR):
        return render(request, "403.html", status=403)
    form = ParametrosForm(request.POST if bloco == "parametros" else None, instance=parametros,
                          prefix="parametros")
    conjuntos = {}
    for chave, (classe, modelo, _) in BLOCOS.items():
        conjuntos[chave] = classe(request.POST if bloco == chave else None,
                                  queryset=modelo.objects.all(), prefix=chave)
    status = 200
    if bloco == "parametros":
        if form.is_valid():
            antes = {campo: str(getattr(parametros, campo)) for campo in form.changed_data}
            form.save()
            registrar("planejamento.ajustes", usuario=request.user, recurso=parametros, antes=antes,
                      depois={campo: str(form.cleaned_data[campo]) for campo in form.changed_data})
            messages.success(request, "Regras salvas.")
            return redirect("planejamento:ajustes")
        status = 400
    elif bloco in conjuntos:
        conjunto = conjuntos[bloco]
        if conjunto.is_valid():
            salvos = conjunto.save()
            if salvos:
                registrar(f"planejamento.ajustes_{bloco}", usuario=request.user,
                          depois={"itens": [str(o) for o in salvos]})
            messages.success(request, f"{BLOCOS[bloco][2]}: salvo.")
            return redirect(f"{request.path}#{bloco}")
        status = 400
    return render(request, "planejamento/ajustes.html", _base(
        request, "planejamento:ajustes", "Ajustes do planejamento",
        form=form, conjuntos=[(chave, BLOCOS[chave][2], conjuntos[chave]) for chave in BLOCOS],
        fixos_mes=regras.fixos_por_mes(regras.Contexto.carregar()),
    ), status=status)
