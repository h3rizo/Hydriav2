# Generated manually to remove infrastructure.Ouvrage model and rename field references
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('infrastructure', '0018_alter_cartesociale_ouvrage'),
        ('organization', '0001_initial'),
    ]

    operations = [
        # Step 1: Rename infrastructure field to ouvrage in state only (database already has ouvrage_id)
        migrations.SeparateDatabaseAndState(
            state_operations=[
                # Rename Incident.infrastructure to Incident.ouvrage
                migrations.RenameField(
                    model_name='incident',
                    old_name='infrastructure',
                    new_name='ouvrage',
                ),
                # Rename MaintenanceTask.infrastructure to MaintenanceTask.ouvrage
                migrations.RenameField(
                    model_name='maintenancetask',
                    old_name='infrastructure',
                    new_name='ouvrage',
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="""
                    DO $$
                    BEGIN
                        IF EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'incidents'
                              AND column_name = 'infrastructure_id'
                        ) AND NOT EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'incidents'
                              AND column_name = 'ouvrage_id'
                        ) THEN
                            ALTER TABLE incidents RENAME COLUMN infrastructure_id TO ouvrage_id;
                        END IF;

                        IF EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'maintenance_tasks'
                              AND column_name = 'infrastructure_id'
                        ) AND NOT EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'maintenance_tasks'
                              AND column_name = 'ouvrage_id'
                        ) THEN
                            ALTER TABLE maintenance_tasks RENAME COLUMN infrastructure_id TO ouvrage_id;
                        END IF;
                    END
                    $$;
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),

        # Step 2: Update the foreign key target from infrastructure.Ouvrage to organization.Ouvrage
        migrations.SeparateDatabaseAndState(
            state_operations=[
                # Update Incident.ouvrage to point to organization.Ouvrage
                migrations.AlterField(
                    model_name='incident',
                    name='ouvrage',
                    field=models.ForeignKey(
                        on_delete=models.CASCADE,
                        related_name='incidents',
                        to='organization.ouvrage'
                    ),
                ),
                # Update MaintenanceTask.ouvrage to point to organization.Ouvrage
                migrations.AlterField(
                    model_name='maintenancetask',
                    name='ouvrage',
                    field=models.ForeignKey(
                        on_delete=models.CASCADE,
                        related_name='maintenance_tasks',
                        to='organization.ouvrage'
                    ),
                ),
            ],
            database_operations=[
                # Database foreign keys will be added separately
            ],
        ),

        # Step 3: Remove the Ouvrage model from state
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(
                    name='Ouvrage',
                ),
            ],
            database_operations=[
                # No database operations - table ouvrages_infrastructure already gone
            ],
        ),
    ]
