# -*- coding: utf-8 -*-
"""
Data migration: insere "Agent de maintenance" en position 7 dans l'ordre de
reference des postes (entre "Agent de recouvrement superviseur technique" et
"Assistant(e) admin"), en decalant les postes suivants d'un cran.

Nouvel ordre demande :
1. Directeur d'antenne
2. Responsable operationnel
3. Responsable administratif et financier
4. Superviseur technique
5. Agent de recouvrement
6. Agent de recouvrement superviseur technique
7. Agent de maintenance
8. Assistant(e) admin
9. Caissiere
10. Mpikojakoja ifotony
11. Gardien
12. Femme de menage
"""
import unicodedata

from django.db import migrations


def _normalize(value):
    if not value:
        return ''
    normalized = unicodedata.normalize('NFKD', str(value))
    ascii_only = normalized.encode('ascii', errors='ignore').decode('ascii')
    return ascii_only.lower().strip()


# Nouvel ordre complet (remplace celui de la migration 0077).
ORDRE_POSTES = [
    ["directeur d'antenne", "directeur dantenne"],
    ["responsable operationnel"],
    ["responsable administratif et financier"],
    ["superviseur technique"],
    ["agent de recouvrement"],
    ["agent de recouvrement superviseur technique"],
    ["agent de maintenance"],
    ["assistant(e) admin", "assisitant(e) admin", "assistante admin", "assistant admin"],
    ["caissiere"],
    ["mpikojakoja ifotony", "mpikojakoja ifoftony"],
    ["gardien"],
    ["femme de menage"],
]


def set_ordre_affichage(apps, schema_editor):
    Poste = apps.get_model('employees', 'Poste')

    variante_to_position = {}
    for position, variantes in enumerate(ORDRE_POSTES, start=1):
        for variante in variantes:
            variante_to_position[variante] = position

    for poste in Poste.objects.all():
        cle = _normalize(poste.nom_poste)
        position = variante_to_position.get(cle)
        if position is not None and poste.ordre_affichage != position:
            poste.ordre_affichage = position
            poste.save(update_fields=['ordre_affichage'])


def revert_ordre(apps, schema_editor):
    # Remet "Agent de maintenance" au sentinel "non classe" (comportement
    # d'avant cette migration) et decale les autres d'un cran vers le bas
    # pour retrouver l'ordre de la migration 0077.
    Poste = apps.get_model('employees', 'Poste')

    ANCIEN_ORDRE = [
        ["directeur d'antenne", "directeur dantenne"],
        ["responsable operationnel"],
        ["responsable administratif et financier"],
        ["superviseur technique"],
        ["agent de recouvrement"],
        ["agent de recouvrement superviseur technique"],
        ["assistant(e) admin", "assisitant(e) admin", "assistante admin", "assistant admin"],
        ["caissiere"],
        ["mpikojakoja ifotony", "mpikojakoja ifoftony"],
        ["gardien"],
        ["femme de menage"],
    ]

    variante_to_position = {}
    for position, variantes in enumerate(ANCIEN_ORDRE, start=1):
        for variante in variantes:
            variante_to_position[variante] = position

    for poste in Poste.objects.all():
        cle = _normalize(poste.nom_poste)
        if cle == 'agent de maintenance':
            poste.ordre_affichage = 9999
            poste.save(update_fields=['ordre_affichage'])
            continue
        position = variante_to_position.get(cle)
        if position is not None and poste.ordre_affichage != position:
            poste.ordre_affichage = position
            poste.save(update_fields=['ordre_affichage'])


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0078_poste_ordre_affichage_default_sentinel'),
    ]

    operations = [
        migrations.RunPython(set_ordre_affichage, revert_ordre),
    ]
