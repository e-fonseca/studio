"""A tela do backup no GitHub: onde se cola o repositório e o token."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.auditoria.servicos import registrar
from apps.importacao import servicos as importacao_servicos

from . import envio, vigia
from .forms import ConfiguracaoDeBackupForm
from .github import NaoDeuCerto
from .models import ConfiguracaoDeBackup


def _para_a_auditoria(configuracao):
    """O que a auditoria guarda da configuração.

    O token NÃO entra, nem cifrado, nem como "mudou de tal para tal": o que importa para
    quem lê a auditoria é se existe um token guardado. O valor nunca é lido aqui.
    """
    return {"repositorio": configuracao.repositorio, "ramo": configuracao.ramo,
            "ativo": configuracao.ativo, "tem_token": configuracao.tem_token}


def _ligar_de_vez(request, configuracao):
    """Manda a primeira cópia na hora em que o token entra, sem pedir mais um clique.

    Ele pediu em 14/10/2026: *"conectar e ativar automaticamente, tornar um processo
    automático sem ação humana"*. A autorização do GitHub é a única coisa que precisa
    de uma pessoa, e nada tira isso. O que dá para tirar é tudo o que vinha DEPOIS
    dela: marcar o automático (agora já nasce marcado) e clicar em "Enviar agora".
    Gravar o token passou a ser a ação inteira — a partir daí a pessoa vê o resultado,
    e não uma tela dizendo que está tudo preenchido e nada subiu.

    Só na PRIMEIRA vez: trocar o token de um backup que já funciona não precisa
    reenviar o sistema inteiro, e a atualização seguinte manda o que mudar.
    """
    if not (configuracao.ativo and configuracao.configurado):
        return
    if configuracao.ultimo_sucesso_em is not None:
        return
    try:
        resultado = envio.enviar(usuario=request.user, configuracao=configuracao)
    except NaoDeuCerto as erro:
        # A configuração FICA gravada: perdê-la por causa de um token errado obrigaria
        # a digitar tudo de novo. O motivo vai para a tela, que é onde se conserta.
        messages.error(request, f"O token foi guardado, mas a primeira cópia não subiu. {erro}")
        return
    messages.success(request, f"Cópia do programa ligada e primeira cópia no GitHub: {resultado.mensagem}")


@login_required
@permission_required("backup.configurar_backup", raise_exception=True)
def painel(request):
    configuracao = ConfiguracaoDeBackup.atual()
    if request.method == "POST":
        # O "antes" sai daqui, ANTES de o formulário encostar na configuração: o ModelForm
        # grava o que foi digitado na própria instância dentro do is_valid(), e lido depois
        # o antes sairia igual ao depois.
        antes = _para_a_auditoria(configuracao)
        formulario = ConfiguracaoDeBackupForm(request.POST, instance=configuracao)
        if formulario.is_valid():
            salva = formulario.save(usuario=request.user)
            registrar("backup.configurado", usuario=request.user, recurso=salva,
                      recurso_rotulo=salva.repositorio[:200] or "backup no GitHub",
                      antes=antes, depois=_para_a_auditoria(salva))
            messages.success(request, "Configuração gravada.")
            _ligar_de_vez(request, salva)
            return redirect("backup:painel")
    else:
        formulario = ConfiguracaoDeBackupForm(instance=configuracao)
    return render(request, "backup/painel.html", {
        "titulo": "Cópia do programa no GitHub",
        "estado": importacao_servicos.estado_dos_dados(),
        "configuracao": configuracao,
        "estado_do_backup": vigia.situacao(configuracao),
        "formulario": formulario,
        # A contagem, não o conteúdo: a tela não precisa ler 500 arquivos para dizer 500.
        "quantos_arquivos": envio.quantos_arquivos(),
    })


@login_required
@permission_required("backup.configurar_backup", raise_exception=True)
@require_POST
def enviar_agora(request):
    """Manda o código agora, para a pessoa ver o resultado antes de confiar na rotina."""
    try:
        resultado = envio.enviar(usuario=request.user)
    except NaoDeuCerto as erro:
        messages.error(request, str(erro))
        return redirect("backup:painel")
    if resultado.enviou:
        messages.success(request, f"Enviado para o GitHub: {resultado.mensagem}")
    else:
        messages.success(request, resultado.mensagem)
    return redirect("backup:painel")
