"""Tela Tempo e venda: anotar o tempo do dia e ver o que ele faz com o movimento."""

from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.auditoria.servicos import registrar
from apps.importacao import servicos as importacao_servicos
from apps.tempo import analise as servico_de_analise, indicador, servicos
from apps.tempo.forms import ConfiguracaoForm
from apps.tempo.fonte import ErroDoTempo
from apps.tempo.models import ConfiguracaoDoTempo, TempoDoDia

anotar_tempo = permission_required("tempo.anotar_tempo", raise_exception=True)


def _contexto(request, form=None):
    estado = importacao_servicos.estado_dos_dados()
    configuracao = ConfiguracaoDoTempo.atual()
    return {
        "titulo": "Tempo e venda",
        "estado": estado,
        "esconder_aviso_dados": True,
        "analise": servico_de_analise.montar(estado.importacao),
        "sem_registro": servico_de_analise.dias_sem_registro(estado.importacao),
        # A previsão dos próximos dias vive à parte da análise, que só conta dia fechado.
        # É o mesmo indicador que a Visão geral mostra, e aqui ele abre em tabela.
        "tempo": indicador.montar(estado.importacao),
        "configuracao": configuracao,
        "form": form or ConfiguracaoForm(instance=configuracao),
        "condicoes": TempoDoDia.Condicao.choices,
        "hoje": date.today(),
        "pode_configurar": request.user.has_perm("tempo.configurar_tempo"),
        "dias_para_concluir": servico_de_analise.DIAS_PARA_CONCLUIR,
    }


@login_required
@anotar_tempo
def painel(request):
    """O que o clima faz com a venda, e o campo para anotar o dia."""
    return render(request, "tempo/painel.html", _contexto(request))


@login_required
@anotar_tempo
@require_POST
def anotar(request):
    """Grava o tempo de um dia escrito por alguém da loja."""
    bruto = (request.POST.get("data") or "").strip()
    try:
        quando = date.fromisoformat(bruto)
    except ValueError:
        messages.error(request, "Escolha o dia no calendário.")
        return redirect("tempo:painel")
    try:
        registro = servicos.anotar(
            data=quando,
            condicao=(request.POST.get("condicao") or "").strip(),
            chuva=request.POST.get("chuva"),
            minima=request.POST.get("minima"),
            maxima=request.POST.get("maxima"),
            feriado=bool(request.POST.get("feriado")),
            observacao=request.POST.get("observacao", ""),
            usuario=request.user,
        )
    except servicos.ErroDeRegistro as erro:
        messages.error(request, str(erro))
        return redirect("tempo:painel")
    registrar("tempo.anotado", usuario=request.user, recurso=registro,
              recurso_rotulo=f"{quando:%d/%m/%Y}",
              depois={"condicao": registro.condicao, "chuva_mm": str(registro.chuva_mm or ""),
                      "feriado": registro.feriado})
    messages.success(request, f"Tempo de {quando:%d/%m/%Y} anotado: {registro.resumo}.")
    return redirect("tempo:painel")


@login_required
@permission_required("tempo.configurar_tempo", raise_exception=True)
@require_POST
def configurar(request):
    """Grava onde fica a loja e, na mesma hora, descobre o lugar e busca o tempo.

    Salvar a cidade e esperar as 06:10 do dia seguinte para ver se funcionou é o tipo de
    coisa que ninguém confere. Então o Salvar faz o caminho inteiro: descobre a latitude
    e a longitude pelo nome da cidade, busca o tempo e diz o que achou, numa frase. Se a
    internet do servidor não alcançar, a configuração continua gravada e a frase explica
    o que faltou — nada fica pela metade.
    """
    configuracao = ConfiguracaoDoTempo.atual()
    form = ConfiguracaoForm(request.POST, instance=configuracao)
    if not form.is_valid():
        return render(request, "tempo/painel.html", _contexto(request, form))
    antes = {"ativo": configuracao.ativo, "cidade": configuracao.cidade}
    salva = form.save()
    registrar("tempo.configurado", usuario=request.user, recurso=salva,
              recurso_rotulo="busca do tempo", antes=antes,
              depois={"ativo": salva.ativo, "cidade": salva.cidade,
                      "latitude": str(salva.latitude or ""), "longitude": str(salva.longitude or "")})
    messages.success(request, "Configuração gravada.")
    if salva.pronta:
        _buscar_e_contar(request, salva, dias=14)
    return redirect("tempo:painel")


def _buscar_e_contar(request, configuracao, dias=14):
    """Busca o tempo e põe na tela, em uma frase, o que entrou e de onde."""
    tinha_lugar = configuracao.tem_lugar
    try:
        novos, atualizados, respeitados = servicos.atualizar(configuracao, dias=dias)
    except ErroDoTempo as erro:
        registrar("tempo.busca", usuario=request.user, resultado="falha",
                  depois={"erro": str(erro)[:200]})
        messages.error(request, str(erro))
        return False
    configuracao.refresh_from_db()
    if not tinha_lugar and configuracao.lugar_encontrado:
        messages.success(
            request,
            f"O sistema descobriu o lugar da loja sozinho: {configuracao.lugar_encontrado}. "
            "Se não for essa a cidade, corrija o nome ou escreva as coordenadas à mão."
        )
    registrar("tempo.busca", usuario=request.user,
              depois={"novos": novos, "atualizados": atualizados,
                      "escritos_a_mao_respeitados": respeitados})
    messages.success(
        request,
        f"{novos} dia(s) novo(s) e {atualizados} atualizado(s), já com a previsão dos "
        "próximos dias. "
        + (f"{respeitados} dia(s) ficaram como alguém da loja escreveu." if respeitados else ""))
    return True


@login_required
@permission_required("tempo.configurar_tempo", raise_exception=True)
@require_POST
def buscar_agora(request):
    """Busca o tempo na hora, para provar o caminho antes de confiar na tarefa da noite."""
    _buscar_e_contar(request, ConfiguracaoDoTempo.atual(), dias=14)
    return redirect("tempo:painel")


@login_required
@anotar_tempo
def em_arquivo(request):
    """O tempo e a venda, dia a dia, em CSV para abrir no Excel."""
    import csv
    import io as entrada_e_saida

    estado = importacao_servicos.estado_dos_dados()
    dados = servico_de_analise.montar(estado.importacao, dias_na_tabela=400)
    buffer = entrada_e_saida.StringIO()
    escritor = csv.writer(buffer, delimiter=";")
    escritor.writerows(servico_de_analise.em_linhas(dados))
    resposta = HttpResponse("﻿" + buffer.getvalue(), content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = 'attachment; filename="tempo-e-venda.csv"'
    return resposta
