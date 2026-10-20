"""
Vues pour l'analyse des packs d'analyses d'eau.
Logique métier : Un pack = groupe d'analyses faites le même jour (date_analyse).
"""

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Count, Min, Max
from datetime import datetime
from collections import defaultdict

from .models_analyse_eau import AnalyseEau
from apps.geography.models import Commune


@require_http_methods(["GET"])
def api_packs_analyses_stats(request):
    """
    API pour obtenir les statistiques par pack d'analyse.

    Un pack = toutes les analyses faites le même jour (date_analyse identique).

    Statut du pack :
    - ✅ VALIDE : Contient au moins un témoin positif (coliformes sur point_eau_traditionnel)
                  ET aucune contamination de bouteille
                  ET aucune anomalie sur équipements/points d'eau

    - ⚠️ PROBLEMATIQUE : Coliformes trouvés sur équipement ou point_eau
                         (mais pas de contamination bouteille)

    - ❌ CONTAMINE : Coliformes trouvés sur bouteille → pack invalide
    """
    try:
        # Récupérer les filtres
        annee = request.GET.get('annee')
        commune_id = request.GET.get('commune_id')

        # Récupérer toutes les analyses
        analyses = AnalyseEau.objects.all().select_related(
            'equipement',
            'equipement__ouvrage',
            'point_eau',
            'point_eau__parcelle__village__fokontany__commune'
        )

        # Filtrer par année
        if annee:
            analyses = analyses.filter(date_analyse__year=int(annee))

        # Grouper par date d'analyse (sans heure)
        packs = defaultdict(list)
        for analyse in analyses:
            # Filtrer par commune si spécifié
            if commune_id and commune_id != 'all':
                if analyse.commune_nom:
                    try:
                        commune = Commune.objects.get(id=commune_id)
                        if analyse.commune_nom != commune.nom_commune:
                            continue
                    except Commune.DoesNotExist:
                        continue

            date_key = analyse.date_analyse.date().isoformat()
            packs[date_key].append(analyse)

        # Analyser chaque pack
        packs_data = []
        stats_globales = {
            'total_packs': 0,
            'packs_valides': 0,
            'packs_problematiques': 0,
            'packs_contamines': 0,
            'total_analyses': 0
        }

        for date_str, analyses_pack in packs.items():
            # Compteurs par type
            nb_equipements = 0
            nb_points_eau = 0
            nb_traditionnels = 0
            nb_bouteilles = 0
            nb_autres = 0

            # Détection des problèmes
            has_temoin_positif = False
            has_contamination_bouteille = False
            has_probleme_equipement = False
            has_probleme_point_eau = False

            analyses_problematiques = []

            for a in analyses_pack:
                # Compter par type
                if a.type_prelevement == 'equipement':
                    nb_equipements += 1
                    # Si positif sur équipement → PROBLEME
                    if a.est_positif:
                        has_probleme_equipement = True
                        analyses_problematiques.append({
                            'type': 'equipement',
                            'lieu': a.lieu_affichage,
                            'nombre_pour_100ml': a.nombre_pour_100ml
                        })

                elif a.type_prelevement == 'point_eau':
                    nb_points_eau += 1
                    # Si positif sur point d'eau → PROBLEME
                    if a.est_positif:
                        has_probleme_point_eau = True
                        analyses_problematiques.append({
                            'type': 'point_eau',
                            'lieu': a.lieu_affichage,
                            'nombre_pour_100ml': a.nombre_pour_100ml
                        })

                elif a.type_prelevement == 'point_eau_traditionnel':
                    nb_traditionnels += 1
                    # Si positif sur traditionnel → TEMOIN VALIDE
                    if a.est_positif:
                        has_temoin_positif = True

                elif a.type_prelevement == 'bouteille':
                    nb_bouteilles += 1
                    # Si positif sur bouteille → CONTAMINATION
                    if a.est_positif:
                        has_contamination_bouteille = True
                        analyses_problematiques.append({
                            'type': 'bouteille',
                            'lieu': a.lieu_affichage,
                            'nombre_pour_100ml': a.nombre_pour_100ml
                        })

                else:
                    nb_autres += 1

            # Déterminer le statut du pack
            if has_contamination_bouteille:
                statut = 'contamine'
                statut_label = 'Contaminé'
                statut_badge = 'error'
                stats_globales['packs_contamines'] += 1
            elif has_probleme_equipement or has_probleme_point_eau:
                statut = 'problematique'
                statut_label = 'Problématique'
                statut_badge = 'warning'
                stats_globales['packs_problematiques'] += 1
            elif has_temoin_positif:
                statut = 'valide'
                statut_label = 'Validé'
                statut_badge = 'success'
                stats_globales['packs_valides'] += 1
            else:
                # Aucun témoin positif → statut indéterminé
                statut = 'indetermine'
                statut_label = 'Indéterminé'
                statut_badge = 'ghost'

            packs_data.append({
                'date_analyse': date_str,
                'date_analyse_fr': datetime.fromisoformat(date_str).strftime('%d/%m/%Y'),
                'nb_analyses': len(analyses_pack),
                'nb_equipements': nb_equipements,
                'nb_points_eau': nb_points_eau,
                'nb_traditionnels': nb_traditionnels,
                'nb_bouteilles': nb_bouteilles,
                'nb_autres': nb_autres,
                'statut': statut,
                'statut_label': statut_label,
                'statut_badge': statut_badge,
                'has_temoin_positif': has_temoin_positif,
                'has_contamination': has_contamination_bouteille,
                'analyses_problematiques': analyses_problematiques
            })

            stats_globales['total_analyses'] += len(analyses_pack)

        stats_globales['total_packs'] = len(packs_data)

        # Trier par date décroissante
        packs_data.sort(key=lambda x: x['date_analyse'], reverse=True)

        return JsonResponse({
            'success': True,
            'packs': packs_data,
            'stats': stats_globales
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def api_pack_details(request, date_analyse):
    """
    API pour obtenir les détails d'un pack spécifique.

    Paramètres:
    - date_analyse: Date ISO (YYYY-MM-DD)
    """
    try:
        # Parser la date
        try:
            date_obj = datetime.fromisoformat(date_analyse).date()
        except ValueError:
            return JsonResponse({
                'success': False,
                'error': 'Format de date invalide. Utiliser YYYY-MM-DD'
            }, status=400)

        # Récupérer les analyses de ce jour
        analyses = AnalyseEau.objects.filter(
            date_analyse__date=date_obj
        ).select_related(
            'equipement',
            'equipement__ouvrage',
            'point_eau',
            'point_eau__parcelle__village__fokontany__commune'
        ).order_by('date_prelevement')

        if not analyses.exists():
            return JsonResponse({
                'success': False,
                'error': 'Aucune analyse trouvée pour cette date'
            }, status=404)

        # Convertir en liste
        data = []
        for analyse in analyses:
            data.append({
                'id': str(analyse.id),
                'type_prelevement': analyse.type_prelevement,
                'type_prelevement_display': analyse.get_type_prelevement_display(),
                'lieu': analyse.lieu_affichage,
                'description_lieu': analyse.description_lieu,
                'date_prelevement': analyse.date_prelevement.strftime('%d/%m/%Y %H:%M'),
                'date_analyse': analyse.date_analyse.strftime('%d/%m/%Y %H:%M'),
                'date_resultat': analyse.date_resultat.strftime('%d/%m/%Y %H:%M'),
                'volume_analyse': analyse.volume_analyse,
                'nombre_coliformes': analyse.nombre_coliformes,
                'tnc': analyse.tnc,
                'nombre_pour_100ml': analyse.nombre_pour_100ml,
                'ph': float(analyse.ph) if analyse.ph else None,
                'observation': analyse.observation,
                'est_positif': analyse.est_positif,
                'commune': analyse.commune_nom,
                'village': analyse.village_nom,
            })

        return JsonResponse({
            'success': True,
            'date_analyse': date_analyse,
            'total': len(data),
            'analyses': data
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
