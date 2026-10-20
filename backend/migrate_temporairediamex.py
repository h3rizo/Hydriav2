#!/usr/bin/env python
"""
Script pour migrer les données de TemporaireDiameX vers DiameXTemporaire
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.billing.models import TemporaireDiameX
from apps.accounting.models import DiameXTemporaire
from django.db import transaction

def migrate_data():
    """Migrer les données de TemporaireDiameX vers DiameXTemporaire"""

    anciennes_lignes = TemporaireDiameX.objects.all()
    print(f"Nombre de lignes à migrer: {anciennes_lignes.count()}")

    if anciennes_lignes.count() == 0:
        print("Aucune ligne à migrer")
        return

    compteur_migre = 0
    compteur_erreur = 0

    with transaction.atomic():
        for ligne in anciennes_lignes:
            try:
                # Mapper les champs de TemporaireDiameX vers DiameXTemporaire
                # Déterminer le type_transaction
                type_transaction = 'avance'
                if ligne.type_ticket == 'recette':
                    type_transaction = 'recette'
                elif ligne.type_ticket == 'livraison':
                    type_transaction = 'depense'  # Les livraisons sont des dépenses

                # Mapper le statut
                statut_mapping = {
                    'en_attente': 'en_attente',
                    'envoye': 'exporte',
                    'erreur': 'rejete',
                }
                statut = statut_mapping.get(ligne.statut, 'en_attente')

                # Créer la nouvelle ligne dans DiameXTemporaire
                nouvelle_ligne = DiameXTemporaire.objects.create(
                    planning_detail=ligne.planning_detail,
                    type_transaction=type_transaction,
                    journal_code=ligne.journal,
                    date_m=ligne.date_rec,
                    rec=ligne.rec,
                    date_rec=ligne.date_rec,
                    description=ligne.description or ligne.designation,
                    montant_in=float(ligne.in_amount),
                    montant_out=float(ligne.out_amount),
                    compte_code=ligne.cat,
                    pers=ligne.pers,
                    detail='',  # Vide, car fournisseur est ForeignKey maintenant
                    info=f'Ticket {ligne.numero_ticket}',
                    scan='',
                    prog=ligne.activ,
                    fournisseur=ligne.fournisseur,
                    statut=statut,
                    created_by=ligne.employe if ligne.employe else None,
                    created_at=ligne.date_traitement if hasattr(ligne, 'date_traitement') else None,
                )

                print(f"[OK] Migré: {ligne.numero_ticket} - {ligne.designation[:50]}")
                compteur_migre += 1

            except Exception as e:
                print(f"[ERREUR] Erreur migration ligne {ligne.numero_ticket}: {e}")
                compteur_erreur += 1

    print(f"\n=== RÉSULTAT ===")
    print(f"Lignes migrées avec succès: {compteur_migre}")
    print(f"Erreurs: {compteur_erreur}")
    print(f"\nVérification:")
    print(f"  - TemporaireDiameX: {TemporaireDiameX.objects.count()} lignes")
    print(f"  - DiameXTemporaire: {DiameXTemporaire.objects.count()} lignes")

if __name__ == '__main__':
    migrate_data()
