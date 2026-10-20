from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0083_fichposte_regles_cible_composants'),
    ]

    operations = [
        migrations.AddField(
            model_name='ficheposte',
            name='composants_admis',
            field=models.TextField(blank=True, default='', help_text='Un nom de composant par ligne (accents et majuscules ignorés). Vide : tous les composants du type de la cible. Ex. « Anti-rouille » : Boîte métallique, Fer plat, Cadenas vita gasy.', verbose_name='Composants admis'),
        ),
    ]
