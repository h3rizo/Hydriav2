"""
Service pour gérer les requêtes géographiques complexes
Gère les relations Commune → Fokontany → Village → Parcelle
"""
import logging
from typing import Dict, Any, List, Optional
from django.db.models import Sum, Count, Q
from django.core.exceptions import ObjectDoesNotExist

logger = logging.getLogger(__name__)


class GeographyQueries:
    """
    Gère les requêtes sur les données géographiques avec relations complexes
    """

    def __init__(self):
        # Import des modèles ici pour éviter les imports circulaires
        from apps.geography.models import Commune, Fokontany, Village, Parcelle

        self.Commune = Commune
        self.Fokontany = Fokontany
        self.Village = Village
        self.Parcelle = Parcelle

    def can_handle(self, user_message: str) -> bool:
        """
        Vérifie si ce service peut traiter le message
        """
        message_lower = user_message.lower()

        # Mots-clés géographiques
        geo_keywords = [
            'habitants', 'population', 'commune', 'fokontany', 'village',
            'parcelle', 'localité', 'région', 'district'
        ]

        # Mots-clés infrastructure avec contexte géographique
        # Ex: "Combien de points d'eau à Ambato"
        has_geo_location = any(keyword in message_lower for keyword in geo_keywords)
        has_infra_with_location = (
            ('point' in message_lower and 'eau' in message_lower) or
            'ouvrage' in message_lower
        ) and (
            'à' in message_lower or 'a' in message_lower or
            'dans' in message_lower or 'de' in message_lower
        )

        return has_geo_location or has_infra_with_location

    def process_query(self, user_message: str) -> Dict[str, Any]:
        """
        Traite une requête géographique
        """
        message_lower = user_message.lower()

        try:
            # Requête sur les habitants d'une commune
            if 'habitants' in message_lower or 'population' in message_lower:
                return self._handle_population_query(user_message)

            # Requête sur les villages d'une commune (nécessite "village" ET "commune")
            elif 'village' in message_lower and 'commune' in message_lower:
                return self._handle_villages_query(user_message)

            # Requête sur les fokontany d'une commune (nécessite "fokontany" ET "commune")
            elif 'fokontany' in message_lower and 'commune' in message_lower:
                return self._handle_fokontany_query(user_message)

            # Requête sur les communes (d'un district implicite)
            # Ex: "Liste des communes de Ambanja" ou "communes de X"
            elif 'commune' in message_lower and ('liste' in message_lower or 'combien' in message_lower or 'de' in message_lower):
                # Si "district" est explicitement mentionné ou si c'est une demande de liste/comptage
                return self._handle_communes_query(user_message)

            # Requête sur les districts (d'une région implicite)
            # Ex: "Liste des districts de Diana" ou "districts de X"
            elif 'district' in message_lower and ('liste' in message_lower or 'combien' in message_lower or 'de' in message_lower):
                # Si "région" est explicitement mentionné ou si c'est une demande de liste/comptage
                return self._handle_districts_query(user_message)

            # Requête sur les régions (toutes les régions)
            elif ('region' in message_lower or 'région' in message_lower) and ('liste' in message_lower or 'toutes' in message_lower):
                return self._handle_regions_query(user_message)

            # Requête sur les parcelles d'un village
            elif 'parcelle' in message_lower and ('village' in message_lower or 'de' in message_lower):
                return self._handle_parcelles_query(user_message)

            # Requête sur les points d'eau
            elif 'point' in message_lower and 'eau' in message_lower:
                return self._handle_points_eau_query(user_message)

            # Requête sur les ouvrages
            elif 'ouvrage' in message_lower or 'infrastructure' in message_lower:
                return self._handle_ouvrages_query(user_message)

            # Requête générale
            else:
                return self._handle_general_geo_query(user_message)

        except Exception as e:
            logger.error(f"Erreur dans GeographyQueries: {e}")
            return {
                'success': False,
                'response': f"Erreur lors du traitement de votre question : {str(e)}",
                'metadata': {'error': str(e)}
            }

    def _extract_location_name(self, message: str) -> Optional[str]:
        """
        Extrait le nom de la localité depuis le message
        """
        # Patterns communs : "à [Nom]", "de [Nom]", "dans [Nom]"
        import re

        patterns = [
            # Accepter n'importe quel mot qui commence par une majuscule après "à" ou "a", "de", "dans"
            r'[àa]\s+([A-Z][a-zéèêàâôùûïëA-Z]+(?:\s+[A-Z][a-zéèêàâôùûïë]+)*)',
            r'de\s+([A-Z][a-zéèêàâôùûïëA-Z]+(?:\s+[A-Z][a-zéèêàâôùûïë]+)*)',
            r'dans\s+([A-Z][a-zéèêàâôùûïëA-Z]+(?:\s+[A-Z][a-zéèêàâôùûïë]+)*)',
            r'\s([A-Z][a-zéèêàâôùûïëA-Z]+)\s*\?',  # Dernier mot avant ?
        ]

        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                return match.group(1)

        return None

    def _handle_population_query(self, message: str) -> Dict[str, Any]:
        """
        Traite les requêtes sur la population
        Exemple: "Combien d'habitants à Ankazondandy"
        """
        location_name = self._extract_location_name(message)

        if not location_name:
            return {
                'success': False,
                'response': "Je n'ai pas pu identifier le nom de la localité. Pourriez-vous reformuler ? Par exemple : 'Combien d'habitants à Ankazondandy ?'",
                'metadata': {}
            }

        # Chercher d'abord comme commune
        try:
            commune = self.Commune.objects.filter(
                Q(nom_commune__iexact=location_name) |
                Q(nom_commune__icontains=location_name)
            ).first()

            if commune:
                # Calculer la population via les parcelles
                population = self.Parcelle.objects.filter(
                    village__fokontany__commune=commune
                ).aggregate(
                    total=Sum('nombre_habitants')
                )['total'] or 0

                return {
                    'success': True,
                    'response': f"**Population de {commune.nom_commune} :**\n\n" +
                              f"🏘️ **{population:,}** habitants".replace(',', ' '),
                    'metadata': {
                        'type': 'population',
                        'location': commune.nom_commune,
                        'location_type': 'commune',
                        'population': population
                    }
                }

        except Exception as e:
            logger.error(f"Erreur recherche commune: {e}")

        # Chercher comme fokontany
        try:
            fokontany = self.Fokontany.objects.filter(
                Q(nom_fokontany__iexact=location_name) |
                Q(nom_fokontany__icontains=location_name)
            ).first()

            if fokontany:
                population = self.Parcelle.objects.filter(
                    village__fokontany=fokontany
                ).aggregate(
                    total=Sum('nombre_habitants')
                )['total'] or 0

                return {
                    'success': True,
                    'response': f"**Population de {fokontany.nom_fokontany} :**\n\n" +
                              f"🏘️ **{population:,}** habitants\n\n".replace(',', ' ') +
                              f"📍 Commune : {fokontany.commune.nom_commune if fokontany.commune else 'Non renseignée'}",
                    'metadata': {
                        'type': 'population',
                        'location': fokontany.nom_fokontany,
                        'location_type': 'fokontany',
                        'population': population
                    }
                }

        except Exception as e:
            logger.error(f"Erreur recherche fokontany: {e}")

        # Chercher comme village
        try:
            village = self.Village.objects.filter(
                Q(nom_village__iexact=location_name) |
                Q(nom_village__icontains=location_name)
            ).first()

            if village:
                population = self.Parcelle.objects.filter(
                    village=village
                ).aggregate(
                    total=Sum('nombre_habitants')
                )['total'] or 0

                location_info = f"📍 Fokontany : {village.fokontany.nom_fokontany if village.fokontany else 'Non renseigné'}"
                if village.fokontany and village.fokontany.commune:
                    location_info += f"\n📍 Commune : {village.fokontany.commune.nom_commune}"

                return {
                    'success': True,
                    'response': f"**Population de {village.nom_village} :**\n\n" +
                              f"🏘️ **{population:,}** habitants\n\n".replace(',', ' ') +
                              location_info,
                    'metadata': {
                        'type': 'population',
                        'location': village.nom_village,
                        'location_type': 'village',
                        'population': population
                    }
                }

        except Exception as e:
            logger.error(f"Erreur recherche village: {e}")

        # Si aucune localité trouvée
        return {
            'success': False,
            'response': f"Je n'ai pas trouvé de localité nommée '{location_name}' dans la base de données.\n\n" +
                      "**Suggestions :**\n" +
                      "- Vérifiez l'orthographe\n" +
                      "- Essayez avec juste la première partie du nom\n" +
                      "- Cherchez par commune, fokontany ou village",
            'metadata': {
                'searched_location': location_name
            }
        }

    def _handle_villages_query(self, message: str) -> Dict[str, Any]:
        """
        Traite les requêtes sur les villages d'une commune
        """
        location_name = self._extract_location_name(message)

        if not location_name:
            return {
                'success': False,
                'response': "Veuillez préciser le nom de la commune.",
                'metadata': {}
            }

        try:
            commune = self.Commune.objects.filter(
                Q(nom_commune__iexact=location_name) |
                Q(nom_commune__icontains=location_name)
            ).first()

            if not commune:
                return {
                    'success': False,
                    'response': f"Commune '{location_name}' non trouvée.",
                    'metadata': {}
                }

            # Compter les villages via la chaîne de relations
            villages = self.Village.objects.filter(
                fokontany__commune=commune
            ).select_related('fokontany').order_by('nom_village')

            count = villages.count()

            # Lister les premiers villages
            villages_list = "\n".join([
                f"  • {v.nom_village} ({v.fokontany.nom_fokontany if v.fokontany else 'Fokontany non renseigné'})"
                for v in villages[:10]
            ])

            more_text = f"\n\n... et {count - 10} autres villages" if count > 10 else ""

            return {
                'success': True,
                'response': f"**Villages de la commune de {commune.nom_commune} :**\n\n" +
                          f"📊 Total : **{count}** village{'s' if count > 1 else ''}\n\n" +
                          f"**Liste :**\n{villages_list}{more_text}",
                'metadata': {
                    'type': 'villages',
                    'commune': commune.nom_commune,
                    'count': count
                }
            }

        except Exception as e:
            logger.error(f"Erreur villages query: {e}")
            return {
                'success': False,
                'response': f"Erreur : {str(e)}",
                'metadata': {'error': str(e)}
            }

    def _handle_fokontany_query(self, message: str) -> Dict[str, Any]:
        """
        Traite les requêtes sur les fokontany d'une commune
        """
        location_name = self._extract_location_name(message)

        if not location_name:
            return {
                'success': False,
                'response': "Veuillez préciser le nom de la commune.",
                'metadata': {}
            }

        try:
            commune = self.Commune.objects.filter(
                Q(nom_commune__iexact=location_name) |
                Q(nom_commune__icontains=location_name)
            ).first()

            if not commune:
                return {
                    'success': False,
                    'response': f"Commune '{location_name}' non trouvée.",
                    'metadata': {}
                }

            fokontany_list = self.Fokontany.objects.filter(
                commune=commune
            ).order_by('nom_fokontany')

            count = fokontany_list.count()

            fokontany_items = "\n".join([
                f"  • {f.nom_fokontany}"
                for f in fokontany_list
            ])

            return {
                'success': True,
                'response': f"**Fokontany de la commune de {commune.nom_commune} :**\n\n" +
                          f"📊 Total : **{count}** fokontany\n\n" +
                          f"**Liste :**\n{fokontany_items}",
                'metadata': {
                    'type': 'fokontany',
                    'commune': commune.nom_commune,
                    'count': count
                }
            }

        except Exception as e:
            logger.error(f"Erreur fokontany query: {e}")
            return {
                'success': False,
                'response': f"Erreur : {str(e)}",
                'metadata': {'error': str(e)}
            }

    def _handle_communes_query(self, message: str) -> Dict[str, Any]:
        """
        Traite les requêtes sur les communes d'un district
        """
        location_name = self._extract_location_name(message)

        if not location_name:
            return {
                'success': False,
                'response': "Veuillez préciser le nom du district.",
                'metadata': {}
            }

        try:
            # Chercher le district
            from apps.geography.models import District

            district = District.objects.filter(
                Q(nom_district__iexact=location_name) |
                Q(nom_district__icontains=location_name)
            ).first()

            if not district:
                return {
                    'success': False,
                    'response': f"District '{location_name}' non trouvé.",
                    'metadata': {}
                }

            # Lister les communes du district
            communes_list = self.Commune.objects.filter(
                district=district
            ).order_by('nom_commune')

            count = communes_list.count()

            communes_items = "\n".join([
                f"  • {c.nom_commune}"
                for c in communes_list
            ])

            return {
                'success': True,
                'response': f"**Communes du district de {district.nom_district} :**\n\n" +
                          f"📊 Total : **{count}** commune{'s' if count > 1 else ''}\\n\n" +
                          f"**Liste :**\n{communes_items}",
                'metadata': {
                    'type': 'communes',
                    'district': district.nom_district,
                    'count': count
                }
            }

        except Exception as e:
            logger.error(f"Erreur communes query: {e}")
            return {
                'success': False,
                'response': f"Erreur : {str(e)}",
                'metadata': {'error': str(e)}
            }

    def _handle_districts_query(self, message: str) -> Dict[str, Any]:
        """
        Traite les requêtes sur les districts d'une région
        """
        location_name = self._extract_location_name(message)

        if not location_name:
            return {
                'success': False,
                'response': "Veuillez préciser le nom de la région.",
                'metadata': {}
            }

        try:
            # Chercher la région
            from apps.geography.models import Region, District

            region = Region.objects.filter(
                Q(nom_region__iexact=location_name) |
                Q(nom_region__icontains=location_name)
            ).first()

            if not region:
                return {
                    'success': False,
                    'response': f"Région '{location_name}' non trouvée.",
                    'metadata': {}
                }

            # Lister les districts de la région
            districts_list = District.objects.filter(
                region=region
            ).order_by('nom_district')

            count = districts_list.count()

            districts_items = "\n".join([
                f"  • {d.nom_district}"
                for d in districts_list
            ])

            return {
                'success': True,
                'response': f"**Districts de la région {region.nom_region} :**\n\n" +
                          f"📊 Total : **{count}** district{'s' if count > 1 else ''}\\n\n" +
                          f"**Liste :**\n{districts_items}",
                'metadata': {
                    'type': 'districts',
                    'region': region.nom_region,
                    'count': count
                }
            }

        except Exception as e:
            logger.error(f"Erreur districts query: {e}")
            return {
                'success': False,
                'response': f"Erreur : {str(e)}",
                'metadata': {'error': str(e)}
            }

    def _handle_regions_query(self, message: str) -> Dict[str, Any]:
        """
        Traite les requêtes sur les régions
        """
        try:
            from apps.geography.models import Region

            # Lister toutes les régions
            regions_list = Region.objects.all().order_by('nom_region')

            count = regions_list.count()

            regions_items = "\n".join([
                f"  • {r.nom_region}"
                for r in regions_list
            ])

            return {
                'success': True,
                'response': f"**Régions disponibles :**\n\n" +
                          f"📊 Total : **{count}** région{'s' if count > 1 else ''}\\n\n" +
                          f"**Liste :**\n{regions_items}",
                'metadata': {
                    'type': 'regions',
                    'count': count
                }
            }

        except Exception as e:
            logger.error(f"Erreur regions query: {e}")
            return {
                'success': False,
                'response': f"Erreur : {str(e)}",
                'metadata': {'error': str(e)}
            }

    def _handle_parcelles_query(self, message: str) -> Dict[str, Any]:
        """
        Traite les requêtes sur les parcelles d'un village
        """
        location_name = self._extract_location_name(message)

        if not location_name:
            return {
                'success': False,
                'response': "Veuillez préciser le nom du village.",
                'metadata': {}
            }

        try:
            # Chercher le village
            village = self.Village.objects.filter(
                Q(nom_village__iexact=location_name) |
                Q(nom_village__icontains=location_name)
            ).first()

            if not village:
                return {
                    'success': False,
                    'response': f"Village '{location_name}' non trouvé.",
                    'metadata': {}
                }

            # Compter les parcelles
            count = self.Parcelle.objects.filter(village=village).count()

            location_info = f"📍 Fokontany : {village.fokontany.nom_fokontany if village.fokontany else 'Non renseigné'}"
            if village.fokontany and village.fokontany.commune:
                location_info += f"\n📍 Commune : {village.fokontany.commune.nom_commune}"

            return {
                'success': True,
                'response': f"**Parcelles de {village.nom_village} :**\n\n" +
                          f"📊 Total : **{count}** parcelle{'s' if count > 1 else ''}\\n\n" +
                          location_info,
                'metadata': {
                    'type': 'parcelles',
                    'village': village.nom_village,
                    'count': count
                }
            }

        except Exception as e:
            logger.error(f"Erreur parcelles query: {e}")
            return {
                'success': False,
                'response': f"Erreur : {str(e)}",
                'metadata': {'error': str(e)}
            }

    def _handle_points_eau_query(self, message: str) -> Dict[str, Any]:
        """
        Traite les requêtes sur les points d'eau
        """
        location_name = self._extract_location_name(message)

        if not location_name:
            return {
                'success': False,
                'response': "Veuillez préciser le nom de la localité (commune, fokontany ou village).",
                'metadata': {}
            }

        # Vérifier si l'utilisateur demande les détails
        message_lower = message.lower()
        wants_details = any(keyword in message_lower for keyword in ['détail', 'detail', 'par ouvrage', 'liste', 'tous'])

        try:
            from apps.billing.models import PointEau
            from apps.organization.models import Ouvrage

            # Chercher d'abord comme commune
            commune = self.Commune.objects.filter(
                Q(nom_commune__iexact=location_name) |
                Q(nom_commune__icontains=location_name)
            ).first()

            if commune:
                points_eau = PointEau.objects.filter(
                    parcelle__village__fokontany__commune=commune
                ).select_related('ouvrage', 'ouvrage__type_ouvrage')

                count = points_eau.count()

                # Si détails demandés, grouper par ouvrage
                if wants_details:
                    # Grouper par ouvrage
                    ouvrages_dict = {}
                    for pe in points_eau:
                        if pe.ouvrage:
                            ouvrage_key = f"{pe.ouvrage.nom_ouvrage} ({pe.ouvrage.type_ouvrage.nom_type_ouvrage if pe.ouvrage.type_ouvrage else 'Type non renseigné'})"
                            if ouvrage_key not in ouvrages_dict:
                                ouvrages_dict[ouvrage_key] = 0
                            ouvrages_dict[ouvrage_key] += 1
                        else:
                            if 'Sans ouvrage' not in ouvrages_dict:
                                ouvrages_dict['Sans ouvrage'] = 0
                            ouvrages_dict['Sans ouvrage'] += 1

                    # Trier par nombre décroissant
                    ouvrages_sorted = sorted(ouvrages_dict.items(), key=lambda x: x[1], reverse=True)

                    # Construire la liste détaillée
                    details_list = "\n".join([
                        f"  • **{ouvrage}** : {nb} point{'s' if nb > 1 else ''} d'eau"
                        for ouvrage, nb in ouvrages_sorted
                    ])

                    return {
                        'success': True,
                        'response': f"**Points d'eau de {commune.nom_commune} - Détail par ouvrage :**\n\n" +
                                  f"📊 **Total : {count}** point{'s' if count > 1 else ''} d'eau\n" +
                                  f"🏗️ **{len(ouvrages_sorted)}** ouvrage{'s' if len(ouvrages_sorted) > 1 else ''}\n\n" +
                                  f"**Répartition :**\n{details_list}",
                        'metadata': {
                            'type': 'points_eau_details',
                            'location': commune.nom_commune,
                            'location_type': 'commune',
                            'count': count,
                            'ouvrages_count': len(ouvrages_sorted),
                            'details': dict(ouvrages_sorted)
                        }
                    }
                else:
                    # Réponse simple
                    return {
                        'success': True,
                        'response': f"**Points d'eau de {commune.nom_commune} :**\n\n" +
                                  f"💧 **{count}** point{'s' if count > 1 else ''} d'eau",
                        'metadata': {
                            'type': 'points_eau',
                            'location': commune.nom_commune,
                            'location_type': 'commune',
                            'count': count
                        }
                    }

            # Chercher comme fokontany
            fokontany = self.Fokontany.objects.filter(
                Q(nom_fokontany__iexact=location_name) |
                Q(nom_fokontany__icontains=location_name)
            ).first()

            if fokontany:
                points_eau = PointEau.objects.filter(
                    parcelle__village__fokontany=fokontany
                ).select_related('ouvrage', 'ouvrage__type_ouvrage')

                count = points_eau.count()

                # Si détails demandés, grouper par ouvrage
                if wants_details:
                    # Grouper par ouvrage
                    ouvrages_dict = {}
                    for pe in points_eau:
                        if pe.ouvrage:
                            ouvrage_key = f"{pe.ouvrage.nom_ouvrage} ({pe.ouvrage.type_ouvrage.nom_type_ouvrage if pe.ouvrage.type_ouvrage else 'Type non renseigné'})"
                            if ouvrage_key not in ouvrages_dict:
                                ouvrages_dict[ouvrage_key] = 0
                            ouvrages_dict[ouvrage_key] += 1
                        else:
                            if 'Sans ouvrage' not in ouvrages_dict:
                                ouvrages_dict['Sans ouvrage'] = 0
                            ouvrages_dict['Sans ouvrage'] += 1

                    # Trier par nombre décroissant
                    ouvrages_sorted = sorted(ouvrages_dict.items(), key=lambda x: x[1], reverse=True)

                    # Construire la liste détaillée
                    details_list = "\n".join([
                        f"  • **{ouvrage}** : {nb} point{'s' if nb > 1 else ''} d'eau"
                        for ouvrage, nb in ouvrages_sorted
                    ])

                    return {
                        'success': True,
                        'response': f"**Points d'eau de {fokontany.nom_fokontany} - Détail par ouvrage :**\n\n" +
                                  f"📊 **Total : {count}** point{'s' if count > 1 else ''} d'eau\n" +
                                  f"🏗️ **{len(ouvrages_sorted)}** ouvrage{'s' if len(ouvrages_sorted) > 1 else ''}\n" +
                                  f"📍 Commune : {fokontany.commune.nom_commune if fokontany.commune else 'Non renseignée'}\n\n" +
                                  f"**Répartition :**\n{details_list}",
                        'metadata': {
                            'type': 'points_eau_details',
                            'location': fokontany.nom_fokontany,
                            'location_type': 'fokontany',
                            'count': count,
                            'ouvrages_count': len(ouvrages_sorted),
                            'details': dict(ouvrages_sorted)
                        }
                    }
                else:
                    # Réponse simple
                    return {
                        'success': True,
                        'response': f"**Points d'eau de {fokontany.nom_fokontany} :**\n\n" +
                                  f"💧 **{count}** point{'s' if count > 1 else ''} d'eau\n\n" +
                                  f"📍 Commune : {fokontany.commune.nom_commune if fokontany.commune else 'Non renseignée'}",
                        'metadata': {
                            'type': 'points_eau',
                            'location': fokontany.nom_fokontany,
                            'location_type': 'fokontany',
                            'count': count
                        }
                    }

            # Chercher comme village
            village = self.Village.objects.filter(
                Q(nom_village__iexact=location_name) |
                Q(nom_village__icontains=location_name)
            ).first()

            if village:
                points_eau = PointEau.objects.filter(
                    parcelle__village=village
                ).select_related('ouvrage', 'ouvrage__type_ouvrage')

                count = points_eau.count()

                location_info = f"📍 Fokontany : {village.fokontany.nom_fokontany if village.fokontany else 'Non renseigné'}"
                if village.fokontany and village.fokontany.commune:
                    location_info += f"\n📍 Commune : {village.fokontany.commune.nom_commune}"

                # Si détails demandés, grouper par ouvrage
                if wants_details:
                    # Grouper par ouvrage
                    ouvrages_dict = {}
                    for pe in points_eau:
                        if pe.ouvrage:
                            ouvrage_key = f"{pe.ouvrage.nom_ouvrage} ({pe.ouvrage.type_ouvrage.nom_type_ouvrage if pe.ouvrage.type_ouvrage else 'Type non renseigné'})"
                            if ouvrage_key not in ouvrages_dict:
                                ouvrages_dict[ouvrage_key] = 0
                            ouvrages_dict[ouvrage_key] += 1
                        else:
                            if 'Sans ouvrage' not in ouvrages_dict:
                                ouvrages_dict['Sans ouvrage'] = 0
                            ouvrages_dict['Sans ouvrage'] += 1

                    # Trier par nombre décroissant
                    ouvrages_sorted = sorted(ouvrages_dict.items(), key=lambda x: x[1], reverse=True)

                    # Construire la liste détaillée
                    details_list = "\n".join([
                        f"  • **{ouvrage}** : {nb} point{'s' if nb > 1 else ''} d'eau"
                        for ouvrage, nb in ouvrages_sorted
                    ])

                    return {
                        'success': True,
                        'response': f"**Points d'eau de {village.nom_village} - Détail par ouvrage :**\n\n" +
                                  f"📊 **Total : {count}** point{'s' if count > 1 else ''} d'eau\n" +
                                  f"🏗️ **{len(ouvrages_sorted)}** ouvrage{'s' if len(ouvrages_sorted) > 1 else ''}\n" +
                                  location_info + "\n\n" +
                                  f"**Répartition :**\n{details_list}",
                        'metadata': {
                            'type': 'points_eau_details',
                            'location': village.nom_village,
                            'location_type': 'village',
                            'count': count,
                            'ouvrages_count': len(ouvrages_sorted),
                            'details': dict(ouvrages_sorted)
                        }
                    }
                else:
                    # Réponse simple
                    return {
                        'success': True,
                        'response': f"**Points d'eau de {village.nom_village} :**\n\n" +
                                  f"💧 **{count}** point{'s' if count > 1 else ''} d'eau\n\n" +
                                  location_info,
                        'metadata': {
                            'type': 'points_eau',
                            'location': village.nom_village,
                            'location_type': 'village',
                            'count': count
                        }
                    }

            # Si aucune localité trouvée
            return {
                'success': False,
                'response': f"Je n'ai pas trouvé de localité nommée '{location_name}' dans la base de données.",
                'metadata': {
                    'searched_location': location_name
                }
            }

        except Exception as e:
            logger.error(f"Erreur points eau query: {e}")
            return {
                'success': False,
                'response': f"Erreur : {str(e)}",
                'metadata': {'error': str(e)}
            }

    def _handle_ouvrages_query(self, message: str) -> Dict[str, Any]:
        """
        Traite les requêtes sur les ouvrages/infrastructures
        """
        location_name = self._extract_location_name(message)

        if not location_name:
            return {
                'success': False,
                'response': "Veuillez préciser le nom de la localité (commune, fokontany ou village).",
                'metadata': {}
            }

        try:
            from apps.organization.models import Ouvrage

            # Chercher d'abord comme commune
            commune = self.Commune.objects.filter(
                Q(nom_commune__iexact=location_name) |
                Q(nom_commune__icontains=location_name)
            ).first()

            if commune:
                count = Ouvrage.objects.filter(
                    pointeau__parcelle__village__fokontany__commune=commune
                ).distinct().count()

                return {
                    'success': True,
                    'response': f"**Ouvrages de {commune.nom_commune} :**\n\n" +
                              f"🏗️ **{count}** ouvrage{'s' if count > 1 else ''}",
                    'metadata': {
                        'type': 'ouvrages',
                        'location': commune.nom_commune,
                        'location_type': 'commune',
                        'count': count
                    }
                }

            # Chercher comme fokontany
            fokontany = self.Fokontany.objects.filter(
                Q(nom_fokontany__iexact=location_name) |
                Q(nom_fokontany__icontains=location_name)
            ).first()

            if fokontany:
                count = Ouvrage.objects.filter(
                    pointeau__parcelle__village__fokontany=fokontany
                ).distinct().count()

                return {
                    'success': True,
                    'response': f"**Ouvrages de {fokontany.nom_fokontany} :**\n\n" +
                              f"🏗️ **{count}** ouvrage{'s' if count > 1 else ''}\\n\n" +
                              f"📍 Commune : {fokontany.commune.nom_commune if fokontany.commune else 'Non renseignée'}",
                    'metadata': {
                        'type': 'ouvrages',
                        'location': fokontany.nom_fokontany,
                        'location_type': 'fokontany',
                        'count': count
                    }
                }

            # Chercher comme village
            village = self.Village.objects.filter(
                Q(nom_village__iexact=location_name) |
                Q(nom_village__icontains=location_name)
            ).first()

            if village:
                count = Ouvrage.objects.filter(
                    pointeau__parcelle__village=village
                ).distinct().count()

                location_info = f"📍 Fokontany : {village.fokontany.nom_fokontany if village.fokontany else 'Non renseigné'}"
                if village.fokontany and village.fokontany.commune:
                    location_info += f"\n📍 Commune : {village.fokontany.commune.nom_commune}"

                return {
                    'success': True,
                    'response': f"**Ouvrages de {village.nom_village} :**\n\n" +
                              f"🏗️ **{count}** ouvrage{'s' if count > 1 else ''}\\n\n" +
                              location_info,
                    'metadata': {
                        'type': 'ouvrages',
                        'location': village.nom_village,
                        'location_type': 'village',
                        'count': count
                    }
                }

            # Si aucune localité trouvée
            return {
                'success': False,
                'response': f"Je n'ai pas trouvé de localité nommée '{location_name}' dans la base de données.",
                'metadata': {
                    'searched_location': location_name
                }
            }

        except Exception as e:
            logger.error(f"Erreur ouvrages query: {e}")
            return {
                'success': False,
                'response': f"Erreur : {str(e)}",
                'metadata': {'error': str(e)}
            }

    def _handle_general_geo_query(self, message: str) -> Dict[str, Any]:
        """
        Traite les requêtes géographiques générales
        """
        return {
            'success': True,
            'response': """**Questions géographiques disponibles :**

🏘️ **Population :**
- "Combien d'habitants à [Nom de commune/fokontany/village] ?"

🏘️ **Villages :**
- "Combien de villages dans [Nom de commune] ?"
- "Liste des villages de [Nom de commune]"

📍 **Fokontany :**
- "Combien de fokontany dans [Nom de commune] ?"
- "Liste des fokontany de [Nom de commune]"

🏛️ **Communes :**
- "Combien de communes dans [Nom de district] ?"
- "Liste des communes de [Nom de district]"

📍 **Districts :**
- "Combien de districts dans [Nom de région] ?"
- "Liste des districts de [Nom de région]"

🗺️ **Régions :**
- "Liste des régions"

📦 **Parcelles :**
- "Combien de parcelles dans [Nom de village] ?"

💧 **Points d'eau :**
- "Combien de points d'eau à [Nom de commune/fokontany/village] ?"

🏗️ **Ouvrages :**
- "Combien d'ouvrages à [Nom de commune/fokontany/village] ?"

**Exemple :** "Combien d'habitants à Ankazondandy ?" """,
            'metadata': {
                'type': 'help',
                'category': 'geography'
            }
        }
