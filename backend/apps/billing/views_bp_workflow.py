"""
APIs pour le workflow complet des paiements BP
"""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db import transaction
from decimal import Decimal
from datetime import datetime, date
import json

from .bp_branchement_utils import normalize_missing_bp_branchement
from .models import PointEau, Releve
from apps.accounting.models import DiameXTemporaire
from apps.organization.models import Ouvrage
from apps.organization.scoping import get_user_accessible_gestionnaire_ids


def _get_user_organisation_id(user):
    employe = getattr(user, 'employe', None)
    base = getattr(employe, 'base', None)
    return getattr(base, 'organisation_id', None)


def _get_point_eau_qs_for_user(user):
    qs = PointEau.objects.all()
    if getattr(user, 'is_superuser', False):
        return qs

    gestionnaire_ids = get_user_accessible_gestionnaire_ids(user)
    if gestionnaire_ids is None:
        return qs
    if not gestionnaire_ids:
        return qs.none()

    return qs.filter(
        ouvrage__modalites_gestion__date_fin__isnull=True,
        ouvrage__modalites_gestion__gestionnaire_id__in=gestionnaire_ids
    ).distinct()


def _get_point_eau_for_user(user, point_eau_id, *relations):
    qs = _get_point_eau_qs_for_user(user)
    if relations:
        qs = qs.select_related(*relations)
    return qs.filter(id=point_eau_id).first()


@csrf_exempt
@require_http_methods(["POST"])
def api_paiement_demande(request, point_eau_id):
    """
    API pour traiter le paiement de la demande BP
    - Calcul automatique du montant depuis tarif_demande de l'organisation
    - Export vers DiameXTemporaire
    - Génération des données pour le ticket de caisse
    """
    try:
        point_eau = _get_point_eau_for_user(
            request.user,
            point_eau_id,
            'ouvrage',
            'type_point_eau',
            'parcelle__village__fokontany__commune'
        )
        if not point_eau:
            return JsonResponse({
                'success': False,
                'error': 'Point d\'eau introuvable'
            }, status=404)

        # Vérifier qu'il n'y a pas déjà un numéro DiameX demande
        if point_eau.numerodiamexdemande:
            return JsonResponse({
                'success': False,
                'error': f'Le paiement de la demande a déjà été enregistré (N° DiameX: {point_eau.numerodiamexdemande})'
            }, status=400)

        # Récupérer l'organisation liée à l'ouvrage via ModaliteGestion
        organisation = None
        if point_eau.ouvrage:
            from apps.billing.models import ModaliteGestion
            modalite_active = ModaliteGestion.objects.filter(
                ouvrage=point_eau.ouvrage,
                date_fin__isnull=True
            ).select_related('gestionnaire').first()

            if modalite_active and modalite_active.gestionnaire:
                organisation = modalite_active.gestionnaire

        if not organisation:
            return JsonResponse({
                'success': False,
                'error': 'Impossible de déterminer l\'organisation gestionnaire de cet ouvrage'
            }, status=400)

        # Récupérer le tarif_demande de l'organisation
        if not organisation.tarif_demande:
            return JsonResponse({
                'success': False,
                'error': f'Le tarif de demande n\'est pas configuré pour l\'organisation {organisation.nom_organisation}'
            }, status=400)

        montant = organisation.tarif_demande

        with transaction.atomic():
            # Mettre à jour le point d'eau
            point_eau.montantdemandepaye = float(montant)
            point_eau.datepaiementdemande = date.today()
            point_eau.save()

            # Créer la ligne dans DiameXTemporaire
            description = f"Paiement demande BP - {point_eau.nomabonne or point_eau.code_point_eau}"
            if point_eau.parcelle and point_eau.parcelle.village:
                description += f" ({point_eau.parcelle.village.nom_village})"

            diamex_temp = DiameXTemporaire.objects.create(
                type_transaction='recette',
                date_rec=date.today(),
                description=description,
                montant_in=float(montant),
                montant_out=0,
                compte_code='748401',  # Compte obligatoire pour les demandes BP
                statut='en_attente',
                info='hydria paiement demande',
                detail=point_eau.nomabonne or '',
            )

            # Générer le numéro de ticket (basé sur l'ID DiameX)
            numero_ticket = f"BP-DEM-{diamex_temp.id:06d}"

            # Récupérer l'organisation de l'employé connecté
            organisation_data = {
                'nom': 'HYDRIA',
                'adresse': 'Madagascar',
                'nif': 'N/A',
                'stat': 'N/A',
                'base': 'Centrale',
                'logo_url': ''
            }

            if hasattr(request.user, 'employe') and request.user.employe:
                employe = request.user.employe
                if employe.base:
                    organisation_data['base'] = employe.base.nom_base
                    if employe.base.organisation:
                        org = employe.base.organisation
                        organisation_data['nom'] = org.nom_organisation
                        organisation_data['nif'] = org.nif or 'N/A'
                        organisation_data['stat'] = org.stat or 'N/A'
                        # Construire l'adresse depuis adresse1 et adresse2
                        adresse_parts = [org.adresse1, org.adresse2, org.localite]
                        adresse_complete = ', '.join([a for a in adresse_parts if a])
                        organisation_data['adresse'] = adresse_complete or 'Madagascar'
                        if org.logo:
                            organisation_data['logo_url'] = org.logo.url

            # Données pour le ticket de caisse
            ticket_data = {
                'numero_ticket': numero_ticket,
                'type': 'Demande BP',
                'date': date.today().strftime('%d/%m/%Y'),
                'heure': timezone.now().strftime('%H:%M'),
                'point_eau_code': point_eau.code_point_eau or '',
                'abonne': point_eau.nomabonne or 'N/A',
                'ouvrage': point_eau.ouvrage.nom_ouvrage if point_eau.ouvrage else 'N/A',
                'village': point_eau.parcelle.village.nom_village if point_eau.parcelle and point_eau.parcelle.village else 'N/A',
                'type_bp': point_eau.type_point_eau.nom_type if point_eau.type_point_eau else 'BP',
                'montant': float(montant),
                'description': description,
                'organisation': organisation_data
            }

            return JsonResponse({
                'success': True,
                'message': 'Paiement de la demande enregistré avec succès',
                'point_eau_id': str(point_eau.id),
                'diamex_id': diamex_temp.id,
                'ticket': ticket_data
            })

    except PointEau.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Point d\'eau introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_paiement_devis(request, point_eau_id):
    """
    API pour traiter le paiement du devis BP
    - Saisie de la distance et promotion (optionnelle)
    - Calcul automatique du montant :
      * Si distance ≤ 12m : montant = tarif_devis_bp
      * Si distance > 12m : montant = tarif_devis_bp + ((distance - 12) × tarif_metre_supplementaire) - promotion_devis
    - Export vers DiameXTemporaire
    - Génération des données pour le ticket de caisse avec info distance
    """
    try:
        point_eau = _get_point_eau_for_user(
            request.user,
            point_eau_id,
            'ouvrage',
            'type_point_eau',
            'parcelle__village__fokontany__commune'
        )
        if not point_eau:
            return JsonResponse({
                'success': False,
                'error': 'Point d\'eau introuvable'
            }, status=404)

        # Vérifier qu'il n'y a pas déjà un numéro DiameX devis
        if point_eau.numerodiamexpaiementdevis:
            return JsonResponse({
                'success': False,
                'error': f'Le paiement du devis a déjà été enregistré (N° DiameX: {point_eau.numerodiamexpaiementdevis})'
            }, status=400)

        # Vérifier que le paiement de la demande a été fait
        if not point_eau.numerodiamexdemande and not point_eau.datepaiementdemande:
            return JsonResponse({
                'success': False,
                'error': 'Le paiement de la demande doit être effectué avant le paiement du devis'
            }, status=400)

        if False and normalize_missing_bp_branchement(point_eau):
            return JsonResponse({
                'success': True,
                'message': 'Branchement déjÃ  constaté via les relevés existants et régularisé automatiquement.',
                'point_eau_id': str(point_eau.id),
                'date_branchement': point_eau.datebranchement.strftime('%d/%m/%Y'),
                'auto_regularise': True,
            })

        data = json.loads(request.body)
        distance = data.get('distance')
        promotion = data.get('promotion', 0)

        if distance is None or float(distance) < 0:
            return JsonResponse({
                'success': False,
                'error': 'La distance est obligatoire et doit être supérieure ou égale à 0'
            }, status=400)

        distance = Decimal(str(distance))
        promotion = Decimal(str(promotion)) if promotion else Decimal('0')

        # Récupérer l'organisation liée à l'ouvrage via ModaliteGestion
        organisation = None
        if point_eau.ouvrage:
            from apps.billing.models import ModaliteGestion
            modalite_active = ModaliteGestion.objects.filter(
                ouvrage=point_eau.ouvrage,
                date_fin__isnull=True
            ).select_related('gestionnaire').first()

            if modalite_active and modalite_active.gestionnaire:
                organisation = modalite_active.gestionnaire

        if not organisation:
            return JsonResponse({
                'success': False,
                'error': 'Impossible de déterminer l\'organisation gestionnaire de cet ouvrage'
            }, status=400)

        # Vérifier les tarifs de l'organisation
        if not organisation.tarif_devis_bp:
            return JsonResponse({
                'success': False,
                'error': f'Le tarif devis BP n\'est pas configuré pour l\'organisation {organisation.nom_organisation}'
            }, status=400)

        if distance > 12 and not organisation.tarif_metre_supplementaire:
            return JsonResponse({
                'success': False,
                'error': f'Le tarif mètre supplémentaire n\'est pas configuré pour l\'organisation {organisation.nom_organisation}'
            }, status=400)

        # Calcul du montant selon la distance
        if distance <= 12:
            montant = organisation.tarif_devis_bp
        else:
            metres_supplementaires = distance - Decimal('12')
            montant = organisation.tarif_devis_bp + (metres_supplementaires * organisation.tarif_metre_supplementaire) - promotion

        with transaction.atomic():
            # Mettre à jour le point d'eau avec distance, promotion et montant
            point_eau.distance = float(distance)
            point_eau.promotion_devis = float(promotion) if promotion > 0 else 0
            point_eau.montantdevispaye = float(montant)
            point_eau.datepaiementdevis = date.today()
            point_eau.save()

            # Créer la ligne dans DiameXTemporaire
            description = f"Paiement devis BP - {point_eau.nomabonne or point_eau.code_point_eau}"
            if point_eau.parcelle and point_eau.parcelle.village:
                description += f" ({point_eau.parcelle.village.nom_village})"
            description += f" - Distance: {float(distance)}m"
            if promotion > 0:
                description += f" - Promotion: {float(promotion)} Ar"

            diamex_temp = DiameXTemporaire.objects.create(
                type_transaction='recette',
                date_rec=date.today(),
                description=description,
                montant_in=float(montant),
                montant_out=0,
                compte_code='748401',  # Compte obligatoire pour les devis BP
                statut='en_attente',
                info='hydria paiement devis',
                detail=point_eau.nomabonne or '',
            )

            # Générer le numéro de ticket (basé sur l'ID DiameX)
            numero_ticket = f"BP-DEV-{diamex_temp.id:06d}"

            # Récupérer l'organisation de l'employé connecté
            organisation_data = {
                'nom': 'HYDRIA',
                'adresse': 'Madagascar',
                'nif': 'N/A',
                'stat': 'N/A',
                'base': 'Centrale',
                'logo_url': ''
            }

            if hasattr(request.user, 'employe') and request.user.employe:
                employe = request.user.employe
                if employe.base:
                    organisation_data['base'] = employe.base.nom_base
                    if employe.base.organisation:
                        org = employe.base.organisation
                        organisation_data['nom'] = org.nom_organisation
                        organisation_data['nif'] = org.nif or 'N/A'
                        organisation_data['stat'] = org.stat or 'N/A'
                        # Construire l'adresse depuis adresse1 et adresse2
                        adresse_parts = [org.adresse1, org.adresse2, org.localite]
                        adresse_complete = ', '.join([a for a in adresse_parts if a])
                        organisation_data['adresse'] = adresse_complete or 'Madagascar'
                        if org.logo:
                            organisation_data['logo_url'] = org.logo.url

            # Données pour le ticket de caisse
            ticket_data = {
                'numero_ticket': numero_ticket,
                'type': 'Devis BP',
                'date': date.today().strftime('%d/%m/%Y'),
                'heure': timezone.now().strftime('%H:%M'),
                'point_eau_code': point_eau.code_point_eau or '',
                'abonne': point_eau.nomabonne or 'N/A',
                'ouvrage': point_eau.ouvrage.nom_ouvrage if point_eau.ouvrage else 'N/A',
                'village': point_eau.parcelle.village.nom_village if point_eau.parcelle and point_eau.parcelle.village else 'N/A',
                'type_bp': point_eau.type_point_eau.nom_type if point_eau.type_point_eau else 'BP',
                'distance': float(distance),
                'promotion': float(promotion) if promotion > 0 else 0,
                'tarif_devis_base': float(organisation.tarif_devis_bp),
                'tarif_metre_supp': float(organisation.tarif_metre_supplementaire) if organisation.tarif_metre_supplementaire else 0,
                'montant': float(montant),
                'description': description,
                'organisation': organisation_data
            }

            return JsonResponse({
                'success': True,
                'message': 'Paiement du devis enregistré avec succès',
                'point_eau_id': str(point_eau.id),
                'diamex_id': diamex_temp.id,
                'ticket': ticket_data
            })

    except PointEau.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Point d\'eau introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_enregistrer_branchement(request, point_eau_id):
    """
    API pour enregistrer le branchement
    - Date de branchement
    - Index initial dans la table Releve
    """
    try:
        point_eau = _get_point_eau_for_user(
            request.user,
            point_eau_id,
            'ouvrage',
            'type_point_eau'
        )
        if not point_eau:
            return JsonResponse({
                'success': False,
                'error': 'Point d\'eau introuvable'
            }, status=404)

        # Vérifier qu'il n'y a pas déjà une date de branchement
        if point_eau.datebranchement:
            return JsonResponse({
                'success': False,
                'error': f'Le branchement a déjà été enregistré le {point_eau.datebranchement.strftime("%d/%m/%Y")}'
            }, status=400)

        # Vérifier que les paiements ont été effectués
        if not point_eau.datepaiementdemande:
            return JsonResponse({
                'success': False,
                'error': 'Le paiement de la demande doit être effectué avant l\'enregistrement du branchement'
            }, status=400)

        if not point_eau.datepaiementdevis:
            return JsonResponse({
                'success': False,
                'error': 'Le paiement du devis doit être effectué avant l\'enregistrement du branchement'
            }, status=400)

        if normalize_missing_bp_branchement(point_eau):
            return JsonResponse({
                'success': True,
                'message': 'Branchement déjÃ  constaté via les relevés existants et régularisé automatiquement.',
                'point_eau_id': str(point_eau.id),
                'date_branchement': point_eau.datebranchement.strftime('%d/%m/%Y'),
                'auto_regularise': True,
            })

        data = json.loads(request.body)
        date_branchement_str = data.get('date_branchement')
        index_initial = data.get('index_initial')

        if not date_branchement_str:
            return JsonResponse({
                'success': False,
                'error': 'La date de branchement est obligatoire'
            }, status=400)

        if index_initial is None or float(index_initial) < 0:
            return JsonResponse({
                'success': False,
                'error': 'L\'index initial doit être supérieur ou égal à 0'
            }, status=400)

        # Parser la date
        try:
            date_branchement = datetime.strptime(date_branchement_str, '%Y-%m-%d').date()
        except ValueError:
            try:
                date_branchement = datetime.strptime(date_branchement_str, '%d/%m/%Y').date()
            except ValueError:
                return JsonResponse({
                    'success': False,
                    'error': 'Format de date invalide (utilisez YYYY-MM-DD ou DD/MM/YYYY)'
                }, status=400)

        with transaction.atomic():
            # Mettre à jour le point d'eau
            point_eau.datebranchement = date_branchement
            point_eau.save()

            # Créer le relevé initial avec l'index de départ
            releve_initial = Releve.objects.create(
                point_eau=point_eau,
                abonne=point_eau.nomabonne or 'N/A',
                datereleve=date_branchement,
                ancienindex=0,  # Pas d'ancien index pour le premier relevé
                nouvelindex=Decimal(str(index_initial)),
                consommation=0,  # Pas de consommation pour le relevé initial
                statut='paye',  # Marqué comme payé (relevé initial, pas de facture)
                montant=None,  # Pas de montant pour le relevé initial
            )

            return JsonResponse({
                'success': True,
                'message': 'Branchement enregistré avec succès',
                'point_eau_id': str(point_eau.id),
                'date_branchement': date_branchement.strftime('%d/%m/%Y'),
                'index_initial': float(index_initial),
                'releve_id': str(releve_initial.id)
            })

    except PointEau.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Point d\'eau introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def api_calculer_montant_demande(request, point_eau_id):
    """
    API pour calculer le montant de la demande BP avant paiement
    Retourne le montant calculé automatiquement depuis l'organisation
    """
    try:
        point_eau = _get_point_eau_for_user(request.user, point_eau_id, 'ouvrage')
        if not point_eau:
            return JsonResponse({
                'success': False,
                'error': 'Point d\'eau introuvable'
            }, status=404)

        # Récupérer l'organisation liée à l'ouvrage via ModaliteGestion
        organisation = None
        if point_eau.ouvrage:
            from apps.billing.models import ModaliteGestion
            modalite_active = ModaliteGestion.objects.filter(
                ouvrage=point_eau.ouvrage,
                date_fin__isnull=True
            ).select_related('gestionnaire').first()

            if modalite_active and modalite_active.gestionnaire:
                organisation = modalite_active.gestionnaire

        if not organisation:
            return JsonResponse({
                'success': False,
                'error': 'Impossible de déterminer l\'organisation gestionnaire de cet ouvrage'
            }, status=400)

        # Récupérer le tarif_demande de l'organisation
        if not organisation.tarif_demande:
            return JsonResponse({
                'success': False,
                'error': f'Le tarif de demande n\'est pas configuré pour l\'organisation {organisation.nom_organisation}'
            }, status=400)

        return JsonResponse({
            'success': True,
            'montant': float(organisation.tarif_demande),
            'organisation': organisation.nom_organisation
        })

    except PointEau.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Point d\'eau introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_calculer_montant_devis(request, point_eau_id):
    """
    API pour calculer le montant du devis BP en temps réel
    Accepte distance et promotion, retourne le montant calculé avec détails
    """
    try:
        point_eau = _get_point_eau_for_user(request.user, point_eau_id, 'ouvrage')
        if not point_eau:
            return JsonResponse({
                'success': False,
                'error': 'Point d\'eau introuvable'
            }, status=404)

        # Récupérer l'organisation liée à l'ouvrage via ModaliteGestion
        organisation = None
        if point_eau.ouvrage:
            from apps.billing.models import ModaliteGestion
            modalite_active = ModaliteGestion.objects.filter(
                ouvrage=point_eau.ouvrage,
                date_fin__isnull=True
            ).select_related('gestionnaire').first()

            if modalite_active and modalite_active.gestionnaire:
                organisation = modalite_active.gestionnaire

        if not organisation:
            return JsonResponse({
                'success': False,
                'error': 'Impossible de déterminer l\'organisation gestionnaire de cet ouvrage'
            }, status=400)

        # Vérifier les tarifs de l'organisation
        if not organisation.tarif_devis_bp:
            return JsonResponse({
                'success': False,
                'error': f'Le tarif devis BP n\'est pas configuré pour l\'organisation {organisation.nom_organisation}'
            }, status=400)

        # Récupérer distance et promotion depuis la requête
        data = json.loads(request.body)
        distance = data.get('distance', 0)
        promotion = data.get('promotion', 0)

        if distance is None or float(distance) < 0:
            return JsonResponse({
                'success': False,
                'error': 'La distance doit être supérieure ou égale à 0'
            }, status=400)

        distance = Decimal(str(distance))
        promotion = Decimal(str(promotion)) if promotion else Decimal('0')

        # Calcul du montant selon la distance
        tarif_base = organisation.tarif_devis_bp
        supplement_distance = Decimal('0')

        if distance <= 12:
            montant = tarif_base
        else:
            if not organisation.tarif_metre_supplementaire:
                return JsonResponse({
                    'success': False,
                    'error': f'Le tarif mètre supplémentaire n\'est pas configuré pour l\'organisation {organisation.nom_organisation}'
                }, status=400)

            metres_supplementaires = distance - Decimal('12')
            supplement_distance = metres_supplementaires * organisation.tarif_metre_supplementaire
            montant = tarif_base + supplement_distance - promotion

        return JsonResponse({
            'success': True,
            'montant': float(montant),
            'tarif_base': float(tarif_base),
            'supplement_distance': float(supplement_distance),
            'promotion': float(promotion),
            'tarif_metre_supp': float(organisation.tarif_metre_supplementaire) if organisation.tarif_metre_supplementaire else 0,
            'organisation': organisation.nom_organisation
        })

    except PointEau.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Point d\'eau introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

