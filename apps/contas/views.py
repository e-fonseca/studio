"""Usuários e acessos: quem entra no sistema e o que cada um pode abrir.

Só o perfil de administração abre esta tela. Toda ação aqui vai para a auditoria com
o antes e o depois, menos a senha, que nunca é registrada em lugar nenhum.
"""

import datetime

from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.core import documento

from . import servicos
from .perfis import DESCRICOES, PERFIS

PERMISSAO = "contas.gerenciar_usuarios"


def _lista_de_usuarios():
    Usuario = get_user_model()
    pessoas = []
    consulta = Usuario.objects.order_by("-is_active", "username").prefetch_related("groups")
    for usuario in consulta.select_related("vinculo"):
        perfis = servicos.perfis_do_usuario(usuario)
        vinculo = getattr(usuario, "vinculo", None)
        pessoas.append({
            "usuario": usuario,
            "perfil": perfis[0] if perfis else "",
            "sem_senha": not usuario.has_usable_password(),
            "cpf": documento.formatar(vinculo.cpf) if vinculo and vinculo.cpf else "",
            "acesso_ate": vinculo.acesso_ate if vinculo else None,
        })
    return pessoas


def _contexto(request):
    return {
        "titulo": "Usuários e acessos",
        "pessoas": _lista_de_usuarios(),
        "perfis": [{"nome": nome, "descricao": DESCRICOES.get(nome, "")} for nome in PERFIS],
        "hoje": timezone.localdate(),
    }


def _ultimo_dia(texto):
    """A data do campo "acesso até", que o navegador manda como AAAA-MM-DD.

    Em branco é "sem data". Data que não se lê vira erro com frase, nunca "sem data":
    quem digitou uma data queria uma data.
    """
    texto = (texto or "").strip()
    if not texto:
        return None
    try:
        return datetime.date.fromisoformat(texto)
    except ValueError:
        raise ValueError("Não deu para ler a data do último dia de acesso. Escolha no calendário.") from None


@login_required
@permission_required(PERMISSAO, raise_exception=True)
def lista(request):
    return render(request, "contas/usuarios.html", _contexto(request))


@login_required
@permission_required(PERMISSAO, raise_exception=True)
def criar(request):
    if request.method != "POST":
        return redirect("contas:usuarios")
    try:
        usuario = servicos.criar_usuario(
            apelido=request.POST.get("apelido", ""),
            nome=request.POST.get("nome", ""),
            sobrenome=request.POST.get("sobrenome", ""),
            email=request.POST.get("email", ""),
            cpf=request.POST.get("cpf", ""),
            perfil=request.POST.get("perfil", ""),
            acesso_ate=_ultimo_dia(request.POST.get("acesso_ate")),
            responsavel=request.user,
        )
    except ValueError as erro:
        messages.error(request, str(erro))
    else:
        messages.success(
            request,
            f"Usuário {usuario.get_username()} criado. Agora defina a senha dele: "
            "enquanto não tiver senha, ele não consegue entrar.",
        )
    return redirect("contas:usuarios")


@login_required
@permission_required(PERMISSAO, raise_exception=True)
def alterar(request, pk):
    """Muda o perfil, liga ou desliga o acesso e define a senha. Uma ação por envio."""
    if request.method != "POST":
        return redirect("contas:usuarios")
    alvo = get_object_or_404(get_user_model(), pk=pk)
    acao = request.POST.get("acao", "")

    if acao == "perfil":
        try:
            servicos.definir_perfil(alvo, request.POST.get("perfil", ""), responsavel=request.user)
        except ValueError as erro:
            messages.error(request, str(erro))
        else:
            messages.success(request, f"Perfil de {alvo.get_username()} atualizado.")

    elif acao == "senha":
        try:
            servicos.definir_senha(alvo, request.POST.get("senha", ""), responsavel=request.user)
        except ValidationError as erro:
            messages.error(request, " ".join(erro.messages))
        else:
            messages.success(
                request,
                f"Senha de {alvo.get_username()} definida. Passe a senha para a pessoa e "
                "peça para ela trocar na primeira entrada, clicando no próprio nome, no "
                "alto da tela.",
            )

    elif acao == "desligar":
        if alvo == request.user:
            messages.error(request, "Você não pode desligar o seu próprio acesso.")
        else:
            motivo = request.POST.get("motivo", "").strip() or "Desligado pela tela de usuários"
            servicos.desligar_usuario(alvo, motivo=motivo, responsavel=request.user)
            messages.success(request, f"Acesso de {alvo.get_username()} encerrado.")

    elif acao == "reativar":
        servicos.reativar_usuario(alvo, responsavel=request.user)
        messages.success(request, f"Acesso de {alvo.get_username()} liberado de novo.")

    return redirect("contas:usuarios")


@login_required
@permission_required(PERMISSAO, raise_exception=True)
def prazo_de_acesso(request):
    """Marca (ou tira) o último dia de acesso de uma pessoa. Um formulário só na tela."""
    if request.method != "POST":
        return redirect("contas:usuarios")
    escolhido = (request.POST.get("usuario") or "").strip()
    alvo = get_object_or_404(get_user_model(), pk=int(escolhido) if escolhido.isdigit() else 0)
    nome = alvo.get_full_name() or alvo.get_username()
    if alvo == request.user:
        messages.error(request, "Você não pode pôr data para acabar o seu próprio acesso.")
        return redirect("contas:usuarios")
    try:
        ultimo_dia = _ultimo_dia(request.POST.get("acesso_ate"))
        mudou = servicos.definir_acesso_ate(alvo, ultimo_dia, responsavel=request.user)
    except ValueError as erro:
        messages.error(request, str(erro))
    else:
        if not mudou:
            messages.info(request, f"Nada mudou no acesso de {nome}.")
        elif ultimo_dia is None:
            messages.success(request, f"O acesso de {nome} não tem mais data para acabar.")
        else:
            messages.success(request, f"O acesso de {nome} vai até {ultimo_dia:%d/%m/%Y}. No dia "
                                      "seguinte a conta se desliga sozinha e a sessão aberta cai.")
    return redirect("contas:usuarios")


@login_required
def trocar_senha(request):
    """Cada pessoa troca a própria senha, de qualquer perfil, inclusive o vendedor.

    A tela de usuários dizia "peça para ela trocar na primeira entrada" desde a 1.4.0, e
    não havia onde trocar: a senha que a gerência escolheu continuava valendo para sempre.
    Pede a senha atual (quem achou o computador aberto não troca a senha de ninguém) e
    passa pelas mesmas regras da senha definida pela gerência.
    """
    if request.method == "POST":
        formulario = PasswordChangeForm(request.user, request.POST)
        if formulario.is_valid():
            servicos.trocar_a_propria_senha(request.user, formulario.cleaned_data["new_password1"])
            # A sessão de agora continua; as outras (outro computador, o celular) caíram.
            update_session_auth_hash(request, request.user)
            messages.success(request, "Senha trocada. Nos outros aparelhos, entre de novo com "
                                      "a senha nova.")
            return redirect("core:inicio")
    else:
        formulario = PasswordChangeForm(request.user)
    return render(request, "contas/trocar_senha.html", {
        "titulo": "Trocar a minha senha",
        "formulario": formulario,
    })
