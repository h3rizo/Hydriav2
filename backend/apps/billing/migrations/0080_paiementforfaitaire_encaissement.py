import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0079_smslog'),
        ('employees', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='paiementforfaitaire',
            name='date_encaissement',
            field=models.DateField(blank=True, db_index=True, help_text="Date à laquelle la caissière a encaissé ce paiement (vide = pas encore encaissé)", null=True, verbose_name="Date d'encaissement"),
        ),
        migrations.AddField(
            model_name='paiementforfaitaire',
            name='encaisse_par',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='paiements_forfaitaires_encaisses', to='employees.employe', verbose_name='Encaissé par'),
        ),
    ]
