"""
Vues pour le workflow des paiements forfaitaires

Workflow similaire à la facturation volumétrique mais avec montant fixe.
"""

import json
import openpyxl
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Sum, Count, Prefetch
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

import pytz

from apps.billing.models import PointEau, PaiementForfaitaire, ModaliteGestion, CoupureEau
from apps.organization.models import Organisation, Ouvrage
from apps.organization.scoping import get_user_accessible_gestionnaire_ids
from apps.geography.models import Commune, District, Region
from apps.planning.models import Planning, PlanningDetail, Designation
from apps.employees.models import Employe, EmployeOuvrages
from apps.employees.models_evaluation import FichePoste
from apps.employees.permissions import can_manage_forfaitaire_factures


def _normalize_date(value):
    if isinstance(value, datetime):
        return value.date()
    return value


def _calc_duree_mois(montant, tarif_forfaitaire, quantite=None):
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


def _calc_date_fin_validite(date_facture, duree_mois):
    if not date_facture or not duree_mois:
        return None
    from dateutil.relativedelta import relativedelta
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


def _ensure_forfaitaire_facture_write_access(user):
    if can_manage_forfaitaire_factures(user):
        return None

    return JsonResponse({
        'success': False,
        'error': "Vous n'avez pas l'autorisation de creer, modifier ou supprimer des factures forfaitaires."
    }, status=403)


def _get_collecte_forfaitaire_fiche_poste():
    fiche_poste = FichePoste.objects.select_related('type_activites').filter(
        tache__iexact='Collecte des paiements forfaitaires'
    ).first()
    if fiche_poste:
        return fiche_poste

    return FichePoste.objects.select_related('type_activites').filter(
        tache__icontains='paiements forfaitaires'
    ).order_by('tache').first()


def _get_forfaitaire_employe_label(employe):
    if not employe:
        return ''

    label = employe.nom_affichage
    base_name = getattr(getattr(employe, 'base', None), 'nom_base', '')
    if base_name:
        return f"{label} ({base_name})"
    return label


def _get_forfaitaire_points_for_ouvrage(ouvrage, allowed_ouvrage_ids):
    points_eau = PointEau.objects.filter(
        ouvrage=ouvrage,
        ouvrage_id__in=allowed_ouvrage_ids
    ).filter(
        Q(tarifforfaitaire__isnull=False, tarifforfaitaire__gt=0)
        | Q(paiements_forfaitaires__isnull=False)
        | Q(coupures_eau__isnull=False)
    ).distinct().order_by('code_point_eau')

    derniers_evenements_coupure = {}
    for evt in CoupureEau.objects.filter(point_eau__in=points_eau).order_by('point_eau_id', '-date_evenement', '-created_at'):
        point_id = str(evt.point_eau_id)
        if point_id not in derniers_evenements_coupure:
            derniers_evenements_coupure[point_id] = evt

    points_data = []
    for pe in points_eau:
        dernier_evenement = derniers_evenements_coupure.get(str(pe.id))
        est_coupe = bool(
            (dernier_evenement and dernier_evenement.type_evenement == 'coupure')
            or pe.datearretbranchement
        )
        date_arret = None
        if dernier_evenement and dernier_evenement.type_evenement == 'coupure' and dernier_evenement.date_evenement:
            date_arret = dernier_evenement.date_evenement.strftime('%Y-%m-%d')
        elif pe.datearretbranchement:
            date_arret = pe.datearretbranchement.strftime('%Y-%m-%d')

        points_data.append({
            'id': str(pe.id),
            'code': pe.code_point_eau,
            'idxls': pe.idxls or '',
            'nom': pe.nomabonne or '',
            'tarif_forfaitaire': float(pe.tarifforfaitaire) if pe.tarifforfaitaire else 0,
            'display': f"{pe.code_point_eau} - {pe.nomabonne}" if pe.nomabonne else pe.code_point_eau,
            'point_coupe': est_coupe,
            'est_coupe_actuellement': est_coupe,
            'date_arret_branchement': date_arret,
        })

    return points_data


def _get_forfaitaire_planning_employes_data(user, ouvrage=None, extra_employe_ids=None):
    today = timezone.localdate()
    user_org_id = _get_user_organisation_id(user)
    extra_ids = {
        str(employe_id)
        for employe_id in (extra_employe_ids or [])
        if employe_id
    }

    employes_qs = Employe.objects.select_related('base', 'poste').filter(
        Q(date_debauchage__isnull=True) | Q(date_debauchage__gte=today)
    )
    if user_org_id:
        employes_qs = employes_qs.filter(base__organisation_id=user_org_id)

    if ouvrage:
        active_assignment_ids = list(
            EmployeOuvrages.objects.filter(
                ouvrage=ouvrage,
                date_debut__lte=today,
            ).filter(
                Q(date_fin__isnull=True) | Q(date_fin__gte=today)
            ).values_list('employe_id', flat=True).distinct()
        )
        if active_assignment_ids:
            employes_qs = employes_qs.filter(id__in=active_assignment_ids)

    employes = list(
        employes_qs.order_by('surnom', 'prenom', 'nom', 'nom_employe')
    )
    seen_ids = {str(employe.id) for employe in employes}

    if extra_ids:
        extra_employes = (
            Employe.objects.select_related('base', 'poste')
            .filter(id__in=extra_ids)
            .exclude(id__in=seen_ids)
            .order_by('surnom', 'prenom', 'nom', 'nom_employe')
        )
        employes.extend(list(extra_employes))

    return [
        {
            'id': str(employe.id),
            'label': _get_forfaitaire_employe_label(employe),
        }
        for employe in employes
    ]


def _get_default_forfaitaire_ouvrage_recouvreur_id(ouvrage):
    if not ouvrage:
        return ''

    today = timezone.localdate()
    assignments = (
        EmployeOuvrages.objects.select_related('employe', 'employe__poste')
        .filter(
            ouvrage=ouvrage,
            date_debut__lte=today,
        )
        .filter(
            Q(date_fin__isnull=True) | Q(date_fin__gte=today)
        )
        .order_by(
            '-est_responsable_principal',
            '-date_debut',
            'employe__surnom',
            'employe__prenom',
            'employe__nom',
        )
    )

    for assignment in assignments:
        employe = assignment.employe
        if not employe:
            continue
        if employe.date_debauchage and employe.date_debauchage < today:
            continue
        if employe.is_agent_recouvrement:
            return str(employe.id)

    return ''


def _resolve_forfaitaire_planning_employe(user, employe_id, ouvrage=None, extra_employe_ids=None):
    employe_id_str = str(employe_id or '').strip()
    if not employe_id_str:
        return None

    allowed_employe_ids = {
        item['id']
        for item in _get_forfaitaire_planning_employes_data(
            user,
            ouvrage=ouvrage,
            extra_employe_ids=extra_employe_ids,
        )
    }
    if employe_id_str not in allowed_employe_ids:
        raise ValueError("Employe introuvable ou non autorise pour cet ouvrage.")

    employe = Employe.objects.select_related('base', 'poste').filter(
        id=employe_id_str
    ).first()
    if not employe:
        raise ValueError("Employe introuvable.")
    return employe


def _parse_forfaitaire_iso_date(value, field_label):
    value_str = str(value or '').strip()
    if not value_str:
        return None

    try:
        return datetime.strptime(value_str, '%Y-%m-%d').date()
    except ValueError as exc:
        raise ValueError(
            f"{field_label} invalide (attendu: YYYY-MM-DD)."
        ) from exc


def _get_or_create_forfaitaire_planning(point_eau, date_facture, employe):
    fiche_poste = _get_collecte_forfaitaire_fiche_poste()
    if not fiche_poste:
        raise ValueError(
            "La fiche de poste 'Collecte des paiements forfaitaires' est introuvable."
        )

    planning_dt = datetime.combine(date_facture, datetime.min.time())
    if timezone.is_naive(planning_dt) and timezone.is_aware(timezone.now()):
        planning_dt = timezone.make_aware(planning_dt, timezone.get_current_timezone())

    existing_qs = Planning.objects.filter(
        date__date=date_facture,
        ouvrage=point_eau.ouvrage,
        fiche_poste=fiche_poste,
    ).order_by('created_at', 'date')

    planning = None
    if employe:
        planning = existing_qs.filter(employe=employe).first()
        if planning is None:
            planning = existing_qs.filter(employe__isnull=True).first()
    else:
        planning = existing_qs.first()

    if planning:
        updated_fields = []
        if not planning.type_activite_id and fiche_poste.type_activites_id:
            planning.type_activite_id = fiche_poste.type_activites_id
            updated_fields.append('type_activite_id')
        if not planning.employe_id and employe:
            planning.employe = employe
            updated_fields.append('employe_id')
        if updated_fields:
            updated_fields.append('updated_at')
            planning.save(update_fields=updated_fields)
        return planning, False

    planning = Planning.objects.create(
        date=planning_dt,
        remarque=(
            "Collecte des paiements forfaitaires "
            f"(PE: {point_eau.code_point_eau or point_eau.id})"
        ),
        estvalide=False,
        statut='en_cours',
        employe=employe,
        ouvrage=point_eau.ouvrage,
        fiche_poste=fiche_poste,
        type_activite=fiche_poste.type_activites,
    )
    return planning, True


def _mark_forfaitaire_planning_validated(planning):
    if not planning:
        return False

    update_fields = []
    if planning.estvalide is not True:
        planning.estvalide = True
        update_fields.append('estvalide')

    if not planning.statut:
        planning.statut = 'en_cours'
        update_fields.append('statut')

    if update_fields:
        update_fields.append('updated_at')
        planning.save(update_fields=update_fields)
        return True

    return False


def _ensure_forfaitaire_paiement_planning_ready(paiement, employe=None, allow_create=False):
    if (
        not paiement
        or not getattr(paiement, 'point_eau_id', None)
        or not getattr(paiement, 'date_facture', None)
    ):
        return None, False, False

    planning = getattr(paiement, 'planning', None)
    planning_created = False

    if planning is None and allow_create:
        planning, planning_created = _get_or_create_forfaitaire_planning(
            point_eau=paiement.point_eau,
            date_facture=_normalize_date(paiement.date_facture),
            employe=employe,
        )
        paiement.planning = planning

    planning_validated = _mark_forfaitaire_planning_validated(planning)
    return planning, planning_created, planning_validated


@login_required
def workflow_paiement_forfaitaire(request):
    """
    Page principale du workflow des paiements forfaitaires

    Affiche:
    - Filtres par organisation, mois/année, commune, etc.
    - Liste des points d'eau avec modalité forfaitaire
    - Boutons pour calculer, importer, exporter
    """

    # Récupérer les organisations pour le filtre
    organisations = Organisation.objects.all().order_by('nom_organisation')

    # Récupérer les communes, districts, régions pour filtres géographiques
    regions = Region.objects.all().order_by('nom_region')
    districts = District.objects.all().order_by('nom_district')
    communes = Commune.objects.all().order_by('nom_commune')

    # Vérifier si l'utilisateur est Directeur
    est_directeur = False
    if hasattr(request.user, 'employe') and request.user.employe:
        if request.user.employe.poste:
            est_directeur = request.user.employe.poste.nom_poste.lower() == 'directeur'

    # Cloisonnement: ouvrages autorises via modalite de gestion active
    allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)

    # Annee par defaut pour le filtre
    annee_param = request.GET.get('annee_facture')
    annee_defaut = timezone.now().year
    if annee_param:
        try:
            annee_defaut = int(annee_param)
        except (TypeError, ValueError):
            annee_defaut = timezone.now().year

    # Liste des annees disponibles pour le filtre
    paiements_annees_qs = PaiementForfaitaire.objects.filter(
        point_eau__ouvrage_id__in=allowed_ouvrage_ids
    )
    annees = sorted(
        {d.year for d in paiements_annees_qs.dates('date_facture', 'year')} | {annee_defaut},
        reverse=True
    )

    # Stats: Points d'eau avec modalité forfaitaire
    stats_points_eau = PointEau.objects.filter(
        tarifforfaitaire__gt=0,
        ouvrage_id__in=allowed_ouvrage_ids
    ).distinct().count()

    paiements_base_qs = PaiementForfaitaire.objects.filter(
        point_eau__ouvrage_id__in=allowed_ouvrage_ids
    )

    paiements_annee_qs = paiements_base_qs.filter(date_facture__year=annee_defaut)

    # Stats: Total des paiements enregistres pour l'annee
    stats_paiements_total = paiements_annee_qs.count()

    # Stats: Montant total des paiements pour l'annee
    stats_montant_total = paiements_annee_qs.aggregate(total=Sum('montant'))['total'] or 0

    # Stats: Montant paye pour l'annee
    stats_montant_paye = paiements_annee_qs.filter(
        Q(numeroDiameX__isnull=False)
        & ~Q(numeroDiameX__exact='')
        & Q(baseDiameX__isnull=False)
        & ~Q(baseDiameX__exact='')
    ).aggregate(total=Sum('montant'))['total'] or 0

    stats_recouvrement = int(round((stats_montant_paye / stats_montant_total) * 100)) if stats_montant_total else 0

    context = {
        'title': 'Workflow Paiements Forfaitaires',
        'organisations': organisations,
        'regions': regions,
        'districts': districts,
        'communes': communes,
        'est_directeur': est_directeur,
        'stats_points_eau': stats_points_eau,
        'stats_paiements_total': stats_paiements_total,
        'stats_montant_total': int(stats_montant_total),
        'stats_montant_paye': int(stats_montant_paye),
        'stats_recouvrement': stats_recouvrement,
        'annees': annees,
        'annee_defaut': annee_defaut,
    }

    return render(request, 'billing/workflow_paiement_forfaitaire.html', context)


@login_required
@require_http_methods(["GET"])
def api_points_eau_forfaitaires(request):
    """
    API pour lister les points d'eau avec modalité forfaitaire

    Filtres GET:
    - organisation_id: ID de l'organisation
    - mois_facture: Mois de facturation (1-12)
    - annee_facture: Année de facturation
    - commune_id, district_id, region_id: Filtres géographiques
    - recherche: Recherche par nom point d'eau ou ouvrage

    Returns:
        JSON avec liste des points d'eau et leurs informations
    """

    try:
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)

        # Récupérer les filtres
        mois_facture = request.GET.get('mois_facture')
        annee_facture = request.GET.get('annee_facture')
        commune_id = request.GET.get('commune_id', 'all')
        district_id = request.GET.get('district_id', 'all')
        region_id = request.GET.get('region_id', 'all')
        recherche = request.GET.get('recherche', '').strip()
        communes_only = request.GET.get('communes_only') in ['1', 'true', 'yes']

        annee_val = None
        if annee_facture and annee_facture != 'all':
            try:
                annee_val = int(annee_facture)
            except (TypeError, ValueError):
                annee_val = None
        if not annee_val:
            annee_val = timezone.now().year

        # Requête de base: points d'eau avec TarifForfaitaire > 0
        points_eau_qs = PointEau.objects.filter(
            tarifforfaitaire__gt=0
        ).select_related(
            'ouvrage',
            'ouvrage__type_ouvrage',
            'type_point_eau',
            'parcelle__village__fokontany__commune__district__region'
        )

        # Filtrer par organisation de l'utilisateur connecté
        # CHANGEMENT: On filtre par organisation via modalités OU via paiements existants
        # pour inclure les ouvrages qui ont eu des paiements forfaitaires mais n'ont plus de modalité active
        points_eau_qs = points_eau_qs.filter(ouvrage_id__in=allowed_ouvrage_ids)

        # Filtres géographiques
        if region_id and region_id != 'all':
            points_eau_qs = points_eau_qs.filter(
                parcelle__village__fokontany__commune__district__region_id=region_id
            )
        if district_id and district_id != 'all':
            points_eau_qs = points_eau_qs.filter(
                parcelle__village__fokontany__commune__district_id=district_id
            )

        # Recherche par nom abonné ou nom ouvrage
        if recherche:
            points_eau_qs = points_eau_qs.filter(
                Q(nomabonne__icontains=recherche) |
                Q(code_point_eau__icontains=recherche) |
                Q(ouvrage__nom_ouvrage__icontains=recherche)
            )

        communes_raw = points_eau_qs.values(
            'parcelle__village__fokontany__commune_id',
            'parcelle__village__fokontany__commune__nom_commune'
        ).distinct()
        communes_list = [
            {
                'id': str(row['parcelle__village__fokontany__commune_id']),
                'nom': row['parcelle__village__fokontany__commune__nom_commune']
            }
            for row in communes_raw
            if row['parcelle__village__fokontany__commune_id']
        ]
        communes_list.sort(key=lambda item: item['nom'] or '')

        if commune_id and commune_id != 'all':
            points_eau_qs = points_eau_qs.filter(
                parcelle__village__fokontany__commune_id=commune_id
            )

        if communes_only:
            return JsonResponse({
                'success': True,
                'communes': communes_list
            })

        # Distinct pour éviter doublons
        points_eau_qs = points_eau_qs.distinct()

        paiements_annee_qs = PaiementForfaitaire.objects.filter(
            date_facture__year=annee_val
        ).order_by('-date_facture', '-created_at')
        points_eau_qs = points_eau_qs.prefetch_related(
            Prefetch('paiements_forfaitaires', queryset=paiements_annee_qs, to_attr='paiements_annee')
        )

        points_eau_list = list(points_eau_qs)

        def idxls_to_int(val):
            try:
                return int(str(val).strip())
            except (TypeError, ValueError):
                return None

        def pe_sort_key(pe):
            idxls_num = idxls_to_int(pe.idxls)
            idxls_sort = idxls_num if idxls_num is not None else 10**12
            return (
                idxls_sort,
                str(pe.idxls or ''),
                pe.nomabonne or pe.code_point_eau or '',
                str(pe.id)
            )

        points_eau_list.sort(key=pe_sort_key)

        # Calculer les statistiques sur les points d'eau filtrés
        stats_points_eau_filtres = len(points_eau_list)

        # Récupérer les IDs des points d'eau filtrés pour calculer les stats de paiements
        points_eau_ids = [pe.id for pe in points_eau_list]

        # Stats: Total des paiements pour ces points d'eau (annee filtree)
        stats_paiements = PaiementForfaitaire.objects.filter(
            point_eau_id__in=points_eau_ids,
            date_facture__year=annee_val
        )
        stats_paiements_total = stats_paiements.count()
        stats_montant_total = stats_paiements.aggregate(total=Sum('montant'))['total'] or 0
        stats_montant_paye = stats_paiements.filter(
            Q(numeroDiameX__isnull=False)
            & ~Q(numeroDiameX__exact='')
            & Q(baseDiameX__isnull=False)
            & ~Q(baseDiameX__exact='')
        ).aggregate(total=Sum('montant'))['total'] or 0
        stats_recouvrement = int(round((stats_montant_paye / stats_montant_total) * 100)) if stats_montant_total else 0

        # Construire la liste de résultats
        resultats = []

        for pe in points_eau_list:
            # Informations géographiques
            commune_nom = None
            district_nom = None
            if pe.parcelle and pe.parcelle.village and pe.parcelle.village.fokontany:
                if pe.parcelle.village.fokontany.commune:
                    commune_nom = pe.parcelle.village.fokontany.commune.nom_commune
                    if pe.parcelle.village.fokontany.commune.district:
                        district_nom = pe.parcelle.village.fokontany.commune.district.nom_district

            paiements_annee = getattr(pe, 'paiements_annee', [])
            paiement_existant = paiements_annee[0] if paiements_annee else None
            idxls_num = idxls_to_int(pe.idxls)

            total_quantite = 0
            total_montant = 0.0
            total_montant_paye = 0.0
            total_duree_mois = 0
            est_paye_annee = False

            if paiements_annee:
                est_paye_annee = all(paiement.est_paye for paiement in paiements_annee)

            for paiement in paiements_annee:
                quantite = paiement.quantite or 0
                total_quantite += quantite
                total_duree_mois += paiement.duree_mois or (quantite * 3)
                montant_val = float(paiement.montant or 0)
                total_montant += montant_val
                if paiement.est_paye:
                    total_montant_paye += montant_val

            resultats.append({
                'id': str(pe.id),
                'idxls': pe.idxls or '',
                'idxls_numeric': idxls_num,
                'nom': pe.nomabonne or pe.code_point_eau or 'Point d\'eau sans nom',
                'code_point_eau': pe.code_point_eau or '',
                'ouvrage_nom': pe.ouvrage.nom_ouvrage if pe.ouvrage else 'N/A',
                'ouvrage_id': str(pe.ouvrage.id) if pe.ouvrage else None,
                'ouvrage_type': pe.ouvrage.type_ouvrage.nom_type_ouvrage if pe.ouvrage and pe.ouvrage.type_ouvrage else 'N/A',
                'ouvrage_saisonnier': bool(pe.ouvrage.saisonnier) if pe.ouvrage else False,
                'type_point_eau': pe.type_point_eau.nom_type if pe.type_point_eau else 'N/A',
                'tarif_forfaitaire': float(pe.tarifforfaitaire),
                'commune': commune_nom or 'N/A',
                'district': district_nom or 'N/A',
                'point_coupe': bool(pe.datearretbranchement),
                'date_arret_branchement': pe.datearretbranchement.strftime('%Y-%m-%d') if pe.datearretbranchement else None,
                'paiement_resume': {
                    'quantite_total': total_quantite,
                    'montant_total': float(total_montant),
                    'montant_paye': float(total_montant_paye),
                    'duree_mois': total_duree_mois,
                    'paye': est_paye_annee
                },
                'paiement_existant': {
                    'id': str(paiement_existant.id),
                    'date_facture': paiement_existant.date_facture.strftime('%Y-%m-%d'),
                    'quantite': paiement_existant.quantite,
                    'montant': float(paiement_existant.montant),
                    'paye': paiement_existant.est_paye,
                    'date_paiement': paiement_existant.date_paiement.strftime('%Y-%m-%d') if paiement_existant.date_paiement else None,
                    'date_fin_validite': paiement_existant.date_fin_validite.strftime('%Y-%m-%d') if paiement_existant.date_fin_validite else None,
                } if paiement_existant else None,
            })

        return JsonResponse({
            'success': True,
            'points_eau': resultats,
            'total': len(resultats),
            'communes': communes_list,
            'stats': {
                'points_eau': stats_points_eau_filtres,
                'paiements_total': stats_paiements_total,
                'montant_total': int(stats_montant_total),
                'montant_paye': int(stats_montant_paye),
                'taux_recouvrement': stats_recouvrement
            }
        })

    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_enregistrer_paiements(request):
    """
    API pour enregistrer les paiements forfaitaires calculés

    POST body (JSON):
    {
        "paiements": [
            {
                "point_eau_id": "uuid",
                "date_facture": "YYYY-MM-DD",
                "quantite": 2,
                "prix_unitaire": 100000,
                "montant": 200000
            },
            ...
        ]
    }

    Returns:
        JSON avec succès et nombre de paiements enregistrés
    """

    try:
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        data = json.loads(request.body)
        paiements_data = data.get('paiements', [])

        if not paiements_data:
            return JsonResponse({
                'success': False,
                'error': 'Aucun paiement à enregistrer'
            }, status=400)

        tz_madagascar = pytz.timezone('Indian/Antananarivo')
        nb_enregistres = 0
        erreurs = []

        for paiement_data in paiements_data:
            try:
                point_eau_id = paiement_data.get('point_eau_id')
                date_facture_str = paiement_data.get('date_facture')
                quantite = paiement_data.get('quantite')
                prix_unitaire = paiement_data.get('prix_unitaire')
                montant = paiement_data.get('montant')

                # Validation
                if not all([point_eau_id, date_facture_str, quantite, prix_unitaire]):
                    erreurs.append(f"Point d'eau {point_eau_id}: champs obligatoires manquants")
                    continue

                # Vérifier que le point d'eau existe
                try:
                    point_eau = PointEau.objects.get(id=point_eau_id, ouvrage_id__in=allowed_ouvrage_ids)
                except PointEau.DoesNotExist:
                    erreurs.append(f"Point d'eau {point_eau_id} introuvable")
                    continue

                # Parser la date
                try:
                    date_naive = datetime.strptime(date_facture_str, '%Y-%m-%d')
                    date_facture = tz_madagascar.localize(date_naive)
                except ValueError:
                    erreurs.append(f"Point d'eau {point_eau.nom}: format de date invalide")
                    continue

                date_facture_val = _normalize_date(date_facture)
                duree_mois = _calc_duree_mois(
                    montant,
                    point_eau.tarifforfaitaire,
                    quantite
                )
                date_fin_validite = _calc_date_fin_validite(date_facture_val, duree_mois)

                # Vérifier si un paiement existe déjà pour ce mois
                paiement_existant = PaiementForfaitaire.objects.filter(
                    point_eau=point_eau,
                    date_facture__year=date_facture.year,
                    date_facture__month=date_facture.month
                ).first()

                if paiement_existant:
                    # Mettre à jour
                    paiement_existant.quantite = quantite
                    paiement_existant.prix_unitaire = Decimal(str(prix_unitaire))
                    paiement_existant.montant = Decimal(str(montant))
                    paiement_existant.date_facture = date_facture
                    paiement_existant.date_fin_validite = date_fin_validite
                    paiement_existant.save()
                else:
                    # Créer nouveau
                    PaiementForfaitaire.objects.create(
                        point_eau=point_eau,
                        date_facture=date_facture,
                        quantite=quantite,
                        prix_unitaire=Decimal(str(prix_unitaire)),
                        montant=Decimal(str(montant)),
                        date_fin_validite=date_fin_validite,
                        paye=False
                    )

                nb_enregistres += 1

            except Exception as e:
                erreurs.append(f"Erreur: {str(e)}")

        message = f'{nb_enregistres} paiement(s) enregistré(s)'
        if erreurs:
            message += f', {len(erreurs)} erreur(s)'

        return JsonResponse({
            'success': True,
            'message': message,
            'nb_enregistres': nb_enregistres,
            'erreurs': erreurs
        })

    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


@login_required
def export_excel_paiements_forfaitaires(request):
    """
    Export Excel des paiements forfaitaires avec filtres

    GET params: mêmes filtres que api_points_eau_forfaitaires
    """

    try:
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)

        # Récupérer les filtres
        mois_facture = request.GET.get('mois_facture')
        annee_facture = request.GET.get('annee_facture')
        commune_id = request.GET.get('commune_id', 'all')

        # Requête de base
        paiements_qs = PaiementForfaitaire.objects.select_related(
            'point_eau',
            'point_eau__ouvrage',
            'point_eau__parcelle__village__fokontany__commune'
        )
        paiements_qs = paiements_qs.filter(point_eau__ouvrage_id__in=allowed_ouvrage_ids)

        # Filtrer par mois/année
        if annee_facture and annee_facture != 'all':
            paiements_qs = paiements_qs.filter(
                date_facture__year=annee_facture
            )
        if mois_facture:
            paiements_qs = paiements_qs.filter(
                date_facture__month=mois_facture
            )

        # Filtrer par commune
        if commune_id and commune_id != 'all':
            paiements_qs = paiements_qs.filter(
                point_eau__parcelle__village__fokontany__commune_id=commune_id
            )

        paiements_qs = paiements_qs.distinct().order_by('date_facture', 'point_eau__nom')

        # Créer le fichier Excel
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Paiements Forfaitaires"

        # En-têtes
        headers = [
            'ID Point d\'eau', 'Nom Point d\'eau', 'Code Point d\'eau', 'Ouvrage', 'Commune',
            'Date Facture', 'Quantité (périodes 3 mois)', 'Prix Unitaire (Ar)',
            'Montant Total (Ar)', 'Durée (mois)', 'Payé', 'Date Paiement',
            'Date Début Validité', 'Date Fin Validité', 'Jours Restants',
            'Numéro DiameX', 'Base DiameX', 'Remarque'
        ]

        ws.append(headers)

        # Données
        for paiement in paiements_qs:
            # Commune
            commune_nom = ''
            if paiement.point_eau.parcelle and paiement.point_eau.parcelle.village:
                v = paiement.point_eau.parcelle.village
                if v.fokontany and v.fokontany.commune:
                    commune_nom = v.fokontany.commune.nom_commune

            ws.append([
                str(paiement.point_eau.id),
                paiement.point_eau.nomabonne or paiement.point_eau.code_point_eau or 'N/A',
                paiement.point_eau.code_point_eau or '',
                paiement.point_eau.ouvrage.nom_ouvrage if paiement.point_eau.ouvrage else 'N/A',
                commune_nom,
                paiement.date_facture.strftime('%Y-%m-%d'),
                paiement.quantite,
                float(paiement.prix_unitaire),
                float(paiement.montant),
                paiement.duree_mois,
                'Oui' if paiement.est_paye else 'Non',
                paiement.date_paiement.strftime('%Y-%m-%d') if paiement.date_paiement else '',
                paiement.date_debut_validite.strftime('%Y-%m-%d') if paiement.date_debut_validite else '',
                paiement.date_fin_validite.strftime('%Y-%m-%d') if paiement.date_fin_validite else '',
                paiement.jours_restants if paiement.jours_restants is not None else '',
                paiement.numeroDiameX or '',
                paiement.baseDiameX or '',
                paiement.remarque or ''
            ])

        # Préparer la réponse HTTP
        output = BytesIO()
        wb.save(output)
        output.seek(0)

        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

        filename_parts = ['paiements_forfaitaires']
        if annee_facture and annee_facture != 'all':
            filename_parts.append(str(annee_facture))
        if mois_facture:
            filename_parts.append(str(mois_facture).zfill(2))
        filename = '_'.join(filename_parts) + '.xlsx'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        return response

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return HttpResponse(f'Erreur: {str(e)}', status=500)


@csrf_exempt
@login_required
def template_excel_paiements_forfaitaires(request):
    """
    Télécharger le template Excel pour l'import des paiements forfaitaires
    """

    # Créer le fichier Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Template Paiements Forfaitaires"

    # En-têtes
    headers = [
        'ID Point d\'eau*',
        'Date Facture* (YYYY-MM-DD)',
        'Quantité* (nombre)',
        'Numéro DiameX',
        'Base DiameX'
    ]
    ws.append(headers)

    # Ligne d'exemple
    exemple = [
        '12345678-1234-1234-1234-123456789abc',
        '2025-01-01',
        '2',
        '',
        ''
    ]
    ws.append(exemple)

    # Instructions
    ws.append([])
    ws.append(['INSTRUCTIONS:'])
    ws.append(['* Champs obligatoires'])
    ws.append(['- ID Point d\'eau: UUID du point d\'eau (voir liste des points d\'eau)'])
    ws.append(['- Date Facture: Format YYYY-MM-DD ou DD/MM/YYYY'])
    ws.append(['- Quantité: Nombre entier (1 quantité = 3 mois d\'ouverture)'])
    ws.append(['  Exemple: Quantité=2 → 6 mois d\'ouverture'])
    ws.append(['- Prix unitaire: Récupéré automatiquement depuis TarifForfaitaire du point d\'eau'])
    ws.append(['- Montant: Calculé automatiquement (Quantité × Prix unitaire)'])
    ws.append(['- Numéro/Base DiameX: Optionnels, à remplir si paiement déjà enregistré'])

    # Ajuster largeurs colonnes
    ws.column_dimensions['A'].width = 40
    ws.column_dimensions['B'].width = 25
    ws.column_dimensions['C'].width = 20
    ws.column_dimensions['D'].width = 20
    ws.column_dimensions['E'].width = 20

    # Générer la réponse
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=template_paiements_forfaitaires.xlsx'

    return response


@login_required
@require_http_methods(["POST"])
def import_excel_paiements_forfaitaires(request):
    """
    Import Excel des paiements forfaitaires

    Format Excel attendu:
    - Colonne A: ID Point d'eau (UUID)
    - Colonne B: Date Facture (YYYY-MM-DD ou DD/MM/YYYY)
    - Colonne C: Quantité
    - Colonne D: Numéro DiameX (optionnel)
    - Colonne E: Base DiameX (optionnel)
    """

    try:
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        if 'file' not in request.FILES:
            return JsonResponse({
                'success': False,
                'error': 'Aucun fichier fourni'
            }, status=400)

        excel_file = request.FILES['file']

        # Lire le fichier Excel
        wb = openpyxl.load_workbook(excel_file)
        ws = wb.active

        tz_madagascar = pytz.timezone('Indian/Antananarivo')
        nb_importes = 0
        erreurs = []

        # Parcourir les lignes (skip header)
        for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            try:
                point_eau_id = row[0]
                date_facture_val = row[1]
                quantite = row[2]
                numero_diamex = row[3] if len(row) > 3 else None
                base_diamex = row[4] if len(row) > 4 else None

                # Skip lignes vides
                if not point_eau_id or not date_facture_val or not quantite:
                    continue

                # Récupérer le point d'eau
                try:
                    point_eau = PointEau.objects.get(id=point_eau_id, ouvrage_id__in=allowed_ouvrage_ids)
                except PointEau.DoesNotExist:
                    erreurs.append(f"Ligne {i}: Point d'eau {point_eau_id} introuvable")
                    continue

                # Parser la date
                if isinstance(date_facture_val, datetime):
                    date_facture = tz_madagascar.localize(date_facture_val)
                else:
                    # Essayer plusieurs formats
                    for fmt in ['%Y-%m-%d', '%d/%m/%Y']:
                        try:
                            date_naive = datetime.strptime(str(date_facture_val), fmt)
                            date_facture = tz_madagascar.localize(date_naive)
                            break
                        except ValueError:
                            continue
                    else:
                        erreurs.append(f"Ligne {i}: Format de date invalide")
                        continue

                # Convertir quantité en entier
                try:
                    quantite = int(quantite)
                except (ValueError, TypeError):
                    erreurs.append(f"Ligne {i}: Quantité invalide")
                    continue

                # Calculer prix unitaire et montant
                prix_unitaire = point_eau.tarifforfaitaire
                montant = quantite * prix_unitaire
                date_facture_val = _normalize_date(date_facture)
                duree_mois = _calc_duree_mois(
                    montant,
                    point_eau.tarifforfaitaire,
                    quantite
                )
                date_fin_validite = _calc_date_fin_validite(date_facture_val, duree_mois)


                # Vérifier si existe déjà
                paiement_existant = PaiementForfaitaire.objects.filter(
                    point_eau=point_eau,
                    date_facture__year=date_facture.year,
                    date_facture__month=date_facture.month
                ).first()

                if paiement_existant:
                    # Mettre à jour
                    paiement_existant.quantite = quantite
                    paiement_existant.prix_unitaire = prix_unitaire
                    paiement_existant.montant = montant
                    paiement_existant.date_facture = date_facture
                    paiement_existant.date_fin_validite = date_fin_validite
                    if numero_diamex:
                        paiement_existant.numeroDiameX = str(numero_diamex)
                        # Si numéro DiameX renseigné, marquer comme payé
                        paiement_existant.paye = True
                        if not paiement_existant.date_paiement:
                            paiement_existant.date_paiement = date_facture
                    if base_diamex:
                        paiement_existant.baseDiameX = str(base_diamex)
                    paiement_existant.save()
                else:
                    # Créer
                    PaiementForfaitaire.objects.create(
                        point_eau=point_eau,
                        date_facture=date_facture,
                        quantite=quantite,
                        prix_unitaire=prix_unitaire,
                        montant=montant,
                        date_fin_validite=date_fin_validite,
                        numeroDiameX=str(numero_diamex) if numero_diamex else None,
                        baseDiameX=str(base_diamex) if base_diamex else None,
                        paye=True if numero_diamex else False,  # Payé si numéro DiameX renseigné
                        date_paiement=date_facture if numero_diamex else None
                    )

                nb_importes += 1

            except Exception as e:
                erreurs.append(f"Ligne {i}: {str(e)}")

        message = f'{nb_importes} paiement(s) importé(s)'
        if erreurs:
            message += f', {len(erreurs)} erreur(s)'

        return JsonResponse({
            'success': True,
            'message': message,
            'nb_importes': nb_importes,
            'erreurs': erreurs
        })

    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_paiements_par_diamex(request):
    """
    API pour récupérer les paiements forfaitaires par numeroDiameX et baseDiameX
    + les paiements non payés du même ouvrage

    Utilisé dans la page de recoupement pour afficher les détails d'une ligne
    """
    numero_diamex = request.GET.get('numeroDiameX', '')
    base_diamex = request.GET.get('baseDiameX', '')

    if not numero_diamex or not base_diamex:
        return JsonResponse({
            'success': False,
            'error': 'Paramètres numeroDiameX et baseDiameX requis'
        }, status=400)

    try:
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        # Récupérer les paiements avec ce couple (numeroDiameX, baseDiameX)
        paiements_payes = PaiementForfaitaire.objects.filter(
            numeroDiameX=numero_diamex,
            baseDiameX=base_diamex
        ).select_related('point_eau', 'point_eau__ouvrage').order_by('date_facture')
        paiements_payes = paiements_payes.filter(point_eau__ouvrage_id__in=allowed_ouvrage_ids)

        # Récupérer l'ouvrage depuis un des paiements
        ouvrage = None
        if paiements_payes.exists():
            premier = paiements_payes.first()
            if premier.point_eau and premier.point_eau.ouvrage:
                ouvrage = premier.point_eau.ouvrage

        # Récupérer les paiements non payés du même ouvrage
        paiements_non_payes = PaiementForfaitaire.objects.none()
        if ouvrage:
            paiements_non_payes = PaiementForfaitaire.objects.filter(
                point_eau__ouvrage=ouvrage,
                point_eau__ouvrage_id__in=allowed_ouvrage_ids,
                paye=False
            ).select_related('point_eau', 'point_eau__ouvrage').order_by('date_facture')

        # Formater les données (paiements payés)
        paiements_data = []
        for p in paiements_payes:
            paiements_data.append({
                'id': str(p.id),
                'point_eau_code': p.point_eau.code_point_eau if p.point_eau else None,
                'point_eau_nom': p.point_eau.nomabonne if p.point_eau else None,
                'date_facture': p.date_facture.strftime('%d/%m/%Y') if p.date_facture else None,
                'quantite': float(p.quantite) if p.quantite else 0,
                'prix_unitaire': float(p.prix_unitaire) if p.prix_unitaire else 0,
                'montant': float(p.montant) if p.montant else 0,
                'paye': p.paye,
                'numeroDiameX': p.numeroDiameX,
                'baseDiameX': p.baseDiameX,
            })

        # Formater les données (paiements non payés)
        paiements_non_payes_data = []
        for p in paiements_non_payes:
            paiements_non_payes_data.append({
                'id': str(p.id),
                'point_eau_code': p.point_eau.code_point_eau if p.point_eau else None,
                'point_eau_nom': p.point_eau.nomabonne if p.point_eau else None,
                'date_facture': p.date_facture.strftime('%d/%m/%Y') if p.date_facture else None,
                'quantite': float(p.quantite) if p.quantite else 0,
                'prix_unitaire': float(p.prix_unitaire) if p.prix_unitaire else 0,
                'montant': float(p.montant) if p.montant else 0,
                'paye': p.paye,
                'numeroDiameX': p.numeroDiameX,
                'baseDiameX': p.baseDiameX,
            })

        return JsonResponse({
            'success': True,
            'paiements': paiements_data,
            'paiements_non_payes': paiements_non_payes_data,
            'total': len(paiements_data),
            'total_non_payes': len(paiements_non_payes_data)
        })

    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_get_paiements_point_eau(request, pe_id):
    """
    API pour récupérer tous les paiements forfaitaires d'un point d'eau spécifique
    """
    try:
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        paiements = (
            PaiementForfaitaire.objects
            .select_related('point_eau', 'planning', 'planning__employe', 'planning__employe__base')
            .filter(point_eau_id=pe_id, point_eau__ouvrage_id__in=allowed_ouvrage_ids)
            .order_by('-date_facture')
        )
        
        paiements_data = []
        for p in paiements:
            paiements_data.append({
                'id': str(p.id),
                'date_facture': p.date_facture.strftime('%Y-%m-%d') if p.date_facture else None,
                'date_paiement': p.date_paiement.strftime('%Y-%m-%d') if p.date_paiement else None,
                'point_eau_idxls': str(p.point_eau.idxls) if p.point_eau and p.point_eau.idxls else '',
                'quantite': float(p.quantite) if p.quantite else 0,
                'prix_unitaire': float(p.prix_unitaire) if p.prix_unitaire else 0,
                'montant': float(p.montant) if p.montant else 0,
                'numeroDiameX': p.numeroDiameX,
                'baseDiameX': p.baseDiameX,
                'paye': p.paye,
            })
            
        return JsonResponse({
            'success': True,
            'paiements': paiements_data
        })
    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_get_paiements_ouvrage(request, ouvrage_id):
    """
    API pour récupérer tous les paiements forfaitaires d'un ouvrage
    (tous les points d'eau forfaitaires de l'ouvrage).
    """
    try:
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        if str(ouvrage_id) not in {str(x) for x in allowed_ouvrage_ids}:
            return JsonResponse({
                'success': False,
                'error': 'Accès refusé à cet ouvrage'
            }, status=403)

        ouvrage = Ouvrage.objects.filter(
            id=ouvrage_id,
            id__in=allowed_ouvrage_ids,
        ).first()
        if not ouvrage:
            return JsonResponse({
                'success': False,
                'error': 'Ouvrage introuvable'
            }, status=404)

        annee = request.GET.get('annee')
        paiements = (
            PaiementForfaitaire.objects
            .select_related('point_eau', 'planning', 'planning__employe', 'planning__employe__base')
            .filter(
                point_eau__ouvrage_id=ouvrage_id,
                point_eau__tarifforfaitaire__isnull=False,
            )
            .order_by('-date_facture', '-created_at')
        )

        if annee:
            try:
                paiements = paiements.filter(date_facture__year=int(annee))
            except (TypeError, ValueError):
                return JsonResponse({
                    'success': False,
                    'error': 'Paramètre annee invalide'
                }, status=400)

        points_eau_data = _get_forfaitaire_points_for_ouvrage(ouvrage, allowed_ouvrage_ids)

        extra_employe_ids = set()
        if hasattr(request.user, 'employe') and getattr(request.user, 'employe', None):
            extra_employe_ids.add(str(request.user.employe.id))
        extra_employe_ids.update(
            str(employe_id)
            for employe_id in paiements.values_list('planning__employe_id', flat=True)
            if employe_id
        )
        planning_employes = _get_forfaitaire_planning_employes_data(
            request.user,
            ouvrage=ouvrage,
            extra_employe_ids=extra_employe_ids,
        )
        planning_employe_ids = {item['id'] for item in planning_employes}
        default_planning_employe_id = _get_default_forfaitaire_ouvrage_recouvreur_id(ouvrage)
        if default_planning_employe_id and default_planning_employe_id not in planning_employe_ids:
            default_planning_employe_id = ''
        if not default_planning_employe_id and hasattr(request.user, 'employe') and getattr(request.user, 'employe', None):
            user_employe_id = str(request.user.employe.id)
            if user_employe_id in planning_employe_ids:
                default_planning_employe_id = user_employe_id
        if not default_planning_employe_id and len(planning_employes) == 1:
            default_planning_employe_id = planning_employes[0]['id']

        paiements_data = []
        for p in paiements:
            planning_date = _normalize_date(p.planning.date) if p.planning and p.planning.date else None
            paiements_data.append({
                'id': str(p.id),
                'point_eau_id': str(p.point_eau_id) if p.point_eau_id else '',
                'point_eau_nom': p.point_eau.nomabonne if p.point_eau and p.point_eau.nomabonne else (p.point_eau.code_point_eau if p.point_eau else ''),
                'point_eau_idxls': str(p.point_eau.idxls) if p.point_eau and p.point_eau.idxls else '',
                'date_facture': p.date_facture.strftime('%Y-%m-%d') if p.date_facture else None,
                'date_paiement': p.date_paiement.strftime('%Y-%m-%d') if p.date_paiement else None,
                'planning_id': str(p.planning_id) if p.planning_id else '',
                'planning_date': planning_date.strftime('%Y-%m-%d') if planning_date else None,
                'planning_employe_id': str(p.planning.employe_id) if p.planning and p.planning.employe_id else '',
                'planning_employe_label': _get_forfaitaire_employe_label(getattr(p.planning, 'employe', None)),
                'quantite': float(p.quantite) if p.quantite else 0,
                'prix_unitaire': float(p.prix_unitaire) if p.prix_unitaire else 0,
                'montant': float(p.montant) if p.montant else 0,
                'numeroDiameX': p.numeroDiameX,
                'baseDiameX': p.baseDiameX,
                'paye': p.paye,
            })

        return JsonResponse({
            'success': True,
            'paiements': paiements_data,
            'points_eau': points_eau_data,
            'planning_employes': planning_employes,
            'default_planning_employe_id': default_planning_employe_id,
        })

    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_paiement_detail(request, paiement_id):
    """
    API pour récupérer les détails d'un paiement forfaitaire
    """
    try:
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        paiement = PaiementForfaitaire.objects.select_related(
            'point_eau', 'point_eau__ouvrage'
        ).get(id=paiement_id, point_eau__ouvrage_id__in=allowed_ouvrage_ids)

        paiement_data = {
            'id': str(paiement.id),
            'point_eau_id': str(paiement.point_eau.id) if paiement.point_eau else None,
            'point_eau_code': paiement.point_eau.code_point_eau if paiement.point_eau else None,
            'date_facture': paiement.date_facture.strftime('%Y-%m-%d') if paiement.date_facture else None,
            'quantite': float(paiement.quantite) if paiement.quantite else 0,
            'prix_unitaire': float(paiement.prix_unitaire) if paiement.prix_unitaire else 0,
            'montant': float(paiement.montant) if paiement.montant else 0,
            'numeroDiameX': paiement.numeroDiameX,
            'baseDiameX': paiement.baseDiameX,
            'paye': paiement.paye,
        }

        return JsonResponse({
            'success': True,
            'paiement': paiement_data
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
@require_http_methods(["POST"])
def api_paiement_update(request, paiement_id):
    """
    API pour mettre à jour un paiement forfaitaire

    Permet de modifier: quantite, prix_unitaire, numeroDiameX, baseDiameX, point_eau_id
    """
    try:
        access_denied_response = _ensure_forfaitaire_facture_write_access(request.user)
        if access_denied_response:
            return access_denied_response
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        paiement = PaiementForfaitaire.objects.select_related(
            'point_eau',
            'point_eau__ouvrage',
            'planning',
            'planning__employe',
        ).get(id=paiement_id, point_eau__ouvrage_id__in=allowed_ouvrage_ids)
        employe = getattr(request.user, 'employe', None) if hasattr(request.user, 'employe') else None

        # Verrouillage: une ligne déjà pointée (numero/base présents) ne peut plus être modifiée
        if (paiement.numeroDiameX or '').strip() and (paiement.baseDiameX or '').strip():
            return JsonResponse({
                'success': False,
                'error': 'Cette facture est déjà pointée et est verrouillée.'
            }, status=400)

        # Charger les données JSON
        data = json.loads(request.body)

        # Mettre à jour le point d'eau (réassignation)
        if 'point_eau_id' in data and data['point_eau_id'] != str(paiement.point_eau_id):
            new_pe_id = data['point_eau_id']
            try:
                new_pe = PointEau.objects.get(id=new_pe_id, ouvrage_id__in=allowed_ouvrage_ids)
                # Vérifier si c'est le même ouvrage (sécurité)
                if paiement.point_eau and paiement.point_eau.ouvrage_id != new_pe.ouvrage_id:
                     return JsonResponse({
                        'success': False,
                        'error': 'Le point d\'eau doit appartenir au même ouvrage'
                    }, status=400)
                paiement.point_eau = new_pe
            except PointEau.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Point d\'eau introuvable'
                }, status=404)

        if 'date_facture' in data and data['date_facture']:
            try:
                paiement.date_facture = datetime.strptime(data['date_facture'], '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({
                    'success': False,
                    'error': 'Format de date invalide (attendu: YYYY-MM-DD)'
                }, status=400)

        # Mettre à jour les autres champs
        if 'quantite' in data:
            paiement.quantite = Decimal(str(data['quantite']))
            
        if 'prix_unitaire' in data:
            paiement.prix_unitaire = Decimal(str(data['prix_unitaire']))

        # Recalculer le montant si nécessaire
        if 'quantite' in data or 'prix_unitaire' in data:
            if paiement.quantite is not None and paiement.prix_unitaire is not None:
                paiement.montant = paiement.quantite * paiement.prix_unitaire

        if 'numeroDiameX' in data:
            paiement.numeroDiameX = data['numeroDiameX'] if data['numeroDiameX'] else None

        if 'baseDiameX' in data:
            paiement.baseDiameX = data['baseDiameX'] if data['baseDiameX'] else None

        # Mettre à jour le statut payé
        if paiement.numeroDiameX and paiement.baseDiameX:
            paiement.paye = True
            if not paiement.date_paiement:
                paiement.date_paiement = timezone.now().date()
        else:
            # Ne pas débiter si déjà marqué payé manuellement ? 
            # Pour l'instant on suit la logique numeroDiameX
            paiement.paye = bool(paiement.numeroDiameX)
            if not paiement.paye:
                paiement.date_paiement = None

        if paiement.date_facture:
            duree_mois = _calc_duree_mois(
                paiement.montant,
                paiement.point_eau.tarifforfaitaire,
                paiement.quantite
            )
            paiement.date_fin_validite = _calc_date_fin_validite(
                _normalize_date(paiement.date_facture),
                duree_mois
            )

        planning = paiement.planning if paiement.planning_id else None
        planning_created = False
        planning_validated = False
        ouvrage = paiement.point_eau.ouvrage if paiement.point_eau else None
        extra_employe_ids = []
        if planning and planning.employe_id:
            extra_employe_ids.append(planning.employe_id)
        if employe and employe.id:
            extra_employe_ids.append(employe.id)

        if 'planning_date' in data:
            try:
                planning_date = _parse_forfaitaire_iso_date(
                    data.get('planning_date'),
                    'Date planning',
                )
            except ValueError as exc:
                return JsonResponse({
                    'success': False,
                    'error': str(exc)
                }, status=400)
        else:
            planning_date = (
                _normalize_date(planning.date)
                if planning and planning.date else _normalize_date(paiement.date_facture)
            )

        if not planning_date:
            planning_date = _normalize_date(paiement.date_facture)

        if 'planning_employe_id' in data:
            try:
                planning_employe = _resolve_forfaitaire_planning_employe(
                    request.user,
                    data.get('planning_employe_id'),
                    ouvrage=ouvrage,
                    extra_employe_ids=extra_employe_ids,
                )
            except ValueError as exc:
                return JsonResponse({
                    'success': False,
                    'error': str(exc)
                }, status=400)
        else:
            planning_employe = getattr(planning, 'employe', None) or employe

        should_sync_planning = (
            planning is None
            or 'date_facture' in data
            or 'point_eau_id' in data
            or 'planning_date' in data
            or 'planning_employe_id' in data
        )

        if should_sync_planning:
            if not planning_date:
                return JsonResponse({
                    'success': False,
                    'error': 'Date planning requise.'
                }, status=400)
            planning, planning_created = _get_or_create_forfaitaire_planning(
                point_eau=paiement.point_eau,
                date_facture=planning_date,
                employe=planning_employe,
            )
            paiement.planning = planning
            planning_validated = _mark_forfaitaire_planning_validated(planning)
        else:
            planning, _, planning_validated = _ensure_forfaitaire_paiement_planning_ready(
                paiement,
                employe=employe,
                allow_create=False,
            )

        paiement.save()

        return JsonResponse({
            'success': True,
            'message': 'Paiement mis à jour avec succès'
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
@require_http_methods(["POST"])
def api_paiement_create(request):
    """
    API pour créer un nouveau paiement forfaitaire
    """
    try:
        access_denied_response = _ensure_forfaitaire_facture_write_access(request.user)
        if access_denied_response:
            return access_denied_response
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        # Charger les données JSON
        data = json.loads(request.body)

        # Validation des champs obligatoires
        if not data.get('point_eau_id'):
            return JsonResponse({
                'success': False,
                'error': 'Point d\'eau requis'
            }, status=400)

        # Récupérer le point d'eau
        point_eau = PointEau.objects.select_related('ouvrage').get(
            id=data['point_eau_id'],
            ouvrage_id__in=allowed_ouvrage_ids
        )
        date_facture_str = data.get('date_facture')
        if date_facture_str:
            try:
                date_facture = datetime.strptime(date_facture_str, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({
                    'success': False,
                    'error': 'Format de date invalide (attendu: YYYY-MM-DD)'
                }, status=400)
        else:
            date_facture = timezone.now().date()


        # Créer le paiement (avec planning lié)
        try:
            quantite = Decimal(str(data.get('quantite', 1)))
        except Exception:
            return JsonResponse({
                'success': False,
                'error': 'Quantité invalide'
            }, status=400)

        if quantite <= 0:
            return JsonResponse({
                'success': False,
                'error': 'La quantité doit être supérieure à 0'
            }, status=400)

        prix_unitaire_raw = data.get('prix_unitaire')
        if prix_unitaire_raw in (None, ''):
            prix_unitaire_raw = point_eau.tarifforfaitaire or 0

        try:
            prix_unitaire = Decimal(str(prix_unitaire_raw))
        except Exception:
            return JsonResponse({
                'success': False,
                'error': 'Prix unitaire invalide'
            }, status=400)

        if prix_unitaire < 0:
            return JsonResponse({
                'success': False,
                'error': 'Le prix unitaire ne peut pas être négatif'
            }, status=400)

        montant = quantite * prix_unitaire
        duree_mois = _calc_duree_mois(
            montant,
            point_eau.tarifforfaitaire,
            quantite
        )
        date_fin_validite = _calc_date_fin_validite(date_facture, duree_mois)

        # Date planning = date de facture à minuit (timezone courante)
        planning_dt = datetime.combine(date_facture, datetime.min.time())
        if timezone.is_naive(planning_dt) and timezone.is_aware(timezone.now()):
            planning_dt = timezone.make_aware(planning_dt, timezone.get_current_timezone())

        employe = None
        if hasattr(request.user, 'employe'):
            try:
                employe = request.user.employe
            except Exception:
                employe = None

        try:
            planning_date = _parse_forfaitaire_iso_date(
                data.get('planning_date'),
                'Date planning',
            ) or date_facture
        except ValueError as exc:
            return JsonResponse({
                'success': False,
                'error': str(exc)
            }, status=400)

        try:
            planning_employe = _resolve_forfaitaire_planning_employe(
                request.user,
                data.get('planning_employe_id'),
                ouvrage=point_eau.ouvrage,
                extra_employe_ids=[employe.id] if employe and employe.id else None,
            )
        except ValueError as exc:
            return JsonResponse({
                'success': False,
                'error': str(exc)
            }, status=400)

        if planning_employe is None:
            planning_employe = employe

        designation_pf = Designation.objects.filter(
            actif=True,
            nom__iexact='Paiement forfaitaire'
        ).first()
        if not designation_pf:
            designation_pf = Designation.objects.filter(
                actif=True,
                nom__icontains='Paiement forfaitaire'
            ).first()

        with transaction.atomic():
            planning = Planning.objects.create(
                date=planning_dt,
                remarque=(
                    "Paiement forfaitaire créé via API "
                    f"(PE: {point_eau.code_point_eau or point_eau.id})"
                ),
                estvalide=False,
                statut='en_cours',
                employe=employe,
                ouvrage=point_eau.ouvrage
            )

            detail_created = False
            if designation_pf:
                PlanningDetail.objects.create(
                    planning=planning,
                    designation=designation_pf,
                    quantity=float(quantite),
                    pu=prix_unitaire,
                    montant=montant,
                    point_eau=point_eau
                )
                detail_created = True

            paiement = PaiementForfaitaire.objects.create(
                point_eau=point_eau,
                planning=planning,
                date_facture=date_facture,
                quantite=quantite,
                prix_unitaire=prix_unitaire,
                montant=montant,
                date_fin_validite=date_fin_validite,
                numeroDiameX=data.get('numeroDiameX'),
                baseDiameX=data.get('baseDiameX'),
                paye=bool(data.get('numeroDiameX')),
                date_paiement=timezone.now().date() if data.get('numeroDiameX') else None
            )

        return JsonResponse({
            'success': True,
            'message': 'Paiement créé avec succès',
            'paiement_id': str(paiement.id),
            'planning_id': str(planning.id),
            'planning_detail_created': detail_created
        })

    except PointEau.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Point d\'eau non trouvé'
        }, status=404)
    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


@login_required
@require_http_methods(["POST"])
def api_paiement_create(request):
    """
    API pour creer un nouveau paiement forfaitaire
    """
    try:
        access_denied_response = _ensure_forfaitaire_facture_write_access(request.user)
        if access_denied_response:
            return access_denied_response

        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        data = json.loads(request.body)

        if not data.get('point_eau_id'):
            return JsonResponse({
                'success': False,
                'error': "Point d'eau requis"
            }, status=400)

        point_eau = PointEau.objects.select_related('ouvrage').get(
            id=data['point_eau_id'],
            ouvrage_id__in=allowed_ouvrage_ids
        )

        date_facture_str = data.get('date_facture')
        if date_facture_str:
            try:
                date_facture = datetime.strptime(date_facture_str, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({
                    'success': False,
                    'error': 'Format de date invalide (attendu: YYYY-MM-DD)'
                }, status=400)
        else:
            date_facture = timezone.now().date()

        try:
            quantite = Decimal(str(data.get('quantite', 1)))
        except Exception:
            return JsonResponse({
                'success': False,
                'error': 'Quantite invalide'
            }, status=400)

        if quantite <= 0:
            return JsonResponse({
                'success': False,
                'error': 'La quantite doit etre strictement positive'
            }, status=400)

        try:
            prix_unitaire = Decimal(str(point_eau.tarifforfaitaire or 0))
        except Exception:
            return JsonResponse({
                'success': False,
                'error': "Tarif forfaitaire invalide sur ce point d'eau"
            }, status=400)

        if prix_unitaire <= 0:
            return JsonResponse({
                'success': False,
                'error': "Le tarif forfaitaire du point d'eau doit etre renseigne et strictement positif."
            }, status=400)

        montant = quantite * prix_unitaire
        duree_mois = _calc_duree_mois(
            montant,
            point_eau.tarifforfaitaire,
            quantite,
        )
        date_fin_validite = _calc_date_fin_validite(date_facture, duree_mois)

        employe = None
        if hasattr(request.user, 'employe'):
            try:
                employe = request.user.employe
            except Exception:
                employe = None

        try:
            planning_date = _parse_forfaitaire_iso_date(
                data.get('planning_date'),
                'Date planning',
            ) or date_facture
        except ValueError as exc:
            return JsonResponse({
                'success': False,
                'error': str(exc)
            }, status=400)

        try:
            planning_employe = _resolve_forfaitaire_planning_employe(
                request.user,
                data.get('planning_employe_id'),
                ouvrage=point_eau.ouvrage,
                extra_employe_ids=[employe.id] if employe and employe.id else None,
            )
        except ValueError as exc:
            return JsonResponse({
                'success': False,
                'error': str(exc)
            }, status=400)

        if planning_employe is None:
            planning_employe = employe

        designation_pf = Designation.objects.filter(
            actif=True,
            nom__iexact='Paiement forfaitaire'
        ).first()
        if not designation_pf:
            designation_pf = Designation.objects.filter(
                actif=True,
                nom__icontains='Paiement forfaitaire'
            ).first()

        with transaction.atomic():
            planning, planning_created = _get_or_create_forfaitaire_planning(
                point_eau=point_eau,
                date_facture=planning_date,
                employe=planning_employe,
            )
            _mark_forfaitaire_planning_validated(planning)

            detail_created = False
            if designation_pf:
                PlanningDetail.objects.create(
                    planning=planning,
                    designation=designation_pf,
                    quantity=float(quantite),
                    pu=prix_unitaire,
                    montant=montant,
                    point_eau=point_eau,
                )
                detail_created = True

            paiement = PaiementForfaitaire.objects.create(
                point_eau=point_eau,
                planning=planning,
                date_facture=date_facture,
                quantite=quantite,
                prix_unitaire=prix_unitaire,
                montant=montant,
                date_fin_validite=date_fin_validite,
                numeroDiameX=data.get('numeroDiameX'),
                baseDiameX=data.get('baseDiameX'),
                paye=bool(data.get('numeroDiameX')),
                date_paiement=timezone.now().date() if data.get('numeroDiameX') else None,
            )

        return JsonResponse({
            'success': True,
            'message': 'Paiement cree avec succes',
            'paiement_id': str(paiement.id),
            'planning_id': str(planning.id),
            'planning_detail_created': detail_created,
            'planning_created': planning_created,
        })

    except PointEau.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': "Point d'eau non trouve"
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
def api_points_eau_par_numero_base_diamex(request):
    """
    API pour récupérer les points d'eau associés à un numeroDiameX et baseDiameX
    Utilisé pour peupler le dropdown lors de l'ajout d'un paiement
    """
    numero_diamex = request.GET.get('numeroDiameX', '')
    base_diamex = request.GET.get('baseDiameX', '')

    if not numero_diamex or not base_diamex:
        return JsonResponse({
            'success': False,
            'error': 'Paramètres numeroDiameX et baseDiameX requis'
        }, status=400)

    try:
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        # Récupérer un paiement existant pour trouver l'ouvrage
        paiement_ref = PaiementForfaitaire.objects.filter(
            numeroDiameX=numero_diamex,
            baseDiameX=base_diamex
        ).filter(point_eau__ouvrage_id__in=allowed_ouvrage_ids
        ).select_related('point_eau', 'point_eau__ouvrage').first()

        if not paiement_ref or not paiement_ref.point_eau or not paiement_ref.point_eau.ouvrage:
            return JsonResponse({
                'success': False,
                'error': 'Ouvrage non trouvé pour ces paramètres'
            }, status=404)

        ouvrage = paiement_ref.point_eau.ouvrage

        # Récupérer tous les points d'eau de cet ouvrage
        points_eau = PointEau.objects.filter(ouvrage=ouvrage, ouvrage_id__in=allowed_ouvrage_ids).order_by('code_point_eau')

        # Formater les données
        derniers_evenements = {}
        for evt in CoupureEau.objects.filter(point_eau__in=points_eau).order_by('point_eau_id', '-date_evenement', '-created_at'):
            point_id = str(evt.point_eau_id)
            if point_id not in derniers_evenements:
                derniers_evenements[point_id] = evt

        derniers_evenements_coupure = {}
        for evt in CoupureEau.objects.filter(point_eau__in=points_eau).order_by('point_eau_id', '-date_evenement', '-created_at'):
            point_id = str(evt.point_eau_id)
            if point_id not in derniers_evenements_coupure:
                derniers_evenements_coupure[point_id] = evt

        points_data = []
        for pe in points_eau:
            dernier_evenement = derniers_evenements.get(str(pe.id))
            est_coupe = bool(
                (dernier_evenement and dernier_evenement.type_evenement == 'coupure')
                or pe.datearretbranchement
            )
            date_arret = None
            if dernier_evenement and dernier_evenement.type_evenement == 'coupure' and dernier_evenement.date_evenement:
                date_arret = dernier_evenement.date_evenement.strftime('%Y-%m-%d')
            elif pe.datearretbranchement:
                date_arret = pe.datearretbranchement.strftime('%Y-%m-%d')
            points_data.append({
                'id': str(pe.id),
                'code': pe.code_point_eau,
                'nom': pe.nomabonne or '',
                'display': f"{pe.code_point_eau} - {pe.nomabonne}" if pe.nomabonne else pe.code_point_eau,
                'point_coupe': est_coupe,
                'est_coupe_actuellement': est_coupe,
                'date_arret_branchement': date_arret
            })

        return JsonResponse({
            'success': True,
            'points_eau': points_data,
            'ouvrage_nom': ouvrage.nom_ouvrage
        })
    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_paiements_non_payes_par_ouvrage(request):
    """
    API pour récupérer les paiements forfaitaires non payés d'un ouvrage spécifique
    Utilisé pour le modal de la section 2 (recoupement inverse)
    """
    ouvrage_nom = request.GET.get('ouvrage_nom', '')

    if not ouvrage_nom:
        return JsonResponse({
            'success': False,
            'error': 'Paramètre ouvrage_nom requis'
        }, status=400)

    try:
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        # Chercher l'ouvrage par nom
        from apps.organization.models import Ouvrage
        ouvrage = Ouvrage.objects.filter(nom_ouvrage__iexact=ouvrage_nom, id__in=allowed_ouvrage_ids).first()

        if not ouvrage:
            return JsonResponse({
                'success': False,
                'error': f'Ouvrage "{ouvrage_nom}" non trouvé'
            }, status=404)

        # Récupérer les paiements non payés de cet ouvrage
        paiements_non_payes = PaiementForfaitaire.objects.filter(
            point_eau__ouvrage=ouvrage,
                point_eau__ouvrage_id__in=allowed_ouvrage_ids,
            paye=False
        ).select_related('point_eau', 'point_eau__ouvrage').order_by('date_facture')

        # Formater les données
        paiements_data = []
        for p in paiements_non_payes:
            paiements_data.append({
                'id': str(p.id),
                'point_eau_code': p.point_eau.code_point_eau if p.point_eau else None,
                'point_eau_nom': p.point_eau.nomabonne if p.point_eau else None,
                'date_facture': p.date_facture.strftime('%d/%m/%Y') if p.date_facture else None,
                'quantite': float(p.quantite) if p.quantite else 0,
                'prix_unitaire': float(p.prix_unitaire) if p.prix_unitaire else 0,
                'montant': float(p.montant) if p.montant else 0,
                'paye': p.paye,
                'numeroDiameX': p.numeroDiameX,
                'baseDiameX': p.baseDiameX,
            })

        return JsonResponse({
            'success': True,
            'paiements_non_payes': paiements_data,
            'total': len(paiements_data),
            'ouvrage_nom': ouvrage.nom_ouvrage
        })

    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_points_eau_par_ouvrage(request):
    """
    API pour récupérer les points d'eau d'un ouvrage
    Utilisé pour peupler le dropdown lors de l'ajout d'un paiement dans le modal inverse
    """
    ouvrage_id = (request.GET.get('ouvrage_id') or '').strip()
    ouvrage_nom = request.GET.get('ouvrage_nom', '')

    if not ouvrage_id and not ouvrage_nom:
        return JsonResponse({
            'success': False,
            'error': 'Paramètre ouvrage_id ou ouvrage_nom requis'
        }, status=400)

    try:
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        from apps.organization.models import Ouvrage

        ouvrage = None
        if ouvrage_id:
            ouvrage = Ouvrage.objects.filter(
                id=ouvrage_id,
                id__in=allowed_ouvrage_ids
            ).first()

        if not ouvrage and ouvrage_nom:
            # Fallback par nom (historique)
            ouvrage = Ouvrage.objects.filter(
                nom_ouvrage__iexact=ouvrage_nom,
                id__in=allowed_ouvrage_ids
            ).first()

        if not ouvrage:
            return JsonResponse({
                'success': False,
                'error': 'Ouvrage introuvable'
            }, status=404)

        # Récupérer les points d'eau forfaitaires de cet ouvrage
        points_eau = PointEau.objects.filter(
            ouvrage=ouvrage,
            ouvrage_id__in=allowed_ouvrage_ids
        ).filter(
            Q(tarifforfaitaire__isnull=False, tarifforfaitaire__gt=0)
            | Q(paiements_forfaitaires__isnull=False)
            | Q(coupures_eau__isnull=False)
        ).distinct().order_by('code_point_eau')

        # Formater les données
        points_data = []
        for pe in points_eau:
            dernier_evenement = derniers_evenements_coupure.get(str(pe.id))
            est_coupe = bool(
                (dernier_evenement and dernier_evenement.type_evenement == 'coupure')
                or pe.datearretbranchement
            )
            date_arret = None
            if dernier_evenement and dernier_evenement.type_evenement == 'coupure' and dernier_evenement.date_evenement:
                date_arret = dernier_evenement.date_evenement.strftime('%Y-%m-%d')
            elif pe.datearretbranchement:
                date_arret = pe.datearretbranchement.strftime('%Y-%m-%d')
            points_data.append({
                'id': str(pe.id),
                'code': pe.code_point_eau,
                'nom': pe.nomabonne or '',
                'tarif_forfaitaire': float(pe.tarifforfaitaire) if pe.tarifforfaitaire else 0,
                'display': f"{pe.code_point_eau} - {pe.nomabonne}" if pe.nomabonne else pe.code_point_eau,
                'point_coupe': est_coupe,
                'est_coupe_actuellement': est_coupe,
                'date_arret_branchement': date_arret
            })

        return JsonResponse({
            'success': True,
            'points_eau': points_data,
            'ouvrage_id': str(ouvrage.id),
            'ouvrage_nom': ouvrage.nom_ouvrage
        })

    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


@login_required
@require_http_methods(['POST'])
def supprimer_paiement_forfaitaire(request, paiement_id):
    """
    API pour supprimer un paiement forfaitaire.

    Args:
        paiement_id: UUID du paiement à supprimer

    Returns:
        JSON avec success=True/False et message
    """

    try:
        access_denied_response = _ensure_forfaitaire_facture_write_access(request.user)
        if access_denied_response:
            return access_denied_response
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        # Récupérer le paiement
        paiement = PaiementForfaitaire.objects.get(id=paiement_id, point_eau__ouvrage_id__in=allowed_ouvrage_ids)

        # Verrouillage: une ligne déjà pointée (numero/base présents) ne peut plus être supprimée
        if (paiement.numeroDiameX or '').strip() and (paiement.baseDiameX or '').strip():
            return JsonResponse({
                'success': False,
                'error': 'Cette facture est déjà pointée et ne peut pas être supprimée.'
            }, status=400)

        # Stocker les infos pour le message de confirmation
        point_eau_nom = paiement.point_eau.code_point_eau if paiement.point_eau else 'Inconnu'
        date_paiement = paiement.date_paiement.strftime('%d/%m/%Y') if paiement.date_paiement else 'N/A'

        # Supprimer le paiement
        paiement.delete()

        return JsonResponse({
            'success': True,
            'message': f'Paiement du {date_paiement} pour {point_eau_nom} supprimé avec succès.'
        })

    except PaiementForfaitaire.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Paiement introuvable.'
        }, status=404)

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur lors de la suppression : {str(e)}'
        }, status=500)
