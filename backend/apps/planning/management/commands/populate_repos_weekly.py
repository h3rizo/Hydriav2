"""
Commande Django pour peupler automatiquement les Repos (Samedi + Dimanche)
pour les employés salariés (non journaliers)

Usage:
    python manage.py populate_repos_weekly --start 2025-01-01 --end 2025-12-31
    python manage.py populate_repos_weekly --weeks 4  # 4 semaines à partir d'aujourd'hui
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime, timedelta
import pytz

from apps.employees.models import Employe
from apps.employees.utils_contrat import est_salarie
from apps.planning.models import Planning, Activite


class Command(BaseCommand):
    help = 'Crée automatiquement les Planning "Repos" (Sam+Dim) pour les employés salariés'

    def add_arguments(self, parser):
        parser.add_argument(
            '--start',
            type=str,
            help='Date de début (YYYY-MM-DD)'
        )
        parser.add_argument(
            '--end',
            type=str,
            help='Date de fin (YYYY-MM-DD)'
        )
        parser.add_argument(
            '--weeks',
            type=int,
            default=4,
            help='Nombre de semaines à partir d\'aujourd\'hui (défaut: 4)'
        )

    def handle(self, *args, **options):
        # Timezone Madagascar
        tz_madagascar = pytz.timezone('Indian/Antananarivo')

        # Déterminer la période
        if options['start'] and options['end']:
            date_debut = datetime.strptime(options['start'], '%Y-%m-%d').date()
            date_fin = datetime.strptime(options['end'], '%Y-%m-%d').date()
        else:
            # Par défaut: 4 semaines à partir d'aujourd'hui
            date_debut = timezone.now().date()
            date_fin = date_debut + timedelta(weeks=options['weeks'])

        self.stdout.write(f"📅 Période: {date_debut} → {date_fin}")

        # Récupérer l'activité "Repos"
        try:
            activite_repos = Activite.objects.get(nom="Repos")
        except Activite.DoesNotExist:
            self.stdout.write(self.style.ERROR("❌ Activité 'Repos' non trouvée"))
            return

        # Récupérer tous les employés salariés (non journaliers)
        employes = Employe.objects.all()
        employes_salaries = [e for e in employes if est_salarie(e)]

        self.stdout.write(f"👥 {len(employes_salaries)} employé(s) salarié(s) trouvé(s)")

        total_crees = 0
        total_existants = 0

        # Pour chaque employé salarié
        for employe in employes_salaries:
            crees_employe = 0

            # Parcourir tous les jours de la période
            date_courante = date_debut

            while date_courante <= date_fin:
                # Samedi = 5, Dimanche = 6
                if date_courante.weekday() in [5, 6]:
                    # Créer datetime aware
                    date_planning = timezone.make_aware(
                        datetime.combine(date_courante, datetime.min.time()),
                        tz_madagascar
                    )

                    # Vérifier qu'il n'existe pas déjà un planning
                    existing = Planning.objects.filter(
                        employe=employe,
                        date__date=date_courante
                    ).first()

                    if not existing:
                        # Créer le repos
                        Planning.objects.create(
                            employe=employe,
                            date=date_planning,
                            activite=activite_repos,
                            estvalide=True,  # Validé automatiquement
                        )
                        crees_employe += 1
                        total_crees += 1
                    else:
                        total_existants += 1

                # Jour suivant
                date_courante += timedelta(days=1)

            if crees_employe > 0:
                self.stdout.write(
                    f"  ✅ {employe.nom_complet}: {crees_employe} repos créé(s)"
                )

        # Résumé
        self.stdout.write(self.style.SUCCESS(
            f"\n✅ Terminé! {total_crees} repos créé(s), {total_existants} déjà existant(s)"
        ))
