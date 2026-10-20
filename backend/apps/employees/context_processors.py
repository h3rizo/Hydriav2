"""
Context processors pour les employes.
Fournit des donnees globales sur l employe connecte dans tous les templates.
"""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import PositionGPSEmploye
from .permissions import (
    has_admin_access,
    has_admin_compta_access,
    has_compta_access,
    is_directeur_poste,
    is_visiteur,
)


def employee_tracking_info(request):
    """
    Ajoute les informations de tracking GPS de l employe connecte.
    - Derniere position GPS
    - Village le plus proche
    - Cumul temps de connexion du mois
    """
    context = {
        'employee_tracking': {
            'has_position': False,
            'latitude': None,
            'longitude': None,
            'village_proche': None,
            'distance_village': None,
            'temps_connexion_mois': 0,
            'last_update': None,
        }
    }

    if not request.user.is_authenticated:
        return context

    try:
        employe = request.user.employe
    except AttributeError:
        return context

    derniere_position = PositionGPSEmploye.objects.filter(
        employe=employe
    ).select_related('village_proche').order_by('-date_enregistrement').first()

    if derniere_position:
        context['employee_tracking'].update({
            'has_position': True,
            'latitude': float(derniere_position.latitude) if derniere_position.latitude else None,
            'longitude': float(derniere_position.longitude) if derniere_position.longitude else None,
            'village_proche': derniere_position.village_proche.nom_village if derniere_position.village_proche else None,
            'distance_village': float(derniere_position.distance_village) if derniere_position.distance_village else None,
            'last_update': derniere_position.date_enregistrement,
        })

    now = timezone.now()
    debut_mois = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    positions_mois = PositionGPSEmploye.objects.filter(
        employe=employe,
        date_enregistrement__gte=debut_mois
    ).order_by('date_enregistrement')

    duree_totale = timedelta(0)
    positions_list = list(positions_mois)

    for i, pos in enumerate(positions_list):
        if i + 1 < len(positions_list):
            next_pos = positions_list[i + 1]
            diff = next_pos.date_enregistrement - pos.date_enregistrement
            if diff <= timedelta(hours=8):
                duree_totale += diff

    heures_totales = duree_totale.total_seconds() / 3600
    context['employee_tracking']['temps_connexion_mois'] = round(heures_totales, 1)

    return context


def permissions(request):
    """
    Ajoute les fonctions de verification des permissions dans le contexte des templates.
    """
    documentation_shell_base_template = 'base.html'
    if getattr(request, 'is_accounting_subdomain', False) or getattr(request, 'is_accounting_workflow_subdomain', False):
        documentation_shell_base_template = 'accounting/base.html'
    elif getattr(request, 'is_payroll_subdomain', False):
        documentation_shell_base_template = 'payroll/base.html'
    elif getattr(request, 'is_admin_subdomain', False):
        documentation_shell_base_template = 'admin/base.html'
    elif getattr(request, 'is_recruitment_subdomain', False):
        documentation_shell_base_template = 'recrutement/base.html'
    elif getattr(request, 'is_analyses_subdomain', False):
        documentation_shell_base_template = 'analyses/base.html'
    elif getattr(request, 'is_ouvrages_subdomain', False):
        documentation_shell_base_template = 'ouvrages/base.html'
    elif getattr(request, 'is_planning_subdomain', False):
        documentation_shell_base_template = 'planning/base.html'
    elif getattr(request, 'is_logistics_subdomain', False):
        documentation_shell_base_template = 'logistique/base.html'

    dashboard_shell_base_template = 'base.html'
    if getattr(request, 'is_logistics_subdomain', False):
        dashboard_shell_base_template = 'logistique/base.html'
    elif getattr(request, 'is_analyses_subdomain', False):
        dashboard_shell_base_template = 'analyses/base.html'

    return {
        'has_admin_compta_access': has_admin_compta_access(request.user),
        'has_admin_access': has_admin_access(request.user),
        'has_compta_access': has_compta_access(request.user),
        'is_directeur_poste': is_directeur_poste(request.user),
        'is_visiteur': is_visiteur(request.user),
        'documentation_shell_base_template': documentation_shell_base_template,
        'dashboard_shell_base_template': dashboard_shell_base_template,
        'accounting_shell_base_template': 'accounting/base.html' if (
            getattr(request, 'is_accounting_subdomain', False)
            or getattr(request, 'is_accounting_workflow_subdomain', False)
        ) else 'base.html',
        'payroll_shell_base_template': 'payroll/base.html' if getattr(request, 'is_payroll_subdomain', False) else 'base.html',
        'payroll_subdomain_url': (getattr(settings, 'PAYROLL_SUBDOMAIN_URL', 'https://paie.hydria.mg') or 'https://paie.hydria.mg').rstrip('/'),
        'admin_shell_base_template': 'admin/base.html' if getattr(request, 'is_admin_subdomain', False) else 'base.html',
        'admin_subdomain_url': (getattr(settings, 'ADMIN_SUBDOMAIN_URL', 'https://admin.hydria.mg') or 'https://admin.hydria.mg').rstrip('/'),
        'recrutement_shell_base_template': 'recrutement/base.html' if getattr(request, 'is_recruitment_subdomain', False) else 'base.html',
        'recruitment_subdomain_url': (getattr(settings, 'RECRUITMENT_SUBDOMAIN_URL', 'https://recrutement.hydria.mg') or 'https://recrutement.hydria.mg').rstrip('/'),
        'analyses_shell_base_template': 'analyses/base.html' if getattr(request, 'is_analyses_subdomain', False) else 'base.html',
        'analyses_subdomain_url': (getattr(settings, 'ANALYSES_SUBDOMAIN_URL', 'https://analyses.hydria.mg') or 'https://analyses.hydria.mg').rstrip('/'),
        'ouvrages_shell_base_template': 'ouvrages/base.html' if getattr(request, 'is_ouvrages_subdomain', False) else 'base.html',
        'ouvrages_subdomain_url': (getattr(settings, 'OUVRAGES_SUBDOMAIN_URL', 'https://ouvrages.hydria.mg') or 'https://ouvrages.hydria.mg').rstrip('/'),
        'planning_shell_base_template': 'planning/base.html' if getattr(request, 'is_planning_subdomain', False) else 'base.html',
        'planning_subdomain_url': (getattr(settings, 'PLANNING_SUBDOMAIN_URL', 'https://planning.hydria.mg') or 'https://planning.hydria.mg').rstrip('/'),
        'logistics_shell_base_template': 'logistique/base.html' if getattr(request, 'is_logistics_subdomain', False) else 'base.html',
        'logistics_subdomain_url': (getattr(settings, 'LOGISTICS_SUBDOMAIN_URL', 'https://logistique.hydria.mg') or 'https://logistique.hydria.mg').rstrip('/'),
    }
