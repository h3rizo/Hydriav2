from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0050_ficheposte_preuve_type_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='configsalaire',
            name='indemnite_hors_zone',
            field=models.DecimalField(decimal_places=2, default=0, help_text="Montant de l'indemnit? hors zone", max_digits=12, verbose_name='Indemnit? hors zone (Ar)'),
        ),
        migrations.AddField(
            model_name='configsalaire',
            name='indemnite_terrain',
            field=models.DecimalField(decimal_places=2, default=0, help_text="Montant de l'indemnit? terrain", max_digits=12, verbose_name='Indemnit? terrain (Ar)'),
        ),
        migrations.AddField(
            model_name='configsalaire',
            name='indemnite_herizo',
            field=models.DecimalField(decimal_places=2, default=0, help_text="Montant de l'indemnit? Herizo", max_digits=12, verbose_name='Indemnit? Herizo (Ar)'),
        ),
    ]
