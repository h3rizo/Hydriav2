import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0037_saisiecomptablearticle'),
        ('employees', '0086_contrat_quotite_temps_travail'),
    ]

    operations = [
        migrations.CreateModel(
            name='LivraisonArticle',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('quantite', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Quantite livree')),
                ('date_livraison', models.DateField(verbose_name='Date de livraison')),
                ('remarque', models.CharField(blank=True, default='', max_length=255)),
                ('fiche_stock_id', models.CharField(blank=True, default='', max_length=50)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('annulee', models.BooleanField(default=False)),
                ('annulee_at', models.DateTimeField(blank=True, null=True)),
                ('annulee_par', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='livraisons_articles_saisie_annulees', to='employees.employe')),
                ('article', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='livraisons', to='accounting.saisiecomptablearticle', verbose_name='Article')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='livraisons_articles_saisie', to='employees.employe')),
            ],
            options={
                'verbose_name': 'Livraison de reste a livrer',
                'verbose_name_plural': 'Livraisons de restes a livrer',
                'db_table': 'saisie_comptable_livraisons',
                'ordering': ['date_livraison', 'created_at'],
                'indexes': [models.Index(fields=['article', 'annulee'], name='saisie_comp_article_5058a1_idx')],
            },
        ),
    ]
