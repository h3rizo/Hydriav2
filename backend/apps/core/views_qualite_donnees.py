"""Vues pour le rapport qualité des données"""
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q, Count, Case, When, IntegerField
import json
from decimal import Decimal

from apps.geography.models import Village, Parcelle
from apps.billing.models import PointEau
from apps.infrastructure.models import EquipementConstitutif, CarteSociale
from apps.inspections.models import PointDeControleComposant


@login_required
def rapport_qualite_donnees(request):
    """Page principale du rapport qualité des données"""

    # 1. Villages - Coordonnées GPS manquantes
    villages_sans_gps = Village.objects.filter(
        Q(latitude__isnull=True) | Q(longitude__isnull=True)
    ).select_related(
        'fokontany__commune'
    ).order_by('nom_village')

    villages_total = Village.objects.count()
    villages_avec_gps = Village.objects.filter(
        latitude__isnull=False, longitude__isnull=False
    ).count()

    # 2. Parcelles - Habitants et ménages manquants
    parcelles_incomplets = Parcelle.objects.filter(
        Q(nombre_habitants__isnull=True) | Q(nombre_menages__isnull=True)
    ).select_related(
        'village__fokontany__commune'
    ).order_by('reference_parcelle')

    parcelles_total = Parcelle.objects.count()
    parcelles_complets = Parcelle.objects.filter(
        nombre_habitants__isnull=False,
        nombre_menages__isnull=False
    ).count()

    # 3. Points d'eau - Données manquantes
    points_eau_incomplets = PointEau.objects.filter(
        Q(nomabonne__isnull=True) | Q(nomabonne='') |
        Q(nombre_consommateurs__isnull=True) |
        Q(nombre_menages_consommateurs__isnull=True) |
        Q(latitude__isnull=True) | Q(longitude__isnull=True)
    ).select_related(
        'ouvrage',
        'type_point_eau',
        'parcelle__village__fokontany__commune'
    ).order_by('code_point_eau')

    points_eau_total = PointEau.objects.count()
    points_eau_complets = PointEau.objects.filter(
        nomabonne__isnull=False,
        nombre_consommateurs__isnull=False,
        nombre_menages_consommateurs__isnull=False,
        latitude__isnull=False,
        longitude__isnull=False
    ).exclude(nomabonne='').count()

    # 4. Équipements - GPS et photos manquants
    equipements_incomplets = EquipementConstitutif.objects.filter(
        Q(latitude__isnull=True) | Q(longitude__isnull=True)
    ).select_related(
        'ouvrage',
        'type_equipement'
    ).order_by('nom')

    equipements_total = EquipementConstitutif.objects.count()
    equipements_complets = EquipementConstitutif.objects.filter(
        latitude__isnull=False,
        longitude__isnull=False
    ).count()

    # 5. Points de contrôle composants points d'eau - Photos manquantes
    pc_pe_sans_photos = PointDeControleComposant.objects.filter(
        Q(photo_reference__isnull=True),
        composant_point_eau__isnull=False  # Seulement les points d'eau
    ).select_related(
        'composant_point_eau',
        'point_de_controle'
    ).order_by('composant_point_eau__nom_composant', 'point_de_controle__nom')

    pc_pe_total = PointDeControleComposant.objects.filter(
        composant_point_eau__isnull=False
    ).count()
    pc_pe_avec_photos = PointDeControleComposant.objects.filter(
        composant_point_eau__isnull=False,
        photo_reference__isnull=False
    ).count()

    # 6. Points de contrôle composants équipements - Photos manquantes
    pc_eq_sans_photos = PointDeControleComposant.objects.filter(
        Q(photo_reference__isnull=True),
        composant_equipement__isnull=False  # Seulement les équipements
    ).select_related(
        'composant_equipement',
        'point_de_controle'
    ).order_by('composant_equipement__nom_composant', 'point_de_controle__nom')

    pc_eq_total = PointDeControleComposant.objects.filter(
        composant_equipement__isnull=False
    ).count()
    pc_eq_avec_photos = PointDeControleComposant.objects.filter(
        composant_equipement__isnull=False,
        photo_reference__isnull=False
    ).count()

    # 7. Cartes sociales - Nombre d'habitants manquant
    cartes_sans_habitants = CarteSociale.objects.filter(
        Q(nombre_habitants__isnull=True) | Q(nombre_habitants=0)
    ).select_related(
        'ouvrage',
        'point_eau'
    ).order_by('numero_carte')

    cartes_total = CarteSociale.objects.count()
    cartes_avec_habitants = CarteSociale.objects.filter(
        nombre_habitants__isnull=False,
        nombre_habitants__gt=0
    ).count()

    context = {
        'title': 'Rapport Qualité des Données',

        # Villages
        'villages_sans_gps': villages_sans_gps,
        'villages_total': villages_total,
        'villages_avec_gps': villages_avec_gps,
        'villages_taux': int((villages_avec_gps / villages_total * 100) if villages_total > 0 else 0),

        # Parcelles
        'parcelles_incomplets': parcelles_incomplets,
        'parcelles_total': parcelles_total,
        'parcelles_complets': parcelles_complets,
        'parcelles_taux': int((parcelles_complets / parcelles_total * 100) if parcelles_total > 0 else 0),

        # Points d'eau
        'points_eau_incomplets': points_eau_incomplets,
        'points_eau_total': points_eau_total,
        'points_eau_complets': points_eau_complets,
        'points_eau_taux': int((points_eau_complets / points_eau_total * 100) if points_eau_total > 0 else 0),

        # Équipements
        'equipements_incomplets': equipements_incomplets,
        'equipements_total': equipements_total,
        'equipements_complets': equipements_complets,
        'equipements_taux': int((equipements_complets / equipements_total * 100) if equipements_total > 0 else 0),

        # Points de contrôle PE
        'pc_pe_sans_photos': pc_pe_sans_photos,
        'pc_pe_total': pc_pe_total,
        'pc_pe_avec_photos': pc_pe_avec_photos,
        'pc_pe_taux': int((pc_pe_avec_photos / pc_pe_total * 100) if pc_pe_total > 0 else 0),

        # Points de contrôle Équipements
        'pc_eq_sans_photos': pc_eq_sans_photos,
        'pc_eq_total': pc_eq_total,
        'pc_eq_avec_photos': pc_eq_avec_photos,
        'pc_eq_taux': int((pc_eq_avec_photos / pc_eq_total * 100) if pc_eq_total > 0 else 0),

        # Cartes sociales
        'cartes_sans_habitants': cartes_sans_habitants,
        'cartes_total': cartes_total,
        'cartes_avec_habitants': cartes_avec_habitants,
        'cartes_taux': int((cartes_avec_habitants / cartes_total * 100) if cartes_total > 0 else 0),
    }

    return render(request, 'core/rapport_qualite_donnees.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def api_update_village_gps(request):
    """Mettre à jour les coordonnées GPS d'un village"""
    try:
        data = json.loads(request.body)
        village_id = data.get('village_id')
        latitude = data.get('latitude')
        longitude = data.get('longitude')

        village = Village.objects.get(id=village_id)
        village.latitude = Decimal(str(latitude)) if latitude else None
        village.longitude = Decimal(str(longitude)) if longitude else None
        village.save()

        return JsonResponse({'success': True, 'message': 'Coordonnées GPS mises à jour'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_update_parcelle(request):
    """Mettre à jour le nombre d'habitants et de ménages d'une parcelle"""
    try:
        data = json.loads(request.body)
        parcelle_id = data.get('parcelle_id')
        nombre_habitants = data.get('nombre_habitants')
        nombre_menages = data.get('nombre_menages')

        parcelle = Parcelle.objects.get(id=parcelle_id)
        parcelle.nombre_habitants = int(nombre_habitants) if nombre_habitants else None
        parcelle.nombre_menages = int(nombre_menages) if nombre_menages else None
        parcelle.save()

        return JsonResponse({'success': True, 'message': 'Parcelle mise à jour'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_update_point_eau(request):
    """Mettre à jour les données d'un point d'eau"""
    try:
        data = json.loads(request.body)
        pe_id = data.get('pe_id')

        pe = PointEau.objects.get(id=pe_id)

        if 'nomabonne' in data:
            pe.nomabonne = data['nomabonne']
        if 'nombre_consommateurs' in data:
            pe.nombre_consommateurs = int(data['nombre_consommateurs']) if data['nombre_consommateurs'] else None
        if 'nombre_menages_consommateurs' in data:
            pe.nombre_menages_consommateurs = int(data['nombre_menages_consommateurs']) if data['nombre_menages_consommateurs'] else None
        if 'latitude' in data:
            pe.latitude = Decimal(str(data['latitude'])) if data['latitude'] else None
        if 'longitude' in data:
            pe.longitude = Decimal(str(data['longitude'])) if data['longitude'] else None

        pe.save()

        return JsonResponse({'success': True, 'message': 'Point d\'eau mis à jour'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_update_equipement(request):
    """Mettre à jour les coordonnées GPS d'un équipement"""
    try:
        data = json.loads(request.body)
        eq_id = data.get('eq_id')
        latitude = data.get('latitude')
        longitude = data.get('longitude')

        eq = EquipementConstitutif.objects.get(id=eq_id)
        eq.latitude = Decimal(str(latitude)) if latitude else None
        eq.longitude = Decimal(str(longitude)) if longitude else None
        eq.save()

        return JsonResponse({'success': True, 'message': 'Coordonnées GPS mises à jour'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_update_carte_sociale(request):
    """Mettre à jour le nombre d'habitants d'une carte sociale"""
    try:
        data = json.loads(request.body)
        carte_id = data.get('carte_id')
        nombre_habitants = data.get('nombre_habitants')

        carte = CarteSociale.objects.get(id=carte_id)
        carte.nombre_habitants = int(nombre_habitants) if nombre_habitants else None
        carte.save()

        return JsonResponse({'success': True, 'message': 'Carte sociale mise à jour'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
