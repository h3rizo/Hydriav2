# Generated manually to fix updatedat column issue

from django.db import migrations


def drop_updatedat_column(apps, schema_editor):
    """
    Supprime la colonne 'updatedat' (sans underscore) qui est en conflit
    On garde 'updated_at' (avec underscore) qui est la colonne correcte
    """
    db_alias = schema_editor.connection.alias
    with schema_editor.connection.cursor() as cursor:
        # Vérifier si la colonne existe avant de la supprimer
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'plannings' AND column_name = 'updatedat'
        """)
        if cursor.fetchone():
            # Supprimer la colonne updatedat (l'ancienne)
            cursor.execute("ALTER TABLE plannings DROP COLUMN IF EXISTS updatedat")


class Migration(migrations.Migration):

    dependencies = [
        ('planning', '0041_remove_old_timestamp_fields'),
    ]

    operations = [
        migrations.RunPython(drop_updatedat_column, reverse_code=migrations.RunPython.noop),
    ]
