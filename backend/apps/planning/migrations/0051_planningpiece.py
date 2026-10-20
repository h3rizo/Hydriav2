from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('planning', '0050_activiteposte_frequence_mode'),
        ('filemanager', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='PlanningPiece',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('fichier', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='planning_pieces', to='filemanager.fileupload')),
                ('planning', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='pieces', to='planning.planning')),
            ],
            options={
                'db_table': 'planning_pieces',
                'verbose_name': 'Pièce justificative',
                'verbose_name_plural': 'Pièces justificatives',
            },
        ),
    ]
