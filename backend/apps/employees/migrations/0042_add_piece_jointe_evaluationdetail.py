from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0041_add_new_conge_types'),
    ]

    operations = [
        migrations.AddField(
            model_name='evaluationdetail',
            name='piece_jointe',
            field=models.FileField(blank=True, null=True, upload_to='evaluations/pieces_jointes/', verbose_name='Piece jointe'),
        ),
    ]
