#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script pour déboguer les ouvrages avec commune/district N/A
"""
import os
import sys
import django

# Fix encoding for Windows console
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.organization.models import Ouvrage
from apps.billing.models import PointEau

# Les 3 ouvrages problématiques
ouvrages_names = ['Mandena', 'Antanetibe Ambohipihaonana', 'Ambondrona Est']

print("=" * 80)
print("ANALYSE DES OUVRAGES AVEC COMMUNE/DISTRICT N/A")
print("=" * 80)

for nom in ouvrages_names:
    print(f"\n\n{'='*80}")
    print(f"OUVRAGE: {nom}")
    print(f"{'='*80}")

    try:
        ouvrage = Ouvrage.objects.get(nom_ouvrage=nom)
        print(f"✓ Ouvrage trouvé: ID={ouvrage.id}")
        print(f"  Type: {ouvrage.type_ouvrage.nom_type_ouvrage if ouvrage.type_ouvrage else 'N/A'}")

        # Récupérer les points d'eau
        points_eau = PointEau.objects.filter(ouvrage=ouvrage)
        print(f"\n  Nombre de points d'eau: {points_eau.count()}")

        for i, pe in enumerate(points_eau, 1):
            print(f"\n  --- Point d'eau {i}: {pe.nomabonne or pe.code_point_eau or 'Sans nom'} ---")
            print(f"      ID: {pe.id}")

            # Vérifier la parcelle
            if pe.parcelle:
                print(f"      ✓ Parcelle définie: {pe.parcelle.nom_parcelle if hasattr(pe.parcelle, 'nom_parcelle') else pe.parcelle.id}")

                # Vérifier le village
                if pe.parcelle.village:
                    print(f"      ✓ Village: {pe.parcelle.village.nom_village}")

                    # Vérifier le fokontany
                    if pe.parcelle.village.fokontany:
                        print(f"      ✓ Fokontany: {pe.parcelle.village.fokontany.nom_fokontany}")

                        # Vérifier la commune
                        if pe.parcelle.village.fokontany.commune:
                            commune = pe.parcelle.village.fokontany.commune
                            print(f"      ✓ Commune: {commune.nom_commune}")

                            # Vérifier le district
                            if commune.district:
                                district = commune.district
                                print(f"      ✓ District: {district.nom_district}")

                                # Vérifier la région
                                if district.region:
                                    print(f"      ✓ Région: {district.region.nom_region}")
                                else:
                                    print(f"      ✗ PROBLÈME: District n'a pas de région")
                            else:
                                print(f"      ✗ PROBLÈME: Commune n'a pas de district")
                        else:
                            print(f"      ✗ PROBLÈME: Fokontany n'a pas de commune")
                    else:
                        print(f"      ✗ PROBLÈME: Village n'a pas de fokontany")
                else:
                    print(f"      ✗ PROBLÈME: Parcelle n'a pas de village")
            else:
                print(f"      ✗ PROBLÈME: Point d'eau n'a pas de parcelle")

    except Ouvrage.DoesNotExist:
        print(f"✗ Ouvrage '{nom}' non trouvé dans la base")
    except Exception as e:
        print(f"✗ Erreur: {type(e).__name__}: {e}")

print("\n" + "=" * 80)
print("FIN DE L'ANALYSE")
print("=" * 80)
