"""
Assistant IA modulaire pour le chatbot Hydria
Orchestre les différents agents pour traiter les demandes utilisateurs
"""
import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from asgiref.sync import sync_to_async

from .sql_analyzer import SQLAnalyzer
from .chart_generator import ChartGenerator
from .file_exporter import FileExporter
from .stats_handler import StatsHandler
from .geography_queries import GeographyQueries
from .infrastructure_queries import InfrastructureQueries
from .analytics_queries import AnalyticsQueries

logger = logging.getLogger(__name__)


class AIAssistant:
    """
    Assistant IA principal qui coordonne les différents modules
    """

    def __init__(self):
        self.sql_analyzer = SQLAnalyzer()
        self.chart_generator = ChartGenerator()
        self.file_exporter = FileExporter()
        self.stats_handler = StatsHandler()
        self.geography_queries = GeographyQueries()
        self.infrastructure_queries = InfrastructureQueries()
        self.analytics_queries = AnalyticsQueries()
        
        # Intent mapping pour l'analyse des demandes
        self.intent_keywords = {
            'data_query': [
                'combien', 'nombre', 'count', 'total', 'liste', 'affiche',
                'montant', 'somme', 'moyenne', 'statistiques', 'données'
            ],
            'chart_request': [
                'graphique', 'graph', 'chart', 'courbe', 'barres', 'camembert',
                'pie', 'histogramme', 'visualisation', 'diagramme'
            ],
            'report_generation': [
                'rapport', 'report', 'document', 'synthèse', 'bilan',
                'analyse', 'résumé', 'export', 'pdf', 'excel'
            ],
            'help_request': [
                'aide', 'help', 'comment', 'expliquer', 'qu\'est-ce que',
                'que faire', 'utiliser', 'fonctionnement'
            ]
        }
    
    async def process_message(self, user_message: str, session_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Traite un message utilisateur et génère une réponse appropriée
        """
        try:
            # Initialiser le contexte de session si nécessaire
            if session_context is None:
                session_context = {}

            # Vérifier si c'est une demande de détails sur la dernière réponse
            if self._is_followup_details_request(user_message, session_context):
                return await self._handle_followup_details(session_context)

            # Vérifier en PRIORITÉ si c'est une demande analytique (tableaux, graphiques, évolutions)
            # DOIT être avant geography_queries car plus spécifique
            if self.analytics_queries.can_handle(user_message):
                result = await sync_to_async(self.analytics_queries.process_query)(user_message)

                # Stocker le contexte pour les follow-ups
                session_context['last_query'] = user_message
                session_context['last_result'] = result
                session_context['last_type'] = 'analytics'

                return result

            # Vérifier si c'est une demande géographique
            if self.geography_queries.can_handle(user_message):
                # Utiliser sync_to_async pour appeler process_query depuis un contexte async
                result = await sync_to_async(self.geography_queries.process_query)(user_message)

                # Stocker le contexte pour les follow-ups
                session_context['last_query'] = user_message
                session_context['last_result'] = result
                session_context['last_type'] = 'geography'

                return result

            # Vérifier si c'est une demande d'infrastructure
            if self.infrastructure_queries.can_handle(user_message):
                # Utiliser sync_to_async pour appeler process_query depuis un contexte async
                return await sync_to_async(self.infrastructure_queries.process_query)(user_message)

            # Vérifier si c'est une demande de statistiques
            if self.stats_handler.can_handle(user_message):
                return self.stats_handler.generate_response(user_message)

            # Analyser l'intention de l'utilisateur
            intent = self._analyze_intent(user_message)

            # Traiter selon le type d'intention
            if intent['type'] == 'data_query':
                return await self._handle_data_query(user_message, intent, session_context)
            elif intent['type'] == 'chart_request':
                return await self._handle_chart_request(user_message, intent, session_context)
            elif intent['type'] == 'report_generation':
                return await self._handle_report_generation(user_message, intent, session_context)
            elif intent['type'] == 'help_request':
                return self._handle_help_request(user_message, intent)
            else:
                return self._handle_general_query(user_message, intent)

        except Exception as e:
            logger.error(f"Erreur lors du traitement du message: {e}")
            return {
                'response': "Désolé, j'ai rencontré une erreur lors du traitement de votre demande. Pourriez-vous reformuler ?",
                'metadata': {'error': str(e)},
                'success': False
            }
    
    def _analyze_intent(self, message: str) -> Dict[str, Any]:
        """
        Analyse l'intention de l'utilisateur
        """
        message_lower = message.lower()
        intent_scores = {}
        
        # Calculer les scores pour chaque type d'intention
        for intent_type, keywords in self.intent_keywords.items():
            score = sum(1 for keyword in keywords if keyword in message_lower)
            if score > 0:
                intent_scores[intent_type] = score / len(keywords)  # Normaliser
        
        # Déterminer l'intention principale
        if intent_scores:
            primary_intent = max(intent_scores, key=intent_scores.get)
            confidence = intent_scores[primary_intent]
        else:
            primary_intent = 'general'
            confidence = 0.0
        
        # Analyser plus finement avec le SQLAnalyzer
        sql_intent = self.sql_analyzer.analyze_query_intent(message)
        
        return {
            'type': primary_intent,
            'confidence': confidence,
            'sql_intent': sql_intent,
            'original_message': message
        }
    
    async def _handle_data_query(self, message: str, intent: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Traite les demandes de données
        """
        sql_intent = intent['sql_intent']
        
        # Générer la requête SQL
        sql_query, query_params = self.sql_analyzer.generate_sql_query(sql_intent, message)
        
        if not sql_query:
            return {
                'response': "Je n'ai pas pu comprendre votre demande de données. Pourriez-vous préciser quelle table vous intéresse ? (plannings, factures, stocks, employés, bases)",
                'metadata': {'error': 'no_sql_generated'},
                'success': False
            }
        
        # Exécuter la requête
        success, results = self.sql_analyzer.execute_safe_query(sql_query)
        
        if not success:
            return {
                'response': f"Erreur lors de l'exécution de la requête : {results.get('error', 'Erreur inconnue')}",
                'metadata': {'sql_query': sql_query, 'error': results},
                'success': False
            }
        
        # Formater les résultats
        formatted_results = self.sql_analyzer.format_results_for_chat(results, sql_intent)
        
        # Générer la réponse textuelle
        response_text = self._generate_data_response_text(formatted_results, sql_intent)
        
        # Préparer les métadonnées
        metadata = {
            'sql_query': sql_query,
            'result_type': formatted_results.get('type'),
            'row_count': formatted_results.get('row_count', 0)
        }
        
        # Ajouter les données de graphique si disponibles
        if formatted_results.get('chart_data'):
            chart_config = self.chart_generator.generate_chart_config(
                formatted_results['chart_data'].get('data', []),
                formatted_results['chart_data'].get('type', 'bar'),
                {'title': formatted_results['chart_data'].get('title')}
            )
            metadata['chart_data'] = chart_config
        
        return {
            'response': response_text,
            'metadata': metadata,
            'success': True
        }
    
    async def _handle_chart_request(self, message: str, intent: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Traite les demandes de graphiques
        """
        # D'abord obtenir les données
        data_response = await self._handle_data_query(message, intent, context)
        
        if not data_response['success']:
            return data_response
        
        # Forcer la génération d'un graphique
        sql_intent = intent['sql_intent']
        if not sql_intent.get('chart_type'):
            # Déterminer le type de graphique par défaut
            if any(word in message.lower() for word in ['répartition', 'camembert']):
                sql_intent['chart_type'] = 'pie'
            elif any(word in message.lower() for word in ['évolution', 'courbe', 'ligne']):
                sql_intent['chart_type'] = 'line'
            else:
                sql_intent['chart_type'] = 'bar'
        
        # Générer le graphique si pas déjà fait
        if 'chart_data' not in data_response['metadata']:
            # Essayer de créer un graphique avec les données retournées
            # (cette partie nécessiterait plus de logique selon le format des résultats)
            pass

        response_text = data_response['response'] + "\n\nVoici la visualisation des données :"
        
        return {
            'response': response_text,
            'metadata': data_response['metadata'],
            'success': True
        }
    
    async def _handle_report_generation(self, message: str, intent: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Traite les demandes de génération de rapports
        """
        # Identifier le type de rapport demandé
        report_data = {
            'title': 'Rapport Hydria',
            'summary': 'Rapport généré automatiquement par l\'assistant IA',
            'metrics': [],
            'table_data': {},
            'charts': []
        }
        
        # Analyser quelles données inclure
        sql_intent = intent['sql_intent']
        if sql_intent.get('tables'):
            for table in sql_intent['tables']:
                table_info = self.sql_analyzer.get_table_info(table)
                report_data['title'] = f"Rapport {table_info.get('description', table)}"
        
        # Créer le rapport PDF
        try:
            pdf_path = self.file_exporter.create_pdf_report(report_data)
            
            return {
                'response': f"J'ai généré un rapport PDF pour vous. Voici les données analysées :\n\n**{report_data['title']}**\n\n{report_data['summary']}",
                'metadata': {
                    'generated_files': [{
                        'name': 'rapport_hydria.pdf',
                        'type': 'pdf',
                        'url': f'/assistant/download/{pdf_path}',
                        'size': 'À calculer'
                    }]
                },
                'success': True
            }
        except Exception as e:
            logger.error(f"Erreur lors de la génération du rapport: {e}")
            return {
                'response': "Désolé, j'ai rencontré une erreur lors de la génération du rapport PDF.",
                'metadata': {'error': str(e)},
                'success': False
            }
    
    def _handle_help_request(self, message: str, intent: Dict[str, Any]) -> Dict[str, Any]:
        """
        Traite les demandes d'aide
        """
        help_topics = {
            'données': """
            **Interrogation des données :**
            - "Combien de plannings ce mois-ci ?"
            - "Affiche les factures impayées"
            - "Quel est le montant total des ventes ?"
            - "Liste des employés actifs"
            """,
            'graphiques': """
            **Création de graphiques :**
            - "Montre un graphique des ventes par mois"
            - "Crée un camembert des stocks par catégorie"
            - "Graphique en barres des performances"
            """,
            'rapports': """
            **Génération de rapports :**
            - "Génère un rapport PDF des plannings"
            - "Export Excel des factures du trimestre"
            - "Crée un bilan des activités"
            """,
            'général': """
            **Utilisation générale :**
            Je peux vous aider avec :
            • 📊 Analyse des données métiers
            • 📈 Création de graphiques interactifs
            • 📋 Génération de rapports PDF/Excel
            • 💬 Réponses à vos questions sur Hydria
            
            **Tables disponibles :**
            - Plannings (livraisons, opérations)
            - Factures (paiements, montants)
            - Stocks (inventaires, produits)  
            - Employés (équipes, fonctions)
            - Bases (approvisionnement)
            - Fichiers (documents uploadés)
            """
        }
        
        # Déterminer le sujet d'aide demandé
        topic = 'général'
        message_lower = message.lower()
        
        for key in help_topics.keys():
            if key in message_lower:
                topic = key
                break
        
        return {
            'response': f"**Aide - {topic.title()} :**\n\n{help_topics[topic]}",
            'metadata': {'help_topic': topic},
            'success': True
        }
    
    def _handle_general_query(self, message: str, intent: Dict[str, Any]) -> Dict[str, Any]:
        """
        Traite les requêtes générales
        """
        # Réponses contextuelles basiques
        message_lower = message.lower()
        
        if any(greeting in message_lower for greeting in ['bonjour', 'salut', 'hello', 'bonsoir']):
            return {
                'response': "Bonjour ! Je suis votre assistant IA pour Hydria. Comment puis-je vous aider avec vos données aujourd'hui ?",
                'metadata': {'type': 'greeting'},
                'success': True
            }
        
        if any(thanks in message_lower for thanks in ['merci', 'thank', 'parfait', 'super']):
            return {
                'response': "Je vous en prie ! N'hésitez pas si vous avez d'autres questions sur vos données Hydria.",
                'metadata': {'type': 'acknowledgment'},
                'success': True
            }
        
        # Réponse par défaut avec suggestions
        available_tables = self.sql_analyzer.list_available_tables()
        suggestions = []
        
        for table, description in available_tables.items():
            suggestions.append(f"• **{table.title()}** : {description}")
        
        return {
            'response': f"""Je n'ai pas bien compris votre demande. Voici ce que je peux faire pour vous :

**💡 Suggestions :**
- Analyser vos données métiers
- Créer des graphiques et visualisations  
- Générer des rapports PDF/Excel
- Répondre à vos questions sur les performances

**📊 Tables disponibles :**
{chr(10).join(suggestions[:5])}

**Exemples de questions :**
- "Combien de plannings cette semaine ?"
- "Montre-moi un graphique des factures"
- "Génère un rapport des stocks"

Que souhaitez-vous analyser ?""",
            'metadata': {'type': 'general_help'},
            'success': True
        }
    
    def _generate_data_response_text(self, formatted_results: Dict[str, Any], sql_intent: Dict[str, Any]) -> str:
        """
        Génère une réponse textuelle pour les résultats de données
        """
        result_type = formatted_results.get('type')
        
        if result_type == 'metric':
            value = formatted_results.get('value')
            label = formatted_results.get('label')
            return f"**Résultat :** {formatted_results.get('formatted_text')}"
        
        elif result_type == 'table':
            row_count = formatted_results.get('row_count', 0)
            table_name = sql_intent.get('tables', ['données'])[0]
            
            response = f"**Données trouvées :** {row_count} {table_name}"
            
            if row_count > 0:
                if row_count <= 10:
                    response += "\n\nVoici le détail :"
                else:
                    response += f"\n\nVoici les {min(10, row_count)} premiers résultats :"
            
            return response
        
        elif result_type == 'empty':
            return "Aucun résultat trouvé pour votre demande. Pourriez-vous préciser votre recherche ?"
        
        else:
            return formatted_results.get('formatted_text', 'Données analysées avec succès.')
    
    def get_conversation_summary(self, messages: List[Dict[str, Any]]) -> str:
        """
        Génère un résumé de la conversation pour le titre
        """
        if not messages:
            return "Nouvelle conversation"

        # Prendre le premier message utilisateur
        first_user_message = next((msg for msg in messages if msg.get('role') == 'user'), None)

        if first_user_message:
            content = first_user_message.get('content', '')
            return content[:50] + ('...' if len(content) > 50 else '')

        return f"Conversation ({len(messages)} messages)"

    def _is_followup_details_request(self, message: str, session_context: Dict[str, Any]) -> bool:
        """
        Détecte si le message demande des détails sur la question précédente
        """
        message_lower = message.lower()

        # Mots-clés de follow-up
        followup_keywords = [
            'détail', 'detail', 'détails', 'details',
            'explique', 'explication',
            'calcul', 'comment',
            'par ouvrage', 'liste', 'tous'
        ]

        # Vérifier qu'on a un contexte de question précédente
        has_context = (
            session_context.get('last_query') and
            session_context.get('last_result') and
            session_context.get('last_type') == 'geography'
        )

        if not has_context:
            return False

        # Vérifier que le message contient un mot-clé de follow-up
        has_followup_keyword = any(keyword in message_lower for keyword in followup_keywords)

        # Si pas de mot-clé de follow-up, ce n'est pas un follow-up
        if not has_followup_keyword:
            return False

        # Patterns qui indiquent une NOUVELLE question (avec nouveau lieu)
        new_question_patterns = [
            'combien de points d\'eau à',
            'combien de points d\'eau dans',
            'liste des points d\'eau à',
            'liste des points d\'eau dans',
            'où se trouve',
            'dans quelle commune',
            'dans quel district'
        ]

        # Si le message contient un pattern de nouvelle question spécifique, ce n'est PAS un follow-up
        has_new_question = any(pattern in message_lower for pattern in new_question_patterns)

        # C'est un follow-up si on a le mot-clé ET qu'il n'y a pas de nouvelle question
        return has_followup_keyword and not has_new_question

    async def _handle_followup_details(self, session_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Traite une demande de détails sur la question précédente
        """
        last_query = session_context.get('last_query', '')
        last_result = session_context.get('last_result', {})

        # Vérifier si la dernière réponse était déjà détaillée
        if last_result.get('metadata', {}).get('type') == 'points_eau_details':
            return {
                'success': True,
                'response': "Voici à nouveau les détails :\n\n" + last_result.get('response', ''),
                'metadata': last_result.get('metadata', {})
            }

        # Si c'était une réponse simple sur les points d'eau, refaire la requête avec détails
        if last_result.get('metadata', {}).get('type') == 'points_eau':
            # Ajouter le mot-clé "détail" à la question originale
            detailed_query = last_query + " détail"

            # Relancer la requête avec le mot-clé
            result = await sync_to_async(self.geography_queries.process_query)(detailed_query)

            # Mettre à jour le contexte
            session_context['last_result'] = result

            return result

        # Si ce n'était pas une question sur les points d'eau, retourner un message d'erreur
        return {
            'success': False,
            'response': "Je ne peux pas fournir plus de détails sur la question précédente. Pourriez-vous préciser votre demande ?",
            'metadata': {}
        }