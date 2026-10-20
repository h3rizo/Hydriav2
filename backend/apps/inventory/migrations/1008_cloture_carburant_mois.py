from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '1007_utilisations_carburant_perso'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ClotureCarburantMois',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('mois', models.IntegerField()),
                ('annee', models.IntegerField()),
                ('override_directeur', models.BooleanField(default=False)),
                ('commentaire', models.TextField(blank=True, null=True)),
                ('date_cloture', models.DateTimeField(auto_now_add=True)),
                ('cloture_par', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='clotures_carburant_mensuelles', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'clotures_carburant_mensuelles',
                'ordering': ['-annee', '-mois'],
                'unique_together': {('mois', 'annee')},
            },
        ),
    ]
