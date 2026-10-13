"""Candado a nivel de base de datos: la tabla de auditoría rechaza UPDATE y DELETE.

Es la última capa de defensa (las otras: AuditLog.save/delete, AuditQuerySet y el admin de solo
lectura). Aunque alguien ejecute SQL a mano o use `.raw()`, la base se niega.
Nota: no se bloquea TRUNCATE a propósito, para no romper `manage.py flush` ni TransactionTestCase.
"""

from django.db import migrations

TABLE = "audit_auditlog"
MESSAGE = "audit_auditlog es inmutable: no se permite modificar ni borrar registros"

POSTGRES_FORWARD = f"""
CREATE OR REPLACE FUNCTION audit_auditlog_block_changes() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION '{MESSAGE}';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_auditlog_immutable
    BEFORE UPDATE OR DELETE ON {TABLE}
    FOR EACH ROW EXECUTE FUNCTION audit_auditlog_block_changes();
"""

POSTGRES_REVERSE = f"""
DROP TRIGGER IF EXISTS audit_auditlog_immutable ON {TABLE};
DROP FUNCTION IF EXISTS audit_auditlog_block_changes();
"""

SQLITE_FORWARD = [
    f"CREATE TRIGGER audit_auditlog_no_update BEFORE UPDATE ON {TABLE} "
    f"BEGIN SELECT RAISE(ABORT, '{MESSAGE}'); END;",
    f"CREATE TRIGGER audit_auditlog_no_delete BEFORE DELETE ON {TABLE} "
    f"BEGIN SELECT RAISE(ABORT, '{MESSAGE}'); END;",
]

SQLITE_REVERSE = [
    "DROP TRIGGER IF EXISTS audit_auditlog_no_update;",
    "DROP TRIGGER IF EXISTS audit_auditlog_no_delete;",
]


def _run(schema_editor, postgres_sql, sqlite_statements):
    vendor = schema_editor.connection.vendor
    if vendor == "postgresql":
        schema_editor.execute(postgres_sql)
    elif vendor == "sqlite":
        for statement in sqlite_statements:
            schema_editor.execute(statement)
    # Otros motores: solo quedan las protecciones de la aplicación


def add_triggers(apps, schema_editor):
    _run(schema_editor, POSTGRES_FORWARD, SQLITE_FORWARD)


def remove_triggers(apps, schema_editor):
    _run(schema_editor, POSTGRES_REVERSE, SQLITE_REVERSE)


class Migration(migrations.Migration):

    dependencies = [("audit", "0001_initial")]

    operations = [migrations.RunPython(add_triggers, remove_triggers)]
