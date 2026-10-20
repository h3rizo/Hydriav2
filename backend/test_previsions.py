import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.billing.services_previsions import recalculer_previsions_annee

print("Test du calcul des previsions pour l'annee 2025...")
result = recalculer_previsions_annee(2025)

print("\n=== STATISTIQUES DU CALCUL ===")
print(f"Annee: {result['annee']}")
print(f"Lignes supprimees: {result['supprimees']}")
print(f"Lignes creees: {result['creees']}")
print(f"\nRECETTES:")
print(f"  - Forfaitaires: {result.get('recettes_forfaitaires', 0)}")
print(f"  - Volumetriques: {result.get('recettes_volumetriques', 0)}")
print(f"  - Nouveaux PE: {result.get('recettes_nouveaux_pe', 0)}")
print(f"\nDEPENSES:")
print(f"  - Avances: {result.get('depenses_avances', 0)}")
print(f"  - Bons de livraison: {result.get('depenses_bons_livraison', 0)}")
print(f"  - Indemnites: {result.get('depenses_indemnites', 0)}")
print(f"  - SALAIRES: {result.get('depenses_salaires', 0)} (nouveau)")
print(f"  - IRSA: {result.get('depenses_irsa', 0)} (nouveau)")
print(f"  - CHARGES SOCIALES: {result.get('depenses_charges_sociales', 0)} (nouveau)")
print(f"\nEMPLOYES:")
print(f"  - Indemnites: {result.get('nb_employes_indemnites', 0)}")
print(f"  - SALAIRES: {result.get('nb_employes_salaires', 0)} (nouveau)")
print(f"  - IRSA: {result.get('nb_employes_irsa', 0)} (nouveau)")
print(f"\nERREURS: {result.get('erreurs', [])}")
print(f"AVERTISSEMENTS: {result.get('avertissements', [])}")
