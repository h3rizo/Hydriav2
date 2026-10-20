from django.core.validators import FileExtensionValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '1015_utilisationcarburantvehicule_base_diamex_entry'),
    ]

    operations = [
        migrations.AddField(
            model_name='stock',
            name='etat',
            field=models.CharField(
                choices=[('bon', 'Bon'), ('moyen', 'Moyen'), ('mauvais', 'Mauvais'), ('hs', 'HS')],
                default='bon',
                max_length=20,
                verbose_name='État',
            ),
        ),
        migrations.AddField(
            model_name='stock',
            name='photo',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to='stocks/photos/%Y/%m/',
                validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'webp'])],
                verbose_name='Photo du stock',
            ),
        ),
    ]
