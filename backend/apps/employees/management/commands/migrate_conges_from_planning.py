"""
Script de migration des congés depuis Planning vers DemandeConge
Valide automatiquement tous les congés passés
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from datetime import datetime, date
import pytz

from apps.planning.models import Planning, Activite
from apps.employees.models import Employe
from apps.employees.models_conges import DemandeConge, SoldeConge


class Command(BaseCommand):
    help = 'Migre les congés du Planning vers DemandeConge et valide automatiquement les congés passés'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simule la migration sans enregistrer en base',
        )
        parser.add_argument(
            '--employe',
            type=str,
            help='Migrer uniquement pour un employé spécifique (surnom)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        employe_filter = options.get('employe')

        self.stdout.write(self.style.WARNING('=' * 80))
        self.stdout.write(self.style.WARNING('MIGRATION DES CONGES: Planning -> DemandeConge'))
        self.stdout.write(self.style.WARNING('=' * 80))

        if dry_run:
            self.stdout.write(self.style.WARNING('MODE SIMULATION (--dry-run) - Aucune modification en base'))

        # Timezone Madagascar
        tz_madagascar = pytz.timezone('Indian/Antananarivo')
        aujourd_hui = timezone.now().astimezone(tz_madagascar).date()

        # Récupérer les activités de type "Congé"
        activites_conge = Activite.objects.filter(nom__icontains='Congé')

        if not activites_conge.exists():
            self.stdout.write(self.style.ERROR('Aucune activité de type "Congé" trouvée'))
            return

        self.stdout.write(f"Activités de congé trouvées: {', '.join([a.nom for a in activites_conge])}")

        # Récupérer tous les plannings de congé
        plannings_conge = Planning.objects.filter(
            activite__in=activites_conge
        ).select_related('employe', 'activite').order_by('employe', 'date')

        if employe_filter:
            plannings_conge = plannings_conge.filter(employe__surnom__iexact=employe_filter)

        total_plannings = plannings_conge.count()
        self.stdout.write(f"\n{total_plannings} entrées de planning à traiter\n")

        if total_plannings == 0:
            self.stdout.write(self.style.WARNING('Aucun congé à migrer'))
            return

        # Regrouper par employé et période continue
        conges_par_employe = {}

        for planning in plannings_conge:
            if not planning.employe:
                continue

            employe_id = str(planning.employe.id)
            if employe_id not in conges_par_employe:
                conges_par_employe[employe_id] = {
                    'employe': planning.employe,
                    'periodes': []
                }

            # Convertir la date en timezone Madagascar
            if planning.date.tzinfo:
                date_madagascar = planning.date.astimezone(tz_madagascar).date()
            else:
                date_madagascar = tz_madagascar.localize(planning.date).date()

            # Ajouter la date à la liste
            conges_par_employe[employe_id]['periodes'].append({
                'date': date_madagascar,
                'activite': planning.activite.nom,
                'planning_id': planning.id
            })

        # Regrouper les dates consécutives en périodes
        def regrouper_periodes_consecutives(dates_list):
            """Regroupe les dates consécutives en périodes"""
            if not dates_list:
                return []

            # Trier par date
            dates_sorted = sorted(dates_list, key=lambda x: x['date'])

            periodes = []
            debut_periode = dates_sorted[0]['date']
            fin_periode = dates_sorted[0]['date']
            activite = dates_sorted[0]['activite']
            planning_ids = [dates_sorted[0]['planning_id']]

            for i in range(1, len(dates_sorted)):
                date_courante = dates_sorted[i]['date']
                date_precedente = fin_periode

                # Si la date est consécutive (différence = 1 jour)
                if (date_courante - date_precedente).days == 1:
                    fin_periode = date_courante
                    planning_ids.append(dates_sorted[i]['planning_id'])
                else:
                    # Enregistrer la période précédente
                    periodes.append({
                        'date_debut': debut_periode,
                        'date_fin': fin_periode,
                        'nb_jours': (fin_periode - debut_periode).days + 1,
                        'activite': activite,
                        'planning_ids': planning_ids
                    })

                    # Démarrer une nouvelle période
                    debut_periode = date_courante
                    fin_periode = date_courante
                    activite = dates_sorted[i]['activite']
                    planning_ids = [dates_sorted[i]['planning_id']]

            # Ajouter la dernière période
            periodes.append({
                'date_debut': debut_periode,
                'date_fin': fin_periode,
                'nb_jours': (fin_periode - debut_periode).days + 1,
                'activite': activite,
                'planning_ids': planning_ids
            })

            return periodes

        # Statistiques
        stats = {
            'employes_traites': 0,
            'demandes_creees': 0,
            'demandes_validees': 0,
            'demandes_futures': 0,
            'erreurs': []
        }

        # Traiter chaque employé
        for employe_id, data in conges_par_employe.items():
            employe = data['employe']
            periodes = regrouper_periodes_consecutives(data['periodes'])

            self.stdout.write(f"\n{employe.nom_affichage} - {len(periodes)} période(s) de congé")

            for periode in periodes:
                date_debut = periode['date_debut']
                date_fin = periode['date_fin']
                nb_jours = periode['nb_jours']
                est_passe = date_fin < aujourd_hui

                self.stdout.write(f"  * {date_debut} -> {date_fin} ({nb_jours} jour{'s' if nb_jours > 1 else ''}) "
                                f"[{'PASSE' if est_passe else 'FUTUR'}]")

                if not dry_run:
                    try:
                        with transaction.atomic():
                            # Vérifier si une demande existe déjà pour cette période
                            demande_existante = DemandeConge.objects.filter(
                                employe=employe,
                                date_debut=date_debut,
                                date_fin=date_fin
                            ).first()

                            if demande_existante:
                                self.stdout.write(self.style.WARNING(f"    -> Demande existante (ID: {demande_existante.id}) - Ignoree"))
                                continue

                            # Récupérer le solde actuel (dernier solde disponible)
                            from django.db.models import Max
                            dernier_solde = SoldeConge.objects.filter(
                                employe=employe
                            ).order_by('-annee', '-mois').first()

                            reliquat_conge = dernier_solde.solde_conges_fin if dernier_solde else 0
                            reliquat_permission = dernier_solde.solde_permissions_fin if dernier_solde else 0

                            # Créer la demande de congé
                            demande = DemandeConge.objects.create(
                                employe=employe,
                                type_demande='conge',
                                date_debut=date_debut,
                                date_fin=date_fin,
                                nb_jours_demandes=nb_jours,
                                motif=f"Migré depuis Planning - Activité: {periode['activite']}",
                                reliquat_conge_avant=reliquat_conge,
                                reliquat_permission_avant=reliquat_permission,
                                statut='inscrite_planning',  # Statut par défaut
                                date_demande=timezone.now(),
                            )

                            # Si le congé est passé, le valider automatiquement
                            if est_passe:
                                demande.statut = 'inscrite_planning'
                                demande.date_validation_chef = timezone.now()
                                demande.date_validation_directeur = timezone.now()
                                demande.date_inscription_planning = timezone.now()
                                demande.save()

                                stats['demandes_validees'] += 1
                                self.stdout.write(self.style.SUCCESS(f"    -> Creee et VALIDEE (ID: {demande.id})"))
                            else:
                                stats['demandes_futures'] += 1
                                self.stdout.write(self.style.SUCCESS(f"    -> Creee (ID: {demande.id}) - A valider manuellement"))

                            stats['demandes_creees'] += 1

                    except Exception as e:
                        msg_erreur = f"{employe.nom_affichage} - {date_debut} -> {date_fin}: {str(e)}"
                        stats['erreurs'].append(msg_erreur)
                        self.stdout.write(self.style.ERROR(f"    -> ERREUR: {str(e)}"))
                else:
                    # Mode simulation
                    if est_passe:
                        self.stdout.write(f"    -> [SIMULATION] Serait creee et VALIDEE")
                        stats['demandes_validees'] += 1
                    else:
                        self.stdout.write(f"    -> [SIMULATION] Serait creee (a valider manuellement)")
                        stats['demandes_futures'] += 1
                    stats['demandes_creees'] += 1

            stats['employes_traites'] += 1

        # Afficher le résumé
        self.stdout.write('\n')
        self.stdout.write(self.style.WARNING('=' * 80))
        self.stdout.write(self.style.WARNING('RESUME DE LA MIGRATION'))
        self.stdout.write(self.style.WARNING('=' * 80))
        self.stdout.write(f"Employes traites: {stats['employes_traites']}")
        self.stdout.write(f"Demandes creees: {stats['demandes_creees']}")
        self.stdout.write(self.style.SUCCESS(f"  * Validees automatiquement (passees): {stats['demandes_validees']}"))
        self.stdout.write(self.style.WARNING(f"  * Futures (a valider): {stats['demandes_futures']}"))

        if stats['erreurs']:
            self.stdout.write(self.style.ERROR(f"\nErreurs ({len(stats['erreurs'])}):"))
            for erreur in stats['erreurs']:
                self.stdout.write(self.style.ERROR(f"  * {erreur}"))

        if dry_run:
            self.stdout.write('\n' + self.style.WARNING('MODE SIMULATION - Aucune modification en base'))
            self.stdout.write(self.style.WARNING('Relancer sans --dry-run pour appliquer les changements'))
        else:
            self.stdout.write('\n' + self.style.SUCCESS('Migration terminee avec succes'))
