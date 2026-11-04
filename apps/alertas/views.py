"""Tela de alertas: configurar o e-mail, mandar um teste e ver o que já saiu."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.alertas import agenda, envio, metas, relatorios, telegram
from apps.alertas.forms import ConfiguracaoForm, MetasNoTelegramForm, TelegramForm
from apps.alertas.models import Canal, ConfiguracaoDeEmail, ConfiguracaoDeTelegram, EnvioDeRelatorio, Rotina
from apps.auditoria.servicos import registrar
from apps.caixa.models import RegraDeDesconto
from apps.financeiro import servicos as financeiro
from apps.importacao import servicos as importacao_servicos

configurar = permission_required("alertas.configurar_email", raise_exception=True)


def _linhas_das_rotinas(importacao):
    """Uma linha por relatório, com o que ele leva e quando saiu pela última vez.

    Montado aqui, e não no template, porque a frase de cada relatório depende de número
    do banco (quantas contas estão em aberto) e porque `{% if %}` encadeado num template
    para escolher texto é onde erro de conteúdo se esconde.
    """
    em_aberto = relatorios.contas_em_aberto(importacao)
    descricoes = {
        Rotina.CONTAS: (
            "O que já venceu, o que vence hoje e o que vence em até "
            f"{financeiro.DIAS_PRESTES_A_VENCER} dias."
            + (f" Hoje há {em_aberto} conta(s) em aberto." if importacao else "")
        ),
        Rotina.VENDAS: "Tudo o que saiu no dia, com o custo do dia, o lucro em reais e a margem.",
        Rotina.ESTOQUE: "Quanto está na prateleira, o que não gira e o que precisa sair pela venda.",
        Rotina.COMPRA: "O que comprar antes de faltar, por fornecedor, dentro do teto do mês.",
    }
    # O rótulo da rotina carrega a frequência entre parênteses ("Contas a pagar (todo
    # dia)"), que serve no registro de envios mas fica repetitivo como título de cartão.
    nomes = {Rotina.CONTAS: ("Contas a pagar", "Todo dia"),
             Rotina.VENDAS: ("Vendas do dia", "Todo dia"),
             Rotina.ESTOQUE: ("Estoque da loja", "Toda semana"),
             Rotina.COMPRA: ("Sugestão de compra", "Toda semana")}
    ultimos = envio.ultimo_de_cada_rotina()
    no_telegram = telegram.ultimo_de_cada_rotina()
    return [
        {"chave": rotina.value, "nome": nomes[rotina][0], "cadencia": nomes[rotina][1],
         "rotulo": rotina.label, "descricao": descricoes[rotina],
         "ultimo": ultimos.get(rotina.value), "ultimo_telegram": no_telegram.get(rotina.value)}
        for rotina in (Rotina.CONTAS, Rotina.VENDAS, Rotina.ESTOQUE, Rotina.COMPRA)
    ]


def _contexto(configuracao, form=None, form_telegram=None, chats=None, form_metas=None):
    importacao = importacao_servicos.ultima_concluida()
    no_telegram = ConfiguracaoDeTelegram.atual()
    return {
        "titulo": "Alertas e notificações",
        "configuracao": configuracao,
        "form": form or ConfiguracaoForm(instance=configuracao),
        "faltas": configuracao.o_que_falta,
        "telegram": no_telegram,
        "form_telegram": form_telegram or TelegramForm(instance=no_telegram),
        "faltas_telegram": no_telegram.o_que_falta,
        # Preenchido só depois do botão "descobrir a conversa": é a resposta do Telegram,
        # e ela não sobrevive ao redirect, então a tela a mostra na mesma resposta.
        "chats": chats or [],
        # O grupo das metas (1.47.0): o mesmo robô, outro destino.
        "form_metas": form_metas or MetasNoTelegramForm(instance=no_telegram),
        "faltas_metas": no_telegram.metas_o_que_falta,
        "regra_das_metas": RegraDeDesconto.atual(),
        "ultimos_avisos_de_meta": list(EnvioDeRelatorio.objects.filter(
            rotina=Rotina.METAS, canal=Canal.TELEGRAM)[:3]),
        "proximo": agenda.proximo_envio(configuracao),
        "ultimos": envio.ultimos_envios(),
        "rotinas": _linhas_das_rotinas(importacao),
        "tem_importacao": importacao is not None,
    }


@login_required
@configurar
def painel(request):
    """O estado do envio: o que falta, quando sai o próximo e o que já saiu."""
    configuracao = ConfiguracaoDeEmail.atual()
    if request.method != "POST":
        return render(request, "alertas/painel.html", _contexto(configuracao))

    form = ConfiguracaoForm(request.POST, instance=configuracao)
    if not form.is_valid():
        return render(request, "alertas/painel.html", _contexto(configuracao, form))

    antes = {"ativo": configuracao.ativo, "usuario": configuracao.usuario,
             "destinatarios": configuracao.destinatarios}
    salva = form.save()
    registrar(
        "alertas.configurado", usuario=request.user, recurso=salva,
        recurso_rotulo="configuração de e-mail",
        antes=antes,
        # A senha nunca entra na auditoria; o que importa é se existe uma.
        depois={"ativo": salva.ativo, "usuario": salva.usuario,
                "destinatarios": salva.destinatarios, "tem_senha": salva.tem_senha},
    )
    messages.success(request, "Configuração gravada.")
    return redirect("alertas:painel")


@login_required
@configurar
@require_POST
def testar(request):
    """Manda um e-mail de teste agora, para provar o caminho antes de confiar nele."""
    configuracao = ConfiguracaoDeEmail.atual()
    registro = envio.enviar_teste(configuracao, disparado_por=request.user.get_username())
    registrar("alertas.teste", usuario=request.user, recurso=registro,
              recurso_rotulo="teste de envio",
              resultado="sucesso" if registro.deu_certo else "falha",
              depois={"erro": registro.erro[:200]} if registro.erro else None)
    if registro.deu_certo:
        messages.success(
            request,
            "E-mail de teste enviado para " + registro.destinatarios +
            ". Confira a caixa de entrada e também o spam, que é onde a primeira mensagem costuma cair.")
    else:
        messages.error(request, registro.erro)
    return redirect("alertas:painel")


@login_required
@configurar
@require_POST
def mandar_agora(request, rotina):
    """Manda um relatório na hora, mesmo sem notícia: quem pediu quer ver o e-mail."""
    if rotina not in relatorios.MONTADORES:
        messages.error(request, "Relatório desconhecido.")
        return redirect("alertas:painel")
    configuracao = ConfiguracaoDeEmail.atual()
    no_telegram = ConfiguracaoDeTelegram.atual()
    # Montado uma vez e mandado pelos dois: "mandar agora" é um pedido só, e algumas
    # destas contas passam por onze mil produtos.
    relatorio = relatorios.montar(rotina)
    registro = envio.enviar_rotina(
        rotina, configuracao, disparado_por=request.user.get_username(), forcar=True,
        relatorio=relatorio,
    )
    registrar("alertas.enviado", usuario=request.user, recurso=registro,
              recurso_rotulo=Rotina(rotina).label,
              resultado="sucesso" if registro.deu_certo else "falha",
              depois={"resumo": registro.resumo[:200]})
    if registro.deu_certo:
        messages.success(request, f"{Rotina(rotina).label} enviado para {registro.destinatarios}.")
    else:
        messages.error(request, registro.erro)

    # O Telegram só entra quando está ligado na tela: apertar "mandar agora" não é pedido
    # para ligar um canal que a pessoa deixou desligado.
    if no_telegram.ativo:
        aviso = telegram.enviar_rotina(
            rotina, no_telegram, disparado_por=request.user.get_username(), forcar=True,
            relatorio=relatorio,
        )
        registrar("alertas.telegram_enviado", usuario=request.user, recurso=aviso,
                  recurso_rotulo=Rotina(rotina).label,
                  resultado="sucesso" if aviso.deu_certo else "falha",
                  depois={"resumo": aviso.resumo[:200]})
        if aviso.deu_certo:
            messages.success(request, f"{Rotina(rotina).label} também avisado no Telegram.")
        else:
            messages.error(request, "No Telegram: " + aviso.erro)
    return redirect("alertas:painel")


@login_required
@configurar
def previa(request, rotina):
    """Como o e-mail vai chegar, sem mandar nada.

    Serve para conferir o conteúdo antes de ligar o envio, e para a gente conseguir
    olhar o relatório numa tela em vez de numa caixa de entrada.
    """
    if rotina not in relatorios.MONTADORES:
        messages.error(request, "Relatório desconhecido.")
        return redirect("alertas:painel")
    relatorio = relatorios.montar(rotina)
    return render(request, "alertas/email/relatorio.html", {
        "r": relatorio,
        "configuracao": ConfiguracaoDeEmail.atual(),
        "quando": timezone.localtime(),
    })


@login_required
@configurar
@require_POST
def configurar_telegram(request):
    """Grava o token e a conversa do Telegram."""
    configuracao = ConfiguracaoDeTelegram.atual()
    form = TelegramForm(request.POST, instance=configuracao)
    if not form.is_valid():
        return render(request, "alertas/painel.html",
                      _contexto(ConfiguracaoDeEmail.atual(), form_telegram=form))

    antes = {"ativo": configuracao.ativo, "chat_id": configuracao.chat_id}
    salva = form.save()
    registrar(
        "alertas.telegram_configurado", usuario=request.user, recurso=salva,
        recurso_rotulo="configuração do Telegram",
        antes=antes,
        # O token nunca entra na auditoria; o que importa é se existe um.
        depois={"ativo": salva.ativo, "chat_id": salva.chat_id, "tem_token": salva.tem_token},
    )
    messages.success(request, "Configuração do Telegram gravada.")
    return redirect("alertas:painel")


@login_required
@configurar
@require_POST
def testar_telegram(request):
    """Manda um aviso de teste no Telegram, para provar o caminho antes de confiar."""
    configuracao = ConfiguracaoDeTelegram.atual()
    registro = telegram.enviar_teste(configuracao, disparado_por=request.user.get_username())
    registrar("alertas.telegram_teste", usuario=request.user, recurso=registro,
              recurso_rotulo="teste de Telegram",
              resultado="sucesso" if registro.deu_certo else "falha",
              depois={"erro": registro.erro[:200]} if registro.erro else None)
    if registro.deu_certo:
        messages.success(
            request,
            "Aviso de teste enviado no Telegram para " + (registro.destinatarios or "a conversa") +
            ". Confira o celular.")
    else:
        messages.error(request, registro.erro)
    return redirect("alertas:painel")


@login_required
@configurar
@require_POST
def descobrir_chat(request):
    """Pergunta ao Telegram quais conversas já falaram com o robô.

    Não redireciona: a lista é a resposta da pergunta e precisa aparecer junto do campo,
    com o botão que preenche o número. Mandar para outra página perderia a lista.
    """
    configuracao = ConfiguracaoDeTelegram.atual()
    achados, erro = telegram.descobrir_chats(configuracao)
    if erro:
        messages.error(request, erro)
    elif not achados:
        messages.error(request, "Nenhuma conversa encontrada.")
    contexto = _contexto(ConfiguracaoDeEmail.atual(), chats=achados)
    # Do botão do grupo das metas, a lista aparece lá, com o botão de usar para as metas.
    contexto["chats_para"] = "metas" if request.POST.get("para") == "metas" else ""
    return render(request, "alertas/painel.html", contexto)


@login_required
@configurar
@require_POST
def usar_chat(request):
    """Grava a conversa escolhida na lista que o Telegram devolveu.

    Um botão por conversa, e não um campo para digitar o número: o número tem onze
    dígitos e um sinal de menos quando é grupo, e errar um dígito dá "chat not found"
    só na madrugada seguinte.
    """
    configuracao = ConfiguracaoDeTelegram.atual()
    identificador = (request.POST.get("chat_id") or "").strip()
    if not identificador.lstrip("-").isdigit():
        messages.error(request, "Conversa inválida.")
        return redirect("alertas:painel")
    nome = (request.POST.get("chat_nome") or "")[:120]
    if request.POST.get("para") == "metas":
        # O mesmo botão, para o grupo das metas (1.47.0).
        configuracao.metas_chat_id, configuracao.metas_chat_nome = identificador, nome
        configuracao.save(update_fields=["metas_chat_id", "metas_chat_nome", "atualizado_em"])
        registrar("alertas.telegram_configurado", usuario=request.user, recurso=configuracao,
                  recurso_rotulo="grupo das metas do Telegram",
                  depois={"metas_chat_id": identificador, "metas_chat_nome": nome})
        messages.success(
            request,
            f"Grupo das metas gravado: {configuracao.metas_para_quem}. Agora use o botão de "
            "teste do grupo das metas para ver se o aviso chega lá.")
        return redirect(f"{reverse('alertas:painel')}#grupo-das-metas")
    configuracao.chat_id = identificador
    configuracao.chat_nome = nome
    configuracao.save(update_fields=["chat_id", "chat_nome", "atualizado_em"])
    registrar("alertas.telegram_configurado", usuario=request.user, recurso=configuracao,
              recurso_rotulo="conversa do Telegram",
              depois={"chat_id": configuracao.chat_id, "chat_nome": configuracao.chat_nome})
    messages.success(
        request,
        f"Conversa gravada: {configuracao.para_quem}. Agora use o botão de teste para ver "
        "se o aviso chega no celular.")
    return redirect("alertas:painel")


@login_required
@configurar
@require_POST
def configurar_metas(request):
    """Liga ou desliga o aviso de meta batida, e grava o número do grupo."""
    configuracao = ConfiguracaoDeTelegram.atual()
    form = MetasNoTelegramForm(request.POST, instance=configuracao)
    if not form.is_valid():
        return render(request, "alertas/painel.html",
                      _contexto(ConfiguracaoDeEmail.atual(), form_metas=form))
    antes = {"metas_ativo": configuracao.metas_ativo, "metas_chat_id": configuracao.metas_chat_id}
    salva = form.save()
    registrar("alertas.telegram_configurado", usuario=request.user, recurso=salva,
              recurso_rotulo="grupo das metas do Telegram", antes=antes,
              depois={"metas_ativo": salva.metas_ativo, "metas_chat_id": salva.metas_chat_id})
    if salva.metas_ativo:
        messages.success(request, "Aviso das metas ligado. Ele sai na primeira volta da tarefa "
                                  "depois da importação que trouxer um dia que bateu a meta.")
    else:
        messages.success(request, "Aviso das metas gravado, desligado.")
    return redirect(f"{reverse('alertas:painel')}#grupo-das-metas")


@login_required
@configurar
@require_POST
def testar_metas(request):
    """Manda o teste no grupo das metas, com as metas e o prêmio de hoje."""
    registro = metas.enviar_teste(disparado_por=request.user.get_username())
    registrar("alertas.telegram_teste", usuario=request.user, recurso=registro,
              recurso_rotulo="teste do grupo das metas",
              resultado="sucesso" if registro.deu_certo else "falha",
              depois={"erro": registro.erro[:200]} if registro.erro else None)
    if registro.deu_certo:
        messages.success(request, "Teste enviado no grupo das metas (" + registro.destinatarios +
                                  "). Confira no Telegram.")
    else:
        messages.error(request, registro.erro)
    return redirect(f"{reverse('alertas:painel')}#grupo-das-metas")
