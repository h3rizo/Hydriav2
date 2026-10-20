"""
Vues pour la gestion des relevés de compteurs avec workflow complet
"""
from django.shortcuts import redirect, render
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.db.models import F, Q, Max, Avg, Sum
from django.db.models.functions import Coalesce
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import datetime, timedelta
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, Alignment, PatternFill
from django.http import HttpResponse
import json
import base64
import binascii
from decimal import Decimal
import pytz

from .models import (
    Releve, CompteurTete, TarifVolumetrique, PointEau, ModaliteGestion,
    ConsoCarteSociale, TypePointEau, CompteurAbonne, ChangementCompteurAbonne,
)
from apps.core.views_mobile_auth import mobile_auth_required
from .services_compteurs_abonnes import (
    build_consumption_segments, save_consumption_segments, serialize_segments,
)
from apps.organization.models import Ouvrage
from apps.geography.models import Parcelle
from apps.organization.scoping import (
    apply_user_responsable_ouvrage_scope,
    get_user_accessible_gestionnaire_ids,
)
from apps.infrastructure.models import CarteSociale

CONSOMMATION_ECART_SEUIL = 0.5
RELEVES_MODALITES_AUTORISEES = ['au_volume', 'mixte']
POINT_EAU_COUPE_EXCLUSION_DAYS = 90


def _parse_iso_date(date_str):
    if not date_str:
        return None
    return datetime.strptime(str(date_str), '%Y-%m-%d').date()


def _get_previous_releve_for_date(point_eau_id, date_releve):
    return Releve.objects.filter(
        point_eau_id=point_eau_id,
        datereleve__lt=date_releve
    ).order_by('-datereleve', '-created_at').first()


def _get_next_releves_for_date(point_eau_id, date_releve):
    return Releve.objects.filter(
        point_eau_id=point_eau_id,
        datereleve__gt=date_releve
    ).order_by('datereleve', 'created_at', 'id')


def _recompute_releve_chain(point_eau_id, starting_releve):
    previous_index = Decimal(str(starting_releve.nouvelindex or 0))

    for releve in _get_next_releves_for_date(point_eau_id, starting_releve.datereleve):
        volume_carte_sociale = Decimal(str(
            ConsoCarteSociale.objects.filter(releve=releve).aggregate(
                total=Sum('volume_total')
            )['total'] or 0
        ))
        volume_non_facture = Decimal(str(getattr(releve, 'volume_non_facture', 0) or 0))
        nouvel_index = Decimal(str(releve.nouvelindex or 0))
        consommation = nouvel_index - previous_index
        volume_facture = consommation - volume_carte_sociale - volume_non_facture

        releve.ancienindex = float(previous_index)
        releve.consommation = float(consommation)
        releve.volume_carte_sociale = float(volume_carte_sociale)
        releve.volume_facture = float(volume_facture)

        # Un relevé recalculé au milieu de la chaîne doit repasser par la facturation.
        if not (releve.numeroDiameX and releve.numeroDiameX.strip()):
            releve.montant = None
            releve.statut = 'en_attente'
            releve.facture_imprimee = False
            releve.date_impression = None
            releve.numero_facture = None

        releve.save()
        previous_index = Decimal(str(releve.nouvelindex or 0))


def _is_directeur_user(user):
    if not user or not user.is_authenticated:
        return False

    employe = getattr(user, 'employe', None)
    if employe and hasattr(employe, 'is_directeur') and employe.is_directeur:
        return True
    return user.groups.filter(name='Directeur').exists()


def _get_user_organisation_id(user):
    employe = getattr(user, 'employe', None)
    base = getattr(employe, 'base', None)
    return getattr(base, 'organisation_id', None)


def _get_allowed_ouvrage_ids(user, modalites_paiement=None):
    """
    Ouvrages autorisés via ModaliteGestion active (date_fin NULL),
    cloisonnés par organisation du user (gestionnaire).
    """
    modalites = ModaliteGestion.objects.filter(date_fin__isnull=True)

    if modalites_paiement:
        modalites = modalites.filter(modalitepaiement__in=modalites_paiement)

    if not (getattr(user, 'is_superuser', False) or _is_directeur_user(user)):
        gestionnaire_ids = get_user_accessible_gestionnaire_ids(user)
        if gestionnaire_ids is None:
            pass
        elif not gestionnaire_ids:
            return modalites.none().values_list('ouvrage_id', flat=True)
        else:
            modalites = modalites.filter(gestionnaire_id__in=gestionnaire_ids)

    ouvrage_ids = set(
        modalites.exclude(ouvrage_id__isnull=True).values_list('ouvrage_id', flat=True).distinct()
    )
    # Postes de support (caissière, assistant(e) admin, RAF...) : ouvrages de
    # leur base (responsables actifs de la même base), pas leur hiérarchie.
    scoped_ids = apply_user_responsable_ouvrage_scope(
        ouvrage_ids,
        user,
        allow_same_base_support_roles=True,
    )
    return list(ouvrage_ids if scoped_ids is None else scoped_ids)


def _get_consommation_analysis(point_eau_id, nouvelle_consommation=None):
    historiques_qs = Releve.objects.filter(
        point_eau_id=point_eau_id,
        consommation__isnull=False,
        consommation__gt=0
    )

    nb_releves_precedents = historiques_qs.count()
    moyenne_consommation = float(
        historiques_qs.aggregate(avg=Avg('consommation')).get('avg') or 0
    )

    analyse = {
        'nb_releves_precedents': nb_releves_precedents,
        'moyenne_consommation': moyenne_consommation,
        'seuil_ecart': CONSOMMATION_ECART_SEUIL,
        'depassement_50': False,
        'ecart_relatif': None,
        'ecart_pourcentage': None,
    }

    if (
        nouvelle_consommation is not None
        and nb_releves_precedents > 0
        and moyenne_consommation > 0
    ):
        ecart_relatif = abs(float(nouvelle_consommation) - moyenne_consommation) / moyenne_consommation
        analyse['ecart_relatif'] = ecart_relatif
        analyse['ecart_pourcentage'] = round(ecart_relatif * 100, 2)
        analyse['depassement_50'] = ecart_relatif > CONSOMMATION_ECART_SEUIL

    return analyse


def _motifs_blocage_impression(analyse_consommation, volume_non_facture, user):
    """
    Motifs pour lesquels un agent ne peut pas imprimer la facture sur place.

    Règles : consommation à plus de ±50 % de la moyenne du point d'eau, ou
    volume non facturé différent de 0 (les cartes sociales ne comptent pas).
    Le Directeur n'est jamais bloqué. Liste vide = impression autorisée.
    """
    if _is_directeur_user(user):
        return []
    motifs = []
    if analyse_consommation.get('depassement_50'):
        motifs.append(
            "Consommation en écart de %.0f %% par rapport à la moyenne (%.2f m3) : limite de ±%.0f %%."
            % (
                analyse_consommation.get('ecart_pourcentage') or 0,
                analyse_consommation.get('moyenne_consommation') or 0,
                CONSOMMATION_ECART_SEUIL * 100,
            )
        )
    if volume_non_facture != 0:
        motifs.append("Volume non facturé différent de 0 (hors cartes sociales).")
    return motifs


def _releve_ticket_data(releve):
    """Champs du relevé nécessaires au ticket 80 mm (réponse save-releve-terrain)."""
    return {
        'id': str(releve.id),
        'numero_facture': releve.numero_facture or '',
        'date_releve': releve.datereleve.strftime('%d/%m/%Y'),
        'ancien_index': float(releve.ancienindex),
        'nouvel_index': float(releve.nouvelindex),
        'volume_consomme': float(releve.consommation),
        'volume_carte_sociale': float(releve.volume_carte_sociale or 0),
        'volume_non_facture': float(releve.volume_non_facture or 0),
        'volume_facture': float(releve.volume_facture or 0),
        'montant': float(releve.montant) if releve.montant is not None else None,
    }


def _organisation_ticket_data(point_eau):
    """En-tête organisation du ticket : gestionnaire actif de l'ouvrage, sinon None."""
    return organisation_ticket_data_ouvrage(point_eau.ouvrage)


def organisation_ticket_data_ouvrage(ouvrage):
    if not ouvrage:
        return None
    modalite = ouvrage.modalites_gestion.filter(date_fin__isnull=True).first()
    organisation = modalite.gestionnaire if modalite else None
    if not organisation:
        return None
    return {
        'nom': organisation.nom_organisation,
        'adresse1': organisation.adresse1,
        'localite': organisation.localite,
        'province': organisation.province,
        'telephone': organisation.telephone,
        'nif': organisation.nif,
        'stat': organisation.stat,
    }


def releves_workflow(request):
    """
    Page principale du workflow de gestion des relevés
    """
    # Récupérer les ouvrages avec modalité au volume ou mixte (actifs)
    allowed_ouvrage_ids = _get_allowed_ouvrage_ids(
        request.user,
        modalites_paiement=RELEVES_MODALITES_AUTORISEES
    )
    ouvrages = Ouvrage.objects.filter(
        modalites_gestion__modalitepaiement__in=['au_volume', 'mixte'],
        modalites_gestion__date_fin__isnull=True,
        id__in=allowed_ouvrage_ids
    ).select_related('type_ouvrage').distinct()

    # Enrichir avec nom de modalité
    ouvrages_list = []
    gestionnaire_ids = get_user_accessible_gestionnaire_ids(request.user)
    user_is_global = getattr(request.user, 'is_superuser', False) or _is_directeur_user(request.user)
    for ouvrage in ouvrages:
        modalite_qs = ouvrage.modalites_gestion.filter(
            date_fin__isnull=True,
            modalitepaiement__in=RELEVES_MODALITES_AUTORISEES
        )
        if not user_is_global and gestionnaire_ids is not None:
            if gestionnaire_ids:
                modalite_qs = modalite_qs.filter(gestionnaire_id__in=gestionnaire_ids)
            else:
                modalite_qs = modalite_qs.none()
        modalite = modalite_qs.first()
        ouvrages_list.append({
            'id': ouvrage.id,
            'nom_ouvrage': ouvrage.nom_ouvrage,
            'modalite_nom': modalite.get_modalitepaiement_display() if modalite else 'N/A'
        })

    # Vérifier si l'utilisateur est directeur
    is_directeur = _is_directeur_user(request.user)

    types_points_eau = TypePointEau.objects.filter(actif=True).order_by('nom_type')
    parcelles_disponibles = Parcelle.objects.select_related(
        'village__fokontany__commune'
    ).order_by(
        'reference_parcelle'
    )

    return render(request, 'billing/releves_workflow.html', {
        'ouvrages': ouvrages_list,
        'is_directeur': is_directeur,
        'types_points_eau': types_points_eau,
        'parcelles_disponibles': parcelles_disponibles,
        'compact_base': True,
    })


@login_required
@require_http_methods(["GET", "POST"])
def gestion_consos_cartes_sociales(request):
    """Correction manuelle et securisee des dates de consommation sociale."""
    if not (getattr(request.user, 'is_superuser', False) or _is_directeur_user(request.user)):
        messages.error(request, 'Acces reserve aux Directeurs.')
        return redirect('billing:releves')

    if request.method == 'POST':
        selected_ids = list(dict.fromkeys(request.POST.getlist('consommation_ids')))
        try:
            target_date = _parse_iso_date(request.POST.get('date_cible'))
        except (TypeError, ValueError):
            target_date = None
        confirmation = (request.POST.get('confirmation') or '').strip().upper()

        if not selected_ids:
            messages.error(request, 'Selectionnez au moins une consommation.')
        elif not target_date:
            messages.error(request, 'La date cible est invalide.')
        elif confirmation != 'DEPLACER':
            messages.error(request, 'Saisissez DEPLACER pour confirmer la correction.')
        elif len(selected_ids) > 500:
            messages.error(request, 'La correction est limitee a 500 lignes par operation.')
        else:
            try:
                with transaction.atomic():
                    consos = list(
                        ConsoCarteSociale.objects.select_for_update(of=('self',))
                        .select_related('releve', 'releve__point_eau')
                        .filter(id__in=selected_ids)
                    )
                    if len(consos) != len(selected_ids):
                        raise ValueError('Une ou plusieurs consommations sont introuvables.')

                    releves = {conso.releve_id: conso.releve for conso in consos if conso.releve_id}
                    releves_payes = [
                        releve for releve in releves.values()
                        if releve.numeroDiameX and releve.numeroDiameX.strip()
                    ]
                    if releves_payes:
                        raise ValueError(
                            f'{len(releves_payes)} releve(s) sont deja enregistres dans DiameX. '
                            'Leur date ne peut pas etre modifiee depuis cette page.'
                        )

                    for releve in releves.values():
                        conflit = Releve.objects.filter(
                            point_eau_id=releve.point_eau_id,
                            datereleve=target_date,
                        ).exclude(id=releve.id).exists()
                        if conflit:
                            point_nom = getattr(releve.point_eau, 'code_point_eau', None) or releve.abonne
                            raise ValueError(
                                f'Un releve existe deja le {target_date:%d/%m/%Y} pour {point_nom}.'
                            )

                    consos_liees_modifiees = 0
                    for releve in releves.values():
                        releve.datereleve = target_date
                        releve.save(update_fields=['datereleve'])
                        consos_liees_modifiees += ConsoCarteSociale.objects.filter(
                            releve_id=releve.id
                        ).exclude(date=target_date).update(date=target_date)

                    ids_sans_releve = [conso.id for conso in consos if not conso.releve_id]
                    consos_sans_releve_modifiees = ConsoCarteSociale.objects.filter(
                        id__in=ids_sans_releve
                    ).exclude(date=target_date).update(date=target_date)

                messages.success(
                    request,
                    f'Correction terminee : {len(releves)} releve(s), '
                    f'{consos_liees_modifiees} consommation(s) liee(s) et '
                    f'{consos_sans_releve_modifiees} ancienne(s) consommation(s) sans releve mises a jour.'
                )
                return redirect(f"{request.path}?date_debut={target_date:%Y-%m-01}&date_fin={target_date:%Y-%m-%d}")
            except ValueError as exc:
                messages.error(request, str(exc))
            except Exception as exc:
                messages.error(request, f'Correction annulee : {exc}')

    consommations = ConsoCarteSociale.objects.select_related(
        'carte_sociale',
        'carte_sociale__ouvrage',
        'carte_sociale__point_eau',
        'releve',
        'releve__point_eau',
    ).annotate(
        # Les anciennes consommations importees n'ont pas toujours de releve.
        # Dans ce seul cas, leur propre date sert de valeur de secours.
        date_regroupement=Coalesce('releve__datereleve', 'date'),
    ).order_by(
        'carte_sociale__ouvrage__nom_ouvrage',
        'carte_sociale__point_eau__code_point_eau',
        'releve__point_eau__code_point_eau',
        F('date_regroupement').desc(nulls_last=True),
        'carte_sociale__numero_carte',
    )

    date_debut = request.GET.get('date_debut', '')
    date_fin = request.GET.get('date_fin', '')
    recherche = (request.GET.get('q') or '').strip()
    liaison = request.GET.get('liaison', 'toutes')
    ouvrage_id = request.GET.get('ouvrage', '')

    if date_debut:
        try:
            parsed = _parse_iso_date(date_debut)
        except (TypeError, ValueError):
            parsed = None
        if parsed:
            consommations = consommations.filter(date__gte=parsed)
    if date_fin:
        try:
            parsed = _parse_iso_date(date_fin)
        except (TypeError, ValueError):
            parsed = None
        if parsed:
            consommations = consommations.filter(date__lte=parsed)
    if recherche:
        consommations = consommations.filter(
            Q(carte_sociale__numero_carte__icontains=recherche)
            | Q(carte_sociale__nom_beneficiaire__icontains=recherche)
            | Q(carte_sociale__point_eau__code_point_eau__icontains=recherche)
            | Q(releve__abonne__icontains=recherche)
        )
    if liaison == 'liees':
        consommations = consommations.filter(releve__isnull=False)
    elif liaison == 'sans_releve':
        consommations = consommations.filter(releve__isnull=True)
    if ouvrage_id:
        consommations = consommations.filter(carte_sociale__ouvrage_id=ouvrage_id)

    paginator = Paginator(consommations, 100)
    page_obj = paginator.get_page(request.GET.get('page'))
    grouped_ouvrages_map = {}
    for conso in page_obj.object_list:
        ouvrage = conso.carte_sociale.ouvrage
        ouvrage_key = str(ouvrage.id) if ouvrage else 'sans-ouvrage'
        ouvrage_group = grouped_ouvrages_map.setdefault(ouvrage_key, {
            'ouvrage': ouvrage,
            'points_map': {},
        })

        point_eau = conso.carte_sociale.point_eau or (
            conso.releve.point_eau if conso.releve else None
        )
        point_key = str(point_eau.id) if point_eau else 'sans-point-eau'
        point_group = ouvrage_group['points_map'].setdefault(point_key, {
            'point_eau': point_eau,
            'nom_abonne': (
                getattr(point_eau, 'nomabonne', None)
                or (conso.releve.abonne if conso.releve else None)
                or 'Abonne non renseigne'
            ),
            'dates_map': {},
        })

        date_regroupement = conso.date_regroupement
        date_key = date_regroupement.isoformat() if date_regroupement else 'sans-date'
        date_group = point_group['dates_map'].setdefault(date_key, {
            'date_releve': date_regroupement,
            'date_de_secours': not bool(conso.releve_id),
            'consommations': [],
        })
        date_group['consommations'].append(conso)

    grouped_ouvrages = []
    for ouvrage_group in grouped_ouvrages_map.values():
        points = []
        for point_group in ouvrage_group['points_map'].values():
            point_group['dates'] = list(point_group.pop('dates_map').values())
            points.append(point_group)
        ouvrage_group['points'] = points
        ouvrage_group.pop('points_map')
        grouped_ouvrages.append(ouvrage_group)

    ouvrages = Ouvrage.objects.filter(
        cartes_sociales_infra__consommations__isnull=False
    ).distinct().order_by('nom_ouvrage')

    return render(request, 'billing/gestion_consos_cartes_sociales.html', {
        'page_obj': page_obj,
        'grouped_ouvrages': grouped_ouvrages,
        'ouvrages': ouvrages,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'recherche': recherche,
        'liaison': liaison,
        'ouvrage_id': ouvrage_id,
        'compact_base': True,
    })


@require_http_methods(["GET"])
def api_points_eau_par_ouvrage(request, ouvrage_id):
    """
    Retourne la liste des points d'eau pour un ouvrage donné.
    Si les paramètres annee/mois sont fournis, chaque point est annoté d'un
    champ deja_releve_mois (relevé déjà saisi ce mois-là ou non) — utilisé par
    le workflow de campagne pour filtrer les points restant à relever.
    """
    try:
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(
            request.user,
            modalites_paiement=RELEVES_MODALITES_AUTORISEES
        )
        if not Ouvrage.objects.filter(id=ouvrage_id, id__in=allowed_ouvrage_ids).exists():
            return JsonResponse({'error': 'Ouvrage non autorisé'}, status=403)

        points_eau = PointEau.objects.filter(
            ouvrage_id=ouvrage_id
        ).select_related('type_point_eau', 'parcelle__village')

        campagne_annee = request.GET.get('annee')
        campagne_mois = request.GET.get('mois')
        points_deja_releves_ids = None
        if campagne_annee and campagne_mois:
            try:
                points_deja_releves_ids = set(
                    Releve.objects.filter(
                        point_eau__ouvrage_id=ouvrage_id,
                        datereleve__year=int(campagne_annee),
                        datereleve__month=int(campagne_mois),
                    ).values_list('point_eau_id', flat=True).distinct()
                )
            except (TypeError, ValueError):
                points_deja_releves_ids = None

        # Fonction pour extraire le type normalisé
        def get_type_code(type_nom):
            type_lower = type_nom.lower() if type_nom else ''
            if 'kiosque' in type_lower:
                return 'kiosque'
            elif 'bi' in type_lower or 'borne' in type_lower and 'individu' in type_lower:
                return 'bi'
            elif 'bp' in type_lower or 'borne' in type_lower and 'public' in type_lower:
                return 'bp'
            else:
                return 'autre'

        today = timezone.localdate()
        date_limite_coupure = today - timedelta(days=POINT_EAU_COUPE_EXCLUSION_DAYS)
        inclure_coupes = request.GET.get('inclure_coupes', 'false').lower() == 'true'

        # Préparer la liste avec tri
        points_eau_list = []
        points_eau_coupes_longue_duree = 0
        for pe in points_eau:
            date_arret = pe.datearretbranchement
            if isinstance(date_arret, datetime):
                date_arret = timezone.localtime(date_arret).date() if timezone.is_aware(date_arret) else date_arret.date()

            est_coupe_longue_duree = date_arret and date_arret < date_limite_coupure
            if est_coupe_longue_duree:
                points_eau_coupes_longue_duree += 1
                if not inclure_coupes:
                    continue

            # Compter les cartes sociales liées à ce point d'eau
            nb_cartes_sociales = CarteSociale.objects.filter(
                point_eau=pe,
                statut='active'  # Cartes sociales actives uniquement
            ).count()

            entry = {
                'id': str(pe.id),
                'code': pe.code_point_eau or f'PE-{str(pe.id)[:8]}',
                'nom': pe.nomabonne or 'N/A',
                'village': pe.parcelle.village.nom_village if (pe.parcelle and pe.parcelle.village) else 'N/A',
                'type': pe.type_point_eau.nom_type if pe.type_point_eau else 'N/A',
                'est_institutionnel': bool(pe.estbranchementinstitutionnel),
                'type_code': get_type_code(pe.type_point_eau.nom_type if pe.type_point_eau else ''),
                'idxls': pe.idxls or '',
                'parcelle_id': str(pe.parcelle_id) if pe.parcelle_id else '',
                'parcelle': pe.parcelle.reference_parcelle if pe.parcelle else 'N/A',
                'nb_cartes_sociales': nb_cartes_sociales,
                'date_arret': date_arret.strftime('%Y-%m-%d') if date_arret else None,
                'date_arret_display': date_arret.strftime('%d/%m/%Y') if date_arret else None,
            }
            if points_deja_releves_ids is not None:
                entry['deja_releve_mois'] = pe.id in points_deja_releves_ids
            points_eau_list.append(entry)

        # Trier: Kiosques > BI > BP > Autres
        type_order = {'kiosque': 1, 'bi': 2, 'bp': 3, 'autre': 4}
        points_eau_list.sort(key=lambda x: type_order.get(x['type_code'], 4))

        data = {
            'points_eau': points_eau_list,
            'points_eau_coupes_longue_duree': points_eau_coupes_longue_duree,
        }

        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@require_http_methods(["GET"])
def api_ouvrages_campagne(request):
    """
    Liste des ouvrages du périmètre avec la progression des relevés pour un
    mois donné (par défaut le mois en cours) — alimente l'écran de démarrage
    de campagne pour voir d'un coup d'œil quels ouvrages restent à relever,
    sans les ouvrir un par un.
    """
    try:
        today = timezone.localdate()
        try:
            annee = int(request.GET.get('annee') or today.year)
            mois = int(request.GET.get('mois') or today.month)
        except (TypeError, ValueError):
            annee, mois = today.year, today.month

        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(
            request.user,
            modalites_paiement=RELEVES_MODALITES_AUTORISEES
        )
        ouvrages = Ouvrage.objects.filter(id__in=allowed_ouvrage_ids).order_by('nom_ouvrage')

        date_limite_coupure = today - timedelta(days=POINT_EAU_COUPE_EXCLUSION_DAYS)

        ouvrages_list = []
        for ouvrage in ouvrages:
            points_actifs_ids = []
            # District/commune de l'ouvrage = ceux de son premier point d'eau actif
            # (chaîne géographique : PointEau -> Parcelle -> Village -> Fokontany -> Commune -> District).
            district_nom = 'Sans district'
            commune_nom = 'Sans commune'
            geo_trouvee = False
            points_qs = PointEau.objects.filter(ouvrage_id=ouvrage.id).select_related(
                'parcelle__village__fokontany__commune__district'
            )
            for pe in points_qs:
                date_arret = pe.datearretbranchement
                if isinstance(date_arret, datetime):
                    date_arret = timezone.localtime(date_arret).date() if timezone.is_aware(date_arret) else date_arret.date()
                if date_arret and date_arret < date_limite_coupure:
                    continue
                points_actifs_ids.append(pe.id)
                if not geo_trouvee:
                    village = pe.parcelle.village if pe.parcelle else None
                    fokontany = village.fokontany if village else None
                    commune = fokontany.commune if fokontany else None
                    if commune:
                        commune_nom = commune.nom_commune
                        district_nom = commune.district.nom_district if commune.district else 'Sans district'
                        geo_trouvee = True

            total = len(points_actifs_ids)
            if total == 0:
                continue

            nb_releves = Releve.objects.filter(
                point_eau_id__in=points_actifs_ids,
                datereleve__year=annee,
                datereleve__month=mois,
            ).values_list('point_eau_id', flat=True).distinct().count()

            ouvrages_list.append({
                'id': str(ouvrage.id),
                'nom_ouvrage': ouvrage.nom_ouvrage,
                'nb_points_eau': total,
                'nb_releves_mois': nb_releves,
                'district': district_nom,
                'commune': commune_nom,
            })

        ouvrages_list.sort(key=lambda o: (o['district'], o['commune'], o['nom_ouvrage'] or ''))

        return JsonResponse({'ouvrages': ouvrages_list, 'annee': annee, 'mois': mois})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def api_changement_compteur_abonne(request):
    """Remplace un compteur sans modifier les releves ni les factures existants."""
    try:
        if not (getattr(request.user, 'is_superuser', False) or _is_directeur_user(request.user)):
            return JsonResponse({'success': False, 'error': 'Acces reserve aux Directeurs'}, status=403)

        data = json.loads(request.body or '{}') if request.content_type == 'application/json' else request.POST
        point_eau_id = data.get('point_eau_id')
        date_changement = _parse_iso_date(data.get('date_changement'))
        nouveau_numero = str(data.get('nouveau_numero') or '').strip()
        ancien_numero = str(data.get('ancien_numero') or '').strip()
        motif = str(data.get('motif') or '').strip()
        explication = str(data.get('explication') or '').strip()
        illisible = str(data.get('ancien_compteur_illisible', '')).lower() in ('1', 'true', 'yes', 'on')

        if not point_eau_id or not date_changement or not nouveau_numero or not motif or not explication:
            return JsonResponse({
                'success': False,
                'error': 'Point d eau, date, nouveau numero, motif et explication sont obligatoires.'
            }, status=400)

        try:
            index_initial_nouveau = Decimal(str(data.get('index_initial_nouveau')))
            index_retrait_saisi = data.get('index_retrait')
            estimation_saisie = data.get('consommation_ancienne_estimee')
            index_retrait = Decimal(str(index_retrait_saisi)) if index_retrait_saisi not in (None, '') else None
            estimation = Decimal(str(estimation_saisie)) if estimation_saisie not in (None, '') else None
        except Exception:
            return JsonResponse({'success': False, 'error': 'Les index saisis sont invalides.'}, status=400)

        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(
            request.user, modalites_paiement=RELEVES_MODALITES_AUTORISEES
        )
        with transaction.atomic():
            point_eau = PointEau.objects.select_for_update().filter(
                id=point_eau_id, ouvrage_id__in=allowed_ouvrage_ids
            ).first()
            if not point_eau:
                return JsonResponse({'success': False, 'error': 'Point d eau introuvable ou non autorise.'}, status=404)

            dernier_releve = Releve.objects.select_for_update().filter(
                point_eau=point_eau
            ).order_by('-datereleve', '-created_at').first()
            if dernier_releve and date_changement < dernier_releve.datereleve:
                return JsonResponse({
                    'success': False,
                    'error': 'Le changement est anterieur au dernier releve. Les factures historiques ne seront pas reecrites.'
                }, status=400)

            ancien_compteur = point_eau.compteur_abonne_actuel
            if ancien_compteur:
                ancien_compteur = CompteurAbonne.objects.select_for_update().get(id=ancien_compteur.id)
                if ancien_numero and ancien_numero.casefold() != ancien_compteur.numero.casefold():
                    return JsonResponse({'success': False, 'error': "Le numero de l'ancien compteur ne correspond pas au compteur actif."}, status=400)
            else:
                if not ancien_numero:
                    return JsonResponse({'success': False, 'error': "Le numero de l'ancien compteur est obligatoire pour initialiser l'historique."}, status=400)
                if CompteurAbonne.objects.filter(numero__iexact=ancien_numero).exists():
                    return JsonResponse({'success': False, 'error': "Ce numero d'ancien compteur existe deja."}, status=400)
                installation = date_changement
                if point_eau.datebranchement:
                    installation = point_eau.datebranchement.date() if hasattr(point_eau.datebranchement, 'date') else point_eau.datebranchement
                elif dernier_releve:
                    installation = dernier_releve.datereleve
                ancien_compteur = CompteurAbonne.objects.create(
                    point_eau=point_eau,
                    numero=ancien_numero,
                    date_installation=installation,
                    index_initial=Decimal(str(dernier_releve.ancienindex if dernier_releve else 0)),
                )

            if nouveau_numero.casefold() == ancien_compteur.numero.casefold():
                return JsonResponse({'success': False, 'error': 'Le nouveau compteur doit avoir un autre numero.'}, status=400)
            if CompteurAbonne.objects.filter(numero__iexact=nouveau_numero).exists():
                return JsonResponse({'success': False, 'error': 'Ce numero de compteur existe deja.'}, status=400)

            changement_entrant_en_attente = ChangementCompteurAbonne.objects.filter(
                nouveau_compteur=ancien_compteur, releve_facture__isnull=True
            ).first()
            if changement_entrant_en_attente:
                index_reference = Decimal(str(changement_entrant_en_attente.index_initial_nouveau))
            else:
                index_reference = Decimal(str(
                    dernier_releve.nouvelindex if dernier_releve else ancien_compteur.index_initial
                ))
            if illisible:
                if estimation is None or estimation < 0:
                    return JsonResponse({'success': False, 'error': "Une consommation estimee positive ou nulle est obligatoire si l'ancien compteur est illisible."}, status=400)
                index_retrait = index_reference
            elif index_retrait is None:
                return JsonResponse({'success': False, 'error': "L'index de retrait est obligatoire."}, status=400)

            nouveau_compteur = CompteurAbonne(
                point_eau=point_eau,
                numero=nouveau_numero,
                date_installation=date_changement,
                index_initial=index_initial_nouveau,
            )
            nouveau_compteur.full_clean()
            nouveau_compteur.save()

            ancien_compteur.date_retrait = date_changement
            ancien_compteur.index_retrait = index_retrait
            ancien_compteur.statut = 'perdu' if motif == 'vole' else 'hors_service'
            ancien_compteur.full_clean()
            ancien_compteur.save(update_fields=['date_retrait', 'index_retrait', 'statut', 'updated_at'])

            changement = ChangementCompteurAbonne(
                point_eau=point_eau,
                ancien_compteur=ancien_compteur,
                nouveau_compteur=nouveau_compteur,
                releve_precedent=dernier_releve,
                date_changement=date_changement,
                index_reference_ancien=index_reference,
                index_retrait=index_retrait,
                index_initial_nouveau=index_initial_nouveau,
                motif=motif,
                explication=explication,
                ancien_compteur_illisible=illisible,
                consommation_ancienne_estimee=estimation if illisible else None,
                created_by=request.user,
            )
            changement.full_clean()
            changement.save()
            point_eau.compteur_abonne_actuel = nouveau_compteur
            point_eau.save(update_fields=['compteur_abonne_actuel'])

        return JsonResponse({
            'success': True,
            'message': 'Compteur remplace. La prochaine facture additionnera les deux segments.',
            'changement': {
                'id': str(changement.id),
                'ancien_numero': ancien_compteur.numero,
                'nouveau_numero': nouveau_compteur.numero,
                'volume_avant_changement': float(changement.volume_ancien),
                'index_initial_nouveau': float(changement.index_initial_nouveau),
            }
        })
    except ValidationError as exc:
        message = exc.message_dict if hasattr(exc, 'message_dict') else exc.messages
        return JsonResponse({'success': False, 'error': message}, status=400)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)


@require_http_methods(["GET"])
def api_point_eau_details(request, point_eau_id):
    """
    Retourne les détails d'un point d'eau avec historique des relevés
    """
    try:
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(
            request.user,
            modalites_paiement=RELEVES_MODALITES_AUTORISEES
        )
        point_eau = PointEau.objects.select_related(
            'type_point_eau', 'parcelle__village', 'compteur_abonne_actuel'
        ).filter(
            id=point_eau_id,
            ouvrage_id__in=allowed_ouvrage_ids
        ).first()
        if not point_eau:
            return JsonResponse({'error': 'Point d\'eau introuvable ou non autorisé'}, status=404)

        # Chercher le dernier relevé
        dernier_releve = Releve.objects.filter(
            point_eau_id=point_eau_id
        ).order_by('-datereleve').first()

        page = int(request.GET.get('page', 1) or 1)
        page_size = int(request.GET.get('page_size', 10) or 10)
        if page_size <= 0:
            page_size = 10
        if page_size > 100:
            page_size = 100

        historique_qs = Releve.objects.filter(
            point_eau_id=point_eau_id
        ).order_by('-datereleve')
        paginator = Paginator(historique_qs, page_size)
        page_obj = paginator.get_page(page)
        historique = page_obj.object_list

        # Type de point d'eau
        type_nom = point_eau.type_point_eau.nom_type if point_eau.type_point_eau else None

        # Village
        village_nom = None
        if hasattr(point_eau, 'parcelle') and point_eau.parcelle and point_eau.parcelle.village:
            village_nom = point_eau.parcelle.village.nom_village

        changements_en_attente = list(
            ChangementCompteurAbonne.objects.select_related('ancien_compteur', 'nouveau_compteur').filter(
                point_eau=point_eau, releve_facture__isnull=True
            ).order_by('date_changement', 'created_at')
        )
        dernier_changement = changements_en_attente[-1] if changements_en_attente else None
        volume_avant_compteur = sum(
            (changement.volume_ancien for changement in changements_en_attente), Decimal('0')
        )

        data = {
            'id': str(point_eau.id),
            'nom': point_eau.nomabonne or 'N/A',
            'code': point_eau.code_point_eau or f'PE-{point_eau.id}',
            'type': type_nom,
            'est_institutionnel': bool(point_eau.estbranchementinstitutionnel),
            'village': village_nom,
            'dernier_releve': {
                'nouvel_index': float(dernier_releve.nouvelindex),
                'date_releve': dernier_releve.datereleve.strftime('%Y-%m-%d'),
            } if dernier_releve else None,
            'compteur_abonne': {
                'id': str(point_eau.compteur_abonne_actuel_id),
                'numero': point_eau.compteur_abonne_actuel.numero,
                'index_reference': float(
                    dernier_changement.index_initial_nouveau if dernier_changement
                    else (
                        dernier_releve.nouvelindex
                        if dernier_releve and dernier_releve.compteur_abonne_id == point_eau.compteur_abonne_actuel_id
                        else point_eau.compteur_abonne_actuel.index_initial
                    )
                ),
                'volume_avant_compteur': float(volume_avant_compteur),
                'changement_en_attente': bool(changements_en_attente),
            } if point_eau.compteur_abonne_actuel else None,
            'changements_compteur_en_attente': [
                {
                    'date': changement.date_changement.isoformat(),
                    'ancien_numero': changement.ancien_compteur.numero,
                    'nouveau_numero': changement.nouveau_compteur.numero,
                    'volume_ancien': float(changement.volume_ancien),
                    'estime': changement.ancien_compteur_illisible,
                }
                for changement in changements_en_attente
            ],
            'historique': [
                {
                    'id': str(rel.id),
                    'date_releve': rel.datereleve.strftime('%d/%m/%Y'),
                    'ancien_index': float(rel.ancienindex),
                    'nouvel_index': float(rel.nouvelindex),
                    'volume_consomme': float(rel.consommation),
                    'volume_carte_sociale': float(getattr(rel, 'volume_carte_sociale', 0)),
                    'volume_non_facture': float(getattr(rel, 'volume_non_facture', 0)),
                    'volume_facture': float(getattr(rel, 'volume_facture', rel.consommation)),
                    'montant': float(rel.montant) if rel.montant else None,
                    'statut': rel.statut,
                    'numero_diamex': rel.numeroDiameX or '',
                    'remarque': rel.remarque or '',
                    'origine_calcul': rel.origine_calcul,
                    'compteur_numero': rel.compteur_abonne.numero if rel.compteur_abonne_id else '',
                    'segments_compteur': serialize_segments(rel),
                }
                for rel in historique
            ],
            'historique_pagination': {
                'page': page_obj.number,
                'page_size': page_size,
                'total': paginator.count,
                'num_pages': paginator.num_pages,
                'has_previous': page_obj.has_previous(),
                'has_next': page_obj.has_next(),
                'start_index': page_obj.start_index() if paginator.count > 0 else 0,
                'end_index': page_obj.end_index() if paginator.count > 0 else 0,
            },
            'analyse_consommation': _get_consommation_analysis(point_eau_id)
        }

        return JsonResponse(data)
    except PointEau.DoesNotExist:
        return JsonResponse({'error': 'Point d\'eau introuvable'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@require_http_methods(["GET"])
def api_releve_reference(request, point_eau_id):
    """
    Retourne le contexte de saisie pour une date donnee.
    Utilise pour la saisie historique reservee au directeur.
    """
    try:
        date_releve = _parse_iso_date(request.GET.get('date_releve'))
        if not date_releve:
            return JsonResponse({'error': 'Date releve invalide'}, status=400)
        if not (getattr(request.user, 'is_superuser', False) or _is_directeur_user(request.user)):
            return JsonResponse({'error': 'Acces reserve aux Directeurs'}, status=403)

        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(
            request.user,
            modalites_paiement=RELEVES_MODALITES_AUTORISEES
        )
        point_eau = PointEau.objects.filter(
            id=point_eau_id,
            ouvrage_id__in=allowed_ouvrage_ids
        ).first()
        if not point_eau:
            return JsonResponse({'error': 'Point d\'eau introuvable ou non autorise'}, status=404)

        previous_releve = _get_previous_releve_for_date(point_eau_id, date_releve)
        duplicate_exists = Releve.objects.filter(
            point_eau_id=point_eau_id,
            datereleve=date_releve
        ).exists()
        has_later_paid_releves = Releve.objects.filter(
            point_eau_id=point_eau_id,
            datereleve__gt=date_releve,
            numeroDiameX__isnull=False
        ).exclude(numeroDiameX='').exists()
        return JsonResponse({
            'success': True,
            'reference_releve': {
                'nouvel_index': float(previous_releve.nouvelindex),
                'date_releve': previous_releve.datereleve.strftime('%Y-%m-%d'),
            } if previous_releve else None,
            'duplicate_exists': duplicate_exists,
            'has_later_paid_releves': has_later_paid_releves,
            'analyse_consommation': _get_consommation_analysis(point_eau_id),
            'warning': None
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@require_http_methods(["GET"])
def api_imprimer_facture_releve(request, releve_id):
    """
    Retourne les données d'une facture individuelle de relevé pour impression A4.
    Accès réservé au Directeur.
    """
    try:
        if not (getattr(request.user, 'is_superuser', False) or _is_directeur_user(request.user)):
            return JsonResponse({'success': False, 'error': 'Acces reserve aux Directeurs'}, status=403)

        from .views_facturation import (
            calculer_montant_releve,
            _get_directeur_phone_for_organisation,
            _get_ouvrage_responsable_contact,
        )

        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(
            request.user,
            modalites_paiement=RELEVES_MODALITES_AUTORISEES
        )
        releve = Releve.objects.select_related(
            'point_eau__ouvrage',
            'point_eau__type_point_eau',
            'point_eau__parcelle',
            'point_eau__ouvrage__type_ouvrage',
        ).filter(
            id=releve_id,
            point_eau__ouvrage_id__in=allowed_ouvrage_ids
        ).first()
        if not releve:
            return JsonResponse({'success': False, 'error': 'Releve introuvable ou non autorise'}, status=404)

        resultat = calculer_montant_releve(releve)
        if not resultat.get('success'):
            return JsonResponse({'success': False, 'error': resultat.get('error') or 'Calcul impossible'}, status=400)

        factures_impayees = Releve.objects.filter(
            point_eau=releve.point_eau,
            montant__isnull=False,
            numeroDiameX__isnull=True,
            datereleve__lt=releve.datereleve,
            datereleve__year__gte=2025
        ).order_by('datereleve').values(
            'datereleve', 'ancienindex', 'nouvelindex', 'volume_facture', 'montant'
        )
        total_impaye = sum(f['montant'] for f in factures_impayees if f['montant'])

        ouvrage = getattr(releve.point_eau, 'ouvrage', None)
        organisation_id = _get_user_organisation_id(request.user)
        if not organisation_id and ouvrage:
            organisation_id = getattr(ouvrage, 'organisation_id', None)
        responsable_contact = _get_ouvrage_responsable_contact(getattr(ouvrage, 'id', None), releve.datereleve)
        organisation = None
        if organisation_id:
            from apps.organization.models import Organisation
            organisation = Organisation.objects.filter(id=organisation_id).first()

        releve_data = {
            'releve_id': str(releve.id),
            'ouvrage_nom': ouvrage.nom_ouvrage if ouvrage else '',
            'responsable_ouvrage_nom': responsable_contact['nom'],
            'responsable_ouvrage_telephone': responsable_contact['telephone'],
            'numero_facture': releve.numero_facture or '',
            'point_eau': releve.point_eau.code_point_eau or releve.point_eau.nomabonne,
            'abonne': releve.abonne or 'N/A',
            'idxls': releve.point_eau.idxls or '',
            'ancienindex': float(releve.ancienindex) if releve.ancienindex is not None else None,
            'nouvelindex': float(releve.nouvelindex) if releve.nouvelindex is not None else None,
            'parcelle': releve.point_eau.parcelle.reference_parcelle if releve.point_eau.parcelle else 'N/A',
            'type_point_eau': releve.point_eau.type_point_eau.nom_type if releve.point_eau.type_point_eau else 'N/A',
            'volume_facture': float(releve.volume_facture or 0),
            'montant_calcule': resultat['montant_total'],
            'montant_enregistre': float(releve.montant) if releve.montant else 0,
            'facture_imprimee': releve.facture_imprimee or False,
            'detail_calcul': resultat['detail'],
            'segments_compteur': serialize_segments(releve),
            'factures_impayees': list(factures_impayees),
            'total_impaye': float(total_impaye),
            'success': True,
            'date_facture': releve.datereleve.strftime('%Y-%m-%d') if releve.datereleve else '',
        }
        organisation_data = {
            'nom': getattr(organisation, 'nom_organisation', '') or 'HYDRIA',
            'logo_url': getattr(getattr(organisation, 'logo', None), 'url', '') if organisation else '',
            'nif': getattr(organisation, 'nif', '') if organisation else '',
            'stat': getattr(organisation, 'stat', '') if organisation else '',
            'adresse': getattr(organisation, 'adresse', '') if organisation else '',
            'directeur_telephone': _get_directeur_phone_for_organisation(organisation_id),
        }
        employe = getattr(request.user, 'employe', None)
        base = getattr(employe, 'base', None)
        organisation_data['base'] = getattr(base, 'nom_base', '') if base else ''
        organisation_data['base_telephone'] = getattr(base, 'telephone', '') if base else ''

        return JsonResponse({
            'success': True,
            'releve': releve_data,
            'ouvrage_nom': releve_data['ouvrage_nom'],
            'organisation_data': organisation_data,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@require_http_methods(["GET"])
def api_cartes_sociales(request, point_eau_id):
    """
    Retourne les cartes sociales liées à un point d'eau
    """
    try:
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(
            request.user,
            modalites_paiement=RELEVES_MODALITES_AUTORISEES
        )
        point_eau = PointEau.objects.filter(
            id=point_eau_id,
            ouvrage_id__in=allowed_ouvrage_ids
        ).first()
        if not point_eau:
            return JsonResponse({'error': 'Point d\'eau introuvable ou non autorisé'}, status=404)

        releve_id = request.GET.get('releve_id')

        # Si un relevé précis est demandé, l'utiliser pour préremplir les consommations.
        dernier_releve = None
        if releve_id:
            dernier_releve = Releve.objects.filter(
                id=releve_id,
                point_eau_id=point_eau_id
            ).first()

        if not dernier_releve:
            dernier_releve = Releve.objects.filter(
                point_eau_id=point_eau_id
            ).order_by('-datereleve').first()

        # Chercher les cartes sociales liées directement au point d'eau
        cartes_sociales = CarteSociale.objects.filter(
            point_eau_id=point_eau_id,
            statut='active'
        )

        # Préparer les données avec les quantités du dernier relevé
        cartes_data = []
        for cs in cartes_sociales:
            # Par défaut : 0 bidons
            quantite_bidons = 0

            # Si un dernier relevé existe, chercher la consommation associée
            if dernier_releve:
                conso = ConsoCarteSociale.objects.filter(
                    releve=dernier_releve,
                    carte_sociale=cs
                ).first()

                if conso:
                    quantite_bidons = conso.quantite_bidons

            cartes_data.append({
                'id': str(cs.id),
                'beneficiaire': cs.nom_beneficiaire or 'N/A',
                'type_carte': 'Standard',
                'volume_unitaire': ConsoCarteSociale.VOLUME_BIDON_LITRES,  # Constante 20L
                'quantite_bidons': quantite_bidons,
                'volume_total': (quantite_bidons * ConsoCarteSociale.VOLUME_BIDON_LITRES / 1000),
            })

        data = {'cartes_sociales': cartes_data}
        return JsonResponse(data)
    except PointEau.DoesNotExist:
        return JsonResponse({'error': 'Point d\'eau introuvable'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
@transaction.atomic
def api_save_releve(request):
    """
    Enregistre un nouveau relevé avec calcul automatique
    """
    try:
        point_eau_id = request.POST.get('point_eau_id')
        date_releve = request.POST.get('date_releve')
        nouvel_index = request.POST.get('nouvel_index')
        volume_non_facture = request.POST.get('volume_non_facture', 0)
        remarque = request.POST.get('remarque', '').strip()
        remarque_finale = remarque if remarque else None
        historical_mode = str(request.POST.get('historical_mode', '')).lower() in ('1', 'true', 'yes', 'on')
        date_releve_obj = _parse_iso_date(date_releve)

        if not date_releve_obj:
            return JsonResponse({'success': False, 'error': 'Date de releve invalide'}, status=400)

        # Parse des cartes sociales
        cartes_sociales_json = request.POST.get('cartes_sociales', '[]')
        cartes_sociales = json.loads(cartes_sociales_json)

        # Récupérer le point d'eau
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(
            request.user,
            modalites_paiement=RELEVES_MODALITES_AUTORISEES
        )
        point_eau = PointEau.objects.select_related('compteur_abonne_actuel').filter(
            id=point_eau_id,
            ouvrage_id__in=allowed_ouvrage_ids
        ).first()
        if not point_eau:
            return JsonResponse({'success': False, 'error': 'Point d\'eau introuvable ou non autorisé'}, status=404)

        # Idempotence mobile : si le serveur a créé le relevé mais que la
        # réponse s'est perdue, le retry retourne le même objet.
        terrain_local_uuid = str(request.POST.get('local_uuid') or '').strip() or None
        if terrain_local_uuid:
            existing_mobile = Releve.objects.filter(terrain_local_uuid=terrain_local_uuid).first()
            if existing_mobile:
                if existing_mobile.point_eau_id != point_eau.id:
                    return JsonResponse({'success': False, 'error': 'Identifiant offline deja utilise'}, status=409)
                return JsonResponse({
                    'success': True,
                    'duplicate_prevented': True,
                    'releve': {'id': str(existing_mobile.id), 'numero_facture': existing_mobile.numero_facture or ''},
                })

        def optional_float(key):
            raw = request.POST.get(key)
            if raw in (None, ''):
                return None
            return float(raw)

        terrain_latitude = optional_float('terrain_latitude')
        terrain_longitude = optional_float('terrain_longitude')
        terrain_accuracy = optional_float('terrain_gps_accuracy_m')
        terrain_distance = optional_float('terrain_distance_point_m')
        if terrain_latitude is not None and not -90 <= terrain_latitude <= 90:
            return JsonResponse({'success': False, 'error': 'Latitude agent hors limites'}, status=400)
        if terrain_longitude is not None and not -180 <= terrain_longitude <= 180:
            return JsonResponse({'success': False, 'error': 'Longitude agent hors limites'}, status=400)
        tz_madagascar = pytz.timezone('Indian/Antananarivo')
        captured_raw = str(request.POST.get('terrain_captured_at') or '').strip()
        try:
            terrain_captured_at = datetime.fromisoformat(captured_raw.replace('Z', '+00:00')) if captured_raw else timezone.now()
            if timezone.is_naive(terrain_captured_at):
                terrain_captured_at = tz_madagascar.localize(terrain_captured_at)
        except ValueError:
            terrain_captured_at = timezone.now()

        # Compatibilité avec l'enrichissement opportuniste de la version 1.8.
        # On remplit uniquement les informations absentes de la base.
        point_update_fields = []
        point_latitude_raw = request.POST.get('point_latitude')
        point_longitude_raw = request.POST.get('point_longitude')
        if (point_eau.latitude is None or point_eau.longitude is None) and point_latitude_raw not in (None, '') and point_longitude_raw not in (None, ''):
            point_eau.latitude = float(point_latitude_raw)
            point_eau.longitude = float(point_longitude_raw)
            point_update_fields.extend(['latitude', 'longitude'])
        point_photo_data = str(request.POST.get('point_photo_data') or '').strip()
        if not point_eau.photos and point_photo_data:
            photo_type = str(request.POST.get('point_photo_type') or 'image/jpeg').lower()
            try:
                photo_bytes = base64.b64decode(point_photo_data, validate=True)
            except (ValueError, binascii.Error):
                return JsonResponse({'success': False, 'error': 'Photo du point invalide'}, status=400)
            if photo_type not in {'image/jpeg', 'image/png', 'image/webp'} or not photo_bytes or len(photo_bytes) > 5 * 1024 * 1024:
                return JsonResponse({'success': False, 'error': 'Photo du point invalide ou trop volumineuse'}, status=400)
            point_eau.photos = [{
                'filename': str(request.POST.get('point_photo_name') or 'point-eau-terrain.jpg')[:180],
                'size': len(photo_bytes), 'content_type': photo_type,
                'data': point_photo_data, 'uploaded_at': timezone.now().isoformat(),
            }]
            point_update_fields.append('photos')
        if point_update_fields:
            point_eau.updatedat = timezone.now()
            point_eau.updated_by = getattr(request.user, 'employe', None)
            point_eau.save(update_fields=point_update_fields + ['updatedat', 'updated_by'])

        # Profiter du passage de l'agent pour completer la fiche du point
        # d'eau, sans jamais remplacer une information deja renseignee.
        point_update_fields = []
        latitude_raw = request.POST.get('point_latitude')
        longitude_raw = request.POST.get('point_longitude')
        if (point_eau.latitude is None or point_eau.longitude is None) and (
            latitude_raw not in (None, '') or longitude_raw not in (None, '')
        ):
            try:
                latitude = float(latitude_raw)
                longitude = float(longitude_raw)
            except (TypeError, ValueError):
                return JsonResponse({'success': False, 'error': 'Les coordonnees GPS du point d\'eau sont invalides.'}, status=400)
            if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                return JsonResponse({'success': False, 'error': 'Les coordonnees GPS du point d\'eau sont hors limites.'}, status=400)
            point_eau.latitude = latitude
            point_eau.longitude = longitude
            point_update_fields.extend(['latitude', 'longitude'])

        photo_data = str(request.POST.get('point_photo_data') or '').strip()
        if not point_eau.photos and photo_data:
            photo_type = str(request.POST.get('point_photo_type') or 'image/jpeg').lower()
            if photo_type not in {'image/jpeg', 'image/png', 'image/webp'}:
                return JsonResponse({'success': False, 'error': 'Le format de la photo du point d\'eau est invalide.'}, status=400)
            if photo_data.startswith('data:'):
                try:
                    header, photo_data = photo_data.split(',', 1)
                    photo_type = header[5:].split(';', 1)[0].lower()
                except ValueError:
                    return JsonResponse({'success': False, 'error': 'La photo du point d\'eau est invalide.'}, status=400)
            if photo_type not in {'image/jpeg', 'image/png', 'image/webp'}:
                return JsonResponse({'success': False, 'error': 'Le format de la photo du point d\'eau est invalide.'}, status=400)
            try:
                photo_bytes = base64.b64decode(photo_data, validate=True)
            except (ValueError, binascii.Error):
                return JsonResponse({'success': False, 'error': 'La photo du point d\'eau est invalide.'}, status=400)
            if not photo_bytes or len(photo_bytes) > 5 * 1024 * 1024:
                return JsonResponse({'success': False, 'error': 'La photo du point d\'eau doit faire moins de 5 Mo.'}, status=400)
            point_eau.photos = [{
                'filename': str(request.POST.get('point_photo_name') or 'point-eau-terrain.jpg')[:180],
                'size': len(photo_bytes),
                'content_type': photo_type,
                'data': photo_data,
                'uploaded_at': timezone.now().isoformat(),
            }]
            point_update_fields.append('photos')

        if point_update_fields:
            point_eau.updatedat = timezone.now()
            point_eau.updated_by = getattr(request.user, 'employe', None)
            point_update_fields.extend(['updatedat', 'updated_by'])
            point_eau.save(update_fields=list(dict.fromkeys(point_update_fields)))

        # Dernier relevé pour index précédent
        dernier_releve = Releve.objects.filter(
            point_eau_id=point_eau_id
        ).order_by('-datereleve').first()

        if historical_mode and not (getattr(request.user, 'is_superuser', False) or _is_directeur_user(request.user)):
            return JsonResponse({'success': False, 'error': 'Acces reserve aux Directeurs'}, status=403)

        if historical_mode and Releve.objects.filter(
            point_eau_id=point_eau_id,
            datereleve=date_releve_obj
        ).exists():
            return JsonResponse({
                'success': False,
                'error': 'Un releve existe deja a cette date pour ce point d\'eau'
            }, status=400)

        reference_releve = (
            _get_previous_releve_for_date(point_eau_id, date_releve_obj)
            if historical_mode else
            dernier_releve
        )
        calcul_compteur = build_consumption_segments(
            point_eau, reference_releve, date_releve_obj, nouvel_index
        ) if not historical_mode else {'managed': False}
        index_precedent = (
            float(calcul_compteur['ancien_index']) if calcul_compteur.get('managed')
            else (float(reference_releve.nouvelindex) if reference_releve else 0)
        )

        # Calculs
        volume_consomme = (
            float(calcul_compteur['volume_total']) if calcul_compteur.get('managed')
            else float(nouvel_index) - index_precedent
        )
        if volume_consomme == 0 and not remarque:
            return JsonResponse({
                'success': False,
                'error': 'La remarque est obligatoire si la consommation est égale à 0'
            }, status=400)
        if float(volume_non_facture) < 0:
            return JsonResponse({
                'success': False,
                'error': 'Un volume non facture negatif est interdit. Utilisez Changer le compteur.'
            }, status=400)
        volume_carte_sociale = sum(float(cs.get('volume_total', 0)) for cs in cartes_sociales)
        # Permettre les volumes facturés négatifs (ex: changement de compteur)
        volume_facture = volume_consomme - volume_carte_sociale - float(volume_non_facture)

        # WORKFLOW: Ne pas calculer le montant ici, il sera calculé dans la page facturation
        # Si on calcule ici, le montant pourrait être 0 et la facturation ignorerait le relevé
        # Le montant doit rester NULL pour être traité par le workflow de facturation

        # Créer le relevé avec montant NULL
        releve = Releve.objects.create(
            point_eau_id=point_eau_id,
            compteur_abonne=calcul_compteur.get('compteur'),
            origine_calcul=(
                'multi_compteur' if calcul_compteur.get('changements')
                else ('simple' if calcul_compteur.get('managed') else 'legacy')
            ),
            abonne=point_eau.nomabonne or f"Point d'eau {point_eau.code_point_eau or point_eau.id}",
            datereleve=date_releve_obj,
            ancienindex=index_precedent,
            nouvelindex=nouvel_index,
            consommation=volume_consomme,
            montant=None,  # NULL - sera calculé dans le workflow de facturation
            statut='en_attente',
            # Champs personnalisés
            volume_carte_sociale=volume_carte_sociale,
            volume_non_facture=volume_non_facture,
            volume_facture=volume_facture,
            remarque=remarque_finale,
            terrain_local_uuid=terrain_local_uuid,
            terrain_agent=getattr(request.user, 'employe', None),
            terrain_captured_at=terrain_captured_at,
            terrain_latitude=terrain_latitude,
            terrain_longitude=terrain_longitude,
            terrain_gps_accuracy_m=terrain_accuracy,
            terrain_distance_point_m=terrain_distance,
            terrain_gps_anomaly=bool(
                terrain_distance is not None and terrain_distance > 250
            ),
        )
        save_consumption_segments(releve, calcul_compteur)

        # Enregistrer les détails des cartes sociales dans la table conso_cartes_sociales
        for cs_data in cartes_sociales:
            carte_sociale_id = cs_data.get('id')
            quantite_bidons = int(cs_data.get('quantite_bidons', 0))

            if carte_sociale_id and quantite_bidons > 0:
                ConsoCarteSociale.objects.create(
                    releve=releve,
                    carte_sociale_id=carte_sociale_id,
                    quantite_bidons=quantite_bidons
                    # volume_unitaire n'est plus nécessaire, utilise la constante 20L
                )

        if historical_mode:
            _recompute_releve_chain(point_eau_id, releve)

        return JsonResponse({
            'success': True,
            'releve_id': str(releve.id),
            'montant': None  # Sera calculé dans le workflow de facturation
        })

    except PointEau.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Point d\'eau introuvable'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def api_releve_terrain(request):
    """
    Workflow terrain: calcul rapide et génération de ticket
    """
    try:
        data = json.loads(request.body)
        code_point_eau = data.get('code_point_eau')
        nouvel_index = float(data.get('nouvel_index'))

        # Chercher le point d'eau par code
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(
            request.user,
            modalites_paiement=RELEVES_MODALITES_AUTORISEES
        )
        point_eau = PointEau.objects.filter(
            Q(code_point_eau=code_point_eau) | Q(id=code_point_eau),
            ouvrage_id__in=allowed_ouvrage_ids
        ).first()

        if not point_eau:
            return JsonResponse({'success': False, 'error': 'Point d\'eau introuvable'})

        # Dernier relevé
        dernier_releve = Releve.objects.filter(
            point_eau_id=point_eau.id
        ).order_by('-datereleve').first()

        index_precedent = float(dernier_releve.nouvelindex) if dernier_releve else 0

        # Calculs (sans cartes sociales en terrain)
        volume_consomme = nouvel_index - index_precedent
        volume_facture = max(0, volume_consomme)

        # WORKFLOW: Ne pas calculer le montant ici, il sera calculé dans la page facturation
        # Le montant doit rester NULL pour être traité par le workflow de facturation

        # Enregistrer le relevé avec montant NULL
        # CRITICAL: Convertir en timezone Madagascar AVANT .date()
        tz_madagascar = pytz.timezone('Indian/Antananarivo')
        date_madagascar = timezone.now().astimezone(tz_madagascar).date()

        releve = Releve.objects.create(
            point_eau_id=point_eau.id,
            abonne=point_eau.nomabonne or f"Point d'eau {point_eau.code_point_eau or point_eau.id}",
            datereleve=date_madagascar,
            ancienindex=index_precedent,
            nouvelindex=nouvel_index,
            consommation=volume_consomme,
            montant=None,  # NULL - sera calculé dans le workflow de facturation
            statut='en_attente',
            volume_carte_sociale=0,
            volume_non_facture=0,
            volume_facture=volume_facture,
        )

        # Données du ticket (montant et tarif seront calculés plus tard)
        ticket_data = {
            'date': timezone.now().strftime('%d/%m/%Y %H:%M'),
            'point_eau': point_eau.code_point_eau or str(point_eau.id),
            'village': point_eau.parcelle.village.nom_village if point_eau.parcelle else 'N/A',
            'index_precedent': f"{index_precedent:.2f}",
            'nouvel_index': f"{nouvel_index:.2f}",
            'volume_consomme': f"{volume_consomme:.2f}",
            'volume_carte_sociale': "0.00",
            'volume_facture': f"{volume_facture:.2f}",
            'tarif': "À calculer",
            'montant': "À calculer",
        }

        return JsonResponse({
            'success': True,
            'ticket_data': ticket_data
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@require_http_methods(["GET"])
def api_template_releves(request):
    """
    Génère un template Excel vide pour import de relevés
    """
    try:
        wb = Workbook()
        ws = wb.active
        ws.title = "Relevés à importer"

        # En-têtes
        headers = [
            'ID Point d\'Eau*', 'Date Relevé (DD/MM/YYYY)*', 'Nouvel Index*',
            'Volume Non Facturé', 'Montant (Ar)', 'Numéro DiameX', 'Base DiameX', 'Photo Relevé', 'Notes'
        ]

        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_num)
            cell.value = header
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
            cell.alignment = Alignment(horizontal='center')

        # Exemples
        ws.cell(row=2, column=1, value="12345678-1234-1234-1234-123456789012")
        ws.cell(row=2, column=2, value="15/01/2025")
        ws.cell(row=2, column=3, value=150.5)
        ws.cell(row=2, column=4, value=0)
        ws.cell(row=2, column=5, value=45000)
        ws.cell(row=2, column=6, value=2025001)
        ws.cell(row=2, column=7, value="BASE01")
        ws.cell(row=2, column=8, value="releves/2025/01/photo_PE001_20250115.jpg")
        ws.cell(row=2, column=9, value="Exemple de relevé")

        # Instructions
        ws.cell(row=4, column=1, value="INSTRUCTIONS:")
        ws.cell(row=5, column=1, value="1. ID Point d'Eau* : UUID du point d'eau (obligatoire)")
        ws.cell(row=6, column=1, value="2. Date Relevé* : Format DD/MM/YYYY (obligatoire)")
        ws.cell(row=7, column=1, value="3. Nouvel Index* : Index du compteur (obligatoire)")
        ws.cell(row=8, column=1, value="4. Volume Non Facturé : Volume exceptionnel non facturé (optionnel, réservé directeur)")
        ws.cell(row=9, column=1, value="5. Montant : Montant calculé de la facture en Ariary (calculé automatiquement si vide)")
        ws.cell(row=10, column=1, value="6. Numéro DiameX : Numéro entier DiameX (optionnel)")
        ws.cell(row=11, column=1, value="7. Base DiameX : Base comptable DiameX (optionnel)")
        ws.cell(row=12, column=1, value="8. Photo Relevé : Chemin de la photo du compteur (optionnel)")
        ws.cell(row=13, column=1, value="9. Notes : Remarques éventuelles (optionnel)")
        ws.cell(row=15, column=1, value="NOTE: Le montant est stocké en dur dans la base. Si non fourni, il sera calculé automatiquement.")

        # Ajuster largeur colonnes
        ws.column_dimensions['A'].width = 40
        ws.column_dimensions['B'].width = 20
        ws.column_dimensions['C'].width = 15
        ws.column_dimensions['D'].width = 20
        ws.column_dimensions['E'].width = 15
        ws.column_dimensions['F'].width = 18
        ws.column_dimensions['G'].width = 15
        ws.column_dimensions['H'].width = 45
        ws.column_dimensions['I'].width = 30

        # Réponse HTTP
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename=template_releves.xlsx'
        wb.save(response)
        return response

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@require_http_methods(["GET"])
def api_template_cartes_sociales(request):
    """
    Génère un template Excel vide pour import de consommations cartes sociales
    """
    try:
        wb = Workbook()
        ws = wb.active
        ws.title = "Cartes Sociales"

        # En-têtes
        headers = [
            'ID Point d\'Eau*', 'Date*', 'ID Carte Sociale*', 'Bénéficiaire',
            'Quantité Bidons*', 'Volume Unitaire (L)', 'Notes'
        ]

        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_num)
            cell.value = header
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill(start_color="2E7D32", end_color="2E7D32", fill_type="solid")
            cell.alignment = Alignment(horizontal='center')

        # Exemples
        ws.cell(row=2, column=1, value="12345678-1234-1234-1234-123456789012")
        ws.cell(row=2, column=2, value="2025-01-15")
        ws.cell(row=2, column=3, value="87654321-4321-4321-4321-210987654321")
        ws.cell(row=2, column=4, value="RAKOTO Jean")
        ws.cell(row=2, column=5, value=5)
        ws.cell(row=2, column=6, value=20)
        ws.cell(row=2, column=7, value="Distribution normale")

        ws.cell(row=3, column=1, value="12345678-1234-1234-1234-123456789012")
        ws.cell(row=3, column=2, value="2025-01-15")
        ws.cell(row=3, column=3, value="11111111-2222-3333-4444-555555555555")
        ws.cell(row=3, column=4, value="RAZAKA Marie")
        ws.cell(row=3, column=5, value=3)
        ws.cell(row=3, column=6, value=20)
        ws.cell(row=3, column=7, value="")

        # Instructions
        ws.cell(row=5, column=1, value="INSTRUCTIONS:")
        ws.cell(row=6, column=1, value="1. ID Point d'Eau* : UUID du point d'eau (obligatoire)")
        ws.cell(row=7, column=1, value="2. Date* : Date de distribution, format YYYY-MM-DD (obligatoire)")
        ws.cell(row=8, column=1, value="3. ID Carte Sociale* : UUID de la carte sociale (obligatoire)")
        ws.cell(row=9, column=1, value="4. Bénéficiaire : Nom du bénéficiaire (optionnel, pour référence)")
        ws.cell(row=10, column=1, value="5. Quantité Bidons* : Nombre de bidons distribués (obligatoire)")
        ws.cell(row=11, column=1, value="6. Volume Unitaire : Volume d'un bidon en litres, défaut 20L (optionnel)")
        ws.cell(row=12, column=1, value="7. Notes : Remarques éventuelles (optionnel)")
        ws.cell(row=14, column=1, value="NOTE: Le volume total en m³ sera calculé automatiquement (Quantité × Volume unitaire ÷ 1000)")

        # Ajuster largeur colonnes
        ws.column_dimensions['A'].width = 40
        ws.column_dimensions['B'].width = 15
        ws.column_dimensions['C'].width = 40
        ws.column_dimensions['D'].width = 25
        ws.column_dimensions['E'].width = 18
        ws.column_dimensions['F'].width = 20
        ws.column_dimensions['G'].width = 30

        # Réponse HTTP
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename=template_cartes_sociales.xlsx'
        wb.save(response)
        return response

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@require_http_methods(["GET"])
def api_export_releves(request):
    """
    Exporte les relevés au format Excel
    """
    try:
        wb = Workbook(write_only=True)
        # Note: Excel sheet titles cannot contain certain characters (?, *, :, /, \, [, ])
        ws = wb.create_sheet(title="Releves")

        # En-t?tes
        headers = [
            'ID Relev?', 'Date Relev?', "Point d'Eau", 'Village', 'Ouvrage',
            'IDXls', 'Num?ro DiameX', 'BaseDiameX',
            'Index Pr?c?dent', 'Nouvel Index', 'Volume Consomm?',
            'Volume Carte Sociale', 'Volume Non Factur?', 'Volume Factur?',
            'Tarif (Ar/m?)', 'Montant (Ar)', 'Statut'
        ]
        ws.append(headers)

        # Donn?es
        releves = Releve.objects.select_related(
            'point_eau',
            'point_eau__parcelle__village',
            'point_eau__ouvrage'
        ).order_by('-datereleve').iterator(chunk_size=2000)

        def safe_float(value):
            try:
                return float(value) if value is not None else 0
            except (TypeError, ValueError):
                return 0

        def safe_str(value, default=''):
            return value if value is not None else default

        errors = []  # Collecte des erreurs non bloquantes pour diagnostic

        for releve in releves:
            try:
                date_str = releve.datereleve.strftime('%d/%m/%Y') if releve.datereleve else ''
                try:
                    statut_display = releve.get_statut_display() if releve.statut else ''
                except Exception:
                    statut_display = safe_str(releve.statut)

                village = 'N/A'
                ouvrage_nom = 'N/A'
                idxls = ''

                pe = getattr(releve, 'point_eau', None)
                if pe:
                    try:
                        if getattr(pe, 'parcelle', None) and getattr(pe.parcelle, 'village', None):
                            village = pe.parcelle.village.nom_village or 'N/A'
                        if getattr(pe, 'ouvrage', None):
                            ouvrage_nom = pe.ouvrage.nom_ouvrage or 'N/A'
                        idxls = getattr(pe, 'idxls', '') or ''
                    except Exception as pe_err:
                        errors.append(f"{releve.id}: point_eau invalide ({pe_err})")

                ws.append([
                    str(releve.id),
                    date_str,
                    safe_str(releve.abonne),
                    village,
                    ouvrage_nom,
                    idxls,
                    safe_str(releve.numeroDiameX),
                    safe_str(releve.baseDiameX),
                    safe_float(releve.ancienindex),
                    safe_float(releve.nouvelindex),
                    safe_float(releve.consommation),
                    safe_float(getattr(releve, 'volume_carte_sociale', 0)),
                    safe_float(getattr(releve, 'volume_non_facture', 0)),
                    safe_float(getattr(releve, 'volume_facture', releve.consommation)),
                    0,  # TODO tarif
                    safe_float(releve.montant),
                    statut_display
                ])
            except Exception as row_err:
                errors.append(f"{releve.id}: {row_err}")

        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename=releves_{timezone.now().strftime("%Y%m%d")}.xlsx'
        if errors:
            response['X-Export-Warnings'] = "; ".join(errors[:10])  # limite la taille de l'entête
        wb.save(response)
        return response

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def api_import_releves(request):
    """
    Importe des relevés depuis un fichier Excel avec streaming de progression

    Format attendu :
    - Colonne A (0) : ID Point d'Eau (UUID)
    - Colonne B (1) : Date Relevé (DD/MM/YYYY ou YYYY-MM-DD)
    - Colonne C (2) : Nouvel Index
    - Colonne D (3) : Volume Non Facturé (optionnel, défaut 0)
    - Colonne E (4) : Montant (Ar) (optionnel, laissé vide si non fourni - sera rempli par workflow)
    - Colonne F (5) : Numéro DiameX (optionnel)
    - Colonne G (6) : Base DiameX (optionnel)
    - Colonne H (7) : Photo Relevé (optionnel)
    - Colonne I (8) : Notes (optionnel)

    Note : Le montant N'est PAS calculé automatiquement lors de l'import.
           Il sera renseigné ultérieurement via un workflow spécifique de facturation.

    Logique update_or_create :
    - Unicité : couple (point_eau, datereleve)
    - Si existe : mise à jour des autres champs
    - Sinon : création nouvelle ligne
    """
    try:
        fichier = request.FILES.get('fichier')
        if not fichier:
            return JsonResponse({'success': False, 'error': 'Aucun fichier fourni'}, status=400)

        # ✅ OPTIMISATION : read_only=True pour accélérer la lecture
        wb = load_workbook(fichier, read_only=True)
        ws = wb.active

        nb_imported = 0
        nb_created = 0
        nb_updated = 0
        errors = []

        # ✅ LIMITE : Maximum 10,000 lignes par import pour éviter les blocages
        MAX_ROWS = 10000
        processed_rows = 0

        # Helper pour parser les dates
        def parse_date(date_val):
            if not date_val:
                return None
            if isinstance(date_val, datetime):
                return date_val.date()
            date_str = str(date_val).strip()
            try:
                # Format DD/MM/YYYY
                return datetime.strptime(date_str, '%d/%m/%Y').date()
            except:
                try:
                    # Format YYYY-MM-DD
                    return datetime.strptime(date_str, '%Y-%m-%d').date()
                except:
                    return None

        for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
            # ✅ LIMITE : Arrêter après MAX_ROWS pour éviter les blocages
            processed_rows += 1
            if processed_rows > MAX_ROWS:
                errors.append(f"⚠️ Limite de {MAX_ROWS} lignes atteinte. Import arrêté.")
                break

            try:
                # Ignorer les lignes complètement vides
                if not any(row):
                    continue

                # Extraire les données avec gestion robuste des valeurs
                point_eau_id = str(row[0]).strip() if row[0] else None
                date_releve = parse_date(row[1]) if len(row) > 1 else None
                nouvel_index = float(row[2]) if len(row) > 2 and row[2] not in (None, '') else None
                volume_non_facture = float(row[3]) if len(row) > 3 and row[3] not in (None, '') else 0

                # Montant : gérer les valeurs vides et les conversions
                montant_fourni = None
                if len(row) > 4 and row[4] not in (None, '', 'None', 'NULL'):
                    try:
                        montant_fourni = float(row[4])
                    except (ValueError, TypeError):
                        pass

                # Numéro DiameX : gérer les chaînes et les nombres
                numero_diamex = None
                if len(row) > 5 and row[5] not in (None, '', 'None', 'NULL'):
                    try:
                        # Peut être int ou string
                        numero_diamex = str(row[5]).strip()
                    except (ValueError, TypeError):
                        pass

                base_diamex = str(row[6]).strip() if len(row) > 6 and row[6] not in (None, '', 'None') else None
                photo_releve = str(row[7]).strip() if len(row) > 7 and row[7] not in (None, '', 'None') else None
                notes = str(row[8]).strip() if len(row) > 8 and row[8] not in (None, '', 'None') else None

                # Validation des champs obligatoires
                if not point_eau_id:
                    errors.append(f"Ligne {row_num}: ID Point d'Eau manquant")
                    continue
                if not date_releve:
                    errors.append(f"Ligne {row_num}: Date Relevé invalide ou manquante")
                    continue
                if nouvel_index is None:
                    errors.append(f"Ligne {row_num}: Nouvel Index manquant")
                    continue

                # Récupérer le point d'eau
                try:
                    point_eau = PointEau.objects.get(id=point_eau_id)
                except PointEau.DoesNotExist:
                    errors.append(f"Ligne {row_num}: Point d'eau {point_eau_id} non trouvé")
                    continue

                # Dernier relevé AVANT la date actuelle pour calculer l'index précédent
                dernier_releve = Releve.objects.filter(
                    point_eau_id=point_eau.id,
                    datereleve__lt=date_releve
                ).order_by('-datereleve').first()

                index_precedent = float(dernier_releve.nouvelindex) if dernier_releve else 0

                # Calculs
                volume_consomme = nouvel_index - index_precedent

                if volume_consomme < 0:
                    # Autoriser les imports historiques ou corrections d'index en neutralisant la conso négative.
                    volume_consomme = 0

                volume_carte_sociale = 0  # Pas géré dans l'import Excel pour l'instant
                volume_facture = max(0, volume_consomme - volume_carte_sociale - volume_non_facture)

                # Ne PAS calculer automatiquement le montant
                # Il sera rempli plus tard via un workflow spécifique
                montant = montant_fourni  # Peut être None

                # Créer ou mettre à jour le relevé (éviter les doublons)
                releve, created = Releve.objects.update_or_create(
                    point_eau=point_eau,
                    datereleve=date_releve,
                    defaults={
                        'abonne': point_eau.nomabonne or f"Point d'eau {point_eau.code_point_eau or point_eau.id}",
                        'ancienindex': index_precedent,
                        'nouvelindex': nouvel_index,
                        'consommation': volume_consomme,
                        'montant': Decimal(str(montant)) if montant is not None else None,
                        'statut': 'en_attente',
                        'volume_carte_sociale': volume_carte_sociale,
                        'volume_non_facture': volume_non_facture,
                        'volume_facture': volume_facture,
                        'numeroDiameX': numero_diamex if numero_diamex else None,
                        'baseDiameX': base_diamex,
                    }
                )

                nb_imported += 1
                if created:
                    nb_created += 1
                else:
                    nb_updated += 1

            except ValueError as e:
                errors.append(f"Ligne {row_num}: Erreur de format - {str(e)}")
            except Exception as e:
                errors.append(f"Ligne {row_num}: {str(e)}")

        # Message détaillé
        message_parts = []
        if nb_created > 0:
            message_parts.append(f"{nb_created} créé(s)")
        if nb_updated > 0:
            message_parts.append(f"{nb_updated} mis à jour")
        message = f"{nb_imported} relevé(s) importé(s) : " + ", ".join(message_parts)

        if errors:
            message += f" - {len(errors)} erreur(s)"

        return JsonResponse({
            'success': True,
            'message': message,
            'nb_imported': nb_imported,
            'nb_created': nb_created,
            'nb_updated': nb_updated,
            'errors': errors
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
def api_import_releves_streaming(request):
    """
    Importe des relevés avec streaming SSE pour affichage en temps réel
    """
    import json
    from django.http import StreamingHttpResponse

    def event_stream():
        try:
            fichier = request.FILES.get('fichier')
            if not fichier:
                yield f"data: {json.dumps({'error': 'Aucun fichier fourni'})}\n\n"
                return

            # ✅ OPTIMISATION : Charger en read_only pour accélérer
            wb = load_workbook(fichier, read_only=True)
            ws = wb.active

            # ✅ OPTIMISATION : Ne pas compter les lignes à l'avance (trop lent)
            # On enverra la progression au fur et à mesure
            start_message = json.dumps({'type': 'start', 'message': "Démarrage de l'import..."})
            yield f"data: {start_message}\n\n"

            nb_created = 0
            nb_updated = 0
            errors = []
            processed_rows = 0

            # ✅ LIMITE : Maximum de lignes pour éviter les timeouts
            MAX_ROWS = 5000

            # Helper pour parser les dates
            def parse_date(date_val):
                if not date_val:
                    return None
                if isinstance(date_val, datetime):
                    return date_val.date()
                date_str = str(date_val).strip()
                try:
                    return datetime.strptime(date_str, '%d/%m/%Y').date()
                except:
                    try:
                        return datetime.strptime(date_str, '%Y-%m-%d').date()
                    except:
                        return None

            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
                # ✅ Vérifier la limite
                processed_rows += 1
                if processed_rows > MAX_ROWS:
                    yield f"data: {json.dumps({'type': 'warning', 'message': f'Limite de {MAX_ROWS} lignes atteinte. Import arrêté.'})}\n\n"
                    break
                try:
                    # ✅ Vérifier que la ligne n'est pas vide
                    if not row or not any(row):
                        continue

                    # ✅ Sécurité : Vérifier qu'il y a au moins 3 colonnes (minimum requis)
                    if len(row) < 3:
                        error_msg = f"Ligne {row_num}: Pas assez de colonnes (minimum 3 requises)"
                        errors.append(error_msg)
                        yield f"data: {json.dumps({'type': 'error', 'message': error_msg, 'created': nb_created, 'updated': nb_updated})}\n\n"
                        continue

                    # Extraire les données avec gestion robuste
                    try:
                        point_eau_id = str(row[0]).strip() if row[0] else None
                    except:
                        point_eau_id = None

                    try:
                        date_releve = parse_date(row[1]) if len(row) > 1 else None
                    except:
                        date_releve = None

                    try:
                        nouvel_index = float(row[2]) if len(row) > 2 and row[2] not in (None, '') else None
                    except (ValueError, TypeError):
                        nouvel_index = None

                    try:
                        volume_non_facture = float(row[3]) if len(row) > 3 and row[3] not in (None, '') else 0
                    except (ValueError, TypeError):
                        volume_non_facture = 0

                    montant_fourni = None
                    if len(row) > 4 and row[4] not in (None, '', 'None', 'NULL'):
                        try:
                            montant_fourni = float(row[4])
                        except (ValueError, TypeError):
                            pass

                    numero_diamex = None
                    if len(row) > 5 and row[5] not in (None, '', 'None', 'NULL'):
                        try:
                            numero_diamex = str(row[5]).strip()
                        except (ValueError, TypeError):
                            pass

                    try:
                        base_diamex = str(row[6]).strip() if len(row) > 6 and row[6] not in (None, '', 'None') else None
                    except:
                        base_diamex = None

                    # Validation
                    if not point_eau_id:
                        error_msg = f"Ligne {row_num}: ID Point d'Eau manquant"
                        errors.append(error_msg)
                        yield f"data: {json.dumps({'type': 'error', 'message': error_msg, 'created': nb_created, 'updated': nb_updated})}\n\n"
                        continue
                    if not date_releve:
                        error_msg = f"Ligne {row_num}: Date Relevé invalide"
                        errors.append(error_msg)
                        yield f"data: {json.dumps({'type': 'error', 'message': error_msg, 'created': nb_created, 'updated': nb_updated})}\n\n"
                        continue
                    if nouvel_index is None:
                        error_msg = f"Ligne {row_num}: Nouvel Index manquant"
                        errors.append(error_msg)
                        yield f"data: {json.dumps({'type': 'error', 'message': error_msg, 'created': nb_created, 'updated': nb_updated})}\n\n"
                        continue

                    # Récupérer le point d'eau
                    try:
                        point_eau = PointEau.objects.get(id=point_eau_id)
                    except PointEau.DoesNotExist:
                        error_msg = f"Ligne {row_num}: Point d'eau non trouvé"
                        errors.append(error_msg)
                        yield f"data: {json.dumps({'type': 'error', 'message': error_msg, 'created': nb_created, 'updated': nb_updated})}\n\n"
                        continue

                    # Dernier relevé pour index précédent
                    dernier_releve = Releve.objects.filter(
                        point_eau_id=point_eau.id,
                        datereleve__lt=date_releve
                    ).order_by('-datereleve').first()

                    index_precedent = float(dernier_releve.nouvelindex) if dernier_releve else 0

                    # Calculs
                    volume_consomme = nouvel_index - index_precedent
                    if volume_consomme < 0:
                        # Autoriser les imports historiques ou corrections d'index en neutralisant la conso négative.
                        volume_consomme = 0

                    volume_carte_sociale = 0
                    volume_facture = max(0, volume_consomme - volume_carte_sociale - volume_non_facture)
                    montant = montant_fourni

                    # Créer ou mettre à jour (UNICITÉ : point_eau + datereleve)
                    releve, created = Releve.objects.update_or_create(
                        point_eau=point_eau,
                        datereleve=date_releve,
                        defaults={
                            'abonne': point_eau.nomabonne or f"Point d'eau {point_eau.code_point_eau or point_eau.id}",
                            'ancienindex': index_precedent,
                            'nouvelindex': nouvel_index,
                            'consommation': volume_consomme,
                            'montant': Decimal(str(montant)) if montant is not None else None,
                            'statut': 'en_attente',
                            'volume_carte_sociale': volume_carte_sociale,
                            'volume_non_facture': volume_non_facture,
                            'volume_facture': volume_facture,
                            'numeroDiameX': numero_diamex if numero_diamex else None,
                            'baseDiameX': base_diamex,
                        }
                    )

                    if created:
                        nb_created += 1
                    else:
                        nb_updated += 1

                    # Envoyer progression
                    yield f"data: {json.dumps({'type': 'progress', 'row': row_num, 'created': nb_created, 'updated': nb_updated, 'action': 'créé' if created else 'mis à jour'})}\n\n"

                except Exception as e:
                    error_msg = f"Ligne {row_num}: {str(e)}"
                    errors.append(error_msg)
                    yield f"data: {json.dumps({'type': 'error', 'message': error_msg, 'created': nb_created, 'updated': nb_updated})}\n\n"

            # Envoyer résumé final
            yield f"data: {json.dumps({'type': 'complete', 'created': nb_created, 'updated': nb_updated, 'errors': len(errors), 'error_list': errors})}\n\n"

        except Exception as e:
            import traceback
            yield f"data: {json.dumps({'type': 'fatal_error', 'error': str(e), 'traceback': traceback.format_exc()})}\n\n"

    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


@csrf_exempt
@require_http_methods(["POST"])
def api_supprimer_releve(request):
    """
    API pour supprimer un relevé
    Protection: Impossible de supprimer si numeroDiameX est renseigné (enregistré en comptabilité)
    """
    try:
        data = json.loads(request.body)
        releve_id = data.get('releve_id')

        if not releve_id:
            return JsonResponse({
                'success': False,
                'error': 'ID du relevé manquant'
            }, status=400)

        # Vérifier si l'utilisateur est directeur (ou membre du groupe Directeur)
        is_directeur = False
        try:
            if request.user.is_authenticated:
                employe = getattr(request.user, 'employe', None)
                if employe and getattr(employe, 'is_directeur', False):
                    is_directeur = True
                else:
                    is_directeur = request.user.groups.filter(name='Directeur').exists()
        except Exception:
            is_directeur = False

        # Récupérer le relevé
        try:
            # Convertir en UUID si nécessaire
            import uuid as uuid_module
            if isinstance(releve_id, str):
                releve_uuid = uuid_module.UUID(releve_id)
            else:
                releve_uuid = releve_id

            releve = Releve.objects.get(id=releve_uuid)
        except (Releve.DoesNotExist, ValueError, AttributeError) as e:
            return JsonResponse({
                'success': False,
                'error': f'Relevé introuvable (ID: {releve_id}, erreur: {type(e).__name__})'
            }, status=404)

        # PROTECTION 1: Vérifier si le relevé est enregistré en comptabilité
        if not is_directeur and releve.numeroDiameX and releve.numeroDiameX.strip():
            return JsonResponse({
                'success': False,
                'error': 'Impossible de supprimer ce relevé : déjà enregistré en comptabilité (DiameX)',
                'protected': True,
                'reason': 'comptabilite'
            }, status=403)

        # PROTECTION 2: Vérifier si le relevé date de plus d'1 mois
        from datetime import timedelta
        from django.utils import timezone
        date_limite = timezone.now().date() - timedelta(days=30)

        if not is_directeur and releve.datereleve < date_limite:
            return JsonResponse({
                'success': False,
                'error': f'Impossible de supprimer ce relevé : il date de plus d\'un mois (date: {releve.datereleve.strftime("%d/%m/%Y")})',
                'protected': True,
                'reason': 'anciennete'
            }, status=403)

        # Sauvegarder les informations pour le message de confirmation
        info_releve = {
            'point_eau': str(releve.point_eau.code_point_eau if releve.point_eau else 'N/A'),
            'abonne': releve.abonne,
            'date': releve.datereleve.strftime('%d/%m/%Y'),
            'montant': float(releve.montant) if releve.montant else 0
        }

        # Supprimer le relevé
        releve.delete()

        return JsonResponse({
            'success': True,
            'message': f'Relevé supprimé avec succès',
            'info': info_releve
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Format JSON invalide'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur serveur: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_create_beneficiaire(request):
    """
    API pour créer un nouveau bénéficiaire de carte sociale
    """
    try:
        data = json.loads(request.body)

        numero_carte = data.get('numero_carte')
        nom_beneficiaire = data.get('nom_beneficiaire')
        point_eau_id = data.get('point_eau_id')
        nombre_habitants = data.get('nombre_habitants')
        observations = data.get('observations')

        # Validation
        if not numero_carte or not nom_beneficiaire or not point_eau_id:
            return JsonResponse({
                'success': False,
                'error': 'Numéro de carte, nom du bénéficiaire et point d\'eau sont obligatoires'
            }, status=400)

        # Vérifier que le numéro de carte n'existe pas déjà
        if CarteSociale.objects.filter(numero_carte=numero_carte).exists():
            return JsonResponse({
                'success': False,
                'error': f'Le numéro de carte "{numero_carte}" existe déjà'
            }, status=400)

        # Récupérer le point d'eau et l'ouvrage
        try:
            point_eau = PointEau.objects.get(id=point_eau_id)
        except PointEau.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Point d\'eau introuvable'
            }, status=404)

        # Créer la carte sociale
        carte_sociale = CarteSociale.objects.create(
            numero_carte=numero_carte,
            nom_beneficiaire=nom_beneficiaire,
            point_eau=point_eau,
            ouvrage=point_eau.ouvrage,
            nombre_habitants=int(nombre_habitants) if nombre_habitants else None,
            observations=observations,
            statut='active'
        )

        return JsonResponse({
            'success': True,
            'message': f'Bénéficiaire "{nom_beneficiaire}" créé avec succès',
            'carte_sociale': {
                'id': str(carte_sociale.id),
                'numero_carte': carte_sociale.numero_carte,
                'beneficiaire': carte_sociale.nom_beneficiaire,
            }
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Format JSON invalide'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur serveur: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_save_cartes_sociales_brouillon(request):
    """
    API pour sauvegarder les quantités de cartes sociales immédiatement
    Stocke dans le dernier relevé existant pour éviter la perte des données
    """
    try:
        data = json.loads(request.body)
        point_eau_id = data.get('point_eau_id')
        cartes_sociales = data.get('cartes_sociales', [])

        if not point_eau_id:
            return JsonResponse({
                'success': False,
                'error': 'ID du point d\'eau manquant'
            }, status=400)

        # Chercher le dernier relevé pour ce point d'eau
        dernier_releve = Releve.objects.filter(
            point_eau_id=point_eau_id
        ).order_by('-datereleve').first()

        if not dernier_releve:
            return JsonResponse({
                'success': False,
                'error': 'Aucun relevé existant. Veuillez d\'abord créer un relevé.',
                'need_releve': True
            }, status=400)

        # Mettre à jour ou créer les consommations de cartes sociales
        nb_updated = 0
        for cs_data in cartes_sociales:
            carte_sociale_id = cs_data.get('id')
            quantite_bidons = int(cs_data.get('quantite_bidons', 0))

            if carte_sociale_id:
                conso, created = ConsoCarteSociale.objects.update_or_create(
                    releve=dernier_releve,
                    carte_sociale_id=carte_sociale_id,
                    defaults={'quantite_bidons': quantite_bidons}
                )
                nb_updated += 1

        # Recalculer le volume total des cartes sociales
        volume_total_cs = sum(
            conso.volume_total for conso in
            ConsoCarteSociale.objects.filter(releve=dernier_releve)
        )

        # Mettre à jour le relevé
        dernier_releve.volume_carte_sociale = volume_total_cs
        dernier_releve.volume_facture = max(
            0,
            dernier_releve.consommation - volume_total_cs - dernier_releve.volume_non_facture
        )
        dernier_releve.save()

        return JsonResponse({
            'success': True,
            'message': f'{nb_updated} carte(s) sociale(s) mise(s) à jour',
            'volume_total_cs': float(volume_total_cs)
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Format JSON invalide'
        }, status=400)
    except PointEau.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Point d\'eau introuvable'
        }, status=404)
    except ValueError as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur de validation: {str(e)}'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur serveur: {str(e)}'
        }, status=500)


# APIs Workflow Terrain ajoutées ci-dessous

# ============================================
# APIs WORKFLOW TERRAIN
# ============================================

@mobile_auth_required
@require_http_methods(["GET"])
def api_point_eau_by_code(request, code):
    """
    Rechercher un point d'eau par son code
    """
    try:
        from apps.geography.models import Village
        from django.db import models as django_models

        # Chercher par code_point_eau ou par ID
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(
            request.user,
            modalites_paiement=RELEVES_MODALITES_AUTORISEES
        )
        point_eau = PointEau.objects.filter(
            django_models.Q(code_point_eau=code) | django_models.Q(id=code),
            ouvrage_id__in=allowed_ouvrage_ids
        ).select_related('type_point_eau', 'ouvrage', 'parcelle__village').first()

        if not point_eau:
            return JsonResponse({'error': 'Point d\'eau introuvable'}, status=404)

        # Dernier relevé
        dernier_releve = Releve.objects.filter(
            point_eau_id=point_eau.id
        ).order_by('-datereleve').first()

        # Village
        village_nom = None
        if hasattr(point_eau, 'parcelle') and point_eau.parcelle and point_eau.parcelle.village:
            village_nom = point_eau.parcelle.village.nom_village

        # Ouvrage
        ouvrage_nom = None
        if point_eau.ouvrage:
            ouvrage_nom = point_eau.ouvrage.nom_ouvrage

        data = {
            'id': str(point_eau.id),
            'code': point_eau.code_point_eau or f'PE-{point_eau.id}',
            'nom': point_eau.nomabonne or 'N/A',
            'village': village_nom,
            'ouvrage': ouvrage_nom,
            'dernier_releve': {
                'nouvel_index': float(dernier_releve.nouvelindex),
                'date_releve': dernier_releve.datereleve.strftime('%Y-%m-%d'),
            } if dernier_releve else None
        }

        return JsonResponse(data)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@mobile_auth_required
@csrf_exempt
@require_http_methods(["POST"])
def api_calculer_facture_terrain(request):
    """
    Calculer la facture pour le workflow terrain
    Utilise le moteur de calcul de facturation existant
    """
    try:
        from apps.billing.views_facturation import calculer_montant_releve

        data = json.loads(request.body)
        point_eau_id = data.get('point_eau_id')
        date_releve = data.get('date_releve')
        date_releve_obj = _parse_iso_date(date_releve)
        nouvel_index = float(data.get('nouvel_index'))
        volume_facture = float(data.get('volume_facture'))
        # Optionnels (app Android) : sans eux le moteur ignorerait les cartes
        # sociales et le volume non facturé d'un relevé pas encore enregistré.
        volume_carte_sociale = max(0.0, float(data.get('volume_carte_sociale') or 0))
        volume_non_facture = float(data.get('volume_non_facture') or 0)

        if not date_releve_obj:
            return JsonResponse({'success': False, 'error': 'Date de releve invalide'}, status=400)

        # Récupérer le point d'eau
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(
            request.user,
            modalites_paiement=RELEVES_MODALITES_AUTORISEES
        )
        point_eau = PointEau.objects.select_related('compteur_abonne_actuel').filter(
            id=point_eau_id,
            ouvrage_id__in=allowed_ouvrage_ids
        ).first()
        if not point_eau:
            return JsonResponse({'success': False, 'error': 'Point d\'eau introuvable ou non autorisé'}, status=404)

        # Dernier relevé pour index précédent
        dernier_releve = Releve.objects.filter(
            point_eau_id=point_eau_id
        ).order_by('-datereleve').first()

        index_precedent = float(dernier_releve.nouvelindex) if dernier_releve else 0
        volume_consomme = nouvel_index - index_precedent

        # Créer un relevé temporaire pour le calcul
        releve_temp = Releve(
            point_eau=point_eau,
            abonne=point_eau.nomabonne or 'N/A',
            datereleve=date_releve_obj,
            ancienindex=index_precedent,
            nouvelindex=nouvel_index,
            consommation=volume_consomme,
            volume_non_facture=volume_non_facture,
            volume_facture=volume_facture
        )

        # Calculer le montant avec le moteur de facturation
        resultat = calculer_montant_releve(
            releve_temp,
            volume_carte_sociale=volume_carte_sociale if 'volume_carte_sociale' in data else None,
        )

        if not resultat['success']:
            return JsonResponse({
                'success': False,
                'error': resultat['error']
            }, status=400)

        # Récupérer l'historique des factures impayées pour ce point d'eau
        factures_impayees = Releve.objects.filter(
            point_eau=point_eau,
            montant__isnull=False,  # Facture calculée
            facture_imprimee=True,  # Facture déjà imprimée
            numeroDiameX__isnull=True,  # Pas encore payée
            datereleve__lt=releve_temp.datereleve  # Avant le relevé actuel
        ).order_by('datereleve').values(
            'datereleve', 'ancienindex', 'nouvelindex',
            'volume_facture', 'montant'
        )

        # Calculer le total des impayés
        total_impaye = sum(f['montant'] for f in factures_impayees if f['montant'])

        # Ajouter les impayés au résultat
        resultat['factures_impayees'] = list(factures_impayees)
        resultat['total_impaye'] = float(total_impaye)

        # Décision d'impression : même règle que l'enregistrement, pour que
        # l'agent le sache avant d'enregistrer (le serveur reste l'arbitre).
        analyse = _get_consommation_analysis(point_eau_id, volume_consomme)
        motifs = _motifs_blocage_impression(analyse, volume_non_facture, request.user)
        resultat['analyse_consommation'] = analyse
        resultat['impression_autorisee'] = not motifs
        resultat['motifs_blocage_impression'] = motifs

        return JsonResponse(resultat)

    except PointEau.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Point d\'eau introuvable'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Format JSON invalide'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def api_modifier_releve(request):
    """
    Modification manuelle d'un relevé avec recalcul éventuel.
    Accessible uniquement aux Directeurs.
    """
    try:
        if not request.user.is_authenticated:
            return JsonResponse({'success': False, 'error': 'Non autorisé'}, status=403)

        employe = getattr(request.user, 'employe', None)
        is_directeur = bool(getattr(request.user, 'is_superuser', False))
        if employe and hasattr(employe, 'is_directeur'):
            is_directeur = employe.is_directeur
        if not is_directeur:
            is_directeur = request.user.groups.filter(name='Directeur').exists()

        if not is_directeur:
            return JsonResponse({'success': False, 'error': 'Accès réservé aux Directeurs'}, status=403)

        data = json.loads(request.body)
        releve_id = data.get('releve_id')
        nouvel_index = data.get('nouvel_index')
        montant = data.get('montant')
        remarque = data.get('remarque')
        date_releve_str = data.get('date_releve')
        volume_non_facture = data.get('volume_non_facture')
        cartes_sociales = data.get('cartes_sociales', [])

        if not releve_id:
            return JsonResponse({'success': False, 'error': 'ID relevé requis'}, status=400)
        if nouvel_index is None:
            return JsonResponse({'success': False, 'error': 'Nouvel index requis'}, status=400)

        releve = Releve.objects.get(id=releve_id)
        if releve.numeroDiameX or releve.statut == 'paye' or releve.montantpaye:
            return JsonResponse({
                'success': False,
                'error': 'Une facture payee ou enregistree dans DiameX ne peut pas etre modifiee. Creez une regularisation.'
            }, status=409)
        if releve.facture_imprimee:
            return JsonResponse({
                'success': False,
                'error': 'Cette facture a deja ete imprimee. Elle doit etre annulee puis remplacee, pas reecrite.'
            }, status=409)
        if releve.origine_calcul == 'multi_compteur':
            return JsonResponse({
                'success': False,
                'error': 'Ce releve contient plusieurs segments de compteur et ne peut pas etre modifie directement.'
            }, status=409)

        # Mettre à jour la date si fournie (YYYY-MM-DD)
        if date_releve_str:
            try:
                releve.datereleve = datetime.strptime(date_releve_str, '%Y-%m-%d').date()
            except Exception:
                return JsonResponse({'success': False, 'error': 'Format de date invalide (attendu YYYY-MM-DD)'}, status=400)

        nouvel_index = Decimal(str(nouvel_index))
        ancien_index = Decimal(str(releve.ancienindex or 0))
        consommation = nouvel_index - ancien_index

        if volume_non_facture is None or volume_non_facture == '':
            volume_non_facture_decimal = Decimal(str(getattr(releve, 'volume_non_facture', 0) or 0))
        else:
            volume_non_facture_decimal = Decimal(str(volume_non_facture))

        # Un volume non facturé négatif n'est plus autorisé, même s'il reprend
        # une valeur déjà existante sur le relevé (utiliser Changer le compteur).
        if volume_non_facture_decimal < 0:
            return JsonResponse({
                'success': False,
                'error': 'Un volume non facturé négatif est interdit. Utilisez Changer le compteur.'
            }, status=400)

        if consommation == 0 and not (remarque or '').strip():
            return JsonResponse({
                'success': False,
                'error': 'La remarque est obligatoire si la consommation est égale à 0'
            }, status=400)

        if volume_non_facture_decimal != 0 and not (remarque or '').strip():
            return JsonResponse({
                'success': False,
                'error': 'La remarque est obligatoire si le volume non facturé est différent de 0'
            }, status=400)

        releve.nouvelindex = nouvel_index
        releve.consommation = consommation
        if hasattr(releve, 'volume_non_facture'):
            releve.volume_non_facture = volume_non_facture_decimal

        if montant is not None and montant != '':
            releve.montant = Decimal(str(montant))
        else:
            releve.montant = None

        if remarque is not None:
            releve.remarque = remarque.strip() or None

        releve.save()

        volume_carte_sociale_decimal = Decimal('0')

        if isinstance(cartes_sociales, list):
            consos_existantes = {
                str(conso.carte_sociale_id): conso
                for conso in ConsoCarteSociale.objects.filter(releve=releve)
            }
            cartes_ids_recues = set()

            for cs_data in cartes_sociales:
                carte_id = str(cs_data.get('id') or '').strip()
                if not carte_id:
                    continue

                cartes_ids_recues.add(carte_id)
                quantite_bidons = int(float(cs_data.get('quantite_bidons', 0) or 0))
                volume_total_cs = Decimal(str(cs_data.get('volume_total', 0) or 0))

                conso_existante = consos_existantes.get(carte_id)
                if conso_existante:
                    conso_existante.quantite_bidons = quantite_bidons
                    conso_existante.volume_total = volume_total_cs
                    conso_existante.save(update_fields=['quantite_bidons', 'volume_total'])
                else:
                    ConsoCarteSociale.objects.create(
                        releve=releve,
                        carte_sociale_id=carte_id,
                        quantite_bidons=quantite_bidons,
                        volume_total=volume_total_cs
                    )

            ConsoCarteSociale.objects.filter(releve=releve).exclude(
                carte_sociale_id__in=cartes_ids_recues
            ).delete()

            volume_carte_sociale_decimal = Decimal(str(
                ConsoCarteSociale.objects.filter(
                    releve=releve,
                    carte_sociale__point_eau_id=releve.point_eau_id,
                    carte_sociale__statut='active',
                ).aggregate(total=Sum('volume_total'))['total'] or 0
            ))
        else:
            volume_carte_sociale_decimal = Decimal(str(
                ConsoCarteSociale.objects.filter(
                    releve=releve,
                    carte_sociale__point_eau_id=releve.point_eau_id,
                    carte_sociale__statut='active',
                ).aggregate(total=Sum('volume_total'))['total'] or 0
            ))

        volume_facture = consommation - volume_carte_sociale_decimal - volume_non_facture_decimal
        if volume_facture < 0:
            return JsonResponse({
                'success': False,
                'error': 'Le volume facture ne peut pas etre negatif'
            }, status=400)
        if hasattr(releve, 'volume_carte_sociale'):
            releve.volume_carte_sociale = volume_carte_sociale_decimal
        if hasattr(releve, 'volume_facture'):
            releve.volume_facture = volume_facture
        releve.save(update_fields=[
            'nouvelindex',
            'consommation',
            'volume_carte_sociale',
            'volume_non_facture',
            'volume_facture',
            'montant',
            'remarque',
            'datereleve',
        ])

        # Une consommation de carte sociale liee doit toujours porter la date
        # de son releve. ``update`` couvre egalement les anciennes lignes dont
        # la date etait vide ou incorrecte, sans modifier leurs volumes.
        consos_date_synchronisees = ConsoCarteSociale.objects.filter(
            releve=releve
        ).exclude(date=releve.datereleve).update(date=releve.datereleve)

        response_data = {
            'success': True,
            'consos_cartes_sociales_date_synchronisees': consos_date_synchronisees,
            'releve': {
                'id': str(releve.id),
                'nouvel_index': float(releve.nouvelindex),
                'montant': float(releve.montant) if releve.montant is not None else None,
                'volume_consomme': float(releve.consommation),
                'volume_carte_sociale': float(getattr(releve, 'volume_carte_sociale', 0) or 0),
                'volume_non_facture': float(getattr(releve, 'volume_non_facture', 0) or 0),
                'volume_facture': float(getattr(releve, 'volume_facture', releve.consommation)),
            }
        }
        return JsonResponse(response_data)
    except Releve.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Relevé introuvable'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Format JSON invalide'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@mobile_auth_required
@csrf_exempt
@require_http_methods(["POST"])
@transaction.atomic
def api_save_releve_terrain(request):
    """
    Enregistrer un relevé complet depuis le workflow terrain
    Avec photo, cartes sociales, et montant calculé
    """
    try:
        import pytz
        from django.utils import timezone as dj_timezone

        point_eau_id = request.POST.get('point_eau_id')
        date_releve_str = request.POST.get('date_releve')
        nouvel_index = float(request.POST.get('nouvel_index'))
        volume_non_facture = float(request.POST.get('volume_non_facture', 0))
        if volume_non_facture < 0:
            return JsonResponse({
                'success': False,
                'error': 'Un volume non facture negatif est interdit. Utilisez Changer le compteur.'
            }, status=400)
        remarque = request.POST.get('remarque', '').strip()

        # Montant nullable : un relevé saisi hors ligne (app terrain
        # Android, sans réseau pour appeler api_calculer_facture_terrain)
        # ne connaît pas encore son montant — il est rempli plus tard par
        # le workflow de facturation, exactement comme pour l'import Excel
        # (Releve.montant est null=True, blank=True, cf. migration
        # billing.0032_releve_montant_nullable). Une chaîne vide ou absente
        # équivaut à "pas encore calculé", pas à une erreur de saisie.
        montant_raw = request.POST.get('montant')
        montant = float(montant_raw) if montant_raw not in (None, '') else None

        # Parser la date et la localiser à Madagascar (règles TIMEZONE_GUIDE.md)
        tz_madagascar = pytz.timezone('Indian/Antananarivo')
        if isinstance(date_releve_str, datetime):
            date_releve = date_releve_str if dj_timezone.is_aware(date_releve_str) else tz_madagascar.localize(date_releve_str)
        else:
            date_naive = datetime.strptime(str(date_releve_str), '%Y-%m-%d')
            date_releve = tz_madagascar.localize(date_naive)

        # Cartes sociales
        cartes_sociales_json = request.POST.get('cartes_sociales', '[]')
        cartes_sociales = json.loads(cartes_sociales_json)

        # Photo
        photo_file = request.FILES.get('photo_releve')

        # Récupérer le point d'eau
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(
            request.user,
            modalites_paiement=RELEVES_MODALITES_AUTORISEES
        )
        point_eau = PointEau.objects.select_related('compteur_abonne_actuel').filter(
            id=point_eau_id,
            ouvrage_id__in=allowed_ouvrage_ids
        ).first()
        if not point_eau:
            return JsonResponse({'success': False, 'error': 'Point d\'eau introuvable ou non autorisé'}, status=404)

        # Identifiant stable créé par le téléphone. Si la réponse HTTP s'est
        # perdue après la création, un nouvel essai retourne le même relevé au
        # lieu de créer une facture en double.
        terrain_local_uuid = str(request.POST.get('local_uuid') or '').strip() or None
        if terrain_local_uuid:
            existing_mobile = Releve.objects.filter(terrain_local_uuid=terrain_local_uuid).first()
            if existing_mobile:
                if existing_mobile.point_eau_id != point_eau.id:
                    return JsonResponse({
                        'success': False,
                        'error': 'Identifiant offline déjà utilisé pour un autre point d\'eau',
                    }, status=409)
                return JsonResponse({
                    'success': True,
                    'duplicate_prevented': True,
                    'releve': _releve_ticket_data(existing_mobile),
                    'organisation': _organisation_ticket_data(point_eau),
                    'pending_validation': (
                        not existing_mobile.facture_imprimee
                        and '[VALIDATION_DIRECTEUR_REQUISE]' in (existing_mobile.remarque or '')
                    ),
                })

        def optional_terrain_float(key):
            raw = request.POST.get(key)
            return None if raw in (None, '') else float(raw)

        terrain_latitude = optional_terrain_float('terrain_latitude')
        terrain_longitude = optional_terrain_float('terrain_longitude')
        terrain_accuracy = optional_terrain_float('terrain_gps_accuracy_m')
        terrain_distance = optional_terrain_float('terrain_distance_point_m')
        if terrain_latitude is not None and not -90 <= terrain_latitude <= 90:
            return JsonResponse({'success': False, 'error': 'Latitude agent hors limites'}, status=400)
        if terrain_longitude is not None and not -180 <= terrain_longitude <= 180:
            return JsonResponse({'success': False, 'error': 'Longitude agent hors limites'}, status=400)

        captured_raw = str(request.POST.get('terrain_captured_at') or '').strip()
        try:
            terrain_captured_at = (
                datetime.fromisoformat(captured_raw.replace('Z', '+00:00'))
                if captured_raw else dj_timezone.now()
            )
            if dj_timezone.is_naive(terrain_captured_at):
                terrain_captured_at = tz_madagascar.localize(terrain_captured_at)
        except ValueError:
            terrain_captured_at = dj_timezone.now()

        # Le relevé peut aussi compléter le GPS et la photo absents du point
        # d'eau. Une valeur serveur existante n'est jamais remplacée ici.
        point_update_fields = []
        point_latitude_raw = request.POST.get('point_latitude')
        point_longitude_raw = request.POST.get('point_longitude')
        if (
            (point_eau.latitude is None or point_eau.longitude is None)
            and point_latitude_raw not in (None, '')
            and point_longitude_raw not in (None, '')
        ):
            try:
                point_latitude = float(point_latitude_raw)
                point_longitude = float(point_longitude_raw)
            except (TypeError, ValueError):
                return JsonResponse({'success': False, 'error': 'Coordonnées du point d\'eau invalides'}, status=400)
            if not -90 <= point_latitude <= 90 or not -180 <= point_longitude <= 180:
                return JsonResponse({'success': False, 'error': 'Coordonnées du point d\'eau hors limites'}, status=400)
            point_eau.latitude = point_latitude
            point_eau.longitude = point_longitude
            point_update_fields.extend(['latitude', 'longitude'])

        point_photo_data = str(request.POST.get('point_photo_data') or '').strip()
        if not point_eau.photos and point_photo_data:
            point_photo_type = str(request.POST.get('point_photo_type') or 'image/jpeg').lower()
            if point_photo_data.startswith('data:'):
                try:
                    header, point_photo_data = point_photo_data.split(',', 1)
                    point_photo_type = header[5:].split(';', 1)[0].lower()
                except ValueError:
                    return JsonResponse({'success': False, 'error': 'Photo du point invalide'}, status=400)
            try:
                point_photo_bytes = base64.b64decode(point_photo_data, validate=True)
            except (ValueError, binascii.Error):
                return JsonResponse({'success': False, 'error': 'Photo du point invalide'}, status=400)
            if (
                point_photo_type not in {'image/jpeg', 'image/png', 'image/webp'}
                or not point_photo_bytes
                or len(point_photo_bytes) > 5 * 1024 * 1024
            ):
                return JsonResponse({'success': False, 'error': 'Photo du point invalide ou trop volumineuse'}, status=400)
            point_eau.photos = [{
                'filename': str(request.POST.get('point_photo_name') or 'point-eau-terrain.jpg')[:180],
                'size': len(point_photo_bytes),
                'content_type': point_photo_type,
                'data': point_photo_data,
                'uploaded_at': dj_timezone.now().isoformat(),
                'local_uuid': terrain_local_uuid or '',
            }]
            point_update_fields.append('photos')

        if point_update_fields:
            point_eau.updatedat = dj_timezone.now()
            point_eau.updated_by = getattr(request.user, 'employe', None)
            point_update_fields.extend(['updatedat', 'updated_by'])
            point_eau.save(update_fields=list(dict.fromkeys(point_update_fields)))

        # Dernier relevé pour index précédent
        dernier_releve = Releve.objects.filter(
            point_eau_id=point_eau_id
        ).order_by('-datereleve').first()

        # Seconde barriere cote serveur : le mobile peut avoir travaille hors
        # ligne avec un ancien instantane tandis qu'un autre agent a saisi un
        # relevé plus recent. Ne jamais accepter un index inferieur au dernier
        # index desormais connu du serveur.
        if dernier_releve and nouvel_index < float(dernier_releve.nouvelindex):
            return JsonResponse({
                'success': False,
                'error': (
                    f'Index refuse : le dernier releve est '
                    f'{float(dernier_releve.nouvelindex):g}. '
                    'Saisissez une valeur superieure ou egale.'
                ),
            }, status=400)

        calcul_compteur = build_consumption_segments(
            point_eau, dernier_releve, date_releve.date(), nouvel_index
        )
        index_precedent = (
            float(calcul_compteur['ancien_index']) if calcul_compteur.get('managed')
            else (float(dernier_releve.nouvelindex) if dernier_releve else 0)
        )

        # Calculs
        volume_consomme = (
            float(calcul_compteur['volume_total']) if calcul_compteur.get('managed')
            else nouvel_index - index_precedent
        )

        if volume_consomme == 0 and not remarque:
            return JsonResponse({
                'success': False,
                'error': 'La remarque est obligatoire si la consommation est égale à 0'
            }, status=400)

        if volume_non_facture != 0 and not remarque:
            return JsonResponse({
                'success': False,
                'error': 'Le champ remarque est obligatoire si le volume non facturé est différent de 0'
            }, status=400)

        volume_carte_sociale = sum(float(cs.get('volume_total', 0)) for cs in cartes_sociales)
        volume_facture = volume_consomme - volume_carte_sociale - volume_non_facture
        if volume_facture < 0:
            return JsonResponse({
                'success': False,
                'error': 'Le volume facture ne peut pas etre negatif'
            }, status=400)
        # Ticket imprime hors ligne : le montant du telephone n'est qu'une trace.
        # Le serveur recalcule avec son moteur tarifaire et fait foi ; un ecart
        # (tarif perime sur le telephone) est signale dans la remarque.
        ticket_local = str(request.POST.get('ticket_local') or '').strip() in ('1', 'true', 'True')
        ecart_ticket = None
        if montant is not None:
            from apps.billing.views_facturation import calculer_montant_releve
            calcul_serveur = calculer_montant_releve(
                Releve(
                    point_eau=point_eau, datereleve=date_releve, consommation=volume_consomme,
                    volume_non_facture=volume_non_facture,
                ),
                volume_carte_sociale=volume_carte_sociale,
            )
            montant_ticket = montant
            montant = float(calcul_serveur['montant_total']) if calcul_serveur.get('success') else None
            if montant is None or abs(montant - montant_ticket) > 0.5:
                ecart_ticket = (montant_ticket, montant)

        analyse_consommation = _get_consommation_analysis(point_eau_id, volume_consomme)
        motifs_blocage = _motifs_blocage_impression(
            analyse_consommation, volume_non_facture, request.user
        )
        validation_directeur_requise = bool(motifs_blocage)
        # Un relevé sans montant (saisi hors ligne, montant à calculer
        # ultérieurement) ne peut par définition pas être considéré comme
        # "imprimable" — sinon la règle produit "tant qu'une facture n'est
        # pas imprimée, on peut la recalculer" (cf. CLAUDE.md, Facturation
        # Volumétrique) serait violée dès sa création.
        montant_pas_encore_calcule = montant is None

        # Générer le numéro de facture
        from apps.planning.utils import generer_numero_bon
        numero_facture = generer_numero_bon('facture')
        remarque_finale = remarque if remarque else None
        if validation_directeur_requise:
            motif_validation = (
                f"[VALIDATION_DIRECTEUR_REQUISE] "
                f"Conso={volume_consomme:.2f} m3, "
                f"Moyenne={analyse_consommation.get('moyenne_consommation', 0):.2f} m3, "
                f"Ecart={analyse_consommation.get('ecart_pourcentage') or 0:.2f}%, "
                f"NonFacture={volume_non_facture:.2f} m3"
            )
            remarque_finale = f"{motif_validation}\n{remarque_finale}" if remarque_finale else motif_validation
        if ticket_local and terrain_local_uuid:
            repere = f"[TICKET_LOCAL T-{terrain_local_uuid.replace('-', '')[:8].upper()}]"
            if ecart_ticket:
                serveur = 'n/a' if ecart_ticket[1] is None else format(ecart_ticket[1], '.0f')
                repere += f" [ECART_TICKET ticket={ecart_ticket[0]:.0f} Ar, serveur={serveur} Ar]"
            remarque_finale = f"{repere}\n{remarque_finale}" if remarque_finale else repere

        # Créer le relevé avec montant calculé et marqué comme imprimé
        releve = Releve.objects.create(
            point_eau_id=point_eau_id,
            compteur_abonne=calcul_compteur.get('compteur'),
            origine_calcul=(
                'multi_compteur' if calcul_compteur.get('changements')
                else ('simple' if calcul_compteur.get('managed') else 'legacy')
            ),
            abonne=point_eau.nomabonne or f"Point d'eau {point_eau.code_point_eau or point_eau.id}",
            datereleve=date_releve,
            ancienindex=index_precedent,
            nouvelindex=nouvel_index,
            consommation=volume_consomme,
            montant=montant,
            statut='en_attente',
            volume_carte_sociale=volume_carte_sociale,
            volume_non_facture=volume_non_facture,
            volume_facture=volume_facture,
            remarque=remarque_finale,
            photo_releve=photo_file if photo_file else None,
            terrain_local_uuid=terrain_local_uuid,
            terrain_agent=getattr(request.user, 'employe', None),
            terrain_captured_at=terrain_captured_at,
            terrain_latitude=terrain_latitude,
            terrain_longitude=terrain_longitude,
            terrain_gps_accuracy_m=terrain_accuracy,
            terrain_distance_point_m=terrain_distance,
            terrain_gps_anomaly=bool(terrain_distance is not None and terrain_distance > 250),
            numero_facture=numero_facture,
            facture_imprimee=(not validation_directeur_requise) and (not montant_pas_encore_calcule),
            date_impression=(None if (validation_directeur_requise or montant_pas_encore_calcule) else dj_timezone.now())
        )
        save_consumption_segments(releve, calcul_compteur)

        # Enregistrer les cartes sociales avec photos
        for idx, cs_data in enumerate(cartes_sociales):
            carte_sociale_id = cs_data.get('id')
            quantite_bidons = int(cs_data.get('quantite_bidons', 0))

            if quantite_bidons > 0:
                # Récupérer la photo associée à cette carte (si fournie)
                photo_file = request.FILES.get(f'photo_carte_{idx}')

                # Si carte existante
                if carte_sociale_id:
                    conso = ConsoCarteSociale.objects.create(
                        releve=releve,
                        carte_sociale_id=carte_sociale_id,
                        quantite_bidons=quantite_bidons,
                        date=date_releve.date(),
                        montant_paye=cs_data.get('montant_paye')
                    )

                    # Stocker la photo si fournie (base64 ou chemin)
                    if photo_file:
                        import base64
                        photo_data = base64.b64encode(photo_file.read()).decode('utf-8')
                        conso.photo = f"data:{photo_file.content_type};base64,{photo_data}"
                        conso.save()
                else:
                    # Nouvelle carte à créer
                    numero_carte = cs_data.get('numero_carte')
                    beneficiaire = cs_data.get('beneficiaire')

                    if numero_carte and beneficiaire:
                        # Créer la carte sociale
                        nouvelle_carte = CarteSociale.objects.create(
                            point_eau=point_eau,
                            numero_carte=numero_carte,
                            nom_beneficiaire=beneficiaire,
                            statut='active',
                            ouvrage=point_eau.ouvrage
                        )

                        # Créer la conso avec photo
                        conso = ConsoCarteSociale.objects.create(
                            releve=releve,
                            carte_sociale=nouvelle_carte,
                            quantite_bidons=quantite_bidons,
                            date=date_releve.date(),
                            montant_paye=cs_data.get('montant_paye')
                        )

                        # Stocker la photo si fournie
                        if photo_file:
                            import base64
                            photo_data = base64.b64encode(photo_file.read()).decode('utf-8')
                            conso.photo = f"data:{photo_file.content_type};base64,{photo_data}"
                            conso.save()

        # Infos de l'organisation pour le ticket (gestionnaire actif de l'ouvrage)
        org_data = _organisation_ticket_data(point_eau)

        response_data = {
            'success': True,
            'releve': _releve_ticket_data(releve),
            'organisation': org_data,
            'analyse_consommation': analyse_consommation,
            'pending_validation': bool(validation_directeur_requise),
            'montant_a_calculer': montant_pas_encore_calcule
        }

        if validation_directeur_requise:
            response_data['motifs_blocage_impression'] = motifs_blocage
            response_data['message'] = (
                "Releve enregistre. Validation du Directeur requise "
                "avant impression du ticket : " + " ".join(motifs_blocage)
            )

        return JsonResponse(response_data)

    except PointEau.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Point d\'eau introuvable'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Format JSON invalide'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@mobile_auth_required
@require_http_methods(["GET"])
def api_rechercher_ouvrages(request):
    """
    Rechercher des ouvrages par nom (pour workflow terrain)
    """
    try:
        from django.db.models import Count

        q = request.GET.get('q', '').strip()

        if len(q) < 2:
            return JsonResponse({'success': True, 'ouvrages': []})

        # Rechercher les ouvrages avec nombre de points d'eau
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(
            request.user,
            modalites_paiement=RELEVES_MODALITES_AUTORISEES
        )
        ouvrages = Ouvrage.objects.filter(
            nom_ouvrage__icontains=q,
            id__in=allowed_ouvrage_ids
        ).annotate(
            nb_points_eau=Count('pointeau')
        ).filter(nb_points_eau__gt=0).order_by('nom_ouvrage')[:20]

        data = {
            'success': True,
            'ouvrages': [
                {
                    'id': str(ouvrage.id),
                    'nom': ouvrage.nom_ouvrage,
                    'nb_points_eau': ouvrage.nb_points_eau
                }
                for ouvrage in ouvrages
            ]
        }

        return JsonResponse(data)

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@mobile_auth_required
@require_http_methods(["GET"])
def api_points_eau_by_gps(request):
    """
    Rechercher des points d'eau par coordonnées GPS (pour workflow terrain)
    Retourne les points d'eau dans un rayon défini autour de la position de l'utilisateur
    """
    try:
        from math import radians, cos, sin, asin, sqrt

        # Récupérer les coordonnées GPS de l'utilisateur
        lat_str = request.GET.get('latitude')
        lon_str = request.GET.get('longitude')
        rayon_km = float(request.GET.get('rayon', 5))  # Rayon par défaut: 5 km

        if not lat_str or not lon_str:
            return JsonResponse({
                'success': False,
                'error': 'Latitude et longitude requises'
            }, status=400)

        try:
            user_lat = float(lat_str)
            user_lon = float(lon_str)
        except (ValueError, TypeError):
            return JsonResponse({
                'success': False,
                'error': 'Coordonnées GPS invalides'
            }, status=400)

        # Fonction pour calculer la distance Haversine entre deux points GPS
        def haversine(lon1, lat1, lon2, lat2):
            """
            Calcule la distance en km entre deux points GPS
            """
            # Convertir les degrés en radians
            lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

            # Formule Haversine
            dlon = lon2 - lon1
            dlat = lat2 - lat1
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            c = 2 * asin(sqrt(a))

            # Rayon de la Terre en km
            r = 6371

            return c * r

        # Récupérer tous les points d'eau avec coordonnées GPS
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(
            request.user,
            modalites_paiement=RELEVES_MODALITES_AUTORISEES
        )
        points_eau = PointEau.objects.filter(
            latitude__isnull=False,
            longitude__isnull=False,
            ouvrage_id__in=allowed_ouvrage_ids
        ).select_related('parcelle__village', 'type_point_eau', 'ouvrage')

        # Calculer la distance pour chaque point d'eau
        points_eau_proches = []
        for pe in points_eau:
            distance = haversine(user_lon, user_lat, pe.longitude, pe.latitude)

            # Ne garder que les points dans le rayon défini
            if distance <= rayon_km:
                # Récupérer le dernier relevé
                dernier_releve = Releve.objects.filter(
                    point_eau_id=pe.id
                ).order_by('-datereleve').first()

                village_nom = None
                if hasattr(pe, 'parcelle') and pe.parcelle and pe.parcelle.village:
                    village_nom = pe.parcelle.village.nom_village

                # Type de point d'eau
                type_nom = None
                if hasattr(pe, 'type_point_eau') and pe.type_point_eau:
                    type_nom = pe.type_point_eau.nom_type

                # Nom de l'ouvrage
                ouvrage_nom = None
                if hasattr(pe, 'ouvrage') and pe.ouvrage:
                    ouvrage_nom = pe.ouvrage.nom_ouvrage

                points_eau_proches.append({
                    'id': str(pe.id),
                    'nom': pe.nomabonne or 'N/A',
                    'code': pe.code_point_eau or f'PE-{str(pe.id)[:8]}',
                    'type': type_nom,
                    'est_institutionnel': bool(pe.estbranchementinstitutionnel),
                    'village': village_nom,
                    'ouvrage': ouvrage_nom,
                    'dernier_index': float(dernier_releve.nouvelindex) if dernier_releve else None,
                    'derniere_date': dernier_releve.datereleve.strftime('%d/%m/%Y') if dernier_releve else None,
                    'distance': round(distance, 2)  # Distance en km
                })

        # Trier par distance croissante
        points_eau_proches.sort(key=lambda x: x['distance'])

        # Limiter à 20 résultats maximum
        points_eau_proches = points_eau_proches[:20]

        return JsonResponse({
            'success': True,
            'points_eau': points_eau_proches,
            'count': len(points_eau_proches),
            'rayon_km': rayon_km,
            'position': {
                'latitude': user_lat,
                'longitude': user_lon
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@mobile_auth_required
@require_http_methods(["GET"])
def api_points_eau_by_ouvrage(request, ouvrage_id):
    """
    Récupérer tous les points d'eau d'un ouvrage (pour workflow terrain)
    """
    try:
        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(
            request.user,
            modalites_paiement=RELEVES_MODALITES_AUTORISEES
        )
        if not Ouvrage.objects.filter(id=ouvrage_id, id__in=allowed_ouvrage_ids).exists():
            return JsonResponse({'success': False, 'error': 'Ouvrage non autorisé'}, status=403)
        # Récupérer les points d'eau de l'ouvrage
        points_eau = PointEau.objects.filter(
            ouvrage_id=ouvrage_id
        ).select_related('parcelle__village', 'type_point_eau').order_by('code_point_eau', 'nomabonne')

        if not points_eau.exists():
            return JsonResponse({'success': False, 'error': 'Aucun point d\'eau trouvé'}, status=404)

        # Récupérer les derniers index pour chaque point d'eau
        points_eau_data = []
        for pe in points_eau:
            dernier_releve = Releve.objects.filter(
                point_eau_id=pe.id
            ).order_by('-datereleve').first()

            village_nom = None
            if hasattr(pe, 'parcelle') and pe.parcelle and pe.parcelle.village:
                village_nom = pe.parcelle.village.nom_village

            # Type de point d'eau
            type_nom = None
            if hasattr(pe, 'type_point_eau') and pe.type_point_eau:
                type_nom = pe.type_point_eau.nom_type

            points_eau_data.append({
                'id': str(pe.id),
                'code': pe.code_point_eau,
                'abonne': pe.nomabonne,
                'village': village_nom,
                'type': type_nom,
                'est_institutionnel': bool(pe.estbranchementinstitutionnel),
                'dernier_index': float(dernier_releve.nouvelindex) if dernier_releve else None
            })

        return JsonResponse({
            'success': True,
            'points_eau': points_eau_data
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
