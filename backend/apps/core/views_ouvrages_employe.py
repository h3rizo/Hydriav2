from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from apps.organization.models import Ouvrage
from apps.billing.models import ModaliteGestion


@require_http_methods(["GET"])
def api_ouvrages_employe(request):
    """API pour récupérer les ouvrages gérés par un employé spécifique"""
    employe_id = request.GET.get('employe_id')

    if not employe_id:
        return JsonResponse({
            'success': False,
            'error': 'L\'ID de l\'employé est requis'
        }, status=400)

    try:
        # Récupérer les ouvrages via les modalités de gestion actives de l'employé
        modalites = ModaliteGestion.objects.filter(
            employe_id=employe_id,
            date_fin__isnull=True  # Modalités actives uniquement
        ).select_related('ouvrage', 'ouvrage__type_ouvrage')

        ouvrages_data = []
        for modalite in modalites:
            if modalite.ouvrage:
                ouvrages_data.append({
                    'id': str(modalite.ouvrage.id),
                    'nom': modalite.ouvrage.nom,
                    'type': modalite.ouvrage.type_ouvrage.nom_type_ouvrage if modalite.ouvrage.type_ouvrage else 'Non spécifié',
                    'modalite': modalite.get_modalitepaiement_display()
                })

        return JsonResponse({
            'success': True,
            'ouvrages': ouvrages_data,
            'count': len(ouvrages_data)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
