import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0017_merge_20260922_1925'),
        ('billing', '0072_pointeau_problematique_paiement'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ExplicationEcartIndemnitePoint',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('annee', models.PositiveIntegerField()),
                ('motif', models.CharField(choices=[('depasse', 'Depasse 10 000 Ar par forfaitaire'), ('sans_forfait', 'Aucun forfaitaire pointe')], max_length=20)),
                ('montant_paye', models.DecimalField(decimal_places=2, max_digits=14)),
                ('plafond', models.DecimalField(decimal_places=2, max_digits=14)),
                ('unites_forfait', models.PositiveIntegerField()),
                ('explication', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='explications_ecart_indemnite_point', to=settings.AUTH_USER_MODEL)),
                ('point_eau', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='explications_ecart_indemnite', to='billing.pointeau')),
            ],
            options={
                'verbose_name': "Explication d'ecart d'indemnite (point d'eau)",
                'verbose_name_plural': "Explications d'ecart d'indemnite (point d'eau)",
                'db_table': 'core_explication_ecart_indemnite_point',
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['point_eau', 'annee', '-created_at'], name='core_explic_point_e_ef4e97_idx')],
            },
        ),
    ]
