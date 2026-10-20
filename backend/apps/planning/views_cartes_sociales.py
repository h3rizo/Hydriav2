from django.shortcuts import render
from django.db.models import Q, Sum, Count, F
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
import json
import pytz

from apps.infrastructure.models import CarteSociale
from apps.billing.models import PointEau, Releve, ModaliteGestion
from apps.geography.models import Commune, District, Region
from apps.organization.models import Ouvrage


def gestion_cartes_sociales_global(request):
    """Vue globale des paiements cartes sociales par commune"""

    # Timezone Madagascar
    tz_madagascar = pytz.timezone('Indian/Antananarivo')

    # Récupérer les filtres
    annee_courante = datetime.now().year
    annee_filter = request.GET.get('annee', str(annee_courante))
    region_filter = request.GET.get('region', '')
    district_filter = request.GET.get('district', '')
    communes_filter = request.GET.getlist('communes')  # Peut être multiple
    ouvrage_id = request.GET.get('ouvrage', '')

    # Récupérer les modalités actives (au volume ou mixte)
    modalites_ids = ModaliteGestion.objects.filter(
        date_fin__isnull=True,
        modalitepaiement__in=['au_volume', 'mixte']
    ).values_list('ouvrage_id', flat=True).distinct()

    # Filtrer les cartes sociales actives
    cartes = CarteSociale.objects.filter(
        ouvrage_id__in=modalites_ids,
        statut='active'
    ).select_related(
        'ouvrage',
        'point_eau',
        'point_eau__parcelle__village__fokontany__commune__district__region'
    )

    # Appliquer les filtres géographiques
    if region_filter:
        cartes = cartes.filter(
            point_eau__parcelle__village__fokontany__commune__district__region_id=region_filter
        )
    if district_filter:
        cartes = cartes.filter(
            point_eau__parcelle__village__fokontany__commune__district_id=district_filter
        )
    if communes_filter:
        cartes = cartes.filter(
            point_eau__parcelle__village__fokontany__commune_id__in=communes_filter
        )
    if ouvrage_id:
        cartes = cartes.filter(ouvrage_id=ouvrage_id)

    # Listes pour les dropdowns
    regions = Region.objects.all().order_by('nom_region')
    districts = District.objects.all().order_by('nom_district')
    communes = Commune.objects.all().order_by('nom_commune')
    ouvrages = Ouvrage.objects.filter(id__in=modalites_ids).order_by('nom_ouvrage')

    # Statistiques globales
    total_cartes = cartes.count()
    total_habitants = cartes.aggregate(total=Sum('nombre_habitants'))['total'] or 0

    context = {
        'cartes': cartes,
        'total_cartes': total_cartes,
        'total_habitants': total_habitants,
        'annee_filter': annee_filter,
        'region_filter': region_filter,
        'district_filter': district_filter,
        'communes_filter': communes_filter,
        'ouvrage_filter': ouvrage_id,
        'regions': regions,
        'districts': districts,
        'communes': communes,
        'ouvrages': ouvrages,
        'annee_courante': annee_courante,
    }

    return render(request, 'planning/cartes_sociales_global.html', context)


def gestion_cartes_sociales(request):
    """Vue détaillée des paiements cartes sociales par point d'eau et par mois"""

    # Timezone Madagascar
    tz_madagascar = pytz.timezone('Indian/Antananarivo')

    # Récupérer les filtres
    annee_courante = datetime.now().year
    annee_filter = request.GET.get('annee', str(annee_courante))
    commune_id = request.GET.get('commune', '')
    ouvrage_id = request.GET.get('ouvrage', '')
    carte_id = request.GET.get('carte', '')
    statut_filter = request.GET.get('statut', '')  # active, suspendue, expiree

    # Récupérer les modalités actives (au volume ou mixte)
    modalites_ids = ModaliteGestion.objects.filter(
        date_fin__isnull=True,
        modalitepaiement__in=['au_volume', 'mixte']
    ).values_list('ouvrage_id', flat=True).distinct()

    # Filtrer les cartes sociales
    cartes = CarteSociale.objects.filter(
        ouvrage_id__in=modalites_ids
    ).select_related(
        'ouvrage',
        'point_eau',
        'point_eau__parcelle__village__fokontany__commune'
    ).order_by('numero_carte')

    # Appliquer les filtres
    if commune_id:
        cartes = cartes.filter(point_eau__parcelle__village__fokontany__commune_id=commune_id)
    if ouvrage_id:
        cartes = cartes.filter(ouvrage_id=ouvrage_id)
    if carte_id:
        cartes = cartes.filter(id=carte_id)
    if statut_filter:
        cartes = cartes.filter(statut=statut_filter)

    # Listes pour les dropdowns
    communes = Commune.objects.filter(
        id__in=PointEau.objects.filter(
            ouvrage_id__in=modalites_ids
        ).values_list('parcelle__village__fokontany__commune_id', flat=True).distinct()
    ).order_by('nom_commune')

    ouvrages = Ouvrage.objects.filter(id__in=modalites_ids).order_by('nom_ouvrage')

    # Statistiques
    total_cartes = cartes.count()
    cartes_actives = cartes.filter(statut='active').count()
    total_habitants = cartes.aggregate(total=Sum('nombre_habitants'))['total'] or 0

    context = {
        'cartes': cartes,
        'total_cartes': total_cartes,
        'cartes_actives': cartes_actives,
        'total_habitants': total_habitants,
        'annee_filter': annee_filter,
        'commune_filter': commune_id,
        'ouvrage_filter': ouvrage_id,
        'carte_filter': carte_id,
        'statut_filter': statut_filter,
        'communes': communes,
        'ouvrages': ouvrages,
        'annee_courante': annee_courante,
    }

    return render(request, 'planning/cartes_sociales.html', context)


def impression_cartes_sociales(request):
    """Page d'impression pour les cartes sociales"""

    # Timezone Madagascar
    tz_madagascar = pytz.timezone('Indian/Antananarivo')

    # Récupérer les filtres
    annee_filter = request.GET.get('annee', str(datetime.now().year))
    communes_filter = request.GET.getlist('communes')
    ouvrage_id = request.GET.get('ouvrage', '')

    # Récupérer les modalités actives
    modalites_ids = ModaliteGestion.objects.filter(
        date_fin__isnull=True,
        modalitepaiement__in=['au_volume', 'mixte']
    ).values_list('ouvrage_id', flat=True).distinct()

    # Filtrer les cartes sociales actives
    cartes = CarteSociale.objects.filter(
        ouvrage_id__in=modalites_ids,
        statut='active'
    ).select_related(
        'ouvrage',
        'point_eau',
        'point_eau__parcelle__village__fokontany__commune'
    ).order_by(
        'point_eau__parcelle__village__fokontany__commune__nom_commune',
        'ouvrage__nom_ouvrage',
        'numero_carte'
    )

    # Appliquer les filtres
    if communes_filter:
        cartes = cartes.filter(
            point_eau__parcelle__village__fokontany__commune_id__in=communes_filter
        )
    if ouvrage_id:
        cartes = cartes.filter(ouvrage_id=ouvrage_id)

    # Grouper par commune et ouvrage
    cartes_par_commune = {}
    for carte in cartes:
        if carte.point_eau and carte.point_eau.parcelle:
            commune = carte.point_eau.parcelle.village.fokontany.commune
            commune_nom = commune.nom_commune

            if commune_nom not in cartes_par_commune:
                cartes_par_commune[commune_nom] = {
                    'commune': commune,
                    'ouvrages': {}
                }

            ouvrage_nom = carte.ouvrage.nom_ouvrage
            if ouvrage_nom not in cartes_par_commune[commune_nom]['ouvrages']:
                cartes_par_commune[commune_nom]['ouvrages'][ouvrage_nom] = {
                    'ouvrage': carte.ouvrage,
                    'cartes': []
                }

            cartes_par_commune[commune_nom]['ouvrages'][ouvrage_nom]['cartes'].append(carte)

    # Statistiques globales
    total_cartes = cartes.count()
    total_habitants = cartes.aggregate(total=Sum('nombre_habitants'))['total'] or 0

    context = {
        'cartes_par_commune': cartes_par_commune,
        'total_cartes': total_cartes,
        'total_habitants': total_habitants,
        'annee_filter': annee_filter,
        'date_impression': datetime.now().strftime('%d/%m/%Y %H:%M'),
    }

    return render(request, 'planning/cartes_sociales_impression.html', context)


@csrf_exempt
@require_http_methods(["GET"])
def api_cartes_sociales_data(request):
    """API pour récupérer les données des cartes sociales avec paiements par mois"""

    try:
        # Timezone Madagascar
        tz_madagascar = pytz.timezone('Indian/Antananarivo')

        # Récupérer les filtres
        annee_filter = request.GET.get('annee', str(datetime.now().year))
        commune_id = request.GET.get('commune', '')
        ouvrage_id = request.GET.get('ouvrage', '')
        carte_id = request.GET.get('carte', '')

        # Récupérer les modalités actives
        modalites_ids = ModaliteGestion.objects.filter(
            date_fin__isnull=True,
            modalitepaiement__in=['au_volume', 'mixte']
        ).values_list('ouvrage_id', flat=True).distinct()

        # Filtrer les cartes sociales
        cartes = CarteSociale.objects.filter(
            ouvrage_id__in=modalites_ids,
            statut='active'
        ).select_related(
            'ouvrage',
            'point_eau',
            'point_eau__parcelle__village__fokontany__commune'
        )

        # Appliquer les filtres
        if commune_id:
            cartes = cartes.filter(point_eau__parcelle__village__fokontany__commune_id=commune_id)
        if ouvrage_id:
            cartes = cartes.filter(ouvrage_id=ouvrage_id)
        if carte_id:
            cartes = cartes.filter(id=carte_id)

        # Construire les données pour chaque carte
        data = []
        for carte in cartes:
            # Récupérer les relevés du point d'eau pour l'année
            releves = Releve.objects.filter(
                point_eau=carte.point_eau,
                datereleve__year=annee_filter
            ).exclude(
                Q(montant__isnull=True) | Q(montant=0)
            ).order_by('datereleve')

            # Construire les paiements par mois
            paiements_mois = {}
            for i in range(1, 13):
                paiements_mois[i] = {
                    'mois': i,
                    'montant': 0,
                    'volume_carte_sociale': 0,
                    'paye': False,
                    'numero_diamex': ''
                }

            # Remplir les paiements réels
            for releve in releves:
                date_aware = releve.datereleve
                if date_aware.tzinfo:
                    date_madagascar = date_aware.astimezone(tz_madagascar)
                else:
                    date_madagascar = tz_madagascar.localize(date_aware)

                mois = date_madagascar.month

                # Volume carte sociale (si disponible)
                volume_cs = getattr(releve, 'volume_carte_sociale', 0) or 0

                if volume_cs > 0:
                    paiements_mois[mois]['volume_carte_sociale'] += float(volume_cs)
                    # Le montant pour carte sociale peut être calculé selon tarif
                    # Pour l'instant, on affiche le volume

                # Vérifier si payé (numeroDiameX renseigné)
                if releve.numeroDiameX and releve.numeroDiameX.strip():
                    paiements_mois[mois]['paye'] = True
                    paiements_mois[mois]['numero_diamex'] = releve.numeroDiameX

            carte_data = {
                'id': str(carte.id),
                'numero_carte': carte.numero_carte or '-',
                'nom_beneficiaire': carte.nom_beneficiaire,
                'nombre_habitants': carte.nombre_habitants or 0,
                'ouvrage': carte.ouvrage.nom_ouvrage,
                'point_eau': carte.point_eau.nom if carte.point_eau else '-',
                'commune': carte.point_eau.parcelle.village.fokontany.commune.nom_commune if carte.point_eau and carte.point_eau.parcelle else '-',
                'paiements': list(paiements_mois.values()),
            }

            data.append(carte_data)

        return JsonResponse({
            'success': True,
            'data': data,
            'total': len(data)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
