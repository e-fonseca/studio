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
def desligar_usuario(usuario, *, motivo, responsavel=None, servico=None):
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
        servico=servico or (None if responsavel else "linha de comando"),
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


def _data(valor):
    return valor.isoformat() if valor else ""


def definir_acesso_ate(usuario, ultimo_dia, *, responsavel=None):
    """Marca o último dia de acesso da pessoa. `None` tira a data.

    A data é inclusiva: "até 12/11" entra no dia 12 inteiro e a conta se desliga sozinha
    no dia 13 (`encerrar_acessos_vencidos`). Data que já passou é recusada, porque ela
    desligaria a conta na hora sem ninguém ter pedido isso: para encerrar hoje, existe o
    Encerrar, que pede o motivo.
    """
    if ultimo_dia is not None and ultimo_dia < timezone.localdate():
        raise ValueError(
            f"{ultimo_dia:%d/%m/%Y} já passou. Para encerrar o acesso hoje, use Encerrar, "
            "com o motivo."
        )
    vinculo, _ = VinculoIdentidade.objects.get_or_create(usuario=usuario)
    antes = vinculo.acesso_ate
    if antes == ultimo_dia:
        return False
    vinculo.acesso_ate = ultimo_dia
    vinculo.save(update_fields=["acesso_ate"])
    registrar(
        "acesso.prazo_definido",
        usuario=responsavel,
        servico=None if responsavel else "linha de comando",
        recurso=usuario,
        recurso_rotulo=usuario.get_username(),
        antes={"acesso_ate": _data(antes)},
        depois={"acesso_ate": _data(ultimo_dia)},
    )
    return True


def encerrar_acessos_vencidos(hoje=None):
    """Desliga quem passou do último dia de acesso, e devolve quem foi desligado.

    É o Encerrar da tela de usuários, feito pelo sistema: a conta fica desligada, as
    sessões abertas caem e a auditoria diz que foi a data marcada, e quando.
    """
    hoje = hoje or timezone.localdate()
    vencidos = (VinculoIdentidade.objects
                .filter(acesso_ate__lt=hoje, usuario__is_active=True)
                .select_related("usuario"))
    desligados = []
    for vinculo in vencidos:
        desligar_usuario(
            vinculo.usuario,
            motivo=f"Acesso combinado até {vinculo.acesso_ate:%d/%m/%Y}",
            servico="data marcada para o acesso acabar",
        )
        desligados.append(vinculo.usuario)
    return desligados


@transaction.atomic
def criar_usuario(*, apelido, nome, sobrenome="", email="", cpf="", perfil="", responsavel=None,
                  acesso_ate=None):
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

    if acesso_ate is not None and acesso_ate < timezone.localdate():
        raise ValueError(f"O último dia de acesso ({acesso_ate:%d/%m/%Y}) já passou.")

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
    VinculoIdentidade.objects.get_or_create(usuario=usuario,
                                            defaults={"cpf": numeros, "acesso_ate": acesso_ate})
    if perfil:
        definir_perfil(usuario, perfil, responsavel=responsavel)
    registrar(
        "acesso.usuario_criado",
        usuario=responsavel,
        servico=None if responsavel else "linha de comando",
        recurso=usuario,
        recurso_rotulo=apelido,
        # O CPF não entra aqui de propósito: a trilha de auditoria não guarda documento.
        depois={"nome": usuario.get_full_name(), "perfil": perfil, "ativo": True,
                "acesso_ate": _data(acesso_ate)},
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
    # A data que acabou com o acesso também sai: deixá-la desligaria a conta de novo no
    # minuto seguinte. Quem liberou marca outra data, se for o caso.
    prazo_antigo = vinculo.acesso_ate
    vinculo.acesso_ate = None
    vinculo.save(update_fields=["desligado_em", "acesso_ate"])
    registrar(
        "acesso.usuario_reativado",
        usuario=responsavel,
        servico=None if responsavel else "linha de comando",
        recurso=usuario,
        recurso_rotulo=usuario.get_username(),
        antes={"acesso_ate": _data(prazo_antigo)},
        depois={"ativo": True, "acesso_ate": ""},
    )


def trocar_a_propria_senha(usuario, senha_nova):
    """A pessoa troca a própria senha. As OUTRAS sessões dela caem; a de agora a tela refaz.

    Já validada pelo formulário (o mesmo validador de `definir_senha`). A senha nunca
    entra na auditoria; entra só que foi trocada, por quem e quantas sessões caíram.
    """
    usuario.set_password(senha_nova)
    usuario.save(update_fields=["password"])
    sessoes = encerrar_sessoes(usuario)
    registrar(
        "acesso.senha_trocada",
        usuario=usuario,
        recurso=usuario,
        recurso_rotulo=usuario.get_username(),
        depois={"sessoes_encerradas": sessoes},
    )
    return sessoes
