"""
Service pour gérer les requêtes sur les infrastructures
Gère les relations Ouvrage → Équipement → PointEau → Parcelle
"""
import logging
from typing import Dict, Any, List, Optional
from django.db.models import Count, Q
from django.core.exceptions import ObjectDoesNotExist

logger = logging.getLogger(__name__)


class InfrastructureQueries:
    """
    Gère les requêtes sur les infrastructures (ouvrages, équipements, points d'eau)
    """

    def __init__(self):
        # Import des modèles ici pour éviter les imports circulaires
        from apps.organization.models import Ouvrage, TypeOuvrage
        from apps.infrastructure.models import EquipementConstitutif, TypeEquipement
        from apps.billing.models import PointEau, TypePointEau
        from apps.billing.models import CompteurTete, ModaliteGestion

        self.Ouvrage = Ouvrage
        self.TypeOuvrage = TypeOuvrage
        self.EquipementConstitutif = EquipementConstitutif
        self.TypeEquipement = TypeEquipement
        self.PointEau = PointEau
        self.TypePointEau = TypePointEau
        self.CompteurTete = CompteurTete
        self.ModaliteGestion = ModaliteGestion

    def can_handle(self, user_message: str) -> bool:
        """
        Vérifie si ce service peut traiter le message
        """
        message_lower = user_message.lower()

        # Mots-clés d'infrastructure
        infra_keywords = [
            'équipement', 'equipement', 'compteur', 'modalité', 'modalite',
            'gestion', 'tarif', 'type ouvrage', 'type point', 'type équipement'
        ]

        # Vérifier si c'est une requête sur les types (haute priorité)
        is_types_query = (
            'type' in message_lower and
            ('liste' in message_lower or 'tous' in message_lower or 'toutes' in message_lower or 'quels' in message_lower)
        )

        # Vérifier si le message mentionne un ouvrage ou un point d'eau avec une question sur l'infrastructure
        has_infra_keyword = any(keyword in message_lower for keyword in infra_keywords)
        has_ouvrage_ref = 'ouvrage' in message_lower
        has_point_eau_ref = 'point d\'eau' in message_lower or 'point eau' in message_lower

        return is_types_query or has_infra_keyword or (has_ouvrage_ref and ('type' in message_lower or 'équipement' in message_lower or 'equipement' in message_lower))

    def process_query(self, user_message: str) -> Dict[str, Any]:
        """
        Traite une requête sur les infrastructures
        """
        message_lower = user_message.lower()

        try:
            # Requête générale sur les types (priorité haute car plus spécifique)
            if 'type' in message_lower and ('liste' in message_lower or 'tous' in message_lower or 'toutes' in message_lower or 'quels' in message_lower):
                return self._handle_types_query(user_message)

            # Requête sur les équipements d'un ouvrage
            elif ('équipement' in message_lower or 'equipement' in message_lower) and 'ouvrage' in message_lower:
                return self._handle_equipements_ouvrage_query(user_message)

            # Requête sur les points d'eau d'un ouvrage
            elif 'point' in message_lower and 'eau' in message_lower and 'ouvrage' in message_lower:
                return self._handle_points_eau_ouvrage_query(user_message)

            # Requête sur le type d'un ouvrage spécifique (avec nom d'ouvrage)
            elif 'type' in message_lower and 'ouvrage' in message_lower:
                # Vérifier si un nom d'ouvrage est mentionné
                ouvrage_name = self._extract_ouvrage_name(user_message)
                if ouvrage_name:
                    return self._handle_type_ouvrage_query(user_message)
                else:
                    # Sinon, c'est une demande de liste de types
                    return self._handle_types_query(user_message)

            # Requête sur les ouvrages avec compteur de tête
            elif 'compteur' in message_lower and ('tête' in message_lower or 'tete' in message_lower):
                return self._handle_ouvrages_compteur_query(user_message)

            # Requête sur la modalité de gestion d'un ouvrage
            elif ('modalité' in message_lower or 'modalite' in message_lower) and 'ouvrage' in message_lower:
                return self._handle_modalite_ouvrage_query(user_message)

            # Requête générale
            else:
                return self._handle_general_infra_query(user_message)

        except Exception as e:
            logger.error(f"Erreur dans InfrastructureQueries: {e}")
            return {
                'success': False,
                'response': f"Erreur lors du traitement de votre question : {str(e)}",
                'metadata': {'error': str(e)}
            }

    def _extract_ouvrage_name(self, message: str) -> Optional[str]:
        """
        Extrait le nom de l'ouvrage depuis le message
        """
        import re

        patterns = [
            r'ouvrage\s+([A-Z][a-zéèêàâôùûïëA-Z0-9\s-]+)',
            r'de\s+l\'ouvrage\s+([A-Z][a-zéèêàâôùûïëA-Z0-9\s-]+)',
            r'pour\s+l\'ouvrage\s+([A-Z][a-zéèêàâôùûïëA-Z0-9\s-]+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                return match.group(1).strip()

        return None

    def _handle_equipements_ouvrage_query(self, message: str) -> Dict[str, Any]:
        """
        Traite les requêtes sur les équipements d'un ouvrage
        """
        ouvrage_name = self._extract_ouvrage_name(message)

        if not ouvrage_name:
            return {
                'success': False,
                'response': "Veuillez préciser le nom de l'ouvrage.",
                'metadata': {}
            }

        try:
            # Chercher l'ouvrage
            ouvrage = self.Ouvrage.objects.filter(
                Q(nom_ouvrage__iexact=ouvrage_name) |
                Q(nom_ouvrage__icontains=ouvrage_name)
            ).first()

            if not ouvrage:
                return {
                    'success': False,
                    'response': f"Ouvrage '{ouvrage_name}' non trouvé.",
                    'metadata': {}
                }

            # Lister les équipements
            equipements = self.EquipementConstitutif.objects.filter(
                ouvrage=ouvrage
            ).select_related('type_equipement').order_by('type_equipement__nom_type_equipement')

            count = equipements.count()

            if count == 0:
                return {
                    'success': True,
                    'response': f"**Équipements de l'ouvrage {ouvrage.nom_ouvrage} :**\n\n" +
                              "Aucun équipement enregistré.",
                    'metadata': {
                        'type': 'equipements_ouvrage',
                        'ouvrage': ouvrage.nom_ouvrage,
                        'count': 0
                    }
                }

            # Grouper par type d'équipement
            equipements_by_type = {}
            for equip in equipements:
                type_nom = equip.type_equipement.nom_type_equipement if equip.type_equipement else 'Type non défini'
                if type_nom not in equipements_by_type:
                    equipements_by_type[type_nom] = []
                equipements_by_type[type_nom].append(equip)

            equipements_list = ""
            for type_nom, equips in sorted(equipements_by_type.items()):
                equipements_list += f"\n**{type_nom}** ({len(equips)}) :\n"
                for eq in equips:
                    equipements_list += f"  • {eq.nom_equipement}\n"

            return {
                'success': True,
                'response': f"**Équipements de l'ouvrage {ouvrage.nom_ouvrage} :**\n\n" +
                          f"📊 Total : **{count}** équipement{'s' if count > 1 else ''}\n" +
                          equipements_list,
                'metadata': {
                    'type': 'equipements_ouvrage',
                    'ouvrage': ouvrage.nom_ouvrage,
                    'count': count,
                    'types': list(equipements_by_type.keys())
                }
            }

        except Exception as e:
            logger.error(f"Erreur equipements ouvrage query: {e}")
            return {
                'success': False,
                'response': f"Erreur : {str(e)}",
                'metadata': {'error': str(e)}
            }

    def _handle_points_eau_ouvrage_query(self, message: str) -> Dict[str, Any]:
        """
        Traite les requêtes sur les points d'eau d'un ouvrage
        """
        ouvrage_name = self._extract_ouvrage_name(message)

        if not ouvrage_name:
            return {
                'success': False,
                'response': "Veuillez préciser le nom de l'ouvrage.",
                'metadata': {}
            }

        try:
            # Chercher l'ouvrage
            ouvrage = self.Ouvrage.objects.filter(
                Q(nom_ouvrage__iexact=ouvrage_name) |
                Q(nom_ouvrage__icontains=ouvrage_name)
            ).first()

            if not ouvrage:
                return {
                    'success': False,
                    'response': f"Ouvrage '{ouvrage_name}' non trouvé.",
                    'metadata': {}
                }

            # Lister les points d'eau
            points_eau = self.PointEau.objects.filter(
                ouvrage=ouvrage
            ).select_related('type_point_eau', 'parcelle__village').order_by('nom_point_eau')

            count = points_eau.count()

            if count == 0:
                return {
                    'success': True,
                    'response': f"**Points d'eau de l'ouvrage {ouvrage.nom_ouvrage} :**\n\n" +
                              "Aucun point d'eau enregistré.",
                    'metadata': {
                        'type': 'points_eau_ouvrage',
                        'ouvrage': ouvrage.nom_ouvrage,
                        'count': 0
                    }
                }

            # Grouper par type de point d'eau
            points_by_type = {}
            for pe in points_eau:
                type_nom = pe.type_point_eau.nom_type_point_eau if pe.type_point_eau else 'Type non défini'
                if type_nom not in points_by_type:
                    points_by_type[type_nom] = []
                village_nom = pe.parcelle.village.nom_village if pe.parcelle and pe.parcelle.village else 'Village non renseigné'
                points_by_type[type_nom].append({'nom': pe.nom_point_eau, 'village': village_nom})

            points_list = ""
            for type_nom, points in sorted(points_by_type.items()):
                points_list += f"\n**{type_nom}** ({len(points)}) :\n"
                for pt in points[:10]:  # Limiter à 10 pour éviter trop de texte
                    points_list += f"  • {pt['nom']} ({pt['village']})\n"
                if len(points) > 10:
                    points_list += f"  ... et {len(points) - 10} autres\n"

            return {
                'success': True,
                'response': f"**Points d'eau de l'ouvrage {ouvrage.nom_ouvrage} :**\n\n" +
                          f"📊 Total : **{count}** point{'s' if count > 1 else ''} d'eau\n" +
                          points_list,
                'metadata': {
                    'type': 'points_eau_ouvrage',
                    'ouvrage': ouvrage.nom_ouvrage,
                    'count': count,
                    'types': list(points_by_type.keys())
                }
            }

        except Exception as e:
            logger.error(f"Erreur points eau ouvrage query: {e}")
            return {
                'success': False,
                'response': f"Erreur : {str(e)}",
                'metadata': {'error': str(e)}
            }

    def _handle_type_ouvrage_query(self, message: str) -> Dict[str, Any]:
        """
        Traite les requêtes sur le type d'un ouvrage
        """
        ouvrage_name = self._extract_ouvrage_name(message)

        if not ouvrage_name:
            return {
                'success': False,
                'response': "Veuillez préciser le nom de l'ouvrage.",
                'metadata': {}
            }

        try:
            # Chercher l'ouvrage
            ouvrage = self.Ouvrage.objects.filter(
                Q(nom_ouvrage__iexact=ouvrage_name) |
                Q(nom_ouvrage__icontains=ouvrage_name)
            ).select_related('type_ouvrage').first()

            if not ouvrage:
                return {
                    'success': False,
                    'response': f"Ouvrage '{ouvrage_name}' non trouvé.",
                    'metadata': {}
                }

            type_nom = ouvrage.type_ouvrage.nom_type_ouvrage if ouvrage.type_ouvrage else 'Type non défini'

            return {
                'success': True,
                'response': f"**Type de l'ouvrage {ouvrage.nom_ouvrage} :**\n\n" +
                          f"🏗️ {type_nom}",
                'metadata': {
                    'type': 'type_ouvrage',
                    'ouvrage': ouvrage.nom_ouvrage,
                    'type_ouvrage': type_nom
                }
            }

        except Exception as e:
            logger.error(f"Erreur type ouvrage query: {e}")
            return {
                'success': False,
                'response': f"Erreur : {str(e)}",
                'metadata': {'error': str(e)}
            }

    def _handle_ouvrages_compteur_query(self, message: str) -> Dict[str, Any]:
        """
        Traite les requêtes sur les ouvrages avec compteur de tête
        """
        try:
            # Récupérer les ouvrages avec compteur de tête
            ouvrages_with_compteur = self.Ouvrage.objects.filter(
                compteurs_tete__isnull=False
            ).distinct().select_related('type_ouvrage')

            count = ouvrages_with_compteur.count()

            if count == 0:
                return {
                    'success': True,
                    'response': "Aucun ouvrage avec compteur de tête enregistré.",
                    'metadata': {
                        'type': 'ouvrages_compteur',
                        'count': 0
                    }
                }

            ouvrages_list = "\n".join([
                f"  • {o.nom_ouvrage} ({o.type_ouvrage.nom_type_ouvrage if o.type_ouvrage else 'Type non défini'})"
                for o in ouvrages_with_compteur[:20]
            ])

            more_text = f"\n... et {count - 20} autres" if count > 20 else ""

            return {
                'success': True,
                'response': f"**Ouvrages avec compteur de tête :**\n\n" +
                          f"📊 Total : **{count}** ouvrage{'s' if count > 1 else ''}\n\n" +
                          f"**Liste :**\n{ouvrages_list}{more_text}",
                'metadata': {
                    'type': 'ouvrages_compteur',
                    'count': count
                }
            }

        except Exception as e:
            logger.error(f"Erreur ouvrages compteur query: {e}")
            return {
                'success': False,
                'response': f"Erreur : {str(e)}",
                'metadata': {'error': str(e)}
            }

    def _handle_modalite_ouvrage_query(self, message: str) -> Dict[str, Any]:
        """
        Traite les requêtes sur la modalité de gestion d'un ouvrage
        """
        ouvrage_name = self._extract_ouvrage_name(message)

        if not ouvrage_name:
            return {
                'success': False,
                'response': "Veuillez préciser le nom de l'ouvrage.",
                'metadata': {}
            }

        try:
            # Chercher l'ouvrage
            ouvrage = self.Ouvrage.objects.filter(
                Q(nom_ouvrage__iexact=ouvrage_name) |
                Q(nom_ouvrage__icontains=ouvrage_name)
            ).first()

            if not ouvrage:
                return {
                    'success': False,
                    'response': f"Ouvrage '{ouvrage_name}' non trouvé.",
                    'metadata': {}
                }

            # Récupérer la modalité de gestion active
            modalite = self.ModaliteGestion.objects.filter(
                ouvrage=ouvrage,
                date_fin__isnull=True  # Modalité active
            ).select_related('gestionnaire').first()

            if not modalite:
                return {
                    'success': True,
                    'response': f"**Modalité de gestion de l'ouvrage {ouvrage.nom_ouvrage} :**\n\n" +
                              "Aucune modalité de gestion active.",
                    'metadata': {
                        'type': 'modalite_ouvrage',
                        'ouvrage': ouvrage.nom_ouvrage,
                        'has_modalite': False
                    }
                }

            gestionnaire_nom = modalite.gestionnaire.nom if modalite.gestionnaire else 'Non défini'
            modalite_type = modalite.get_modalitepaiement_display() if hasattr(modalite, 'get_modalitepaiement_display') else modalite.modalitepaiement

            response_text = f"**Modalité de gestion de l'ouvrage {ouvrage.nom_ouvrage} :**\n\n"
            response_text += f"🏢 Gestionnaire : {gestionnaire_nom}\n"
            response_text += f"💰 Type de paiement : {modalite_type}\n"
            if modalite.date_debut:
                response_text += f"📅 Date de début : {modalite.date_debut.strftime('%d/%m/%Y')}\n"

            return {
                'success': True,
                'response': response_text,
                'metadata': {
                    'type': 'modalite_ouvrage',
                    'ouvrage': ouvrage.nom_ouvrage,
                    'has_modalite': True,
                    'gestionnaire': gestionnaire_nom,
                    'type_paiement': modalite.modalitepaiement
                }
            }

        except Exception as e:
            logger.error(f"Erreur modalite ouvrage query: {e}")
            return {
                'success': False,
                'response': f"Erreur : {str(e)}",
                'metadata': {'error': str(e)}
            }

    def _handle_types_query(self, message: str) -> Dict[str, Any]:
        """
        Traite les requêtes sur les types (ouvrages, équipements, points d'eau)
        """
        message_lower = message.lower()

        try:
            if 'ouvrage' in message_lower:
                # Liste des types d'ouvrages
                types = self.TypeOuvrage.objects.all().order_by('nom_type_ouvrage')
                count = types.count()

                types_list = "\n".join([f"  • {t.nom_type_ouvrage}" for t in types])

                return {
                    'success': True,
                    'response': f"**Types d'ouvrages disponibles :**\n\n" +
                              f"📊 Total : **{count}** type{'s' if count > 1 else ''}\n\n" +
                              f"**Liste :**\n{types_list}",
                    'metadata': {
                        'type': 'types_ouvrages',
                        'count': count
                    }
                }

            elif 'équipement' in message_lower or 'equipement' in message_lower:
                # Liste des types d'équipements
                types = self.TypeEquipement.objects.all().order_by('nom_type')
                count = types.count()

                types_list = "\n".join([f"  • {t.nom_type}" for t in types])

                return {
                    'success': True,
                    'response': f"**Types d'équipements disponibles :**\n\n" +
                              f"📊 Total : **{count}** type{'s' if count > 1 else ''}\n\n" +
                              f"**Liste :**\n{types_list}",
                    'metadata': {
                        'type': 'types_equipements',
                        'count': count
                    }
                }

            elif 'point' in message_lower and 'eau' in message_lower:
                # Liste des types de points d'eau
                types = self.TypePointEau.objects.all().order_by('nom_type')
                count = types.count()

                types_list = "\n".join([f"  • {t.nom_type}" for t in types])

                return {
                    'success': True,
                    'response': f"**Types de points d'eau disponibles :**\n\n" +
                              f"📊 Total : **{count}** type{'s' if count > 1 else ''}\n\n" +
                              f"**Liste :**\n{types_list}",
                    'metadata': {
                        'type': 'types_points_eau',
                        'count': count
                    }
                }

            else:
                return self._handle_general_infra_query(message)

        except Exception as e:
            logger.error(f"Erreur types query: {e}")
            return {
                'success': False,
                'response': f"Erreur : {str(e)}",
                'metadata': {'error': str(e)}
            }

    def _handle_general_infra_query(self, message: str) -> Dict[str, Any]:
        """
        Traite les requêtes générales sur les infrastructures
        """
        return {
            'success': True,
            'response': """**Questions sur les infrastructures disponibles :**

🏗️ **Ouvrages :**
- "Quel est le type de l'ouvrage [Nom] ?"
- "Quels sont les équipements de l'ouvrage [Nom] ?"
- "Quels sont les points d'eau de l'ouvrage [Nom] ?"
- "Quelle est la modalité de gestion de l'ouvrage [Nom] ?"
- "Liste des types d'ouvrages"

⚙️ **Équipements :**
- "Liste des types d'équipements"

💧 **Points d'eau :**
- "Liste des types de points d'eau"

📊 **Compteurs :**
- "Quels ouvrages ont des compteurs de tête ?"

**Exemple :** "Quels sont les équipements de l'ouvrage Ambanja FPMH ?" """,
            'metadata': {
                'type': 'help',
                'category': 'infrastructure'
            }
        }
