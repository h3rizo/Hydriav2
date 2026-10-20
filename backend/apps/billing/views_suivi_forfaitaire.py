"""
Vues pour le suivi des paiements forfaitaires par ouvrage

Cette page affiche la liste des ouvrages avec modalité forfaitaire,
regroupés par District/Commune, avec pour chaque ouvrage :
- Liste des points d'eau
- Historique des paiements de chaque point d'eau
- Calcul des soldes à payer (trous dans les factures)
"""

import json
from datetime import datetime, timedelta, date
from decimal import Decimal, ROUND_HALF_UP
from dateutil.relativedelta import relativedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count, Sum, Prefetch
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

import pytz

from apps.billing.models import PointEau, PaiementForfaitaire, CoupureEau, ModaliteGestion
from apps.organization.models import Organisation, Ouvrage
from apps.organization.scoping import get_user_accessible_gestionnaire_ids
from apps.geography.models import Commune, District, Region


def _normalize_date(value):
    if isinstance(value, datetime):
        return value.date()
    return value


def _validate_coupure_alternance(point_eau, type_evenement, date_evenement, exclude_id=None):
    """
    Valide l'alternance stricte des événements pour un point d'eau.
    Règle métier: la séquence doit alterner coupure/remise/coupure/...,
    sans doublon consécutif, dans l'ordre chronologique.
    """
    qs = CoupureEau.objects.filter(point_eau=point_eau)
    if exclude_id:
        qs = qs.exclude(id=exclude_id)

    prev_evt = qs.filter(
        date_evenement__lte=date_evenement
    ).order_by('-date_evenement', '-created_at').first()
    next_evt = qs.filter(
        date_evenement__gt=date_evenement
    ).order_by('date_evenement', 'created_at').first()

    # Ne pas commencer une timeline par une remise.
    if prev_evt is None and type_evenement == 'remise':
        return "Impossible d'enregistrer une remise en eau sans coupure préalable."

    if prev_evt and prev_evt.type_evenement == type_evenement:
        return (
            f"Séquence invalide: l'événement précédent du "
            f"{prev_evt.date_evenement.strftime('%d/%m/%Y')} est déjà '{prev_evt.type_evenement}'."
        )

    if next_evt and next_evt.type_evenement == type_evenement:
        return (
            f"Séquence invalide: l'événement suivant du "
            f"{next_evt.date_evenement.strftime('%d/%m/%Y')} est déjà '{next_evt.type_evenement}'."
        )

    return None


def _calculer_duree_mois(montant, tarif_forfaitaire, quantite=None):
    if montant is None or tarif_forfaitaire in (None, 0, Decimal('0')):
        if quantite:
            return int(quantite) * 3
        return 3

    try:
        montant_dec = Decimal(str(montant))
        tarif_dec = Decimal(str(tarif_forfaitaire))
        if tarif_dec == 0:
            return int(quantite) * 3 if quantite else 3
        mois = (montant_dec * Decimal('3')) / tarif_dec
        return max(int(mois.to_integral_value(rounding=ROUND_HALF_UP)), 1)
    except Exception:
        return int(quantite) * 3 if quantite else 3


def _calculer_date_fin_validite(date_facture, duree_mois):
    if not date_facture or not duree_mois:
        return None
    return date_facture + relativedelta(months=duree_mois) - timedelta(days=1)


def _get_user_organisation_id(user):
    employe = getattr(user, 'employe', None)
    base = getattr(employe, 'base', None)
    return getattr(base, 'organisation_id', None)


def _get_allowed_ouvrage_ids(user):
    modalites_qs = ModaliteGestion.objects.filter(
        date_fin__isnull=True,
        modalitepaiement__in=['forfaitaire', 'mixte']
    )
    if not getattr(user, 'is_superuser', False):
        gestionnaire_ids = get_user_accessible_gestionnaire_ids(user)
        if gestionnaire_ids is None:
            pass
        elif not gestionnaire_ids:
            return []
        else:
            modalites_qs = modalites_qs.filter(gestionnaire_id__in=gestionnaire_ids)

    return list(
        modalites_qs.exclude(ouvrage_id__isnull=True)
        .values_list('ouvrage_id', flat=True)
        .distinct()
    )


@login_required
def suivi_paiements_forfaitaires(request):
    """
    Page principale du suivi des paiements forfaitaires

    Affiche les ouvrages regroupés par District/Commune avec :
    - Liste des points d'eau par ouvrage
    - Historique des paiements
    - Calcul des soldes (factures manquantes, factures impayées)
    """

    # Récupérer les données pour les filtres
    allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
    points_scope = PointEau.objects.filter(ouvrage_id__in=allowed_ouvrage_ids)
    region_ids = points_scope.values_list(
        'parcelle__village__fokontany__commune__district__region_id',
        flat=True
    ).distinct()
    district_ids = points_scope.values_list(
        'parcelle__village__fokontany__commune__district_id',
        flat=True
    ).distinct()
    commune_ids = points_scope.values_list(
        'parcelle__village__fokontany__commune_id',
        flat=True
    ).distinct()

    regions = Region.objects.filter(id__in=region_ids).order_by('nom_region')
    districts = District.objects.filter(id__in=district_ids).order_by('nom_district')
    communes = Commune.objects.filter(id__in=commune_ids).order_by('nom_commune')

    context = {
        'title': 'Suivi des Paiements Forfaitaires',
        'regions': regions,
        'districts': districts,
        'communes': communes,
    }

    return render(request, 'billing/suivi_paiements_forfaitaires.html', context)


@login_required
@require_http_methods(["GET"])
def api_ouvrages_forfaitaires(request):
    """
    API pour récupérer les ouvrages avec modalité forfaitaire
    et leurs points d'eau avec historique des paiements

    Retourne aussi le calcul des soldes:
    - Nombre de tranches manquantes (trous de facturation)
    - Nombre de factures impayées
    """

    try:
        # Récupérer les filtres
        region_id = request.GET.get('region_id', 'all')
        district_id = request.GET.get('district_id', 'all')
        commune_id = request.GET.get('commune_id', 'all')
        recherche = request.GET.get('recherche', '').strip()

        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)

        # CORRECTION: Récupérer TOUS les ouvrages qui ont des points d'eau avec tarif forfaitaire
        # Ne pas se limiter aux modalités actives car les paiements peuvent exister sans modalité
        ouvrages_qs = Ouvrage.objects.filter(
            pointeau__tarifforfaitaire__gt=0,
            type_ouvrage__existe=True,
            id__in=allowed_ouvrage_ids
        ).select_related(
            'type_ouvrage'
        ).prefetch_related(
            Prefetch(
                'pointeau_set',
                queryset=PointEau.objects.filter(tarifforfaitaire__gt=0).select_related(
                    'type_point_eau',
                    'parcelle__village__fokontany__commune__district__region'
                ).prefetch_related(
                    'paiements_forfaitaires',
                    'coupures_eau'
                )
            )
        ).distinct()

        # Cloisonnement deja applique via id__in=allowed_ouvrage_ids

        # Filtres géographiques
        if commune_id and commune_id != 'all':
            ouvrages_qs = ouvrages_qs.filter(
                pointeau__parcelle__village__fokontany__commune_id=commune_id
            ).distinct()
        elif district_id and district_id != 'all':
            ouvrages_qs = ouvrages_qs.filter(
                pointeau__parcelle__village__fokontany__commune__district_id=district_id
            ).distinct()
        elif region_id and region_id != 'all':
            ouvrages_qs = ouvrages_qs.filter(
                pointeau__parcelle__village__fokontany__commune__district__region_id=region_id
            ).distinct()

        # Recherche par nom d'ouvrage OU nom de point d'eau
        if recherche:
            ouvrages_qs = ouvrages_qs.filter(
                Q(nom_ouvrage__icontains=recherche) |
                Q(pointeau__code_point_eau__icontains=recherche) |
                Q(pointeau__nomabonne__icontains=recherche)
            ).distinct()

        # Construire les résultats
        resultats = []
        tz_madagascar = pytz.timezone('Indian/Antananarivo')

        for ouvrage in ouvrages_qs:
            # Informations géographiques (depuis le premier point d'eau)
            district_nom = None
            commune_nom = None
            points_eau_list = list(ouvrage.pointeau_set.filter(tarifforfaitaire__gt=0))

            if points_eau_list:
                pe = points_eau_list[0]
                if pe.parcelle and pe.parcelle.village and pe.parcelle.village.fokontany:
                    if pe.parcelle.village.fokontany.commune:
                        commune_nom = pe.parcelle.village.fokontany.commune.nom_commune
                        if pe.parcelle.village.fokontany.commune.district:
                            district_nom = pe.parcelle.village.fokontany.commune.district.nom_district

            # Points d'eau avec leurs paiements et soldes
            points_eau_data = []
            total_factures_manquantes = 0
            total_factures_impayees = 0
            total_recommandations_coupure = 0

            for pe in points_eau_list:
                # Paiements du point d'eau (triés par date)
                paiements = list(pe.paiements_forfaitaires.all().order_by('date_facture'))
                paiements_data = []

                for paiement in paiements:
                    date_facture_aware = paiement.date_facture
                    if isinstance(date_facture_aware, datetime):
                        if date_facture_aware.tzinfo:
                            date_facture_mg = date_facture_aware.astimezone(tz_madagascar).date()
                        else:
                            date_facture_mg = tz_madagascar.localize(date_facture_aware).date()
                    else:
                        date_facture_mg = date_facture_aware

                    duree_mois_calc = _calculer_duree_mois(
                        paiement.montant,
                        pe.tarifforfaitaire,
                        paiement.quantite
                    )
                    date_fin_calc = _calculer_date_fin_validite(date_facture_mg, duree_mois_calc)

                    paiements_data.append({
                        'id': str(paiement.id),
                        'date_facture': date_facture_mg.strftime('%Y-%m-%d'),
                        'quantite': paiement.quantite,
                        'prix_unitaire': float(paiement.prix_unitaire),
                        'montant': float(paiement.montant),
                        'paye': paiement.paye,
                        'date_paiement': paiement.date_paiement.strftime('%Y-%m-%d') if paiement.date_paiement else None,
                        'numero_diamex': paiement.numeroDiameX or '',
                        'duree_mois': duree_mois_calc,
                        'date_fin_validite': date_fin_calc.strftime('%Y-%m-%d') if date_fin_calc else None,
                    })

                # Coupures d'eau du point d'eau
                coupures = list(pe.coupures_eau.all().order_by('date_evenement'))
                coupures_data = []

                for coupure in coupures:
                    coupures_data.append({
                        'id': str(coupure.id),
                        'type_evenement': coupure.type_evenement,
                        'date_evenement': coupure.date_evenement.strftime('%Y-%m-%d'),
                        'raison': coupure.raison or '',
                        'notes': coupure.notes or '',
                    })

                # Calcul des soldes
                soldes = calculer_soldes_point_eau(pe, paiements, coupures)

                total_factures_manquantes += soldes['factures_manquantes']
                total_factures_impayees += soldes['factures_impayees']
                if soldes.get('recommander_coupure'):
                    total_recommandations_coupure += 1

                points_eau_data.append({
                    'id': str(pe.id),
                    'nom': pe.nomabonne or pe.code_point_eau or 'Point d\'eau sans nom',
                    'code': pe.code_point_eau or '',
                    'tarif_forfaitaire': float(pe.tarifforfaitaire),
                    'paiements': paiements_data,
                    'coupures': coupures_data,
                    'soldes': soldes,
                })

            resultats.append({
                'id': str(ouvrage.id),
                'nom': ouvrage.nom_ouvrage,
                'type': ouvrage.type_ouvrage.nom_type_ouvrage if ouvrage.type_ouvrage else 'N/A',
                'district': district_nom or 'N/A',
                'commune': commune_nom or 'N/A',
                'nb_points_eau': len(points_eau_data),
                'points_eau': points_eau_data,
                'total_factures_manquantes': total_factures_manquantes,
                'total_factures_impayees': total_factures_impayees,
                'total_recommandations_coupure': total_recommandations_coupure,
            })

        # Calculer les statistiques globales
        stats = {
            'total_ouvrages': len(resultats),
            'total_points_eau': sum(len(ouvrage['points_eau']) for ouvrage in resultats),
            'total_factures_manquantes': sum(ouvrage['total_factures_manquantes'] for ouvrage in resultats),
            'total_factures_impayees': sum(ouvrage['total_factures_impayees'] for ouvrage in resultats),
            'total_recommandations_coupure': sum(ouvrage['total_recommandations_coupure'] for ouvrage in resultats),
            'total_coupes_actifs': sum(
                1 for ouvrage in resultats
                for pe in ouvrage['points_eau']
                if pe.get('coupure_active', False)
            )
        }

        return JsonResponse({
            'success': True,
            'ouvrages': resultats,
            'total': len(resultats),
            'stats': stats
        })

    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


def calculer_soldes_point_eau(point_eau, paiements, coupures):
    """
    Calcule les soldes d'un point d'eau :
    1. Factures manquantes (trous dans la facturation)
    2. Factures impayées

    Règle: 1 an de fonctionnement = 4 tranches facturées (1 tranche = 3 mois)
    Les périodes de coupure ne comptent pas.
    """

    # Si pas de paiements, impossible de calculer
    if not paiements:
        return {
            'factures_manquantes': 0,
            'factures_impayees': 0,
            'premier_paiement': None,
            'dernier_paiement': None,
            'mois_fonctionnement': 0,
            'tranches_attendues': 0,
            'tranches_facturees': len(paiements),
            'periodes_coupure': []
        }

    # Dates de début et fin (convertir en date si datetime)
    dates_facture = []
    for p in paiements:
        dates_facture.append(_normalize_date(p.date_facture))

    premier_paiement = min(dates_facture)
    dernier_paiement = max(dates_facture)

    # Calculer les périodes de coupure (coupure -> remise)
    periodes_coupure = []
    coupures_list = sorted(coupures, key=lambda c: c.date_evenement)

    date_coupure_courante = None
    for coupure in coupures_list:
        if coupure.type_evenement == 'coupure':
            date_coupure_courante = coupure.date_evenement
        elif coupure.type_evenement == 'remise' and date_coupure_courante:
            periodes_coupure.append({
                'debut': date_coupure_courante,
                'fin': coupure.date_evenement,
            })
            date_coupure_courante = None

    # Si une coupure est en cours (pas de remise), elle va jusqu'à aujourd'hui
    if date_coupure_courante:
        periodes_coupure.append({
            'debut': date_coupure_courante,
            'fin': date.today(),
        })

    # Calculer les mois de fonctionnement (sans les périodes de coupure)
    total_jours = (dernier_paiement - premier_paiement).days
    jours_coupure = 0

    for periode in periodes_coupure:
        # Intersection avec la période de fonctionnement
        debut = max(periode['debut'], premier_paiement)
        fin = min(periode['fin'], dernier_paiement)
        if debut < fin:
            jours_coupure += (fin - debut).days

    jours_fonctionnement = total_jours - jours_coupure
    mois_fonctionnement = max(0, jours_fonctionnement / 30)  # Approximation

    # Nombre de tranches attendues (1 tranche = 3 mois)
    tranches_attendues = int(mois_fonctionnement / 3)

    # Nombre de tranches facturées
    tranches_facturees = len(paiements)

    # Factures manquantes
    factures_manquantes = max(0, tranches_attendues - tranches_facturees)

    # Factures impayées
    factures_impayees = sum(1 for p in paiements if not p.paye)

    # Recommandation de coupure :
    # - Si une facture est impayée ET sa date de validité est dépassée
    # - Vérifier qu'il n'y a pas déjà une coupure active
    recommander_coupure = False
    facture_expiring_details = []

    coupure_active = date_coupure_courante is not None  # Variable définie plus haut

    if not coupure_active:
        today = date.today()
        for p in paiements:
            if not p.paye:
                date_facture = _normalize_date(p.date_facture)
                if not date_facture:
                    continue

                duree_mois_calc = _calculer_duree_mois(
                    p.montant,
                    point_eau.tarifforfaitaire,
                    p.quantite
                )
                date_fin = _calculer_date_fin_validite(date_facture, duree_mois_calc)
                if date_fin and date_fin < today:
                    recommander_coupure = True
                    facture_expiring_details.append({
                        'date_facture': date_facture.strftime('%d/%m/%Y'),
                        'date_fin_validite': date_fin.strftime('%d/%m/%Y'),
                        'montant': float(p.montant),
                        'jours_depassement': (today - date_fin).days
                    })

    return {
        'factures_manquantes': factures_manquantes,
        'factures_impayees': factures_impayees,
        'premier_paiement': premier_paiement.strftime('%Y-%m-%d'),
        'dernier_paiement': dernier_paiement.strftime('%Y-%m-%d'),
        'mois_fonctionnement': round(mois_fonctionnement, 1),
        'tranches_attendues': tranches_attendues,
        'tranches_facturees': tranches_facturees,
        'periodes_coupure': [
            {
                'debut': p['debut'].strftime('%Y-%m-%d'),
                'fin': p['fin'].strftime('%Y-%m-%d'),
            }
            for p in periodes_coupure
        ],
        'recommander_coupure': recommander_coupure,
        'factures_expirees': facture_expiring_details,
        'coupure_active': coupure_active
    }


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_create_coupure(request):
    """
    API pour créer une coupure d'eau

    POST data:
    - point_eau_id: UUID du point d'eau
    - type_evenement: 'coupure' ou 'remise'
    - date_evenement: Date (YYYY-MM-DD)
    - raison: Raison de la coupure (optionnel)
    - notes: Notes (optionnel)
    """

    try:
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        data = json.loads(request.body)

        # Validation des champs obligatoires
        point_eau_id = data.get('point_eau_id')
        type_evenement = data.get('type_evenement')
        date_evenement = data.get('date_evenement')

        if not all([point_eau_id, type_evenement, date_evenement]):
            return JsonResponse({
                'success': False,
                'error': 'Champs obligatoires manquants'
            }, status=400)

        # Vérifier que le point d'eau existe
        try:
            point_eau = PointEau.objects.get(id=point_eau_id, ouvrage_id__in=allowed_ouvrage_ids)
        except PointEau.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Point d\'eau introuvable'
            }, status=404)

        # Vérifier que le type est valide
        if type_evenement not in ['coupure', 'remise']:
            return JsonResponse({
                'success': False,
                'error': 'Type d\'événement invalide'
            }, status=400)

        dernier_evenement = CoupureEau.objects.filter(point_eau=point_eau).order_by('-date_evenement', '-created_at').first()
        point_est_coupe = bool(dernier_evenement and dernier_evenement.type_evenement == 'coupure')

        if type_evenement == 'coupure' and point_est_coupe:
            return JsonResponse({
                'success': False,
                'error': "Ce point d'eau est deja coupe. Effectuez d'abord une remise en eau avant une nouvelle coupure."
            }, status=400)

        if type_evenement == 'remise' and not point_est_coupe:
            return JsonResponse({
                'success': False,
                'error': "Ce point d'eau n'est pas actuellement coupe. Impossible d'enregistrer une remise en eau."
            }, status=400)

        # Parser la date
        try:
            date_obj = datetime.strptime(date_evenement, '%Y-%m-%d').date()
        except ValueError:
            return JsonResponse({
                'success': False,
                'error': 'Format de date invalide (attendu: YYYY-MM-DD)'
            }, status=400)

        # Validation de l'alternance chronologique stricte
        validation_error = _validate_coupure_alternance(point_eau, type_evenement, date_obj)
        if validation_error:
            return JsonResponse({
                'success': False,
                'error': validation_error
            }, status=400)

        # Créer la coupure
        coupure = CoupureEau.objects.create(
            point_eau=point_eau,
            type_evenement=type_evenement,
            date_evenement=date_obj,
            raison=data.get('raison'),
            notes=data.get('notes')
        )

        paiements_supprimes = 0
        if type_evenement == 'coupure':
            paiements_supprimes = PaiementForfaitaire.objects.filter(
                point_eau=point_eau,
                date_facture__gte=date_obj
            ).delete()[0]

        return JsonResponse({
            'success': True,
            'message': f'Coupure d\'eau {type_evenement} enregistrée avec succès',
            'paiements_supprimes': paiements_supprimes,
            'coupure': {
                'id': str(coupure.id),
                'type_evenement': coupure.type_evenement,
                'date_evenement': coupure.date_evenement.strftime('%Y-%m-%d'),
                'raison': coupure.raison or '',
                'notes': coupure.notes or '',
            }
        })

    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_update_coupure(request, coupure_id):
    """
    API pour modifier une coupure d'eau existante
    """
    try:
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        coupure = CoupureEau.objects.get(id=coupure_id, point_eau__ouvrage_id__in=allowed_ouvrage_ids)
        data = json.loads(request.body)

        description_changes = []
        nouveau_type = data.get('type_evenement', coupure.type_evenement)
        if nouveau_type not in ['coupure', 'remise']:
            return JsonResponse({
                'success': False,
                'error': 'Type d\'événement invalide'
            }, status=400)

        nouvelle_date = coupure.date_evenement
        if 'date_evenement' in data:
            try:
                nouvelle_date = datetime.strptime(data['date_evenement'], '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({
                    'success': False,
                    'error': 'Format de date invalide (attendu: YYYY-MM-DD)'
                }, status=400)

        validation_error = _validate_coupure_alternance(
            point_eau=coupure.point_eau,
            type_evenement=nouveau_type,
            date_evenement=nouvelle_date,
            exclude_id=coupure.id
        )
        if validation_error:
            return JsonResponse({
                'success': False,
                'error': validation_error
            }, status=400)

        if nouveau_type != coupure.type_evenement:
            description_changes.append(f"type: {coupure.type_evenement} -> {nouveau_type}")
            coupure.type_evenement = nouveau_type

        if nouvelle_date != coupure.date_evenement:
            description_changes.append(f"date: {coupure.date_evenement} -> {nouvelle_date}")
            coupure.date_evenement = nouvelle_date

        if 'raison' in data:
            old_val = coupure.raison
            coupure.raison = data['raison']
            if old_val != coupure.raison:
                description_changes.append(f"raison: {old_val} -> {coupure.raison}")

        if 'notes' in data:
            old_val = coupure.notes
            coupure.notes = data['notes']
            if old_val != coupure.notes:
                description_changes.append(f"notes: {old_val} -> {coupure.notes}")

        coupure.save()

        paiements_supprimes = 0
        if coupure.type_evenement == 'coupure':
            paiements_supprimes = PaiementForfaitaire.objects.filter(
                point_eau=coupure.point_eau,
                date_facture__gte=coupure.date_evenement
            ).delete()[0]

        return JsonResponse({
            'success': True,
            'message': 'Coupure mise à jour avec succès',
            'paiements_supprimes': paiements_supprimes,
            'changes': description_changes
        })

    except CoupureEau.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Coupure introuvable'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST", "DELETE"])
@login_required
def api_delete_coupure(request, coupure_id):
    """
    API pour supprimer une coupure d'eau
    """
    try:
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        coupure = CoupureEau.objects.get(id=coupure_id, point_eau__ouvrage_id__in=allowed_ouvrage_ids)
        coupure.delete()
        return JsonResponse({
            'success': True,
            'message': 'Coupure supprimée avec succès'
        })
    except CoupureEau.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Coupure introuvable'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)




@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_create_paiement(request):
    """
    API pour créer un nouveau paiement forfaitaire
    """
    try:
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        data = json.loads(request.body)
        point_eau_id = data.get('point_eau_id')
        date_facture = data.get('date_facture')
        quantite = data.get('quantite', 1)
        prix_unitaire = data.get('prix_unitaire')
        duree_mois = data.get('duree_mois')

        if not all([point_eau_id, date_facture, prix_unitaire]):
            return JsonResponse({'success': False, 'error': 'Champs obligatoires manquants'}, status=400)

        point_eau = PointEau.objects.get(id=point_eau_id, ouvrage_id__in=allowed_ouvrage_ids)
        date_obj = datetime.strptime(date_facture, '%Y-%m-%d').date()
        montant = Decimal(str(quantite)) * Decimal(str(prix_unitaire))

        duree_mois_calc = _calculer_duree_mois(
            montant,
            point_eau.tarifforfaitaire,
            quantite
        )
        if isinstance(duree_mois, int) and duree_mois > 0:
            duree_mois_calc = duree_mois

        date_fin_validite = _calculer_date_fin_validite(date_obj, duree_mois_calc)

        paiement = PaiementForfaitaire.objects.create(
            point_eau=point_eau,
            date_facture=date_obj,
            quantite=quantite,
            prix_unitaire=Decimal(str(prix_unitaire)),
            montant=montant,
            date_fin_validite=date_fin_validite,
            paye=False
        )

        return JsonResponse({
            'success': True,
            'message': 'Paiement créé avec succès',
            'paiement': {'id': str(paiement.id), 'montant': float(paiement.montant)}
        })

    except Exception as e:
        import traceback
        return JsonResponse({'success': False, 'error': str(e), 'traceback': traceback.format_exc()}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_update_paiement(request, paiement_id):
    """
    API pour modifier/réassigner un paiement forfaitaire à un autre point d'eau

    Permet de modifier:
    - Le point d'eau (réassignation)
    - La quantité
    - Le prix unitaire
    - Le numéro DiameX
    - La base DiameX
    """
    try:
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        paiement = PaiementForfaitaire.objects.select_related('point_eau', 'point_eau__ouvrage').get(
            id=paiement_id,
            point_eau__ouvrage_id__in=allowed_ouvrage_ids
        )
        data = json.loads(request.body)

        # Récupérer les données
        nouveau_point_eau_id = data.get('point_eau_id')
        quantite = data.get('quantite')
        prix_unitaire = data.get('prix_unitaire')
        numero_diamex = data.get('numeroDiameX', '').strip()
        base_diamex = data.get('baseDiameX', '').strip()

        description_changes = []

        # Réassignation à un autre point d'eau
        if nouveau_point_eau_id and str(paiement.point_eau.id) != nouveau_point_eau_id:
            nouveau_point_eau = PointEau.objects.select_related('ouvrage').get(
                id=nouveau_point_eau_id,
                ouvrage_id__in=allowed_ouvrage_ids
            )

            # Vérifier que le nouveau point d'eau appartient au même ouvrage (sécurité)
            if paiement.point_eau.ouvrage.id != nouveau_point_eau.ouvrage.id:
                return JsonResponse({
                    'success': False,
                    'error': 'Le point d\'eau doit appartenir au même ouvrage'
                }, status=400)

            ancien_pe = paiement.point_eau.nomabonne
            paiement.point_eau = nouveau_point_eau
            description_changes.append(f"Point d'eau: {ancien_pe} → {nouveau_point_eau.nomabonne}")

        # Modification de la quantité
        if quantite is not None and int(quantite) != paiement.quantite:
            ancien_qte = paiement.quantite
            paiement.quantite = int(quantite)
            paiement.montant = Decimal(str(paiement.quantite)) * paiement.prix_unitaire
            description_changes.append(f"Quantité: {ancien_qte} → {quantite}")

        # Modification du prix unitaire
        if prix_unitaire is not None and Decimal(str(prix_unitaire)) != paiement.prix_unitaire:
            ancien_pu = paiement.prix_unitaire
            paiement.prix_unitaire = Decimal(str(prix_unitaire))
            paiement.montant = Decimal(str(paiement.quantite)) * paiement.prix_unitaire
            description_changes.append(f"Prix unitaire: {ancien_pu} → {prix_unitaire} Ar")

        # Modification numéro DiameX
        if numero_diamex and numero_diamex != (paiement.numeroDiameX or ''):
            paiement.numeroDiameX = numero_diamex
            description_changes.append(f"N° DiameX: {numero_diamex}")

        # Modification base DiameX
        if base_diamex and base_diamex != (paiement.baseDiameX or ''):
            paiement.baseDiameX = base_diamex
            description_changes.append(f"Base DiameX: {base_diamex}")

        if paiement.date_facture:
            duree_mois_calc = _calculer_duree_mois(
                paiement.montant,
                paiement.point_eau.tarifforfaitaire,
                paiement.quantite
            )
            paiement.date_fin_validite = _calculer_date_fin_validite(
                _normalize_date(paiement.date_facture),
                duree_mois_calc
            )

        paiement.save()

        return JsonResponse({
            'success': True,
            'message': 'Paiement mis à jour avec succès',
            'changes': description_changes
        })

    except PaiementForfaitaire.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Paiement introuvable'}, status=404)
    except PointEau.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Point d\'eau introuvable'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST", "DELETE"])
@login_required
def api_delete_paiement(request, paiement_id):
    """
    API pour supprimer un paiement forfaitaire

    RESTRICTION: Disponible uniquement pour les utilisateurs avec le poste 'Directeur'
    """
    try:
        # Vérifier le rôle de l'utilisateur
        user_poste = None
        if hasattr(request.user, 'employe') and request.user.employe and request.user.employe.poste:
            user_poste = request.user.employe.poste.nom_poste

        # Restriction: uniquement les Directeurs peuvent supprimer
        if user_poste != 'Directeur':
            return JsonResponse({
                'success': False,
                'error': 'Accès refusé: seuls les Directeurs peuvent supprimer des paiements'
            }, status=403)

        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        paiement = PaiementForfaitaire.objects.get(id=paiement_id, point_eau__ouvrage_id__in=allowed_ouvrage_ids)

        # Sauvegarder les infos pour le message de confirmation
        point_eau_nom = paiement.point_eau.nomabonne if paiement.point_eau else 'Inconnu'
        montant = paiement.montant

        paiement.delete()

        return JsonResponse({
            'success': True,
            'message': f'Paiement supprimé: {point_eau_nom} - {montant} Ar'
        })

    except PaiementForfaitaire.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Paiement introuvable'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_valider_paiement(request):
    """API pour valider un paiement (marquer comme payé)"""
    try:
        data = json.loads(request.body)
        paiement_id = data.get('paiement_id')

        if not paiement_id:
            return JsonResponse({
                'success': False,
                'error': 'paiement_id requis'
            }, status=400)

        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        paiement = PaiementForfaitaire.objects.get(id=paiement_id, point_eau__ouvrage_id__in=allowed_ouvrage_ids)

        # Marquer comme payé avec la date du jour
        paiement.paye = True
        paiement.date_paiement = timezone.now().date()
        paiement.save()

        return JsonResponse({
            'success': True,
            'message': 'Paiement validé avec succès',
            'paiement': {
                'id': str(paiement.id),
                'paye': paiement.paye,
                'date_paiement': str(paiement.date_paiement) if paiement.date_paiement else None
            }
        })

    except PaiementForfaitaire.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Paiement non trouvé'
        }, status=404)

    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


@login_required
@require_http_methods(["GET"])
def export_excel_paiements(request):
    """Export Excel de tous les paiements avec les filtres appliqués"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from django.http import HttpResponse

    # Récupérer les filtres
    allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
    region_id = request.GET.get('region_id', 'all')
    district_id = request.GET.get('district_id', 'all')
    commune_id = request.GET.get('commune_id', 'all')
    recherche = request.GET.get('recherche', '').strip()

    # Construire le queryset des ouvrages avec modalité forfaitaire
    ouvrages_qs = Ouvrage.objects.filter(
        modalites_gestion__modalitepaiement='forfaitaire',
        modalites_gestion__date_fin__isnull=True,
        id__in=allowed_ouvrage_ids
    ).select_related(
        'type_ouvrage'
    ).prefetch_related(
        'modalites_gestion__gestionnaire',
        Prefetch(
            'pointeau_set',
            queryset=PointEau.objects.filter(tarifforfaitaire__isnull=False).prefetch_related(
                Prefetch(
                    'paiements_forfaitaires',
                    queryset=PaiementForfaitaire.objects.all().order_by('date_facture')
                )
            )
        )
    ).distinct()

    # Appliquer les filtres géographiques
    if commune_id != 'all':
        ouvrages_qs = ouvrages_qs.filter(
            pointeau__parcelle__village__fokontany__commune_id=commune_id
        ).distinct()
    elif district_id != 'all':
        ouvrages_qs = ouvrages_qs.filter(
            pointeau__parcelle__village__fokontany__commune__district_id=district_id
        ).distinct()
    elif region_id != 'all':
        ouvrages_qs = ouvrages_qs.filter(
            pointeau__parcelle__village__fokontany__commune__district__region_id=region_id
        ).distinct()

    # Filtre recherche
    if recherche:
        ouvrages_qs = ouvrages_qs.filter(
            nom_ouvrage__icontains=recherche
        )

    # Créer le workbook Excel
    wb = Workbook()
    ws = wb.active
    ws.title = "Paiements Forfaitaires"

    # Styles
    header_fill = PatternFill(start_color="0066CC", end_color="0066CC", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    # En-têtes
    headers = [
        'Région', 'District', 'Commune', 'Ouvrage', 'Organisation',
        'Point d\'eau', 'Nom abonné', 'Tarif forfaitaire',
        'Date facture', 'Quantité', 'Prix unitaire', 'Montant',
        'Durée (mois)', 'Date fin validité', 'Statut', 'Date paiement',
        'Numéro DiameX', 'Base DiameX'
    ]

    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num)
        cell.value = header
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = border

    # Données
    row_num = 2
    for ouvrage in ouvrages_qs:
        # Récupérer l'organisation via la modalité de gestion
        modalite = ouvrage.modalites_gestion.filter(
            modalitepaiement='forfaitaire',
            date_fin__isnull=True
        ).first()
        organisation_nom = modalite.gestionnaire.nom_organisation if modalite and modalite.gestionnaire else 'N/A'

        # Récupérer les infos géographiques via le premier point d'eau
        premier_pe = ouvrage.pointeau_set.first()
        region = district = commune = 'N/A'

        if premier_pe and premier_pe.parcelle:
            parcelle = premier_pe.parcelle
            if parcelle.village and parcelle.village.fokontany:
                fokontany = parcelle.village.fokontany
                if fokontany.commune:
                    commune = fokontany.commune.nom_commune
                    if fokontany.commune.district:
                        district = fokontany.commune.district.nom_district
                        if fokontany.commune.district.region:
                            region = fokontany.commune.district.region.nom_region

        # Pour chaque point d'eau de l'ouvrage
        for point_eau in ouvrage.pointeau_set.all():
            # Pour chaque paiement du point d'eau
            paiements = point_eau.paiements_forfaitaires.all()

            if paiements.exists():
                for paiement in paiements:
                    ws.cell(row=row_num, column=1).value = region
                    ws.cell(row=row_num, column=2).value = district
                    ws.cell(row=row_num, column=3).value = commune
                    ws.cell(row=row_num, column=4).value = ouvrage.nom_ouvrage
                    ws.cell(row=row_num, column=5).value = organisation_nom
                    ws.cell(row=row_num, column=6).value = point_eau.code_point_eau or 'N/A'
                    ws.cell(row=row_num, column=7).value = point_eau.nomabonne or 'N/A'
                    ws.cell(row=row_num, column=8).value = float(point_eau.tarifforfaitaire) if point_eau.tarifforfaitaire else 0
                    ws.cell(row=row_num, column=9).value = paiement.date_facture.strftime('%Y-%m-%d') if paiement.date_facture else ''
                    ws.cell(row=row_num, column=10).value = paiement.quantite or 0
                    ws.cell(row=row_num, column=11).value = float(paiement.prix_unitaire) if paiement.prix_unitaire else 0
                    ws.cell(row=row_num, column=12).value = float(paiement.montant) if paiement.montant else 0
                    ws.cell(row=row_num, column=13).value = paiement.duree_mois or 0
                    ws.cell(row=row_num, column=14).value = paiement.date_fin_validite.strftime('%Y-%m-%d') if paiement.date_fin_validite else ''
                    ws.cell(row=row_num, column=15).value = 'Payé' if paiement.paye else 'Non payé'
                    ws.cell(row=row_num, column=16).value = paiement.date_paiement.strftime('%Y-%m-%d') if paiement.date_paiement else ''
                    ws.cell(row=row_num, column=17).value = paiement.numeroDiameX or ''
                    ws.cell(row=row_num, column=18).value = paiement.baseDiameX or ''

                    # Bordures pour toutes les cellules
                    for col in range(1, 19):
                        ws.cell(row=row_num, column=col).border = border

                    row_num += 1
            else:
                # Point d'eau sans paiement
                ws.cell(row=row_num, column=1).value = region
                ws.cell(row=row_num, column=2).value = district
                ws.cell(row=row_num, column=3).value = commune
                ws.cell(row=row_num, column=4).value = ouvrage.nom_ouvrage
                ws.cell(row=row_num, column=5).value = organisation_nom
                ws.cell(row=row_num, column=6).value = point_eau.code_point_eau or 'N/A'
                ws.cell(row=row_num, column=7).value = point_eau.nomabonne or 'N/A'
                ws.cell(row=row_num, column=8).value = float(point_eau.tarifforfaitaire) if point_eau.tarifforfaitaire else 0
                ws.cell(row=row_num, column=9).value = 'Aucun paiement'

                for col in range(1, 19):
                    ws.cell(row=row_num, column=col).border = border

                row_num += 1

    # Ajuster la largeur des colonnes
    column_widths = [12, 15, 15, 20, 20, 15, 20, 15, 12, 10, 12, 12, 12, 15, 10, 12, 15, 15]
    for col_num, width in enumerate(column_widths, 1):
        ws.column_dimensions[ws.cell(row=1, column=col_num).column_letter].width = width

    # Préparer la réponse HTTP
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

    filename = f'paiements_forfaitaires_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    wb.save(response)
    return response


@login_required
@require_http_methods(["GET"])
def export_excel_coupures(request):
    """Export Excel de toutes les coupures d'eau avec filtres"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from django.http import HttpResponse

    # Récupérer les filtres
    allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
    region_id = request.GET.get('region_id', 'all')
    district_id = request.GET.get('district_id', 'all')
    commune_id = request.GET.get('commune_id', 'all')
    recherche = request.GET.get('recherche', '').strip()

    # Construire le queryset des coupures
    coupures_qs = CoupureEau.objects.select_related(
        'point_eau',
        'cree_par'
    ).filter(
        point_eau__ouvrage_id__in=allowed_ouvrage_ids
    ).order_by('-date_evenement')

    # Filtrer par géographie via le point d'eau
    if commune_id != 'all':
        coupures_qs = coupures_qs.filter(
            point_eau__parcelle__village__fokontany__commune_id=commune_id
        )
    elif district_id != 'all':
        coupures_qs = coupures_qs.filter(
            point_eau__parcelle__village__fokontany__commune__district_id=district_id
        )
    elif region_id != 'all':
        coupures_qs = coupures_qs.filter(
            point_eau__parcelle__village__fokontany__commune__district__region_id=region_id
        )

    # Filtre recherche sur nom du point d'eau ou abonné
    if recherche:
        coupures_qs = coupures_qs.filter(
            Q(point_eau__code_point_eau__icontains=recherche) |
            Q(point_eau__nomabonne__icontains=recherche)
        )

    # Créer le workbook Excel
    wb = Workbook()
    ws = wb.active
    ws.title = "Coupures et Remises"

    # Styles
    header_fill = PatternFill(start_color="DC3545", end_color="DC3545", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    # En-têtes
    headers = [
        'Code Point d\'eau', 'Nom abonné', 'Type événement', 'Date événement',
        'Raison', 'Notes', 'Créé par', 'Date création'
    ]

    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num)
        cell.value = header
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = border

    # Données
    row_num = 2
    for coupure in coupures_qs:
        ws.cell(row=row_num, column=1).value = coupure.point_eau.code_point_eau or 'N/A'
        ws.cell(row=row_num, column=2).value = coupure.point_eau.nomabonne or 'N/A'
        ws.cell(row=row_num, column=3).value = dict(CoupureEau.TYPE_COUPURE_CHOICES).get(coupure.type_evenement, coupure.type_evenement)
        ws.cell(row=row_num, column=4).value = coupure.date_evenement.strftime('%d/%m/%Y')
        ws.cell(row=row_num, column=5).value = dict(CoupureEau.RAISON_CHOICES).get(coupure.raison, coupure.raison or '')
        ws.cell(row=row_num, column=6).value = coupure.notes or ''
        ws.cell(row=row_num, column=7).value = coupure.cree_par.username if coupure.cree_par else 'N/A'
        ws.cell(row=row_num, column=8).value = coupure.created_at.strftime('%d/%m/%Y %H:%M') if coupure.created_at else ''

        # Bordures
        for col in range(1, 9):
            ws.cell(row=row_num, column=col).border = border

        row_num += 1

    # Ajuster la largeur des colonnes
    column_widths = [18, 25, 15, 15, 18, 30, 15, 18]
    for col_num, width in enumerate(column_widths, 1):
        ws.column_dimensions[ws.cell(row=1, column=col_num).column_letter].width = width

    # Préparer la réponse HTTP
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

    filename = f'coupures_eau_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    wb.save(response)
    return response


@login_required
@require_http_methods(["GET"])
def template_excel_coupures(request):
    """Télécharger un template Excel pour l'import des coupures"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from django.http import HttpResponse

    # Créer le workbook Excel
    allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
    wb = Workbook()
    ws = wb.active
    ws.title = "Template Coupures"

    # Styles
    header_fill = PatternFill(start_color="DC3545", end_color="DC3545", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    instruction_fill = PatternFill(start_color="FFF3CD", end_color="FFF3CD", fill_type="solid")
    border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    # En-têtes
    headers = [
        'ID Point d\'eau *', 'Type événement *', 'Date événement *',
        'Raison', 'Notes'
    ]

    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num)
        cell.value = header
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = border

    # Instructions
    ws.cell(row=2, column=1).value = 'UUID du point d\'eau'
    ws.cell(row=2, column=2).value = 'coupure ou remise'
    ws.cell(row=2, column=3).value = 'DD/MM/YYYY'
    ws.cell(row=2, column=4).value = 'non_paiement, travaux, maintenance, saison, autre'
    ws.cell(row=2, column=5).value = 'Commentaires (optionnel)'

    for col in range(1, 6):
        ws.cell(row=2, column=col).fill = instruction_fill
        ws.cell(row=2, column=col).border = border

    # Exemples
    ws.cell(row=3, column=1).value = '12345678-1234-1234-1234-123456789abc'
    ws.cell(row=3, column=2).value = 'coupure'
    ws.cell(row=3, column=3).value = '15/01/2025'
    ws.cell(row=3, column=4).value = 'non_paiement'
    ws.cell(row=3, column=5).value = 'Impayé depuis 3 mois'

    ws.cell(row=4, column=1).value = '12345678-1234-1234-1234-123456789abc'
    ws.cell(row=4, column=2).value = 'remise'
    ws.cell(row=4, column=3).value = '01/02/2025'
    ws.cell(row=4, column=4).value = 'non_paiement'
    ws.cell(row=4, column=5).value = 'Paiement reçu'

    for row in [3, 4]:
        for col in range(1, 6):
            ws.cell(row=row, column=col).border = border

    # Ajuster largeurs
    column_widths = [38, 18, 18, 35, 30]
    for col_num, width in enumerate(column_widths, 1):
        ws.column_dimensions[ws.cell(row=1, column=col_num).column_letter].width = width

    # Feuille de référence des points d'eau
    ws_ref = wb.create_sheet("Points d'eau")
    ws_ref.cell(row=1, column=1).value = "ID Point d'eau"
    ws_ref.cell(row=1, column=1).font = header_font
    ws_ref.cell(row=1, column=1).fill = header_fill
    ws_ref.cell(row=1, column=2).value = "Code"
    ws_ref.cell(row=1, column=2).font = header_font
    ws_ref.cell(row=1, column=2).fill = header_fill
    ws_ref.cell(row=1, column=3).value = "Nom abonné"
    ws_ref.cell(row=1, column=3).font = header_font
    ws_ref.cell(row=1, column=3).fill = header_fill

    # Lister les points d'eau (limité à 500)
    points_eau = PointEau.objects.filter(ouvrage_id__in=allowed_ouvrage_ids)[:500]
    for idx, pe in enumerate(points_eau, 2):
        ws_ref.cell(row=idx, column=1).value = str(pe.id)
        ws_ref.cell(row=idx, column=2).value = pe.code_point_eau or 'N/A'
        ws_ref.cell(row=idx, column=3).value = pe.nomabonne or 'N/A'

    ws_ref.column_dimensions['A'].width = 38
    ws_ref.column_dimensions['B'].width = 18
    ws_ref.column_dimensions['C'].width = 30

    # Préparer la réponse HTTP
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

    filename = 'template_coupures_eau.xlsx'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    wb.save(response)
    return response


@login_required
@require_http_methods(["POST"])
def import_excel_coupures(request):
    """Importer des coupures depuis un fichier Excel"""
    from openpyxl import load_workbook
    from django.http import JsonResponse

    if 'file' not in request.FILES:
        return JsonResponse({
            'success': False,
            'error': 'Aucun fichier fourni'
        }, status=400)

    try:
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        fichier = request.FILES['file']
        wb = load_workbook(fichier)
        ws = wb.active

        nb_imported = 0
        erreurs = []

        # Parcourir les lignes (ignorer header et instructions)
        for row_num, row in enumerate(ws.iter_rows(min_row=3, values_only=True), start=3):
            try:
                point_eau_id = row[0]
                type_evenement = row[1]
                date_evenement_str = row[2]
                raison = row[3] if len(row) > 3 else None
                notes = row[4] if len(row) > 4 else None

                # Validation des champs obligatoires
                if not all([point_eau_id, type_evenement, date_evenement_str]):
                    erreurs.append(f'Ligne {row_num}: Champs obligatoires manquants')
                    continue

                # Vérifier le point d'eau
                try:
                    point_eau = PointEau.objects.get(id=point_eau_id, ouvrage_id__in=allowed_ouvrage_ids)
                except PointEau.DoesNotExist:
                    erreurs.append(f'Ligne {row_num}: Point d\'eau {point_eau_id} introuvable')
                    continue

                # Valider le type d'événement
                if type_evenement not in ['coupure', 'remise']:
                    erreurs.append(f'Ligne {row_num}: Type événement invalide ({type_evenement}). Doit être "coupure" ou "remise"')
                    continue

                # Parser la date (format DD/MM/YYYY)
                if isinstance(date_evenement_str, datetime):
                    date_evenement = date_evenement_str.date()
                else:
                    try:
                        # Essayer d'abord DD/MM/YYYY
                        date_evenement = datetime.strptime(str(date_evenement_str), '%d/%m/%Y').date()
                    except:
                        try:
                            # Fallback sur YYYY-MM-DD
                            date_evenement = datetime.strptime(str(date_evenement_str), '%Y-%m-%d').date()
                        except:
                            erreurs.append(f'Ligne {row_num}: Format de date invalide ({date_evenement_str}). Utilisez DD/MM/YYYY')
                            continue

                # Créer la coupure
                CoupureEau.objects.create(
                    point_eau=point_eau,
                    type_evenement=type_evenement,
                    date_evenement=date_evenement,
                    raison=raison if raison else None,
                    notes=notes if notes else None,
                    cree_par=request.user
                )

                nb_imported += 1

            except Exception as e:
                erreurs.append(f'Ligne {row_num}: {str(e)}')
                continue

        return JsonResponse({
            'success': True,
            'message': f'{nb_imported} coupure(s)/remise(s) importée(s)',
            'nb_imported': nb_imported,
            'erreurs': erreurs
        })

    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


