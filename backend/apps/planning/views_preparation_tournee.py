"""
API de preparation de tournee hors ligne : fournit en un seul appel toutes
les donnees de reference qu'un agent terrain doit precharger avant de
partir sans reseau (fiche point d'eau + historique, planning a venir,
reparations echues, tarifs en lecture seule).

Reutilise strictement des logiques deja existantes ailleurs dans le
projet - aucune nouvelle logique metier n'est introduite ici :
- Plannings : meme queryset que views_modal_bienvenue.api_planning_7_jours.
- Reparations : apps.messaging.repair_reminder (source Planning reelle,
  PAS apps.planning.models_reparations.Reparation qui est vide en
  production - erreur deja corrigee dans le moteur de relance email).
- Points d'eau : meme structure que views_releves.api_points_eau_par_ouvrage.
- Historique releves : meme structure que views_releves.api_point_eau_details,
  limitee a 3 releves par point d'eau (prechargement, pas consultation fine).
- Tarifs : TarifVolumetrique + TarifVolumetriqueTranche (le modele reel
  utilise par le moteur de calcul serveur, cf. views_facturation.
  calculer_montant_releve) - DISPLAY-ONLY, jamais utilise pour recalculer
  un montant cote client (le calcul reste impossible a dupliquer hors
  ligne, cf. moteur de tranches tarifaires).
"""
import base64
import binascii
import hashlib
import json
import logging
import unicodedata
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from apps.core.views_mobile_auth import mobile_auth_required
from django.db import transaction
from django.core.exceptions import ValidationError
from django.db.models import Avg, Count, Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

import pytz

from apps.billing.models import (
    CompteurTete, ConsoCarteSociale, PointEau, Releve, ReleveCompteurTete,
    TarifVolumetrique,
)
from apps.core.search_mobile_formatting import point_type_pictogram
from apps.infrastructure.models import CarteSociale, EquipementConstitutif
from apps.messaging.monthly_billing_reminder import date_actuelle_madagascar
from apps.ouvrages.models import TarifVolumetriqueTranche
from apps.planning.models import DebitSourceMesure, Planning
from apps.planning import terrain_points
from apps.planning.doublons_reparations import calculer_doublons_securise
from apps.planning.reparation_composants import catalogue_composants_par_type, regles_fiche, serialize_repair_target
from apps.planning.repair_classification import get_repair_fiches_queryset, get_mobile_repair_fiches_queryset
from apps.planning.views_reparations_apis import (
    _get_scoped_ouvrage_ids_for_request,
    _get_selected_organisation_id,
    _parse_planning_photo_payload,
    _serialize_planning_photo_payload,
)
from apps.planning.views_reparations import _get_scoped_ouvrage_ids
from apps.planning.views_simple import _get_planning_scope, is_jour_ferie_malgache
from apps.employees.models import Employe, EmployeOuvrages
from apps.employees.models_evaluation import FichePoste
from apps.employees.permissions import is_directeur_poste
from apps.messaging.repair_sync import ensure_repair_conversation
from apps.billing.views_releves import (
    RELEVES_MODALITES_AUTORISEES,
    _get_allowed_ouvrage_ids,
    _is_directeur_user,
    organisation_ticket_data_ouvrage,
)
from apps.organization.scoping import (
    get_user_accessible_gestionnaire_ids,
    get_active_subordinate_employe_ids,
)

NB_POINTS_EAU_AVERTISSEMENT = 300
NB_RELEVES_HISTORIQUE_MAX = 3
NB_FACTURES_MOBILE_MAX = 100
NB_MESURES_TERRAIN_MAX = 20
FREQUENCE_DEBIT_TERRAIN_JOURS = 90
POINT_EAU_COUPE_EXCLUSION_DAYS = 90

TZ_MADAGASCAR = pytz.timezone('Indian/Antananarivo')
logger = logging.getLogger(__name__)


def _ouvrage_age_annees(ouvrage, reference_date=None):
    """Age en annees entieres: annee courante moins annee de realisation."""
    reference_date = reference_date or date_actuelle_madagascar()
    year = getattr(ouvrage, 'annee_realisation', None) or getattr(
        ouvrage, 'annee_realisation_avant', None
    )
    try:
        year = int(year)
    except (TypeError, ValueError):
        return None
    if year <= 0 or year > reference_date.year:
        return None
    return reference_date.year - year


def _mobile_employes_queryset(user):
    """Employes actifs de la meme base que l'utilisateur mobile."""
    employe = getattr(user, 'employe', None)
    queryset = Employe.objects.filter(date_debauchage__isnull=True).select_related('base')
    if not employe or not employe.base_id:
        return queryset.none()
    return queryset.filter(base_id=employe.base_id).order_by('nom_employe')


def _mobile_plannings_queryset(user):
    """Meme perimetre que les cartes planning fournies au mobile.

    CRITICAL (hierarchie) : le scope 'base' doit inclure les subordonnes
    actifs du responsable (meme moteur que Terrain/Reparations/Releves via
    apps.organization.scoping.get_active_subordinate_employe_ids), sinon un
    responsable ne voit jamais le planning de son equipe - seulement le sien.
    """
    employe = getattr(user, 'employe', None)
    scope = _get_planning_scope(user)
    queryset = Planning.objects.all()
    if scope == 'all':
        return queryset
    if not employe or scope == 'none':
        return queryset.none()
    if scope == 'organisation':
        organisation_id = getattr(getattr(employe, 'base', None), 'organisation_id', None)
        return queryset.filter(employe__base__organisation_id=organisation_id) if organisation_id else queryset.none()
    if not employe.base_id:
        return queryset.none()
    employe_ids = get_active_subordinate_employe_ids(employe.id)
    return queryset.filter(employe__base_id=employe.base_id).filter(
        Q(employe_id__in=employe_ids) | Q(planning_employees__employee_id__in=employe_ids)
    ).distinct()


def _request_payload(request):
    if request.content_type and 'application/json' in request.content_type:
        try:
            return json.loads(request.body.decode('utf-8') or '{}')
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
    return request.POST.dict()


def _parse_mobile_date(value):
    try:
        parsed = datetime.strptime(str(value or '').strip(), '%Y-%m-%d')
    except ValueError:
        return None
    return TZ_MADAGASCAR.localize(parsed.replace(hour=8))


def _jours_semaine_fr(date_obj):
    jours = {0: 'Lundi', 1: 'Mardi', 2: 'Mercredi', 3: 'Jeudi', 4: 'Vendredi', 5: 'Samedi', 6: 'Dimanche'}
    return jours.get(date_obj.weekday(), '') if date_obj else ''


def _nom_employe(employe):
    if not employe:
        return ''
    return employe.surnom or employe.prenom or employe.nom_employe or ''


def _geographies_par_ouvrage(ouvrage_ids):
    """Premiere implantation geographique connue de chaque ouvrage."""
    points = PointEau.objects.filter(
        ouvrage_id__in=set(filter(None, ouvrage_ids)),
    ).select_related(
        'parcelle__village__fokontany__commune__district__region'
    ).order_by('ouvrage_id', 'id')
    geographies = {}
    for point in points:
        if point.ouvrage_id in geographies:
            continue
        parcelle = getattr(point, 'parcelle', None)
        village = getattr(parcelle, 'village', None)
        fokontany = getattr(village, 'fokontany', None)
        commune_obj = getattr(fokontany, 'commune', None)
        district = getattr(commune_obj, 'district', None)
        region = getattr(district, 'region', None)
        geographies[point.ouvrage_id] = {
            'commune_id': str(commune_obj.id) if commune_obj else '',
            'commune': getattr(commune_obj, 'nom_commune', '') or '',
            'district_id': str(district.id) if district else '',
            'district': getattr(district, 'nom_district', '') or '',
            'region_id': str(region.id) if region else '',
            'region': getattr(region, 'nom_region', '') or '',
        }
    return geographies


def _employes_planning(planning):
    employes = []
    vus = set()
    candidats = [planning.employe] + [
        relation.employee for relation in planning.planning_employees.all()
        if relation.employee
    ]
    for employe in candidats:
        if not employe or employe.id in vus:
            continue
        vus.add(employe.id)
        employes.append({'id': str(employe.id), 'nom': _nom_employe(employe)})
    return employes


def _serialiser_plannings(user, employe, aujourd_hui, date_fin):
    """Version mobile des cartes de /plannings/agenda/."""
    aujourd_hui_dt = TZ_MADAGASCAR.localize(datetime.combine(aujourd_hui, datetime.min.time()))
    date_fin_dt = TZ_MADAGASCAR.localize(datetime.combine(date_fin, datetime.max.time()))

    plannings = Planning.objects.filter(
        date__gte=aujourd_hui_dt, date__lte=date_fin_dt,
    ).select_related(
        'fiche_poste', 'fiche_poste__type_activites', 'type_activite',
        'ouvrage', 'employe', 'employe__base',
    ).prefetch_related(
        'planning_employees__employee', 'details', 'bons_livraison',
        'paiements_forfaitaires', 'composants_equipement', 'composants_point_eau',
    )
    scope = _get_planning_scope(user)
    if scope == 'none':
        return []
    employe_ids_hierarchie = None
    if scope == 'base':
        if not employe.base_id:
            return []
        plannings = plannings.filter(employe__base_id=employe.base_id)
        # CRITICAL (hierarchie) : inclure les subordonnes actifs du
        # responsable (meme moteur que Terrain/Reparations/Releves), sinon
        # un responsable ne voit jamais le planning de son equipe.
        employe_ids_hierarchie = get_active_subordinate_employe_ids(employe.id, aujourd_hui)
    elif scope == 'organisation':
        organisation_id = getattr(getattr(employe, 'base', None), 'organisation_id', None)
        if not organisation_id:
            return []
        plannings = plannings.filter(employe__base__organisation_id=organisation_id)
    if scope not in ('all', 'organisation'):
        ids = employe_ids_hierarchie or {employe.id}
        plannings = plannings.filter(
            Q(employe_id__in=ids) | Q(planning_employees__employee_id__in=ids)
        )
    plannings = list(plannings.distinct().order_by('date'))
    geographies = _geographies_par_ouvrage(planning.ouvrage_id for planning in plannings)
    doublons = calculer_doublons_securise([planning.id for planning in plannings])

    resultats = []
    for planning in plannings:
        date_mg = planning.date.astimezone(TZ_MADAGASCAR).date() if planning.date else None
        participants = []
        for relation in planning.planning_employees.all():
            participant = relation.employee
            if participant:
                participants.append(_nom_employe(participant))
        geographie = geographies.get(planning.ouvrage_id, {})
        employes = _employes_planning(planning)
        details = list(planning.details.all())
        cible = serialize_repair_target(planning)
        resultats.append({
            'id': str(planning.id),
            'date': date_mg.strftime('%Y-%m-%d') if date_mg else None,
            'date_display': date_mg.strftime('%d/%m/%Y') if date_mg else '',
            'jour_semaine': _jours_semaine_fr(date_mg),
            'fiche_poste': planning.activite_display,
            'fiche_poste_id': str(planning.fiche_poste_id) if planning.fiche_poste_id else '',
            'doublons': doublons.get(str(planning.id)),
            'type_activite': (
                getattr(getattr(planning.fiche_poste, 'type_activites', None), 'nomtype', '')
                or getattr(planning.type_activite, 'nomtype', '') or ''
            ),
            'ouvrage_id': str(planning.ouvrage_id) if planning.ouvrage_id else None,
            'ouvrage_nom': planning.ouvrage.nom_ouvrage if planning.ouvrage else '',
            **geographie,
            'employes': employes,
            'employe_id': str(planning.employe_id) if planning.employe_id else '',
            'employe': _nom_employe(planning.employe),
            'participants': ', '.join(filter(None, participants)),
            'valide': planning.estvalide,
            'statut_code': planning.statut or 'en_cours',
            'statut': planning.get_statut_display() if planning.statut else ('Validé' if planning.estvalide else 'En cours'),
            'jour_ferie': is_jour_ferie_malgache(date_mg) if date_mg else False,
            'weekend': date_mg.weekday() >= 5 if date_mg else False,
            'preuve_obligatoire': bool(getattr(planning.fiche_poste, 'preuve_obligatoire', False)),
            'preuve_type': getattr(planning.fiche_poste, 'preuve_type', '') or '',
            'nb_avances': sum(1 for detail in details if not detail.livraison and not hasattr(detail, 'deplacement')),
            'nb_deplacements': sum(1 for detail in details if hasattr(detail, 'deplacement')),
            'nb_livraisons': planning.bons_livraison.count(),
            'nb_paiements': planning.paiements_forfaitaires.count(),
            'remarque': planning.remarque or '',
            # Cible et composants concernés (comme les réparations), pour le formulaire mobile.
            'point_eau_id': cible['cible_point_eau_id'] or '',
            'equipement_id': cible['cible_equipement_id'] or '',
            'composants': cible['composants'],
            'composants_ids': cible['composants_ids'],
        })
    return resultats


def _serialiser_reparations(request, date_reference):
    """Reparations consultables, avec indication du perimetre utilisateur."""
    organisation_id, ouvrages_ids = _get_scoped_ouvrage_ids_for_request(request)
    ouvrages_ids = set(ouvrages_ids)
    ouvrages_accessibles_ids = _get_scoped_ouvrage_ids(
        organisation_id,
        get_user_accessible_gestionnaire_ids(request.user),
        annee=date_reference.year,
    )
    fiche_ids = list(get_mobile_repair_fiches_queryset().values_list('id', flat=True))
    reparations = list(Planning.objects.filter(
        ouvrage_id__in=ouvrages_accessibles_ids,
        fiche_poste_id__in=fiche_ids,
        date__year=date_reference.year,
    ).select_related(
        'ouvrage', 'fiche_poste', 'fiche_poste__type_activites', 'employe'
    ).prefetch_related(
        'planning_employees__employee', 'details', 'bons_livraison',
        'composants_equipement', 'composants_point_eau',
    ).order_by('-date'))
    geographies = _geographies_par_ouvrage(reparation.ouvrage_id for reparation in reparations)
    doublons = calculer_doublons_securise([reparation.id for reparation in reparations])
    resultats = []
    for reparation in reparations:
        date_mg = reparation.date.astimezone(TZ_MADAGASCAR).date() if reparation.date else None
        jours_retard = max(0, (date_reference - date_mg).days) if date_mg else 0
        statut = 'Validée' if reparation.estvalide else ('Planifiée' if date_mg and date_mg > date_reference else 'En cours')
        participants = [
            relation.employee.surnom or relation.employee.prenom or relation.employee.nom_employe or ''
            for relation in reparation.planning_employees.all() if relation.employee
        ]
        geographie = geographies.get(reparation.ouvrage_id, {})
        employes = _employes_planning(reparation)
        cible = serialize_repair_target(reparation)
        details = list(reparation.details.all())
        resultats.append({
            'id': str(reparation.id),
            'ouvrage_id': str(reparation.ouvrage_id),
            'ouvrage_nom': reparation.ouvrage.nom_ouvrage,
            'titre': reparation.activite_display,
            'fiche_poste_id': str(reparation.fiche_poste_id) if reparation.fiche_poste_id else '',
            'type_activite': getattr(getattr(reparation.fiche_poste, 'type_activites', None), 'nomtype', '') or '',
            'date_prevue': date_mg.isoformat() if date_mg else None,
            'date_prevue_display': date_mg.strftime('%d/%m/%Y') if date_mg else '',
            'jours_retard': jours_retard,
            'priorite': reparation.get_priorite_suivi_display() if reparation.priorite_suivi else 'Normale',
            'priorite_code': reparation.priorite_suivi or 'normale',
            'statut': statut,
            'statut_code': reparation.statut or 'en_cours',
            'terminee': bool(reparation.estvalide),
            'hors_perimetre': reparation.ouvrage_id not in ouvrages_ids,
            **geographie,
            'employes': employes,
            'employe_id': str(reparation.employe_id) if reparation.employe_id else '',
            'assigne_a': _nom_employe(reparation.employe),
            'participants': ', '.join(filter(None, participants)),
            'remarque': reparation.remarque or '',
            'bilan': reparation.bilan or '',
            'suite_a_donner': reparation.suiteadonner or '',
            'nb_details': len(details),
            'nb_livraisons': reparation.bons_livraison.count(),
            'nb_photos': len(_parse_planning_photo_payload(reparation.photo)),
            # Cible : celle enregistree, sinon deduite du materiel saisi (anciennes reparations)
            'point_eau_id': cible['cible_point_eau_id']
                or next((str(d.point_eau_id) for d in details if d.point_eau_id), ''),
            'equipement_id': cible['cible_equipement_id']
                or next((str(d.equipement_constitutif_id) for d in details if d.equipement_constitutif_id), ''),
            'composants': cible['composants'],
            'composants_ids': cible['composants_ids'],
            'doublons': doublons.get(str(reparation.id)),
        })
    return resultats


def _serialiser_points_eau_et_tarifs(ouvrage):
    """Meme structure que views_releves.api_points_eau_par_ouvrage, avec
    historique limite (prechargement, pas consultation fine)."""
    points_eau = PointEau.objects.filter(
        ouvrage=ouvrage
    ).select_related('type_point_eau', 'parcelle__village')

    points_eau_list = []
    today = date_actuelle_madagascar()
    long_cutoff = today - timedelta(days=POINT_EAU_COUPE_EXCLUSION_DAYS)

    # Ticket 80 mm hors ligne : moyenne de consommation (règle ±50 %) et
    # impayés antérieurs, mêmes critères que billing.api_calculer_facture_terrain.
    # Deux requêtes par ouvrage, pas une par point d'eau.
    stats_consommation = {
        str(row['point_eau_id']): row
        for row in Releve.objects.filter(
            point_eau__ouvrage=ouvrage, consommation__isnull=False, consommation__gt=0,
        ).values('point_eau_id').annotate(moyenne=Avg('consommation'), nb=Count('id'))
    }
    impayes_par_point = {}
    for row in Releve.objects.filter(
        point_eau__ouvrage=ouvrage, montant__isnull=False, facture_imprimee=True,
        numeroDiameX__isnull=True,
    ).order_by('datereleve').values('point_eau_id', 'datereleve', 'volume_facture', 'montant'):
        impayes_par_point.setdefault(str(row['point_eau_id']), []).append({
            'date_releve': row['datereleve'].strftime('%Y-%m-%d'),
            'volume_facture': float(row['volume_facture'] or 0),
            'montant': float(row['montant']),
        })

    # Alertes « BP déguisé » (kiosque consommant moins de 10 m³/mois) : une seule passe par ouvrage.
    # Une erreur ici ne doit jamais empêcher l'envoi des points d'eau à l'agent.
    try:
        from apps.planning.views_analyse_consommation import alertes_bp_deguises_pour_ouvrage
        alertes_bp = alertes_bp_deguises_pour_ouvrage(ouvrage.id)
    except Exception:
        alertes_bp = {}

    for pe in points_eau:
        cut_date = pe.datearretbranchement
        if isinstance(cut_date, datetime):
            cut_date = (
                timezone.localtime(cut_date).date()
                if timezone.is_aware(cut_date) else cut_date.date()
            )
        if cut_date and cut_date < long_cutoff:
            continue

        dernier_releve = Releve.objects.filter(point_eau_id=pe.id).order_by('-datereleve').first()
        historique_qs = Releve.objects.filter(point_eau_id=pe.id).order_by('-datereleve')[:NB_RELEVES_HISTORIQUE_MAX]

        type_nom = (pe.type_point_eau.nom_type if pe.type_point_eau else '') or ''

        # Cartes sociales préchargées (kiosques uniquement, comme l'étape 3 du
        # workflow web /facturation/releves/). Les bidons du dernier relevé
        # servent de valeur par défaut. Permet la saisie 100 % hors ligne.
        cartes_sociales_list = []
        if 'KIOSQUE' in type_nom.upper():
            for cs in CarteSociale.objects.filter(point_eau_id=pe.id, statut='active'):
                quantite_bidons = 0
                if dernier_releve:
                    conso = ConsoCarteSociale.objects.filter(
                        releve=dernier_releve, carte_sociale=cs
                    ).first()
                    if conso:
                        quantite_bidons = conso.quantite_bidons
                cartes_sociales_list.append({
                    'id': str(cs.id),
                    'numero_carte': cs.numero_carte or '',
                    'beneficiaire': cs.nom_beneficiaire or 'N/A',
                    'quantite_bidons': quantite_bidons,
                    'volume_total': round(
                        quantite_bidons * ConsoCarteSociale.VOLUME_BIDON_LITRES / 1000, 3
                    ),
                })

        points_eau_list.append({
            'id': str(pe.id),
            'code': pe.code_point_eau or f'PE-{str(pe.id)[:8]}',
            'nom': pe.nomabonne or 'N/A',
            'village': pe.parcelle.village.nom_village if (pe.parcelle and pe.parcelle.village) else 'N/A',
            # Formulaire de relevé mobile : filtre en cascade Parcelle > Point d'eau
            # et saisie du téléphone de l'abonné s'il manque.
            'parcelle_id': str(pe.parcelle_id) if pe.parcelle_id else '',
            'parcelle': (pe.parcelle.reference_parcelle or '') if pe.parcelle else '',
            'telephone': pe.numeroteleph or pe.contactabonne or '',
            'updated_at': pe.updatedat.isoformat() if pe.updatedat else '',
            'type': type_nom or 'N/A',
            'est_institutionnel': bool(pe.estbranchementinstitutionnel),
            'type_pictogram': point_type_pictogram(type_nom),
            'cartes_sociales': cartes_sociales_list,
            'idxls': pe.idxls or '',
            'has_coordinates': pe.latitude is not None and pe.longitude is not None,
            'latitude': pe.latitude,
            'longitude': pe.longitude,
            'has_photo': bool(pe.photos),
            'a_relever': True,
            'alerte_bp_deguise': alertes_bp.get(str(pe.id)),
            'releve_mois_courant': bool(
                dernier_releve
                and dernier_releve.datereleve.year == today.year
                and dernier_releve.datereleve.month == today.month
            ),
            'dernier_releve': {
                'nouvel_index': float(dernier_releve.nouvelindex),
                'date_releve': dernier_releve.datereleve.strftime('%Y-%m-%d'),
            } if dernier_releve else None,
            'moyenne_consommation': float(
                (stats_consommation.get(str(pe.id)) or {}).get('moyenne') or 0
            ),
            'nb_releves_precedents': (stats_consommation.get(str(pe.id)) or {}).get('nb', 0),
            'impayes': impayes_par_point.get(str(pe.id), []),
            'historique_recent': [
                {
                    'date_releve': rel.datereleve.strftime('%Y-%m-%d'),
                    'numero_facture': rel.numero_facture or '',
                    'ancien_index': float(rel.ancienindex),
                    'nouvel_index': float(rel.nouvelindex),
                    'consommation': float(rel.consommation),
                    'montant': float(rel.montant) if rel.montant else None,
                    'pointee': rel.est_paye,
                    'numero_diamex': rel.numeroDiameX or '',
                }
                for rel in historique_qs
            ],
        })

    tarifs_list = []
    # Tarifs ordinaires d'abord : une appli plus ancienne, qui retient le premier tarif du type,
    # ne tombe ainsi jamais sur un tarif institutionnel pour un point ordinaire.
    tarifs = TarifVolumetrique.objects.filter(
        ouvrage=ouvrage, datefintarif__isnull=True, actif=True,
    ).select_related('type_point_eau').prefetch_related('tranches_volumetriques').order_by('institutionnel')
    for tarif in tarifs:
        tranches = tarif.tranches_volumetriques.order_by('tranchesuperieur')
        tarifs_list.append({
            'type_point_eau': tarif.type_point_eau.nom_type if tarif.type_point_eau else 'N/A',
            'institutionnel': tarif.institutionnel,
            'prixabonnement': tarif.prixabonnement,
            'volume_minimum_facture': float(tarif.volume_minimum_facture) if tarif.volume_minimum_facture else 0,
            'tranches': [
                {'tranchesuperieur': t.tranchesuperieur, 'tarif': t.tarif} for t in tranches
            ],
        })

    return points_eau_list, tarifs_list


def _normaliser_terrain(value):
    return ' '.join(
        unicodedata.normalize('NFKD', str(value or ''))
        .encode('ascii', errors='ignore')
        .decode('ascii')
        .lower()
        .split()
    )


def _subscriber_name_expected(point):
    """Les points publics (BF, kiosque...) ne sont pas penalises."""
    type_name = _normaliser_terrain(
        getattr(getattr(point, 'type_point_eau', None), 'nom_type', '')
    )
    return (
        'branchement prive' in type_name
        or type_name == 'bp'
        or type_name.startswith('bp ')
    )


def _has_usable_photo(value):
    if isinstance(value, (list, tuple, dict)):
        return bool(value)
    raw = str(value or '').strip().lower()
    return raw not in {'', '[]', '{}', 'null', 'none'}


def _photo_has_local_uuid(value, local_uuid):
    """Reconnaît un upload déjà traité après perte de la réponse HTTP."""
    if not local_uuid:
        return False
    photos = value if isinstance(value, list) else [value] if isinstance(value, dict) else []
    return any(str(photo.get('local_uuid') or '') == str(local_uuid) for photo in photos)


MAX_MOBILE_PHOTOS = 10


def _append_mobile_photo(existing, photo):
    """Ajoute une photo terrain à la liste existante (on garde les 10 plus récentes).

    Avant, chaque envoi remplaçait toute la liste : la 2e photo d'une même fiche
    écrasait la 1re. Une photo ajoutée ne peut pas écraser le travail d'un autre,
    donc elle n'est plus soumise au contrôle de conflit de version.
    """
    if isinstance(existing, list):
        photos = list(existing)
    elif isinstance(existing, dict) and existing:
        photos = [existing]
    else:
        photos = []
    photos.append(photo)
    return photos[-MAX_MOBILE_PHOTOS:]


def _point_update_matches_payload(point, payload):
    """Vrai lorsque le retry contient déjà exactement la valeur serveur."""
    comparisons = []
    if 'subscriber_name' in payload:
        comparisons.append((point.nomabonne or '') == str(payload.get('subscriber_name') or '').strip()[:255])
    if 'telephone' in payload:
        comparisons.append((point.numeroteleph or '') == str(payload.get('telephone') or '').strip()[:20])
    if 'latitude' in payload or 'longitude' in payload:
        try:
            comparisons.append(
                point.latitude is not None
                and point.longitude is not None
                and abs(float(point.latitude) - float(payload.get('latitude'))) < 0.0000001
                and abs(float(point.longitude) - float(payload.get('longitude'))) < 0.0000001
            )
        except (TypeError, ValueError):
            comparisons.append(False)
    return bool(comparisons) and all(comparisons)


def _point_server_value(point):
    return {
        'subscriber_name': point.nomabonne or '',
        'telephone': point.numeroteleph or '',
        'latitude': point.latitude,
        'longitude': point.longitude,
        'has_coordinates': point.latitude is not None and point.longitude is not None,
        'has_photo': _has_usable_photo(point.photos),
    }


def _force_sync_requested(payload):
    """Accepte les valeurs usuelles envoyees par les clients mobiles."""
    return str(payload.get('force_sync') or '').strip().lower() in {
        '1', 'true', 'yes', 'oui', 'on',
    }


def _get_direct_ouvrage_ids_for_request(request):
    """Sous-ensemble de _get_scoped_ouvrage_ids_for_request restreint a la
    hierarchie stricte de l'utilisateur : lui-meme + ses subordonnes actifs
    (EmployeOuvrages), SANS l'elargissement "meme base" que
    _apply_employe_hierarchy_ouvrage_scope applique aux roles de support
    (caissiere, RAF, assistant admin...). C'est justement cet elargissement
    "meme base" que le bouton "Elargir" du mobile doit reveler - pas une
    restriction plus stricte que la hierarchie (un responsable sans ouvrage
    en propre mais avec des subordonnes actifs doit voir leurs ouvrages ici).
    Sert de perimetre par defaut a l'ecran Terrain mobile.
    """
    user = request.user
    gestionnaire_ids = get_user_accessible_gestionnaire_ids(user)
    organisation_id = _get_selected_organisation_id(request, gestionnaire_ids)

    annee_filter = (request.GET.get('annee') or '').strip()
    try:
        annee_int = int(annee_filter) if annee_filter and annee_filter != 'all' else None
    except (TypeError, ValueError):
        annee_int = None

    ouvrage_ids = _get_scoped_ouvrage_ids(organisation_id, gestionnaire_ids, annee=annee_int)

    if getattr(user, 'is_superuser', False) or is_directeur_poste(user):
        return set(ouvrage_ids)

    employe = getattr(user, 'employe', None)
    if not employe:
        return set()

    reference_date = timezone.now().date()
    employe_ids = get_active_subordinate_employe_ids(employe.id, reference_date)
    direct_ids = set(
        EmployeOuvrages.objects.filter(
            employe_id__in=employe_ids,
            date_debut__lte=reference_date,
        ).filter(
            Q(date_fin__isnull=True) | Q(date_fin__gte=reference_date)
        ).values_list('ouvrage_id', flat=True).distinct()
    )
    return set(ouvrage_ids).intersection(direct_ids)


def _aggregate_terrain_stats(ouvrages_data):
    """Agrege les stats globales terrain a partir d'une liste d'ouvrages
    deja serialises par _serialiser_terrain (meme formule que le calcul
    par ouvrage, reutilisee pour le perimetre direct comme pour l'elargi).
    """
    global_stats = {
        'total_ouvrages': len(ouvrages_data), 'total_points_eau': 0, 'total_equipements': 0,
        'points_sans_coordonnees': 0, 'points_sans_photo': 0,
        'points_sans_nom_abonne': 0, 'equipements_sans_photo': 0,
        'captages_sans_mesure': 0, 'captages_mesure_en_retard': 0,
    }
    nb_points_sujet_nom = 0
    nb_sources = 0
    for ouvrage in ouvrages_data:
        stats = ouvrage['stats']
        points_data = ouvrage['points_eau']
        equipements_data = ouvrage['equipements']
        global_stats['total_points_eau'] += len(points_data)
        global_stats['total_equipements'] += len(equipements_data)
        for key in stats:
            global_stats[key] += stats[key]
        nb_points_sujet_nom += sum(item['subscriber_name_expected'] for item in points_data)
        nb_sources += int(ouvrage['debit_source_applicable'])

    applicable_global = (
        global_stats['total_points_eau'] * 2 + nb_points_sujet_nom
        + global_stats['total_equipements'] + nb_sources
    )
    missing_global = sum(global_stats[key] for key in (
        'points_sans_coordonnees', 'points_sans_photo', 'points_sans_nom_abonne',
        'equipements_sans_photo', 'captages_sans_mesure', 'captages_mesure_en_retard',
    ))
    global_stats['completion_score'] = (
        round(max(0, applicable_global - missing_global) * 100 / applicable_global)
        if applicable_global else 100
    )
    return global_stats


def _serialiser_terrain(request, ouvrage_ids, today, direct_ouvrage_ids=None):
    """Snapshot compact pour le tableau de bord mobile offline.

    Les IDs proviennent exclusivement du scope serveur existant. Les donnees
    sont chargees en lots afin d'eviter un aller-retour SQL par ouvrage.

    `direct_ouvrage_ids` (optionnel) marque, par ouvrage, si l'utilisateur en
    est directement responsable (par opposition au perimetre elargi par
    hierarchie/role de support) : sert au bouton "Elargir" cote mobile.
    """
    from apps.organization.models import Ouvrage

    ouvrage_ids = set(ouvrage_ids)
    direct_ouvrage_ids = ouvrage_ids if direct_ouvrage_ids is None else set(direct_ouvrage_ids)
    ouvrages = list(
        Ouvrage.objects.filter(id__in=ouvrage_ids)
        .select_related('type_ouvrage')
        .order_by('nom_ouvrage')
    )
    geographies = _geographies_par_ouvrage(ouvrage_ids)

    points_by_ouvrage = {ouvrage_id: [] for ouvrage_id in ouvrage_ids}
    point_data_by_id = {}
    points = PointEau.objects.filter(ouvrage_id__in=ouvrage_ids).select_related(
        'type_point_eau', 'parcelle__village'
    ).order_by('ouvrage_id', 'code_point_eau', 'id')
    for point in points:
        expected_name = _subscriber_name_expected(point)
        name = str(point.nomabonne or '').strip()
        normalized_name = _normaliser_terrain(name)
        # Un nom compose uniquement de chiffres (numero de compteur/abonne
        # saisi par erreur dans le champ nom) n'est pas un vrai nom d'abonne :
        # toujours a renseigner tant que le vrai nom n'a pas ete trouve.
        has_name = bool(
            name
            and normalized_name not in {'n/a', 'na', 'inconnu', 'non renseigne'}
            and not normalized_name.replace(' ', '').isdigit()
        )
        point_data = {
            'id': str(point.id),
            'code': point.code_point_eau or f'PE-{str(point.id)[:8]}',
            'nom': name,
            'idxls': str(point.idxls).strip() if point.idxls is not None else '',
            'type': getattr(point.type_point_eau, 'nom_type', '') or '',
            'type_id': str(point.type_point_eau_id) if point.type_point_eau_id else '',
            'village': point.parcelle.village.nom_village if (point.parcelle and point.parcelle.village) else '',
            'subscriber_name_expected': expected_name,
            'has_subscriber_name': (has_name if expected_name else True),
            'telephone': point.numeroteleph or point.contactabonne or '',
            'has_coordinates': point.latitude is not None and point.longitude is not None,
            'latitude': point.latitude,
            'longitude': point.longitude,
            'coordinates_accuracy': None,
            'coordinates_updated_at': point.updatedat.isoformat() if point.updatedat else None,
            'has_photo': _has_usable_photo(point.photos),
            'updated_at': point.updatedat.isoformat() if point.updatedat else None,
            'compteur_tete_id': str(point.compteur_tete_id) if point.compteur_tete_id else '',
            'historique_recent': [],
        }
        points_by_ouvrage.setdefault(point.ouvrage_id, []).append(point_data)
        point_data_by_id[point.id] = point_data

    for reading in Releve.objects.filter(point_eau_id__in=point_data_by_id).order_by(
        'point_eau_id', '-datereleve', '-created_at'
    ):
        bucket = point_data_by_id[reading.point_eau_id]['historique_recent']
        if len(bucket) >= NB_MESURES_TERRAIN_MAX:
            continue
        bucket.append({
            'date': reading.datereleve.isoformat(),
            'ancien_index': float(reading.ancienindex),
            'nouvel_index': float(reading.nouvelindex),
            'consommation': float(reading.consommation),
        })

    equipments_by_ouvrage = {ouvrage_id: [] for ouvrage_id in ouvrage_ids}
    equipments = EquipementConstitutif.objects.filter(ouvrage_id__in=ouvrage_ids).select_related(
        'type_equipement'
    ).order_by('ouvrage_id', 'nom')
    for equipment in equipments:
        equipments_by_ouvrage.setdefault(equipment.ouvrage_id, []).append({
            'id': str(equipment.id),
            'nom': equipment.nom or '',
            'code': equipment.code_equipement or '',
            'type': getattr(equipment.type_equipement, 'nom_type', '') or '',
            'type_id': str(equipment.type_equipement_id) if equipment.type_equipement_id else '',
            'has_photo': bool(equipment.photo_reference_id) or _has_usable_photo(equipment.photos),
            'has_coordinates': equipment.latitude is not None and equipment.longitude is not None,
            'latitude': float(equipment.latitude) if equipment.latitude is not None else None,
            'longitude': float(equipment.longitude) if equipment.longitude is not None else None,
            'updated_at': equipment.updated_at.isoformat() if equipment.updated_at else None,
        })

    # La page Debit source existante ne concerne que les AEPG actifs autorises.
    # On reutilise exactement son queryset puis on l'intersecte avec le scope mobile.
    from apps.planning.views import _get_debit_source_ouvrages_queryset
    source_ids = set(
        _get_debit_source_ouvrages_queryset(request.user)
        .filter(id__in=ouvrage_ids)
        .values_list('id', flat=True)
    )
    measures_by_ouvrage = {ouvrage_id: [] for ouvrage_id in source_ids}
    measures = DebitSourceMesure.objects.filter(ouvrage_id__in=source_ids).order_by(
        'ouvrage_id', '-date_visite', '-created_at'
    )
    for measure in measures:
        bucket = measures_by_ouvrage.setdefault(measure.ouvrage_id, [])
        if len(bucket) >= NB_MESURES_TERRAIN_MAX:
            continue
        bucket.append({
            'id': str(measure.id),
            'date': measure.date_visite.isoformat(),
            'debit_l_s': float(measure.debit_l_s),
            'remarque': measure.remarque or '',
        })

    meters_by_ouvrage = {ouvrage_id: [] for ouvrage_id in ouvrage_ids}
    meters = CompteurTete.objects.filter(ouvrage_id__in=ouvrage_ids).order_by('ouvrage_id', 'numerocompteur')
    meter_ids = [meter.id for meter in meters]
    readings_by_meter = {meter_id: [] for meter_id in meter_ids}
    for reading in ReleveCompteurTete.objects.filter(compteur_tete_id__in=meter_ids).order_by(
        'compteur_tete_id', '-date_releve', '-created_at'
    ):
        bucket = readings_by_meter.setdefault(reading.compteur_tete_id, [])
        if len(bucket) >= NB_MESURES_TERRAIN_MAX:
            continue
        bucket.append({
            'id': str(reading.id),
            'date': reading.date_releve.isoformat(),
            'ancien_index': float(reading.ancien_index),
            'nouvel_index': float(reading.nouvel_index),
            'volume_tete': float(reading.volume_tete),
            'volume_aval': float(reading.volume_aval),
            'ecart_volume': float(reading.ecart_volume),
        })
    for meter in meters:
        meters_by_ouvrage.setdefault(meter.ouvrage_id, []).append({
            'id': str(meter.id),
            'numero': meter.numerocompteur or '',
            'statut': meter.statut or '',
            'index_initial': float(meter.index_initial),
            'historique_recent': readings_by_meter.get(meter.id, []),
        })

    result = []
    for ouvrage in ouvrages:
        points_data = points_by_ouvrage.get(ouvrage.id, [])
        equipments_data = equipments_by_ouvrage.get(ouvrage.id, [])
        source_measures = measures_by_ouvrage.get(ouvrage.id, [])
        is_source = ouvrage.id in source_ids
        last_flow_date = date.fromisoformat(source_measures[0]['date']) if source_measures else None
        flow_due_date = last_flow_date + timedelta(days=FREQUENCE_DEBIT_TERRAIN_JOURS) if last_flow_date else None
        flow_overdue = bool(is_source and flow_due_date and flow_due_date < today)
        stats = {
            'points_sans_coordonnees': sum(not item['has_coordinates'] for item in points_data),
            'points_sans_photo': sum(not item['has_photo'] for item in points_data),
            'points_sans_nom_abonne': sum(not item['has_subscriber_name'] for item in points_data),
            'equipements_sans_photo': sum(not item['has_photo'] for item in equipments_data),
            'captages_sans_mesure': int(is_source and not source_measures),
            'captages_mesure_en_retard': int(flow_overdue),
        }
        applicable = len(points_data) * 2 + sum(item['subscriber_name_expected'] for item in points_data) + len(equipments_data) + int(is_source)
        missing = sum(stats.values())
        score = round(max(0, applicable - missing) * 100 / applicable) if applicable else 100
        result.append({
            'id': str(ouvrage.id),
            'nom': ouvrage.nom_ouvrage,
            'type': getattr(ouvrage.type_ouvrage, 'nom_type_ouvrage', '') or '',
            'annee_realisation': ouvrage.annee_realisation,
            'annee_realisation_avant': ouvrage.annee_realisation_avant,
            'age_annees': _ouvrage_age_annees(ouvrage, today),
            **geographies.get(ouvrage.id, {}),
            'points_eau': points_data,
            'equipements': equipments_data,
            'compteurs_tete': meters_by_ouvrage.get(ouvrage.id, []),
            'debit_source_applicable': is_source,
            'debits_source_recents': source_measures,
            'last_flow_measurement_date': last_flow_date.isoformat() if last_flow_date else None,
            'flow_measurement_due_date': flow_due_date.isoformat() if flow_due_date else None,
            'flow_measurement_overdue': flow_overdue,
            'flow_frequency_days': FREQUENCE_DEBIT_TERRAIN_JOURS if is_source else None,
            'completion_score': score,
            'stats': stats,
            'responsable_direct': ouvrage.id in direct_ouvrage_ids,
        })

    ouvrages_directs = [item for item in result if item['responsable_direct']]
    # Par defaut le mobile affiche le perimetre direct (bouton "Elargir" pour
    # basculer sur stats_perimetre_etendu / la liste complete de `ouvrages`).
    stats_directes = _aggregate_terrain_stats(ouvrages_directs) if ouvrages_directs else _aggregate_terrain_stats([])
    stats_etendues = _aggregate_terrain_stats(result)
    return {
        'flow_frequency_default_days': FREQUENCE_DEBIT_TERRAIN_JOURS,
        'stats': stats_directes,
        'stats_perimetre_etendu': stats_etendues,
        'perimetre_elargi_disponible': len(ouvrages_directs) < len(result),
        'ouvrages': result,
    }


@mobile_auth_required
@require_http_methods(["GET"])
def api_preparer_tournee(request):
    """
    Point d'entree unique du prechargement hors ligne : plannings a venir,
    reparations echues, points d'eau + historique + tarifs des ouvrages
    assignes a l'employe connecte.
    """
    if not hasattr(request.user, 'employe') or not request.user.employe:
        return JsonResponse({'success': False, 'error': "Utilisateur non lié à un employé"}, status=400)

    employe = request.user.employe

    try:
        horizon_jours = int(request.GET.get('horizon_jours', 7))
    except (TypeError, ValueError):
        horizon_jours = 7
    horizon_jours = max(1, min(horizon_jours, 30))

    aujourd_hui = date_actuelle_madagascar()
    date_fin = aujourd_hui + timedelta(days=horizon_jours - 1)

    # Source de verite identique a /facturation/releves/ : uniquement les
    # ouvrages avec une ModaliteGestion active au volume ou mixte, limites
    # a l'organisation et au scope de responsabilite/hierarchie du user.
    ouvrages_ids = set(_get_allowed_ouvrage_ids(
        request.user,
        modalites_paiement=RELEVES_MODALITES_AUTORISEES,
    ))

    plannings = _serialiser_plannings(request.user, employe, aujourd_hui, date_fin)
    reparations = _serialiser_reparations(request, aujourd_hui)

    from apps.organization.models import Ouvrage
    ouvrages_qs = Ouvrage.objects.filter(
        id__in=ouvrages_ids,
        modalites_gestion__modalitepaiement__in=RELEVES_MODALITES_AUTORISEES,
        modalites_gestion__date_fin__isnull=True,
    ).distinct().order_by('nom_ouvrage')

    ouvrages_data = []
    nb_points_eau_total = 0
    for ouvrage in ouvrages_qs:
        points_eau_list, tarifs_list = _serialiser_points_eau_et_tarifs(ouvrage)
        nb_points_eau_total += len(points_eau_list)
        ouvrages_data.append({
            'id': str(ouvrage.id),
            'nom': ouvrage.nom_ouvrage,
            'annee_realisation': ouvrage.annee_realisation,
            'annee_realisation_avant': ouvrage.annee_realisation_avant,
            'age_annees': _ouvrage_age_annees(ouvrage, aujourd_hui),
            'points_eau': points_eau_list,
            'tarifs': tarifs_list,
            'organisation': organisation_ticket_data_ouvrage(ouvrage),
        })

    # References de saisie. Les ouvrages de releve restent volontairement
    # limites au volume/mixte, tandis que les formulaires planning/reparation
    # utilisent tous les ouvrages autorises dans le perimetre de l'utilisateur.
    _, planning_ouvrage_ids = _get_scoped_ouvrage_ids_for_request(request)
    direct_ouvrage_ids = _get_direct_ouvrage_ids_for_request(request)
    terrain_data = _serialiser_terrain(request, planning_ouvrage_ids, aujourd_hui, direct_ouvrage_ids)
    planning_ouvrages = [
        {'id': str(ouvrage.id), 'nom': ouvrage.nom_ouvrage}
        for ouvrage in Ouvrage.objects.filter(id__in=planning_ouvrage_ids).order_by('nom_ouvrage')
    ]
    employes_reference = [
        {'id': str(item.id), 'nom': _nom_employe(item) or item.nom_employe,
         # Employé de l'utilisateur connecté : valeur par défaut des formulaires planning/réparation.
         'moi': item.id == employe.id}
        for item in _mobile_employes_queryset(request.user)
    ]
    repair_fiche_ids = set(get_repair_fiches_queryset().values_list('id', flat=True))
    fiches_queryset = FichePoste.objects.filter(dans_planning=True).select_related('type_activites__groupe').order_by(
        'type_activites__nomtype', 'ordre', 'tache'
    )

    def serialiser_fiche(fiche):
        type_activite = getattr(fiche, 'type_activites', None)
        type_nom = getattr(type_activite, 'nomtype', '') or ''
        groupe = getattr(type_activite, 'groupe', None)
        return {
            'id': str(fiche.id),
            'nom': fiche.tache,
            'type_activite': type_nom,
            'label': f'{type_nom} - {fiche.tache}' if type_nom else fiche.tache,
            # Cascade Groupe > Type d'activite > Activite dans les listes de l'app terrain.
            'type_activite_id': str(type_activite.id) if type_activite else '',
            'groupe_id': str(groupe.id) if groupe else '',
            'groupe': groupe.nom if groupe else '',
            'groupe_ordre': groupe.ordre if groupe else 9999,
            # Cible / composants obligatoires et composants admis (mêmes règles que le serveur).
            'regles': regles_fiche(fiche),
        }

    planning_fiches = [serialiser_fiche(fiche) for fiche in fiches_queryset if fiche.id not in repair_fiche_ids]
    repair_fiches = [
        serialiser_fiche(fiche)
        for fiche in get_mobile_repair_fiches_queryset().select_related('type_activites__groupe').order_by(
            'type_activites__nomtype', 'ordre', 'tache'
        )
    ]

    reponse = {
        'success': True,
        'generated_at': timezone.now().astimezone(TZ_MADAGASCAR).isoformat(),
        'horizon_jours': horizon_jours,
        'scope_source': 'facturation_releves',
        # Le Directeur n'est pas soumis au blocage d'impression (±50 %, non facturé).
        'utilisateur': {'est_directeur': _is_directeur_user(request.user)},
        'plannings': plannings,
        'reparations': reparations,
        'ouvrages': ouvrages_data,
        'terrain': terrain_data,
        'references': {
            'employes': employes_reference,
            'ouvrages': planning_ouvrages,
            'planning_fiches': planning_fiches,
            'repair_fiches': repair_fiches,
            'composants': catalogue_composants_par_type(),
            'statuts': [
                {'id': code, 'nom': label} for code, label in Planning.STATUS_CHOICES
            ],
            'priorites': [
                {'id': code, 'nom': label} for code, label in Planning.PRIORITE_SUIVI_CHOICES
            ],
        },
        'stats': {
            'nb_ouvrages': len(ouvrages_data),
            'nb_points_eau': nb_points_eau_total,
            'nb_plannings': len(plannings),
            'nb_reparations': len(reparations),
        },
    }
    if nb_points_eau_total > NB_POINTS_EAU_AVERTISSEMENT:
        reponse['warning'] = (
            f"Volume important ({nb_points_eau_total} points d'eau), "
            f"le préchargement peut prendre du temps."
        )

    # Version stable du contenu, sans l'horodatage de génération. Le mobile
    # peut ainsi actualiser souvent sans retélécharger un snapshot identique.
    version_payload = {key: value for key, value in reponse.items() if key != 'generated_at'}
    snapshot_version = hashlib.sha256(
        json.dumps(version_payload, sort_keys=True, default=str, separators=(',', ':')).encode('utf-8')
    ).hexdigest()
    reponse['snapshot_version'] = snapshot_version
    if request.GET.get('snapshot_version') == snapshot_version:
        return JsonResponse({
            'success': True,
            'not_modified': True,
            'generated_at': reponse['generated_at'],
            'snapshot_version': snapshot_version,
        })

    return JsonResponse(reponse)


def _serialiser_facture_mobile(releve):
    return {
        'id': str(releve.id),
        'date_releve': releve.datereleve.strftime('%Y-%m-%d'),
        'numero_facture': releve.numero_facture or '',
        'ancien_index': float(releve.ancienindex),
        'nouvel_index': float(releve.nouvelindex),
        'consommation': float(releve.consommation),
        'volume_facture': float(releve.volume_facture) if releve.volume_facture is not None else None,
        'montant': float(releve.montant) if releve.montant is not None else None,
        'statut': releve.get_statut_display() if releve.statut else '',
        'pointee': releve.est_paye,
        'numero_diamex': releve.numeroDiameX or '',
    }


def _nom_abonne_renseigne(name):
    """Meme regle que has_subscriber_name du snapshot : un vrai nom, pas un marqueur."""
    value = str(name or '').strip().lower()
    return bool(value) and value not in {'n/a', 'na', 'inconnu', 'non renseigne'} and not value.replace(' ', '').isdigit()


def _clean_base_version(value):
    """Version locale envoyee par le mobile ; 'null'/'none' (point sans date au
    moment de la synchro) valent « pas de version » et non « version invalide »."""
    raw = str(value or '').strip()
    return '' if raw.lower() in {'null', 'none', 'undefined'} else raw


@mobile_auth_required
@require_http_methods(["GET"])
def api_factures_point_eau_mobile(request, point_eau_id):
    """Dernieres factures d'un point autorise, avec etat de pointage DiameX."""
    allowed_ouvrage_ids = _get_allowed_ouvrage_ids(
        request.user,
        modalites_paiement=RELEVES_MODALITES_AUTORISEES,
    )
    point = PointEau.objects.filter(
        id=point_eau_id,
        ouvrage_id__in=allowed_ouvrage_ids,
    ).select_related('ouvrage').first()
    if not point:
        return JsonResponse({'success': False, 'error': "Point d'eau introuvable ou non autorise"}, status=404)

    factures_qs = Releve.objects.filter(point_eau=point).order_by('-datereleve', '-created_at')
    total = factures_qs.count()
    factures = [_serialiser_facture_mobile(item) for item in factures_qs[:NB_FACTURES_MOBILE_MAX]]
    return JsonResponse({
        'success': True,
        'point_eau': {
            'id': str(point.id),
            'code': point.code_point_eau or '',
            'nom': point.nomabonne or '',
            'ouvrage': point.ouvrage.nom_ouvrage if point.ouvrage else '',
        },
        'factures': factures,
        'total': total,
        'limite': NB_FACTURES_MOBILE_MAX,
        'tronque': total > NB_FACTURES_MOBILE_MAX,
    })


def _save_mobile_planning(request, *, is_repair):
    payload = _request_payload(request)
    if payload is None:
        return JsonResponse({'success': False, 'error': 'Corps JSON invalide'}, status=400)

    planning_id = str(payload.get('id') or '').strip()
    employe_id = str(payload.get('employe_id') or '').strip()
    fiche_poste_id = str(payload.get('fiche_poste_id') or '').strip()
    ouvrage_id = str(payload.get('ouvrage_id') or '').strip()
    planning_date = _parse_mobile_date(payload.get('date'))
    remarque = str(payload.get('remarque') or '').strip()
    statut = str(payload.get('statut') or 'en_cours').strip()
    priorite = str(payload.get('priorite') or 'normale').strip()

    if not planning_date:
        return JsonResponse({'success': False, 'error': 'Date invalide (format AAAA-MM-JJ attendu)'}, status=400)
    if not employe_id or not _mobile_employes_queryset(request.user).filter(id=employe_id).exists():
        return JsonResponse({'success': False, 'error': 'Employe non autorise'}, status=403)
    if statut not in dict(Planning.STATUS_CHOICES):
        return JsonResponse({'success': False, 'error': 'Statut invalide'}, status=400)
    if priorite not in dict(Planning.PRIORITE_SUIVI_CHOICES):
        return JsonResponse({'success': False, 'error': 'Priorite invalide'}, status=400)

    repair_fiche_ids = set(get_repair_fiches_queryset().values_list('id', flat=True))
    mobile_repair_fiche_ids = set(get_mobile_repair_fiches_queryset().values_list('id', flat=True))
    fiche_query = FichePoste.objects.filter(id=fiche_poste_id)
    if is_repair:
        fiche_query = fiche_query.filter(id__in=mobile_repair_fiche_ids)
    else:
        fiche_query = fiche_query.filter(dans_planning=True).exclude(id__in=repair_fiche_ids)
    fiche = fiche_query.select_related('type_activites').first()
    if not fiche:
        return JsonResponse({'success': False, 'error': 'Activite non autorisee'}, status=403)

    _, ouvrage_ids = _get_scoped_ouvrage_ids_for_request(request)
    ouvrage_ids = {str(value) for value in ouvrage_ids}
    if is_repair and not ouvrage_id:
        return JsonResponse({'success': False, 'error': 'Ouvrage requis pour une reparation'}, status=400)
    if ouvrage_id and ouvrage_id not in ouvrage_ids:
        return JsonResponse({'success': False, 'error': 'Ouvrage non autorise'}, status=403)

    if planning_id:
        queryset = _mobile_plannings_queryset(request.user)
        if is_repair:
            queryset = Planning.objects.filter(
                ouvrage_id__in=ouvrage_ids,
                fiche_poste_id__in=mobile_repair_fiche_ids,
            )
        else:
            queryset = queryset.exclude(fiche_poste_id__in=repair_fiche_ids)
        planning = queryset.filter(id=planning_id).first()
        if not planning:
            return JsonResponse({'success': False, 'error': 'Element introuvable ou non autorise'}, status=404)
        created = False
        if planning.estvalide:
            if statut == 'annule' and planning.statut != 'annule':
                return JsonResponse({'success': False, 'error': (
                    "Planning validé : il ne peut pas être annulé. "
                    "Vous pouvez seulement changer sa date ou son employé.")}, status=400)
            if str(planning.fiche_poste_id or '') != fiche_poste_id or str(planning.ouvrage_id or '') != ouvrage_id:
                return JsonResponse({'success': False, 'error': (
                    "Planning validé : l'activité et l'ouvrage ne peuvent plus changer. "
                    "Vous pouvez seulement changer sa date ou son employé.")}, status=400)
    else:
        planning = Planning()
        created = True

    target_given = 'equipement_id' in payload or 'point_eau_id' in payload
    target_equipement = target_point_eau = None
    if target_given:
        from apps.infrastructure.models import EquipementConstitutif
        equipement_id = str(payload.get('equipement_id') or '').strip()
        point_eau_id = str(payload.get('point_eau_id') or '').strip()
        if equipement_id and point_eau_id:
            return JsonResponse({'success': False, 'error': "Un equipement ou un point d'eau, pas les deux"}, status=400)
        try:
            if equipement_id:
                target_equipement = EquipementConstitutif.objects.filter(id=equipement_id).first()
                bad = not target_equipement or str(target_equipement.ouvrage_id) != ouvrage_id
            elif point_eau_id:
                target_point_eau = PointEau.objects.filter(id=point_eau_id).first()
                bad = not target_point_eau or str(target_point_eau.ouvrage_id) != ouvrage_id
            else:
                bad = False
        except (ValueError, ValidationError):
            bad = True
        if bad:
            return JsonResponse({'success': False, 'error': "Cible introuvable pour cet ouvrage"}, status=400)

    with transaction.atomic():
        planning.date = planning_date
        planning.employe_id = employe_id
        planning.fiche_poste = fiche
        planning.type_activite_id = fiche.type_activites_id
        planning.ouvrage_id = ouvrage_id or None
        planning.remarque = remarque
        planning.statut = statut
        planning.priorite_suivi = priorite if is_repair else (planning.priorite_suivi or None)
        planning.save()
        if target_given:
            from apps.planning.reparation_composants import (
                ComposantsError, apply_repair_target, parse_composants_ids, verifier_regles_fiche,
            )
            try:
                verifier_regles_fiche(
                    fiche, target_equipement, target_point_eau, parse_composants_ids(payload) or [])
                apply_repair_target(planning, target_equipement, target_point_eau, parse_composants_ids(payload))
            except ComposantsError as exc:
                transaction.set_rollback(True)
                return JsonResponse({'success': False, 'error': str(exc)}, status=400)
        if is_repair:
            ensure_repair_conversation(planning, actor=request.user, notify=False)

    return JsonResponse({
        'success': True,
        'id': str(planning.id),
        'created': created,
        'message': ('Reparation' if is_repair else 'Planning') + (' cree' if created else ' modifie'),
    })


@csrf_exempt
@mobile_auth_required
@require_http_methods(["POST"])
def api_enregistrer_reparation_mobile(request):
    return _save_mobile_planning(request, is_repair=True)


@csrf_exempt
@mobile_auth_required
@require_http_methods(["POST"])
def api_enregistrer_planning_mobile(request):
    return _save_mobile_planning(request, is_repair=False)


def _decode_mobile_photo(payload):
    photo_data = str(payload.get('photo_data') or '').strip()
    content_type = str(payload.get('content_type') or 'image/jpeg').lower()
    if photo_data.startswith('data:'):
        try:
            header, photo_data = photo_data.split(',', 1)
            content_type = header[5:].split(';', 1)[0].lower()
        except ValueError:
            return None, None, 'Photo invalide'
    if content_type not in {'image/jpeg', 'image/png', 'image/webp'}:
        return None, None, 'Format photo invalide'
    photo_data = _normalize_mobile_base64(photo_data)
    if not photo_data:
        return None, None, 'Photo vide : reprenez la photo'
    try:
        photo_bytes = base64.b64decode(photo_data, validate=True)
    except (ValueError, binascii.Error):
        logger.warning(
            "Photo mobile non decodable (len=%s, debut=%r, fin=%r)",
            len(photo_data), photo_data[:16], photo_data[-16:],
        )
        return None, None, f'Photo invalide (base64 illisible, {len(photo_data)} caracteres recus)'
    if not photo_bytes or len(photo_bytes) > 5 * 1024 * 1024:
        return None, None, 'La photo doit faire moins de 5 Mo'
    return photo_data, content_type, None


def _normalize_mobile_base64(raw):
    """Répare les altérations de transport courantes d'un base64 de photo mobile.

    - « + » décodé en espace par un encodage de formulaire non conforme ;
    - retours à la ligne (Base64.DEFAULT Android coupe toutes les 76 colonnes) ;
    - alphabet URL-safe (« - » / « _ ») ;
    - padding « = » manquant.
    """
    value = str(raw or '').strip().replace(' ', '+')
    value = ''.join(value.split())
    value = value.replace('-', '+').replace('_', '/')
    value = value.rstrip('=')
    return value + '=' * (-len(value) % 4)


@csrf_exempt
@mobile_auth_required
@require_http_methods(["POST"])
def api_photo_reparation_mobile(request, planning_id):
    """Ajoute une photo preuve a une reparation (Planning) depuis l'app terrain.

    Meme stockage que le formulaire web (Suivi Reparations > Photos preuve) :
    Planning.photo, liste JSON d'objets {id, name, data, size, originalSize,
    type, date}. Contrairement a photo_point/photo_equipment (une seule photo,
    remplacee a chaque envoi), les photos de reparation s'accumulent - une
    intervention peut avoir plusieurs photos (avant/apres travaux, angles
    differents).
    """
    payload = _request_payload(request)
    if payload is None:
        return JsonResponse({'success': False, 'error': 'Corps JSON invalide'}, status=400)

    repair_fiche_ids = set(get_mobile_repair_fiches_queryset().values_list('id', flat=True))
    _, ouvrage_ids = _get_scoped_ouvrage_ids_for_request(request)
    ouvrage_ids = {str(value) for value in ouvrage_ids}

    planning = Planning.objects.filter(
        id=planning_id,
        ouvrage_id__in=ouvrage_ids,
        fiche_poste_id__in=repair_fiche_ids,
    ).first()
    if not planning:
        return JsonResponse({'success': False, 'error': 'Reparation introuvable ou non autorisee'}, status=404)

    local_uuid = str(payload.get('local_uuid') or '').strip()
    existing_photos = _parse_planning_photo_payload(planning.photo)
    if local_uuid and any(str(item.get('id') or '') == local_uuid for item in existing_photos):
        return JsonResponse({
            'success': True,
            'id': str(planning.id),
            'duplicate_prevented': True,
            'photo_count': len(existing_photos),
        })

    photo_data, content_type, error = _decode_mobile_photo(payload)
    if error:
        return JsonResponse({'success': False, 'error': error}, status=400)

    now = timezone.now()
    photo_bytes_size = len(base64.b64decode(photo_data))
    existing_photos.append({
        'id': local_uuid or uuid.uuid4().hex,
        'name': str(payload.get('filename') or 'reparation-terrain.jpg')[:180],
        'data': f'data:{content_type};base64,{photo_data}',
        'size': photo_bytes_size,
        'originalSize': photo_bytes_size,
        'type': content_type,
        'date': now.isoformat(),
    })

    planning.photo = _serialize_planning_photo_payload(existing_photos)
    planning.save(update_fields=['photo', 'updated_at'])

    return JsonResponse({
        'success': True,
        'id': str(planning.id),
        'photo_count': len(existing_photos),
        'server_updated_at': now.isoformat(),
    })


@csrf_exempt
@mobile_auth_required
@require_http_methods(["POST"])
def api_sync_terrain_item(request):
    """Synchronise une action Terrain legere ou une photo separee."""
    payload = _request_payload(request)
    if payload is None:
        return JsonResponse({'success': False, 'error': 'Corps JSON invalide'}, status=400)
    operation_type = str(payload.get('operation_type') or '').strip()
    force_sync = _force_sync_requested(payload)
    _, allowed_ouvrage_ids = _get_scoped_ouvrage_ids_for_request(request)
    allowed_ouvrage_ids = set(allowed_ouvrage_ids)
    now = timezone.now()

    if operation_type in {'update_point', 'photo_point'}:
        point = PointEau.objects.filter(
            id=payload.get('point_id'), ouvrage_id__in=allowed_ouvrage_ids
        ).first()
        if not point:
            return JsonResponse({'success': False, 'error': "Point d'eau introuvable ou non autorise"}, status=404)
        local_uuid = str(payload.get('local_uuid') or '').strip()
        if operation_type == 'photo_point' and _photo_has_local_uuid(point.photos, local_uuid):
            return JsonResponse({
                'success': True,
                'id': str(point.id),
                'duplicate_prevented': True,
                'server_updated_at': point.updatedat.isoformat() if point.updatedat else None,
                'server_value': _point_server_value(point),
            })
        if operation_type == 'update_point' and _point_update_matches_payload(point, payload):
            return JsonResponse({
                'success': True,
                'id': str(point.id),
                'duplicate_prevented': True,
                'server_updated_at': point.updatedat.isoformat() if point.updatedat else None,
                'server_value': _point_server_value(point),
            })
        base_updated_raw = _clean_base_version(payload.get('base_updated_at'))
        if base_updated_raw and point.updatedat:
            try:
                base_updated_at = datetime.fromisoformat(base_updated_raw.replace('Z', '+00:00'))
                if timezone.is_naive(base_updated_at):
                    base_updated_at = timezone.make_aware(base_updated_at)
            except ValueError:
                return JsonResponse({'success': False, 'error': 'Version locale invalide'}, status=400)
            if point.updatedat > base_updated_at and not force_sync and operation_type != 'photo_point':
                return JsonResponse({
                    'success': False,
                    'error': "Conflit : le point d'eau a ete modifie depuis la synchronisation",
                    'conflict': True,
                    'server_updated_at': point.updatedat.isoformat(),
                    'server_value': _point_server_value(point),
                }, status=409)
        update_fields = []
        champs_points = []  # champs qui etaient VIDES avant cet envoi (seuls eligibles aux points)
        if operation_type == 'update_point':
            if 'subscriber_name' in payload:
                name = str(payload.get('subscriber_name') or '').strip()
                if not name:
                    return JsonResponse({'success': False, 'error': "Nom d'abonne requis"}, status=400)
                if not _nom_abonne_renseigne(point.nomabonne):
                    champs_points.append('nom_abonne')
                point.nomabonne = name[:255]
                update_fields.append('nomabonne')
            if 'telephone' in payload:
                new_phone = str(payload.get('telephone') or '').strip()[:20]
                if not new_phone and point.numeroteleph and not request.user.is_superuser:
                    return JsonResponse({'success': False, 'error': "Effacement du telephone interdit : corrigez-le en saisissant le bon numero."}, status=400)
                if new_phone and not (point.numeroteleph or '').strip():
                    champs_points.append('telephone')
                point.numeroteleph = new_phone or None
                update_fields.append('numeroteleph')
            if 'latitude' in payload or 'longitude' in payload:
                try:
                    latitude = float(payload.get('latitude'))
                    longitude = float(payload.get('longitude'))
                except (TypeError, ValueError):
                    return JsonResponse({'success': False, 'error': 'Coordonnees invalides'}, status=400)
                if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                    return JsonResponse({'success': False, 'error': 'Coordonnees hors limites'}, status=400)
                distance_error = terrain_points.controle_distance_gps(request.user, 'point_eau', point, latitude, longitude)
                if distance_error:
                    return JsonResponse({'success': False, 'error': distance_error, 'code': 'gps_trop_loin'}, status=422)
                if point.latitude is None or point.longitude is None:
                    champs_points.append('gps')
                point.latitude, point.longitude = latitude, longitude
                update_fields.extend(['latitude', 'longitude'])
        else:
            photo_data, content_type, error = _decode_mobile_photo(payload)
            if error:
                return JsonResponse({'success': False, 'error': error}, status=400)
            if not _has_usable_photo(point.photos):
                champs_points.append('photo')
            point.photos = _append_mobile_photo(point.photos, {
                'filename': str(payload.get('filename') or 'point-eau-terrain.jpg')[:180],
                'size': len(base64.b64decode(photo_data)),
                'content_type': content_type,
                'data': photo_data,
                'uploaded_at': now.isoformat(),
                'local_uuid': str(payload.get('local_uuid') or ''),
            })
            update_fields.append('photos')
        if not update_fields:
            return JsonResponse({'success': False, 'error': 'Aucune donnee a enregistrer'}, status=400)
        point.updatedat = now
        point.updated_by = getattr(request.user, 'employe', None)
        update_fields.extend(['updatedat', 'updated_by'])
        point.save(update_fields=list(dict.fromkeys(update_fields)))
        point.refresh_from_db()
        employe = getattr(request.user, 'employe', None)
        gagnes = terrain_points.attribuer(employe, 'point_eau', point.id, champs_points)
        return JsonResponse({
            'success': True,
            'id': str(point.id),
            'server_updated_at': point.updatedat.isoformat() if point.updatedat else now.isoformat(),
            'server_value': _point_server_value(point),
            **terrain_points.infos_points(employe, gagnes),
        })

    if operation_type == 'update_equipment':
        # Coordonnées GPS d'un équipement (fiche Recherche de l'app terrain).
        equipment = EquipementConstitutif.objects.filter(
            id=payload.get('equipment_id'), ouvrage_id__in=allowed_ouvrage_ids
        ).first()
        if not equipment:
            return JsonResponse({'success': False, 'error': 'Equipement introuvable ou non autorise'}, status=404)
        try:
            latitude = float(payload.get('latitude'))
            longitude = float(payload.get('longitude'))
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Coordonnees invalides'}, status=400)
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            return JsonResponse({'success': False, 'error': 'Coordonnees hors limites'}, status=400)

        def equipment_value():
            return {
                'latitude': float(equipment.latitude) if equipment.latitude is not None else None,
                'longitude': float(equipment.longitude) if equipment.longitude is not None else None,
                'has_coordinates': equipment.latitude is not None and equipment.longitude is not None,
                'has_photo': bool(equipment.photo_reference_id) or _has_usable_photo(equipment.photos),
            }

        distance_error = terrain_points.controle_distance_gps(request.user, 'equipement', equipment, latitude, longitude)
        if distance_error:
            return JsonResponse({'success': False, 'error': distance_error, 'code': 'gps_trop_loin'}, status=422)
        gps_etait_vide = equipment.latitude is None or equipment.longitude is None
        new_lat = Decimal(str(round(latitude, 8)))
        new_lon = Decimal(str(round(longitude, 8)))
        if equipment.latitude == new_lat and equipment.longitude == new_lon:
            return JsonResponse({'success': True, 'id': str(equipment.id), 'duplicate_prevented': True,
                                 'server_value': equipment_value()})
        base_updated_raw = _clean_base_version(payload.get('base_updated_at'))
        if base_updated_raw and equipment.updated_at:
            try:
                base_updated_at = datetime.fromisoformat(base_updated_raw.replace('Z', '+00:00'))
                if timezone.is_naive(base_updated_at):
                    base_updated_at = timezone.make_aware(base_updated_at)
            except ValueError:
                return JsonResponse({'success': False, 'error': 'Version locale invalide'}, status=400)
            if equipment.updated_at > base_updated_at and not force_sync:
                return JsonResponse({
                    'success': False,
                    'error': 'Conflit : equipement modifie depuis la synchronisation',
                    'conflict': True,
                    'server_updated_at': equipment.updated_at.isoformat(),
                    'server_value': equipment_value(),
                }, status=409)
        equipment.latitude, equipment.longitude = new_lat, new_lon
        equipment.updated_by = request.user
        equipment.save(update_fields=['latitude', 'longitude', 'updated_by', 'updated_at'])
        equipment.refresh_from_db()
        employe = getattr(request.user, 'employe', None)
        gagnes = terrain_points.attribuer(employe, 'equipement', equipment.id, ['gps'] if gps_etait_vide else [])
        return JsonResponse({
            'success': True,
            'id': str(equipment.id),
            'server_updated_at': equipment.updated_at.isoformat(),
            'server_value': equipment_value(),
            **terrain_points.infos_points(employe, gagnes),
        })

    if operation_type == 'photo_equipment':
        equipment = EquipementConstitutif.objects.filter(
            id=payload.get('equipment_id'), ouvrage_id__in=allowed_ouvrage_ids
        ).first()
        if not equipment:
            return JsonResponse({'success': False, 'error': 'Equipement introuvable ou non autorise'}, status=404)
        local_uuid = str(payload.get('local_uuid') or '').strip()
        if _photo_has_local_uuid(equipment.photos, local_uuid):
            return JsonResponse({
                'success': True,
                'id': str(equipment.id),
                'duplicate_prevented': True,
                'server_updated_at': equipment.updated_at.isoformat() if equipment.updated_at else None,
                'server_value': {'has_photo': _has_usable_photo(equipment.photos)},
            })
        # Une photo s'ajoute à la liste : pas de contrôle de conflit de version (voir _append_mobile_photo).
        photo_data, content_type, error = _decode_mobile_photo(payload)
        if error:
            return JsonResponse({'success': False, 'error': error}, status=400)
        photo_etait_vide = not _has_usable_photo(equipment.photos)
        equipment.photos = _append_mobile_photo(equipment.photos, {
            'filename': str(payload.get('filename') or 'equipement-terrain.jpg')[:180],
            'size': len(base64.b64decode(photo_data)),
            'content_type': content_type,
            'data': photo_data,
            'uploaded_at': now.isoformat(),
            'local_uuid': str(payload.get('local_uuid') or ''),
        })
        equipment.updated_by = request.user
        equipment.save(update_fields=['photos', 'updated_by', 'updated_at'])
        equipment.refresh_from_db()
        employe = getattr(request.user, 'employe', None)
        gagnes = terrain_points.attribuer(employe, 'equipement', equipment.id, ['photo'] if photo_etait_vide else [])
        return JsonResponse({
            'success': True,
            'id': str(equipment.id),
            'server_updated_at': equipment.updated_at.isoformat(),
            'server_value': {'has_photo': _has_usable_photo(equipment.photos)},
            **terrain_points.infos_points(employe, gagnes),
        })

    if operation_type == 'flow_measure':
        from apps.planning.views import _get_debit_source_ouvrages_queryset
        ouvrage = _get_debit_source_ouvrages_queryset(request.user).filter(
            id=payload.get('ouvrage_id'), id__in=allowed_ouvrage_ids
        ).first()
        if not ouvrage:
            return JsonResponse({'success': False, 'error': 'Captage introuvable ou non autorise'}, status=404)
        try:
            measurement_date = date.fromisoformat(str(payload.get('date') or ''))
            if payload.get('debit_l_s') not in (None, ''):
                flow = Decimal(str(payload.get('debit_l_s')))
            else:
                volume_l = Decimal(str(payload.get('volume_l')))
                duration_s = Decimal(str(payload.get('duration_s')))
                if duration_s <= 0:
                    raise ValueError('Le temps doit etre superieur a zero')
                flow = volume_l / duration_s
            if flow < 0:
                raise ValueError('Le debit ne peut pas etre negatif')
        except (ValueError, TypeError, InvalidOperation) as exc:
            return JsonResponse({'success': False, 'error': str(exc) or 'Mesure invalide'}, status=400)
        existing = DebitSourceMesure.objects.filter(
            ouvrage=ouvrage, date_visite=measurement_date
        ).first()
        if existing:
            if existing.debit_l_s == flow:
                return JsonResponse({
                    'success': True,
                    'id': str(existing.id),
                    'created': False,
                    'duplicate_prevented': True,
                    'debit_l_s': float(existing.debit_l_s),
                })
            return JsonResponse({
                'success': False,
                'error': 'Une autre mesure de débit existe déjà à cette date',
                'conflict': True,
            }, status=409)
        measure = DebitSourceMesure.objects.create(
            ouvrage=ouvrage,
            date_visite=measurement_date,
            debit_l_s=flow,
            remarque=str(payload.get('remarque') or '').strip(),
            employe=getattr(request.user, 'employe', None),
            created_by=getattr(request.user, 'employe', None),
        )
        recent = list(DebitSourceMesure.objects.filter(ouvrage=ouvrage).order_by('-date_visite', '-created_at')[:20])
        previous = recent[1] if len(recent) > 1 else None
        average = sum((item.debit_l_s for item in recent), Decimal('0')) / len(recent)
        variation = ((flow - previous.debit_l_s) / previous.debit_l_s * 100) if previous and previous.debit_l_s else None
        return JsonResponse({
            'success': True, 'id': str(measure.id), 'created': True,
            'debit_l_s': float(flow),
            'previous_debit_l_s': float(previous.debit_l_s) if previous else None,
            'variation_percent': float(variation) if variation is not None else None,
            'recent_average_l_s': float(average),
        })

    if operation_type == 'head_meter_reading':
        from apps.organization.views_compteurs_releves import _build_snapshot, _resequence_releves
        meter = CompteurTete.objects.filter(
            id=payload.get('meter_id'), ouvrage_id__in=allowed_ouvrage_ids
        ).first()
        if not meter:
            return JsonResponse({'success': False, 'error': 'Compteur de tete introuvable ou non autorise'}, status=404)
        try:
            reading_date = date.fromisoformat(str(payload.get('date') or ''))
            new_index = Decimal(str(payload.get('new_index')))
            snapshot = _build_snapshot(meter, reading_date, new_index)
        except (ValueError, TypeError, InvalidOperation, ValidationError) as exc:
            message = getattr(exc, 'message_dict', None) or str(exc)
            return JsonResponse({'success': False, 'error': message}, status=400)
        existing = ReleveCompteurTete.objects.filter(compteur_tete=meter, date_releve=reading_date).first()
        if existing:
            if existing.nouvel_index == new_index:
                return JsonResponse({'success': True, 'id': str(existing.id), 'duplicate_prevented': True})
            return JsonResponse({'success': False, 'error': 'Un autre releve existe deja a cette date'}, status=409)
        with transaction.atomic():
            reading = ReleveCompteurTete.objects.create(
                compteur_tete=meter, date_releve=reading_date,
                ancien_index=snapshot['ancien_index'], nouvel_index=new_index,
                volume_tete=snapshot['volume_tete'], volume_aval=snapshot['volume_aval'],
                ecart_volume=snapshot['ecart_volume'], nb_points_eau_aval=snapshot['nb_points_eau_aval'],
                explication_ecart=str(payload.get('explanation') or '').strip() or None,
            )
            _resequence_releves(meter)
            reading.refresh_from_db()
        percent = (abs(reading.ecart_volume) / abs(reading.volume_tete) * 100) if reading.volume_tete else Decimal('0')
        return JsonResponse({
            'success': True, 'id': str(reading.id),
            'ancien_index': float(reading.ancien_index), 'nouvel_index': float(reading.nouvel_index),
            'volume_tete': float(reading.volume_tete), 'volume_aval': float(reading.volume_aval),
            'ecart_volume': float(reading.ecart_volume), 'ecart_percent': float(percent),
        })

    return JsonResponse({'success': False, 'error': 'Type operation Terrain inconnu'}, status=400)


@mobile_auth_required
@require_http_methods(["GET"])
def api_debits_ouvrage_mobile(request, ouvrage_id):
    """Historique des debits de source d'un ouvrage + niveau de criticite.

    Rejoue la logique de la page /plannings/debits-source/ (meme perimetre
    d'acces, meme seuil, memes statuts) pour l'application mobile.
    """
    from apps.planning.services_debit_critique import get_etat_debit
    from apps.planning.views import (
        _get_debit_source_ouvrages_queryset,
        _get_debit_source_type,
        _get_debit_status_label,
        _get_ouvrage_debit_context,
    )

    ouvrage = _get_debit_source_ouvrages_queryset(request.user).filter(id=ouvrage_id).first()
    if not ouvrage:
        return JsonResponse({'success': False, 'error': 'Ouvrage introuvable ou non autorise'}, status=404)

    today = timezone.localdate()
    info = _get_ouvrage_debit_context(ouvrage, today)
    seuil = info.get('seuil_minimum')
    mesures = list(
        DebitSourceMesure.objects.select_related('employe')
        .filter(ouvrage=ouvrage)
        .order_by('-date_visite', '-created_at')[:20]
    )

    items = []
    for index, mesure in enumerate(mesures):
        precedente = mesures[index + 1] if index + 1 < len(mesures) else None
        delta = None
        if precedente and precedente.debit_l_s is not None and mesure.debit_l_s is not None:
            delta = mesure.debit_l_s - precedente.debit_l_s
        employe = mesure.employe
        items.append({
            'id': str(mesure.id),
            'date_visite': mesure.date_visite.isoformat(),
            'debit_l_s': float(mesure.debit_l_s) if mesure.debit_l_s is not None else None,
            'delta_l_s': float(delta) if delta is not None else None,
            'periode': _get_debit_source_type(mesure.date_visite),
            'statut': _get_debit_status_label(mesure, info, delta),
            'sous_seuil': bool(
                seuil is not None and mesure.debit_l_s is not None and mesure.debit_l_s < seuil
            ),
            'remarque': mesure.remarque or '',
            'employe': (employe.surnom or employe.nom) if employe else '',
        })

    etat = get_etat_debit(ouvrage.id)
    dernier = mesures[0] if mesures else None
    plus_bas = min((m for m in mesures if m.debit_l_s is not None), key=lambda m: m.debit_l_s, default=None)
    return JsonResponse({
        'success': True,
        'ouvrage': {'id': str(ouvrage.id), 'nom': ouvrage.nom_ouvrage},
        'niveau': etat['niveau'] if etat else ('inconnu' if not mesures else 'normal'),
        'ratio_pct': etat['ratio_pct'] if etat else None,
        'seuil_l_s': float(seuil) if seuil is not None else None,
        'mode_paiement': info.get('mode_paiement'),
        'bornes': info.get('bornes'),
        'comparatif': info.get('comparative_label') or '',
        'interpretation': info.get('interpretation') or '',
        'dernier_debit_l_s': float(dernier.debit_l_s) if dernier and dernier.debit_l_s is not None else None,
        'plus_bas_debit_l_s': float(plus_bas.debit_l_s) if plus_bas else None,
        'mesures': items,
    })
