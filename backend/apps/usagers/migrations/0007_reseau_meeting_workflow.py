from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('usagers', '0006_representantusager_dates'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReseauAvailabilitySlot',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('start_at', models.DateTimeField(verbose_name='Debut')),
                ('end_at', models.DateTimeField(verbose_name='Fin')),
                ('is_active', models.BooleanField(default=True, verbose_name='Actif')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Creneau reseau',
                'verbose_name_plural': 'Creneaux reseau',
                'db_table': 'reseau_availability_slots',
                'ordering': ['start_at'],
            },
        ),
        migrations.CreateModel(
            name='ReseauMeetingSession',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('titre', models.CharField(max_length=255, verbose_name='Titre')),
                ('slug', models.SlugField(max_length=120, unique=True, verbose_name='Slug')),
                ('description', models.TextField(blank=True, null=True, verbose_name='Description')),
                ('lieu', models.CharField(blank=True, max_length=255, null=True, verbose_name='Lieu')),
                ('duree_minutes', models.PositiveIntegerField(default=60, verbose_name='Duree (minutes)')),
                ('fuseau_horaire', models.CharField(default='Indian/Antananarivo', max_length=64, verbose_name='Fuseau horaire')),
                ('seuil_confirmation', models.PositiveIntegerField(default=2, verbose_name='Seuil minimum')),
                ('statut', models.CharField(choices=[('draft', 'Brouillon'), ('open', 'Ouverte'), ('confirmed', 'Confirmee'), ('closed', 'Cloturee')], default='draft', max_length=16, verbose_name='Statut')),
                ('date_debut', models.DateField(blank=True, null=True, verbose_name='Date debut')),
                ('date_fin', models.DateField(blank=True, null=True, verbose_name='Date fin')),
                ('confirmation_envoyee_at', models.DateTimeField(blank=True, null=True, verbose_name='Confirmation envoyee le')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Session reseau',
                'verbose_name_plural': 'Sessions reseau',
                'db_table': 'reseau_meeting_sessions',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddField(
            model_name='reseauavailabilityslot',
            name='session',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='slots', to='usagers.reseaumeetingsession', verbose_name='Session'),
        ),
        migrations.CreateModel(
            name='ReseauParticipant',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('nom', models.CharField(max_length=255, verbose_name='Nom')),
                ('email', models.EmailField(max_length=254, verbose_name='Email')),
                ('google_calendar_email', models.EmailField(blank=True, max_length=254, null=True, verbose_name='Email Google Agenda')),
                ('actif', models.BooleanField(default=True, verbose_name='Actif')),
                ('last_login_at', models.DateTimeField(blank=True, null=True, verbose_name='Dernier acces')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='participants', to='usagers.reseaumeetingsession', verbose_name='Session')),
            ],
            options={
                'verbose_name': 'Participant reseau',
                'verbose_name_plural': 'Participants reseau',
                'db_table': 'reseau_participants',
                'ordering': ['nom', 'email'],
            },
        ),
        migrations.CreateModel(
            name='ReseauMagicLink',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('token', models.CharField(max_length=64, unique=True, verbose_name='Token')),
                ('expires_at', models.DateTimeField(verbose_name='Expire le')),
                ('used_at', models.DateTimeField(blank=True, null=True, verbose_name='Utilise le')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('participant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='magic_links', to='usagers.reseauparticipant', verbose_name='Participant')),
            ],
            options={
                'verbose_name': 'Lien magique reseau',
                'verbose_name_plural': 'Liens magiques reseau',
                'db_table': 'reseau_magic_links',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='ReseauParticipantAvailability',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('participant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='availabilities', to='usagers.reseauparticipant', verbose_name='Participant')),
                ('slot', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='participant_availabilities', to='usagers.reseauavailabilityslot', verbose_name='Creneau')),
            ],
            options={
                'verbose_name': 'Disponibilite participant reseau',
                'verbose_name_plural': 'Disponibilites participants reseau',
                'db_table': 'reseau_participant_availabilities',
            },
        ),
        migrations.AddField(
            model_name='reseaumeetingsession',
            name='confirmed_slot',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='confirmed_for_sessions', to='usagers.reseauavailabilityslot', verbose_name='Creneau confirme'),
        ),
        migrations.AddConstraint(
            model_name='reseauavailabilityslot',
            constraint=models.UniqueConstraint(fields=('session', 'start_at', 'end_at'), name='uniq_reseau_slot_session_start_end'),
        ),
        migrations.AddConstraint(
            model_name='reseauparticipant',
            constraint=models.UniqueConstraint(fields=('session', 'email'), name='uniq_reseau_participant_session_email'),
        ),
        migrations.AddConstraint(
            model_name='reseauparticipantavailability',
            constraint=models.UniqueConstraint(fields=('participant', 'slot'), name='uniq_reseau_participant_slot'),
        ),
    ]
