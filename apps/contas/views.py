"""Usuários e acessos: quem entra no sistema e o que cada um pode abrir.

Só o perfil de administração abre esta tela. Toda ação aqui vai para a auditoria com
o antes e o depois, menos a senha, que nunca é registrada em lugar nenhum.
"""

import datetime

from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from apps.core import documento

from . import recuperacao, servicos
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
            # Sem e-mail, a pessoa não recupera a senha sozinha (1.43.0): a tela avisa.
            "sem_email": not (usuario.email or "").strip(),
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
@permission_required(PERMISSAO, raise_exception=True)
def email_de_recuperacao(request):
    """A gerência grava o e-mail para onde vai o código de recuperar a senha (1.43.0)."""
    if request.method != "POST":
        return redirect("contas:usuarios")
    escolhido = (request.POST.get("usuario") or "").strip()
    alvo = get_object_or_404(get_user_model(), pk=int(escolhido) if escolhido.isdigit() else 0)
    nome = alvo.get_full_name() or alvo.get_username()
    try:
        mudou = recuperacao.definir_email(alvo, request.POST.get("email"), responsavel=request.user)
    except ValueError as erro:
        messages.error(request, str(erro))
    else:
        if not mudou:
            messages.info(request, f"Nada mudou no e-mail de {nome}.")
        elif alvo.email:
            messages.success(request, f"E-mail de {nome} salvo. Se esquecer a senha, o código "
                                      f"vai para {alvo.email}.")
        else:
            messages.success(request, f"E-mail de {nome} tirado. Sem e-mail, só a gerência "
                                      "define uma senha nova para essa pessoa.")
    return redirect("contas:usuarios")


@login_required
def trocar_senha(request):
    """Cada pessoa troca a própria senha, de qualquer perfil, inclusive o vendedor.

    A tela de usuários dizia "peça para ela trocar na primeira entrada" desde a 1.4.0, e
    não havia onde trocar: a senha que a gerência escolheu continuava valendo para sempre.
    Pede a senha atual (quem achou o computador aberto não troca a senha de ninguém) e
    passa pelas mesmas regras da senha definida pela gerência.
    """
    if request.method == "POST" and request.POST.get("acao") == "email":
        return _meu_email(request)
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


def _meu_email(request):
    """A própria pessoa grava o e-mail de recuperação, confirmando a senha de agora.

    A senha de agora pelo mesmo motivo da troca de senha: quem achar o computador aberto
    não põe o próprio e-mail na conta de outra pessoa para tomar a senha dela depois.
    """
    if not request.user.check_password(request.POST.get("senha_atual") or ""):
        messages.error(request, "A senha de agora não confere. O e-mail não foi mudado.")
        return redirect("contas:trocar_senha")
    try:
        mudou = recuperacao.definir_email(request.user, request.POST.get("email"),
                                          responsavel=request.user)
    except ValueError as erro:
        messages.error(request, str(erro))
    else:
        if not mudou:
            messages.info(request, "O e-mail continua o mesmo.")
        elif request.user.email:
            messages.success(request, f"E-mail salvo. Se esquecer a senha, o código vai para "
                                      f"{request.user.email}.")
        else:
            messages.success(request, "E-mail tirado. Sem e-mail, se esquecer a senha, só a "
                                      "gerência define outra.")
    return redirect("contas:trocar_senha")


# ------------------------------------------------------------ esqueci a minha senha
# Ver apps/contas/recuperacao.py. A pessoa ainda não entrou, então nada aqui pede login;
# quem ela é fica na sessão entre a primeira tela e a segunda, e só lá.
CHAVE_DA_SESSAO = "recuperar_senha"


def _conta_da_sessao(request):
    guardado = request.session.get(CHAVE_DA_SESSAO) or {}
    if not guardado.get("usuario"):
        return None, ""
    conta = get_user_model().objects.filter(pk=guardado["usuario"], is_active=True).first()
    return conta, guardado.get("para", "")


def _recado_do_pedido(request, pedido, *, outro=False):
    """O recado verde só quando diz algo que a tela do código ainda não diz.

    A tela do código já abre dizendo para onde o código foi; repetir isso num quadro
    verde logo abaixo era a mesma frase duas vezes. Fica o recado de quando o código
    é o mesmo de antes (pediu duas vezes seguidas) e de quando saiu outro código.
    """
    if pedido.reaproveitado:
        messages.info(request, f"O código mandado há pouco para {pedido.para} ainda vale. "
                               "Confira a caixa de entrada e também o spam.")
    elif outro:
        messages.success(request, f"Mandamos outro código para {pedido.para}. Use o mais "
                                  "novo: o anterior deixou de valer.")


@never_cache
def esqueci_a_senha(request):
    """Primeira tela: quem é a pessoa. Se der, o código sai para o e-mail cadastrado."""
    digitado, erro = "", ""
    if request.method == "POST":
        digitado = (request.POST.get("identificacao") or "").strip()
        pedido = recuperacao.pedir_codigo(digitado)
        if pedido.deu_certo:
            request.session[CHAVE_DA_SESSAO] = {"usuario": pedido.usuario.pk, "para": pedido.para}
            _recado_do_pedido(request, pedido)
            return redirect("contas:codigo_da_senha")
        erro = pedido.erro
    return render(request, "contas/esqueci_a_senha.html", {
        "titulo": "Esqueci a minha senha",
        "digitado": digitado,
        "erro": erro,
    })


@never_cache
def codigo_da_senha(request):
    """Segunda tela: o código que chegou no e-mail e a senha nova, duas vezes."""
    conta, para = _conta_da_sessao(request)
    if conta is None:
        return redirect("contas:esqueci_a_senha")
    erro_do_codigo = ""
    digitado = ""
    if request.method == "POST" and request.POST.get("acao") == "outro":
        pedido = recuperacao.pedir_codigo(conta.get_username())
        if pedido.deu_certo:
            _recado_do_pedido(request, pedido, outro=True)
        else:
            messages.error(request, pedido.erro)
        return redirect("contas:codigo_da_senha")
    if request.method == "POST":
        formulario = SetPasswordForm(conta, request.POST)
        digitado = (request.POST.get("codigo") or "").strip()[:12]
        with transaction.atomic():
            codigo, erro_do_codigo = recuperacao.conferir_codigo(conta, digitado)
            senha_boa = formulario.is_valid()
            if codigo is not None and senha_boa:
                recuperacao.criar_senha_nova(conta, codigo, formulario.cleaned_data["new_password1"])
        if codigo is not None and senha_boa:
            request.session.pop(CHAVE_DA_SESSAO, None)
            messages.success(request, "Senha nova salva. Entre com ela.")
            return redirect("contas:entrar")
    else:
        formulario = SetPasswordForm(conta)
    return render(request, "contas/codigo_da_senha.html", {
        "titulo": "Código do e-mail",
        "formulario": formulario,
        "para": para,
        "erro_do_codigo": erro_do_codigo,
        "digitado": digitado,
        "aberto": recuperacao.codigo_aberto(conta) is not None,
    })
