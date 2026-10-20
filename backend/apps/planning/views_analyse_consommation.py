"""Vue pour l'analyse de la consommation d'eau par habitant"""
from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum, Avg, Count, Max, Min
from datetime import datetime
import pytz
from collections import defaultdict
from decimal import Decimal

from apps.billing.models import Releve, PointEau, ModaliteGestion, TypePointEau, ConsoCarteSociale
from apps.billing.payment_modalities import is_private_point_type_name
from apps.geography.models import Commune, District, Region, Parcelle, Village, DonneeMeteo
from apps.organization.models import Ouvrage, Organisation
from apps.organization.scoping import get_user_accessible_gestionnaire_ids
from apps.infrastructure.models import CarteSociale
from apps.planning.models import DebitSourceMesure


MODALITE_LABELS = {
    'au_volume': 'Au volume',
    'forfaitaire': 'Forfaitaire',
    'mixte': 'Mixte',
    'cotisation_annuelle': 'Cotisation annuelle',
    'inconnue': 'Non renseignee',
}

# Categorisation des points d'eau pour separer la consommation privee (BP, estimee a
# 4 personnes/branchement) de la consommation collective/publique (kiosques - qui
# portent aussi la consommation des cartes sociales -, bornes individuelles au volume,
# et le reste des points d'eau non-BP).
POPULATION_PAR_BP = 4
CATEGORIES_PUBLIC = ['kiosque', 'bi_volume', 'autres']


def _classify_point_eau_category(type_nom, est_institutionnel=False):
    normalized = str(type_nom or '').strip().upper()
    if is_private_point_type_name(type_nom, est_institutionnel):
        return 'bp'
    if 'KIOSQUE' in normalized:
        return 'kiosque'
    # Ancien type « BI volume » = BP institutionnel (« BI VOLUME » conservé pour d'anciennes données)
    if 'BI VOLUME' in normalized or (est_institutionnel and normalized == 'BP'):
        return 'bi_volume'
    return 'autres'


LIBELLES_TYPE_ABONNE = {
    'particulier': 'Particuliers',
    'boutique': 'Boutiques',
    'non_renseigne': 'Abonné non renseigné',
}


def _segment_conso_point_eau(type_nom, typeabonne):
    """Segment d'analyse d'un point d'eau : son type, et pour les kiosques le type d'abonné."""
    type_nom = str(type_nom or '').strip() or 'Sans type'
    if 'KIOSQUE' in type_nom.upper():
        abonne = str(typeabonne or '').strip().lower()
        return type_nom, abonne if abonne in ('particulier', 'boutique') else 'non_renseigne'
    return type_nom, None


def _resume_valeurs(valeurs):
    """Moyenne / médiane / min / max d'une liste de nombres (zéros si vide)."""
    import statistics
    if not valeurs:
        return {'moyenne': 0, 'mediane': 0, 'minimum': 0, 'maximum': 0}
    return {
        'moyenne': round(statistics.mean(valeurs), 2),
        'mediane': round(statistics.median(valeurs), 2),
        'minimum': round(min(valeurs), 2),
        'maximum': round(max(valeurs), 2),
    }


def calculer_stats_conso_par_point_eau(pe_segments, volumes_pe_mois):
    """
    Moyenne et médiane de consommation PAR POINT D'EAU, par segment (type de point d'eau ; pour
    les kiosques, un segment par type d'abonné + une ligne agrégée « tous abonnés »).

    pe_segments : {pe_id: (type_nom, sous_segment|None)}
    volumes_pe_mois : {pe_id: {mois: volume_m3}} (volumes répartis par mois, point d'eau avec volume > 0)

    Valeur retenue pour un point d'eau = son volume mensuel moyen sur les mois où il a consommé
    (même convention que les tranches de consommation des BP). Retourne la liste des segments, avec
    pour chacun les moyennes / médianes mensuelles (12 valeurs) utilisées par le graphique d'évolution.
    """
    par_segment = defaultdict(list)        # (type, sous) -> [pe_id]
    for pe_id, (type_nom, sous) in pe_segments.items():
        if not volumes_pe_mois.get(pe_id):
            continue
        par_segment[(type_nom, sous)].append(pe_id)
        if sous is not None:
            par_segment[(type_nom, None)].append(pe_id)   # ligne agrégée du type (kiosque, tous abonnés)

    segments = []
    for (type_nom, sous), pe_ids in par_segment.items():
        mensuel_moyen, mensuel_median = [], []
        for mois in range(1, 13):
            vols = [volumes_pe_mois[p][mois] for p in pe_ids if volumes_pe_mois[p].get(mois, 0) > 0]
            r = _resume_valeurs(vols)
            mensuel_moyen.append(r['moyenne'])
            mensuel_median.append(r['mediane'])
        par_pe = [sum(v for v in volumes_pe_mois[p].values() if v > 0) /
                  max(1, sum(1 for v in volumes_pe_mois[p].values() if v > 0)) for p in pe_ids]
        a_sous_segments = any(t == type_nom and s is not None for (t, s) in par_segment)
        agregat = sous is None and a_sous_segments
        if sous is not None:
            label = f"{type_nom} · {LIBELLES_TYPE_ABONNE[sous]}"
        elif agregat:
            label = f"{type_nom} (tous abonnés)"
        else:
            label = type_nom
        segments.append({
            'label': label,
            'type': type_nom,
            'sous_segment': sous,
            'agregat': agregat,
            'nb_points_eau': len(pe_ids),
            'volume_total': round(sum(sum(volumes_pe_mois[p].values()) for p in pe_ids), 2),
            **_resume_valeurs(par_pe),
            'mensuel_moyenne': mensuel_moyen,
            'mensuel_mediane': mensuel_median,
        })
    # Tri : par type (alphabétique), la ligne agrégée d'un type avant ses sous-segments
    rang_abonne = {None: 0, 'particulier': 1, 'boutique': 2, 'non_renseigne': 3}
    segments.sort(key=lambda s: (s['type'].lower(), rang_abonne[s['sous_segment']]))
    return segments


SEUIL_KIOSQUE_BP_DEGUISE = 10   # m³ par mois : en dessous, un « kiosque » consomme comme un branchement privé
ALERTE_BP_MIN_RELEVES = 3       # relevés minimum (sur 12 mois) pour alerter l'agent : évite les kiosques récents


def lister_kiosques_faible_conso(points_eau, volumes_pe_mois, jours_couverts_pe, seuil, institutionnel='tous'):
    """
    Kiosques dont la consommation moyenne est inférieure à `seuil` m³ par mois (BP déguisés).
    `institutionnel` : 'tous' | 'non' (hors branchements institutionnels : écoles, blocs sanitaires…)
    | 'oui' (institutionnels seulement).

    Moyenne = volume total de l'année / jours couverts par les relevés × 30,44 : elle ne dépend pas des
    mois partiellement couverts (début / fin de période), contrairement à une moyenne de volumes mensuels.
    Triés du plus faible au plus fort consommateur.
    """
    lignes = []
    libelles_abonne = {'particulier': 'Particulier', 'boutique': 'Boutique'}
    for pe in points_eau:
        type_nom = getattr(pe.type_point_eau, 'nom_type', None) or ''
        if 'KIOSQUE' not in type_nom.upper():
            continue
        est_institutionnel = bool(getattr(pe, 'estbranchementinstitutionnel', False))
        if (institutionnel == 'non' and est_institutionnel) or (institutionnel == 'oui' and not est_institutionnel):
            continue
        pe_id = str(pe.id)
        mois_actifs = [v for v in volumes_pe_mois.get(pe_id, {}).values() if v > 0]
        jours = jours_couverts_pe.get(pe_id, 0)
        if not mois_actifs or jours <= 0:
            continue
        volume = sum(mois_actifs)
        moyenne = volume / jours * 30.44
        if moyenne >= seuil:
            continue
        parcelle = pe.parcelle
        village = parcelle.village if parcelle else None
        commune = village.fokontany.commune if village and village.fokontany else None
        abonne = str(pe.typeabonne or '').strip().lower()
        lignes.append({
            'id': pe_id,
            'nom': pe.nomabonne or pe.code_point_eau or '-',
            'idxls': pe.idxls or '',
            'ouvrage': pe.ouvrage.nom_ouvrage if pe.ouvrage else '-',
            'ouvrage_id': str(pe.ouvrage_id or ''),
            'village': village.nom_village if village else '',
            'commune': commune.nom_commune if commune else '',
            'type_abonne': libelles_abonne.get(abonne, 'Non renseigné'),
            'institutionnel': est_institutionnel,
            'moyenne': round(moyenne, 2),
            'nb_mois': len(mois_actifs),
            'volume_total': round(volume, 2),
        })
    lignes.sort(key=lambda l: (l['moyenne'], l['ouvrage'].lower(), l['nom'].lower()))
    return lignes


def _category_sum(mapping, oid, categories):
    oid_map = mapping.get(oid, {})
    return sum(oid_map.get(cat, 0) for cat in categories)


def _category_sum_list(mapping, oid, categories, length=12):
    oid_map = mapping.get(oid, {})
    totals = [0.0] * length
    for cat in categories:
        values = oid_map.get(cat)
        if not values:
            continue
        for idx in range(length):
            totals[idx] += values[idx]
    return totals


def _compute_consumption_metrics(volumes, montants, population, nb_points_eau):
    """Calcule montants/hab, conso/hab et moyennes a partir de volumes/montants bruts
    (listes de 12 valeurs mensuelles) et d'une population de reference."""
    population_ref = population or max(4, nb_points_eau * 4)

    montants_hab = [0] * 12
    conso_hab = [0] * 12
    for idx, volume in enumerate(volumes):
        jours_mois = 31 if idx + 1 in [1, 3, 5, 7, 8, 10, 12] else 28 if idx + 1 == 2 else 30
        conso_hab[idx] = round((volume * 1000) / population_ref / jours_mois, 1) if population_ref > 0 else 0
        montants_hab[idx] = round((montants[idx] / population_ref), 2) if population_ref > 0 else 0

    volume_non_zero = [v for v in volumes if v > 0]
    montant_non_zero = [v for v in montants if v > 0]
    montant_hab_non_zero = [v for v in montants_hab if v > 0]
    conso_non_zero = [v for v in conso_hab if v > 0]

    return {
        'volumes': [round(v, 2) for v in volumes],
        'montants': [round(v, 2) for v in montants],
        'montants_hab': [round(v, 2) for v in montants_hab],
        'conso_hab': [round(v, 1) for v in conso_hab],
        'volume_total': round(sum(volumes), 2),
        'montant_total': round(sum(montants), 2),
        'moyenne_volume': round(sum(volume_non_zero) / len(volume_non_zero), 2) if volume_non_zero else 0,
        'moyenne_montant': round(sum(montant_non_zero) / len(montant_non_zero), 2) if montant_non_zero else 0,
        'moyenne_montant_hab': round(sum(montant_hab_non_zero) / len(montant_hab_non_zero), 2) if montant_hab_non_zero else 0,
        'moyenne_conso_hab': round(sum(conso_non_zero) / len(conso_non_zero), 1) if conso_non_zero else 0,
    }


def _finalize_card_metrics(stats, debit_by_ouvrage, premiere_date_by_ouvrage, aujourdhui_mg):
    """Calcule montants/hab, conso/hab, moyennes, comparaison au debit de la source et
    anciennete du suivi a partir des volumes/montants/population bruts d'une carte."""
    jours_mois_moyen = 30.44
    population = stats['population'] or max(4, stats['nb_points_eau'] * 4)

    stats.update(_compute_consumption_metrics(
        stats['volumes'], stats['montants'], population, stats['nb_points_eau']
    ))

    stats['debit_l_s'] = None
    stats['debit_capacite_hab_jour'] = None
    stats['debit_capacite_m3_mois'] = None
    stats['taux_utilisation_pct'] = None
    stats['niveau_criticite'] = 'inconnu'
    debit_l_s = debit_by_ouvrage.get(stats['ouvrage_id'])
    if debit_l_s is not None:
        debit_l_jour = debit_l_s * 86400
        stats['debit_l_s'] = round(debit_l_s, 3)
        stats['debit_capacite_hab_jour'] = round(debit_l_jour / population, 1) if population > 0 else None
        stats['debit_capacite_m3_mois'] = round((debit_l_jour * jours_mois_moyen) / 1000, 2)
        if stats['debit_capacite_hab_jour']:
            taux = (stats['moyenne_conso_hab'] / stats['debit_capacite_hab_jour']) * 100
            stats['taux_utilisation_pct'] = round(taux, 1)
            if taux >= 80:
                stats['niveau_criticite'] = 'critique'
            elif taux >= 60:
                stats['niveau_criticite'] = 'attention'
            else:
                stats['niveau_criticite'] = 'ok'

    stats['premiere_date_releve'] = None
    stats['anciennete_jours'] = None
    stats['niveau_historique'] = 'inconnu'
    premiere_date = premiere_date_by_ouvrage.get(stats['ouvrage_id'])
    if premiere_date:
        anciennete_jours = (aujourdhui_mg - premiere_date).days
        stats['premiere_date_releve'] = premiere_date.isoformat()
        stats['anciennete_jours'] = anciennete_jours
        if anciennete_jours >= 365:
            stats['niveau_historique'] = 'etabli'
        elif anciennete_jours >= 90:
            stats['niveau_historique'] = 'court'
        else:
            stats['niveau_historique'] = 'recent'

    return stats


def _attach_bp_public_breakdown(stats, oid, category_pe_count, category_population, category_volumes, category_montants):
    """Ajoute au dict de carte les sous-metriques BP et Public (kiosque + BI volume +
    autres), en plus des metriques globales 'tous' deja calculees, pour permettre
    d'afficher 3 courbes de consommation (tous/BP/public) a cote d'un seul histogramme
    de montant."""
    bp_population = _category_sum(category_population, oid, ['bp'])
    bp_nb_points = _category_sum(category_pe_count, oid, ['bp'])
    bp_metrics = _compute_consumption_metrics(
        _category_sum_list(category_volumes, oid, ['bp']),
        _category_sum_list(category_montants, oid, ['bp']),
        bp_population,
        bp_nb_points,
    )
    for key, value in bp_metrics.items():
        stats[f'{key}_bp'] = value
    stats['population_bp'] = bp_population
    stats['nb_points_eau_bp'] = bp_nb_points

    public_population = _category_sum(category_population, oid, CATEGORIES_PUBLIC)
    public_nb_points = _category_sum(category_pe_count, oid, CATEGORIES_PUBLIC)
    public_metrics = _compute_consumption_metrics(
        _category_sum_list(category_volumes, oid, CATEGORIES_PUBLIC),
        _category_sum_list(category_montants, oid, CATEGORIES_PUBLIC),
        public_population,
        public_nb_points,
    )
    for key, value in public_metrics.items():
        stats[f'{key}_public'] = value
    stats['population_public'] = public_population
    stats['nb_points_eau_public'] = public_nb_points

    return stats


def _days_in_month(year, month):
    if month == 2:
        is_leap = (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)
        return 29 if is_leap else 28
    if month in [1, 3, 5, 7, 8, 10, 12]:
        return 31
    return 30


def _visible_month_count(year, reference_datetime=None):
    """Nombre de mois terminés à tracer, en excluant le mois en cours."""
    current = reference_datetime or datetime.now(pytz.timezone('Indian/Antananarivo'))
    if year < current.year:
        return 12
    if year > current.year:
        return 0
    return max(0, current.month - 1)


def _normalize_modalite_label(modalite_code):
    return MODALITE_LABELS.get(modalite_code or 'inconnue', MODALITE_LABELS['inconnue'])


def _get_modalite_by_ouvrage_ids(ouvrage_ids, gestionnaire_ids, organisation_filter):
    modalites = _apply_organisation_filter_to_modalites(
        ModaliteGestion.objects.filter(
            date_fin__isnull=True,
            ouvrage_id__in=ouvrage_ids,
        ).select_related('ouvrage'),
        gestionnaire_ids,
        organisation_filter,
    ).order_by('ouvrage_id', '-date_debut', '-created_at')

    modalite_by_ouvrage = {}
    for modalite in modalites:
        oid = str(modalite.ouvrage_id)
        if oid in modalite_by_ouvrage:
            continue
        code = modalite.modalitepaiement or 'inconnue'
        modalite_by_ouvrage[oid] = {
            'code': code,
            'label': _normalize_modalite_label(code),
        }
    return modalite_by_ouvrage


def _get_geo_by_ouvrage_ids(points_eau):
    geo_by_ouvrage = {}
    for point_eau in points_eau:
        if not point_eau.ouvrage_id:
            continue
        oid = str(point_eau.ouvrage_id)
        if oid in geo_by_ouvrage:
            continue
        district = getattr(point_eau.parcelle.village.fokontany.commune, 'district', None) if point_eau.parcelle_id and point_eau.parcelle and point_eau.parcelle.village and point_eau.parcelle.village.fokontany and point_eau.parcelle.village.fokontany.commune else None
        region = getattr(district, 'region', None) if district else None
        geo_by_ouvrage[oid] = {
            'region_label': region.nom_region if region else 'Sans region',
            'district_label': district.nom_district if district else 'Sans district',
        }
    return geo_by_ouvrage


def _get_modalite_ouvrages_ids(gestionnaire_ids, organisation_filter, modalite_paiement_filter):
    modalite_query = ModaliteGestion.objects.filter(date_fin__isnull=True)

    if modalite_paiement_filter:
        if modalite_paiement_filter == 'au_volume':
            modalite_query = modalite_query.filter(modalitepaiement__in=['au_volume', 'mixte'])
        elif modalite_paiement_filter == 'forfaitaire':
            modalite_query = modalite_query.filter(modalitepaiement='forfaitaire')
        elif modalite_paiement_filter == 'mixte':
            modalite_query = modalite_query.filter(modalitepaiement='mixte')
    else:
        modalite_query = modalite_query.filter(modalitepaiement__in=['au_volume', 'mixte'])

    modalite_query = _apply_organisation_filter_to_modalites(
        modalite_query,
        gestionnaire_ids,
        organisation_filter,
    )
    return modalite_query.values_list('ouvrage_id', flat=True).distinct()


def _get_organisation_filter_state(request):
    gestionnaire_ids = get_user_accessible_gestionnaire_ids(request.user)

    if gestionnaire_ids is None:
        raw_ids = None
        normalized_ids = None
        default_org = 'all'
        organisations = Organisation.objects.filter(
            type_organisation=Organisation.TYPE_GESTIONNAIRE
        )
    else:
        raw_ids = list(gestionnaire_ids)
        normalized_ids = [str(_id) for _id in raw_ids]
        organisations = Organisation.objects.filter(id__in=raw_ids)
        if normalized_ids:
            default_org = normalized_ids[0] if len(normalized_ids) == 1 else 'all'
        else:
            default_org = 'all'
            organisations = organisations.none()

    organisation_filter = request.GET.get('organisation', default_org) or default_org
    if organisation_filter != 'all' and normalized_ids is not None:
        if organisation_filter not in set(normalized_ids):
            organisation_filter = default_org

    return {
        'gestionnaire_ids': raw_ids if gestionnaire_ids is not None else None,
        'organisation_filter': organisation_filter,
        'organisations': organisations.order_by('nom_organisation'),
    }


def _apply_organisation_filter_to_modalites(modalite_qs, gestionnaire_ids, organisation_filter):
    if organisation_filter and organisation_filter != 'all':
        return modalite_qs.filter(gestionnaire_id=organisation_filter)

    if gestionnaire_ids is None:
        return modalite_qs

    if gestionnaire_ids:
        return modalite_qs.filter(gestionnaire_id__in=gestionnaire_ids)

    return modalite_qs.none()


@login_required
def analyse_consommation(request):
    """Page d'analyse de la consommation d'eau par habitant"""

    # Filtres
    annee_filter = request.GET.get('annee', str(datetime.now().year))
    regions_ids = request.GET.getlist('regions')
    districts_ids = request.GET.getlist('districts')
    communes_ids = request.GET.getlist('communes')
    villages_ids = request.GET.getlist('villages')
    parcelles_ids = request.GET.getlist('parcelles')
    ouvrages_ids = request.GET.getlist('ouvrages')
    types_pe_ids = request.GET.getlist('types_pe')
    modalite_paiement_filter = request.GET.get('modalite_paiement', '')
    organisation_state = _get_organisation_filter_state(request)
    gestionnaire_ids = organisation_state['gestionnaire_ids']
    organisation_filter = organisation_state['organisation_filter']
    organisations = organisation_state['organisations']

    # Récupérer les ouvrages selon la modalité de paiement sélectionnée
    modalite_query = ModaliteGestion.objects.filter(date_fin__isnull=True)

    if modalite_paiement_filter:
        # Filtrer par modalité spécifique
        if modalite_paiement_filter == 'au_volume':
            modalite_query = modalite_query.filter(modalitepaiement__in=['au_volume', 'mixte'])
        elif modalite_paiement_filter == 'forfaitaire':
            modalite_query = modalite_query.filter(modalitepaiement='forfaitaire')
        elif modalite_paiement_filter == 'mixte':
            modalite_query = modalite_query.filter(modalitepaiement='mixte')
    else:
        # Par défaut, seulement les modalités volumétriques (pour les relevés)
        modalite_query = modalite_query.filter(modalitepaiement__in=['au_volume', 'mixte'])

    modalite_query = _apply_organisation_filter_to_modalites(
        modalite_query,
        gestionnaire_ids,
        organisation_filter,
    )

    ouvrages_volumetriques_ids = modalite_query.values_list('ouvrage_id', flat=True).distinct()

    # Base queryset des points d'eau
    points_eau_qs = PointEau.objects.filter(
        ouvrage_id__in=ouvrages_volumetriques_ids
    ).select_related(
        'ouvrage',
        'parcelle__village__fokontany__commune__district__region',
        'type_point_eau'
    )

    # Filtrer par régions
    if regions_ids and regions_ids != ['']:
        points_eau_qs = points_eau_qs.filter(
            parcelle__village__fokontany__commune__district__region_id__in=regions_ids
        )

    # Filtrer par districts
    if districts_ids and districts_ids != ['']:
        points_eau_qs = points_eau_qs.filter(
            parcelle__village__fokontany__commune__district_id__in=districts_ids
        )

    # Filtrer par communes
    if communes_ids and communes_ids != ['']:
        points_eau_qs = points_eau_qs.filter(
            parcelle__village__fokontany__commune_id__in=communes_ids
        )

    if villages_ids and villages_ids != ['']:
        points_eau_qs = points_eau_qs.filter(
            parcelle__village_id__in=villages_ids
        )

    if parcelles_ids and parcelles_ids != ['']:
        points_eau_qs = points_eau_qs.filter(
            parcelle_id__in=parcelles_ids
        )

    # Filtrer par ouvrages
    if ouvrages_ids and ouvrages_ids != ['']:
        points_eau_qs = points_eau_qs.filter(ouvrage_id__in=ouvrages_ids)

    # Filtrer par types de points d'eau
    if types_pe_ids and types_pe_ids != ['']:
        points_eau_qs = points_eau_qs.filter(type_point_eau_id__in=types_pe_ids)

    # Récupérer les relevés de l'année avec volume > 0 (consommation réelle)
    # IMPORTANT: Pour l'analyse de consommation, on se base sur le volume, pas le montant
    # Ancien chargement complet des releves supprime: trop couteux sur gros volumes.

    # Filtrer par année ET volume > 0
    annee_int = int(annee_filter)

    # Optimisation: recharger uniquement les relevés utiles directement en base
    # pour éviter de conserver en mémoire tout l'historique des points d'eau.
    releves_annee = list(
        Releve.objects.filter(
            point_eau__in=points_eau_qs,
            datereleve__year=annee_int,
            volume_facture__gt=0,
        ).select_related(
            'point_eau__type_point_eau',
            'point_eau__parcelle',
            'point_eau__ouvrage',
        )
    )

    # Calculer la population totale et par type
    # Récupérer les IDs des parcelles avec parcelle non null
    points_eau_with_parcelle = points_eau_qs.exclude(parcelle__isnull=True)
    parcelles_ids = list(points_eau_with_parcelle.values_list('parcelle_id', flat=True).distinct())

    if parcelles_ids:
        parcelles = Parcelle.objects.filter(id__in=parcelles_ids)
        # Population totale des parcelles
        parcelles_list = list(parcelles)
        population_totale_parcelles = sum([p.nombre_habitants or 0 for p in parcelles_list])
    else:
        population_totale_parcelles = 0

    # Séparer les types de points d'eau selon modalité de paiement et type
    # Catégorie 1: BP (Branchements Privés) - 4 personnes par BP
    # Catégorie 2: BF (Branchements Forfaitaires) + BI (Bornes Individuelles) forfaitaires
    # Catégorie 3: Kiosques volumétriques
    # Catégorie 4: BI volumétriques

    points_eau_bp = []  # BP
    points_eau_kiosques_volume = []  # Kiosques avec modalité au volume
    points_eau_bi_volume = []  # BI avec modalité au volume
    points_eau_bf_bi_forfait = []  # BF + BI forfaitaires

    # Récupérer les ouvrages avec modalité forfaitaire
    ouvrages_forfaitaires_ids = ModaliteGestion.objects.filter(
        date_fin__isnull=True,
        modalitepaiement__in=['forfaitaire']
    ).values_list('ouvrage_id', flat=True).distinct()

    ouvrages_forfaitaires_ids = {str(_id) for _id in ouvrages_forfaitaires_ids}

    for pe in points_eau_qs:
        if pe.type_point_eau:
            type_nom = pe.type_point_eau.nom_type.upper() if pe.type_point_eau.nom_type else ''
            est_forfaitaire = str(pe.ouvrage_id) in ouvrages_forfaitaires_ids

            if 'BP' in type_nom or ('BRANCHEMENT' in type_nom and 'PRIVÉ' in type_nom) or 'PRIVE' in type_nom:
                # Branchement Privé
                points_eau_bp.append(pe)
            elif 'KIOSQUE' in type_nom:
                if est_forfaitaire:
                    points_eau_bf_bi_forfait.append(pe)
                else:
                    points_eau_kiosques_volume.append(pe)
            elif 'BI' in type_nom or 'BORNE' in type_nom:
                if est_forfaitaire:
                    points_eau_bf_bi_forfait.append(pe)
                else:
                    points_eau_bi_volume.append(pe)
            elif 'BF' in type_nom or ('BRANCHEMENT' in type_nom and 'FORFAIT' in type_nom):
                # Branchement Forfaitaire
                points_eau_bf_bi_forfait.append(pe)
            else:
                # Par défaut, on classe dans les forfaitaires/BI
                points_eau_bf_bi_forfait.append(pe)
        else:
            points_eau_bf_bi_forfait.append(pe)

    # Calculs population
    nb_bp = len(points_eau_bp)
    nb_kiosques_volume = len(points_eau_kiosques_volume)
    nb_bi_volume = len(points_eau_bi_volume)
    nb_bf_bi_forfait = len(points_eau_bf_bi_forfait)

    population_bp = nb_bp * 4  # 4 personnes par BP

    # Répartir le reste de la population entre les 3 autres catégories
    population_restante = max(0, population_totale_parcelles - population_bp)
    nb_autres_total = nb_kiosques_volume + nb_bi_volume + nb_bf_bi_forfait

    if nb_autres_total > 0:
        # Répartir proportionnellement
        population_kiosques_volume_brut = int((nb_kiosques_volume / nb_autres_total) * population_restante)
        population_bi_volume = int((nb_bi_volume / nb_autres_total) * population_restante)
        population_bf_bi_forfait = population_restante - population_kiosques_volume_brut - population_bi_volume
    else:
        population_kiosques_volume_brut = 0
        population_bi_volume = 0
        population_bf_bi_forfait = 0

    # NOTE: population_cartes_sociales sera calculée plus tard (ligne 380+)
    # On garde la valeur brute pour l'instant et on la soustraira après
    population_kiosques_volume = population_kiosques_volume_brut

    population_totale = population_bp + population_kiosques_volume + population_bi_volume + population_bf_bi_forfait

    # Analyser les consommations par mois avec répartition sur la période
    # IMPORTANT: Répartir le volume entre le relevé précédent et l'actuel
    from datetime import date
    from dateutil.relativedelta import relativedelta

    mois_liste = list(range(1, 13))
    consommations_par_mois = {mois: [] for mois in mois_liste}
    volumes_par_mois = {mois: 0 for mois in mois_liste}
    montants_par_mois = {mois: 0 for mois in mois_liste}
    volumes_annuels_par_pe = defaultdict(float)
    volumes_pe_mois = defaultdict(lambda: defaultdict(float))   # {pe_id: {mois: volume}} pour moyenne/médiane par point d'eau
    jours_couverts_pe = defaultdict(int)                        # {pe_id: jours de l'année couverts par les relevés}
    mois_actifs_par_pe = defaultdict(set)
    volumes_par_type_mois = {
        'bp': {mois: 0 for mois in mois_liste},
        'kiosques': {mois: 0 for mois in mois_liste},
        'kiosques_cartes_sociales': {mois: 0 for mois in mois_liste},
        'kiosques_hors_cartes': {mois: 0 for mois in mois_liste},
        'bi': {mois: 0 for mois in mois_liste},
        'bf_bi': {mois: 0 for mois in mois_liste}
    }

    pe_type_mapping = {}
    for pe in points_eau_bp:
        pe_type_mapping[str(pe.id)] = 'bp'
    for pe in points_eau_kiosques_volume:
        pe_type_mapping[str(pe.id)] = 'kiosques'
    for pe in points_eau_bi_volume:
        pe_type_mapping[str(pe.id)] = 'bi'
    for pe in points_eau_bf_bi_forfait:
        pe_type_mapping[str(pe.id)] = 'bf_bi'

    consos_cartes_sociales = ConsoCarteSociale.objects.filter(
        carte_sociale__point_eau__in=points_eau_qs,
        date__year=annee_int
    ).select_related('carte_sociale__point_eau')

    volumes_cartes_sociales_par_pe_mois = {}
    for conso in consos_cartes_sociales:
        if conso.date and conso.carte_sociale and conso.carte_sociale.point_eau:
            pe_id = str(conso.carte_sociale.point_eau.id)
            mois = conso.date.month

            if pe_id not in volumes_cartes_sociales_par_pe_mois:
                volumes_cartes_sociales_par_pe_mois[pe_id] = {m: 0 for m in mois_liste}

            volumes_cartes_sociales_par_pe_mois[pe_id][mois] += float(conso.volume_total or 0)

    # Grouper les relevés par point d'eau
    releves_par_pe = {}
    for releve in releves_annee:
        pe_id = str(releve.point_eau_id)
        if pe_id not in releves_par_pe:
            releves_par_pe[pe_id] = []
        releves_par_pe[pe_id].append(releve)

    # Éviter les requêtes N+1 pour retrouver le relevé précédent de chaque point d'eau.
    pe_ids = list(releves_par_pe.keys())
    debut_annee = datetime(annee_int, 1, 1).date()
    derniers_releves_avant_annee = {
        str(row['point_eau_id']): row['last_date']
        for row in Releve.objects.filter(
            point_eau_id__in=pe_ids,
            datereleve__lt=debut_annee
        ).values('point_eau_id').annotate(last_date=Max('datereleve'))
    }

    # Pour chaque point d'eau, analyser les relevés successifs
    for pe_id, releves_pe in releves_par_pe.items():
        # Trier les relevés par date
        releves_pe_sorted = sorted(releves_pe, key=lambda r: r.datereleve)

        for i, releve in enumerate(releves_pe_sorted):
            if not releve.datereleve:
                continue

            volume = float(releve.volume_facture) if releve.volume_facture else 0
            montant_total_releve = float(releve.montant or 0)
            if volume <= 0:
                continue

            # Chercher le relevé précédent (dans l'année ou avant)
            date_debut = None
            if i > 0:
                # Relevé précédent dans la liste
                date_debut = releves_pe_sorted[i-1].datereleve
            else:
                date_precedente = derniers_releves_avant_annee.get(pe_id)
                if date_precedente:
                    date_debut = date_precedente
                else:
                    # Pas de relevé précédent, supposer début du mois du relevé
                    date_debut = releve.datereleve.replace(day=1)

            date_fin = releve.datereleve

            # Calculer le nombre de jours entre les deux relevés
            delta_jours = (date_fin - date_debut).days
            if delta_jours <= 0:
                delta_jours = 1  # Au moins 1 jour

            # Calculer la consommation journalière moyenne
            conso_journaliere = volume / delta_jours

            # Répartir la consommation sur tous les mois de la période
            # Important: On parcourt TOUS les mois de date_debut à date_fin, même si date_debut < année analysée
            date_courante = date_debut
            while date_courante <= date_fin:
                mois = date_courante.month
                annee_courante = date_courante.year

                # Calculer le nombre de jours dans ce mois pour cette période
                # Début: soit le 1er du mois, soit date_debut si on est dans le mois de départ
                if date_courante.year == date_debut.year and date_courante.month == date_debut.month:
                    debut_mois = date_debut
                else:
                    debut_mois = date_courante.replace(day=1)

                # Fin: soit le dernier jour du mois, soit date_fin si on est dans le mois d'arrivée
                if date_courante.month == 12:
                    dernier_jour_mois = date_courante.replace(year=date_courante.year + 1, month=1, day=1) - relativedelta(days=1)
                else:
                    dernier_jour_mois = date_courante.replace(month=date_courante.month + 1, day=1) - relativedelta(days=1)

                if date_courante.year == date_fin.year and date_courante.month == date_fin.month:
                    fin_mois = date_fin
                else:
                    fin_mois = dernier_jour_mois

                # Nombre de jours dans ce mois pour cette période
                jours_dans_mois = (fin_mois - debut_mois).days + 1

                # Volume et montant pour ce mois
                volume_mois = conso_journaliere * jours_dans_mois
                montant_mois = (montant_total_releve / delta_jours) * jours_dans_mois if montant_total_releve > 0 else 0

                # IMPORTANT: On enregistre SEULEMENT si on est dans l'année analysée
                if annee_courante == annee_int and volume_mois > 0:
                    consommations_par_mois[mois].append(volume_mois)
                    volumes_par_mois[mois] += volume_mois
                    montants_par_mois[mois] += montant_mois
                    volumes_annuels_par_pe[pe_id] += volume_mois
                    volumes_pe_mois[pe_id][mois] += volume_mois
                    jours_couverts_pe[pe_id] += jours_dans_mois
                    mois_actifs_par_pe[pe_id].add(mois)
                    pe_type = pe_type_mapping.get(pe_id, 'bf_bi')
                    volumes_par_type_mois[pe_type][mois] += volume_mois

                    if pe_type == 'kiosques':
                        volume_cartes_sociales = min(
                            volumes_cartes_sociales_par_pe_mois.get(pe_id, {}).get(mois, 0),
                            volume_mois,
                        )
                        volumes_par_type_mois['kiosques_cartes_sociales'][mois] += volume_cartes_sociales
                        volumes_par_type_mois['kiosques_hors_cartes'][mois] += max(0, volume_mois - volume_cartes_sociales)

                # Passer au mois suivant
                if date_courante.month == 12:
                    date_courante = date_courante.replace(year=date_courante.year + 1, month=1, day=1)
                else:
                    date_courante = date_courante.replace(month=date_courante.month + 1, day=1)

    # Calculer les statistiques par mois
    stats_par_mois = []
    for mois in mois_liste:
        consommations = consommations_par_mois[mois]
        volume_total = volumes_par_mois[mois]
        montant_total = montants_par_mois[mois]

        if len(consommations) > 0:
            # Moyenne
            moyenne = sum(consommations) / len(consommations)

            # Médiane
            consommations_sorted = sorted(consommations)
            n = len(consommations_sorted)
            if n % 2 == 0:
                mediane = (consommations_sorted[n//2 - 1] + consommations_sorted[n//2]) / 2
            else:
                mediane = consommations_sorted[n//2]

            # Consommation par habitant (litre/hab/jour)
            if population_totale > 0:
                # Volume mensuel / population / nombre de jours dans le mois
                jours_mois = 30  # Approximation
                if mois in [1, 3, 5, 7, 8, 10, 12]:
                    jours_mois = 31
                elif mois == 2:
                    jours_mois = 28  # Ignorer les années bissextiles pour simplifier

                conso_hab_jour = (volume_total * 1000) / population_totale / jours_mois  # Convertir m³ en litres
            else:
                conso_hab_jour = 0

            stats_par_mois.append({
                'mois': mois,
                'mois_numero': mois,
                'mois_nom': ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                            'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'][mois],
                'volume_total': volume_total,
                'montant_total': montant_total,
                'nb_releves': len(consommations),
                'moyenne': moyenne,
                'mediane': mediane,
                'conso_hab_jour': conso_hab_jour
            })
        else:
            stats_par_mois.append({
                'mois': mois,
                'mois_numero': mois,
                'mois_nom': ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                            'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'][mois],
                'volume_total': 0,
                'montant_total': 0,
                'nb_releves': 0,
                'moyenne': 0,
                'mediane': 0,
                'conso_hab_jour': 0
            })

    # Statistiques globales annuelles
    volume_total_annuel = sum([s['volume_total'] for s in stats_par_mois])
    nb_releves_total = sum([s['nb_releves'] for s in stats_par_mois])

    montant_total_annuel = sum([s['montant_total'] for s in stats_par_mois])

    nb_jours_couverts = sum(
        _days_in_month(annee_int, s['mois_numero'])
        for s in stats_par_mois
        if s['nb_releves'] > 0
    )

    if population_totale > 0 and volume_total_annuel > 0 and nb_jours_couverts > 0:
        conso_hab_jour_annuelle = (volume_total_annuel * 1000) / population_totale / nb_jours_couverts
    else:
        conso_hab_jour_annuelle = 0

    # Calculer toutes les consommations pour la médiane annuelle
    toutes_consommations = []
    for mois_data in consommations_par_mois.values():
        toutes_consommations.extend(mois_data)

    if len(toutes_consommations) > 0:
        consommations_sorted = sorted(toutes_consommations)
        n = len(consommations_sorted)
        if n % 2 == 0:
            mediane_annuelle = (consommations_sorted[n//2 - 1] + consommations_sorted[n//2]) / 2
        else:
            mediane_annuelle = consommations_sorted[n//2]
        moyenne_annuelle = sum(toutes_consommations) / len(toutes_consommations)
    else:
        mediane_annuelle = 0
        moyenne_annuelle = 0

    # Moyenne / médiane de consommation par point d'eau, par type (kiosques : par type d'abonné)
    pe_segments = {
        str(pe.id): _segment_conso_point_eau(
            getattr(pe.type_point_eau, 'nom_type', None), getattr(pe, 'typeabonne', None)
        )
        for pe in points_eau_qs
    }
    stats_pe_segments = calculer_stats_conso_par_point_eau(pe_segments, volumes_pe_mois)

    # Kiosques à faible consommation (« BP déguisés ») : moyenne mensuelle sous le seuil (10 m³ par défaut)
    try:
        seuil_kiosque_bp = float(str(request.GET.get('seuil_kiosque', SEUIL_KIOSQUE_BP_DEGUISE)).replace(',', '.'))
    except ValueError:
        seuil_kiosque_bp = SEUIL_KIOSQUE_BP_DEGUISE
    filtre_institutionnel = request.GET.get('institutionnel', 'tous')
    if filtre_institutionnel not in ('tous', 'non', 'oui'):
        filtre_institutionnel = 'tous'
    kiosques_bp_deguises = lister_kiosques_faible_conso(
        points_eau_qs, volumes_pe_mois, jours_couverts_pe, seuil_kiosque_bp, filtre_institutionnel,
    )
    nb_kiosques_institutionnels = sum(1 for k in kiosques_bp_deguises if k['institutionnel'])

    bp_point_ids = {str(pe.id) for pe in points_eau_bp}
    bp_tranche_counts = {
        'moins_3': 0,
        'entre_3_10': 0,
        'plus_10': 0,
    }
    bp_tranche_percentages = {
        'moins_3': 0,
        'entre_3_10': 0,
        'plus_10': 0,
    }
    nb_bp_analyses = 0

    for pe_id in bp_point_ids:
        total_volume = float(volumes_annuels_par_pe.get(pe_id, 0))
        active_months = len(mois_actifs_par_pe.get(pe_id, set()))
        if total_volume <= 0 or active_months <= 0:
            continue

        nb_bp_analyses += 1
        moyenne_mensuelle_bp = total_volume / active_months

        if moyenne_mensuelle_bp < 3:
            bp_tranche_counts['moins_3'] += 1
        elif moyenne_mensuelle_bp <= 10:
            bp_tranche_counts['entre_3_10'] += 1
        else:
            bp_tranche_counts['plus_10'] += 1

    if nb_bp_analyses > 0:
        bp_tranche_percentages = {
            key: round((value / nb_bp_analyses) * 100, 1)
            for key, value in bp_tranche_counts.items()
        }


    # Calculer la population des cartes sociales (nécessaire pour les calculs de conso/hab)
    # Filtrer les cartes sociales actives liées aux ouvrages sélectionnés
    cartes_sociales_qs = CarteSociale.objects.filter(
        statut='active',
        ouvrage__in=points_eau_qs.values_list('ouvrage_id', flat=True).distinct()
    )

    population_cartes_sociales = 0
    for carte in cartes_sociales_qs:
        if carte.nombre_habitants and carte.nombre_habitants > 0:
            population_cartes_sociales += carte.nombre_habitants
        else:
            population_cartes_sociales += 4  # Hypothèse : 4 personnes par carte (comme les BP)

    # Les volumes par type sont déjà calculés pendant la répartition principale
    # des relevés, pour éviter un second parcours complet des données.

    # Calculer les consommations par habitant par type
    conso_hab_par_type_mois = {
        'bp': {mois: 0 for mois in mois_liste},
        'kiosques': {mois: 0 for mois in mois_liste},
        'kiosques_cartes_sociales': {mois: 0 for mois in mois_liste},
        'kiosques_hors_cartes': {mois: 0 for mois in mois_liste},
        'bi': {mois: 0 for mois in mois_liste},
        'bf_bi': {mois: 0 for mois in mois_liste}
    }

    populations = {
        'bp': population_bp,
        'kiosques': population_kiosques_volume,
        'kiosques_cartes_sociales': population_cartes_sociales,  # Population des cartes sociales
        'kiosques_hors_cartes': max(0, population_kiosques_volume - population_cartes_sociales),  # Reste de la population kiosques
        'bi': population_bi_volume,
        'bf_bi': population_bf_bi_forfait
    }

    for pe_type in ['bp', 'kiosques', 'kiosques_cartes_sociales', 'kiosques_hors_cartes', 'bi', 'bf_bi']:
        pop = populations[pe_type]
        if pop > 0:
            for mois in mois_liste:
                # Jours dans le mois
                jours_mois = 30
                if mois in [1, 3, 5, 7, 8, 10, 12]:
                    jours_mois = 31
                elif mois == 2:
                    jours_mois = 28

                volume_mois = volumes_par_type_mois[pe_type][mois]
                conso_hab_par_type_mois[pe_type][mois] = (volume_mois * 1000) / pop / jours_mois

    # Préparer les données pour les graphiques (format JSON). Pour l'année
    # courante, ne dessiner que les mois entièrement terminés.
    import json
    visible_month_count = _visible_month_count(annee_int)
    visible_stats_par_mois = stats_par_mois[:visible_month_count]
    visible_mois_liste = mois_liste[:visible_month_count]
    graphique_volumes = {
        'labels': [s['mois_nom'][:3] for s in visible_stats_par_mois],  # Jan, Fév, Mar...
        'volumes': [round(s['volume_total'], 2) for s in visible_stats_par_mois],
        'volumes_bp': [round(volumes_par_type_mois['bp'][mois], 2) for mois in visible_mois_liste],
        'volumes_kiosques': [round(volumes_par_type_mois['kiosques'][mois], 2) for mois in visible_mois_liste],
        'volumes_kiosques_cartes_sociales': [round(volumes_par_type_mois['kiosques_cartes_sociales'][mois], 2) for mois in visible_mois_liste],
        'volumes_kiosques_hors_cartes': [round(volumes_par_type_mois['kiosques_hors_cartes'][mois], 2) for mois in visible_mois_liste],
        'volumes_bi': [round(volumes_par_type_mois['bi'][mois], 2) for mois in visible_mois_liste],
        'volumes_bf_bi': [round(volumes_par_type_mois['bf_bi'][mois], 2) for mois in visible_mois_liste],
        'conso_hab': [round(s['conso_hab_jour'], 1) for s in visible_stats_par_mois],
        'conso_hab_bp': [round(conso_hab_par_type_mois['bp'][mois], 1) for mois in visible_mois_liste],
        'conso_hab_kiosques': [round(conso_hab_par_type_mois['kiosques'][mois], 1) for mois in visible_mois_liste],
        'conso_hab_kiosques_cartes_sociales': [round(conso_hab_par_type_mois['kiosques_cartes_sociales'][mois], 1) for mois in visible_mois_liste],
        'conso_hab_kiosques_hors_cartes': [round(conso_hab_par_type_mois['kiosques_hors_cartes'][mois], 1) for mois in visible_mois_liste],
        'conso_hab_bi': [round(conso_hab_par_type_mois['bi'][mois], 1) for mois in visible_mois_liste],
        'conso_hab_bf_bi': [round(conso_hab_par_type_mois['bf_bi'][mois], 1) for mois in visible_mois_liste],
        'montants': [round(s['montant_total'], 2) for s in visible_stats_par_mois],
        'bp_tranches_labels': ['Moins de 3 m³', 'Entre 3 et 10 m³', 'Plus de 10 m³'],
        'bp_tranches_counts': [
            bp_tranche_counts['moins_3'],
            bp_tranche_counts['entre_3_10'],
            bp_tranche_counts['plus_10'],
        ],
        'bp_tranches_percentages': [
            bp_tranche_percentages['moins_3'],
            bp_tranche_percentages['entre_3_10'],
            bp_tranche_percentages['plus_10'],
        ]
    }

    # Listes pour les dropdowns - Filtrer SEULEMENT les entités qui ont des relevés
    # Récupérer tous les points d'eau qui ont des relevés

    # Listes pour les dropdowns - limiter aux points d'eau presents dans l'annee analysee
    points_eau_avec_releves = points_eau_qs.filter(id__in={releve.point_eau_id for releve in releves_annee if releve.point_eau_id})
    # Extraire les IDs des entités géographiques liées à ces points d'eau
    communes_ids_avec_releves = points_eau_avec_releves.exclude(
        parcelle__village__fokontany__commune__isnull=True
    ).values_list('parcelle__village__fokontany__commune_id', flat=True).distinct()

    districts_ids_avec_releves = points_eau_avec_releves.exclude(
        parcelle__village__fokontany__commune__district__isnull=True
    ).values_list('parcelle__village__fokontany__commune__district_id', flat=True).distinct()

    regions_ids_avec_releves = points_eau_avec_releves.exclude(
        parcelle__village__fokontany__commune__district__region__isnull=True
    ).values_list('parcelle__village__fokontany__commune__district__region_id', flat=True).distinct()

    types_pe_ids_avec_releves = points_eau_avec_releves.exclude(
        type_point_eau__isnull=True
    ).values_list('type_point_eau_id', flat=True).distinct()

    villages_ids_avec_releves = points_eau_avec_releves.exclude(
        parcelle__village__isnull=True
    ).values_list('parcelle__village_id', flat=True).distinct()

    parcelles_ids_avec_releves = points_eau_avec_releves.exclude(
        parcelle__isnull=True
    ).values_list('parcelle_id', flat=True).distinct()

    # Filtrer les listes pour n'afficher que celles qui ont des relevés
    regions = Region.objects.filter(id__in=regions_ids_avec_releves).order_by('nom_region')
    districts = District.objects.filter(id__in=districts_ids_avec_releves).order_by('nom_district')
    communes = Commune.objects.filter(id__in=communes_ids_avec_releves).order_by('nom_commune')
    villages = Village.objects.filter(id__in=villages_ids_avec_releves).order_by('nom_village')
    parcelles = Parcelle.objects.filter(id__in=parcelles_ids_avec_releves).order_by('reference_parcelle')
    ouvrages = Ouvrage.objects.filter(id__in=ouvrages_volumetriques_ids).order_by('nom_ouvrage')
    types_pe = TypePointEau.objects.filter(id__in=types_pe_ids_avec_releves).order_by('nom_type')

    # Statistiques des ouvrages et villages desservis
    # Calculer à partir des points d'eau qui ont réellement des relevés
    tous_points_eau_avec_releves = (points_eau_bp + points_eau_kiosques_volume +
                                    points_eau_bi_volume + points_eau_bf_bi_forfait)

    # Nombre d'ouvrages uniques
    ouvrages_ids_avec_releves = set()
    for pe in tous_points_eau_avec_releves:
        if pe.ouvrage_id:
            ouvrages_ids_avec_releves.add(pe.ouvrage_id)
    nb_ouvrages = len(ouvrages_ids_avec_releves)

    # Nombre de villages desservis
    villages_ids_desservis = set()
    for pe in tous_points_eau_avec_releves:
        if pe.parcelle and pe.parcelle.village_id:
            villages_ids_desservis.add(pe.parcelle.village_id)
    nb_villages_desservis = len(villages_ids_desservis)

    # Statistiques des cartes sociales (déjà calculées plus haut, mais on recalcule avec les bons ouvrages)
    if ouvrages_ids_avec_releves:
        cartes_sociales_qs_filtered = cartes_sociales_qs.filter(ouvrage_id__in=ouvrages_ids_avec_releves)
        nb_cartes_sociales = cartes_sociales_qs_filtered.count()
        # Recalculer la population des cartes sociales avec le bon filtre
        population_cartes_sociales = 0
        for carte in cartes_sociales_qs_filtered:
            if carte.nombre_habitants and carte.nombre_habitants > 0:
                population_cartes_sociales += carte.nombre_habitants
            else:
                population_cartes_sociales += 4
    else:
        nb_cartes_sociales = 0
        population_cartes_sociales = 0

    # Soustraire la population des cartes sociales de celle des kiosques
    # Les cartes sociales utilisent les kiosques, donc leur population doit être déduite
    population_kiosques_hors_cartes_sociales = max(0, population_kiosques_volume - population_cartes_sociales)

    # Recalculer le total avec la bonne répartition
    population_totale_avec_cartes = (population_bp + population_cartes_sociales +
                                     population_kiosques_hors_cartes_sociales +
                                     population_bi_volume + population_bf_bi_forfait)

    # Calculer les pourcentages
    if population_totale_avec_cartes > 0:
        pct_bp = int((population_bp / population_totale_avec_cartes) * 100)
        pct_cartes_sociales = int((population_cartes_sociales / population_totale_avec_cartes) * 100)
        pct_kiosques = int((population_kiosques_hors_cartes_sociales / population_totale_avec_cartes) * 100)
        pct_bi = int((population_bi_volume / population_totale_avec_cartes) * 100)
        pct_bf_bi = int((population_bf_bi_forfait / population_totale_avec_cartes) * 100)
        ratio_population_cartes_sociales = pct_cartes_sociales
    else:
        pct_bp = 0
        pct_cartes_sociales = 0
        pct_kiosques = 0
        pct_bi = 0
        pct_bf_bi = 0
        ratio_population_cartes_sociales = 0

    context = {
        'title': 'Analyse de la Consommation d\'Eau',
        'annee_filter': annee_filter,
        'regions_ids': regions_ids,
        'districts_ids': districts_ids,
        'communes_ids': communes_ids,
        'villages_ids': villages_ids,
        'parcelles_ids': parcelles_ids,
        'ouvrages_ids': ouvrages_ids,
        'types_pe_ids': types_pe_ids,
        'organisation_filter': organisation_filter,
        'modalite_paiement_filter': modalite_paiement_filter,
        'organisations': organisations,
        'regions': regions,
        'districts': districts,
        'communes': communes,
        'villages': villages,
        'parcelles': parcelles,
        'ouvrages': ouvrages,
        'types_pe': types_pe,
        'population_totale': population_totale_avec_cartes,
        'population_bp': population_bp,
        'population_kiosques_volume': population_kiosques_hors_cartes_sociales,
        'population_bi_volume': population_bi_volume,
        'population_bf_bi_forfait': population_bf_bi_forfait,
        'nb_bp': nb_bp,
        'nb_kiosques_volume': nb_kiosques_volume,
        'nb_bi_volume': nb_bi_volume,
        'nb_bf_bi_forfait': nb_bf_bi_forfait,
        'volume_total_annuel': volume_total_annuel,
        'montant_total_annuel': montant_total_annuel,
        'nb_releves_total': nb_releves_total,
        'nb_jours_couverts': nb_jours_couverts,
        'conso_hab_jour_annuelle': conso_hab_jour_annuelle,
        'mediane_annuelle': mediane_annuelle,
        'moyenne_annuelle': moyenne_annuelle,
        'stats_par_mois': stats_par_mois,
        'graphique_volumes_json': json.dumps(graphique_volumes),
        'stats_pe_segments': stats_pe_segments,
        'kiosques_bp_deguises': kiosques_bp_deguises,
        'seuil_kiosque_bp': seuil_kiosque_bp,
        'filtre_institutionnel': filtre_institutionnel,
        'nb_kiosques_institutionnels': nb_kiosques_institutionnels,
        'stats_pe_segments_json': json.dumps({
            'labels_mois': graphique_volumes['labels'],
            'nb_mois_visibles': visible_month_count,
            'segments': stats_pe_segments,
        }),
        # Nouvelles statistiques
        'nb_ouvrages': nb_ouvrages,
        'nb_villages_desservis': nb_villages_desservis,
        'nb_cartes_sociales': nb_cartes_sociales,
        'population_cartes_sociales': population_cartes_sociales,
        'ratio_population_cartes_sociales': ratio_population_cartes_sociales,
        # Pourcentages
        'pct_bp': pct_bp,
        'pct_cartes_sociales': pct_cartes_sociales,
        'pct_kiosques': pct_kiosques,
        'pct_bi': pct_bi,
        'pct_bf_bi': pct_bf_bi,
        'nb_bp_analyses': nb_bp_analyses,
        'bp_tranche_moins_3': bp_tranche_counts['moins_3'],
        'bp_tranche_entre_3_10': bp_tranche_counts['entre_3_10'],
        'bp_tranche_plus_10': bp_tranche_counts['plus_10'],
        'bp_tranche_pct_moins_3': bp_tranche_percentages['moins_3'],
        'bp_tranche_pct_entre_3_10': bp_tranche_percentages['entre_3_10'],
        'bp_tranche_pct_plus_10': bp_tranche_percentages['plus_10'],
    }

    # Le widget de consommation réutilise volontairement ce calcul complet :
    # la page d'analyse et les widgets partagent ainsi une seule source de vérité.
    if request.GET.get('format') == 'widget_json':
        query = request.GET.copy()
        query.pop('format', None)
        return JsonResponse({
            'success': True,
            'annee': annee_int,
            'stats': {
                'nb_ouvrages': nb_ouvrages,
                'population': population_totale_avec_cartes,
                'volume_consomme': round(volume_total_annuel, 2),
                'conso_hab_jour': round(conso_hab_jour_annuelle, 1),
            },
            'charts': {
                'labels': graphique_volumes['labels'],
                'volumes': graphique_volumes['volumes'],
                'conso_hab': graphique_volumes['conso_hab'],
            },
            'full_url': f"/plannings/volumetrique/analyse-consommation/?{query.urlencode()}",
        })

    return render(request, 'planning/analyse_consommation.html', context)


@login_required
def api_ouvrages_filtre_cascade(request):
    """API pour récupérer les ouvrages filtrés par commune (filtrage en cascade)"""
    from django.http import JsonResponse

    communes_ids = request.GET.getlist('communes')
    modalite_paiement_filter = request.GET.get('modalite_paiement', '')
    organisation_state = _get_organisation_filter_state(request)
    gestionnaire_ids = organisation_state['gestionnaire_ids']
    organisation_filter = organisation_state['organisation_filter']

    # Récupérer les ouvrages selon la modalité de paiement
    modalite_query = ModaliteGestion.objects.filter(date_fin__isnull=True)

    if modalite_paiement_filter:
        if modalite_paiement_filter == 'au_volume':
            modalite_query = modalite_query.filter(modalitepaiement__in=['au_volume', 'mixte'])
        elif modalite_paiement_filter == 'forfaitaire':
            modalite_query = modalite_query.filter(modalitepaiement='forfaitaire')
        elif modalite_paiement_filter == 'mixte':
            modalite_query = modalite_query.filter(modalitepaiement='mixte')
    else:
        # Par défaut: au volume
        modalite_query = modalite_query.filter(modalitepaiement__in=['au_volume', 'mixte'])

    modalite_query = _apply_organisation_filter_to_modalites(
        modalite_query,
        gestionnaire_ids,
        organisation_filter,
    )

    ouvrages_modalite_ids = list(modalite_query.values_list('ouvrage_id', flat=True).distinct())

    # Si des communes sont sélectionnées, filtrer les ouvrages qui ont des points d'eau dans ces communes
    if communes_ids and communes_ids != ['']:
        points_eau_commune = PointEau.objects.filter(
            parcelle__village__fokontany__commune_id__in=communes_ids,
            ouvrage_id__in=ouvrages_modalite_ids,
            releves__isnull=False  # Seulement ceux qui ont des relevés
        ).select_related('ouvrage').distinct()

        ouvrages_ids = points_eau_commune.values_list('ouvrage_id', flat=True).distinct()
        ouvrages = Ouvrage.objects.filter(id__in=ouvrages_ids).order_by('nom_ouvrage')
    else:
        # Pas de filtre commune: tous les ouvrages de la modalité qui ont des relevés
        points_eau_avec_releves = PointEau.objects.filter(
            ouvrage_id__in=ouvrages_modalite_ids,
            releves__isnull=False
        ).select_related('ouvrage').distinct()

        ouvrages_ids = points_eau_avec_releves.values_list('ouvrage_id', flat=True).distinct()
        ouvrages = Ouvrage.objects.filter(id__in=ouvrages_ids).order_by('nom_ouvrage')

    # Retourner la liste des ouvrages
    ouvrages_data = [
        {
            'id': str(ouvrage.id),
            'nom': ouvrage.nom_ouvrage
        }
        for ouvrage in ouvrages
    ]

    return JsonResponse({
        'success': True,
        'ouvrages': ouvrages_data
    })


@login_required
def api_filtres_cascade_consommation(request):
    annee_filter = request.GET.get('annee', str(datetime.now().year))
    regions_ids = request.GET.getlist('regions')
    districts_ids = request.GET.getlist('districts')
    communes_ids = request.GET.getlist('communes')
    villages_ids = request.GET.getlist('villages')
    parcelles_ids = request.GET.getlist('parcelles')
    ouvrages_ids = request.GET.getlist('ouvrages')
    modalite_paiement_filter = request.GET.get('modalite_paiement', '')
    organisation_state = _get_organisation_filter_state(request)
    gestionnaire_ids = organisation_state['gestionnaire_ids']
    organisation_filter = organisation_state['organisation_filter']

    ouvrages_modalite_ids = _get_modalite_ouvrages_ids(
        gestionnaire_ids,
        organisation_filter,
        modalite_paiement_filter,
    )

    annee_int = int(annee_filter)
    point_ids_with_releves = Releve.objects.filter(
        datereleve__year=annee_int,
        volume_facture__gt=0,
    ).values_list('point_eau_id', flat=True).distinct()

    base_points_qs = PointEau.objects.filter(
        id__in=point_ids_with_releves,
        ouvrage_id__in=ouvrages_modalite_ids,
    ).select_related(
        'ouvrage',
        'type_point_eau',
        'parcelle__village__fokontany__commune__district__region',
    )

    pe_for_districts = base_points_qs
    if regions_ids and regions_ids != ['']:
        pe_for_districts = pe_for_districts.filter(
            parcelle__village__fokontany__commune__district__region_id__in=regions_ids
        )

    pe_for_communes = pe_for_districts
    if districts_ids and districts_ids != ['']:
        pe_for_communes = pe_for_communes.filter(
            parcelle__village__fokontany__commune__district_id__in=districts_ids
        )

    pe_for_villages = pe_for_communes
    if communes_ids and communes_ids != ['']:
        pe_for_villages = pe_for_villages.filter(
            parcelle__village__fokontany__commune_id__in=communes_ids
        )

    pe_for_parcelles = pe_for_villages
    if villages_ids and villages_ids != ['']:
        pe_for_parcelles = pe_for_parcelles.filter(
            parcelle__village_id__in=villages_ids
        )

    pe_for_ouvrages = pe_for_parcelles
    if parcelles_ids and parcelles_ids != ['']:
        pe_for_ouvrages = pe_for_ouvrages.filter(parcelle_id__in=parcelles_ids)

    pe_for_types = pe_for_ouvrages
    if ouvrages_ids and ouvrages_ids != ['']:
        pe_for_types = pe_for_types.filter(ouvrage_id__in=ouvrages_ids)

    districts = District.objects.filter(
        id__in=pe_for_districts.exclude(
            parcelle__village__fokontany__commune__district__isnull=True
        ).values_list('parcelle__village__fokontany__commune__district_id', flat=True).distinct()
    ).order_by('nom_district')

    communes = Commune.objects.filter(
        id__in=pe_for_communes.exclude(
            parcelle__village__fokontany__commune__isnull=True
        ).values_list('parcelle__village__fokontany__commune_id', flat=True).distinct()
    ).order_by('nom_commune')

    villages = Village.objects.filter(
        id__in=pe_for_villages.exclude(
            parcelle__village__isnull=True
        ).values_list('parcelle__village_id', flat=True).distinct()
    ).order_by('nom_village')

    parcelles = Parcelle.objects.filter(
        id__in=pe_for_parcelles.exclude(
            parcelle__isnull=True
        ).values_list('parcelle_id', flat=True).distinct()
    ).order_by('reference_parcelle')

    ouvrages = Ouvrage.objects.filter(
        id__in=pe_for_ouvrages.exclude(ouvrage__isnull=True).values_list('ouvrage_id', flat=True).distinct()
    ).order_by('nom_ouvrage')
    modalite_by_ouvrage = _get_modalite_by_ouvrage_ids(
        [item.id for item in ouvrages],
        gestionnaire_ids,
        organisation_filter,
    )
    geo_by_ouvrage = _get_geo_by_ouvrage_ids(list(pe_for_ouvrages))

    types_pe = TypePointEau.objects.filter(
        id__in=pe_for_types.exclude(type_point_eau__isnull=True).values_list('type_point_eau_id', flat=True).distinct()
    ).order_by('nom_type')

    return JsonResponse({
        'success': True,
        'districts': [{'id': str(item.id), 'nom': item.nom_district} for item in districts],
        'communes': [{'id': str(item.id), 'nom': item.nom_commune} for item in communes],
        'villages': [{'id': str(item.id), 'nom': item.nom_village} for item in villages],
        'parcelles': [{'id': str(item.id), 'nom': item.reference_parcelle or f'Parcelle {item.id}'} for item in parcelles],
        'ouvrages': [
            {
                'id': str(item.id),
                'nom': item.nom_ouvrage,
                'modalite_code': modalite_by_ouvrage.get(str(item.id), {}).get('code', 'inconnue'),
                'modalite_label': modalite_by_ouvrage.get(str(item.id), {}).get('label', MODALITE_LABELS['inconnue']),
                'region_label': geo_by_ouvrage.get(str(item.id), {}).get('region_label', 'Sans region'),
                'district_label': geo_by_ouvrage.get(str(item.id), {}).get('district_label', 'Sans district'),
            }
            for item in ouvrages
        ],
        'types_pe': [{'id': str(item.id), 'nom': item.nom_type} for item in types_pe],
    })


@login_required
def analyse_consommation_comparatif(request):
    annee_filter = request.GET.get('annee', str(datetime.now().year))
    regions_ids = request.GET.getlist('regions')
    districts_ids = request.GET.getlist('districts')
    communes_ids = request.GET.getlist('communes')
    villages_ids = request.GET.getlist('villages')
    parcelles_ids = request.GET.getlist('parcelles')
    ouvrages_ids = request.GET.getlist('ouvrages')
    types_pe_ids = request.GET.getlist('types_pe')
    modalite_paiement_filter = request.GET.get('modalite_paiement', '')
    organisation_state = _get_organisation_filter_state(request)
    gestionnaire_ids = organisation_state['gestionnaire_ids']
    organisation_filter = organisation_state['organisation_filter']

    ouvrages_modalite_ids = list(_get_modalite_ouvrages_ids(
        gestionnaire_ids,
        organisation_filter,
        modalite_paiement_filter,
    ))

    # Regroupement ouvrage AEPG <-> ses extensions : une extension partage la source
    # (et donc le debit) de son ouvrage AEPG principal, il faut donc cumuler leurs
    # consommations avant de comparer au debit mesure sur la source.
    ouvrage_group_lookup = {}
    ouvrage_name_lookup = {}
    group_members_map = defaultdict(list)
    ouvrage_ids_in_scope = set()
    raw_group_target = {}
    for ouvrage_row in Ouvrage.objects.filter(
        id__in=ouvrages_modalite_ids
    ).select_related('type_ouvrage', 'ouvrage_source'):
        oid = str(ouvrage_row.id)
        ouvrage_ids_in_scope.add(oid)
        ouvrage_name_lookup[oid] = ouvrage_row.nom_ouvrage
        type_nom = str(getattr(ouvrage_row.type_ouvrage, 'nom_type_ouvrage', '') or '').strip().lower()
        if type_nom == 'aepg extension' and ouvrage_row.ouvrage_source_id:
            raw_group_target[oid] = str(ouvrage_row.ouvrage_source_id)
        else:
            raw_group_target[oid] = oid

    for oid, gid in raw_group_target.items():
        if gid not in ouvrage_ids_in_scope:
            # La source n'est pas dans le perimetre filtre (autre modalite) : pas de regroupement possible
            gid = oid
        ouvrage_group_lookup[oid] = gid
        group_members_map[gid].append(oid)

    def _pick_first(mapping, ids, default=None):
        for candidate in ids:
            if candidate in mapping:
                return mapping[candidate]
        return default

    points_eau_qs = PointEau.objects.filter(
        ouvrage_id__in=ouvrages_modalite_ids
    ).select_related(
        'ouvrage',
        'parcelle',
        'type_point_eau',
        'parcelle__village__fokontany__commune__district__region',
    )

    if regions_ids and regions_ids != ['']:
        points_eau_qs = points_eau_qs.filter(
            parcelle__village__fokontany__commune__district__region_id__in=regions_ids
        )
    if districts_ids and districts_ids != ['']:
        points_eau_qs = points_eau_qs.filter(
            parcelle__village__fokontany__commune__district_id__in=districts_ids
        )
    if communes_ids and communes_ids != ['']:
        points_eau_qs = points_eau_qs.filter(
            parcelle__village__fokontany__commune_id__in=communes_ids
        )
    if villages_ids and villages_ids != ['']:
        points_eau_qs = points_eau_qs.filter(parcelle__village_id__in=villages_ids)
    if parcelles_ids and parcelles_ids != ['']:
        points_eau_qs = points_eau_qs.filter(parcelle_id__in=parcelles_ids)
    if ouvrages_ids and ouvrages_ids != ['']:
        # Si un ouvrage (principal ou extension) est selectionne, on inclut automatiquement
        # le reste de son groupe (source + toutes ses extensions) pour ne pas fausser la
        # comparaison avec le debit de la source.
        selected_groups = {ouvrage_group_lookup.get(oid, oid) for oid in ouvrages_ids}
        expanded_ouvrage_ids = {
            oid for oid, gid in ouvrage_group_lookup.items() if gid in selected_groups
        }
        expanded_ouvrage_ids |= set(ouvrages_ids)
        points_eau_qs = points_eau_qs.filter(ouvrage_id__in=list(expanded_ouvrage_ids))
    if types_pe_ids and types_pe_ids != ['']:
        points_eau_qs = points_eau_qs.filter(type_point_eau_id__in=types_pe_ids)

    annee_int = int(annee_filter)
    releves = list(
        Releve.objects.filter(
            point_eau__in=points_eau_qs,
            datereleve__year=annee_int,
            volume_facture__gt=0,
        ).select_related('point_eau__ouvrage', 'point_eau__parcelle', 'point_eau__type_point_eau')
    )

    ouvrages_stats = {}
    mois_labels = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Jun', 'Jul', 'Aoû', 'Sep', 'Oct', 'Nov', 'Déc']

    points_eau_list = list(points_eau_qs)
    modalite_by_ouvrage = _get_modalite_by_ouvrage_ids(
        [pe.ouvrage_id for pe in points_eau_list if pe.ouvrage_id],
        gestionnaire_ids,
        organisation_filter,
    )
    geo_by_ouvrage = _get_geo_by_ouvrage_ids(points_eau_list)
    ouvrage_population = defaultdict(int)
    ouvrage_pe_count = defaultdict(int)
    ouvrage_nb_bp = defaultdict(int)
    ouvrage_nb_public = defaultdict(int)
    ouvrage_parcelles_seen = defaultdict(set)
    # Repartition par categorie (bp / kiosque / bi_volume / autres) pour permettre de
    # recomposer les 3 graphiques en ne considerant que certains types de points d'eau
    # (ex : BP seuls avec leur estimation de 4 pers./branchement, ou kiosques+cartes
    # sociales+BI volume) sans refaire de requete serveur.
    category_pe_count = defaultdict(lambda: defaultdict(int))
    category_population = defaultdict(lambda: defaultdict(int))
    category_parcelles_seen = defaultdict(lambda: defaultdict(set))
    for pe in points_eau_list:
        if not pe.ouvrage_id:
            continue
        raw_oid = str(pe.ouvrage_id)
        oid = ouvrage_group_lookup.get(raw_oid, raw_oid)
        ouvrage_pe_count[oid] += 1
        type_nom = pe.type_point_eau.nom_type if pe.type_point_eau else ''
        if is_private_point_type_name(type_nom, pe.estbranchementinstitutionnel):
            ouvrage_nb_bp[oid] += 1
        else:
            ouvrage_nb_public[oid] += 1
        if pe.parcelle_id and pe.parcelle_id not in ouvrage_parcelles_seen[oid]:
            ouvrage_parcelles_seen[oid].add(pe.parcelle_id)
            ouvrage_population[oid] += pe.parcelle.nombre_habitants or 0

        category = _classify_point_eau_category(type_nom, pe.estbranchementinstitutionnel)
        category_pe_count[oid][category] += 1
        if pe.parcelle_id and pe.parcelle_id not in category_parcelles_seen[oid][category]:
            category_parcelles_seen[oid][category].add(pe.parcelle_id)
            category_population[oid][category] += pe.parcelle.nombre_habitants or 0

    # La population des BP n'est pas prise depuis la parcelle : on utilise l'estimation
    # fixe de 4 personnes par branchement prive, comme sur la page d'analyse globale.
    for oid, per_category in category_pe_count.items():
        category_population[oid]['bp'] = per_category.get('bp', 0) * POPULATION_PAR_BP

    for pe in points_eau_list:
        if not pe.ouvrage_id:
            continue
        raw_oid = str(pe.ouvrage_id)
        oid = ouvrage_group_lookup.get(raw_oid, raw_oid)
        if oid not in ouvrages_stats:
            member_ids_for_group = [oid] + [m for m in group_members_map.get(oid, []) if m != oid]
            modalite_info = _pick_first(modalite_by_ouvrage, member_ids_for_group, {})
            geo_info = _pick_first(geo_by_ouvrage, member_ids_for_group, {})
            extensions_noms = sorted(
                ouvrage_name_lookup.get(m, m) for m in group_members_map.get(oid, []) if m != oid
            )
            ouvrages_stats[oid] = {
                'ouvrage_id': oid,
                'ouvrage_nom': ouvrage_name_lookup.get(oid, pe.ouvrage.nom_ouvrage if pe.ouvrage else 'Sans ouvrage'),
                'extensions_noms': extensions_noms,
                'nb_extensions': len(extensions_noms),
                'nb_points_eau': 0,
                'nb_bp': 0,
                'nb_public': 0,
                'population': 0,
                'modalite_code': modalite_info.get('code', 'inconnue'),
                'modalite_label': modalite_info.get('label', MODALITE_LABELS['inconnue']),
                'region_label': geo_info.get('region_label', 'Sans region'),
                'district_label': geo_info.get('district_label', 'Sans district'),
                'volumes': [0] * 12,
                'montants': [0] * 12,
                'montants_hab': [0] * 12,
                'conso_hab': [0] * 12,
                'volume_total': 0,
                'montant_total': 0,
                'moyenne_volume': 0,
                'moyenne_montant': 0,
                'moyenne_montant_hab': 0,
                'moyenne_conso_hab': 0,
                'debit_l_s': None,
                'debit_capacite_hab_jour': None,
                'debit_capacite_m3_mois': None,
                'taux_utilisation_pct': None,
                'niveau_criticite': 'inconnu',
                'premiere_date_releve': None,
                'anciennete_jours': None,
                'niveau_historique': 'inconnu',
            }
        ouvrages_stats[oid]['nb_points_eau'] = ouvrage_pe_count[oid]
        ouvrages_stats[oid]['nb_bp'] = ouvrage_nb_bp[oid]
        ouvrages_stats[oid]['nb_public'] = ouvrage_nb_public[oid]
        ouvrages_stats[oid]['population'] = ouvrage_population[oid]

    category_volumes = defaultdict(lambda: defaultdict(lambda: [0.0] * 12))
    category_montants = defaultdict(lambda: defaultdict(lambda: [0.0] * 12))
    for releve in releves:
        if not releve.point_eau or not releve.point_eau.ouvrage_id or not releve.datereleve:
            continue
        raw_oid = str(releve.point_eau.ouvrage_id)
        oid = ouvrage_group_lookup.get(raw_oid, raw_oid)
        if oid not in ouvrages_stats:
            continue
        month_index = releve.datereleve.month - 1
        volume = float(releve.volume_facture or 0)
        montant = float(releve.montant or 0)
        ouvrages_stats[oid]['volumes'][month_index] += volume
        ouvrages_stats[oid]['montants'][month_index] += montant
        ouvrages_stats[oid]['volume_total'] += volume
        ouvrages_stats[oid]['montant_total'] += montant

        type_nom = releve.point_eau.type_point_eau.nom_type if releve.point_eau.type_point_eau else ''
        category = _classify_point_eau_category(type_nom, releve.point_eau.estbranchementinstitutionnel)
        category_volumes[oid][category][month_index] += volume
        category_montants[oid][category][month_index] += montant

    # Le debit d'une extension AEPG est mesure sur son ouvrage source : on interroge donc
    # le groupe complet (ouvrage principal + extensions) et on privilegie la mesure portee
    # par l'id du groupe (la source), avec repli sur un membre si besoin.
    debit_by_ouvrage = {}
    if ouvrages_stats:
        debit_query_ids = set()
        for gid in ouvrages_stats.keys():
            debit_query_ids.add(gid)
            debit_query_ids.update(group_members_map.get(gid, []))
        debit_qs = DebitSourceMesure.objects.filter(
            ouvrage_id__in=list(debit_query_ids)
        ).order_by('ouvrage_id', '-date_visite', '-created_at')
        debit_by_raw_ouvrage = {}
        for mesure in debit_qs:
            oid_str = str(mesure.ouvrage_id)
            if oid_str not in debit_by_raw_ouvrage:
                debit_by_raw_ouvrage[oid_str] = float(mesure.debit_l_s)
        for gid in ouvrages_stats.keys():
            member_ids_for_group = [gid] + [m for m in group_members_map.get(gid, []) if m != gid]
            value = _pick_first(debit_by_raw_ouvrage, member_ids_for_group)
            if value is not None:
                debit_by_ouvrage[gid] = value

    # Anciennete du suivi de l'ouvrage : date du tout premier releve connu (toutes annees
    # confondues, sur l'ouvrage principal ET ses extensions), pour aider a expliquer une
    # consommation moyenne peu fiable par un historique de releves encore court plutot que
    # par une vraie tendance.
    premiere_date_by_ouvrage = {}
    if ouvrages_stats:
        premiere_query_ids = set()
        for gid in ouvrages_stats.keys():
            premiere_query_ids.add(gid)
            premiere_query_ids.update(group_members_map.get(gid, []))
        premieres_dates = Releve.objects.filter(
            point_eau__ouvrage_id__in=list(premiere_query_ids)
        ).values('point_eau__ouvrage_id').annotate(premiere_date=Min('datereleve'))
        raw_premiere_dates = {}
        for row in premieres_dates:
            raw_premiere_dates[str(row['point_eau__ouvrage_id'])] = row['premiere_date']
        for gid in ouvrages_stats.keys():
            member_ids_for_group = [gid] + [m for m in group_members_map.get(gid, []) if m != gid]
            candidates = [raw_premiere_dates[m] for m in member_ids_for_group if m in raw_premiere_dates]
            if candidates:
                premiere_date_by_ouvrage[gid] = min(candidates)

    aujourdhui_mg = datetime.now(pytz.timezone('Indian/Antananarivo')).date()

    for oid, stats in ouvrages_stats.items():
        _finalize_card_metrics(stats, debit_by_ouvrage, premiere_date_by_ouvrage, aujourdhui_mg)
        _attach_bp_public_breakdown(stats, oid, category_pe_count, category_population, category_volumes, category_montants)

    ouvrages_cards = sorted(
        ouvrages_stats.values(),
        key=lambda item: item['volume_total'],
        reverse=True,
    )

    if not ouvrages_ids:
        ouvrages_cards = ouvrages_cards[:12]

    visible_month_count = _visible_month_count(annee_int)

    import json
    return render(request, 'planning/analyse_consommation_comparatif.html', {
        'title': "Comparatif consommation par ouvrage",
        'annee_filter': annee_filter,
        'visible_month_count': visible_month_count,
        'cards_json': json.dumps(ouvrages_cards),
        'ouvrages_options_json': json.dumps([
            {
                'id': card['ouvrage_id'],
                'nom': card['ouvrage_nom'],
                'modalite_code': card['modalite_code'],
                'modalite_label': card['modalite_label'],
                'region_label': card['region_label'],
                'district_label': card['district_label'],
                'selected': True,
            }
            for card in sorted(ouvrages_stats.values(), key=lambda item: item['ouvrage_nom'].lower())
        ]),
        'mois_labels_json': json.dumps(mois_labels),
        'selected_count': len(ouvrages_cards),
        'back_querystring': request.GET.urlencode(),
    })


@login_required
def api_details_points_eau_mois(request):
    """API pour récupérer les détails des consommations par point d'eau pour un mois donné"""
    from django.http import JsonResponse

    mois = request.GET.get('mois')  # Format: "YYYY-MM"
    regions_ids = request.GET.getlist('regions')
    districts_ids = request.GET.getlist('districts')
    communes_ids = request.GET.getlist('communes')
    ouvrages_ids = request.GET.getlist('ouvrages')
    types_pe_ids = request.GET.getlist('types_pe')
    modalite_paiement_filter = request.GET.get('modalite_paiement', '')
    organisation_state = _get_organisation_filter_state(request)
    gestionnaire_ids = organisation_state['gestionnaire_ids']
    organisation_filter = organisation_state['organisation_filter']

    if not mois:
        return JsonResponse({'success': False, 'error': 'Paramètre mois manquant'}, status=400)

    try:
        annee, mois_numero = mois.split('-')
        annee = int(annee)
        mois_numero = int(mois_numero)
    except:
        return JsonResponse({'success': False, 'error': 'Format mois invalide (attendu: YYYY-MM)'}, status=400)

    # Récupérer les ouvrages selon la modalité de paiement
    modalite_query = ModaliteGestion.objects.filter(date_fin__isnull=True)
    if modalite_paiement_filter:
        if modalite_paiement_filter == 'au_volume':
            modalite_query = modalite_query.filter(modalitepaiement__in=['au_volume', 'mixte'])
        elif modalite_paiement_filter == 'forfaitaire':
            modalite_query = modalite_query.filter(modalitepaiement='forfaitaire')
        elif modalite_paiement_filter == 'mixte':
            modalite_query = modalite_query.filter(modalitepaiement='mixte')
    else:
        modalite_query = modalite_query.filter(modalitepaiement__in=['au_volume', 'mixte'])

    modalite_query = _apply_organisation_filter_to_modalites(
        modalite_query,
        gestionnaire_ids,
        organisation_filter,
    )

    ouvrages_volumetriques_ids = modalite_query.values_list('ouvrage_id', flat=True).distinct()

    # Base queryset des points d'eau
    points_eau_qs = PointEau.objects.filter(
        ouvrage_id__in=ouvrages_volumetriques_ids
    ).select_related(
        'ouvrage',
        'parcelle__village__fokontany__commune',
        'type_point_eau'
    )

    # Appliquer les filtres géographiques
    if regions_ids and regions_ids != ['']:
        points_eau_qs = points_eau_qs.filter(
            parcelle__village__fokontany__commune__district__region_id__in=regions_ids
        )
    if districts_ids and districts_ids != ['']:
        points_eau_qs = points_eau_qs.filter(
            parcelle__village__fokontany__commune__district_id__in=districts_ids
        )
    if communes_ids and communes_ids != ['']:
        points_eau_qs = points_eau_qs.filter(
            parcelle__village__fokontany__commune_id__in=communes_ids
        )
    if ouvrages_ids and ouvrages_ids != ['']:
        points_eau_qs = points_eau_qs.filter(ouvrage_id__in=ouvrages_ids)
    if types_pe_ids and types_pe_ids != ['']:
        points_eau_qs = points_eau_qs.filter(type_point_eau_id__in=types_pe_ids)

    # Limiter aux relevés du mois demandé et aux consommations réelles pour éviter
    # de charger toute l'année en mémoire lors de l'ouverture du détail.
    releves_all = Releve.objects.filter(
        point_eau__in=points_eau_qs,
        datereleve__year=annee,
        datereleve__month=mois_numero,
        volume_facture__gt=0,
    ).select_related(
        'point_eau__type_point_eau',
        'point_eau__ouvrage',
        'point_eau__parcelle__village__fokontany__commune'
    )

    # Regrouper par point d'eau et calculer les totaux
    points_eau_data = {}
    for releve in releves_all:
        pe_id = str(releve.point_eau.id)
        volume = float(releve.volume_facture) if releve.volume_facture else 0

        if pe_id not in points_eau_data:
            commune_nom = ''
            if releve.point_eau.parcelle and releve.point_eau.parcelle.village:
                village = releve.point_eau.parcelle.village
                if village.fokontany and village.fokontany.commune:
                    commune_nom = village.fokontany.commune.nom_commune

            points_eau_data[pe_id] = {
                'point_eau_id': pe_id,
                'idxls': releve.point_eau.idxls or 'N/A',
                'nom_abonne': releve.point_eau.nomabonne or releve.abonne or 'N/A',
                'ouvrage': releve.point_eau.ouvrage.nom_ouvrage if releve.point_eau.ouvrage else 'N/A',
                'type': releve.point_eau.type_point_eau.nom_type if releve.point_eau.type_point_eau else 'N/A',
                'commune': commune_nom,
                'volume_total': 0,
                'nb_releves': 0,
                'volumes': []
            }

        points_eau_data[pe_id]['volume_total'] += volume
        points_eau_data[pe_id]['nb_releves'] += 1
        points_eau_data[pe_id]['volumes'].append(volume)

    # Calculer moyenne et médiane pour chaque point d'eau
    for pe_data in points_eau_data.values():
        volumes = pe_data['volumes']
        pe_data['moyenne'] = pe_data['volume_total'] / pe_data['nb_releves'] if pe_data['nb_releves'] > 0 else 0

        # Calculer la médiane
        volumes_sorted = sorted(volumes)
        n = len(volumes_sorted)
        if n > 0:
            if n % 2 == 0:
                pe_data['mediane'] = (volumes_sorted[n//2 - 1] + volumes_sorted[n//2]) / 2
            else:
                pe_data['mediane'] = volumes_sorted[n//2]
        else:
            pe_data['mediane'] = 0

        del pe_data['volumes']  # Supprimer la liste des volumes (pas nécessaire dans la réponse)

    # Trier par ouvrage puis idxls
    points_eau_list = sorted(points_eau_data.values(), key=lambda x: (x['ouvrage'], x['idxls']))

    return JsonResponse({
        'success': True,
        'points_eau': points_eau_list,
        'total': len(points_eau_list)
    })


@login_required
def api_donnees_meteo_filtrees(request):
    """
    API pour récupérer les données météo (pluviométrie) filtrées selon les mêmes critères
    que l'analyse de consommation. Les données sont agrégées par mois.
    """
    from django.http import JsonResponse
    from django.db.models import Sum, Avg, Count

    # Récupérer les filtres (identiques à analyse_consommation)
    annee_filter = request.GET.get('annee', str(datetime.now().year))
    regions_ids = request.GET.getlist('regions')
    districts_ids = request.GET.getlist('districts')
    communes_ids = request.GET.getlist('communes')
    ouvrages_ids = request.GET.getlist('ouvrages')
    types_pe_ids = request.GET.getlist('types_pe')
    modalite_paiement_filter = request.GET.get('modalite_paiement', '')
    organisation_state = _get_organisation_filter_state(request)
    gestionnaire_ids = organisation_state['gestionnaire_ids']
    organisation_filter = organisation_state['organisation_filter']

    try:
        annee_int = int(annee_filter)
    except:
        return JsonResponse({'success': False, 'error': 'Année invalide'}, status=400)

    # Récupérer les ouvrages selon la modalité de paiement
    modalite_query = ModaliteGestion.objects.filter(date_fin__isnull=True)

    if modalite_paiement_filter:
        if modalite_paiement_filter == 'au_volume':
            modalite_query = modalite_query.filter(modalitepaiement__in=['au_volume', 'mixte'])
        elif modalite_paiement_filter == 'forfaitaire':
            modalite_query = modalite_query.filter(modalitepaiement='forfaitaire')
        elif modalite_paiement_filter == 'mixte':
            modalite_query = modalite_query.filter(modalitepaiement='mixte')
    else:
        # Par défaut: au volume
        modalite_query = modalite_query.filter(modalitepaiement__in=['au_volume', 'mixte'])

    modalite_query = _apply_organisation_filter_to_modalites(
        modalite_query,
        gestionnaire_ids,
        organisation_filter,
    )

    ouvrages_volumetriques_ids = modalite_query.values_list('ouvrage_id', flat=True).distinct()

    # Base queryset des points d'eau
    points_eau_qs = PointEau.objects.filter(
        ouvrage_id__in=ouvrages_volumetriques_ids
    ).select_related(
        'parcelle__village__fokontany__commune__district__region'
    )

    # Appliquer les filtres géographiques
    if regions_ids and regions_ids != ['']:
        points_eau_qs = points_eau_qs.filter(
            parcelle__village__fokontany__commune__district__region_id__in=regions_ids
        )

    if districts_ids and districts_ids != ['']:
        points_eau_qs = points_eau_qs.filter(
            parcelle__village__fokontany__commune__district_id__in=districts_ids
        )

    if communes_ids and communes_ids != ['']:
        points_eau_qs = points_eau_qs.filter(
            parcelle__village__fokontany__commune_id__in=communes_ids
        )

    if ouvrages_ids and ouvrages_ids != ['']:
        points_eau_qs = points_eau_qs.filter(ouvrage_id__in=ouvrages_ids)

    if types_pe_ids and types_pe_ids != ['']:
        points_eau_qs = points_eau_qs.filter(type_point_eau_id__in=types_pe_ids)

    # Récupérer les villages liés aux points d'eau filtrés
    villages_ids = points_eau_qs.exclude(
        parcelle__village__isnull=True
    ).values_list('parcelle__village_id', flat=True).distinct()

    if not villages_ids:
        # Aucun village trouvé, retourner des données vides
        return JsonResponse({
            'success': True,
            'donnees_meteo': {
                'labels': ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Jun', 'Jul', 'Aoû', 'Sep', 'Oct', 'Nov', 'Déc'],
                'precipitations': [0] * 12,
                'temperatures_max': [0] * 12,
                'temperatures_min': [0] * 12,
                'humidites': [0] * 12,
                'nb_mesures_par_mois': [0] * 12
            },
            'villages_count': 0,
            'total_mesures': 0
        })

    # Agréger en une seule requête SQL au lieu de 12 requêtes + 12 exists().
    stats_par_mois = DonneeMeteo.objects.filter(
        village_id__in=villages_ids,
        date__year=annee_int
    ).values('date__month').annotate(
        precipitation_totale=Sum('precipitation'),
        temperature_max_avg=Avg('temperature_max'),
        temperature_min_avg=Avg('temperature_min'),
        humidite_avg=Avg('humidite'),
        nb_mesures=Count('id')
    )

    donnees_par_mois = {
        mois: {
            'precipitation_totale': 0,
            'temperature_max_avg': 0,
            'temperature_min_avg': 0,
            'humidite_avg': 0,
            'nb_mesures': 0,
        }
        for mois in range(1, 13)
    }

    for row in stats_par_mois:
        mois = row['date__month']
        donnees_par_mois[mois] = {
            'precipitation_totale': float(row['precipitation_totale'] or 0),
            'temperature_max_avg': float(row['temperature_max_avg'] or 0),
            'temperature_min_avg': float(row['temperature_min_avg'] or 0),
            'humidite_avg': float(row['humidite_avg'] or 0),
            'nb_mesures': row['nb_mesures'] or 0,
        }

    # Préparer les données pour le graphique
    mois_labels = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Jun', 'Jul', 'Aoû', 'Sep', 'Oct', 'Nov', 'Déc']

    graphique_meteo = {
        'labels': mois_labels,
        'precipitations': [round(donnees_par_mois[mois]['precipitation_totale'], 1) for mois in range(1, 13)],
        'temperatures_max': [round(donnees_par_mois[mois]['temperature_max_avg'], 1) for mois in range(1, 13)],
        'temperatures_min': [round(donnees_par_mois[mois]['temperature_min_avg'], 1) for mois in range(1, 13)],
        'humidites': [round(donnees_par_mois[mois]['humidite_avg'], 1) for mois in range(1, 13)],
        'nb_mesures_par_mois': [donnees_par_mois[mois]['nb_mesures'] for mois in range(1, 13)]
    }

    # Statistiques globales
    total_mesures = sum([donnees_par_mois[mois]['nb_mesures'] for mois in range(1, 13)])
    villages_count = Village.objects.filter(id__in=villages_ids).count()

    return JsonResponse({
        'success': True,
        'donnees_meteo': graphique_meteo,
        'villages_count': villages_count,
        'total_mesures': total_mesures,
        'annee': annee_int
    })


@login_required
def api_points_eau_par_mois(request):
    """
    API pour obtenir le nombre de points d'eau par mois par type
    (nombre de relevés par type de point d'eau par mois)
    """
    from django.http import JsonResponse

    # Récupérer les filtres (identiques à analyse_consommation)
    annee_filter = request.GET.get('annee', str(datetime.now().year))
    regions_ids = request.GET.getlist('regions')
    districts_ids = request.GET.getlist('districts')
    communes_ids = request.GET.getlist('communes')
    ouvrages_ids = request.GET.getlist('ouvrages')
    types_pe_ids = request.GET.getlist('types_pe')
    modalite_paiement_filter = request.GET.get('modalite_paiement', '')
    organisation_state = _get_organisation_filter_state(request)
    gestionnaire_ids = organisation_state['gestionnaire_ids']
    organisation_filter = organisation_state['organisation_filter']

    try:
        annee_int = int(annee_filter)
    except:
        return JsonResponse({'success': False, 'error': 'Année invalide'}, status=400)

    # Ne présenter que les mois entièrement terminés, comme dans les autres
    # graphiques de consommation. Le mois en cours et les mois futurs sont
    # exclus pour l'année courante.
    visible_month_count = _visible_month_count(annee_int)
    visible_months = range(1, visible_month_count + 1)

    # Récupérer les ouvrages selon la modalité de paiement
    modalite_query = ModaliteGestion.objects.filter(date_fin__isnull=True)

    if modalite_paiement_filter:
        if modalite_paiement_filter == 'au_volume':
            modalite_query = modalite_query.filter(modalitepaiement__in=['au_volume', 'mixte'])
        elif modalite_paiement_filter == 'forfaitaire':
            modalite_query = modalite_query.filter(modalitepaiement='forfaitaire')
        elif modalite_paiement_filter == 'mixte':
            modalite_query = modalite_query.filter(modalitepaiement='mixte')
    else:
        # Par défaut: au volume
        modalite_query = modalite_query.filter(modalitepaiement__in=['au_volume', 'mixte'])

    modalite_query = _apply_organisation_filter_to_modalites(
        modalite_query,
        gestionnaire_ids,
        organisation_filter,
    )

    ouvrages_volumetriques_ids = modalite_query.values_list('ouvrage_id', flat=True).distinct()

    # Base queryset des points d'eau
    points_eau_qs = PointEau.objects.filter(
        ouvrage_id__in=ouvrages_volumetriques_ids
    ).select_related('type_point_eau')

    # Appliquer les filtres géographiques
    if regions_ids and regions_ids != ['']:
        points_eau_qs = points_eau_qs.filter(
            parcelle__village__fokontany__commune__district__region_id__in=regions_ids
        )

    if districts_ids and districts_ids != ['']:
        points_eau_qs = points_eau_qs.filter(
            parcelle__village__fokontany__commune__district_id__in=districts_ids
        )

    if communes_ids and communes_ids != ['']:
        points_eau_qs = points_eau_qs.filter(
            parcelle__village__fokontany__commune_id__in=communes_ids
        )

    if ouvrages_ids and ouvrages_ids != ['']:
        points_eau_qs = points_eau_qs.filter(ouvrage_id__in=ouvrages_ids)

    if types_pe_ids and types_pe_ids != ['']:
        points_eau_qs = points_eau_qs.filter(type_point_eau_id__in=types_pe_ids)

    # Agréger directement en base pour éviter de parcourir tous les relevés en Python.
    releves_groupes = Releve.objects.filter(
        point_eau__in=points_eau_qs,
        datereleve__year=annee_int,
        datereleve__month__lte=visible_month_count,
        point_eau__type_point_eau__isnull=False,
    ).values(
        'datereleve__month',
        'point_eau__type_point_eau__nom_type',
    ).annotate(
        count_points_eau=Count('point_eau_id', distinct=True)
    )

    compteurs_par_mois_type = {mois: defaultdict(int) for mois in visible_months}
    for row in releves_groupes:
        mois = row['datereleve__month']
        type_nom = row['point_eau__type_point_eau__nom_type']
        if mois and type_nom:
            compteurs_par_mois_type[mois][type_nom] = row['count_points_eau']

    # Récupérer tous les types de points d'eau présents
    tous_types = set()
    for mois_data in compteurs_par_mois_type.values():
        tous_types.update(mois_data.keys())

    tous_types = sorted(list(tous_types))

    # Préparer les datasets pour Chart.js (stacked bar)
    datasets = []
    couleurs = [
        'rgba(59, 130, 246, 0.7)',    # Bleu
        'rgba(34, 197, 94, 0.7)',     # Vert
        'rgba(251, 191, 36, 0.7)',    # Jaune
        'rgba(168, 85, 247, 0.7)',    # Violet
        'rgba(239, 68, 68, 0.7)',     # Rouge
        'rgba(236, 72, 153, 0.7)',    # Rose
        'rgba(14, 165, 233, 0.7)',    # Cyan
        'rgba(132, 204, 22, 0.7)',    # Lime
    ]

    for i, type_nom in enumerate(tous_types):
        couleur = couleurs[i % len(couleurs)]
        donnees = [compteurs_par_mois_type[mois].get(type_nom, 0) for mois in visible_months]
        datasets.append({
            'label': type_nom,
            'data': donnees,
            'backgroundColor': couleur,
            'borderColor': couleur.replace('0.7', '1'),
            'borderWidth': 1
        })

    mois_labels = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Jun', 'Jul', 'Aoû', 'Sep', 'Oct', 'Nov', 'Déc'][:visible_month_count]

    return JsonResponse({
        'success': True,
        'graphique': {
            'labels': mois_labels,
            'datasets': datasets
        },
        'annee': annee_int,
        'visible_month_count': visible_month_count,
        'nb_types': len(tous_types)
    })


# ---------------------------------------------------------------------------------------------------
# Rappel : kiosques à reclasser (BP déguisés). Le type de point d'eau est à corriger.
# ---------------------------------------------------------------------------------------------------

def calculer_kiosques_faible_conso_periode(ouvrages_ids, debut, fin, seuil, min_releves=1):
    """
    Kiosques dont la consommation moyenne sur [debut, fin] est inférieure à `seuil` m³/mois (BP déguisés).
    Moyenne = volume facturé de la période ÷ jours couverts (depuis le relevé précédent la période, ou le
    début du mois du premier relevé) × 30,44. `min_releves` : nombre minimal de relevés pour conclure.
    Triés du plus faible au plus fort consommateur.
    """
    points = list(
        PointEau.objects.filter(
            ouvrage_id__in=ouvrages_ids, type_point_eau__nom_type__icontains='kiosque',
        ).select_related('type_point_eau', 'ouvrage', 'parcelle__village__fokontany__commune')
    )
    pe_ids = [pe.id for pe in points]
    releves_par_pe = defaultdict(list)
    for pe_id, dte, volume in Releve.objects.filter(
        point_eau_id__in=pe_ids, datereleve__gte=debut, datereleve__lte=fin, volume_facture__gt=0,
    ).values_list('point_eau_id', 'datereleve', 'volume_facture'):
        releves_par_pe[str(pe_id)].append((dte, float(volume)))
    avant_periode = {
        str(row['point_eau_id']): row['d']
        for row in Releve.objects.filter(
            point_eau_id__in=pe_ids, datereleve__lt=debut,
        ).values('point_eau_id').annotate(d=Max('datereleve'))
    }

    libelles_abonne = {'particulier': 'Particulier', 'boutique': 'Boutique'}
    lignes = []
    for pe in points:
        releves = releves_par_pe.get(str(pe.id))
        if not releves or len(releves) < min_releves:
            continue
        dates = [d for d, _ in releves]
        depart = avant_periode.get(str(pe.id)) or min(dates).replace(day=1)
        jours = max(1, (max(dates) - depart).days)
        volume = sum(v for _, v in releves)
        moyenne = volume / jours * 30.44
        if moyenne >= seuil:
            continue
        village = pe.parcelle.village if pe.parcelle else None
        commune = village.fokontany.commune if village and village.fokontany else None
        abonne = str(pe.typeabonne or '').strip().lower()
        lignes.append({
            'id': str(pe.id),
            'nom': pe.nomabonne or pe.code_point_eau or '-',
            'idxls': pe.idxls or '',
            'ouvrage': pe.ouvrage.nom_ouvrage if pe.ouvrage else '-',
            'ouvrage_id': str(pe.ouvrage_id or ''),
            'village': village.nom_village if village else '',
            'commune': commune.nom_commune if commune else '',
            'type_abonne': libelles_abonne.get(abonne, 'Non renseigné'),
            'institutionnel': bool(getattr(pe, 'estbranchementinstitutionnel', False)),
            'actif': pe.datebranchement is not None and pe.datearretbranchement is None,
            'moyenne': round(moyenne, 2),
            'nb_releves': len(releves),
            'volume_total': round(volume, 2),
        })
    lignes.sort(key=lambda l: (l['moyenne'], l['ouvrage'].lower(), l['nom'].lower()))
    return lignes


def calculer_kiosques_a_reclasser(annee, ouvrages_ids, seuil):
    """Kiosques sous `seuil` m³/mois sur l'année civile `annee` (page « Kiosques à reclasser »)."""
    from datetime import date
    return calculer_kiosques_faible_conso_periode(ouvrages_ids, date(annee, 1, 1), date(annee, 12, 31), seuil)


def alertes_bp_deguises_pour_ouvrage(ouvrage_id, aujourd_hui=None):
    """
    Alertes « BP déguisé » à afficher dans l'app Android pendant le relevé : {point_eau_id: alerte}.
    Fenêtre glissante de 12 mois, au moins 3 relevés, branchements institutionnels exclus.
    Le texte est fourni par le serveur : une évolution de la règle ne demande pas de nouvelle version de l'app.
    """
    from datetime import date, timedelta

    aujourd_hui = aujourd_hui or date.today()
    lignes = calculer_kiosques_faible_conso_periode(
        [ouvrage_id], aujourd_hui - timedelta(days=365), aujourd_hui,
        SEUIL_KIOSQUE_BP_DEGUISE, min_releves=ALERTE_BP_MIN_RELEVES,
    )
    alertes = {}
    for l in lignes:
        if l['institutionnel']:
            continue
        moyenne = str(l['moyenne']).replace('.', ',')
        alertes[l['id']] = {
            'moyenne_m3_mois': l['moyenne'],
            'seuil_m3_mois': SEUIL_KIOSQUE_BP_DEGUISE,
            'nb_releves': l['nb_releves'],
            'titre': "Kiosque à faible consommation : BP déguisé ?",
            'message': (
                f"Ce kiosque consomme en moyenne {moyenne} m³ par mois sur les 12 derniers mois "
                f"(moins de {SEUIL_KIOSQUE_BP_DEGUISE} m³). Il se comporte comme un branchement privé. "
                "Parlez à l'abonné : soit couper ce kiosque, soit le transformer en BP."
            ),
            'actions': ['couper', 'transformer_en_bp'],
        }
    return alertes


@login_required
def kiosques_a_reclasser(request):
    """Page de rappel : kiosques consommant comme des BP, dont le type de point d'eau est à corriger."""
    try:
        annee = int(request.GET.get('annee', datetime.now().year))
    except ValueError:
        annee = datetime.now().year
    try:
        seuil = float(str(request.GET.get('seuil', SEUIL_KIOSQUE_BP_DEGUISE)).replace(',', '.'))
    except ValueError:
        seuil = SEUIL_KIOSQUE_BP_DEGUISE

    organisation_state = _get_organisation_filter_state(request)
    modalite_query = ModaliteGestion.objects.filter(
        date_fin__isnull=True, modalitepaiement__in=['au_volume', 'mixte'],
    )
    modalite_query = _apply_organisation_filter_to_modalites(
        modalite_query, organisation_state['gestionnaire_ids'], organisation_state['organisation_filter'],
    )
    ouvrages_ids = list(modalite_query.values_list('ouvrage_id', flat=True).distinct())

    lignes = calculer_kiosques_a_reclasser(annee, ouvrages_ids, seuil)
    types_cibles = TypePointEau.objects.filter(actif=True).exclude(
        nom_type__icontains='kiosque'
    ).order_by('nom_type')
    return render(request, 'planning/kiosques_a_reclasser.html', {
        'title': 'Kiosques à reclasser',
        'annee': annee,
        'annees': list(range(datetime.now().year, 2023, -1)),
        'seuil': seuil,
        'lignes': lignes,
        'types_cibles': types_cibles,
        'organisations': organisation_state['organisations'],
        'organisation_filter': organisation_state['organisation_filter'],
    })


@login_required
def api_changer_type_point_eau(request):
    """Change le type de point d'eau d'un point d'eau (accès contrôlé par les permissions de l'utilisateur)."""
    from django.shortcuts import get_object_or_404
    from django.utils import timezone
    from apps.employees.permissions import filter_queryset_by_permissions

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Méthode non autorisée'}, status=405)
    point = get_object_or_404(
        filter_queryset_by_permissions(PointEau.objects.select_related('type_point_eau'), request.user),
        pk=request.POST.get('point_eau_id'),
    )
    type_cible = get_object_or_404(TypePointEau, pk=request.POST.get('type_point_eau_id'), actif=True)

    ancien = point.type_point_eau.nom_type if point.type_point_eau else ''
    point.type_point_eau = type_cible
    if 'kiosque' not in (type_cible.nom_type or '').lower():
        point.typeabonne = None        # le type d'abonné n'a de sens que pour un kiosque (même règle que la fiche)
    if hasattr(request.user, 'employe') and request.user.employe:
        point.updated_by = request.user.employe
    point.updatedat = timezone.now()
    point.save()
    return JsonResponse({
        'success': True,
        'message': f"« {point.nomabonne or point.code_point_eau} » : {ancien or 'sans type'} → {type_cible.nom_type}",
        'type': type_cible.nom_type,
    })
