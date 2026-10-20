"""
Vues pour le recoupement des frais médicaux et scolarité vs comptabilité DiameX
"""
import json
from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q

from apps.employees.models import FraisMedicaux, FraisScolarite, Employe, Base
from apps.organization.models import Organisation
from .models import BaseDiameX


def _get_user_organisation_id(user):
    if getattr(user, 'is_superuser', False):
        return None
    try:
        return user.employe.base.organisation_id
    except Exception:
        return None


def _get_allowed_progs(user):
    if getattr(user, 'is_superuser', False):
        return None
    organisation_id = _get_user_organisation_id(user)
    if not organisation_id:
        return []
    return list(
        Base.objects.filter(organisation_id=organisation_id)
        .exclude(prog_diamex__isnull=True)
        .exclude(prog_diamex='')
        .values_list('prog_diamex', flat=True)
        .distinct()
    )


def _scope_frais_medicaux(queryset, user):
    if getattr(user, 'is_superuser', False):
        return queryset
    organisation_id = _get_user_organisation_id(user)
    if not organisation_id:
        return queryset.none()
    return queryset.filter(membre_famille__employe__base__organisation_id=organisation_id)


def _scope_frais_scolarite(queryset, user):
    if getattr(user, 'is_superuser', False):
        return queryset
    organisation_id = _get_user_organisation_id(user)
    if not organisation_id:
        return queryset.none()
    return queryset.filter(membre_famille__employe__base__organisation_id=organisation_id)


def _scope_employes(queryset, user):
    if getattr(user, 'is_superuser', False):
        return queryset
    organisation_id = _get_user_organisation_id(user)
    if not organisation_id:
        return queryset.none()
    return queryset.filter(base__organisation_id=organisation_id)


@login_required
def recoupement_frais_medicaux(request):
    """
    Page de recoupement des frais médicaux vs comptabilité DiameX.
    """
    organisation_id = _get_user_organisation_id(request.user)
    organisations = Organisation.objects.all().order_by('nom_organisation')
    if organisation_id and not getattr(request.user, 'is_superuser', False):
        organisations = organisations.filter(id=organisation_id)
    employes = _scope_employes(
        Employe.objects.filter(date_debauchage__isnull=True).order_by('nom', 'prenom'),
        request.user
    )

    # Statistiques
    total = _scope_frais_medicaux(FraisMedicaux.objects.filter(statut='imprime'), request.user).count()
    avec_diamex = _scope_frais_medicaux(FraisMedicaux.objects.filter(
        statut='imprime',
        numero_diamex__isnull=False
    ), request.user).exclude(numero_diamex='').count()
    sans_diamex = total - avec_diamex

    context = {
        'organisations': organisations,
        'employes': employes,
        'stats': {
            'total': total,
            'avec_diamex': avec_diamex,
            'sans_diamex': sans_diamex,
            'taux': int((avec_diamex / total * 100) if total > 0 else 0)
        }
    }
    return render(request, 'accounting/recoupement_frais_medicaux.html', context)


@login_required
def recoupement_frais_scolarite(request):
    """
    Page de recoupement des frais de scolarité vs comptabilité DiameX.
    """
    organisation_id = _get_user_organisation_id(request.user)
    organisations = Organisation.objects.all().order_by('nom_organisation')
    if organisation_id and not getattr(request.user, 'is_superuser', False):
        organisations = organisations.filter(id=organisation_id)
    employes = _scope_employes(
        Employe.objects.filter(date_debauchage__isnull=True).order_by('nom', 'prenom'),
        request.user
    )

    # Statistiques
    total = _scope_frais_scolarite(FraisScolarite.objects.filter(statut='imprime'), request.user).count()
    avec_diamex = _scope_frais_scolarite(FraisScolarite.objects.filter(
        statut='imprime',
        numero_diamex__isnull=False
    ), request.user).exclude(numero_diamex='').count()
    sans_diamex = total - avec_diamex

    context = {
        'organisations': organisations,
        'employes': employes,
        'stats': {
            'total': total,
            'avec_diamex': avec_diamex,
            'sans_diamex': sans_diamex,
            'taux': int((avec_diamex / total * 100) if total > 0 else 0)
        }
    }
    return render(request, 'accounting/recoupement_frais_scolarite.html', context)


@csrf_exempt
@require_http_methods(["GET"])
@login_required
def api_frais_medicaux_a_recouper(request):
    """
    API pour lister les frais médicaux imprimés à recouper.
    """
    try:
        employe_id = request.GET.get('employe_id')
        mois = request.GET.get('mois')
        statut_diamex = request.GET.get('statut_diamex')  # 'avec' ou 'sans'

        queryset = _scope_frais_medicaux(FraisMedicaux.objects.filter(
            statut='imprime'
        ), request.user).select_related(
            'membre_famille__employe__poste',
            'membre_famille__employe__base'
        ).order_by('-date')

        if employe_id:
            queryset = queryset.filter(membre_famille__employe_id=employe_id)
        if mois:
            year, month = mois.split('-')
            queryset = queryset.filter(
                mois_concerne__year=int(year),
                mois_concerne__month=int(month)
            )
        if statut_diamex == 'avec':
            queryset = queryset.filter(numero_diamex__isnull=False).exclude(numero_diamex='')
        elif statut_diamex == 'sans':
            queryset = queryset.filter(Q(numero_diamex__isnull=True) | Q(numero_diamex=''))

        frais_list = []
        for frais in queryset[:100]:
            employe = frais.membre_famille.employe
            frais_list.append({
                'id': str(frais.id),
                'employe_id': str(employe.id),
                'employe_nom': employe.nom_complet,
                'membre': frais.membre_famille.nom,
                'affection': frais.affection,
                'type_soin': frais.type_soin,
                'mois_concerne': frais.mois_concerne.strftime('%Y-%m'),
                'montant_rembourse': float(frais.montant_rembourse),
                'numero_diamex': frais.numero_diamex or '',
                'base_diamex': frais.base_diamex or '',
                'date': frais.date.strftime('%Y-%m-%d'),
                'search_pattern': f"Frais médicaux_{frais.membre_famille.nom}_{frais.affection}"
            })

        return JsonResponse({
            'success': True,
            'frais': frais_list
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
@login_required
def api_frais_scolarite_a_recouper(request):
    """
    API pour lister les frais de scolarité imprimés à recouper.
    """
    try:
        employe_id = request.GET.get('employe_id')
        annee_scolaire = request.GET.get('annee_scolaire')
        statut_diamex = request.GET.get('statut_diamex')  # 'avec' ou 'sans'

        queryset = _scope_frais_scolarite(FraisScolarite.objects.filter(
            statut='imprime'
        ), request.user).select_related(
            'membre_famille__employe__poste',
            'membre_famille__employe__base'
        ).order_by('-date')

        if employe_id:
            queryset = queryset.filter(membre_famille__employe_id=employe_id)
        if annee_scolaire:
            queryset = queryset.filter(annee_scolaire=annee_scolaire)
        if statut_diamex == 'avec':
            queryset = queryset.filter(numero_diamex__isnull=False).exclude(numero_diamex='')
        elif statut_diamex == 'sans':
            queryset = queryset.filter(Q(numero_diamex__isnull=True) | Q(numero_diamex=''))

        frais_list = []
        for frais in queryset[:100]:
            employe = frais.membre_famille.employe
            frais_list.append({
                'id': str(frais.id),
                'employe_id': str(employe.id),
                'employe_nom': employe.nom_complet,
                'membre': frais.membre_famille.nom,
                'annee_scolaire': frais.annee_scolaire,
                'ecole': frais.ecole,
                'classe': frais.classe,
                'montant_rembourse': float(frais.montant_rembourse),
                'numero_diamex': frais.numero_diamex or '',
                'base_diamex': frais.base_diamex or '',
                'date': frais.date.strftime('%Y-%m-%d'),
                'search_pattern': f"Frais scolarité_{frais.membre_famille.nom}_{frais.annee_scolaire}"
            })

        return JsonResponse({
            'success': True,
            'frais': frais_list
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_rechercher_diamex_frais_medical(request):
    """
    API pour rechercher une correspondance DiameX pour un frais médical.
    """
    try:
        data = json.loads(request.body)
        frais_id = data.get('frais_id')

        frais = _scope_frais_medicaux(FraisMedicaux.objects.select_related(
            'membre_famille__employe'
        ), request.user).get(id=frais_id)

        employe = frais.membre_famille.employe
        montant = float(frais.montant_rembourse)

        # Rechercher dans BaseDiameX
        resultats = BaseDiameX.objects.filter(
            Q(description__icontains='Frais médicaux') &
            Q(description__icontains=frais.membre_famille.nom),
            montant_out__gte=montant - 100,
            montant_out__lte=montant + 100
        )[:10]
        allowed_progs = _get_allowed_progs(request.user)
        if allowed_progs is not None:
            resultats = resultats.filter(prog__in=allowed_progs)

        matches = []
        for r in resultats:
            matches.append({
                'id': r.id,
                'prog': r.prog,
                'description': r.description,
                'montant_out': float(r.montant_out) if r.montant_out else 0,
                'date_m': r.date_m.strftime('%Y-%m-%d') if r.date_m else '',
                'base_name': r.base_name or ''
            })

        return JsonResponse({
            'success': True,
            'matches': matches,
            'frais_info': {
                'employe': employe.nom_complet,
                'membre': frais.membre_famille.nom,
                'montant': montant
            }
        })
    except FraisMedicaux.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Frais médical non trouvé'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_rechercher_diamex_frais_scolarite(request):
    """
    API pour rechercher une correspondance DiameX pour un frais de scolarité.
    """
    try:
        data = json.loads(request.body)
        frais_id = data.get('frais_id')

        frais = _scope_frais_scolarite(FraisScolarite.objects.select_related(
            'membre_famille__employe'
        ), request.user).get(id=frais_id)

        employe = frais.membre_famille.employe
        montant = float(frais.montant_rembourse)

        # Rechercher dans BaseDiameX
        resultats = BaseDiameX.objects.filter(
            Q(description__icontains='Frais scolarité') &
            Q(description__icontains=frais.membre_famille.nom),
            montant_out__gte=montant - 100,
            montant_out__lte=montant + 100
        )[:10]
        allowed_progs = _get_allowed_progs(request.user)
        if allowed_progs is not None:
            resultats = resultats.filter(prog__in=allowed_progs)

        matches = []
        for r in resultats:
            matches.append({
                'id': r.id,
                'prog': r.prog,
                'description': r.description,
                'montant_out': float(r.montant_out) if r.montant_out else 0,
                'date_m': r.date_m.strftime('%Y-%m-%d') if r.date_m else '',
                'base_name': r.base_name or ''
            })

        return JsonResponse({
            'success': True,
            'matches': matches,
            'frais_info': {
                'employe': employe.nom_complet,
                'membre': frais.membre_famille.nom,
                'montant': montant
            }
        })
    except FraisScolarite.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Frais de scolarité non trouvé'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_appliquer_diamex_frais_medical(request):
    """
    API pour appliquer l'ID DiameX à un frais médical.
    """
    try:
        data = json.loads(request.body)
        frais_id = data.get('frais_id')
        diamex_id = data.get('diamex_id')
        diamex_prog = data.get('diamex_prog')
        base_name = data.get('base_name')

        frais = _scope_frais_medicaux(FraisMedicaux.objects, request.user).get(id=frais_id)
        allowed_progs = _get_allowed_progs(request.user)
        if allowed_progs is not None and diamex_prog and diamex_prog not in allowed_progs:
            return JsonResponse({
                'success': False,
                'error': 'Base DiameX hors périmètre'
            }, status=403)
        frais.numero_diamex = str(diamex_prog)
        frais.base_diamex = base_name
        frais.statut = 'exporte'
        frais.save()

        return JsonResponse({
            'success': True,
            'message': f'ID DiameX {diamex_prog} appliqué'
        })
    except FraisMedicaux.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Frais médical non trouvé'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_appliquer_diamex_frais_scolarite(request):
    """
    API pour appliquer l'ID DiameX à un frais de scolarité.
    """
    try:
        data = json.loads(request.body)
        frais_id = data.get('frais_id')
        diamex_id = data.get('diamex_id')
        diamex_prog = data.get('diamex_prog')
        base_name = data.get('base_name')

        frais = _scope_frais_scolarite(FraisScolarite.objects, request.user).get(id=frais_id)
        allowed_progs = _get_allowed_progs(request.user)
        if allowed_progs is not None and diamex_prog and diamex_prog not in allowed_progs:
            return JsonResponse({
                'success': False,
                'error': 'Base DiameX hors périmètre'
            }, status=403)
        frais.numero_diamex = str(diamex_prog)
        frais.base_diamex = base_name
        frais.statut = 'exporte'
        frais.save()

        return JsonResponse({
            'success': True,
            'message': f'ID DiameX {diamex_prog} appliqué'
        })
    except FraisScolarite.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Frais de scolarité non trouvé'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
