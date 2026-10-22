"""No PostgreSQL, recusa UPDATE e DELETE na trilha de auditoria.

Proteção proporcional: impede alteração pelo fluxo comum e por engano. Um
administrador do banco consegue remover o gatilho; isso deve ficar restrito e
ser monitorado (ver docs/arquitetura.md).
"""

from django.db import migrations

CRIAR = """
CREATE OR REPLACE FUNCTION auditoria_recusar_alteracao() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'Eventos de auditoria não podem ser alterados nem apagados.';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER auditoria_somente_inclusao
BEFORE UPDATE OR DELETE ON auditoria_eventoauditoria
FOR EACH ROW EXECUTE FUNCTION auditoria_recusar_alteracao();

CREATE TRIGGER auditoria_sem_truncate
BEFORE TRUNCATE ON auditoria_eventoauditoria
FOR EACH STATEMENT EXECUTE FUNCTION auditoria_recusar_alteracao();
"""

REMOVER = """
DROP TRIGGER IF EXISTS auditoria_sem_truncate ON auditoria_eventoauditoria;
DROP TRIGGER IF EXISTS auditoria_somente_inclusao ON auditoria_eventoauditoria;
DROP FUNCTION IF EXISTS auditoria_recusar_alteracao();
"""


class Migration(migrations.Migration):
    dependencies = [("auditoria", "0001_initial")]

    operations = [migrations.RunSQL(CRIAR, REMOVER)]
