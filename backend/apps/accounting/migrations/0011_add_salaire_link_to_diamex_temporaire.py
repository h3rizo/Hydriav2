# Generated manually

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0010_add_purchase_to_diamex_temporaire'),
        ('employees', '0020_add_prorata_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='diamextemporaire',
            name='salaire',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='transactions_temporaires',
                to='employees.salaire',
                verbose_name='Salaire source'
            ),
        ),
    ]
