"""A faixa de cotações do topo (1.50.0): o dólar comercial e as principais ações da B3.

Pedido do Edson em 06/11/2026: *"na parte de cima do menu colocar a data e hora em real
time / (...) uma linha formato carrossel informando valor do dólar comercial no momento em
destaque e os principais ações em alta e queda em real time"*.

De onde vem cada número, os dois de graça e sem cadastro:

- **Dólar comercial**: AwesomeAPI (economia.awesomeapi.com.br), o preço de VENDA, que é o
  do jornal ("o dólar fechou a R$ 5,42"). Lido no máximo uma vez por minuto.
- **Ações**: brapi.dev. Sem cadastro ela responde quatro ações, que estão entre as que mais
  pesam na bolsa (Petrobras, Vale, Itaú) e uma do varejo (Magalu). No plano grátis o preço
  chega com uns 30 minutos de atraso (o preço ao vivo da B3 é pago), e por isso a faixa
  diz a hora do preço. Lidas no máximo a cada 15 minutos.

Nenhuma página espera a internet (decisão da ficha técnica, a mesma do tempo em
apps/tempo/fonte.py): a tela lê só o que está guardado no cache, e quem vai à internet é
uma busca em segundo plano, uma de cada vez, quando o guardado envelheceu. Sem internet,
a faixa mostra o último valor com a hora dele; sem valor nenhum, fica só o relógio.
"""

import json
import logging
import threading
from datetime import datetime, timedelta, timezone as fuso
from decimal import Decimal, InvalidOperation
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.core.templatetags.cabana import reais

logger = logging.getLogger(__name__)

SAO_PAULO = ZoneInfo("America/Sao_Paulo")
ENDERECO_DO_DOLAR = "https://economia.awesomeapi.com.br/json/last/USD-BRL"
ENDERECO_DA_ACAO = "https://brapi.dev/api/quote/{codigo}"
ACOES = (("PETR4", "Petrobras"), ("VALE3", "Vale"), ("ITUB4", "Itaú"), ("MGLU3", "Magalu"))
TEMPO_LIMITE = 8
# De quanto em quanto tempo cada lado volta à internet, enquanto alguém estiver com o
# sistema aberto. Ninguém olhando, ninguém busca.
VALIDADE_DO_DOLAR = timedelta(minutes=1)
VALIDADE_DAS_ACOES = timedelta(minutes=15)
CHAVE = "cotacoes:faixa"
CHAVE_DA_BUSCA = "cotacoes:buscando"
# A trava solta sozinha depois disto, se a busca morrer no meio: 5 pedidos de 8 s cabem.
PRAZO_DA_BUSCA = 60


def _abrir(endereco):
    pedido = Request(endereco, headers={"User-Agent": "studio-sistema", "Accept": "application/json"})
    with urlopen(pedido, timeout=TEMPO_LIMITE) as resposta:  # noqa: S310 - endereço fixo, https
        return json.loads(resposta.read().decode("utf-8"))


def _decimal(valor):
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return numero if numero.is_finite() else None


def _quando(valor):
    """A hora de um preço, venha como segundos desde 1970 ou como texto ISO."""
    try:
        if isinstance(valor, (int, float)) or str(valor).isdigit():
            return datetime.fromtimestamp(int(valor), tz=fuso.utc)
        quando = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError, OSError):
        return None
    return quando if quando.tzinfo else quando.replace(tzinfo=fuso.utc)


def ler_dolar(dados):
    """O dólar do JSON da AwesomeAPI, ou None se a resposta não for a esperada (limite de
    pedidos, erro, formato novo): resposta estranha nunca vira cotação na tela."""
    par = dados.get("USDBRL") if isinstance(dados, dict) else None
    if not isinstance(par, dict):
        return None
    valor = _decimal(par.get("ask"))
    if valor is None or valor <= 0:
        return None
    variacao = _decimal(par.get("pctChange"))
    quando = _quando(par.get("timestamp"))
    return {"valor": str(valor), "variacao": None if variacao is None else str(variacao),
            "hora": quando.isoformat() if quando else None}


def ler_acao(dados, codigo, nome):
    """Uma ação do JSON da brapi, ou None se a resposta não for a esperada."""
    resultados = dados.get("results") if isinstance(dados, dict) else None
    if not isinstance(resultados, list) or not resultados or not isinstance(resultados[0], dict):
        return None
    resultado = resultados[0]
    preco = _decimal(resultado.get("regularMarketPrice"))
    variacao = _decimal(resultado.get("regularMarketChangePercent"))
    if preco is None or preco <= 0 or variacao is None:
        return None
    quando = _quando(resultado.get("regularMarketTime"))
    return {"codigo": codigo, "nome": nome, "preco": str(preco), "variacao": str(variacao),
            "hora": quando.isoformat() if quando else None}


def _velho(quando, validade, agora):
    lido = _quando(quando)
    return lido is None or agora - lido >= validade


def atualizar(abrir=None, agora=None):
    """Vai à internet buscar o que envelheceu e guarda no cache. Falha nunca apaga o que já
    havia, e conta como busca feita: sem internet, ninguém fica batendo na porta."""
    abrir = abrir or _abrir
    agora = agora or timezone.now()
    guardado = dict(cache.get(CHAVE) or {})
    if _velho(guardado.get("dolar_lido_em"), VALIDADE_DO_DOLAR, agora):
        dolar = _tentar(lambda: ler_dolar(abrir(ENDERECO_DO_DOLAR)), "o dólar")
        if dolar:
            guardado["dolar"] = dolar
        guardado["dolar_lido_em"] = agora.isoformat()
    if _velho(guardado.get("acoes_lidas_em"), VALIDADE_DAS_ACOES, agora):
        antes = {acao["codigo"]: acao for acao in guardado.get("acoes") or []}
        acoes = []
        for codigo, nome in ACOES:
            acao = _tentar(lambda c=codigo, n=nome: ler_acao(abrir(ENDERECO_DA_ACAO.format(codigo=c)), c, n),
                           codigo) or antes.get(codigo)
            if acao:
                acoes.append(acao)
        guardado["acoes"] = acoes
        guardado["acoes_lidas_em"] = agora.isoformat()
    cache.set(CHAVE, guardado, None)
    return guardado


def _tentar(buscar, o_que):
    try:
        return buscar()
    except Exception as erro:  # noqa: BLE001 - sem internet a faixa fica com o último valor
        logger.info("Cotação de %s não veio: %s", o_que, erro)
        return None


def faixa(agora=None):
    """O que a faixa mostra agora, lido do cache: nunca espera a internet."""
    agora = agora or timezone.now()
    guardado = cache.get(CHAVE) or {}
    envelheceu = (_velho(guardado.get("dolar_lido_em"), VALIDADE_DO_DOLAR, agora)
                  or _velho(guardado.get("acoes_lidas_em"), VALIDADE_DAS_ACOES, agora))
    if envelheceu and getattr(settings, "COTACOES_NA_INTERNET", True):
        _buscar_em_segundo_plano()
    return para_tela(guardado, agora)


def _buscar_em_segundo_plano():
    # `add` só grava se a chave ainda não existe: é a trava entre os processos e as abas.
    if cache.add(CHAVE_DA_BUSCA, True, timeout=PRAZO_DA_BUSCA):
        threading.Thread(target=_buscar_e_soltar, name="cotacoes", daemon=True).start()


def _buscar_e_soltar():
    try:
        atualizar()
    except Exception:  # noqa: BLE001 - a busca é enfeite; a tela segue sem ela
        logger.exception("A busca das cotações falhou")
    finally:
        cache.delete(CHAVE_DA_BUSCA)


def _variacao(numero):
    if numero is None:
        return {"variacao": "", "seta": "", "sentido": "neutro"}
    texto = f"{abs(numero):.2f}".replace(".", ",") + "%"
    if numero > 0:
        return {"variacao": "+" + texto, "seta": "▲", "sentido": "alta"}
    if numero < 0:
        return {"variacao": "-" + texto, "seta": "▼", "sentido": "queda"}
    return {"variacao": texto, "seta": "=", "sentido": "neutro"}


def _hora(texto, agora):
    """"às 10:00" para hoje; "em 05/11 às 17:59" para o preço de outro dia (bolsa fechada)."""
    quando = _quando(texto)
    if quando is None:
        return ""
    local, hoje = quando.astimezone(SAO_PAULO), agora.astimezone(SAO_PAULO).date()
    if local.date() == hoje:
        return f"às {local:%H:%M}"
    return f"em {local:%d/%m} às {local:%H:%M}"


def para_tela(guardado, agora=None):
    """O guardado no jeito da tela: reais, porcentagem com sinal, seta, cor e hora."""
    agora = agora or timezone.now()
    tela = {"dolar": None, "grupos": [], "hora_das_acoes": ""}
    dolar = guardado.get("dolar") or {}
    valor = _decimal(dolar.get("valor"))
    if valor:
        tela["dolar"] = {"valor": reais(valor), **_variacao(_decimal(dolar.get("variacao"))),
                         "hora": _hora(dolar.get("hora"), agora)}
    acoes = []
    for acao in guardado.get("acoes") or []:
        preco, variacao = _decimal(acao.get("preco")), _decimal(acao.get("variacao"))
        if preco and variacao is not None:
            acoes.append({"codigo": acao.get("codigo", ""), "nome": acao.get("nome", ""),
                          "preco": reais(preco), "numero": variacao, **_variacao(variacao)})
    for titulo, escolhe, maior_primeiro in (("Em alta", lambda n: n > 0, True),
                                            ("Em queda", lambda n: n < 0, False),
                                            ("Sem mudança", lambda n: n == 0, False)):
        grupo = sorted((a for a in acoes if escolhe(a["numero"])), key=lambda a: a["numero"],
                       reverse=maior_primeiro)
        if grupo:
            tela["grupos"].append({"titulo": titulo, "acoes": grupo})
    horas = [_quando(acao.get("hora")) for acao in guardado.get("acoes") or []]
    horas = [hora for hora in horas if hora]
    if acoes and horas:
        tela["hora_das_acoes"] = _hora(max(horas).isoformat(), agora)
    return tela
