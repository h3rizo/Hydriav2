from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0071_fournisseurduplicatesuggestionignore'),
    ]

    operations = [
        migrations.AddField(
            model_name='pointeau',
            name='problematique_commentaire',
            field=models.TextField(blank=True, null=True, verbose_name='Problématique commentaire'),
        ),
        migrations.AddField(
            model_name='pointeau',
            name='problematique_paiement',
            field=models.IntegerField(
                choices=[(0, '0'), (1, '1'), (2, '2'), (3, '3'), (4, '4'), (5, '5')],
                default=0,
                help_text="0: pas de problème, 1: attente avant paiement, 2: certains usagers ne paient pas, 3: coupure avant paiement, 4: coupure longue avant paiement, 5: usagers ne paient pas et coupure impossible",
                verbose_name='Problématique paiement',
            ),
        ),
    ]
