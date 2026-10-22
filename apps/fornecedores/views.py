"""Tela de fornecedores: quanto cada um representa e em quantos dias entrega."""

from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.auditoria.servicos import registrar
from apps.core.templatetags.cabana import reais
from apps.importacao import servicos as importacao_servicos

from . import catalogo as catalogo_de_produtos, servicos
from .models import PRAZO_MAXIMO, REPUTACAO_MAXIMA, Fornecedor


@login_required
@permission_required("fornecedores.view_fornecedor", raise_exception=True)
def lista(request):
    estado = importacao_servicos.estado_dos_dados()
    todos = servicos.resumir(estado.importacao)
    busca = (request.GET.get("busca") or "").strip()[:80]
    resumos = servicos.procurar(todos, busca)
    return render(request, "fornecedores/lista.html", {
        "titulo": "Fornecedores",
        "estado": estado,
        "fornecedores": resumos,
        "busca": busca,
        "quantos_ao_todo": len(todos),
        # As pendências contam a loja INTEIRA, não o resultado da busca: "faltam 40
        # prazos" é a fila de trabalho, e ela não encolhe porque alguém procurou um nome.
        "sem_prazo": sum(1 for r in todos if r.precisa_de_prazo),
        "sem_reputacao": sum(1 for r in todos if r.precisa_de_reputacao),
        "prazo_maximo": PRAZO_MAXIMO,
        "estrelas_possiveis": range(1, REPUTACAO_MAXIMA + 1),
        "relacoes": Fornecedor.Relacao.choices,
    })


@login_required
@permission_required("fornecedores.view_fornecedor", raise_exception=True)
def sugestoes(request):
    """Os nomes que a lista oferece enquanto a pessoa digita na busca de fornecedores.

    Fica atrás da mesma permissão da tela, como a busca de contas a pagar: nome de
    fornecedor com valor comprado ao lado não é coisa de endereço aberto, e o vendedor
    não entra aqui.
    """
    termo = (request.GET.get("q") or "").strip()[:80]
    itens = []
    if len(termo) >= 2:
        estado = importacao_servicos.estado_dos_dados()
        achados = servicos.procurar(servicos.resumir(estado.importacao), termo)
        itens = [
            {
                "descricao": resumo.nome,
                "ajuda": f"{reais(resumo.valor_comprado_12m)} comprado em 12m"
                         f" · {resumo.produtos} produto{'s' if resumo.produtos != 1 else ''}",
            }
            for resumo in achados[:servicos.QUANTAS_SUGESTOES]
        ]
    return JsonResponse({"itens": itens})


@login_required
@permission_required("fornecedores.change_fornecedor", raise_exception=True)
def avaliar(request):
    """Grava a reputação em estrelas e como a loja trabalha com o fornecedor.

    Isto não vem do SET: é o julgamento de quem negocia. Entra na tela de compra para a
    gerência enxergar com quem dá para pedir prazo e de quem é melhor não depender.
    """
    if request.method != "POST":
        return redirect("fornecedores:lista")
    nome = (request.POST.get("nome") or "").strip()
    if not nome:
        messages.error(request, "Não entendi de qual fornecedor é a avaliação. Tente de novo pela lista.")
        return redirect("fornecedores:lista")

    bruto = (request.POST.get("reputacao") or "").strip()
    reputacao = None
    if bruto:
        if not bruto.isdigit() or not 1 <= int(bruto) <= REPUTACAO_MAXIMA:
            messages.error(request, f"A reputação vai de 1 a {REPUTACAO_MAXIMA} estrelas.")
            return redirect("fornecedores:lista")
        reputacao = int(bruto)

    relacao = (request.POST.get("relacao") or "").strip()
    if relacao not in dict(Fornecedor.Relacao.choices):
        messages.error(request, "Escolha uma das opções de relação: parceiro, flexível ou eventual.")
        return redirect("fornecedores:lista")

    fornecedor, _ = Fornecedor.objects.get_or_create(nome=nome)
    antes = {"reputacao": fornecedor.reputacao, "relacao": fornecedor.relacao}
    fornecedor.reputacao = reputacao
    fornecedor.relacao = relacao
    fornecedor.atualizado_por = request.user
    fornecedor.save()
    registrar(
        "fornecedor.avaliado",
        usuario=request.user,
        recurso=fornecedor,
        recurso_rotulo=fornecedor.nome,
        antes=antes,
        depois={"reputacao": fornecedor.reputacao, "relacao": fornecedor.relacao},
    )
    if reputacao is None:
        messages.success(request, f"Avaliação de {nome} apagada.")
    else:
        messages.success(request, f"{nome}: {reputacao} estrela{'s' if reputacao != 1 else ''}"
                                  f"{', ' + fornecedor.get_relacao_display().lower() if relacao else ''}.")
    return redirect("fornecedores:lista")


@login_required
@permission_required("fornecedores.change_fornecedor", raise_exception=True)
def salvar(request):
    """Grava o prazo de um fornecedor. O prazo informado vale mais que o medido no SET."""
    if request.method != "POST":
        return redirect("fornecedores:lista")
    nome = (request.POST.get("nome") or "").strip()
    bruto = (request.POST.get("prazo_dias") or "").strip()
    if not nome:
        messages.error(request, "Não entendi de qual fornecedor é o prazo. Tente de novo pela lista.")
        return redirect("fornecedores:lista")

    prazo = None
    if bruto:
        if not bruto.isdigit() or not 0 <= int(bruto) <= PRAZO_MAXIMO:
            messages.error(request, f"Informe o prazo em dias, de 0 a {PRAZO_MAXIMO}. Exemplo: 15.")
            return redirect("fornecedores:lista")
        prazo = int(bruto)

    fornecedor, _ = Fornecedor.objects.get_or_create(nome=nome)
    antes = {"prazo_dias": fornecedor.prazo_dias, "observacao": fornecedor.observacao}
    fornecedor.prazo_dias = prazo
    fornecedor.observacao = (request.POST.get("observacao") or "").strip()[:300]
    fornecedor.atualizado_por = request.user
    fornecedor.save()
    registrar(
        "fornecedor.prazo_alterado",
        usuario=request.user,
        recurso=fornecedor,
        recurso_rotulo=fornecedor.nome,
        antes=antes,
        depois={"prazo_dias": fornecedor.prazo_dias, "observacao": fornecedor.observacao},
    )
    if prazo is None:
        messages.success(request, f"Prazo de {nome} apagado. Volta a valer o prazo medido no SET.")
    else:
        messages.success(request, f"Prazo de {nome}: {prazo} dia{'s' if prazo != 1 else ''}. "
                                  "A sugestão de reposição já considera esse prazo.")
    return redirect("fornecedores:lista")


@login_required
@permission_required("fornecedores.view_fornecedor", raise_exception=True)
def ficha(request):
    """Tudo o que o sistema sabe de um fornecedor, numa tela só.

    Metade vem do cadastro do SET (CNPJ, endereço, telefone) e metade é da gerência
    (prazo, estrelas, relação e que documento o fornecedor emite). A tela separa as duas
    coisas, porque uma se corrige no SET e a outra aqui.
    """
    nome = (request.GET.get("nome") or "").strip()
    estado = importacao_servicos.estado_dos_dados()
    cadastro = Fornecedor.objects.filter(nome=nome).first()
    return render(request, "fornecedores/ficha.html", {
        "titulo": nome or "Fornecedor",
        "estado": estado,
        "nome": nome,
        "ficha": servicos.ficha(estado.importacao, nome),
        "resumo": servicos.resumo_de(estado.importacao, nome),
        "cadastro": cadastro,
        "produtos": servicos.produtos_do_fornecedor(estado.importacao, nome),
        "prazo_maximo": PRAZO_MAXIMO,
        "estrelas_possiveis": range(1, REPUTACAO_MAXIMA + 1),
        "relacoes": Fornecedor.Relacao.choices,
        "documentos": Fornecedor.Documento.choices,
    })


@login_required
@permission_required("fornecedores.change_fornecedor", raise_exception=True)
def documento(request):
    """Grava que documento o fornecedor emite: nota completa, parcial ou só romaneio."""
    if request.method != "POST":
        return redirect("fornecedores:lista")
    nome = (request.POST.get("nome") or "").strip()
    escolhido = (request.POST.get("documento_fiscal") or "").strip()
    if not nome or escolhido not in dict(Fornecedor.Documento.choices):
        messages.error(request, "Escolha uma das opções: nota completa, nota parcial ou recibo.")
        return redirect("fornecedores:lista")

    fornecedor, _ = Fornecedor.objects.get_or_create(nome=nome)
    antes = {"documento_fiscal": fornecedor.documento_fiscal}
    fornecedor.documento_fiscal = escolhido
    fornecedor.atualizado_por = request.user
    fornecedor.save()
    registrar(
        "fornecedor.documento_informado",
        usuario=request.user,
        recurso=fornecedor,
        recurso_rotulo=fornecedor.nome,
        antes=antes,
        depois={"documento_fiscal": escolhido},
    )
    messages.success(request, f"Documento de {nome} anotado: {fornecedor.get_documento_fiscal_display()}.")
    return redirect(f"{reverse('fornecedores:ficha')}?nome={quote(nome)}")


def _catalogo(request, quantos=catalogo_de_produtos.POR_PAGINA):
    """O catálogo pedido pela tela e pelo arquivo, montado uma vez só."""
    estado = importacao_servicos.estado_dos_dados()
    return estado, catalogo_de_produtos.montar(
        estado.importacao,
        nome=(request.GET.get("nome") or "").strip(),
        busca=(request.GET.get("busca") or "").strip()[:60],
        grupo=(request.GET.get("grupo") or "").strip(),
        quantos=quantos,
    )


@login_required
@permission_required("fornecedores.view_fornecedor", raise_exception=True)
def produtos(request):
    """A variedade de um fornecedor: quantos produtos, de quantos tipos, e quais.

    Separada da ficha de propósito: a ficha responde "quem é e quanto custou", e esta
    responde "o que ele tem". Juntar as duas daria uma tela que ninguém lê até o fim.
    """
    estado, catalogo = _catalogo(request)
    return render(request, "fornecedores/produtos.html", {
        "titulo": catalogo.nome or "Produtos do fornecedor",
        "estado": estado,
        "catalogo": catalogo,
        "cadastro": Fornecedor.objects.filter(nome=catalogo.nome).first(),
    })


@login_required
@permission_required("fornecedores.view_fornecedor", raise_exception=True)
def produtos_em_arquivo(request):
    """O catálogo inteiro em CSV, com ponto e vírgula e BOM, como os outros arquivos."""
    import csv
    import io as entrada_e_saida

    _estado, catalogo = _catalogo(request, quantos=None)
    buffer = entrada_e_saida.StringIO()
    escritor = csv.writer(buffer, delimiter=";")
    escritor.writerows(catalogo_de_produtos.em_linhas(catalogo))
    nome_do_arquivo = "produtos-do-fornecedor.csv"
    if catalogo.nome:
        limpo = "".join(letra if letra.isalnum() else "-" for letra in catalogo.nome).strip("-")
        nome_do_arquivo = f"produtos-{limpo.lower()[:40]}.csv"
    resposta = HttpResponse("\ufeff" + buffer.getvalue(), content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = f'attachment; filename="{nome_do_arquivo}"'
    return resposta
