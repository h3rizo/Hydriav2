# Generated migration to fix planning_id column type in planning_employees table

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('planning', '0044_remove_magasin_from_planningdetail'),
    ]

    operations = [
        # Convertir la colonne planning_id de integer en UUID
        migrations.RunSQL(
            sql="""
                -- Étape 1: Supprimer la contrainte de clé étrangère existante
                ALTER TABLE planning_employees
                DROP CONSTRAINT IF EXISTS planning_employees_planning_id_fkey;

                -- Étape 2: Ajouter une colonne temporaire UUID
                ALTER TABLE planning_employees
                ADD COLUMN planning_id_temp UUID;

                -- Étape 3: Copier les données en faisant la conversion
                -- (cela ne fonctionnera que si les IDs dans plannings sont déjà des UUIDs)
                UPDATE planning_employees pe
                SET planning_id_temp = p.id
                FROM plannings p
                WHERE pe.planning_id::text = p.id::text;

                -- Étape 4: Supprimer l'ancienne colonne
                ALTER TABLE planning_employees
                DROP COLUMN planning_id;

                -- Étape 5: Renommer la nouvelle colonne
                ALTER TABLE planning_employees
                RENAME COLUMN planning_id_temp TO planning_id;

                -- Étape 6: Rendre la colonne NOT NULL
                ALTER TABLE planning_employees
                ALTER COLUMN planning_id SET NOT NULL;

                -- Étape 7: Recréer la contrainte de clé étrangère
                ALTER TABLE planning_employees
                ADD CONSTRAINT planning_employees_planning_id_fkey
                FOREIGN KEY (planning_id) REFERENCES plannings(id) ON DELETE CASCADE;

                -- Étape 8: Recréer l'index
                CREATE INDEX planning_employees_planning_id_idx
                ON planning_employees(planning_id);
            """,
            reverse_sql="""
                -- Reverse migration (retour à integer)
                ALTER TABLE planning_employees DROP CONSTRAINT IF EXISTS planning_employees_planning_id_fkey;
                ALTER TABLE planning_employees ADD COLUMN planning_id_temp INTEGER;
                UPDATE planning_employees SET planning_id_temp = planning_id::text::integer;
                ALTER TABLE planning_employees DROP COLUMN planning_id;
                ALTER TABLE planning_employees RENAME COLUMN planning_id_temp TO planning_id;
                ALTER TABLE planning_employees ALTER COLUMN planning_id SET NOT NULL;
                ALTER TABLE planning_employees
                ADD CONSTRAINT planning_employees_planning_id_fkey
                FOREIGN KEY (planning_id) REFERENCES plannings(id) ON DELETE CASCADE;
            """
        ),
    ]
