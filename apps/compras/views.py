"""Antes de comprar: a tela que se abre na hora de fechar o pedido.

Separada do painel de propósito. O painel conta o que já aconteceu; esta responde
três perguntas de quem está comprando agora: quanto cabe este mês, o que a compra
do ano passado virou e se vale levar este produto.
"""

from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_http_methods, require_POST

from apps.auditoria.servicos import registrar
from apps.core import menu, pdf
from apps.core.templatetags.cabana import quantidade as escrever
from apps.financeiro import servicos as financeiro
from apps.importacao import servicos

from . import (
    ajustes, comparacao, equipe, historico, janela as janelas, limite, lista_de_compra,
    pedido, sugestoes as motor_de_sugestoes,
)
from .forms import DadosDaEmpresaForm
from .models import DadosDaEmpresa, PoliticaDeCompra, SugestaoDeCompra


@login_required
@permission_required("importacao.ver_painel", raise_exception=True)
def antes_de_comprar(request):
    estado = servicos.estado_dos_dados()
    importacao = estado.importacao
    procurado = (request.GET.get("produto") or "").strip()
    return render(request, "compras/antes_de_comprar.html", {
        "titulo": "Antes de comprar",
        "estado": estado,
        "esconder_aviso_dados": True,
        "em_andamento": servicos.em_andamento(),
        "dados": limite.montar(importacao, resumo_caixa=financeiro.resumir(importacao)),
        "procurado": procurado,
        "vereditos": limite.conferir(importacao, procurado),
        "encontrados": limite.quantos_casam(importacao, procurado),
        "mostrados": limite.QUANTOS_RESULTADOS,
    })


def _lista_de_compra(request):
    """A lista pronta, com o teto do mês já aplicado. Usada pela tela e pelo arquivo."""
    estado = servicos.estado_dos_dados()
    lista = lista_de_compra.montar(
        estado.importacao,
        fornecedor=(request.GET.get("fornecedor") or "").strip(),
        urgencia=(request.GET.get("situacao") or "").strip(),
        # De que pedaço de calendário sai a média de venda que vira sugestão. `media` e
        # não `periodo` porque `periodo` já é o do quadro de comparação, nesta mesma
        # tela: dois filtros diferentes com o mesmo nome na URL se atropelariam.
        media=(request.GET.get("media") or "").strip(),
    )
    teto = None
    if estado.importacao is not None:
        # `teto_de` e não `montar`: a tela só precisa do teto, e `montar` traria os onze
        # mil produtos para a memória para depois jogar fora tudo menos ele.
        teto = limite.teto_de(estado.importacao,
                              resumo_caixa=financeiro.resumir(estado.importacao))
    return estado, lista_de_compra.priorizar(lista, teto), teto


@login_required
@permission_required("importacao.ver_painel", raise_exception=True)
def lista(request):
    """A lista de compra: o que comprar antes de faltar, e de quem.

    A comparação com o ano passado entra aqui dentro, e não mais numa tela própria do
    menu (pedido do Edson, 14/10/2026): é na hora de fechar o pedido que saber o que o
    mesmo período vendeu um ano atrás muda a decisão. Ela herda o fornecedor filtrado
    nesta tela, então filtrar por um fornecedor compara esse fornecedor, e não a loja.
    """
    estado, lista, teto = _lista_de_compra(request)
    ano_passado = comparacao.montar(
        estado.importacao,
        periodo=_periodo_pedido(request),
        de=(request.GET.get("de") or "").strip()[:7],
        ate=(request.GET.get("ate") or "").strip()[:7],
        grupo=(request.GET.get("grupo") or "").strip()[:120],
        # O fornecedor PEDIDO na tela, e não o que a lista de compra validou: a lista só
        # conhece quem tem produto abaixo do ponto de pedido, e quem não tem nada para
        # comprar hoje cai fora dela. O quadro comparando a loja inteira enquanto a tela
        # diz estar filtrada por um fornecedor seria um número certo no lugar errado.
        fornecedor=(request.GET.get("fornecedor") or "").strip()[:120],
        # A tabela produto a produto é da tela de "ver tudo"; aqui ficam o resumo e as
        # duas listas curtas de quem subiu e quem caiu, que é o que decide a compra.
        quantos=0,
    )
    return render(request, "compras/lista_de_compra.html", {
        "titulo": "Lista de compra",
        "estado": estado,
        "esconder_aviso_dados": True,
        "em_andamento": servicos.em_andamento(),
        "lista": lista,
        "teto": teto,
        "ano_passado": ano_passado,
        "periodos": comparacao.PERIODOS,
        "janelas_de_media": janelas.PERIODOS,
        "situacoes": [(chave, lista_de_compra.ROTULO[chave])
                      for chave in (lista_de_compra.Urgencia.FALTANDO,
                                    lista_de_compra.Urgencia.ABAIXO_DO_MINIMO,
                                    lista_de_compra.Urgencia.VAI_FALTAR)],
        "explicacao": lista_de_compra.EXPLICACAO,
        "prazo_padrao": lista_de_compra.PRAZO_PADRAO_DIAS,
        # Quem não pode ajustar vê o número como texto, e não um campo que recusa o
        # clique: campo desabilitado é promessa quebrada na cara de quem clicou.
        "pode_ajustar": request.user.has_perm("compras.ajustar_compra"),
        "empresa": DadosDaEmpresa.atual(),
        # As telas que saíram do menu de Compras em 22/10/2026 abrem daqui.
        "mais_em_compras": menu.recursos_de("compras:lista", request.user),
    })


@login_required
@permission_required("importacao.ver_painel", raise_exception=True)
def lista_em_arquivo(request):
    """A lista inteira em arquivo, para levar ao fornecedor ou abrir no Excel.

    Sai com ponto e vírgula e BOM porque é assim que o Excel em português abre o
    arquivo sem pedir nada a ninguém.
    """
    import csv
    import io as entrada_e_saida

    _estado, lista, _teto = _lista_de_compra(request)
    buffer = entrada_e_saida.StringIO()
    escritor = csv.writer(buffer, delimiter=";")
    escritor.writerows(lista_de_compra.em_linhas(lista))
    corpo = "\ufeff" + buffer.getvalue()
    nome = f"lista-de-compra-{lista.data_corte:%Y-%m-%d}.csv" if lista.data_corte else "lista-de-compra.csv"
    resposta = HttpResponse(corpo, content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = f'attachment; filename="{nome}"'
    return resposta


@login_required
@permission_required("importacao.ver_painel", raise_exception=True)
def consulta_de_compras(request):
    """Última compra de cada fornecedor e a lista das compras, uma a uma."""
    estado = servicos.estado_dos_dados()
    dados = historico.montar(
        estado.importacao,
        fornecedor=(request.GET.get("fornecedor") or "").strip(),
        procurado=(request.GET.get("busca") or "").strip(),
    )
    return render(request, "compras/consulta_de_compras.html", {
        "titulo": "Compras",
        "estado": estado,
        "importacao": estado.importacao,
        "dados": dados,
        "mostradas": historico.QUANTAS_COMPRAS,
    })


@login_required
@permission_required("importacao.ver_painel", raise_exception=True)
def compra(request, id_set):
    """Uma compra inteira: o cabeçalho e cada item que veio nela."""
    estado = servicos.estado_dos_dados()
    achada = historico.uma(estado.importacao, id_set)
    if achada is None:
        raise Http404("Essa compra não está na última importação.")
    return render(request, "compras/compra.html", {
        "titulo": f"Compra {achada.numero}",
        "estado": estado,
        "importacao": estado.importacao,
        "compra": achada,
        "itens": list(achada.linhas.all()),
    })


@login_required
@permission_required("importacao.ver_painel", raise_exception=True)
def sugestoes(request):
    """Cinco listas curtas: o que repor, o que parar, o que girar, o que vender, quem cobrar."""
    estado = servicos.estado_dos_dados()
    return render(request, "compras/sugestoes.html", {
        "titulo": "Sugestões",
        "estado": estado,
        "esconder_aviso_dados": True,
        "dados": motor_de_sugestoes.montar(estado.importacao),
        "quantos": motor_de_sugestoes.QUANTOS,
    })


@login_required
@permission_required("compras.sugerir_compra", raise_exception=True)
def sugestoes_da_equipe(request):
    """O que a equipe viu na loja e acha que precisa ser comprado."""
    situacao = request.GET.get("situacao", "")
    return render(request, "compras/sugestoes_da_equipe.html", {
        "titulo": "Sugestões da equipe",
        "estado": servicos.estado_dos_dados(),
        "sugestoes": equipe.listar(situacao),
        "contagem": equipe.contagem_por_situacao(),
        "situacao": situacao,
        "situacoes": SugestaoDeCompra.Situacao.choices,
        "motivos": SugestaoDeCompra.Motivo.choices,
    })


@login_required
@permission_required("compras.sugerir_compra", raise_exception=True)
@require_POST
def registrar_sugestao(request):
    try:
        sugestao = equipe.registrar_sugestao(
            produto=request.POST.get("produto"),
            codigo=request.POST.get("codigo", ""),
            quantidade=equipe.quantidade_informada(request.POST.get("quantidade")),
            motivo=request.POST.get("motivo", ""),
            observacao=request.POST.get("observacao", ""),
            fornecedor=request.POST.get("fornecedor", ""),
            usuario=request.user,
        )
    except equipe.ErroDeSugestao as erro:
        messages.error(request, str(erro))
    else:
        messages.success(request, f"Sugestão de {sugestao.produto} registrada. "
                                  "A gerência vê na lista aqui embaixo.")
    return redirect("compras:sugestoes_da_equipe")


@login_required
@permission_required("compras.responder_sugestao", raise_exception=True)
@require_POST
def responder_sugestao(request, pk):
    sugestao = get_object_or_404(SugestaoDeCompra, pk=pk)
    try:
        equipe.responder(sugestao, situacao=request.POST.get("situacao", ""),
                         resposta=request.POST.get("resposta", ""), usuario=request.user)
    except equipe.ErroDeSugestao as erro:
        messages.error(request, str(erro))
    else:
        messages.success(request, f"Sugestão de {sugestao.produto} respondida.")
    return redirect("compras:sugestoes_da_equipe")


def _de_volta_a_lista(request):
    """A mesma tela de onde a pessoa veio, com o filtro que ela tinha escolhido.

    Montado dos campos do formulário e não de um endereço vindo de fora: aceitar um
    "para onde voltar" de quem manda o POST é como se abre um redirecionamento para
    site de terceiro.
    """
    filtros = {chave: valor for chave, valor in (
        ("fornecedor", (request.POST.get("fornecedor") or "").strip()),
        ("situacao", (request.POST.get("situacao") or "").strip()),
        # A janela da média também, que o formulário manda: sem ela, quem ajustava uma
        # quantidade olhando a média de 30 dias voltava para a lista de doze meses, com
        # a linha mostrando outra sugestão — e toda linha ajustada passava a aparecer
        # como "ajuste desatualizado", porque o ajuste guarda a sugestão da janela.
        ("media", (request.POST.get("media") or "").strip()),
    ) if valor}
    endereco = reverse("compras:lista")
    if filtros:
        endereco += "?" + urlencode(filtros)
    return redirect(f"{endereco}#produto-{(request.POST.get('codigo') or '').strip()}"
                    if request.POST.get("codigo") else endereco)


@login_required
@permission_required("compras.ajustar_compra", raise_exception=True)
@require_POST
def politica(request):
    """Grava o alerta (% do estoque ideal) e quantos produtos são o carro-chefe.

    É a mesma permissão de mudar a quantidade: as duas decidem quanto dinheiro sai.
    Número fora da faixa não é recusado com erro, é trazido para dentro dela e a tela
    diz o que valeu — quem digitou 0 queria "o menor possível", não um formulário em
    vermelho.
    """
    atual = PoliticaDeCompra.atual()
    antes = {"alerta_percentual": atual.alerta_percentual, "carros_chefe": atual.carros_chefe}

    def numero(nome, minimo, maximo, padrao):
        try:
            valor = int((request.POST.get(nome) or "").strip())
        except ValueError:
            return padrao
        return max(minimo, min(maximo, valor))

    atual.alerta_percentual = numero("alerta_percentual", PoliticaDeCompra.ALERTA_MINIMO,
                                     PoliticaDeCompra.ALERTA_MAXIMO, atual.alerta_percentual)
    atual.carros_chefe = numero("carros_chefe", PoliticaDeCompra.CARROS_MINIMO,
                                PoliticaDeCompra.CARROS_MAXIMO, atual.carros_chefe)
    atual.atualizado_por = request.user
    atual.save()
    depois = {"alerta_percentual": atual.alerta_percentual, "carros_chefe": atual.carros_chefe}
    if depois != antes:
        registrar("compras.politica_alterada", usuario=request.user,
                  recurso_rotulo="Regra do alerta e do carro-chefe", antes=antes, depois=depois)
    messages.success(request, f"Estoque mínimo em {atual.alerta_percentual}% do ideal, "
                              f"com os {atual.carros_chefe} produtos que mais faturam como carro-chefe.")
    return redirect(reverse("compras:lista") + "#carros-chefe")


@login_required
@permission_required("compras.ajustar_compra", raise_exception=True)
@require_POST
def ajustar_quantidade(request):
    """Grava a quantidade que a gerência ACRESCENTA à conta do sistema.

    A sugestão do sistema continua ali, e agora é a primeira parcela de uma soma:
    sugerida + manual = total, que foi o pedido dele em 20/10/2026. O botão "voltar à
    sugestão" apaga o ajuste e devolve a linha para a conta, inclusive para as
    próximas sincronizações.
    """
    codigo = (request.POST.get("codigo") or "").strip()
    descricao = (request.POST.get("descricao") or codigo).strip()

    if request.POST.get("voltar_a_sugestao"):
        # Lido antes de apagar: "voltou à sugestão" sem dizer de que número voltou não
        # responde nada depois.
        desfeito = ajustes.escolhida_antes(codigo)
        if ajustes.limpar(codigo):
            registrar("compras.quantidade_restaurada", usuario=request.user,
                      recurso_rotulo=f"{codigo} · {descricao}"[:200],
                      antes={"codigo": codigo,
                             "escolhida": str(desfeito.quantidade) if desfeito else "",
                             "observacao": desfeito.observacao if desfeito else ""})
            messages.success(request, f"{descricao} voltou a seguir a sugestão do sistema.")
        return _de_volta_a_lista(request)

    # O que estava escolhido ANTES, lido antes de gravar: sem isto a trilha dizia a
    # sugestão do sistema e o número novo, e a pergunta que se faz três meses depois é
    # "quem mudou de 10 para 6", não "qual era a conta". Pedido dele em 20/10/2026,
    # seção 11: registrar em histórico auditável os ajustes manuais e a justificativa.
    anterior = ajustes.escolhida_antes(codigo)

    nao_comprar = bool(request.POST.get("nao_comprar"))
    try:
        ajuste, total = ajustes.salvar(
            codigo=codigo,
            a_mais=request.POST.get("a_mais"),
            sugerida=request.POST.get("sugerida"),
            nao_comprar=nao_comprar,
            usuario=request.user,
            observacao=request.POST.get("observacao", ""),
        )
    except ajustes.ErroDeAjuste as erro:
        messages.error(request, f"{descricao}: {erro}")
        return _de_volta_a_lista(request)

    registrar("compras.quantidade_ajustada", usuario=request.user, recurso=ajuste,
              recurso_rotulo=f"{codigo} · {descricao}"[:200],
              antes={"sugerida": str(request.POST.get("sugerida") or ""),
                     "a_mais": str(anterior.a_mais) if anterior else "",
                     "escolhida": str(anterior.quantidade) if anterior else "",
                     "nao_comprar": bool(anterior.nao_comprar) if anterior else False,
                     "observacao": anterior.observacao if anterior else ""},
              depois={"a_mais": str(ajuste.a_mais) if ajuste else "0",
                      "quantidade": str(total),
                      "nao_comprar": nao_comprar,
                      # A justificativa é o POR QUÊ, e era a única parte da decisão que
                      # ficava só no registro do ajuste — que a próxima edição sobrescreve.
                      "observacao": (request.POST.get("observacao") or "").strip()[:200],
                      "seguiu_a_sugestao": ajuste is None},
              motivo=(request.POST.get("observacao") or "").strip()[:300])
    if ajuste is None:
        messages.success(
            request,
            f"{descricao}: sem quantidade a mais, a linha continua seguindo a "
            "sugestão do sistema.")
    elif nao_comprar:
        messages.success(request, f"{descricao}: fica fora do pedido por agora.")
    else:
        messages.success(request, f"{descricao}: comprar {escrever(total)}.")
    return _de_volta_a_lista(request)


@login_required
@permission_required("importacao.ver_painel", raise_exception=True)
@require_http_methods(["GET", "POST"])
def pedido_ao_fornecedor(request):
    """O pedido em PDF, com o timbre da loja, para mandar ao fornecedor.

    Sai exatamente a lista que está na tela — inclusive o filtro de situação, se
    houver um — com as quantidades já ajustadas. Sem `fornecedor` no endereço, saem
    os fornecedores do começo da lista, um por folha, que é o "fornecedor(es)" do
    pedido do Edson.
    """
    estado = servicos.estado_dos_dados()
    if estado.importacao is None:
        raise Http404("Ainda não há importação concluída para montar um pedido.")

    escolhido = (request.GET.get("fornecedor") or "").strip()
    situacao = (request.GET.get("situacao") or "").strip()
    # A janela da média VAI no endereço, junto com o fornecedor e a situação. Sem ela a
    # folha saía da média de doze meses enquanto a tela mostrava a de 30 dias: outro
    # número no papel que vai ao fornecedor, e — desde a 1.31.0 — no pedido gravado.
    # Produto que só entra na lista pela janela curta nem apareceria na folha.
    lista = lista_de_compra.montar(estado.importacao, fornecedor=escolhido, urgencia=situacao,
                                   media=(request.GET.get("media") or "").strip())
    if escolhido:
        # `montar` ignora filtro de fornecedor que não existe na lista, e um pedido com
        # a loja inteira dentro por causa de um nome errado no endereço seria pior do
        # que nenhum pedido.
        if lista.filtro_fornecedor != escolhido:
            raise Http404("Esse fornecedor não está na lista de compra desta importação.")
        blocos = lista.fornecedores
    else:
        teto = limite.teto_de(estado.importacao,
                              resumo_caixa=financeiro.resumir(estado.importacao))
        blocos = lista_de_compra.priorizar(lista, teto).primeiro
    if not blocos:
        raise Http404("Não há o que pedir com esses filtros.")

    empresa = DadosDaEmpresa.atual()
    emitido_por = request.user.get_full_name() or request.user.get_username()
    relatorio = pedido.montar(blocos, empresa, data_corte=lista.data_corte, emitido_por=emitido_por)
    registrar("compras.pedido_gerado", usuario=request.user,
              recurso_rotulo=", ".join(b.nome for b in blocos)[:200],
              depois={"fornecedores": len(blocos),
                      "itens": sum(len(pedido.itens_do_pedido(b)) for b in blocos)})

    # POST é fazer o pedido: fica guardado em Pedidos, com a própria folha anexada, e
    # é a ele que o romaneio e a nota fiscal vão ser anexados quando a mercadoria
    # chegar (pedido do Edson, 14/10/2026). GET continua sendo só a folha, para
    # reimprimir sem registrar nada.
    if request.method == "POST" and request.user.has_perm("pedidos.registrar_pedido"):
        _guardar_os_pedidos(request, blocos, empresa, lista, emitido_por)
    return pdf.resposta(relatorio, pedido.nome_do_arquivo(blocos, lista.data_corte))


def _guardar_os_pedidos(request, blocos, empresa, lista, emitido_por):
    """Registra um pedido por fornecedor e anexa a folha DELE, não o maço inteiro.

    A gravação mora em `apps.pedidos.geracao`, porque desde a 1.37.0 a tela de Pedidos
    gera os mesmos pedidos pelo outro lado — e um pedido guardado com a folha de outro
    fornecedor é o tipo de erro que só aparece quando a mercadoria chega.
    """
    from apps.pedidos import geracao  # noqa: PLC0415

    guardados, _ = geracao.gerar(request.user, blocos, data_corte=lista.data_corte,
                                 emitido_por=emitido_por, empresa=empresa)
    if not guardados:
        return
    if len(guardados) == 1:
        endereco = reverse("pedidos:detalhe", args=[guardados[0].numero])
        messages.success(request, mark_safe(
            f"Pedido {guardados[0].numero} guardado. "
            f'<a href="{endereco}">Abrir o pedido</a> para anexar o romaneio e a nota '
            "quando a mercadoria chegar."))
    else:
        endereco = reverse("pedidos:lista")
        messages.success(request, mark_safe(
            f"{len(guardados)} pedidos guardados. "
            f'<a href="{endereco}">Ver os pedidos</a> para anexar romaneio e nota fiscal.'))


@login_required
@permission_required("compras.change_dadosdaempresa", raise_exception=True)
def dados_da_empresa(request):
    """O timbre que vai no pedido: nome da loja, razão social, endereço e contato."""
    empresa = DadosDaEmpresa.atual()
    if request.method == "POST":
        form = DadosDaEmpresaForm(request.POST, instance=empresa)
        if form.is_valid():
            antes = {campo: str(getattr(empresa, campo)) for campo in form.changed_data}
            salva = form.save()
            registrar("compras.empresa_configurada", usuario=request.user, recurso=salva,
                      recurso_rotulo="dados da empresa", antes=antes,
                      depois={campo: str(getattr(salva, campo)) for campo in form.changed_data})
            messages.success(request, "Dados gravados. O próximo pedido já sai com eles.")
            return redirect("compras:dados_da_empresa")
    else:
        form = DadosDaEmpresaForm(instance=empresa)
    return render(request, "compras/dados_da_empresa.html", {
        "titulo": "Dados da empresa",
        "estado": servicos.estado_dos_dados(),
        "esconder_aviso_dados": True,
        "empresa": empresa,
        "form": form,
        "faltas": empresa.falta_preencher,
    })


def _periodo_pedido(request):
    """Qual período a tela pediu, lendo o BOTÃO que a pessoa apertou.

    São dois botões no mesmo formulário: um compara o período pronto do seletor, o outro
    compara os meses escolhidos a dedo ao lado. Sem isso o sistema teria que adivinhar
    qual dos dois controles a pessoa mexeu, e adivinharia errado metade das vezes.
    """
    if (request.GET.get("comparar") or "").strip() == "meses":
        return comparacao.PERIODO_LIVRE
    return (request.GET.get("periodo") or comparacao.PERIODO_PADRAO).strip()


def _comparacao(request, quantos=comparacao.POR_PAGINA):
    """A comparação pedida pela tela e pelo arquivo, montada uma vez só."""
    estado = servicos.estado_dos_dados()
    return estado, comparacao.montar(
        estado.importacao,
        periodo=_periodo_pedido(request),
        de=(request.GET.get("de") or "").strip()[:7],
        ate=(request.GET.get("ate") or "").strip()[:7],
        grupo=(request.GET.get("grupo") or "").strip(),
        fornecedor=(request.GET.get("fornecedor") or "").strip(),
        busca=(request.GET.get("busca") or "").strip()[:60],
        quantos=quantos,
    )


@login_required
@permission_required("importacao.ver_painel", raise_exception=True)
def comparar_com_o_ano_passado(request):
    """O que o período vendeu contra o mesmo período do ano passado, produto a produto."""
    estado, dados = _comparacao(request)
    return render(request, "compras/comparacao.html", {
        "titulo": "Comparar com o ano passado",
        "estado": estado,
        "esconder_aviso_dados": True,
        "dados": dados,
        "periodos": comparacao.PERIODOS,
    })


@login_required
@permission_required("importacao.ver_painel", raise_exception=True)
def comparacao_em_arquivo(request):
    """A comparação inteira em CSV, com ponto e vírgula e BOM, como os outros arquivos."""
    import csv
    import io as entrada_e_saida

    _estado, dados = _comparacao(request, quantos=None)
    buffer = entrada_e_saida.StringIO()
    escritor = csv.writer(buffer, delimiter=";")
    escritor.writerows(comparacao.em_linhas(dados))
    resposta = HttpResponse("﻿" + buffer.getvalue(), content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = (
        f'attachment; filename="comparacao-{dados.meses}-meses.csv"')
    return resposta
