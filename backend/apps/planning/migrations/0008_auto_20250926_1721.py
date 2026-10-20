from django.db import migrations


def noop_fix_table_references(apps, schema_editor):
    """
    Historical no-op.

    The original migration dropped and recreated `plannings` with SQLite-only
    SQL and obsolete foreign-key targets. That behavior is incompatible with
    PostgreSQL and unsafe for existing data.
    """


class Migration(migrations.Migration):

    dependencies = [
        ('planning', '0007_auto_20250926_1720'),
    ]

    operations = [
        migrations.RunPython(noop_fix_table_references, migrations.RunPython.noop),
    ]
