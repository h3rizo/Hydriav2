from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("geography", "0013_photos_entites_geographiques"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE regions ADD COLUMN IF NOT EXISTS photo text;
                ALTER TABLE districts ADD COLUMN IF NOT EXISTS photo text;
                ALTER TABLE communes ADD COLUMN IF NOT EXISTS photo text;
                ALTER TABLE fokontanys ADD COLUMN IF NOT EXISTS photo text;
                ALTER TABLE villages ADD COLUMN IF NOT EXISTS photo text;
                ALTER TABLE parcelles ADD COLUMN IF NOT EXISTS photo text;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
