from django.http import JsonResponse
from apps.infrastructure.models import Adresse, CarteSociale


def api_adresses(request):
    """API pour récupérer les adresses par ouvrage"""
    try:
        ouvrage_id = request.GET.get('ouvrage_id')
        if ouvrage_id:
            adresses = Adresse.objects.filter(ouvrage_id=ouvrage_id).order_by('nomadresse')
        else:
            adresses = Adresse.objects.all().order_by('ouvrage__nom', 'nomadresse')

        data = []
        for adresse in adresses:
            data.append({
                'id': str(adresse.id),
                'nomadresse': adresse.nomadresse,
                'adresse_complete': adresse.adresse_complete,
                'type_adresse': adresse.type_adresse,
                'type_adresse_display': adresse.get_type_adresse_display(),
                'latitude': float(adresse.latitude) if adresse.latitude else None,
                'longitude': float(adresse.longitude) if adresse.longitude else None,
                'is_active': adresse.is_active,
                'ouvrage_id': str(adresse.ouvrage_id),
                'ouvrage_nom': adresse.ouvrage.nom,
            })
        return JsonResponse(data, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def api_cartes_sociales(request):
    """API pour récupérer les cartes sociales par point d'eau/ouvrage"""
    try:
        point_eau_nom = request.GET.get('point_eau_nom')
        ouvrage_id = request.GET.get('ouvrage_id')

        if point_eau_nom:
            # Filtrer par nom du point d'eau
            cartes = CarteSociale.objects.filter(point_eau_nom=point_eau_nom).order_by('numero_carte')
        elif ouvrage_id:
            # Filtrer par ouvrage
            cartes = CarteSociale.objects.filter(ouvrage_id=ouvrage_id).order_by('numero_carte')
        else:
            # Toutes les cartes
            cartes = CarteSociale.objects.all().order_by('ouvrage__nom', 'numero_carte')

        data = []
        for carte in cartes:
            data.append({
                'id': str(carte.id),
                'numero_carte': carte.numero_carte,
                'nom_beneficiaire': carte.nom_beneficiaire,
                'point_eau_nom': carte.point_eau_nom,
                'statut': carte.statut,
                'statut_display': carte.get_statut_display(),
                'date_creation': carte.date_creation.isoformat(),
                'date_expiration': carte.date_expiration.isoformat() if carte.date_expiration else None,
                'observations': carte.observations,
                'ouvrage_id': str(carte.ouvrage_id),
                'ouvrage_nom': carte.ouvrage.nom,
            })
        return JsonResponse(data, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)