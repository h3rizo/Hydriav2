#!/usr/bin/env python
"""
Script de nettoyage des points d'eau vides créés par erreur lors d'imports

Ce script supprime les points d'eau qui n'ont AUCUN attribut significatif :
- Pas de nom d'abonné
- Pas de code
- Pas d'ouvrage
- Pas de parcelle
- Pas de type
- Pas de GPS
- Pas de compteur
- Pas de tarif
- Pas de nombre de consommateurs
"""

import os
import django

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.billing.models import PointEau
from django.db.models import Q

def cleanup_empty_points_eau():
    """
    Supprime les points d'eau qui n'ont AUCUN attribut significatif
    """
    print("🔍 Recherche des points d'eau complètement vides...")

    # Trouver les points d'eau sans AUCUN attribut significatif
    # Un point d'eau vide = pas de nom ET pas d'ouvrage ET pas de parcelle ET pas de GPS, etc.
    empty_points = PointEau.objects.filter(
        Q(nomabonne__isnull=True) | Q(nomabonne__exact=''),  # Pas de nom
        Q(code_point_eau__isnull=True) | Q(code_point_eau__exact=''),  # Pas de code
        ouvrage__isnull=True,  # Pas d'ouvrage
        parcelle__isnull=True,  # Pas de parcelle
        type_point_eau__isnull=True,  # Pas de type
        compteur_tete__isnull=True,  # Pas de compteur
        latitude__isnull=True,  # Pas de GPS
        longitude__isnull=True,
        tarifforfaitaire__isnull=True,  # Pas de tarif
        nombre_consommateurs__isnull=True  # Pas de consommateurs
    )

    count = empty_points.count()

    if count == 0:
        print("✅ Aucun point d'eau complètement vide trouvé")
        return

    print(f"⚠️  Trouvé {count} points d'eau COMPLÈTEMENT vides (aucun attribut significatif)")

    # Afficher quelques exemples
    print("\n📋 Exemples de points d'eau à supprimer :")
    for point in empty_points[:10]:
        print(f"  - ID: {point.id}")
        print(f"    Code: {point.code_point_eau or 'N/A'}")
        print(f"    Nom: '{point.nomabonne}'")
        print(f"    Ouvrage: {point.ouvrage.nom_ouvrage if point.ouvrage else 'N/A'}")
        print(f"    Créé: {point.createdat or 'N/A'}")
        print()

    # Demander confirmation
    confirmation = input(f"\n❓ Voulez-vous supprimer ces {count} points d'eau vides ? (oui/non) : ")

    if confirmation.lower() in ['oui', 'yes', 'o', 'y']:
        print("\n🗑️  Suppression en cours...")
        deleted_count, _ = empty_points.delete()
        print(f"✅ {deleted_count} points d'eau supprimés avec succès !")
    else:
        print("❌ Suppression annulée")

if __name__ == '__main__':
    cleanup_empty_points_eau()
