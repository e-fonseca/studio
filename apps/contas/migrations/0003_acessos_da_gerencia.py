"""Cria os acessos da gerência que o Edson nomeou em 07/10/2026.

Henriett e Moizes entram como administradores, junto com o Edson, que já tinha conta.
As contas nascem SEM SENHA de propósito: conta sem senha utilizável não entra no
sistema, então não existe senha provisória circulando por aí. Quem administra define a
senha de cada uma na tela de Usuários.

A migração não mexe em conta que já exista, e também não tira acesso de ninguém.
"""

from django.db import migrations

# (usuário de acesso, nome que aparece na tela)
ADMINISTRADORES = [
    ("edson", "Edson"),
    ("henriett", "Henriett"),
    ("moizes", "Moizes"),
]
PERFIL = "Administrador gerência"

# Os perfis antigos, de antes de 07/10/2026, e para onde vai quem estava neles. Sem isto
# quem já tinha conta ficaria num grupo que ninguém mais configura, com as permissões
# congeladas no que eram antes.
EQUIVALENCIA = {
    "Gerência": PERFIL,
    "Compras": "Operador administrativo",
    "Estoque": "Operador administrativo",
    "Consulta e auditoria": "Operador administrativo",
    "Operadores": "Operador vendedor",
}


def criar(apps, schema_editor):
    Usuario = apps.get_model("auth", "User")
    Group = apps.get_model("auth", "Group")
    grupo, _ = Group.objects.get_or_create(name=PERFIL)
    for apelido, nome in ADMINISTRADORES:
        usuario, criado = Usuario.objects.get_or_create(
            username=apelido,
            defaults={"first_name": nome, "is_active": True, "password": "!sem-senha-definida"},
        )
        if criado and not usuario.first_name:
            usuario.first_name = nome
            usuario.save(update_fields=["first_name"])
        usuario.groups.add(grupo)

    for antigo, novo in EQUIVALENCIA.items():
        grupo_antigo = Group.objects.filter(name=antigo).first()
        if grupo_antigo is None:
            continue
        grupo_novo, _ = Group.objects.get_or_create(name=novo)
        for usuario in Usuario.objects.filter(groups=grupo_antigo):
            usuario.groups.add(grupo_novo)
            usuario.groups.remove(grupo_antigo)
        grupo_antigo.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("contas", "0002_alter_vinculoidentidade_options"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]
    # Sem volta: tirar acesso de alguém é decisão de pessoa, não de migração.
    operations = [migrations.RunPython(criar, migrations.RunPython.noop)]
