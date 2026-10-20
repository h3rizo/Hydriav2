import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.core.validators


INITIAL_TYPES = (
    ('pont', 'Pont'), ('sentier', 'Sentier'), ('intersection', 'Intersection'),
    ('rond_point', 'Rond-point'), ('batiment', 'Bâtiment'), ('ecole', 'École'),
    ('sante', 'Centre de santé'), ('riviere', 'Rivière'),
    ('passage_difficile', 'Passage difficile'), ('depart', 'Point de départ'), ('autre', 'Autre'),
)


def seed_types(apps, schema_editor):
    TypeRepere = apps.get_model('navigation_terrain', 'TypeRepere')
    for order, (icon, name) in enumerate(INITIAL_TYPES):
        TypeRepere.objects.get_or_create(nom=name, defaults={
            'icone': icon, 'couleur': '#58D594', 'ordre_affichage': order, 'actif': True,
        })


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('geography', '0014_repair_missing_photo_columns'),
        ('organization', '0035_compte_financement'),
    ]
    operations = [
        migrations.CreateModel(name='TypeRepere', fields=[
            ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ('nom', models.CharField(max_length=120, unique=True)), ('description', models.TextField(blank=True)),
            ('icone', models.CharField(default='autre', max_length=50)),
            ('couleur', models.CharField(default='#58D594', max_length=7, validators=[django.core.validators.RegexValidator('^#[0-9A-Fa-f]{6}$', 'Couleur hexadécimale invalide.')])),
            ('ordre_affichage', models.PositiveIntegerField(default=0)), ('actif', models.BooleanField(default=True)),
            ('created_at', models.DateTimeField(auto_now_add=True)), ('updated_at', models.DateTimeField(auto_now=True)),
        ], options={'db_table': 'navigation_types_reperes', 'ordering': ('ordre_affichage', 'nom')}),
        migrations.CreateModel(name='Repere', fields=[
            ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ('nom', models.CharField(max_length=255)), ('latitude', models.DecimalField(decimal_places=7, max_digits=10)),
            ('longitude', models.DecimalField(decimal_places=7, max_digits=10)),
            ('altitude', models.DecimalField(blank=True, decimal_places=2, max_digits=9, null=True)),
            ('accuracy_m', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
            ('remarques', models.TextField(blank=True)), ('capture_method', models.CharField(choices=[('gps', 'GPS'), ('carte', 'Carte')], max_length=10)),
            ('captured_at', models.DateTimeField()), ('version', models.PositiveIntegerField(default=1)),
            ('archived_at', models.DateTimeField(blank=True, null=True)), ('created_at', models.DateTimeField(auto_now_add=True)),
            ('updated_at', models.DateTimeField(auto_now=True)),
            ('createur', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='reperes_terrain', to=settings.AUTH_USER_MODEL)),
            ('organisation', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reperes_terrain', to='organization.organisation')),
            ('ouvrage', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reperes_terrain', to='organization.ouvrage')),
            ('type_repere', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='reperes', to='navigation_terrain.typerepere')),
            ('village', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reperes_terrain', to='geography.village')),
        ], options={'db_table': 'navigation_reperes'}),
        migrations.CreateModel(name='ReperePhoto', fields=[
            ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ('local_uuid', models.UUIDField(unique=True)), ('fichier', models.FileField(upload_to='navigation-terrain/reperes/')),
            ('nom', models.CharField(max_length=180)), ('mime_type', models.CharField(max_length=80)),
            ('taille', models.PositiveIntegerField()), ('sha256', models.CharField(max_length=64)),
            ('ordre', models.PositiveIntegerField(default=0)), ('legende', models.CharField(blank=True, max_length=255)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('createur', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='photos_reperes_terrain', to=settings.AUTH_USER_MODEL)),
            ('repere', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='photos', to='navigation_terrain.repere')),
        ], options={'db_table': 'navigation_reperes_photos', 'ordering': ('ordre', 'created_at')}),
        migrations.CreateModel(name='GeoPositionAudit', fields=[
            ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ('local_uuid', models.UUIDField(unique=True)), ('entity_kind', models.CharField(choices=[('village', 'Village'), ('water_point', "Point d'eau"), ('equipment', 'Équipement'), ('landmark', 'Repère')], max_length=20)),
            ('entity_uuid', models.UUIDField(db_index=True)),
            ('old_latitude', models.DecimalField(blank=True, decimal_places=8, max_digits=11, null=True)),
            ('old_longitude', models.DecimalField(blank=True, decimal_places=8, max_digits=11, null=True)),
            ('new_latitude', models.DecimalField(decimal_places=8, max_digits=11)), ('new_longitude', models.DecimalField(decimal_places=8, max_digits=11)),
            ('old_altitude', models.DecimalField(blank=True, decimal_places=2, max_digits=9, null=True)),
            ('new_altitude', models.DecimalField(blank=True, decimal_places=2, max_digits=9, null=True)),
            ('accuracy_m', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
            ('capture_method', models.CharField(choices=[('gps', 'GPS'), ('carte', 'Carte')], max_length=10)), ('captured_at', models.DateTimeField()),
            ('received_at', models.DateTimeField(auto_now_add=True)), ('appareil', models.CharField(blank=True, max_length=160)),
            ('motif', models.CharField(blank=True, max_length=255)), ('technical_data', models.JSONField(blank=True, default=dict)),
            ('utilisateur', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='audits_positions_terrain', to=settings.AUTH_USER_MODEL)),
        ], options={'db_table': 'navigation_geo_position_audits'}),
        migrations.AddIndex(model_name='repere', index=models.Index(fields=['ouvrage', 'archived_at'], name='nav_rep_ouv_arch')),
        migrations.AddIndex(model_name='repere', index=models.Index(fields=['organisation', 'updated_at'], name='nav_rep_org_upd')),
        migrations.AddIndex(model_name='geopositionaudit', index=models.Index(fields=['entity_kind', 'entity_uuid', '-received_at'], name='nav_audit_entity')),
        migrations.RunPython(seed_types, migrations.RunPython.noop),
    ]
