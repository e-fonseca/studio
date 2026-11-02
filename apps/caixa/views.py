"""Telas do caixa: a lista de turnos, o detalhe de um turno e os descontos.

Pedido do Edson em 08/10/2026. São duas telas porque a lista responde "como foram os
caixas" e o detalhe responde "por que este não fechou" — misturar as duas daria uma
página de cinquenta mil linhas.

Os descontos e as metas (1.46.0, pedido de 02/11/2026) têm permissão própria: quem
confere a gaveta no dia a dia não é quem aprova desconto fora da regra.
"""

from decimal import Decimal
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.auditoria.servicos import registrar
from apps.importacao import servicos as importacao_servicos
from apps.importacao.models import VendaImportada

from . import descontos, dinheiro, feriados, servicos
from .forms import AprovacaoForm, RegraDeDescontoForm
from .models import CaixaImportado, DescontoAprovado, RegraDeDesconto

PERMISSAO = "caixa.ver_caixa"
PERMISSAO_DESCONTOS = "caixa.controlar_descontos"


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


def _endereco_dos_descontos(periodo, quem):
    """Volta para a tela de descontos no mesmo período e na mesma pessoa."""
    filtros = {chave: valor for chave, valor in (("periodo", periodo), ("quem", quem)) if valor}
    endereco = reverse("caixa:descontos")
    return f"{endereco}?{urlencode(filtros)}" if filtros else endereco


@login_required
@permission_required(PERMISSAO_DESCONTOS, raise_exception=True)
def descontos_e_metas(request):
    """As vendas com desconto contra as regras da loja, e as metas do fim de semana."""
    estado = importacao_servicos.estado_dos_dados()
    tela = descontos.montar(
        estado.importacao,
        periodo=request.GET.get("periodo", descontos.PERIODO_PADRAO),
        quem=(request.GET.get("quem") or "").strip(),
    )
    contexto = _base("Descontos e metas")
    contexto.update({
        "t": tela,
        "regra": tela.regra,
        "periodos": descontos.PERIODOS,
        "nomes_que_autorizam": tela.regra.nomes_de_quem_autoriza(),
        "voltar": _endereco_dos_descontos(tela.periodo if tela.periodo != descontos.PERIODO_PADRAO else "",
                                          tela.filtro_quem),
    })
    return render(request, "caixa/descontos.html", contexto)


def _como_estava(regra):
    """Os valores da regra como texto, com dois decimais: 12000 e 12000.00 são a mesma meta."""
    def texto(valor):
        return f"{valor:.2f}" if isinstance(valor, Decimal) else str(valor)
    return {nome: texto(getattr(regra, nome)) for nome in RegraDeDescontoForm.Meta.fields}


@login_required
@permission_required(PERMISSAO_DESCONTOS, raise_exception=True)
def regras_de_desconto(request):
    """As regras de desconto e as metas, que a gerência muda sem programador."""
    regra = RegraDeDesconto.atual()
    antes = _como_estava(regra)
    form = RegraDeDescontoForm(request.POST or None, instance=regra)
    if request.method == "POST" and form.is_valid():
        regra = form.save(commit=False)
        regra.atualizada_por = request.user
        regra.save()
        depois = _como_estava(regra)
        mudou = {nome: depois[nome] for nome in depois if depois[nome] != antes[nome]}
        if mudou:
            registrar("caixa.regras_de_desconto_mudadas", usuario=request.user, recurso=regra,
                      antes={nome: antes[nome] for nome in mudou}, depois=mudou)
            messages.success(request, "Regras salvas. A tela de descontos já confere as vendas com elas.")
        else:
            messages.info(request, "Nada mudou nas regras.")
        return redirect("caixa:descontos")
    hoje = timezone.localdate()
    conhecidos = feriados.feriados_entre(hoje.replace(month=1, day=1), hoje.replace(month=12, day=31),
                                         regra.outros_feriados)
    contexto = _base("Regras de desconto e metas")
    contexto.update({
        "form": form,
        "regra": regra,
        "ano": hoje.year,
        "feriados_do_ano": sorted(conhecidos.items()),
    })
    return render(request, "caixa/regras_de_desconto.html", contexto)


@login_required
@permission_required(PERMISSAO_DESCONTOS, raise_exception=True)
@require_POST
def aprovar_desconto(request):
    """Anota quem do grupo aprovou a venda que saiu da regra."""
    regra = RegraDeDesconto.atual()
    form = AprovacaoForm(request.POST, nomes=regra.nomes_de_quem_autoriza())
    voltar = _endereco_dos_descontos(request.POST.get("periodo", ""), request.POST.get("quem", ""))
    if not form.is_valid():
        messages.error(request, "Escolha quem aprovou no grupo; a venda continua na lista.")
        return redirect(voltar)
    estado = importacao_servicos.estado_dos_dados()
    venda = None
    if estado.importacao is not None:
        venda = (VendaImportada.objects.filter(importacao=estado.importacao, id_set=form.cleaned_data["venda"])
                 .prefetch_related("itens").first())
    if venda is None:
        messages.error(request, "Essa venda não está na última importação do SET.")
        return redirect(voltar)
    avaliada = descontos.avaliar(venda, regra)
    # Quem barra a segunda aprovação é o banco (uma_aprovacao_valendo_por_venda), e não uma
    # consulta antes: duas pessoas anotando a mesma venda no mesmo segundo passariam as duas
    # pela consulta, e a segunda veria a tela de erro.
    try:
        with transaction.atomic():
            aprovacao = DescontoAprovado.objects.create(
                id_venda=venda.id_set, numero=venda.numero, dia=venda.data, valor_da_venda=venda.valor,
                desconto=avaliada.desconto, autorizado_por=form.cleaned_data["autorizado_por"],
                observacao=form.cleaned_data["observacao"].strip(), registrado_por=request.user,
            )
    except IntegrityError:
        messages.info(request, f"A venda {venda.numero} já estava com a aprovação anotada.")
        return redirect(voltar)
    registrar("caixa.desconto_aprovado", usuario=request.user, recurso=aprovacao, depois={
        "venda": venda.numero, "dia": venda.data.isoformat(), "valor": str(venda.valor),
        "desconto": str(avaliada.desconto), "porcentagem": str(avaliada.percentual),
        "autorizado_por": aprovacao.autorizado_por, "observacao": aprovacao.observacao,
    })
    messages.success(request, f"Venda {venda.numero}: aprovação de {aprovacao.autorizado_por} anotada.")
    return redirect(voltar)


@login_required
@permission_required(PERMISSAO_DESCONTOS, raise_exception=True)
@require_POST
def desfazer_aprovacao(request, pk):
    """Tira a aprovação anotada por engano: a venda volta para a lista. Nada se apaga."""
    aprovacao = get_object_or_404(DescontoAprovado, pk=pk, desfeito_em__isnull=True)
    aprovacao.desfeito_em = timezone.now()
    aprovacao.desfeito_por = request.user
    aprovacao.save(update_fields=["desfeito_em", "desfeito_por"])
    registrar("caixa.aprovacao_desfeita", usuario=request.user, recurso=aprovacao, antes={
        "venda": aprovacao.numero, "autorizado_por": aprovacao.autorizado_por,
        "observacao": aprovacao.observacao,
    })
    messages.success(request, f"Venda {aprovacao.numero}: a aprovação foi desfeita e ela voltou para a lista.")
    return redirect(_endereco_dos_descontos(request.POST.get("periodo", ""), request.POST.get("quem", "")))
