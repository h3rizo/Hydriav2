from django.core.management.base import BaseCommand
from django.db import transaction
from apps.inspections.models import ComposantTypeEquipement, ComposantTypePointEau
from apps.infrastructure.models import TypeEquipement
from apps.billing.models import TypePointEau


class Command(BaseCommand):
    help = 'Peuple les composants standards pour chaque type d\'équipement et point d\'eau'

    def handle(self, *args, **options):
        with transaction.atomic():
            self.create_composants_equipements()
            self.create_composants_points_eau()
            self.stdout.write(
                self.style.SUCCESS('Composants créés avec succès !')
            )

    def create_composants_equipements(self):
        """Crée les composants standards pour chaque type d'équipement"""

        # Définition des composants par type d'équipement (basée sur les types existants)
        composants_par_type = {
            'Captage': [
                {'nom': 'Bassin versant', 'ordre': 1, 'description': 'Zone de captage des eaux'},
                {'nom': 'Perimetre rapproche', 'ordre': 2, 'description': 'Zone de protection immediate'},
                {'nom': 'Cloture', 'ordre': 3, 'description': 'Cloture de protection du captage'},
                {'nom': 'Boite de captage', 'ordre': 4, 'description': 'Structure de captage principal'},
                {'nom': 'Trop-plein', 'ordre': 5, 'description': 'Systeme d\'evacuation du surplus'},
            ],
            'Citerne': [
                {'nom': 'Structure principale', 'ordre': 1, 'description': 'Corps principal de la citerne'},
                {'nom': 'Etancheite', 'ordre': 2, 'description': 'Systeme d\'etancheite'},
                {'nom': 'Robinetterie', 'ordre': 3, 'description': 'Vannes et robinets'},
                {'nom': 'Systeme de niveau', 'ordre': 4, 'description': 'Indicateurs de niveau d\'eau'},
                {'nom': 'Acces et securite', 'ordre': 5, 'description': 'Echelles, garde-corps, fermetures'},
            ],
            'Conduite': [
                {'nom': 'Tuyauterie principale', 'ordre': 1, 'description': 'Conduite de transport'},
                {'nom': 'Joints et raccords', 'ordre': 2, 'description': 'Elements de liaison'},
                {'nom': 'Supports et ancrages', 'ordre': 3, 'description': 'Fixations de la conduite'},
                {'nom': 'Vannes de sectionnement', 'ordre': 4, 'description': 'Dispositifs d\'arret'},
            ],
            'Filtre': [
                {'nom': 'Media filtrant', 'ordre': 1, 'description': 'Materiau de filtration'},
                {'nom': 'Structure filtrante', 'ordre': 2, 'description': 'Bac ou reservoir de filtration'},
                {'nom': 'Systeme de lavage', 'ordre': 3, 'description': 'Dispositif de nettoyage'},
                {'nom': 'Robinetterie', 'ordre': 4, 'description': 'Vannes de controle'},
            ],
        }

        for nom_type, composants in composants_par_type.items():
            try:
                type_equipement = TypeEquipement.objects.get(nom_type=nom_type)
                self.stdout.write(f'Traitement du type: {nom_type}')

                for comp_data in composants:
                    composant, created = ComposantTypeEquipement.objects.get_or_create(
                        type_equipement=type_equipement,
                        nom_composant=comp_data['nom'],
                        defaults={
                            'description': comp_data['description'],
                            'ordre_affichage': comp_data['ordre'],
                            'est_obligatoire': True
                        }
                    )
                    if created:
                        self.stdout.write(f'  + Cree: {comp_data["nom"]}')
                    else:
                        self.stdout.write(f'  - Existe deja: {comp_data["nom"]}')

            except TypeEquipement.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f'Type d\'equipement "{nom_type}" introuvable')
                )

    def create_composants_points_eau(self):
        """Crée les composants standards pour chaque type de point d'eau"""

        # Définition des composants par type de point d'eau (basée sur les types existants)
        composants_par_type = {
            'Borne Fontaine': [
                {'nom': 'Maconnerie', 'ordre': 1, 'description': 'Structure en beton/pierre'},
                {'nom': 'Evacuation', 'ordre': 2, 'description': 'Systeme d\'evacuation des eaux'},
                {'nom': 'Plomberie', 'ordre': 3, 'description': 'Robinets et tuyauterie'},
            ],
            'Branchement Prive': [
                {'nom': 'Branchement principal', 'ordre': 1, 'description': 'Raccordement au reseau'},
                {'nom': 'Compteur', 'ordre': 2, 'description': 'Dispositif de mesure'},
                {'nom': 'Robinetterie', 'ordre': 3, 'description': 'Vannes et robinets'},
                {'nom': 'Installation domestique', 'ordre': 4, 'description': 'Installation chez l\'abonne'},
            ],
            'Branchement institutionnel': [
                {'nom': 'Branchement principal', 'ordre': 1, 'description': 'Raccordement au reseau'},
                {'nom': 'Compteur', 'ordre': 2, 'description': 'Dispositif de mesure'},
                {'nom': 'Robinetterie', 'ordre': 3, 'description': 'Vannes et robinets'},
                {'nom': 'Installation institutionnelle', 'ordre': 4, 'description': 'Installation dans l\'etablissement'},
            ],
            'Kiosque': [
                {'nom': 'Structure du kiosque', 'ordre': 1, 'description': 'Batiment de distribution'},
                {'nom': 'Robinets de distribution', 'ordre': 2, 'description': 'Points de puisage'},
                {'nom': 'Signalisation', 'ordre': 3, 'description': 'Panneaux et marquage'},
                {'nom': 'Aire de distribution', 'ordre': 4, 'description': 'Zone d\'accueil du public'},
            ],
            'PMH': [
                {'nom': 'Pompe manuelle', 'ordre': 1, 'description': 'Mecanisme de pompage'},
                {'nom': 'Margelle', 'ordre': 2, 'description': 'Bordure de protection'},
                {'nom': 'Evacuation', 'ordre': 3, 'description': 'Evacuation des eaux de surface'},
                {'nom': 'Signalisation', 'ordre': 4, 'description': 'Identification du point'},
            ],
        }

        for nom_type, composants in composants_par_type.items():
            try:
                type_point_eau = TypePointEau.objects.get(nom_type=nom_type)
                self.stdout.write(f'Traitement du type: {nom_type}')

                for comp_data in composants:
                    composant, created = ComposantTypePointEau.objects.get_or_create(
                        type_point_eau=type_point_eau,
                        nom_composant=comp_data['nom'],
                        defaults={
                            'description': comp_data['description'],
                            'ordre_affichage': comp_data['ordre'],
                            'est_obligatoire': True
                        }
                    )
                    if created:
                        self.stdout.write(f'  + Cree: {comp_data["nom"]}')
                    else:
                        self.stdout.write(f'  - Existe deja: {comp_data["nom"]}')

            except TypePointEau.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f'Type de point d\'eau "{nom_type}" introuvable')
                )