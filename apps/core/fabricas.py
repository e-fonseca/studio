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
