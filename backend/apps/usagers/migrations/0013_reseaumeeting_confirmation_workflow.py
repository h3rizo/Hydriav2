from django.db import migrations, models
import django.db.models.deletion
import uuid


def seed_existing_meeting_confirmations(apps, schema_editor):
    ReseauMeeting = apps.get_model('usagers', 'ReseauMeeting')
    ReseauMeetingConfirmation = apps.get_model('usagers', 'ReseauMeetingConfirmation')

    for meeting in ReseauMeeting.objects.all().iterator():
        participant_ids = list(meeting.participants.values_list('id', flat=True))
        confirmations = [
            ReseauMeetingConfirmation(
                id=uuid.uuid4(),
                meeting_id=meeting.id,
                participant_id=participant_id,
                confirmed_at=meeting.created_at,
            )
            for participant_id in participant_ids
        ]
        if confirmations:
            ReseauMeetingConfirmation.objects.bulk_create(confirmations, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        ('usagers', '0012_reseaumeeting_completed_at_reseaumeeting_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='reseaumeeting',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='meetings_created', to='usagers.reseauparticipant', verbose_name='Propose par'),
        ),
        migrations.AlterField(
            model_name='reseaumeeting',
            name='status',
            field=models.CharField(choices=[('proposed', 'Propose'), ('planned', 'Planifie'), ('completed', 'Termine')], default='proposed', max_length=20, verbose_name='Statut'),
        ),
        migrations.CreateModel(
            name='ReseauMeetingConfirmation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('confirmed_at', models.DateTimeField(blank=True, null=True, verbose_name='Confirme le')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('meeting', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='confirmations', to='usagers.reseaumeeting', verbose_name='Rendez-vous')),
                ('participant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='meeting_confirmations', to='usagers.reseauparticipant', verbose_name='Participant')),
            ],
            options={
                'verbose_name': 'Confirmation rendez-vous reseau',
                'verbose_name_plural': 'Confirmations rendez-vous reseau',
                'db_table': 'reseau_meeting_confirmations',
            },
        ),
        migrations.AddConstraint(
            model_name='reseaumeetingconfirmation',
            constraint=models.UniqueConstraint(fields=('meeting', 'participant'), name='uniq_reseau_meeting_confirmation_participant'),
        ),
        migrations.RunPython(seed_existing_meeting_confirmations, migrations.RunPython.noop),
    ]
