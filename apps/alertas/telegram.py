"""Manda o aviso pelo Telegram, e registra o que aconteceu.

Pedido do Edson em 11/10/2026: "quero junto ao e-mail também seja enviado notificação
pelo telegram". O Telegram chega no bolso em segundos, então ele carrega o que faz a
pessoa parar e olhar — a manchete e os números —, e o e-mail continua levando o
relatório inteiro, com as tabelas.

Decisões que este arquivo carrega:

- **Nada de biblioteca nova.** É um POST para api.telegram.org, e `urllib` do próprio
  Python faz isso. Instalar um pacote a mais no servidor da loja, que atualiza por zip
  e não tem internet garantida, custaria mais do que as vinte linhas daqui.
- **O erro vira frase de loja.** O Telegram responde `{"ok":false,"error_code":400,
  "description":"Bad Request: chat not found"}`, que não diz a ninguém o que fazer.
- **Falha nunca derruba quem chamou**, igual ao e-mail: quem manda é tarefa agendada
  ou botão de tela, e nos dois casos a resposta certa é registrar e seguir.
- **Mensagem sem formatação.** O Telegram tem Markdown e HTML, e os dois obrigam a
  escapar caractere a caractere; nome de produto da loja tem `*`, `_`, `(` e `.` à
  vontade. Texto puro nunca estraga a mensagem nem some com um pedaço dela.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

from django.utils import timezone

from apps.alertas import relatorios
from apps.alertas.models import Canal, ConfiguracaoDeTelegram, EnvioDeRelatorio
from apps.core import https

# Fora de um teste isto nunca muda; é constante para o teste não ter que falar com a
# internet para provar que a mensagem foi montada certa.
API = "https://api.telegram.org"

# O Telegram corta mensagem acima de 4096 caracteres. Cortamos antes, com aviso, porque
# mensagem cortada pelo servidor perde justamente o fim, onde está o link.
MAXIMO = 3500

SEGUNDOS_DE_ESPERA = 20

# Quantas linhas de cada bloco entram no aviso. Três, porque aviso de celular que precisa
# de rolagem deixa de ser aviso e passa a ser relatório — e relatório vai por e-mail.
LINHAS_NO_AVISO = 3

# O que o Telegram responde, e o que a pessoa precisa fazer a respeito.
TRADUCOES = (
    ("unauthorized",
     "O Telegram não reconheceu o token do robô. Confira se ele foi copiado inteiro do "
     "BotFather, sem espaço no começo nem no fim."),
    ("chat not found",
     "O Telegram não encontrou essa conversa. Mande qualquer mensagem para o robô no "
     "celular e use o botão \"Descobrir a conversa\" aqui na tela: o número muda se o "
     "robô for trocado."),
    ("bot was blocked by the user",
     "O robô foi bloqueado nessa conversa. Desbloqueie no Telegram e mande qualquer "
     "mensagem para ele."),
    ("bot can't initiate conversation",
     "O robô não pode falar primeiro. Abra o Telegram, procure o robô e mande qualquer "
     "mensagem para ele; depois use o botão \"Descobrir a conversa\"."),
    ("not enough rights",
     "O robô está no grupo mas não tem permissão para escrever nele. Dê permissão de "
     "enviar mensagem ao robô nas configurações do grupo."),
    # O grupo comum vira supergrupo quando alguém muda certas configurações dele, e o
    # número muda junto; o número antigo passa a dar este erro para sempre.
    ("upgraded to a supergroup",
     "O grupo mudou de número no Telegram (virou supergrupo). Use \"Descobrir a conversa\" "
     "aqui na tela e escolha o grupo de novo."),
    ("bot was kicked",
     "O robô foi tirado do grupo. Ponha o robô de volta no grupo pelo Telegram (Adicionar "
     "membro) e mande o teste de novo."),
    ("bot is not a member",
     "O robô não está nesse grupo. Ponha o robô no grupo pelo Telegram (Adicionar membro) e "
     "use \"Descobrir a conversa\" aqui na tela."),
    ("name or service not known",
     "O servidor da loja não conseguiu resolver api.telegram.org. É internet do servidor "
     "ou DNS; o e-mail usa outro caminho e pode continuar funcionando."),
    ("timed out",
     "O Telegram não respondeu a tempo. Costuma ser internet do servidor da loja, ou "
     "firewall bloqueando a saída para a internet."),
    ("certificate verify failed",
     "A conexão segura com o Telegram não foi aceita pelo servidor da loja. Isso costuma "
     "ser data e hora erradas no Windows, ou antivírus inspecionando a conexão."),
)


def explicar(erro):
    """O erro do Telegram em frase de loja, com a resposta original no fim."""
    texto = str(erro)
    achatado = texto.lower()
    for pedaco, explicacao in TRADUCOES:
        if pedaco in achatado:
            return f"{explicacao} (o Telegram respondeu: {texto})"
    return texto


class ErroDoTelegram(Exception):
    """O Telegram respondeu, mas disse não."""


def _pedir(token, metodo, dados=None):
    """Chama um método da API e devolve o `result`. Levanta ErroDoTelegram se não deu.

    Tudo o que fala com a internet passa por aqui, numa função só: é o único ponto que
    um teste precisa substituir para provar o resto sem sair da máquina.
    """
    endereco = f"{API}/bot{token}/{metodo}"
    corpo = urllib.parse.urlencode(dados or {}).encode("utf-8")
    pedido = urllib.request.Request(endereco, data=corpo, method="POST")
    try:
        with urllib.request.urlopen(pedido, timeout=SEGUNDOS_DE_ESPERA) as resposta:
            resultado = json.loads(resposta.read().decode("utf-8"))
    except urllib.error.HTTPError as erro:
        # O Telegram manda o motivo no corpo do 400 e do 401; sem ler o corpo a pessoa
        # receberia "HTTP Error 400: Bad Request", que não ajuda ninguém.
        detalhe = ""
        try:
            detalhe = json.loads(erro.read().decode("utf-8")).get("description", "")
        except (ValueError, OSError):
            detalhe = erro.reason or ""
        raise ErroDoTelegram(detalhe or f"erro {erro.code}") from erro
    except (urllib.error.URLError, OSError, ValueError) as erro:
        raise ErroDoTelegram(getattr(erro, "reason", None) or erro) from erro
    if not resultado.get("ok"):
        raise ErroDoTelegram(resultado.get("description") or "resposta sem explicação")
    return resultado.get("result")


def _cortar(texto):
    if len(texto) <= MAXIMO:
        return texto
    return texto[:MAXIMO].rstrip() + "\n\n[…] O relatório inteiro está no sistema."


def mandar_texto(token, chat_id, texto):
    """Manda um texto pronto a uma conversa. Levanta ErroDoTelegram se não deu.

    Sem formatação e sem prévia de link, pelos motivos do alto deste arquivo. É o que o
    relatório e o aviso das metas (apps/alertas/metas.py) usam para sair.
    """
    return _pedir(token, "sendMessage", {
        "chat_id": chat_id,
        "text": _cortar(texto),
        "disable_web_page_preview": "true",
    })


def texto_do_relatorio(relatorio, configuracao_de_email=None):
    """O relatório em texto curto, do jeito que se lê numa notificação do celular.

    A manchete primeiro, porque é ela que decide se a pessoa abre o resto. Depois os
    blocos, só com título e as primeiras linhas — a tabela inteira é assunto do e-mail.
    """
    partes = [f"Cabana · {relatorio.assunto}"]
    if relatorio.data_corte:
        partes.append(f"Dados de {relatorio.data_corte:%d/%m/%Y}")
    partes.append("")
    if relatorio.manchete:
        partes.append(relatorio.manchete)
    if relatorio.aviso:
        partes.append(f"Atenção: {relatorio.aviso}")
    for bloco in relatorio.blocos:
        partes.append("")
        partes.append(bloco.titulo)
        if bloco.frase:
            partes.append(bloco.frase)
        for linha in bloco.linhas[:LINHAS_NO_AVISO]:
            quem = linha.get("quem") or ""
            valor = linha.get("valor") or ""
            partes.append(f"· {quem} — {valor}" if valor else f"· {quem}")
        if bloco.escondidas:
            partes.append(f"· e mais {bloco.escondidas} no sistema")
    partes.append("")
    partes.append(f"Aberto em {timezone.localtime():%d/%m/%Y %H:%M}. No sistema: "
                  + https.endereco_do_sistema(relatorio.caminho or "/sistema/"))
    return _cortar("\n".join(partes))


def enviar(relatorio, configuracao=None, disparado_por=""):
    """Manda um relatório pelo Telegram e devolve o registro, tenha dado certo ou não."""
    configuracao = configuracao or ConfiguracaoDeTelegram.atual()
    registro = EnvioDeRelatorio(
        rotina=relatorio.rotina,
        canal=Canal.TELEGRAM,
        resumo=relatorio.resumo[:300],
        destinatarios=configuracao.para_quem,
        disparado_por=disparado_por[:60],
        assunto=relatorio.assunto[:250],
    )
    faltas = configuracao.o_que_falta
    if faltas:
        registro.erro = "Falta preencher na tela de alertas: " + ", ".join(faltas) + "."
        registro.save()
        return registro
    try:
        mandar_texto(configuracao.token, configuracao.chat_id, texto_do_relatorio(relatorio))
    except ErroDoTelegram as erro:
        registro.erro = explicar(erro)
    else:
        registro.deu_certo = True
    registro.save()
    return registro


def enviar_rotina(rotina, configuracao=None, disparado_por="", forcar=False, relatorio=None):
    """Monta o relatório da rotina e avisa, se houver notícia.

    A regra é a mesma do e-mail: sem notícia não manda, senão o aviso do celular vira
    ruído e deixa de ser lido no dia em que trouxer uma conta vencida. `relatorio` existe
    para quem já montou o relatório para o e-mail não montá-lo duas vezes — são as mesmas
    contas das telas, e algumas passam por onze mil produtos.
    """
    configuracao = configuracao or ConfiguracaoDeTelegram.atual()
    relatorio = relatorio or relatorios.montar(rotina)
    if not relatorio.tem_noticia and not forcar:
        registro = EnvioDeRelatorio(
            rotina=rotina,
            canal=Canal.TELEGRAM,
            resumo=relatorio.resumo[:300],
            sem_noticia=True,
            destinatarios=configuracao.para_quem,
            disparado_por=disparado_por[:60],
        )
        registro.save()
        return registro
    return enviar(relatorio, configuracao, disparado_por=disparado_por)


def enviar_teste(configuracao=None, disparado_por=""):
    return enviar(relatorios.de_teste(), configuracao, disparado_por=disparado_por)


def descobrir_chats(configuracao=None):
    """As conversas que já falaram com o robô, para a tela preencher o chat sozinha.

    Existe porque o número do chat não está em lugar nenhum visível do Telegram, e
    pedir que a pessoa descubra sozinha é pedir que ela instale outro robô para isso.
    O robô não consegue escrever para quem nunca falou com ele, então mandar uma
    mensagem para o robô é passo obrigatório de qualquer forma — e é o que faz a
    conversa aparecer aqui.

    Devolve (chats, erro): a lista do mais recente para o mais antigo, sem repetir.
    """
    configuracao = configuracao or ConfiguracaoDeTelegram.atual()
    if not configuracao.tem_token:
        return [], "Primeiro grave o token do robô; sem ele não há o que perguntar ao Telegram."
    try:
        atualizacoes = _pedir(configuracao.token, "getUpdates", {"limit": 50}) or []
    except ErroDoTelegram as erro:
        return [], explicar(erro)

    achados, vistos = [], set()
    for atualizacao in reversed(atualizacoes):
        mensagem = (atualizacao.get("message") or atualizacao.get("channel_post")
                    or atualizacao.get("my_chat_member") or {})
        chat = mensagem.get("chat") or {}
        identificador = chat.get("id")
        if identificador is None or identificador in vistos:
            continue
        vistos.add(identificador)
        achados.append({"id": str(identificador), "nome": _nome_do_chat(chat)})
    if not achados:
        return [], ("O robô ainda não recebeu mensagem de ninguém. Abra o Telegram, "
                    "procure o robô pelo nome de usuário dele e mande qualquer mensagem; "
                    "depois volte e clique aqui de novo.")
    return achados, ""


def _nome_do_chat(chat):
    titulo = chat.get("title")
    if titulo:
        return titulo
    nome = " ".join(p for p in (chat.get("first_name"), chat.get("last_name")) if p)
    apelido = chat.get("username")
    if nome and apelido:
        return f"{nome} (@{apelido})"
    return nome or (f"@{apelido}" if apelido else "conversa sem nome")


def ultimo_de_cada_rotina():
    """O último aviso de cada rotina, para a tela mostrar o estado de cada um."""
    from apps.alertas.models import Rotina

    return {
        rotina: EnvioDeRelatorio.objects.filter(rotina=rotina, canal=Canal.TELEGRAM).first()
        for rotina in Rotina.values
    }
