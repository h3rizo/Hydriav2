"""
Service pour gérer les requêtes analytiques complexes
Gère les tableaux, graphiques et analyses temporelles
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from django.db.models import Sum, Count, Q, Avg, Max, Min
from django.db.models.functions import TruncYear, TruncMonth
from collections import defaultdict

logger = logging.getLogger(__name__)


class AnalyticsQueries:
    """
    Gère les requêtes analytiques : tableaux, graphiques, évolutions temporelles
    """

    def __init__(self):
        # Import des modèles ici pour éviter les imports circulaires
        from apps.geography.models import Commune, Fokontany, Village
        from apps.billing.models import PointEau, Releve
        from apps.organization.models import Ouvrage

        self.Commune = Commune
        self.Fokontany = Fokontany
        self.Village = Village
        self.PointEau = PointEau
        self.Releve = Releve
        self.Ouvrage = Ouvrage

    def can_handle(self, user_message: str) -> bool:
        """
        Vérifie si ce service peut traiter le message
        """
        message_lower = user_message.lower()

        # Mots-clés pour tableaux
        tableau_keywords = [
            'tableau', 'liste', 'comparaison', 'compare',
            'classement', 'top', 'meilleur', 'pire'
        ]

        # Mots-clés pour graphiques
        graphique_keywords = [
            'graphique', 'courbe', 'évolution', 'evolution', 'tendance',
            'progression', 'variation', 'historique'
        ]

        # Mots-clés temporels
        temporel_keywords = [
            'année', 'annee', 'mois', 'trimestre',
            'par an', 'par mois', 'mensuel', 'annuel',
            'depuis', 'entre', 'période', 'periode'
        ]

        has_tableau = any(keyword in message_lower for keyword in tableau_keywords)
        has_graphique = any(keyword in message_lower for keyword in graphique_keywords)
        has_temporel = any(keyword in message_lower for keyword in temporel_keywords)

        return has_tableau or has_graphique or has_temporel

    def process_query(self, user_message: str) -> Dict[str, Any]:
        """
        Traite une requête analytique et retourne les résultats
        """
        message_lower = user_message.lower()

        try:
            # Détection du type de requête
            if 'évolution' in message_lower or 'evolution' in message_lower:
                if 'consommation' in message_lower or 'volume' in message_lower:
                    return self._evolution_consommation(message_lower)
                elif any(pattern in message_lower for pattern in ['points d\'eau', 'point d\'eau', 'points d eau', 'point d eau']):
                    return self._evolution_points_eau(message_lower)

            elif 'tableau' in message_lower or 'comparaison' in message_lower:
                if 'commune' in message_lower:
                    return self._tableau_communes(message_lower)
                elif 'ouvrage' in message_lower:
                    return self._tableau_ouvrages(message_lower)

            elif 'top' in message_lower or 'classement' in message_lower:
                return self._classement(message_lower)

            # Si aucun pattern spécifique, retourner un message d'aide
            return {
                'success': False,
                'response': self._message_aide_analytics(),
                'metadata': {'type': 'aide_analytics'}
            }

        except Exception as e:
            logger.error(f"Erreur lors du traitement de la requête analytique: {e}")
            return {
                'success': False,
                'response': f"Erreur lors de l'analyse : {str(e)}",
                'metadata': {'type': 'error', 'error': str(e)}
            }

    def _evolution_consommation(self, message_lower: str) -> Dict[str, Any]:
        """
        Génère l'évolution de la consommation d'eau par année/mois
        """
        # Extraire la commune si mentionnée
        commune_nom = self._extract_location(message_lower)

        # Requête pour les relevés
        releves_query = self.Releve.objects.filter(
            consommation__isnull=False,
            consommation__gt=0
        )

        # Filtrer par commune si spécifiée
        if commune_nom:
            commune = self._find_commune(commune_nom)
            if commune:
                releves_query = releves_query.filter(
                    point_eau__parcelle__village__fokontany__commune=commune
                )

        # Grouper par année
        evolution_annuelle = releves_query.annotate(
            annee=TruncYear('datereleve')
        ).values('annee').annotate(
            total_consommation=Sum('consommation'),
            nb_releves=Count('id'),
            moyenne_consommation=Avg('consommation')
        ).order_by('annee')

        # Formater les données pour le graphique
        data_graphique = {
            'labels': [],
            'consommation_totale': [],
            'consommation_moyenne': [],
            'nb_releves': []
        }

        tableau_rows = []
        for item in evolution_annuelle:
            annee = item['annee'].year
            data_graphique['labels'].append(str(annee))
            data_graphique['consommation_totale'].append(float(item['total_consommation'] or 0))
            data_graphique['consommation_moyenne'].append(float(item['moyenne_consommation'] or 0))
            data_graphique['nb_releves'].append(item['nb_releves'])

            tableau_rows.append({
                'annee': annee,
                'total': f"{item['total_consommation']:,.0f} m³" if item['total_consommation'] else "0 m³",
                'moyenne': f"{item['moyenne_consommation']:,.2f} m³" if item['moyenne_consommation'] else "0 m³",
                'nb_releves': item['nb_releves']
            })

        # Générer la réponse textuelle
        response = self._format_evolution_response(tableau_rows, commune_nom)

        return {
            'success': True,
            'response': response,
            'metadata': {
                'type': 'evolution_consommation',
                'commune': commune_nom,
                'data_graphique': data_graphique,
                'tableau': tableau_rows
            }
        }

    def _evolution_points_eau(self, message_lower: str) -> Dict[str, Any]:
        """
        Génère l'évolution du nombre de points d'eau par année
        """
        commune_nom = self._extract_location(message_lower)

        # Requête pour les points d'eau avec date de création
        points_query = self.PointEau.objects.filter(
            createdat__isnull=False
        )

        if commune_nom:
            commune = self._find_commune(commune_nom)
            if commune:
                points_query = points_query.filter(
                    parcelle__village__fokontany__commune=commune
                )

        # Grouper par année de création
        evolution = points_query.annotate(
            annee=TruncYear('createdat')
        ).values('annee').annotate(
            nb_points=Count('id')
        ).order_by('annee')

        data_graphique = {
            'labels': [],
            'nb_points': [],
            'cumul': []
        }

        cumul = 0
        tableau_rows = []
        for item in evolution:
            annee = item['annee'].year
            nb_points = item['nb_points']
            cumul += nb_points

            data_graphique['labels'].append(str(annee))
            data_graphique['nb_points'].append(nb_points)
            data_graphique['cumul'].append(cumul)

            tableau_rows.append({
                'annee': annee,
                'nouveaux': nb_points,
                'cumul': cumul
            })

        response = f"**Évolution du nombre de points d'eau"
        if commune_nom:
            response += f" à {commune_nom}"
        response += " :**\n\n"

        response += "| Année | Nouveaux PE | Total cumulé |\n"
        response += "|-------|-------------|-------------|\n"
        for row in tableau_rows:
            response += f"| {row['annee']} | {row['nouveaux']} | {row['cumul']} |\n"

        return {
            'success': True,
            'response': response,
            'metadata': {
                'type': 'evolution_points_eau',
                'commune': commune_nom,
                'data_graphique': data_graphique,
                'tableau': tableau_rows
            }
        }

    def _tableau_communes(self, message_lower: str) -> Dict[str, Any]:
        """
        Génère un tableau comparatif des communes
        """
        # Récupérer toutes les communes avec leurs statistiques
        communes = self.Commune.objects.all()

        tableau_rows = []
        for commune in communes:
            # Compter les points d'eau
            nb_points_eau = self.PointEau.objects.filter(
                parcelle__village__fokontany__commune=commune
            ).count()

            # Compter les ouvrages
            nb_ouvrages = self.Ouvrage.objects.filter(
                pointeau__parcelle__village__fokontany__commune=commune
            ).distinct().count()

            # Compter les villages
            nb_villages = self.Village.objects.filter(
                fokontany__commune=commune
            ).count()

            tableau_rows.append({
                'commune': commune.nom_commune,
                'nb_villages': nb_villages,
                'nb_points_eau': nb_points_eau,
                'nb_ouvrages': nb_ouvrages
            })

        # Trier par nombre de points d'eau (décroissant)
        tableau_rows.sort(key=lambda x: x['nb_points_eau'], reverse=True)

        # Formater en markdown
        response = "**Tableau comparatif des communes :**\n\n"
        response += "| Commune | Villages | Points d'eau | Ouvrages |\n"
        response += "|---------|----------|--------------|----------|\n"

        for row in tableau_rows[:20]:  # Limiter à 20 communes
            response += f"| {row['commune']} | {row['nb_villages']} | {row['nb_points_eau']} | {row['nb_ouvrages']} |\n"

        return {
            'success': True,
            'response': response,
            'metadata': {
                'type': 'tableau_communes',
                'tableau': tableau_rows,
                'total_communes': len(tableau_rows)
            }
        }

    def _tableau_ouvrages(self, message_lower: str) -> Dict[str, Any]:
        """
        Génère un tableau des ouvrages avec leurs caractéristiques
        """
        commune_nom = self._extract_location(message_lower)

        ouvrages_query = self.Ouvrage.objects.all().select_related(
            'type_ouvrage'
        )

        if commune_nom:
            commune = self._find_commune(commune_nom)
            if commune:
                ouvrages_query = ouvrages_query.filter(
                    pointeau__parcelle__village__fokontany__commune=commune
                ).distinct()

        tableau_rows = []
        for ouvrage in ouvrages_query:
            # Compter les points d'eau
            nb_points = ouvrage.pointeau_set.count()

            tableau_rows.append({
                'nom': ouvrage.nom_ouvrage,
                'type': ouvrage.type_ouvrage.nom_type_ouvrage if ouvrage.type_ouvrage else 'N/A',
                'nb_points_eau': nb_points,
                'annee_construction': ouvrage.annee_construction or 'N/A'
            })

        response = f"**Tableau des ouvrages"
        if commune_nom:
            response += f" à {commune_nom}"
        response += " :**\n\n"

        response += "| Nom ouvrage | Type | Points d'eau | Année |\n"
        response += "|-------------|------|--------------|-------|\n"

        for row in tableau_rows[:30]:
            response += f"| {row['nom']} | {row['type']} | {row['nb_points_eau']} | {row['annee_construction']} |\n"

        return {
            'success': True,
            'response': response,
            'metadata': {
                'type': 'tableau_ouvrages',
                'commune': commune_nom,
                'tableau': tableau_rows,
                'total_ouvrages': len(tableau_rows)
            }
        }

    def _classement(self, message_lower: str) -> Dict[str, Any]:
        """
        Génère un classement (top N)
        """
        # Déterminer le critère de classement
        if 'consommation' in message_lower:
            return self._classement_consommation(message_lower)
        elif any(pattern in message_lower for pattern in ['points d\'eau', 'point d\'eau', 'points d eau', 'point d eau']):
            return self._classement_points_eau(message_lower)
        else:
            return {
                'success': False,
                'response': "Veuillez préciser le critère de classement (consommation, points d'eau, etc.)",
                'metadata': {'type': 'error'}
            }

    def _classement_points_eau(self, message_lower: str) -> Dict[str, Any]:
        """
        Classement des communes par nombre de points d'eau
        """
        # Extraire le nombre (top N)
        import re
        match = re.search(r'top\s+(\d+)', message_lower)
        limit = int(match.group(1)) if match else 10

        communes = self.Commune.objects.all()
        classement = []

        for commune in communes:
            nb_points = self.PointEau.objects.filter(
                parcelle__village__fokontany__commune=commune
            ).count()

            classement.append({
                'commune': commune.nom_commune,
                'nb_points_eau': nb_points
            })

        # Trier par nombre décroissant
        classement.sort(key=lambda x: x['nb_points_eau'], reverse=True)

        response = f"**Top {limit} des communes par nombre de points d'eau :**\n\n"
        for i, item in enumerate(classement[:limit], 1):
            response += f"{i}. **{item['commune']}** : {item['nb_points_eau']} points d'eau\n"

        return {
            'success': True,
            'response': response,
            'metadata': {
                'type': 'classement_points_eau',
                'classement': classement[:limit],
                'limit': limit
            }
        }

    def _classement_consommation(self, message_lower: str) -> Dict[str, Any]:
        """
        Classement des communes par consommation totale
        """
        import re
        match = re.search(r'top\s+(\d+)', message_lower)
        limit = int(match.group(1)) if match else 10

        # Extraire l'année si mentionnée
        year_match = re.search(r'20\d{2}', message_lower)
        year = int(year_match.group(0)) if year_match else None

        communes = self.Commune.objects.all()
        classement = []

        for commune in communes:
            releves_query = self.Releve.objects.filter(
                point_eau__parcelle__village__fokontany__commune=commune,
                consommation__isnull=False
            )

            if year:
                releves_query = releves_query.filter(datereleve__year=year)

            total_conso = releves_query.aggregate(
                total=Sum('consommation')
            )['total'] or 0

            classement.append({
                'commune': commune.nom_commune,
                'consommation_totale': float(total_conso)
            })

        classement.sort(key=lambda x: x['consommation_totale'], reverse=True)

        response = f"**Top {limit} des communes par consommation"
        if year:
            response += f" en {year}"
        response += " :**\n\n"

        for i, item in enumerate(classement[:limit], 1):
            conso = item['consommation_totale']
            response += f"{i}. **{item['commune']}** : {conso:,.0f} m³\n"

        return {
            'success': True,
            'response': response,
            'metadata': {
                'type': 'classement_consommation',
                'year': year,
                'classement': classement[:limit],
                'limit': limit
            }
        }

    def _extract_location(self, message_lower: str) -> Optional[str]:
        """
        Extrait le nom de la commune du message
        """
        # Chercher des patterns comme "à X", "de X", "dans X"
        import re
        patterns = [
            r'à\s+([A-Za-zÀ-ÿ\s]+?)(?:\s|$)',
            r'de\s+([A-Za-zÀ-ÿ\s]+?)(?:\s|$)',
            r'dans\s+([A-Za-zÀ-ÿ\s]+?)(?:\s|$)'
        ]

        for pattern in patterns:
            match = re.search(pattern, message_lower)
            if match:
                return match.group(1).strip().title()

        return None

    def _find_commune(self, nom: str) -> Optional[Any]:
        """
        Trouve une commune par nom (recherche insensible à la casse)
        """
        try:
            return self.Commune.objects.get(nom_commune__iexact=nom)
        except self.Commune.DoesNotExist:
            return None

    def _format_evolution_response(self, tableau_rows: List[Dict], commune_nom: Optional[str]) -> str:
        """
        Formate la réponse pour l'évolution de la consommation
        """
        response = f"**Évolution de la consommation d'eau"
        if commune_nom:
            response += f" à {commune_nom}"
        response += " :**\n\n"

        response += "| Année | Consommation totale | Consommation moyenne | Nb relevés |\n"
        response += "|-------|---------------------|---------------------|------------|\n"

        for row in tableau_rows:
            response += f"| {row['annee']} | {row['total']} | {row['moyenne']} | {row['nb_releves']} |\n"

        if len(tableau_rows) > 1:
            # Calculer la variation entre première et dernière année
            premier = tableau_rows[0]
            dernier = tableau_rows[-1]

            response += f"\n📊 **Variation** : "
            response += f"La consommation est passée de {premier['total']} en {premier['annee']} "
            response += f"à {dernier['total']} en {dernier['annee']}.\n"

        return response

    def _message_aide_analytics(self) -> str:
        """
        Message d'aide pour les requêtes analytiques
        """
        return """**Questions analytiques disponibles :**

📊 **Évolutions temporelles :**
• "Évolution de la consommation d'eau par année"
• "Évolution du nombre de points d'eau à [commune]"

📋 **Tableaux comparatifs :**
• "Tableau comparatif des communes"
• "Tableau des ouvrages à [commune]"

🏆 **Classements :**
• "Top 10 des communes par nombre de points d'eau"
• "Top 5 des communes par consommation en 2024"

Exemples :
• "Montre moi l'évolution de la consommation à Ambato"
• "Compare les communes par nombre de points d'eau"
• "Quel est le top 5 des communes par consommation ?"
"""
