"""
views_express.py

APIs pour le workflow d'inspection express
Permet d'inspecter des points de contrôle spécifiques sans passer par tous
"""

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.contrib.auth.models import User
from decimal import Decimal
import json

from apps.inspections.models import (
    Inspection,
    PointDeControleComposant,
    ResultatInspectionComposant,
    ActionCorrective
)
from apps.billing.models import PointEau
from apps.infrastructure.models import EquipementConstitutif


@require_http_methods(["GET"])
def api_control_points_for_item(request, item_type, item_id):
    """
    Récupère les points de contrôle disponibles pour un item

    Args:
        item_type (str): Type d'item ('point_eau' ou 'equipement')
        item_id (str): UUID de l'item

    Returns:
        JsonResponse: Liste des points de contrôle
    """
    try:
        if item_type == 'point_eau':
            # Vérifier que le point d'eau existe
            try:
                point_eau = PointEau.objects.select_related('type_point_eau').get(id=item_id)
            except PointEau.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Point d\'eau introuvable'
                }, status=404)

            # Récupérer le type de point d'eau
            type_pe = point_eau.type_point_eau
            if not type_pe:
                return JsonResponse({
                    'success': False,
                    'error': 'Type de point d\'eau non défini'
                }, status=400)

            # Récupérer les points de contrôle liés aux composants du type de point d'eau
            points_controle = PointDeControleComposant.objects.filter(
                composant_point_eau__type_point_eau=type_pe
            ).select_related(
                'point_de_controle',
                'composant_point_eau'
            ).order_by(
                'composant_point_eau__ordre_affichage',
                'ordre_affichage',
                'point_de_controle__nom'
            )

        elif item_type == 'equipement':
            # Vérifier que l'équipement existe
            try:
                equipement = EquipementConstitutif.objects.select_related('type_equipement').get(id=item_id)
            except EquipementConstitutif.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Équipement introuvable'
                }, status=404)

            # Récupérer le type d'équipement
            type_eq = equipement.type_equipement
            if not type_eq:
                return JsonResponse({
                    'success': False,
                    'error': 'Type d\'équipement non défini'
                }, status=400)

            # Récupérer les points de contrôle liés aux composants du type d'équipement
            points_controle = PointDeControleComposant.objects.filter(
                composant_equipement__type_equipement=type_eq
            ).select_related(
                'point_de_controle',
                'composant_equipement'
            ).order_by(
                'composant_equipement__ordre_affichage',
                'ordre_affichage',
                'point_de_controle__nom'
            )

        else:
            return JsonResponse({
                'success': False,
                'error': 'Type d\'item invalide (doit être point_eau ou equipement)'
            }, status=400)

        # Formater les données
        control_points_data = []
        for lien in points_controle:
            point = lien.point_de_controle
            composant = lien.composant_point_eau or lien.composant_equipement
            control_points_data.append({
                'id': str(lien.id),
                'point_id': str(point.id),
                'nom': point.nom,
                'type': point.type_resultat,
                'ordre': lien.ordre_affichage,
                'composant_nom': composant.nom_composant if composant else '',
                'composant_id': str(composant.id) if composant else None,
                'composant_type': 'point_eau' if lien.composant_point_eau_id else 'equipement',
                'photo_reference_url': lien.photo_reference.get_download_url() if lien.photo_reference else None
            })

        return JsonResponse({
            'success': True,
            'control_points': control_points_data
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_create_inspection_express(request):
    """
    Crée une nouvelle inspection express

    Request body:
        {
            "item_id": "uuid",
            "item_type": "point_eau" ou "equipement"
        }

    Returns:
        JsonResponse: ID de l'inspection créée et numéro d'inspection
    """
    try:
        data = json.loads(request.body)
        item_id = data.get('item_id')
        item_type = data.get('item_type')

        if not item_id or not item_type:
            return JsonResponse({
                'success': False,
                'error': 'Paramètres manquants (item_id, item_type)'
            }, status=400)

        # Générer un numéro d'inspection unique
        timestamp = timezone.now().strftime('%Y%m%d%H%M%S%f')
        numero_inspection = f"INSP-EXP-{timestamp}"

        inspecteur = request.user if request.user.is_authenticated else User.objects.first()
        if not inspecteur:
            return JsonResponse({
                'success': False,
                'error': 'Aucun inspecteur disponible'
            }, status=400)

        # Valider l'item et préparer la liaison
        if item_type == 'point_eau':
            if not PointEau.objects.filter(id=item_id).exists():
                return JsonResponse({
                    'success': False,
                    'error': 'Point d\'eau introuvable'
                }, status=404)
        elif item_type == 'equipement':
            if not EquipementConstitutif.objects.filter(id=item_id).exists():
                return JsonResponse({
                    'success': False,
                    'error': 'Équipement introuvable'
                }, status=404)
        else:
            return JsonResponse({
                'success': False,
                'error': 'Type d\'item invalide (doit être point_eau ou equipement)'
            }, status=400)

        # Créer l'inspection
        inspection = Inspection.objects.create(
            numero_inspection=numero_inspection,
            type_inspection='express',
            statut='en_cours',
            date_inspection=timezone.now(),
            inspecteur=inspecteur
        )

        # Lier l'item selon le type
        if item_type == 'point_eau':
            inspection.point_eau_id = item_id
        else:
            inspection.equipement_id = item_id

        inspection.save()

        return JsonResponse({
            'success': True,
            'inspection_id': str(inspection.id),
            'numero_inspection': numero_inspection
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_save_inspection_result(request):
    """
    Enregistre le résultat d'un point de contrôle

    Request body:
        {
            "inspection_id": "uuid",
            "point_link_id": "uuid",
            "valeur_bool": true/false (si type BOOL),
            "valeur_num": 123.45 (si type NUM),
            "valeur_text": "texte" (si type TEXT),
            "observations": "texte optionnel",
            "photo": "data:image/png;base64,..." (optionnel)
        }

    Returns:
        JsonResponse: Confirmation de l'enregistrement
    """
    try:
        data = json.loads(request.body)
        inspection_id = data.get('inspection_id')
        point_link_id = data.get('point_link_id')

        if not inspection_id or not point_link_id:
            return JsonResponse({
                'success': False,
                'error': 'Paramètres manquants (inspection_id, point_link_id)'
            }, status=400)

        # Vérifier que l'inspection existe
        try:
            inspection = Inspection.objects.get(id=inspection_id)
        except Inspection.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Inspection introuvable'
            }, status=404)

        # Vérifier que le point de contrôle existe via le lien composant
        try:
            lien = PointDeControleComposant.objects.select_related(
                'point_de_controle',
                'composant_equipement',
                'composant_point_eau'
            ).get(id=point_link_id)
        except PointDeControleComposant.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Lien point de contrôle introuvable'
            }, status=404)

        point_controle = lien.point_de_controle
        composant_equipement = lien.composant_equipement
        composant_point_eau = lien.composant_point_eau

        if not composant_equipement and not composant_point_eau:
            return JsonResponse({
                'success': False,
                'error': 'Composant introuvable pour ce point de contrôle'
            }, status=400)

        operateur = request.user if request.user.is_authenticated else User.objects.first()
        if not operateur:
            return JsonResponse({
                'success': False,
                'error': 'Aucun opérateur disponible'
            }, status=400)

        # Créer ou mettre à jour le résultat
        resultat, created = ResultatInspectionComposant.objects.get_or_create(
            inspection=inspection,
            point_de_controle=point_controle,
            composant_equipement=composant_equipement,
            composant_point_eau=composant_point_eau,
            defaults={
                'observations': data.get('observations', ''),
                'date_mesure': timezone.now(),
                'operateur': operateur
            }
        )

        resultat.observations = data.get('observations', '')
        resultat.date_mesure = timezone.now()
        resultat.operateur = operateur
        resultat.unite = point_controle.unite or ''

        # Mettre à jour les valeurs selon le type
        if point_controle.type_resultat == 'BOOL':
            if 'valeur_bool' not in data:
                return JsonResponse({
                    'success': False,
                    'error': 'Valeur booléenne manquante'
                }, status=400)
            resultat.valeur_mesuree = 'Oui' if data['valeur_bool'] else 'Non'
            resultat.valeur_numerique = None

        elif point_controle.type_resultat == 'NUM':
            if 'valeur_num' not in data:
                return JsonResponse({
                    'success': False,
                    'error': 'Valeur numérique manquante'
                }, status=400)
            try:
                resultat.valeur_numerique = Decimal(str(data['valeur_num']))
            except (ValueError, TypeError):
                return JsonResponse({
                    'success': False,
                    'error': 'Valeur numérique invalide'
                }, status=400)
            resultat.valeur_mesuree = str(data['valeur_num'])

        elif point_controle.type_resultat == 'TEXT':
            if 'valeur_text' not in data:
                return JsonResponse({
                    'success': False,
                    'error': 'Valeur textuelle manquante'
                }, status=400)
            resultat.valeur_mesuree = data['valeur_text']
            resultat.valeur_numerique = None

        # Gérer l'action corrective si fournie
        corrective_action = data.get('corrective_action')
        if corrective_action and isinstance(corrective_action, dict):
            from datetime import date
            date_str = corrective_action.get('date_prevue')
            date_prevue = None
            if date_str:
                try:
                    date_prevue = date.fromisoformat(date_str)
                except ValueError:
                    date_prevue = None
            if not date_prevue:
                date_prevue = date.today()

            activite_label = (corrective_action.get('activite') or '').strip()
            remarque = (corrective_action.get('remarque') or '').strip()

            description_parts = []
            if activite_label:
                description_parts.append(f"Activité: {activite_label}")
            if remarque:
                description_parts.append(f"Remarque: {remarque}")
            description = "\n".join(description_parts) if description_parts else "Action corrective."

            action = resultat.actions_correctives.first() if hasattr(resultat, 'actions_correctives') else None
            if not action:
                action = ActionCorrective(
                    resultat_inspection=resultat,
                    titre=f"Action corrective - {point_controle.nom}",
                    description=description,
                    priorite='normale',
                    date_prevue=date_prevue,
                    responsable=operateur
                )
            else:
                action.description = description
                action.date_prevue = date_prevue

            if activite_label:
                try:
                    from apps.planning.models import Activite
                    activite_mapping = {
                        'maintenance': 'maintenance',
                        'reparation': 'reparation',
                        'réparation': 'reparation',
                        'remplacement': 'remplacement',
                        'nettoyage': 'nettoyage',
                        'verification': 'verification',
                        'vérification': 'verification'
                    }
                    lookup = activite_mapping.get(activite_label.lower(), activite_label)
                    action.activite = Activite.objects.filter(nom__icontains=lookup).first()
                except Exception:
                    pass

            action.save()

        # Gérer la photo si fournie (stockée en base64 dans la liste)
        photo_data = data.get('photo')
        if photo_data and isinstance(photo_data, str) and photo_data.startswith('data:image'):
            photos = resultat.photos or []
            photos.append(photo_data)
            resultat.photos = photos

        resultat.save()

        return JsonResponse({
            'success': True,
            'resultat_id': str(resultat.id),
            'message': 'Résultat enregistré avec succès'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_finish_inspection_express(request):
    """
    Termine une inspection express

    Request body:
        {
            "inspection_id": "uuid"
        }

    Returns:
        JsonResponse: Confirmation de la finalisation
    """
    try:
        data = json.loads(request.body)
        inspection_id = data.get('inspection_id')

        if not inspection_id:
            return JsonResponse({
                'success': False,
                'error': 'inspection_id manquant'
            }, status=400)

        # Vérifier que l'inspection existe
        try:
            inspection = Inspection.objects.get(id=inspection_id)
        except Inspection.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Inspection introuvable'
            }, status=404)

        # Marquer comme terminée
        inspection.statut = 'terminee'
        inspection.save()

        return JsonResponse({
            'success': True,
            'message': 'Inspection terminée avec succès',
            'numero_inspection': inspection.numero_inspection
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
