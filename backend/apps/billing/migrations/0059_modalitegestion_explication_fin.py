from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0058_depenses_services'),
    ]

    operations = [
        migrations.AddField(
            model_name='modalitegestion',
            name='explication_fin',
            field=models.TextField(blank=True, null=True, verbose_name='Explication de fin'),
        ),
    ]
