"""
Vues pour l'évaluation des objectifs du planning par poste
Exemple: Superviseur Technique doit faire 1 visite d'inspection par ouvrage par an
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Count, Q, F
from django.utils import timezone
from datetime import datetime, timedelta
import pytz

from .models import Planning, Activite
from apps.employees.models import Employe, Poste, EmployeOuvrages
from apps.organization.models import Ouvrage
from .views import _get_planning_scope, _filter_employes_by_scope
from apps.organization.scoping import (
    apply_employee_organisation_scope,
    get_employee_list_organisations,
    is_partenaire_user,
    resolve_employee_organisation_scope,
)


def _employes_visibles(user):
    """
    Employés évaluables : le périmètre de planning habituel (base / organisation / tout) et, pour un
    employé d'organisation partenaire, tous les employés des organisations qui lui sont affectées.
    """
    if is_partenaire_user(user):
        return Employe.objects.select_related('base__organisation').filter(
            base__organisation__in=get_employee_list_organisations(user)
        )
    return _filter_employes_by_scope(Employe.objects.select_related('base__organisation'), user)


@login_required
def evaluation_objectifs_planning(request):
    """
    Page principale d'évaluation des objectifs du planning par poste
    """
    # Récupérer tous les postes
    postes = Poste.objects.all()
    scope = _get_planning_scope(request.user)
    organisation_scope = resolve_employee_organisation_scope(
        request.user, request.GET.get('organisation', ''), superuser_default_all=True,
    )
    if organisation_scope['options']:
        # Superuser ou partenaire : postes des organisations choisies dans le sélecteur
        postes = apply_employee_organisation_scope(postes, organisation_scope, field='organisation')
    elif scope != 'all':
        user_employe = getattr(request.user, 'employe', None)
        organisation_id = getattr(getattr(user_employe, 'base', None), 'organisation_id', None)
        if organisation_id:
            postes = postes.filter(organisation_id=organisation_id)
        else:
            postes = postes.none()
    postes = postes.order_by('organisation__nom_organisation', 'ordre_affichage', 'nom_poste')

    # Récupérer toutes les activités
    activites = Activite.objects.all().order_by('nom')

    context = {
        'postes': postes,
        'activites': activites,
        'organisation_options': organisation_scope['options'],
        'organisation_selected': organisation_scope['selected'],
    }

    return render(request, 'planning/evaluation_objectifs.html', context)


@login_required
@require_http_methods(["GET"])
def api_evaluation_objectifs(request):
    """
    API pour obtenir l'évaluation des objectifs
    Retourne une grille: Ouvrages d'un employé avec comptage des activités
    """
    try:
        # Paramètres
        employe_id = request.GET.get('employe_id')
        annee = request.GET.get('annee')
        periode_debut = request.GET.get('periode_debut')
        periode_fin = request.GET.get('periode_fin')
        objectif_min = request.GET.get('objectif_min', 1)  # Nombre minimum attendu

        if not employe_id:
            return JsonResponse({
                'success': False,
                'error': 'Employé requis'
            }, status=400)

        # Timezone Madagascar
        tz_madagascar = pytz.timezone('Indian/Antananarivo')

        # Déterminer la période
        if annee:
            annee_int = int(annee)
            date_debut = timezone.make_aware(datetime(annee_int, 1, 1), tz_madagascar)
            date_fin = timezone.make_aware(datetime(annee_int, 12, 31, 23, 59, 59), tz_madagascar)
        elif periode_debut and periode_fin:
            date_debut = timezone.make_aware(datetime.strptime(periode_debut, '%Y-%m-%d'), tz_madagascar)
            date_fin = timezone.make_aware(datetime.strptime(periode_fin, '%Y-%m-%d'), tz_madagascar)
            date_fin = date_fin.replace(hour=23, minute=59, second=59)
        else:
            # Par défaut: année en cours
            annee_courante = timezone.now().year
            date_debut = timezone.make_aware(datetime(annee_courante, 1, 1), tz_madagascar)
            date_fin = timezone.make_aware(datetime(annee_courante, 12, 31, 23, 59, 59), tz_madagascar)

        # Récupérer l'employé sélectionné
        employe = _employes_visibles(request.user).get(id=employe_id)

        # Construire la grille d'évaluation pour cet employé
        grille = []

        # Récupérer les ouvrages dont l'employé est responsable
        ouvrages_responsabilite = EmployeOuvrages.objects.filter(
            employe=employe,
            date_fin__isnull=True  # Responsabilités actives
        ).select_related('ouvrage')

        ouvrages_data = []
        total_realise = 0
        total_attendu = 0

        for resp in ouvrages_responsabilite:
            ouvrage = resp.ouvrage

            # Compter le nombre de visites (toutes activités confondues) pour cet ouvrage
            count_activites = Planning.objects.filter(
                employe=employe,
                date__gte=date_debut,
                date__lte=date_fin,
                estvalide=True,
                ouvrage=ouvrage  # L'ouvrage est directement sur le Planning
            ).count()

            objectif = int(objectif_min)
            total_attendu += objectif
            total_realise += count_activites

            # Statut: conforme si réalisé >= objectif
            statut = 'conforme' if count_activites >= objectif else 'non_conforme'
            taux = int((count_activites / objectif * 100)) if objectif > 0 else 0

            ouvrages_data.append({
                'ouvrage_id': str(ouvrage.id),
                'ouvrage_nom': ouvrage.nom_ouvrage,
                'ouvrage_code': ouvrage.code_ouvrage if hasattr(ouvrage, 'code_ouvrage') else '',
                'objectif': objectif,
                'realise': count_activites,
                'ecart': count_activites - objectif,
                'taux': taux,
                'statut': statut,
            })

        # Calculer le taux global pour l'employé
        taux_global = int((total_realise / total_attendu * 100)) if total_attendu > 0 else 0
        statut_global = 'conforme' if total_realise >= total_attendu else 'non_conforme'

        grille.append({
            'employe_id': str(employe.id),
            'employe_nom': employe.nom,
            'employe_prenom': employe.prenom,
            'employe_surnom': employe.surnom,
            'employe_nom_complet': f"{employe.nom} {employe.prenom or ''}",
            'ouvrages': ouvrages_data,
            'total_ouvrages': len(ouvrages_data),
            'total_attendu': total_attendu,
            'total_realise': total_realise,
            'total_ecart': total_realise - total_attendu,
            'taux_global': taux_global,
            'statut_global': statut_global,
        })

        # Statistiques globales (basées sur les ouvrages, pas les employés)
        total_conformes = sum(1 for ouvr in ouvrages_data if ouvr['statut'] == 'conforme')
        total_non_conformes = len(ouvrages_data) - total_conformes

        return JsonResponse({
            'success': True,
            'grille': grille,
            'periode': {
                'debut': date_debut.strftime('%Y-%m-%d'),
                'fin': date_fin.strftime('%Y-%m-%d'),
            },
            'employe': {
                'id': str(employe.id),
                'nom_complet': f"{employe.nom} {employe.prenom or ''}",
            },
            'stats': {
                'total_ouvrages': len(ouvrages_data),
                'total_conformes': total_conformes,
                'total_non_conformes': total_non_conformes,
                'taux_conformite': int((total_conformes / len(ouvrages_data) * 100)) if len(ouvrages_data) > 0 else 0,
            }
        })

    except Employe.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Employé non trouvé'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_ouvrages_employe(request, employe_id):
    """
    API pour récupérer les ouvrages dont un employé est responsable
    """
    try:
        employe = _employes_visibles(request.user).get(id=employe_id)

        ouvrages = EmployeOuvrages.objects.filter(
            employe=employe,
            date_fin__isnull=True  # Responsabilités actives
        ).select_related('ouvrage').order_by('ouvrage__nom_ouvrage')

        ouvrages_data = []
        for resp in ouvrages:
            ouvrages_data.append({
                'id': str(resp.ouvrage.id),
                'nom': resp.ouvrage.nom_ouvrage,
                'code': resp.ouvrage.code_ouvrage if hasattr(resp.ouvrage, 'code_ouvrage') else '',
                'est_responsable_principal': resp.est_responsable_principal,
            })

        return JsonResponse({
            'success': True,
            'ouvrages': ouvrages_data,
            'employe': {
                'id': str(employe.id),
                'nom_complet': f"{employe.nom} {employe.prenom or ''}",
            }
        })

    except Employe.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Employé non trouvé'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
