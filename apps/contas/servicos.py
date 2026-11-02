"""O que muda o acesso de alguém. Toda mudança passa por aqui e vai para a auditoria.

As telas chamam estas funções com `responsavel=request.user`; aí valem as regras de
`autorizacao.py` (ninguém mexe no próprio acesso, ninguém dá o que não tem, sempre fica
alguém administrando). Os comandos do servidor chamam sem responsável: quem está no
servidor como administrador do Windows já pode tudo, e a auditoria assina "linha de
comando". Mesmo assim, ninguém tira o último administrador sem perceber.
"""

import contextvars

from django.contrib.auth.models import Group
from django.contrib.sessions.models import Session
from django.db import transaction
from django.utils import timezone

from apps.auditoria.servicos import registrar

from . import autorizacao, catalogo, sessao
from .autorizacao import NaoPode
from .models import Perfil, PermissaoOferecida, VinculoIdentidade
from .perfis import DESCRICOES, ORDEM, PADRAO

# Ligado enquanto um serviço daqui muda as permissões de um perfil ou os perfis de uma
# pessoa: os sinais genéricos de sinais.py (que pegam mudança feita por qualquer caminho,
# inclusive o admin do Django) ficam quietos, porque o serviço já registra o evento
# completo, com quem fez e o motivo. Assim a ficha não mostra a mesma mudança duas vezes.
mudando_pela_tela = contextvars.ContextVar("contas_mudando_pela_tela", default=False)


def _quem(responsavel):
    return None if responsavel else "linha de comando"


def _data(valor):
    return valor.isoformat() if valor else ""


# ------------------------------------------------------------------ perfis
def perfil_de(grupo):
    """O Perfil (descrição e ordem) de um grupo, criado na hora se ainda não existir."""
    perfil, _ = Perfil.objects.get_or_create(
        grupo=grupo,
        defaults={"descricao": DESCRICOES.get(grupo.name, ""),
                  "padrao": grupo.name in PADRAO,
                  "ordem": ORDEM.get(grupo.name, 100)},
    )
    return perfil


def configurar_perfis():
    """Cria os perfis que vêm com o sistema e entrega a cada um o padrão dele, UMA vez.

    Roda a cada atualização (instalar.ps1, depois do migrate). Até a 1.43.0 ele regravava
    as permissões de cada perfil com o que estava no código; com os perfis editáveis pela
    tela, isso desfaria o que a gerência mudou. Agora cada permissão do padrão entra no
    perfil uma vez só (`PermissaoOferecida`): se a gerência tirar, não volta; se uma versão
    nova trouxer permissão nova para um perfil, ela entra uma vez e daí em diante é da
    gerência. Perfil padrão que a gerência retirou não é recriado. Rodar de novo não
    duplica nada.
    """
    resultado = {}
    novidades = {}
    for nome, codigos in PADRAO.items():
        grupo, _ = Group.objects.get_or_create(name=nome)
        perfil = perfil_de(grupo)
        if not perfil.padrao:
            perfil.padrao = True
            perfil.save(update_fields=["padrao"])
        if perfil.retirado_em is not None:
            continue
        permissoes = catalogo.objetos(codigos)
        ja = set(PermissaoOferecida.objects.filter(grupo=grupo).values_list("permissao_id", flat=True))
        entram = [p for p in permissoes if p.pk not in ja]
        if entram:
            token = mudando_pela_tela.set(True)
            try:
                grupo.permissions.add(*entram)
            finally:
                mudando_pela_tela.reset(token)
            PermissaoOferecida.objects.bulk_create(
                [PermissaoOferecida(grupo=grupo, permissao=p) for p in entram], ignore_conflicts=True)
            novidades[nome] = sorted(catalogo.codigo_de(p) for p in entram)
        resultado[nome] = grupo.permissions.count()
    # Grupos criados por outro caminho (admin do Django, versão antiga) também são perfis.
    for grupo in Group.objects.filter(perfil__isnull=True):
        perfil_de(grupo)
    registrar("permissao.perfis_configurados", servico="sistema",
              depois={"permissoes_por_perfil": resultado, "entraram_agora": novidades})
    return resultado


def perfis_ativos():
    """Os perfis que se podem dar, na ordem da tela."""
    for grupo in Group.objects.filter(perfil__isnull=True):
        perfil_de(grupo)
    return list(Perfil.objects.filter(retirado_em__isnull=True).select_related("grupo"))


def perfis_retirados():
    return list(Perfil.objects.filter(retirado_em__isnull=False).select_related("grupo"))


def perfis_do_usuario(usuario):
    """Os nomes dos perfis desta pessoa, na ordem da tela."""
    return list(usuario.groups.order_by("perfil__ordem", "name").values_list("name", flat=True))


def _grupos_por_nome(nomes):
    nomes = [n for n in dict.fromkeys(n.strip() for n in nomes if n and n.strip())]
    grupos = list(Group.objects.filter(name__in=nomes).select_related("perfil"))
    faltando = [n for n in nomes if n not in {g.name for g in grupos}]
    if faltando and all(n in PADRAO for n in faltando):
        # Banco recém-criado, antes do configurar_perfis do instalador: os perfis que vêm
        # com o sistema passam a existir agora, com o padrão de cada um.
        configurar_perfis()
        grupos = list(Group.objects.filter(name__in=nomes).select_related("perfil"))
        faltando = [n for n in nomes if n not in {g.name for g in grupos}]
    if faltando:
        raise ValueError(f"Perfil desconhecido: {', '.join(faltando)}.")
    for grupo in grupos:
        perfil = getattr(grupo, "perfil", None)
        if perfil is not None and perfil.retirado_em is not None:
            raise ValueError(f"O perfil {grupo.name} foi retirado e não se dá mais a ninguém.")
    return grupos


@transaction.atomic
def definir_perfis(usuario, nomes, *, responsavel=None):
    """Deixa a pessoa com estes perfis (zero, um ou vários). Devolve se mudou."""
    novos = _grupos_por_nome(nomes)
    antes_grupos = set(usuario.groups.all())
    if set(novos) == antes_grupos:
        return False
    if responsavel is not None:
        autorizacao.conferir_mexer_em(responsavel, usuario)
        for grupo in antes_grupos ^ set(novos):
            autorizacao.conferir_dar_ou_tirar(responsavel, grupo)
    antes = perfis_do_usuario(usuario)
    with autorizacao.mantendo_um_administrador():
        token = mudando_pela_tela.set(True)
        try:
            usuario.groups.set(novos)
        finally:
            mudando_pela_tela.reset(token)
    registrar(
        "acesso.perfil_definido",
        usuario=responsavel,
        servico=_quem(responsavel),
        recurso=usuario,
        recurso_rotulo=usuario.get_username(),
        antes={"perfis": antes},
        depois={"perfis": perfis_do_usuario(usuario)},
    )
    return True


def definir_perfil(usuario, perfil, *, responsavel=None):
    """Deixa a pessoa com um perfil só. Perfil em branco tira todo o acesso.

    É o jeito da 1.43.0 (um perfil por pessoa), mantido para os comandos e testes antigos.
    """
    return definir_perfis(usuario, [perfil] if perfil else [], responsavel=responsavel)


@transaction.atomic
def criar_perfil(nome, *, descricao="", copiar_de=None, responsavel=None):
    """Cria um perfil novo. Com `copiar_de`, nasce com as mesmas permissões daquele."""
    nome = " ".join((nome or "").split())
    if not nome:
        raise ValueError("Dê um nome ao perfil.")
    if len(nome) > 150:
        raise ValueError("Nome de perfil grande demais: até 150 letras.")
    if Group.objects.filter(name__iexact=nome).exists():
        raise ValueError(f"Já existe um perfil chamado {nome}.")
    codigos = autorizacao.permissoes_do_perfil(copiar_de) if copiar_de is not None else set()
    if responsavel is not None:
        if not (responsavel.is_superuser or responsavel.has_perm(autorizacao.EDITAR_PERFIS)):
            raise NaoPode(autorizacao.NEGADO)
        faltam = autorizacao.faltam_para(responsavel, codigos)
        if faltam:
            raise NaoPode(f"Você não pode copiar o perfil {copiar_de.name}: ele tem acesso que "
                          f"você não tem ({autorizacao.nomes(faltam)}).")
    grupo = Group.objects.create(name=nome)
    Perfil.objects.create(grupo=grupo, descricao=(descricao or "").strip(), padrao=False, ordem=100)
    if codigos:
        token = mudando_pela_tela.set(True)
        try:
            grupo.permissions.set(catalogo.objetos(codigos))
        finally:
            mudando_pela_tela.reset(token)
    registrar("permissao.perfil_criado", usuario=responsavel, servico=_quem(responsavel),
              recurso=grupo, recurso_rotulo=nome,
              depois={"perfil": nome, "copiado_de": copiar_de.name if copiar_de else "",
                      "permissoes": sorted(codigos)})
    return grupo


@transaction.atomic
def editar_perfil(grupo, codigos, *, descricao=None, motivo="", responsavel=None):
    """Deixa o perfil com estas permissões (códigos do catálogo). Devolve se mudou."""
    codigos = set(codigos)
    if responsavel is not None:
        autorizacao.conferir_editar_perfil(responsavel, grupo, codigos)
    perfil = perfil_de(grupo)
    antes = autorizacao.permissoes_do_perfil(grupo)
    # Permissão que está no perfil e não está no catálogo (criada à mão no admin do Django)
    # não some por a tela não mostrá-la: a tela só manda o que está no catálogo.
    fora_do_catalogo = antes - set(catalogo.CODIGOS)
    depois = codigos | fora_do_catalogo
    nova_descricao = perfil.descricao if descricao is None else descricao.strip()
    if depois == antes and nova_descricao == perfil.descricao:
        return False
    if depois != antes and not (motivo or "").strip():
        raise ValueError("Diga em poucas palavras por que o perfil mudou. Fica na auditoria.")
    manter = [p for p in grupo.permissions.select_related("content_type")
              if catalogo.codigo_de(p) in fora_do_catalogo]
    with autorizacao.mantendo_um_administrador():
        token = mudando_pela_tela.set(True)
        try:
            grupo.permissions.set(catalogo.objetos(codigos) + manter)
        finally:
            mudando_pela_tela.reset(token)
    if nova_descricao != perfil.descricao:
        perfil.descricao = nova_descricao
        perfil.save(update_fields=["descricao"])
    registrar("permissao.perfil_alterado", usuario=responsavel, servico=_quem(responsavel),
              recurso=grupo, recurso_rotulo=grupo.name,
              antes={"permissoes": sorted(antes)},
              depois={"permissoes": sorted(depois), "entraram": sorted(depois - antes),
                      "sairam": sorted(antes - depois),
                      "pessoas_no_perfil": grupo.user_set.count()},
              motivo=(motivo or "").strip())
    return True


@transaction.atomic
def retirar_perfil(grupo, *, responsavel=None):
    """Tira o perfil das listas. Só perfil sem ninguém dentro."""
    if responsavel is not None:
        autorizacao.conferir_editar_perfil(responsavel, grupo, set())
    if grupo.user_set.exists():
        raise ValueError(f"Ainda há gente no perfil {grupo.name}. Tire as pessoas dele antes.")
    perfil = perfil_de(grupo)
    antes = autorizacao.permissoes_do_perfil(grupo)
    token = mudando_pela_tela.set(True)
    try:
        grupo.permissions.clear()
    finally:
        mudando_pela_tela.reset(token)
    perfil.retirado_em = timezone.now()
    perfil.save(update_fields=["retirado_em"])
    registrar("permissao.perfil_retirado", usuario=responsavel, servico=_quem(responsavel),
              recurso=grupo, recurso_rotulo=grupo.name, antes={"permissoes": sorted(antes)})


@transaction.atomic
def devolver_perfil(grupo, *, responsavel=None):
    """Traz de volta um perfil retirado, sem permissão nenhuma: a gerência escolhe de novo."""
    if responsavel is not None and not (responsavel.is_superuser
                                        or responsavel.has_perm(autorizacao.EDITAR_PERFIS)):
        raise NaoPode(autorizacao.NEGADO)
    perfil = perfil_de(grupo)
    perfil.retirado_em = None
    perfil.save(update_fields=["retirado_em"])
    registrar("permissao.perfil_devolvido", usuario=responsavel, servico=_quem(responsavel),
              recurso=grupo, recurso_rotulo=grupo.name)


# ------------------------------------------------------------------ sessões
def encerrar_sessoes(usuario, *, menos=None):
    """Remove as sessões abertas do usuário (banco de sessões do Django).

    `menos` é a chave de uma sessão que fica (a de quem está encerrando as próprias).
    """
    removidas = 0
    for registro in Session.objects.filter(expire_date__gte=timezone.now()).iterator():
        if menos and registro.session_key == menos:
            continue
        if str(registro.get_decoded().get("_auth_user_id")) == str(usuario.pk):
            registro.delete()
            removidas += 1
    return removidas


def encerrar_todas_as_sessoes(usuario, *, responsavel=None, menos=None):
    """O "Encerrar todas" da ficha: derruba as sessões da pessoa em todos os aparelhos.

    Na própria ficha, a sessão de agora fica (`menos`): é o "sair dos outros aparelhos".
    """
    if responsavel is not None:
        autorizacao.conferir_mexer_em(responsavel, usuario, no_proprio=True)
    removidas = encerrar_sessoes(usuario, menos=menos)
    registrar("acesso.sessoes_encerradas", usuario=responsavel, servico=_quem(responsavel),
              recurso=usuario, recurso_rotulo=usuario.get_username(),
              depois={"sessoes_encerradas": removidas})
    return removidas


def sessoes_de(usuario):
    """As sessões vivas da pessoa: de quando, de onde e de que aparelho.

    Sessão que já passou do tempo parado ou do tempo máximo ainda está no banco até o
    cookie vencer, mas não entra mais (o LimiteDeSessaoMiddleware a derruba no primeiro
    clique); por isso não aparece aqui.
    """
    vivas = []
    for registro in Session.objects.filter(expire_date__gte=timezone.now()).iterator():
        dados = registro.get_decoded()
        if str(dados.get("_auth_user_id")) != str(usuario.pk):
            continue
        descricao = sessao.descrever(dados)
        if descricao["vencida"]:
            continue
        descricao["chave"] = registro.session_key
        vivas.append(descricao)
    vivas.sort(key=lambda s: s["visto_em"] or s["entrou_em"] or timezone.now(), reverse=True)
    return vivas


def encerrar_sessao(usuario, chave, *, responsavel=None):
    """Encerra UMA sessão, conferindo que ela é desta pessoa. Devolve se encerrou."""
    if responsavel is not None:
        autorizacao.conferir_mexer_em(responsavel, usuario, no_proprio=True)
    registro = Session.objects.filter(session_key=chave, expire_date__gte=timezone.now()).first()
    if registro is None:
        return False
    dados = registro.get_decoded()
    # A chave veio da tela: sem esta conferência, trocar o número do usuário no endereço e
    # mandar a chave de outra pessoa derrubaria a sessão de quem não devia.
    if str(dados.get("_auth_user_id")) != str(usuario.pk):
        return False
    descricao = sessao.descrever(dados)
    registro.delete()
    registrar("acesso.sessao_encerrada", usuario=responsavel, servico=_quem(responsavel),
              recurso=usuario, recurso_rotulo=usuario.get_username(),
              depois={"aparelho": descricao["aparelho"], "origem": descricao["origem"]})
    return True


# ------------------------------------------------------------------ situação da conta
@transaction.atomic
def desligar_usuario(usuario, *, motivo, responsavel=None, servico=None):
    """Bloqueia o acesso de quem saiu da empresa e encerra as sessões abertas."""
    if not motivo.strip():
        raise ValueError("Informe o motivo do desligamento.")
    if responsavel is not None:
        autorizacao.conferir_mexer_em(responsavel, usuario)
    with autorizacao.mantendo_um_administrador():
        usuario.is_active = False
        usuario.save(update_fields=["is_active"])
        vinculo, _ = VinculoIdentidade.objects.get_or_create(usuario=usuario)
        vinculo.desligado_em = timezone.now()
        # Desligado vale mais que bloqueado: quem saiu da empresa não está "parado".
        vinculo.bloqueado_em = None
        vinculo.bloqueio_motivo = ""
        vinculo.save(update_fields=["desligado_em", "bloqueado_em", "bloqueio_motivo"])
    sessoes = encerrar_sessoes(usuario)
    registrar(
        "acesso.usuario_desligado",
        usuario=responsavel,
        servico=servico or _quem(responsavel),
        recurso=usuario,
        recurso_rotulo=usuario.get_username(),
        depois={"ativo": False, "sessoes_encerradas": sessoes},
        motivo=motivo,
    )
    return sessoes


@transaction.atomic
def bloquear_usuario(usuario, *, motivo, responsavel=None):
    """Para o acesso por um tempo (férias, afastamento, suspeita). Derruba as sessões."""
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValueError("Diga o motivo do bloqueio. Fica na ficha da pessoa e na auditoria.")
    if responsavel is not None:
        autorizacao.conferir_mexer_em(responsavel, usuario)
    vinculo, _ = VinculoIdentidade.objects.get_or_create(usuario=usuario)
    if not usuario.is_active:
        raise ValueError(f"{usuario.get_username()} já está sem acesso.")
    with autorizacao.mantendo_um_administrador():
        usuario.is_active = False
        usuario.save(update_fields=["is_active"])
        vinculo.bloqueado_em = timezone.now()
        vinculo.bloqueio_motivo = motivo[:200]
        vinculo.save(update_fields=["bloqueado_em", "bloqueio_motivo"])
    sessoes = encerrar_sessoes(usuario)
    registrar("acesso.usuario_bloqueado", usuario=responsavel, servico=_quem(responsavel),
              recurso=usuario, recurso_rotulo=usuario.get_username(),
              depois={"ativo": False, "sessoes_encerradas": sessoes}, motivo=motivo)
    return sessoes


@transaction.atomic
def desbloquear_usuario(usuario, *, responsavel=None):
    if responsavel is not None:
        autorizacao.conferir_mexer_em(responsavel, usuario)
    vinculo, _ = VinculoIdentidade.objects.get_or_create(usuario=usuario)
    if vinculo.bloqueado_em is None or vinculo.desligado_em is not None:
        raise ValueError(f"{usuario.get_username()} não está bloqueado.")
    antes = vinculo.bloqueio_motivo
    usuario.is_active = True
    usuario.save(update_fields=["is_active"])
    vinculo.bloqueado_em = None
    vinculo.bloqueio_motivo = ""
    vinculo.save(update_fields=["bloqueado_em", "bloqueio_motivo"])
    registrar("acesso.usuario_desbloqueado", usuario=responsavel, servico=_quem(responsavel),
              recurso=usuario, recurso_rotulo=usuario.get_username(),
              antes={"motivo_do_bloqueio": antes}, depois={"ativo": True})


@transaction.atomic
def reativar_usuario(usuario, *, responsavel=None):
    """"Liberar de novo" quem foi desligado (ou bloqueado): a conta volta a entrar."""
    if responsavel is not None:
        autorizacao.conferir_mexer_em(responsavel, usuario)
    usuario.is_active = True
    usuario.save(update_fields=["is_active"])
    vinculo, _ = VinculoIdentidade.objects.get_or_create(usuario=usuario)
    vinculo.desligado_em = None
    vinculo.bloqueado_em = None
    vinculo.bloqueio_motivo = ""
    # A data que acabou com o acesso também sai: deixá-la desligaria a conta de novo no
    # minuto seguinte. Quem liberou marca outra data, se for o caso.
    prazo_antigo = vinculo.acesso_ate
    vinculo.acesso_ate = None
    vinculo.save(update_fields=["desligado_em", "bloqueado_em", "bloqueio_motivo", "acesso_ate"])
    registrar(
        "acesso.usuario_reativado",
        usuario=responsavel,
        servico=_quem(responsavel),
        recurso=usuario,
        recurso_rotulo=usuario.get_username(),
        antes={"acesso_ate": _data(prazo_antigo)},
        depois={"ativo": True, "acesso_ate": ""},
    )


def situacao(usuario, vinculo=None):
    """A situação que a tela mostra: pendente, ativo, bloqueado ou desligado."""
    if vinculo is None:
        vinculo = getattr(usuario, "vinculo", None)
    if not usuario.is_active:
        if vinculo is not None and vinculo.bloqueado_em is not None and vinculo.desligado_em is None:
            return "bloqueado"
        return "desligado"
    if not usuario.has_usable_password():
        return "pendente"
    return "ativo"


SITUACOES = {
    "ativo": "Ativo",
    "pendente": "Pendente de ativação",
    "bloqueado": "Bloqueado",
    "desligado": "Desligado",
}


def definir_acesso_ate(usuario, ultimo_dia, *, responsavel=None):
    """Marca o último dia de acesso da pessoa. `None` tira a data.

    A data é inclusiva: "até 12/11" entra no dia 12 inteiro e a conta se desliga sozinha
    no dia 13 (`encerrar_acessos_vencidos`). Data que já passou é recusada, porque ela
    desligaria a conta na hora sem ninguém ter pedido isso: para encerrar hoje, existe o
    Encerrar, que pede o motivo.
    """
    if responsavel is not None:
        autorizacao.conferir_mexer_em(responsavel, usuario)
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
        servico=_quem(responsavel),
        recurso=usuario,
        recurso_rotulo=usuario.get_username(),
        antes={"acesso_ate": _data(antes)},
        depois={"acesso_ate": _data(ultimo_dia)},
    )
    return True


def encerrar_acessos_vencidos(hoje=None):
    """Desliga quem passou do último dia de acesso, e devolve quem foi desligado.

    É o Encerrar da tela de usuários, feito pelo sistema: a conta fica desligada, as
    sessões abertas caem e a auditoria diz que foi a data marcada, e quando. A única
    exceção é a última pessoa que administra os acessos: essa não se desliga sozinha (a
    loja ficaria sem ninguém para dar acesso), e a auditoria registra o porquê a cada dia.
    """
    hoje = hoje or timezone.localdate()
    vencidos = (VinculoIdentidade.objects
                .filter(acesso_ate__lt=hoje, usuario__is_active=True)
                .select_related("usuario"))
    desligados = []
    for vinculo in vencidos:
        try:
            with transaction.atomic():
                desligar_usuario(
                    vinculo.usuario,
                    motivo=f"Acesso combinado até {vinculo.acesso_ate:%d/%m/%Y}",
                    servico="data marcada para o acesso acabar",
                )
        except NaoPode as erro:
            registrar("acesso.prazo_nao_cumprido", servico="data marcada para o acesso acabar",
                      recurso=vinculo.usuario, recurso_rotulo=vinculo.usuario.get_username(),
                      resultado="negado", motivo=str(erro))
            continue
        desligados.append(vinculo.usuario)
    return desligados


# ------------------------------------------------------------------ contas e senhas
@transaction.atomic
def criar_usuario(*, apelido, nome, sobrenome="", email="", cpf="", perfil="", perfis=None,
                  responsavel=None, acesso_ate=None):
    """Cria a conta sem senha: quem administra define a senha logo em seguida.

    Conta sem senha utilizável não entra no sistema, então não há janela em que alguém
    acessa com uma senha provisória que ficou escrita em algum lugar.
    """
    from django.contrib.auth import get_user_model  # noqa: PLC0415 - evita import circular no topo

    from apps.core import documento  # noqa: PLC0415 - idem

    escolhidos = list(perfis) if perfis is not None else ([perfil] if perfil else [])
    grupos = _grupos_por_nome(escolhidos)
    if responsavel is not None:
        autorizacao.conferir_administra(responsavel)
        for grupo in grupos:
            autorizacao.conferir_dar_ou_tirar(responsavel, grupo)

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
    if grupos:
        token = mudando_pela_tela.set(True)
        try:
            usuario.groups.set(grupos)
        finally:
            mudando_pela_tela.reset(token)
    registrar(
        "acesso.usuario_criado",
        usuario=responsavel,
        servico=_quem(responsavel),
        recurso=usuario,
        recurso_rotulo=apelido,
        # O CPF não entra aqui de propósito: a trilha de auditoria não guarda documento.
        depois={"nome": usuario.get_full_name(), "perfis": [g.name for g in grupos],
                "ativo": True, "acesso_ate": _data(acesso_ate)},
    )
    return usuario


def definir_senha(usuario, senha, *, responsavel=None):
    """Troca a senha e derruba as sessões abertas, para a senha antiga não continuar valendo."""
    from django.contrib.auth.password_validation import validate_password  # noqa: PLC0415

    if responsavel is not None:
        autorizacao.conferir_mexer_em(responsavel, usuario)
    validate_password(senha, usuario)
    usuario.set_password(senha)
    usuario.save(update_fields=["password"])
    sessoes = encerrar_sessoes(usuario)
    registrar(
        "acesso.senha_definida",
        usuario=responsavel,
        servico=_quem(responsavel),
        recurso=usuario,
        recurso_rotulo=usuario.get_username(),
        # A senha em si nunca entra na auditoria.
        depois={"sessoes_encerradas": sessoes},
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


# ------------------------------------------------------------------ o que a pessoa pode
def permissoes_efetivas(usuario):
    """O que a pessoa pode, por módulo, e de onde vem cada permissão.

    [(módulo, [{"permissao": Permissao, "de": ["Perfil A", "individual"]}, ...]), ...]
    """
    origem = {}
    for grupo in usuario.groups.prefetch_related("permissions__content_type"):
        for permissao in grupo.permissions.all():
            origem.setdefault(catalogo.codigo_de(permissao), []).append(grupo.name)
    for permissao in usuario.user_permissions.select_related("content_type"):
        origem.setdefault(catalogo.codigo_de(permissao), []).append("permissão individual")
    if usuario.is_superuser:
        for codigo in catalogo.CODIGOS:
            origem.setdefault(codigo, []).append("superusuário")
    return [
        (modulo, [{"permissao": p, "de": origem[p.codigo]} for p in itens])
        for modulo, itens in catalogo.por_modulo(set(origem))
    ]
