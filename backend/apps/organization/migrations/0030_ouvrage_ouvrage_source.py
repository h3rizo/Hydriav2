from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('organization', '0029_base_telephone'),
    ]

    operations = [
        migrations.AddField(
            model_name='ouvrage',
            name='ouvrage_source',
            field=models.ForeignKey(
                blank=True,
                help_text="Ouvrage AEPG dont la source est partagee avec cet ouvrage extension.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='ouvrages_extensions',
                to='organization.ouvrage',
                verbose_name='Ouvrage AEPG source',
            ),
        ),
    ]
