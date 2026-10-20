from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('recrutement', '0007_alter_candidat_adresse'),
    ]

    operations = [
        migrations.AddField(
            model_name='candidatpreconfigure',
            name='autre_experience',
            field=models.TextField(blank=True, default='', verbose_name='Autre expérience'),
        ),
        migrations.AddField(
            model_name='candidatpreconfigure',
            name='commentaire_analyse',
            field=models.TextField(blank=True, default='', verbose_name="Commentaire d'analyse"),
        ),
        migrations.AddField(
            model_name='candidatpreconfigure',
            name='cv',
            field=models.FileField(blank=True, help_text='Format accepté: PDF, DOC, DOCX', null=True, upload_to='recrutement/preconfig/cv/%Y/%m/', validators=[django.core.validators.FileExtensionValidator(allowed_extensions=['pdf', 'doc', 'docx'])], verbose_name='CV'),
        ),
        migrations.AddField(
            model_name='candidatpreconfigure',
            name='date_naissance',
            field=models.DateField(blank=True, null=True, verbose_name='Date de naissance'),
        ),
        migrations.AddField(
            model_name='candidatpreconfigure',
            name='domicile',
            field=models.TextField(blank=True, default='', verbose_name='Domicile'),
        ),
        migrations.AddField(
            model_name='candidatpreconfigure',
            name='experience_poste',
            field=models.TextField(blank=True, default='', verbose_name='Expérience sur le poste'),
        ),
        migrations.AddField(
            model_name='candidatpreconfigure',
            name='formation',
            field=models.TextField(blank=True, default='', verbose_name='Formation'),
        ),
        migrations.AddField(
            model_name='candidatpreconfigure',
            name='invite_test_envoyee',
            field=models.BooleanField(default=False, verbose_name='Invitation test envoyée'),
        ),
        migrations.AddField(
            model_name='candidatpreconfigure',
            name='lettre_motivation',
            field=models.FileField(blank=True, help_text='Format accepté: PDF, DOC, DOCX', null=True, upload_to='recrutement/preconfig/lettres/%Y/%m/', validators=[django.core.validators.FileExtensionValidator(allowed_extensions=['pdf', 'doc', 'docx'])], verbose_name='Lettre de motivation'),
        ),
        migrations.AddField(
            model_name='candidatpreconfigure',
            name='nom',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='Nom'),
        ),
        migrations.AddField(
            model_name='candidatpreconfigure',
            name='note_age',
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True, verbose_name='Note âge'),
        ),
        migrations.AddField(
            model_name='candidatpreconfigure',
            name='note_domicile',
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True, verbose_name='Note domicile'),
        ),
        migrations.AddField(
            model_name='candidatpreconfigure',
            name='note_experience',
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True, verbose_name='Note expérience'),
        ),
        migrations.AddField(
            model_name='candidatpreconfigure',
            name='note_formation',
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True, verbose_name='Note formation'),
        ),
        migrations.AddField(
            model_name='candidatpreconfigure',
            name='note_permis',
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True, verbose_name='Note permis'),
        ),
        migrations.AddField(
            model_name='candidatpreconfigure',
            name='note_pretention',
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True, verbose_name='Note prétention'),
        ),
        migrations.AddField(
            model_name='candidatpreconfigure',
            name='permis_conduire',
            field=models.BooleanField(default=False, verbose_name='Permis de conduire'),
        ),
        migrations.AddField(
            model_name='candidatpreconfigure',
            name='photo_candidat',
            field=models.ImageField(blank=True, help_text='Format accepté: JPG, JPEG, PNG, WEBP', null=True, upload_to='recrutement/photos/%Y/%m/', validators=[django.core.validators.FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'webp'])], verbose_name='Photo du candidat'),
        ),
        migrations.AddField(
            model_name='candidatpreconfigure',
            name='prenom',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='Prénom'),
        ),
        migrations.AddField(
            model_name='candidatpreconfigure',
            name='pretention_salariale',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name='Prétention salariale'),
        ),
        migrations.AddField(
            model_name='candidatpreconfigure',
            name='screening_statut',
            field=models.CharField(choices=[('a_analyser', 'A analyser'), ('analyse_en_cours', 'Analyse en cours'), ('pret_test', 'Prêt pour test'), ('invite_test', 'Invité au test'), ('elimine', 'Éliminé')], default='a_analyser', max_length=20, verbose_name='Statut screening'),
        ),
    ]
