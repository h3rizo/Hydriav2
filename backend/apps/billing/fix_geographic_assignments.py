"""
Script pour corriger l'assignation géographique erronée
des salaires, IRSA et charges sociales.

Ces dépenses ne sont PAS géographiques et doivent avoir
district=NULL et commune=NULL.
"""

import re

# Lire le fichier
with open('services_previsions.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Pattern à remplacer (le bloc complet d'assignation géographique via organisation)
old_pattern = r"""        district_obj = None
        commune_obj = None
        ouvrage_obj = None

        if hasattr\(employe, 'organisation'\) and employe\.organisation:
            from apps\.billing\.models import ModaliteGestion, PointEau

            modalite = ModaliteGestion\.objects\.filter\(gestionnaire=employe\.organisation, date_fin__isnull=True\)\.select_related\('ouvrage'\)\.first\(\)

            if modalite and modalite\.ouvrage:
                ouvrage_obj = modalite\.ouvrage

                point_eau = PointEau\.objects\.filter\(ouvrage=ouvrage_obj\)\.select_related\('parcelle__village__fokontany__commune__district'\)\.first\(\)

                if point_eau and point_eau\.parcelle:
                    parcelle = point_eau\.parcelle
                    if parcelle\.village and parcelle\.village\.fokontany:
                        fokontany = parcelle\.village\.fokontany
                        if fokontany\.commune:
                            commune_obj = fokontany\.commune
                            if commune_obj\.district:
                                district_obj = commune_obj\.district"""

# Nouveau code simplifié (sans assignation géographique)
new_pattern = """        # Les salaires/IRSA/charges sociales ne sont PAS des dépenses géographiques
        # Ils doivent rester SANS district/commune (NULL)
        district_obj = None
        commune_obj = None
        ouvrage_obj = None"""

# Remplacer toutes les occurrences
content_fixed = re.sub(old_pattern, new_pattern, content)

# Compter les remplacements
nb_replacements = content.count("if hasattr(employe, 'organisation') and employe.organisation:") - \
                  content_fixed.count("if hasattr(employe, 'organisation') and employe.organisation:")

print(f"[OK] {nb_replacements} bloc(s) d'assignation géographique supprimé(s)")

# Sauvegarder
with open('services_previsions.py', 'w', encoding='utf-8') as f:
    f.write(content_fixed)

print("[OK] Fichier services_previsions.py corrigé")
print("[INFO] Les salaires, IRSA et charges sociales auront maintenant district=NULL et commune=NULL")
