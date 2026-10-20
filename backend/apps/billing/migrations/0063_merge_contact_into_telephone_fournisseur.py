from django.db import migrations


def copy_contact_to_telephone(apps, schema_editor):
    Fournisseur = apps.get_model('billing', 'Fournisseur')

    for fournisseur in Fournisseur.objects.all().iterator():
        telephone = (fournisseur.telephone or '').strip()
        # Historical field still exists at this migration step.
        contact = (getattr(fournisseur, 'contact_fournisseur', None) or '').strip()

        if not telephone and contact:
            fournisseur.telephone = contact
            fournisseur.save(update_fields=['telephone'])


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0062_relevecompteurtete'),
    ]

    operations = [
        migrations.RunPython(copy_contact_to_telephone, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='fournisseur',
            name='contact_fournisseur',
        ),
    ]
