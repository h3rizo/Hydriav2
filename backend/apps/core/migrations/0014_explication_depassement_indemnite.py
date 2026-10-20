import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0013_mobile_token_expiry_refresh'),
        ('organization', '0037_compte_compte_ouvrage_analyse'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ExplicationDepassementIndemnite',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('annee', models.PositiveIntegerField()),
                ('montant_paye', models.DecimalField(decimal_places=2, max_digits=14)),
                ('plafond', models.DecimalField(decimal_places=2, max_digits=14)),
                ('nb_points_publics', models.PositiveIntegerField()),
                ('explication', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='explications_depassement_indemnite', to=settings.AUTH_USER_MODEL)),
                ('ouvrage', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='explications_depassement_indemnite', to='organization.ouvrage')),
            ],
            options={
                'verbose_name': "Explication de depassement d'indemnite",
                'verbose_name_plural': "Explications de depassement d'indemnite",
                'db_table': 'core_explication_depassement_indemnite',
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['ouvrage', 'annee', '-created_at'], name='core_explic_ouvrage_3dd7a3_idx')],
            },
        ),
    ]
