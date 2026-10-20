"""
Gestionnaire de statistiques pour le chatbot Hydria
Permet au chatbot de répondre aux demandes de comptages et statistiques
"""
import logging
import re
from typing import Dict, Any, List, Optional, Tuple
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class StatsHandler:
    """
    Gestionnaire pour les demandes de statistiques et comptages
    Utilise les APIs de dashboard existantes
    """

    def __init__(self):
        # Mapping des entités reconnues vers les clés API
        self.entity_mappings = {
            'ouvrage': ['ouvrages', 'ouvrage', 'infrastructure', 'infrastructures'],
            'point_eau': ['point d\'eau', 'points d\'eau', 'point eau', 'points eau', 'branchement', 'branchements'],
            'point_eau_prive': ['point d\'eau privé', 'points d\'eau privés', 'bp', 'branchement privé'],
            'point_eau_public': ['point d\'eau public', 'points d\'eau publics', 'borne fontaine', 'bornes fontaines'],
            'point_eau_coupe': ['point d\'eau coupé', 'points d\'eau coupés', 'branchement coupé', 'coupure'],
            'equipement': ['équipement', 'équipements', 'equipement', 'equipements'],
            'compteur_tete': ['compteur de tête', 'compteurs de tête', 'compteur tête', 'compteurs tête'],
            'adresse': ['adresse', 'adresses'],
            'carte_sociale': ['carte sociale', 'cartes sociales'],
            'tarif': ['tarif', 'tarifs', 'tarif volumétrique', 'tarifs volumétriques'],
            'modalite': ['modalité', 'modalités', 'modalité de gestion', 'modalités de gestion'],
            'fournisseur': ['fournisseur', 'fournisseurs'],
            'commune': ['commune', 'communes'],
            'habitant': ['habitant', 'habitants', 'population'],
        }

        # Patterns de questions pour détecter les demandes de comptage
        self.count_patterns = [
            r'combien\s+(?:de\s+)?(.+)',
            r'nombre\s+(?:de\s+)?(.+)',
            r'total\s+(?:de\s+)?(.+)',
            r'(?:il\s+y\s+a|y\s+a-t-il)\s+combien\s+(?:de\s+)?(.+)',
            r'(?:donne|donner|affiche|afficher|montre|montrer)\s+(?:moi\s+)?(?:le\s+)?(?:nombre|total|combien)\s+(?:de\s+)?(.+)',
        ]

        # Patterns pour les filtres géographiques
        self.filter_patterns = {
            'region': r'(?:dans|en|pour|à)\s+(?:la\s+)?région\s+(.+?)(?:\s|$|,)',
            'district': r'(?:dans|en|pour|à)\s+(?:le\s+)?district\s+(?:de\s+)?(.+?)(?:\s|$|,)',
            'commune': r'(?:dans|en|pour|à)\s+(?:la\s+)?commune\s+(?:de\s+)?(.+?)(?:\s|$|,)',
            'annee': r'(?:en|pour|de)\s+(?:l\')?année\s+(\d{4})',
        }

    def can_handle(self, message: str) -> bool:
        """
        Vérifie si ce gestionnaire peut traiter le message
        """
        message_lower = message.lower()

        # Vérifier si c'est une demande de comptage
        for pattern in self.count_patterns:
            if re.search(pattern, message_lower):
                return True

        # Vérifier si le message mentionne des statistiques
        stats_keywords = ['statistique', 'comptage', 'combien', 'nombre', 'total']
        return any(keyword in message_lower for keyword in stats_keywords)

    def extract_entities(self, message: str) -> List[str]:
        """
        Extrait les entités (types de données) mentionnées dans le message
        """
        message_lower = message.lower()
        entities = []

        for entity_key, variations in self.entity_mappings.items():
            for variation in variations:
                if variation in message_lower:
                    entities.append(entity_key)
                    break

        return list(set(entities))  # Supprimer les doublons

    def extract_filters(self, message: str) -> Dict[str, str]:
        """
        Extrait les filtres géographiques et temporels du message
        """
        filters = {}

        for filter_type, pattern in self.filter_patterns.items():
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                filters[filter_type] = match.group(1).strip()

        return filters

    def get_dashboard_stats(self, filters: Dict[str, str] = None) -> Optional[Dict[str, Any]]:
        """
        Récupère les statistiques depuis l'API dashboard
        """
        try:
            # Construire l'URL avec les filtres
            base_url = 'http://localhost:8000/api/dashboard/'
            params = []

            if filters:
                if 'annee' in filters:
                    params.append(f"annee={filters['annee']}")
                if 'commune_id' in filters:
                    params.append(f"commune_id={filters['commune_id']}")
                elif 'district_id' in filters:
                    params.append(f"district_id={filters['district_id']}")
                elif 'region_id' in filters:
                    params.append(f"region_id={filters['region_id']}")

            url = base_url + ('?' + '&'.join(params) if params else '')

            # Faire la requête
            response = requests.get(url, timeout=5)
            response.raise_for_status()

            return response.json()

        except Exception as e:
            logger.error(f"Erreur lors de la récupération des stats: {e}")
            return None

    def format_number(self, number: int) -> str:
        """
        Formate un nombre pour l'affichage
        """
        return f"{number:,}".replace(',', ' ')

    def generate_response(self, message: str) -> Dict[str, Any]:
        """
        Génère une réponse aux demandes de statistiques
        """
        # Extraire les entités et filtres
        entities = self.extract_entities(message)
        filters = self.extract_filters(message)

        # Récupérer les statistiques
        stats = self.get_dashboard_stats(filters)

        if not stats:
            return {
                'content': "Désolé, je n'ai pas pu récupérer les statistiques pour le moment. Veuillez réessayer.",
                'success': False
            }

        # Générer la réponse en fonction des entités demandées
        response_parts = []
        stats_data = {}

        # Mapping des entités vers les clés de l'API
        entity_to_api_key = {
            'ouvrage': ('ouvrages', 'ouvrages'),
            'point_eau': ('points_eau_total', 'points d\'eau'),
            'point_eau_prive': ('points_eau_prives', 'points d\'eau privés (BP)'),
            'point_eau_public': ('points_eau_publics', 'points d\'eau publics'),
            'point_eau_coupe': ('points_eau_coupes', 'points d\'eau coupés'),
            'equipement': ('equipements', 'équipements constitutifs'),
            'compteur_tete': ('compteurs_tete', 'compteurs de tête'),
            'adresse': ('adresses', 'adresses'),
            'carte_sociale': ('cartes_sociales', 'cartes sociales'),
            'tarif': ('tarifs_volumetriques', 'tarifs volumétriques actifs'),
            'modalite': ('modalites_gestion', 'modalités de gestion actives'),
            'fournisseur': ('fournisseurs', 'fournisseurs actifs'),
            'commune': ('communes', 'communes'),
            'habitant': ('habitants', 'habitants'),
        }

        if entities:
            # Répondre pour chaque entité demandée
            for entity in entities:
                if entity in entity_to_api_key:
                    api_key, display_name = entity_to_api_key[entity]
                    if api_key in stats:
                        count = stats[api_key]
                        response_parts.append(f"• **{self.format_number(count)}** {display_name}")
                        stats_data[entity] = count
        else:
            # Si aucune entité spécifique n'est demandée, donner un résumé
            response_parts.append("Voici un résumé des statistiques :")
            response_parts.append(f"• **{self.format_number(stats.get('ouvrages', 0))}** ouvrages")
            response_parts.append(f"• **{self.format_number(stats.get('points_eau_total', 0))}** points d'eau")
            response_parts.append(f"  - {self.format_number(stats.get('points_eau_prives', 0))} privés (BP)")
            response_parts.append(f"  - {self.format_number(stats.get('points_eau_publics', 0))} publics")
            response_parts.append(f"• **{self.format_number(stats.get('habitants', 0))}** habitants")
            stats_data = stats

        # Ajouter les informations sur les filtres appliqués
        filter_info = []
        if 'region' in filters:
            filter_info.append(f"région {filters['region']}")
        if 'district' in filters:
            filter_info.append(f"district de {filters['district']}")
        if 'commune' in filters:
            filter_info.append(f"commune de {filters['commune']}")
        if 'annee' in filters:
            filter_info.append(f"année {filters['annee']} (cumulé)")

        if filter_info:
            response_parts.insert(0, f"**Filtres appliqués:** {', '.join(filter_info)}\n")

        response_text = "\n".join(response_parts)

        return {
            'content': response_text,
            'metadata': {
                'stats': stats_data,
                'filters': filters,
                'entities': entities
            },
            'success': True
        }


# Fonction utilitaire pour intégrer dans ai_assistant.py
def create_stats_handler():
    """Factory function pour créer une instance du gestionnaire"""
    return StatsHandler()
