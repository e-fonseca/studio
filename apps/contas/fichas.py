"""O que as telas de acesso mostram: a lista de pessoas, a ficha de cada uma e a matriz.

Só leitura. O que muda acesso está em `servicos.py`; quem pode o quê, em `autorizacao.py`.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models import Count, Q

from apps.auditoria.models import EventoAuditoria

from . import autorizacao, catalogo, servicos, sessao
from .perfis import ORDEM

# O nome em português de cada evento de acesso, para a ficha e o histórico.
ROTULOS = {
    "acesso.entrada": "Entrou no sistema",
    "acesso.saida": "Saiu do sistema",
    "acesso.falha": "Senha errada na entrada",
    "acesso.negado": "Tentou abrir o que o perfil não deixa",
    "acesso.usuario_criado": "Conta criada",
    "acesso.perfil_definido": "Perfis mudaram",
    "acesso.senha_definida": "Senha definida pela administração",
    "acesso.senha_trocada": "Trocou a própria senha",
    "acesso.senha_recuperada": "Criou senha nova pelo código do e-mail",
    "acesso.codigo_pedido": "Pediu o código para recuperar a senha",
    "acesso.codigo_errado": "Errou o código de recuperar a senha",
    "acesso.email_definido": "E-mail de recuperação mudou",
    "acesso.usuario_bloqueado": "Acesso bloqueado",
    "acesso.usuario_desbloqueado": "Acesso desbloqueado",
    "acesso.usuario_desligado": "Acesso encerrado",
    "acesso.usuario_reativado": "Acesso liberado de novo",
    "acesso.prazo_definido": "Data para o acesso acabar mudou",
    "acesso.prazo_nao_cumprido": "A data passou, mas a conta não se desligou",
    "acesso.sessao_encerrada": "Sessão encerrada pela administração",
    "acesso.sessoes_encerradas": "Todas as sessões encerradas",
    "acesso.senha_confirmada": "Confirmou a senha para mexer em acessos",
    "acesso.confirmacao_falhou": "Errou a senha ao confirmar",
    "acesso.administrador_recuperado": "Acesso de administração recuperado no servidor",
    "permissao.perfis_alterados": "Perfis mudaram (por fora da tela)",
    "permissao.permissoes_individuais_alteradas": "Permissão individual mudou",
}


def rotulo(acao):
    return ROTULOS.get(acao, acao)


def _nome(usuario):
    return usuario.get_full_name() or usuario.get_username()


# ------------------------------------------------------------------ a lista
FILTROS = ("todos", "ativo", "pendente", "bloqueado", "desligado")


def pessoas(*, busca="", situacao="todos"):
    """A lista da tela Usuários, já filtrada no servidor, e quantas há em cada situação.

    A contagem é de todo mundo (sem a busca), para o filtro dizer quantos há em cada um.
    """
    Usuario = get_user_model()
    consulta = (Usuario.objects.select_related("vinculo").prefetch_related("groups")
                .order_by("first_name", "username"))
    linhas, contagem = [], dict.fromkeys(FILTROS, 0)
    busca = (busca or "").strip()
    for usuario in consulta:
        estado = servicos.situacao(usuario)
        contagem["todos"] += 1
        contagem[estado] += 1
        if situacao in FILTROS[1:] and estado != situacao:
            continue
        if busca and not _confere(usuario, busca):
            continue
        vinculo = getattr(usuario, "vinculo", None)
        linhas.append({
            "usuario": usuario,
            "nome": _nome(usuario),
            "perfis": sorted((g.name for g in usuario.groups.all()), key=_ordem_do_perfil),
            "situacao": estado,
            "situacao_rotulo": servicos.SITUACOES[estado],
            "sem_email": not (usuario.email or "").strip(),
            "acesso_ate": vinculo.acesso_ate if vinculo else None,
            "superusuario": usuario.is_superuser,
        })
    return linhas, contagem


def _confere(usuario, busca):
    alvo = " ".join([usuario.get_username(), usuario.first_name, usuario.last_name,
                     usuario.email or ""]).lower()
    return all(parte in alvo for parte in busca.lower().split())


def _ordem_do_perfil(nome):
    return (ORDEM.get(nome, 100), nome)


def perfis_para_dar(ator, *, ja_tem=()):
    """Os perfis ativos, cada um dizendo se este ator pode dá-lo, e por que não."""
    itens = []
    for perfil in servicos.perfis_ativos():
        grupo = perfil.grupo
        try:
            autorizacao.conferir_dar_ou_tirar(ator, grupo)
            motivo = ""
        except autorizacao.NaoPode as erro:
            motivo = str(erro)
        itens.append({"nome": grupo.name, "descricao": perfil.descricao,
                      "marcado": grupo.name in ja_tem, "pode": not motivo, "motivo": motivo})
    return itens


# ------------------------------------------------------------------ a ficha
def historico(alvo, limite=40):
    """O que aconteceu com esta conta e o que ela fez com o próprio acesso.

    Entra o que foi feito NA conta (perfil, senha, bloqueio), as entradas e saídas dela,
    as tentativas de abrir o que o perfil não deixa e as senhas erradas digitadas com o
    usuário dela (que a auditoria guarda pelo nome tentado, porque quem errou ainda não
    entrou).
    """
    eventos = (EventoAuditoria.objects
               .filter(Q(recurso_tipo="auth.user", recurso_id=str(alvo.pk))
                       | Q(usuario=alvo, acao__startswith="acesso.")
                       | Q(acao="acesso.falha", depois__usuario_tentado=alvo.get_username()))
               .order_by("-momento", "-id")[:limite])
    linhas = []
    for evento in eventos:
        linhas.append({
            "momento": evento.momento,
            "o_que": rotulo(evento.acao),
            "quem": evento.usuario_rotulo,
            "resultado": evento.resultado,
            "detalhe": _detalhe(evento),
            "origem": sessao.origem(evento.ip) if evento.ip else "",
        })
    return linhas


def _detalhe(evento):
    """Uma linha que diga o que mudou, sem despejar o JSON da auditoria."""
    antes, depois = evento.antes or {}, evento.depois or {}
    if evento.acao == "acesso.perfil_definido":
        de = ", ".join(antes.get("perfis") or []) or "nenhum"
        para = ", ".join(depois.get("perfis") or []) or "nenhum"
        return f"de {de} para {para}"
    if evento.acao == "acesso.usuario_criado":
        return "perfis: " + (", ".join(depois.get("perfis") or []) or "nenhum")
    if evento.acao == "acesso.prazo_definido":
        return f"de {antes.get('acesso_ate') or 'sem data'} para {depois.get('acesso_ate') or 'sem data'}"
    if evento.acao == "acesso.email_definido":
        return f"de {antes.get('email') or 'sem e-mail'} para {depois.get('email') or 'sem e-mail'}"
    if evento.acao == "acesso.negado":
        return depois.get("endereco", "")
    if evento.acao == "acesso.sessao_encerrada":
        return f"{depois.get('aparelho', '')}, {depois.get('origem', '')}".strip(", ")
    if "sessoes_encerradas" in depois and depois["sessoes_encerradas"]:
        quantas = depois["sessoes_encerradas"]
        texto = "1 sessão caiu" if quantas == 1 else f"{quantas} sessões caíram"
        return f"{evento.motivo}. {texto}" if evento.motivo else texto
    if depois.get("superusuario"):
        return "conta técnica do servidor (superusuário)"
    return evento.motivo


def ficha(ator, alvo):
    """Tudo o que a ficha mostra, e o que este ator pode fazer nela."""
    vinculo = getattr(alvo, "vinculo", None)
    try:
        autorizacao.conferir_mexer_em(ator, alvo)
        nao_pode = ""
    except autorizacao.NaoPode as erro:
        nao_pode = str(erro)
    proprio = alvo.pk == ator.pk
    ja_tem = set(servicos.perfis_do_usuario(alvo))
    perfis = perfis_para_dar(ator, ja_tem=ja_tem)
    # Perfil retirado que a pessoa ainda tem (não deveria acontecer: só se retira vazio).
    nomes = {p["nome"] for p in perfis}
    for nome in sorted(ja_tem - nomes):
        perfis.append({"nome": nome, "descricao": "", "marcado": True, "pode": False,
                       "motivo": "Perfil retirado."})
    estado = servicos.situacao(alvo, vinculo)
    efetivas = servicos.permissoes_efetivas(alvo)
    return {
        "alvo": alvo,
        "nome": _nome(alvo),
        "vinculo": vinculo,
        "situacao": estado,
        "situacao_rotulo": servicos.SITUACOES[estado],
        "proprio": proprio,
        "pode_mexer": not nao_pode,
        "nao_pode": nao_pode,
        "perfis": perfis,
        "perfis_atuais": [p for p in perfis if p["marcado"]],
        "efetivas": efetivas,
        "contagem": {
            "total": sum(len(itens) for _, itens in efetivas),
            "dinheiro": sum(1 for _, itens in efetivas for i in itens if i["permissao"].dinheiro),
            "administracao": sum(1 for _, itens in efetivas for i in itens
                                 if i["permissao"].administracao),
        },
        "sessoes": servicos.sessoes_de(alvo),
        "historico": historico(alvo),
        "ve_auditoria": ator.has_perm("auditoria.ver_auditoria"),
    }


# ------------------------------------------------------------------ perfis e permissões
def matriz():
    """A matriz da tela Perfis e permissões: linhas = permissões por módulo, colunas = perfis."""
    perfis = servicos.perfis_ativos()
    grupos = [perfil.grupo for perfil in perfis]
    tem = {grupo.pk: autorizacao.permissoes_do_perfil(grupo) for grupo in grupos}
    gente = dict(Group.objects.filter(pk__in=[g.pk for g in grupos])
                 .annotate(n=Count("user", filter=Q(user__is_active=True)))
                 .values_list("pk", "n"))
    colunas = [{"grupo": perfil.grupo, "perfil": perfil, "pessoas": gente.get(perfil.grupo.pk, 0),
                "permissoes": len(tem[perfil.grupo.pk] & set(catalogo.CODIGOS))}
               for perfil in perfis]
    modulos = []
    for modulo, itens in catalogo.por_modulo():
        linhas = [{"permissao": p, "marcas": [p.codigo in tem[g.pk] for g in grupos]} for p in itens]
        modulos.append({"modulo": modulo, "linhas": linhas})
    return colunas, modulos


def impacto():
    """O relatório de impacto pedido no prompt: quem tem acesso a quê, e o que pede olho.

    - Pessoas ativas sem perfil nenhum (entram e não abrem nada).
    - Contas técnicas (superusuário), que passam por cima de tudo.
    - Pessoas com permissão individual, fora de perfil (não aparecem na matriz).
    - Perfis sem ninguém dentro.
    - Quantas pessoas ativas veem dinheiro, e quantas administram acessos.
    """
    Usuario = get_user_model()
    ativos = Usuario.objects.filter(is_active=True)
    sem_perfil = list(ativos.filter(groups__isnull=True, is_superuser=False).order_by("username"))
    superusuarios = list(Usuario.objects.filter(is_superuser=True).order_by("username"))
    individuais = list(ativos.filter(user_permissions__isnull=False).distinct().order_by("username"))
    vazios = [perfil.grupo.name for perfil in servicos.perfis_ativos()
              if not perfil.grupo.user_set.filter(is_active=True).exists()]
    dinheiro, administram = [], []
    for pessoa in ativos.filter(is_superuser=False).order_by("first_name", "username"):
        codigos = autorizacao.permissoes_de(pessoa)
        if codigos & {p.codigo for p in catalogo.CATALOGO if p.dinheiro}:
            dinheiro.append(pessoa)
        if autorizacao.GERENCIAR in codigos or autorizacao.EDITAR_PERFIS in codigos:
            administram.append(pessoa)
    return {
        "sem_perfil": sem_perfil,
        "superusuarios": superusuarios,
        "individuais": individuais,
        "perfis_vazios": vazios,
        "veem_dinheiro": dinheiro,
        "administram": administram,
        "administradores_completos": autorizacao.administradores(),
    }
