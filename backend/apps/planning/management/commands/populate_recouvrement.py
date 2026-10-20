from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime, time, timedelta
from collections import defaultdict
import pytz

from apps.employees.models import Employe, EmployeOuvrages
from apps.employees.models_evaluation import FichePoste
from apps.planning.models import Planning
from apps.billing.models import PaiementForfaitaire


class Command(BaseCommand):
    help = "Genere automatiquement le planning de recouvrement base sur les paiements forfaitaires"

    def add_arguments(self, parser):
        parser.add_argument(
            "--start-date",
            type=str,
            default=(timezone.now().date()).isoformat(),
            help="Date de debut (YYYY-MM-DD, defaut: aujourd'hui)",
        )
        parser.add_argument(
            "--end-date",
            type=str,
            default=(timezone.now().date() + timedelta(days=90)).isoformat(),
            help="Date de fin (YYYY-MM-DD, defaut: aujourd'hui + 90 jours)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Afficher ce qui serait cree sans creer reellement",
        )
        parser.add_argument(
            "--employe-id",
            type=str,
            default=None,
            help="Filtrer sur un agent specifique",
        )
        parser.add_argument(
            "--ouvrage-ids",
            type=str,
            default=None,
            help="Liste d'ouvrages (UUID) separes par des virgules",
        )

    def handle(self, *args, **options):
        start_date_str = options["start_date"]
        end_date_str = options["end_date"]
        dry_run = options["dry_run"]
        employe_id = options.get("employe_id")
        ouvrage_ids = options.get("ouvrage_ids")

        tz_madagascar = pytz.timezone("Indian/Antananarivo")

        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()

        if dry_run:
            self.stdout.write(self.style.WARNING("[MODE SIMULATION - Aucune donnee ne sera creee]"))

        self.stdout.write(f"[LOG] Periode: {start_date} -> {end_date}")

        # Recuperer ou creer la fiche de poste Recouvrement
        fiche_rec = None
        try:
            fiche_rec = FichePoste.objects.get(tache__iexact="Recouvrement")
        except FichePoste.DoesNotExist:
            if dry_run:
                self.stdout.write(self.style.WARNING('[LOG] Fiche de poste "Recouvrement" serait creee'))
                return
            fiche_rec = FichePoste.objects.create(
                tache="Recouvrement",
                description="Recouvrement des paiements forfaitaires",
                dans_planning=True,
            )
            self.stdout.write(self.style.SUCCESS('[LOG] Fiche de poste "Recouvrement" creee'))

        paiements = PaiementForfaitaire.objects.filter(
            date_paiement__isnull=False,
            date_paiement__gte=start_date,
            date_paiement__lte=end_date,
        ).select_related(
            "point_eau",
            "point_eau__ouvrage",
        ).order_by("date_paiement")

        if not paiements.exists():
            self.stdout.write(self.style.WARNING("[WARNING] Aucun paiement forfaitaire trouve dans cette periode"))
            return

        self.stdout.write(self.style.SUCCESS(f"[LOG] {paiements.count()} paiement(s) trouve(s)"))

        paiements_par_ouvrage_date = defaultdict(list)
        for paiement in paiements:
            if not paiement.point_eau or not paiement.point_eau.ouvrage:
                continue
            ouvrage = paiement.point_eau.ouvrage
            date_paiement = paiement.date_paiement
            key = (ouvrage.id, date_paiement)
            paiements_par_ouvrage_date[key].append({
                "ouvrage": ouvrage,
                "date": date_paiement,
                "point_eau": paiement.point_eau,
                "montant": paiement.montant,
            })

        self.stdout.write(f"[LOG] {len(paiements_par_ouvrage_date)} combinaison(s) ouvrage-date unique(s)")

        total_crees = 0
        total_deja_existants = 0
        total_sans_agent = 0

        for (ouvrage_id, date_paiement), paiements_groupe in paiements_par_ouvrage_date.items():
            ouvrage = paiements_groupe[0]["ouvrage"]
            nb_points_eau = len(paiements_groupe)

            responsabilite = EmployeOuvrages.objects.filter(
                ouvrage_id=ouvrage_id,
                date_fin__isnull=True,
                employe__date_debauchage__isnull=True,
                employe__poste__nom_poste__icontains="recouvrement",
            ).select_related("employe").first()

            if employe_id and (not responsabilite or str(responsabilite.employe_id) != str(employe_id)):
                continue

            if ouvrage_ids:
                ids = [oid.strip() for oid in ouvrage_ids.split(",") if oid.strip()]
                if str(ouvrage_id) not in ids:
                    continue

            if not responsabilite:
                total_sans_agent += 1
                self.stdout.write(
                    self.style.WARNING(f"[WARNING] Aucun agent de recouvrement assigne a {ouvrage.nom_ouvrage}")
                )
                continue

            agent = responsabilite.employe

            date_aware = tz_madagascar.localize(
                datetime.combine(date_paiement, time(0, 0))
            )

            existing = Planning.objects.filter(
                employe=agent,
                date=date_aware,
                ouvrage=ouvrage,
                fiche_poste=fiche_rec,
            ).first()

            if existing:
                total_deja_existants += 1
                self.stdout.write(
                    f"[INFO] Planning deja existant pour {agent.surnom or agent.prenom} - {ouvrage.nom_ouvrage} le {date_paiement}"
                )
                continue

            if not dry_run:
                Planning.objects.create(
                    employe=agent,
                    date=date_aware,
                    fiche_poste=fiche_rec,
                    type_activite=fiche_rec.type_activites,
                    ouvrage=ouvrage,
                    estvalide=True,
                    remarque=f"Recouvrement {nb_points_eau} point(s) d'eau - {ouvrage.nom_ouvrage}",
                )
            total_crees += 1

        self.stdout.write("\n" + "=" * 60)
        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                f"[OK] Simulation terminee: {total_crees} planning(s) seraient cree(s)"
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"[OK] Generation terminee: {total_crees} planning(s) cree(s)"
            ))

        if total_deja_existants > 0:
            self.stdout.write(f"[INFO] {total_deja_existants} planning(s) deja existant(s)")

        if total_sans_agent > 0:
            self.stdout.write(self.style.WARNING(
                f"[WARNING] {total_sans_agent} ouvrage(s) sans agent de recouvrement assigne"
            ))
