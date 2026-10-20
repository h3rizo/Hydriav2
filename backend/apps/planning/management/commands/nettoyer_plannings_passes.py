"""
Commande Django pour nettoyer automatiquement les plannings passés

Usage:
    python manage.py nettoyer_plannings_passes [--dry-run] [--days N]

Options:
    --dry-run    : Affiche ce qui serait modifié sans appliquer les changements
    --days N     : Nombre de jours dans le passé (défaut: 30)

Règles appliquées:
    1. Plannings datant de plus de N jours (défaut 30) :
       - Passe estvalide=True si False

    2. PlanningDetails liés à ces plannings :
       - Passe retour=True si False
       - Passe date_retour=date du planning si NULL

    3. BonLivraison liés à ces plannings :
       - Passe retour=True si False
       - Passe date_retour=date du planning si NULL

    4. PaiementForfaitaire créés il y a plus de N jours :
       - Passe paye=True si False
       - Passe date_paiement=date_facture ou created_at si NULL
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from apps.planning.models import Planning, PlanningDetail, BonLivraison
from apps.billing.models import PaiementForfaitaire


class Command(BaseCommand):
    help = 'Nettoie automatiquement les plannings et données associées de plus de N jours'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Affiche ce qui serait modifié sans appliquer les changements'
        )
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Nombre de jours dans le passé (défaut: 30)'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        nb_jours = options['days']

        # Date limite : il y a N jours
        date_limite = timezone.now() - timedelta(days=nb_jours)

        self.stdout.write(self.style.WARNING(
            f"\n{'[DRY RUN] ' if dry_run else ''}Nettoyage des données de plus de {nb_jours} jours"
        ))
        self.stdout.write(self.style.WARNING(f"Date limite : {date_limite.strftime('%Y-%m-%d %H:%M:%S')}\n"))

        # ========================================
        # 1. PLANNINGS
        # ========================================
        self.stdout.write(self.style.HTTP_INFO("\n=== 1. PLANNINGS ==="))

        plannings_a_valider = Planning.objects.filter(
            date__lt=date_limite,
            estvalide=False
        )

        nb_plannings = plannings_a_valider.count()
        self.stdout.write(f"Plannings à valider : {nb_plannings}")

        if nb_plannings > 0:
            # Afficher quelques exemples
            exemples = plannings_a_valider.select_related('employe', 'fiche_poste')[:5]
            for p in exemples:
                employe_nom = p.employe.surnom if p.employe and p.employe.surnom else "Sans employé"
                activite_nom = p.fiche_poste.tache if p.fiche_poste else "Sans fiche de poste"
                self.stdout.write(
                    f"  - Planning {p.id} | {employe_nom} | {activite_nom} | {p.date.strftime('%Y-%m-%d')}"
                )

            if nb_plannings > 5:
                self.stdout.write(f"  ... et {nb_plannings - 5} autre(s)")

            if not dry_run:
                nb_updated = plannings_a_valider.update(estvalide=True)
                self.stdout.write(self.style.SUCCESS(f"✓ {nb_updated} planning(s) validé(s)"))

        # ========================================
        # 2. PLANNING DETAILS
        # ========================================
        self.stdout.write(self.style.HTTP_INFO("\n=== 2. PLANNING DETAILS ==="))

        # Récupérer tous les plannings passés (validés ou non)
        plannings_passes = Planning.objects.filter(date__lt=date_limite)
        planning_ids = list(plannings_passes.values_list('id', flat=True))

        details_a_retourner = PlanningDetail.objects.filter(
            planning_id__in=planning_ids,
            retour=False
        )

        nb_details = details_a_retourner.count()
        self.stdout.write(f"PlanningDetails à marquer retournés : {nb_details}")

        if nb_details > 0:
            # Afficher quelques exemples
            exemples = details_a_retourner.select_related('designation', 'planning')[:5]
            for d in exemples:
                designation_nom = d.designation.nom if d.designation else "Sans désignation"
                date_planning = d.planning.date.strftime('%Y-%m-%d') if d.planning else "Aucune date"
                self.stdout.write(
                    f"  - Detail {d.id} | {designation_nom} | Planning: {date_planning}"
                )

            if nb_details > 5:
                self.stdout.write(f"  ... et {nb_details - 5} autre(s)")

            if not dry_run:
                # Mettre à jour retour + date_retour
                nb_updated = 0
                for detail in details_a_retourner:
                    detail.retour = True
                    if not detail.date_retour and detail.planning:
                        detail.date_retour = detail.planning.date
                    detail.save()
                    nb_updated += 1

                self.stdout.write(self.style.SUCCESS(f"✓ {nb_updated} detail(s) marqué(s) retourné(s)"))

        # ========================================
        # 3. BONS DE LIVRAISON
        # ========================================
        self.stdout.write(self.style.HTTP_INFO("\n=== 3. BONS DE LIVRAISON ==="))

        bons_a_retourner = BonLivraison.objects.filter(
            planning_id__in=planning_ids,
            retour=False
        ).distinct()

        nb_bons = bons_a_retourner.count()
        self.stdout.write(f"Bons de livraison à marquer retournés : {nb_bons}")

        if nb_bons > 0:
            # Afficher quelques exemples
            exemples = bons_a_retourner.select_related('planning')[:5]
            for b in exemples:
                magasin_nom = b.magasin if b.magasin else "Sans magasin"
                date_planning = b.planning.date.strftime('%Y-%m-%d') if b.planning and b.planning.date else "Aucune date"
                self.stdout.write(
                    f"  - Bon {b.numero_bon or b.id} | {magasin_nom} | Planning: {date_planning}"
                )

            if nb_bons > 5:
                self.stdout.write(f"  ... et {nb_bons - 5} autre(s)")

            if not dry_run:
                nb_updated = 0
                for bon in bons_a_retourner:
                    bon.retour = True
                    if not bon.date_retour and bon.planning:
                        bon.date_retour = bon.planning.date
                    bon.save()
                    nb_updated += 1

                self.stdout.write(self.style.SUCCESS(f"✓ {nb_updated} bon(s) marqué(s) retourné(s)"))

        # ========================================
        # 4. PAIEMENTS FORFAITAIRES
        # ========================================
        self.stdout.write(self.style.HTTP_INFO("\n=== 4. PAIEMENTS FORFAITAIRES ==="))

        paiements_a_payer = PaiementForfaitaire.objects.filter(
            created_at__lt=date_limite,
            paye=False
        )

        nb_paiements = paiements_a_payer.count()
        self.stdout.write(f"Paiements forfaitaires à marquer payés : {nb_paiements}")

        if nb_paiements > 0:
            # Afficher quelques exemples
            exemples = paiements_a_payer.select_related('point_eau')[:5]
            for p in exemples:
                point_eau_nom = p.point_eau.nomabonne if p.point_eau and p.point_eau.nomabonne else "Sans point d'eau"
                montant = p.montant if p.montant else 0
                date_reference = p.created_at.strftime('%Y-%m-%d') if p.created_at else p.date_facture.strftime('%Y-%m-%d')
                self.stdout.write(
                    f"  - Paiement {p.id} | {point_eau_nom} | Montant: {montant} Ar | Cree: {date_reference}"
                )

            if nb_paiements > 5:
                self.stdout.write(f"  ... et {nb_paiements - 5} autre(s)")

            if not dry_run:
                # Mettre à jour paye + date_paiement
                nb_updated = 0
                for paiement in paiements_a_payer:
                    paiement.paye = True
                    if not paiement.date_paiement:
                        paiement.date_paiement = paiement.date_facture or (
                            paiement.created_at.date() if paiement.created_at else None
                        )
                    paiement.save()
                    nb_updated += 1

                self.stdout.write(self.style.SUCCESS(f"✓ {nb_updated} paiement(s) marqué(s) payé(s)"))

        # ========================================
        # RÉSUMÉ
        # ========================================
        self.stdout.write(self.style.HTTP_INFO("\n=== RÉSUMÉ ==="))

        if dry_run:
            self.stdout.write(self.style.WARNING("[DRY RUN] Aucune modification appliquée"))
            self.stdout.write("\nCe qui SERAIT modifié :")
        else:
            self.stdout.write(self.style.SUCCESS("✓ Nettoyage terminé avec succès"))
            self.stdout.write("\nModifications appliquées :")

        self.stdout.write(f"  - Plannings validés : {nb_plannings}")
        self.stdout.write(f"  - PlanningDetails retournés : {nb_details}")
        self.stdout.write(f"  - Bons de livraison retournés : {nb_bons}")
        self.stdout.write(f"  - Paiements forfaitaires payés : {nb_paiements}")

        total = nb_plannings + nb_details + nb_bons + nb_paiements
        self.stdout.write(f"\n  TOTAL : {total} enregistrement(s)")

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"\nPour appliquer ces modifications, relancez sans --dry-run :"
            ))
            self.stdout.write(f"  python manage.py nettoyer_plannings_passes --days {nb_jours}")
