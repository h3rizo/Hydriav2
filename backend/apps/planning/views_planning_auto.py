from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.core.management import call_command
from django.db.models import Q
from io import StringIO
from apps.employees.models import Employe


@require_http_methods(['POST'])
def generer_repos_jours_feries(request):
    """API pour générer les repos et jours fériés pour un employé spécifique"""
    try:
        employe_id = request.POST.get('employe_id')
        date_debut = request.POST.get('date_debut')
        date_fin = request.POST.get('date_fin')

        if not employe_id:
            return JsonResponse({
                'success': False,
                'error': 'L\'ID de l\'employé est requis'
            }, status=400)

        output = StringIO()
        kwargs = {'employe_id': employe_id}

        if date_debut:
            kwargs['start_date'] = date_debut
        if date_fin:
            kwargs['end_date'] = date_fin

        call_command('populate_repos_jours_feries', stdout=output, **kwargs)

        return JsonResponse({
            'success': True,
            'message': output.getvalue()
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@require_http_methods(['POST'])
def generer_contre_visites(request):
    """API pour générer les contre-visites pour un superviseur et ses ouvrages"""
    try:
        employe_id = request.POST.get('employe_id')
        year = request.POST.get('year')
        ouvrage_ids = request.POST.getlist('ouvrage_ids')

        if not employe_id:
            return JsonResponse({
                'success': False,
                'error': 'L\'ID du superviseur est requis'
            }, status=400)

        if not ouvrage_ids:
            return JsonResponse({
                'success': False,
                'error': 'Au moins un ouvrage doit être sélectionné'
            }, status=400)

        output = StringIO()
        kwargs = {
            'employe_id': employe_id,
            'ouvrage_ids': ','.join(ouvrage_ids)
        }

        if year:
            kwargs['year'] = int(year)

        call_command('populate_contre_visites', stdout=output, **kwargs)

        return JsonResponse({
            'success': True,
            'message': output.getvalue()
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@require_http_methods(['POST'])
def generer_recouvrement(request):
    """API pour générer le recouvrement pour un agent et ses ouvrages"""
    try:
        employe_id = request.POST.get('employe_id')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        ouvrage_ids = request.POST.getlist('ouvrage_ids')

        if not employe_id:
            return JsonResponse({
                'success': False,
                'error': 'L\'ID de l\'agent est requis'
            }, status=400)

        if not ouvrage_ids:
            return JsonResponse({
                'success': False,
                'error': 'Au moins un ouvrage doit être sélectionné'
            }, status=400)

        output = StringIO()
        kwargs = {
            'employe_id': employe_id,
            'ouvrage_ids': ','.join(ouvrage_ids)
        }

        if start_date:
            kwargs['start_date'] = start_date
        if end_date:
            kwargs['end_date'] = end_date

        call_command('populate_recouvrement', stdout=output, **kwargs)

        return JsonResponse({
            'success': True,
            'message': output.getvalue()
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(['GET'])
def api_employes_ouvrages_planning_auto(request):
    """API pour lister les employés et leurs ouvrages selon le rôle"""
    role = request.GET.get('role')
    if role not in ('superviseur_technique', 'agent_recouvrement'):
        return JsonResponse({
            'success': False,
            'error': 'Role invalide'
        }, status=400)

    try:
        employe_request = getattr(request.user, 'employe', None)
        if not employe_request or not employe_request.organisation:
            return JsonResponse({
                'success': False,
                'error': 'Employé non associé à une organisation'
            }, status=403)

        qs = Employe.objects.filter(
            date_debauchage__isnull=True,
            base__organisation=employe_request.organisation
        ).select_related('poste', 'base')

        if role == 'superviseur_technique':
            qs = qs.filter(
                Q(poste__nom_poste__icontains='superviseur') &
                Q(poste__nom_poste__icontains='technique')
            )
        else:
            qs = qs.filter(
                poste__nom_poste__icontains='recouvrement'
            )

        employees_data = []
        for emp in qs:
            ouvrages = emp.get_accessible_ouvrages()
            employees_data.append({
                'id': str(emp.id),
                'nom': emp.nom_affichage,
                'base': emp.base.nom_base if emp.base else '',
                'ouvrages': [
                    {
                        'id': str(ouvrage.id),
                        'nom': ouvrage.nom_ouvrage,
                    } for ouvrage in ouvrages
                ]
            })

        return JsonResponse({
            'success': True,
            'employees': employees_data
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
