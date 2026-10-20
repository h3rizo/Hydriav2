from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from datetime import datetime
from dateutil.relativedelta import relativedelta
from decimal import Decimal

from apps.geography.models import Region, District, Commune
from apps.organization.models import Ouvrage
from apps.billing.models import Releve, ModaliteGestion, PointEau, TypePointEau


@login_required
def analyse_par_point_eau(request):
    """Page d'analyse de la consommation par point d'eau"""

    # Filtres
    annee_filter = request.GET.get('annee', str(datetime.now().year))
    regions_ids = request.GET.getlist('regions')
    districts_ids = request.GET.getlist('districts')
    communes_ids = request.GET.getlist('communes')
    ouvrages_ids = request.GET.getlist('ouvrages')
    types_pe_ids = request.GET.getlist('types_pe')
    modalite_paiement_filter = request.GET.get('modalite_paiement', '')
    point_eau_id = request.GET.get('point_eau')

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

    ouvrages_ids_modalite = list(modalite_query.values_list('ouvrage_id', flat=True).distinct())

    # Base queryset des points d'eau
    points_eau_qs = PointEau.objects.filter(
        ouvrage_id__in=ouvrages_ids_modalite
    ).select_related(
        'ouvrage',
        'parcelle__village__fokontany__commune__district__region',
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

    # Statistiques globales (tous les points d'eau filtrés)
    stats_globales = analyser_points_eau_globaux(points_eau_qs, int(annee_filter))

    # Statistiques du point d'eau sélectionné
    point_eau_selectionne = None
    stats_point_eau = None
    comparaison_ouvrage = None

    if point_eau_id:
        try:
            point_eau_selectionne = PointEau.objects.select_related(
                'ouvrage', 'type_point_eau', 'parcelle__village'
            ).get(id=point_eau_id)

            # Analyser ce point d'eau spécifique
            stats_point_eau = analyser_point_eau_specifique(point_eau_selectionne, int(annee_filter))

            # Comparer avec la moyenne de l'ouvrage
            points_eau_ouvrage = PointEau.objects.filter(ouvrage=point_eau_selectionne.ouvrage)
            stats_ouvrage = analyser_points_eau_globaux(points_eau_ouvrage, int(annee_filter))

            comparaison_ouvrage = comparer_avec_ouvrage(stats_point_eau, stats_ouvrage)

        except PointEau.DoesNotExist:
            pass

    # Listes pour les dropdowns - Filtrer SEULEMENT les entités qui ont des relevés
    # Récupérer tous les points d'eau qui ont des relevés
    points_eau_avec_releves = PointEau.objects.filter(
        releves__isnull=False
    ).select_related(
        'parcelle__village__fokontany__commune__district__region',
        'type_point_eau',
        'ouvrage'
    ).distinct()

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

    # Filtrer les listes pour n'afficher que celles qui ont des relevés
    regions = Region.objects.filter(id__in=regions_ids_avec_releves).order_by('nom_region')
    districts = District.objects.filter(id__in=districts_ids_avec_releves).order_by('nom_district')
    communes = Commune.objects.filter(id__in=communes_ids_avec_releves).order_by('nom_commune')
    ouvrages = Ouvrage.objects.filter(id__in=ouvrages_ids_modalite).order_by('nom_ouvrage')
    types_pe = TypePointEau.objects.filter(id__in=types_pe_ids_avec_releves).order_by('nom_type')

    # Liste des points d'eau pour le dropdown (limité aux points filtrés)
    points_eau_liste = list(
        points_eau_qs.order_by('ouvrage__nom_ouvrage', 'code_point_eau')[:500]
    )
    for point_eau in points_eau_liste:
        idxls_brut = str(point_eau.idxls or '').strip()
        point_eau.idxls_display = idxls_brut.zfill(2) if idxls_brut.isdigit() else (idxls_brut or 'Sans IDXLS')
        point_eau.idxls_sort_key = (0, int(idxls_brut)) if idxls_brut.isdigit() else (1, idxls_brut.casefold())

    points_eau_liste.sort(key=lambda point_eau: (
        (point_eau.ouvrage.nom_ouvrage or '').casefold() if point_eau.ouvrage else '',
        point_eau.idxls_sort_key,
        str(point_eau.code_point_eau or '').casefold(),
    ))

    import json
    context = {
        'title': 'Analyse par Point d\'Eau',
        'annee_filter': annee_filter,
        'regions_ids': regions_ids,
        'districts_ids': districts_ids,
        'communes_ids': communes_ids,
        'ouvrages_ids': ouvrages_ids,
        'types_pe_ids': types_pe_ids,
        'modalite_paiement_filter': modalite_paiement_filter,
        'point_eau_id': point_eau_id,
        'regions': regions,
        'districts': districts,
        'communes': communes,
        'ouvrages': ouvrages,
        'types_pe': types_pe,
        'points_eau_liste': points_eau_liste,
        'point_eau_selectionne': point_eau_selectionne,
        'stats_globales': stats_globales,
        'stats_point_eau': stats_point_eau,
        'comparaison_ouvrage': comparaison_ouvrage,
        'graphique_global_json': json.dumps(stats_globales.get('graphique', {})),
        'graphique_point_eau_json': json.dumps(stats_point_eau.get('graphique', {}) if stats_point_eau else {}),
    }

    return render(request, 'planning/analyse_par_point_eau.html', context)


def analyser_points_eau_globaux(points_eau_qs, annee):
    """Analyse la consommation globale d'un ensemble de points d'eau"""
    from collections import defaultdict

    # Classifier les points d'eau par type
    points_eau_bp = []
    points_eau_kiosques = []
    points_eau_bi = []
    points_eau_bf_bi = []

    # Récupérer les ouvrages forfaitaires
    ouvrages_forfaitaires_ids = ModaliteGestion.objects.filter(
        date_fin__isnull=True,
        modalitepaiement__in=['forfaitaire']
    ).values_list('ouvrage_id', flat=True).distinct()

    for pe in points_eau_qs.select_related('type_point_eau', 'ouvrage'):
        if pe.type_point_eau:
            type_nom = pe.type_point_eau.nom_type.upper() if pe.type_point_eau.nom_type else ''
            est_forfaitaire = str(pe.ouvrage_id) in [str(x) for x in ouvrages_forfaitaires_ids]

            if 'BP' in type_nom or ('BRANCHEMENT' in type_nom and 'PRIVÉ' in type_nom) or 'PRIVE' in type_nom:
                points_eau_bp.append(pe)
            elif 'KIOSQUE' in type_nom:
                if est_forfaitaire:
                    points_eau_bf_bi.append(pe)
                else:
                    points_eau_kiosques.append(pe)
            elif 'BI' in type_nom or 'BORNE' in type_nom:
                if est_forfaitaire:
                    points_eau_bf_bi.append(pe)
                else:
                    points_eau_bi.append(pe)
            elif 'BF' in type_nom or ('BRANCHEMENT' in type_nom and 'FORFAIT' in type_nom):
                points_eau_bf_bi.append(pe)
            else:
                points_eau_bf_bi.append(pe)
        else:
            points_eau_bf_bi.append(pe)

    # Créer un mapping des points d'eau vers leur type
    pe_type_mapping = {}
    for pe in points_eau_bp:
        pe_type_mapping[str(pe.id)] = 'bp'
    for pe in points_eau_kiosques:
        pe_type_mapping[str(pe.id)] = 'kiosques'
    for pe in points_eau_bi:
        pe_type_mapping[str(pe.id)] = 'bi'
    for pe in points_eau_bf_bi:
        pe_type_mapping[str(pe.id)] = 'bf_bi'

    # Récupérer tous les relevés de l'année
    releves = Releve.objects.filter(
        point_eau__in=points_eau_qs,
        datereleve__year=annee
    ).select_related('point_eau').order_by('point_eau_id', 'datereleve')

    # Répartition mensuelle avec même algorithme que analyse_consommation
    mois_liste = list(range(1, 13))
    consommations_par_mois = defaultdict(list)
    volumes_par_mois = defaultdict(float)

    # Grouper par point d'eau
    releves_par_pe = defaultdict(list)
    for releve in releves:
        volume = float(releve.volume_facture) if releve.volume_facture else 0
        if volume > 0:
            releves_par_pe[str(releve.point_eau_id)].append(releve)

    # Pour chaque point d'eau, analyser les relevés
    for pe_id, releves_pe in releves_par_pe.items():
        releves_pe_sorted = sorted(releves_pe, key=lambda r: r.datereleve)

        for i, releve in enumerate(releves_pe_sorted):
            volume = float(releve.volume_facture) if releve.volume_facture else 0
            if volume <= 0:
                continue

            # Trouver le relevé précédent
            if i > 0:
                date_debut = releves_pe_sorted[i-1].datereleve
            else:
                # Chercher dans l'année précédente
                releve_precedent = Releve.objects.filter(
                    point_eau_id=pe_id,
                    datereleve__lt=releve.datereleve
                ).order_by('-datereleve').first()

                if releve_precedent and releve_precedent.datereleve:
                    date_debut = releve_precedent.datereleve
                else:
                    date_debut = releve.datereleve.replace(day=1)

            date_fin = releve.datereleve
            delta_jours = (date_fin - date_debut).days
            if delta_jours <= 0:
                delta_jours = 1

            conso_journaliere = volume / delta_jours

            # Distribuer sur les mois
            date_courante = date_debut
            while date_courante <= date_fin:
                mois = date_courante.month
                annee_courante = date_courante.year

                # Début du mois
                if date_courante.year == date_debut.year and date_courante.month == date_debut.month:
                    debut_mois = date_debut
                else:
                    debut_mois = date_courante.replace(day=1)

                # Fin du mois
                if date_courante.month == 12:
                    dernier_jour_mois = date_courante.replace(year=date_courante.year + 1, month=1, day=1) - relativedelta(days=1)
                else:
                    dernier_jour_mois = date_courante.replace(month=date_courante.month + 1, day=1) - relativedelta(days=1)

                if date_courante.year == date_fin.year and date_courante.month == date_fin.month:
                    fin_mois = date_fin
                else:
                    fin_mois = dernier_jour_mois

                jours_dans_mois = (fin_mois - debut_mois).days + 1
                volume_mois = conso_journaliere * jours_dans_mois

                if annee_courante == annee and volume_mois > 0:
                    consommations_par_mois[mois].append(volume_mois)
                    volumes_par_mois[mois] += volume_mois

                # Mois suivant
                if date_courante.month == 12:
                    date_courante = date_courante.replace(year=date_courante.year + 1, month=1, day=1)
                else:
                    date_courante = date_courante.replace(month=date_courante.month + 1, day=1)

    # Calculer les statistiques par mois
    stats_par_mois = []
    for mois in mois_liste:
        consommations = consommations_par_mois[mois]
        volume_total = volumes_par_mois[mois]

        if len(consommations) > 0:
            moyenne = sum(consommations) / len(consommations)
            consommations_sorted = sorted(consommations)
            n = len(consommations_sorted)
            if n % 2 == 0:
                mediane = (consommations_sorted[n//2 - 1] + consommations_sorted[n//2]) / 2
            else:
                mediane = consommations_sorted[n//2]
        else:
            moyenne = 0
            mediane = 0

        stats_par_mois.append({
            'mois': mois,
            'mois_nom': ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                        'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'][mois],
            'volume_total': volume_total,
            'nb_releves': len(consommations),
            'moyenne': moyenne,
            'mediane': mediane
        })

    # Statistiques annuelles
    volume_total_annuel = sum([s['volume_total'] for s in stats_par_mois])
    nb_releves_total = sum([s['nb_releves'] for s in stats_par_mois])

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

    # Calculer les volumes par type et par mois
    volumes_par_type_mois = {
        'bp': {mois: 0 for mois in mois_liste},
        'kiosques': {mois: 0 for mois in mois_liste},
        'bi': {mois: 0 for mois in mois_liste},
        'bf_bi': {mois: 0 for mois in mois_liste}
    }

    # Recalculer les volumes par type
    for pe_id, releves_pe in releves_par_pe.items():
        pe_type = pe_type_mapping.get(pe_id, 'bf_bi')
        releves_pe_sorted = sorted(releves_pe, key=lambda r: r.datereleve)

        for i, releve in enumerate(releves_pe_sorted):
            volume = float(releve.volume_facture) if releve.volume_facture else 0
            if volume <= 0:
                continue

            # Trouver le relevé précédent
            if i > 0:
                date_debut = releves_pe_sorted[i-1].datereleve
            else:
                releve_precedent = Releve.objects.filter(
                    point_eau_id=pe_id,
                    datereleve__lt=releve.datereleve
                ).order_by('-datereleve').first()

                if releve_precedent and releve_precedent.datereleve:
                    date_debut = releve_precedent.datereleve
                else:
                    date_debut = releve.datereleve.replace(day=1)

            date_fin = releve.datereleve
            delta_jours = (date_fin - date_debut).days
            if delta_jours <= 0:
                delta_jours = 1

            conso_journaliere = volume / delta_jours

            # Distribuer sur les mois
            date_courante = date_debut
            while date_courante <= date_fin:
                mois = date_courante.month
                annee_courante = date_courante.year

                # Début du mois
                if date_courante.year == date_debut.year and date_courante.month == date_debut.month:
                    debut_mois = date_debut
                else:
                    debut_mois = date_courante.replace(day=1)

                # Fin du mois
                if date_courante.month == 12:
                    dernier_jour_mois = date_courante.replace(year=date_courante.year + 1, month=1, day=1) - relativedelta(days=1)
                else:
                    dernier_jour_mois = date_courante.replace(month=date_courante.month + 1, day=1) - relativedelta(days=1)

                if date_courante.year == date_fin.year and date_courante.month == date_fin.month:
                    fin_mois = date_fin
                else:
                    fin_mois = dernier_jour_mois

                jours_dans_mois = (fin_mois - debut_mois).days + 1
                volume_mois = conso_journaliere * jours_dans_mois

                if annee_courante == annee and volume_mois > 0:
                    volumes_par_type_mois[pe_type][mois] += volume_mois

                # Mois suivant
                if date_courante.month == 12:
                    date_courante = date_courante.replace(year=date_courante.year + 1, month=1, day=1)
                else:
                    date_courante = date_courante.replace(month=date_courante.month + 1, day=1)

    # Graphique
    graphique = {
        'labels': [s['mois_nom'][:3] for s in stats_par_mois],
        'volumes': [round(s['volume_total'], 2) for s in stats_par_mois],
        'volumes_bp': [round(volumes_par_type_mois['bp'][mois], 2) for mois in mois_liste],
        'volumes_kiosques': [round(volumes_par_type_mois['kiosques'][mois], 2) for mois in mois_liste],
        'volumes_bi': [round(volumes_par_type_mois['bi'][mois], 2) for mois in mois_liste],
        'volumes_bf_bi': [round(volumes_par_type_mois['bf_bi'][mois], 2) for mois in mois_liste],
        'moyennes': [round(s['moyenne'], 2) for s in stats_par_mois],
        'medianes': [round(s['mediane'], 2) for s in stats_par_mois]
    }

    return {
        'nb_points_eau': points_eau_qs.count(),
        'volume_total_annuel': volume_total_annuel,
        'nb_releves_total': nb_releves_total,
        'moyenne_annuelle': moyenne_annuelle,
        'mediane_annuelle': mediane_annuelle,
        'stats_par_mois': stats_par_mois,
        'graphique': graphique
    }


def analyser_point_eau_specifique(point_eau, annee):
    """Analyse la consommation d'un point d'eau spécifique"""
    from collections import defaultdict

    # Récupérer l'historique complet du point d'eau pour les statistiques de synthèse
    releves_historique = Releve.objects.filter(
        point_eau=point_eau,
        volume_facture__gt=0
    ).order_by('datereleve')

    # Récupérer les relevés de ce point d'eau pour l'année sélectionnée
    releves = Releve.objects.filter(
        point_eau=point_eau,
        datereleve__year=annee
    ).order_by('datereleve')

    mois_liste = list(range(1, 13))
    volumes_par_mois = defaultdict(float)
    nb_releves_par_mois = defaultdict(int)

    releves_list = list(releves)

    for releve in releves_list:
        volume = float(releve.volume_facture) if releve.volume_facture else 0
        if volume > 0 and releve.datereleve and releve.datereleve.year == annee:
            nb_releves_par_mois[releve.datereleve.month] += 1

    for i, releve in enumerate(releves_list):
        volume = float(releve.volume_facture) if releve.volume_facture else 0
        if volume <= 0:
            continue

        # Trouver le relevé précédent
        if i > 0:
            date_debut = releves_list[i-1].datereleve
        else:
            releve_precedent = Releve.objects.filter(
                point_eau=point_eau,
                datereleve__lt=releve.datereleve
            ).order_by('-datereleve').first()

            if releve_precedent and releve_precedent.datereleve:
                date_debut = releve_precedent.datereleve
            else:
                date_debut = releve.datereleve.replace(day=1)

        date_fin = releve.datereleve
        delta_jours = (date_fin - date_debut).days
        if delta_jours <= 0:
            delta_jours = 1

        conso_journaliere = volume / delta_jours

        # Distribuer sur les mois
        date_courante = date_debut
        while date_courante <= date_fin:
            mois = date_courante.month
            annee_courante = date_courante.year

            if date_courante.year == date_debut.year and date_courante.month == date_debut.month:
                debut_mois = date_debut
            else:
                debut_mois = date_courante.replace(day=1)

            if date_courante.month == 12:
                dernier_jour_mois = date_courante.replace(year=date_courante.year + 1, month=1, day=1) - relativedelta(days=1)
            else:
                dernier_jour_mois = date_courante.replace(month=date_courante.month + 1, day=1) - relativedelta(days=1)

            if date_courante.year == date_fin.year and date_courante.month == date_fin.month:
                fin_mois = date_fin
            else:
                fin_mois = dernier_jour_mois

            jours_dans_mois = (fin_mois - debut_mois).days + 1
            volume_mois = conso_journaliere * jours_dans_mois

            if annee_courante == annee and volume_mois > 0:
                volumes_par_mois[mois] += volume_mois

            if date_courante.month == 12:
                date_courante = date_courante.replace(year=date_courante.year + 1, month=1, day=1)
            else:
                date_courante = date_courante.replace(month=date_courante.month + 1, day=1)

    # Statistiques par mois
    stats_par_mois = []
    for mois in mois_liste:
        stats_par_mois.append({
            'mois': mois,
            'mois_nom': ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                        'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'][mois],
            'volume': volumes_par_mois[mois],
            'nb_releves': nb_releves_par_mois[mois]
        })

    volume_total_annuel = sum(volumes_par_mois.values())

    # Statistiques sur l'historique complet du point d'eau
    historiques_volumes = [
        float(releve.volume_facture) if releve.volume_facture else 0
        for releve in releves_historique
        if (float(releve.volume_facture) if releve.volume_facture else 0) > 0
    ]
    nb_releves_total = len(historiques_volumes)

    if historiques_volumes:
        moyenne_historique = sum(historiques_volumes) / len(historiques_volumes)
        volumes_sorted = sorted(historiques_volumes)
        n = len(volumes_sorted)
        if n % 2 == 0:
            mediane_historique = (volumes_sorted[n//2 - 1] + volumes_sorted[n//2]) / 2
        else:
            mediane_historique = volumes_sorted[n//2]
    else:
        moyenne_historique = 0
        mediane_historique = 0

    # Graphique
    graphique = {
        'labels': [s['mois_nom'][:3] for s in stats_par_mois],
        'volumes': [round(s['volume'], 2) if s['nb_releves'] > 0 else None for s in stats_par_mois],
        'nb_releves': [s['nb_releves'] for s in stats_par_mois]
    }

    return {
        'volume_total_annuel': volume_total_annuel,
        'nb_releves_total': nb_releves_total,
        'moyenne_historique': moyenne_historique,
        'mediane_historique': mediane_historique,
        'stats_par_mois': stats_par_mois,
        'graphique': graphique
    }


def comparer_avec_ouvrage(stats_point_eau, stats_ouvrage):
    """Compare les statistiques du point d'eau avec celles de l'ouvrage"""
    if not stats_point_eau or not stats_ouvrage:
        return None

    moyenne_pe = stats_point_eau.get('moyenne_historique', 0)
    moyenne_ouvrage = stats_ouvrage.get('moyenne_annuelle', 0)

    if moyenne_ouvrage > 0:
        ecart_pourcentage = ((moyenne_pe - moyenne_ouvrage) / moyenne_ouvrage) * 100
        position = 'au-dessus' if ecart_pourcentage > 0 else 'en-dessous' if ecart_pourcentage < 0 else 'égale'
    else:
        ecart_pourcentage = 0
        position = 'indéterminée'

    return {
        'moyenne_pe': moyenne_pe,
        'moyenne_ouvrage': moyenne_ouvrage,
        'ecart_pourcentage': abs(ecart_pourcentage),
        'position': position
    }
