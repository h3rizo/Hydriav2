"""
Service de génération de graphiques pour le chatbot
Crée des graphiques interactifs en utilisant Chart.js et Plotly
"""
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ChartGenerator:
    """
    Service pour générer des configurations de graphiques
    Compatible avec Chart.js et Plotly pour l'affichage frontend
    """
    
    def __init__(self):
        self.default_colors = [
            '#3B82F6', '#EF4444', '#10B981', '#F59E0B', '#8B5CF6',
            '#06B6D4', '#84CC16', '#F97316', '#EC4899', '#6366F1'
        ]
    
    def generate_chart_config(self, data: Any, chart_type: str, options: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Génère une configuration de graphique basée sur les données et le type
        """
        if options is None:
            options = {}
        
        try:
            if chart_type == 'pie':
                return self._create_pie_chart(data, options)
            elif chart_type == 'bar':
                return self._create_bar_chart(data, options)
            elif chart_type == 'line':
                return self._create_line_chart(data, options)
            elif chart_type == 'doughnut':
                return self._create_doughnut_chart(data, options)
            elif chart_type == 'area':
                return self._create_area_chart(data, options)
            elif chart_type == 'scatter':
                return self._create_scatter_chart(data, options)
            else:
                # Type par défaut basé sur les données
                return self._auto_detect_chart_type(data, options)
                
        except Exception as e:
            logger.error(f"Erreur lors de la génération du graphique: {e}")
            return self._create_error_chart(str(e))
    
    def _create_pie_chart(self, data: List[Dict[str, Any]], options: Dict[str, Any]) -> Dict[str, Any]:
        """
        Crée un graphique en camembert
        """
        labels = []
        values = []
        
        for item in data:
            if 'name' in item and 'value' in item:
                labels.append(str(item['name']))
                values.append(float(item['value']))
        
        return {
            'type': 'pie',
            'data': {
                'labels': labels,
                'datasets': [{
                    'data': values,
                    'backgroundColor': self.default_colors[:len(values)],
                    'borderWidth': 2,
                    'borderColor': '#ffffff'
                }]
            },
            'options': {
                'responsive': True,
                'maintainAspectRatio': False,
                'plugins': {
                    'title': {
                        'display': True,
                        'text': options.get('title', 'Répartition'),
                        'font': {'size': 16}
                    },
                    'legend': {
                        'position': 'bottom'
                    }
                }
            }
        }
    
    def _create_bar_chart(self, data: List[Dict[str, Any]], options: Dict[str, Any]) -> Dict[str, Any]:
        """
        Crée un graphique en barres
        """
        if not data:
            return self._create_error_chart("Aucune donnée pour le graphique en barres")
        
        # Extraire les clés automatiquement
        sample = data[0]
        x_key = options.get('x_key', list(sample.keys())[0])
        y_key = options.get('y_key', list(sample.keys())[1] if len(sample.keys()) > 1 else list(sample.keys())[0])
        
        labels = [str(item.get(x_key, '')) for item in data]
        values = [float(item.get(y_key, 0)) for item in data]
        
        return {
            'type': 'bar',
            'data': {
                'labels': labels,
                'datasets': [{
                    'label': y_key.replace('_', ' ').title(),
                    'data': values,
                    'backgroundColor': self.default_colors[0],
                    'borderColor': self.default_colors[0],
                    'borderWidth': 1
                }]
            },
            'options': {
                'responsive': True,
                'maintainAspectRatio': False,
                'plugins': {
                    'title': {
                        'display': True,
                        'text': options.get('title', f'{y_key} par {x_key}'),
                        'font': {'size': 16}
                    }
                },
                'scales': {
                    'y': {
                        'beginAtZero': True,
                        'title': {
                            'display': True,
                            'text': y_key.replace('_', ' ').title()
                        }
                    },
                    'x': {
                        'title': {
                            'display': True,
                            'text': x_key.replace('_', ' ').title()
                        }
                    }
                }
            }
        }
    
    def _create_line_chart(self, data: List[Dict[str, Any]], options: Dict[str, Any]) -> Dict[str, Any]:
        """
        Crée un graphique en courbes
        """
        if not data:
            return self._create_error_chart("Aucune donnée pour le graphique en courbes")
        
        sample = data[0]
        x_key = options.get('x_key', list(sample.keys())[0])
        y_key = options.get('y_key', list(sample.keys())[1] if len(sample.keys()) > 1 else list(sample.keys())[0])
        
        labels = [str(item.get(x_key, '')) for item in data]
        values = [float(item.get(y_key, 0)) for item in data]
        
        return {
            'type': 'line',
            'data': {
                'labels': labels,
                'datasets': [{
                    'label': y_key.replace('_', ' ').title(),
                    'data': values,
                    'borderColor': self.default_colors[0],
                    'backgroundColor': self.default_colors[0] + '20',  # Transparence
                    'borderWidth': 2,
                    'fill': False,
                    'tension': 0.4
                }]
            },
            'options': {
                'responsive': True,
                'maintainAspectRatio': False,
                'plugins': {
                    'title': {
                        'display': True,
                        'text': options.get('title', f'Évolution de {y_key}'),
                        'font': {'size': 16}
                    }
                },
                'scales': {
                    'y': {
                        'beginAtZero': True,
                        'title': {
                            'display': True,
                            'text': y_key.replace('_', ' ').title()
                        }
                    },
                    'x': {
                        'title': {
                            'display': True,
                            'text': x_key.replace('_', ' ').title()
                        }
                    }
                }
            }
        }
    
    def _create_doughnut_chart(self, data: List[Dict[str, Any]], options: Dict[str, Any]) -> Dict[str, Any]:
        """
        Crée un graphique en anneau (doughnut)
        """
        pie_config = self._create_pie_chart(data, options)
        pie_config['type'] = 'doughnut'
        pie_config['options']['cutout'] = '60%'
        return pie_config
    
    def _create_area_chart(self, data: List[Dict[str, Any]], options: Dict[str, Any]) -> Dict[str, Any]:
        """
        Crée un graphique en aires
        """
        line_config = self._create_line_chart(data, options)
        line_config['data']['datasets'][0]['fill'] = True
        line_config['data']['datasets'][0]['backgroundColor'] = self.default_colors[0] + '40'
        return line_config
    
    def _create_scatter_chart(self, data: List[Dict[str, Any]], options: Dict[str, Any]) -> Dict[str, Any]:
        """
        Crée un graphique de dispersion
        """
        if not data:
            return self._create_error_chart("Aucune donnée pour le graphique de dispersion")
        
        sample = data[0]
        x_key = options.get('x_key', list(sample.keys())[0])
        y_key = options.get('y_key', list(sample.keys())[1] if len(sample.keys()) > 1 else list(sample.keys())[0])
        
        scatter_data = []
        for item in data:
            x_val = item.get(x_key, 0)
            y_val = item.get(y_key, 0)
            scatter_data.append({'x': float(x_val), 'y': float(y_val)})
        
        return {
            'type': 'scatter',
            'data': {
                'datasets': [{
                    'label': f'{y_key} vs {x_key}',
                    'data': scatter_data,
                    'backgroundColor': self.default_colors[0],
                    'borderColor': self.default_colors[0],
                    'pointRadius': 5
                }]
            },
            'options': {
                'responsive': True,
                'maintainAspectRatio': False,
                'plugins': {
                    'title': {
                        'display': True,
                        'text': options.get('title', f'{y_key} vs {x_key}'),
                        'font': {'size': 16}
                    }
                },
                'scales': {
                    'x': {
                        'title': {
                            'display': True,
                            'text': x_key.replace('_', ' ').title()
                        }
                    },
                    'y': {
                        'title': {
                            'display': True,
                            'text': y_key.replace('_', ' ').title()
                        }
                    }
                }
            }
        }
    
    def _auto_detect_chart_type(self, data: Any, options: Dict[str, Any]) -> Dict[str, Any]:
        """
        Détecte automatiquement le meilleur type de graphique
        """
        if isinstance(data, list) and len(data) > 0:
            sample = data[0]
            
            # Si c'est des données nom/valeur, utiliser un camembert
            if 'name' in sample and 'value' in sample:
                return self._create_pie_chart(data, options)
            
            # Si c'est une série temporelle, utiliser une courbe
            keys = list(sample.keys())
            if len(keys) >= 2:
                # Vérifier s'il y a une colonne qui ressemble à une date
                for key in keys:
                    if 'date' in key.lower() or 'time' in key.lower():
                        options['x_key'] = key
                        options['y_key'] = [k for k in keys if k != key][0]
                        return self._create_line_chart(data, options)
                
                # Par défaut, utiliser un graphique en barres
                return self._create_bar_chart(data, options)
        
        return self._create_error_chart("Format de données non reconnu")
    
    def _create_error_chart(self, error_message: str) -> Dict[str, Any]:
        """
        Crée un graphique d'erreur
        """
        return {
            'type': 'bar',
            'data': {
                'labels': ['Erreur'],
                'datasets': [{
                    'label': 'Erreur',
                    'data': [0],
                    'backgroundColor': '#EF4444'
                }]
            },
            'options': {
                'responsive': True,
                'plugins': {
                    'title': {
                        'display': True,
                        'text': f'Erreur: {error_message}',
                        'color': '#EF4444'
                    }
                }
            }
        }
    
    def create_dashboard_charts(self, data_sets: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Crée plusieurs graphiques pour un tableau de bord
        """
        charts = []
        
        for name, dataset in data_sets.items():
            chart_config = self.generate_chart_config(
                dataset['data'], 
                dataset.get('type', 'bar'),
                {'title': dataset.get('title', name)}
            )
            charts.append({
                'id': name,
                'config': chart_config,
                'title': dataset.get('title', name)
            })
        
        return charts
    
    def export_chart_image(self, chart_config: Dict[str, Any], width: int = 800, height: int = 600) -> Optional[str]:
        """
        Exporte un graphique en image (nécessite Chart.js headless ou Plotly)
        Retourne le chemin vers l'image générée
        """
        # TODO: Implémenter l'export d'images avec headless Chrome ou Plotly
        # Pour l'instant, retourner None
        logger.info("Export d'image de graphique non encore implémenté")
        return None
