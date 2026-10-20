from django.db import migrations, models
import django.db.models.deletion
import uuid


def normalize_address(value):
    if value is None:
        return ''
    return ' '.join(str(value).split()).strip()


def forwards(apps, schema_editor):
    AdresseFournisseur = apps.get_model('billing', 'AdresseFournisseur')
    AdresseFournisseurDistrict = apps.get_model('billing', 'AdresseFournisseurDistrict')
    Fournisseur = apps.get_model('billing', 'Fournisseur')

    fournisseur_rows = list(Fournisseur.objects.all().only('id', 'adresse', 'adresse_fournisseur'))
    mapping_rows = list(
        AdresseFournisseurDistrict.objects.all().only('id', 'adresse', 'adresse_fournisseur')
    )

    normalized_values = set()
    for fournisseur in fournisseur_rows:
        normalized = normalize_address(fournisseur.adresse)
        if normalized:
            normalized_values.add(normalized)
    for mapping in mapping_rows:
        normalized = normalize_address(mapping.adresse)
        if normalized:
            normalized_values.add(normalized)

    existing_addresses = {
        obj.adresse: obj
        for obj in AdresseFournisseur.objects.filter(adresse__in=normalized_values)
    }
    missing_values = [
        AdresseFournisseur(adresse=value)
        for value in normalized_values
        if value not in existing_addresses
    ]
    if missing_values:
        AdresseFournisseur.objects.bulk_create(missing_values, batch_size=1000)
        existing_addresses = {
            obj.adresse: obj
            for obj in AdresseFournisseur.objects.filter(adresse__in=normalized_values)
        }

    fournisseurs_to_update = []
    for fournisseur in fournisseur_rows:
        normalized = normalize_address(fournisseur.adresse)
        adresse_obj = existing_addresses.get(normalized) if normalized else None
        changed = False
        new_adresse = normalized or None
        if fournisseur.adresse != new_adresse:
            fournisseur.adresse = new_adresse
            changed = True
        new_fk_id = adresse_obj.id if adresse_obj else None
        if getattr(fournisseur, 'adresse_fournisseur_id', None) != new_fk_id:
            fournisseur.adresse_fournisseur_id = new_fk_id
            changed = True
        if changed:
            fournisseurs_to_update.append(fournisseur)

    if fournisseurs_to_update:
        Fournisseur.objects.bulk_update(
            fournisseurs_to_update,
            ['adresse', 'adresse_fournisseur'],
            batch_size=1000,
        )

    mappings_to_update = []
    for mapping in mapping_rows:
        normalized = normalize_address(mapping.adresse)
        adresse_obj = existing_addresses.get(normalized) if normalized else None
        changed = False
        if mapping.adresse != normalized:
            mapping.adresse = normalized
            changed = True
        new_fk_id = adresse_obj.id if adresse_obj else None
        if getattr(mapping, 'adresse_fournisseur_id', None) != new_fk_id:
            mapping.adresse_fournisseur_id = new_fk_id
            changed = True
        if changed:
            mappings_to_update.append(mapping)

    if mappings_to_update:
        AdresseFournisseurDistrict.objects.bulk_update(
            mappings_to_update,
            ['adresse', 'adresse_fournisseur'],
            batch_size=1000,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0020_adresse_fournisseur_district'),
        ('billing', '0064_depenses_service_lignes'),
    ]

    operations = [
        migrations.CreateModel(
            name='AdresseFournisseur',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('adresse', models.TextField(unique=True, verbose_name='Adresse fournisseur')),
                ('actif', models.BooleanField(default=True, verbose_name='Active')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'adresses_fournisseurs',
                'verbose_name': 'Adresse fournisseur',
                'verbose_name_plural': 'Adresses fournisseurs',
                'ordering': ['adresse'],
            },
        ),
        migrations.AddField(
            model_name='adressefournisseurdistrict',
            name='adresse_fournisseur',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='mappings_districts', to='billing.adressefournisseur', verbose_name='Adresse fournisseur (relation)'),
        ),
        migrations.AddField(
            model_name='fournisseur',
            name='adresse_fournisseur',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='fournisseurs', to='billing.adressefournisseur', verbose_name='Adresse fournisseur'),
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
