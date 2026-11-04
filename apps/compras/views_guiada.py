"""As telas da compra guiada. As contas e as perguntas moram em `apps/compras/guiada.py`.

Cada pergunta é um endereço próprio (`/compras/guiada/<compra>/<pergunta>/`), e não uma
janela que troca de conteúdo no navegador: a resposta fica gravada a cada "Continuar",
então fechar a aba, cair a internet do celular ou parar para atender um cliente não
perde nada. A pessoa volta pela abertura, em "Continuar de onde parou".

A cara de apresentação (o cartão no meio, o fundo escuro, uma pergunta por vez) é toda
de CSS (`.guiada-*` em static/css/sistema.css); o JavaScript (static/js/guiada.js) só
soma na hora o que a pessoa digita, e a tela funciona inteira sem ele.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from apps.auditoria.servicos import registrar, registrar_arquivo
from apps.core import pdf
from apps.core.templatetags.cabana import quantidade as escrever, reais
from apps.importacao import servicos

from . import guiada
from .lista_de_compra import SEM_FORNECEDOR
from .models import CompraGuiada, DadosDaEmpresa

PERMISSAO = "compras.ver_compras"
# A compra guiada não tem tela antes nem depois dela: as setas do pé da página levariam
# para fora no meio de uma pergunta.
SEM_SETAS = {"tela_anterior": None, "tela_proxima": None, "esconder_aviso_dados": True}

TITULOS = {
    guiada.PRAZO: "Prazo de entrega",
    guiada.PROXIMA: "Próxima compra",
    guiada.TIPOS: "O que entra",
    guiada.VENDA: "Venda de base",
    guiada.ENCOMENDAS: "Encomendas",
    guiada.ORCAMENTO: "Orçamento",
    guiada.REVISAO: "Conferir e gerar",
}

# O nome do campo de cada pergunta de escolha única, para remarcar a escolha quando a
# resposta volta com erro (por exemplo, "Outro" marcado com o número em branco).
CAMPO_DA_ESCOLHA = {
    guiada.PRAZO: "prazo",
    guiada.PROXIMA: "proxima_compra",
    guiada.VENDA: "media",
    guiada.PRODUTO: "quantidade",
    guiada.ORCAMENTO: "orcamento",
}

MODELOS = {
    guiada.PRAZO: "compras/guiada/prazo.html",
    guiada.PROXIMA: "compras/guiada/proxima_compra.html",
    guiada.TIPOS: "compras/guiada/tipos.html",
    guiada.VENDA: "compras/guiada/venda.html",
    guiada.ENCOMENDAS: "compras/guiada/encomendas.html",
    guiada.ORCAMENTO: "compras/guiada/orcamento.html",
    guiada.REVISAO: "compras/guiada/revisao.html",
}


def _titulo_do_passo(passo, proposta):
    if passo.startswith(guiada.PRODUTO):
        posicao = passo[len(guiada.PRODUTO):]
        return f"Os que mais vendem ({posicao} de {len(proposta.principais)})"
    return TITULOS.get(passo, "")


def _endereco(compra, passo, de=""):
    endereco = reverse("compras:guiada_passo", args=[compra.pk, passo])
    return f"{endereco}?de={de}" if de else endereco


def _da_pessoa(request, pk):
    """A compra é de quem começou: a de outra pessoa não abre nem pelo número."""
    return get_object_or_404(CompraGuiada, pk=pk, criada_por=request.user)


def _nome_de_quem(request):
    return request.user.get_full_name() or request.user.get_username()


@login_required
@permission_required(PERMISSAO, raise_exception=True)
def abertura(request):
    """A leitura da loja e a primeira pergunta: de qual fornecedor é a compra."""
    estado = servicos.estado_dos_dados()
    leitura = guiada.ler_a_loja(estado.importacao)
    sugerido = (request.GET.get("fornecedor") or "").strip()[:200]
    return render(request, "compras/guiada/abertura.html", {
        "titulo": "Compra guiada",
        "estado": estado,
        "leitura": leitura,
        "sugerido": sugerido,
        "sugerido_na_lista": any(opcao.nome == sugerido for opcao in leitura.opcoes),
        "em_andamento": guiada.em_andamento(request.user),
        "feitas": guiada.ultimas_concluidas(),
        "pode_gerar": request.user.has_perm("pedidos.registrar_pedido"),
        **SEM_SETAS,
    })


@login_required
@permission_required(PERMISSAO, raise_exception=True)
@require_POST
def comecar(request):
    estado = servicos.estado_dos_dados()
    importacao = estado.importacao
    if importacao is None:
        messages.error(request, "Ainda não há dados do SET importados para montar uma compra.")
        return redirect("compras:guiada")
    # O botão "Comprar de" de um carro-chefe manda o fornecedor dele direto. Fora isso, o
    # nome digitado vence a escolha marcada: quem marcou um cartão e depois escreveu outro
    # nome quis o que escreveu por último.
    direto = (request.POST.get("direto") or "").strip()
    digitado = (request.POST.get("outro_fornecedor") or "").strip()
    marcado = (request.POST.get("fornecedor") or "").strip()
    pedido = (direto or digitado or ("" if marcado == "outro" else marcado))[:200]
    if not pedido:
        messages.error(request, "Escolha um fornecedor, ou escreva o nome dele.")
        return redirect("compras:guiada")
    nome = (importacao.itens.filter(fornecedor__iexact=pedido)
            .values_list("fornecedor", flat=True).first())
    if not nome or nome == SEM_FORNECEDOR:
        messages.error(request, f"Não achei “{pedido}” entre os fornecedores dos produtos do "
                                "SET. Escolha um da lista que aparece ao digitar.")
        return redirect(reverse("compras:guiada") + "?" + _consulta({"fornecedor": pedido}))
    compra = (CompraGuiada.objects.filter(criada_por=request.user, fornecedor=nome,
                                          situacao=CompraGuiada.Situacao.ANDAMENTO).first())
    if compra is None:
        compra = CompraGuiada.objects.create(fornecedor=nome, criada_por=request.user,
                                             data_corte=importacao.data_corte)
    else:
        messages.success(request, f"Você já tinha começado a compra de {nome}: seguimos dela.")
    proposta = guiada.montar(compra, importacao, aplicar_orcamento=False)
    return redirect(_endereco(compra, guiada.onde_parou(compra, proposta)))


@login_required
@permission_required(PERMISSAO, raise_exception=True)
def continuar(request, pk):
    """Volta à compra na primeira pergunta ainda sem resposta."""
    compra = _da_pessoa(request, pk)
    if compra.situacao == CompraGuiada.Situacao.CONCLUIDA:
        return redirect("compras:guiada_pronto", pk=compra.pk)
    importacao = servicos.estado_dos_dados().importacao
    if compra.situacao != CompraGuiada.Situacao.ANDAMENTO or importacao is None:
        return redirect("compras:guiada")
    proposta = guiada.montar(compra, importacao, aplicar_orcamento=False)
    return redirect(_endereco(compra, guiada.onde_parou(compra, proposta)))


def _consulta(campos):
    from urllib.parse import urlencode  # noqa: PLC0415

    return urlencode(campos)


@login_required
@permission_required(PERMISSAO, raise_exception=True)
@require_http_methods(["GET", "POST"])
def passo(request, pk, passo):
    compra = _da_pessoa(request, pk)
    if compra.situacao == CompraGuiada.Situacao.CONCLUIDA:
        return redirect("compras:guiada_pronto", pk=compra.pk)
    if compra.situacao == CompraGuiada.Situacao.DEIXADA:
        messages.error(request, f"A compra de {compra.fornecedor} foi deixada de lado. "
                                "Comece outra pela escolha do fornecedor.")
        return redirect("compras:guiada")
    estado = servicos.estado_dos_dados()
    importacao = estado.importacao
    if importacao is None:
        messages.error(request, "Ainda não há dados do SET importados para montar uma compra.")
        return redirect("compras:guiada")

    proposta = guiada.montar(compra, importacao)
    lista = guiada.passos(compra, proposta)
    if passo not in lista:
        # Pergunta que deixou de existir (o quinto produto, quando agora são três): volta
        # para a primeira sem resposta, em vez de uma página de erro.
        return redirect(_endereco(compra, guiada.onde_parou(compra, proposta)))
    de = "revisao" if (request.POST.get("de") or request.GET.get("de")) == "revisao" else ""

    erro = ""
    if request.method == "POST":
        try:
            recado = guiada.salvar_resposta(compra, passo, request.POST, request.user, importacao)
        except guiada.RespostaInvalida as problema:
            erro = str(problema)
        else:
            if recado:
                messages.success(request, recado)
            acao = request.POST.get("acao") or ""
            if passo == guiada.ENCOMENDAS and acao in ("adicionar", "tirar"):
                return redirect(_endereco(compra, passo, de))
            if passo == guiada.REVISAO:
                if acao == "gerar":
                    return _gerar(request, compra, importacao)
                if not recado:
                    messages.success(request, "Mudanças guardadas.")
                return redirect(_endereco(compra, passo))
            proposta = guiada.montar(compra, importacao)
            return redirect(_endereco(compra, _depois_de(compra, proposta, passo, de)))

    return render(request, MODELOS.get(passo, "compras/guiada/produto.html"),
                  _contexto(request, compra, proposta, lista, passo, estado, importacao, erro, de))


def _depois_de(compra, proposta, passo, de):
    """Para onde o "Continuar" leva: a próxima pergunta, ou de volta à conferência."""
    if de == "revisao":
        return guiada.REVISAO
    lista = guiada.passos(compra, proposta)
    if passo in lista:
        for seguinte in lista[lista.index(passo) + 1:]:
            if seguinte == guiada.REVISAO or not guiada.respondida(compra, proposta, seguinte):
                return seguinte
        return guiada.REVISAO
    return guiada.onde_parou(compra, proposta)


def _contexto(request, compra, proposta, lista, passo, estado, importacao, erro, de):
    posicao = lista.index(passo)
    # A escolha do fornecedor, na abertura, é a primeira pergunta.
    numero, total = posicao + 2, len(lista) + 1
    if de == "revisao":
        anterior = _endereco(compra, guiada.REVISAO)
    elif posicao > 0:
        anterior = _endereco(compra, lista[posicao - 1])
    else:
        anterior = reverse("compras:guiada")
    contexto = {
        "titulo": f"Compra guiada · {compra.fornecedor}",
        "compra": compra,
        "proposta": proposta,
        "passo": passo,
        "titulo_do_passo": _titulo_do_passo(passo, proposta),
        "numero": numero,
        "total_de_passos": total,
        "porcentagem": int(numero * 100 / total),
        "anterior": anterior,
        "primeiro": posicao == 0,
        "de": de,
        "erro": erro,
        "estado": estado,
        "dados": request.POST if erro else None,
        **SEM_SETAS,
    }
    respostas = compra.respostas or {}
    if passo == guiada.PRAZO:
        contexto["opcoes"] = guiada.opcoes_de_prazo(compra, importacao)
        contexto["marcado"] = ("nao_sei" if respostas.get("prazo_nao_sabe") or "prazo" not in respostas
                               else str(respostas.get("prazo")))
        if contexto["marcado"] not in {str(dias) for dias, _ in guiada.PRAZOS} | {"nao_sei"}:
            contexto["outro_prazo"], contexto["marcado"] = contexto["marcado"], "outro"
        contexto["grava_na_ficha"] = request.user.has_perm("fornecedores.change_fornecedor")
        contexto["prazo_padrao"] = guiada.lista_de_compra.PRAZO_PADRAO_DIAS
    elif passo == guiada.PROXIMA:
        historico = guiada.historico_do_fornecedor(importacao, compra.fornecedor)
        contexto["historico"] = historico
        contexto["opcoes"] = guiada.opcoes_de_proxima_compra(compra, importacao, historico)
        contexto["marcado"] = respostas.get("proxima_compra") or historico.proxima_recomendada
        contexto["anteriores"] = guiada.anteriores_do_fornecedor(compra.fornecedor, menos=compra)
        if historico.ultima_compra and proposta.data_corte:
            contexto["dias_da_ultima"] = (proposta.data_corte - historico.ultima_compra).days
    elif passo == guiada.TIPOS:
        contexto["tipos_marcados"] = (set(request.POST.getlist("tipo")) if erro else
                                      {tipo.grupo for tipo in proposta.tipos if tipo.escolhido})
        contexto["entra_marcada"] = request.POST.get("entra") if erro else proposta.entra
        contexto["entra"] = [
            guiada.Opcao(chave=chave, rotulo=rotulo, quantos=proposta.por_entra.get(chave, 0),
                         recomendada=chave == guiada.ENTRA_PADRAO)
            for chave, rotulo in guiada.ENTRA]
    elif passo == guiada.VENDA:
        contexto["historico"] = guiada.historico_do_fornecedor(importacao, compra.fornecedor)
        contexto["opcoes"] = guiada.opcoes_de_venda(compra, importacao)
        contexto["marcado"] = proposta.media
    elif passo.startswith(guiada.PRODUTO):
        linha = guiada.principal(proposta, passo)
        contexto["linha"] = linha
        contexto["opcoes"] = linha.opcoes() if linha else []
        contexto["marcado"] = linha.escolha or "sugerida" if linha else "sugerida"
        if linha and contexto["marcado"] not in ("sugerida", "metade", "dobro", "nao"):
            contexto["outra_quantidade"], contexto["marcado"] = contexto["marcado"], "outro"
    elif passo == guiada.ENCOMENDAS:
        procurado = (request.GET.get("procurar") or "").strip()[:60]
        contexto["procurado"] = procurado
        contexto["achados"] = guiada.achar_produtos(importacao, procurado, compra.fornecedor)
        marcadas = respostas.get("equipe") or {}
        equipe = guiada.sugestoes_da_equipe(compra, importacao)
        for sugestao in equipe:
            sugestao.marcada = str(sugestao.pk) in marcadas
            sugestao.unidades = escrever(marcadas.get(str(sugestao.pk)) or sugestao.quantidade,
                                         vazio="1")
        contexto["equipe"] = equipe
    elif passo == guiada.ORCAMENTO:
        teto = guiada.teto_do_mes(importacao)
        contexto["teto"] = teto
        contexto["opcoes"] = guiada.opcoes_de_orcamento(proposta, teto)
        marcado = respostas.get("orcamento")
        if marcado not in guiada.ORCAMENTOS:
            marcado = next(opcao.chave for opcao in contexto["opcoes"] if opcao.recomendada)
        contexto["marcado"] = marcado
        contexto["orcamento_valor"] = respostas.get("orcamento_valor", "")
    elif passo == guiada.REVISAO:
        contexto["respondidas"] = _respondidas(compra, proposta, lista)
        contexto["pode_gerar"] = request.user.has_perm("pedidos.registrar_pedido")
        from apps.pedidos import servicos as pedidos  # noqa: PLC0415

        contexto["vai_esperar"] = contexto["pode_gerar"] and not pedidos.aprova(request.user)
        contexto["recado"] = respostas.get("recado", "")
        contexto["tempo"] = guiada.lista_de_compra.duracao(proposta.tempo_ate_chegar)
        # Primeiro o que a conta pede (em falta e acabando), depois todos os outros
        # produtos do fornecedor, pedido do Edson em 04/11/2026. O posto à mão fica na
        # segunda tabela, no lugar dele (guiada.os_demais).
        contexto["pedidas"] = [linha for linha in proposta.linhas if not linha.a_mao]
        contexto["demais"] = guiada.os_demais(proposta, importacao)
    if "marcado" in contexto:
        contexto["marcado"] = str(contexto["marcado"])
        campo = CAMPO_DA_ESCOLHA.get(passo[:len(guiada.PRODUTO)] if passo.startswith(guiada.PRODUTO)
                                     else passo)
        if erro and campo and request.POST.get(campo) is not None:
            # A resposta voltou com erro: a tela mostra marcado o que a pessoa escolheu.
            contexto["marcado"] = request.POST.get(campo)
    return contexto


def _respondidas(compra, proposta, lista):
    """As respostas da compra em frases curtas, cada uma com o caminho para mudar."""
    respostas = compra.respostas or {}
    linhas = []
    for passo in lista:
        if passo == guiada.REVISAO:
            continue
        texto = ""
        if passo == guiada.PRAZO:
            texto = (f"{proposta.prazo_dias} dias" if not respostas.get("prazo_nao_sabe")
                     else f"não sei (contando {proposta.prazo_dias} dias)")
        elif passo == guiada.PROXIMA:
            texto = dict(guiada.PROXIMA_COMPRA).get(proposta.proxima_compra, "")
        elif passo == guiada.TIPOS:
            escolhidos = [tipo.grupo or "sem grupo" for tipo in proposta.tipos if tipo.escolhido]
            todos = len(escolhidos) == len(proposta.tipos)
            texto = ("todos os tipos" if todos else ", ".join(escolhidos)) + "; " + \
                dict(guiada.ENTRA)[proposta.entra].lower()
        elif passo == guiada.VENDA:
            texto = dict(guiada.MEDIAS).get(proposta.media, "")
        elif passo.startswith(guiada.PRODUTO):
            linha = guiada.principal(proposta, passo)
            if linha is None:
                continue
            texto = f"{linha.descricao}: {_quantidade_dita(linha)}"
        elif passo == guiada.ENCOMENDAS:
            quantas = len(proposta.encomendas)
            texto = ("nenhuma" if not quantas
                     else f"{quantas} produto{'s' if quantas != 1 else ''} encomendado{'s' if quantas != 1 else ''}")
        elif passo == guiada.ORCAMENTO:
            if proposta.orcamento is not None:
                texto = f"até {reais(proposta.orcamento)}"
            else:
                texto = "sem limite"
        linhas.append({"titulo": _titulo_do_passo(passo, proposta), "texto": texto,
                       "endereco": _endereco(compra, passo, "revisao")})
    return linhas


def _quantidade_dita(linha):
    nomes = {"sugerida": "a sugestão", "metade": "a metade", "dobro": "o dobro",
             "nao": "não comprar agora"}
    if linha.escolha in nomes:
        return f"{nomes[linha.escolha]} ({escrever(linha.reposicao, vazio='0')})"
    if linha.escolha:
        return f"{escrever(linha.reposicao, vazio='0')} unidades"
    return f"a sugestão ({escrever(linha.sugerida, vazio='0')})"


def _gerar(request, compra, importacao):
    if not request.user.has_perm("pedidos.registrar_pedido"):
        messages.error(request, "Gerar o pedido é da gerência ou da Líder de loja. As mudanças "
                                "ficaram guardadas: baixe a folha e entregue a quem pode gerar.")
        return redirect(_endereco(compra, guiada.REVISAO))
    proposta = guiada.montar(compra, importacao)
    try:
        guiada.gerar_pedido(compra, proposta, request.user, emitido_por=_nome_de_quem(request))
    except guiada.RespostaInvalida as problema:
        messages.error(request, str(problema))
        return redirect(_endereco(compra, guiada.REVISAO))
    return redirect("compras:guiada_pronto", pk=compra.pk)


@login_required
@permission_required(PERMISSAO, raise_exception=True)
def folha(request, pk):
    """A folha do pedido em PDF, como está agora, sem gravar pedido nenhum.

    Quem não aprova pedido (a Líder de loja, ou quem não gera pedido) leva a folha com o
    aviso de que ela ainda não vale: é o mesmo cuidado da folha guardada no pedido.
    """
    compra = _da_pessoa(request, pk)
    importacao = servicos.estado_dos_dados().importacao
    if importacao is None:
        raise Http404("Ainda não há importação concluída para montar um pedido.")
    proposta = guiada.montar(compra, importacao)
    bloco = proposta.bloco()
    if not bloco.itens:
        raise Http404("Não há o que pedir: todas as quantidades estão em zero.")

    from apps.pedidos import folha as folha_guardada, servicos as pedidos  # noqa: PLC0415

    from . import pedido as folha_do_pedido  # noqa: PLC0415

    aprova = request.user.has_perm("pedidos.registrar_pedido") and pedidos.aprova(request.user)
    aviso = "" if aprova else folha_guardada.AVISO_SEM_APROVACAO
    relatorio = folha_do_pedido.montar(
        [bloco], DadosDaEmpresa.atual(), data_corte=proposta.data_corte,
        emitido_por=_nome_de_quem(request), observacao=(compra.respostas or {}).get("recado", ""),
        aviso=aviso)
    nome = folha_do_pedido.nome_do_arquivo([bloco], proposta.data_corte)
    if aviso:
        nome = folha_guardada.com_o_aviso_no_nome(nome)
    registrar_arquivo(request, nome)
    return pdf.resposta(relatorio, nome)


@login_required
@permission_required(PERMISSAO, raise_exception=True)
def pronto(request, pk):
    compra = _da_pessoa(request, pk)
    if compra.situacao != CompraGuiada.Situacao.CONCLUIDA:
        return redirect("compras:guiada")
    from apps.pedidos.models import Pedido  # noqa: PLC0415

    registro = Pedido.objects.filter(numero=compra.pedido_numero).first()
    return render(request, "compras/guiada/pronto.html", {
        "titulo": f"Compra guiada · {compra.fornecedor}",
        "compra": compra,
        "registro": registro,
        **SEM_SETAS,
    })


@login_required
@permission_required(PERMISSAO, raise_exception=True)
@require_POST
def deixar(request, pk):
    compra = _da_pessoa(request, pk)
    if compra.situacao == CompraGuiada.Situacao.ANDAMENTO:
        compra.situacao = CompraGuiada.Situacao.DEIXADA
        compra.save(update_fields=["situacao", "atualizada_em"])
        registrar("compras.compra_guiada_deixada", usuario=request.user, recurso=compra,
                  recurso_rotulo=compra.fornecedor[:200],
                  depois={"respostas": {chave: valor for chave, valor in (compra.respostas or {}).items()
                                        if chave != "respondidos"}})
        messages.success(request, f"A compra de {compra.fornecedor} foi deixada de lado. "
                                  "Nada foi pedido.")
    return redirect("compras:guiada")
