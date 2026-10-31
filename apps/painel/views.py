"""Painel de compras e estoque: os números da última importação concluída.

São duas telas sobre a mesma conta. O painel resumido responde "como está a loja
hoje" em poucos números, que é o que a gerência olha todo dia. O completo abre
todos os indicadores, as listas de produtos e os avisos, para quando a decisão
de compra precisa ser destrinchada.
"""

from datetime import date

from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponse
from django.shortcuts import render

from apps.importacao import servicos
from apps.tempo import indicador as indicador_do_tempo

from . import dashboard as dashboard_servicos
from . import servicos as painel_servicos
from . import tarefas
from . import ticket as ticket_servicos
from . import vendas_do_dia as vendas_servicos


def _contexto(request, titulo):
    estado = servicos.estado_dos_dados()
    contexto = {
        "titulo": titulo,
        "estado": estado,
        # A página já abre com o estado dos dados em destaque; repetir na faixa do topo é ruído.
        "esconder_aviso_dados": True,
        "em_andamento": servicos.em_andamento(),
        "ultima": servicos.ultima_com_explicacao(),
        "painel": None if estado.importacao is None else painel_servicos.painel_da_importacao(estado.importacao),
    }
    return contexto


@login_required
@permission_required("importacao.ver_painel", raise_exception=True)
def geral(request):
    """Visão geral: a tela de abrir e entender, sem precisar de outra."""
    # Não passa por _contexto de propósito: aquele calcula o painel inteiro, com a conta de
    # reposição sobre os onze mil produtos, e esta tela não usa nada disso.
    estado = servicos.estado_dos_dados()
    return render(request, "painel/visao_geral.html", {
        "titulo": "Visão geral",
        "estado": estado,
        "esconder_aviso_dados": True,
        "em_andamento": servicos.em_andamento(),
        "visao": painel_servicos.visao_da_importacao(estado.importacao),
        # O que fazer agora: a lista que o sistema monta sozinho, em ordem de urgência.
        "agenda": painel_servicos.agenda_da_importacao(
            estado.importacao, estado, usuario=request.user),
        # O tempo virou indicador daqui, e deixou de ser tela do menu (pedido do Edson,
        # 14/10/2026): é a única coisa desta tela que olha para frente. O que vem no
        # próximo fim de semana, ao lado do que a chuva já custou à loja.
        "tempo": indicador_do_tempo.montar(estado.importacao),
    })


@login_required
@permission_required("importacao.ver_painel", raise_exception=True)
def painel(request):
    """Resumido: a situação da loja em poucos números."""
    contexto = _contexto(request, "Painel")
    dados = contexto["painel"]
    if dados is not None:
        contexto["melhores"] = dados.listas.get("melhores_para_comprar", [])
        contexto["destaque"] = dados.indicador("comprou_mais")
        contexto["repor"] = dados.indicador("comprar")
        contexto["falta"] = dados.indicador("falta")
    return render(request, "painel/resumo.html", contexto)


@login_required
@permission_required("importacao.ver_painel", raise_exception=True)
def completo(request):
    """Completo: todos os indicadores, as listas e os avisos."""
    contexto = _contexto(request, "Painel completo")
    dados = contexto["painel"]
    contexto.update(lista_escolhida=None, linhas=[], indicador_escolhido=None)
    if dados is not None:
        escolhida = request.GET.get("lista") or "comprou_mais"
        if dados.indicador(escolhida) is None:
            escolhida = "comprou_mais"
        contexto.update(
            lista_escolhida=escolhida,
            linhas=dados.listas.get(escolhida, []),
            indicador_escolhido=dados.indicador(escolhida),
            recentes=dados.listas.get("comprados_recentemente", []),
            parados=dados.listas.get("comprados_ha_anos", []),
            melhores=dados.listas.get("melhores_para_comprar", []),
        )
    return render(request, "painel/painel.html", contexto)


@login_required
@permission_required("importacao.ver_painel", raise_exception=True)
def ticket_medio(request):
    """Quanto o cliente gasta por compra, com os filtros da gerência."""
    estado = servicos.estado_dos_dados()
    resultado = ticket_servicos.calcular(
        estado.importacao,
        periodo=request.GET.get("periodo", ticket_servicos.PERIODO_PADRAO),
        forma=request.GET.get("forma", "").strip(),
        vendedor=request.GET.get("vendedor", "").strip(),
        dia=request.GET.get("dia", "").strip(),
    )
    return render(request, "painel/ticket_medio.html", {
        "titulo": "Ticket médio",
        "estado": estado,
        "importacao": estado.importacao,
        "t": resultado,
        "periodos": ticket_servicos.PERIODOS,
        "dias_da_semana": ticket_servicos.DIAS_DA_SEMANA,
        "minimo_para_comparar": ticket_servicos.MINIMO_PARA_COMPARAR,
    })


@login_required
@permission_required("importacao.ver_painel", raise_exception=True)
def dashboard(request):
    """Dashboard: os gráficos e as estatísticas do varejo, com filtros."""
    estado = servicos.estado_dos_dados()
    periodo = request.GET.get("periodo", dashboard_servicos.PERIODO_PADRAO)
    grupo = (request.GET.get("grupo") or "").strip()
    fornecedor = (request.GET.get("fornecedor") or "").strip()
    if grupo or fornecedor:
        painel_dashboard = dashboard_servicos.montar(
            estado.importacao, periodo=periodo, grupo=grupo, fornecedor=fornecedor)
    else:
        # Sem filtro, a conta guardada: é a tela que abre logo depois de entrar (1.43.0).
        painel_dashboard = painel_servicos.dashboard_da_importacao(estado.importacao, periodo)
    # A lista do que fazer é a da Visão geral, guardada por importação e filtrada pela
    # permissão de quem olha: o quadro de problemas e a palavra da situação saem dela.
    agenda = painel_servicos.agenda_da_importacao(estado.importacao, estado, usuario=request.user)
    return render(request, "painel/dashboard.html", {
        "titulo": "Dashboard",
        "estado": estado,
        "esconder_aviso_dados": True,
        "d": painel_dashboard,
        "periodos": dashboard_servicos.PERIODOS,
        "agenda": agenda,
        "situacao": tarefas.situacao(agenda),
    })


def _dia_da_url(texto):
    """O dia pedido na URL, no formato do campo de data. Texto torto vira nenhum dia."""
    if not texto:
        return None
    try:
        return date.fromisoformat(texto.strip())
    except ValueError:
        return None


@login_required
@permission_required("importacao.ver_painel", raise_exception=True)
def vendas_dia(request):
    """O que a loja vendeu num dia, com custo, lucro em reais e em porcentagem."""
    estado = servicos.estado_dos_dados()
    resultado = vendas_servicos.calcular(
        estado.importacao, dia=_dia_da_url(request.GET.get("dia")))
    return render(request, "painel/vendas_do_dia.html", {
        "titulo": "Vendas do dia",
        "estado": estado,
        "esconder_aviso_dados": True,
        "v": resultado,
    })


@login_required
@permission_required("importacao.ver_painel", raise_exception=True)
def vendas_dia_arquivo(request):
    """A relação do dia inteira para abrir no Excel.

    Ponto e vírgula e BOM porque é assim que o Excel em português abre sem perguntar
    nada a ninguém, igual aos outros CSV do sistema.
    """
    import csv
    import io as entrada_e_saida

    estado = servicos.estado_dos_dados()
    resultado = vendas_servicos.calcular(
        estado.importacao, dia=_dia_da_url(request.GET.get("dia")), limite=0)
    cabecalho, corpo = vendas_servicos.linhas_do_csv(resultado)
    buffer = entrada_e_saida.StringIO()
    escritor = csv.writer(buffer, delimiter=";")
    escritor.writerow(cabecalho)
    escritor.writerows(corpo)
    nome = (f"vendas-do-dia-{resultado.dia:%Y-%m-%d}.csv" if resultado.dia
            else "vendas-do-dia.csv")
    resposta = HttpResponse("\ufeff" + buffer.getvalue(), content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = f'attachment; filename="{nome}"'
    return resposta
