"""De onde vem o tempo quando o sistema busca sozinho.

Open-Meteo: serviço aberto de meteorologia, sem cadastro e sem chave, com o tempo que
JÁ FEZ e com a PREVISÃO dos próximos dias. Escolhido por três motivos, nesta ordem: não
exige conta nem cartão, devolve o dia fechado com chuva em milímetros, e responde em
JSON simples, que a biblioteca padrão do Python lê sem instalar nada.

A mesma chamada traz os dois lados, e cada um serve a uma coisa diferente:

- **O dia que já fechou** é medição, e é dele que sai a conta de quanto a chuva custa à
  loja. Vem com `past_days`.
- **Os próximos dias** são previsão, e servem para a loja se preparar: o fim de semana é
  quando ela fatura, e saber na quinta-feira que vai chover no sábado é o que dá tempo
  de fazer alguma coisa. Vêm com `forecast_days` e ficam MARCADOS como previsão, porque
  média de previsão não mede nada (apps/tempo/models.py, campo `previsao`).

A busca é tarefa de servidor, nunca de tela: nenhuma página do sistema espera a
internet para abrir (é decisão registrada na ficha técnica). Se a internet da loja
estiver fora, o dia simplesmente fica sem registro automático e alguém pode escrever na
tela — nada quebra e nada fica pela metade.
"""

import json
from datetime import date, timedelta
from decimal import Decimal
from urllib.error import URLError
from urllib.request import Request, urlopen

ENDERECO = "https://api.open-meteo.com/v1/forecast"
TEMPO_LIMITE = 20
# Quantos dias para frente a previsão alcança. Sete cobre sempre o próximo fim de
# semana, que é o que a loja precisa saber de véspera, qualquer que seja o dia de hoje.
DIAS_DE_PREVISAO = 7

# Os códigos de tempo da Organização Meteorológica Mundial, agrupados no que muda o
# movimento da loja. Não interessa distinguir "garoa congelante" de "chuvisco": o que
# muda a venda é se deu para sair de casa.
CODIGOS = {
    "sol": {0, 1},
    "nublado": {2, 3, 45, 48},
    "chuva": {51, 53, 55, 56, 57, 61, 63, 66, 67, 80, 81},
    "chuva_forte": {65, 82},
    "tempestade": {95, 96, 99},
}


class ErroDoTempo(Exception):
    """Falha na busca, com mensagem pronta para a tela."""


class FaltaOLugar(ErroDoTempo):
    """Ainda não se sabe onde é a loja: é campo em branco, e não falha do sistema.

    Separado para a tarefa agendada do Windows não terminar em erro por causa disso. Um
    campo que ninguém preencheu ainda tem que aparecer na tela, não no log de falhas.
    """


def condicao_do_codigo(codigo):
    """O código da OMM traduzido para as cinco condições que a loja usa."""
    if codigo is None:
        return ""
    for condicao, codigos in CODIGOS.items():
        if int(codigo) in codigos:
            return condicao
    return "nublado"


def _decimal(valor, casas="0.1"):
    if valor is None:
        return None
    return Decimal(str(valor)).quantize(Decimal(casas))


def montar_endereco(latitude, longitude, dias=7, dias_de_previsao=DIAS_DE_PREVISAO):
    """O endereço da consulta: os últimos dias fechados, hoje e os próximos dias."""
    campos = "weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum"
    return (f"{ENDERECO}?latitude={latitude}&longitude={longitude}&daily={campos}"
            f"&past_days={max(int(dias), 1)}"
            f"&forecast_days={max(int(dias_de_previsao), 1)}"
            "&timezone=America%2FSao_Paulo")


def ler(conteudo, hoje=None):
    """Transforma a resposta do serviço em uma lista de dias. Separado para poder testar.

    Hoje e os dias seguintes saem marcados como previsão. Hoje entra na marca de
    propósito: às 06:10 da manhã o dia não fechou, e a chuva que vai cair à tarde ainda
    é palpite. A busca de amanhã devolve o mesmo dia já fechado e a marca cai.
    """
    hoje = hoje or date.today()
    try:
        dados = json.loads(conteudo)
    except ValueError as erro:
        raise ErroDoTempo("O serviço de meteorologia respondeu algo que não é JSON.") from erro
    diario = dados.get("daily") or {}
    datas = diario.get("time") or []
    if not datas:
        raise ErroDoTempo("O serviço de meteorologia não devolveu nenhum dia.")
    codigos = diario.get("weathercode") or []
    maximas = diario.get("temperature_2m_max") or []
    minimas = diario.get("temperature_2m_min") or []
    chuvas = diario.get("precipitation_sum") or []
    dias = []
    for posicao, texto in enumerate(datas):
        try:
            quando = date.fromisoformat(texto)
        except ValueError:
            continue
        dias.append({
            "data": quando,
            "condicao": condicao_do_codigo(codigos[posicao] if posicao < len(codigos) else None),
            "temperatura_maxima": _decimal(maximas[posicao] if posicao < len(maximas) else None),
            "temperatura_minima": _decimal(minimas[posicao] if posicao < len(minimas) else None),
            "chuva_mm": _decimal(chuvas[posicao] if posicao < len(chuvas) else None),
            "previsao": quando >= hoje,
        })
    return dias


def buscar(latitude, longitude, dias=7, dias_de_previsao=DIAS_DE_PREVISAO, abrir=None,
           hoje=None):
    """Os últimos dias e a previsão. `abrir` existe para o teste não sair à internet."""
    endereco = montar_endereco(latitude, longitude, dias, dias_de_previsao)
    abrir = abrir or _abrir
    try:
        return ler(abrir(endereco), hoje=hoje)
    except ErroDoTempo:
        raise
    except URLError as erro:
        raise ErroDoTempo(
            "Não consegui falar com o serviço de meteorologia. Isso costuma ser internet "
            f"fora ou bloqueio de saída no servidor ({erro.reason})."
        ) from erro
    except Exception as erro:  # noqa: BLE001 - urllib lança tipos variados
        raise ErroDoTempo(f"Não consegui buscar o tempo: {erro}") from erro


def _abrir(endereco):
    pedido = Request(endereco, headers={"User-Agent": "studio-sistema"})
    with urlopen(pedido, timeout=TEMPO_LIMITE) as resposta:  # noqa: S310 - endereço fixo, https
        return resposta.read().decode("utf-8")


def ontem(hoje=None):
    return (hoje or date.today()) - timedelta(days=1)
