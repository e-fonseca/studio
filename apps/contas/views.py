"""Usuários e acessos: quem entra no sistema e o que cada um pode abrir.

Desde a 1.44.0 (prompt de controle de acesso, 02/11/2026) são três telas: a lista de
pessoas, a ficha de cada uma (perfis, senha, situação, o que ela pode de fato, sessões
abertas e histórico) e Perfis e permissões, com a matriz. Para abrir qualquer uma, a
pessoa confirma a própria senha (`confirmacao.py`).

As telas só mostram e mandam; quem decide se pode é `servicos.py`, com as regras de
`autorizacao.py`, conferidas no servidor na hora de gravar. Toda ação vai para a
auditoria com o antes e o depois, menos a senha, que nunca é registrada em lugar nenhum.
"""

import datetime
from functools import wraps

from django.contrib import messages
from django.contrib.auth import get_user_model, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.auditoria.models import EventoAuditoria
from apps.auditoria.servicos import registrar
from apps.core import menu

from . import autorizacao, catalogo, confirmacao, fichas, recuperacao, servicos
from .autorizacao import NaoPode

PERMISSAO = autorizacao.GERENCIAR

FILTROS_DA_LISTA = (
    ("todos", "Todos"),
    ("ativo", "Ativos"),
    ("pendente", "Pendentes"),
    ("bloqueado", "Bloqueados"),
    ("desligado", "Desligados"),
)


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


def _nome(usuario):
    return usuario.get_full_name() or usuario.get_username()


def _administra(usuario):
    return usuario.has_perm(autorizacao.GERENCIAR) or usuario.has_perm(autorizacao.EDITAR_PERFIS)


def _exigir_quem_administra(request):
    if not _administra(request.user):
        raise PermissionDenied


def _so_quem_administra(view):
    """Quem não administra recebe o 403 antes de a tela pedir a senha: pedir a senha a quem
    não vai entrar de todo jeito só faz a pessoa digitar à toa, e conta tentativa errada."""
    @wraps(view)
    def _por_dentro(request, *args, **kwargs):
        _exigir_quem_administra(request)
        return view(request, *args, **kwargs)
    return _por_dentro


# ------------------------------------------------------------------ a senha de novo
@never_cache
@login_required
@_so_quem_administra
def confirmar_senha(request):
    """A senha outra vez antes da área de acessos. Ver `confirmacao.py`."""
    proximo = request.POST.get("proximo") or request.GET.get("proximo") or ""
    if not url_has_allowed_host_and_scheme(proximo, allowed_hosts={request.get_host()},
                                           require_https=request.is_secure()):
        proximo = reverse("contas:usuarios")
    erro = ""
    if request.method == "POST":
        if request.user.check_password(request.POST.get("senha") or ""):
            confirmacao.marcar(request)
            registrar("acesso.senha_confirmada", usuario=request.user,
                      recurso=request.user, recurso_rotulo=request.user.get_username())
            return redirect(proximo)
        erros = confirmacao.contar_erro(request)
        registrar("acesso.confirmacao_falhou", usuario=request.user,
                  recurso=request.user, recurso_rotulo=request.user.get_username(),
                  resultado=EventoAuditoria.Resultado.FALHA, depois={"tentativa": erros})
        if erros >= confirmacao.MAXIMO_DE_ERROS:
            logout(request)
            messages.error(request, "A senha não conferiu cinco vezes seguidas e a sessão foi "
                                    "encerrada por segurança. Entre de novo.")
            return redirect("contas:entrar")
        faltam = confirmacao.MAXIMO_DE_ERROS - erros
        erro = ("A senha não confere. " + ("Mais uma senha errada e a sessão se encerra."
                                            if faltam == 1 else
                                            f"Depois de mais {faltam} senhas erradas a sessão se encerra."))
    return render(request, "contas/confirmar_senha.html", {
        "titulo": "Confirmar a senha",
        "proximo": proximo,
        "erro": erro,
    })


# ------------------------------------------------------------------ a lista
@login_required
@permission_required(PERMISSAO, raise_exception=True)
@confirmacao.exigir
def lista(request):
    situacao = request.GET.get("situacao", "todos")
    if situacao not in fichas.FILTROS:
        situacao = "todos"
    busca = (request.GET.get("q") or "").strip()[:80]
    linhas, contagem = fichas.pessoas(busca=busca, situacao=situacao)
    return render(request, "contas/usuarios.html", {
        "titulo": "Usuários e acessos",
        "pessoas": linhas,
        "filtros": [{"chave": chave, "rotulo": rotulo, "quantos": contagem[chave],
                     "ativo": chave == situacao} for chave, rotulo in FILTROS_DA_LISTA],
        "situacao": situacao,
        "busca": busca,
        "perfis": fichas.perfis_para_dar(request.user),
        "hoje": timezone.localdate(),
        "mais_em_acessos": menu.recursos_de("contas:usuarios", request.user),
    })


@login_required
@permission_required(PERMISSAO, raise_exception=True)
@confirmacao.exigir
@require_POST
def criar(request):
    try:
        usuario = servicos.criar_usuario(
            apelido=request.POST.get("apelido", ""),
            nome=request.POST.get("nome", ""),
            sobrenome=request.POST.get("sobrenome", ""),
            email=request.POST.get("email", ""),
            cpf=request.POST.get("cpf", ""),
            perfis=request.POST.getlist("perfis"),
            acesso_ate=_ultimo_dia(request.POST.get("acesso_ate")),
            responsavel=request.user,
        )
    except (ValueError, NaoPode) as erro:
        messages.error(request, str(erro))
        return redirect(reverse("contas:usuarios") + "#dar-acesso")
    messages.success(
        request,
        f"Usuário {usuario.get_username()} criado. Agora defina a senha dele aqui: "
        "enquanto não tiver senha, ele não consegue entrar.",
    )
    return redirect("contas:ficha", pk=usuario.pk)


# ------------------------------------------------------------------ a ficha
@login_required
@permission_required(PERMISSAO, raise_exception=True)
@confirmacao.exigir
def ficha(request, pk):
    alvo = get_object_or_404(get_user_model().objects.select_related("vinculo"), pk=pk)
    contexto = fichas.ficha(request.user, alvo)
    contexto.update({
        "titulo": _nome(alvo),
        "hoje": timezone.localdate(),
        "sessao_de_agora": request.session.session_key,
    })
    return render(request, "contas/ficha.html", contexto)


def _acao_na_ficha(request, alvo, acao):
    """Faz a ação pedida e devolve o recado de sucesso. Erros sobem como exceção."""
    nome = _nome(alvo)
    if acao == "perfis":
        if not servicos.definir_perfis(alvo, request.POST.getlist("perfis"), responsavel=request.user):
            return "", f"Nada mudou nos perfis de {nome}."
        atuais = servicos.perfis_do_usuario(alvo)
        return (f"Perfis de {nome}: {', '.join(atuais)}. Vale a partir do próximo clique dela."
                if atuais else f"{nome} ficou sem perfil: entra, mas não abre nada."), ""
    if acao == "senha":
        servicos.definir_senha(alvo, request.POST.get("senha", ""), responsavel=request.user)
        return (f"Senha de {nome} definida. Passe a senha para a pessoa e peça para ela trocar "
                "na primeira entrada, clicando no próprio nome, no alto da tela."), ""
    if acao == "email":
        autorizacao.conferir_mexer_em(request.user, alvo)
        if not recuperacao.definir_email(alvo, request.POST.get("email"), responsavel=request.user):
            return "", f"Nada mudou no e-mail de {nome}."
        if alvo.email:
            return f"E-mail de {nome} salvo. Se esquecer a senha, o código vai para {alvo.email}.", ""
        return (f"E-mail de {nome} tirado. Sem e-mail, só a administração define uma senha nova "
                "para essa pessoa."), ""
    if acao == "bloquear":
        sessoes = servicos.bloquear_usuario(alvo, motivo=request.POST.get("motivo", ""),
                                            responsavel=request.user)
        return f"{nome} está bloqueado. {_sessoes_caidas(sessoes)}", ""
    if acao == "desbloquear":
        servicos.desbloquear_usuario(alvo, responsavel=request.user)
        return f"{nome} pode entrar de novo, com os mesmos perfis de antes.", ""
    if acao == "desligar":
        motivo = request.POST.get("motivo", "").strip()
        if not motivo:
            raise ValueError("Diga o motivo do encerramento. Fica na ficha e na auditoria.")
        sessoes = servicos.desligar_usuario(alvo, motivo=motivo, responsavel=request.user)
        return f"Acesso de {nome} encerrado. {_sessoes_caidas(sessoes)}", ""
    if acao == "reativar":
        servicos.reativar_usuario(alvo, responsavel=request.user)
        return f"Acesso de {nome} liberado de novo.", ""
    if acao == "prazo":
        ultimo_dia = _ultimo_dia(request.POST.get("acesso_ate"))
        if not servicos.definir_acesso_ate(alvo, ultimo_dia, responsavel=request.user):
            return "", f"Nada mudou no acesso de {nome}."
        if ultimo_dia is None:
            return f"O acesso de {nome} não tem mais data para acabar.", ""
        return (f"O acesso de {nome} vai até {ultimo_dia:%d/%m/%Y}. No dia seguinte a conta se "
                "desliga sozinha e a sessão aberta cai."), ""
    if acao == "encerrar_sessao":
        chave = request.POST.get("chave", "")
        if chave and chave == request.session.session_key:
            raise ValueError("Esta é a sessão que você está usando agora. Para sair dela, use Sair.")
        if not servicos.encerrar_sessao(alvo, chave, responsavel=request.user):
            return "", "Essa sessão já tinha acabado."
        return "Sessão encerrada. Naquele aparelho, a pessoa precisa entrar de novo.", ""
    if acao == "encerrar_sessoes":
        menos = request.session.session_key if alvo.pk == request.user.pk else None
        sessoes = servicos.encerrar_todas_as_sessoes(alvo, responsavel=request.user, menos=menos)
        if menos:
            return f"Você saiu dos outros aparelhos. {_sessoes_caidas(sessoes)}", ""
        return _sessoes_caidas(sessoes) or "Não havia sessão aberta.", ""
    raise ValueError("A tela mandou uma ação que não existe. Abra a ficha de novo.")


def _sessoes_caidas(quantas):
    if not quantas:
        return ""
    return "1 sessão aberta caiu." if quantas == 1 else f"{quantas} sessões abertas caíram."


@login_required
@permission_required(PERMISSAO, raise_exception=True)
@confirmacao.exigir
@require_POST
def alterar(request, pk):
    """Uma ação por envio, vinda da ficha da pessoa."""
    alvo = get_object_or_404(get_user_model(), pk=pk)
    try:
        sucesso, nada = _acao_na_ficha(request, alvo, request.POST.get("acao", ""))
    except ValidationError as erro:
        messages.error(request, " ".join(erro.messages))
    except (ValueError, NaoPode) as erro:
        messages.error(request, str(erro))
    else:
        if sucesso:
            messages.success(request, sucesso)
        elif nada:
            messages.info(request, nada)
    return redirect("contas:ficha", pk=alvo.pk)


# ------------------------------------------------------------------ perfis e permissões
@login_required
@_so_quem_administra
@confirmacao.exigir
def perfis(request):
    colunas, modulos = fichas.matriz()
    return render(request, "contas/perfis.html", {
        "titulo": "Perfis e permissões",
        "colunas": colunas,
        "modulos": modulos,
        "impacto": fichas.impacto(),
        "pode_editar": request.user.has_perm(autorizacao.EDITAR_PERFIS),
        "retirados": servicos.perfis_retirados(),
    })


def _travadas(ator):
    """As permissões marcadas que este ator não tem: na tela, a caixa delas não se mexe."""
    if ator.is_superuser:
        return set()
    return set(catalogo.MARCADAS) - autorizacao.permissoes_de(ator)


@login_required
@_so_quem_administra
@confirmacao.exigir
def perfil(request, pk):
    grupo = get_object_or_404(Group, pk=pk)
    atuais = autorizacao.permissoes_do_perfil(grupo)
    travadas = _travadas(request.user)
    if request.method == "POST":
        if not request.user.has_perm(autorizacao.EDITAR_PERFIS):
            raise PermissionDenied
        enviados = set(request.POST.getlist("permissoes"))
        # Caixa travada não vem no envio (o navegador não manda campo desligado) e não
        # muda: fica como está no banco, mande a tela o que mandar.
        codigos = (enviados - travadas) | (atuais & travadas & set(catalogo.CODIGOS))
        try:
            mudou = servicos.editar_perfil(grupo, codigos, descricao=request.POST.get("descricao"),
                                           motivo=request.POST.get("motivo", ""),
                                           responsavel=request.user)
        except (ValueError, NaoPode) as erro:
            messages.error(request, str(erro))
        else:
            if mudou:
                messages.success(request, f"Perfil {grupo.name} salvo. Quem está nele já abre "
                                          "o que mudou no próximo clique.")
            else:
                messages.info(request, f"Nada mudou no perfil {grupo.name}.")
        return redirect("contas:perfil", pk=grupo.pk)
    perfil_ = servicos.perfil_de(grupo)
    editavel = autorizacao.pode_editar_perfil(request.user, grupo) and perfil_.retirado_em is None
    if not request.user.has_perm(autorizacao.EDITAR_PERFIS):
        motivo_travado = "Você vê este perfil, mas quem muda o que ele pode é quem edita perfis."
    elif perfil_.retirado_em is not None:
        motivo_travado = "Este perfil foi retirado. Para usá-lo de novo, traga-o de volta."
    elif not editavel:
        motivo_travado = (f"Você está no perfil {grupo.name}: quem muda o que ele pode é outra "
                          "pessoa que edita perfis. Assim ninguém aumenta o próprio acesso.")
    else:
        motivo_travado = ""
    modulos = []
    for modulo, itens in catalogo.por_modulo():
        modulos.append({"modulo": modulo, "linhas": [
            {"permissao": p, "marcada": p.codigo in atuais,
             "travada": (not editavel) or p.codigo in travadas}
            for p in itens]})
    pessoas = grupo.user_set.order_by("-is_active", "first_name", "username")
    return render(request, "contas/perfil.html", {
        "titulo": f"Perfil {grupo.name}",
        "grupo": grupo,
        "perfil": perfil_,
        "editavel": editavel,
        "motivo_travado": motivo_travado,
        "tem_travadas": editavel and any(linha["travada"] for m in modulos for linha in m["linhas"]),
        "modulos": modulos,
        "pessoas": pessoas,
        "fora_do_catalogo": sorted(atuais - set(catalogo.CODIGOS)),
        "pode_editar": request.user.has_perm(autorizacao.EDITAR_PERFIS),
        "outros_perfis": [p.grupo for p in servicos.perfis_ativos() if p.grupo.pk != grupo.pk],
    })


@login_required
@permission_required(autorizacao.EDITAR_PERFIS, raise_exception=True)
@confirmacao.exigir
@require_POST
def criar_perfil(request):
    copiar = (request.POST.get("copiar_de") or "").strip()
    origem = Group.objects.filter(pk=int(copiar)).first() if copiar.isdigit() else None
    try:
        grupo = servicos.criar_perfil(request.POST.get("nome", ""),
                                      descricao=request.POST.get("descricao", ""),
                                      copiar_de=origem, responsavel=request.user)
    except (ValueError, NaoPode) as erro:
        messages.error(request, str(erro))
        return redirect(reverse("contas:perfis") + "#criar-perfil")
    messages.success(request, f"Perfil {grupo.name} criado. Marque o que ele pode e salve.")
    return redirect("contas:perfil", pk=grupo.pk)


@login_required
@permission_required(autorizacao.EDITAR_PERFIS, raise_exception=True)
@confirmacao.exigir
@require_POST
def retirar_perfil(request, pk):
    grupo = get_object_or_404(Group, pk=pk)
    try:
        servicos.retirar_perfil(grupo, responsavel=request.user)
    except (ValueError, NaoPode) as erro:
        messages.error(request, str(erro))
        return redirect("contas:perfil", pk=grupo.pk)
    messages.success(request, f"Perfil {grupo.name} retirado. Ele não aparece mais para dar a "
                              "ninguém; o histórico dele continua na auditoria.")
    return redirect("contas:perfis")


@login_required
@permission_required(autorizacao.EDITAR_PERFIS, raise_exception=True)
@confirmacao.exigir
@require_POST
def devolver_perfil(request, pk):
    grupo = get_object_or_404(Group, pk=pk)
    try:
        servicos.devolver_perfil(grupo, responsavel=request.user)
    except NaoPode as erro:
        messages.error(request, str(erro))
        return redirect("contas:perfis")
    messages.success(request, f"Perfil {grupo.name} de volta, sem permissão nenhuma. Marque o "
                              "que ele pode e salve.")
    return redirect("contas:perfil", pk=grupo.pk)


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
