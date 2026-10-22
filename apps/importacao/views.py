"""Telas da importação: disparar à mão e ver o histórico."""

import re

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST

from apps.core import barras, procura

from . import comparacao as comparacao_servicos
from . import conferencia as conferencia_servicos
from . import servicos
from .models import Importacao

# Quantos produtos a consulta de balcão lista de uma vez. Lista longa no balcão não
# ajuda: ou a pessoa escreve o nome mais completo, ou procura pelo código.
QUANTOS_NA_CONSULTA = 15


@login_required
@permission_required("importacao.executar_importacao", raise_exception=True)
@require_POST
def importar(request):
    """Começa uma importação e volta para a tela de onde veio; o andamento aparece lá.

    Com `forcar`, é o botão "Forçar atualização com o último backup": relê o backup
    mais recente mesmo sendo o mesmo da importação anterior. A conferência de tamanho
    e data roda aqui, antes de começar, para quem clicou já receber o motivo na tela
    quando o arquivo está lá e não serve, em vez de esperar a importação falhar.
    """
    forcar = bool(request.POST.get("forcar"))
    destino = "importacao:historico" if request.POST.get("voltar") == "importacoes" else "painel:painel"
    rodando = servicos.em_andamento()
    if rodando is not None:
        messages.warning(request, "Já existe uma importação em andamento. Aguarde o fim dela.")
        return redirect(destino)
    conferencia = conferencia_servicos.conferir(anterior=servicos.ultima_concluida())
    # Só recusa aqui o arquivo que existe e não serve, porque esse motivo se explica numa
    # linha. Não achar arquivo nenhum, ou não ter pasta configurada, segue para a
    # importação: ela registra a falha e a tela de importações mostra o passo a passo de
    # como resolver, que é bem mais do que cabe num aviso.
    if conferencia.achou and not conferencia.pode_importar(forcar):
        messages.error(
            request,
            f"Não importei: {conferencia.por_que_nao(forcar)} "
            "Os números que estão na tela continuam valendo.",
        )
        return redirect(destino)
    servicos.executar_em_segundo_plano(usuario=request.user, forcar=forcar)
    messages.success(
        request,
        ("Importação forçada: o sistema vai ler o backup mais recente de novo e substituir os "
         "números pelos dele. Leva alguns minutos; esta página se atualiza sozinha.")
        if forcar else
        "Importação iniciada. Ler a cópia do banco leva alguns minutos; esta página se atualiza sozinha.",
    )
    return redirect(destino)


@login_required
@permission_required("importacao.ver_painel", raise_exception=True)
def historico(request):
    return render(request, "importacao/historico.html", {
        "titulo": "Importações",
        "importacoes": Importacao.objects.select_related("acionada_por")[:60],
        "estado": servicos.estado_dos_dados(),
        "em_andamento": servicos.em_andamento(),
        "ultima": servicos.ultima_com_explicacao(),
        # Prova, em números, que sincronizar substitui e não soma.
        "comparacao": comparacao_servicos.montar(),
        # O que o sistema vê no arquivo de backup agora: tamanho, data e o que estranhou.
        "conferencia": conferencia_servicos.conferir(anterior=servicos.ultima_concluida()),
        "hora_automatica": getattr(settings, "IMPORTACAO_HORA", ""),
        "horarios_automaticos": getattr(settings, "IMPORTACAO_HORARIOS", []),
        # O aviso só aparece quando há mais de uma sincronização por dia: aí vale
        # dizer que elas dependem de o SET gerar backup mais de uma vez.
        "backup_so_de_madrugada": len(getattr(settings, "IMPORTACAO_HORARIOS", [])) > 1,
        "pasta_backup": getattr(settings, "IMPORTACAO_BACKUP_ORIGEM", ""),
        "esconder_aviso_dados": True,
    })


@login_required
@permission_required("importacao.ver_painel", raise_exception=True)
def log(request, pk):
    """Baixa o log de uma importação como texto, para anexar num e-mail ou guardar."""
    importacao = get_object_or_404(Importacao, pk=pk)
    cabecalho = [
        "Log da importação do sistema da Cabana do Jacarandá",
        f"Início: {timezone.localtime(importacao.iniciada_em):%d/%m/%Y %H:%M:%S}",
        f"Resultado: {importacao.get_situacao_display()}",
        f"Origem: {importacao.get_origem_display()}",
        f"Arquivo: {importacao.arquivo or '—'}",
        f"Versão do sistema: {importacao.versao_sistema or '—'}",
        "",
    ]
    corpo = "\n".join(cabecalho) + (importacao.log or "Sem linhas registradas.\n")
    resposta = HttpResponse(corpo, content_type="text/plain; charset=utf-8")
    nome = f"importacao-{timezone.localtime(importacao.iniciada_em):%Y%m%d-%H%M}-{importacao.pk}.txt"
    resposta["Content-Disposition"] = f'attachment; filename="{nome}"'
    return resposta


@login_required
@permission_required("importacao.consultar_produtos", raise_exception=True)
def consulta(request):
    """Consulta de balcão: o produto e de quem a loja compra, sem nada de dinheiro.

    É a única tela do perfil de vendedor. Mostra o que serve para atender o cliente na
    frente da pessoa (tem na prateleira? quem traz? em quantos dias chega?) e não mostra
    custo, margem, quanto a loja comprou nem valor nenhum: isso é assunto da gerência.
    """
    from apps.fornecedores import servicos as fornecedores_servicos  # noqa: PLC0415

    procurado = (request.GET.get("produto") or "").strip()
    # Campo só para o número da etiqueta. Quem está com o produto na mão sabe o código de
    # barras e nada mais, e procurar por ele dentro da busca livre devolvia o produto certo
    # junto de qualquer descrição que tivesse aqueles dígitos. Aqui a comparação é exata.
    codigo_de_barras = re.sub(r"\D", "", request.GET.get("barras") or "")
    estado = servicos.estado_dos_dados()
    importacao = estado.importacao
    achados = []
    encontrados = 0
    if importacao is not None and (procurado or codigo_de_barras):
        # O leitor de código de barras digita o número e aperta Enter, então o que chega
        # aqui é igualzinho ao que alguém digitaria: a busca é a mesma, só com o código de
        # barras incluído na comparação exata. A leitura pela câmera devolve o EAN-13 sem
        # o zero da frente, por isso as variantes (apps/core/barras.py).
        if codigo_de_barras:
            por_barras = Q()
            for forma in barras.variantes(codigo_de_barras):
                por_barras |= Q(codigo_barras__iexact=forma)
            consulta_itens = importacao.itens.filter(por_barras).order_by("descricao")
        else:
            por_barras = Q()
            for forma in barras.variantes(procurado):
                por_barras |= Q(codigo_barras__iexact=forma)
            consulta_itens = importacao.itens.filter(
                Q(descricao__icontains=procurado) | Q(codigo__iexact=procurado) | por_barras
            ).order_by("descricao")
        encontrados = consulta_itens.count()
        prazos = fornecedores_servicos.prazos_informados()
        for produto in consulta_itens[:QUANTOS_NA_CONSULTA]:
            achados.append({
                "produto": produto,
                "prazo": prazos.get((produto.fornecedor or "").strip()),
                "tem_na_prateleira": (produto.estoque or 0) > 0,
                # O desenho sai pronto da view para o template não precisar saber de EAN-13.
                "desenho": mark_safe(barras.svg(produto.codigo_barras) or ""),
            })
    return render(request, "importacao/consulta.html", {
        "titulo": "Consulta de produtos",
        "estado": estado,
        "esconder_aviso_dados": True,
        "procurado": procurado,
        "codigo_de_barras": codigo_de_barras,
        # O que a pessoa procurou, para a tela falar do que ela digitou e não de "o termo".
        "termo": codigo_de_barras or procurado,
        "procurou_por_barras": bool(codigo_de_barras),
        "achados": achados,
        "encontrados": encontrados,
        "mostrados": QUANTOS_NA_CONSULTA,
    })


# Quantas sugestões o autopreenchimento devolve enquanto a pessoa digita. Mais que isto
# vira lista comprida demais para escolher com o dedo no celular.
QUANTAS_SUGESTOES = 8


@login_required
@permission_required("importacao.consultar_produtos", raise_exception=True)
def sugestoes(request):
    """Lista de produtos que começam a casar com o que está sendo digitado.

    É o autopreenchimento das caixas de busca. Devolve JSON, nunca valor de dinheiro:
    a mesma regra da tela de consulta vale aqui, porque o vendedor também usa.
    """
    from django.http import JsonResponse  # noqa: PLC0415

    procurado = (request.GET.get("q") or "").strip()[:60]
    itens = []
    if len(procurado) >= 2:
        importacao = servicos.ultima_concluida()
        if importacao is not None:
            # Com acento ou sem, e o que COMEÇA com o digitado na frente; empate vai
            # para o que mais vendeu no ano, que é o que quase sempre se procura.
            achados = procura.por_relevancia(
                importacao.itens.filter(
                    procura.filtro(procurado, "descricao")
                    | Q(codigo__istartswith=procurado)
                    | Q(codigo_barras__istartswith=procurado)
                ),
                procurado, "descricao", "codigo",
                desempate=("-vendas_12m", "descricao"),
            )[:QUANTAS_SUGESTOES]
            itens = [
                {
                    "descricao": produto.descricao,
                    "codigo": produto.codigo,
                    "grupo": produto.grupo,
                    "estoque": str(produto.estoque or 0),
                }
                for produto in achados
            ]
    return JsonResponse({"itens": itens})
