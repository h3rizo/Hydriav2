from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q
from datetime import datetime, time
import pytz

from apps.employees.models import Employe, EmployeOuvrages
from apps.employees.models_evaluation import FichePoste
from apps.planning.models import Planning


class Command(BaseCommand):
    help = "Genere automatiquement les contre-visites pour les superviseurs techniques"

    def add_arguments(self, parser):
        parser.add_argument(
            "--year",
            type=int,
            default=timezone.now().year,
            help="Annee pour laquelle generer les contre-visites (defaut: annee en cours)",
        )
        parser.add_argument(
            "--start-month",
            type=int,
            default=1,
            help="Mois de debut (1-12, defaut: 1)",
        )
        parser.add_argument(
            "--end-month",
            type=int,
            default=12,
            help="Mois de fin (1-12, defaut: 12)",
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
            help="Filtrer sur un superviseur specifique",
        )
        parser.add_argument(
            "--ouvrage-ids",
            type=str,
            default=None,
            help="Liste d'ouvrages (UUID) separes par des virgules",
        )

    def handle(self, *args, **options):
        year = options["year"]
        start_month = options["start_month"]
        end_month = options["end_month"]
        dry_run = options["dry_run"]
        employe_id = options.get("employe_id")
        ouvrage_ids = options.get("ouvrage_ids")

        tz_madagascar = pytz.timezone("Indian/Antananarivo")

        if dry_run:
            self.stdout.write(self.style.WARNING("[MODE SIMULATION - Aucune donnee ne sera creee]"))

        # Recuperer ou creer la fiche de poste Contre-visite
        fiche_cv = None
        try:
            fiche_cv = FichePoste.objects.get(tache__iexact="Contre-visite")
        except FichePoste.DoesNotExist:
            if dry_run:
                self.stdout.write(self.style.WARNING('[LOG] Fiche de poste "Contre-visite" serait creee'))
                return
            fiche_cv = FichePoste.objects.create(
                tache="Contre-visite",
                description="Contre-visite annuelle des ouvrages",
                dans_planning=True,
            )
            self.stdout.write(self.style.SUCCESS('[LOG] Fiche de poste "Contre-visite" creee'))

        # Recuperer les superviseurs techniques
        superviseurs = Employe.objects.filter(
            date_debauchage__isnull=True
        ).filter(
            Q(poste__nom_poste__icontains="superviseur") & Q(poste__nom_poste__icontains="technique")
        ).distinct()

        if employe_id:
            superviseurs = superviseurs.filter(id=employe_id)

        if not superviseurs.exists():
            self.stdout.write(self.style.WARNING("[WARNING] Aucun superviseur technique trouve"))
            return

        self.stdout.write(self.style.SUCCESS(f"[LOG] {superviseurs.count()} superviseur(s) technique(s) trouve(s)"))

        total_crees = 0
        total_deja_existants = 0
        total_sans_ouvrages = 0

        for superviseur in superviseurs:
            self.stdout.write(f"\n[LOG] Traitement: {superviseur.surnom or superviseur.prenom} {superviseur.nom}")

            responsabilites = EmployeOuvrages.objects.filter(
                employe=superviseur,
                date_fin__isnull=True,
            ).select_related("ouvrage")

            if ouvrage_ids:
                ids = [oid.strip() for oid in ouvrage_ids.split(",") if oid.strip()]
                responsabilites = responsabilites.filter(ouvrage_id__in=ids)

            if not responsabilites.exists():
                total_sans_ouvrages += 1
                self.stdout.write(self.style.WARNING("  [WARNING] Aucun ouvrage assigne"))
                continue

            self.stdout.write(f"  Ouvrages a traiter: {responsabilites.count()}")

            mois_disponibles = list(range(start_month, end_month + 1))

            for idx, resp in enumerate(responsabilites):
                ouvrage = resp.ouvrage

                existing_cv_ouvrage = Planning.objects.filter(
                    employe=superviseur,
                    fiche_poste=fiche_cv,
                    ouvrage=ouvrage,
                    date__year=year,
                ).first()

                if existing_cv_ouvrage:
                    total_deja_existants += 1
                    date_existante = existing_cv_ouvrage.date.strftime("%d/%m/%Y")
                    self.stdout.write(
                        f"  [INFO] Contre-visite deja planifiee pour {ouvrage.nom_ouvrage} le {date_existante}"
                    )
                    continue

                mois = mois_disponibles[idx % len(mois_disponibles)]

                jour_trouve = False
                for jour in range(1, 29):
                    try:
                        date_candidate = datetime(year, mois, jour).date()

                        if date_candidate.weekday() in [5, 6]:
                            continue

                        date_aware = tz_madagascar.localize(
                            datetime.combine(date_candidate, time(0, 0))
                        )

                        existing = Planning.objects.filter(
                            employe=superviseur,
                            date=date_aware,
                        ).exists()

                        if not existing:
                            if not dry_run:
                                Planning.objects.create(
                                    employe=superviseur,
                                    date=date_aware,
                                    fiche_poste=fiche_cv,
                                    type_activite=fiche_cv.type_activites,
                                    ouvrage=ouvrage,
                                    estvalide=True,
                                    remarque=f"Contre-visite annuelle {ouvrage.nom_ouvrage}",
                                )
                            total_crees += 1
                            jour_trouve = True
                            break
                    except ValueError:
                        continue

                if not jour_trouve:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  [WARNING] Aucun jour disponible trouve pour {ouvrage.nom_ouvrage}"
                        )
                    )

        self.stdout.write("\n" + "=" * 60)
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"[OK] Simulation terminee: {total_crees} contre-visite(s) seraient creee(s)"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"[OK] Generation terminee: {total_crees} contre-visite(s) creee(s)"
                )
            )

        if total_deja_existants > 0:
            self.stdout.write(f"[INFO] {total_deja_existants} contre-visite(s) deja existante(s)")

        if total_sans_ouvrages > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"[WARNING] {total_sans_ouvrages} superviseur(s) sans ouvrages assignes"
                )
            )
