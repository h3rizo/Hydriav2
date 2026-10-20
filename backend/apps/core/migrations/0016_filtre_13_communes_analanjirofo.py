# Generated manually on 2026-09-22
"""Crée le filtre sauvegardé "13 communes Analanjirofo" pour la page
analyse-villages-desserte, à partir de la combinaison de communes fournie
par l'utilisateur.
"""
from django.db import migrations

COMMUNE_IDS = [
    "5e07c0b5-121a-4251-acb0-c9da672901ed",
    "496a56ee-29b8-4be0-b72e-528173986188",
    "cd3358ed-3961-4791-95e1-d1166e24875a",
    "063ac1aa-fef0-489a-8ea0-6443b3162504",
    "b54d4f9f-d6fd-408d-9bd1-a84e4931f43c",
    "fcd92677-a9a7-4338-8fc6-2de9e430afd6",
    "7a9bbeea-a701-4463-8799-acb6841b0931",
    "bc09feb4-dcd0-4eec-9bfb-56741a4fc5ff",
    "e40d64df-a9f8-4305-a7dd-e5ce8d66d268",
    "b4d6acc7-61f8-45cf-b40c-7c8fc90ed72b",
    "ac3262ad-9c2d-47dc-ab19-25ffc423afdb",
    "7dc779eb-fadf-41c3-bd86-c47cb5cdbcee",
    "6ac14096-6b28-4e55-91d8-d6c63aa52c4b",
]


def creer_filtre(apps, schema_editor):
    FiltreSauvegarde = apps.get_model('core', 'FiltreSauvegarde')
    FiltreSauvegarde.objects.update_or_create(
        page_key='villages_desserte',
        nom='13 communes Analanjirofo',
        defaults={
            'parametres': {
                'region': '',
                'district': [],
                'commune': COMMUNE_IDS,
                'fokontany': '',
            },
        },
    )


def supprimer_filtre(apps, schema_editor):
    FiltreSauvegarde = apps.get_model('core', 'FiltreSauvegarde')
    FiltreSauvegarde.objects.filter(
        page_key='villages_desserte',
        nom='13 communes Analanjirofo',
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0015_filtresauvegarde'),
    ]

    operations = [
        migrations.RunPython(creer_filtre, supprimer_filtre),
    ]
