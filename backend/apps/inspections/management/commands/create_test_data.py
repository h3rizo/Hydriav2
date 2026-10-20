from django.core.management.base import BaseCommand
from django.db import transaction
from apps.organization.models import Organisation, Base, Ouvrage
from apps.infrastructure.models import TypeOuvrage, EquipementConstitutif
from apps.inspections.models import PointDeControle, Checklist, ChecklistPointControle
from apps.employees.models import Employe


class Command(BaseCommand):
    help = 'Crée des données de test pour les équipements et points de contrôle'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Supprimer les données existantes avant de créer les nouvelles',
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write('Suppression des données existantes...')
            EquipementConstitutif.objects.all().delete()
            Checklist.objects.all().delete()
            PointDeControle.objects.all().delete()

        with transaction.atomic():
            # Créer des organisations et ouvrages de test si nécessaires
            self.create_base_data()

            # Créer des points de contrôle de base
            self.create_points_controle()

            # Créer des équipements de test
            self.create_equipements()

            # Créer des checklists
            self.create_checklists()

        self.stdout.write(self.style.SUCCESS('Donnees de test creees avec succes!'))

    def create_base_data(self):
        """Créer les données de base nécessaires."""
        self.stdout.write('Création des données de base...')

        # Organisation
        organisation, created = Organisation.objects.get_or_create(
            nom_organisation='JIRAMA Antananarivo',
            defaults={
                'localite': 'Antananarivo',
                'telephone': '+261 20 22 222 22',
                'mail': 'contact@jirama.mg'
            }
        )

        # Type d'ouvrage
        type_station, created = TypeOuvrage.objects.get_or_create(
            nomtype='Station de pompage',
            defaults={}
        )

        type_reservoir, created = TypeOuvrage.objects.get_or_create(
            nomtype='Réservoir',
            defaults={}
        )

        # Ouvrages
        self.station_nord, created = Ouvrage.objects.get_or_create(
            nom='Station de pompage Nord',
            defaults={
                'typeouvrage': type_station,
                'organisation': organisation,
                'anneerealisation': 2020,
                'remarque': 'Station principale de distribution'
            }
        )

        self.reservoir_central, created = Ouvrage.objects.get_or_create(
            nom='Réservoir Central',
            defaults={
                'typeouvrage': type_reservoir,
                'organisation': organisation,
                'anneerealisation': 2018,
                'remarque': 'Réservoir de stockage principal'
            }
        )

    def create_points_controle(self):
        """Créer des points de contrôle de base."""
        self.stdout.write('Création des points de contrôle...')

        points_data = [
            # Points booléens
            {
                'nom': 'État général équipement',
                'description': 'Vérifier l\'état général de l\'équipement (propreté, corrosion, dommages visibles)',
                'type_resultat': 'BOOL'
            },
            {
                'nom': 'Fonctionnement normal',
                'description': 'L\'équipement fonctionne-t-il normalement sans bruit anormal?',
                'type_resultat': 'BOOL'
            },
            {
                'nom': 'Absence de fuite',
                'description': 'Vérifier qu\'il n\'y a pas de fuite d\'eau ou d\'huile',
                'type_resultat': 'BOOL'
            },
            {
                'nom': 'Connexions électriques',
                'description': 'Vérifier l\'état des connexions électriques et leur sécurité',
                'type_resultat': 'BOOL'
            },
            {
                'nom': 'Propreté et rangement',
                'description': 'L\'environnement de l\'équipement est-il propre et rangé?',
                'type_resultat': 'BOOL'
            },

            # Points numériques
            {
                'nom': 'Pression manomètre',
                'description': 'Mesurer la pression affichée sur le manomètre principal',
                'type_resultat': 'NUM',
                'valeur_min': 1.5,
                'valeur_max': 4.0,
                'unite': 'bar'
            },
            {
                'nom': 'Température moteur',
                'description': 'Mesurer la température du moteur en fonctionnement',
                'type_resultat': 'NUM',
                'valeur_min': 20.0,
                'valeur_max': 80.0,
                'unite': '°C'
            },
            {
                'nom': 'Débit sortie',
                'description': 'Mesurer le débit à la sortie de la pompe',
                'type_resultat': 'NUM',
                'valeur_min': 50.0,
                'valeur_max': 200.0,
                'unite': 'l/min'
            },
            {
                'nom': 'Niveau d\'eau réservoir',
                'description': 'Mesurer le niveau d\'eau dans le réservoir',
                'type_resultat': 'NUM',
                'valeur_min': 20.0,
                'valeur_max': 95.0,
                'unite': '%'
            },
            {
                'nom': 'Tension électrique',
                'description': 'Mesurer la tension d\'alimentation électrique',
                'type_resultat': 'NUM',
                'valeur_min': 200.0,
                'valeur_max': 240.0,
                'unite': 'V'
            },
        ]

        for point_data in points_data:
            point, created = PointDeControle.objects.get_or_create(
                nom=point_data['nom'],
                defaults=point_data
            )
            if created:
                self.stdout.write(f'  + Point de controle cree: {point.nom}')

    def create_equipements(self):
        """Créer des équipements de test."""
        self.stdout.write('Création des équipements...')

        # Équipements pour la station de pompage
        equipements_station = [
            {
                'nom': 'Pompe principale #1',
                'description': 'Pompe centrifuge principale pour l\'alimentation en eau',
                'type_equipement': 'pompe',
                'code_equipement': 'PUMP-SPN-001',
                'statut': 'operationnel'
            },
            {
                'nom': 'Pompe de secours #2',
                'description': 'Pompe centrifuge de secours',
                'type_equipement': 'pompe',
                'code_equipement': 'PUMP-SPN-002',
                'statut': 'operationnel'
            },
            {
                'nom': 'Vanne d\'arrêt principale',
                'description': 'Vanne d\'arrêt sur la conduite principale',
                'type_equipement': 'vanne',
                'code_equipement': 'VALVE-SPN-001',
                'statut': 'operationnel'
            },
            {
                'nom': 'Manomètre pression',
                'description': 'Manomètre de mesure de pression de refoulement',
                'type_equipement': 'compteur',
                'code_equipement': 'GAUGE-SPN-001',
                'statut': 'operationnel'
            },
            {
                'nom': 'Générateur de secours',
                'description': 'Générateur diesel pour alimentation de secours',
                'type_equipement': 'generateur',
                'code_equipement': 'GEN-SPN-001',
                'statut': 'operationnel'
            },
        ]

        for equip_data in equipements_station:
            equipement, created = EquipementConstitutif.objects.get_or_create(
                code_equipement=equip_data['code_equipement'],
                defaults={
                    **equip_data,
                    'ouvrage': self.station_nord
                }
            )
            if created:
                self.stdout.write(f'  + Equipement cree: {equipement.nom}')

        # Équipements pour le réservoir
        equipements_reservoir = [
            {
                'nom': 'Réservoir principal 500m³',
                'description': 'Réservoir de stockage en béton de 500m³',
                'type_equipement': 'reservoir',
                'code_equipement': 'TANK-RC-001',
                'statut': 'operationnel'
            },
            {
                'nom': 'Sonde de niveau',
                'description': 'Sonde de mesure du niveau d\'eau',
                'type_equipement': 'compteur',
                'code_equipement': 'PROBE-RC-001',
                'statut': 'operationnel'
            },
            {
                'nom': 'Vanne de sortie principale',
                'description': 'Vanne de distribution principale',
                'type_equipement': 'vanne',
                'code_equipement': 'VALVE-RC-001',
                'statut': 'operationnel'
            },
            {
                'nom': 'Vanne de vidange',
                'description': 'Vanne de vidange pour maintenance',
                'type_equipement': 'vanne',
                'code_equipement': 'VALVE-RC-002',
                'statut': 'operationnel'
            },
            {
                'nom': 'Chlorateur automatique',
                'description': 'Système de chloration automatique',
                'type_equipement': 'chlorateur',
                'code_equipement': 'CHLOR-RC-001',
                'statut': 'operationnel'
            },
        ]

        for equip_data in equipements_reservoir:
            equipement, created = EquipementConstitutif.objects.get_or_create(
                code_equipement=equip_data['code_equipement'],
                defaults={
                    **equip_data,
                    'ouvrage': self.reservoir_central
                }
            )
            if created:
                self.stdout.write(f'  + Equipement cree: {equipement.nom}')

    def create_checklists(self):
        """Créer des checklists type par équipement."""
        self.stdout.write('Création des checklists...')

        # Récupérer les équipements et points de contrôle
        pompes = EquipementConstitutif.objects.filter(type_equipement='pompe')
        vannes = EquipementConstitutif.objects.filter(type_equipement='vanne')
        reservoirs = EquipementConstitutif.objects.filter(type_equipement='reservoir')
        compteurs = EquipementConstitutif.objects.filter(type_equipement='compteur')

        points_controle = {
            'etat_general': PointDeControle.objects.get(nom='État général équipement'),
            'fonctionnement': PointDeControle.objects.get(nom='Fonctionnement normal'),
            'fuites': PointDeControle.objects.get(nom='Absence de fuite'),
            'electricite': PointDeControle.objects.get(nom='Connexions électriques'),
            'proprete': PointDeControle.objects.get(nom='Propreté et rangement'),
            'pression': PointDeControle.objects.get(nom='Pression manomètre'),
            'temperature': PointDeControle.objects.get(nom='Température moteur'),
            'debit': PointDeControle.objects.get(nom='Débit sortie'),
            'niveau': PointDeControle.objects.get(nom='Niveau d\'eau réservoir'),
            'tension': PointDeControle.objects.get(nom='Tension électrique'),
        }

        # Checklists pour pompes
        for pompe in pompes:
            checklist_entretien, created = Checklist.objects.get_or_create(
                equipement_constitutif=pompe,
                type_visite='ENTRETIEN',
                defaults={
                    'nom': f'Entretien {pompe.nom}',
                    'frequence_jours': 30
                }
            )

            if created:
                # Points de contrôle pour pompe - entretien
                points_pompe = [
                    (points_controle['etat_general'], 1, True),
                    (points_controle['fonctionnement'], 2, True),
                    (points_controle['fuites'], 3, True),
                    (points_controle['electricite'], 4, True),
                    (points_controle['pression'], 5, True),
                    (points_controle['temperature'], 6, True),
                    (points_controle['debit'], 7, True),
                    (points_controle['proprete'], 8, False),
                ]

                for point, ordre, obligatoire in points_pompe:
                    ChecklistPointControle.objects.create(
                        checklist=checklist_entretien,
                        point_de_controle=point,
                        ordre=ordre,
                        est_obligatoire=obligatoire
                    )

                self.stdout.write(f'  + Checklist creee: {checklist_entretien.nom}')

        # Checklists pour réservoirs
        for reservoir in reservoirs:
            checklist_controle, created = Checklist.objects.get_or_create(
                equipement_constitutif=reservoir,
                type_visite='COMPLET',
                defaults={
                    'nom': f'Contrôle complet {reservoir.nom}',
                    'frequence_jours': 7
                }
            )

            if created:
                # Points de contrôle pour réservoir
                points_reservoir = [
                    (points_controle['etat_general'], 1, True),
                    (points_controle['niveau'], 2, True),
                    (points_controle['fuites'], 3, True),
                    (points_controle['proprete'], 4, True),
                ]

                for point, ordre, obligatoire in points_reservoir:
                    ChecklistPointControle.objects.create(
                        checklist=checklist_controle,
                        point_de_controle=point,
                        ordre=ordre,
                        est_obligatoire=obligatoire
                    )

                self.stdout.write(f'  + Checklist creee: {checklist_controle.nom}')

        # Checklists pour vannes
        for vanne in vannes:
            checklist_inspection, created = Checklist.objects.get_or_create(
                equipement_constitutif=vanne,
                type_visite='ENTRETIEN',
                defaults={
                    'nom': f'Inspection {vanne.nom}',
                    'frequence_jours': 15
                }
            )

            if created:
                # Points de contrôle pour vanne
                points_vanne = [
                    (points_controle['etat_general'], 1, True),
                    (points_controle['fonctionnement'], 2, True),
                    (points_controle['fuites'], 3, True),
                ]

                for point, ordre, obligatoire in points_vanne:
                    ChecklistPointControle.objects.create(
                        checklist=checklist_inspection,
                        point_de_controle=point,
                        ordre=ordre,
                        est_obligatoire=obligatoire
                    )

                self.stdout.write(f'  + Checklist creee: {checklist_inspection.nom}')

        self.stdout.write('Données de test créées avec succès!')