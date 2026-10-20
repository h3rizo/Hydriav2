"""
Script pour supprimer tous les relevés de la base de données
À utiliser avant de réimporter les relevés depuis Excel

Usage:
    python supprimer_tous_releves.py
"""

import os
import sys
import django

# Configuration Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.billing.models import Releve

def supprimer_tous_releves():
    """Supprime tous les relevés de la base de données"""

    # Compter les relevés
    total_releves = Releve.objects.count()

    if total_releves == 0:
        print("\n✅ Aucun relevé à supprimer. La table est déjà vide.\n")
        return

    # Demander confirmation
    print(f"\n⚠️  ATTENTION : Vous êtes sur le point de supprimer {total_releves} relevé(s).")
    print("Cette action est IRRÉVERSIBLE.\n")

    confirmation = input("Tapez 'OUI' pour confirmer la suppression : ")

    if confirmation.upper() != 'OUI':
        print("\n❌ Suppression annulée.\n")
        return

    # Supprimer
    print(f"\n🗑️  Suppression de {total_releves} relevé(s) en cours...")
    Releve.objects.all().delete()

    # Vérifier
    restants = Releve.objects.count()

    if restants == 0:
        print(f"✅ Suppression réussie ! {total_releves} relevé(s) supprimé(s).\n")
    else:
        print(f"⚠️  Suppression partielle. Il reste {restants} relevé(s).\n")

if __name__ == '__main__':
    supprimer_tous_releves()
