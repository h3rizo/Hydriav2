"""
Commande pour mettre à jour les unités et prix unitaires
des PaiementIRIDetail existants en parsant les descriptions DiameX
"""
from django.core.management.base import BaseCommand
from django.db.models import Q
from apps.employees.models import PaiementIRIDetail
from apps.accounting.models import BaseDiameX
from decimal import Decimal
import re


class Command(BaseCommand):
    help = 'Met a jour les unites et prix unitaires dans les PaiementIRIDetail existants'

    def handle(self, *args, **options):
        # Récupérer tous les détails
        details = PaiementIRIDetail.objects.all()

        total = details.count()
        self.stdout.write(f'[LOG] Traitement de {total} detail(s) IRI...')

        nb_updated = 0

        for detail in details:
            updated = False

            # Méthode 1: Rechercher la transaction DiameX source pour re-parser
            if detail.numero_diamex_source and detail.base_diamex_source:
                try:
                    transaction = BaseDiameX.objects.filter(
                        rec=int(detail.numero_diamex_source),
                        prog=detail.base_diamex_source
                    ).first()

                    if transaction and transaction.description:
                        # Parser la description
                        description = transaction.description or ''
                        parts = description.strip('_').split('_')

                        # Extraire libellé, unité, prix
                        libelle = parts[2] if len(parts) > 2 else description
                        unite = parts[3] if len(parts) > 3 else None

                        prix_unitaire = Decimal('0')
                        if len(parts) > 4:
                            try:
                                prix_str = parts[4].replace(',', '').strip()
                                prix_match = re.search(r'\d+', prix_str)
                                if prix_match:
                                    prix_unitaire = Decimal(prix_match.group())
                            except (ValueError, IndexError):
                                prix_unitaire = Decimal('0')

                        # Mettre à jour si différent
                        if detail.libelle != libelle:
                            detail.libelle = libelle
                            updated = True

                        if unite and detail.unite != unite:
                            detail.unite = unite
                            updated = True

                        if prix_unitaire > 0 and detail.prix_unitaire != prix_unitaire:
                            detail.prix_unitaire = prix_unitaire
                            updated = True

                except Exception as e:
                    self.stdout.write(f'[WARNING] Erreur transaction {detail.numero_diamex_source}: {e}')

            if updated:
                detail.save()
                nb_updated += 1
                self.stdout.write(
                    f'[OK] {detail.fournisseur_nom} - {detail.libelle} '
                    f'(Unite: {detail.unite}, PU: {detail.prix_unitaire})'
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'\n[SUCCESS] Traitement termine: {nb_updated} detail(s) mis a jour'
            )
        )
