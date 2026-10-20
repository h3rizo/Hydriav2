"""
Script pour valider les congés passés et recalculer les reliquats
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from datetime import datetime, date
from decimal import Decimal
import pytz

from apps.employees.models import Employe
from apps.employees.models_conges import DemandeConge, SoldeConge


class Command(BaseCommand):
    help = 'Valide les congés passés et recalcule les reliquats de congés pour tous les employés'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simule le traitement sans enregistrer en base',
        )
        parser.add_argument(
            '--employe',
            type=str,
            help='Traiter uniquement un employé spécifique (surnom)',
        )
        parser.add_argument(
            '--annee',
            type=int,
            help='Recalculer uniquement pour une année spécifique',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        employe_filter = options.get('employe')
        annee_filter = options.get('annee')

        self.stdout.write(self.style.WARNING('=' * 80))
        self.stdout.write(self.style.WARNING('VALIDATION DES CONGES PASSES ET RECALCUL DES RELIQUATS'))
        self.stdout.write(self.style.WARNING('=' * 80))

        if dry_run:
            self.stdout.write(self.style.WARNING('MODE SIMULATION (--dry-run) - Aucune modification en base'))

        # Timezone Madagascar
        tz_madagascar = pytz.timezone('Indian/Antananarivo')
        aujourd_hui = timezone.now().astimezone(tz_madagascar).date()

        # Récupérer les employés actifs (sans date de débauche)
        employes = Employe.objects.filter(date_debauchage__isnull=True)
        if employe_filter:
            employes = employes.filter(surnom=employe_filter)

        total_employes = employes.count()
        self.stdout.write(f"\n{total_employes} employe(s) a traiter\n")

        # Statistiques
        stats = {
            'employes_traites': 0,
            'conges_valides': 0,
            'soldes_recalcules': 0,
            'erreurs': []
        }

        # ÉTAPE 1 : Valider les congés passés qui ne sont pas encore validés
        self.stdout.write(self.style.SUCCESS('\n=== ETAPE 1: Validation des conges passes ===\n'))

        conges_a_valider = DemandeConge.objects.filter(
            date_fin__lt=aujourd_hui,
            statut='inscrite_planning'
        ).select_related('employe')

        if employe_filter:
            conges_a_valider = conges_a_valider.filter(employe__surnom=employe_filter)

        nb_a_valider = conges_a_valider.count()
        self.stdout.write(f"{nb_a_valider} conge(s) passe(s) a valider")

        if not dry_run and nb_a_valider > 0:
            for conge in conges_a_valider:
                self.stdout.write(f"  * {conge.employe.nom_affichage}: {conge.date_debut} -> {conge.date_fin} ({conge.nb_jours_demandes} jours)")
                # Pas besoin de changer le statut, il est déjà 'inscrite_planning'
                # On s'assure juste que les dates de validation sont renseignées
                if not conge.date_validation_chef:
                    conge.date_validation_chef = conge.date_demande or timezone.now()
                if not conge.date_validation_directeur:
                    conge.date_validation_directeur = conge.date_demande or timezone.now()
                if not conge.date_inscription_planning:
                    conge.date_inscription_planning = conge.date_demande or timezone.now()
                conge.save()
                stats['conges_valides'] += 1
        elif dry_run and nb_a_valider > 0:
            for conge in conges_a_valider[:5]:  # Afficher les 5 premiers
                self.stdout.write(f"  [SIMULATION] {conge.employe.nom_affichage}: {conge.date_debut} -> {conge.date_fin}")
            if nb_a_valider > 5:
                self.stdout.write(f"  ... et {nb_a_valider - 5} autre(s)")
            stats['conges_valides'] = nb_a_valider

        # ÉTAPE 2 : Recalculer les reliquats pour chaque employé
        self.stdout.write(self.style.SUCCESS('\n=== ETAPE 2: Recalcul des reliquats ===\n'))

        for employe in employes:
            self.stdout.write(f"\n{employe.nom_affichage}:")

            # Années à traiter
            if annee_filter:
                annees = [annee_filter]
            else:
                # Trouver les années des congés de cet employé
                conges_employe = DemandeConge.objects.filter(employe=employe)
                annees_conges = set()
                for conge in conges_employe:
                    annees_conges.add(conge.date_debut.year)
                    if conge.date_fin.year != conge.date_debut.year:
                        annees_conges.add(conge.date_fin.year)
                annees = sorted(annees_conges)

            if not annees:
                self.stdout.write("  Aucun conge trouve - Solde par defaut")
                # Créer un solde initial si nécessaire
                if not dry_run:
                    annee_courante = aujourd_hui.year
                    for mois in range(1, 13):
                        solde, created = SoldeConge.objects.get_or_create(
                            employe=employe,
                            annee=annee_courante,
                            mois=mois,
                            defaults={
                                'solde_conges_debut': Decimal('0'),
                                'acquisition_conges': Decimal('2.5'),
                                'consommation_conges': Decimal('0'),
                                'solde_conges_fin': Decimal('2.5'),
                                'solde_permissions_debut': 10,
                                'consommation_permissions': 0,
                                'solde_permissions_fin': 10,
                            }
                        )
                        if created:
                            stats['soldes_recalcules'] += 1
                continue

            # Traiter chaque année
            for annee in annees:
                self.stdout.write(f"  Annee {annee}:")

                # Solde de départ (report de l'année précédente)
                solde_debut_annee = Decimal('0')
                dernier_solde_annee_prec = SoldeConge.objects.filter(
                    employe=employe,
                    annee=annee - 1
                ).order_by('-mois').first()

                if dernier_solde_annee_prec:
                    solde_debut_annee = dernier_solde_annee_prec.solde_conges_fin

                self.stdout.write(f"    Solde debut annee: {solde_debut_annee} jours")

                # Calculer mois par mois
                solde_courant = solde_debut_annee

                for mois in range(1, 13):
                    # Acquisition : 2.5 jours par mois
                    acquisition = Decimal('2.5')

                    # Consommation : congés pris ce mois
                    conges_mois = DemandeConge.objects.filter(
                        employe=employe,
                        statut='inscrite_planning',
                        date_debut__year=annee,
                        date_debut__month=mois
                    )

                    consommation = Decimal('0')
                    for conge in conges_mois:
                        consommation += Decimal(str(conge.nb_jours_demandes))

                    # Solde fin de mois
                    solde_fin = solde_courant + acquisition - consommation

                    # Permissions (10 jours par an, réinitialisés en janvier)
                    if mois == 1:
                        solde_permissions_debut = 10
                    else:
                        solde_mois_prec = SoldeConge.objects.filter(
                            employe=employe,
                            annee=annee,
                            mois=mois - 1
                        ).first()
                        solde_permissions_debut = solde_mois_prec.solde_permissions_fin if solde_mois_prec else 10

                    # Consommation permissions (0 pour l'instant, à implémenter si nécessaire)
                    consommation_permissions = 0
                    solde_permissions_fin = solde_permissions_debut - consommation_permissions

                    if dry_run:
                        if consommation > 0 or mois == 1:  # Afficher uniquement les mois avec activité
                            self.stdout.write(
                                f"    [SIMULATION] Mois {mois:02d}: "
                                f"Debut={solde_courant:.2f}, Acq={acquisition:.2f}, "
                                f"Conso={consommation:.2f}, Fin={solde_fin:.2f}"
                            )
                    else:
                        # Créer ou mettre à jour le solde
                        solde, created = SoldeConge.objects.update_or_create(
                            employe=employe,
                            annee=annee,
                            mois=mois,
                            defaults={
                                'solde_conges_debut': solde_courant,
                                'acquisition_conges': acquisition,
                                'consommation_conges': consommation,
                                'solde_conges_fin': solde_fin,
                                'solde_permissions_debut': solde_permissions_debut,
                                'consommation_permissions': consommation_permissions,
                                'solde_permissions_fin': solde_permissions_fin,
                            }
                        )
                        if created or consommation > 0:
                            stats['soldes_recalcules'] += 1

                    # Préparer pour le mois suivant
                    solde_courant = solde_fin

                # Afficher le solde final de l'année
                self.stdout.write(f"    Solde fin annee {annee}: {solde_fin:.2f} jours")

            stats['employes_traites'] += 1

        # Afficher le résumé
        self.stdout.write('\n')
        self.stdout.write(self.style.WARNING('=' * 80))
        self.stdout.write(self.style.WARNING('RESUME DU TRAITEMENT'))
        self.stdout.write(self.style.WARNING('=' * 80))
        self.stdout.write(f"Employes traites: {stats['employes_traites']}")
        self.stdout.write(f"Conges valides: {stats['conges_valides']}")
        self.stdout.write(f"Soldes recalcules: {stats['soldes_recalcules']}")

        if stats['erreurs']:
            self.stdout.write(self.style.ERROR(f"\nErreurs ({len(stats['erreurs'])}):"))
            for erreur in stats['erreurs']:
                self.stdout.write(self.style.ERROR(f"  * {erreur}"))

        if dry_run:
            self.stdout.write('\n' + self.style.WARNING('MODE SIMULATION - Aucune modification en base'))
            self.stdout.write(self.style.WARNING('Relancer sans --dry-run pour appliquer les changements'))
        else:
            self.stdout.write('\n' + self.style.SUCCESS('Traitement termine avec succes'))
