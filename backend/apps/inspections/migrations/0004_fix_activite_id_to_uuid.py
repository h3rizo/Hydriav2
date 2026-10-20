# Generated manually for converting activite_id from IntegerField to UUIDField

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('inspections', '0003_pointcontroleactivitecorrectible'),
    ]

    operations = [
        # Étape 1: Supprimer la colonne activite_id de ResultatControle
        migrations.RunSQL(
            "ALTER TABLE resultats_controle DROP COLUMN IF EXISTS activite_id;",
            reverse_sql="ALTER TABLE resultats_controle ADD COLUMN activite_id INTEGER NULL;"
        ),

        # Étape 2: Supprimer la colonne activite_id de PointControleActiviteCorrectible
        migrations.RunSQL(
            "ALTER TABLE point_controle_activites_correctives DROP COLUMN IF EXISTS activite_id;",
            reverse_sql="ALTER TABLE point_controle_activites_correctives ADD COLUMN activite_id INTEGER NOT NULL;"
        ),

        # Étape 3: Recréer la colonne activite_id comme UUIDField dans ResultatControle
        migrations.RunSQL(
            "ALTER TABLE resultats_controle ADD COLUMN activite_id UUID NULL;",
            reverse_sql="ALTER TABLE resultats_controle DROP COLUMN activite_id;"
        ),

        # Étape 4: Recréer la colonne activite_id comme UUIDField dans PointControleActiviteCorrectible
        migrations.RunSQL(
            "ALTER TABLE point_controle_activites_correctives ADD COLUMN activite_id UUID NOT NULL;",
            reverse_sql="ALTER TABLE point_controle_activites_correctives DROP COLUMN activite_id;"
        ),
    ]