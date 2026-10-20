from django.db import migrations


def noop_fix_uuid_columns(apps, schema_editor):
    """
    Historical no-op.

    The original migration used SQLite-specific DDL (`AUTOINCREMENT`) and
    dropped/recreated `plannings`, which is unsafe on PostgreSQL and would
    destroy data. The actual schema evolution is handled by later migrations.
    """


class Migration(migrations.Migration):

    dependencies = [
        ('planning', '0006_remove_planning_activiteid_remove_planning_employeid_and_more'),
    ]

    operations = [
        migrations.RunPython(noop_fix_uuid_columns, migrations.RunPython.noop),
    ]
