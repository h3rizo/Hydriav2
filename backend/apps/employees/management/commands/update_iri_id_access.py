"""
Commande pour mettre à jour les ID Access dans les PaiementIRIDetail existants
"""
from django.core.management.base import BaseCommand
from apps.employees.models import PaiementIRIDetail
from apps.accounting.models import BaseDiameX


class Command(BaseCommand):
    help = 'Met à jour les ID Access dans les PaiementIRIDetail existants'

    def handle(self, *args, **options):
        # Récupérer tous les détails sans id_access_source
        details = PaiementIRIDetail.objects.filter(id_access_source__isnull=True)

        total = details.count()
        self.stdout.write(f'[LOG] Traitement de {total} detail(s) IRI...')

        nb_updated = 0

        for detail in details:
            # Rechercher la transaction DiameX source
            if detail.numero_diamex_source and detail.base_diamex_source:
                try:
                    transaction = BaseDiameX.objects.filter(
                        rec=int(detail.numero_diamex_source),
                        prog=detail.base_diamex_source
                    ).first()

                    if transaction and transaction.id_access:
                        detail.id_access_source = transaction.id_access
                        detail.save()
                        nb_updated += 1
                        self.stdout.write(
                            f'[OK] {detail.fournisseur_nom} -> ID Access: {transaction.id_access}'
                        )
                except Exception as e:
                    self.stdout.write(f'[WARNING] Erreur detail {detail.id}: {e}')

        self.stdout.write(
            f'\n[SUCCESS] Traitement termine: {nb_updated} detail(s) mis a jour'
        )
