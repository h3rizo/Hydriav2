from collections import defaultdict
import unicodedata

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db import models
from django.http import JsonResponse
from django.http import HttpResponse
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Count, Q, Min, Max, Avg, Prefetch
from django.db.models.functions import TruncDate
from datetime import datetime, timedelta
from django.utils import timezone
from .models import Poste, Employe, Contrat, GrilleSalaire, Salaire, PositionGPSEmploye, HierarchieEmploye, EmployeOuvrages
from .forms import (
    PosteForm,
    EmployeForm,
    ContratForm,
    GrilleSalaireForm,
    SalaireForm,
    HierarchieEmployeForm,
    EmployeOuvrageForm,
)
from .permissions import employe_required, is_directeur_poste
from .salary_consistency import (
    expected_salaire_values_from_grille,
    refresh_grille_calculs,
    sync_salaire_with_grille,
)
from .views_config_salaire import _compute_simulation_snapshot, _pick_best_integer_gross, _solve_gross_from_net_exact
from apps.organization.models import Base, Ouvrage
from apps.billing.models import PointEau, ModaliteGestion
from apps.infrastructure.models import EquipementConstitutif
from openpyxl import Workbook


def _get_user_organisation(user):
    if hasattr(user, 'employe') and user.employe and user.employe.base:
        return user.employe.base.organisation
    return None


def _normalize_sort_text(value):
    normalized = unicodedata.normalize('NFKD', str(value or ''))
    return normalized.encode('ascii', errors='ignore').decode('ascii').lower().strip()


def _filter_postes_by_scope(queryset, user):
    if getattr(user, 'is_superuser', False):
        return queryset
    user_organisation = _get_user_organisation(user)
    if not user_organisation:
        return queryset.none()
    return queryset.filter(organisation=user_organisation)


def _scope_organigramme_queryset(queryset, user, organisation_id=None):
    """
    Périmètre de l'organigramme : l'organisation de l'utilisateur par défaut, avec bascule pour les
    superusers et les partenaires. Les endpoints qui ciblent un seul employé (fiche, modale) passent
    organisation_id='all' pour accepter toute organisation du périmètre de l'utilisateur.
    Retourne (queryset, organisation affichée ou None).
    """
    from apps.organization.scoping import apply_employee_organisation_scope, resolve_employee_organisation_scope
    scope = resolve_employee_organisation_scope(user, organisation_id or '')
    return apply_employee_organisation_scope(queryset, scope), scope['organisation']


def _filter_active_employes_queryset(queryset):
    return queryset.filter(date_debauchage__isnull=True)


def _is_simplified_organigramme_poste(poste_nom):
    return _normalize_sort_text(poste_nom) == _normalize_sort_text('Mpikojakoja ifotony')


def _base_color_for_key(base_key):
    palette = [
        ('#dbeafe', '#1d4ed8', '#eff6ff'),
        ('#dcfce7', '#15803d', '#f0fdf4'),
        ('#fef3c7', '#b45309', '#fffbeb'),
        ('#ede9fe', '#6d28d9', '#f5f3ff'),
        ('#fee2e2', '#dc2626', '#fef2f2'),
        ('#cffafe', '#0e7490', '#ecfeff'),
        ('#e2e8f0', '#334155', '#f8fafc'),
        ('#fce7f3', '#be185d', '#fff1f2'),
    ]
    idx = sum(ord(ch) for ch in str(base_key or '')) % len(palette)
    return palette[idx]


def _get_fiche_paie_planning_details(employe, reference_date):
    from datetime import date as dt_date
    from apps.employees.models_conges import JourFerie
    from apps.planning.models import Planning

    if not employe or not reference_date:
        return {'dimanches': [], 'jours_feries': []}

    periode = reference_date if isinstance(reference_date, dt_date) else reference_date.date()
    holiday_dates = set(
        JourFerie.objects.filter(
            actif=True,
            date__year=periode.year,
            date__month=periode.month,
        ).values_list('date', flat=True)
    )

    plannings = (
        Planning.objects.filter(
            date__year=periode.year,
            date__month=periode.month,
            ouvrage__isnull=False,
        )
        .filter(
            Q(employe_id=employe.id) |
            Q(planning_employees__employee_id=employe.id)
        )
        .select_related('ouvrage', 'fiche_poste', 'type_activite')
        .distinct()
        .order_by('date', 'ouvrage__nom_ouvrage')
    )

    details = {'dimanches': [], 'jours_feries': []}

    for planning in plannings:
        planning_date = planning.date.date() if planning.date else None
        if not planning_date:
            continue

        activite_label = (
            getattr(getattr(planning, 'fiche_poste', None), 'tache', '') or
            getattr(getattr(planning, 'type_activite', None), 'nomtype', '') or
            '-'
        )
        ouvrage_label = (
            getattr(getattr(planning, 'ouvrage', None), 'nom_ouvrage', '') or
            getattr(getattr(planning, 'ouvrage', None), 'infra_name', '') or
            getattr(getattr(planning, 'ouvrage', None), 'nom', '') or
            '-'
        )
        item = {
            'date': planning_date,
            'ouvrage': ouvrage_label,
            'activite': activite_label,
            'is_premier_mai': planning_date.month == 5 and planning_date.day == 1,
        }

        if planning_date in holiday_dates:
            details['jours_feries'].append(item)
        elif planning_date.weekday() == 6:
            details['dimanches'].append(item)

    return details


def _organigram_sort_key(node):
    return (
        (node.get('organisation_nom') or '').lower(),
        (node.get('base_nom') or '').lower(),
        (node.get('poste_nom') or '').lower(),
        (node.get('nom_affichage') or '').lower(),
    )


def _modalite_active_on_reference_date(modalite, reference_date):
    if not modalite or not reference_date:
        return False
    if getattr(modalite, 'statut', None) != 'actif':
        return False
    if modalite.date_debut and modalite.date_debut > reference_date:
        return False
    if modalite.date_fin and modalite.date_fin < reference_date:
        return False
    return True


def _format_modalite_reconciliation_summary(modalite, include_gestionnaire=True):
    if not modalite:
        return 'Aucune modalite'

    gestionnaire_nom = (
        modalite.gestionnaire.nom_organisation
        if include_gestionnaire and getattr(modalite, 'gestionnaire', None)
        else None
    )
    periode = []
    if modalite.date_debut:
        periode.append(f"debut {modalite.date_debut.strftime('%d/%m/%Y')}")
    if modalite.date_fin:
        periode.append(f"fin {modalite.date_fin.strftime('%d/%m/%Y')}")
    elif modalite.date_debut:
        periode.append('sans fin')
    statut_label = modalite.get_statut_display() if hasattr(modalite, 'get_statut_display') else (modalite.statut or '')

    parts = []
    if gestionnaire_nom:
        parts.append(gestionnaire_nom)
    if periode:
        parts.append(', '.join(periode))
    if statut_label:
        parts.append(statut_label)
    return ' | '.join(parts)


def _filter_employes_by_base(queryset, base_id):
    """Restreint à une base si l'identifiant fait partie des bases présentes dans le queryset."""
    base_id = str(base_id or '').strip()
    if not base_id:
        return queryset
    known_base_ids = {str(value) for value in queryset.values_list('base_id', flat=True).distinct() if value}
    if base_id not in known_base_ids:
        return queryset
    return queryset.filter(base_id=base_id)


def _build_organigramme_ouvrage_reconciliation(
    ouvrage_relations,
    organisation,
    reference_date,
    scope_ouvrage_ids=None,
):
    """
    scope_ouvrage_ids : si fourni (filtre par base), ouvrage_relations couvre toute l'organisation
    pour que les ouvrages affectés à d'autres bases ne ressortent pas comme sans responsable ;
    seuls les ouvrages hors affectation appartenant à ce périmètre sont listés.
    """
    displayed_ouvrage_ids = {
        relation.ouvrage_id
        for relation in ouvrage_relations
        if relation.ouvrage_id
    }

    empty_result = {
        'displayed_ouvrage_ids': displayed_ouvrage_ids,
        'active_organisation_ouvrage_ids': displayed_ouvrage_ids,
        'displayed_diagnostics': {},
        'extra_items': [],
        'missing_items': [],
    }
    if not organisation:
        return empty_result

    active_modalites_qs = ModaliteGestion.objects.filter(
        gestionnaire=organisation,
        statut='actif',
        date_debut__lte=reference_date,
    ).filter(
        Q(date_fin__isnull=True) | Q(date_fin__gte=reference_date)
    ).select_related(
        'gestionnaire',
        'ouvrage',
    ).order_by(
        'ouvrage_id',
        '-date_debut',
        '-updated_at',
    )
    active_org_by_ouvrage = {}
    for modalite in active_modalites_qs:
        active_org_by_ouvrage.setdefault(modalite.ouvrage_id, modalite)

    active_organisation_ouvrage_ids = set(active_org_by_ouvrage.keys())
    extra_ouvrage_ids = displayed_ouvrage_ids - active_organisation_ouvrage_ids
    if scope_ouvrage_ids is not None:
        extra_ouvrage_ids &= set(scope_ouvrage_ids)
    missing_ouvrage_ids = active_organisation_ouvrage_ids - displayed_ouvrage_ids
    relevant_ouvrage_ids = extra_ouvrage_ids | missing_ouvrage_ids

    if not relevant_ouvrage_ids:
        empty_result['active_organisation_ouvrage_ids'] = active_organisation_ouvrage_ids
        return empty_result

    latest_any_by_ouvrage = {}
    latest_org_by_ouvrage = {}

    latest_any_qs = ModaliteGestion.objects.filter(
        ouvrage_id__in=relevant_ouvrage_ids,
    ).select_related(
        'gestionnaire',
        'ouvrage',
    ).order_by(
        'ouvrage_id',
        '-date_debut',
        '-updated_at',
    )
    for modalite in latest_any_qs:
        latest_any_by_ouvrage.setdefault(modalite.ouvrage_id, modalite)

    latest_org_qs = ModaliteGestion.objects.filter(
        ouvrage_id__in=relevant_ouvrage_ids,
        gestionnaire=organisation,
    ).select_related(
        'gestionnaire',
        'ouvrage',
    ).order_by(
        'ouvrage_id',
        '-date_debut',
        '-updated_at',
    )
    for modalite in latest_org_qs:
        latest_org_by_ouvrage.setdefault(modalite.ouvrage_id, modalite)

    ouvrages_map = {
        ouvrage.id: ouvrage
        for ouvrage in Ouvrage.objects.filter(id__in=relevant_ouvrage_ids).order_by('nom_ouvrage')
    }

    responsables_by_ouvrage = defaultdict(list)
    for relation in ouvrage_relations:
        if relation.ouvrage_id not in extra_ouvrage_ids:
            continue
        responsable_nom = relation.employe.nom_affichage if relation.employe_id else ''
        if responsable_nom and responsable_nom not in responsables_by_ouvrage[relation.ouvrage_id]:
            responsables_by_ouvrage[relation.ouvrage_id].append(responsable_nom)

    displayed_diagnostics = {}
    extra_items = []
    for ouvrage_id in sorted(extra_ouvrage_ids, key=lambda oid: _normalize_sort_text(getattr(ouvrages_map.get(oid), 'nom_ouvrage', ''))):
        ouvrage = ouvrages_map.get(ouvrage_id)
        latest_any = latest_any_by_ouvrage.get(ouvrage_id)
        latest_org = latest_org_by_ouvrage.get(ouvrage_id)
        any_active = _modalite_active_on_reference_date(latest_any, reference_date)

        reason_short = f"Hors affectation active {organisation.nom_organisation}"
        if latest_org and latest_org.date_fin:
            reason_detail = (
                f"Derniere modalite {organisation.nom_organisation} terminee le "
                f"{latest_org.date_fin.strftime('%d/%m/%Y')}."
            )
        elif latest_any and any_active and getattr(latest_any, 'gestionnaire_id', None) != organisation.id:
            other_org = latest_any.gestionnaire.nom_organisation if latest_any.gestionnaire else 'autre organisation'
            reason_detail = (
                f"Modalite active trouvee chez {other_org}, pas chez {organisation.nom_organisation}."
            )
        elif latest_any:
            reason_detail = (
                f"Aucune modalite active {organisation.nom_organisation}. "
                f"Derniere modalite connue: {_format_modalite_reconciliation_summary(latest_any)}."
            )
        else:
            reason_detail = f"Aucune modalite de gestion trouvee pour {organisation.nom_organisation}."

        item = {
            'ouvrage_id': ouvrage_id,
            'nom': ouvrage.nom_ouvrage if ouvrage else 'Ouvrage inconnu',
            'responsables': responsables_by_ouvrage.get(ouvrage_id, []),
            'reason_short': reason_short,
            'reason_detail': reason_detail,
            'last_org_summary': _format_modalite_reconciliation_summary(latest_org, include_gestionnaire=False),
            'last_any_summary': _format_modalite_reconciliation_summary(latest_any),
        }
        displayed_diagnostics[ouvrage_id] = item
        extra_items.append(item)

    missing_items = []
    for ouvrage_id in sorted(missing_ouvrage_ids, key=lambda oid: _normalize_sort_text(getattr(ouvrages_map.get(oid), 'nom_ouvrage', ''))):
        ouvrage = ouvrages_map.get(ouvrage_id)
        active_org = active_org_by_ouvrage.get(ouvrage_id)
        missing_items.append({
            'ouvrage_id': ouvrage_id,
            'nom': ouvrage.nom_ouvrage if ouvrage else 'Ouvrage inconnu',
            'reason_short': 'Aucun responsable actif visible',
            'reason_detail': (
                f"Modalite active {organisation.nom_organisation} sans employe actif rattache dans l organigramme."
            ),
            'active_org_summary': _format_modalite_reconciliation_summary(active_org, include_gestionnaire=False),
        })

    return {
        'displayed_ouvrage_ids': displayed_ouvrage_ids,
        'active_organisation_ouvrage_ids': active_organisation_ouvrage_ids,
        'displayed_diagnostics': displayed_diagnostics,
        'extra_items': extra_items,
        'missing_items': missing_items,
    }


def _build_organigramme_data(
    employes,
    hierarchies,
    ouvrage_relations,
    ouvrage_diagnostics=None,
    include_ouvrages=True,
):
    nodes = {}
    current_superiors = {}
    total_ouvrages_ids = set()
    ouvrage_ids = {relation.ouvrage_id for relation in ouvrage_relations if relation.ouvrage_id}
    ouvrage_communes = defaultdict(set)

    if ouvrage_ids:
        commune_rows = Ouvrage.objects.filter(id__in=ouvrage_ids).values(
            'id',
            'pointeau__parcelle__village__fokontany__commune__nom_commune',
        )
        for row in commune_rows:
            commune_nom = row['pointeau__parcelle__village__fokontany__commune__nom_commune']
            if commune_nom:
                ouvrage_communes[row['id']].add(commune_nom)

    for employe in employes:
        base_key = employe.base.nom_base if employe.base else 'Sans base'
        base_bg, base_fg, base_soft = _base_color_for_key(base_key)
        nodes[employe.id] = {
            'id': employe.id,
            'nom_complet': employe.nom_complet,
            'nom_affichage': employe.nom_affichage,
            'poste_nom': employe.poste.nom_poste if employe.poste else 'Sans poste',
            'base_nom': employe.base.nom_base if employe.base else 'Sans base',
            'organisation_nom': (
                employe.base.organisation.nom_organisation
                if employe.base and employe.base.organisation
                else 'Sans organisation'
            ),
            'telephone': employe.telephone,
            'mail': employe.mail,
            'base_color_bg': base_bg,
            'base_color_fg': base_fg,
            'base_color_soft': base_soft,
            'superieur_nom': None,
            'children': [],
            'ouvrages': [],
            'ouvrages_grouped': [],
            'ouvrages_count': 0,
            'is_root': False,
        }

    for relation in hierarchies:
        if relation.employe_id not in nodes or relation.employe_id in current_superiors:
            continue
        current_superiors[relation.employe_id] = relation.superieur_id

    if include_ouvrages:
        ouvrages_by_employe = defaultdict(list)
        for relation in ouvrage_relations:
            if relation.employe_id not in nodes:
                continue
            total_ouvrages_ids.add(relation.ouvrage_id)
            ouvrage_diagnostic = (ouvrage_diagnostics or {}).get(relation.ouvrage_id, {})
            commune_labels = sorted(
                ouvrage_communes.get(relation.ouvrage_id, set()),
                key=_normalize_sort_text,
            )
            ouvrages_by_employe[relation.employe_id].append({
                'id': relation.ouvrage_id,
                'nom': relation.ouvrage.nom_ouvrage if relation.ouvrage else 'Sans ouvrage',
                'type_ouvrage': (
                    relation.ouvrage.type_ouvrage.nom_type_ouvrage
                    if relation.ouvrage and relation.ouvrage.type_ouvrage
                    else ''
                ),
                'principal': relation.est_responsable_principal,
                'recevoir_alertes': relation.recevoir_alertes,
                'date_debut': relation.date_debut,
                'commune_label': ', '.join(commune_labels) if commune_labels else 'Sans commune',
                'hors_affectation_active': bool(ouvrage_diagnostic),
                'reconciliation_reason_short': ouvrage_diagnostic.get('reason_short', ''),
                'reconciliation_reason_detail': ouvrage_diagnostic.get('reason_detail', ''),
            })

        for employe_id, ouvrages in ouvrages_by_employe.items():
            ouvrages = sorted(
                ouvrages,
                key=lambda item: (
                    _normalize_sort_text(item.get('commune_label', '')),
                    not item['principal'],
                    _normalize_sort_text(item.get('nom', '')),
                )
            )
            grouped_ouvrages = []
            for ouvrage in ouvrages:
                if not grouped_ouvrages or grouped_ouvrages[-1]['commune_label'] != ouvrage['commune_label']:
                    grouped_ouvrages.append({
                        'commune_label': ouvrage['commune_label'],
                        'ouvrages': [],
                    })
                grouped_ouvrages[-1]['ouvrages'].append(ouvrage)

            nodes[employe_id]['ouvrages'] = ouvrages
            nodes[employe_id]['ouvrages_grouped'] = grouped_ouvrages
            nodes[employe_id]['ouvrages_count'] = len(ouvrages)

    roots = []
    for employe_id, node in nodes.items():
        superior_id = current_superiors.get(employe_id)
        if superior_id and superior_id in nodes and superior_id != employe_id:
            node['superieur_nom'] = nodes[superior_id]['nom_affichage']
            nodes[superior_id]['children'].append(node)
        else:
            node['is_root'] = True
            roots.append(node)

    def finalize_node(node, visited):
        node_id = node['id']
        if node_id in visited:
            return
        visited.add(node_id)
        unique_children = []
        seen_children = set()
        for child in node['children']:
            if child['id'] in seen_children:
                continue
            seen_children.add(child['id'])
            unique_children.append(child)
        unique_children.sort(key=_organigram_sort_key)
        node['children'] = unique_children
        node['subordinates_count'] = len(unique_children)
        for child in unique_children:
            finalize_node(child, visited)

    roots.sort(key=_organigram_sort_key)
    visited = set()
    for root in roots:
        finalize_node(root, visited)

    remaining_nodes = sorted(
        [node for node in nodes.values() if node['id'] not in visited],
        key=_organigram_sort_key,
    )
    for node in remaining_nodes:
        node['is_root'] = True
        roots.append(node)
        finalize_node(node, visited)

    roots.sort(key=_organigram_sort_key)

    stats = {
        'total_employes': len(nodes),
        'total_relations_hierarchiques': sum(
            1 for superior_id in current_superiors.values() if superior_id in nodes
        ),
        'total_ouvrages': len(total_ouvrages_ids) if include_ouvrages else 0,
        'total_responsables_ouvrages': sum(
            1 for node in nodes.values() if node['ouvrages_count'] > 0
        ),
        'total_racines': len(roots),
    }
    return roots, stats


def _flatten_organigramme_nodes(nodes, depth=0):
    flat_nodes = []
    for node in nodes:
        flat_nodes.append({
            'id': node['id'],
            'nom_affichage': node['nom_affichage'],
            'poste_nom': node['poste_nom'],
            'base_nom': node['base_nom'],
            'organisation_nom': node['organisation_nom'],
            'subordinates_count': node.get('subordinates_count', 0),
            'ouvrages_count': node.get('ouvrages_count', 0),
            'is_root': node.get('is_root', False),
            'depth': depth,
        })
        flat_nodes.extend(_flatten_organigramme_nodes(node.get('children', []), depth + 1))
    return flat_nodes


def _build_employe_organigramme_fiche(employes, hierarchies, ouvrage_relations, reference_date, selected_employe_id):
    employe_by_id = {employe.id: employe for employe in employes}
    selected_employe = employe_by_id.get(selected_employe_id)
    if not selected_employe:
        return None

    children_by_superior = defaultdict(list)
    current_superiors = {}
    for relation in hierarchies:
        if relation.employe_id not in employe_by_id or relation.superieur_id not in employe_by_id:
            continue
        if relation.employe_id in current_superiors:
            continue
        current_superiors[relation.employe_id] = relation.superieur_id
        children_by_superior[relation.superieur_id].append(relation.employe_id)

    for child_ids in children_by_superior.values():
        child_ids.sort(key=lambda employe_id: _normalize_sort_text(employe_by_id[employe_id].nom_affichage))

    descendant_ids = []
    visited = {selected_employe.id}

    def walk_descendants(superior_id):
        for child_id in children_by_superior.get(superior_id, []):
            if child_id in visited:
                continue
            visited.add(child_id)
            descendant_ids.append(child_id)
            walk_descendants(child_id)

    walk_descendants(selected_employe.id)

    commune_labels_by_ouvrage = defaultdict(set)
    ouvrage_ids = {relation.ouvrage_id for relation in ouvrage_relations if relation.ouvrage_id}
    if ouvrage_ids:
        commune_rows = Ouvrage.objects.filter(id__in=ouvrage_ids).values(
            'id',
            'pointeau__parcelle__village__fokontany__commune__nom_commune',
        )
        for row in commune_rows:
            commune_nom = row['pointeau__parcelle__village__fokontany__commune__nom_commune']
            if commune_nom:
                commune_labels_by_ouvrage[row['id']].add(commune_nom)

    active_modalites_by_ouvrage = {}
    if ouvrage_ids:
        modalites_qs = ModaliteGestion.objects.filter(
            ouvrage_id__in=ouvrage_ids,
            statut='actif',
            date_debut__lte=reference_date,
        ).filter(
            Q(date_fin__isnull=True) | Q(date_fin__gte=reference_date)
        ).select_related(
            'ouvrage',
            'gestionnaire',
            'employe',
        ).order_by(
            'ouvrage_id',
            '-date_debut',
            '-updated_at',
        )
        for modalite in modalites_qs:
            active_modalites_by_ouvrage.setdefault(modalite.ouvrage_id, modalite)

    def build_relation_item(relation, owner_label=None):
        modalite = active_modalites_by_ouvrage.get(relation.ouvrage_id)
        commune_labels = sorted(
            commune_labels_by_ouvrage.get(relation.ouvrage_id, set()),
            key=_normalize_sort_text,
        )
        return {
            'ouvrage_id': relation.ouvrage_id,
            'ouvrage_nom': relation.ouvrage.nom_ouvrage if relation.ouvrage else 'Sans ouvrage',
            'type_ouvrage': (
                relation.ouvrage.type_ouvrage.nom_type_ouvrage
                if relation.ouvrage and relation.ouvrage.type_ouvrage
                else ''
            ),
            'communes': ', '.join(commune_labels) if commune_labels else 'Sans commune',
            'owner_label': owner_label or relation.employe.nom_affichage,
            'principal': relation.est_responsable_principal,
            'date_debut': relation.date_debut,
            'modalite_paiement': (
                modalite.get_modalitepaiement_display()
                if modalite and modalite.modalitepaiement
                else 'Non definie'
            ),
            'gestionnaire': (
                modalite.gestionnaire.nom_organisation
                if modalite and modalite.gestionnaire
                else ''
            ),
        }

    own_relations = []
    subordinates_relations = []
    modalite_counts = defaultdict(int)
    subordinate_ouvrage_ids = set()

    for relation in ouvrage_relations:
        if relation.employe_id == selected_employe.id:
            item = build_relation_item(relation, owner_label=selected_employe.nom_affichage)
            own_relations.append(item)
            modalite_counts[item['modalite_paiement']] += 1
        elif relation.employe_id in descendant_ids:
            owner = employe_by_id.get(relation.employe_id)
            item = build_relation_item(
                relation,
                owner_label=owner.nom_affichage if owner else 'Subordonne',
            )
            subordinates_relations.append(item)
            subordinate_ouvrage_ids.add(relation.ouvrage_id)

    own_relations.sort(key=lambda item: (
        _normalize_sort_text(item['communes']),
        not item['principal'],
        _normalize_sort_text(item['ouvrage_nom']),
    ))
    subordinates_relations.sort(key=lambda item: (
        _normalize_sort_text(item['owner_label']),
        _normalize_sort_text(item['communes']),
        not item['principal'],
        _normalize_sort_text(item['ouvrage_nom']),
    ))

    subordinates = [
        employe_by_id[employe_id]
        for employe_id in descendant_ids
        if employe_id in employe_by_id
    ]

    return {
        'employe': selected_employe,
        'subordinates': subordinates,
        'subordinates_count': len(subordinates),
        'own_ouvrages_count': len({item['ouvrage_id'] for item in own_relations}),
        'subordinate_ouvrages_count': len(subordinate_ouvrage_ids),
        'modalite_counts': sorted(
            modalite_counts.items(),
            key=lambda entry: (_normalize_sort_text(entry[0]), entry[1]),
        ),
        'own_ouvrages': own_relations,
        'subordinates_ouvrages': subordinates_relations,
    }


def _is_mpikojakoja_ifotony_poste(poste_nom):
    normalized = _normalize_sort_text(poste_nom)
    return 'mpikojakoja' in normalized and 'ifotony' in normalized


def _build_mpikojakoja_organigramme_export_rows(user, reference_date, organisation_id=None, base_id=None):
    employes_queryset = Employe.objects.select_related(
        'poste',
        'base',
        'base__organisation',
    )
    employes_queryset = _filter_active_employes_queryset(employes_queryset)
    employes_queryset, _ = _scope_organigramme_queryset(employes_queryset, user, organisation_id)
    employes_queryset = _filter_employes_by_base(employes_queryset, base_id)
    employes = [
        employe for employe in employes_queryset.order_by('base__nom_base', 'nom', 'prenom')
        if _is_mpikojakoja_ifotony_poste(getattr(getattr(employe, 'poste', None), 'nom_poste', ''))
    ]
    employe_ids = [employe.id for employe in employes]
    if not employe_ids:
        return []

    relations_ouvrages = list(
        EmployeOuvrages.objects.filter(
            employe_id__in=employe_ids,
            date_debut__lte=reference_date,
        ).filter(
            Q(date_fin__gte=reference_date) | Q(date_fin__isnull=True)
        ).select_related(
            'employe',
            'ouvrage',
        ).order_by('employe__nom', 'employe__prenom', '-est_responsable_principal', 'ouvrage__nom_ouvrage')
    )

    ouvrage_ids = sorted({relation.ouvrage_id for relation in relations_ouvrages if relation.ouvrage_id})
    point_eau_rows = []
    if ouvrage_ids:
        point_eau_rows = list(
            PointEau.objects.filter(ouvrage_id__in=ouvrage_ids).values(
                'id',
                'ouvrage_id',
                'tarifforfaitaire',
                'datearretbranchement',
                'parcelle__village__fokontany__commune__nom_commune',
                'parcelle__village__fokontany__commune__district__nom_district',
                'parcelle__village__fokontany__commune__district__region__nom_region',
            ).annotate(
                has_releve_montant=Count(
                    'releves',
                    filter=Q(releves__montant__gt=0),
                    distinct=True,
                )
            )
        )

    active_modalites = {
        row['ouvrage_id']: row['modalitepaiement']
        for row in ModaliteGestion.objects.filter(
            ouvrage_id__in=ouvrage_ids,
            statut='actif',
            date_debut__lte=reference_date,
        ).filter(
            Q(date_fin__gte=reference_date) | Q(date_fin__isnull=True)
        ).order_by('ouvrage_id', '-date_debut', '-updated_at').values('ouvrage_id', 'modalitepaiement')
    }

    points_by_ouvrage = defaultdict(list)
    for row in point_eau_rows:
        points_by_ouvrage[row['ouvrage_id']].append(row)

    relations_by_employe = defaultdict(list)
    for relation in relations_ouvrages:
        relations_by_employe[relation.employe_id].append(relation)

    export_rows = []
    for employe in employes:
        employe_relations = relations_by_employe.get(employe.id, [])
        for relation in employe_relations:
            if not relation.ouvrage_id or not relation.ouvrage:
                continue

            communes = set()
            districts = set()
            regions = set()
            forfaitaire_point_ids = set()
            volumetrique_point_ids = set()
            modalite = active_modalites.get(relation.ouvrage_id)

            for point_row in points_by_ouvrage.get(relation.ouvrage_id, []):
                commune = point_row.get('parcelle__village__fokontany__commune__nom_commune')
                district = point_row.get('parcelle__village__fokontany__commune__district__nom_district')
                region = point_row.get('parcelle__village__fokontany__commune__district__region__nom_region')
                if commune:
                    communes.add(commune)
                if district:
                    districts.add(district)
                if region:
                    regions.add(region)

                if modalite in {'forfaitaire', 'mixte'} and point_row.get('tarifforfaitaire') not in (None, '', 0):
                    forfaitaire_point_ids.add(point_row['id'])
                if modalite in {'au_volume', 'mixte'} and (point_row.get('has_releve_montant') or 0) > 0:
                    volumetrique_point_ids.add(point_row['id'])

            export_rows.append({
                'surnom': employe.surnom or employe.nom_affichage,
                'ouvrage_responsable': relation.ouvrage.nom_ouvrage,
                'communes': ', '.join(sorted(communes, key=_normalize_sort_text)),
                'districts': ', '.join(sorted(districts, key=_normalize_sort_text)),
                'regions': ', '.join(sorted(regions, key=_normalize_sort_text)),
                'nb_points_eau_forfaitaires': len(forfaitaire_point_ids),
                'nb_points_eau_volumetriques': len(volumetrique_point_ids),
            })

    export_rows.sort(
        key=lambda row: (
            _normalize_sort_text(row['regions']),
            _normalize_sort_text(row['districts']),
            _normalize_sort_text(row['communes']),
            _normalize_sort_text(row['ouvrage_responsable']),
            _normalize_sort_text(row['surnom']),
        )
    )
    return export_rows


def _get_safe_next_url(request, fallback_url):
    next_url = (
        request.POST.get('next')
        or request.GET.get('next')
        or ''
    ).strip()
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return fallback_url


def _get_directeur_relations_management_redirect(
    request,
    fallback_url,
    require_password=False,
    action_label='cette action',
):
    if is_directeur_poste(request.user):
        if not require_password:
            return None

        password = (request.POST.get('director_password') or '').strip()
        if not password:
            messages.error(
                request,
                f"Confirmation requise. Saisissez votre mot de passe Directeur pour {action_label}.",
            )
            return redirect(_get_safe_next_url(request, fallback_url))

        if not request.user.check_password(password):
            messages.error(
                request,
                f"Mot de passe Directeur incorrect. Impossible de {action_label}.",
            )
            return redirect(_get_safe_next_url(request, fallback_url))

        return None

    messages.error(
        request,
        "Seul le poste Directeur peut modifier les superieurs hierarchiques et les ouvrages responsables.",
    )
    return redirect(_get_safe_next_url(request, fallback_url))


def _get_employe_ouvrages_management_context(employe):
    relations_ouvrages_qs = employe.ouvrages_responsable.select_related(
        'ouvrage',
        'ouvrage__type_ouvrage',
    ).all()
    relations_ouvrages = list(relations_ouvrages_qs)
    ouvrage_ids = [relation.ouvrage_id for relation in relations_ouvrages if relation.ouvrage_id]

    ouvrage_communes = defaultdict(set)
    if ouvrage_ids:
        commune_rows = Ouvrage.objects.filter(id__in=ouvrage_ids).values(
            'id',
            'pointeau__parcelle__village__fokontany__commune__nom_commune',
        )
        for row in commune_rows:
            commune_nom = row['pointeau__parcelle__village__fokontany__commune__nom_commune']
            if commune_nom:
                ouvrage_communes[row['id']].add(commune_nom)

    for relation in relations_ouvrages:
        commune_labels = sorted(
            ouvrage_communes.get(relation.ouvrage_id, set()),
            key=_normalize_sort_text,
        )
        relation.ouvrage_commune_label = ', '.join(commune_labels) if commune_labels else 'Sans commune'

    relations_ouvrages.sort(
        key=lambda relation: (
            _normalize_sort_text(getattr(relation, 'ouvrage_commune_label', '')),
            _normalize_sort_text(relation.ouvrage.nom_ouvrage),
            relation.date_debut,
            str(relation.pk),
        )
    )

    return {
        'relations_ouvrages': relations_ouvrages,
        'employe_ouvrage_form': EmployeOuvrageForm(employe=employe),
    }


def employees_list(request):
    """Page principale pour la gestion en cascade des employés"""
    user_organisation = _get_user_organisation(request.user)

    if user_organisation:
        bases = Base.objects.filter(organisation=user_organisation).select_related('organisation').order_by('nom_base')
        postes = Poste.objects.filter(organisation=user_organisation).select_related('organisation').order_by('ordre_affichage', 'nom_poste')
    else:
        bases = Base.objects.select_related('organisation').all().order_by('organisation__nom_organisation', 'nom_base')
        postes = Poste.objects.select_related('organisation').all().order_by('organisation__nom_organisation', 'ordre_affichage', 'nom_poste')

    return render(request, 'employees/employees_cascade.html', {
        'title': 'Gestion en Cascade - Employés',
        'bases': bases,
        'postes': postes,
    })


def employees_cascade(request):
    """Alias pour la page de gestion en cascade des employés"""
    return employees_list(request)




# CRUD pour les Postes
def poste_list(request):
    postes = Poste.objects.select_related('organisation').all()
    postes = _filter_postes_by_scope(postes, request.user).order_by('organisation__nom_organisation', 'ordre_affichage', 'nom_poste')
    return render(request, 'employees/poste_list.html', {
        'postes': postes,
        'title': 'Postes'
    })


def poste_create(request):
    user_organisation = _get_user_organisation(request.user)
    if request.method == 'POST':
        form = PosteForm(request.POST)
        if not getattr(request.user, 'is_superuser', False):
            form.fields['organisation'].queryset = form.fields['organisation'].queryset.filter(
                id=getattr(user_organisation, 'id', None)
            )
        if form.is_valid():
            poste = form.save(commit=False)
            if not getattr(request.user, 'is_superuser', False):
                if not user_organisation:
                    messages.error(request, "Organisation introuvable pour votre compte.")
                    return redirect('employees:poste_list')
                poste.organisation = user_organisation
            poste.save()
            messages.success(request, 'Poste cree avec succes!')
            return redirect('employees:poste_list')
        else:
            messages.error(request, 'Erreur dans le formulaire. Veuillez verifier les champs.')
    else:
        form = PosteForm()
        if not getattr(request.user, 'is_superuser', False):
            form.fields['organisation'].queryset = form.fields['organisation'].queryset.filter(
                id=getattr(user_organisation, 'id', None)
            )
            if user_organisation:
                form.initial['organisation'] = user_organisation

    return render(request, 'employees/poste_form.html', {
        'form': form,
        'title': 'Nouveau Poste'
    })


def poste_detail(request, pk):
    poste = get_object_or_404(_filter_postes_by_scope(Poste.objects.all(), request.user), pk=pk)
    employes = poste.employes.all().order_by('nom', 'prenom')
    return render(request, 'employees/poste_detail.html', {
        'poste': poste,
        'employes': employes,
        'title': f'Poste {poste.nom_poste}'
    })


def poste_update(request, pk):
    poste = get_object_or_404(_filter_postes_by_scope(Poste.objects.all(), request.user), pk=pk)
    user_organisation = _get_user_organisation(request.user)
    if request.method == 'POST':
        form = PosteForm(request.POST, instance=poste)
        if not getattr(request.user, 'is_superuser', False):
            form.fields['organisation'].queryset = form.fields['organisation'].queryset.filter(
                id=getattr(user_organisation, 'id', None)
            )
        if form.is_valid():
            updated_poste = form.save(commit=False)
            if not getattr(request.user, 'is_superuser', False):
                if not user_organisation:
                    messages.error(request, "Organisation introuvable pour votre compte.")
                    return redirect('employees:poste_list')
                updated_poste.organisation = user_organisation
            updated_poste.save()
            messages.success(request, 'Poste modifie avec succes!')
            return redirect('employees:poste_detail', pk=pk)
    else:
        form = PosteForm(instance=poste)
        if not getattr(request.user, 'is_superuser', False):
            form.fields['organisation'].queryset = form.fields['organisation'].queryset.filter(
                id=getattr(user_organisation, 'id', None)
            )

    return render(request, 'employees/poste_form.html', {
        'form': form,
        'poste': poste,
        'title': 'Modifier Poste'
    })


def poste_delete(request, pk):
    poste = get_object_or_404(_filter_postes_by_scope(Poste.objects.all(), request.user), pk=pk)
    if request.method == 'POST':
        poste.delete()
        messages.success(request, 'Poste supprimé avec succès!')
        return redirect('employees:poste_list')
    return render(request, 'employees/poste_confirm_delete.html', {
        'poste': poste,
        'title': 'Supprimer Poste'
    })


# CRUD pour les Employés
@employe_required
def employe_list(request):
    # Récupérer les paramètres de recherche et filtres
    search_query = request.GET.get('search', '')
    poste_filter = request.GET.get('poste', 'all')
    base_filter = request.GET.get('base', 'all')
    statut_filter = request.GET.get('statut', 'actif')  # Par défaut : actifs seulement
    sort_by = request.GET.get('sort', 'nom')

    # Récupérer l'organisation de l'utilisateur connecté
    user_organisation = None
    if hasattr(request.user, 'employe') and request.user.employe:
        if request.user.employe.base:
            user_organisation = request.user.employe.base.organisation

    # Requête de base - filtrer par organisation si applicable
    employes = Employe.objects.select_related('poste', 'base', 'base__organisation').all()

    # Périmètre : verrouillé sur l'organisation de l'utilisateur, sauf superuser (toutes les
    # organisations) et partenaire (la sienne + les gestionnaires affectés) qui peuvent basculer.
    from apps.organization.scoping import get_employee_list_organisations
    organisations_selectables = get_employee_list_organisations(request.user)
    organisation_filter = ''
    organisation_options = []
    if organisations_selectables is None:
        if user_organisation:
            employes = employes.filter(base__organisation=user_organisation)
        else:
            employes = employes.none()  # sans organisation : rien à voir (et non « tout »)
        organisation_scope = user_organisation
    else:
        organisation_options = list(organisations_selectables)
        allowed_ids = {str(o.id) for o in organisation_options}
        default_org = str(user_organisation.id) if user_organisation and str(user_organisation.id) in allowed_ids else 'all'
        organisation_filter = request.GET.get('organisation', '') or default_org
        if organisation_filter != 'all' and organisation_filter not in allowed_ids:
            organisation_filter = default_org
        if organisation_filter != 'all':
            employes = employes.filter(base__organisation_id=organisation_filter)
            organisation_scope = next(o for o in organisation_options if str(o.id) == organisation_filter)
        else:
            organisation_scope = None
            if not request.user.is_superuser:
                employes = employes.filter(base__organisation__in=organisation_options)

    # Appliquer la recherche
    if search_query:
        employes = employes.filter(
            Q(nom__icontains=search_query) |
            Q(prenom__icontains=search_query) |
            Q(surnom__icontains=search_query) |
            Q(mail__icontains=search_query) |
            Q(telephone__icontains=search_query)
        )

    # Filtrer par poste
    if poste_filter and poste_filter != 'all':
        employes = employes.filter(poste_id=poste_filter)

    # Filtrer par base
    if base_filter and base_filter != 'all':
        employes = employes.filter(base_id=base_filter)

    # Filtrer par statut
    if statut_filter == 'actif':
        employes = employes.filter(date_debauchage__isnull=True)
    elif statut_filter == 'inactif':
        employes = employes.filter(date_debauchage__isnull=False)
    elif statut_filter == 'salarie':
        employes = employes.filter(date_debauchage__isnull=True, salarie=True)
    elif statut_filter == 'prestataire':
        employes = employes.filter(date_debauchage__isnull=True, salarie=False)
    # Si statut_filter == 'all', ne rien filtrer (afficher tous les employés)

    # Trier
    if sort_by == 'nom':
        employes = employes.order_by('nom', 'prenom')
    elif sort_by == 'prenom':
        employes = employes.order_by('prenom', 'nom')
    elif sort_by == 'poste':
        employes = employes.order_by('poste__ordre_affichage', 'poste__nom_poste', 'nom')
    elif sort_by == 'base':
        employes = employes.order_by('base__nom_base', 'nom')
    elif sort_by == 'recent':
        employes = employes.order_by('-date_embauche', 'nom')

    # Calculer les statistiques
    total_employes = employes.count()
    actifs = employes.filter(date_debauchage__isnull=True).count()
    inactifs = employes.filter(date_debauchage__isnull=False).count()
    salaries = employes.filter(date_debauchage__isnull=True, salarie=True).count()
    prestataires = employes.filter(date_debauchage__isnull=True, salarie=False).count()

    # Récupérer les listes pour les dropdowns - suivent l'organisation affichée
    if organisation_scope:
        postes = Poste.objects.filter(organisation=organisation_scope).order_by('ordre_affichage', 'nom_poste')
        bases = Base.objects.filter(organisation=organisation_scope).order_by('nom_base')
    elif organisations_selectables is not None and not request.user.is_superuser:
        postes = Poste.objects.filter(organisation__in=organisation_options).order_by('ordre_affichage', 'nom_poste')
        bases = Base.objects.filter(organisation__in=organisation_options).order_by('nom_base')
    else:
        postes = Poste.objects.all().order_by('ordre_affichage', 'nom_poste')
        bases = Base.objects.all().order_by('nom_base')

    return render(request, 'employees/employees_list.html', {
        'employes': employes,
        'title': 'Employés',
        'search_query': search_query,
        'poste_filter': poste_filter,
        'base_filter': base_filter,
        'statut_filter': statut_filter,
        'sort_by': sort_by,
        'organisation_options': organisation_options,
        'organisation_filter': organisation_filter,
        'postes': postes,
        'bases': bases,
        'stats': {
            'total': total_employes,
            'actifs': actifs,
            'inactifs': inactifs,
            'salaries': salaries,
            'prestataires': prestataires,
        }
    })


@employe_required
def organigramme_employes(request):
    today = timezone.now().date()
    organigram_mode = (request.GET.get('mode') or 'tree').strip().lower()
    if organigram_mode not in {'tree', 'tree_simple', 'tree_lr', 'a4'}:
        organigram_mode = 'tree'
    simplified_mode = organigram_mode in {'tree_simple', 'tree_lr'}
    left_to_right_mode = organigram_mode == 'tree_lr'

    employes_queryset = Employe.objects.select_related(
        'poste',
        'base',
        'base__organisation',
    )
    employes_queryset = _filter_active_employes_queryset(employes_queryset)
    from apps.organization.scoping import resolve_employee_organisation_scope
    organisation_scope = resolve_employee_organisation_scope(request.user, request.GET.get('organisation', ''))
    employes_queryset, user_organisation = _scope_organigramme_queryset(
        employes_queryset,
        request.user,
        request.GET.get('organisation', ''),
    )

    # Filtre base : options limitées aux bases ayant des employés actifs dans le périmètre courant
    base_options = [
        {'id': str(row['base_id']), 'nom_base': row['base__nom_base']}
        for row in employes_queryset.filter(base__isnull=False)
        .values('base_id', 'base__nom_base')
        .distinct()
        .order_by('base__nom_base')
    ]
    base_selected = (request.GET.get('base') or '').strip()
    if base_selected not in {option['id'] for option in base_options}:
        base_selected = ''
    organisation_employe_ids = []
    if base_selected:
        organisation_employe_ids = list(employes_queryset.values_list('id', flat=True))
        employes_queryset = employes_queryset.filter(base_id=base_selected)

    employes = list(
        employes_queryset.order_by(
            'base__organisation__nom_organisation',
            'base__nom_base',
            'poste__nom_poste',
            'nom',
            'prenom',
        )
    )
    if simplified_mode:
        employes = [
            employe for employe in employes
            if not _is_simplified_organigramme_poste(
                employe.poste.nom_poste if employe.poste else ''
            )
        ]
    employe_ids = [employe.id for employe in employes]

    relations_hierarchiques = HierarchieEmploye.objects.filter(
        employe_id__in=employe_ids,
        date_debut__lte=today,
    ).filter(
        Q(date_fin__gte=today) | Q(date_fin__isnull=True)
    ).select_related(
        'employe',
        'superieur',
        'superieur__poste',
        'superieur__base',
        'superieur__base__organisation',
    ).order_by('employe_id', '-date_debut')

    relations_ouvrages = EmployeOuvrages.objects.filter(
        employe_id__in=employe_ids,
        date_debut__lte=today,
    ).filter(
        Q(date_fin__gte=today) | Q(date_fin__isnull=True)
    ).select_related(
        'employe',
        'ouvrage',
        'ouvrage__type_ouvrage',
    ).order_by(
        'employe__nom',
        'employe__prenom',
        '-est_responsable_principal',
        'ouvrage__nom_ouvrage',
    )

    if base_selected:
        # Réconciliation sur toute l'organisation : un ouvrage affecté à une autre base n'est pas orphelin
        relations_ouvrages_organisation = EmployeOuvrages.objects.filter(
            employe_id__in=organisation_employe_ids,
            date_debut__lte=today,
        ).filter(
            Q(date_fin__gte=today) | Q(date_fin__isnull=True)
        ).select_related('employe', 'ouvrage')
        ouvrage_reconciliation = _build_organigramme_ouvrage_reconciliation(
            relations_ouvrages_organisation,
            user_organisation,
            today,
            scope_ouvrage_ids={r.ouvrage_id for r in relations_ouvrages if r.ouvrage_id},
        )
    else:
        ouvrage_reconciliation = _build_organigramme_ouvrage_reconciliation(
            relations_ouvrages,
            user_organisation,
            today,
        )
    organigram_roots, stats = _build_organigramme_data(
        employes,
        relations_hierarchiques,
        relations_ouvrages,
        ouvrage_diagnostics=ouvrage_reconciliation['displayed_diagnostics'],
        include_ouvrages=not simplified_mode,
    )
    organigram_flat_nodes = _flatten_organigramme_nodes(organigram_roots)
    selected_fiche_employe_id = request.GET.get('fiche_employe')
    fiche_employe = _build_employe_organigramme_fiche(
        employes,
        relations_hierarchiques,
        relations_ouvrages,
        today,
        selected_fiche_employe_id,
    ) if selected_fiche_employe_id else None
    stats.update({
        'total_ouvrages_affectation_active': len(ouvrage_reconciliation['active_organisation_ouvrage_ids']),
        'total_ouvrages_hors_affectation': len(ouvrage_reconciliation['extra_items']),
        'total_ouvrages_sans_responsable': len(ouvrage_reconciliation['missing_items']),
    })

    return render(request, 'employees/organigramme.html', {
        'title': 'Organigramme RH',
        'organigram_roots': organigram_roots,
        'organigram_flat_nodes': organigram_flat_nodes,
        'organigram_mode': organigram_mode,
        'simplified_mode': simplified_mode,
        'left_to_right_mode': left_to_right_mode,
        'can_manage_employee_relations': is_directeur_poste(request.user),
        'stats': stats,
        'date_reference': today,
        'organisation_cible': (
            user_organisation.nom_organisation
            if user_organisation
            else 'Toutes les organisations'
        ),
        'organisation_options': organisation_scope['options'],
        'organisation_selected': organisation_scope['selected'],
        # Paramètre à conserver dans les liens de la page (modes d'affichage, fiche...)
        'base_options': base_options,
        'base_selected': base_selected,
        'organisation_qs': (
            (f"&organisation={organisation_scope['selected']}" if organisation_scope['options'] else '')
            + (f"&base={base_selected}" if base_selected else '')
        ),
        'has_organisation_scope': bool(user_organisation),
        'organigram_ouvrages_hors_affectation': ouvrage_reconciliation['extra_items'],
        'organigram_ouvrages_sans_responsable': ouvrage_reconciliation['missing_items'],
        'fiche_employe': fiche_employe,
        'selected_fiche_employe_id': selected_fiche_employe_id,
        'fiche_employe_options': employes,
    })


@employe_required
def export_organigramme_mpikojakoja_excel(request):
    reference_date = timezone.now().date()
    rows = _build_mpikojakoja_organigramme_export_rows(
        request.user,
        reference_date,
        request.GET.get('organisation', ''),
        request.GET.get('base', ''),
    )

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = 'Mpikojakoja ifotony'

    headers = [
        'Surnom',
        'Ouvrage responsable',
        'Commune',
        'District',
        'Region',
        'Nombre points d eau avec tarif forfaitaire',
        'Nombre points d eau avec factures volumetriques',
    ]
    worksheet.append(headers)

    for row in rows:
        worksheet.append([
            row['surnom'],
            row['ouvrage_responsable'],
            row['communes'],
            row['districts'],
            row['regions'],
            row['nb_points_eau_forfaitaires'],
            row['nb_points_eau_volumetriques'],
        ])

    for column_cells in worksheet.columns:
        max_length = 0
        column_letter = column_cells[0].column_letter
        for cell in column_cells:
            cell_value = '' if cell.value is None else str(cell.value)
            if len(cell_value) > max_length:
                max_length = len(cell_value)
        worksheet.column_dimensions[column_letter].width = min(max_length + 2, 60)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = (
        f'attachment; filename="organigramme_mpikojakoja_ifotony_{reference_date.strftime("%Y%m%d")}.xlsx"'
    )
    workbook.save(response)
    return response


@employe_required
def employe_create(request):
    if request.method == 'POST':
        form = EmployeForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Employé créé avec succès!')
            return redirect('employees:employe_list')
        else:
            messages.error(request, 'Erreur dans le formulaire. Veuillez vérifier les champs.')
    else:
        form = EmployeForm()

    return render(request, 'employees/employe_form.html', {
        'form': form,
        'title': 'Nouvel Employé'
    })


def employe_detail(request, pk):
    selected_employe = get_object_or_404(Employe, pk=pk)
    contrats = selected_employe.contrats.all().order_by('-debut_contrat')
    relations = selected_employe.relations_hierarchiques.select_related(
        'superieur',
        'superieur__poste',
    ).all().order_by('-date_debut')
    hierarchie_form = HierarchieEmployeForm(employe=selected_employe)
    ouvrages_context = _get_employe_ouvrages_management_context(selected_employe)

    return render(request, 'employees/employe_detail.html', {
        'employe': getattr(request.user, 'employe', None),
        'selected_employe': selected_employe,
        'contrats': contrats,
        'relations_hierarchiques': relations,
        'hierarchie_form': hierarchie_form,
        'is_directeur_poste': is_directeur_poste(request.user),
        **ouvrages_context,
        'title': f'{selected_employe.prenom} {selected_employe.nom}'
    })


@employe_required
def organigramme_employe_ouvrages_modal(request, pk):
    employe_queryset = Employe.objects.select_related(
        'poste',
        'base',
        'base__organisation',
    )
    employe_queryset = _filter_active_employes_queryset(employe_queryset)
    employe_queryset, _ = _scope_organigramme_queryset(
        employe_queryset,
        request.user,
        'all',
    )
    employe = get_object_or_404(employe_queryset, pk=pk)

    mode = (request.GET.get('mode') or 'tree').strip().lower()
    if mode not in {'tree', 'a4'}:
        mode = 'tree'

    fallback_url = reverse('employees:organigramme')
    return_to = _get_safe_next_url(
        request,
        f'{fallback_url}?mode={mode}&manage_ouvrages={employe.id}'
    )
    ouvrages_context = _get_employe_ouvrages_management_context(employe)

    return render(request, 'employees/partials/organigramme_employe_ouvrages_modal_content.html', {
        'employe': employe,
        'return_to': return_to,
        'organigram_mode': mode,
        'can_manage_employee_relations': is_directeur_poste(request.user),
        **ouvrages_context,
    })


@employe_required
def organigramme_employe_fiche_print(request, pk):
    today = timezone.now().date()

    employes_queryset = Employe.objects.select_related(
        'poste',
        'base',
        'base__organisation',
    )
    employes_queryset = _filter_active_employes_queryset(employes_queryset)
    employes_queryset, _ = _scope_organigramme_queryset(
        employes_queryset,
        request.user,
        'all',
    )

    employes = list(
        employes_queryset.order_by(
            'base__organisation__nom_organisation',
            'base__nom_base',
            'poste__nom_poste',
            'nom',
            'prenom',
        )
    )
    employe_ids = [employe.id for employe in employes]
    employe = get_object_or_404(employes_queryset, pk=pk)

    relations_hierarchiques = HierarchieEmploye.objects.filter(
        employe_id__in=employe_ids,
        date_debut__lte=today,
    ).filter(
        Q(date_fin__gte=today) | Q(date_fin__isnull=True)
    ).select_related(
        'employe',
        'superieur',
        'superieur__poste',
        'superieur__base',
        'superieur__base__organisation',
    ).order_by('employe_id', '-date_debut')

    relations_ouvrages = EmployeOuvrages.objects.filter(
        employe_id__in=employe_ids,
        date_debut__lte=today,
    ).filter(
        Q(date_fin__gte=today) | Q(date_fin__isnull=True)
    ).select_related(
        'employe',
        'ouvrage',
        'ouvrage__type_ouvrage',
    ).order_by(
        'employe__nom',
        'employe__prenom',
        '-est_responsable_principal',
        'ouvrage__nom_ouvrage',
    )

    fiche_employe = _build_employe_organigramme_fiche(
        employes,
        relations_hierarchiques,
        relations_ouvrages,
        today,
        employe.id,
    )

    return render(request, 'employees/organigramme_employe_fiche_print.html', {
        'title': f'Fiche employe - {employe.nom_affichage}',
        'fiche_employe': fiche_employe,
        'date_reference': today,
    })


def employe_update(request, pk):
    employe = get_object_or_404(Employe, pk=pk)
    if request.method == 'POST':
        form = EmployeForm(request.POST, request.FILES, instance=employe)
        if form.is_valid():
            form.save()
            messages.success(request, 'Employé modifié avec succès!')
            return redirect('employees:employe_detail', pk=pk)
    else:
        form = EmployeForm(instance=employe)

    return render(request, 'employees/employe_form.html', {
        'form': form,
        'employe': employe,
        'title': 'Modifier Employé'
    })


def employe_delete(request, pk):
    employe = get_object_or_404(Employe, pk=pk)
    if request.method == 'POST':
        employe.delete()
        messages.success(request, 'Employé supprimé avec succès!')
        return redirect('employees:employe_list')
    return render(request, 'employees/employe_confirm_delete.html', {
        'employe': employe,
        'title': 'Supprimer Employé'
    })


@csrf_exempt
@employe_required
def employe_delete_api(request, pk):
    """API pour supprimer un employé (retourne JSON)"""
    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': 'Méthode non autorisée'
        }, status=405)

    try:
        employe = get_object_or_404(Employe, pk=pk)
        employe_nom = employe.nom_complet

        # Supprimer l'employé (cascade supprimera les contrats, grilles, salaires)
        employe.delete()

        return JsonResponse({
            'success': True,
            'message': f'Employé "{employe_nom}" supprimé avec succès'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["POST"])
def hierarchie_create(request, employe_id):
    """Vue pour ajouter une relation hiérarchique"""
    employe = get_object_or_404(Employe, id=employe_id)
    redirect_target = _get_safe_next_url(
        request,
        reverse('employees:employe_detail', kwargs={'pk': employe_id})
    )
    permission_redirect = _get_directeur_relations_management_redirect(
        request,
        redirect_target,
        require_password=True,
        action_label='ajouter un superieur hierarchique',
    )
    if permission_redirect:
        return permission_redirect

    form = HierarchieEmployeForm(request.POST, employe=employe)
    if form.is_valid():
        relation = form.save(commit=False)
        relation.employe = employe
        relation.save()
        messages.success(request, 'Relation hiérarchique ajoutée.')
    else:
        messages.error(request, 'Erreur dans le formulaire.')
    return redirect(redirect_target)


@require_http_methods(["POST"])
def hierarchie_update_dates(request, pk):
    """Vue pour modifier la date de fin (et le commentaire) d'une relation hiérarchique"""
    relation = get_object_or_404(HierarchieEmploye, pk=pk)
    redirect_target = _get_safe_next_url(
        request,
        reverse('employees:employe_detail', kwargs={'pk': relation.employe_id})
    )
    permission_redirect = _get_directeur_relations_management_redirect(
        request,
        redirect_target,
        require_password=True,
        action_label='modifier un superieur hierarchique',
    )
    if permission_redirect:
        return permission_redirect

    date_fin_raw = (request.POST.get('date_fin') or '').strip()
    if date_fin_raw:
        try:
            nouvelle_date_fin = datetime.strptime(date_fin_raw, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, 'Format de date de fin invalide.')
            return redirect(redirect_target)

        if nouvelle_date_fin < relation.date_debut:
            messages.error(request, 'La date de fin doit etre posterieure ou egale a la date de debut.')
            return redirect(redirect_target)

        relation.date_fin = nouvelle_date_fin
    else:
        relation.date_fin = None

    relation.commentaire = (request.POST.get('commentaire') or '').strip() or None
    relation.save(update_fields=['date_fin', 'commentaire', 'date_modification'])
    messages.success(request, 'Relation hiérarchique mise à jour.')
    return redirect(redirect_target)


@require_http_methods(["POST"])
def hierarchie_delete(request, pk):
    """Vue pour supprimer une relation hiérarchique"""
    relation = get_object_or_404(HierarchieEmploye, pk=pk)
    employe_id = relation.employe.id
    redirect_target = _get_safe_next_url(
        request,
        reverse('employees:employe_detail', kwargs={'pk': employe_id})
    )
    permission_redirect = _get_directeur_relations_management_redirect(
        request,
        redirect_target,
        require_password=True,
        action_label='supprimer un superieur hierarchique',
    )
    if permission_redirect:
        return permission_redirect

    relation.delete()
    messages.success(request, 'Relation supprimée.')
    return redirect(redirect_target)


@require_http_methods(["POST"])
def employe_ouvrage_create(request, employe_id):
    """Vue pour ajouter une responsabilite d ouvrage a un employe."""
    employe = get_object_or_404(Employe, id=employe_id)
    redirect_target = _get_safe_next_url(
        request,
        reverse('employees:employe_detail', kwargs={'pk': employe_id})
    )
    permission_redirect = _get_directeur_relations_management_redirect(
        request,
        redirect_target,
        require_password=True,
        action_label='ajouter un ouvrage responsable',
    )
    if permission_redirect:
        return permission_redirect
    if request.method == 'POST':
        submit_action = (request.POST.get('submit_action') or 'single').strip()
        bulk_mode = submit_action == 'bulk_commune'
        form = EmployeOuvrageForm(request.POST, employe=employe, bulk_mode=bulk_mode)
        if form.is_valid():
            if bulk_mode:
                commune = form.cleaned_data['commune']
                ouvrages_qs = form.get_commune_ouvrages(commune)
                ouvrage_ids = list(ouvrages_qs.values_list('id', flat=True))

                if not ouvrage_ids:
                    messages.info(request, 'Aucun ouvrage disponible pour la commune selectionnee.')
                    return redirect(redirect_target)

                existing_ouvrage_ids = set(
                    EmployeOuvrages.objects.filter(
                        employe=employe,
                        ouvrage_id__in=ouvrage_ids,
                    ).values_list('ouvrage_id', flat=True)
                )

                relations_to_create = [
                    EmployeOuvrages(
                        employe=employe,
                        ouvrage_id=ouvrage_id,
                        date_debut=form.cleaned_data['date_debut'],
                        date_fin=form.cleaned_data.get('date_fin'),
                        est_responsable_principal=form.cleaned_data.get('est_responsable_principal') or False,
                        recevoir_alertes=form.cleaned_data.get('recevoir_alertes', True),
                        notes=form.cleaned_data.get('notes'),
                    )
                    for ouvrage_id in ouvrage_ids
                    if ouvrage_id not in existing_ouvrage_ids
                ]

                if relations_to_create:
                    EmployeOuvrages.objects.bulk_create(relations_to_create, ignore_conflicts=True)

                created_count = len(relations_to_create)
                skipped_count = len(ouvrage_ids) - created_count

                if created_count and skipped_count:
                    messages.success(
                        request,
                        f'{created_count} ouvrage(s) ajoute(s) pour la commune {commune.nom_commune}. '
                        f'{skipped_count} deja present(s) dans le tableau.'
                    )
                elif created_count:
                    messages.success(
                        request,
                        f'{created_count} ouvrage(s) ajoute(s) pour la commune {commune.nom_commune}.'
                    )
                else:
                    messages.info(
                        request,
                        f'Tous les ouvrages de la commune {commune.nom_commune} sont deja presents dans le tableau.'
                    )
            else:
                relation = form.save(commit=False)
                relation.employe = employe
                relation.save()
                messages.success(request, 'Responsabilite d ouvrage ajoutee.')
        else:
            first_error = next(iter(form.errors.values()), None)
            if first_error:
                messages.error(request, first_error[0])
            else:
                messages.error(request, 'Erreur dans le formulaire.')
    return redirect(redirect_target)


@require_http_methods(["POST"])
def employe_ouvrage_delete(request, pk):
    """Vue pour supprimer une responsabilite d ouvrage."""
    relation = get_object_or_404(EmployeOuvrages, pk=pk)
    employe_id = relation.employe.id
    redirect_target = _get_safe_next_url(
        request,
        reverse('employees:employe_detail', kwargs={'pk': employe_id})
    )
    permission_redirect = _get_directeur_relations_management_redirect(
        request,
        redirect_target,
        require_password=True,
        action_label='supprimer un ouvrage responsable',
    )
    if permission_redirect:
        return permission_redirect
    relation.delete()
    messages.success(request, 'Responsabilite d ouvrage supprimee.')
    return redirect(redirect_target)


@require_http_methods(["POST"])
def employe_ouvrages_delete_selected(request, employe_id):
    """Vue pour supprimer plusieurs responsabilites d ouvrage cochees pour un employe."""
    employe = get_object_or_404(Employe, id=employe_id)
    redirect_target = _get_safe_next_url(
        request,
        reverse('employees:employe_detail', kwargs={'pk': employe_id})
    )
    permission_redirect = _get_directeur_relations_management_redirect(
        request,
        redirect_target,
        require_password=True,
        action_label='supprimer les ouvrages responsables selectionnes',
    )
    if permission_redirect:
        return permission_redirect
    relation_ids = [relation_id for relation_id in request.POST.getlist('relation_ids') if relation_id]

    if not relation_ids:
        messages.info(request, 'Aucun ouvrage responsable selectionne.')
        return redirect(redirect_target)

    relations_qs = employe.ouvrages_responsable.filter(id__in=relation_ids)
    total_deleted = relations_qs.count()

    if total_deleted > 0:
        relations_qs.delete()
        messages.success(
            request,
            f'{total_deleted} responsabilite(s) d ouvrage selectionnee(s) supprimee(s).'
        )
    else:
        messages.info(request, 'Aucun ouvrage responsable selectionne a supprimer.')

    return redirect(redirect_target)


@require_http_methods(["POST"])
def employe_ouvrage_update_dates(request, pk):
    """Vue pour modifier la date de fin et le statut principal d une responsabilite d ouvrage."""
    relation = get_object_or_404(EmployeOuvrages, pk=pk)
    employe_id = relation.employe.id
    redirect_target = _get_safe_next_url(
        request,
        reverse('employees:employe_detail', kwargs={'pk': employe_id})
    )
    permission_redirect = _get_directeur_relations_management_redirect(
        request,
        redirect_target,
        require_password=True,
        action_label='supprimer tous les ouvrages responsables',
    )
    if permission_redirect:
        return permission_redirect
    date_fin_raw = (request.POST.get('date_fin') or '').strip()
    est_responsable_principal = request.POST.get('est_responsable_principal') == 'on'

    if date_fin_raw:
        try:
            nouvelle_date_fin = datetime.strptime(date_fin_raw, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, 'Format de date de fin invalide.')
            return redirect(redirect_target)

        if nouvelle_date_fin < relation.date_debut:
            messages.error(request, 'La date de fin doit etre posterieure ou egale a la date de debut.')
            return redirect(redirect_target)

        relation.date_fin = nouvelle_date_fin
    else:
        relation.date_fin = None

    relation.est_responsable_principal = est_responsable_principal
    relation.save(update_fields=['date_fin', 'est_responsable_principal', 'updated_at'])

    if relation.date_fin:
        if relation.est_responsable_principal:
            messages.success(request, 'Date de fin et statut responsable principal mis a jour.')
        else:
            messages.success(request, 'Date de fin mise a jour.')
    else:
        if relation.est_responsable_principal:
            messages.success(request, 'Date de fin retiree et statut responsable principal mis a jour.')
        else:
            messages.success(request, 'Date de fin retiree. La responsabilite est a nouveau en cours.')

    return redirect(redirect_target)


@require_http_methods(["POST"])
def employe_ouvrages_delete_all(request, employe_id):
    """Vue pour supprimer toutes les responsabilites d ouvrage d un employe."""
    employe = get_object_or_404(Employe, id=employe_id)
    redirect_target = _get_safe_next_url(
        request,
        reverse('employees:employe_detail', kwargs={'pk': employe_id})
    )
    permission_redirect = _get_directeur_relations_management_redirect(request, redirect_target)
    if permission_redirect:
        return permission_redirect
    relations_qs = employe.ouvrages_responsable.all()
    total_deleted = relations_qs.count()

    if total_deleted > 0:
        relations_qs.delete()
        messages.success(
            request,
            f'{total_deleted} responsabilite(s) d ouvrage supprimee(s).'
        )
    else:
        messages.info(request, 'Aucun ouvrage responsable a supprimer.')

    return redirect(redirect_target)


# CRUD pour les Contrats
def contrat_list(request):
    contrats = Contrat.objects.select_related('employe', 'employe__poste').all().order_by('-debut_contrat')
    return render(request, 'employees/contrat_list.html', {
        'contrats': contrats,
        'title': 'Contrats'
    })


def contrat_create(request):
    if request.method == 'POST':
        form = ContratForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Contrat créé avec succès!')
            return redirect('employees:contrat_list')
        else:
            messages.error(request, 'Erreur dans le formulaire. Veuillez vérifier les champs.')
    else:
        form = ContratForm()

    return render(request, 'employees/contrat_form.html', {
        'form': form,
        'title': 'Nouveau Contrat'
    })


def contrat_detail(request, pk):
    contrat = get_object_or_404(Contrat, pk=pk)
    grilles = contrat.grilles_salaire.all().order_by('-date_salaire')
    return render(request, 'employees/contrat_detail.html', {
        'contrat': contrat,
        'grilles': grilles,
        'title': f'Contrat {contrat.employe}'
    })


def contrat_update(request, pk):
    contrat = get_object_or_404(Contrat, pk=pk)
    if request.method == 'POST':
        form = ContratForm(request.POST, instance=contrat)
        if form.is_valid():
            form.save()
            messages.success(request, 'Contrat modifié avec succès!')
            return redirect('employees:contrat_detail', pk=pk)
    else:
        form = ContratForm(instance=contrat)

    return render(request, 'employees/contrat_form.html', {
        'form': form,
        'contrat': contrat,
        'title': 'Modifier Contrat'
    })


def contrat_delete(request, pk):
    contrat = get_object_or_404(Contrat, pk=pk)
    if request.method == 'POST':
        contrat.delete()
        messages.success(request, 'Contrat supprimé avec succès!')
        return redirect('employees:contrat_list')
    return render(request, 'employees/contrat_confirm_delete.html', {
        'contrat': contrat,
        'title': 'Supprimer Contrat'
    })


# CRUD pour les Grilles de Salaire
def grille_salaire_list(request):
    grilles = GrilleSalaire.objects.select_related('contrat', 'contrat__employe').all().order_by('-date_salaire')
    return render(request, 'employees/grille_salaire_list.html', {
        'grilles': grilles,
        'title': 'Grilles de Salaire'
    })


def grille_salaire_create(request):
    if request.method == 'POST':
        form = GrilleSalaireForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Grille de salaire créée avec succès!')
            return redirect('employees:grille_salaire_list')
        else:
            messages.error(request, 'Erreur dans le formulaire. Veuillez vérifier les champs.')
    else:
        form = GrilleSalaireForm()

    return render(request, 'employees/grille_salaire_form.html', {
        'form': form,
        'title': 'Nouvelle Grille de Salaire'
    })


def grille_salaire_detail(request, pk):
    grille = get_object_or_404(GrilleSalaire, pk=pk)
    salaires = grille.salaires.all().order_by('-date_paiement')
    return render(request, 'employees/grille_salaire_detail.html', {
        'grille': grille,
        'salaires': salaires,
        'title': f'Grille {grille.contrat.employe} - {grille.date_salaire}'
    })


def grille_salaire_update(request, pk):
    grille = get_object_or_404(GrilleSalaire, pk=pk)
    if request.method == 'POST':
        form = GrilleSalaireForm(request.POST, instance=grille)
        if form.is_valid():
            form.save()
            messages.success(request, 'Grille de salaire modifiée avec succès!')
            return redirect('employees:grille_salaire_detail', pk=pk)
    else:
        form = GrilleSalaireForm(instance=grille)

    return render(request, 'employees/grille_salaire_form.html', {
        'form': form,
        'grille': grille,
        'title': 'Modifier Grille de Salaire'
    })


def grille_salaire_delete(request, pk):
    grille = get_object_or_404(GrilleSalaire, pk=pk)
    if request.method == 'POST':
        grille.delete()
        messages.success(request, 'Grille de salaire supprimée avec succès!')
        return redirect('employees:grille_salaire_list')
    return render(request, 'employees/grille_salaire_confirm_delete.html', {
        'grille': grille,
        'title': 'Supprimer Grille de Salaire'
    })


# API ENDPOINTS pour les formulaires en cascade

def api_postes(request):
    """API pour charger tous les postes"""
    postes = Poste.objects.select_related('organisation').all()
    postes = _filter_postes_by_scope(postes, request.user).order_by('organisation__nom_organisation', 'ordre_affichage', 'nom_poste')

    data = []
    for poste in postes:
        data.append({
            'id': str(poste.id),
            'nom_poste': poste.nom_poste,
            'organisation_nom': poste.organisation.nom_organisation if poste.organisation else None,
        })

    return JsonResponse(data, safe=False)


def api_create(request):
    """API pour créer de nouveaux éléments"""
    if request.method == 'POST':
        entity_type = request.POST.get('type')

        try:
            if entity_type == 'employe':
                form = EmployeForm(request.POST)
                if form.is_valid():
                    employe = form.save()
                    return JsonResponse({
                        'success': True,
                        'message': 'Employé créé avec succès!',
                        'id': str(employe.id)
                    })
                else:
                    return JsonResponse({
                        'success': False,
                        'message': 'Erreur dans le formulaire',
                        'errors': dict(form.errors)
                    })

            elif entity_type == 'contrat':
                # Debug: afficher les données reçues
                print("=== DEBUG CONTRAT ===")
                print("POST data:", dict(request.POST))
                print("employe:", request.POST.get('employe'))

                form = ContratForm(request.POST)
                if form.is_valid():
                    contrat = form.save()
                    return JsonResponse({
                        'success': True,
                        'message': 'Contrat créé avec succès!',
                        'id': str(contrat.id)
                    })
                else:
                    print("Form errors:", form.errors)
                    print("Form cleaned_data:", form.cleaned_data if hasattr(form, 'cleaned_data') else 'N/A')
                    return JsonResponse({
                        'success': False,
                        'message': 'Erreur dans le formulaire',
                        'errors': dict(form.errors)
                    })

            elif entity_type == 'grille':
                form = GrilleSalaireForm(request.POST)
                if form.is_valid():
                    grille = form.save()
                    return JsonResponse({
                        'success': True,
                        'message': 'Grille de salaire créée avec succès!',
                        'id': str(grille.id)
                    })
                else:
                    return JsonResponse({
                        'success': False,
                        'message': 'Erreur dans le formulaire',
                        'errors': dict(form.errors)
                    })

            elif entity_type == 'salaire':
                form = SalaireForm(request.POST)
                if form.is_valid():
                    salaire = form.save()
                    return JsonResponse({
                        'success': True,
                        'message': 'Paiement créé avec succès!',
                        'id': str(salaire.id)
                    })
                else:
                    return JsonResponse({
                        'success': False,
                        'message': 'Erreur dans le formulaire',
                        'errors': dict(form.errors)
                    })

            else:
                return JsonResponse({
                    'success': False,
                    'message': f'Type d\'entité non reconnu: {entity_type}'
                })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la création: {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


@employe_required
def api_employes(request):
    """API pour charger tous les employés avec filtrage optionnel par base"""
    from django.core.paginator import Paginator

    today = timezone.now().date()
    current_hierarchy_qs = HierarchieEmploye.objects.filter(
        date_debut__lte=today
    ).filter(
        Q(date_fin__gte=today) | Q(date_fin__isnull=True)
    ).select_related('superieur').order_by('-date_debut')

    employes_queryset = Employe.objects.select_related(
        'poste',
        'base',
        'base__organisation'
    ).prefetch_related(
        Prefetch(
            'relations_hierarchiques',
            queryset=current_hierarchy_qs,
            to_attr='current_hierarchy_relations',
        )
    ).annotate(
        contrats_count=Count('contrats'),
        bases_diamex_count=Count('bases_diamex')
    )

    # Filtrage par statut actif (employés sans date de débauchage)
    actifs_only = request.GET.get('actifs_only', 'true').lower() == 'true'
    if actifs_only:
        employes_queryset = employes_queryset.filter(date_debauchage__isnull=True)

    # Filtrage par organisation : celle de l'utilisateur par défaut ; ?organisation=<id|all> pour
    # les superusers et les partenaires (même règle que la liste des employés).
    from apps.organization.scoping import apply_employee_organisation_scope, resolve_employee_organisation_scope
    organisation_scope = resolve_employee_organisation_scope(request.user, request.GET.get('organisation', ''))
    employes_queryset = apply_employee_organisation_scope(employes_queryset, organisation_scope)

    # Filtrage optionnel par base
    base_id = request.GET.get('base')
    if base_id:
        employes_queryset = employes_queryset.filter(base_id=base_id)

    poste_id = request.GET.get('poste_id')
    if poste_id:
        employes_queryset = employes_queryset.filter(poste_id=poste_id)

    # Recherche
    search = request.GET.get('search', '').strip()
    if search:
        employes_queryset = employes_queryset.filter(
            Q(nom__icontains=search) |
            Q(prenom__icontains=search) |
            Q(surnom__icontains=search) |
            Q(numero_cin__icontains=search) |
            Q(numero_cnaps__icontains=search) |
            Q(telephone__icontains=search)
        )

    employes_queryset = employes_queryset.order_by(
        'base__nom_base', 'poste__nom_poste', 'nom', 'prenom'
    )

    # Pagination
    page = request.GET.get('page', 1)
    per_page = request.GET.get('per_page', 10)  # Par défaut 10, mais peut être augmenté
    try:
        per_page = int(per_page)
        # Limiter Ã  un maximum de 1000 pour éviter les abus
        per_page = min(per_page, 1000)
    except (ValueError, TypeError):
        per_page = 10

    paginator = Paginator(employes_queryset, per_page)
    employes_page = paginator.get_page(page)
    employes = employes_page.object_list

    data = []
    for employe in employes:
        current_relation = employe.current_hierarchy_relations[0] if getattr(employe, 'current_hierarchy_relations', []) else None
        superieur = current_relation.superieur if current_relation else None
        data.append({
            'id': str(employe.id),
            'nom_employe': employe.nom_employe,
            'nom': employe.nom,
            'prenom': employe.prenom,
            'surnom': employe.surnom,
            'poste_id': str(employe.poste.id) if employe.poste else None,
            'poste_nom': employe.poste.nom_poste if employe.poste else None,
            'genre': employe.genre if employe.genre else '',
            'genre_display': 'Masculin' if employe.genre == 'M' else 'Féminin' if employe.genre == 'F' else '',
            'date_naissance': str(employe.date_naissance) if employe.date_naissance else '',
            'mutuelle_sante': employe.mutuelle_sante if employe.mutuelle_sante else '',
            'base_id': str(employe.base.id) if employe.base else None,
            'base_nom': employe.base.nom_base if employe.base else None,
            'organisation_nom': employe.base.organisation.nom_organisation if employe.base and employe.base.organisation else None,
            'date_embauche': str(employe.date_embauche) if employe.date_embauche else '',
            'date_debauchage': str(employe.date_debauchage) if employe.date_debauchage else '',
            'numero_cnaps': employe.numero_cnaps,
            'numero_cin': employe.numero_cin,
            'lieu_delivrance_cin': employe.lieu_delivrance_cin,
            'date_delivrance_cin': str(employe.date_delivrance_cin) if employe.date_delivrance_cin else '',
            'lieu_naissance': employe.lieu_naissance,
            'adresse': employe.adresse,
            'telephone': employe.telephone,
            'personnes_charge': employe.personnes_charge,
            'salarie': employe.salarie,
            'mail': employe.mail,
            'superieur_hierarchique_id': str(superieur.id) if superieur else None,
            'superieur_hierarchique_nom': (superieur.surnom or superieur.nom_complet) if superieur else None,
            'contrats_count': employe.contrats_count,
            'bases_diamex_count': employe.bases_diamex_count
        })

    return JsonResponse({
        'employes': data,
        'pagination': {
            'current_page': employes_page.number,
            'total_pages': paginator.num_pages,
            'total_count': paginator.count,
            'has_previous': employes_page.has_previous(),
            'has_next': employes_page.has_next(),
            'previous_page': employes_page.previous_page_number() if employes_page.has_previous() else None,
            'next_page': employes_page.next_page_number() if employes_page.has_next() else None,
        }
    })


def api_contrats(request, employe_id):
    """API pour charger les contrats d'un employé"""
    contrats = Contrat.objects.filter(
        employe_id=employe_id
    ).select_related('poste', 'employe').annotate(
        grilles_count=Count('grilles_salaire')
    ).order_by('-debut_contrat')

    data = []
    for contrat in contrats:
        data.append({
            'id': str(contrat.id),
            'employe_id': str(contrat.employe_id),  # CRITICAL pour l'édition
            'debut_contrat': str(contrat.debut_contrat),
            'fin_contrat': str(contrat.fin_contrat) if contrat.fin_contrat else '',
            'categorie_professionnel': contrat.categorie_professionnel,
            'type_contrat': contrat.type_contrat,
            'poste_id': str(contrat.poste.id) if contrat.poste else None,
            'poste_nom': contrat.poste.nom_poste if contrat.poste else None,
            'salaire_brut_base': float(contrat.salaire_brut_base) if contrat.salaire_brut_base else 0,
            'personnes_charge': contrat.employe.personnes_charge if contrat.employe else 0,
            'is_active': contrat.is_active,
            'grilles_count': contrat.grilles_count
        })

    return JsonResponse(data, safe=False)


def api_grilles_salaire(request, contrat_id):
    """API pour charger les grilles de salaire d'un contrat"""
    from django.db.models import Count

    grilles = GrilleSalaire.objects.filter(
        contrat_id=contrat_id
    ).select_related('contrat').annotate(
        nb_salaires=Count('salaires')  # Compte les paiements liés via related_name='salaires'
    ).order_by('-date_salaire')

    data = []
    for grille in grilles:
        # Si salaire_brut_base de la grille est 0 ou NULL, prendre celui du contrat
        salaire_brut_base = grille.salaire_brut_base
        if not salaire_brut_base or salaire_brut_base == 0:
            salaire_brut_base = grille.contrat.salaire_brut_base if grille.contrat else 0

        data.append({
            'id': str(grille.id),
            'contrat_id': str(grille.contrat_id),  #  AJOUTE: ID du contrat parent
            'date_salaire': str(grille.date_salaire),
            'personnes_charge': grille.personnes_charge,
            'nb_jours_presence': grille.nb_jours_presence,
            'nb_dimanches_travailles': grille.nb_dimanches_travailles,
            'est_prorata': grille.est_prorata,
            'nb_jours_feries_gardien': grille.nb_jours_feries_gardien,
            'a_travaille_1er_mai': grille.a_travaille_1er_mai,
            'montant_majoration_1er_mai': str(grille.montant_majoration_1er_mai),
            'nb_heures_remplacement_gardien': str(grille.nb_heures_remplacement_gardien),
            'nb_heures_nuit_gardien': str(grille.nb_heures_nuit_gardien),
            'nb_heures_dimanche_gardien': str(grille.nb_heures_dimanche_gardien),
            'nb_heures_feries_gardien': str(grille.nb_heures_feries_gardien),
            'nb_heures_1er_mai_gardien': str(grille.nb_heures_1er_mai_gardien),
            'salaire_brut_base': str(salaire_brut_base),  #  Récupéré depuis contrat si besoin
            'salaire_brut_total': str(grille.salaire_brut_total),
            'charge_cnaps_employe': str(grille.charge_cnaps_employe),
            'irsa': str(grille.irsa),
            'mutuelle_sante': str(grille.mutuelle_sante),
            'salaire_net': str(grille.salaire_net),
            'salaires_count': grille.nb_salaires  #  Compte réel des paiements liés
        })

    return JsonResponse(data, safe=False)


@csrf_exempt
@require_http_methods(["POST"])
def api_calculer_grille_preview(request):
    """
    API pour calculer une grille de salaire en temps réel (prévisualisation).
    Retourne tous les champs calculés sans sauvegarder en base.
    """
    import json
    from decimal import Decimal, ROUND_HALF_UP
    from apps.employees.models import ConfigSalaire, ConfigTrancheIRSA, Contrat

    try:
        data = json.loads(request.body)

        # Récupérer les paramètres
        contrat_id = data.get('contrat_id')

        #  Validation: contrat_id obligatoire
        if not contrat_id:
            return JsonResponse({
                'success': False,
                'error': 'contrat_id est requis'
            }, status=400)

        salaire_brut_base = Decimal(str(data.get('salaire_brut_base', 0)))
        personnes_charge = int(data.get('personnes_charge', 0))
        nb_jours_presence = int(data.get('nb_jours_presence', 0))
        est_prorata = bool(data.get('est_prorata', False))
        nb_jours_feries_gardien = int(data.get('nb_jours_feries_gardien', 0))
        a_travaille_1er_mai = bool(data.get('a_travaille_1er_mai'))
        nb_heures_remplacement_gardien = Decimal(str(data.get('nb_heures_remplacement_gardien', 0)))

        # Récupérer le contrat pour déterminer le type
        try:
            contrat = Contrat.objects.select_related('employe__poste').get(id=contrat_id)
        except Contrat.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'Contrat avec ID {contrat_id} introuvable'
            }, status=404)
        type_contrat = contrat.type_contrat

        # Vérifier si c'est un poste de gardien
        poste_nom = contrat.employe.poste.nom_poste if contrat.employe.poste else ""
        est_gardien = "gardien" in poste_nom.lower()

        # Récupérer la config
        config = ConfigSalaire.get_config()
        salaire_minimum = config.salaire_minimum
        deduction_irsa = config.deduction_irsa
        minimum_irsa = config.minimum_irsa

        # Initialiser les r??sultats
        result = {}

        from datetime import date as dt_date
        from apps.employees.models import GrilleSalaire

        date_salaire_raw = data.get('date_salaire')
        date_salaire = None
        if date_salaire_raw:
            try:
                date_salaire = dt_date.fromisoformat(str(date_salaire_raw))
            except ValueError:
                date_salaire = None

        temp_grille = GrilleSalaire(
            contrat=contrat,
            date_salaire=date_salaire or dt_date.today(),
            personnes_charge=personnes_charge,
            salaire_brut_base=salaire_brut_base,
            nb_jours_presence=nb_jours_presence,
            est_prorata=est_prorata,
            nb_jours_feries_gardien=nb_jours_feries_gardien,
            nb_dimanches_travailles=int(data.get('nb_dimanches_travailles', 0) or 0),
            a_travaille_1er_mai=a_travaille_1er_mai,
            nb_heures_remplacement_gardien=nb_heures_remplacement_gardien,
        )
        temp_grille.calculer_tous_les_champs()

        majoration_nuit = Decimal(str(temp_grille.majoration_nuit_gardien))
        majoration_dimanche = Decimal(str(temp_grille.majoration_dimanche_gardien))
        montant_jours_feries = Decimal(str(temp_grille.montant_jours_feries_gardien))
        montant_majoration_1er_mai = Decimal(str(temp_grille.montant_majoration_1er_mai))
        montant_remplacement = Decimal(str(temp_grille.montant_remplacement_gardien))
        salaire_brut_total = Decimal(str(temp_grille.salaire_brut_total))
        est_journalier = type_contrat.lower() == 'journalier'

        result['majoration_nuit_gardien'] = float(majoration_nuit)
        result['majoration_dimanche_gardien'] = float(majoration_dimanche)
        result['montant_jours_feries_gardien'] = float(montant_jours_feries)
        result['montant_majoration_1er_mai'] = float(montant_majoration_1er_mai)
        result['montant_remplacement_gardien'] = float(montant_remplacement)
        result['nb_dimanches_travailles'] = int(temp_grille.nb_dimanches_travailles or 0)
        result['a_travaille_1er_mai'] = bool(temp_grille.a_travaille_1er_mai)
        result['nb_jours_feries_gardien'] = int(temp_grille.nb_jours_feries_gardien or 0)
        result['nb_heures_nuit_gardien'] = float(temp_grille.nb_heures_nuit_gardien or 0)
        result['nb_heures_dimanche_gardien'] = float(temp_grille.nb_heures_dimanche_gardien or 0)
        result['nb_heures_feries_gardien'] = float(temp_grille.nb_heures_feries_gardien or 0)
        result['nb_heures_1er_mai_gardien'] = float(temp_grille.nb_heures_1er_mai_gardien or 0)
        result['nb_heures_remplacement_gardien'] = float(temp_grille.nb_heures_remplacement_gardien or 0)
        result['taux_horaire_gardien'] = float(salaire_brut_base / Decimal('240')) if est_gardien else 0
        result['taux_horaire_majoration'] = float(
            salaire_brut_base / (Decimal('240') if est_gardien else Decimal('173.33'))
        )

        result['salaire_brut_total'] = float(salaire_brut_total)

        # Les champs suivants sont deja calcules par temp_grille.calculer_tous_les_champs()
        # (CNaPS, mutuelle, base imposable arrondie a 100 Ar pres par valeur inferieure,
        # IRSA, salaire net). On les reutilise directement pour rester coherent avec le
        # moteur central, au lieu de dupliquer la logique de calcul ici.
        plafond_cnaps = Decimal('8') * salaire_minimum
        result['plafond_cnaps'] = float(plafond_cnaps)
        result['charge_cnaps_employe'] = float(temp_grille.charge_cnaps_employe)
        result['mutuelle_sante'] = float(temp_grille.mutuelle_sante)
        result['base_imposable'] = float(temp_grille.base_imposable)
        result['deduction_impots'] = float(temp_grille.deduction_impots)
        result['irsa'] = float(temp_grille.irsa)
        result['salaire_net'] = float(temp_grille.salaire_net)

        # Infos config
        result['config'] = {
            'salaire_minimum': float(salaire_minimum),
            'deduction_irsa': float(deduction_irsa),
            'minimum_irsa': float(minimum_irsa),
            'type_contrat': type_contrat,
            'poste': poste_nom,
            'est_gardien': est_gardien,
            'est_journalier': est_journalier,
            'utilise_majorations_planning': temp_grille.utilise_majorations_planning,
        }

        return JsonResponse({
            'success': True,
            'calculs': result
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def api_calculer_brut_depuis_net(request):
    """
    API pour calculer le salaire brut nécessaire Ã  partir d'un salaire net cible.
    Utilise une méthode itérative pour trouver le salaire brut optimal.
    """
    import json
    from decimal import Decimal, ROUND_HALF_UP
    from apps.employees.models import ConfigSalaire, ConfigTrancheIRSA, Contrat

    try:
        data = json.loads(request.body)

        # Récupérer les paramètres
        contrat_id = data.get('contrat_id')
        salaire_net_cible = Decimal(str(data.get('salaire_net_cible', 0)))

        if not contrat_id:
            return JsonResponse({
                'success': False,
                'error': 'contrat_id est requis'
            }, status=400)

        if salaire_net_cible <= 0:
            return JsonResponse({
                'success': False,
                'error': 'salaire_net_cible doit être supérieur Ã  0'
            }, status=400)

        personnes_charge = int(data.get('personnes_charge', 0))
        nb_jours_presence = int(data.get('nb_jours_presence', 0))
        est_prorata = bool(data.get('est_prorata', False))
        nb_jours_feries_gardien = int(data.get('nb_jours_feries_gardien', 0))
        a_travaille_1er_mai = bool(data.get('a_travaille_1er_mai'))
        nb_heures_remplacement_gardien = Decimal(str(data.get('nb_heures_remplacement_gardien', 0)))

        # Récupérer le contrat
        try:
            contrat = Contrat.objects.select_related('employe__poste').get(id=contrat_id)
        except Contrat.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'Contrat avec ID {contrat_id} introuvable'
            }, status=404)

        # Fonction de calcul du salaire net ???? partir du brut
        from datetime import date as dt_date
        from apps.employees.models import GrilleSalaire

        date_salaire_raw = data.get('date_salaire')
        date_salaire = None
        if date_salaire_raw:
            try:
                date_salaire = dt_date.fromisoformat(str(date_salaire_raw))
            except ValueError:
                date_salaire = None

        preview_grille = GrilleSalaire(
            contrat=contrat,
            date_salaire=date_salaire or dt_date.today(),
            personnes_charge=personnes_charge,
            salaire_brut_base=Decimal('0'),
            nb_jours_presence=nb_jours_presence,
            est_prorata=est_prorata,
            nb_jours_feries_gardien=nb_jours_feries_gardien,
            nb_dimanches_travailles=0,
            a_travaille_1er_mai=a_travaille_1er_mai,
            nb_heures_remplacement_gardien=nb_heures_remplacement_gardien,
        )
        brut_estime = _solve_gross_from_net_exact(preview_grille, salaire_net_cible)
        brut_estime = _pick_best_integer_gross(preview_grille, brut_estime, salaire_net_cible)
        preview_grille.salaire_brut_base = brut_estime
        snapshot = _compute_simulation_snapshot(preview_grille)

        return JsonResponse({
            'success': True,
            'salaire_brut_base': float(brut_estime),
            'salaire_net_obtenu': float(snapshot['salaire_net_exact']),
            'salaire_net_arrondi': float(snapshot['salaire_net_arrondi']),
            'ecart': float(salaire_net_cible - snapshot['salaire_net_exact']),
            'iterations': 0
        })

        def calculer_net(brut_base):
            preview_grille = GrilleSalaire(
                contrat=contrat,
                date_salaire=date_salaire or dt_date.today(),
                personnes_charge=personnes_charge,
                salaire_brut_base=brut_base,
                nb_jours_presence=nb_jours_presence,
                est_prorata=est_prorata,
                nb_jours_feries_gardien=nb_jours_feries_gardien,
                nb_dimanches_travailles=0,
                a_travaille_1er_mai=a_travaille_1er_mai,
                nb_heures_remplacement_gardien=nb_heures_remplacement_gardien,
            )
            preview_grille.calculer_tous_les_champs()
            return Decimal(str(preview_grille.salaire_net))

        # Méthode itérative pour trouver le salaire brut
        # Estimation initiale : salaire_net_cible * 1.2 (approximation)
        brut_estime = salaire_net_cible * Decimal('1.2')

        # Itérations pour converger vers la solution
        tolerance = Decimal('100')  # Tolérance de 100 Ar
        max_iterations = 50

        for i in range(max_iterations):
            net_calcule = calculer_net(brut_estime)
            ecart = salaire_net_cible - net_calcule

            # Si l'écart est acceptable, on arrête
            if abs(ecart) < tolerance:
                break

            # Ajuster le brut estimé proportionnellement Ã  l'écart
            # Si net_calcule < cible, il faut augmenter le brut
            # Si net_calcule > cible, il faut diminuer le brut
            facteur_ajustement = Decimal('1.15') if est_gardien or est_journalier else Decimal('1.18')
            brut_estime += ecart * facteur_ajustement

        # Vérification finale
        net_final = calculer_net(brut_estime)

        return JsonResponse({
            'success': True,
            'salaire_brut_base': float(brut_estime),
            'salaire_net_obtenu': float(net_final),
            'ecart': float(salaire_net_cible - net_final),
            'iterations': i + 1
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


def api_salaires(request, grille_id):
    """API pour charger les salaires d'une grille"""
    salaires = Salaire.objects.filter(
        grille_salaire_id=grille_id
    ).order_by('-date_paiement')

    data = []
    for salaire in salaires:
        data.append({
            'id': str(salaire.id),
            'date_paiement': str(salaire.date_paiement),
            'salaire_net_paye': str(salaire.salaire_net_paye),
            'irsa_paye': str(salaire.irsa_paye),
            'cnaps_paye': str(salaire.cnaps_paye),
            'fmfp_paye': str(salaire.fmfp_paye),
            'mutuelle_sante_paye': str(salaire.mutuelle_sante_paye),
            # Champs DiameX optionnels
            'numero_diamex_salaire': salaire.numero_diamex_salaire or '',
            'base_diamex_salaire': salaire.base_diamex_salaire or '',
            'numero_diamex_irsa': salaire.numero_diamex_irsa or '',
            'base_diamex_irsa': salaire.base_diamex_irsa or '',
            'numero_diamex_cnaps': salaire.numero_diamex_cnaps or '',
            'base_diamex_cnaps': salaire.base_diamex_cnaps or '',
            'numero_diamex_fmfp': salaire.numero_diamex_fmfp or '',
            'base_diamex_fmfp': salaire.base_diamex_fmfp or '',
            'numero_diamex_mutuelle_sante': salaire.numero_diamex_mutuelle_sante or '',
            'base_diamex_mutuelle_sante': salaire.base_diamex_mutuelle_sante or ''
        })

    return JsonResponse(data, safe=False)


def api_update(request):
    """API pour modifier un élément"""
    if request.method == 'POST':
        entity_type = request.POST.get('type')
        entity_id = request.POST.get('id')

        try:
            if entity_type == 'employe':
                employe = get_object_or_404(Employe, pk=entity_id)
                form = EmployeForm(request.POST, instance=employe)
                if form.is_valid():
                    form.save()
                    return JsonResponse({
                        'success': True,
                        'message': 'Employé modifié avec succès!'
                    })
                else:
                    return JsonResponse({
                        'success': False,
                        'message': 'Erreur dans le formulaire',
                        'errors': dict(form.errors)
                    })

            elif entity_type == 'contrat':
                contrat = get_object_or_404(Contrat, pk=entity_id)

                # Sauvegarder la valeur existante du salaire brut
                ancien_salaire = contrat.salaire_brut_base

                # Vérifier si le salaire est dans le POST
                salaire_post = request.POST.get('salaire_brut_base', '').strip()

                form = ContratForm(request.POST, instance=contrat)
                if form.is_valid():
                    contrat_updated = form.save(commit=False)

                    # Restaurer l'ancien salaire SEULEMENT si le POST était vide
                    # Si l'utilisateur a saisi une nouvelle valeur (même 0), on la garde
                    if not salaire_post and ancien_salaire is not None:
                        contrat_updated.salaire_brut_base = ancien_salaire

                    contrat_updated.save()
                    return JsonResponse({
                        'success': True,
                        'message': 'Contrat modifié avec succès!'
                    })
                else:
                    return JsonResponse({
                        'success': False,
                        'message': 'Erreur dans le formulaire',
                        'errors': dict(form.errors)
                    })

            elif entity_type == 'grille':
                grille = get_object_or_404(GrilleSalaire, pk=entity_id)
                form = GrilleSalaireForm(request.POST, instance=grille)
                if form.is_valid():
                    form.save()
                    return JsonResponse({
                        'success': True,
                        'message': 'Grille de salaire modifiée avec succès!'
                    })
                else:
                    return JsonResponse({
                        'success': False,
                        'message': 'Erreur dans le formulaire',
                        'errors': dict(form.errors)
                    })

            elif entity_type == 'salaire':
                salaire = get_object_or_404(Salaire, pk=entity_id)
                form = SalaireForm(request.POST, instance=salaire)
                if form.is_valid():
                    form.save()
                    return JsonResponse({
                        'success': True,
                        'message': 'Salaire modifié avec succès!'
                    })
                else:
                    return JsonResponse({
                        'success': False,
                        'message': 'Erreur dans le formulaire',
                        'errors': dict(form.errors)
                    })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur : {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


def api_delete(request):
    """API pour supprimer un élément"""
    if request.method == 'POST':
        if request.content_type == 'application/json':
            import json
            try:
                payload = json.loads(request.body or '{}')
            except json.JSONDecodeError:
                payload = {}
            entity_type = payload.get('type')
            entity_id = payload.get('id')
        else:
            entity_type = request.POST.get('type')
            entity_id = request.POST.get('id')

        try:
            if entity_type == 'employe':
                employe = get_object_or_404(Employe, pk=entity_id)
                employe.delete()
                return JsonResponse({
                    'success': True,
                    'message': 'Employé supprimé avec succès!'
                })

            elif entity_type == 'contrat':
                contrat = get_object_or_404(Contrat, pk=entity_id)
                contrat.delete()
                return JsonResponse({
                    'success': True,
                    'message': 'Contrat supprimé avec succès!'
                })

            elif entity_type == 'grille':
                grille = get_object_or_404(GrilleSalaire, pk=entity_id)
                grille.delete()
                return JsonResponse({
                    'success': True,
                    'message': 'Grille de salaire supprimée avec succès!'
                })

            elif entity_type == 'salaire':
                salaire = get_object_or_404(Salaire, pk=entity_id)
                salaire.delete()
                return JsonResponse({
                    'success': True,
                    'message': 'Salaire supprimé avec succès!'
                })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur : {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisé'})


# API pour modales d'édition
@employe_required
def employe_form_api(request, pk):
    """API pour charger le formulaire d'édition d'employé dans une modale"""
    try:
        employe = get_object_or_404(Employe, pk=pk)

        # Si on demande du JSON, retourner les données au format JSON
        if request.headers.get('Accept') == 'application/json' or request.GET.get('format') == 'json':
            return JsonResponse({
                'id': str(employe.id),
                'nom': employe.nom,
                'prenom': employe.prenom,
                'surnom': employe.surnom,
                'telephone': employe.telephone,
                'mail': employe.mail,
                'numero_cin': employe.numero_cin,
                'lieu_delivrance_cin': employe.lieu_delivrance_cin,
                'date_delivrance_cin': str(employe.date_delivrance_cin) if employe.date_delivrance_cin else '',
                'numero_cnaps': employe.numero_cnaps,
                'code_tiers': employe.code_tiers,
                'personnes_charge': employe.personnes_charge,
                'genre': employe.genre if employe.genre else '',
                'date_naissance': str(employe.date_naissance) if employe.date_naissance else '',
                'lieu_naissance': employe.lieu_naissance,
                'adresse': employe.adresse,
                'mutuelle_sante': employe.mutuelle_sante if employe.mutuelle_sante else '',
                'date_embauche': str(employe.date_embauche) if employe.date_embauche else '',
                'date_debauchage': str(employe.date_debauchage) if employe.date_debauchage else '',
                'salarie': employe.salarie,
                'base_id': str(employe.base.id) if employe.base else None,
                'poste_id': str(employe.poste.id) if employe.poste else None,
            })

        # Sinon retourner le HTML du formulaire
        form = EmployeForm(instance=employe)
        return render(request, 'employees/employe_form_modal.html', {
            'form': form,
            'employe': employe
        })
    except Exception as e:
        if request.headers.get('Accept') == 'application/json' or request.GET.get('format') == 'json':
            return JsonResponse({
                'error': f'Erreur lors du chargement de l\'employé: {str(e)}'
            }, status=404)
        return render(request, 'employees/employe_form_modal.html', {
            'error': f'Erreur lors du chargement de l\'employé: {str(e)}'
        })


@employe_required
def employe_update_api(request, pk):
    """API pour sauvegarder les modifications d'employé depuis une modale"""
    if request.method == 'POST':
        try:
            employe = get_object_or_404(Employe, pk=pk)

            # DEBUG: Collecte des informations de debug
            poste_avant = str(employe.poste_id) if employe.poste_id else None
            poste_recu = request.POST.get('poste')

            form = EmployeForm(request.POST, instance=employe)

            if form.is_valid():
                saved_employe = form.save()
                poste_apres = str(saved_employe.poste_id) if saved_employe.poste_id else None

                # Convertir l'objet Poste en UUID string pour la sérialisation JSON
                poste_obj = form.cleaned_data.get('poste')
                poste_dans_form = str(poste_obj.id) if poste_obj else None

                return JsonResponse({
                    'success': True,
                    'message': 'Employé modifié avec succès!',
                    'debug': {
                        'poste_avant': poste_avant,
                        'poste_recu': poste_recu,
                        'poste_apres': poste_apres,
                        'poste_dans_form_data': poste_dans_form
                    }
                })
            else:
                return JsonResponse({
                    'success': False,
                    'errors': form.errors,
                    'message': 'Erreurs dans le formulaire',
                    'debug': {
                        'poste_avant': poste_avant,
                        'poste_recu': poste_recu,
                        'form_errors': str(form.errors)
                    }
                })
        except Exception as e:
            import traceback
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la sauvegarde: {str(e)}',
                'debug': {
                    'exception': str(e),
                    'traceback': traceback.format_exc()
                }
            })

    return JsonResponse({
        'success': False,
        'message': 'Méthode non autorisée'
    })


@employe_required
def positions_gps_list(request):
    """Page de gestion des positions GPS des employés"""

    # Récupérer les paramètres de recherche
    search_query = request.GET.get('search', '')
    date_debut = request.GET.get('date_debut', '')
    date_fin = request.GET.get('date_fin', '')
    employe_id = request.GET.get('employe', '')
    village_id = request.GET.get('village', '')
    type_connexion = request.GET.get('type_connexion', '')

    # Requête de base
    positions = PositionGPSEmploye.objects.select_related(
        'employe__poste',
        'employe__base',
        'village_proche__fokontany__commune'
    ).all()

    # Appliquer les filtres
    if search_query:
        positions = positions.filter(
            Q(employe__surnom__icontains=search_query) |
            Q(employe__poste__nom_poste__icontains=search_query) |
            Q(village_proche__nom_village__icontains=search_query)
        )

    if date_debut:
        positions = positions.filter(date_enregistrement__gte=date_debut)

    if date_fin:
        date_fin_obj = datetime.strptime(date_fin, '%Y-%m-%d')
        date_fin_obj = date_fin_obj.replace(hour=23, minute=59, second=59)
        positions = positions.filter(date_enregistrement__lte=date_fin_obj)

    if employe_id:
        positions = positions.filter(employe_id=employe_id)

    if village_id:
        positions = positions.filter(village_proche_id=village_id)

    if type_connexion:
        positions = positions.filter(type_connexion=type_connexion)

    # Ordonner par date décroissante
    positions = positions.order_by('-date_enregistrement')

    # Calculer les statistiques AVANT de convertir en liste
    stats = {}
    stats['total_positions'] = positions.count()

    # Calculer la durée de connexion pour chaque position
    # (temps jusqu'Ã  la prochaine position du même employé)
    positions_list = list(positions[:100])  # Limiter Ã  100 pour la performance
    for i, pos in enumerate(positions_list):
        # Trouver la position suivante du même employé
        next_pos = PositionGPSEmploye.objects.filter(
            employe=pos.employe,
            date_enregistrement__gt=pos.date_enregistrement
        ).order_by('date_enregistrement').first()

        if next_pos:
            duree = next_pos.date_enregistrement - pos.date_enregistrement
            pos.duree_connexion = duree
        else:
            pos.duree_connexion = None

    positions_display = positions_list

    # Nombre d'employés uniques
    stats['total_employes'] = positions.values('employe').distinct().count()

    # Positions aujourd'hui
    today = datetime.now().date()
    stats['positions_today'] = positions.filter(date_enregistrement__date=today).count()

    # Positions cette semaine
    week_ago = datetime.now() - timedelta(days=7)
    stats['positions_week'] = positions.filter(date_enregistrement__gte=week_ago).count()

    # Positions ce mois
    month_ago = datetime.now() - timedelta(days=30)
    stats['positions_month'] = positions.filter(date_enregistrement__gte=month_ago).count()

    # Répartition par type de connexion
    stats['by_type'] = list(positions.values('type_connexion').annotate(
        count=Count('id')
    ).order_by('-count'))

    # Top 5 employés par nombre de connexions
    stats['top_employes'] = list(positions.values(
        'employe__surnom',
        'employe__poste__nom_poste'
    ).annotate(
        count=Count('id')
    ).order_by('-count')[:5])

    # Top 5 villages les plus proches
    stats['top_villages'] = list(positions.filter(
        village_proche__isnull=False
    ).values(
        'village_proche__nom_village',
        'village_proche__fokontany__nom_fokontany'
    ).annotate(
        count=Count('id')
    ).order_by('-count')[:5])

    # Positions hors zone (>10 km)
    stats['hors_zone'] = positions.filter(est_hors_zone=True).count()

    # Distance moyenne au village le plus proche
    stats['avg_distance'] = positions.filter(
        distance_village__isnull=False
    ).aggregate(Avg('distance_village'))['distance_village__avg']

    if stats['avg_distance']:
        stats['avg_distance'] = round(stats['avg_distance'], 2)

    # Connexions par jour (7 derniers jours)
    stats['by_day'] = list(positions.filter(
        date_enregistrement__gte=week_ago
    ).annotate(
        day=TruncDate('date_enregistrement')
    ).values('day').annotate(
        count=Count('id')
    ).order_by('day'))

    # Liste des employés pour le filtre
    employes_list = Employe.objects.filter(
        id__in=positions.values('employe_id').distinct()
    ).select_related('poste').order_by('surnom')

    # Liste des villages pour le filtre
    from apps.geography.models import Village
    villages_list = Village.objects.filter(
        id__in=positions.values('village_proche_id').distinct()
    ).select_related('fokontany').order_by('nom_village')

    # Types de connexion - récupérer depuis le field
    types_connexion = PositionGPSEmploye._meta.get_field('type_connexion').choices

    context = {
        'title': 'Positions GPS des Employés',
        'positions': positions_display,  # Liste avec durée de connexion calculée
        'stats': stats,
        'employes_list': employes_list,
        'villages_list': villages_list,
        'types_connexion': types_connexion,
        'search_query': search_query,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'selected_employe': employe_id,
        'selected_village': village_id,
        'selected_type': type_connexion,
    }

    return render(request, 'employees/positions_gps_list.html', context)


@employe_required
def positions_gps_map(request):
    """Page carte interactive dédiée pour les positions GPS"""

    # Requête de base pour les positions avec GPS
    base_query = PositionGPSEmploye.objects.filter(
        latitude__isnull=False,
        longitude__isnull=False
    )

    # Récupérer les positions pour l'affichage (limitées Ã  500)
    positions = base_query.select_related(
        'employe__poste',
        'employe__base',
        'village_proche__fokontany'
    ).order_by('-date_enregistrement')[:500]

    # Donnees JSON-safe pour la carte (evite les erreurs JS de formatage localise)
    positions_data = []
    for position in positions:
        if position.latitude is None or position.longitude is None:
            continue
        positions_data.append({
            'lat': float(position.latitude),
            'lon': float(position.longitude),
            'surnom': (position.employe.surnom if position.employe and position.employe.surnom else '-'),
            'poste': (
                position.employe.poste.nom_poste
                if position.employe and getattr(position.employe, 'poste', None)
                else '-'
            ),
            'base': (
                position.employe.base.nom_base
                if position.employe and getattr(position.employe, 'base', None)
                else '-'
            ),
            'village': (position.village_proche.nom_village if position.village_proche else '-'),
            'fokontany': (
                position.village_proche.fokontany.nom_fokontany
                if position.village_proche and getattr(position.village_proche, 'fokontany', None)
                else '-'
            ),
            'distance': float(position.distance_village) if position.distance_village is not None else None,
            'type': position.get_type_connexion_display(),
            'date': position.date_enregistrement.strftime('%d/%m/%Y %H:%M:%S') if position.date_enregistrement else '-',
            'altitude': float(position.altitude) if position.altitude is not None else None,
            'ip': position.adresse_ip or '-',
        })

    def _extract_first_photo_url(photos):
        if not photos:
            return None
        if isinstance(photos, list) and len(photos) > 0:
            first = photos[0]
            if isinstance(first, dict):
                return first.get('data') or first.get('url') or first.get('path')
            if isinstance(first, str):
                return first
        return None

    # Points d'eau avec coordonnées GPS
    points_eau_qs = PointEau.objects.filter(
        latitude__isnull=False,
        longitude__isnull=False
    ).select_related(
        'ouvrage',
        'type_point_eau',
        'parcelle__village__fokontany__commune'
    ).order_by('-updatedat')[:1500]

    points_eau_data = []
    for point in points_eau_qs:
        village_nom = '-'
        commune_nom = '-'
        try:
            if point.parcelle and point.parcelle.village:
                village_nom = point.parcelle.village.nom_village or '-'
                if point.parcelle.village.fokontany and point.parcelle.village.fokontany.commune:
                    commune_nom = point.parcelle.village.fokontany.commune.nom_commune or '-'
        except Exception:
            pass

        points_eau_data.append({
            'id': str(point.id),
            'lat': float(point.latitude),
            'lon': float(point.longitude),
            'code': point.code_point_eau or '-',
            'nom': point.nomabonne or '-',
            'type': point.type_point_eau.nom_type if point.type_point_eau else '-',
            'ouvrage': point.ouvrage.nom_ouvrage if point.ouvrage else '-',
            'village': village_nom,
            'commune': commune_nom,
            'telephone': point.numeroteleph or '-',
            'photo_url': _extract_first_photo_url(point.photos),
        })

    # Equipements avec coordonnées GPS
    equipements_qs = EquipementConstitutif.objects.filter(
        latitude__isnull=False,
        longitude__isnull=False
    ).select_related(
        'ouvrage',
        'type_equipement'
    ).order_by('-updated_at')[:1500]

    equipements_data = []
    for eq in equipements_qs:
        equipements_data.append({
            'id': str(eq.id),
            'lat': float(eq.latitude),
            'lon': float(eq.longitude),
            'nom': eq.nom or '-',
            'code': eq.code_equipement or '-',
            'type': eq.type_equipement.nom_type if eq.type_equipement else '-',
            'ouvrage': eq.ouvrage.nom_ouvrage if eq.ouvrage else '-',
            'statut': eq.statut or '-',
            'photo_url': _extract_first_photo_url(eq.photos),
        })

    # Statistiques basiques pour l'en-tête (sur la requête non slicée)
    from datetime import datetime
    today = datetime.now().date()

    stats = {
        'total_employes': base_query.values('employe').distinct().count(),
        'positions_today': base_query.filter(date_enregistrement__date=today).count(),
        'avg_distance': base_query.filter(
            distance_village__isnull=False
        ).aggregate(Avg('distance_village'))['distance_village__avg']
    }

    if stats['avg_distance']:
        stats['avg_distance'] = round(stats['avg_distance'], 2)

    context = {
        'title': 'Carte Interactive GPS',
        'positions': positions,
        'positions_data': positions_data,
        'points_eau_data': points_eau_data,
        'equipements_data': equipements_data,
        'stats': stats,
    }

    return render(request, 'employees/positions_gps_map.html', context)



@employe_required
def test_gps_page(request):
    """Page de diagnostic pour tester la capture GPS"""
    return render(request, 'test_gps.html')

def capture_gps_position(request):
    """API pour capturer la position GPS envoyée depuis le frontend"""
    if request.method == 'POST':
        import json

        # Vérifier l'authentification sans redirection
        if not request.user.is_authenticated:
            return JsonResponse({
                'success': False,
                'message': 'Non authentifié'
            }, status=401)

        # Récupérer l'employé
        employe = None
        if hasattr(request.user, 'employe') and request.user.employe:
            employe = request.user.employe

        if not employe and not request.user.is_superuser:
            return JsonResponse({
                'success': False,
                'message': 'Aucun employé lié Ã  votre compte'
            }, status=403)

        try:
            data = json.loads(request.body)

            # Récupérer les données GPS
            latitude = data.get('latitude')
            longitude = data.get('longitude')
            altitude = data.get('altitude')
            precision = data.get('precision')

            if not latitude or not longitude:
                return JsonResponse({
                    'success': False,
                    'message': 'Latitude et longitude requis'
                }, status=400)

            # Bornes des colonnes (DecimalField) : sur PC sans GPS, la geolocalisation
            # par reseau renvoie une precision de plusieurs dizaines de km (> 99 999,99 m)
            # qui faisait deborder la colonne -> 500.
            def _borne(valeur, maxi, decimales):
                try:
                    v = round(float(valeur), decimales)
                except (TypeError, ValueError):
                    return None
                return max(-maxi, min(maxi, v))

            # Créer l'enregistrement de position
            position = PositionGPSEmploye.objects.create(
                employe=employe,
                latitude=_borne(latitude, 90, 7),
                longitude=_borne(longitude, 180, 7),
                altitude=_borne(altitude, 99999.99, 2),
                precision=_borne(precision, 99999.99, 2),
                type_connexion='login',
                adresse_ip=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500]
            )

            # Calculer le village proche
            position.calculer_village_proche()
            position.save()

            # Retirer le flag de la session
            if 'awaiting_gps' in request.session:
                del request.session['awaiting_gps']

            return JsonResponse({
                'success': True,
                'message': 'Position GPS enregistrée',
                'village_proche': position.village_proche.nom_village if position.village_proche else None,
                'distance': float(position.distance_village) if position.distance_village else None,
                'est_hors_zone': position.est_hors_zone,
                'message_zone': 'Attention: vous êtes Ã  plus de 10 km du village le plus proche' if position.est_hors_zone else None
            })

        except Exception as e:
            import logging
            logging.getLogger('django.request').exception('capture_gps_position a echoue')
            return JsonResponse({
                'success': False,
                'message': f'Erreur: {str(e)}'
            }, status=500)

    return JsonResponse({
        'success': False,
        'message': 'Méthode non autorisée'
    }, status=405)


# ===================================
# API CRUD pour Bases DiameX (en cascade sous employé)
# ===================================

@require_http_methods(["GET"])
def api_bases_diamex(request, employe_id):
    """API pour récupérer les bases DiameX d'un employé"""
    from apps.employees.models import EmployeBaseDiameX

    bases = EmployeBaseDiameX.objects.filter(employe_id=employe_id).order_by('base_diamex')

    data = [{
        'id': str(base.id),
        'base_diamex': base.base_diamex,
        'chemin_base_diamex': base.chemin_base_diamex,
        'created_at': base.created_at.strftime('%Y-%m-%d %H:%M') if base.created_at else None,
    } for base in bases]

    return JsonResponse({'success': True, 'bases_diamex': data})


@require_http_methods(["POST"])
def api_base_diamex_create(request):
    """API pour créer une base DiameX"""
    from apps.employees.models import EmployeBaseDiameX, Employe

    try:
        employe_id = request.POST.get('employe_id')
        base_diamex = request.POST.get('base_diamex', '').strip()
        chemin_base_diamex = request.POST.get('chemin_base_diamex', '').strip()

        if not all([employe_id, base_diamex, chemin_base_diamex]):
            return JsonResponse({
                'success': False,
                'message': 'Tous les champs sont requis'
            }, status=400)

        employe = Employe.objects.get(id=employe_id)

        # Vérifier l'unicité
        if EmployeBaseDiameX.objects.filter(employe=employe, base_diamex=base_diamex).exists():
            return JsonResponse({
                'success': False,
                'message': f'Cette base DiameX existe déjÃ  pour {employe.surnom or employe.nom_employe}'
            }, status=400)

        base = EmployeBaseDiameX.objects.create(
            employe=employe,
            base_diamex=base_diamex,
            chemin_base_diamex=chemin_base_diamex
        )

        return JsonResponse({
            'success': True,
            'message': f'Base DiameX "{base_diamex}" créée',
            'base': {
                'id': str(base.id),
                'base_diamex': base.base_diamex,
                'chemin_base_diamex': base.chemin_base_diamex,
            }
        })

    except Employe.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Employé non trouvé'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur: {str(e)}'
        }, status=500)


@require_http_methods(["POST"])
def api_base_diamex_update(request, pk):
    """API pour mettre Ã  jour une base DiameX"""
    from apps.employees.models import EmployeBaseDiameX

    try:
        base = EmployeBaseDiameX.objects.get(id=pk)

        base_diamex = request.POST.get('base_diamex', '').strip()
        chemin_base_diamex = request.POST.get('chemin_base_diamex', '').strip()

        if not all([base_diamex, chemin_base_diamex]):
            return JsonResponse({
                'success': False,
                'message': 'Tous les champs sont requis'
            }, status=400)

        # Vérifier l'unicité (exclure l'enregistrement actuel)
        if EmployeBaseDiameX.objects.filter(
            employe=base.employe,
            base_diamex=base_diamex
        ).exclude(id=pk).exists():
            return JsonResponse({
                'success': False,
                'message': f'Cette base DiameX existe déjÃ  pour {base.employe.surnom or base.employe.nom_employe}'
            }, status=400)

        base.base_diamex = base_diamex
        base.chemin_base_diamex = chemin_base_diamex
        base.save()

        return JsonResponse({
            'success': True,
            'message': f'Base DiameX "{base_diamex}" mise Ã  jour'
        })

    except EmployeBaseDiameX.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Base DiameX non trouvée'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur: {str(e)}'
        }, status=500)


@require_http_methods(["POST"])
def api_base_diamex_delete(request, pk):
    """API pour supprimer une base DiameX"""
    from apps.employees.models import EmployeBaseDiameX

    try:
        base = EmployeBaseDiameX.objects.get(id=pk)
        base_name = base.base_diamex
        base.delete()

        return JsonResponse({
            'success': True,
            'message': f'Base DiameX "{base_name}" supprimée'
        })

    except EmployeBaseDiameX.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Base DiameX non trouvée'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur: {str(e)}'
        }, status=500)


def fiche_paie(request, salaire_id):
    """G?n?re la fiche de paie imprimable pour un salaire donn?"""
    from apps.organization.models import Organisation
    from decimal import Decimal
    import math

    # R?cup?rer le salaire avec toutes les relations
    salaire = get_object_or_404(
        Salaire.objects.select_related(
            'grille_salaire__contrat__employe__base__organisation',
            'grille_salaire__contrat__employe__poste',
            'grille_salaire__contrat'
        ),
        id=salaire_id
    )

    grille = salaire.grille_salaire
    contrat = grille.contrat
    employe = contrat.employe
    organisation = employe.base.organisation if employe.base else None

    est_herizo = (employe.surnom or '').strip().lower() == 'herizo'

    mois_annee_date = salaire.date_paiement
    try:
        planning_details = _get_fiche_paie_planning_details(employe, mois_annee_date)
    except Exception:
        planning_details = {'dimanches': [], 'jours_feries': []}

    # R?cup?rer le directeur de l'organisation
    directeur = None
    if organisation:
        directeur = Employe.objects.filter(
            base__organisation=organisation,
            poste__nom_poste__iexact='directeur'
        ).select_related('poste').first()

        if not directeur:
            directeur = Employe.objects.filter(
                base__organisation=organisation
            ).filter(
                Q(poste__nom_poste__icontains='direction') |
                Q(poste__nom_poste__icontains='responsable')
            ).select_related('poste').first()

        if not directeur:
            directeur = Employe.objects.filter(
                base__organisation=organisation,
                signature__isnull=False
            ).exclude(signature='').select_related('poste').first()

    def nombre_en_lettres(n):
        """Convertit un nombre en toutes lettres en fran?ais"""
        try:
            from num2words import num2words
            montant_int = int(float(n or 0))
            return num2words(montant_int, lang='fr').upper() + " ARIARY"
        except (ImportError, Exception):
            montant_int = int(float(n or 0))
            return f"{montant_int:,} ARIARY".replace(',', ' ')

    salaire_net_lettres = nombre_en_lettres(salaire.salaire_net_paye)

    # Calculer le salaire net arrondi
    salaire_net_arrondi = Decimal(math.ceil(float(grille.salaire_net or 0) / 100) * 100)
    est_journalier = bool(contrat.type_contrat and 'journalier' in contrat.type_contrat.lower())
    salaire_brut_reference = Decimal(str(grille.salaire_brut_base or 0))
    salaire_reference_majoration = (
        salaire_brut_reference
        if est_journalier
        else (salaire_brut_reference / Decimal('30'))
    )
    taux_horaire_gardien = salaire_brut_reference / Decimal('240')
    taux_horaire_autre = salaire_brut_reference / Decimal('173.33')

    context = {
        'salaire': salaire,
        'grille': grille,
        'contrat': contrat,
        'employe': employe,
        'organisation': organisation,
        'directeur': directeur,
        'mois_annee_date': mois_annee_date,
        'salaire_net_lettres': salaire_net_lettres,
        'salaire_net_arrondi': salaire_net_arrondi,
        'est_herizo': est_herizo,
        'est_journalier': est_journalier,
        'est_gardien': bool(employe.poste and employe.poste.nom_poste and 'gardien' in employe.poste.nom_poste.lower()),
        'salaire_reference_majoration': salaire_reference_majoration,
        'taux_horaire_gardien': taux_horaire_gardien,
        'taux_horaire_autre': taux_horaire_autre,
        'planning_details': planning_details,
    }

    return render(request, 'employees/fiche_paie.html', context)


def fiche_indemnite_herizo(request, salaire_id):
    """Fiche s?par?e pour l'indemnit? Herizo"""
    from apps.employees.models import ConfigSalaire
    from decimal import Decimal
    import locale

    salaire = get_object_or_404(
        Salaire.objects.select_related(
            'grille_salaire__contrat__employe__base__organisation',
            'grille_salaire__contrat__employe__poste',
            'grille_salaire__contrat'
        ),
        id=salaire_id
    )

    grille = salaire.grille_salaire
    contrat = grille.contrat
    employe = contrat.employe
    organisation = employe.base.organisation if employe.base else None

    est_herizo = (employe.surnom or '').strip().lower() == 'herizo'
    if not est_herizo:
        return render(request, 'employees/fiche_indemnite_herizo.html', {
            'error': "Cette fiche est r?serv?e ? l'employ? HERIZO."
        })

    config_salaire = ConfigSalaire.get_config()
    indemnite_herizo = config_salaire.indemnite_herizo

    mois_annee_date = salaire.date_paiement

    context = {
        'salaire': salaire,
        'grille': grille,
        'contrat': contrat,
        'employe': employe,
        'organisation': organisation,
        'mois_annee_date': mois_annee_date,
        'indemnite_herizo': Decimal(str(indemnite_herizo)),
    }

    return render(request, 'employees/fiche_indemnite_herizo.html', context)


def fiche_indemnite_herizo_depuis_grille(request, grille_id):
    """Aperçu de la fiche d'indemnité Herizo sans salaire créé en base."""
    from apps.employees.models import ConfigSalaire
    from decimal import Decimal
    from datetime import date
    from types import SimpleNamespace

    grille = get_object_or_404(
        GrilleSalaire.objects.select_related(
            'contrat__employe__base__organisation',
            'contrat__employe__poste',
            'contrat',
        ),
        id=grille_id,
    )

    contrat = grille.contrat
    employe = contrat.employe
    organisation = employe.base.organisation if employe.base else None

    est_herizo = (employe.surnom or '').strip().lower() == 'herizo'
    if not est_herizo:
        return render(request, 'employees/fiche_indemnite_herizo.html', {
            'error': "Cette fiche est réservée à l'employé HERIZO."
        })

    try:
        mois = int(request.GET.get('mois') or 0)
        annee = int(request.GET.get('annee') or 0)
        mois_annee_date = date(annee, mois, 1)
    except (TypeError, ValueError):
        mois_annee_date = grille.date_salaire or timezone.now().date()

    salaire = Salaire.objects.filter(
        grille_salaire__contrat__employe=employe,
        date_paiement__year=mois_annee_date.year,
        date_paiement__month=mois_annee_date.month,
    ).first()

    if salaire:
        mois_annee_date = salaire.date_paiement
    else:
        salaire = SimpleNamespace(date_paiement=mois_annee_date)

    config_salaire = ConfigSalaire.get_config()
    indemnite_herizo = config_salaire.indemnite_herizo

    context = {
        'salaire': salaire,
        'grille': grille,
        'contrat': contrat,
        'employe': employe,
        'organisation': organisation,
        'mois_annee_date': mois_annee_date,
        'indemnite_herizo': Decimal(str(indemnite_herizo)),
    }

    return render(request, 'employees/fiche_indemnite_herizo.html', context)


def fiches_paie_mensuelles(request):
    """Page pour sélectionner et générer les fiches de paie mensuelles pour tous les employés"""
    from apps.organization.models import Base
    from datetime import date

    user_organisation = _get_user_organisation(request.user)

    # Récupérer les bases (cloisonnées sur l'organisation courante, sauf superuser)
    bases = Base.objects.all().select_related('organisation')
    if not getattr(request.user, 'is_superuser', False):
        if user_organisation:
            bases = bases.filter(organisation=user_organisation)
        else:
            bases = bases.none()
    bases = bases.order_by('organisation__nom_organisation', 'nom_base')

    # Mois et année par défaut (mois courant)
    today = date.today()
    mois_defaut = today.month
    annee_defaut = today.year

    context = {
        'bases': bases,
        'mois_defaut': mois_defaut,
        'annee_defaut': annee_defaut,
        'user_organisation': user_organisation,
    }

    return render(request, 'employees/fiches_paie_mensuelles.html', context)


def api_salaires_mensuels(request):
    """API pour obtenir la liste des salaires du mois (cloisonnée sur l'organisation courante)"""
    import json
    from datetime import datetime
    from decimal import Decimal

    try:
        mois = int(request.GET.get('mois', 0))
        annee = int(request.GET.get('annee', 0))
        base_id = request.GET.get('base_id', '').strip()  # Nouveau filtre par base

        # Validation des paramètres
        if not mois or not annee:
            return JsonResponse({
                'success': False,
                'error': 'Mois et année requis'
            }, status=400)

        user_organisation = _get_user_organisation(request.user)
        if not getattr(request.user, 'is_superuser', False) and not user_organisation:
            return JsonResponse({
                'success': False,
                'error': 'Organisation utilisateur introuvable'
            }, status=403)

        # Récupérer tous les employés actifs de l'organisation courante
        employes = Employe.objects.filter(
            salarie=True,
            date_debauchage__isnull=True
        )
        if user_organisation:
            employes = employes.filter(base__organisation=user_organisation)
        elif not getattr(request.user, 'is_superuser', False):
            return JsonResponse({
                'success': False,
                'error': 'Organisation utilisateur introuvable'
            }, status=403)

        # Filtrer par base si spécifié
        if base_id and base_id != 'all':
            employes = employes.filter(base_id=base_id)

        employes = employes.select_related('poste', 'base__organisation').order_by('base__nom_base', 'nom_employe')
        # Preparer les donnees en mode groupe pour eviter le N+1 de requetes
        import math

        employes = list(employes)
        employe_ids = [employe.id for employe in employes]

        contrats_actifs = list(
            Contrat.objects.filter(
                employe_id__in=employe_ids,
                fin_contrat__isnull=True
            )
            .select_related('employe')
            .order_by('employe_id', '-debut_contrat')
        )
        contrat_by_employe = {}
        for contrat in contrats_actifs:
            contrat_by_employe.setdefault(contrat.employe_id, contrat)

        contrat_ids = [contrat.id for contrat in contrat_by_employe.values()]
        grille_counts_qs = (
            GrilleSalaire.objects.filter(contrat_id__in=contrat_ids)
            .values('contrat_id')
            .annotate(total=Count('id'))
        )
        grille_count_by_contrat = {row['contrat_id']: row['total'] for row in grille_counts_qs}

        latest_grilles_qs = list(
            GrilleSalaire.objects.filter(contrat_id__in=contrat_ids)
            .select_related('contrat')
            .order_by('contrat_id', '-date_salaire')
            .distinct('contrat_id')
        )
        latest_grille_by_contrat = {grille.contrat_id: grille for grille in latest_grilles_qs}

        salaires_qs = list(
            Salaire.objects.filter(
                grille_salaire__contrat__employe_id__in=employe_ids,
                date_paiement__year=annee,
                date_paiement__month=mois,
                fiche_imprimee=False,
            )
            .select_related('grille_salaire__contrat__employe')
            .order_by('grille_salaire__contrat__employe_id', '-date_paiement')
            .distinct('grille_salaire__contrat__employe_id')
        )
        salaire_by_employe = {salaire.grille_salaire.contrat.employe_id: salaire for salaire in salaires_qs}

        liste_employes = []
        for employe in employes:
            est_herizo = (employe.surnom or '').strip().lower() == 'herizo'
            contrat_actif = contrat_by_employe.get(employe.id)
            contrat_id = getattr(contrat_actif, 'id', None)
            grille_active = latest_grille_by_contrat.get(contrat_id)
            nb_grilles = grille_count_by_contrat.get(contrat_id, 0)
            salaire_existant = salaire_by_employe.get(employe.id)

            if salaire_existant:
                statut = 'paye'
                salaire_id = str(salaire_existant.id)
                salaire_net = float(salaire_existant.salaire_net_paye) if salaire_existant.salaire_net_paye else 0
                salaire_net_arrondi = math.ceil(salaire_net / 100) * 100
                date_paiement = salaire_existant.date_paiement.strftime('%d/%m/%Y')
            elif grille_active:
                statut = 'a_traiter'
                salaire_id = None
                salaire_net = float(grille_active.salaire_net) if grille_active.salaire_net else 0
                salaire_net_arrondi = math.ceil(salaire_net / 100) * 100
                date_paiement = '-'
            else:
                statut = 'sans_grille'
                salaire_id = None
                salaire_net = 0
                salaire_net_arrondi = 0
                date_paiement = '-'

            liste_employes.append({
                'employe_id': str(employe.id),
                'employe_nom': employe.nom_complet,
                'poste': employe.poste.nom_poste if employe.poste else '-',
                'base': employe.base.nom_base if employe.base else '-',
                'matricule': employe.idxlsx or '-',
                'contrat_id': str(contrat_id) if contrat_id else None,
                'grille_id': str(grille_active.id) if grille_active else None,
                'nb_grilles': nb_grilles,
                'salaire_id': salaire_id,
                'salaire_net': salaire_net,
                'salaire_net_arrondi': salaire_net_arrondi,
                'date_paiement': date_paiement,
                'statut': statut,
                'est_prorata': grille_active.est_prorata if grille_active else False,
                'nb_jours_presence': grille_active.nb_jours_presence if grille_active else 0,
                'est_herizo': est_herizo
            })

        return JsonResponse({
            'success': True,
            'count': len(liste_employes),
            'employes': liste_employes
        })

    except Exception as e:
        import traceback
        print(f"Erreur dans api_salaires_mensuels: {str(e)}")
        print(traceback.format_exc())
        return JsonResponse({
            'success': False,
            'error': f'Erreur serveur: {str(e)}'
        }, status=500)


@csrf_exempt
def api_creer_salaire_depuis_grille(request):
    """API pour créer un salaire depuis une grille existante"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Méthode non autorisée'}, status=405)

    try:
        import json
        from datetime import date
        from django.utils import timezone
    
        data = json.loads(request.body)
        grille_id = data.get('grille_id', '').strip()
        mois = int(data.get('mois', 0))
        annee = int(data.get('annee', 0))

        if not grille_id or not mois or not annee:
            return JsonResponse({
                'success': False,
                'error': 'Paramètres manquants (grille_id, mois, annee)'
            })

        # Récupérer la grille
        try:
            grille = GrilleSalaire.objects.select_related(
                'contrat__employe'
            ).get(id=grille_id)
        except GrilleSalaire.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Grille de salaire introuvable'
            })

        refresh_grille_calculs(grille)
        montant_salaire = expected_salaire_values_from_grille(grille)

        # Vérifier qu'un salaire n'existe pas déjÃ  pour ce mois
        salaire_existant = Salaire.objects.filter(
            grille_salaire__contrat__employe=grille.contrat.employe,
            date_paiement__year=annee,
            date_paiement__month=mois
        ).first()

        if salaire_existant:
            return JsonResponse({
                'success': False,
                'error': f'Un paiement existe déjÃ  pour {grille.contrat.employe.nom_complet} en {mois}/{annee}'
            })

        # Créer le salaire avec les montants calculés depuis la grille
        date_paiement = date(annee, mois, 1)  # 1er du mois

        salaire = Salaire.objects.create(
            grille_salaire=grille,
            date_paiement=date_paiement,
            salaire_net_paye=montant_salaire['salaire_net_paye'],
            irsa_paye=montant_salaire['irsa_paye'],
            cnaps_paye=montant_salaire['cnaps_paye'],
            fmfp_paye=montant_salaire['fmfp_paye'],
            mutuelle_sante_paye=montant_salaire['mutuelle_sante_paye'],
        )

        return JsonResponse({
            'success': True,
            'message': f'Paiement créé pour {grille.contrat.employe.nom_complet}',
            'salaire_id': str(salaire.id)
        })

    except Exception as e:
        import traceback
        print(f"Erreur dans api_creer_salaire_depuis_grille: {str(e)}")
        print(traceback.format_exc())
        return JsonResponse({
            'success': False,
            'error': f'Erreur serveur: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_remettre_salaire_a_traiter(request, salaire_id):
    """Supprimer un salaire mensuel pour permettre sa correction puis sa recreation."""
    try:
        salaire = get_object_or_404(
            Salaire.objects.select_related('grille_salaire__contrat__employe__base__organisation'),
            id=salaire_id
        )

        user_organisation = _get_user_organisation(request.user)
        employe_base = getattr(salaire.grille_salaire.contrat.employe, 'base', None)
        salaire_organisation = getattr(employe_base, 'organisation', None)

        if not getattr(request.user, 'is_superuser', False):
            if not user_organisation or not salaire_organisation or str(salaire_organisation.id) != str(user_organisation.id):
                return JsonResponse({
                    'success': False,
                    'error': 'Vous ne pouvez pas modifier ce salaire.'
                }, status=403)

        diamex_fields = [
            salaire.numero_diamex_salaire,
            salaire.numero_diamex_irsa,
            salaire.numero_diamex_cnaps,
            salaire.numero_diamex_fmfp,
            salaire.numero_diamex_mutuelle_sante,
        ]
        if any(str(value or '').strip() for value in diamex_fields):
            return JsonResponse({
                'success': False,
                'error': 'Impossible de corriger un salaire deja lie a DiameX.'
            }, status=400)

        employe_nom = salaire.grille_salaire.contrat.employe.nom_complet
        periode = salaire.date_paiement.strftime('%m/%Y')
        salaire.delete()

        return JsonResponse({
            'success': True,
            'message': f'Salaire de {employe_nom} remis a traiter pour {periode}.'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Erreur serveur: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_grille_salaire_detail(request, grille_id):
    """API pour récupérer les détails d'une grille de salaire"""
    try:
        grille = GrilleSalaire.objects.select_related('contrat').get(id=grille_id)
        refresh_grille_calculs(grille)

        # Si salaire_brut_base de la grille est 0 ou NULL, prendre celui du contrat
        salaire_brut_base = grille.salaire_brut_base
        if not salaire_brut_base or salaire_brut_base == 0:
            salaire_brut_base = grille.contrat.salaire_brut_base if grille.contrat else 0

        # Calculer salaire net arrondi Ã  100 Ar près (arrondi supérieur)
        import math
        from decimal import Decimal
        salaire_net_arrondi = Decimal(math.ceil(float(grille.salaire_net) / 100) * 100)

        return JsonResponse({
            'success': True,
            'grille': {
                'id': str(grille.id),
                'salaire_brut_base': float(salaire_brut_base),  #  Récupéré depuis contrat si besoin
                'salaire_brut_total': float(grille.salaire_brut_total),
                'charge_cnaps_employe': float(grille.charge_cnaps_employe),
                'base_imposable': float(grille.base_imposable),
                'irsa': float(grille.irsa),
                'mutuelle_sante': float(grille.mutuelle_sante),
                'salaire_net': float(grille.salaire_net),
                'salaire_net_arrondi': float(salaire_net_arrondi),
                'personnes_charge': grille.personnes_charge,
                'nb_jours_presence': grille.nb_jours_presence,
                'nb_dimanches_travailles': grille.nb_dimanches_travailles,
                'est_prorata': grille.est_prorata,
                'nb_jours_feries_gardien': grille.nb_jours_feries_gardien,
                'nb_heures_remplacement_gardien': float(grille.nb_heures_remplacement_gardien),
                'date_salaire': grille.date_salaire.strftime('%Y-%m-%d')
            }
        })

    except GrilleSalaire.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Grille de salaire non trouvée'
        }, status=404)

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_grilles_employe_mois(request, employe_id):
    """API pour récupérer toutes les grilles d'un employé (contrat actif)"""
    try:
        employe = Employe.objects.get(id=employe_id)

        # Chercher le contrat actif
        contrat_actif = Contrat.objects.filter(
            employe=employe,
            fin_contrat__isnull=True
        ).first()

        if not contrat_actif:
            return JsonResponse({
                'success': False,
                'error': 'Aucun contrat actif pour cet employé'
            }, status=404)

        # Récupérer TOUTES les grilles du contrat actif (toutes dates confondues)
        grilles = GrilleSalaire.objects.filter(
            contrat=contrat_actif
        ).select_related('contrat').order_by('-date_salaire')

        import math
        from decimal import Decimal

        grilles_data = []
        for grille in grilles:
            refresh_grille_calculs(grille)
            # Si salaire_brut_base de la grille est 0 ou NULL, prendre celui du contrat
            salaire_brut_base = grille.salaire_brut_base
            if not salaire_brut_base or salaire_brut_base == 0:
                salaire_brut_base = grille.contrat.salaire_brut_base if grille.contrat else 0

            salaire_net_arrondi = Decimal(math.ceil(float(grille.salaire_net) / 100) * 100)
            grilles_data.append({
                'id': str(grille.id),
                'salaire_brut_base': float(salaire_brut_base),  #  Récupéré depuis contrat si besoin
                'salaire_brut_total': float(grille.salaire_brut_total),
                'charge_cnaps_employe': float(grille.charge_cnaps_employe),
                'base_imposable': float(grille.base_imposable),
                'irsa': float(grille.irsa),
                'mutuelle_sante': float(grille.mutuelle_sante),
                'salaire_net': float(grille.salaire_net),
                'salaire_net_arrondi': float(salaire_net_arrondi),
                'personnes_charge': grille.personnes_charge,
                'nb_jours_presence': grille.nb_jours_presence,
                'nb_dimanches_travailles': grille.nb_dimanches_travailles,
                'est_prorata': grille.est_prorata,
                'nb_jours_feries_gardien': grille.nb_jours_feries_gardien,
                'nb_heures_remplacement_gardien': float(grille.nb_heures_remplacement_gardien),
                'date_salaire': grille.date_salaire.strftime('%Y-%m-%d')
            })

        return JsonResponse({
            'success': True,
            'employe_nom': employe.nom_complet,
            'nb_grilles': len(grilles_data),
            'grilles': grilles_data
        })

    except Employe.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Employé non trouvé'
        }, status=404)

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def fiches_paie_impression(request):
    """Page d'impression groupée des fiches de paie"""
    from apps.organization.models import Organisation
    from decimal import Decimal
    import math
    import locale

    # Récupérer les IDs des salaires Ã  imprimer
    salaires_ids = request.GET.get('salaires', '').split(',')

    if not salaires_ids or salaires_ids == ['']:
        return render(request, 'employees/fiches_paie_impression.html', {
            'error': 'Aucun salaire sélectionné'
        })

    # Récupérer tous les salaires avec leurs relations
    salaires = Salaire.objects.filter(
        id__in=salaires_ids
    ).select_related(
        'grille_salaire__contrat__employe__base__organisation',
        'grille_salaire__contrat__employe__poste',
        'grille_salaire__contrat'
    ).order_by('grille_salaire__contrat__employe__nom_employe')

    # Préparer les données pour chaque fiche
    fiches_data = []

    # Configurer locale français
    try:
        locale.setlocale(locale.LC_TIME, 'fr_FR.UTF-8')
    except:
        try:
            locale.setlocale(locale.LC_TIME, 'French_France.1252')
        except:
            pass

    for salaire in salaires:
        grille = salaire.grille_salaire
        contrat = grille.contrat
        employe = contrat.employe
        organisation = employe.base.organisation if employe.base else None

        est_herizo = (employe.surnom or '').strip().lower() == 'herizo'

        # Calculer le mois/année
        mois_annee_date = salaire.date_paiement
        try:
            planning_details = _get_fiche_paie_planning_details(employe, mois_annee_date)
        except Exception:
            planning_details = {'dimanches': [], 'jours_feries': []}

        # Récupérer le directeur
        directeur = None
        if organisation:
            directeur = Employe.objects.filter(
                base__organisation=organisation,
                poste__nom_poste__iexact='directeur'
            ).select_related('poste').first()

            if not directeur:
                directeur = Employe.objects.filter(
                    base__organisation=organisation
                ).filter(
                    Q(poste__nom_poste__icontains='direction') |
                    Q(poste__nom_poste__icontains='responsable')
                ).select_related('poste').first()

            if not directeur:
                directeur = Employe.objects.filter(
                    base__organisation=organisation,
                    signature__isnull=False
                ).exclude(signature='').select_related('poste').first()

        # Fonction pour convertir un nombre en lettres
        def nombre_en_lettres(n):
            try:
                from num2words import num2words
                montant_int = int(float(n or 0))
                return num2words(montant_int, lang='fr').upper() + " ARIARY"
            except (ImportError, Exception):
                montant_int = int(float(n or 0))
                return f"{montant_int:,} ARIARY".replace(',', ' ')

        salaire_net_lettres = nombre_en_lettres(salaire.salaire_net_paye)
        salaire_net_arrondi = Decimal(math.ceil(float(grille.salaire_net or 0) / 100) * 100)
        est_journalier = bool(contrat.type_contrat and 'journalier' in contrat.type_contrat.lower())
        salaire_brut_reference = Decimal(str(grille.salaire_brut_base or 0))
        salaire_reference_majoration = (
            salaire_brut_reference
            if est_journalier
            else (salaire_brut_reference / Decimal('30'))
        )
        taux_horaire_gardien = salaire_brut_reference / Decimal('240')
        taux_horaire_autre = salaire_brut_reference / Decimal('173.33')

        fiches_data.append({
            'salaire': salaire,
            'grille': grille,
            'contrat': contrat,
            'employe': employe,
            'organisation': organisation,
            'directeur': directeur,
            'mois_annee_date': mois_annee_date,
            'salaire_net_lettres': salaire_net_lettres,
            'salaire_net_arrondi': salaire_net_arrondi,
            'est_herizo': est_herizo,
            'est_journalier': est_journalier,
            'est_gardien': bool(employe.poste and employe.poste.nom_poste and 'gardien' in employe.poste.nom_poste.lower()),
            'salaire_reference_majoration': salaire_reference_majoration,
            'taux_horaire_gardien': taux_horaire_gardien,
            'taux_horaire_autre': taux_horaire_autre,
            'planning_details': planning_details,
        })

    context = {
        'fiches': fiches_data,
        'nb_fiches': len(fiches_data)
    }

    return render(request, 'employees/fiches_paie_impression.html', context)



