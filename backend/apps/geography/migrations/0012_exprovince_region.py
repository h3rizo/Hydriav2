from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('geography', '0011_liaisonvillage_distance_km_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExProvince',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('nom_ex_province', models.CharField(max_length=255, unique=True, verbose_name="Nom de l'ex-province")),
            ],
            options={
                'verbose_name': 'Ex-province',
                'verbose_name_plural': 'Ex-provinces',
                'db_table': 'ex_provinces',
                'ordering': ['nom_ex_province'],
            },
        ),
        migrations.AddField(
            model_name='region',
            name='ex_province',
            field=models.ForeignKey(blank=True, db_column='ex_province_id', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='regions', to='geography.exprovince', verbose_name='Ex-province'),
        ),
    ]
