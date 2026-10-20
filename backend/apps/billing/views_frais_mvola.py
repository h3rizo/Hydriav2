"""
Vues pour la gestion du bareme des frais de transfert MVola
"""
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from decimal import Decimal, InvalidOperation
import json

from .models import FraisTransfertMvola


def _parse_decimal(value, field_label):
    if value is None or value == '':
        raise ValueError(f"{field_label} est obligatoire")
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        raise ValueError(f"{field_label} doit etre un nombre valide")


@login_required
def frais_mvola_list(request):
    """Page de gestion du bareme des frais de transfert MVola"""
    paliers = FraisTransfertMvola.objects.all().order_by('montant_min')
    return render(request, 'billing/frais_mvola_list.html', {
        'title': 'Frais de transfert MVola',
        'paliers': paliers,
    })


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def frais_mvola_create_api(request):
    """API pour creer un palier de frais MVola"""
    try:
        data = json.loads(request.body)

        montant_min = _parse_decimal(data.get('montant_min'), 'Le montant minimum')
        montant_max = _parse_decimal(data.get('montant_max'), 'Le montant maximum')
        frais = _parse_decimal(data.get('frais'), 'Le frais')

        palier = FraisTransfertMvola(
            montant_min=montant_min,
            montant_max=montant_max,
            frais=frais,
            actif=data.get('actif', True),
        )
        palier.full_clean()
        palier.save()

        return JsonResponse({
            'success': True,
            'message': 'Palier de frais cree avec succes',
            'palier_id': str(palier.id),
        })
    except (ValueError, ValidationError) as e:
        message = '; '.join(e.messages) if hasattr(e, 'messages') else str(e)
        return JsonResponse({'success': False, 'error': message}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def frais_mvola_update_api(request, pk):
    """API pour modifier un palier de frais MVola"""
    try:
        palier = get_object_or_404(FraisTransfertMvola, pk=pk)
        data = json.loads(request.body)

        palier.montant_min = _parse_decimal(data.get('montant_min'), 'Le montant minimum')
        palier.montant_max = _parse_decimal(data.get('montant_max'), 'Le montant maximum')
        palier.frais = _parse_decimal(data.get('frais'), 'Le frais')
        palier.actif = data.get('actif', True)

        palier.full_clean()
        palier.save()

        return JsonResponse({'success': True, 'message': 'Palier de frais modifie avec succes'})
    except (ValueError, ValidationError) as e:
        message = '; '.join(e.messages) if hasattr(e, 'messages') else str(e)
        return JsonResponse({'success': False, 'error': message}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def frais_mvola_delete_api(request, pk):
    """API pour supprimer un palier de frais MVola"""
    try:
        palier = get_object_or_404(FraisTransfertMvola, pk=pk)
        palier.delete()
        return JsonResponse({'success': True, 'message': 'Palier de frais supprime avec succes'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def frais_mvola_calculer_api(request):
    """API publique (auth requise) pour calculer le frais applicable a un montant"""
    montant_raw = request.GET.get('montant')
    try:
        montant = _parse_decimal(montant_raw, 'Le montant')
    except ValueError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

    frais = FraisTransfertMvola.calculer_frais(montant)
    return JsonResponse({
        'success': True,
        'montant': float(montant),
        'frais': float(frais) if frais is not None else None,
    })
