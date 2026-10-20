"""
Vues pour le recoupement intelligent DiameX <-> Relevés
"""

from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import re
import json
import traceback


@login_required
@require_http_methods(["GET"])
def api_rechercher_releves_candidats(request):
    """
    API pour rechercher les relevés candidats depuis une entrée DiameX orpheline.
    Analyse la description DiameX pour extraire l'ouvrage et le mois,
    puis recherche les relevés correspondants sans numeroDiameX.
    """
    try:
        from apps.billing.models import Releve, PointEau
        from apps.organization.models import Ouvrage
        from apps.accounting.models import BaseDiameX
        from django.db.models import Q

        # Récupérer les paramètres
        id_diamex = request.GET.get('id_diamex')
        id_access = request.GET.get('id_access')
        prog = request.GET.get('prog')
        description = request.GET.get('description', '')

        if not all([id_diamex, id_access, prog]):
            return JsonResponse({
                'success': False,
                'error': 'Paramètres manquants (id_diamex, id_access, prog)'
            }, status=400)

        # Récupérer l'entrée DiameX complète
        try:
            diamex_entry = BaseDiameX.objects.get(id=int(id_diamex))
        except BaseDiameX.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Entrée DiameX non trouvée'
            }, status=404)

        # Utiliser l'extracteur générique pour analyser la description
        from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique

        extraction = extraire_ouvrage_et_mois_generique(description, diamex_entry.compte_code)

        ouvrage_obj = extraction.get('ouvrage_obj')
        ouvrage_nom_extrait = extraction.get('ouvrage_nom')
        mois_extrait = extraction.get('mois')
        annee_extrait = extraction.get('annee')

        # Si l'extraction a trouvé un mois/année, les utiliser
        if mois_extrait and annee_extrait:
            # Le mois extrait représente le mois de facturation (mois SUIVANT le relevé)
            # Donc si mois_extrait = 10, le relevé est du mois de septembre (09)
            if mois_extrait > 1:
                mois_releve = mois_extrait - 1
                annee_releve = annee_extrait
            else:
                mois_releve = 12
                annee_releve = annee_extrait - 1
        else:
            # Fallback : utiliser la date_m de l'entrée DiameX
            if diamex_entry.date_m:
                date_m = diamex_entry.date_m
                if date_m.month > 1:
                    mois_releve = date_m.month - 1
                    annee_releve = date_m.year
                else:
                    mois_releve = 12
                    annee_releve = date_m.year - 1
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'Impossible d\'extraire le mois de la description ou date_m'
                }, status=400)

        # Si l'extraction a trouvé un ouvrage, utiliser celui-ci
        if ouvrage_obj:
            ouvrages_candidats = Ouvrage.objects.filter(id=ouvrage_obj.id)
        elif ouvrage_nom_extrait:
            # Recherche flexible par nom
            ouvrages_candidats = Ouvrage.objects.filter(
                nom_ouvrage__icontains=ouvrage_nom_extrait[:20]
            )
            # Si aucun ouvrage trouvé, essayer avec des mots-clés
            if not ouvrages_candidats.exists():
                mots_cles = ouvrage_nom_extrait.split()[:3]
                if mots_cles:
                    query = Q()
                    for mot in mots_cles:
                        if len(mot) > 2:
                            query |= Q(nom_ouvrage__icontains=mot)
                    ouvrages_candidats = Ouvrage.objects.filter(query)
        else:
            # Pas d'ouvrage extrait du tout
            ouvrages_candidats = Ouvrage.objects.none()

        # Récupérer les points d'eau de ces ouvrages
        ouvrages_ids = list(ouvrages_candidats.values_list('id', flat=True))
        points_eau_ids = PointEau.objects.filter(
            ouvrage_id__in=ouvrages_ids
        ).values_list('id', flat=True)

        # Rechercher les relevés correspondants SANS numeroDiameX (non comptabilisés)
        # On cherche d'abord avec l'année spécifique, puis sans filtre d'année si rien trouvé
        releves_candidats = Releve.objects.filter(
            point_eau_id__in=points_eau_ids,
            datereleve__year=annee_releve,
            datereleve__month=mois_releve,
            numeroDiameX__isnull=True,  # Seulement les relevés non comptabilisés
            montant__isnull=False  # Avec montant calculé
        ).select_related('point_eau', 'point_eau__ouvrage').order_by('-datereleve', 'point_eau__ouvrage__nom_ouvrage', 'point_eau__code_point_eau')

        # Si aucun relevé trouvé pour l'année spécifique, chercher dans toutes les années
        if not releves_candidats.exists():
            releves_candidats = Releve.objects.filter(
                point_eau_id__in=points_eau_ids,
                datereleve__month=mois_releve,
                numeroDiameX__isnull=True,
                montant__isnull=False
            ).select_related('point_eau', 'point_eau__ouvrage').order_by('-datereleve', 'point_eau__ouvrage__nom_ouvrage', 'point_eau__code_point_eau')

        # Sérialiser les données
        releves_data = []
        total_montant_candidats = 0

        for releve in releves_candidats:
            # Convertir la date (datereleve est un datetime.date, pas datetime)
            if releve.datereleve:
                date_str = releve.datereleve.strftime('%Y-%m-%d')
            else:
                date_str = None

            montant = float(releve.montant) if releve.montant else 0
            total_montant_candidats += montant

            releves_data.append({
                'id': str(releve.id),
                'point_eau_code': releve.point_eau.code_point_eau if releve.point_eau and releve.point_eau.code_point_eau else releve.point_eau.nomabonne if releve.point_eau else 'Sans PE',
                'ouvrage_nom': releve.point_eau.ouvrage.nom_ouvrage if releve.point_eau and releve.point_eau.ouvrage else 'Sans ouvrage',
                'ouvrage_id': str(releve.point_eau.ouvrage.id) if releve.point_eau and releve.point_eau.ouvrage else None,
                'date_releve': date_str,
                'nouvel_index': float(releve.nouvelindex) if releve.nouvelindex else 0,
                'volume': float(releve.consommation) if releve.consommation else 0,
                'montant': montant,
            })

        return JsonResponse({
            'success': True,
            'releves_candidats': releves_data,
            'total_candidats': len(releves_data),
            'total_montant_candidats': total_montant_candidats,
            'montant_diamex_in': float(diamex_entry.montant_in or 0),
            'montant_diamex_out': float(diamex_entry.montant_out or 0),
            'ecart': float(diamex_entry.montant_in or 0) - total_montant_candidats,
            'info_extraction': {
                'ouvrage_nom_extrait': ouvrage_nom_extrait,
                'mois_releve': mois_releve,
                'annee_releve': annee_releve,
                'nb_ouvrages_candidats': len(ouvrages_ids)
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


@login_required
@require_http_methods(["POST"])
@csrf_exempt
def api_associer_releves_diamex(request):
    """
    API pour associer les relevés sélectionnés à une entrée DiameX.
    Remplit les champs numeroDiameX et baseDiameX pour les relevés cochés.
    """
    try:
        from apps.billing.models import Releve

        data = json.loads(request.body)
        releves_ids = data.get('releves_ids', [])
        id_access = data.get('id_access')
        prog = data.get('prog')

        if not all([releves_ids, id_access, prog]):
            return JsonResponse({
                'success': False,
                'error': 'Paramètres manquants (releves_ids, id_access, prog)'
            }, status=400)

        if not isinstance(releves_ids, list) or len(releves_ids) == 0:
            return JsonResponse({
                'success': False,
                'error': 'Aucun relevé sélectionné'
            }, status=400)

        # Mettre à jour les relevés
        nb_updated = Releve.objects.filter(
            id__in=releves_ids,
            numeroDiameX__isnull=True  # Seulement ceux qui ne sont pas déjà associés
        ).update(
            numeroDiameX=str(id_access),
            baseDiameX=prog
        )

        return JsonResponse({
            'success': True,
            'message': f'{nb_updated} relevé(s) associé(s) à DiameX ({id_access}, {prog})',
            'nb_updated': nb_updated
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)
