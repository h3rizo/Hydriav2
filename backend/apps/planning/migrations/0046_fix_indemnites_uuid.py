# Generated migration to fix planning_id column type in indemnites table

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('planning', '0045_fix_planning_employees_uuid'),
    ]

    operations = [
        # Convertir la colonne planning_id de integer en UUID
        migrations.RunSQL(
            sql="""
                -- Étape 1: Supprimer la contrainte de clé étrangère existante
                ALTER TABLE indemnites
                DROP CONSTRAINT IF EXISTS indemnites_planning_id_fkey;

                -- Étape 2: Ajouter une colonne temporaire UUID
                ALTER TABLE indemnites
                ADD COLUMN planning_id_temp UUID;

                -- Étape 3: Copier les données en faisant la conversion
                UPDATE indemnites ind
                SET planning_id_temp = p.id
                FROM plannings p
                WHERE ind.planning_id IS NOT NULL
                  AND ind.planning_id::text = p.id::text;

                -- Étape 4: Supprimer l'ancienne colonne
                ALTER TABLE indemnites
                DROP COLUMN planning_id;

                -- Étape 5: Renommer la nouvelle colonne
                ALTER TABLE indemnites
                RENAME COLUMN planning_id_temp TO planning_id;

                -- Étape 6: Recréer la contrainte de clé étrangère (NULL autorisé)
                ALTER TABLE indemnites
                ADD CONSTRAINT indemnites_planning_id_fkey
                FOREIGN KEY (planning_id) REFERENCES plannings(id) ON DELETE SET NULL;

                -- Étape 7: Recréer l'index
                CREATE INDEX indemnites_planning_id_idx
                ON indemnites(planning_id);
            """,
            reverse_sql="""
                -- Reverse migration (retour à integer)
                ALTER TABLE indemnites DROP CONSTRAINT IF EXISTS indemnites_planning_id_fkey;
                ALTER TABLE indemnites ADD COLUMN planning_id_temp INTEGER;
                UPDATE indemnites SET planning_id_temp = planning_id::text::integer WHERE planning_id IS NOT NULL;
                ALTER TABLE indemnites DROP COLUMN planning_id;
                ALTER TABLE indemnites RENAME COLUMN planning_id_temp TO planning_id;
                ALTER TABLE indemnites
                ADD CONSTRAINT indemnites_planning_id_fkey
                FOREIGN KEY (planning_id) REFERENCES plannings(id) ON DELETE SET NULL;
            """
        ),
    ]
