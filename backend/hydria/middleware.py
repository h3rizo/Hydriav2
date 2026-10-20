"""
Middleware de développement pour bypasser l'authentification
TEMPORAIRE - À supprimer une fois la base de données accessible
"""
from django.contrib.auth.models import AnonymousUser
from django.conf import settings
from django.http import HttpResponsePermanentRedirect, HttpResponseRedirect
from django.urls import set_urlconf


class MockUser:
    """Utilisateur fictif pour le développement"""
    def __init__(self):
        self.id = 1
        self.username = 'dev_user'
        self.email = 'dev@hydria.mg'
        self.first_name = 'Dev'
        self.last_name = 'User'
        self.is_authenticated = True
        self.is_staff = True
        self.is_superuser = True
        self.is_active = True

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"

    def __str__(self):
        return self.username


class DevAuthBypassMiddleware:
    """
    Middleware pour bypasser l'authentification en développement
    ATTENTION: NE JAMAIS UTILISER EN PRODUCTION
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Simuler un utilisateur connecté uniquement en mode DEBUG
        if settings.DEBUG and not hasattr(request, 'user'):
            request.user = MockUser()

        response = self.get_response(request)
        return response


class SubdomainUrlRoutingMiddleware:
    """
    Route le sous-domaine de saisie comptable vers un URLConf dedie.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = (request.get_host() or '').split(':')[0].lower()
        accounting_hosts = set(getattr(settings, 'ACCOUNTING_SUBDOMAIN_HOSTS', []) or [])
        workflow_hosts = set(getattr(settings, 'ACCOUNTING_WORKFLOW_HOSTS', []) or [])
        payroll_hosts = set(getattr(settings, 'PAYROLL_SUBDOMAIN_HOSTS', []) or [])
        admin_hosts = set(getattr(settings, 'ADMIN_SUBDOMAIN_HOSTS', []) or [])
        recruitment_hosts = set(getattr(settings, 'RECRUITMENT_SUBDOMAIN_HOSTS', []) or [])
        analyses_hosts = set(getattr(settings, 'ANALYSES_SUBDOMAIN_HOSTS', []) or [])
        ouvrages_hosts = set(getattr(settings, 'OUVRAGES_SUBDOMAIN_HOSTS', []) or [])
        planning_hosts = set(getattr(settings, 'PLANNING_SUBDOMAIN_HOSTS', []) or [])
        logistics_hosts = set(getattr(settings, 'LOGISTICS_SUBDOMAIN_HOSTS', []) or [])
        is_accounting_host = host in accounting_hosts
        is_workflow_host = host in workflow_hosts
        is_payroll_host = host in payroll_hosts
        is_admin_host = host in admin_hosts
        is_recruitment_host = host in recruitment_hosts
        is_analyses_host = host in analyses_hosts
        is_ouvrages_host = host in ouvrages_hosts
        is_planning_host = host in planning_hosts
        is_logistics_host = host in logistics_hosts
        is_accounting_home_path = (
            request.path in {'/', '/accueil', '/accueil/'}
            or request.path.startswith('/analyse-couts-ouvrages/')
        )
        payroll_paths = (
            '/employes-cascade/',
            '/postes/',
            '/grilles-salaire/',
            '/config/salaire/',
            '/config/tranches-irsa/',
            '/gardiens/',
            '/contrats-travail/',
            '/employes/revalorisations/',
            '/fiches-paie-mensuelles/',
            '/paiements-irsa/',
            '/paiements-cnaps-fmfp/',
            '/paiements-mutuelle-sante/',
        )
        is_payroll_path = any(request.path.startswith(path) for path in payroll_paths)
        main_site_payroll_paths = (
            '/config/tranches-irsa/api/simuler-salaire/',
        )
        allow_payroll_path_on_main_site = any(
            request.path.startswith(path) for path in main_site_payroll_paths
        )
        admin_paths = (
            '/positions-gps/',
            '/employes/evaluations-resultats/',
            '/system/users/',
            '/system/parameters/',
            '/system/logs/',
            '/plannings/crud/types-activites/table/',
            '/plannings/crud/types-designations/table/',
            '/plannings/deplacements/',
            '/inspections/gestion-checklists/',
            '/inspections/points-controle/table/',
            '/inspections/analyses-eau/',
            '/admin/',
        )
        is_admin_path = any(request.path.startswith(path) for path in admin_paths)
        recruitment_paths = (
            '/recrutement/',
        )
        is_recruitment_path = any(request.path.startswith(path) for path in recruitment_paths)
        analyses_paths = (
            '/geography/dashboard/',
            '/dashboard/carte/',
            '/rapports/',
            '/plannings/visites/',
            '/organisations/ouvrages/grading-annuel/',
            '/comptabilite/dashboard-recettes-globales/',
            '/rapports/partenaires-trimestriel/',
            '/organisations/ouvrages/grading-annuel/analyse/',
            '/plannings/volumetrique/tableau-points-eau/',
            '/plannings/meteo/analyse/',
            '/plannings/analyse-pieces/',
            '/dashboard/depenses/',
            '/dashboard/infrastructures/',
            '/rapports/activites-par-employe/',
            '/rapports/performance-bases/',
            '/rapports/indicateurs-diamex/',
        )
        is_analyses_path = any(request.path.startswith(path) for path in analyses_paths)
        is_moved_accounting_dashboard_path = request.path == '/comptabilite/dashboard/'
        ouvrages_paths = (
            '/ouvrages/',
        )
        is_ouvrages_path = any(request.path.startswith(path) for path in ouvrages_paths)
        planning_paths = (
            '/plannings/liste/',
            '/plannings/calendrier/',
            '/plannings/consolide/',
            '/plannings/avances/',
            '/plannings/indemnites/retour/',
            '/plannings/pointage/',
            '/facturation/paiements-forfaitaires/',
            '/facturation/suivi-forfaitaires/',
            '/facturation/caissiere/retours/',
            '/chantiers/workflows/',
            '/chantiers/demandes/',
            '/chantiers/validations-sources/',
            '/chantiers/',
            '/tacherons/',
            # Hydria Academy (quiz + jeu de plateforme 3D) vit sur planning.hydria.mg.
            '/serious-game/',
        )
        is_planning_path = any(request.path.startswith(path) for path in planning_paths)
        logistics_paths = (
            '/dashboard/expenses',
            '/dashboard/expenses/',
            '/fichiers/',
            '/stocks/',
            '/achats/',
            '/commandes/',
            '/transferts/',
            '/vehicules/',
            '/produits/',
            '/mouvements/',
            '/fiches-stock/',
            '/stock/resume/',
            '/purchases/',
        )
        is_logistics_path = any(request.path.startswith(path) for path in logistics_paths)
        main_site_only_paths = (
            '/plannings/volumetrique/analyse-consommation/',
            '/plannings/volumetrique/analyse-par-point-eau/',
            '/plannings/volumetrique/analyse-cartes-sociales/',
            '/organisations/modalites-gestion/analyse/',
        )
        is_main_site_only_path = any(request.path.startswith(path) for path in main_site_only_paths)
        main_site_accounting_paths = (
            '/comptabilite/dashboard-paiements-forfaitaire/',
            '/comptabilite/dashboard-paiements-volume/',
            '/comptabilite/dashboard-paiements-cartes-sociales/',
            '/comptabilite/dashboard-paiements-forfaitaire/calendrier/',
            '/comptabilite/dashboard-paiements-forfaitaire/calendrier/impression/',
            '/comptabilite/api/import-from-access/',
            '/comptabilite/dashboard-paiements-volume/api/communes/',
            '/comptabilite/dashboard-paiements-volume/api/pointage-releves/',
            '/comptabilite/dashboard-paiements-volume/api/pointage-releves/annuler/',
            '/comptabilite/dashboard-paiements-volume/api/releve/delete/',
            '/comptabilite/dashboard-paiements-volume/api/remarque/',
            '/comptabilite/dashboard-paiements-forfaitaire/api/communes/',
            '/comptabilite/api/forfaitaire/explication/',
            '/comptabilite/api/forfaitaire/details/',
            '/comptabilite/api/forfaitaire/pointage/',
            '/comptabilite/api/forfaitaire/pointage/annuler/',
            '/comptabilite/api/forfaitaire/calendrier/deplacer/',
            '/comptabilite/recoupement/releves/api/details-3e/',
            '/comptabilite/recoupement/releves/api/update-releve/',
            '/comptabilite/api/delais-paiement-details/',
        )
        allow_accounting_path_on_main_site = any(
            request.path.startswith(path) for path in main_site_accounting_paths
        )
        main_site_planning_paths = (
            '/plannings/volumetrique/',
            '/plannings/volumetrique/global/',
            '/plannings/recettes-forfaitaires/',
            '/plannings/avances/maintenance/',
            '/plannings/avances/traiter/',
            '/plannings/avances/api/supprimer-source/',
            '/plannings/avances/imprimer-tickets-recettes/',
            # Ces API sont aussi appelees depuis les dashboards du domaine principal.
            # Ne pas les rediriger vers planning.hydria.mg : un fetch POST avec CSRF
            # ne peut pas suivre cette redirection inter-origine sans erreur CORS.
            '/facturation/suivi-forfaitaires/api/',
        )
        force_planning_path_to_main_site = any(
            request.path.startswith(path) for path in main_site_planning_paths
        )

        request.is_accounting_subdomain = is_accounting_host
        request.is_accounting_workflow_subdomain = is_workflow_host and not is_accounting_host
        request.is_payroll_subdomain = is_payroll_host
        request.is_admin_subdomain = is_admin_host
        request.is_recruitment_subdomain = is_recruitment_host
        request.is_analyses_subdomain = is_analyses_host
        request.is_ouvrages_subdomain = is_ouvrages_host
        request.is_planning_subdomain = is_planning_host
        request.is_logistics_subdomain = is_logistics_host

        # Le dashboard comptable appartient desormais a compta.hydria.mg.
        # Conserver une redirection permanente depuis son ancienne adresse,
        # y compris les filtres presents dans la query string.
        if is_analyses_host and is_moved_accounting_dashboard_path:
            target_base = (getattr(settings, 'ACCOUNTING_SUBDOMAIN_URL', '') or '').rstrip('/')
            if target_base:
                redirect_url = f"{target_base}{request.get_full_path()}"
                return HttpResponsePermanentRedirect(redirect_url)

        if is_accounting_host and allow_accounting_path_on_main_site:
            target_base = (getattr(settings, 'MAIN_SITE_URL', 'https://www.hydria.mg') or 'https://www.hydria.mg').rstrip('/')
            redirect_url = f"{target_base}{request.get_full_path()}"
            return HttpResponseRedirect(redirect_url)

        if is_planning_host and force_planning_path_to_main_site:
            target_base = (getattr(settings, 'MAIN_SITE_URL', 'https://www.hydria.mg') or 'https://www.hydria.mg').rstrip('/')
            redirect_url = f"{target_base}{request.get_full_path()}"
            return HttpResponseRedirect(redirect_url)

        is_compta_path = request.path.startswith('/comptabilite/')
        is_fournisseurs_path = request.path.startswith('/facturation/fournisseurs/')
        is_previsions_path = request.path.startswith('/facturation/previsions/')

        if (
            not is_accounting_host
            and not is_analyses_host
            and host.endswith('hydria.mg')
            and not allow_accounting_path_on_main_site
            and (
                is_compta_path
                or is_previsions_path
                or (is_fournisseurs_path and not is_logistics_host)
            )
        ):
            target_base = (getattr(settings, 'ACCOUNTING_SUBDOMAIN_URL', '') or '').rstrip('/')
            if target_base:
                redirect_url = f"{target_base}{request.get_full_path()}"
                return HttpResponseRedirect(redirect_url)

        if (
            not is_payroll_host
            and host.endswith('hydria.mg')
            and is_payroll_path
            and not allow_payroll_path_on_main_site
        ):
            target_base = (getattr(settings, 'PAYROLL_SUBDOMAIN_URL', '') or '').rstrip('/')
            if target_base:
                redirect_url = f"{target_base}{request.get_full_path()}"
                return HttpResponseRedirect(redirect_url)

        if (
            not is_recruitment_host
            and host.endswith('hydria.mg')
            and is_recruitment_path
        ):
            target_base = (getattr(settings, 'RECRUITMENT_SUBDOMAIN_URL', '') or '').rstrip('/')
            if target_base:
                redirect_url = f"{target_base}{request.get_full_path()}"
                return HttpResponseRedirect(redirect_url)

        if (
            not is_admin_host
            and host.endswith('hydria.mg')
            and is_admin_path
        ):
            target_base = (getattr(settings, 'ADMIN_SUBDOMAIN_URL', '') or '').rstrip('/')
            if target_base:
                redirect_url = f"{target_base}{request.get_full_path()}"
                return HttpResponseRedirect(redirect_url)

        if (
            not is_analyses_host
            and host.endswith('hydria.mg')
            and is_analyses_path
        ):
            target_base = (getattr(settings, 'ANALYSES_SUBDOMAIN_URL', '') or '').rstrip('/')
            if target_base:
                redirect_url = f"{target_base}{request.get_full_path()}"
                return HttpResponseRedirect(redirect_url)

        if (
            not is_ouvrages_host
            and host.endswith('hydria.mg')
            and is_ouvrages_path
        ):
            target_base = (getattr(settings, 'OUVRAGES_SUBDOMAIN_URL', '') or '').rstrip('/')
            if target_base:
                suffix = request.get_full_path()[len('/ouvrages'):] or '/'
                redirect_url = f"{target_base}{suffix}"
                return HttpResponseRedirect(redirect_url)

        # Page des coûts types : déplacée sur ouvrages.hydria.mg (les API d'aperçu et
        # d'application, appelées depuis le formulaire de réparation, restent sur place).
        if (
            not is_ouvrages_host
            and host.endswith('hydria.mg')
            and request.path.rstrip('/') == '/plannings/couts-types'
        ):
            target_base = (getattr(settings, 'OUVRAGES_SUBDOMAIN_URL', '') or '').rstrip('/')
            if target_base:
                query = request.META.get('QUERY_STRING', '')
                return HttpResponseRedirect(f"{target_base}/couts-types/{'?' + query if query else ''}")

        if (
            not is_planning_host
            and host.endswith('hydria.mg')
            and is_planning_path
            and not force_planning_path_to_main_site
        ):
            target_base = (getattr(settings, 'PLANNING_SUBDOMAIN_URL', '') or '').rstrip('/')
            if target_base:
                redirect_url = f"{target_base}{request.get_full_path()}"
                return HttpResponseRedirect(redirect_url)

        if (
            not is_logistics_host
            and host.endswith('hydria.mg')
            and is_logistics_path
        ):
            target_base = (getattr(settings, 'LOGISTICS_SUBDOMAIN_URL', '') or '').rstrip('/')
            if target_base:
                redirect_url = f"{target_base}{request.get_full_path()}"
                return HttpResponseRedirect(redirect_url)

        if is_analyses_host and is_main_site_only_path:
            target_base = (getattr(settings, 'MAIN_SITE_URL', 'https://www.hydria.mg') or 'https://www.hydria.mg').rstrip('/')
            redirect_url = f"{target_base}{request.get_full_path()}"
            return HttpResponseRedirect(redirect_url)

        if (
            request.is_accounting_workflow_subdomain
            or (is_accounting_host and is_accounting_home_path)
            or (is_accounting_host and request.path.startswith('/facturation/fournisseurs/'))
            or (is_accounting_host and request.path.startswith('/facturation/previsions/'))
        ):
            request.urlconf = 'hydria.urls_saisie'
            set_urlconf('hydria.urls_saisie')
        elif is_payroll_host:
            request.urlconf = 'hydria.urls_paie'
            set_urlconf('hydria.urls_paie')
        elif is_admin_host:
            request.urlconf = 'hydria.urls_admin'
            set_urlconf('hydria.urls_admin')
        elif is_recruitment_host:
            request.urlconf = 'hydria.urls_recrutement'
            set_urlconf('hydria.urls_recrutement')
        elif is_analyses_host:
            request.urlconf = 'hydria.urls_analyses'
            set_urlconf('hydria.urls_analyses')
        elif is_ouvrages_host:
            request.urlconf = 'hydria.urls_ouvrages'
            set_urlconf('hydria.urls_ouvrages')
        elif is_planning_host:
            request.urlconf = 'hydria.urls_planning'
            set_urlconf('hydria.urls_planning')
        elif is_logistics_host:
            request.urlconf = 'hydria.urls_logistique'
            set_urlconf('hydria.urls_logistique')

        try:
            response = self.get_response(request)
        finally:
            if (
                request.is_accounting_workflow_subdomain
                or (is_accounting_host and is_accounting_home_path)
                or (is_accounting_host and request.path.startswith('/facturation/fournisseurs/'))
                or (is_accounting_host and request.path.startswith('/facturation/previsions/'))
                or is_payroll_host
                or is_admin_host
                or is_recruitment_host
                or is_analyses_host
                or is_ouvrages_host
                or is_planning_host
                or is_logistics_host
            ):
                set_urlconf(None)

        return response
