"""
Structure du parc pour le dashboard principal : âge des ouvrages, accessibilité et taille des
villages desservis, et croisement des trois (diagramme de flux).

Périmètre = celui des KPI du dashboard (permissions, filtres géographiques, organisation, année).
"""
import statistics
from collections import Counter, defaultdict
from datetime import date

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.http import JsonResponse

from apps.employees.permissions import employe_required, filter_queryset_by_permissions
from apps.geography.models import Parcelle, Village
from apps.organization.models import Ouvrage
from apps.organization.scoping import apply_user_responsable_ouvrage_scope

from apps.organization.services_fonctionnalite import get_statuts_fonctionnel_bulk

from .views import (
    _calculer_continuite,
    _get_dashboard_allowed_organisation_ids,
    _resolve_dashboard_organisation_filter,
    calculate_dashboard_stats_with_permissions,
)

# --- Seuils métier ---------------------------------------------------------------------------
AGE_RECENT_MAX = 3          # < 3 ans            -> récent
AGE_MOYEN_MAX = 10          # 3 à 10 ans inclus  -> moyen ; > 10 ans -> ancien
TAILLE_PETIT_MAX = 250      # < 250 habitants    -> petit
TAILLE_MOYEN_MAX = 500      # 250 à 499         -> moyen ; >= 500 -> grand
DISTANCE_LOIN_KM = 10       # > 10 km à pied depuis le dernier point accessible en véhicule
ACCES_VEHICULE = ('voiture', 'moto', 'pirogue')
# Dimensions du diagramme de flux, dans l'ordre des éléments de la clé de croisement
DIMENSIONS_FLUX = (
    'taille', 'acces', 'age', 'fonct', 'continuite', 'gestion', 'paiement', 'factures', 'reparation', 'desserte',
)


_ND = {'k': 'non_desservi', 'court': 'Non desservi', 'color': '#475569'}


def _cat(k, court, color):
    return {'k': k, 'court': court, 'color': color}


# Titres, libellés courts et couleurs des catégories de chaque dimension du diagramme de flux.
# Utilisé par l'app mobile (fiche commune) : l'app dessine ce que le serveur décrit, sans dupliquer les règles.
DIMENSIONS_META = {
    'taille': {'titre': 'Taille du village', 'cats': [
        _cat('petit', 'Petits (<250 hab.)', '#38bdf8'), _cat('moyen', 'Moyens (250-499)', '#2563eb'),
        _cat('grand', 'Grands (≥500 hab.)', '#1e3a8a'), _cat('non_renseigne', 'Population inconnue', '#9ca3af')]},
    'acces': {'titre': 'Accessibilité', 'cats': [
        _cat('loin', 'Loin (>10 km à pied)', '#dc2626'), _cat('moins_loin', 'Moins loin (≤10 km)', '#f59e0b'),
        _cat('accessible', 'Accessibles (véhicule)', '#16a34a'), _cat('tres_pres', 'Très près (0 km)', '#0d9488'),
        _cat('non_renseigne', 'Accès non renseigné', '#9ca3af')]},
    'age': {'titre': 'Âge des ouvrages', 'cats': [
        _cat('recent', 'Récents (<3 ans)', '#22c55e'), _cat('moyen', 'Moyens (3-10 ans)', '#eab308'),
        _cat('ancien', 'Anciens (>10 ans)', '#b45309'), _cat('non_desservi', 'Non desservi (sans ouvrage)', '#475569'),
        _cat('non_date', 'Ouvrage non daté', '#9ca3af')]},
    'fonct': {'titre': 'Fonctionnement', 'cats': [
        _cat('fonctionnel', 'Ouvrage fonctionnel', '#16a34a'), _cat('non_fonctionnel', 'Ouvrage non fonctionnel', '#dc2626'), _ND]},
    'continuite': {'titre': 'Continuité du service', 'cats': [
        _cat('continu', 'Service continu', '#0d9488'), _cat('interrompu', 'Service interrompu', '#ea580c'), _ND]},
    'gestion': {'titre': 'Modalité de gestion', 'cats': [
        _cat('privee', 'Gestion privée', '#7c3aed'), _cat('comite_eau', 'Comité eau', '#0ea5e9'),
        _cat('pas_de_gestion', 'Pas de gestion', '#64748b'), _cat('plusieurs', 'Gestions différentes', '#f59e0b'),
        _cat('non_renseigne', 'Gestion non renseignée (anomalie)', '#dc2626'), _ND]},
    'paiement': {'titre': 'Modalité de paiement', 'cats': [
        _cat('forfait', 'Forfait', '#0891b2'), _cat('volume', 'Volume', '#2563eb'), _cat('mixte', 'Mixte', '#7c3aed'),
        _cat('sans_tarif', 'Sans tarif', '#9ca3af'), _cat('plusieurs', 'Modalités différentes', '#f59e0b'), _ND]},
    'factures': {'titre': 'Recouvrement (factures non pointées)', 'cats': [
        _cat('passe', 'Non pointées · mois passés', '#dc2626'), _cat('courant', 'Non pointées · mois en cours', '#f59e0b'),
        _cat('a_jour', 'Recouvrement à jour', '#16a34a'), _ND]},
    'reparation': {'titre': 'Réparations / réhabilitations', 'cats': [
        _cat('avec', 'Avec réparation / réhabilitation', '#ea580c'), _cat('sans', 'Sans réparation', '#16a34a'), _ND]},
    'desserte': {'titre': 'Desserte', 'cats': [
        _cat('desservi', 'Village desservi', '#0ea5e9'), _cat('non_desservi', 'Village non desservi', '#475569')]},
}


def classe_age(age):
    """Classe d'âge d'un ouvrage ; 'non_desservi' est attribué plus bas aux villages sans ouvrage."""
    if age is None:
        return 'non_date'
    if age < AGE_RECENT_MAX:
        return 'recent'
    if age <= AGE_MOYEN_MAX:
        return 'moyen'
    return 'ancien'


def classe_taille(habitants):
    if not habitants:
        return 'non_renseigne'
    if habitants < TAILLE_PETIT_MAX:
        return 'petit'
    if habitants < TAILLE_MOYEN_MAX:
        return 'moyen'
    return 'grand'


def classe_accessibilite(accessibilite, distance):
    """
    La distance à pied prime : un village à plus de 0 km du dernier point accessible en véhicule
    est « loin » (> 10 km) ou « moins loin » (<= 10 km), quel que soit son moyen d'accès principal.
    Sinon : véhicule / pirogue -> « accessible » ; route goudronnée, ou 0 km renseigné -> « très près ».
    """
    if distance is not None and distance > 0:
        return 'loin' if distance > DISTANCE_LOIN_KM else 'moins_loin'
    if accessibilite in ACCES_VEHICULE:
        return 'accessible'
    if accessibilite == 'goudron' or distance == 0:
        return 'tres_pres'
    return 'non_renseigne'


def age_village(ages_ouvrages):
    """
    Âge (en années) retenu pour classer un village selon les ouvrages qui le desservent.
    `ages_ouvrages` : liste des âges des ouvrages du village (peut contenir None = ouvrage non daté).
    Retourne un âge en années, ou None si aucun ouvrage n'est daté.

    Règle retenue : l'ouvrage le plus récent (le village est considéré comme servi par son
    ouvrage le plus neuf).
    """
    ages = [a for a in ages_ouvrages if a is not None]
    if not ages:
        return None
    return min(ages)


def classe_fonctionnement_village(statuts_ouvrages):
    """
    Village desservi : « fonctionnel » si au moins un des ouvrages qui le desservent est fonctionnel
    (même règle que la page Villages desservis), sinon « non_fonctionnel ».
    `statuts_ouvrages` : liste de booléens (ouvrage fonctionnel ou non) ; vide = village non desservi.
    """
    if not statuts_ouvrages:
        return 'non_desservi'
    return 'fonctionnel' if any(statuts_ouvrages) else 'non_fonctionnel'


def classe_continuite_village(continuites_ouvrages):
    """
    Continuité du service d'un village : « continu » si au moins un des ouvrages qui le desservent
    est resté sans coupure d'eau ni panne sur la période observée, sinon « interrompu ».
    `continuites_ouvrages` : liste de booléens (ouvrage sans coupure ni panne) ; vide = non desservi.
    """
    if not continuites_ouvrages:
        return 'non_desservi'
    return 'continu' if any(continuites_ouvrages) else 'interrompu'


def classe_uniforme_village(valeurs, mixte='plusieurs'):
    """
    Valeur d'un attribut d'ouvrage (modalité de gestion, modalité de paiement) pour un village :
    la valeur commune si tous ses ouvrages la partagent, sinon `mixte`.
    `valeurs` vide = village non desservi.
    """
    valeurs = set(valeurs)
    if not valeurs:
        return 'non_desservi'
    return next(iter(valeurs)) if len(valeurs) == 1 else mixte


def classe_factures_village(periodes_ouvrages):
    """
    Factures non pointées d'un village : la situation la plus défavorable de ses ouvrages
    (mois passés > mois en cours > à jour), comme le diagramme du widget qui classe d'abord « mois passés ».
    """
    periodes = set(periodes_ouvrages)
    if not periodes:
        return 'non_desservi'
    for niveau in ('passe', 'courant'):
        if niveau in periodes:
            return niveau
    return 'a_jour'


def classe_reparation_village(avec_ouvrages):
    """Village « avec » réparation / réhabilitation en cours ou à venir si au moins un de ses ouvrages en a."""
    avec_ouvrages = list(avec_ouvrages)
    if not avec_ouvrages:
        return 'non_desservi'
    return 'avec' if any(avec_ouvrages) else 'sans'


def calculer_structure(user, params, include_village_rows=False):
    """Structure du parc (ouvrages, villages, diagramme de flux) pour un périmètre : `params` se lit comme request.GET."""
    organisation_id = _resolve_dashboard_organisation_filter(user, params.get('organisation_id'))
    annee = params.get('annee')
    try:
        annee_ref = int(annee) if annee else date.today().year
    except (TypeError, ValueError):
        annee_ref = date.today().year

    ouvrages_accessibles = filter_queryset_by_permissions(Ouvrage.objects.all(), user)
    scoped_ids = apply_user_responsable_ouvrage_scope(
        ouvrages_accessibles.values_list('id', flat=True), user,
    )
    if scoped_ids is not None:
        ouvrages_accessibles = ouvrages_accessibles.filter(id__in=scoped_ids)

    _stats, points_qs, ouvrages_qs = calculate_dashboard_stats_with_permissions(
        ouvrages_accessibles, params.get('region_id'), params.get('district_id'),
        params.get('commune_id'), params.get('fokontany_id'), params.get('village_id'),
        annee, organisation_id, scope_only=True,
    )

    # --- Âge des ouvrages (année de réalisation, repli sur l'année antérieure comme le graphique cumulé)
    ages = {}
    for ouvrage_id, an in ouvrages_qs.annotate(
        an=Coalesce('annee_realisation', 'annee_realisation_avant')
    ).values_list('id', 'an'):
        ages[ouvrage_id] = None if an is None else max(0, annee_ref - an)

    ages_connus = [a for a in ages.values() if a is not None]
    repartition_ouvrages = Counter(classe_age(a) for a in ages.values())
    # --- Fonctionnement (chantier actif / case manuelle) et continuité du service (coupure / panne)
    statuts = get_statuts_fonctionnel_bulk(list(ages.keys()))
    fonctionnel = {oid: bool(statuts.get(oid, {}).get('fonctionnel', True)) for oid in ages}
    mode_continuite = 'cumul' if params.get('periode') == 'cumul' else 'annee'
    continuite = _calculer_continuite(ouvrages_qs, points_qs, annee, mode_continuite)
    sans_perturbation = {
        l['id']: not (l['coupure'] or l['panne']) for l in continuite['lignes']
    }
    sans_perturbation = {oid: sans_perturbation.get(str(oid), True) for oid in ages}

    # --- Éléments du diagramme du widget (/widget/diagramme/) : modalité de paiement (forfait / volume /
    # mixte / sans tarif), factures non pointées, réparations ; + modalité de gestion active de l'ouvrage.
    from apps.billing.models import ModaliteGestion
    from apps.core.views_widget import classify_ouvrages

    classement_widget = classify_ouvrages([str(oid) for oid in ages])
    gestion_ouvrage = {}
    for oid, type_gestion in ModaliteGestion.objects.filter(
        ouvrage_id__in=list(ages), date_fin__isnull=True,
    ).order_by('date_debut').values_list('ouvrage_id', 'type_gestion'):
        gestion_ouvrage[oid] = type_gestion or 'non_renseigne'      # la plus récente l'emporte

    # Anomalie : ouvrage sans aucune modalité de gestion active (date de fin vide). On joint la dernière
    # modalité connue (souvent terminée) pour aider l'utilisateur à renseigner la suivante.
    libelles_gestion = dict(ModaliteGestion.TYPE_GESTION_CHOICES)
    sans_gestion_ids = [oid for oid in ages if oid not in gestion_ouvrage]
    derniere_modalite = {}
    for oid, type_gestion, date_fin in ModaliteGestion.objects.filter(
        ouvrage_id__in=sans_gestion_ids,
    ).order_by('ouvrage_id', '-date_debut').values_list('ouvrage_id', 'type_gestion', 'date_fin'):
        derniere_modalite.setdefault(oid, (type_gestion, date_fin))      # la plus récente d'abord
    points_par_ouvrage = dict(
        points_qs.filter(ouvrage_id__in=sans_gestion_ids).order_by().values_list('ouvrage_id').annotate(n=Count('id'))
    )

    def _libelle_derniere_modalite(oid):
        if oid not in derniere_modalite:
            return 'Aucune modalité enregistrée'
        type_gestion, date_fin = derniere_modalite[oid]
        libelle = libelles_gestion.get(type_gestion, type_gestion or '')
        return f"{libelle} · terminée le {date_fin.strftime('%d/%m/%Y')}" if date_fin else libelle

    ouvrages_sans_gestion = sorted((
        {
            'id': str(o['id']), 'nom': o['nom_ouvrage'] or 'Ouvrage sans nom',
            'type': o['type_ouvrage__nom_type_ouvrage'] or '',
            'nb_points': points_par_ouvrage.get(o['id'], 0),
            'derniere_modalite': _libelle_derniere_modalite(o['id']),
            'a_historique': o['id'] in derniere_modalite,      # a déjà eu une modalité (terminée)
        }
        for o in ouvrages_qs.filter(id__in=sans_gestion_ids).values(
            'id', 'nom_ouvrage', 'type_ouvrage__nom_type_ouvrage')
    ), key=lambda x: x['nom'].lower())
    comptes_gestion = Counter(gestion_ouvrage.get(oid) for oid in ages if oid in gestion_ouvrage)

    # Liste nominative des ouvrages avec les raisons de leur classement (tuiles Fonctionnement / Gestion).
    lignes_continuite = {l['id']: l for l in continuite['lignes']}
    nb_points_ouvrage = dict(
        points_qs.order_by().values_list('ouvrage_id').annotate(n=Count('id'))
    )
    libelle_gestion_court = {k: v for k, v in libelles_gestion.items()}
    liste_ouvrages = []
    for o in ouvrages_qs.annotate(an=Coalesce('annee_realisation', 'annee_realisation_avant')).values(
        'id', 'nom_ouvrage', 'type_ouvrage__nom_type_ouvrage', 'an',
    ):
        oid = o['id']
        st = statuts.get(oid, {})
        cont = lignes_continuite.get(str(oid), {})
        type_gestion = gestion_ouvrage.get(oid, 'non_renseigne')
        liste_ouvrages.append({
            'id': str(oid), 'nom': o['nom_ouvrage'] or 'Ouvrage sans nom',
            'type': o['type_ouvrage__nom_type_ouvrage'] or '',
            'annee': o['an'], 'age': ages.get(oid),
            'nb_points': nb_points_ouvrage.get(oid, 0),
            'fonctionnel': bool(fonctionnel.get(oid, True)),
            'source': st.get('source', 'defaut'),
            'reparation_active': bool(st.get('reparation_active')),
            'gestion': type_gestion,
            'gestion_libelle': libelle_gestion_court.get(type_gestion, '') if type_gestion != 'non_renseigne' else '',
            'derniere_modalite': _libelle_derniere_modalite(oid) if oid in sans_gestion_ids else '',
            'coupure': bool(cont.get('coupure')), 'nb_coupures': cont.get('nb_coupures', 0),
            'panne': bool(cont.get('panne')), 'nb_pannes': cont.get('nb_pannes', 0),
        })
    liste_ouvrages.sort(key=lambda x: x['nom'].lower())

    ouvrages = {
        'liste': liste_ouvrages,
        'gestion': {
            'privee': comptes_gestion.get('privee', 0),
            'comite_eau': comptes_gestion.get('comite_eau', 0),
            'pas_de_gestion': comptes_gestion.get('pas_de_gestion', 0),
            'non_renseigne': len(ouvrages_sans_gestion),
        },
        'sans_gestion': ouvrages_sans_gestion,
        'fonctionnels': sum(1 for v in fonctionnel.values() if v),
        'non_fonctionnels': sum(1 for v in fonctionnel.values() if not v),
        'non_fonct_chantier': sum(1 for oid in ages if statuts.get(oid, {}).get('source') == 'chantier'),
        'non_fonct_manuel': sum(1 for oid in ages if statuts.get(oid, {}).get('source') == 'manuel'),
        'total': len(ages),
        'dates': len(ages_connus),
        'age_moyen': round(statistics.mean(ages_connus), 1) if ages_connus else None,
        'age_median': round(statistics.median(ages_connus), 1) if ages_connus else None,
        'repartition': {k: repartition_ouvrages.get(k, 0) for k in ('recent', 'moyen', 'ancien', 'non_date')},
    }

    # --- Villages : desservis (au moins un point d'eau du périmètre) par défaut. Sans filtre organisation
    # ni année (et pour un utilisateur sans restriction d'organisation), tous les villages de la zone
    # géographique sont inclus ; ceux sans ouvrage sont classés « non desservi ».
    ouvrages_par_village = defaultdict(set)
    for village_id, ouvrage_id in points_qs.filter(parcelle__village__isnull=False).values_list(
        'parcelle__village_id', 'ouvrage_id'
    ).distinct():
        ouvrages_par_village[village_id].add(ouvrage_id)
    nb_desservis = len(ouvrages_par_village)

    tous_les_villages = (
        not organisation_id and not annee
        and _get_dashboard_allowed_organisation_ids(user) is None
    )
    if tous_les_villages:
        villages_zone = Village.objects.all()
        village_id = params.get('village_id')
        fokontany_id = params.get('fokontany_id')
        commune_id = params.get('commune_id')
        district_id = params.get('district_id')
        region_id = params.get('region_id')
        if village_id:
            villages_zone = villages_zone.filter(id=village_id)
        elif fokontany_id:
            villages_zone = villages_zone.filter(fokontany_id=fokontany_id)
        elif commune_id:
            villages_zone = villages_zone.filter(fokontany__commune_id=commune_id)
        elif district_id:
            villages_zone = villages_zone.filter(fokontany__commune__district_id=district_id)
        elif region_id:
            villages_zone = villages_zone.filter(fokontany__commune__district__region_id=region_id)
        village_ids = list(villages_zone.values_list('id', flat=True))
        nb_desservis = len(set(village_ids) & set(ouvrages_par_village))
    else:
        village_ids = list(ouvrages_par_village.keys())

    habitants = dict(
        Parcelle.objects.filter(village_id__in=village_ids)
        .values('village_id').annotate(h=Sum('nombre_habitants')).values_list('village_id', 'h')
    )

    # Les lignes nominatives ne sont calculees que pour le panneau de detail
    # demande au clic. Ainsi, le JSON initial du dashboard reste leger, meme
    # lorsque le perimetre contient beaucoup de villages.
    ouvrages_detail = {}
    points_village_ouvrage = {}
    village_rows = []
    if include_village_rows:
        ouvrage_ids_detail = set().union(*ouvrages_par_village.values()) if ouvrages_par_village else set()
        ouvrages_detail = {
            ouvrage['id']: {
                'id': str(ouvrage['id']),
                'nom': ouvrage['nom_ouvrage'] or 'Ouvrage sans nom',
                'type': ouvrage['type_ouvrage__nom_type_ouvrage'] or 'Type non renseigne',
                'annee': ouvrage['annee_realisation'] or ouvrage['annee_realisation_avant'],
                'age': ages.get(ouvrage['id']),
                'fonctionnel': bool(fonctionnel.get(ouvrage['id'], True)),
                'statut_source': statuts.get(ouvrage['id'], {}).get('source', 'defaut'),
                'coupure': bool(lignes_continuite.get(str(ouvrage['id']), {}).get('coupure')),
                'panne': bool(lignes_continuite.get(str(ouvrage['id']), {}).get('panne')),
                'gestion': gestion_ouvrage.get(ouvrage['id'], 'non_renseigne'),
            }
            for ouvrage in ouvrages_qs.filter(id__in=ouvrage_ids_detail).values(
                'id', 'nom_ouvrage', 'type_ouvrage__nom_type_ouvrage',
                'annee_realisation', 'annee_realisation_avant',
            )
        }
        points_village_ouvrage = {
            (row['parcelle__village_id'], row['ouvrage_id']): row['n']
            for row in points_qs.filter(parcelle__village_id__in=village_ids).values(
                'parcelle__village_id', 'ouvrage_id'
            ).annotate(n=Count('id'))
        }

    combos = Counter()
    for v in Village.objects.filter(id__in=village_ids).values(
        'id', 'nom_village', 'accessibilite', 'distance_dernier_point',
        'fokontany__nom_fokontany', 'fokontany__commune__nom_commune',
        'fokontany__commune__district__nom_district',
        'fokontany__commune__district__region__nom_region',
    ):
        taille = classe_taille(habitants.get(v['id']))
        acces = classe_accessibilite(v['accessibilite'], v['distance_dernier_point'])
        ouvrages_du_village = ouvrages_par_village.get(v['id'])
        if ouvrages_du_village:
            age = classe_age(age_village([ages.get(o) for o in ouvrages_du_village]))
        else:
            age = 'non_desservi'
        fonct = classe_fonctionnement_village([fonctionnel.get(o, True) for o in ouvrages_du_village or ()])
        contin = classe_continuite_village([sans_perturbation.get(o, True) for o in ouvrages_du_village or ()])
        ouvrages_v = list(ouvrages_du_village or ())
        gestion = classe_uniforme_village([gestion_ouvrage.get(o, 'non_renseigne') for o in ouvrages_v])
        paiement = classe_uniforme_village([classement_widget.get(str(o), {}).get('cat', 'sans_tarif') for o in ouvrages_v])
        factures = classe_factures_village([classement_widget.get(str(o), {}).get('per', 'a_jour') for o in ouvrages_v])
        reparation = classe_reparation_village([classement_widget.get(str(o), {}).get('avec', False) for o in ouvrages_v])
        desserte = 'desservi' if ouvrages_v else 'non_desservi'
        combos[(taille, acces, age, fonct, contin, gestion, paiement, factures, reparation, desserte)] += 1
        if include_village_rows:
            village_rows.append({
                'id': str(v['id']),
                'nom': v['nom_village'] or 'Village sans nom',
                'habitants': habitants.get(v['id']) or 0,
                'localisation': {
                    'fokontany': v['fokontany__nom_fokontany'] or '',
                    'commune': v['fokontany__commune__nom_commune'] or '',
                    'district': v['fokontany__commune__district__nom_district'] or '',
                    'region': v['fokontany__commune__district__region__nom_region'] or '',
                },
                'accessibilite': v['accessibilite'] or 'non renseignee',
                'distance_dernier_point': v['distance_dernier_point'],
                'categories': {
                    'taille': taille, 'acces': acces, 'age': age,
                    'fonct': fonct, 'continuite': contin, 'gestion': gestion,
                    'paiement': paiement, 'factures': factures,
                    'reparation': reparation, 'desserte': desserte,
                },
                'ouvrages': [
                    {
                        **ouvrages_detail[ouvrage_id],
                        'points_dans_village': points_village_ouvrage.get((v['id'], ouvrage_id), 0),
                    }
                    for ouvrage_id in sorted(
                        ouvrages_v,
                        key=lambda oid: ouvrages_detail.get(oid, {}).get('nom', '').casefold(),
                    )
                    if ouvrage_id in ouvrages_detail
                ],
            })

    def total_par(index):
        c = Counter()
        for cle, n in combos.items():
            c[cle[index]] += n
        return dict(c)

    result = {
        'annee_ref': annee_ref,
        'ouvrages': ouvrages,
        'villages': {
            'total': sum(combos.values()),
            'perimetre': 'tous' if tous_les_villages else 'desservis',
            'desservis': nb_desservis,
            'taille': total_par(0),
            'acces': total_par(1),
            'age': total_par(2),
            'fonct': total_par(3),
            'continuite': total_par(4),
            'gestion': total_par(5),
            'paiement': total_par(6),
            'factures': total_par(7),
            'reparation': total_par(8),
            'desserte': total_par(9),
        },
        'continuite_periode': continuite['periode'],
        'flux': [
            dict(zip(DIMENSIONS_FLUX, cle), n=n) for cle, n in sorted(combos.items())
        ],
    }
    if include_village_rows:
        result['village_rows'] = village_rows
    return result


@employe_required
def dashboard_structure_api(request):
    """Âge des ouvrages + accessibilité / taille / âge des villages desservis (mêmes filtres que le dashboard)."""
    return JsonResponse(calculer_structure(request.user, request.GET))


@employe_required
def dashboard_structure_details_api(request):
    """Villages et ouvrages d'une tuile/case du diagramme de structure.

    Le calcul est volontairement execute a la demande : le dashboard ne
    transfere pas toute la liste nominative tant que l'utilisateur n'a clique
    sur aucun element du diagramme.
    """
    dimension = (request.GET.get('dimension') or '').strip()
    categorie = (request.GET.get('categorie') or '').strip()
    meta = DIMENSIONS_META.get(dimension)
    if not meta or categorie not in {item['k'] for item in meta['cats']}:
        return JsonResponse({'error': 'Dimension ou categorie invalide.'}, status=400)

    try:
        page = max(1, int(request.GET.get('page', 1)))
    except (TypeError, ValueError):
        page = 1
    page_size = 50

    data = calculer_structure(request.user, request.GET, include_village_rows=True)
    rows = [
        row for row in data['village_rows']
        if row['categories'].get(dimension) == categorie
    ]
    rows.sort(key=lambda row: (
        (row['localisation']['region'] or '').casefold(),
        (row['localisation']['district'] or '').casefold(),
        (row['localisation']['commune'] or '').casefold(),
        row['nom'].casefold(),
    ))
    total = len(rows)
    start = (page - 1) * page_size
    if start >= total and total:
        page = max(1, (total + page_size - 1) // page_size)
        start = (page - 1) * page_size

    return JsonResponse({
        'dimension': dimension,
        'categorie': categorie,
        'title': meta['titre'],
        'category_label': next(item['court'] for item in meta['cats'] if item['k'] == categorie),
        'total': total,
        'page': page,
        'page_size': page_size,
        'pages': (total + page_size - 1) // page_size,
        'rows': rows[start:start + page_size],
    })
