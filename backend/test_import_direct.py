"""
Test d'import direct pour diagnostiquer le problème
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from django.db import transaction
from apps.accounting.models import BaseDiameX
from apps.employees.models import Employe

# Compter avant
print(f"[AVANT] BaseDiameX: {BaseDiameX.objects.count()}")

# Test création simple
try:
    with transaction.atomic():
        # Récupérer un employé
        employe = Employe.objects.filter(surnom='HERIZO').first()
        print(f"[EMPLOYE] Trouvé: {employe}")

        # Créer une entrée test
        entry = BaseDiameX.objects.create(
            fichier_source='TEST',
            id_access=99999,
            description='Test import',
            montant_in=1000.0,
            montant_out=0.0,
            compte_code='TEST',
            prog='TST',
            imported_by=employe
        )
        print(f"[OK] Entrée créée: {entry.id}")

    # Compter après (en dehors du with)
    print(f"[APRES] BaseDiameX: {BaseDiameX.objects.count()}")

    # Vérifier qu'elle existe
    test_entry = BaseDiameX.objects.filter(id_access=99999).first()
    print(f"[VERIF] Entrée existe: {test_entry is not None}")

    if test_entry:
        print(f"[DELETE] Suppression de l'entrée test...")
        test_entry.delete()
        print(f"[FINAL] BaseDiameX: {BaseDiameX.objects.count()}")

except Exception as e:
    print(f"[ERROR] {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()