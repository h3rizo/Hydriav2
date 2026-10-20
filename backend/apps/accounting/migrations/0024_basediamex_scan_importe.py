from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0023_saisiecomptable'),
    ]

    operations = [
        migrations.AddField(
            model_name='basediamex',
            name='scan_importe',
            field=models.FileField(
                blank=True,
                help_text='Copie serveur du scan pour consultation web/mobile',
                max_length=500,
                null=True,
                upload_to='diamex_scans/',
                verbose_name='Scan importé',
            ),
        ),
    ]
