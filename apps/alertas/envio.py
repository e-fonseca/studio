"""Monta e manda o e-mail, e registra o que aconteceu.

O caminho é curto de propósito: um relatório vira HTML e texto, o Django manda pelo
SMTP configurado na tela, e o resultado entra em `EnvioDeRelatorio`. Fora disso não há
fila, nem repetição automática, nem serviço novo — a tarefa agendada do Windows já é o
relógio, e repetir um e-mail que falhou cedo demais é a melhor forma de a caixa de
e-mail da loja ser bloqueada por excesso de tentativa.

Três coisas que este arquivo faz questão de garantir:

- **O erro vira frase de loja.** `smtplib` devolve "(535, b'5.7.8 Username and Password
  not accepted')", que não diz a ninguém o que fazer. `_explicar` traduz os casos que
  acontecem de verdade, e o que sobra vai cru, porque um erro desconhecido escondido é
  pior do que um erro feio.
- **Falha de e-mail nunca derruba quem chamou.** Quem manda é uma tarefa agendada de
  madrugada ou um botão de tela; nos dois casos a resposta certa é registrar e seguir.
- **Toda tentativa fica registrada**, inclusive a que nem saiu por falta de
  configuração. "Não recebi o e-mail de ontem" precisa de resposta.
"""

import smtplib

from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from django.utils import timezone

from apps.alertas import relatorios
from apps.alertas.models import Canal, ConfiguracaoDeEmail, EnvioDeRelatorio, Rotina

# O que o SMTP devolve, e o que a pessoa precisa fazer a respeito.
TRADUCOES = (
    ("username and password not accepted",
     "O servidor de e-mail recusou o usuário e a senha. Confira os dois na tela: a senha é "
     "a da caixa que envia, a mesma de quem entra no webmail dela. (Se um dia o envio for "
     "por Gmail, aí precisa de senha de aplicativo, não da senha da conta.)"),
    ("application-specific password required",
     "A conta do Google exige senha de aplicativo. Gere uma na conta do Google e cole aqui "
     "no lugar da senha normal."),
    ("authentication failed",
     "O servidor de e-mail recusou o usuário e a senha. Confira os dois: o usuário é o "
     "endereço inteiro, com o @ e o domínio, e a senha é a da caixa que envia."),
    ("name or service not known",
     "O servidor de e-mail não foi encontrado pelo nome. Confira o endereço do servidor de "
     "saída e se o servidor da loja está com internet."),
    ("connection refused",
     "O servidor de e-mail recusou a conexão. Confira a porta: na Hostinger é 465."),
    ("timed out",
     "O servidor de e-mail não respondeu a tempo. Costuma ser internet do servidor, "
     "firewall bloqueando a porta de saída, ou a porta trocada (465 e 587 não são a mesma "
     "coisa: a 465 é SSL e a 587 é TLS)."),
    ("wrong version number",
     "O servidor atendeu, mas não falou a mesma língua: é a porta trocada. A 465 é SSL e a "
     "587 é TLS. Na Hostinger, use 465."),
)


def _explicar(erro):
    texto = str(erro)
    achatado = texto.lower()
    for pedaco, explicacao in TRADUCOES:
        if pedaco in achatado:
            return f"{explicacao} (o servidor respondeu: {texto})"
    return texto


def _conexao(configuracao):
    """Abre a conexão do jeito que a porta pede: 465 é SSL direto, 587 é STARTTLS.

    O Django não deixa ligar os dois ao mesmo tempo, e ligar o errado não dá erro de
    senha: dá conexão travada ou derrubada, que é bem mais difícil de entender.
    """
    seguro = {"use_ssl": True} if configuracao.porta_de_ssl else {"use_tls": configuracao.usar_tls}
    return get_connection(
        backend="django.core.mail.backends.smtp.EmailBackend",
        host=configuracao.servidor,
        port=configuracao.porta,
        username=configuracao.usuario,
        password=configuracao.senha,
        timeout=30,
        **seguro,
    )


def _de(configuracao):
    nome = (configuracao.remetente or "").strip()
    return f"{nome} <{configuracao.usuario}>" if nome else configuracao.usuario


def _assunto(relatorio):
    quando = timezone.localdate().strftime("%d/%m/%Y")
    return f"[Cabana] {relatorio.assunto} — {quando}"


def montar_mensagem(relatorio, configuracao):
    """O e-mail pronto, em HTML com alternativa em texto puro.

    Texto puro junto porque nem toda caixa mostra HTML, e porque um e-mail que chega
    vazio num celular antigo é o mesmo que não chegar.
    """
    contexto = {"r": relatorio, "configuracao": configuracao,
                "quando": timezone.localtime()}
    corpo_texto = render_to_string("alertas/email/relatorio.txt", contexto)
    corpo_html = render_to_string("alertas/email/relatorio.html", contexto)
    mensagem = EmailMultiAlternatives(
        subject=_assunto(relatorio),
        body=corpo_texto,
        from_email=_de(configuracao),
        to=configuracao.lista_de_destinatarios,
    )
    mensagem.attach_alternative(corpo_html, "text/html")
    return mensagem


def enviar(relatorio, configuracao=None, disparado_por=""):
    """Manda um relatório e devolve o registro do envio, tenha dado certo ou não."""
    configuracao = configuracao or ConfiguracaoDeEmail.atual()
    registro = EnvioDeRelatorio(
        rotina=relatorio.rotina,
        canal=Canal.EMAIL,
        resumo=relatorio.resumo[:300],
        destinatarios=", ".join(configuracao.lista_de_destinatarios),
        disparado_por=disparado_por[:60],
    )
    faltas = configuracao.o_que_falta
    if faltas:
        registro.erro = "Falta preencher na tela de alertas: " + ", ".join(faltas) + "."
        registro.save()
        return registro

    registro.assunto = _assunto(relatorio)
    try:
        with _conexao(configuracao) as conexao:
            mensagem = montar_mensagem(relatorio, configuracao)
            mensagem.connection = conexao
            mensagem.send(fail_silently=False)
    except (smtplib.SMTPException, OSError, ValueError) as erro:
        registro.erro = _explicar(erro)
    else:
        registro.deu_certo = True
    registro.save()
    return registro


def enviar_avulso(*, assunto, texto, html, para, configuracao=None):
    """Um e-mail que não é relatório, a uma pessoa só (1.43.0: o código de criar a senha nova).

    Usa o mesmo servidor, a mesma caixa e a mesma tradução de erro dos relatórios, e não
    entra em `EnvioDeRelatorio`: quem registra o que aconteceu é quem pediu o envio (a
    recuperação de senha grava na auditoria). Devolve None quando o e-mail saiu, ou a
    frase do erro, já traduzida, quando não saiu. Nunca levanta erro.
    """
    configuracao = configuracao or ConfiguracaoDeEmail.atual()
    if not configuracao.pode_enviar:
        return "O envio de e-mail do sistema não está configurado (tela Alertas)."
    try:
        with _conexao(configuracao) as conexao:
            mensagem = EmailMultiAlternatives(
                subject=assunto, body=texto, from_email=_de(configuracao), to=[para],
                connection=conexao,
            )
            mensagem.attach_alternative(html, "text/html")
            mensagem.send(fail_silently=False)
    except (smtplib.SMTPException, OSError, ValueError) as erro:
        return _explicar(erro)
    return None


def enviar_rotina(rotina, configuracao=None, disparado_por="", forcar=False, relatorio=None):
    """Monta o relatório da rotina e manda, se houver notícia.

    `forcar` existe para o botão "mandar agora" da tela: quando a pessoa pede, ela quer
    ver o e-mail mesmo que o conteúdo seja "está tudo em dia". A tarefa agendada nunca
    força, senão o relatório diário vira ruído e deixa de ser lido justamente no dia em
    que trouxer uma conta vencida.

    `relatorio` existe para quem vai mandar o mesmo relatório pelo Telegram também não
    montá-lo duas vezes: algumas destas contas passam por onze mil produtos.
    """
    configuracao = configuracao or ConfiguracaoDeEmail.atual()
    relatorio = relatorio or relatorios.montar(rotina)
    if not relatorio.tem_noticia and not forcar:
        registro = EnvioDeRelatorio(
            rotina=rotina,
            canal=Canal.EMAIL,
            resumo=relatorio.resumo[:300],
            sem_noticia=True,
            destinatarios=", ".join(configuracao.lista_de_destinatarios),
            disparado_por=disparado_por[:60],
        )
        registro.save()
        return registro
    return enviar(relatorio, configuracao, disparado_por=disparado_por)


def enviar_teste(configuracao=None, disparado_por=""):
    return enviar(relatorios.de_teste(), configuracao, disparado_por=disparado_por)


def ultimos_envios(quantos=20):
    return list(EnvioDeRelatorio.objects.all()[:quantos])


def ultimo_de_cada_rotina():
    """O último e-mail de cada relatório, para a tela mostrar o estado de cada um."""
    resultado = {}
    for rotina in Rotina.values:
        resultado[rotina] = EnvioDeRelatorio.objects.filter(
            rotina=rotina, canal=Canal.EMAIL).first()
    return resultado
