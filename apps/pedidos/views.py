"""As telas dos pedidos ao fornecedor: a lista, o pedido e o que voltou dele."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.auditoria.servicos import registrar
from apps.compras.models import DadosDaEmpresa
from apps.core import pdf
from apps.fornecedores import servicos as fornecedores_servicos
from apps.importacao import servicos as importacao_servicos

from . import conferencia as conferir_documento, folha, geracao, servicos
from .models import AnexoDoPedido, Pedido

POR_PAGINA = 60


@login_required
@permission_required("pedidos.view_pedido", raise_exception=True)
def lista(request):
    """Os pedidos feitos, e os pedidos que a lista de compra de hoje geraria.

    Os dois na mesma tela porque é a tela que ele abre para falar com o fornecedor
    (pedido dele em 20/10/2026: "na tela pedidos, gerar automaticamente pedidos de
    compra mercadorias por fornecedor"). O de cima é o que falta pedir; o de baixo é
    o que já foi pedido e espera mercadoria.
    """
    situacao = (request.GET.get("situacao") or "").strip()
    fornecedor = (request.GET.get("fornecedor") or "").strip()
    pedidos = Pedido.objects.all().prefetch_related("anexos")
    if situacao in Pedido.Situacao.values:
        pedidos = pedidos.filter(situacao=situacao)
    if fornecedor:
        pedidos = pedidos.filter(fornecedor=fornecedor)
    estado = importacao_servicos.estado_dos_dados()
    previstos, lista_de_hoje = _previstos_de_hoje(request, estado)
    return render(request, "pedidos/lista.html", {
        "titulo": "Pedidos ao fornecedor",
        "estado": estado,
        "pedidos": pedidos[:POR_PAGINA],
        "quantos": pedidos.count(),
        "situacao": situacao,
        "fornecedor": fornecedor,
        "situacoes": Pedido.Situacao.choices,
        "em_aberto": servicos.em_aberto(),
        "para_aprovar": servicos.para_aprovar()[0],
        "sem_documento": servicos.sem_documento(),
        # Na tela entram os fornecedores que cabem no mês, mais os que já foram
        # pedidos hoje. Os outros são dezenas — a lista de compra tem 200 e tantos
        # fornecedores — e uma tabela com todos esconderia justamente os cinco que
        # importam hoje, que é a lição do "menos é mais" dele (19/10/2026).
        "previstos": [p for p in previstos if p.cabe_no_mes or p.ja_foi_pedido],
        "fora_do_teto": sum(1 for p in previstos if not p.cabe_no_mes
                            and not p.ja_foi_pedido),
        "lista_de_hoje": lista_de_hoje,
        "cabem_no_mes": [p for p in previstos if p.cabe_no_mes and not p.ja_foi_pedido],
        "pode_gerar": request.user.has_perm("pedidos.registrar_pedido"),
    })


def _previstos_de_hoje(request, estado):
    """Os pedidos que a lista de compra geraria agora, com o teto do mês já aplicado.

    Devolve `([], None)` sem importação concluída: a tela continua mostrando os pedidos
    guardados, que são dado nosso e não dependem da foto do SET.
    """
    if estado.importacao is None or not request.user.has_perm("compras.ver_compras"):
        return [], None
    from apps.compras import limite  # noqa: PLC0415 - evita ciclo no import
    from apps.financeiro import servicos as financeiro  # noqa: PLC0415

    teto = limite.teto_de(estado.importacao,
                          resumo_caixa=financeiro.resumir(estado.importacao))
    return geracao.previstos(estado.importacao, teto=teto)


@login_required
@permission_required("pedidos.registrar_pedido", raise_exception=True)
@require_http_methods(["POST"])
def gerar(request):
    """Faz o pedido de um fornecedor, ou de todos os que cabem no mês.

    Um clique de uma pessoa, sempre: o sistema monta tudo e não pede nada sozinho, que
    é a regra dele ("Não aprovar nem emitir pedidos automaticamente"). Sem `fornecedor`
    no formulário, saem os que cabem no que sobrou do teto do mês — os que passam do
    teto continuam possíveis um a um, porque quem decide é quem está comprando.
    """
    estado = importacao_servicos.estado_dos_dados()
    if estado.importacao is None:
        messages.error(request, "Ainda não há importação concluída para montar pedidos.")
        return redirect("pedidos:lista")

    previstos, lista_de_hoje = _previstos_de_hoje(request, estado)
    escolhido = (request.POST.get("fornecedor") or "").strip()
    if escolhido:
        previsto = geracao.um(previstos, escolhido)
        if previsto is None:
            messages.error(
                request,
                f"{escolhido} não está mais na lista de compra de hoje. Confira a "
                "lista de compra: o estoque ou a venda pode ter mudado na última "
                "sincronização.")
            return redirect("pedidos:lista")
        alvos = [previsto]
    else:
        alvos = [p for p in previstos if p.cabe_no_mes and not p.ja_foi_pedido]
        if not alvos:
            messages.info(request, "Não há pedido novo para gerar dentro do teto do mês.")
            return redirect("pedidos:lista")

    emitido_por = request.user.get_full_name() or request.user.get_username()
    guardados, pulados = geracao.gerar(
        request.user, [p.bloco for p in alvos],
        data_corte=lista_de_hoje.data_corte, emitido_por=emitido_por)
    registrar("pedido.gerado_da_tela", usuario=request.user,
              recurso_rotulo=", ".join(p.nome for p in alvos)[:200],
              depois={"fornecedores": len(alvos), "guardados": len(guardados),
                      "numeros": [p.numero for p in guardados]})
    if pulados:
        messages.error(request, f"Sem linha nenhuma para pedir a {', '.join(pulados)}.")
    esperando = "" if servicos.aprova(request.user) else ", esperando a aprovação da gerência"
    if len(guardados) == 1:
        messages.success(request,
                         f"Pedido {guardados[0].numero} de {guardados[0].fornecedor} "
                         f"guardado{esperando}, com a folha em PDF anexada.")
        return redirect("pedidos:detalhe", numero=guardados[0].numero)
    if guardados:
        messages.success(request, f"{len(guardados)} pedidos guardados{esperando}, cada um "
                                  "com a folha em PDF anexada.")
    return redirect("pedidos:lista")


@login_required
@permission_required("pedidos.view_pedido", raise_exception=True)
def detalhe(request, numero):
    """Um pedido: o que foi pedido, o que foi anexado e o que a conferência achou."""
    pedido = get_object_or_404(Pedido, numero=numero)
    anexos = []
    for anexo in pedido.anexos.all():
        anexos.append((anexo, conferir_documento.conferir(pedido, anexo) if anexo.foi_lido else None))
    return render(request, "pedidos/detalhe.html", {
        "titulo": f"Pedido {pedido.numero}",
        "estado": importacao_servicos.estado_dos_dados(),
        "pedido": pedido,
        "itens": pedido.itens.all(),
        "anexos": anexos,
        "tipos": AnexoDoPedido.Tipo.choices,
        "limite_mb": settings.ANEXO_TAMANHO_MAXIMO // (1024 * 1024),
        "ficha": fornecedores_servicos.cadastrados().get(pedido.fornecedor),
        "pode_mexer": pedido.pode_ser_mudado_por(request.user),
        "pode_aprovar": pedido.esperando_aprovacao and servicos.aprova(request.user),
    })


@login_required
@permission_required("pedidos.aprovar_pedido", raise_exception=True)
@require_http_methods(["POST"])
def aprovar(request, numero):
    """A gerência faz valer o pedido que a Líder de loja montou.

    Um clique, e a folha que vale (sem o aviso vermelho) fica anexada ao pedido, com o
    nome de quem montou e de quem aprovou. Recusar é cancelar, com o motivo: o mesmo
    caminho de qualquer pedido que não vai acontecer.
    """
    pedido = get_object_or_404(Pedido, numero=numero)
    try:
        servicos.aprovar_pedido(request.user, pedido)
    except servicos.NaoDeuCerto as erro:
        messages.error(request, str(erro))
        return redirect("pedidos:detalhe", numero=pedido.numero)
    _guardar_a_folha_nova(request, pedido)
    messages.success(request, f"Pedido {pedido.numero} aprovado. A folha que vale ficou "
                              "anexada aqui, pronta para mandar ao fornecedor.")
    return redirect("pedidos:detalhe", numero=pedido.numero)


@login_required
@permission_required("pedidos.anexar_documento", raise_exception=True)
def anexar(request, numero):
    """Recebe o romaneio ou a nota fiscal e lê o que der para ler dentro."""
    pedido = get_object_or_404(Pedido, numero=numero)
    if request.method != "POST":
        return redirect("pedidos:detalhe", numero=pedido.numero)
    arquivo = request.FILES.get("arquivo")
    if arquivo is None:
        messages.error(request, "Escolha o arquivo para anexar.")
        return redirect("pedidos:detalhe", numero=pedido.numero)
    try:
        anexo = servicos.anexar(
            request.user, pedido, arquivo,
            tipo=(request.POST.get("tipo") or "").strip(),
            observacao=(request.POST.get("observacao") or "").strip(),
            tamanho_maximo=settings.ANEXO_TAMANHO_MAXIMO,
        )
    except servicos.NaoDeuCerto as erro:
        messages.error(request, str(erro))
        return redirect("pedidos:detalhe", numero=pedido.numero)

    if anexo.itens_lidos:
        resultado = conferir_documento.conferir(pedido, anexo)
        if resultado.tudo_confere:
            messages.success(request, f"{anexo.nome_original}: {resultado.resumo}")
        else:
            messages.warning(request, f"{anexo.nome_original}: {resultado.resumo}")
    elif anexo.erro_de_leitura:
        messages.success(request, f"{anexo.nome_original} guardado. {anexo.erro_de_leitura}")
    else:
        messages.success(request, f"{anexo.nome_original} guardado.")
    return redirect("pedidos:detalhe", numero=pedido.numero)


@login_required
@permission_required("pedidos.view_pedido", raise_exception=True)
def baixar(request, numero, anexo_id):
    """Entrega o arquivo anexado. Registra quem baixou, como no anexo de processo."""
    anexo = get_object_or_404(AnexoDoPedido, pk=anexo_id, pedido__numero=numero)
    registrar("pedido.anexo_baixado", usuario=request.user, recurso=anexo.pedido,
              recurso_rotulo=f"pedido {numero} · {anexo.pedido.fornecedor}",
              depois={"anexo_id": anexo.pk, "nome": anexo.nome_original})
    resposta = FileResponse(anexo.arquivo.open("rb"), as_attachment=True,
                            filename=anexo.nome_original)
    # Arquivo que veio de fora nunca é servido para o navegador executar nada.
    resposta["Content-Security-Policy"] = "default-src 'none'"
    resposta["X-Content-Type-Options"] = "nosniff"
    return resposta


@login_required
@permission_required("pedidos.anexar_documento", raise_exception=True)
def receber(request, numero):
    """Marca que a mercadoria chegou, ou desfaz a marcação."""
    pedido = get_object_or_404(Pedido, numero=numero)
    if request.method != "POST":
        return redirect("pedidos:detalhe", numero=pedido.numero)
    recebido = (request.POST.get("recebido") or "") == "1"
    try:
        servicos.marcar_recebido(request.user, pedido, recebido=recebido)
    except servicos.NaoDeuCerto as erro:
        messages.error(request, str(erro))
        return redirect("pedidos:detalhe", numero=pedido.numero)
    if recebido:
        messages.success(request, f"Pedido {pedido.numero} marcado como recebido. "
                                  "Anexe a nota ou o romaneio para a conferência.")
    else:
        messages.success(request, f"Pedido {pedido.numero} voltou para aberto.")
    return redirect("pedidos:detalhe", numero=pedido.numero)


@login_required
@permission_required("pedidos.registrar_pedido", raise_exception=True)
def editar(request, numero):
    """Muda as quantidades de um pedido aberto e refaz a folha dele.

    Pedido do Edson em 20/10/2026. A folha nova é anexada ao pedido em vez de substituir
    a anterior: as duas ficam, com data, porque a regra dele é não eliminar histórico —
    e porque conferir a nota contra "o pedido" exige saber qual versão o fornecedor leu.
    """
    pedido = get_object_or_404(Pedido, numero=numero)
    if request.method != "POST":
        return redirect("pedidos:detalhe", numero=pedido.numero)

    quantidades = {}
    for chave, valor in request.POST.items():
        if chave.startswith("quantidade-"):
            quantidades[chave[len("quantidade-"):]] = valor
    prazo = (request.POST.get("prazo_dias") or "").strip()
    try:
        _, mudou = servicos.editar_pedido(
            request.user, pedido,
            quantidades=quantidades,
            prazo_dias=int(prazo) if prazo.isdigit() else None,
            observacao=(request.POST.get("observacao") or "").strip(),
        )
    except servicos.NaoDeuCerto as erro:
        messages.error(request, str(erro))
        return redirect("pedidos:detalhe", numero=pedido.numero)

    if not mudou:
        messages.info(request, "Nada mudou no pedido.")
        return redirect("pedidos:detalhe", numero=pedido.numero)

    pedido.refresh_from_db()
    _guardar_a_folha_nova(request, pedido)
    messages.success(request, f"Pedido {pedido.numero} alterado: {pedido.quantas_linhas} "
                              f"item(ns), {pedido.valor_total:.2f} no total. A folha nova "
                              "ficou anexada aqui.")
    return redirect("pedidos:detalhe", numero=pedido.numero)


@login_required
@permission_required("pedidos.registrar_pedido", raise_exception=True)
def cancelar(request, numero):
    """Descarta um pedido aberto, com o motivo escrito junto."""
    pedido = get_object_or_404(Pedido, numero=numero)
    if request.method != "POST":
        return redirect("pedidos:detalhe", numero=pedido.numero)
    try:
        servicos.cancelar_pedido(request.user, pedido, request.POST.get("motivo"))
    except servicos.NaoDeuCerto as erro:
        messages.error(request, str(erro))
        return redirect("pedidos:detalhe", numero=pedido.numero)
    messages.success(request, f"Pedido {pedido.numero} cancelado. O pedido e os itens "
                              "ficam guardados, com o motivo, para consulta.")
    return redirect("pedidos:detalhe", numero=pedido.numero)


@login_required
@permission_required("pedidos.view_pedido", raise_exception=True)
def imprimir(request, numero):
    """Gera de novo o pedido de compra deste pedido guardado, em PDF.

    Pedido do Edson em 20/10/2026: *"Pedido, nessa tela gerar pedido de compra de
    mercadorias"*. É a MESMA folha da lista de compra, montada a partir do que está
    guardado — e não da lista de hoje, que já mudou de lá para cá.
    """
    pedido = get_object_or_404(Pedido, numero=numero)
    relatorio = folha.montar(pedido, DadosDaEmpresa.atual(),
                             emitido_por=folha.quem_emite(pedido, request.user))
    registrar("pedido.folha_gerada", usuario=request.user, recurso=pedido,
              recurso_rotulo=f"pedido {pedido.numero} · {pedido.fornecedor}",
              depois={"itens": pedido.quantas_linhas, "valor": str(pedido.valor_total)})
    return pdf.resposta(relatorio, folha.nome_do_arquivo(pedido))


def _guardar_a_folha_nova(request, pedido):
    """Anexa ao pedido a folha que vale depois da edição. Silencioso quando repete."""
    relatorio = folha.montar(pedido, DadosDaEmpresa.atual(),
                             emitido_por=folha.quem_emite(pedido, request.user))
    servicos.guardar_a_folha(request.user, pedido, relatorio, folha.nome_do_arquivo(pedido))
