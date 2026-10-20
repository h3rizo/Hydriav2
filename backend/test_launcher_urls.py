#!/usr/bin/env python
"""Script pour tester toutes les URLs du launcher"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from django.urls import reverse, NoReverseMatch

# Liste de toutes les URLs utilisées dans home_launcher.html
urls_to_test = [
    # Applications Principales
    ('feed:home', 'Fil d\'actualité'),
    ('core:search', 'Recherche'),
    ('core:dashboard', 'Dashboard'),
    ('core:dashboard_map', 'Carte interactive'),

    # Facturation
    ('billing:releves', 'Relevés'),
    ('billing:facturation_volumetrique', 'Facturation'),
    ('billing:points_eau_list', 'Points d\'eau'),
    ('billing:modalites_gestion', 'Modalités'),
    ('billing:compteurs', 'Compteurs'),
    ('billing:fournisseurs_list', 'Fournisseurs'),

    # RH & Paie
    ('employees:employes_list', 'Employés'),
    ('employees:postes_list', 'Postes'),
    ('employees:grilles_salaire_list', 'Grilles'),
    ('employees:fiches_paie_mensuelles', 'Fiches paie'),
    ('employees:paiements_irsa', 'IRSA'),
    ('employees:paiements_cnaps_fmfp', 'CNaPS/FMFP'),
    ('employees:paiements_mutuelle_sante', 'Mutuelle'),

    # Congés
    ('employees:conges_list', 'Congés'),
    ('employees:recuperations_list', 'Récupérations'),

    # Comptabilité
    ('accounting:verification_comptabilite', 'Vérification'),
    ('accounting:import_diamex', 'Import DiameX'),
    ('accounting:declaration_communication', 'Déclaration'),
    ('accounting:natures_declaration_list', 'Natures'),
    ('accounting:comptes_list', 'Comptes'),

    # Inspections
    ('inspections:analyses_eau_list', 'Analyses d\'eau'),
    ('planning:suivi_reparations', 'Réparations'),
    ('employees:positions_gps_list', 'Positions GPS'),

    # Chantiers
    ('chantiers:demandes_list', 'Demandes'),
    ('chantiers:validations_list', 'Validation Sources'),
    ('chantiers:chantiers_list', 'Chantiers'),
    ('chantiers:chantiers_kanban', 'Kanban'),

    # Gestion Volumétrique
    ('planning:analyse_consommation', 'Analyse'),
    ('ouvrages:tarifs_volumetriques_list', 'Tarifs'),

    # Infrastructure
    ('ouvrages:ouvrage_list', 'Ouvrages'),
    ('ouvrages:type_ouvrage_list', 'Types'),
    ('organization:type_equipement_list', 'Équipements'),
    ('ouvrages:gestion_complete', 'Gestion'),

    # Référentiel
    ('geography:regions_list', 'Géographie'),
    ('organization:organization_list', 'Organisations'),
    ('planning:deplacements_list', 'Déplacements'),

    # Système
    ('system:users_management', 'Utilisateurs'),
    ('core:rapport_qualite_donnees', 'Qualité'),
    ('core:architecture_documentation', 'Architecture'),
    ('conversations:conversations_list', 'Messages'),

    # Planning
    ('planning:indemnites', 'Indemnités'),
    ('billing:traitement_retours_caissiere', 'Retour'),
    ('planning:retour_indemnites', 'Retour Indemnités'),
    ('billing:retour_frais_deplacement', 'Retour Frais'),
]

print("=" * 80)
print("TEST DES URLs DU LAUNCHER")
print("=" * 80)

errors = []
success = 0

for url_name, description in urls_to_test:
    try:
        url = reverse(url_name)
        print(f"[OK] {description:30} -> {url}")
        success += 1
    except NoReverseMatch as e:
        print(f"[ERROR] {description:30} -> ERREUR: {url_name}")
        errors.append((url_name, description, str(e)))

print("\n" + "=" * 80)
print(f"RÉSULTAT: {success}/{len(urls_to_test)} URLs valides")
print("=" * 80)

if errors:
    print("\n[WARNING] ERREURS DETAILLEES:\n")
    for url_name, description, error in errors:
        print(f"  • {description} ({url_name})")
        print(f"    {error}\n")
else:
    print("\n[SUCCESS] Toutes les URLs sont valides!")
