import datetime
import logging

from django.contrib.auth.decorators import login_required, permission_required
from django.db import connection
from django.http import FileResponse, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.cache import never_cache

from apps.auditoria.models import EventoAuditoria
from apps.auditoria.servicos import registrar
from apps.core import atualizacoes, certificado as certificado_servicos, https, menu, versao
from apps.core import cotacoes as cotacoes_da_faixa

logger = logging.getLogger(__name__)


def negado(request, exception=None):
    """A tela de "sem permissão" (403), e a tentativa na auditoria (1.44.0).

    O prompt de controle de acesso pediu que tentativa de abrir o que o perfil não deixa
    ficasse registrada, e que o recado não contasse nada do que está do outro lado: a tela
    diz só que o usuário não tem permissão e para procurar a gerência. A mesma pessoa no
    mesmo endereço conta uma vez por minuto, para um recarregar de página não encher a
    auditoria.
    """
    usuario = getattr(request, "user", None)
    if usuario is not None and usuario.is_authenticated:
        endereco = request.path[:200]
        um_minuto = timezone.now() - datetime.timedelta(seconds=60)
        repetido = EventoAuditoria.objects.filter(
            acao="acesso.negado", usuario=usuario, recurso_rotulo=endereco, momento__gte=um_minuto,
        ).exists()
        if not repetido:
            registrar("acesso.negado", usuario=usuario, recurso_rotulo=endereco,
                      resultado=EventoAuditoria.Resultado.NEGADO,
                      depois={"endereco": endereco, "metodo": request.method})
    return render(request, "403.html", status=403)


@login_required
def inicio(request):
    """A porta do sistema: encaminha para o dashboard.

    O Edson pediu que o início fosse o dashboard, e não uma página de boas-vindas
    com atalhos: quem abre o sistema quer ver como a loja está. Desde 31/10/2026 é o
    Dashboard em quadros, a primeira entrada do menu ("causa bom impacto com as
    informações visíveis"). Quem não tem o painel (o vendedor) vai para a primeira tela
    do perfil dele. Quem não tem tela nenhuma vê o recado de falar com a gerência, em
    vez de um erro.
    """
    destino = menu.primeira_tela(request.user)
    if destino:
        return redirect(destino)
    return render(request, "core/inicio.html", {"titulo": "Início"})


# O histórico de mudanças conta o que cada versão consertou, e para explicar um
# conserto ele cita o número que estava errado: faturamento, lucro bruto, margem, o
# que está parado na prateleira, as diferenças de caixa. São os números da loja, os
# mesmos que a Visão geral mostra. Por isso esta tela pede a mesma permissão das
# telas de dinheiro, e não só login: em 11/10/2026 a varredura de rotas × perfis
# descobriu que o Operador vendedor, que só pode ver a consulta de balcão, abria
# aqui o faturamento de 12 meses digitando o endereço.
#
# A VERSÃO em si continua à vista de todo mundo, no alto de toda tela: é assim que
# se confere se a atualização entrou. O que fica guardado é o histórico.
@login_required
@permission_required("importacao.ver_painel", raise_exception=True)
def versoes(request):
    """Mostra qual versão está instalada, as atualizações já aplicadas e o que mudou em cada uma."""
    return render(request, "core/versoes.html", {
        "titulo": "Versões do sistema",
        "versao": versao.atual(),
        "aplicacoes": atualizacoes.historico(),
        "mudancas": atualizacoes.mudancas(),
    })


@never_cache
def saude(request):
    """Teste de saúde para monitoramento. Não expõe detalhes internos."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        banco = "ok"
    except Exception:  # noqa: BLE001
        banco = "falha"
    status = 200 if banco == "ok" else 503
    return JsonResponse({"aplicacao": "ok", "banco": banco}, status=status)


# Quem instala o certificado é a pessoa, no aparelho dela, e todo mundo que usa o
# sistema no celular precisa disso para a câmera funcionar — inclusive o vendedor, que
# tem só uma tela. Por isso esta tela pede login e nada mais: ela não mostra nenhum
# número da loja, só a validade do certificado e o passo a passo da instalação.
def _garantir_certificado():
    """Cria o certificado da loja se ele ainda não existe, e devolve o erro se não der.

    O servir.py já tenta fazer isso quando o sistema sobe, mas ele engole a falha para
    não derrubar o HTTP — e aí ninguém fica sabendo: em 08/10/2026 o Edson clicou em
    baixar a autoridade e levou um "Página não encontrada", sem explicação nenhuma.
    Então a tela tenta de novo, na hora, por dois motivos: na maioria das vezes isso
    resolve sozinho (a pasta é criada e o certificado nasce), e quando não resolve o
    motivo aparece escrito na tela, em vez de ficar só no log.

    Devolve (pasta, erro); erro é None quando deu certo.
    """
    pasta = certificado_servicos.pasta_padrao()
    try:
        certificado_servicos.garantir(pasta, certificado_servicos.enderecos_configurados())
    except Exception as erro:  # noqa: BLE001 - a tela mostra o motivo, seja ele qual for
        logger.exception("Não consegui gerar o certificado da loja em %s", pasta)
        return pasta, f"{type(erro).__name__}: {erro}"
    return pasta, None


@login_required
def certificado(request):
    """Como fazer o celular confiar no sistema: baixar e instalar a autoridade da loja."""
    pasta, erro = _garantir_certificado()
    return render(request, "core/certificado.html", {
        "titulo": "Certificado de segurança",
        "ficha": certificado_servicos.descrever(pasta),
        "enderecos": certificado_servicos.enderecos_configurados(),
        "arquivo": certificado_servicos.NOME_AUTORIDADE,
        "pasta": str(pasta),
        "erro_ao_gerar": erro,
        # O teste de verdade: alguém está falando TLS na porta segura agora? E ela
        # atende no endereço por onde esta pessoa chegou, que é o que o celular usa?
        "diagnostico": https.conferir(
            endereco_rede=(request.get_host() or "").split(":")[0]),
        # Se o túnel tentou subir e falhou, o motivo ficou anotado em arquivo. Com o
        # HTTPS desligado no studio.env não faz sentido mostrar: a porta não subiu
        # porque ninguém mandou subir.
        "falha_do_tunel": https.falha_registrada() if https.ligado() else None,
        "endereco_para_abrir": https.endereco_seguro(request).replace(
            request.path, "/studio/"),
    })


@login_required
def certificado_autoridade(request):
    """Entrega o arquivo da autoridade da loja para instalar no aparelho.

    O tipo application/x-x509-ca-cert é o que faz o iPhone e o Android entenderem
    que aquilo é um certificado para instalar, em vez de baixar um texto qualquer.
    Só a autoridade é entregue: a chave dela nunca sai do servidor.
    """
    pasta, erro = _garantir_certificado()
    caminho = pasta / certificado_servicos.NOME_AUTORIDADE
    if not caminho.is_file():
        # Página de explicação, e não o 404 em branco: quem clicou em baixar precisa
        # saber o que fazer, e o motivo está aqui.
        return render(request, "core/certificado_sem_arquivo.html", {
            "titulo": "Não consegui entregar o certificado",
            "pasta": str(pasta),
            "erro_ao_gerar": erro,
        }, status=503)
    return FileResponse(caminho.open("rb"), as_attachment=True,
                        filename="cabana-autoridade.crt",
                        content_type="application/x-x509-ca-cert")


@never_cache
@login_required
@permission_required("importacao.ver_painel", raise_exception=True)
def cotacoes(request):
    """O miolo da faixa do topo (1.50.0), que a tela pede a cada minuto. Lê só o cache: quem
    vai à internet é a busca em segundo plano de apps/core/cotacoes.py. Este pedido não
    conta como uso do sistema (apps/contas/sessao.py). Só para quem vê número da loja: a
    tela do vendedor não mostra R$ nenhum, nem o do dólar (condição do Edson)."""
    return JsonResponse({"html": render_to_string("core/_cotacoes.html", {"cotacoes": cotacoes_da_faixa.faixa()})})
