from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('usagers', '0008_merge_20260417_2332'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReseauParticipantUnavailability',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('start_at', models.DateTimeField(verbose_name='Debut indisponibilite')),
                ('end_at', models.DateTimeField(verbose_name='Fin indisponibilite')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('participant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='unavailabilities', to='usagers.reseauparticipant', verbose_name='Participant')),
            ],
            options={
                'verbose_name': 'Indisponibilite participant reseau',
                'verbose_name_plural': 'Indisponibilites participants reseau',
                'db_table': 'reseau_participant_unavailabilities',
                'ordering': ['start_at'],
            },
        ),
    ]
