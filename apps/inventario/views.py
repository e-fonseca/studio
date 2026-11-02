"""Telas do inventário: abrir uma contagem, contar com o leitor e fechar com a lista de ajustes."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.auditoria.servicos import registrar_arquivo
from apps.core import pdf, planilha
from apps.importacao import servicos as importacao_servicos

from . import conferencia, relatorio, servicos
from . import organizar as organizar_servicos
from . import plano as plano_de_contagem
from .models import Contagem, ItemContado

PERMISSAO = "inventario.contar_estoque"
# A tela Organizar e os relatórios mostram custo e valor da peça, então ficam fora do
# alcance do vendedor, que vê UMA tela e nenhum dinheiro. Quem conta é quem classifica:
# é trabalho de quem está na loja com a peça na mão, não da gerência de longe.
GERENCIA = "inventario.fechar_contagem"


def _base(titulo):
    estado = importacao_servicos.estado_dos_dados()
    return {"titulo": titulo, "estado": estado, "importacao": estado.importacao}


@login_required
@permission_required(PERMISSAO, raise_exception=True)
def lista(request):
    contexto = _base("Inventário")
    estado = contexto["estado"]
    contexto.update({
        "contagens": servicos.contagens()[:30],
        "aberta": servicos.em_andamento(),
        "endereco_seguro_base": _endereco_seguro(request).replace(request.path, "/sistema/"),
        # O plano de contagem é a decisão desta tela: o que está vencido e o que contar
        # agora. Vem antes do texto que explica para que serve contar.
        "plano": plano_de_contagem.montar(estado.importacao),
        "pendencias": organizar_servicos.contar_por_estado(),
        "pode_organizar": request.user.has_perm(GERENCIA),
    })
    return render(request, "inventario/lista.html", contexto)


@login_required
@permission_required(PERMISSAO, raise_exception=True)
@require_POST
def abrir(request):
    nome = (request.POST.get("nome") or "").strip()
    if not nome:
        messages.error(request, "Dê um nome à contagem, como “prateleira dos tapetes”, "
                                "para depois saber o que foi contado.")
        return redirect("inventario:lista")
    contagem = servicos.abrir(nome, request.user, (request.POST.get("observacao") or "").strip())
    messages.success(request, f"Contagem “{contagem.nome}” aberta. Pode começar a passar o leitor.")
    return redirect("inventario:contagem", pk=contagem.pk)


@login_required
@permission_required(PERMISSAO, raise_exception=True)
def contagem(request, pk):
    achada = servicos.consultar(pk)
    if achada is None:
        raise Http404("Essa contagem não existe.")
    contexto = _base(achada.nome)
    resumo = servicos.resumir(achada)
    contexto.update({
        "contagem": achada,
        "itens": list(achada.itens.all()),
        "resumo": resumo,
        "faltam": servicos.produtos_nao_contados(achada),
        "estados": ItemContado.Estado,
        "estados_na_prateleira": organizar_servicos.na_prateleira(),
        "pode_organizar": request.user.has_perm(GERENCIA),
        # Se os ajustes já foram digitados no SET, quem responde é a importação
        # seguinte, que lê o backup novo. Ver apps/inventario/conferencia.py.
        "conferencia": conferencia.conferir(achada, resumo),
    })
    return render(request, "inventario/contagem.html", contexto)


@login_required
@permission_required(PERMISSAO, raise_exception=True)
@require_POST
def contar(request, pk):
    achada = get_object_or_404(Contagem, pk=pk)
    try:
        item = servicos.registrar_contagem(
            achada,
            termo=(request.POST.get("produto") or "").strip(),
            quantidade=servicos.quantidade_informada(request.POST.get("quantidade")),
            usuario=request.user,
            observacao=(request.POST.get("observacao") or "").strip(),
        )
    except servicos.ErroDeContagem as erro:
        messages.error(request, str(erro))
    else:
        diferenca = item.diferenca
        if diferenca == 0:
            aviso = "bate com o SET."
        elif diferenca < 0:
            aviso = f"faltam {-diferenca:f} em relação ao SET."
        else:
            aviso = f"sobram {diferenca:f} em relação ao SET."
        messages.success(request, f"{item.descricao}: {item.quantidade:f} contado, {aviso}")
    return redirect("inventario:contagem", pk=achada.pk)


@login_required
@permission_required(PERMISSAO, raise_exception=True)
def camera(request, pk):
    """Contagem pelo celular, com a câmera lendo a etiqueta de código de barras.

    Esta tela é a mesma contagem da tela do computador, só que a mão fica livre: a
    câmera lê o código e a pessoa digita a quantidade. Vale pelo wi-fi da loja, sem
    VPN, mas só pelo endereço seguro (https), porque o navegador não libera a câmera
    fora dele. Quando não dá (navegador antigo, endereço sem https), a tela explica o
    que fazer e continua aceitando o código digitado à mão.
    """
    achada = servicos.consultar(pk)
    if achada is None:
        raise Http404("Essa contagem não existe.")
    contexto = _base(f"Contar pela câmera · {achada.nome}")
    contexto.update({
        "contagem": achada,
        "resumo": servicos.resumir(achada),
        "ultimos": list(achada.itens.all()[:15]),
        "endereco_seguro": _endereco_seguro(request),
    })
    return render(request, "inventario/camera.html", contexto)


def _endereco_seguro(request):
    """O mesmo endereço desta tela, em https, para quem abriu em http se mudar para lá.

    A porta segura é outra (8443 por padrão), então não basta trocar o http por https.
    """
    porta = str(getattr(settings, "PORTA_HTTPS", "") or "")
    maquina = request.get_host().split(":")[0]
    destino = f"{maquina}:{porta}" if porta else maquina
    return f"https://{destino}{request.path}"


@login_required
@permission_required(PERMISSAO, raise_exception=True)
@require_POST
def contar_pela_camera(request, pk):
    """Registra uma leitura sem recarregar a página: recarregar desliga a câmera.

    Responde em JSON com o que a tela precisa mostrar: o produto, o que estava no SET,
    a diferença e o resumo atualizado.
    """
    achada = get_object_or_404(Contagem, pk=pk)
    try:
        item = servicos.registrar_contagem(
            achada,
            termo=(request.POST.get("produto") or "").strip(),
            quantidade=servicos.quantidade_informada(request.POST.get("quantidade")),
            usuario=request.user,
            observacao=(request.POST.get("observacao") or "").strip(),
        )
    except servicos.ErroDeContagem as erro:
        return JsonResponse({"ok": False, "erro": str(erro)}, status=200)
    resumo = servicos.resumir(achada)
    diferenca = item.diferenca
    if diferenca == 0:
        recado = "bate com o SET"
    elif diferenca < 0:
        recado = f"faltam {-diferenca:f} em relação ao SET"
    else:
        recado = f"sobram {diferenca:f} em relação ao SET"
    return JsonResponse({
        "ok": True,
        "produto": {
            # O id volta para a tela poder prender a foto neste item logo depois.
            "id": item.pk,
            "foto": reverse("inventario:guardar_foto", args=[achada.pk, item.pk]),
            # Para a tela poder marcar "sem etiqueta" ou "danificada" na peça que acabou
            # de ser lida, sem recarregar e sem desligar a câmera.
            "estado_em": reverse("inventario:estado", args=[achada.pk, item.pk]),
            "estado": item.estado,
            "codigo": item.codigo,
            "descricao": item.descricao,
            "contado": f"{item.quantidade:f}",
            "saldo_set": f"{item.saldo_set:f}",
            "diferenca": f"{diferenca:f}",
            "bate": item.bate,
            "recado": recado,
        },
        "resumo": {
            "contados": resumo.contados,
            "divergentes": resumo.divergentes,
        },
    })


@login_required
@permission_required(PERMISSAO, raise_exception=True)
@require_POST
def remover(request, pk, item_pk):
    item = get_object_or_404(ItemContado, pk=item_pk, contagem_id=pk)
    try:
        servicos.apagar_item(item, request.user)
    except servicos.ErroDeContagem as erro:
        messages.error(request, str(erro))
    else:
        messages.success(request, f"{item.descricao} saiu da contagem.")
    return redirect("inventario:contagem", pk=pk)


@login_required
@permission_required("inventario.fechar_contagem", raise_exception=True)
@require_POST
def fechar(request, pk):
    achada = get_object_or_404(Contagem, pk=pk)
    try:
        servicos.fechar(achada, request.user)
    except servicos.ErroDeContagem as erro:
        messages.error(request, str(erro))
    else:
        messages.success(
            request,
            "Contagem fechada. A lista de ajustes está aqui embaixo: o acerto do saldo é "
            "digitado no SET, que é onde o estoque vale.",
        )
    return redirect("inventario:contagem", pk=achada.pk)


@login_required
@permission_required("inventario.fechar_contagem", raise_exception=True)
def ajustes(request, pk):
    """A lista de divergências em texto, para abrir numa planilha ao lado do SET."""
    achada = get_object_or_404(Contagem, pk=pk)
    resposta = HttpResponse(servicos.divergencias_em_texto(achada),
                            content_type="text/tab-separated-values; charset=utf-8")
    nome = f"ajustes-contagem-{achada.pk}.tsv"
    resposta["Content-Disposition"] = f'attachment; filename="{nome}"'
    registrar_arquivo(request, nome)
    return resposta


@login_required
@permission_required(PERMISSAO, raise_exception=True)
@require_POST
def guardar_foto(request, pk, item_pk):
    """Recebe a foto tirada na tela da câmera e a guarda no item contado."""
    item = get_object_or_404(ItemContado, pk=item_pk, contagem_id=pk)
    try:
        servicos.guardar_foto(item, request.FILES.get("foto"), request.user)
    except servicos.ErroDeContagem as erro:
        return JsonResponse({"ok": False, "erro": str(erro)}, status=200)
    return JsonResponse({"ok": True, "endereco": reverse("inventario:foto", args=[pk, item.pk])})


@login_required
@permission_required(PERMISSAO, raise_exception=True)
def foto(request, pk, item_pk):
    """A foto guardada. Nunca servida direto da pasta: passa por permissão."""
    item = get_object_or_404(ItemContado, pk=item_pk, contagem_id=pk)
    if not item.foto:
        raise Http404("Esse item não tem foto.")
    return FileResponse(item.foto.open("rb"), content_type="image/jpeg")


# -- o plano de contagem e a tela Organizar ----------------------------------------
#
# Entraram na 1.39.0, a pedido dele em 22/10/2026: o padrão de inventário do varejo
# (contagem cíclica com prazo por classe), a classificação do que se acha na prateleira
# e os relatórios que saem dela.

def _formato(request):
    """Papel ou planilha, lido do endereço. Qualquer outra coisa é papel."""
    pedido = (request.GET.get("formato") or "").strip().lower()
    return "planilha" if pedido == "planilha" else "pdf"


def _entregar(request, montar, *, titulo, subtitulo, arquivo, paisagem=True, **dados):
    """Monta o relatório UMA vez e entrega em papel ou em planilha, conforme o pedido.

    O montador é o mesmo nos dois casos (apps/inventario/relatorio.py): é o que impede
    o papel e a planilha da mesma tela de dizerem números diferentes.
    """
    quem = request.user.get_full_name() or request.user.get_username()
    if _formato(request) == "planilha":
        folha = planilha.Planilha(titulo, subtitulo, paisagem=paisagem, emitido_por=quem)
        montar(folha, **dados)
        registrar_arquivo(request, f"{arquivo}.xlsx")
        return planilha.resposta(folha, f"{arquivo}.xlsx")
    papel = pdf.Relatorio(titulo, subtitulo, paisagem=paisagem, emitido_por=quem)
    montar(papel, **dados)
    registrar_arquivo(request, f"{arquivo}.pdf")
    return pdf.resposta(papel, f"{arquivo}.pdf")


def _plano_de_hoje(estado):
    return plano_de_contagem.montar(estado.importacao)


@login_required
@permission_required(PERMISSAO, raise_exception=True)
@require_POST
def abrir_sugerida(request):
    """Abre a contagem que o plano sugere, já com nome, para não ter o que digitar."""
    estado = importacao_servicos.estado_dos_dados()
    plano = _plano_de_hoje(estado)
    if not plano.sugeridos:
        messages.info(request, "Nada vencido no plano: não há contagem a abrir por aqui.")
        return redirect("inventario:lista")
    contagem = servicos.abrir(
        plano_de_contagem.nome_sugerido(plano), request.user,
        observacao="Contagem cíclica sugerida pelo plano de inventário.",
    )
    messages.success(
        request,
        f"Contagem “{contagem.nome}” aberta. A folha com os produtos a contar sai no "
        "botão “Folha de contagem” da tela Inventário.",
    )
    return redirect("inventario:contagem", pk=contagem.pk)


@login_required
@permission_required(PERMISSAO, raise_exception=True)
def folha_de_contagem(request):
    """O plano em papel ou planilha: é a folha com que se anda pela loja contando."""
    estado = importacao_servicos.estado_dos_dados()
    plano = _plano_de_hoje(estado)
    corte = getattr(estado.importacao, "data_corte", None)
    return _entregar(
        request, relatorio.montar_plano,
        titulo="Plano de inventário",
        subtitulo=("Contagem cíclica por curva ABC"
                   + (f" · saldo do SET de {corte:%d/%m/%Y}" if corte else "")),
        arquivo="plano-de-inventario", plano=plano,
    )


@login_required
@permission_required(GERENCIA, raise_exception=True)
def divergencia(request, pk):
    """O comparativo entre o que o SET diz e o que foi contado, em papel ou planilha."""
    achada = get_object_or_404(Contagem, pk=pk)
    resumo = servicos.resumir(achada)
    conferida = conferencia.conferir(achada, resumo)
    return _entregar(
        request, relatorio.montar_divergencia,
        titulo="SET contra a contagem",
        subtitulo=relatorio.subtitulo_da_divergencia(achada, resumo),
        arquivo=f"divergencia-contagem-{achada.pk}",
        contagem=achada, resumo=resumo, conferencia=conferida,
    )


@login_required
@permission_required(GERENCIA, raise_exception=True)
def organizar(request):
    """Sem etiqueta, danificados e parados, com o que fazer em cada caso."""
    estado = importacao_servicos.estado_dos_dados()
    contexto = _base("Organizar a prateleira")
    contexto.update({
        "grupos": organizar_servicos.grupos(estado.importacao),
        "estados": ItemContado.Estado,
        "meses_parado": organizar_servicos.MESES_PARADO,
        "meses_encalhado": organizar_servicos.MESES_ENCALHADO,
        "com_etiqueta": len(organizar_servicos.itens_para_etiqueta()),
    })
    return render(request, "inventario/organizar.html", contexto)


@login_required
@permission_required(GERENCIA, raise_exception=True)
@require_POST
def classificar(request, item_pk):
    """Danificado vira "para conserto" ou "para descarte": é a classificação dele."""
    item = get_object_or_404(ItemContado, pk=item_pk)
    try:
        organizar_servicos.marcar(
            item, (request.POST.get("estado") or "").strip(), request.user,
            observacao=(request.POST.get("observacao") or "").strip(),
        )
    except organizar_servicos.ErroDeOrganizacao as erro:
        messages.error(request, str(erro))
    else:
        messages.success(request, f"{item.descricao}: {item.get_estado_display().lower()}.")
    return redirect("inventario:organizar")


@login_required
@permission_required(GERENCIA, raise_exception=True)
@require_POST
def resolver(request, item_pk):
    """A providência foi tomada: o item sai da fila da tela."""
    item = get_object_or_404(ItemContado, pk=item_pk)
    desfazer = request.POST.get("desfazer")
    try:
        if desfazer:
            organizar_servicos.reabrir(item, request.user)
        else:
            organizar_servicos.resolver(item, request.user)
    except organizar_servicos.ErroDeOrganizacao as erro:
        messages.error(request, str(erro))
    else:
        if desfazer:
            messages.success(request, f"{item.descricao} voltou para a fila.")
        else:
            messages.success(request, f"{item.descricao}: resolvido.")
    return redirect("inventario:organizar")


@login_required
@permission_required(GERENCIA, raise_exception=True)
def descarte(request):
    """As peças sem aproveitamento, com a perda ao custo."""
    itens = organizar_servicos.esperando(ItemContado.Estado.DESCARTE)
    return _entregar(
        request, relatorio.montar_descarte,
        titulo="Descarte de produtos",
        subtitulo=f"{len(itens)} peças marcadas para descarte e ainda não baixadas",
        arquivo="descarte-de-produtos", itens=itens,
    )


@login_required
@permission_required(GERENCIA, raise_exception=True)
def conserto(request):
    """As peças que valem reparo e voltam para a venda."""
    itens = organizar_servicos.esperando(ItemContado.Estado.CONSERTO)
    return _entregar(
        request, relatorio.montar_conserto,
        titulo="Produtos para conserto",
        subtitulo=f"{len(itens)} peças esperando reparo",
        arquivo="produtos-para-conserto", itens=itens,
    )


@login_required
@permission_required(GERENCIA, raise_exception=True)
def parados(request):
    """Os produtos com peça na prateleira e sem venda há muito tempo."""
    estado = importacao_servicos.estado_dos_dados()
    itens = organizar_servicos.parados(estado.importacao)
    return _entregar(
        request, relatorio.montar_parados,
        titulo="Produtos parados",
        subtitulo=(f"Sem vender uma unidade há mais de "
                   f"{organizar_servicos.MESES_PARADO} meses, com peça na prateleira"),
        arquivo="produtos-parados", itens=itens,
    )


@login_required
@permission_required(GERENCIA, raise_exception=True)
def etiquetas(request):
    """A folha de etiquetas para reimprimir, uma por peça que perdeu a sua.

    Sai como página para o navegador imprimir, e não como PDF, porque o desenho do
    código de barras já existe em `apps/core/barras.py` e é o MESMO que a tela de
    consulta mostra: um segundo desenho, feito dentro do PDF, seria um segundo lugar
    onde a etiqueta pode sair errada — e etiqueta errada o leitor lê como outro produto.
    """
    itens = organizar_servicos.itens_para_etiqueta()
    contexto = _base("Etiquetas para reimprimir")
    contexto.update({
        "itens": itens,
        "sem_codigo": [
            item for item in organizar_servicos.esperando(ItemContado.Estado.SEM_ETIQUETA)
            if not item.codigo_barras
        ],
    })
    return render(request, "inventario/etiquetas.html", contexto)


# O que quem está contando pode marcar: o que se vê com a peça na mão. Conserto e
# descarte NÃO estão aqui — decidir entre os dois é da gerência, na tela Organizar, com
# o custo da peça à vista. Na hora da contagem a pessoa diria o que for mais rápido.
NA_PRATELEIRA = (
    ItemContado.Estado.OK,
    ItemContado.Estado.SEM_ETIQUETA,
    ItemContado.Estado.DANIFICADO,
)


@login_required
@permission_required(PERMISSAO, raise_exception=True)
@require_POST
def estado(request, pk, item_pk):
    """Marca como a peça foi achada: perfeita, sem etiqueta ou danificada.

    Responde em JSON para a tela da câmera, que não pode recarregar — recarregar
    desligaria a câmera, e quem está marcando "danificado" está com a outra mão
    segurando a peça. A tela do computador manda o mesmo formulário com `voltar` e
    recebe o redirecionamento de sempre.
    """
    item = get_object_or_404(ItemContado, pk=item_pk, contagem_id=pk)
    # O campo só diz que quem manda é a tela do computador, e não a da câmera: o
    # destino é escolhido aqui. Endereço vindo do formulário num redirect seria
    # redirecionamento aberto.
    da_tela = bool(request.POST.get("da_tela"))
    pedido = (request.POST.get("estado") or "").strip()
    erro = ""
    if pedido not in NA_PRATELEIRA:
        erro = ("Na contagem só dá para marcar perfeita, sem etiqueta ou danificada. "
                "Conserto e descarte são decididos na tela Organizar.")
    else:
        try:
            organizar_servicos.marcar(
                item, pedido, request.user,
                observacao=(request.POST.get("observacao") or "").strip(),
            )
        except organizar_servicos.ErroDeOrganizacao as problema:
            erro = str(problema)
    if da_tela:
        if erro:
            messages.error(request, erro)
        else:
            messages.success(
                request, f"{item.descricao}: {item.get_estado_display().lower()}.")
        return redirect("inventario:contagem", pk=pk)
    if erro:
        return JsonResponse({"ok": False, "erro": erro}, status=200)
    return JsonResponse({
        "ok": True,
        "estado": item.estado,
        "rotulo": item.get_estado_display(),
        "perfeito": item.perfeito,
    })
