"""Descobrir a latitude e a longitude a partir do nome da cidade.

Por que isto existe: até a 1.28.0 a busca do tempo só ligava depois que alguém abrisse o
Google Maps, clicasse com o botão direito no endereço da loja e copiasse dois números de
seis casas decimais para dentro de um formulário. Pedido o passo, ele não foi feito, e
sem as coordenadas a busca nunca rodou uma vez. O Edson pediu em 14/10/2026 "configurar
api de previsão do tempo automática": então o sistema passa a descobrir o lugar sozinho,
e o que se digita é o nome da cidade.

Quem responde é o serviço de geografia do próprio Open-Meteo, da mesma casa que dá a
previsão: aberto, sem cadastro e sem chave, e devolve JSON que a biblioteca padrão do
Python lê sem instalar nada.

Duas cautelas, porque nome de cidade se repete no Brasil:

- A escolha é a cidade de MAIOR POPULAÇÃO entre as do país, que é a leitura certa em
  praticamente todo caso ("Sorocaba" é a de São Paulo, não o distrito de Canelinha).
- O que o serviço entendeu volta escrito ("Sorocaba, São Paulo, Brasil") e fica guardado
  na configuração, à vista na tela. Sem isso, a cidade homônima de outro estado entraria
  calada e a chuva de lá entraria na conta do movimento daqui.
"""

import json
from dataclasses import dataclass
from decimal import Decimal
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from apps.tempo.fonte import ErroDoTempo

ENDERECO = "https://geocoding-api.open-meteo.com/v1/search"
TEMPO_LIMITE = 20
PAIS_PADRAO = "BR"
QUANTOS = 10


@dataclass
class Lugar:
    nome: str
    latitude: Decimal
    longitude: Decimal
    estado: str = ""
    pais: str = ""
    populacao: int = 0

    @property
    def escrito(self):
        """"Sorocaba, São Paulo, Brasil", que é como se confere se é a cidade certa."""
        return ", ".join(parte for parte in (self.nome, self.estado, self.pais) if parte)


def montar_endereco(nome, quantos=QUANTOS):
    return (f"{ENDERECO}?name={quote(nome.strip())}&count={max(int(quantos), 1)}"
            "&language=pt&format=json")


def ler(conteudo, pais=PAIS_PADRAO):
    """A resposta do serviço virada em lugares, do mais populoso para o menos.

    Separado de `procurar` para o teste poder exercitar a leitura sem sair à internet.
    """
    try:
        dados = json.loads(conteudo)
    except ValueError as erro:
        raise ErroDoTempo("O serviço de geografia respondeu algo que não é JSON.") from erro
    achados = dados.get("results") or []
    lugares = []
    for achado in achados:
        latitude, longitude = achado.get("latitude"), achado.get("longitude")
        if latitude is None or longitude is None:
            continue
        if pais and (achado.get("country_code") or "").upper() != pais.upper():
            continue
        lugares.append(Lugar(
            nome=achado.get("name") or "",
            latitude=Decimal(str(latitude)).quantize(Decimal("0.000001")),
            longitude=Decimal(str(longitude)).quantize(Decimal("0.000001")),
            estado=achado.get("admin1") or "",
            pais=achado.get("country") or "",
            # Sem população o serviço manda o campo ausente, e aí ela vale zero: o
            # lugar continua na lista, só não ganha a disputa com uma cidade grande.
            populacao=int(achado.get("population") or 0),
        ))
    lugares.sort(key=lambda lugar: -lugar.populacao)
    return lugares


def procurar(nome, pais=PAIS_PADRAO, abrir=None):
    """Os lugares com esse nome, do mais populoso para o menos. Lista vazia se não achar."""
    nome = (nome or "").strip()
    if not nome:
        raise ErroDoTempo("Escreva o nome da cidade da loja.")
    endereco = montar_endereco(nome)
    abrir = abrir or _abrir
    try:
        return ler(abrir(endereco), pais=pais)
    except ErroDoTempo:
        raise
    except URLError as erro:
        raise ErroDoTempo(
            "Não consegui falar com o serviço de geografia para descobrir onde fica "
            f"{nome}. Isso costuma ser internet fora ou bloqueio de saída no servidor "
            f"({erro.reason})."
        ) from erro
    except Exception as erro:  # noqa: BLE001 - urllib lança tipos variados
        raise ErroDoTempo(f"Não consegui descobrir onde fica {nome}: {erro}") from erro


def primeiro(nome, pais=PAIS_PADRAO, abrir=None):
    """A cidade mais populosa com esse nome, ou erro com a frase pronta para a tela."""
    lugares = procurar(nome, pais=pais, abrir=abrir)
    if not lugares:
        raise ErroDoTempo(
            f"O serviço de geografia não achou nenhuma cidade chamada \"{nome.strip()}\". "
            "Confira o nome, ou escreva a latitude e a longitude da loja à mão."
        )
    return lugares[0]


def _abrir(endereco):
    pedido = Request(endereco, headers={"User-Agent": "cabana-sistema"})
    with urlopen(pedido, timeout=TEMPO_LIMITE) as resposta:  # noqa: S310 - endereço fixo, https
        return resposta.read().decode("utf-8")
