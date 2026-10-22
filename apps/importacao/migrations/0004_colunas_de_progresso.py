"""Acerta as colunas de progresso em bancos criados antes delas existirem.

As colunas etapa e progresso foram acrescentadas ao 0001_initial depois que ele
já tinha rodado no servidor da loja. O Django guarda a migração pelo nome, então
ele a considerava aplicada e nunca criava as duas colunas: a tela de importações
e o painel quebravam com 'column "etapa" does not exist'.

Esta migração cria as colunas se faltarem e não faz nada em banco novo, onde o
0001 já as criou. O estado do Django não muda (state_operations vazio), porque
para ele os campos sempre existiram.
"""

from django.db import migrations

CRIAR = """
ALTER TABLE importacao_importacao ADD COLUMN IF NOT EXISTS etapa varchar(60) NOT NULL DEFAULT '';
ALTER TABLE importacao_importacao ALTER COLUMN etapa DROP DEFAULT;
ALTER TABLE importacao_importacao ADD COLUMN IF NOT EXISTS progresso smallint NOT NULL DEFAULT 0;
ALTER TABLE importacao_importacao ALTER COLUMN progresso DROP DEFAULT;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("importacao", "0003_pedido_em_aberto"),
    ]

    operations = [
        migrations.RunSQL(CRIAR, migrations.RunSQL.noop, state_operations=[]),
    ]
