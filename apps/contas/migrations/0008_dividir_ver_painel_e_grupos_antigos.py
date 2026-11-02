"""1.44.0: divide o `ver_painel` sem ninguém perder acesso, e limpa os grupos antigos.

1. **A divisão.** Até a 1.43.0 o `importacao.ver_painel` abria todo número da loja, do
   Dashboard à margem e à lista de compra. Na 1.44.0 a lista de compra, as vendas, a margem
   e o histórico das importações ganharam permissão própria (`compras.ver_compras`,
   `importacao.ver_vendas`, `importacao.ver_margem`, `importacao.ver_importacoes`). Quem
   tinha o `ver_painel` — perfil ou pessoa — ganha as quatro aqui, então na manhã
   seguinte à atualização cada um abre exatamente as mesmas telas de antes.

2. **Os grupos antigos.** Os cinco perfis do começo (Gerência, Compras, Estoque,
   Operadores, Consulta e auditoria) viraram os de hoje em 07/10/2026 (migração 0003).
   Em 22/10/2026 a reinstalação por engano da 1.4.0 os recriou na loja, vazios, com as
   permissões daquela época — "Compras" e "Estoque" com o `ver_painel`, que abria tudo.
   Ninguém está neles, mas a 1.44.0 traz perfis novos chamados Compras, Estoque e
   Consulta e auditoria, e o perfil novo herdaria o grupo velho com tudo dentro. Então:
   esses três ficam sem permissão nenhuma (o `configurar_perfis` do instalador dá a eles
   o padrão novo logo depois), e Gerência e Operadores, que não voltam, são apagados se
   estiverem vazios. Se houver alguém num deles, a pessoa fica onde está e a auditoria
   registra, para a gerência resolver olhando a tela.

Tudo vai para a auditoria, assinado como a atualização.
"""

import uuid

from django.contrib.auth.management import create_permissions
from django.db import migrations

ANTIGA = ("importacao", "ver_painel")
NOVAS = (
    ("compras", "ver_compras"),
    ("importacao", "ver_vendas"),
    ("importacao", "ver_margem"),
    ("importacao", "ver_importacoes"),
)
# Grupos do começo com o mesmo nome de um perfil novo da 1.44.0: ficam sem permissão,
# e o configurar_perfis dá o padrão novo.
ZERAR = ("Compras", "Estoque", "Consulta e auditoria")
# Grupos do começo que não voltam: apagados, se vazios.
APAGAR = ("Gerência", "Operadores")
QUEM = "atualização 1.44.0"
_NAO_TINHA = object()


def _garantir_permissoes(apps):
    """As permissões novas ainda não existem no banco no meio do `migrate`: o Django só as
    cria no fim (post_migrate). Cria agora, do jeito que ele mesmo cria.

    O `create_permissions` pula app sem `models_module`, que no estado da migração nem
    existe; liga só durante a chamada e devolve o que estava (o teste chama com o registro
    de verdade, que não pode ficar sem ele)."""
    for app_config in apps.get_app_configs():
        original = getattr(app_config, "models_module", _NAO_TINHA)
        app_config.models_module = True
        try:
            create_permissions(app_config, apps=apps, verbosity=0)
        finally:
            if original is _NAO_TINHA:
                del app_config.models_module
            else:
                app_config.models_module = original


def _permissao(apps, app_label, codename):
    Permission = apps.get_model("auth", "Permission")
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


def _registrar(apps, acao, correlacao, depois):
    Evento = apps.get_model("auditoria", "EventoAuditoria")
    Evento.objects.create(usuario=None, usuario_rotulo=QUEM, acao=acao, resultado="sucesso",
                          correlacao=correlacao, depois=depois)


def dividir(apps, schema_editor):
    _garantir_permissoes(apps)
    Group = apps.get_model("auth", "Group")
    User = apps.get_model("auth", "User")
    antiga = _permissao(apps, *ANTIGA)
    novas = [_permissao(apps, *par) for par in NOVAS]
    correlacao = uuid.uuid4()

    grupos = list(Group.objects.filter(permissions=antiga).order_by("name"))
    for grupo in grupos:
        grupo.permissions.add(*novas)
    pessoas = list(User.objects.filter(user_permissions=antiga).order_by("username"))
    for pessoa in pessoas:
        pessoa.user_permissions.add(*novas)
    _registrar(apps, "permissao.ver_painel_dividido", correlacao, {
        "ganharam": [f"{app}.{codigo}" for app, codigo in NOVAS],
        "perfis": [grupo.name for grupo in grupos],
        "pessoas_com_permissao_individual": [pessoa.username for pessoa in pessoas],
    })

    zerados, apagados, com_gente = [], [], {}
    for nome in ZERAR:
        grupo = Group.objects.filter(name=nome).first()
        if grupo is None:
            continue
        antes = sorted(f"{p.content_type.app_label}.{p.codename}"
                       for p in grupo.permissions.select_related("content_type"))
        grupo.permissions.clear()
        zerados.append({"perfil": nome, "tinha": antes})
        gente = list(User.objects.filter(groups=grupo).values_list("username", flat=True))
        if gente:
            com_gente[nome] = sorted(gente)
    for nome in APAGAR:
        grupo = Group.objects.filter(name=nome).first()
        if grupo is None:
            continue
        gente = list(User.objects.filter(groups=grupo).values_list("username", flat=True))
        if gente:
            com_gente[nome] = sorted(gente)
            continue
        grupo.delete()
        apagados.append(nome)
    if zerados or apagados or com_gente:
        _registrar(apps, "permissao.grupos_antigos_limpos", correlacao, {
            "zerados": zerados, "apagados": apagados, "com_gente_dentro": com_gente,
        })


class Migration(migrations.Migration):
    dependencies = [
        ("contas", "0007_perfis_editaveis"),
        ("importacao", "0013_permissoes_divididas"),
        ("compras", "0006_permissao_ver_compras"),
        ("auditoria", "0002_gatilho_somente_inclusao"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]
    # Sem volta: tirar permissão de alguém é decisão de pessoa, não de migração.
    operations = [migrations.RunPython(dividir, migrations.RunPython.noop)]
