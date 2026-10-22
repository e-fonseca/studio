"""Acesso ao painel já calculado, para outras telas não refazerem a conta."""

from django.core.cache import cache
from django.utils import timezone

from apps.core import versao
from apps.fornecedores import servicos as fornecedores

from . import indicadores, visao_geral as visao

# Trinta e seis horas. A chave já carrega o dia e a importação, então o que vence aqui
# é sempre sobra; o prazo existe só para a pasta não crescer para sempre. Era de seis
# horas, que é MENOS que o vão entre a sincronização das 19:30 e a das 08:30: a conta
# adiantada à noite vencia às 01:30 e a primeira pessoa do dia pagava de novo.
VALIDADE_CACHE = 60 * 60 * 36


def chave(importacao, hoje=None):
    """O que, se mudar, torna a conta guardada errada.

    * a **importação** e quantos produtos ela trouxe: foto nova, números novos;
    * o **prazo informado** do fornecedor: mexer num prazo muda a sugestão de reposição;
    * o **dia**: a Visão geral e "O que fazer agora" contam conta vencida e conta a
      vencer, que mudam à meia-noite sem ninguém tocar em nada. Sem o dia na chave, a
      tela amanhecia dizendo o que era verdade ontem;
    * a **versão do sistema**: o que está guardado é o objeto Python pronto, e a forma
      dele muda de uma versão para outra. Como o cache agora vive em `dados\\cache` e
      sobrevive à atualização de propósito, sem isto a versão nova leria um objeto da
      versão velha e a tela de abertura quebraria até a próxima importação.
    """
    dia = hoje or timezone.localdate()
    return (f"painel:{versao.atual().curta}:{importacao.pk}:{importacao.produtos}:"
            f"{fornecedores.versao_dos_prazos()}:{dia:%Y-%m-%d}")


def painel_da_importacao(importacao):
    """Calcula uma vez por importação; a conta roda sobre milhares de produtos."""
    guardado = cache.get(chave(importacao))
    if guardado is None:
        guardado = indicadores.montar(importacao)
        cache.set(chave(importacao), guardado, VALIDADE_CACHE)
    return guardado


def painel_pronto(importacao):
    """O painel só se já estiver calculado. Nunca dispara a conta: serve para telas
    que apenas enfeitam a página com um número, como os lembretes do dia."""
    if importacao is None:
        return None
    return cache.get(chave(importacao))


def visao_da_importacao(importacao, hoje=None):
    """A visão geral, calculada uma vez por importação como o painel."""
    if importacao is None:
        return visao.montar(None)
    chave_visao = "visao:" + chave(importacao, hoje)
    guardado = cache.get(chave_visao)
    if guardado is None:
        guardado = visao.montar(importacao, hoje=hoje)
        cache.set(chave_visao, guardado, VALIDADE_CACHE)
    return guardado


def agenda_da_importacao(importacao, estado, usuario=None, hoje=None):
    """A lista de tarefas da abertura, calculada uma vez por importação.

    A conta pesada é a lista de compra, que roda sobre os produtos todos. O resultado
    não depende de quem está olhando, então fica no cache inteiro e o filtro por
    permissão é aplicado depois, para cada pessoa.
    """
    from apps.compras import limite, lista_de_compra
    from apps.financeiro import servicos as financeiro

    from . import tarefas

    if importacao is None:
        return tarefas.montar(estado, usuario=usuario)
    chave_agenda = "agenda:" + chave(importacao, hoje)
    guardada = cache.get(chave_agenda)
    if guardada is None:
        resumo = financeiro.resumir(importacao, hoje=hoje)
        lista = lista_de_compra.priorizar(
            lista_de_compra.montar(importacao, hoje=hoje),
            # `teto_de` e não `montar`: aqui também só o teto é usado, e esta conta é a
            # da tela de abertura — a que a pessoa espera depois de digitar a senha.
            limite.teto_de(importacao, hoje=hoje, resumo_caixa=resumo),
        )
        guardada = tarefas.montar(estado, importacao, resumo, lista)
        cache.set(chave_agenda, guardada, VALIDADE_CACHE)
    return tarefas.para(guardada, usuario)
