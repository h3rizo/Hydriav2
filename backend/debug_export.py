#!/usr/bin/env python
"""
Debug pourquoi l'export retourne 0 transaction
"""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.accounting.models import DiameXTemporaire

print('=== DEBUG EXPORT ACCESS ===\n')

# Simuler les conditions de l'export
export_type = 'all'  # Simuler export tout
transaction_ids = []  # Aucune sélection

print(f'Export type: {export_type}')
print(f'Transaction IDs fournis: {transaction_ids}')

# Appliquer la même logique que views_export_access.py ligne 53-74
if export_type == 'selection' and transaction_ids:
    transactions = DiameXTemporaire.objects.filter(
        id__in=transaction_ids,
        statut__in=['en_attente', 'valide']
    ).exclude(
        statut='exporte'
    ).exclude(
        compte_code__isnull=True
    ).exclude(
        compte_code=''
    )
else:
    # Export ALL
    transactions = DiameXTemporaire.objects.filter(
        statut__in=['en_attente', 'valide']
    ).exclude(
        statut='exporte'
    ).exclude(
        compte_code__isnull=True
    ).exclude(
        compte_code=''
    )

print(f'\nTransactions trouvées: {transactions.count()}\n')

for t in transactions:
    print(f'ID {t.id}:')
    print(f'  Statut: {t.statut}')
    print(f'  Compte: {t.compte_code}')
    print(f'  Description: {(t.description or "")[:60]}')
    print(f'  Montant In: {t.montant_in}')
    print(f'  Montant Out: {t.montant_out}')
    print(f'  Prog: {t.prog or "NULL"}')
    print(f'  ACTIV: {t.activ or "NULL"}')
    print()

if transactions.count() == 0:
    print('PROBLEME: Aucune transaction trouvée !')
    print('\nVérification des données:')

    all_trans = DiameXTemporaire.objects.all()
    print(f'  Total transactions: {all_trans.count()}')

    status_count = DiameXTemporaire.objects.filter(statut__in=['en_attente', 'valide']).count()
    print(f'  Avec statut en_attente ou valide: {status_count}')

    with_compte = DiameXTemporaire.objects.filter(
        statut__in=['en_attente', 'valide']
    ).exclude(compte_code__isnull=True).exclude(compte_code='').count()
    print(f'  Avec compte valide: {with_compte}')

    not_exported = DiameXTemporaire.objects.filter(
        statut__in=['en_attente', 'valide']
    ).exclude(compte_code__isnull=True).exclude(compte_code='').exclude(statut='exporte').count()
    print(f'  Non exportées: {not_exported}')
