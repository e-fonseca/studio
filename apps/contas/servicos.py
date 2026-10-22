from django.contrib.auth.models import Group, Permission
from django.contrib.sessions.models import Session
from django.db import transaction
from django.utils import timezone

from apps.auditoria.servicos import registrar

from .models import VinculoIdentidade
from .perfis import PERFIS


def configurar_perfis():
    """Cria ou atualiza os perfis com as permissões definidas em perfis.py."""
    resultado = {}
    for nome, codigos in PERFIS.items():
        grupo, _ = Group.objects.get_or_create(name=nome)
        permissoes = []
        for codigo in codigos:
            app_label, codename = codigo.split(".")
            permissoes.append(Permission.objects.get(content_type__app_label=app_label, codename=codename))
        grupo.permissions.set(permissoes)
        resultado[nome] = len(permissoes)
    registrar("permissao.perfis_configurados", servico="sistema", depois=resultado)
    return resultado


def encerrar_sessoes(usuario):
    """Remove as sessões abertas do usuário (banco de sessões do Django)."""
    removidas = 0
    for sessao in Session.objects.filter(expire_date__gte=timezone.now()).iterator():
        if str(sessao.get_decoded().get("_auth_user_id")) == str(usuario.pk):
            sessao.delete()
            removidas += 1
    return removidas


@transaction.atomic
def desligar_usuario(usuario, *, motivo, responsavel=None):
    """Bloqueia o acesso de quem saiu da empresa e encerra as sessões abertas."""
    if not motivo.strip():
        raise ValueError("Informe o motivo do desligamento.")
    usuario.is_active = False
    usuario.save(update_fields=["is_active"])
    vinculo, _ = VinculoIdentidade.objects.get_or_create(usuario=usuario)
    vinculo.desligado_em = timezone.now()
    vinculo.save(update_fields=["desligado_em"])
    sessoes = encerrar_sessoes(usuario)
    registrar(
        "acesso.usuario_desligado",
        usuario=responsavel,
        servico=None if responsavel else "linha de comando",
        recurso=usuario,
        recurso_rotulo=usuario.get_username(),
        depois={"ativo": False, "sessoes_encerradas": sessoes},
        motivo=motivo,
    )
    return sessoes


def perfis_do_usuario(usuario):
    """Os perfis desta pessoa, na ordem em que aparecem em perfis.py."""
    tem = set(usuario.groups.values_list("name", flat=True))
    return [nome for nome in PERFIS if nome in tem]


def definir_perfil(usuario, perfil, *, responsavel=None):
    """Deixa a pessoa com um perfil só. Perfil em branco tira todo o acesso."""
    from django.contrib.auth.models import Group  # noqa: PLC0415 - evita import circular no topo

    if perfil and perfil not in PERFIS:
        raise ValueError("Perfil desconhecido.")
    antes = perfis_do_usuario(usuario)
    # get_or_create e não get: o nome já foi conferido contra PERFIS, e o grupo pode ainda
    # não existir num banco recém-criado, antes do configurar_perfis do instalador.
    usuario.groups.set([Group.objects.get_or_create(name=perfil)[0]] if perfil else [])
    registrar(
        "acesso.perfil_definido",
        usuario=responsavel,
        servico=None if responsavel else "linha de comando",
        recurso=usuario,
        recurso_rotulo=usuario.get_username(),
        antes={"perfis": antes},
        depois={"perfis": perfis_do_usuario(usuario)},
    )


@transaction.atomic
def criar_usuario(*, apelido, nome, sobrenome="", email="", cpf="", perfil="", responsavel=None):
    """Cria a conta sem senha: quem administra define a senha logo em seguida.

    Conta sem senha utilizável não entra no sistema, então não há janela em que alguém
    acessa com uma senha provisória que ficou escrita em algum lugar.
    """
    from django.contrib.auth import get_user_model  # noqa: PLC0415 - idem

    from apps.core import documento  # noqa: PLC0415 - idem

    apelido = (apelido or "").strip().lower()
    if not apelido:
        raise ValueError("Informe o usuário de acesso.")
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("Informe o nome da pessoa.")
    Usuario = get_user_model()
    if Usuario.objects.filter(username__iexact=apelido).exists():
        raise ValueError(f"Já existe um usuário chamado {apelido}.")

    numeros = documento.limpar(cpf)
    if numeros:
        if not documento.valido(numeros):
            raise ValueError("Esse CPF não confere. Confira os números digitados.")
        if VinculoIdentidade.objects.filter(cpf=numeros).exists():
            raise ValueError("Já existe um usuário com esse CPF.")

    usuario = Usuario(username=apelido, email=(email or "").strip(), is_active=True)
    usuario.first_name = nome[:150]
    usuario.last_name = (sobrenome or "").strip()[:150]
    usuario.set_unusable_password()
    usuario.save()
    VinculoIdentidade.objects.get_or_create(usuario=usuario, defaults={"cpf": numeros})
    if perfil:
        definir_perfil(usuario, perfil, responsavel=responsavel)
    registrar(
        "acesso.usuario_criado",
        usuario=responsavel,
        servico=None if responsavel else "linha de comando",
        recurso=usuario,
        recurso_rotulo=apelido,
        # O CPF não entra aqui de propósito: a trilha de auditoria não guarda documento.
        depois={"nome": usuario.get_full_name(), "perfil": perfil, "ativo": True},
    )
    return usuario


def definir_senha(usuario, senha, *, responsavel=None):
    """Troca a senha e derruba as sessões abertas, para a senha antiga não continuar valendo."""
    from django.contrib.auth.password_validation import validate_password  # noqa: PLC0415

    validate_password(senha, usuario)
    usuario.set_password(senha)
    usuario.save(update_fields=["password"])
    sessoes = encerrar_sessoes(usuario)
    registrar(
        "acesso.senha_definida",
        usuario=responsavel,
        servico=None if responsavel else "linha de comando",
        recurso=usuario,
        recurso_rotulo=usuario.get_username(),
        # A senha em si nunca entra na auditoria.
        depois={"sessoes_encerradas": sessoes},
    )


def reativar_usuario(usuario, *, responsavel=None):
    usuario.is_active = True
    usuario.save(update_fields=["is_active"])
    vinculo, _ = VinculoIdentidade.objects.get_or_create(usuario=usuario)
    vinculo.desligado_em = None
    vinculo.save(update_fields=["desligado_em"])
    registrar(
        "acesso.usuario_reativado",
        usuario=responsavel,
        servico=None if responsavel else "linha de comando",
        recurso=usuario,
        recurso_rotulo=usuario.get_username(),
        depois={"ativo": True},
    )
