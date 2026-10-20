#!/usr/bin/env python
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.accounting.models import DiameXTemporaire

exportables = DiameXTemporaire.objects.filter(
    statut__in=['en_attente', 'valide']
).exclude(statut='exporte').exclude(compte_code__isnull=True).exclude(compte_code='')

print(f'=== TRANSACTIONS PRETES POUR EXPORT ===\n')
print(f'Total: {exportables.count()}\n')

for t in exportables:
    print(f'ID {t.id}: {t.type_transaction:<10} | Compte: {t.compte_code:<10} | In: {t.montant_in:>10.0f} | Out: {t.montant_out:>10.0f} | {t.info}')
