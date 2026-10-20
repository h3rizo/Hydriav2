#!/usr/bin/env python
"""
Script de test pour vérifier les données saisonnier
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.organization.models import Ouvrage

# Rechercher l'ouvrage mentionné par l'utilisateur
print("\n[SEARCH] Recherche de l'ouvrage 'Fotsialanana Mahambo'...")
ouvrages = Ouvrage.objects.filter(nom_ouvrage__icontains='Fotsialanana')
print(f"Trouve {ouvrages.count()} ouvrage(s) avec 'Fotsialanana' dans le nom\n")

for ouvrage in ouvrages:
    print(f"[OUVRAGE] Ouvrage : {ouvrage.nom_ouvrage}")
    print(f"   - ID: {ouvrage.id}")
    print(f"   - Saisonnier: {ouvrage.saisonnier}")
    print(f"   - Type: {ouvrage.type_ouvrage.nom_type_ouvrage if ouvrage.type_ouvrage else 'N/A'}")
    print()

# Statistiques générales sur les ouvrages saisonniers
print("\n[STATS] Statistiques des ouvrages saisonniers:")
total = Ouvrage.objects.count()
saisonniers = Ouvrage.objects.filter(saisonnier=True).count()
non_saisonniers = Ouvrage.objects.filter(saisonnier=False).count()
null_saisonniers = Ouvrage.objects.filter(saisonnier__isnull=True).count()

print(f"   - Total ouvrages: {total}")
print(f"   - Saisonniers (True): {saisonniers}")
print(f"   - Non saisonniers (False): {non_saisonniers}")
print(f"   - Saisonnier NULL: {null_saisonniers}")
