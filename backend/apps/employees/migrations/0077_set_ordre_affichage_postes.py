# -*- coding: utf-8 -*-
"""
Data migration: applique l'ordre de reference demande pour les postes
operationnels courants (independamment de l'organisation), via une
correspondance normalisee du nom de poste (accents/casse/espaces ignores,
tolerance sur quelques fautes de frappe connues).

Ordre demande :
1. Directeur d'antenne
2. Responsable operationnel
3. Responsable administratif et financier
4. Superviseur technique
5. Agent de recouvrement
6. Agent de recouvrement superviseur technique
7. Assistant(e) admin
8. Caissiere
9. Mpikojakoja ifotony
10. Gardien
11. Femme de menage

Les postes non lists conservent ordre_affichage=0 et restent tries
alphabetiquement apres ceux de la liste (cf. Meta.ordering du modele).
"""
import unicodedata

from django.db import migrations


def _normalize(value):
    if not value:
        return ''
    normalized = unicodedata.normalize('NFKD', str(value))
    ascii_only = normalized.encode('ascii', errors='ignore').decode('ascii')
    return ascii_only.lower().strip()


# Liste ordonnee des noms cibles (formes normalisees en cle, avec variantes
# connues pour tolerer des fautes de frappe deja presentes en base).
ORDRE_POSTES = [
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


def noop_reverse(apps, schema_editor):
    # Pas de retour arriere: remettre ordre_affichage a 0 romprait un
    # eventuel tri personnalise fait manuellement apres cette migration.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0076_poste_ordre_categorie_competences'),
    ]

    operations = [
        migrations.RunPython(set_ordre_affichage, noop_reverse),
    ]
