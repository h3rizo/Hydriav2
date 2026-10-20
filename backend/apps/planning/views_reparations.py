from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from datetime import date, datetime
from decimal import Decimal
import pytz
import re
import statistics
import unicodedata

from apps.planning.models import PlanningDetail, Activite, Planning, ActivitePoste, Designation
from apps.billing.models import PointEau
from apps.infrastructure.models import EquipementConstitutif
from apps.organization.models import Ouvrage, Magasin
from apps.organization.scoping import (
    filter_modalites_by_gestionnaire_period,
    get_default_gestionnaire_filter_value,
    get_gestionnaire_organisations_queryset,
    get_same_base_active_employe_ids,
    get_user_accessible_gestionnaire_ids,
    is_partenaire_user,
    is_same_base_responsable_support_role,
)
from apps.geography.models import Commune
from apps.employees.models import Employe, FichePoste, HierarchieEmploye, EmployeOuvrages
from apps.employees.permissions import is_directeur_poste
from apps.planning.repair_classification import (
    get_repair_classification,
    get_reparations_fiches_queryset,
)
from apps.planning.repair_workflow_grading import (
    get_repair_workflow_grading_from_flags,
)
from apps.planning import views_simple


def _filter_designations_avance(queryset):
    return queryset.filter(
        Q(type_avance_caissiere='avance') |
        Q(type_avance_caissiere__iexact='Avance') |
        Q(type_avance_caissiere__icontains='avance')
    )


def _filter_designations_bon_livraison(queryset):
    return queryset.filter(
        Q(type_avance_caissiere='bon_livraison') |
        Q(type_avance_caissiere__iexact='Bon de livraison') |
        Q(type_avance_caissiere__icontains='bon') |
        Q(type_avance_caissiere__icontains='livraison')
    )


def get_repair_activities():
    """Retourne les activités de type réparation/réhabilitation"""
    # Recherche avec accents (base de données utilise des accents)
    # Exclure "Préparation" et "Au cas oÃ¹" qui ne sont pas des réparations
    return Activite.objects.filter(
        Q(nom__icontains='paration') |
        Q(nom__icontains='habilitation')
    ).exclude(
        Q(nom__icontains='préparation') |
        Q(nom__icontains='preparation') |
        Q(nom__icontains='au cas')
    ).distinct()


def _repair_activity_keyword(activity_name):
    """Retourne un mot-clé simple pour choisir une fiche de poste de fallback."""
    name = (activity_name or '').lower()
    if 'panne' in name:
        return 'panne'
    if 'habilitation' in name:
        return 'habilitation'
    if 'paration' in name:
        return 'paration'
    return ''


def _normalize_role_name(value):
    if not value:
        return ''
    normalized = unicodedata.normalize('NFKD', str(value))
    return ' '.join(
        normalized.encode('ascii', errors='ignore').decode('ascii').lower().strip().split()
    )


ALLOWED_REPAIR_ASSIGNABLE_ROLES = {
    _normalize_role_name('Mpikojakoja Ifotony'),
    _normalize_role_name('Superviseur technique'),
    _normalize_role_name('Responsable opérationnel'),
    _normalize_role_name('Responsable operationnel'),
    _normalize_role_name('Directeur'),
}

# Postes assignables reconnus par préfixe : « Agent de maintenance », « Agent de maintenance mixte », etc.
ASSIGNABLE_REPAIR_ROLE_PREFIXES = (
    _normalize_role_name('Agent de maintenance'),
)


def _is_assignable_repair_role(poste_nom):
    role = _normalize_role_name(poste_nom)
    return role in ALLOWED_REPAIR_ASSIGNABLE_ROLES or role.startswith(ASSIGNABLE_REPAIR_ROLE_PREFIXES)


def get_repair_activity_fiche_poste_map():
    """
    Map activite_id -> fiche_poste_id pour les activités réparation/réhabilitation.

    Priorité:
    1) Lien direct ActivitePoste (activité -> fiche poste)
    2) Fallback par type_activite (fiche poste dans planning)
    3) Fallback par type_activite (n'importe quelle fiche poste)
    """
    repair_activities = list(get_repair_activities().select_related('type_activite'))
    if not repair_activities:
        return {}

    activity_ids = [activity.id for activity in repair_activities]
    activity_to_fiche = {}

    direct_links = ActivitePoste.objects.filter(
        activite_id__in=activity_ids,
        fiche_poste__isnull=False,
    ).values_list('activite_id', 'fiche_poste_id')
    for activite_id, fiche_poste_id in direct_links:
        activity_to_fiche.setdefault(activite_id, fiche_poste_id)

    missing_type_ids = {
        activity.type_activite_id
        for activity in repair_activities
        if activity.id not in activity_to_fiche and activity.type_activite_id
    }
    if not missing_type_ids:
        return activity_to_fiche

    fiches = list(
        FichePoste.objects.filter(type_activites_id__in=missing_type_ids)
        .order_by('-dans_planning', 'ordre', 'tache')
    )
    fiches_by_type = {}
    for fiche in fiches:
        fiches_by_type.setdefault(fiche.type_activites_id, []).append(fiche)

    for activity in repair_activities:
        if activity.id in activity_to_fiche or not activity.type_activite_id:
            continue

        candidates = fiches_by_type.get(activity.type_activite_id, [])
        if not candidates:
            continue

        keyword = _repair_activity_keyword(activity.nom)
        chosen = None
        if keyword:
            chosen = next(
                (fiche for fiche in candidates if keyword in (fiche.tache or '').lower()),
                None
            )
        if not chosen:
            chosen = candidates[0]

        activity_to_fiche[activity.id] = chosen.id

    return activity_to_fiche


def get_creatable_repair_activities():
    """Activités de réparation réellement créables (avec fallback par type)."""
    activity_to_fiche = get_repair_activity_fiche_poste_map()
    if not activity_to_fiche:
        return Activite.objects.none()
    return Activite.objects.filter(id__in=list(activity_to_fiche.keys())).order_by('nom')


def _get_scoped_organisations_for_user(user):
    gestionnaire_ids = get_user_accessible_gestionnaire_ids(user)
    organisations = get_gestionnaire_organisations_queryset()
    if gestionnaire_ids is not None:
        if gestionnaire_ids:
            organisations = organisations.filter(id__in=gestionnaire_ids)
        else:
            organisations = organisations.none()
    return gestionnaire_ids, organisations


def _get_default_repair_organisation_id(user, gestionnaire_ids):
    return get_default_gestionnaire_filter_value(user, gestionnaire_ids) or 'all'


def _get_year_bounds(annee):
    return date(int(annee), 1, 1), date(int(annee), 12, 31)


def _filter_modalites_for_annee(queryset, annee=None):
    if annee is None:
        today = timezone.localdate()
        return queryset.filter(
            statut='actif',
            date_debut__lte=today,
        ).filter(Q(date_fin__isnull=True) | Q(date_fin__gte=today))

    year_start, year_end = _get_year_bounds(annee)
    return queryset.filter(
        Q(date_debut__isnull=True) | Q(date_debut__lte=year_end)
    ).filter(
        Q(date_fin__isnull=True) | Q(date_fin__gte=year_start)
    )


def _get_scoped_modalites_queryset(organisation_id, gestionnaire_ids, annee=None):
    from apps.billing.models import ModaliteGestion

    modalites_qs = ModaliteGestion.objects.all()
    gestionnaire_filter = None
    if organisation_id and organisation_id != 'all':
        if gestionnaire_ids is not None:
            allowed_ids = {str(_id) for _id in gestionnaire_ids}
            if str(organisation_id) not in allowed_ids:
                return ModaliteGestion.objects.none()
        gestionnaire_filter = organisation_id
    elif gestionnaire_ids is not None:
        if not gestionnaire_ids:
            return ModaliteGestion.objects.none()
        gestionnaire_filter = gestionnaire_ids

    if annee is None:
        today = timezone.localdate()
        modalites_qs = modalites_qs.filter(
            statut='actif',
            date_debut__lte=today,
        ).filter(
            Q(date_fin__isnull=True) | Q(date_fin__gte=today)
        )
        if gestionnaire_filter:
            if isinstance(gestionnaire_filter, (list, tuple, set)):
                return modalites_qs.filter(gestionnaire_id__in=gestionnaire_filter)
            return modalites_qs.filter(gestionnaire_id=gestionnaire_filter)
        return modalites_qs

    return filter_modalites_by_gestionnaire_period(
        modalites_qs,
        gestionnaire_filter,
        annee,
    )


def _get_scoped_ouvrage_ids(organisation_id, gestionnaire_ids, annee=None):
    modalites_qs = _get_scoped_modalites_queryset(
        organisation_id,
        gestionnaire_ids,
        annee=annee,
    )
    return set(modalites_qs.values_list('ouvrage_id', flat=True).distinct())


def _get_active_responsable_ouvrages_queryset(reference_date=None):
    reference_date = reference_date or timezone.now().date()
    return EmployeOuvrages.objects.filter(
        date_debut__lte=reference_date,
    ).filter(
        Q(date_fin__isnull=True) | Q(date_fin__gte=reference_date)
    )


def _get_active_ascendant_employe_ids(root_employe_id, reference_date=None):
    reference_date = reference_date or timezone.now().date()
    employe_ids = set()
    frontier_ids = {root_employe_id}

    while frontier_ids:
        parent_ids = set(
            HierarchieEmploye.objects.filter(
                employe_id__in=frontier_ids,
                date_debut__lte=reference_date,
            ).filter(
                Q(date_fin__isnull=True) | Q(date_fin__gte=reference_date)
            ).values_list('superieur_id', flat=True)
        )
        parent_ids -= employe_ids
        if not parent_ids:
            break
        employe_ids.update(parent_ids)
        frontier_ids = parent_ids

    return employe_ids


def _filter_ouvrages_queryset_by_responsable_employe(queryset, employe_id, reference_date=None):
    normalized_employe_id = (str(employe_id).strip() if employe_id is not None else '')
    if not normalized_employe_id or normalized_employe_id.lower() == 'all':
        return queryset

    reference_date = reference_date or timezone.now().date()
    employe_ids = _get_active_subordinate_employe_ids(normalized_employe_id, reference_date)

    return queryset.filter(
        employes_responsables__employe_id__in=employe_ids,
        employes_responsables__date_debut__lte=reference_date,
    ).filter(
        Q(employes_responsables__date_fin__isnull=True)
        | Q(employes_responsables__date_fin__gte=reference_date)
    ).distinct()


def _get_responsable_employes_for_ouvrage_ids(ouvrage_ids, reference_date=None):
    ouvrage_id_list = list(ouvrage_ids or [])
    if not ouvrage_id_list:
        return Employe.objects.none()

    reference_date = reference_date or timezone.now().date()
    direct_employe_ids = set(_get_active_responsable_ouvrages_queryset(reference_date).filter(
        ouvrage_id__in=ouvrage_id_list
    ).values_list('employe_id', flat=True).distinct())

    if not direct_employe_ids:
        return Employe.objects.none()

    employe_ids = set(direct_employe_ids)
    for employe_id in direct_employe_ids:
        employe_ids.update(_get_active_ascendant_employe_ids(employe_id, reference_date))

    return Employe.objects.filter(
        id__in=employe_ids,
        date_debauchage__isnull=True,
    ).distinct().order_by('surnom', 'nom_employe')


def _get_active_subordinate_employe_ids(root_employe_id, reference_date=None):
    reference_date = reference_date or timezone.now().date()
    employe_ids = {root_employe_id}
    frontier_ids = {root_employe_id}

    while frontier_ids:
        child_ids = set(
            HierarchieEmploye.objects.filter(
                superieur_id__in=frontier_ids,
                date_debut__lte=reference_date,
            ).filter(
                Q(date_fin__isnull=True) | Q(date_fin__gte=reference_date)
            ).values_list('employe_id', flat=True)
        )
        child_ids -= employe_ids
        if not child_ids:
            break
        employe_ids.update(child_ids)
        frontier_ids = child_ids

    return employe_ids


def _get_assignable_repair_employees_queryset(user, reference_date=None):
    reference_date = reference_date or timezone.now().date()
    employe = getattr(user, 'employe', None)
    if not employe:
        return Employe.objects.none()

    assignable_ids = set(get_same_base_active_employe_ids(employe, reference_date))
    if not assignable_ids:
        return Employe.objects.none()

    return Employe.objects.filter(
        id__in=assignable_ids
    ).filter(
        Q(date_debauchage__isnull=True) | Q(date_debauchage__gte=reference_date)
    ).select_related('poste')


def _filter_assignable_repair_roles(employes_queryset):
    allowed_ids = []
    for employe in employes_queryset:
        poste_nom = getattr(getattr(employe, 'poste', None), 'nom_poste', '')
        if _is_assignable_repair_role(poste_nom):
            allowed_ids.append(employe.id)

    if not allowed_ids:
        return Employe.objects.none()

    return employes_queryset.filter(id__in=allowed_ids)


def _get_repair_modal_employees_queryset(user, ouvrage_ids=None, reference_date=None):
    reference_date = reference_date or timezone.now().date()
    same_base_qs = _get_assignable_repair_employees_queryset(user, reference_date)

    union_ids = set(same_base_qs.values_list('id', flat=True))
    if ouvrage_ids:
        ouvrage_responsables_qs = _get_responsable_employes_for_ouvrage_ids(
            ouvrage_ids,
            reference_date=reference_date,
        ).select_related('poste')
        union_ids.update(ouvrage_responsables_qs.values_list('id', flat=True))

    if not union_ids:
        return Employe.objects.none()

    combined_qs = Employe.objects.filter(id__in=union_ids).filter(
        Q(date_debauchage__isnull=True) | Q(date_debauchage__gte=reference_date)
    ).select_related('poste').distinct()

    return _filter_assignable_repair_roles(combined_qs)


def _group_employes_par_base_poste(employes):
    """
    Employés regroupés par base puis par poste, pour un <select> à <optgroup> (pas d'imbrication
    possible en HTML : chaque groupe est étiqueté « Base › Poste »).
    Retourne [{'label': 'Base › Poste', 'employes': [...]}], trié par base, poste puis surnom.
    """
    groupes = {}
    for employe in employes.select_related('base', 'poste'):
        nom_base = getattr(employe.base, 'nom_base', '') or 'Sans base'
        nom_poste = getattr(employe.poste, 'nom_poste', '') or 'Sans poste'
        groupes.setdefault((nom_base.lower(), nom_base, nom_poste.lower(), nom_poste), []).append(employe)

    resultat = []
    for (_, nom_base, _, nom_poste), membres in sorted(groupes.items(), key=lambda kv: (kv[0][0], kv[0][2])):
        membres.sort(key=lambda e: (e.surnom or e.nom or '').lower())
        resultat.append({'label': f"{nom_base} › {nom_poste}", 'employes': membres})
    return resultat


def _apply_employe_hierarchy_ouvrage_scope(ouvrage_ids, user, reference_date=None):
    if ouvrage_ids is None:
        scoped_ids = None
    else:
        scoped_ids = set(ouvrage_ids)

    if getattr(user, 'is_superuser', False) or is_directeur_poste(user):
        return scoped_ids

    # Un employé d'organisation partenaire n'a pas d'ouvrages confiés (EmployeOuvrages) : son
    # périmètre est défini par ses affectations aux gestionnaires, déjà appliquées en amont.
    if is_partenaire_user(user):
        return scoped_ids

    employe = getattr(user, 'employe', None)
    if not employe:
        return scoped_ids

    reference_date = reference_date or timezone.now().date()
    if is_same_base_responsable_support_role(user):
        employe_ids = get_same_base_active_employe_ids(employe, reference_date)
    else:
        employe_ids = _get_active_subordinate_employe_ids(employe.id, reference_date)

    responsable_ouvrage_ids = set(
        EmployeOuvrages.objects.filter(
            employe_id__in=employe_ids,
            date_debut__lte=reference_date,
        ).filter(
            Q(date_fin__isnull=True) | Q(date_fin__gte=reference_date)
        ).values_list('ouvrage_id', flat=True).distinct()
    )

    if scoped_ids is None:
        return responsable_ouvrage_ids

    return scoped_ids.intersection(responsable_ouvrage_ids)


def _get_user_scoped_ouvrage_ids(organisation_id, gestionnaire_ids, user, annee=None, reference_date=None):
    ouvrage_ids = _get_scoped_ouvrage_ids(
        organisation_id,
        gestionnaire_ids,
        annee=annee,
    )
    return _apply_employe_hierarchy_ouvrage_scope(
        ouvrage_ids,
        user,
        reference_date=reference_date,
    )


@login_required
def suivi_reparations(request):
    """Page de suivi des réparations et réhabilitations par ouvrage"""
    # Timezone Madagascar
    tz_madagascar = pytz.timezone('Indian/Antananarivo')

    # Récupérer l'organisation Soakoja par défaut
    gestionnaire_ids, organisations = _get_scoped_organisations_for_user(request.user)
    default_org_id = _get_default_repair_organisation_id(request.user, gestionnaire_ids)
    show_organisation_filter = False

    # Récupérer les filtres
    annee_courante = datetime.now().year
    annee_filter = request.GET.get('annee', str(annee_courante))
    organisation_id = request.GET.get('organisation', default_org_id) or default_org_id
    if organisation_id == 'all':
        organisation_id = default_org_id
    if organisation_id != 'all' and gestionnaire_ids is not None:
        allowed_ids = {str(_id) for _id in gestionnaire_ids}
        if organisation_id not in allowed_ids:
            organisation_id = default_org_id
    commune_id = request.GET.get('commune', '')
    ouvrage_id = request.GET.get('ouvrage', '')
    statut_filter = request.GET.get('statut', '')
    grading_filter = request.GET.get('grading', '')
    activite_filter = request.GET.get('activite', '')
    date_debut = request.GET.get('date_debut', '')
    date_fin = request.GET.get('date_fin', '')

    fiches_reparation = list(get_reparations_fiches_queryset().order_by('type_activites__nomtype', 'ordre', 'tache'))
    fiche_poste_ids = [fiche.id for fiche in fiches_reparation]
    fiche_poste_to_activite_nom = {
        fiche.id: f"{getattr(getattr(fiche, 'type_activites', None), 'nomtype', '') or ''} {fiche.tache or ''}".strip()
        for fiche in fiches_reparation
    }


    # Récupérer les détails de planning avec ces activités
    details = PlanningDetail.objects.filter(
        planning__fiche_poste_id__in=fiche_poste_ids
    ).select_related(
        'planning',
        'planning__fiche_poste',
        'planning__employe',
        'planning__ouvrage',
        'point_eau',
        'point_eau__ouvrage',
        'point_eau__parcelle__village__fokontany__commune',
        'equipement_constitutif',
        'equipement_constitutif__ouvrage'
    ).defer(
        # Photos en base64 (jusqu'à 40 Mo par ligne) non utilisées par cette page, qui les charge
        # à la demande par API : sans defer, ~1 Go de RAM par affichage (select_related les
        # dupliquait pour chaque détail).
        'planning__photo', 'point_eau__photos', 'equipement_constitutif__photos',
    )

    # Appliquer les filtres géographiques
    if commune_id:
        details = details.filter(
            Q(point_eau__parcelle__village__fokontany__commune_id=commune_id) |
            Q(equipement_constitutif__ouvrage__id__in=PointEau.objects.filter(
                parcelle__village__fokontany__commune_id=commune_id
            ).values_list('ouvrage_id', flat=True))
        )

    if ouvrage_id:
        details = details.filter(
            Q(planning__ouvrage_id=ouvrage_id) |
            Q(point_eau__ouvrage_id=ouvrage_id) |
            Q(equipement_constitutif__ouvrage_id=ouvrage_id)
        )

    # Filtrer par dates si spécifiées
    if date_debut:
        details = details.filter(planning__date__gte=date_debut)
    if date_fin:
        details = details.filter(planning__date__lte=date_fin)
    if activite_filter:
        details = details.filter(planning__fiche_poste_id=activite_filter)

    annee_int = int(annee_filter) if annee_filter else annee_courante

    # Pré-filtre SQL borné sur l'année Madagascar (sans extraction de date en SQL,
    # juste une plage sur le datetime complet -> pas de piège timezone, voir
    # TIMEZONE_GUIDE.md). Réduit drastiquement le volume chargé (au lieu de tout
    # l'historique) avant le filtrage Python précis ci-dessous, qui reste la
    # référence pour la correspondance exacte au jour près.
    if not date_debut and not date_fin:
        annee_debut_mg = tz_madagascar.localize(datetime(annee_int, 1, 1))
        annee_fin_mg = tz_madagascar.localize(datetime(annee_int + 1, 1, 1))
        details = details.filter(planning__date__gte=annee_debut_mg, planning__date__lt=annee_fin_mg)

    # Convertir en liste et filtrer par année (conversion timezone précise, jour par jour)
    details_list = list(details.order_by('-planning__date'))

    # Filtrer par année en Python avec conversion timezone
    details_filtered = []
    for detail in details_list:
        if detail.planning and detail.planning.date:
            date_aware = detail.planning.date
            if date_aware.tzinfo:
                date_madagascar = date_aware.astimezone(tz_madagascar)
            else:
                date_madagascar = tz_madagascar.localize(date_aware)

            date_obj = date_madagascar.date()

            if date_obj.year == annee_int:
                details_filtered.append(detail)

    details_list = details_filtered

    # Déterminer l'ouvrage de chaque détail une seule fois, puis pré-charger les
    # communes de tous les ouvrages concernés en une seule requête groupée
    # (au lieu d'une requête par ouvrage distinct dans la boucle -> N+1).
    ouvrage_par_detail = {}
    for detail in details_list:
        ouvrage = None
        if detail.planning and detail.planning.ouvrage:
            ouvrage = detail.planning.ouvrage
        elif detail.point_eau and detail.point_eau.ouvrage:
            ouvrage = detail.point_eau.ouvrage
        elif detail.equipement_constitutif and detail.equipement_constitutif.ouvrage:
            ouvrage = detail.equipement_constitutif.ouvrage
        if ouvrage:
            ouvrage_par_detail[detail.id] = ouvrage

    ouvrage_ids_concernes = {o.id for o in ouvrage_par_detail.values()}
    commune_par_ouvrage = {}
    if ouvrage_ids_concernes:
        for pe in PointEau.objects.filter(
            ouvrage_id__in=ouvrage_ids_concernes,
            parcelle__isnull=False,
            parcelle__village__isnull=False,
            parcelle__village__fokontany__isnull=False,
            parcelle__village__fokontany__commune__isnull=False
        ).select_related('parcelle__village__fokontany__commune').defer('photos').order_by('ouvrage_id'):
            commune_par_ouvrage.setdefault(pe.ouvrage_id, pe.parcelle.village.fokontany.commune)

    # Grouper par ouvrage et calculer les statuts/gradings
    ouvrages_data = {}
    today = timezone.now().date()

    for detail in details_list:
        ouvrage = ouvrage_par_detail.get(detail.id)
        if not ouvrage:
            continue

        if ouvrage.id not in ouvrages_data:
            ouvrages_data[ouvrage.id] = {
                'ouvrage': ouvrage,
                'commune': commune_par_ouvrage.get(ouvrage.id),
                'reparations_passe': set(),  # Utiliser des sets pour éviter les doublons de planning_id
                'reparations_futur': set(),
                'rehabilitations_passe': set(),
                'rehabilitations_futur': set(),
                'pannes_passe': set(),
                'pannes_futur': set(),
                'reparations_ouvertes': set(),
                'rehabilitations_ouvertes': set(),
                'pannes_ouvertes': set(),
                'details': [],
                'durees': []  # Liste des durées pour calculer moyenne/médiane
            }

        # Ajouter le détail
        ouvrages_data[ouvrage.id]['details'].append(detail)

        # Calculer la durée si date de réparation existe
        if detail.planning and detail.planning.date:
            date_reparation_aware = detail.planning.date

            # Convertir en timezone Madagascar
            if date_reparation_aware.tzinfo:
                date_reparation_mg = date_reparation_aware.astimezone(tz_madagascar)
            else:
                date_reparation_mg = tz_madagascar.localize(date_reparation_aware)

            date_reparation = date_reparation_mg.date()

            # Préparer la date de signalement (convertir en date si c'est un datetime)
            if detail.planning.datesignalementactivite:
                date_signalement_raw = detail.planning.datesignalementactivite
                # Convertir en date si c'est un datetime
                if hasattr(date_signalement_raw, 'date'):
                    date_signalement = date_signalement_raw.date()
                else:
                    date_signalement = date_signalement_raw

                # Vérifier la cohérence (signalement <= réparation)
                if date_signalement > date_reparation:
                    date_signalement = date_reparation  # Incohérence, durée = 0
            else:
                # Si pas de signalement, durée = 0
                date_signalement = date_reparation

            # Calculer la durée en jours
            duree_jours = (date_reparation - date_signalement).days
            if duree_jours > 0:  # Ignorer les durées négatives ou nulles
                ouvrages_data[ouvrage.id]['durees'].append(duree_jours)

        # Analyser le type d'activité
        if detail.planning and detail.planning.date:
            date_aware = detail.planning.date
            if date_aware.tzinfo:
                date_madagascar = date_aware.astimezone(tz_madagascar)
            else:
                date_madagascar = tz_madagascar.localize(date_aware)

            date_obj = date_madagascar.date()
            activite_nom = fiche_poste_to_activite_nom.get(
                detail.planning.fiche_poste_id, ''
            )
            classification = get_repair_classification(
                type_name=activite_nom,
                fiche_label=getattr(detail.planning.fiche_poste, 'tache', ''),
                remarque=getattr(detail.planning, 'remarque', ''),
            )

            is_passe = date_obj < today

            # Classifier l'activité (ajouter l'ID du planning pour éviter les doublons)
            planning_id = detail.planning.id

            if classification['is_panne']:
                if is_passe:
                    ouvrages_data[ouvrage.id]['pannes_passe'].add(planning_id)
                else:
                    ouvrages_data[ouvrage.id]['pannes_futur'].add(planning_id)

            if classification['family'] == 'rehabilitation':
                if is_passe:
                    ouvrages_data[ouvrage.id]['rehabilitations_passe'].add(planning_id)
                else:
                    ouvrages_data[ouvrage.id]['rehabilitations_futur'].add(planning_id)
            elif classification['family'] in ('reparation', 'panne'):
                if is_passe:
                    ouvrages_data[ouvrage.id]['reparations_passe'].add(planning_id)
                else:
                    ouvrages_data[ouvrage.id]['reparations_futur'].add(planning_id)

            if not detail.planning.estvalide:
                if classification['is_panne']:
                    ouvrages_data[ouvrage.id]['pannes_ouvertes'].add(planning_id)

                if classification['family'] == 'rehabilitation':
                    ouvrages_data[ouvrage.id]['rehabilitations_ouvertes'].add(planning_id)
                elif classification['family'] == 'reparation':
                    ouvrages_data[ouvrage.id]['reparations_ouvertes'].add(planning_id)

    # Calculer les statuts et gradings pour chaque ouvrage
    for ouvrage_id, data in ouvrages_data.items():
        # CALCUL DU STATUT (7 niveaux par ordre de priorité)
        if data['pannes_passe']:
            data['statut'] = 'reparation_panne_effectuee'
            data['statut_label'] = 'Réparation panne effectuée'
            data['statut_badge'] = 'success'
            data['statut_icon'] = 'check-circle'
        elif data['rehabilitations_passe']:
            data['statut'] = 'rehabilitation_effectuee'
            data['statut_label'] = 'Réhabilitation effectuée'
            data['statut_badge'] = 'info'
            data['statut_icon'] = 'tools'
        elif data['reparations_passe']:
            data['statut'] = 'reparation_effectuee'
            data['statut_label'] = 'Réparation effectuée'
            data['statut_badge'] = 'primary'
            data['statut_icon'] = 'wrench'
        elif data['pannes_futur']:
            data['statut'] = 'panne_prevue'
            data['statut_label'] = 'Panne Ã  réparer'
            data['statut_badge'] = 'error'
            data['statut_icon'] = 'exclamation-triangle'
        elif data['rehabilitations_futur']:
            data['statut'] = 'rehabilitation_prevue'
            data['statut_label'] = 'Réhabilitation prévue'
            data['statut_badge'] = 'warning'
            data['statut_icon'] = 'calendar-check'
        elif data['reparations_futur']:
            data['statut'] = 'reparation_prevue'
            data['statut_label'] = 'Réparation prévue'
            data['statut_badge'] = 'ghost'
            data['statut_icon'] = 'calendar'
        else:
            data['statut'] = 'sans_reparation'
            data['statut_label'] = 'Sans réparation'
            data['statut_badge'] = 'success'
            data['statut_icon'] = 'check-double'

        # CALCUL DU GRADING (5 niveaux par ordre de priorité)
        grading_info = get_repair_workflow_grading_from_flags(
            has_repair=bool(data['reparations_ouvertes']),
            has_rehab=bool(data['rehabilitations_ouvertes']),
            has_panne=bool(data['pannes_ouvertes']),
        )
        data['grading'] = grading_info['code']
        data['grading_label'] = grading_info['short_label']
        data['grading_badge'] = grading_info['badge']

    # Filtrer par statut si spécifié
    if statut_filter:
        ouvrages_data = {k: v for k, v in ouvrages_data.items() if v.get('statut') == statut_filter}

    # Filtrer par grading si spécifié
    if grading_filter:
        ouvrages_data = {k: v for k, v in ouvrages_data.items() if v.get('grading') == grading_filter}

    # Filtrer par organisation via modalités de gestion actives
    ouvrages_org_ids = _get_user_scoped_ouvrage_ids(
        organisation_id,
        gestionnaire_ids,
        request.user,
        annee=annee_int,
    )
    if organisation_id or gestionnaire_ids is not None:
        ouvrages_data = {k: v for k, v in ouvrages_data.items() if k in ouvrages_org_ids}

    # Calculer les durées moyennes et médianes
    all_durees = []
    for data in ouvrages_data.values():
        all_durees.extend(data.get('durees', []))

    duree_moyenne = round(statistics.mean(all_durees), 1) if all_durees else 0
    duree_mediane = round(statistics.median(all_durees), 1) if all_durees else 0

    # Compter les réparations/réhabilitations/pannes (passé/futur)
    total_reparations_passe = sum(len(d.get('reparations_passe', set())) for d in ouvrages_data.values())
    total_reparations_futur = sum(len(d.get('reparations_futur', set())) for d in ouvrages_data.values())
    total_rehabilitations_passe = sum(len(d.get('rehabilitations_passe', set())) for d in ouvrages_data.values())
    total_rehabilitations_futur = sum(len(d.get('rehabilitations_futur', set())) for d in ouvrages_data.values())
    total_pannes_passe = sum(len(d.get('pannes_passe', set())) for d in ouvrages_data.values())
    total_pannes_futur = sum(len(d.get('pannes_futur', set())) for d in ouvrages_data.values())

    # Calculer les statistiques
    total_ouvrages = len(ouvrages_data)
    grade_a = len([d for d in ouvrages_data.values() if d.get('grading') == 'A'])
    grade_b = len([d for d in ouvrages_data.values() if d.get('grading') == 'B'])
    grade_b_panne = len([d for d in ouvrages_data.values() if d.get('grading') == 'B_panne'])
    grade_d = len([d for d in ouvrages_data.values() if d.get('grading') == 'D'])
    grade_d_panne = len([d for d in ouvrages_data.values() if d.get('grading') == 'D_panne'])

    stats = {
        'total_ouvrages': total_ouvrages,
        'grade_a': grade_a,
        'grade_b': grade_b,
        'grade_b_panne': grade_b_panne,
        'grade_d': grade_d,
        'grade_d_panne': grade_d_panne,
        'grade_a_pct': int(round(grade_a / total_ouvrages * 100)) if total_ouvrages > 0 else 0,
        'grade_b_pct': int(round(grade_b / total_ouvrages * 100)) if total_ouvrages > 0 else 0,
        'grade_b_panne_pct': int(round(grade_b_panne / total_ouvrages * 100)) if total_ouvrages > 0 else 0,
        'grade_d_pct': int(round(grade_d / total_ouvrages * 100)) if total_ouvrages > 0 else 0,
        'grade_d_panne_pct': int(round(grade_d_panne / total_ouvrages * 100)) if total_ouvrages > 0 else 0,
        'statut_panne_effectuee': len([d for d in ouvrages_data.values() if d.get('statut') == 'reparation_panne_effectuee']),
        'statut_rehabilitation_effectuee': len([d for d in ouvrages_data.values() if d.get('statut') == 'rehabilitation_effectuee']),
        'statut_reparation_effectuee': len([d for d in ouvrages_data.values() if d.get('statut') == 'reparation_effectuee']),
        'statut_panne_prevue': len([d for d in ouvrages_data.values() if d.get('statut') == 'panne_prevue']),
        'statut_rehabilitation_prevue': len([d for d in ouvrages_data.values() if d.get('statut') == 'rehabilitation_prevue']),
        'statut_reparation_prevue': len([d for d in ouvrages_data.values() if d.get('statut') == 'reparation_prevue']),
        'statut_sans_reparation': len([d for d in ouvrages_data.values() if d.get('statut') == 'sans_reparation']),
        'duree_moyenne': duree_moyenne,
        'duree_mediane': duree_mediane,
        'nb_reparations_avec_duree': len(all_durees),
        'total_reparations_passe': total_reparations_passe,
        'total_reparations_futur': total_reparations_futur,
        'total_rehabilitations_passe': total_rehabilitations_passe,
        'total_rehabilitations_futur': total_rehabilitations_futur,
        'total_pannes_passe': total_pannes_passe,
        'total_pannes_futur': total_pannes_futur,
    }

    # Listes pour les dropdowns
    communes_qs = Commune.objects.filter(
        fokontanys__villages__parcelles__pointeau__ouvrage__isnull=False
    )
    ouvrages_qs = Ouvrage.objects.all()
    if organisation_id or gestionnaire_ids is not None:
        communes_qs = communes_qs.filter(
            fokontanys__villages__parcelles__pointeau__ouvrage_id__in=ouvrages_org_ids
        )
        ouvrages_qs = ouvrages_qs.filter(id__in=ouvrages_org_ids)

    communes = communes_qs.distinct().order_by('nom_commune')
    ouvrages = ouvrages_qs.distinct().order_by('nom_ouvrage')

    # Générer la liste des années disponibles
    annees_disponibles = list(range(2020, annee_courante + 2))

    # Pagination
    from django.core.paginator import Paginator
    ouvrages_list = list(ouvrages_data.values())
    page_number = request.GET.get('page', 1)
    paginator = Paginator(ouvrages_list, 50)
    page_obj = paginator.get_page(page_number)

    context = {
        'ouvrages_data': page_obj.object_list,
        'page_obj': page_obj,
        'stats': stats,
        'communes': communes,
        'ouvrages': ouvrages,
        'organisations': organisations,
        'show_organisation_filter': show_organisation_filter,
        'default_organisation_filter': default_org_id,
        'annees_disponibles': annees_disponibles,
        'annee_filter': annee_filter,
        'organisation_filter': organisation_id,
        'commune_filter': commune_id,
        'ouvrage_filter': ouvrage_id,
        'statut_filter': statut_filter,
        'grading_filter': grading_filter,
        'activite_filter': activite_filter,
        'date_debut': date_debut,
        'date_fin': date_fin,
    }

    # fiches_reparation deja calcule plus haut (meme tri) : reutilise pour le modal,
    # evite une 2e requete + reclassification identique.

    # Alimenter le modal avec les employes de meme base et les responsables des ouvrages du perimetre
    employes = _get_repair_modal_employees_queryset(
        request.user,
        ouvrage_ids=ouvrages_org_ids,
    ).order_by('surnom', 'nom', 'prenom')
    designations = Designation.objects.select_related('type_designation').order_by('nom')
    designations_avance = _filter_designations_avance(designations)
    designations_bon_livraison = _filter_designations_bon_livraison(designations)
    magasins = Magasin.objects.select_related('base').all().order_by('nom_magasin')
    # Listes des modals : le gabarit n'utilise que l'id, le nom et l'ouvrage. Charger les objets
    # complets ramenait toutes les photos base64 (~430 Mo pour 3 500 points + 690 équipements).
    point_eaux = PointEau.objects.only('id', 'nomabonne', 'code_point_eau', 'ouvrage').order_by('id')
    equipements = EquipementConstitutif.objects.only('id', 'nom', 'ouvrage').order_by('nom')

    # Ajouter au contexte
    context['fiches_reparation'] = fiches_reparation
    context['employes'] = employes
    context['employes_groupes'] = _group_employes_par_base_poste(employes)
    context['designations'] = designations
    context['designations_avance'] = designations_avance
    context['designations_bon_livraison'] = designations_bon_livraison
    context['magasins'] = magasins
    context['point_eaux'] = point_eaux
    context['equipements'] = equipements

    context['peut_supprimer_reparations'] = bool(
        getattr(request.user, 'is_superuser', False) or is_directeur_poste(request.user)
    )
    return render(request, 'planning/suivi_reparations.html', context)


@login_required
def suivi_reparations_kanban(request):
    """Vue Kanban du suivi des réparations groupées par grading"""

    # Timezone Madagascar
    tz_madagascar = pytz.timezone('Indian/Antananarivo')

    # Masquer le filtre organisation (filtrage automatique par défaut)
    gestionnaire_ids, organisations = _get_scoped_organisations_for_user(request.user)
    default_org_id = _get_default_repair_organisation_id(request.user, gestionnaire_ids)
    show_organisation_filter = False

    # Récupérer les filtres
    annee_courante = datetime.now().year
    annee_filter = request.GET.get('annee', str(annee_courante))
    organisation_id = request.GET.get('organisation', default_org_id) or default_org_id
    if organisation_id == 'all':
        organisation_id = default_org_id
    if organisation_id != 'all' and gestionnaire_ids is not None:
        allowed_ids = {str(_id) for _id in gestionnaire_ids}
        if organisation_id not in allowed_ids:
            organisation_id = default_org_id
    commune_id = request.GET.get('commune', '')
    ouvrage_id = request.GET.get('ouvrage', '')
    statut_filter = request.GET.get('statut', '')
    grading_filter = request.GET.get('grading', '')

    fiches_reparation = list(get_reparations_fiches_queryset().order_by('type_activites__nomtype', 'ordre', 'tache'))
    fiche_poste_ids = [fiche.id for fiche in fiches_reparation]
    fiche_poste_to_activite_nom = {
        fiche.id: f"{getattr(getattr(fiche, 'type_activites', None), 'nomtype', '') or ''} {fiche.tache or ''}".strip()
        for fiche in fiches_reparation
    }

    # Récupérer les détails de planning avec ces activités
    details = PlanningDetail.objects.filter(
        planning__fiche_poste_id__in=fiche_poste_ids
    ).select_related(
        'planning',
        'planning__fiche_poste',
        'planning__employe',
        'planning__ouvrage',
        'point_eau',
        'point_eau__ouvrage',
        'point_eau__parcelle__village__fokontany__commune',
        'equipement_constitutif',
        'equipement_constitutif__ouvrage'
    ).defer(
        # Photos en base64 (jusqu'à 40 Mo par ligne) non utilisées par cette page, qui les charge
        # à la demande par API : sans defer, ~1 Go de RAM par affichage (select_related les
        # dupliquait pour chaque détail).
        'planning__photo', 'point_eau__photos', 'equipement_constitutif__photos',
    )

    # Appliquer les filtres géographiques
    if commune_id:
        details = details.filter(
            Q(point_eau__parcelle__village__fokontany__commune_id=commune_id) |
            Q(equipement_constitutif__ouvrage__id__in=PointEau.objects.filter(
                parcelle__village__fokontany__commune_id=commune_id
            ).values_list('ouvrage_id', flat=True))
        )

    if ouvrage_id:
        details = details.filter(
            Q(planning__ouvrage_id=ouvrage_id) |
            Q(point_eau__ouvrage_id=ouvrage_id) |
            Q(equipement_constitutif__ouvrage_id=ouvrage_id)
        )

    annee_int = int(annee_filter) if annee_filter else annee_courante

    # Pré-filtre SQL borné sur l'année Madagascar (voir suivi_reparations ci-dessus
    # pour le detail : plage sur le datetime complet, pas d'extraction de date en SQL).
    annee_debut_mg = tz_madagascar.localize(datetime(annee_int, 1, 1))
    annee_fin_mg = tz_madagascar.localize(datetime(annee_int + 1, 1, 1))
    details = details.filter(planning__date__gte=annee_debut_mg, planning__date__lt=annee_fin_mg)

    # Convertir en liste et filtrer par année (conversion timezone précise, jour par jour)
    details_list = list(details.order_by('-planning__date'))

    # Filtrer par année en Python avec conversion timezone
    details_filtered = []
    for detail in details_list:
        if detail.planning and detail.planning.date:
            date_aware = detail.planning.date
            if date_aware.tzinfo:
                date_madagascar = date_aware.astimezone(tz_madagascar)
            else:
                date_madagascar = tz_madagascar.localize(date_aware)

            date_obj = date_madagascar.date()

            if date_obj.year == annee_int:
                details_filtered.append(detail)

    details_list = details_filtered

    # Déterminer l'ouvrage de chaque détail une seule fois, puis pré-charger les
    # communes de tous les ouvrages concernés en une seule requête groupée
    # (au lieu d'une requête par ouvrage distinct dans la boucle -> N+1).
    ouvrage_par_detail = {}
    for detail in details_list:
        ouvrage = None
        if detail.planning and detail.planning.ouvrage:
            ouvrage = detail.planning.ouvrage
        elif detail.point_eau and detail.point_eau.ouvrage:
            ouvrage = detail.point_eau.ouvrage
        elif detail.equipement_constitutif and detail.equipement_constitutif.ouvrage:
            ouvrage = detail.equipement_constitutif.ouvrage
        if ouvrage:
            ouvrage_par_detail[detail.id] = ouvrage

    ouvrage_ids_concernes = {o.id for o in ouvrage_par_detail.values()}
    commune_par_ouvrage = {}
    if ouvrage_ids_concernes:
        for pe in PointEau.objects.filter(
            ouvrage_id__in=ouvrage_ids_concernes,
            parcelle__isnull=False,
            parcelle__village__isnull=False,
            parcelle__village__fokontany__isnull=False,
            parcelle__village__fokontany__commune__isnull=False
        ).select_related('parcelle__village__fokontany__commune').defer('photos').order_by('ouvrage_id'):
            commune_par_ouvrage.setdefault(pe.ouvrage_id, pe.parcelle.village.fokontany.commune)

    # Grouper par ouvrage et calculer les statuts/gradings
    ouvrages_data = {}
    today = timezone.now().date()

    for detail in details_list:
        ouvrage = ouvrage_par_detail.get(detail.id)
        if not ouvrage:
            continue

        if ouvrage.id not in ouvrages_data:
            ouvrages_data[ouvrage.id] = {
                'ouvrage': ouvrage,
                'commune': commune_par_ouvrage.get(ouvrage.id),
                'reparations_passe': set(),  # Utiliser des sets pour éviter les doublons de planning_id
                'reparations_futur': set(),
                'rehabilitations_passe': set(),
                'rehabilitations_futur': set(),
                'pannes_passe': set(),
                'pannes_futur': set(),
                'reparations_ouvertes': set(),
                'rehabilitations_ouvertes': set(),
                'pannes_ouvertes': set(),
                'details': [],
                'durees': []  # Liste des durées pour calculer moyenne/médiane
            }

        # Ajouter le détail
        ouvrages_data[ouvrage.id]['details'].append(detail)

        # Calculer la durée si date de réparation existe
        if detail.planning and detail.planning.date:
            date_reparation_aware = detail.planning.date

            # Convertir en timezone Madagascar
            if date_reparation_aware.tzinfo:
                date_reparation_mg = date_reparation_aware.astimezone(tz_madagascar)
            else:
                date_reparation_mg = tz_madagascar.localize(date_reparation_aware)

            date_reparation = date_reparation_mg.date()

            # Préparer la date de signalement (convertir en date si c'est un datetime)
            if detail.planning.datesignalementactivite:
                date_signalement_raw = detail.planning.datesignalementactivite
                # Convertir en date si c'est un datetime
                if hasattr(date_signalement_raw, 'date'):
                    date_signalement = date_signalement_raw.date()
                else:
                    date_signalement = date_signalement_raw

                # Vérifier la cohérence (signalement <= réparation)
                if date_signalement > date_reparation:
                    date_signalement = date_reparation  # Incohérence, durée = 0
            else:
                # Si pas de signalement, durée = 0
                date_signalement = date_reparation

            # Calculer la durée en jours
            duree_jours = (date_reparation - date_signalement).days
            if duree_jours > 0:  # Ignorer les durées négatives ou nulles
                ouvrages_data[ouvrage.id]['durees'].append(duree_jours)

        # Analyser le type d'activité
        if detail.planning and detail.planning.date:
            date_aware = detail.planning.date
            if date_aware.tzinfo:
                date_madagascar = date_aware.astimezone(tz_madagascar)
            else:
                date_madagascar = tz_madagascar.localize(date_aware)

            date_obj = date_madagascar.date()
            activite_nom = fiche_poste_to_activite_nom.get(
                detail.planning.fiche_poste_id, ''
            )
            classification = get_repair_classification(
                type_name=activite_nom,
                fiche_label=getattr(detail.planning.fiche_poste, 'tache', ''),
                remarque=getattr(detail.planning, 'remarque', ''),
            )

            is_passe = date_obj < today

            # Classifier l'activité (ajouter l'ID du planning pour éviter les doublons)
            planning_id = detail.planning.id

            if classification['is_panne']:
                if is_passe:
                    ouvrages_data[ouvrage.id]['pannes_passe'].add(planning_id)
                else:
                    ouvrages_data[ouvrage.id]['pannes_futur'].add(planning_id)

            if classification['family'] == 'rehabilitation':
                if is_passe:
                    ouvrages_data[ouvrage.id]['rehabilitations_passe'].add(planning_id)
                else:
                    ouvrages_data[ouvrage.id]['rehabilitations_futur'].add(planning_id)
            elif classification['family'] in ('reparation', 'panne'):
                if is_passe:
                    ouvrages_data[ouvrage.id]['reparations_passe'].add(planning_id)
                else:
                    ouvrages_data[ouvrage.id]['reparations_futur'].add(planning_id)

            if not detail.planning.estvalide:
                if classification['is_panne']:
                    ouvrages_data[ouvrage.id]['pannes_ouvertes'].add(planning_id)

                if classification['family'] == 'rehabilitation':
                    ouvrages_data[ouvrage.id]['rehabilitations_ouvertes'].add(planning_id)
                elif classification['family'] == 'reparation':
                    ouvrages_data[ouvrage.id]['reparations_ouvertes'].add(planning_id)

    # Calculer les statuts et gradings pour chaque ouvrage
    for ouvrage_id, data in ouvrages_data.items():
        # CALCUL DU STATUT (7 niveaux par ordre de priorité)
        if data['pannes_passe']:
            data['statut'] = 'reparation_panne_effectuee'
            data['statut_label'] = 'Réparation panne effectuée'
            data['statut_badge'] = 'success'
            data['statut_icon'] = 'check-circle'
        elif data['rehabilitations_passe']:
            data['statut'] = 'rehabilitation_effectuee'
            data['statut_label'] = 'Réhabilitation effectuée'
            data['statut_badge'] = 'info'
            data['statut_icon'] = 'tools'
        elif data['reparations_passe']:
            data['statut'] = 'reparation_effectuee'
            data['statut_label'] = 'Réparation effectuée'
            data['statut_badge'] = 'primary'
            data['statut_icon'] = 'wrench'
        elif data['pannes_futur']:
            data['statut'] = 'panne_prevue'
            data['statut_label'] = 'Panne Ã  réparer'
            data['statut_badge'] = 'error'
            data['statut_icon'] = 'exclamation-triangle'
        elif data['rehabilitations_futur']:
            data['statut'] = 'rehabilitation_prevue'
            data['statut_label'] = 'Réhabilitation prévue'
            data['statut_badge'] = 'warning'
            data['statut_icon'] = 'calendar-check'
        elif data['reparations_futur']:
            data['statut'] = 'reparation_prevue'
            data['statut_label'] = 'Réparation prévue'
            data['statut_badge'] = 'ghost'
            data['statut_icon'] = 'calendar'
        else:
            data['statut'] = 'sans_reparation'
            data['statut_label'] = 'Sans réparation'
            data['statut_badge'] = 'success'
            data['statut_icon'] = 'check-double'

        # CALCUL DU GRADING (5 niveaux par ordre de priorité)
        grading_info = get_repair_workflow_grading_from_flags(
            has_repair=bool(data['reparations_ouvertes']),
            has_rehab=bool(data['rehabilitations_ouvertes']),
            has_panne=bool(data['pannes_ouvertes']),
        )
        data['grading'] = grading_info['code']
        data['grading_label'] = grading_info['short_label']
        data['grading_badge'] = grading_info['badge']

    # Filtrer par statut si spécifié
    if statut_filter:
        ouvrages_data = {k: v for k, v in ouvrages_data.items() if v.get('statut') == statut_filter}

    # Filtrer par grading si spécifié
    if grading_filter:
        ouvrages_data = {k: v for k, v in ouvrages_data.items() if v.get('grading') == grading_filter}

    # Filtrer par organisation via modalités de gestion actives
    ouvrages_org_ids = _get_user_scoped_ouvrage_ids(
        organisation_id,
        gestionnaire_ids,
        request.user,
        annee=annee_int,
    )
    if organisation_id or gestionnaire_ids is not None:
        ouvrages_data = {k: v for k, v in ouvrages_data.items() if k in ouvrages_org_ids}

    # Calculer les durées moyennes et médianes
    all_durees = []
    for data in ouvrages_data.values():
        all_durees.extend(data.get('durees', []))

    duree_moyenne = round(statistics.mean(all_durees), 1) if all_durees else 0
    duree_mediane = round(statistics.median(all_durees), 1) if all_durees else 0

    # Compter les réparations/réhabilitations/pannes (passé/futur)
    total_reparations_passe = sum(len(d.get('reparations_passe', set())) for d in ouvrages_data.values())
    total_reparations_futur = sum(len(d.get('reparations_futur', set())) for d in ouvrages_data.values())
    total_rehabilitations_passe = sum(len(d.get('rehabilitations_passe', set())) for d in ouvrages_data.values())
    total_rehabilitations_futur = sum(len(d.get('rehabilitations_futur', set())) for d in ouvrages_data.values())
    total_pannes_passe = sum(len(d.get('pannes_passe', set())) for d in ouvrages_data.values())
    total_pannes_futur = sum(len(d.get('pannes_futur', set())) for d in ouvrages_data.values())

    # Calculer les statistiques
    total_ouvrages = len(ouvrages_data)
    grade_a = len([d for d in ouvrages_data.values() if d.get('grading') == 'A'])
    grade_b = len([d for d in ouvrages_data.values() if d.get('grading') == 'B'])
    grade_b_panne = len([d for d in ouvrages_data.values() if d.get('grading') == 'B_panne'])
    grade_d = len([d for d in ouvrages_data.values() if d.get('grading') == 'D'])
    grade_d_panne = len([d for d in ouvrages_data.values() if d.get('grading') == 'D_panne'])

    stats = {
        'total_ouvrages': total_ouvrages,
        'grade_a': grade_a,
        'grade_b': grade_b,
        'grade_b_panne': grade_b_panne,
        'grade_d': grade_d,
        'grade_d_panne': grade_d_panne,
        'grade_a_pct': int(round(grade_a / total_ouvrages * 100)) if total_ouvrages > 0 else 0,
        'grade_b_pct': int(round(grade_b / total_ouvrages * 100)) if total_ouvrages > 0 else 0,
        'grade_b_panne_pct': int(round(grade_b_panne / total_ouvrages * 100)) if total_ouvrages > 0 else 0,
        'grade_d_pct': int(round(grade_d / total_ouvrages * 100)) if total_ouvrages > 0 else 0,
        'grade_d_panne_pct': int(round(grade_d_panne / total_ouvrages * 100)) if total_ouvrages > 0 else 0,
        'duree_moyenne': duree_moyenne,
        'duree_mediane': duree_mediane,
        'nb_reparations_avec_duree': len(all_durees),
        'total_reparations_passe': total_reparations_passe,
        'total_reparations_futur': total_reparations_futur,
        'total_rehabilitations_passe': total_rehabilitations_passe,
        'total_rehabilitations_futur': total_rehabilitations_futur,
        'total_pannes_passe': total_pannes_passe,
        'total_pannes_futur': total_pannes_futur,
    }

    # Listes pour les dropdowns
    from apps.geography.models import Region, District

    regions = Region.objects.filter(
        districts__communes__fokontanys__villages__parcelles__pointeau__ouvrage__isnull=False
    ).distinct().order_by('nom_region')

    districts = District.objects.filter(
        communes__fokontanys__villages__parcelles__pointeau__ouvrage__isnull=False
    ).distinct().order_by('nom_district')

    communes_qs = Commune.objects.filter(
        fokontanys__villages__parcelles__pointeau__ouvrage__isnull=False
    )
    ouvrages_qs = Ouvrage.objects.all()
    if organisation_id or gestionnaire_ids is not None:
        communes_qs = communes_qs.filter(
            fokontanys__villages__parcelles__pointeau__ouvrage_id__in=ouvrages_org_ids
        )
        ouvrages_qs = ouvrages_qs.filter(id__in=ouvrages_org_ids)

    communes = communes_qs.distinct().order_by('nom_commune')
    ouvrages = ouvrages_qs.distinct().order_by('nom_ouvrage')

    # Générer la liste des années disponibles
    annees_disponibles = list(range(2020, annee_courante + 2))

    # Grouper par grading pour le Kanban (sans pagination)
    ouvrages_par_grading = {
        'A': [d for d in ouvrages_data.values() if d.get('grading') == 'A'],
        'B': [d for d in ouvrages_data.values() if d.get('grading') == 'B'],
        'B_panne': [d for d in ouvrages_data.values() if d.get('grading') == 'B_panne'],
        'D': [d for d in ouvrages_data.values() if d.get('grading') == 'D'],
        'D_panne': [d for d in ouvrages_data.values() if d.get('grading') == 'D_panne'],
    }

    # Ajouter la liste des grades pour l'affichage
    grades_list = [
        ('A', 'Grading A'),
        ('B', 'Grading B'),
        ('B_panne', 'Grading B - Panne'),
        ('D', 'Grading D'),
        ('D_panne', 'Grading D - Panne'),
    ]

    # fiches_reparation deja calcule plus haut (meme tri) : reutilise pour le modal,
    # evite une 2e requete + reclassification identique.

    # Alimenter le modal avec les employes de meme base et les responsables des ouvrages du perimetre
    employes = _get_repair_modal_employees_queryset(
        request.user,
        ouvrage_ids=ouvrages.values_list('id', flat=True),
    ).order_by('surnom', 'nom', 'prenom')
    designations = Designation.objects.select_related('type_designation').order_by('nom')
    designations_avance = _filter_designations_avance(designations)
    designations_bon_livraison = _filter_designations_bon_livraison(designations)
    magasins = Magasin.objects.select_related('base').all().order_by('nom_magasin')

    context = {
        'ouvrages_par_grading': ouvrages_par_grading,
        'stats': stats,
        'regions': regions,
        'districts': districts,
        'communes': communes,
        'ouvrages': ouvrages,
        'organisations': organisations,
        'show_organisation_filter': show_organisation_filter,
        'default_organisation_filter': default_org_id,
        'annees_disponibles': annees_disponibles,
        'annee_filter': annee_filter,
        'organisation_filter': organisation_id,
        'commune_filter': commune_id,
        'ouvrage_filter': ouvrage_id,
        'statut_filter': statut_filter,
        'grading_filter': grading_filter,
        'grades_list': grades_list,
        'fiches_reparation': fiches_reparation,
        'employes': employes,
        'employes_groupes': _group_employes_par_base_poste(employes),
        'designations': designations,
        'designations_avance': designations_avance,
        'designations_bon_livraison': designations_bon_livraison,
        'magasins': magasins,
    }

    context['peut_supprimer_reparations'] = bool(
        getattr(request.user, 'is_superuser', False) or is_directeur_poste(request.user)
    )
    return render(request, 'planning/suivi_reparations.html', context)
