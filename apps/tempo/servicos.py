"""Gravar o tempo de um dia, venha ele da tela ou da busca automática."""

from decimal import Decimal, InvalidOperation

from django.utils import timezone

from apps.tempo import lugar as servico_de_lugar
from apps.tempo.fonte import DIAS_DE_PREVISAO, ErroDoTempo, FaltaOLugar, buscar
from apps.tempo.models import ConfiguracaoDoTempo, TempoDoDia


class ErroDeRegistro(Exception):
    """Mensagem pronta para a tela."""


def numero(bruto, nome, maximo=Decimal("999")):
    """Número da tela, com vírgula ou com ponto. Vazio é vazio, e não zero."""
    limpo = (bruto or "").strip().replace(" ", "").replace(",", ".")
    if not limpo:
        return None
    try:
        valor = Decimal(limpo)
    except (InvalidOperation, ValueError):
        raise ErroDeRegistro(f"{nome} tem que ser um número, como 23 ou 23,5.")
    if abs(valor) > maximo:
        raise ErroDeRegistro(f"{nome} está fora do que existe nesta cidade.")
    return valor.quantize(Decimal("0.1"))


def anotar(*, data, condicao="", chuva="", minima="", maxima="", feriado=False,
           observacao="", usuario=None):
    """Grava o que a pessoa escreveu. O escrito à mão manda sobre a busca automática."""
    if data is None:
        raise ErroDeRegistro("Escolha o dia.")
    if condicao and condicao not in TempoDoDia.Condicao.values:
        raise ErroDeRegistro("Escolha uma das condições da lista.")
    registro, _ = TempoDoDia.objects.get_or_create(data=data)
    registro.condicao = condicao
    registro.chuva_mm = numero(chuva, "A chuva", maximo=Decimal("9999"))
    registro.temperatura_minima = numero(minima, "A temperatura mínima")
    registro.temperatura_maxima = numero(maxima, "A temperatura máxima")
    registro.feriado = bool(feriado)
    registro.observacao = (observacao or "").strip()[:200]
    registro.origem = TempoDoDia.Origem.PESSOA
    registro.escrito_a_mao = True
    # Quem escreveu viu o dia pela janela; não é mais previsão, mesmo que a linha tenha
    # nascido como previsão da véspera.
    registro.previsao = False
    registro.atualizado_em = timezone.now()
    registro.atualizado_por = usuario if getattr(usuario, "is_authenticated", False) else None
    registro.save()
    return registro


def guardar_dias(dias):
    """Grava o que o serviço devolveu, sem passar por cima do que alguém escreveu.

    Devolve (novos, atualizados, respeitados). O "respeitados" são os dias em que
    alguém da loja já tinha escrito: o que a pessoa viu pela janela vale mais do que a
    média de um quadrado de alguns quilômetros.
    """
    novos = atualizados = respeitados = 0
    for dia in dias:
        registro = TempoDoDia.objects.filter(data=dia["data"]).first()
        if registro is None:
            TempoDoDia.objects.create(origem=TempoDoDia.Origem.AUTOMATICA, **dia)
            novos += 1
            continue
        if registro.escrito_a_mao:
            respeitados += 1
            continue
        for campo, valor in dia.items():
            setattr(registro, campo, valor)
        registro.origem = TempoDoDia.Origem.AUTOMATICA
        registro.atualizado_em = timezone.now()
        registro.save()
        atualizados += 1
    return novos, atualizados, respeitados


def descobrir_o_lugar(configuracao=None, abrir=None):
    """Preenche a latitude e a longitude a partir do nome da cidade, e guarda o que achou.

    É isto que torna a busca automática de verdade: quem configura escreve o nome da
    cidade, e não dois números de seis casas decimais pegos no Google Maps. Chamada
    sozinha pela busca de todo dia quando faltam as coordenadas, e pelo botão da tela
    quando alguém quer conferir na hora qual lugar o sistema entendeu.
    """
    configuracao = configuracao or ConfiguracaoDoTempo.atual()
    achado = servico_de_lugar.primeiro(configuracao.cidade, abrir=abrir)
    configuracao.latitude = achado.latitude
    configuracao.longitude = achado.longitude
    configuracao.lugar_encontrado = achado.escrito[:200]
    configuracao.save(update_fields=["latitude", "longitude", "lugar_encontrado",
                                     "atualizado_em"])
    return achado


def atualizar(configuracao=None, dias=7, dias_de_previsao=DIAS_DE_PREVISAO, abrir=None,
              abrir_lugar=None, hoje=None):
    """A busca de todo dia: os últimos dias, a previsão, e grava o que faltar.

    Guarda o erro na configuração em vez de estourar, porque quem roda isto é a tarefa
    agendada do Windows de madrugada: o erro precisa aparecer na tela no dia seguinte,
    e não só num log que ninguém abre.
    """
    configuracao = configuracao or ConfiguracaoDoTempo.atual()
    if not configuracao.tem_lugar:
        if not configuracao.cidade.strip():
            raise FaltaOLugar(
                "Falta a cidade da loja na tela de Tempo e venda. Escrevendo o nome da "
                "cidade, o sistema descobre as coordenadas sozinho."
            )
        # Primeira execução depois de alguém escrever a cidade: descobre o lugar e
        # segue para a busca do tempo na mesma rodada, sem esperar o dia seguinte.
        try:
            descobrir_o_lugar(configuracao, abrir=abrir_lugar)
        except ErroDoTempo as erro:
            configuracao.ultimo_erro = str(erro)[:300]
            configuracao.ultima_busca = timezone.now()
            configuracao.save(update_fields=["ultimo_erro", "ultima_busca", "atualizado_em"])
            raise
    try:
        achados = buscar(configuracao.latitude, configuracao.longitude, dias=dias,
                         dias_de_previsao=dias_de_previsao, abrir=abrir, hoje=hoje)
    except ErroDoTempo as erro:
        configuracao.ultimo_erro = str(erro)[:300]
        configuracao.ultima_busca = timezone.now()
        configuracao.save(update_fields=["ultimo_erro", "ultima_busca", "atualizado_em"])
        raise
    novos, atualizados, respeitados = guardar_dias(achados)
    configuracao.ultimo_erro = ""
    configuracao.ultima_busca = timezone.now()
    configuracao.save(update_fields=["ultimo_erro", "ultima_busca", "atualizado_em"])
    return novos, atualizados, respeitados
