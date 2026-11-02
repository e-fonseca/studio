"""Ajuda para testes: cria usuários com perfis. Só para testes e demonstração."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from apps.contas.perfis import PERFIS
from apps.contas.servicos import configurar_perfis

SENHA_TESTE = "senha-de-teste-123"


def usuario(nome, *perfis, **extra):
    # A migração que cria os acessos da gerência já deixa um grupo criado, mas sem
    # permissão nenhuma: conferir só se existe grupo daria um usuário sem poder abrir nada.
    if Group.objects.filter(name__in=PERFIS, permissions__isnull=False).distinct().count() < len(PERFIS):
        configurar_perfis()
    # A migração dos acessos da gerência já cria edson, henriett e moizes. Reaproveita a
    # conta em vez de estourar: o que o teste quer é uma pessoa com aquele nome e perfil.
    Usuario = get_user_model()
    u = Usuario.objects.filter(username=nome).first()
    if u is None:
        u = Usuario.objects.create_user(username=nome, password=SENHA_TESTE,
                                        first_name=nome.title(), **extra)
    else:
        for campo, valor in extra.items():
            setattr(u, campo, valor)
        u.set_password(SENHA_TESTE)
        u.is_active = True
        u.save()
        # A conta vinda da migração já tem perfil; o teste pede uma pessoa com os perfis
        # que ele listou, e só esses.
        u.groups.clear()
    for perfil in perfis:
        u.groups.add(Group.objects.get(name=perfil))
    return get_user_model().objects.get(pk=u.pk)  # recarrega para limpar cache de permissões


def confirmar_senha(client):
    """Marca na sessão do cliente de teste que a senha foi confirmada há pouco.

    A área de acessos (Usuários, ficha, Perfis e permissões) pede a senha de novo antes de
    abrir (apps/contas/confirmacao.py). O teste que quer a tela em si, e não a confirmação,
    entra e chama isto; o teste da confirmação passa pela tela da senha de verdade.
    """
    from django.utils import timezone  # noqa: PLC0415

    from apps.contas import confirmacao  # noqa: PLC0415

    sessao = client.session
    sessao[confirmacao.CHAVE] = timezone.now().isoformat()
    sessao.save()


def entrar_na_area_de_acessos(client, nome):
    """Entra como `nome` e já com a senha confirmada para a área de acessos."""
    client.login(username=nome, password=SENHA_TESTE)
    confirmar_senha(client)
