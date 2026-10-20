from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recrutement', '0004_add_candidat_profile_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='candidat',
            name='base',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='Base'),
        ),
    ]
