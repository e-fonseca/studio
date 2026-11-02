"""Quem pode mexer no acesso de quem: as regras num lugar só (1.44.0).

O que cada TELA exige continua no `permission_required` de cada view, conferido pelo
Django a cada requisição. Aqui ficam as regras de CONCESSÃO, que o prompt de controle de
acesso pediu (02/11/2026) e que até a 1.43.0 não existiam porque só a gerência, que tem
tudo, mexia em acesso:

1. **Ninguém mexe no próprio acesso** (perfil, bloqueio, desligamento, data para acabar).
   Senha e e-mail próprios se trocam em "Trocar a minha senha", que pede a senha atual.
2. **Ninguém dá o que não tem.** Permissão com marca de dinheiro ou de administração
   (`catalogo.MARCADAS`) só é dada, tirada ou mexida por quem também a tem. Vale para dar
   perfil, para editar perfil e para mexer na conta de alguém (senha, e-mail, bloqueio):
   quem define a senha de uma conta passa a poder entrar nela, então mexer na conta de
   quem tem mais acesso seria tomar esse acesso para si.
3. **Superusuário** (a conta técnica criada no servidor na primeira instalação) só é
   mexido por outro superusuário.
4. **Sempre fica alguém administrando.** Toda mudança roda dentro de uma transação, e no
   fim se confere que sobrou pelo menos uma conta ativa, com
   senha, que administra pessoas E perfis (`mantendo_um_administrador`). Se não sobrou,
   a mudança inteira volta atrás.

Requisição montada à mão não escapa de nada disso: as regras rodam no servidor, na hora
de gravar, com o que está no banco, e não com o que a tela mostrou.
"""

from contextlib import contextmanager

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db.models import Q

from .catalogo import CODIGOS, MARCADAS, de

GERENCIAR = "contas.gerenciar_usuarios"
EDITAR_PERFIS = "contas.editar_perfis"

NEGADO = "Seu usuário não tem permissão para esta ação. Procure a gerência."


class NaoPode(Exception):
    """A regra que impediu a mudança, numa frase que serve de recado na tela."""


def _codigos(consulta):
    return {f"{p.content_type.app_label}.{p.codename}" for p in consulta.select_related("content_type")}


def permissoes_do_perfil(grupo):
    return _codigos(grupo.permissions.all())


def permissoes_de(usuario):
    """O que a pessoa pode, somando perfis e permissões individuais.

    Diferente do `get_all_permissions` do Django, conta mesmo com a conta desligada ou
    bloqueada: para desbloquear alguém, o que importa é o acesso que ela VAI ter.
    """
    if usuario.is_superuser:
        return set(_codigos(Permission.objects.all())) | set(CODIGOS)
    return _codigos(Permission.objects.filter(Q(group__user=usuario) | Q(user=usuario)).distinct())


def nomes(codigos):
    """Os nomes em português, para a frase da tela."""
    itens = sorted((de(codigo).nome if de(codigo) else codigo) for codigo in codigos)
    if len(itens) > 3:
        return ", ".join(itens[:3]) + f" e mais {len(itens) - 3}"
    return ", ".join(itens)


def faltam_para(ator, codigos):
    """As permissões marcadas destas que o ator não tem (e por isso não pode dar)."""
    if ator.is_superuser:
        return set()
    return (set(codigos) & MARCADAS) - permissoes_de(ator)


def _nome(usuario):
    return usuario.get_full_name() or usuario.get_username()


def conferir_administra(ator):
    if not (ator.is_superuser or ator.has_perm(GERENCIAR)):
        raise NaoPode(NEGADO)


def conferir_mexer_em(ator, alvo, *, no_proprio=False):
    """Pode mexer na conta desta pessoa? `no_proprio` libera quando ator e alvo são o mesmo.

    `no_proprio` serve para o que não aumenta acesso (encerrar as próprias sessões, por
    exemplo). Perfil, bloqueio, desligamento e data para acabar nunca passam com ele.
    """
    conferir_administra(ator)
    if alvo.pk == ator.pk:
        if no_proprio:
            return
        raise NaoPode("Ninguém muda o próprio acesso. Peça a outra pessoa que administra.")
    if alvo.is_superuser and not ator.is_superuser:
        raise NaoPode(f"{_nome(alvo)} é a conta técnica do servidor (superusuário). Ela só se "
                      "muda no próprio servidor.")
    faltam = faltam_para(ator, permissoes_de(alvo))
    if faltam:
        raise NaoPode(f"{_nome(alvo)} tem acesso que você não tem ({nomes(faltam)}). Só quem "
                      "tem esse acesso mexe na conta dessa pessoa.")


def conferir_dar_ou_tirar(ator, grupo):
    """Pode dar (ou tirar) este perfil de alguém?"""
    faltam = faltam_para(ator, permissoes_do_perfil(grupo))
    if faltam:
        raise NaoPode(f"Você não pode dar nem tirar o perfil {grupo.name}: ele tem acesso que "
                      f"você não tem ({nomes(faltam)}).")


def pode_dar(ator, grupo):
    try:
        conferir_dar_ou_tirar(ator, grupo)
    except NaoPode:
        return False
    return True


def conferir_editar_perfil(ator, grupo, novos_codigos):
    """Pode deixar este perfil com estas permissões?"""
    if not (ator.is_superuser or ator.has_perm(EDITAR_PERFIS)):
        raise NaoPode(NEGADO)
    if not ator.is_superuser and grupo.user_set.filter(pk=ator.pk).exists():
        raise NaoPode(f"Você está no perfil {grupo.name}: quem muda o que ele pode é outra "
                      "pessoa que edita perfis. Assim ninguém aumenta o próprio acesso.")
    desconhecidos = set(novos_codigos) - set(CODIGOS)
    if desconhecidos:
        raise NaoPode("A tela mandou uma permissão que não existe. Abra a tela de novo.")
    mudam = permissoes_do_perfil(grupo) ^ set(novos_codigos)
    faltam = faltam_para(ator, mudam)
    if faltam:
        raise NaoPode("Você só dá ou tira de um perfil o acesso a dinheiro e à administração "
                      f"que você mesmo tem. Falta: {nomes(faltam)}.")


def pode_editar_perfil(ator, grupo):
    """Se a tela mostra o perfil como editável para esta pessoa (as caixas de cada
    permissão marcada que ela não tem continuam travadas, conferidas na gravação)."""
    if not (ator.is_superuser or ator.has_perm(EDITAR_PERFIS)):
        return False
    return ator.is_superuser or not grupo.user_set.filter(pk=ator.pk).exists()


def administradores():
    """Contas ativas, com senha, que administram pessoas E perfis (sem o superusuário)."""
    Usuario = get_user_model()
    exigidas = []
    for codigo in (GERENCIAR, EDITAR_PERFIS):
        app_label, codename = codigo.split(".")
        permissao = Permission.objects.filter(content_type__app_label=app_label, codename=codename).first()
        if permissao is None:
            return []
        exigidas.append(permissao)
    consulta = Usuario.objects.filter(is_active=True, is_superuser=False)
    for permissao in exigidas:
        consulta = consulta.filter(Q(groups__permissions=permissao) | Q(user_permissions=permissao))
    return [pessoa for pessoa in consulta.distinct() if pessoa.has_usable_password()]


@contextmanager
def mantendo_um_administrador():
    """Envolve uma mudança de acesso, DENTRO de uma transação: se havia quem administrasse
    antes e não sobrou ninguém depois, levanta `NaoPode` e a transação desfaz tudo.

    Se não havia ninguém antes (banco recém-instalado, ninguém com senha ainda), não há o
    que proteger e a mudança passa: é o caso da instalação e dos comandos do servidor.
    """
    havia = bool(administradores())
    yield
    if havia and not administradores():
        raise NaoPode("Assim ninguém mais administraria os acessos: precisa ficar pelo menos "
                      "uma pessoa ativa, com senha, que administre pessoas e perfis. Dê esse "
                      "acesso a outra pessoa antes.")
