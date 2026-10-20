"""
Commande pour mettre à jour les CIN et adresses des fournisseurs
dans les PaiementIRIDetail existants
"""
from django.core.management.base import BaseCommand
from django.db.models import Q
from apps.employees.models import PaiementIRIDetail
from apps.billing.models import Fournisseur
from apps.accounting.models import BaseDiameX


class Command(BaseCommand):
    help = 'Met à jour les CIN et adresses des fournisseurs dans les PaiementIRIDetail existants'

    def handle(self, *args, **options):
        # Récupérer tous les détails sans CIN/adresse
        details = PaiementIRIDetail.objects.filter(
            Q(fournisseur_cin__isnull=True) | Q(fournisseur_adresse__isnull=True)
        )

        total = details.count()
        self.stdout.write(f'[LOG] Traitement de {total} detail(s) IRI...')

        nb_updated = 0
        nb_found = 0

        for detail in details:
            fournisseur_obj = None

            # Méthode 1: Rechercher la transaction DiameX source
            if detail.numero_diamex_source and detail.base_diamex_source:
                try:
                    transaction = BaseDiameX.objects.filter(
                        rec=int(detail.numero_diamex_source),
                        prog=detail.base_diamex_source
                    ).first()

                    if transaction and transaction.fournisseur:
                        # Essayer de convertir en ID
                        try:
                            fournisseur_id = int(transaction.fournisseur)
                            fournisseur_obj = Fournisseur.objects.filter(
                                idxls=fournisseur_id
                            ).first()
                        except (ValueError, TypeError):
                            # Si ce n'est pas un nombre, chercher par nom
                            fournisseur_obj = Fournisseur.objects.filter(
                                nom_fournisseur__iexact=transaction.fournisseur
                            ).first()
                except Exception as e:
                    self.stdout.write(f'[WARNING] Erreur transaction {detail.numero_diamex_source}: {e}')

            # Méthode 2 (fallback): Rechercher par nom du fournisseur
            if not fournisseur_obj and detail.fournisseur_nom:
                fournisseur_nom_clean = detail.fournisseur_nom.strip()

                # Recherche exacte
                fournisseur_obj = Fournisseur.objects.filter(
                    nom_fournisseur__iexact=fournisseur_nom_clean
                ).first()

                # Recherche partielle
                if not fournisseur_obj:
                    fournisseur_obj = Fournisseur.objects.filter(
                        nom_fournisseur__icontains=fournisseur_nom_clean
                    ).first()

            # Mettre à jour si fournisseur trouvé
            if fournisseur_obj:
                nb_found += 1
                updated = False

                if not detail.fournisseur_cin and fournisseur_obj.cin:
                    detail.fournisseur_cin = fournisseur_obj.cin
                    updated = True

                if not detail.fournisseur_adresse and fournisseur_obj.adresse:
                    detail.fournisseur_adresse = fournisseur_obj.adresse
                    updated = True

                if updated:
                    detail.save()
                    nb_updated += 1
                    self.stdout.write(
                        f'[OK] {detail.fournisseur_nom} -> {fournisseur_obj.nom_fournisseur} '
                        f'(CIN: {fournisseur_obj.cin or "N/A"})'
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f'\n[SUCCESS] Traitement termine: {nb_found} fournisseur(s) trouve(s), '
                f'{nb_updated} detail(s) mis a jour'
            )
        )
