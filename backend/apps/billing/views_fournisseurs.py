"""
Vues pour la gestion CRUD des fournisseurs
"""
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.db.models import Q, F, Count, Sum, Max, Case, When, Value, CharField, Func
from django.db.models.functions import Lower, Trim, Coalesce
from django.core.paginator import Paginator
from django.db import transaction
from .models import Fournisseur, AdresseFournisseur, AdresseFournisseurDistrict
from .models import FournisseurFusionInstruction, FournisseurDuplicateSuggestionIgnore
from apps.infrastructure.models import Adresse
from apps.geography.models import District
import json
from datetime import datetime
from difflib import SequenceMatcher


def _clean_code_tiers(raw_value):
    """Normalize code_tiers from request payload."""
    if raw_value is None:
        return None
    value = str(raw_value).strip()
    if value == '':
        return None
    return value


def _validate_code_tiers(code_tiers, exclude_pk=None):
    """
    Validate format and uniqueness for code_tiers.
    Returns (is_valid, error_message_or_none).
    """
    if code_tiers is None:
        return True, None

    if not code_tiers.isdigit() or len(code_tiers) != 6:
        return False, 'Le code tiers doit contenir exactement 6 chiffres'

    if not code_tiers.startswith('401'):
        return False, 'Le code tiers doit commencer par 401'

    duplicate_qs = Fournisseur.objects.filter(code_tiers=code_tiers)
    if exclude_pk:
        duplicate_qs = duplicate_qs.exclude(pk=exclude_pk)
    if duplicate_qs.exists():
        return False, f'Le code tiers {code_tiers} existe deja'

    return True, None


def _fournisseur_norm_keys(fournisseur_obj):
    """Build normalized matching keys used against BaseDiameX.fournisseur."""
    keys = set()
    if not fournisseur_obj:
        return keys

    if fournisseur_obj.idxls is not None:
        idxls_value = str(fournisseur_obj.idxls).strip()
        if idxls_value:
            if idxls_value.isdigit():
                keys.add(str(int(idxls_value)))
            else:
                keys.add(idxls_value.lower())
            return keys

    nom_value = (fournisseur_obj.nom_fournisseur or '').strip().lower()
    if nom_value:
        keys.add(nom_value)

    return keys


def _diamex_fournisseur_norm_expression():
    trimmed_lower = Lower(Trim(F('fournisseur')))
    return Case(
        When(
            fournisseur__regex=r'^\s*0*\d+\s*$',
            then=Func(
                trimmed_lower,
                Value(r'^0+(?!$)'),
                Value(''),
                function='REGEXP_REPLACE',
                output_field=CharField(),
            ),
        ),
        default=trimmed_lower,
        output_field=CharField(),
    )


def _normalize_supplier_address(value):
    if value is None:
        return ''
    return ' '.join(str(value).split()).strip()


def _normalize_supplier_key(value):
    cleaned = ''.join(ch.lower() if ch.isalnum() else ' ' for ch in str(value or '').strip())
    return ' '.join(cleaned.split())


def _normalize_supplier_identity_value(value):
    if value is None:
        return ''
    return ''.join(ch.lower() for ch in str(value).strip() if ch.isalnum())


def _items_have_identity_conflict(items):
    normalized_cins = {
        normalized
        for normalized in (_normalize_supplier_identity_value(getattr(item, 'cin', '')) for item in items)
        if normalized
    }
    if len(normalized_cins) > 1:
        return True

    normalized_nifs = {
        normalized
        for normalized in (_normalize_supplier_identity_value(getattr(item, 'numero_nif', '')) for item in items)
        if normalized
    }
    if len(normalized_nifs) > 1:
        return True

    return False


DUPLICATE_GROUPS_LIMIT = 25
FUZZY_DUPLICATE_LOOKAHEAD = 80


def _build_duplicate_groups(limit=DUPLICATE_GROUPS_LIMIT):
    ignored_signatures = set()
    ignored_item_sets = set()
    for ignored in FournisseurDuplicateSuggestionIgnore.objects.only('signature', 'reason'):
        if ignored.signature:
            ignored_signatures.add(ignored.signature)
        try:
            payload = json.loads(ignored.reason or '{}') if ignored.reason else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
        item_ids = payload.get('item_ids') if isinstance(payload, dict) else None
        if isinstance(item_ids, list):
            normalized_ids = tuple(sorted(str(item_id).strip() for item_id in item_ids if str(item_id).strip()))
            if normalized_ids:
                ignored_item_sets.add(normalized_ids)
    fournisseurs_qs = (
        Fournisseur.objects
        .select_related('adresse_fournisseur')
        .only(
            'id',
            'nom_fournisseur',
            'idxls',
            'cin',
            'numero_nif',
            'adresse',
            'adresse_fournisseur__adresse',
        )
        .order_by('nom_fournisseur')
    )
    fournisseurs = list(fournisseurs_qs)
    exact_groups = {}
    for fournisseur in fournisseurs:
        key = _normalize_supplier_key(fournisseur.nom_fournisseur)
        if not key:
            continue
        exact_groups.setdefault(key, []).append(fournisseur)

    duplicates = []
    grouped_ids = set()
    for key, items in exact_groups.items():
        if len(items) <= 1:
            continue
        if _items_have_identity_conflict(items):
            continue
        grouped_ids.update(str(item.id) for item in items)
        signature = f"exact:{key}"
        item_ids_signature = tuple(sorted(str(item.id) for item in items))
        if signature in ignored_signatures or item_ids_signature in ignored_item_sets:
            continue
        duplicates.append({
            'label': items[0].nom_fournisseur,
            'items': items,
            'signature': signature,
            'item_ids': list(item_ids_signature),
            'match_type': 'exact',
            'match_label': 'Nom identique normalise',
        })
        if len(duplicates) >= limit:
            duplicates.sort(key=lambda item: item['label'].lower())
            return duplicates

    candidates = [
        {
            'obj': fournisseur,
            'norm': _normalize_supplier_key(fournisseur.nom_fournisseur),
        }
        for fournisseur in fournisseurs
        if str(fournisseur.id) not in grouped_ids
    ]

    fuzzy_grouped_ids = set()

    for index, candidate in enumerate(candidates):
        candidate_id = str(candidate['obj'].id)
        if candidate_id in fuzzy_grouped_ids or not candidate['norm']:
            continue

        current_items = [candidate['obj']]
        current_scores = []
        for other in candidates[index + 1:index + 1 + FUZZY_DUPLICATE_LOOKAHEAD]:
            other_id = str(other['obj'].id)
            if other_id in fuzzy_grouped_ids or not other['norm']:
                continue

            if abs(len(candidate['norm']) - len(other['norm'])) > 2:
                continue

            score = SequenceMatcher(None, candidate['norm'], other['norm']).ratio()
            if score < 0.84:
                continue

            current_items.append(other['obj'])
            current_scores.append(score)

        if len(current_items) > 1:
            if _items_have_identity_conflict(current_items):
                continue
            for item in current_items:
                fuzzy_grouped_ids.add(str(item.id))
            signature = "fuzzy:" + "|".join(sorted(str(item.id) for item in current_items))
            item_ids_signature = tuple(sorted(str(item.id) for item in current_items))
            if signature in ignored_signatures or item_ids_signature in ignored_item_sets:
                continue
            duplicates.append({
                'label': current_items[0].nom_fournisseur,
                'items': current_items,
                'signature': signature,
                'item_ids': list(item_ids_signature),
                'match_type': 'fuzzy',
                'match_label': f"Orthographe proche ({round(max(current_scores) * 100)}%)" if current_scores else 'Orthographe proche',
            })
            if len(duplicates) >= limit:
                duplicates.sort(key=lambda item: item['label'].lower())
                return duplicates

    duplicates.sort(key=lambda item: item['label'].lower())
    return duplicates


def _user_is_directeur(user):
    employe = getattr(user, 'employe', None)
    poste = getattr(employe, 'poste', None)
    nom_poste = getattr(poste, 'nom_poste', '') or ''
    return bool(getattr(user, 'is_superuser', False) or nom_poste.strip().lower() == 'directeur')


def _merge_fournisseur_values(target, source):
    fields = [
        'telephone', 'email', 'adresse_relation', 'adresse_fournisseur', 'adresse',
        'code_postal', 'type_fournisseur', 'nif_ou_isi', 'numero_nif',
        'numero_stat', 'cin', 'date_cin', 'lieu_cin', 'autre_information'
    ]
    changed = []
    for field_name in fields:
        source_value = getattr(source, field_name, None)
        target_value = getattr(target, field_name, None)
        if target_value in (None, '', False) and source_value not in (None, '', False):
            setattr(target, field_name, source_value)
            changed.append(field_name)

    for field_name in ['tacheron', 'devis', 'prestation', 'actif']:
        merged_value = bool(getattr(target, field_name)) or bool(getattr(source, field_name))
        if getattr(target, field_name) != merged_value:
            setattr(target, field_name, merged_value)
            changed.append(field_name)

    if changed:
        target.save(update_fields=sorted(set(changed + ['updated_at'])))


def _reassign_fournisseur_relations(source, target):
    reassigned = {}
    for relation in source._meta.related_objects:
        if relation.many_to_many or relation.related_model.__name__ == 'FournisseurFusionInstruction':
            continue
        field = getattr(relation, 'field', None)
        if field is None or not hasattr(field, 'name'):
            continue
        accessor_name = relation.get_accessor_name()
        if not accessor_name:
            continue

        if relation.one_to_one:
            try:
                related_obj = getattr(source, accessor_name)
            except relation.related_model.DoesNotExist:
                continue
            if related_obj:
                setattr(related_obj, field.name, target)
                related_obj.save(update_fields=[field.name])
                reassigned[relation.related_model._meta.verbose_name_plural] = 1
            continue

        manager = getattr(source, accessor_name, None)
        if manager is None or not hasattr(manager, 'all'):
            continue
        qs = manager.all()
        count = qs.count()
        if not count:
            continue
        qs.update(**{field.name: target})
        reassigned[relation.related_model._meta.verbose_name_plural] = count
    return reassigned


def _build_fournisseur_address_sets():
    mapped_addresses = {
        normalized
        for adresse in (
            AdresseFournisseurDistrict.objects
            .filter(actif=True)
            .values_list('adresse', flat=True)
        )
        for normalized in [_normalize_supplier_address(adresse)]
        if normalized
    }
    all_addresses = {
        normalized
        for adresse in (
            AdresseFournisseur.objects
            .filter(actif=True)
            .values_list('adresse', flat=True)
        )
        for normalized in [_normalize_supplier_address(adresse)]
        if normalized
    }
    return mapped_addresses, all_addresses


def _get_or_create_adresse_fournisseur(raw_adresse):
    normalized = _normalize_supplier_address(raw_adresse)
    if not normalized:
        return None, None
    adresse_obj, _ = AdresseFournisseur.objects.get_or_create(adresse=normalized)
    return adresse_obj, normalized


@login_required
def fournisseurs_list(request):
    """Page de liste des fournisseurs avec filtres et recherche"""
    # Récupérer les paramètres
    search_query = request.GET.get('search', '').strip()
    code_tiers_filter = request.GET.get('code_tiers', '').strip()
    compta_annee_raw = request.GET.get('compta_annee', '').strip()
    compta_mois_raw = request.GET.get('compta_mois', '').strip()
    type_filter = request.GET.get('type', '')
    statut_filter = request.GET.get('statut', '')
    adresse_district_filter = request.GET.get('adresse_district', '').strip()
    sort_by = request.GET.get('sort', 'nom_asc')
    page = request.GET.get('page', '1')
    per_page = request.GET.get('per_page', '25')

    try:
        per_page = int(per_page)
    except (TypeError, ValueError):
        per_page = 25
    per_page = max(5, min(per_page, 200))

    try:
        compta_annee = int(compta_annee_raw) if compta_annee_raw else None
    except (TypeError, ValueError):
        compta_annee = None
    try:
        compta_mois = int(compta_mois_raw) if compta_mois_raw else None
    except (TypeError, ValueError):
        compta_mois = None
    if compta_mois is not None and not (1 <= compta_mois <= 12):
        compta_mois = None

    # Requête de base
    fournisseurs_qs = Fournisseur.objects.all()
    mapped_addresses, all_addresses = _build_fournisseur_address_sets()

    # Appliquer la recherche (inclut ID XLS)
    if search_query:
        search_filters = (
            Q(nom_fournisseur__icontains=search_query) |
            Q(telephone__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(numero_nif__icontains=search_query) |
            Q(cin__icontains=search_query) |
            Q(code_tiers__icontains=search_query)
        )

        # idxls is an IntegerField: numeric exact match
        if search_query.isdigit():
            search_filters |= Q(idxls=int(search_query))

        fournisseurs_qs = fournisseurs_qs.filter(search_filters)

    # Filtrer par type
    if type_filter:
        fournisseurs_qs = fournisseurs_qs.filter(type_fournisseur=type_filter)

    # Filtrer par code tiers
    if code_tiers_filter:
        fournisseurs_qs = fournisseurs_qs.filter(code_tiers__icontains=code_tiers_filter)

    # Filtrer par statut
    if statut_filter == 'actif':
        fournisseurs_qs = fournisseurs_qs.filter(actif=True)
    elif statut_filter == 'inactif':
        fournisseurs_qs = fournisseurs_qs.filter(actif=False)

    if adresse_district_filter in ('mapped', 'unmapped'):
        matching_ids = []
        for fournisseur in fournisseurs_qs.only('id', 'adresse'):
            normalized = _normalize_supplier_address(fournisseur.adresse)
            is_mapped = bool(normalized) and normalized in mapped_addresses
            if adresse_district_filter == 'mapped' and is_mapped:
                matching_ids.append(fournisseur.id)
            elif adresse_district_filter == 'unmapped' and not is_mapped:
                matching_ids.append(fournisseur.id)
        fournisseurs_qs = fournisseurs_qs.filter(id__in=matching_ids)

    # Trier
    if sort_by == 'idxls_asc':
        fournisseurs_qs = fournisseurs_qs.order_by(F('idxls').asc(nulls_last=True), 'nom_fournisseur')
    elif sort_by == 'idxls_desc':
        fournisseurs_qs = fournisseurs_qs.order_by(F('idxls').desc(nulls_last=True), 'nom_fournisseur')
    elif sort_by == 'nom_desc':
        fournisseurs_qs = fournisseurs_qs.order_by('-nom_fournisseur', F('idxls').asc(nulls_last=True))
    else:
        sort_by = 'nom_asc'
        fournisseurs_qs = fournisseurs_qs.order_by('nom_fournisseur', F('idxls').asc(nulls_last=True))

    paginator = Paginator(fournisseurs_qs, per_page)
    page_obj = paginator.get_page(page)

    # Donnees comptables DiameX (globales/filtrees par mois/annee) pour les fournisseurs de la page
    compta_by_key = {}
    compta_available_years = []
    try:
        from apps.accounting.views_controle_conversion import _get_scoped_diamex_queryset

        diamex_scope = _get_scoped_diamex_queryset(request.user)
        years_dates = diamex_scope.exclude(date_m__isnull=True).dates('date_m', 'year', order='DESC')
        compta_available_years = [d.year for d in years_dates]
        if not compta_available_years:
            compta_available_years = [datetime.now().year]

        candidate_norm_keys = set()
        for f in page_obj.object_list:
            candidate_norm_keys.update(_fournisseur_norm_keys(f))

        if candidate_norm_keys:
            diamex_qs = diamex_scope.exclude(fournisseur__isnull=True).exclude(fournisseur='')
            if compta_annee:
                diamex_qs = diamex_qs.filter(date_m__year=compta_annee)
            if compta_mois:
                diamex_qs = diamex_qs.filter(date_m__month=compta_mois)

            diamex_qs = diamex_qs.annotate(fournisseur_norm=_diamex_fournisseur_norm_expression()).filter(
                fournisseur_norm__in=candidate_norm_keys
            )

            grouped = diamex_qs.values('fournisseur_norm').annotate(
                nb_lignes=Count('id'),
                total_in=Sum('montant_in'),
                total_out=Sum('montant_out'),
            )

            for row in grouped:
                key = row.get('fournisseur_norm') or ''
                if not key:
                    continue
                current = compta_by_key.setdefault(key, {'nb_lignes': 0, 'total_montant': 0.0})
                current['nb_lignes'] += row.get('nb_lignes') or 0
                current['total_montant'] += float(row.get('total_in') or 0) + float(row.get('total_out') or 0)
    except Exception:
        compta_available_years = [datetime.now().year]

    def _compta_stats_for_fournisseur(fournisseur_obj):
        keys = _fournisseur_norm_keys(fournisseur_obj)

        total_lignes = 0
        total_montant = 0.0
        for key in keys:
            data = compta_by_key.get(key)
            if not data:
                continue
            total_lignes += int(data.get('nb_lignes') or 0)
            total_montant += float(data.get('total_montant') or 0)
        return total_lignes, total_montant

    # Calculer statistiques sur TOUS les fournisseurs (pas seulement filtrés)
    all_fournisseurs = Fournisseur.objects.all()
    total_fournisseurs = all_fournisseurs.count()
    actifs = all_fournisseurs.filter(actif=True).count()
    inactifs = all_fournisseurs.filter(actif=False).count()
    avec_code_tiers = all_fournisseurs.exclude(code_tiers__isnull=True).exclude(code_tiers='').count()
    fournisseurs_adresse_non_affectee = 0
    for adresse in all_fournisseurs.exclude(adresse__isnull=True).exclude(adresse='').values_list('adresse', flat=True):
        normalized = _normalize_supplier_address(adresse)
        if normalized and normalized not in mapped_addresses:
            fournisseurs_adresse_non_affectee += 1
    type_labels = dict(Fournisseur.TYPE_FOURNISSEUR_CHOICES)
    stats_types = []
    for row in all_fournisseurs.values('type_fournisseur').annotate(total=Count('id')):
        type_value = row.get('type_fournisseur') or ''
        stats_types.append({
            'value': type_value,
            'label': type_labels.get(type_value, 'Non renseigne') if type_value else 'Non renseigne',
            'total': row.get('total', 0),
        })
    stats_types.sort(key=lambda x: x['label'])

    # Types disponibles
    types_fournisseurs = Fournisseur.TYPE_FOURNISSEUR_CHOICES
    merge_instructions = (
        FournisseurFusionInstruction.objects
        .select_related('source_fournisseur', 'target_fournisseur')
        .all()
    )

    # Si requête AJAX, retourner JSON
    # Vérifier plusieurs indicateurs de requête AJAX
    is_ajax = (
        request.headers.get('Accept') == 'application/json' or
        request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
        request.GET.get('format') == 'json'
    )

    if is_ajax:
        fournisseurs_data = []
        for f in page_obj.object_list:
            compta_nb_lignes, compta_total_montant = _compta_stats_for_fournisseur(f)
            fournisseurs_data.append({
                'id': str(f.id),
                'nom_fournisseur': f.nom_fournisseur,
                'type_fournisseur': f.type_fournisseur or '',
                'type_fournisseur_display': f.get_type_fournisseur_display() if f.type_fournisseur else '-',
                'code_tiers': f.code_tiers or '',
                'idxlsx': f.idxls or '',
                'telephone': f.telephone or '',
                'email': f.email or '',
                'numero_nif': f.numero_nif or '',
                'cin': f.cin or '',
                'date_cin': str(f.date_cin) if f.date_cin else '',
                'lieu_cin': f.lieu_cin or '',
                'actif': f.actif,
                'compta_nb_lignes': compta_nb_lignes,
                'compta_total_montant': round(compta_total_montant, 2),
            })

        return JsonResponse({
            'success': True,
            'fournisseurs': fournisseurs_data,
            'sort_by': sort_by,
            'pagination': {
                'page': page_obj.number,
                'per_page': per_page,
                'total_items': paginator.count,
                'total_pages': paginator.num_pages,
                'has_previous': page_obj.has_previous(),
                'has_next': page_obj.has_next(),
                'previous_page': page_obj.previous_page_number() if page_obj.has_previous() else None,
                'next_page': page_obj.next_page_number() if page_obj.has_next() else None,
                'start_index': page_obj.start_index() if paginator.count else 0,
                'end_index': page_obj.end_index() if paginator.count else 0,
            },
            'stats': {
                'total': total_fournisseurs,
                'actifs': actifs,
                'inactifs': inactifs,
                'avec_code_tiers': avec_code_tiers,
                'adresse_non_affectee': fournisseurs_adresse_non_affectee,
                'types': stats_types,
            },
            'compta_filters': {
                'annee': compta_annee,
                'mois': compta_mois,
                'available_years': compta_available_years,
            },
        })

    # Sinon, afficher la page HTML
    return render(request, 'billing/fournisseurs_list.html', {
        'fournisseurs': fournisseurs_qs,
        'title': 'Fournisseurs',
        'search_query': search_query,
        'code_tiers_filter': code_tiers_filter,
        'compta_annee': compta_annee,
        'compta_mois': compta_mois,
        'compta_available_years': compta_available_years,
        'type_filter': type_filter,
        'statut_filter': statut_filter,
        'sort_by': sort_by,
        'page': page_obj.number,
        'per_page': per_page,
        'types_fournisseur': types_fournisseurs,
        'adresse_district_filter': adresse_district_filter,
        'adresses_fournisseur_options': sorted(all_addresses),
        'merge_instructions': merge_instructions,
        'duplicate_groups_count': FournisseurDuplicateSuggestionIgnore.objects.count(),
        'can_merge_fournisseurs': _user_is_directeur(request.user),
        'stats': {
            'total': total_fournisseurs,
            'actifs': actifs,
            'inactifs': inactifs,
            'avec_code_tiers': avec_code_tiers,
            'adresse_non_affectee': fournisseurs_adresse_non_affectee,
            'types': stats_types,
        }
    })


@login_required
def fournisseurs_duplicates(request):
    if not _user_is_directeur(request.user):
        return JsonResponse({'success': False, 'error': 'Acces reserve au directeur'}, status=403)

    duplicate_groups = _build_duplicate_groups()
    merge_instructions = (
        FournisseurFusionInstruction.objects
        .select_related('source_fournisseur', 'target_fournisseur')
        .all()
    )
    fournisseurs = (
        Fournisseur.objects
        .only('id', 'nom_fournisseur', 'idxls')
        .order_by('nom_fournisseur')
    )

    return render(request, 'billing/fournisseurs_duplicates.html', {
        'title': 'Doublons fournisseurs',
        'duplicate_groups': duplicate_groups,
        'merge_instructions': merge_instructions,
        'fournisseurs': fournisseurs,
        'can_merge_fournisseurs': True,
    })


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def fournisseur_merge_api(request):
    if not _user_is_directeur(request.user):
        return JsonResponse({'success': False, 'error': 'Acces reserve au directeur'}, status=403)

    try:
        data = json.loads(request.body)
        source_id = data.get('source_fournisseur_id')
        target_id = data.get('target_fournisseur_id')

        if not source_id or not target_id:
            return JsonResponse({'success': False, 'error': 'Source et cible sont obligatoires'}, status=400)
        if source_id == target_id:
            return JsonResponse({'success': False, 'error': 'Source et cible doivent etre differentes'}, status=400)

        source = get_object_or_404(Fournisseur, pk=source_id)
        target = get_object_or_404(Fournisseur, pk=target_id)

        with transaction.atomic():
            _merge_fournisseur_values(target, source)
            reassigned = _reassign_fournisseur_relations(source, target)

            instruction = None
            if source.idxls is not None and target.idxls is not None and source.idxls != target.idxls:
                from apps.accounting.models import BaseDiameX
                affected_qs = BaseDiameX.objects.filter(fournisseur__iexact=str(source.idxls)).order_by('-date_m', '-id')
                affected_count = affected_qs.count()
                affected_rows = []
                for row in affected_qs[:100]:
                    affected_rows.append({
                        'id': row.id,
                        'date_m': row.date_m.isoformat() if row.date_m else '',
                        'date_rec': row.date_rec.isoformat() if row.date_rec else '',
                        'rec': row.rec or '',
                        'journal_code': row.journal_code or '',
                        'compte_code': row.compte_code or '',
                        'description': row.description or '',
                        'detail': row.detail or '',
                        'fichier_source': row.fichier_source or '',
                        'fournisseur': row.fournisseur or '',
                        'montant_in': float(row.montant_in or 0),
                        'montant_out': float(row.montant_out or 0),
                    })
                instruction = FournisseurFusionInstruction.objects.create(
                    source_fournisseur=source,
                    target_fournisseur=target,
                    source_nom_snapshot=source.nom_fournisseur or '',
                    target_nom_snapshot=target.nom_fournisseur or '',
                    ancien_idxls=source.idxls,
                    nouvel_idxls=target.idxls,
                    lignes_diamex_a_corriger=affected_count,
                    lignes_diamex_details=affected_rows,
                    note=(
                        f"Fusion fournisseur effectuee: '{source.nom_fournisseur}' ({source.idxls}) vers "
                        f"'{target.nom_fournisseur}' ({target.idxls}). Corriger dans DiameX le code "
                        f"fournisseur {source.idxls} en {target.idxls} sur les lignes comptables concernees."
                    ),
                )

            source_nom = source.nom_fournisseur
            target_nom = target.nom_fournisseur
            source.delete()

        details = ', '.join(f'{label}: {count}' for label, count in sorted(reassigned.items()))
        message = f'Fournisseur "{source_nom}" fusionne vers "{target_nom}".'
        if details:
            message += f' Reaffectations: {details}.'
        if instruction:
            message += ' Instruction DiameX creee.'
        return JsonResponse({'success': True, 'message': message})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def fournisseur_merge_instruction_update_api(request, instruction_id):
    if not _user_is_directeur(request.user):
        return JsonResponse({'success': False, 'error': 'Acces reserve au directeur'}, status=403)

    try:
        data = json.loads(request.body)
        instruction = get_object_or_404(FournisseurFusionInstruction, pk=instruction_id)
        statut = (data.get('statut') or '').strip()
        commentaire_admin = (data.get('commentaire_admin') or '').strip()

        if statut not in {
            FournisseurFusionInstruction.STATUS_PENDING,
            FournisseurFusionInstruction.STATUS_DONE,
        }:
            return JsonResponse({'success': False, 'error': 'Statut invalide'}, status=400)

        instruction.statut = statut
        instruction.commentaire_admin = commentaire_admin
        instruction.done_at = datetime.now() if statut == FournisseurFusionInstruction.STATUS_DONE else None
        instruction.save(update_fields=['statut', 'commentaire_admin', 'done_at', 'updated_at'])
        return JsonResponse({'success': True, 'message': 'Instruction mise a jour'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def fournisseur_duplicate_ignore_api(request):
    if not _user_is_directeur(request.user):
        return JsonResponse({'success': False, 'error': 'Acces reserve au directeur'}, status=403)

    try:
        data = json.loads(request.body)
        signature = (data.get('signature') or '').strip()
        label = (data.get('label') or '').strip()
        raw_reason = data.get('reason')
        item_ids = data.get('item_ids') or []
        if isinstance(raw_reason, str) and raw_reason.strip():
            reason = raw_reason.strip()
        else:
            reason = json.dumps({'item_ids': item_ids})

        if not signature:
            return JsonResponse({'success': False, 'error': 'Signature suggestion obligatoire'}, status=400)

        FournisseurDuplicateSuggestionIgnore.objects.get_or_create(
            signature=signature,
            defaults={
                'label': label,
                'reason': reason,
            }
        )
        return JsonResponse({'success': True, 'message': 'Suggestion retiree de la liste'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def fournisseur_duplicate_ignore_batch_api(request):
    if not _user_is_directeur(request.user):
        return JsonResponse({'success': False, 'error': 'Acces reserve au directeur'}, status=403)

    try:
        data = json.loads(request.body)
        suggestions = data.get('suggestions') or []
        if not isinstance(suggestions, list) or not suggestions:
            return JsonResponse({'success': False, 'error': 'Suggestions obligatoires'}, status=400)

        ignored_count = 0
        for item in suggestions:
            if not isinstance(item, dict):
                continue
            signature = (item.get('signature') or '').strip()
            label = (item.get('label') or '').strip()
            raw_reason = item.get('reason')
            item_ids = item.get('item_ids') or []
            if isinstance(raw_reason, str) and raw_reason.strip():
                reason = raw_reason.strip()
            else:
                reason = json.dumps({'item_ids': item_ids})
            if not signature:
                continue
            _, created = FournisseurDuplicateSuggestionIgnore.objects.get_or_create(
                signature=signature,
                defaults={
                    'label': label,
                    'reason': reason,
                }
            )
            if created:
                ignored_count += 1

        return JsonResponse({
            'success': True,
            'message': f'{ignored_count} suggestion(s) retiree(s) de la liste',
            'ignored_count': ignored_count,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def fournisseurs_adresses_districts(request):
    search_query = (request.GET.get('search') or '').strip()
    statut = (request.GET.get('statut') or 'unmapped').strip()
    sort_by = (request.GET.get('sort') or 'adresse').strip()
    page = request.GET.get('page', '1')
    per_page_raw = request.GET.get('per_page', '50').strip()

    try:
        per_page = int(per_page_raw)
    except (TypeError, ValueError):
        per_page = 50
    per_page = max(10, min(per_page, 200))

    fournisseurs = Fournisseur.objects.select_related('adresse_fournisseur').only('adresse', 'adresse_fournisseur__adresse')
    addresses_counter = {}
    for fournisseur in fournisseurs:
        adresse_value = fournisseur.adresse_fournisseur.adresse if fournisseur.adresse_fournisseur_id else fournisseur.adresse
        normalized = _normalize_supplier_address(adresse_value)
        if not normalized:
            continue
        addresses_counter[normalized] = addresses_counter.get(normalized, 0) + 1

    mappings = {
        _normalize_supplier_address(mapping.adresse_fournisseur.adresse if mapping.adresse_fournisseur_id else mapping.adresse): mapping
        for mapping in AdresseFournisseurDistrict.objects.select_related('adresse_fournisseur', 'district__region__ex_province')
    }

    rows = []
    for adresse, usage_count in addresses_counter.items():
        mapping = mappings.get(adresse)
        is_mapped = mapping is not None and mapping.actif
        if statut == 'mapped' and not is_mapped:
            continue
        if statut == 'unmapped' and is_mapped:
            continue
        if search_query and search_query.lower() not in adresse.lower():
            continue

        district = getattr(mapping, 'district', None)
        region = getattr(district, 'region', None) if district else None
        ex_province = getattr(region, 'ex_province', None) if region else None
        rows.append({
            'adresse': adresse,
            'usage_count': usage_count,
            'mapping_id': str(mapping.id) if mapping else '',
            'district_id': str(district.id) if district else '',
            'district_nom': district.nom_district if district else '',
            'region_nom': region.nom_region if region else '',
            'ex_province_nom': ex_province.nom_ex_province if ex_province else '',
            'actif': bool(mapping.actif) if mapping else False,
            'is_mapped': is_mapped,
        })

    if sort_by == 'fournisseurs':
        rows.sort(key=lambda row: (-row['usage_count'], row['adresse'].lower()))
    else:
        sort_by = 'adresse'
        rows.sort(key=lambda row: row['adresse'].lower())
    paginator = Paginator(rows, per_page)
    page_obj = paginator.get_page(page)
    districts = District.objects.select_related('region__ex_province').order_by(
        'region__ex_province__nom_ex_province',
        'region__nom_region',
        'nom_district',
    )

    return render(request, 'billing/fournisseurs_adresses_districts.html', {
        'rows': page_obj.object_list,
        'page_obj': page_obj,
        'per_page': per_page,
        'all_addresses': [row['adresse'] for row in rows],
        'districts': districts,
        'search_query': search_query,
        'statut': statut,
        'sort_by': sort_by,
        'stats': {
            'total': len(rows),
            'mapped': sum(1 for row in rows if row['is_mapped']),
            'unmapped': sum(1 for row in rows if not row['is_mapped']),
        },
    })


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def fournisseur_adresse_mapping_upsert_api(request):
    try:
        data = json.loads(request.body)
        adresse = _normalize_supplier_address(data.get('adresse'))
        district_id = data.get('district_id')
        actif = bool(data.get('actif', True))

        if not adresse:
            return JsonResponse({'success': False, 'error': "L'adresse est obligatoire"}, status=400)
        if not district_id:
            return JsonResponse({'success': False, 'error': 'Le district est obligatoire'}, status=400)

        district = get_object_or_404(District, pk=district_id)
        adresse_obj, normalized = _get_or_create_adresse_fournisseur(adresse)
        mapping, created = AdresseFournisseurDistrict.objects.update_or_create(
            adresse_fournisseur=adresse_obj,
            defaults={
                'adresse': normalized,
                'district': district,
                'actif': actif,
            }
        )
        return JsonResponse({
            'success': True,
            'created': created,
            'message': 'Correspondance enregistrée avec succès',
            'mapping_id': str(mapping.id),
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def fournisseur_adresse_create_api(request):
    try:
        data = json.loads(request.body)
        adresse = _normalize_supplier_address(data.get('adresse'))
        if not adresse:
            return JsonResponse({'success': False, 'error': "L'adresse est obligatoire"}, status=400)
        adresse_obj, created = AdresseFournisseur.objects.get_or_create(adresse=adresse)
        return JsonResponse({
            'success': True,
            'created': created,
            'message': 'Adresse creee avec succes' if created else 'Adresse deja existante',
            'adresse': adresse_obj.adresse,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def fournisseur_adresse_detail_api(request):
    adresse = _normalize_supplier_address(request.GET.get('adresse'))
    if not adresse:
        return JsonResponse({'success': False, 'error': "L'adresse est obligatoire"}, status=400)

    adresse_obj = AdresseFournisseur.objects.filter(adresse=adresse).first()
    fournisseurs_qs = Fournisseur.objects.filter(adresse_fournisseur=adresse_obj).order_by('nom_fournisseur') if adresse_obj else Fournisseur.objects.filter(adresse__iexact=adresse).order_by('nom_fournisseur')

    fournisseurs = [{
        'id': str(fournisseur.id),
        'nom_fournisseur': fournisseur.nom_fournisseur,
        'type_fournisseur': fournisseur.get_type_fournisseur_display() if fournisseur.type_fournisseur else '',
        'telephone': fournisseur.telephone or '',
        'email': fournisseur.email or '',
        'actif': fournisseur.actif,
    } for fournisseur in fournisseurs_qs]

    return JsonResponse({
        'success': True,
        'adresse': adresse,
        'fournisseurs': fournisseurs,
    })


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def fournisseur_adresse_update_api(request):
    try:
        data = json.loads(request.body)
        old_adresse = _normalize_supplier_address(data.get('old_adresse'))
        new_adresse = _normalize_supplier_address(data.get('new_adresse'))

        if not old_adresse:
            return JsonResponse({'success': False, 'error': "L'adresse source est obligatoire"}, status=400)
        if not new_adresse:
            return JsonResponse({'success': False, 'error': "La nouvelle adresse est obligatoire"}, status=400)

        if old_adresse == new_adresse:
            return JsonResponse({'success': True, 'message': 'Adresse inchangee'})

        if AdresseFournisseur.objects.filter(adresse=new_adresse).exists():
            return JsonResponse({'success': False, 'error': 'Cette adresse existe deja'}, status=400)

        with transaction.atomic():
            adresse_obj = AdresseFournisseur.objects.filter(adresse=old_adresse).first()
            if adresse_obj:
                adresse_obj.adresse = new_adresse
                adresse_obj.save(update_fields=['adresse', 'updated_at'])

                Fournisseur.objects.filter(adresse_fournisseur=adresse_obj).update(adresse=new_adresse)
                AdresseFournisseurDistrict.objects.filter(adresse_fournisseur=adresse_obj).update(adresse=new_adresse)
            else:
                Fournisseur.objects.filter(adresse__iexact=old_adresse).update(adresse=new_adresse)
                AdresseFournisseurDistrict.objects.filter(adresse__iexact=old_adresse).update(adresse=new_adresse)

        return JsonResponse({'success': True, 'message': 'Adresse mise a jour avec succes'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def fournisseur_adresse_merge_api(request):
    try:
        data = json.loads(request.body)
        source_adresse = _normalize_supplier_address(data.get('source_adresse'))
        target_adresse = _normalize_supplier_address(data.get('target_adresse'))

        if not source_adresse:
            return JsonResponse({'success': False, 'error': "L'adresse source est obligatoire"}, status=400)
        if not target_adresse:
            return JsonResponse({'success': False, 'error': "L'adresse cible est obligatoire"}, status=400)
        if source_adresse == target_adresse:
            return JsonResponse({'success': False, 'error': "L'adresse cible doit etre differente"}, status=400)

        source_obj = AdresseFournisseur.objects.filter(adresse=source_adresse).first()
        target_obj = AdresseFournisseur.objects.filter(adresse=target_adresse).first()
        if not source_obj:
            return JsonResponse({'success': False, 'error': "Adresse source introuvable"}, status=404)
        if not target_obj:
            return JsonResponse({'success': False, 'error': "Adresse cible introuvable"}, status=404)

        source_mapping = AdresseFournisseurDistrict.objects.filter(adresse_fournisseur=source_obj).first()
        target_mapping = AdresseFournisseurDistrict.objects.filter(adresse_fournisseur=target_obj).first()

        if source_mapping and target_mapping and source_mapping.district_id != target_mapping.district_id:
            return JsonResponse({
                'success': False,
                'error': "Fusion bloquee: les deux adresses ont des districts differents"
            }, status=400)

        with transaction.atomic():
            if source_mapping and not target_mapping:
                source_mapping.adresse_fournisseur = target_obj
                source_mapping.adresse = target_obj.adresse
                source_mapping.save(update_fields=['adresse_fournisseur', 'adresse', 'updated_at'])
                target_mapping = source_mapping
                source_mapping = None

            Fournisseur.objects.filter(adresse_fournisseur=source_obj).update(
                adresse_fournisseur=target_obj,
                adresse=target_obj.adresse,
            )

            if source_mapping:
                source_mapping.delete()

            if target_mapping:
                AdresseFournisseurDistrict.objects.filter(pk=target_mapping.pk).update(adresse=target_obj.adresse)

            source_obj.delete()

        return JsonResponse({'success': True, 'message': 'Fusion realisee avec succes'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def fournisseur_code_tiers_disponible_api(request):
    """API to expose available code tiers suggestions."""
    requested_code = _clean_code_tiers(request.GET.get('code_tiers'))

    used_codes = list(
        Fournisseur.objects
        .exclude(code_tiers__isnull=True)
        .exclude(code_tiers='')
        .filter(code_tiers__startswith='401')
        .values_list('code_tiers', flat=True)
    )

    used_numeric = sorted({int(code) for code in used_codes if str(code).isdigit() and len(str(code)) == 6})
    min_code = 401000
    max_code = 401999

    if used_numeric:
        next_candidate = used_numeric[-1] + 1
    else:
        next_candidate = min_code

    suggestions = []
    used_numeric_set = set(used_numeric)
    current = next_candidate
    while len(suggestions) < 5 and current <= max_code:
        if current not in used_numeric_set:
            suggestions.append(f"{current:06d}")
        current += 1

    is_valid_format = True
    is_available = None
    existing_supplier = None

    max_idxls = Fournisseur.objects.aggregate(max_idxls=Max('idxls')).get('max_idxls')
    next_idxls = (int(max_idxls) + 1) if max_idxls is not None else 1

    if requested_code:
        is_valid_format = (
            requested_code.isdigit() and
            len(requested_code) == 6 and
            requested_code.startswith('401')
        )
        if is_valid_format:
            existing = (
                Fournisseur.objects
                .filter(code_tiers=requested_code)
                .values('id', 'nom_fournisseur')
                .first()
            )
            is_available = existing is None
            if existing:
                existing_supplier = {
                    'id': str(existing['id']),
                    'nom_fournisseur': existing['nom_fournisseur'],
                }
        else:
            is_available = False

    return JsonResponse({
        'success': True,
        'requested_code': requested_code or '',
        'is_valid_format': is_valid_format,
        'is_available': is_available,
        'existing_supplier': existing_supplier,
        'next_available': f"{next_candidate:06d}" if next_candidate <= max_code else None,
        'suggestions': suggestions,
        'used_count': len(used_codes),
        'max_idxls': max_idxls,
        'next_idxls': next_idxls,
    })


@login_required
@require_http_methods(["GET"])
def fournisseur_detail_api(request, pk):
    """API pour obtenir les détails d'un fournisseur"""
    try:
        fournisseur = get_object_or_404(Fournisseur, pk=pk)

        return JsonResponse({
            'success': True,
            'fournisseur': {
                'id': str(fournisseur.id),
                'nom_fournisseur': fournisseur.nom_fournisseur,
                'telephone': fournisseur.telephone or '',
                'email': fournisseur.email or '',
                'adresse': fournisseur.adresse_fournisseur.adresse if fournisseur.adresse_fournisseur_id else (fournisseur.adresse or ''),
                'code_postal': fournisseur.code_postal or '',
                'type_fournisseur': fournisseur.type_fournisseur or '',
                'nif_ou_isi': fournisseur.nif_ou_isi or '',
                'numero_nif': fournisseur.numero_nif or '',
                'numero_stat': fournisseur.numero_stat or '',
                'cin': fournisseur.cin or '',
                'date_cin': str(fournisseur.date_cin) if fournisseur.date_cin else '',
                'code_tiers': fournisseur.code_tiers or '',
                'idxlsx': fournisseur.idxls or '',
                'autre_information': fournisseur.autre_information or '',
                'tacheron': fournisseur.tacheron,
                'devis': fournisseur.devis,
                'prestation': fournisseur.prestation,
                'actif': fournisseur.actif,
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def fournisseur_compta_details_api(request, pk):
    """API pour lister les lignes comptables DiameX d'un fournisseur."""
    try:
        fournisseur = get_object_or_404(Fournisseur, pk=pk)

        compta_annee_raw = request.GET.get('compta_annee', '').strip()
        compta_mois_raw = request.GET.get('compta_mois', '').strip()
        sort_date = request.GET.get('sort_date', 'desc').strip().lower()
        page_raw = request.GET.get('page', '1')
        per_page_raw = request.GET.get('per_page', '25')
        if sort_date not in ('asc', 'desc'):
            sort_date = 'desc'

        try:
            page = int(page_raw)
        except (TypeError, ValueError):
            page = 1
        page = max(1, page)

        try:
            per_page = int(per_page_raw)
        except (TypeError, ValueError):
            per_page = 25
        per_page = max(5, min(per_page, 200))

        def _empty_response(page_value=1):
            return JsonResponse({
                'success': True,
                'fournisseur': {
                    'id': str(fournisseur.id),
                    'nom_fournisseur': fournisseur.nom_fournisseur or '',
                    'idxls': fournisseur.idxls,
                },
                'lignes': [],
                'totaux': {
                    'nb_lignes': 0,
                    'total_in': 0.0,
                    'total_out': 0.0,
                    'total_mouvement': 0.0,
                },
                'pagination': {
                    'page': page_value,
                    'per_page': per_page,
                    'total_items': 0,
                    'total_pages': 0,
                    'has_previous': False,
                    'has_next': False,
                    'previous_page': None,
                    'next_page': None,
                    'start_index': 0,
                    'end_index': 0,
                },
            })

        try:
            compta_annee = int(compta_annee_raw) if compta_annee_raw else None
        except (TypeError, ValueError):
            compta_annee = None
        try:
            compta_mois = int(compta_mois_raw) if compta_mois_raw else None
        except (TypeError, ValueError):
            compta_mois = None
        if compta_mois is not None and not (1 <= compta_mois <= 12):
            compta_mois = None

        fournisseur_keys = _fournisseur_norm_keys(fournisseur)
        if not fournisseur_keys:
            return _empty_response(1)

        try:
            from apps.accounting.views_controle_conversion import _get_scoped_diamex_queryset
            diamex_qs = _get_scoped_diamex_queryset(request.user)
        except Exception:
            # Fallback defensif: si le scope utilisateur est indisponible, retourner vide au lieu d'une 500.
            return _empty_response(1)

        diamex_qs = diamex_qs.exclude(
            fournisseur__isnull=True
        ).exclude(
            fournisseur=''
        )

        if compta_annee:
            diamex_qs = diamex_qs.filter(date_m__year=compta_annee)
        if compta_mois:
            diamex_qs = diamex_qs.filter(date_m__month=compta_mois)

        diamex_qs = diamex_qs.annotate(
            fournisseur_norm=_diamex_fournisseur_norm_expression()
        ).filter(
            fournisseur_norm__in=fournisseur_keys
        )

        totals = diamex_qs.aggregate(
            nb_lignes=Count('id'),
            total_in=Sum('montant_in'),
            total_out=Sum('montant_out'),
        )
        total_in = float(totals.get('total_in') or 0)
        total_out = float(totals.get('total_out') or 0)

        diamex_qs = diamex_qs.annotate(date_tri=Coalesce('date_rec', 'date_m'))
        if sort_date == 'asc':
            diamex_qs = diamex_qs.order_by('date_tri', 'id')
        else:
            diamex_qs = diamex_qs.order_by('-date_tri', '-id')

        paginator = Paginator(diamex_qs, per_page)
        page_obj = paginator.get_page(page)

        lignes = []
        for ligne in page_obj.object_list:
            montant_in = float(ligne.montant_in or 0)
            montant_out = float(ligne.montant_out or 0)
            lignes.append({
                'id': ligne.id,
                'id_access': ligne.id_access,
                'date_m': ligne.date_m.isoformat() if ligne.date_m else '',
                'date_rec': ligne.date_rec.isoformat() if ligne.date_rec else '',
                'journal_code': ligne.journal_code or '',
                'compte_code': ligne.compte_code or '',
                'description': ligne.description or '',
                'fournisseur': ligne.fournisseur or '',
                'montant_in': montant_in,
                'montant_out': montant_out,
                'montant_mouvement': montant_in + montant_out,
                'detail': ligne.detail or '',
                'info': ligne.info or '',
                'prog': ligne.prog or '',
                'fichier_source': ligne.fichier_source or '',
            })

        return JsonResponse({
            'success': True,
            'sort_date': sort_date,
            'fournisseur': {
                'id': str(fournisseur.id),
                'nom_fournisseur': fournisseur.nom_fournisseur or '',
                'idxls': fournisseur.idxls,
            },
            'lignes': lignes,
            'totaux': {
                'nb_lignes': int(totals.get('nb_lignes') or 0),
                'total_in': round(total_in, 2),
                'total_out': round(total_out, 2),
                'total_mouvement': round(total_in + total_out, 2),
            },
            'pagination': {
                'page': page_obj.number,
                'per_page': per_page,
                'total_items': paginator.count,
                'total_pages': paginator.num_pages,
                'has_previous': page_obj.has_previous(),
                'has_next': page_obj.has_next(),
                'previous_page': page_obj.previous_page_number() if page_obj.has_previous() else None,
                'next_page': page_obj.next_page_number() if page_obj.has_next() else None,
                'start_index': page_obj.start_index() if paginator.count else 0,
                'end_index': page_obj.end_index() if paginator.count else 0,
            },
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def fournisseur_create_api(request):
    """API pour créer un nouveau fournisseur"""
    try:
        data = json.loads(request.body)

        # Validation
        if not data.get('nom_fournisseur'):
            return JsonResponse({
                'success': False,
                'error': 'Le nom du fournisseur est obligatoire'
            }, status=400)

        code_tiers = _clean_code_tiers(data.get('code_tiers'))
        is_valid, code_error = _validate_code_tiers(code_tiers)
        if not is_valid:
            return JsonResponse({
                'success': False,
                'error': code_error
            }, status=400)

        # Créer le fournisseur
        adresse_obj, adresse = _get_or_create_adresse_fournisseur(data.get('adresse'))
        fournisseur = Fournisseur.objects.create(
            nom_fournisseur=data.get('nom_fournisseur'),
            telephone=data.get('telephone'),
            email=data.get('email'),
            adresse_fournisseur=adresse_obj,
            adresse=adresse,
            code_postal=data.get('code_postal'),
            type_fournisseur=data.get('type_fournisseur') if data.get('type_fournisseur') else None,
            nif_ou_isi=data.get('nif_ou_isi', ''),
            numero_nif=data.get('numero_nif'),
            numero_stat=data.get('numero_stat'),
            cin=data.get('cin'),
            date_cin=data.get('date_cin') if data.get('date_cin') else None,
            code_tiers=code_tiers,
            idxls=data.get('idxlsx'),
            autre_information=data.get('autre_information'),
            tacheron=data.get('tacheron', False),
            devis=data.get('devis', False),
            prestation=data.get('prestation', False),
            actif=data.get('actif', True),
        )

        return JsonResponse({
            'success': True,
            'message': 'Fournisseur créé avec succès',
            'fournisseur_id': str(fournisseur.id)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def fournisseur_update_api(request, pk):
    """API pour mettre à jour un fournisseur"""
    try:
        fournisseur = get_object_or_404(Fournisseur, pk=pk)
        data = json.loads(request.body)

        # Validation
        if not data.get('nom_fournisseur'):
            return JsonResponse({
                'success': False,
                'error': 'Le nom du fournisseur est obligatoire'
            }, status=400)

        code_tiers = _clean_code_tiers(data.get('code_tiers'))
        is_valid, code_error = _validate_code_tiers(code_tiers, exclude_pk=fournisseur.pk)
        if not is_valid:
            return JsonResponse({
                'success': False,
                'error': code_error
            }, status=400)

        # Mettre à jour
        adresse_obj, adresse = _get_or_create_adresse_fournisseur(data.get('adresse'))
        fournisseur.nom_fournisseur = data.get('nom_fournisseur')
        fournisseur.telephone = data.get('telephone')
        fournisseur.email = data.get('email')
        fournisseur.adresse_fournisseur = adresse_obj
        fournisseur.adresse = adresse
        fournisseur.code_postal = data.get('code_postal')
        fournisseur.type_fournisseur = data.get('type_fournisseur') if data.get('type_fournisseur') else None
        fournisseur.nif_ou_isi = data.get('nif_ou_isi', '')
        fournisseur.numero_nif = data.get('numero_nif')
        fournisseur.numero_stat = data.get('numero_stat')
        fournisseur.cin = data.get('cin')
        fournisseur.date_cin = data.get('date_cin') if data.get('date_cin') else None
        fournisseur.code_tiers = code_tiers
        fournisseur.idxls = data.get('idxlsx')
        fournisseur.autre_information = data.get('autre_information')
        fournisseur.tacheron = data.get('tacheron', False)
        fournisseur.devis = data.get('devis', False)
        fournisseur.prestation = data.get('prestation', False)
        fournisseur.actif = data.get('actif', True)

        fournisseur.save()

        return JsonResponse({
            'success': True,
            'message': 'Fournisseur modifié avec succès'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def fournisseur_delete_api(request, pk):
    """API pour supprimer un fournisseur"""
    try:
        fournisseur = get_object_or_404(Fournisseur, pk=pk)
        nom = fournisseur.nom_fournisseur
        fournisseur.delete()

        return JsonResponse({
            'success': True,
            'message': f'Fournisseur "{nom}" supprimé avec succès'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
