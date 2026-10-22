"""Usuários e acessos: quem entra no sistema e o que cada um pode abrir.

Só o perfil de administração abre esta tela. Toda ação aqui vai para a auditoria com
o antes e o depois, menos a senha, que nunca é registrada em lugar nenhum.
"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

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
        })
    return pessoas


def _contexto(request):
    return {
        "titulo": "Usuários e acessos",
        "pessoas": _lista_de_usuarios(),
        "perfis": [{"nome": nome, "descricao": DESCRICOES.get(nome, "")} for nome in PERFIS],
    }


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
                "peça para ela trocar na primeira entrada.",
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
