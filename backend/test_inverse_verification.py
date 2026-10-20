"""Test de la verification inverse avec les vraies donnees"""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.accounting.helpers_recoupement import verifier_recoupement_inverse
from apps.organization.models import CompteTable

print("Test verification inverse Planning")
print("=" * 80)

# Recuperer les comptes autorises
comptes = list(CompteTable.objects.filter(
    nom_table='plannings_details',
    actif=True
).values_list('compte__compte', flat=True))

print(f"Comptes autorises: {len(comptes)}")
print(f"Liste: {comptes[:5]}...")
print(f"Compte 748411 present: {'748411' in comptes}")
print()

# Executer la verification
print("Execution verifier_recoupement_inverse()...")
result = verifier_recoupement_inverse(comptes, type_recoupement='planning')

print()
print("STATISTIQUES:")
print(f"  Total lignes DiameX: {result['stats']['total']}")
print(f"  Avec correspondance exacte (ok): {result['stats']['ok']}")
print(f"  Avec ecart leger (warning): {result['stats']['warning']}")
print(f"  Avec ecart important (error): {result['stats']['error']}")
print(f"  Sans correspondance (missing): {result['stats']['missing']}")
print()

# Chercher les lignes avec correspondances
matches = [r for r in result['recoupements_inverses'] if r['application_trouve']]
print(f"Nombre avec application_trouve=True: {len(matches)}")

if len(matches) > 0:
    print()
    print("EXEMPLES DE CORRESPONDANCES TROUVEES:")
    for i, match in enumerate(matches[:5]):
        print(f"\n{i+1}. DiameX ID {match['id_access']}, Prog {match['prog']}")
        print(f"   Description: {match['description'][:60]}")
        print(f"   IN: {match['montant_in']}, OUT: {match['montant_out']}")
        print(f"   Application records: {len(match['application_records'])}")
        print(f"   Status: {match['status']}")
        if match['application_records']:
            for rec in match['application_records'][:2]:
                print(f"     - {rec['designation']}: {rec['montant']} Ar")
else:
    print()
    print("AUCUNE CORRESPONDANCE TROUVEE")
    print()
    print("Verification: cherchons la ligne DiameX ID 2403...")
    ligne_2403 = [r for r in result['recoupements_inverses'] if r['id_access'] == 2403]
    if ligne_2403:
        print(f"  TROUVEE! Status: {ligne_2403[0]['status']}")
        print(f"  application_trouve: {ligne_2403[0]['application_trouve']}")
        print(f"  application_records: {len(ligne_2403[0]['application_records'])}")
    else:
        print("  PAS TROUVEE dans les resultats")
