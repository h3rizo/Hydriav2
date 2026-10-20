import datetime
import json
from decimal import Decimal, ROUND_HALF_UP
from unicodedata import normalize as _unicode_normalize
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db import models
from .models import Employe, Poste, Contrat, GrilleSalaire
from .models_evaluation import Evaluation
from .models_evaluation_resultats import EvaluationResultats
from .models_revalorisation import GrilleSalariale, Revalorisation
from apps.organization.scoping import get_user_accessible_gestionnaire_ids
from apps.organization.models import Organisation, PartenaireGestionnaireAffectation

DIRECTEUR_REFERENCE_POSTES = {
    'directeur',
    'directeur adjoint',
}


def _get_request_organisation(request):
    employe_auth = getattr(request.user, 'employe', None)
    if not employe_auth or not getattr(employe_auth, 'base', None):
        return None
    return employe_auth.base.organisation


def _get_request_accessible_organisation_ids(request):
    if getattr(request.user, 'is_superuser', False):
        return None

    organisation = _get_request_organisation(request)
    if not organisation:
        return []

    organisation_ids = {str(organisation.id)}

    scoped_ids = get_user_accessible_gestionnaire_ids(request.user)
    if scoped_ids is None:
        return None
    organisation_ids.update(str(organisation_id) for organisation_id in scoped_ids if organisation_id)

    linked_ids = PartenaireGestionnaireAffectation.objects.filter(
        models.Q(partenaire=organisation) | models.Q(gestionnaire=organisation)
    ).values_list('partenaire_id', 'gestionnaire_id')
    for partenaire_id, gestionnaire_id in linked_ids:
        if partenaire_id:
            organisation_ids.add(str(partenaire_id))
        if gestionnaire_id:
            organisation_ids.add(str(gestionnaire_id))

    return list(organisation_ids)


def _resolve_revalorisation_organisation_filter(accessible_organisation_ids, requested_organisation_id):
    requested_value = str(requested_organisation_id or '').strip()

    if accessible_organisation_ids is None:
        if requested_value:
            return requested_value
        soakoja = Organisation.objects.filter(nom_organisation__iexact='Soakoja').values_list('id', flat=True).first()
        return str(soakoja) if soakoja else ''

    normalized_ids = [str(organisation_id) for organisation_id in accessible_organisation_ids if organisation_id]
    if not normalized_ids:
        return ''

    if requested_value and requested_value in normalized_ids:
        return requested_value

    soakoja = Organisation.objects.filter(
        id__in=normalized_ids,
        nom_organisation__iexact='Soakoja'
    ).values_list('id', flat=True).first()
    if soakoja:
        return str(soakoja)

    return normalized_ids[0]


def _safe_decimal(value):
    return Decimal(str(value or 0))


def _compute_percentage(old_value, new_value):
    old_decimal = _safe_decimal(old_value)
    new_decimal = _safe_decimal(new_value)
    if old_decimal <= 0:
        return Decimal('0.00')
    return ((new_decimal - old_decimal) / old_decimal) * Decimal('100')


def _get_journalier_reference_days(contrat, reference_grille=None):
    if not contrat or contrat.type_contrat != 'journalier':
        return Decimal('1')

    nb_jours = None
    if reference_grille is not None:
        nb_jours = getattr(reference_grille, 'nb_jours_presence', None)

    nb_jours_decimal = _safe_decimal(nb_jours or 30)
    if nb_jours_decimal <= 0:
        nb_jours_decimal = Decimal('30')
    return nb_jours_decimal


def _convert_salary_for_display(value, contrat, reference_grille=None):
    amount = _safe_decimal(value)
    divisor = _get_journalier_reference_days(contrat, reference_grille)
    if contrat and contrat.type_contrat == 'journalier':
        return amount / divisor
    return amount


def _convert_salary_from_display(value, contrat, reference_grille=None):
    amount = _safe_decimal(value)
    multiplier = _get_journalier_reference_days(contrat, reference_grille)
    if contrat and contrat.type_contrat == 'journalier':
        return amount * multiplier
    return amount


def _get_year_bounds(annee):
    return datetime.date(annee, 1, 1), datetime.date(annee, 12, 31)


def _normalize_poste_name(name):
    if not name:
        return ''
    normalized = _unicode_normalize('NFKD', str(name))
    return normalized.encode('ascii', errors='ignore').decode('ascii').lower().strip()


def _get_reference_evaluations_for_revalorisation(employe, annee):
    annee_reference = int(annee) - 1
    date_debut_reference, date_fin_reference = _get_year_bounds(annee_reference)
    evaluations = Evaluation.objects.filter(
        employe=employe
    ).select_related('evaluateur__poste').prefetch_related('details')

    # Priorite au millesime de la periode evaluee, car la date de saisie peut
    # tomber l'annee suivante.
    evaluation_list = list(evaluations.filter(
        periode_fin__gte=date_debut_reference,
        periode_fin__lte=date_fin_reference,
    ).order_by('-periode_fin', '-date_evaluation', '-date_creation'))
    if evaluation_list:
        return evaluation_list

    evaluation_list = list(evaluations.filter(
        periode_debut__lte=date_fin_reference,
        periode_fin__gte=date_debut_reference,
    ).order_by('-periode_fin', '-date_evaluation', '-date_creation'))
    if evaluation_list:
        return evaluation_list

    return list(evaluations.filter(
        date_evaluation__year__lte=annee_reference
    ).order_by('-date_evaluation', '-date_creation')[:1])


def _get_reference_evaluation_for_revalorisation(employe, annee):
    evaluations = _get_reference_evaluations_for_revalorisation(employe, annee)
    return evaluations[0] if evaluations else None


def _is_more_recent_resultats_evaluation(candidate, current):
    if candidate.periode_fin != current.periode_fin:
        return candidate.periode_fin > current.periode_fin

    candidate_date_calcul = candidate.date_calcul or datetime.date.min
    current_date_calcul = current.date_calcul or datetime.date.min
    if candidate_date_calcul != current_date_calcul:
        return candidate_date_calcul > current_date_calcul

    return candidate.date_creation > current.date_creation


def _get_reference_evaluations_resultats_for_revalorisation(employes, annee):
    employe_ids = [employe.id for employe in employes]
    if not employe_ids:
        return {}

    annee_reference = int(annee) - 1
    date_debut_reference, date_fin_reference = _get_year_bounds(annee_reference)

    evaluations = EvaluationResultats.objects.filter(
        employe_id__in=employe_ids
    ).order_by(
        'employe_id',
        '-periode_fin',
        '-date_calcul',
        '-date_creation',
    )

    best_by_employee = {}
    best_rank_by_employee = {}

    for evaluation in evaluations:
        if date_debut_reference <= evaluation.periode_fin <= date_fin_reference:
            rank = 0
        elif evaluation.periode_debut <= date_fin_reference and evaluation.periode_fin >= date_debut_reference:
            rank = 1
        elif evaluation.periode_fin <= date_fin_reference:
            rank = 2
        else:
            continue

        current = best_by_employee.get(evaluation.employe_id)
        if current is None:
            best_by_employee[evaluation.employe_id] = evaluation
            best_rank_by_employee[evaluation.employe_id] = rank
            continue

        current_rank = best_rank_by_employee[evaluation.employe_id]
        if rank < current_rank or (rank == current_rank and _is_more_recent_resultats_evaluation(evaluation, current)):
            best_by_employee[evaluation.employe_id] = evaluation
            best_rank_by_employee[evaluation.employe_id] = rank

    return best_by_employee


def _serialize_reference_evaluation_resultats(evaluation):
    if not evaluation:
        return None

    return {
        'id': str(evaluation.id),
        'periode_debut': evaluation.periode_debut.isoformat(),
        'periode_fin': evaluation.periode_fin.isoformat(),
        'date_calcul': evaluation.date_calcul.isoformat() if evaluation.date_calcul else None,
        'score_obtenu': evaluation.score_obtenu,
        'score_maximum': evaluation.score_maximum,
        'pourcentage': float(evaluation.pourcentage or 0),
        'nb_ouvrages': evaluation.nb_ouvrages,
        'montant_total_collecte': float(evaluation.montant_total_collecte or 0),
        'montant_total_prevu': float(evaluation.montant_total_prevu or 0),
        'taux_recouvrement': float(evaluation.taux_recouvrement or 0),
        'statut': evaluation.statut,
        'statut_display': evaluation.get_statut_display(),
        'commentaire': evaluation.commentaire or '',
    }


def _get_evaluation_weight(evaluation):
    is_auto_evaluation = bool(
        getattr(evaluation, 'est_auto_evaluation', False)
        or (getattr(evaluation, 'evaluateur_id', None) and evaluation.evaluateur_id == evaluation.employe_id)
    )
    if is_auto_evaluation:
        return Decimal('0.5')

    evaluateur = getattr(evaluation, 'evaluateur', None)
    poste_nom = getattr(getattr(evaluateur, 'poste', None), 'nom_poste', '')
    if _normalize_poste_name(poste_nom) in DIRECTEUR_REFERENCE_POSTES:
        return Decimal('2')

    return Decimal('1')


def _build_weighted_evaluation_score(evaluations):
    if not evaluations:
        return None

    weighted_note = Decimal('0')
    weighted_max = Decimal('0')
    counted_evaluations = 0
    auto_count = 0
    direction_count = 0
    standard_count = 0

    for evaluation in evaluations:
        details = list(evaluation.details.all())
        if not details:
            continue

        note_totale = sum(Decimal(str(detail.note or 0)) for detail in details)
        note_maximale = Decimal(str(len(details) * 2))
        if note_maximale <= 0:
            continue

        weight = _get_evaluation_weight(evaluation)
        weighted_note += note_totale * weight
        weighted_max += note_maximale * weight
        counted_evaluations += 1

        if weight == Decimal('0.5'):
            auto_count += 1
        elif weight == Decimal('2'):
            direction_count += 1
        else:
            standard_count += 1

    if weighted_max <= 0 or counted_evaluations == 0:
        return None

    percentage = ((weighted_note / weighted_max) * Decimal('100')).quantize(
        Decimal('0.01'),
        rounding=ROUND_HALF_UP,
    )
    return {
        'percentage': float(percentage),
        'weighted_note': float(weighted_note.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
        'weighted_max': float(weighted_max.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
        'evaluations_count': counted_evaluations,
        'auto_count': auto_count,
        'direction_count': direction_count,
        'standard_count': standard_count,
    }


def _is_employee_eligible_for_revalorisation(employe, annee):
    _, date_fin_annee = _get_year_bounds(annee)

    if employe.date_embauche and employe.date_embauche > date_fin_annee:
        return False

    if employe.date_debauchage and employe.date_debauchage <= date_fin_annee:
        return False

    return True


def _parse_iso_date(value, field_label):
    if value in (None, ''):
        return None
    if isinstance(value, datetime.date):
        return value

    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{field_label} invalide. Format attendu : YYYY-MM-DD.") from exc


def _get_employee_year_window(employe, annee):
    date_debut_annee, date_fin_annee = _get_year_bounds(annee)
    date_debut_emploi = employe.date_embauche or datetime.date.min
    date_fin_emploi = employe.date_debauchage or datetime.date.max

    date_reference_debut = max(date_debut_annee, date_debut_emploi)
    date_reference_fin = min(date_fin_annee, date_fin_emploi)
    if date_reference_debut > date_reference_fin:
        return None

    return {
        'date_debut_annee': date_debut_annee,
        'date_fin_annee': date_fin_annee,
        'date_reference_debut': date_reference_debut,
        'date_reference_fin': date_reference_fin,
    }


def _calculate_anciennete(employe, date_reference):
    """Anciennete de grille : comptee depuis la sortie du niveau Junior (0 pour un Junior)."""
    if not date_reference:
        return Decimal('0.00')
    return employe.anciennete_grille_annees(date_reference).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _get_contract_for_period(employe, date_reference_debut, date_reference_fin):
    contrat = Contrat.objects.filter(
        employe=employe,
        debut_contrat__lte=date_reference_fin
    ).filter(
        models.Q(fin_contrat__gte=date_reference_fin) | models.Q(fin_contrat__isnull=True)
    ).order_by('-debut_contrat').first()
    if contrat:
        return contrat

    return Contrat.objects.filter(
        employe=employe,
        debut_contrat__lte=date_reference_fin
    ).filter(
        models.Q(fin_contrat__gte=date_reference_debut) | models.Q(fin_contrat__isnull=True)
    ).order_by('-debut_contrat').first()


def _get_latest_salary_grid(employe, date_reference):
    return GrilleSalaire.objects.filter(
        contrat__employe=employe,
        date_salaire__lte=date_reference
    ).select_related('contrat').order_by('-date_salaire').first()


def _get_latest_salary_grid_for_period(employe, date_reference_debut, date_reference_fin):
    return GrilleSalaire.objects.filter(
        contrat__employe=employe,
        date_salaire__gte=date_reference_debut,
        date_salaire__lte=date_reference_fin,
    ).select_related('contrat').order_by('-date_salaire').first()


def _get_salary_reference_window_for_revalorisation(employe, annee):
    reference_window = _get_employee_year_window(employe, int(annee) - 1)
    if reference_window:
        return reference_window
    return _get_employee_year_window(employe, int(annee))


def _get_current_salary_reference_for_revalorisation(employe, annee):
    salary_window = _get_salary_reference_window_for_revalorisation(employe, annee)
    if not salary_window:
        return {
            'contrat': None,
            'reference_grille': None,
            'salaire_brut': Decimal('0.00'),
            'salaire_net': Decimal('0.00'),
        }

    date_reference_debut = salary_window['date_reference_debut']
    date_reference_fin = salary_window['date_reference_fin']
    contrat_reference = _get_contract_for_period(employe, date_reference_debut, date_reference_fin)
    reference_grille = _get_latest_salary_grid_for_period(
        employe,
        date_reference_debut,
        date_reference_fin,
    )

    if reference_grille and reference_grille.contrat:
        contrat_reference = reference_grille.contrat

    reference_grille = _sanitize_reference_grille_for_revalorisation(
        contrat_reference,
        employe,
        date_reference_fin,
        reference_grille,
    )

    salaire_brut = None
    if reference_grille:
        salaire_brut = reference_grille.salaire_brut_base
    elif contrat_reference:
        salaire_brut = contrat_reference.salaire_brut_base

    salaire_brut = _safe_decimal(salaire_brut)
    preview = _build_salary_preview(
        contrat=contrat_reference,
        employe=employe,
        date_reference=date_reference_fin,
        reference_grille=reference_grille,
        salaire_brut_base=salaire_brut,
    ) if contrat_reference else None

    return {
        'contrat': contrat_reference,
        'reference_grille': reference_grille,
        'salaire_brut': salaire_brut,
        'salaire_net': preview.salaire_net if preview else Decimal('0.00'),
    }


def _build_preview_instance(contrat, employe, date_reference, reference_grille=None):
    if not contrat:
        return None

    return GrilleSalaire(
        contrat=contrat,
        date_salaire=date_reference,
        personnes_charge=reference_grille.personnes_charge if reference_grille else (employe.personnes_charge or 0),
        nb_jours_presence=reference_grille.nb_jours_presence if reference_grille else (30 if contrat.type_contrat == 'journalier' else 0),
        est_prorata=reference_grille.est_prorata if reference_grille else False,
        nb_jours_feries_gardien=reference_grille.nb_jours_feries_gardien if reference_grille else 0,
        nb_heures_remplacement_gardien=reference_grille.nb_heures_remplacement_gardien if reference_grille else Decimal('0.00'),
        salaire_brut_base=Decimal('0.00'),
    )


def _sanitize_reference_grille_for_revalorisation(contrat, employe, date_reference, reference_grille):
    if not reference_grille:
        return None
    if not getattr(reference_grille, 'est_gardien', False):
        return reference_grille

    sanitized = _build_preview_instance(
        contrat=contrat,
        employe=employe,
        date_reference=date_reference,
        reference_grille=reference_grille,
    )
    if not sanitized:
        return reference_grille

    sanitized.nb_jours_feries_gardien = 0
    sanitized.nb_heures_remplacement_gardien = Decimal('0.00')
    sanitized.salaire_brut_base = _safe_decimal(reference_grille.salaire_brut_base)
    return sanitized


def _build_salary_preview(contrat, employe, date_reference, reference_grille=None, salaire_brut_base=None):
    preview = _build_preview_instance(
        contrat=contrat,
        employe=employe,
        date_reference=date_reference,
        reference_grille=reference_grille,
    )
    if not preview:
        return None

    brut_reference = salaire_brut_base
    if brut_reference is None and reference_grille is not None:
        brut_reference = reference_grille.salaire_brut_base
    if brut_reference is None:
        brut_reference = contrat.salaire_brut_base

    preview.salaire_brut_base = _safe_decimal(brut_reference)
    preview.calculer_tous_les_champs()
    return preview


def _build_salary_preview_from_net(contrat, employe, date_reference, salaire_net, reference_grille=None):
    preview = _build_preview_instance(
        contrat=contrat,
        employe=employe,
        date_reference=date_reference,
        reference_grille=reference_grille,
    )
    if not preview:
        return None

    preview.salaire_brut_base = preview.calculer_salaire_brut_depuis_net(_safe_decimal(salaire_net))
    preview.calculer_tous_les_champs()
    return preview


@login_required
def revalorisations_list(request):
    """
    Affiche la page de gestion des revalorisations salariales.
    """
    # Fetch available years (from Revalorisation or just current year +/- 5)
    current_year = timezone.now().year
    years = list(range(current_year, current_year - 6, -1))
    accessible_organisation_ids = _get_request_accessible_organisation_ids(request)
    organisation = _get_request_organisation(request)

    organisations_filter = []
    organisations_qs = Organisation.objects.all()
    if accessible_organisation_ids is not None:
        organisations_qs = organisations_qs.filter(id__in=accessible_organisation_ids)

    for org in organisations_qs.order_by('nom_organisation').values('id', 'nom_organisation'):
        organisations_filter.append({
            'id': str(org['id']),
            'nom': org['nom_organisation'],
        })

    if not organisations_filter and organisation is not None:
        organisations_filter.append({
            'id': str(organisation.id),
            'nom': organisation.nom_organisation,
        })

    default_organisation_id = ''
    soakoja_item = next((item for item in organisations_filter if str(item['nom']).strip().lower() == 'soakoja'), None)
    if soakoja_item:
        default_organisation_id = soakoja_item['id']
    elif organisations_filter:
        default_organisation_id = organisations_filter[0]['id']

    context = {
        'page_title': 'Revalorisations Salariales Annuelles',
        'current_year': current_year,
        'years': years,
        'organisations_filter': organisations_filter,
        'organisations_filter_json': json.dumps(organisations_filter),
        'default_organisation_id': default_organisation_id,
    }
    return render(request, 'employees/revalorisation/list.html', context)


@login_required
def api_revalorisations_list(request):
    """
    API retournant la liste des employés avec leurs données de revalorisation pour une année donnée.
    """
    annee_str = request.GET.get('annee')
    try:
        annee = int(annee_str)
    except (TypeError, ValueError):
        annee = timezone.now().year
    organisation = _get_request_organisation(request)
    if organisation is None:
        return JsonResponse({
            'success': False,
            'error': "Aucune organisation n'est associee a votre compte."
        }, status=403)
    accessible_organisation_ids = _get_request_accessible_organisation_ids(request)
    if accessible_organisation_ids == []:
        return JsonResponse({'success': True, 'data': []})
    requested_organisation_id = str(request.GET.get('organisation_id') or '').strip()

    # R?cup?rer les employ?s ?ligibles ? une revalorisation sur l'ann?e
    date_debut_annee, date_fin_annee = _get_year_bounds(annee)
    employes_scope_qs = Employe.objects.filter(salarie=True)
    if accessible_organisation_ids is not None:
        employes_scope_qs = employes_scope_qs.filter(base__organisation_id__in=accessible_organisation_ids)

    organisations_data = []
    organisations_seen = set()
    for org_id, org_name in employes_scope_qs.order_by('base__organisation__nom_organisation').values_list(
        'base__organisation_id',
        'base__organisation__nom_organisation',
    ).distinct():
        org_id_str = str(org_id)
        if org_id_str in organisations_seen:
            continue
        organisations_seen.add(org_id_str)
        organisations_data.append({
            'id': org_id_str,
            'nom': org_name,
        })

    if not organisations_data and organisation is not None:
        organisations_data.append({
            'id': str(organisation.id),
            'nom': organisation.nom_organisation,
        })

    selected_organisation_id = ''
    available_org_ids = [item['id'] for item in organisations_data]
    if requested_organisation_id and requested_organisation_id in available_org_ids:
        selected_organisation_id = requested_organisation_id
    else:
        soakoja_item = next((item for item in organisations_data if str(item['nom']).strip().lower() == 'soakoja'), None)
        if soakoja_item:
            selected_organisation_id = soakoja_item['id']
        elif organisations_data:
            selected_organisation_id = organisations_data[0]['id']

    employes_qs = employes_scope_qs
    if selected_organisation_id:
        employes_qs = employes_qs.filter(base__organisation_id=selected_organisation_id)

    employes = list(employes_qs.filter(
        models.Q(date_embauche__isnull=True) | models.Q(date_embauche__lte=date_fin_annee)
    ).filter(
        models.Q(date_debauchage__isnull=True) | models.Q(date_debauchage__gt=date_fin_annee)
    ).select_related('poste', 'base__organisation').order_by(
        'poste__nom_poste',
        'base__nom_base',
        'surnom',
        'nom',
        'prenom',
    ))

    reference_resultats_evaluations = _get_reference_evaluations_resultats_for_revalorisation(employes, annee)
    
    data = []
    
    for emp in employes:
        if not _is_employee_eligible_for_revalorisation(emp, annee):
            continue

        # Calculer l'ancienneté en années
        year_window = _get_employee_year_window(emp, annee)
        if not year_window:
            continue

        date_reference_debut = year_window['date_reference_debut']
        date_reference_fin = year_window['date_reference_fin']
        anciennete = _calculate_anciennete(emp, date_reference_debut)
            
        # Grille applicable : Junior, ou tranche d'anciennete depuis la sortie Junior
        est_junior = emp.est_junior(date_reference_debut)
        grille = GrilleSalariale.get_grille_for_employe(emp, date_reference_debut)
            
        # Le salaire actuel de reference d'une revalorisation N vient du
        # dernier salaire constate sur l'annee N-1.
        salaire_reference = _get_current_salary_reference_for_revalorisation(emp, annee)
        contrat_actif = _get_contract_for_period(emp, date_reference_debut, date_reference_fin)
        salaire_actuel = salaire_reference['salaire_brut']
        reference_grille = salaire_reference['reference_grille']
        salaire_actuel_net = salaire_reference['salaire_net']
        salaire_actuel_net_display = _convert_salary_for_display(
            salaire_actuel_net,
            contrat_actif,
            reference_grille,
        )
        
        # Obtenir ou préparer la revalorisation
        reval = Revalorisation.objects.filter(employe=emp, annee=annee).first()
        
        # Obtenir la dernière évaluation de l'année précédente
        reference_evaluations = _get_reference_evaluations_for_revalorisation(emp, annee)
        derniere_eval = reference_evaluations[0] if reference_evaluations else None
        evaluation_score = _build_weighted_evaluation_score(reference_evaluations)
        evaluation_resultats = reference_resultats_evaluations.get(emp.id)
        note_evaluation = None
        if derniere_eval:
            note_evaluation = getattr(derniere_eval, 'note_globale', None)
            if note_evaluation is None:
                note_evaluation = getattr(derniere_eval, 'note_totale', None)
        
        emp_data = {
            'employe_id': str(emp.id),
            'poste_id': str(emp.poste_id) if emp.poste_id else None,
            'surnom': emp.surnom or emp.nom,
            'nom_complet': emp.nom_complet,
            'poste': emp.poste.nom_poste if emp.poste else 'Non assigné',
            'base_id': str(emp.base_id) if emp.base_id else None,
            'base_nom': emp.base.nom_base if emp.base else 'Sans base',
            'anciennete': float(anciennete),
            'est_junior': est_junior,
            'date_sortie_junior': emp.date_sortie_junior.isoformat() if emp.date_sortie_junior else None,
            'date_embauche': emp.date_embauche.isoformat() if emp.date_embauche else None,
            'date_debauchage': emp.date_debauchage.isoformat() if emp.date_debauchage else None,
            'salaire_actuel': float(salaire_actuel_net_display),
            'salaire_actuel_brut': float(salaire_actuel),
            'type_contrat': contrat_actif.type_contrat if contrat_actif else None,
            'salary_display_unit': 'jour' if contrat_actif and contrat_actif.type_contrat == 'journalier' else 'mois',
            'salary_reference_days': float(_get_journalier_reference_days(contrat_actif, reference_grille)),
        }
        
        if grille:
            fourchette_basse_brut = grille.get_fourchette_basse_for_anciennete(anciennete)
            fourchette_haute_brut = grille.get_fourchette_haute_for_anciennete(anciennete)
            fourchette_basse_net = fourchette_basse_brut
            fourchette_haute_net = fourchette_haute_brut
            if contrat_actif:
                # Si journalier, la fourchette de la grille (mensuelle) doit être
                # divisée par le nombre de jours car le modèle multipliera
                # salaire_brut_base par nb_jours_presence.
                f_basse_sim = fourchette_basse_brut
                f_haute_sim = fourchette_haute_brut
                if contrat_actif.type_contrat == 'journalier':
                    nb_jours = reference_grille.nb_jours_presence if reference_grille else 30
                    if nb_jours <= 0: nb_jours = 30
                    f_basse_sim = fourchette_basse_brut / Decimal(str(nb_jours))
                    f_haute_sim = fourchette_haute_brut / Decimal(str(nb_jours))

                preview_basse = _build_salary_preview(
                    contrat=contrat_actif,
                    employe=emp,
                    date_reference=date_reference_fin,
                    reference_grille=reference_grille,
                    salaire_brut_base=f_basse_sim,
                )
                preview_haute = _build_salary_preview(
                    contrat=contrat_actif,
                    employe=emp,
                    date_reference=date_reference_fin,
                    reference_grille=reference_grille,
                    salaire_brut_base=f_haute_sim,
                )
                if preview_basse:
                    fourchette_basse_net = preview_basse.salaire_net
                if preview_haute:
                    fourchette_haute_net = preview_haute.salaire_net

            fourchette_basse_display = _convert_salary_for_display(
                fourchette_basse_net,
                contrat_actif,
                reference_grille,
            )
            fourchette_haute_display = _convert_salary_for_display(
                fourchette_haute_net,
                contrat_actif,
                reference_grille,
            )

            emp_data['grille'] = {
                'id': str(grille.id),
                'niveau': grille.niveau,
                'fourchette_basse': float(fourchette_basse_display),
                'fourchette_haute': float(fourchette_haute_display),
                'fourchette_basse_brut': float(fourchette_basse_brut),
                'fourchette_haute_brut': float(fourchette_haute_brut),
                'mode_fourchette_haute': grille.mode_fourchette_haute,
                'ratio_annuel_haute': float(grille.ratio_annuel_haute or 0),
                'anciennete_reference_haute': float(grille.anciennete_reference_haute) if grille.anciennete_reference_haute is not None else None,
                'anciennete_min': float(grille.anciennete_min),
                'anciennete_max': float(grille.anciennete_max),
            }
        else:
            emp_data['grille'] = None
            
        if reval:
            preview_revalorise = _build_salary_preview(
                contrat=contrat_actif,
                employe=emp,
                date_reference=date_reference_fin,
                reference_grille=reference_grille,
                salaire_brut_base=reval.salaire_propose,
            )
            salaire_propose_net = preview_revalorise.salaire_net if preview_revalorise else reval.salaire_propose
            salaire_propose_net_display = _convert_salary_for_display(
                salaire_propose_net,
                contrat_actif,
                reference_grille,
            )
            salaire_propose_charge_employeur = Decimal(str(reval.salaire_propose or 0))
            if preview_revalorise:
                salaire_propose_charge_employeur = (
                    _safe_decimal(preview_revalorise.salaire_brut_total) +
                    _safe_decimal(preview_revalorise.charge_cnaps_employe) +
                    (_safe_decimal(preview_revalorise.mutuelle_sante) * Decimal('5')) +
                    (_safe_decimal(preview_revalorise.charge_cnaps_employe) * Decimal('13'))
                )
            salaire_propose_charge_employeur_display = _convert_salary_for_display(
                salaire_propose_charge_employeur,
                contrat_actif,
                reference_grille,
            )
            pourcentage_display = _compute_percentage(salaire_actuel_net_display, salaire_propose_net_display)
            emp_data['revalorisation'] = {
                'id': str(reval.id),
                'salaire_propose': float(salaire_propose_net_display),
                'salaire_propose_brut': float(reval.salaire_propose),
                'salaire_propose_charge_employeur': float(salaire_propose_charge_employeur_display),
                'salaire_propose_charge_employeur_brut': float(salaire_propose_charge_employeur),
                'pourcentage': float(pourcentage_display),
                'pourcentage_brut': float(reval.pourcentage_augmentation),
                'justification': reval.justification,
                'statut': reval.statut,
                'statut_display': reval.get_statut_display(),
            }
        else:
            emp_data['revalorisation'] = None

        emp_data['evaluation_score'] = evaluation_score
        emp_data['evaluation_resultats'] = _serialize_reference_evaluation_resultats(evaluation_resultats)
            
        if derniere_eval:
            emp_data['evaluation'] = {
                'id': str(derniere_eval.id),
                'date': derniere_eval.date_evaluation.strftime('%d/%m/%Y'),
                'note_globale': float(note_evaluation) if note_evaluation is not None else None
            }
        else:
            emp_data['evaluation'] = None
            
        data.append(emp_data)
        
    return JsonResponse({
        'success': True,
        'data': data,
        'organisations': organisations_data,
        'selected_organisation_id': selected_organisation_id,
    })


@login_required
def api_revalorisation_save(request):
    """
    Enregistre ou met à jour une proposition de revalorisation.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Méthode non autorisée'}, status=405)
        
    try:
        data = json.loads(request.body)
        employe_id = data.get('employe_id')
        annee = data.get('annee')
        salaire_propose = data.get('salaire_propose')
        justification = data.get('justification', '')
        organisation = _get_request_organisation(request)
        if organisation is None:
            return JsonResponse({
                'success': False,
                'error': "Aucune organisation n'est associee a votre compte."
            }, status=403)
        accessible_organisation_ids = _get_request_accessible_organisation_ids(request)
        if accessible_organisation_ids == []:
            return JsonResponse({'success': False, 'error': "Aucune organisation accessible."}, status=403)
        
        if not all([employe_id, annee, salaire_propose]):
            return JsonResponse({'success': False, 'error': 'Données manquantes'}, status=400)
            
        employe_qs = Employe.objects.select_related('base__organisation')
        if accessible_organisation_ids is not None:
            employe_qs = employe_qs.filter(base__organisation_id__in=accessible_organisation_ids)
        employe = get_object_or_404(
            employe_qs,
            id=employe_id,
        )

        annee_int = int(annee)
        if not _is_employee_eligible_for_revalorisation(employe, annee_int):
            return JsonResponse({
                'success': False,
                'error': f"Cet employe n'est pas eligible a une revalorisation sur l'annee {annee_int}."
            }, status=400)

        year_window = _get_employee_year_window(employe, annee_int)
        if not year_window:
            return JsonResponse({
                'success': False,
                'error': f"Cet employe n'est pas en poste sur l'annee {annee}."
            }, status=400)

        date_reference_debut = year_window['date_reference_debut']
        date_reference_fin = year_window['date_reference_fin']
        
        # Le salaire actuel de reference d'une revalorisation N vient du
        # dernier salaire constate sur l'annee N-1.
        salaire_reference = _get_current_salary_reference_for_revalorisation(employe, annee)
        contrat_actif = _get_contract_for_period(employe, date_reference_debut, date_reference_fin)
        salaire_actuel = salaire_reference['salaire_brut']
        reference_grille = salaire_reference['reference_grille']
        salaire_actuel_net = salaire_reference['salaire_net']
        
        if salaire_actuel <= 0:
            return JsonResponse({
                'success': False, 
                'error': "Le salaire actuel de l'employé est introuvable ou égal à zéro."
            }, status=400)
            
        salaire_propose_net_display = _safe_decimal(salaire_propose)
        if salaire_propose_net_display <= 0:
            return JsonResponse({
                'success': False,
                'error': "Le salaire net propos? doit?tre sup?rieur ?? z?ro."
            }, status=400)

        salaire_propose_net = _convert_salary_from_display(
            salaire_propose_net_display,
            contrat_actif,
            reference_grille,
        )

        preview_revalorise = _build_salary_preview_from_net(
            contrat=contrat_actif,
            employe=employe,
            date_reference=date_reference_fin,
            salaire_net=salaire_propose_net,
            reference_grille=reference_grille,
        )
        if not preview_revalorise:
            return JsonResponse({
                'success': False,
                'error': "Impossible de calculer le salaire proposé sans contrat actif."
            }, status=400)

        salaire_propose_brut = preview_revalorise.salaire_brut_base

        # Grille correspondante : Junior, ou tranche d'anciennete depuis la sortie Junior
        grille = GrilleSalariale.get_grille_for_employe(employe, date_reference_debut)
            
        # Trouver l'évaluation de référence
        evaluation = _get_reference_evaluation_for_revalorisation(employe, annee)
        
        reval, created = Revalorisation.objects.get_or_create(
            employe=employe,
            annee=int(annee),
            defaults={
                'salaire_actuel': salaire_actuel,
                'salaire_propose': salaire_propose_brut,
                'justification': justification,
                'createur': request.user.employe if hasattr(request.user, 'employe') else None,
                'grille_salariale': grille,
                'evaluation': evaluation
            }
        )
        
        if not created:
            if reval.statut not in ['brouillon', 'rejetee']:
                return JsonResponse({
                    'success': False, 
                    'error': f'Impossible de modifier une revalorisation au statut : {reval.get_statut_display()}'
                }, status=400)
                
            reval.salaire_propose = salaire_propose_brut
            reval.justification = justification
            reval.evaluation = evaluation
            reval.save()
            
        return JsonResponse({
            'success': True,
            'message': 'Revalorisation enregistrée avec succès',
            'revalorisation': {
                'id': str(reval.id),
                'salaire_propose': float(salaire_propose_net_display),
                'salaire_propose_brut': float(reval.salaire_propose),
                'pourcentage': float(_compute_percentage(
                    _convert_salary_for_display(salaire_actuel_net, contrat_actif, reference_grille),
                    salaire_propose_net_display,
                )),
                'pourcentage_brut': float(reval.pourcentage_augmentation),
                'justification': reval.justification,
                'statut': reval.statut,
                'statut_display': reval.get_statut_display()
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def api_revalorisation_update_employe(request):
    """
    Met a jour certaines donnees RH de l'employe directement depuis la page
    des revalorisations.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Methode non autorisee'}, status=405)

    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Payload JSON invalide'}, status=400)

    try:
        organisation = _get_request_organisation(request)
        if organisation is None:
            return JsonResponse({
                'success': False,
                'error': "Aucune organisation n'est associee a votre compte."
            }, status=403)

        employe_id = data.get('employe_id')
        if not employe_id:
            return JsonResponse({'success': False, 'error': "L'identifiant employe est obligatoire."}, status=400)

        employe_qs = Employe.objects.select_related('poste', 'base__organisation')
        if accessible_organisation_ids is not None:
            employe_qs = employe_qs.filter(base__organisation_id__in=accessible_organisation_ids)
        employe = get_object_or_404(
            employe_qs,
            id=employe_id,
        )

        date_embauche = _parse_iso_date(data.get('date_embauche'), "La date d'embauche")
        date_debauchage = _parse_iso_date(data.get('date_debauchage'), "La date de debauchage")

        if date_embauche and date_debauchage and date_debauchage < date_embauche:
            return JsonResponse({
                'success': False,
                'error': "La date de debauchage doit etre posterieure ou egale a la date d'embauche."
            }, status=400)

        employe.date_embauche = date_embauche
        employe.date_debauchage = date_debauchage
        employe.save(update_fields=['date_embauche', 'date_debauchage'])

        return JsonResponse({
            'success': True,
            'message': "Donnees employe mises a jour avec succes.",
            'employe': {
                'id': str(employe.id),
                'nom_complet': employe.nom_complet,
                'poste': employe.poste.nom_poste if employe.poste else 'Non assigne',
                'base': employe.base.nom_base if employe.base else 'Sans base',
                'date_embauche': employe.date_embauche.isoformat() if employe.date_embauche else None,
                'date_debauchage': employe.date_debauchage.isoformat() if employe.date_debauchage else None,
            }
        })
    except ValueError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
def api_revalorisation_action(request, reval_id, action):
    """
    Exécute une action sur une revalorisation (soumettre, valider, rejeter, appliquer).
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Méthode non autorisée'}, status=405)
        
    try:
        organisation = _get_request_organisation(request)
        if organisation is None:
            return JsonResponse({
                'success': False,
                'error': "Aucune organisation n'est associee a votre compte."
            }, status=403)
        accessible_organisation_ids = _get_request_accessible_organisation_ids(request)
        if accessible_organisation_ids == []:
            return JsonResponse({'success': False, 'error': "Aucune organisation accessible."}, status=403)

        reval_qs = Revalorisation.objects.select_related('employe__base__organisation')
        if accessible_organisation_ids is not None:
            reval_qs = reval_qs.filter(employe__base__organisation_id__in=accessible_organisation_ids)
        reval = get_object_or_404(
            reval_qs,
            id=reval_id,
        )
        data = json.loads(request.body) if request.body else {}
        commentaire = data.get('commentaire', '')
        
        employe_auth = request.user.employe if hasattr(request.user, 'employe') else None
        
        if action == 'soumettre':
            reval.soumettre()
        elif action == 'valider':
            # Optionnel: check role (DRH/Direction)
            reval.valider(validateur=employe_auth, commentaire=commentaire)
        elif action == 'rejeter':
            if not commentaire:
                return JsonResponse({'success': False, 'error': 'Le commentaire est obligatoire pour rejeter.'}, status=400)
            reval.rejeter(validateur=employe_auth, commentaire=commentaire)
        elif action == 'appliquer':
            date_application = data.get('date_application')
            import datetime
            if date_application:
                try:
                    date_obj = datetime.datetime.strptime(date_application, '%Y-%m-%d').date()
                except ValueError:
                    date_obj = timezone.now().date()
            else:
                date_obj = timezone.now().date()
                
            reval.appliquer(date_application=date_obj)
            
            # Mettre à jour le contrat avec le nouveau salaire
            # Logique métier: on pourrait créer un avenant ou juste maj le contrat courant (selon Hydria)
            contrat = Contrat.objects.filter(
                employe=reval.employe,
                debut_contrat__lte=date_obj
            ).filter(
                models.Q(fin_contrat__gte=date_obj) | models.Q(fin_contrat__isnull=True)
            ).order_by('-debut_contrat').first()
            
            if contrat:
                contrat.salaire_brut_base = reval.salaire_propose
                contrat.save()
                
        else:
            return JsonResponse({'success': False, 'error': 'Action non reconnue'}, status=400)
            
        return JsonResponse({
            'success': True,
            'message': f'Action {action} exécutée',
            'statut': reval.statut,
            'statut_display': reval.get_statut_display()
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def api_revalorisation_history(request, employe_id):
    """
    Retourne l'historique des revalorisations pour un employé.
    """
    organisation = _get_request_organisation(request)
    if organisation is None:
        return JsonResponse({
            'success': False,
            'error': "Aucune organisation n'est associee a votre compte."
        }, status=403)
    accessible_organisation_ids = _get_request_accessible_organisation_ids(request)
    if accessible_organisation_ids == []:
        return JsonResponse({'success': False, 'error': "Aucune organisation accessible."}, status=403)

    employe_qs = Employe.objects.select_related('base__organisation')
    if accessible_organisation_ids is not None:
        employe_qs = employe_qs.filter(base__organisation_id__in=accessible_organisation_ids)

    employe = get_object_or_404(
        employe_qs,
        id=employe_id,
    )

    revals = Revalorisation.objects.filter(employe=employe).order_by('-annee')

    data = []
    if revals.exists():
        for r in revals:
            date_reference = r.date_application or datetime.date(r.annee, 12, 31)
            contrat_reference = Contrat.objects.filter(
                employe=employe,
                debut_contrat__lte=date_reference
            ).filter(
                models.Q(fin_contrat__gte=date_reference) | models.Q(fin_contrat__isnull=True)
            ).order_by('-debut_contrat').first()
            reference_grille = _get_latest_salary_grid(employe, date_reference)
            preview_actuel = _build_salary_preview(
                contrat=contrat_reference,
                employe=employe,
                date_reference=date_reference,
                reference_grille=reference_grille,
                salaire_brut_base=r.salaire_actuel,
            )
            preview_propose = _build_salary_preview(
                contrat=contrat_reference,
                employe=employe,
                date_reference=date_reference,
                reference_grille=reference_grille,
                salaire_brut_base=r.salaire_propose,
            )
            salaire_actuel_net = preview_actuel.salaire_net if preview_actuel else r.salaire_actuel
            salaire_propose_net = preview_propose.salaire_net if preview_propose else r.salaire_propose
            data.append({
                'id': str(r.id),
                'periode': str(r.annee),
                'annee': r.annee,
                'salaire_actuel': float(salaire_actuel_net),
                'salaire_propose': float(salaire_propose_net),
                'statut': r.get_statut_display(),
                'pourcentage': float(_compute_percentage(salaire_actuel_net, salaire_propose_net)),
                'date_application': r.date_application.strftime('%d/%m/%Y') if r.date_application else None
            })
        return JsonResponse({'success': True, 'data': data})

    grilles = list(
        GrilleSalaire.objects.filter(contrat__employe=employe)
        .select_related('contrat')
        .order_by('date_salaire')
    )

    salaire_precedent = None
    for grille in grilles:
        salaire_courant = grille.salaire_net or Decimal('0.00')
        if salaire_precedent is not None and salaire_courant == salaire_precedent:
            continue

        pourcentage = _compute_percentage(salaire_precedent, salaire_courant)

        data.append({
            'id': str(grille.id),
            'periode': grille.date_salaire.strftime('%m/%Y'),
            'annee': grille.date_salaire.year,
            'salaire_actuel': float(salaire_precedent if salaire_precedent is not None else salaire_courant),
            'salaire_propose': float(salaire_courant),
            'statut': 'Historique paie',
            'pourcentage': float(pourcentage),
            'date_application': grille.date_salaire.strftime('%d/%m/%Y')
        })
        salaire_precedent = salaire_courant

    if data:
        return JsonResponse({'success': True, 'data': list(reversed(data))})

    contrats = Contrat.objects.filter(employe=employe).order_by('debut_contrat')
    salaire_precedent = None
    for contrat in contrats:
        reference_grille = _get_latest_salary_grid(employe, contrat.debut_contrat) if contrat.debut_contrat else None
        preview_contrat = _build_salary_preview(
            contrat=contrat,
            employe=employe,
            date_reference=contrat.debut_contrat or timezone.now().date(),
            reference_grille=reference_grille,
            salaire_brut_base=contrat.salaire_brut_base,
        )
        salaire_courant = preview_contrat.salaire_net if preview_contrat else (contrat.salaire_brut_base or Decimal('0.00'))
        if salaire_precedent is not None and salaire_courant == salaire_precedent:
            continue

        pourcentage = _compute_percentage(salaire_precedent, salaire_courant)

        date_application = contrat.debut_contrat.strftime('%d/%m/%Y') if contrat.debut_contrat else None
        periode = contrat.debut_contrat.strftime('%m/%Y') if contrat.debut_contrat else 'Contrat'
        data.append({
            'id': str(contrat.id),
            'periode': periode,
            'annee': contrat.debut_contrat.year if contrat.debut_contrat else None,
            'salaire_actuel': float(salaire_precedent if salaire_precedent is not None else salaire_courant),
            'salaire_propose': float(salaire_courant),
            'statut': 'Contrat',
            'pourcentage': float(pourcentage),
            'date_application': date_application
        })
        salaire_precedent = salaire_courant

    return JsonResponse({'success': True, 'data': list(reversed(data))})
