"""
Service d'analyse SQL pour le chatbot
Génère des requêtes SQL dynamiques sur Supabase
"""
import logging
from typing import Dict, Any, List, Optional, Tuple
from django.conf import settings
from supabase import create_client
import re

logger = logging.getLogger(__name__)

try:
    import pandas as pd
except Exception:
    pd = None
    logger.warning("Pandas non disponible. Mode degrade pour l'analyse.")


class SQLAnalyzer:
    """
    Service pour analyser et exécuter des requêtes SQL sur Supabase
    """
    
    def __init__(self):
        supabase_url = getattr(settings, 'SUPABASE_URL', None)
        supabase_key = getattr(settings, 'SUPABASE_SERVICE_KEY', None)

        if supabase_url and supabase_key:
            try:
                self.supabase = create_client(supabase_url, supabase_key)
            except Exception as exc:
                self.supabase = None
                logger.warning(f"Supabase non disponible: {exc}")
        else:
            self.supabase = None
            logger.warning("Supabase non configure. Mode local sans requetes SQL distantes.")
        
        # Mapping des tables métiers connues
        self.business_tables = {
            'plannings': {
                'table': 'plannings_planning',
                'description': 'Plannings de livraison et opérations terrain',
                'main_fields': ['id', 'date_planning', 'employee_id', 'base_id', 'status']
            },
            'bases': {
                'table': 'infrastructure_base',
                'description': 'Bases d\'approvisionnement en eau',
                'main_fields': ['id', 'nom', 'localisation', 'capacite', 'is_active']
            },
            'employees': {
                'table': 'employees_employee',
                'description': 'Employés et équipes',
                'main_fields': ['id', 'nom', 'prenom', 'fonction', 'is_active']
            },
            'billing': {
                'table': 'billing_facture',
                'description': 'Factures et paiements',
                'main_fields': ['id', 'numero', 'montant', 'status', 'date_facture']
            },
            'inventory': {
                'table': 'inventory_stock',
                'description': 'Stocks et inventaires',
                'main_fields': ['id', 'produit', 'quantite', 'emplacement']
            },
            'files': {
                'table': 'filemanager_fileupload',
                'description': 'Fichiers et documents',
                'main_fields': ['id', 'original_filename', 'uploaded_at', 'uploaded_by_id']
            }
        }
    
    def analyze_query_intent(self, user_message: str) -> Dict[str, Any]:
        """
        Analyse l'intention de l'utilisateur pour déterminer le type de requête
        """
        intent = {
            'type': 'unknown',
            'tables': [],
            'metrics': [],
            'filters': {},
            'time_period': None,
            'chart_type': None,
            'confidence': 0.0
        }
        
        message_lower = user_message.lower()
        
        # Détection des tables demandées
        for key, table_info in self.business_tables.items():
            # Vérifier le nom de la table
            if key in message_lower:
                intent['tables'].append(key)
                continue
            
            # Vérifier les mots de la description
            description_words = table_info['description'].lower().split()
            if any(word in message_lower for word in description_words):
                intent['tables'].append(key)
        
        # Détection du type de requête
        if any(word in message_lower for word in ['combien', 'nombre', 'count', 'total']):
            intent['type'] = 'count'
            intent['confidence'] += 0.3
        
        if any(word in message_lower for word in ['somme', 'montant', 'sum', 'total']):
            intent['type'] = 'sum'
            intent['confidence'] += 0.3
        
        if any(word in message_lower for word in ['moyenne', 'average', 'moy']):
            intent['type'] = 'average'
            intent['confidence'] += 0.3
        
        # Détection du type de graphique demandé
        if any(word in message_lower for word in ['graphique', 'graph', 'chart', 'courbe']):
            intent['chart_type'] = 'line'
            intent['confidence'] += 0.2
        
        if any(word in message_lower for word in ['barres', 'bar', 'histogramme']):
            intent['chart_type'] = 'bar'
            intent['confidence'] += 0.2
        
        if any(word in message_lower for word in ['camembert', 'pie', 'répartition']):
            intent['chart_type'] = 'pie'
            intent['confidence'] += 0.2
        
        # Détection des périodes temporelles
        if any(word in message_lower for word in ['aujourd\'hui', 'today']):
            intent['time_period'] = 'today'
        elif any(word in message_lower for word in ['semaine', 'week']):
            intent['time_period'] = 'week'
        elif any(word in message_lower for word in ['mois', 'month']):
            intent['time_period'] = 'month'
        elif any(word in message_lower for word in ['année', 'year', 'annuel']):
            intent['time_period'] = 'year'
        
        return intent
    
    def generate_sql_query(self, intent: Dict[str, Any], user_message: str) -> Tuple[str, Dict[str, Any]]:
        """
        Génère une requête SQL basée sur l'intention analysée
        """
        if not intent['tables']:
            return "", {"error": "Aucune table identifiée dans la demande"}
        
        primary_table = intent['tables'][0]
        table_info = self.business_tables[primary_table]
        table_name = table_info['table']
        
        # Construction de la requête de base
        if intent['type'] == 'count':
            query = f"SELECT COUNT(*) as total FROM {table_name}"
        elif intent['type'] == 'sum' and 'montant' in user_message.lower():
            query = f"SELECT SUM(montant) as total_montant FROM {table_name}"
        else:
            # Requête par défaut : les derniers enregistrements
            main_fields = ', '.join(table_info['main_fields'][:5])  # Limiter à 5 champs
            query = f"SELECT {main_fields} FROM {table_name}"
        
        # Ajout des filtres temporels
        where_conditions = []
        if intent['time_period']:
            date_field = self._get_date_field(table_name)
            if date_field:
                if intent['time_period'] == 'today':
                    where_conditions.append(f"{date_field}::date = CURRENT_DATE")
                elif intent['time_period'] == 'week':
                    where_conditions.append(f"{date_field} >= CURRENT_DATE - INTERVAL '7 days'")
                elif intent['time_period'] == 'month':
                    where_conditions.append(f"{date_field} >= CURRENT_DATE - INTERVAL '30 days'")
                elif intent['time_period'] == 'year':
                    where_conditions.append(f"{date_field} >= CURRENT_DATE - INTERVAL '1 year'")
        
        if where_conditions:
            query += f" WHERE {' AND '.join(where_conditions)}"
        
        # Ajout d'un LIMIT pour éviter les requêtes trop lourdes
        if not intent['type'] in ['count', 'sum', 'average']:
            query += " ORDER BY id DESC LIMIT 100"
        
        query_params = {
            'intent': intent,
            'table': primary_table,
            'estimated_rows': 'variable'
        }
        
        return query, query_params
    
    def _get_date_field(self, table_name: str) -> Optional[str]:
        """
        Retourne le champ de date principal pour une table donnée
        """
        date_fields = {
            'plannings_planning': 'date_planning',
            'billing_facture': 'date_facture',
            'filemanager_fileupload': 'uploaded_at',
            'employees_employee': 'created_at',
            'infrastructure_base': 'created_at',
            'inventory_stock': 'created_at'
        }
        return date_fields.get(table_name)
    
    def execute_safe_query(self, query: str) -> Tuple[bool, Any]:
        """
        Exécute une requête SQL de manière sécurisée
        """
        try:
            if self.supabase is None:
                return False, {"error": "Supabase non configuré"}

            # Validation de sécurité de la requête
            if not self._is_safe_query(query):
                return False, {"error": "Requête non autorisée pour des raisons de sécurité"}
            
            # Exécution via Supabase
            result = self.supabase.rpc('execute_readonly_query', {'query_text': query})
            
            if result.data:
                return True, result.data
            else:
                return False, {"error": "Aucun résultat retourné"}
                
        except Exception as e:
            logger.error(f"Erreur lors de l'exécution de la requête: {e}")
            return False, {"error": f"Erreur d'exécution: {str(e)}"}
    
    def _is_safe_query(self, query: str) -> bool:
        """
        Vérifie que la requête est sécurisée (lecture seule)
        """
        query_upper = query.upper().strip()
        
        # Vérifier que c'est une requête SELECT
        if not query_upper.startswith('SELECT'):
            return False
        
        # Interdire les mots-clés dangereux
        dangerous_keywords = [
            'DROP', 'DELETE', 'UPDATE', 'INSERT', 'ALTER', 'CREATE',
            'TRUNCATE', 'EXEC', 'EXECUTE', 'GRANT', 'REVOKE'
        ]
        
        for keyword in dangerous_keywords:
            if keyword in query_upper:
                return False
        
        return True
    
    def format_results_for_chat(self, data: Any, intent: Dict[str, Any]) -> Dict[str, Any]:
        """
        Formate les résultats pour l'affichage dans le chat
        """
        if isinstance(data, list) and len(data) > 0:
            # Cas d'un résultat agrégé (COUNT, SUM, etc.)
            if len(data) == 1 and len(data[0]) == 1:
                value = list(data[0].values())[0]
                key = list(data[0].keys())[0]
                
                response = {
                    'type': 'metric',
                    'value': value,
                    'label': key,
                    'formatted_text': f"Résultat: {value:,}".replace(',', ' ') if isinstance(value, (int, float)) else f"Résultat: {value}"
                }
                
                # Ajouter des données pour graphique si approprié
                if intent.get('chart_type') and isinstance(value, (int, float)):
                    response['chart_data'] = {
                        'type': 'metric',
                        'value': value,
                        'label': key
                    }
                
                return response
            
            # Cas d'une liste de résultats
            else:
                if pd is not None:
                    df = pd.DataFrame(data)
                    columns = list(df.columns)
                else:
                    df = None
                    columns = list(data[0].keys())

                response = {
                    'type': 'table',
                    'data': data,
                    'row_count': len(data),
                    'columns': columns,
                    'formatted_text': f"Trouvé {len(data)} résultat{'s' if len(data) > 1 else ''}"
                }

                # Générer des données pour graphique si demandé
                if intent.get('chart_type') and len(columns) >= 2:
                    chart_data = self._generate_chart_data(df if df is not None else data, intent['chart_type'])
                    if chart_data:
                        response['chart_data'] = chart_data

                return response
        
        return {
            'type': 'empty',
            'formatted_text': "Aucun résultat trouvé"
        }
    
    def _generate_chart_data(self, data: Any, chart_type: str) -> Optional[Dict[str, Any]]:
        """
        Génère des données formatées pour les graphiques
        """
        try:
            if pd is not None and isinstance(data, pd.DataFrame):
                df = data
                columns = list(df.columns)
                records = df.to_dict('records')
            elif pd is not None and isinstance(data, list):
                df = pd.DataFrame(data)
                columns = list(df.columns)
                records = df.to_dict('records')
            elif isinstance(data, list) and data:
                df = None
                columns = list(data[0].keys())
                records = data
            else:
                return None

            if chart_type == 'pie' and len(columns) >= 2:
                if df is not None:
                    grouped = df.groupby(columns[0])[columns[1]].sum()
                    values = [{'name': str(k), 'value': float(v)} for k, v in grouped.items()]
                else:
                    grouped = {}
                    for row in records:
                        key = row.get(columns[0])
                        value = row.get(columns[1], 0) or 0
                        grouped[key] = grouped.get(key, 0) + float(value)
                    values = [{'name': str(k), 'value': float(v)} for k, v in grouped.items()]
                return {
                    'type': 'pie',
                    'data': values,
                    'title': f"Répartition par {columns[0]}"
                }

            if chart_type == 'bar' and len(columns) >= 2:
                return {
                    'type': 'bar',
                    'data': records[:10],
                    'x_key': columns[0],
                    'y_key': columns[1],
                    'title': f"{columns[1]} par {columns[0]}"
                }

            if chart_type == 'line' and len(columns) >= 2:
                return {
                    'type': 'line',
                    'data': records[:20],
                    'x_key': columns[0],
                    'y_key': columns[1],
                    'title': f"Évolution de {columns[1]}"
                }
                
        except Exception as e:
            logger.warning(f"Erreur lors de la génération des données graphique: {e}")
            
        return None
    
    def get_table_info(self, table_key: str) -> Dict[str, Any]:
        """
        Retourne les informations sur une table métier
        """
        return self.business_tables.get(table_key, {})
    
    def list_available_tables(self) -> Dict[str, str]:
        """
        Liste les tables disponibles avec leurs descriptions
        """
        return {key: info['description'] for key, info in self.business_tables.items()}
