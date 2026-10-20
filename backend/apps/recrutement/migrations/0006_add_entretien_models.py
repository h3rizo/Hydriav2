from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0001_initial'),
        ('recrutement', '0005_add_candidat_base'),
    ]

    operations = [
        migrations.CreateModel(
            name='Entretien',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('date_entretien', models.DateField(blank=True, null=True, verbose_name="Date d'entretien")),
                ('decision', models.CharField(blank=True, choices=[('retenu', 'Retenu'), ('rejete', 'Rejete'), ('autre', 'Autre')], default='', max_length=20, verbose_name='Decision finale')),
                ('notes_generales', models.TextField(blank=True, default='', verbose_name='Notes generales')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('candidat', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='entretien', to='recrutement.candidat', verbose_name='Candidat')),
                ('poste', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='employees.poste', verbose_name='Poste')),
            ],
            options={
                'verbose_name': 'Entretien',
                'verbose_name_plural': 'Entretiens',
                'db_table': 'entretiens',
            },
        ),
        migrations.CreateModel(
            name='EntretienQuestion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('texte_question', models.TextField(verbose_name="Question d'entretien")),
                ('ordre', models.IntegerField(default=0, verbose_name='Ordre')),
                ('active', models.BooleanField(default=True, verbose_name='Active')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('poste', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='questions_entretien', to='employees.poste', verbose_name='Poste')),
            ],
            options={
                'verbose_name': "Question d'entretien",
                'verbose_name_plural': "Questions d'entretien",
                'db_table': 'questions_entretien',
                'ordering': ['poste', 'ordre'],
            },
        ),
        migrations.CreateModel(
            name='EntretienReponse',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('reponse_candidat', models.TextField(blank=True, default='', verbose_name='Reponse du candidat')),
                ('remarque', models.TextField(blank=True, default='', verbose_name='Remarque')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('entretien', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reponses', to='recrutement.entretien', verbose_name='Entretien')),
                ('question', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reponses', to='recrutement.entretienquestion', verbose_name='Question')),
            ],
            options={
                'verbose_name': "Reponse d'entretien",
                'verbose_name_plural': "Reponses d'entretien",
                'db_table': 'entretiens_reponses',
                'unique_together': {('entretien', 'question')},
            },
        ),
    ]
