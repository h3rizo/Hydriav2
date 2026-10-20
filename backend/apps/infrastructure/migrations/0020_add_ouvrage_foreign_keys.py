# Generated manually to add foreign key constraints to organization ouvrages
from django.db import migrations


def add_foreign_keys(apps, schema_editor):
    """Add foreign key constraints only when the target tables/columns exist."""
    if schema_editor.connection.vendor != 'postgresql':
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'incidents'
                      AND column_name = 'ouvrage_id'
                ) AND NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'incidents_ouvrage_id_fk_ouvrages_id'
                ) THEN
                    ALTER TABLE incidents
                    ADD CONSTRAINT incidents_ouvrage_id_fk_ouvrages_id
                    FOREIGN KEY (ouvrage_id)
                    REFERENCES ouvrages(id)
                    ON DELETE CASCADE
                    DEFERRABLE INITIALLY DEFERRED;
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'maintenance_tasks'
                      AND column_name = 'ouvrage_id'
                ) AND NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'maintenance_tasks_ouvrage_id_fk_ouvrages_id'
                ) THEN
                    ALTER TABLE maintenance_tasks
                    ADD CONSTRAINT maintenance_tasks_ouvrage_id_fk_ouvrages_id
                    FOREIGN KEY (ouvrage_id)
                    REFERENCES ouvrages(id)
                    ON DELETE CASCADE
                    DEFERRABLE INITIALLY DEFERRED;
                END IF;
            END
            $$;
            """
        )


def remove_foreign_keys(apps, schema_editor):
    """Remove foreign key constraints."""
    if schema_editor.connection.vendor != 'postgresql':
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            ALTER TABLE incidents
            DROP CONSTRAINT IF EXISTS incidents_ouvrage_id_fk_ouvrages_id;
            """
        )
        cursor.execute(
            """
            ALTER TABLE maintenance_tasks
            DROP CONSTRAINT IF EXISTS maintenance_tasks_ouvrage_id_fk_ouvrages_id;
            """
        )


class Migration(migrations.Migration):

    dependencies = [
        ('infrastructure', '0019_remove_ouvrage_model'),
        ('organization', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(add_foreign_keys, remove_foreign_keys),
    ]
