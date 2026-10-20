from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0069_alter_fournisseurfusioninstruction_links'),
    ]

    operations = [
        migrations.AddField(
            model_name='fournisseurfusioninstruction',
            name='lignes_diamex_details',
            field=models.JSONField(blank=True, default=list, verbose_name='Details lignes DiameX'),
        ),
    ]
