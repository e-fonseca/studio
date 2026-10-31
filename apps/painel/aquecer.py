"""Deixar as contas do painel prontas antes de alguém pedir.

O problema que isto resolve
---------------------------
As três contas da abertura — o painel, a Visão geral e "O que fazer agora" — rodam
sobre os onze mil produtos da foto e levam, juntas, cerca de **2,2 segundos**. Elas
ficam em cache, e a chave do cache carrega o número da importação, então cada
sincronização derruba o cache inteiro, de propósito: número velho seria pior que
número lento.

Só que o cache ficava assim: a sincronização das 08:30 apagava as contas, ia embora,
e a conta de 2,2 s sobrava para **a primeira pessoa que abrisse o sistema**. Como a
Visão geral é a primeira tela depois de entrar, essa pessoa sentia isso como "o login
está lento". Três sincronizações por dia, três pessoas pagando a conta.

Desde a 1.43.0 a primeira tela depois de entrar é o Dashboard (pedido do Edson em
31/10/2026), e por isso ele também é adiantado aqui, no período que abre primeiro.

A conta tem que ser feita de qualquer jeito. A escolha é só sobre QUEM espera: a
tarefa agendada, que já está rodando e não tem pressa, ou a pessoa, que acabou de
digitar a senha. Aqui ela passa para a tarefa.

Por que isto só funciona com o cache em arquivo
-----------------------------------------------
Quem importa é a tarefa `CabanaImportacao`; quem mostra a tela é o serviço
`CabanaSistema`. São dois processos. Com o cache na memória de cada um, aquecer
dentro da tarefa não chegaria ao serviço — a conta seria feita duas vezes e a pessoa
esperaria do mesmo jeito. Por isso `CACHES` aponta para uma pasta (config/settings/base.py).
"""

import logging
import time

from . import servicos

registrador = logging.getLogger(__name__)


def aquecer(importacao, estado=None, hoje=None):
    """Calcula e guarda as contas da abertura. Devolve quantos segundos levou.

    São quatro desde a 1.43.0: o painel, a Visão geral, "O que fazer agora" e o
    Dashboard sem filtro, que passou a ser a primeira tela depois de entrar.

    Nunca levanta erro. Isto roda no fim da importação, que já terminou e já gravou os
    números: derrubar a importação porque um cálculo de tela falhou trocaria uma tela
    lenta por uma loja sem dados novos.
    """
    if importacao is None:
        return 0.0
    from apps.importacao import servicos as importacao_servicos

    comeco = time.monotonic()
    try:
        servicos.painel_da_importacao(importacao)
        servicos.visao_da_importacao(importacao, hoje=hoje)
        servicos.agenda_da_importacao(
            importacao, estado if estado is not None else importacao_servicos.estado_dos_dados(),
            hoje=hoje)
        # O Dashboard abre logo depois de entrar desde a 1.43.0: o período padrão é o
        # que a pessoa vê primeiro, então é ele que fica pronto.
        from . import dashboard

        servicos.dashboard_da_importacao(importacao, dashboard.PERIODO_PADRAO)
    except Exception:  # noqa: BLE001 - tela lenta é melhor que importação derrubada
        registrador.exception("Não consegui adiantar as contas do painel da importação %s",
                              importacao.pk)
        return 0.0
    gasto = time.monotonic() - comeco
    registrador.info("Contas do painel adiantadas em %.1fs para a importação %s",
                     gasto, importacao.pk)
    return gasto


def aquecer_a_foto_de_hoje():
    """O mesmo, para a foto que está valendo agora. Chamado pela tarefa de hora em hora.

    A chave do cache carrega o DIA, porque a Visão geral conta conta vencida e conta a
    vencer, e isso vira à meia-noite sem ninguém tocar em nada. Então a conta adiantada
    ontem não serve hoje. A sincronização das 08:30 já cuida disso, mas quem abre o
    sistema antes dela — ou no dia em que ela não roda — pagaria a conta inteira.

    Como a tarefa dos alertas já acorda de hora em hora, aqui isto custa uma leitura de
    arquivo em 23 das 24 vezes: só a primeira depois da meia-noite calcula de verdade,
    e quem espera é a tarefa, não a pessoa.
    """
    from apps.importacao import servicos as importacao_servicos

    return aquecer(importacao_servicos.ultima_concluida())
