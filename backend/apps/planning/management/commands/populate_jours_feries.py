"""
Commande Django pour peupler automatiquement les jours feries
pour les employes salaries (non journaliers).

Usage:
    python manage.py populate_jours_feries --year 2025
    python manage.py populate_jours_feries --year 2024 2025
"""
from datetime import datetime

import pytz
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.employees.models import Employe
from apps.employees.utils_conges import get_jours_feries
from apps.employees.utils_contrat import est_salarie
from apps.planning import views_simple
from apps.planning.models import Activite, Planning, PlanningEmploye


class Command(BaseCommand):
    help = 'Cree automatiquement les plannings "Jour ferie" pour les employes salaries'

    def add_arguments(self, parser):
        parser.add_argument(
            '--year',
            type=int,
            nargs='+',
            default=[timezone.now().year],
            help='Annee(s) a peupler (ex: 2024 2025)',
        )

    def _find_shared_holiday_planning(self, holiday_date):
        candidates = (
            Planning.objects.filter(
                date__date=holiday_date,
                ouvrage__isnull=True,
            )
            .select_related('fiche_poste', 'type_activite', 'employe')
            .order_by('-estvalide', 'created_at', 'date', 'id')
        )

        for candidate in candidates:
            candidate_label = views_simple._normalize_poste_name(
                views_simple._get_planning_activity_label(planning=candidate)
            )
            if candidate_label == 'jour ferie':
                return candidate
        return None

    def handle(self, *args, **options):
        from apps.employees.views_gardiens import _resolve_planning_targets_for_activity

        tz_madagascar = pytz.timezone('Indian/Antananarivo')
        years = options['year']
        self.stdout.write(f"Annee(s): {', '.join(map(str, years))}")

        try:
            activite_ferie = Activite.objects.get(nom="Jour férié")
        except Activite.DoesNotExist:
            self.stdout.write(self.style.ERROR("Activite 'Jour ferie' non trouvee"))
            return

        _, fiche_poste_ferie, type_activite_ferie = _resolve_planning_targets_for_activity('Jour f')

        employes = Employe.objects.all()
        employes_salaries = [employe for employe in employes if est_salarie(employe)]
        self.stdout.write(f"{len(employes_salaries)} employe(s) salarie(s) trouve(s)")

        total_lignes_creees = 0
        total_participants_ajoutes = 0
        total_existants = 0

        for year in years:
            jours_feries_annee = [jour.isoformat() for jour in get_jours_feries(year)]
            if not jours_feries_annee:
                self.stdout.write(self.style.WARNING(f"Annee {year} sans jours feries configures"))
                continue

            self.stdout.write(f"\nAnnee {year}: {len(jours_feries_annee)} jours feries")

            for date_str in jours_feries_annee:
                holiday_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                planning_datetime = timezone.make_aware(
                    datetime.combine(holiday_date, datetime.min.time()),
                    tz_madagascar,
                )

                eligibles = []
                for employe in employes_salaries:
                    existing = Planning.objects.filter(
                        employe=employe,
                        date__date=holiday_date,
                    ).first()
                    if existing:
                        total_existants += 1
                        continue
                    eligibles.append(employe)

                if not eligibles:
                    continue

                shared_planning = self._find_shared_holiday_planning(holiday_date)
                if not shared_planning:
                    owner = eligibles[0]
                    planning_kwargs = {
                        'employe': owner,
                        'date': planning_datetime,
                        'estvalide': True,
                        'remarque': 'Jour ferie genere automatiquement',
                    }
                    if fiche_poste_ferie:
                        planning_kwargs['fiche_poste'] = fiche_poste_ferie
                    if type_activite_ferie:
                        planning_kwargs['type_activite'] = type_activite_ferie
                    if not fiche_poste_ferie and not type_activite_ferie:
                        planning_kwargs['activite'] = activite_ferie

                    shared_planning = Planning.objects.create(**planning_kwargs)
                    total_lignes_creees += 1
                    eligibles = eligibles[1:]

                existing_participant_ids = set(
                    PlanningEmploye.objects.filter(planning=shared_planning).values_list('employee_id', flat=True)
                )
                participants_to_add = [
                    employe for employe in eligibles
                    if employe.id != shared_planning.employe_id and employe.id not in existing_participant_ids
                ]
                if participants_to_add:
                    PlanningEmploye.objects.bulk_create(
                        [
                            PlanningEmploye(planning=shared_planning, employee=employe)
                            for employe in participants_to_add
                        ],
                        ignore_conflicts=True,
                    )
                    total_participants_ajoutes += len(participants_to_add)

        self.stdout.write(
            self.style.SUCCESS(
                f"\nTermine: {total_lignes_creees} ligne(s) Jour ferie creee(s), "
                f"{total_participants_ajoutes} participant(s) ajoute(s), "
                f"{total_existants} employe(s) deja couverts par un planning existant"
            )
        )
