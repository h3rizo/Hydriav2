from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from apps.core.auth_tokens import diamex_agent_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse
from django.db import transaction
from django.core.paginator import Paginator
import uuid
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models import Q, Sum, Count, Max, F, Case, When, Value, CharField
from django.db.models.functions import Lower, Trim
from django.utils import timezone
from django.utils.text import slugify
from decimal import Decimal
try:
    import pyodbc
    PYODBC_AVAILABLE = True
except ImportError:
    PYODBC_AVAILABLE = False
    pyodbc = None
import os
import json
import time
import unicodedata
import re
from datetime import datetime
import calendar
from collections import defaultdict
from io import BytesIO
try:
    from PIL import Image
except ImportError:
    Image = None
from .models import BaseDiameX, RemarqueRecouvrementVolume, SoldesReels
from apps.organization.models import Base, Journal, Compte, Organisation
from apps.organization.scoping import (
    apply_user_responsable_ouvrage_scope,
    current_modalite_q,
    filter_current_modalites,
    get_user_accessible_gestionnaire_ids,
    get_user_organisation,
)
from apps.planning.models import PlanningDetail, Designation
from .views_verification_ouvrages import diviser_paiement_volume_multi
from .extracteurs_description import extraire_ouvrage_et_mois_generique
from .pointage_auto import build_auto_pointage_suggestions


def _normalize_text(value):
    """Normalise une chaîne pour comparaison (sans accents, en minuscule)."""
    if not value:
        return ''
    normalized = unicodedata.normalize('NFKD', str(value))
    return normalized.encode('ascii', errors='ignore').decode('ascii').lower().strip()


def _normalize_fin_bucket(value):
    normalized = _normalize_text(value)
    return re.sub(r'[^a-z0-9]+', '', normalized)


def _clean_fin_label(value):
    if value is None:
        return ''
    return re.sub(r'\s+', ' ', str(value)).strip()


def _build_dashboard_fin_filter_options(raw_values, selected_values):
    """Regroupe les variantes du champ Fin et prepare le filtre multi-selection."""
    buckets = {}
    for raw_value in raw_values:
        label = _clean_fin_label(raw_value) or 'Sans financement'
        key = _normalize_fin_bucket(label) or 'sansfinancement'
        bucket = buckets.setdefault(key, {'value': key, 'label': label, 'raw_values': []})
        if label != 'Sans financement' and len(label) < len(bucket['label']):
            bucket['label'] = label
        if raw_value not in bucket['raw_values']:
            bucket['raw_values'].append(raw_value)

    selected = list(dict.fromkeys(value for value in selected_values if value))
    options = sorted(buckets.values(), key=lambda item: _normalize_text(item['label']))
    matching_raw_values = [
        raw_value
        for key in selected
        for raw_value in buckets.get(key, {}).get('raw_values', [])
    ]
    for option in options:
        option['selected'] = option['value'] in selected

    return options, selected, matching_raw_values


EMPLOYEE_PAYMENT_PARENT_CATEGORIES = {'Salaires', 'Charges salariales', 'Indemnité'}


def _group_dashboard_parent_category(categorie):
    if categorie in EMPLOYEE_PAYMENT_PARENT_CATEGORIES:
        return 'Paiements employés'
    return categorie


def _is_edf_financement_entry(entry):
    """EDF = opérations FND, sans dépendre du libellé."""
    compte_code = (getattr(entry, 'compte_code', '') or '').strip().upper()
    journal_code = (getattr(entry, 'journal_code', '') or '').strip().upper()
    return (
        compte_code.startswith(('00FND1', '00FND2', '00FND3', '00FND4')) or
        journal_code.startswith(('00FND1', '00FND2', '00FND3', '00FND4'))
    )


ENTRY_COMPTE_CATEGORY_CHOICES = [
    ('paiements_employes', 'Paiements employés'),
    ('paiements_fournisseurs', 'Paiements fournisseurs'),
    ('avec_ouvrage', 'Paiements ou recettes avec ouvrage'),
    ('compte_tiers', 'Compte de tiers'),
    ('transfert', 'Transfert'),
    ('sans_ouvrage', 'Paiement sans ouvrage'),
]

OUVRAGE_EXTRACTION_ACCOUNT_CODES = {
    '707401', '748411', '748415', '748201', '621102', '625107', '761000', '761002'
}


def _get_entry_compte_category_key(entry):
    compte = getattr(entry, 'compte', None)
    compte_code = (getattr(entry, 'compte_code', '') or '').upper()
    journal_code = (getattr(entry, 'journal_code', '') or '').upper()

    if (
        '00BOOK' in compte_code or '00BOOK' in journal_code or
        '00FND1' in compte_code or '00FND1' in journal_code or
        '00FND2' in compte_code or '00FND2' in journal_code or
        '00FND3' in compte_code or '00FND3' in journal_code
    ):
        return 'transfert'

    # 00PERS en compte signifie un vrai compte tiers.
    # 00PERS en journal seul ne doit pas écraser les règles métier du compte.
    if '00PERS' in compte_code:
        return 'compte_tiers'

    if compte:
        if compte.employe_obligatoire:
            return 'paiements_employes'
        if compte.fournisseur_obligatoire:
            return 'paiements_fournisseurs'
        if compte.necessite_ouvrage:
            return 'avec_ouvrage'
        return 'sans_ouvrage'

    if (entry.compte_code or '') in OUVRAGE_EXTRACTION_ACCOUNT_CODES:
        return 'avec_ouvrage'

    if '00PERS' in journal_code:
        return 'compte_tiers'

    return 'sans_ouvrage'


def _get_entry_compte_category_label(entry):
    category_key = _get_entry_compte_category_key(entry)
    return dict(ENTRY_COMPTE_CATEGORY_CHOICES).get(category_key, '')


def _extract_supplier_description_parts(description):
    description = (description or '').strip()
    if not description:
        return {
            'nif_ou_isi': '',
            'nom_fournisseur_brut': '',
            'libelle': '',
        }

    parts = [part.strip() for part in description.split('_')]
    nif_ou_isi = parts[0] if parts else ''
    nom_fournisseur = parts[1] if len(parts) > 1 else ''
    libelle = parts[2] if len(parts) > 2 else description

    if nif_ou_isi:
        upper_prefix = nif_ou_isi.upper()
        if not (upper_prefix.startswith('NIF') or upper_prefix.startswith('ISI')):
            nif_ou_isi = ''

    return {
        'nif_ou_isi': nif_ou_isi,
        'nom_fournisseur_brut': nom_fournisseur,
        'libelle': libelle,
    }


def _extract_employee_description_parts(description):
    description = (description or '').strip()
    if not description:
        return {
            'nom_employe_brut': '',
            'libelle': '',
        }

    parts = [part.strip() for part in description.split('_')]
    nom_employe = parts[1] if len(parts) > 1 else ''
    libelle = '_'.join(parts[2:]).strip() if len(parts) > 2 else description
    return {
        'nom_employe_brut': nom_employe,
        'libelle': libelle or description,
    }


def _match_fournisseur_from_name(raw_name, fournisseurs_index):
    normalized_name = _normalize_text(raw_name)
    if not normalized_name:
        return None

    fournisseur = fournisseurs_index.get(normalized_name)
    if fournisseur:
        return fournisseur

    for fournisseur_name, fournisseur_obj in fournisseurs_index.items():
        if normalized_name in fournisseur_name or fournisseur_name in normalized_name:
            return fournisseur_obj

    return None


def _build_fournisseurs_index():
    from apps.billing.models import Fournisseur

    fournisseurs = list(Fournisseur.objects.filter(actif=True).only(
        'id', 'nom_fournisseur', 'nif_ou_isi', 'numero_nif', 'idxls'
    ))
    return {
        _normalize_text(f.nom_fournisseur): f
        for f in fournisseurs
        if f.nom_fournisseur
    }


def _build_employes_index():
    from apps.employees.models import Employe

    employes = list(
        Employe.objects.filter(date_debauchage__isnull=True).only(
            'id', 'nom', 'prenom', 'surnom'
        )
    )
    index = {}
    for employe in employes:
        candidates = [
            employe.surnom or '',
            f"{employe.prenom or ''} {employe.nom or ''}".strip(),
            f"{employe.nom or ''} {employe.prenom or ''}".strip(),
            employe.nom or '',
        ]
        for candidate in candidates:
            normalized = _normalize_text(candidate)
            if normalized and normalized not in index:
                index[normalized] = employe
    return index


def _clean_extracted_libelle(libelle, values_to_remove=None):
    cleaned = (libelle or '').strip()
    for value in (values_to_remove or []):
        if not value:
            continue
        pattern = re.escape(str(value).strip())
        cleaned = re.sub(pattern, ' ', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'[_\-]{2,}', '_', cleaned)
    cleaned = re.sub(r'\s{2,}', ' ', cleaned)
    return cleaned.strip(' _-;,') or (libelle or '').strip()


def _match_employe_for_entry(entry, employes_index):
    candidates = [
        getattr(entry, 'detail', '') or '',
        getattr(entry, 'pers', '') or '',
    ]

    for candidate in candidates:
        employe = employes_index.get(_normalize_text(candidate))
        if employe:
            return employe

    description_normalized = _normalize_text(getattr(entry, 'description', '') or '')
    if not description_normalized:
        return None

    for key, employe in employes_index.items():
        if key and key in description_normalized:
            return employe

    return None


def _format_nombre_fr(valeur, decimales=2):
    """8.78 -> '8,78' ; 30.0 -> '30' ; 5350 -> '5 350' (espace insecable)."""
    texte = f"{float(valeur):,.{decimales}f}".replace(',', '\u202f')
    if '.' in texte:
        texte = texte.rstrip('0').rstrip('.')
    return texte.replace('.', ',')


def _extraire_infos_606(entry):
    """Quantite (litres), prix unitaire et vehicule d'une ecriture carburant 606xxx.

    Libelle type : NIF_STATION SHELL_Essence_L_5350_Ar x 8,78 pour moto 11492WWT
    (segment 5 = prix unitaire ; quantite apres « x » ; matricule dans le libelle ou le detail).
    """
    entry.extracted_quantite = ''
    entry.extracted_prix_unitaire = ''
    entry.extracted_vehicule = ''
    entry.extracted_vehicule_employe = ''
    if not (entry.compte_code or '').startswith('606'):
        return
    from .views_verification_fournisseurs import extraire_infos_carburant
    infos = extraire_infos_carburant(entry.description or '', entry.detail or '')
    if infos.get('quantite_litres'):
        entry.extracted_quantite = _format_nombre_fr(infos['quantite_litres'])
    parts = [p.strip() for p in (entry.description or '').split('_')]
    if len(parts) > 4:
        try:
            entry.extracted_prix_unitaire = _format_nombre_fr(float(parts[4].replace(' ', '').replace(',', '.')), 0)
        except ValueError:
            pass
    matricule = (infos.get('matricule_vehicule') or '').strip()
    # « Stock », « usage groupe »… ne sont pas des vehicules : un matricule contient au moins un chiffre
    if any(c.isdigit() for c in matricule):
        entry.extracted_vehicule = matricule
        if entry.date_m:
            from apps.inventory.models_vehicles import AffectationVehicule
            from .views_verification_fournisseurs import _normalize_matricule

            matricule_normalise = _normalize_matricule(matricule)
            affectations = AffectationVehicule.objects.filter(
                date_debut__lte=entry.date_m,
            ).filter(
                Q(date_fin__isnull=True) | Q(date_fin__gte=entry.date_m),
            ).select_related('employe', 'vehicule').order_by('-date_debut')
            for affectation in affectations:
                if _normalize_matricule(affectation.vehicule.immatriculation) == matricule_normalise:
                    employe = affectation.employe
                    entry.extracted_vehicule_employe = (
                        getattr(employe, 'surnom', '')
                        or getattr(employe, 'nom_complet', '')
                        or ' '.join(filter(None, [getattr(employe, 'prenom', ''), getattr(employe, 'nom', '')]))
                    )
                    break


def _populate_entry_extracted_fields(entry, fournisseurs_index=None):
    fournisseurs_index = fournisseurs_index or {}
    _extraire_infos_606(entry)
    entry.compte_categorie_key = _get_entry_compte_category_key(entry)
    entry.compte_categorie_label = _get_entry_compte_category_label(entry)
    entry.extracted_nif_ou_isi = ''
    entry.extracted_nom_fournisseur = ''
    entry.extracted_libelle = (entry.description or '').strip()
    # Description multiligne = souvent un résidu de copier-coller depuis Access
    entry.description_multiligne = '\n' in (entry.description or '').strip()
    entry.extracted_nom_ouvrage = ''
    entry.extracted_employe_surnom = ''

    if entry.compte_categorie_key == 'paiements_fournisseurs':
        supplier_parts = _extract_supplier_description_parts(entry.description)
        fournisseur = _match_fournisseur_from_name(
            supplier_parts['nom_fournisseur_brut'],
            fournisseurs_index
        )
        entry.extracted_nif_ou_isi = (
            supplier_parts['nif_ou_isi']
            or getattr(fournisseur, 'nif_ou_isi', '')
            or ''
        )
        entry.extracted_nom_fournisseur = (
            getattr(fournisseur, 'nom_fournisseur', '')
            or supplier_parts['nom_fournisseur_brut']
            or ''
        )
        entry.extracted_libelle = supplier_parts['libelle'] or entry.extracted_libelle
    elif entry.compte_categorie_key == 'avec_ouvrage':
        extraction = extraire_ouvrage_et_mois_generique(
            entry.description or '',
            entry.compte_code or ''
        )
        if isinstance(extraction, list):
            extraction = extraction[0] if extraction else {}
        ouvrage_obj = extraction.get('ouvrage_obj') if isinstance(extraction, dict) else None
        ouvrage_nom = ''
        if ouvrage_obj:
            ouvrage_nom = ouvrage_obj.nom_ouvrage
        elif isinstance(extraction, dict):
            ouvrage_nom = extraction.get('ouvrage_nom') or ''
        entry.extracted_nom_ouvrage = ouvrage_nom
        entry.extracted_libelle = _clean_extracted_libelle(
            entry.extracted_libelle,
            [entry.extracted_nom_ouvrage]
        )
    elif entry.compte_categorie_key == 'paiements_employes':
        employes_index = fournisseurs_index.get('__employes_index__', {})
        employee_parts = _extract_employee_description_parts(entry.description)
        employe = _match_employe_for_entry(entry, employes_index)
        entry.extracted_libelle = employee_parts['libelle'] or entry.extracted_libelle
        if employe:
            entry.extracted_employe_surnom = employe.surnom or ''
            entry.extracted_libelle = _clean_extracted_libelle(
                entry.extracted_libelle,
                [
                    employe.surnom,
                    f"{employe.prenom or ''} {employe.nom or ''}".strip(),
                    f"{employe.nom or ''} {employe.prenom or ''}".strip(),
                ]
            )

    return entry


def _build_entries_enrichment(page_obj):
    from .resolution_memoire import resolution_memoire

    fournisseurs_index = _build_fournisseurs_index()
    fournisseurs_index['__employes_index__'] = _build_employes_index()
    # Ouvrages et points d'eau sont résolus en mémoire : sans cela, chaque écriture
    # déclenche jusqu'à cinq requêtes (cf. apps/accounting/resolution_memoire.py).
    with resolution_memoire():
        for entry in page_obj:
            _populate_entry_extracted_fields(entry, fournisseurs_index)

    return page_obj


def _build_entries_autocomplete_values(entries, limit=500):
    from .resolution_memoire import resolution_memoire

    fournisseurs_index = _build_fournisseurs_index()
    fournisseurs_index['__employes_index__'] = _build_employes_index()
    sample_entries = list(entries[:limit])
    fournisseurs = {}
    ouvrages = {}
    employes = {}

    with resolution_memoire():
        for entry in sample_entries:
            _populate_entry_extracted_fields(entry, fournisseurs_index)
            if entry.extracted_nom_fournisseur:
                key = _normalize_text(entry.extracted_nom_fournisseur)
                if key and key not in fournisseurs:
                    fournisseurs[key] = entry.extracted_nom_fournisseur
            if entry.extracted_nom_ouvrage:
                key = _normalize_text(entry.extracted_nom_ouvrage)
                if key and key not in ouvrages:
                    ouvrages[key] = entry.extracted_nom_ouvrage
            if entry.extracted_employe_surnom:
                key = _normalize_text(entry.extracted_employe_surnom)
                if key and key not in employes:
                    employes[key] = entry.extracted_employe_surnom

    return {
        'fournisseur_autocomplete_values': sorted(fournisseurs.values(), key=str.lower),
        'ouvrage_autocomplete_values': sorted(ouvrages.values(), key=str.lower),
        'employe_surnom_autocomplete_values': sorted(employes.values(), key=str.lower),
    }


def _build_grand_livre_autocomplete_values():
    """Listes d'autocomplétion de l'arbre du grand livre, issues des référentiels.

    L'arbre ne charge aucune écriture : impossible d'enrichir un échantillon comme le
    fait ``_build_entries_autocomplete_values`` (plusieurs requêtes par écriture).
    """
    from apps.billing.models import Fournisseur
    from apps.employees.models import Employe
    from apps.organization.models import Ouvrage

    fournisseurs = (
        Fournisseur.objects.filter(actif=True)
        .exclude(Q(nom_fournisseur__isnull=True) | Q(nom_fournisseur=''))
        .values_list('nom_fournisseur', flat=True)
    )
    ouvrages = (
        Ouvrage.objects
        .exclude(Q(nom_ouvrage__isnull=True) | Q(nom_ouvrage=''))
        .values_list('nom_ouvrage', flat=True)
    )
    employes = (
        Employe.objects.filter(date_debauchage__isnull=True)
        .exclude(Q(surnom__isnull=True) | Q(surnom=''))
        .values_list('surnom', flat=True)
    )

    return {
        'fournisseur_autocomplete_values': sorted(set(fournisseurs), key=str.lower),
        'ouvrage_autocomplete_values': sorted(set(ouvrages), key=str.lower),
        'employe_surnom_autocomplete_values': sorted(set(employes), key=str.lower),
    }


def _grand_livre_label_expr(field_name, empty_label):
    """Libellé de regroupement : équivalent SQL de ``(entry.<field> or '<empty>').strip()``."""
    return Case(
        When(
            Q(**{f'{field_name}__isnull': True}) | Q(**{field_name: ''}),
            then=Value(empty_label),
        ),
        default=Trim(F(field_name)),
        output_field=CharField(),
    )


def _grand_livre_categorie_expr():
    """Équivalent SQL de ``_get_entry_compte_category_key()`` (clé de catégorie de compte)."""
    transfert_q = (
        Q(compte_code__icontains='00BOOK') | Q(journal_code__icontains='00BOOK') |
        Q(compte_code__icontains='00FND1') | Q(journal_code__icontains='00FND1') |
        Q(compte_code__icontains='00FND2') | Q(journal_code__icontains='00FND2') |
        Q(compte_code__icontains='00FND3') | Q(journal_code__icontains='00FND3')
    )
    return Case(
        When(transfert_q, then=Value('transfert')),
        When(compte_code__icontains='00PERS', then=Value('compte_tiers')),
        When(compte__employe_obligatoire=True, then=Value('paiements_employes')),
        When(compte__fournisseur_obligatoire=True, then=Value('paiements_fournisseurs')),
        When(compte__necessite_ouvrage=True, then=Value('avec_ouvrage')),
        When(compte__isnull=False, then=Value('sans_ouvrage')),
        When(compte_code__in=OUVRAGE_EXTRACTION_ACCOUNT_CODES, then=Value('avec_ouvrage')),
        When(journal_code__icontains='00PERS', then=Value('compte_tiers')),
        default=Value('sans_ouvrage'),
        output_field=CharField(),
    )


def _grand_livre_nouveau_groupe(key, label, child_key):
    return {
        'key': key,
        'label': label,
        child_key: [],
        'total_in': Decimal('0'),
        'total_out': Decimal('0'),
        'total_in_display': 0,
        'total_out_display': 0,
        'nb': 0,
    }


def _build_grand_livre_groups(entries, avec_comptes=True):
    """Arbre du grand livre agrégé en SQL.

    ``avec_comptes=True`` regroupe par activ > financement > catégorie > compte (niveau
    « comptes d'une catégorie »). ``avec_comptes=False`` s'arrête à la catégorie : c'est
    le niveau affiché par défaut, bien plus léger quand le journal contient des dizaines
    de milliers d'écritures.

    Les écritures ne sont ni chargées ni enrichies : une seule requête ``GROUP BY``
    ramène les totaux et le nombre d'écritures. C'est ce qui rend la vue grand livre
    utilisable à grand volume (l'ancienne version chargeait tout le journal,
    l'enrichissait écriture par écriture puis le rendait — d'où le 504).
    """
    colonnes = ['gl_activ', 'gl_fin', 'gl_cat']
    if avec_comptes:
        colonnes += ['compte_code', 'compte__nom_compte']

    rows = (
        entries.order_by()
        .annotate(
            gl_activ=_grand_livre_label_expr('activ', 'Sans activ'),
            gl_fin=_grand_livre_label_expr('fin', 'Sans financement'),
            gl_cat=_grand_livre_categorie_expr(),
        )
        .values(*colonnes)
        .annotate(
            total_in=Sum('montant_in'),
            total_out=Sum('montant_out'),
            nb=Count('id'),
            derniere=Max('date_m'),
        )
        # L'écriture la plus récente donne son libellé au groupe : les variantes de
        # casse/espaces d'un même activ (ou financement) sont ainsi regroupées sous
        # l'orthographe affichée par l'ancienne vue, de façon déterministe.
        .order_by('-derniere')
    )

    categories_libelles = dict(ENTRY_COMPTE_CATEGORY_CHOICES)
    activ_map = {}

    for row in rows:
        activ_label = (row['gl_activ'] or 'Sans activ').strip()
        fin_label = (row['gl_fin'] or 'Sans financement').strip()
        categorie_label = (
            categories_libelles.get(row['gl_cat'], '') or 'Sans catégorie compte'
        ).strip()

        total_in = Decimal(str(row['total_in'] or 0))
        total_out = Decimal(str(row['total_out'] or 0))
        nb = row['nb'] or 0

        activ_item = activ_map.get(_normalize_text(activ_label))
        if activ_item is None:
            activ_item = _grand_livre_nouveau_groupe(
                _normalize_text(activ_label), activ_label, 'financements')
            activ_item['_fins'] = {}
            activ_map[_normalize_text(activ_label)] = activ_item

        fin_key = _normalize_text(fin_label)
        fin_item = activ_item['_fins'].get(fin_key)
        if fin_item is None:
            fin_item = _grand_livre_nouveau_groupe(fin_key, fin_label, 'categories')
            fin_item['_cats'] = {}
            activ_item['_fins'][fin_key] = fin_item

        categorie_key = _normalize_text(categorie_label)
        categorie_item = fin_item['_cats'].get(categorie_key)
        if categorie_item is None:
            categorie_item = _grand_livre_nouveau_groupe(
                categorie_key, categorie_label, 'comptes')
            categorie_item['cat_key'] = row['gl_cat']
            categorie_item['_comptes'] = {}
            fin_item['_cats'][categorie_key] = categorie_item

        if avec_comptes:
            compte_code = (row['compte_code'] or '').strip() or 'Sans compte'
            compte_nom = (row['compte__nom_compte'] or '').strip()
            compte_label = f'{compte_code} - {compte_nom}' if compte_nom else compte_code
            compte_key = (compte_code, compte_nom)
            compte_item = categorie_item['_comptes'].get(compte_key)
            if compte_item is None:
                compte_item = _grand_livre_nouveau_groupe(compte_key, compte_label, 'entrees')
                compte_item['compte_code'] = compte_code
                compte_item['compte_nom'] = compte_nom
                categorie_item['_comptes'][compte_key] = compte_item
                categorie_item['comptes'].append(compte_item)
            compte_item['total_in'] += total_in
            compte_item['total_out'] += total_out
            compte_item['nb'] += nb
            categorie_item['nb_comptes'] = len(categorie_item['comptes'])

        # Les totaux agrégés par les colonnes du GROUP BY alimentent chaque niveau.
        for item in (activ_item, fin_item, categorie_item):
            item['total_in'] += total_in
            item['total_out'] += total_out
            item['nb'] += nb

    grouped = []
    for activ_item in activ_map.values():
        activ_item['financements'] = sorted(
            activ_item['_fins'].values(), key=lambda item: _normalize_text(item['label']))
        for fin_item in activ_item['financements']:
            fin_item['categories'] = sorted(
                fin_item['_cats'].values(), key=lambda item: _normalize_text(item['label']))
            for categorie_item in fin_item['categories']:
                categorie_item.pop('_comptes', None)
            fin_item.pop('_cats', None)
        activ_item.pop('_fins', None)
        grouped.append(activ_item)

    return sorted(grouped, key=lambda item: _normalize_text(item['label']))


def _grand_livre_entrees_count(groups):
    """Nombre d'écritures du périmètre, sans requête supplémentaire."""
    return sum(activ['nb'] for activ in groups)


def _grand_livre_attach_urls(request, groups, avec_comptes=True):
    """Ajoute les liens de navigation du grand livre à chaque groupe.

    * ``categorie['url']`` : liste des comptes de la catégorie (niveau suivant) ;
    * ``compte['url']``    : écritures du compte, table paginée habituelle.
    """
    from urllib.parse import urlencode

    view_mode = request.GET.get('view_mode') or 'grand_livre'
    a_retirer = {'page', 'view_mode', 'gl_detail', 'gl_activ', 'gl_fin', 'gl_cat',
                 'gl_compte', 'gl_compte_nom'}
    base = [(cle, valeur) for cle, valeur in request.GET.items() if cle not in a_retirer]
    base.append(('view_mode', view_mode))
    base_query = urlencode(base)

    def build_url(**extra):
        return '?' + base_query + '&' + urlencode(extra)

    for activ_group in groups:
        for fin_group in activ_group['financements']:
            for categorie_group in fin_group['categories']:
                cat_key = categorie_group.get('cat_key') or categorie_group['key']
                categorie_group['url'] = build_url(
                    gl_activ=activ_group['label'],
                    gl_fin=fin_group['label'],
                    gl_cat=cat_key,
                )
                if not avec_comptes:
                    continue
                for compte_group in categorie_group['comptes']:
                    compte_group['url'] = build_url(
                        gl_activ=activ_group['label'],
                        gl_fin=fin_group['label'],
                        gl_cat=cat_key,
                        gl_detail='1',
                        gl_compte=compte_group['compte_code'],
                        gl_compte_nom=compte_group['compte_nom'],
                    )
    return groups


def _grand_livre_stats(entries, derniere_verif, scans_valides_ids, liens_morts_ids):
    """Statistiques de l'en-tête du grand livre en une requête agrégée.

    Reprend exactement les définitions de ``entries_list`` (recettes/dépenses sans
    00BOOK/00PERS, transferts 00BOOK + 00FND1 sans EDF, avances 00PERS, pièces
    justificatives) mais les calcule d'un coup au lieu d'une quinzaine de requêtes
    qui rescannaient tout le périmètre.
    """
    montants = Q(montant_in__gt=0) | Q(montant_out__gt=0)
    book = Q(compte_code__startswith='00BOOK')
    fnd1 = Q(compte_code__startswith='00FND1')
    edf = Q(description__icontains='EDF') | Q(info__icontains='EDF')
    pers = Q(compte_code__startswith='00PERS')
    transferts_q = book | (fnd1 & ~edf)
    recettes_q = ~(book | pers) & ~(fnd1 & ~edf)
    sans_scan = Q(scan__isnull=True) | Q(scan='')
    avec_scan = ~sans_scan
    scan_importe = ~(Q(scan_importe__isnull=True) | Q(scan_importe=''))
    necessite_scan = ~(Q(compte_code__icontains='00BOOK') | Q(compte_code__icontains='00PERS'))

    agregat = entries.aggregate(
        recettes_in=Sum('montant_in', filter=recettes_q),
        recettes_out=Sum('montant_out', filter=recettes_q),
        transferts_in=Sum('montant_in', filter=transferts_q),
        transferts_out=Sum('montant_out', filter=transferts_q),
        transferts_nb=Count('id', filter=transferts_q),
        pers_in=Sum('montant_in', filter=pers),
        pers_out=Sum('montant_out', filter=pers),
        pers_nb=Count('id', filter=pers),
        recettes_total=Count('id', filter=recettes_q & Q(montant_in__gt=0)),
        recettes_scan=Count('id', filter=recettes_q & Q(montant_in__gt=0) & avec_scan),
        depenses_total=Count('id', filter=recettes_q & Q(montant_out__gt=0)),
        depenses_scan=Count('id', filter=recettes_q & Q(montant_out__gt=0) & avec_scan),
        operations_total=Count('id', filter=necessite_scan & montants),
        operations_sans_scan=Count('id', filter=necessite_scan & montants & sans_scan),
        scan_importe_nb=Count('id', filter=necessite_scan & montants & scan_importe),
        recettes_sans_scan=Count('id', filter=recettes_q & montants & sans_scan),
    )

    recettes = agregat['recettes_in'] or 0
    depenses = agregat['recettes_out'] or 0
    operations_total = agregat['operations_total'] or 0
    operations_sans_scan = agregat['operations_sans_scan'] or 0

    # Scans valides = copies serveur (scan_importe) + scans validés par le cache de
    # vérification ; liens morts = cache des liens morts, hors copies serveur.
    base_scan = entries.filter(necessite_scan).filter(montants)
    scans_valides_count = agregat['scan_importe_nb'] or 0
    if scans_valides_ids:
        scans_valides_count += _count_entries_with_ids(base_scan, scans_valides_ids)
        scans_valides_count -= _count_entries_with_ids(
            base_scan.filter(scan_importe), scans_valides_ids)
    liens_morts_count = (
        _count_entries_with_ids(base_scan.filter(sans_scan), liens_morts_ids)
        if liens_morts_ids else 0
    )
    recettes_total = agregat['recettes_total'] or 0
    depenses_total = agregat['depenses_total'] or 0

    return {
        'recettes': recettes,
        'depenses': depenses,
        'solde': recettes - depenses,
        'transferts_solde': (agregat['transferts_in'] or 0) - (agregat['transferts_out'] or 0),
        'transferts_count': agregat['transferts_nb'] or 0,
        'pers_solde': float((agregat['pers_out'] or 0) - (agregat['pers_in'] or 0)),
        'pers_count': agregat['pers_nb'] or 0,
        'recettes_sans_scan_count': agregat['recettes_sans_scan'] or 0,
        'recettes_avec_scan': agregat['recettes_scan'] or 0,
        'recettes_total': recettes_total,
        'recettes_couverture': round(
            (agregat['recettes_scan'] or 0) / recettes_total * 100, 1) if recettes_total else 0,
        'depenses_avec_scan': agregat['depenses_scan'] or 0,
        'depenses_total': depenses_total,
        'depenses_couverture': round(
            (agregat['depenses_scan'] or 0) / depenses_total * 100, 1) if depenses_total else 0,
        'operations_total': operations_total,
        'operations_sans_scan': operations_sans_scan,
        'scans_valides_count': scans_valides_count,
        'liens_morts_count': liens_morts_count,
        'taux_sans_scan': int(operations_sans_scan / operations_total * 100) if operations_total else 0,
        'taux_liens_morts': int(liens_morts_count / operations_total * 100) if operations_total else 0,
        'taux_scans_valides': int(scans_valides_count / operations_total * 100) if operations_total else 0,
        'date_derniere_verif': derniere_verif.date_verification if derniere_verif else None,
    }


def _grand_livre_filter_values(entries, user):
    """Listes des filtres (fichiers, journaux, comptes, pers, detail, fin, activ).

    Une seule requête agrégée au lieu de sept ``SELECT DISTINCT`` qui reparcouraient
    tout le périmètre.
    """
    from django.contrib.postgres.aggregates import ArrayAgg
    from django.db.models.functions import Coalesce, Concat

    separateur = '\x1f'
    agregats = entries.aggregate(
        fichiers=ArrayAgg('fichier_source', distinct=True),
        journaux=ArrayAgg('journal_code', distinct=True),
        comptes=ArrayAgg(
            Concat(
                Coalesce('compte_code', Value('')),
                Value(separateur),
                Coalesce('compte__nom_compte', Value('')),
                output_field=CharField(),
            ),
            distinct=True,
        ),
        pers=ArrayAgg('pers', distinct=True),
        details=ArrayAgg('detail', distinct=True),
        fins=ArrayAgg('fin', distinct=True),
        activs=ArrayAgg('activ', distinct=True),
    )

    fichiers_sources = sorted(set(f for f in (agregats['fichiers'] or []) if f))
    journaux_codes = sorted(set(j for j in (agregats['journaux'] or []) if j))

    comptes_noms_par_code = {}
    for paire in agregats['comptes'] or []:
        code, _, nom_compte = paire.partition(separateur)
        code = (code or '').strip()
        nom_compte = (nom_compte or '').strip()
        if not code:
            continue
        comptes_noms_par_code.setdefault(code, set())
        if nom_compte:
            comptes_noms_par_code[code].add(nom_compte)

    codes_sans_nom = [code for code, noms in comptes_noms_par_code.items() if not noms]
    if codes_sans_nom:
        comptes_reference = Compte.objects.filter(compte__in=codes_sans_nom)
        organisation_id = _get_user_organisation_id(user)
        if organisation_id:
            comptes_reference = comptes_reference.filter(organisation_id=organisation_id)
        elif not getattr(user, 'is_superuser', False):
            comptes_reference = comptes_reference.none()
        for code, nom_compte in comptes_reference.values_list('compte', 'nom_compte'):
            code = (code or '').strip()
            nom_compte = (nom_compte or '').strip()
            if code in comptes_noms_par_code and nom_compte:
                comptes_noms_par_code[code].add(nom_compte)

    pers_dict = {}
    for valeur in agregats['pers'] or []:
        if valeur and valeur.lower() not in pers_dict:
            pers_dict[valeur.lower()] = valeur
    detail_dict = {}
    for valeur in agregats['details'] or []:
        if valeur and valeur.lower() not in detail_dict:
            detail_dict[valeur.lower()] = valeur

    return {
        'fichiers_sources': fichiers_sources,
        'journaux_codes': journaux_codes,
        'comptes_options': [
            {
                'code': code,
                'nom': ' / '.join(sorted(comptes_noms_par_code[code], key=str.casefold)),
            }
            for code in sorted(comptes_noms_par_code, key=str.casefold)
        ],
        'pers_values': sorted(pers_dict.values(), key=str.lower),
        'detail_values': sorted(detail_dict.values(), key=str.lower),
        'fin_values': sorted(set(f for f in (agregats['fins'] or []) if f)),
        'activ_values': sorted(set(a for a in (agregats['activs'] or []) if a)),
    }


def _render_grand_livre_agrege(request, entries, *, view_mode, gl_comptes_mode,
                               derniere_verif, scans_valides_ids, liens_morts_ids):
    """Rend l'arbre du grand livre (activ > financement > catégorie) ou les comptes
    d'une catégorie, sans jamais charger les écritures du journal.

    C'est le chemin rapide de la vue grand livre : une requête pour l'arbre, une pour
    les statistiques de l'en-tête, une pour les listes de filtres, plus deux comptages
    de scans. L'ancien chemin chargeait toutes les écritures, les enrichissait une par
    une (plusieurs requêtes par ligne) puis les rendait — d'où le 504.
    """
    import logging

    started = time.perf_counter()

    groups = _build_grand_livre_groups(entries, avec_comptes=gl_comptes_mode)
    _grand_livre_attach_urls(request, groups, avec_comptes=gl_comptes_mode)
    total_count = _grand_livre_entrees_count(groups)
    comptes = _grand_livre_comptes_list(groups) if gl_comptes_mode else []
    back_url = _grand_livre_back_url(request, 'arbre' if gl_comptes_mode else 'comptes')

    stats = _grand_livre_stats(entries, derniere_verif, scans_valides_ids, liens_morts_ids)
    valeurs_filtres = _grand_livre_filter_values(entries, request.user)

    context = {
        'page_obj': [],
        'entries': [],
        'total_count': total_count,
        'grand_livre_groups': groups,
        'grand_livre_comptes': comptes,
        'gl_detail': False,
        'gl_comptes_mode': gl_comptes_mode,
        'gl_back_url': back_url,
        'gl_narrow_label': _grand_livre_narrow_label(request, avec_compte=False),
        'view_mode': view_mode,
        'mouvement_filter': request.GET.get('mouvement', '').strip(),
        'sort_amount': request.GET.get('sort_amount', '').strip(),
        'compte_category_choices': ENTRY_COMPTE_CATEGORY_CHOICES,
        'categories_parentes': [
            'Transferts 00BOOK', 'Transferts 00FND1', 'EDF', 'Compte de tiers', 'Acquisition', 'Matériaux',
            'Fournitures', 'équipement', 'Carburant', 'Fonctionnement',
            'Entretien véhicules', "Main d'Å“uvre", 'Paiements employés', 'Impots',
            'Autres recettes', 'Vente eau au volume', 'Paiement extension', 'Vente eau au forfait',
            'Vente carte sociale', 'Autres'
        ],
        # Panneau « indemnités RBF » et pièces justificatives : propres à la vue liste.
        'rbf_points': [],
        'rbf_points_summary': None,
        'rbf_hidden_count': 0,
        'rbf_show_all': False,
        'rbf_toggle_url': '',
        'rbf_reset_url': '',
        'rbf_selected': None,
        'rbf_plafond': None,
        'recettes_sans_scan': [],
        'recettes_sans_scan_count': stats['recettes_sans_scan_count'],
        **stats,
        **valeurs_filtres,
        **_build_grand_livre_autocomplete_values(),
    }

    response = render(request, 'accounting/entries_list.html', context)
    duree = time.perf_counter() - started
    logger = logging.getLogger(__name__)
    message = (
        "[grand-livre] %s ecritures, %s groupes, %s rendu %s Ko, duree %.2fs"
        % (total_count, len(groups), 'comptes' if gl_comptes_mode else 'arbre',
           len(response.content) // 1024, duree)
    )
    if duree > 5:
        logger.warning(message)
    else:
        logger.info(message)
    return response


def _grand_livre_comptes_list(groups):
    """Liste à plat des comptes d'un arbre (niveau « comptes d'une catégorie »)."""
    comptes = [
        compte_group
        for activ_group in groups
        for fin_group in activ_group['financements']
        for categorie_group in fin_group['categories']
        for compte_group in categorie_group['comptes']
    ]
    return sorted(comptes, key=lambda item: _normalize_text(item['label']))


def _count_entries_with_ids(queryset, ids):
    """COUNT des écritures dont l'id est dans ``ids``.

    Le cache de vérification des scans peut contenir des dizaines de milliers d'ids :
    un ``IN (…)`` géant coûte cher à construire et à analyser côté PostgreSQL. Au-delà
    d'un seuil, la liste part donc en paramètre tableau (``= ANY(%s)``).
    """
    ids = list(ids)
    if not ids:
        return 0
    if len(ids) <= 2000:
        return queryset.filter(id__in=ids).count()
    table = BaseDiameX._meta.db_table
    return queryset.extra(where=[f'"{table}"."id" = ANY(%s)'], params=[ids]).count()


def _grand_livre_back_url(request, niveau='arbre'):
    """Lien de retour au niveau supérieur du grand livre.

    ``arbre``   : retour à l'arbre (activ > financement > catégorie) ;
    ``comptes`` : retour aux comptes de la catégorie (depuis les écritures d'un compte).
    """
    params = request.GET.copy()
    a_retirer = ['page', 'gl_detail', 'gl_compte', 'gl_compte_nom']
    if niveau == 'arbre':
        a_retirer += ['gl_activ', 'gl_fin', 'gl_cat']
    else:
        a_retirer += ['gl_detail']
    for name in a_retirer:
        params.pop(name, None)
    if not params.get('view_mode'):
        params['view_mode'] = 'grand_livre'
    return '?' + params.urlencode()


def _grand_livre_narrow_label(request, avec_compte=True):
    """Libellé lisible du groupe de grand livre ouvert (fil d'Ariane)."""
    cat_key = request.GET.get('gl_cat', '').strip()
    parties = [
        request.GET.get('gl_activ', '').strip() or 'Sans activ',
        request.GET.get('gl_fin', '').strip() or 'Sans financement',
        dict(ENTRY_COMPTE_CATEGORY_CHOICES).get(cat_key) or 'Sans catégorie compte',
    ]
    if avec_compte:
        compte_code = request.GET.get('gl_compte', '').strip() or 'Sans compte'
        compte_nom = request.GET.get('gl_compte_nom', '').strip()
        parties.append(f'{compte_code} - {compte_nom}' if compte_nom else compte_code)
    return ' › '.join(parties)


def _apply_grand_livre_narrow_filter(entries, request, avec_compte=True):
    """Restreint les écritures au groupe de grand livre demandé.

    ``avec_compte=False`` : on s'arrête au niveau catégorie (liste des comptes).
    """
    activ_label = request.GET.get('gl_activ', '').strip()
    fin_label = request.GET.get('gl_fin', '').strip()
    cat_key = request.GET.get('gl_cat', '').strip()
    compte_code = request.GET.get('gl_compte', '').strip()
    compte_nom = request.GET.get('gl_compte_nom', '').strip()

    if activ_label:
        entries = entries.annotate(
            _gl_activ=_grand_livre_label_expr('activ', 'Sans activ')
        ).filter(_gl_activ=activ_label)
    if fin_label:
        entries = entries.annotate(
            _gl_fin=_grand_livre_label_expr('fin', 'Sans financement')
        ).filter(_gl_fin=fin_label)
    if cat_key:
        entries = entries.annotate(_gl_cat=_grand_livre_categorie_expr()).filter(_gl_cat=cat_key)

    if avec_compte and compte_code:
        if compte_code == 'Sans compte':
            entries = entries.filter(Q(compte_code__isnull=True) | Q(compte_code=''))
        else:
            entries = entries.filter(compte_code=compte_code)
        if compte_nom:
            entries = entries.filter(compte__nom_compte=compte_nom)
        else:
            entries = entries.filter(
                Q(compte__nom_compte__isnull=True) | Q(compte__nom_compte=''))

    return entries


def _normalize_scan_value(scan_value):
    scan_clean = (scan_value or '').strip().strip('#')
    if not scan_clean:
        return ''
    if scan_clean.startswith('./') or scan_clean.startswith('.\\'):
        return scan_clean[2:]
    return scan_clean.lstrip('.')


def _clear_imported_scan(entry):
    if entry and getattr(entry, 'scan_importe', None):
        entry.scan_importe.delete(save=False)
        entry.scan_importe = None


def _build_imported_scan_storage_name(fichier_source, id_access, uploaded_name):
    fichier_slug = slugify(os.path.splitext(fichier_source or 'diamex')[0]) or 'diamex'
    extension = os.path.splitext(uploaded_name or '')[1].lower()[:16]
    if not extension:
        extension = '.bin'
    return f"diamex_scans/{fichier_slug}/{id_access}{extension}"


def _is_tiff_file(path):
    return (path or '').lower().endswith(('.tif', '.tiff'))


def _build_tiff_viewer_html(entry_id, filename, page_count):
    return None


def _serve_tiff_page(scan_path, page_number):
    from django.http import Http404, HttpResponse

    if Image is None:
        raise Http404("Pillow est requis pour afficher les TIFF multipages")

    with Image.open(scan_path) as img:
        total_pages = getattr(img, 'n_frames', 1) or 1
        if page_number < 1 or page_number > total_pages:
            raise Http404("Page TIFF introuvable")
        img.seek(page_number - 1)
        frame = img.copy()
        if frame.mode not in ('RGB', 'L'):
            frame = frame.convert('RGB')
        img_io = BytesIO()
        frame.save(img_io, format='PNG')
        img_io.seek(0)
        return HttpResponse(img_io.read(), content_type='image/png')


def _resolve_entry_scan_candidates(entry):
    from apps.employees.models import EmployeBaseDiameX

    scan_value = (entry.scan or '').strip().strip('#')
    if not scan_value:
        return []

    is_absolute = (
        (len(scan_value) > 2 and scan_value[1] == ':' and scan_value[2] in ('\\', '/')) or
        scan_value.startswith('\\\\') or
        scan_value.startswith('/')
    )

    candidates = []
    if is_absolute:
        candidates.append(os.path.normpath(scan_value))

    scan_rel = scan_value[2:] if scan_value.startswith('./') or scan_value.startswith('.\\') else scan_value.lstrip('.')
    prog_value = (entry.prog or '').strip()
    employe = entry.imported_by
    bases_qs = EmployeBaseDiameX.objects.none()

    if employe and entry.fichier_source:
        bases_qs = EmployeBaseDiameX.objects.filter(employe=employe, base_diamex=entry.fichier_source)

    if not bases_qs.exists() and employe and prog_value:
        bases_qs = EmployeBaseDiameX.objects.filter(employe=employe, base_diamex__icontains=prog_value)

    if not bases_qs.exists() and prog_value:
        bases_qs = EmployeBaseDiameX.objects.filter(base_diamex__icontains=prog_value)

    seen_paths = set(candidates)
    for base in bases_qs:
        chemin_base = (base.chemin_base_diamex or '').strip()
        if not chemin_base:
            continue
        full_path = os.path.normpath(os.path.join(chemin_base, scan_rel.lstrip('\\/')))
        if full_path not in seen_paths:
            candidates.append(full_path)
            seen_paths.add(full_path)

    return candidates


def _resolve_entry_scan_path(entry):
    candidates = _resolve_entry_scan_candidates(entry)
    full_scan_path = next((p for p in candidates if os.path.exists(p)), None)
    return full_scan_path, candidates


def _convert_tiff_bytes_to_pdf_content(content, original_name):
    if Image is None:
        return ContentFile(content, name=original_name)

    with Image.open(BytesIO(content)) as img:
        frames = []
        total_pages = getattr(img, 'n_frames', 1) or 1
        for page_index in range(total_pages):
            img.seek(page_index)
            frame = img.copy()
            if frame.mode not in ('RGB', 'L'):
                frame = frame.convert('RGB')
            frames.append(frame)

    pdf_buffer = BytesIO()
    first_frame, *other_frames = frames
    first_frame.save(pdf_buffer, format='PDF', save_all=True, append_images=other_frames)
    pdf_buffer.seek(0)
    pdf_name = f"{os.path.splitext(original_name or 'scan')[0]}.pdf"
    return ContentFile(pdf_buffer.read(), name=pdf_name)


def _save_imported_scan_file(entry, uploaded_file):
    original_name = getattr(uploaded_file, 'name', '') or f'{entry.id_access}.bin'
    prepared_file = uploaded_file

    if _is_tiff_file(original_name):
        uploaded_file.seek(0)
        prepared_file = _convert_tiff_bytes_to_pdf_content(uploaded_file.read(), original_name)

    storage_name = _build_imported_scan_storage_name(
        entry.fichier_source,
        entry.id_access,
        getattr(prepared_file, 'name', ''),
    )
    old_name = (getattr(entry.scan_importe, 'name', '') or '').strip()

    # Remplacement sûr : l'ancien scan n'est jamais touché tant que le nouveau n'est pas
    # écrit ET vérifié sur le disque. Toute erreur lève une exception, l'ancien reste en place.
    prepared_file.seek(0)
    data = prepared_file.read()
    if not data:
        raise ValueError('contenu du scan vide')
    if storage_name.lower().endswith('.pdf') and not data.lstrip()[:5] == b'%PDF-':
        raise ValueError('le fichier reçu n\'est pas un PDF valide')

    base, ext = os.path.splitext(storage_name)
    temp_name = default_storage.save(f"{base}.new-{uuid.uuid4().hex[:8]}{ext}", ContentFile(data))
    try:
        if default_storage.size(temp_name) != len(data):
            raise IOError('écriture du scan incomplète')
    except Exception:
        default_storage.delete(temp_name)
        raise

    # Le nouveau scan est en sécurité : on peut le placer sous son nom définitif.
    try:
        if default_storage.exists(storage_name):
            default_storage.delete(storage_name)
        final_name = default_storage.save(storage_name, ContentFile(data))
        default_storage.delete(temp_name)
    except Exception:
        final_name = temp_name  # la copie vérifiée devient le scan de l'écriture

    entry.scan_importe.name = final_name
    # Ancien fichier (nom différent) à supprimer par l'appelant, une fois la base mise à jour.
    return old_name if old_name and old_name != final_name else None


def _is_pdf_name(file_name):
    return (file_name or '').lower().endswith('.pdf')


def _is_jpg_name(file_name):
    return (file_name or '').lower().endswith(('.jpg', '.jpeg'))


def _can_view_sensitive_diamex_lines(user):
    """
    Autorise les lignes sensibles DiameX (salaires/CNAPS/IRSA/FMFP)
    uniquement pour les postes Directeur et RAF.
    """
    employe = getattr(user, 'employe', None) if hasattr(user, 'employe') else None
    poste_nom = getattr(getattr(employe, 'poste', None), 'nom_poste', '')
    poste_normalized = _normalize_text(poste_nom)

    return (
        'directeur' in poste_normalized or
        poste_normalized in {
            'raf',
            'responsable administratif et financier',
            'responsable administrative et financier',
        }
    )


def _get_diamex_entries_scope_queryset(request):
    """
    Scope de visibilité DiameX:
    - superuser: toutes les lignes
    - utilisateur avec employé/base/organisation: lignes de son organisation
    - fallback: comportement historique (lignes importées par lui, sinon toutes)
    """
    base_qs = BaseDiameX.objects.select_related('journal', 'compte')

    if getattr(request.user, 'is_superuser', False):
        return base_qs.all()

    employe = getattr(request.user, 'employe', None) if hasattr(request.user, 'employe') else None
    organisation = getattr(getattr(employe, 'base', None), 'organisation', None)

    if organisation:
        return base_qs.filter(imported_by__base__organisation=organisation)

    if employe:
        return base_qs.filter(imported_by=employe)

    return base_qs.all()


def _get_user_organisation_id(user):
    if getattr(user, 'is_superuser', False):
        return None
    organisation = get_user_organisation(user)
    return getattr(organisation, 'id', None)


def _get_user_gestionnaire_ids(user):
    return get_user_accessible_gestionnaire_ids(user)


def _get_user_scope_organisation_ids(user):
    """
    Retourne les organisations "gestionnaires" visibles pour l'utilisateur.
    - superuser: None (pas de restriction)
    - autre: liste d'IDs (peut être vide)
    """
    gestionnaire_ids = _get_user_gestionnaire_ids(user)
    if gestionnaire_ids is None:
        return None
    return [str(_id) for _id in gestionnaire_ids]


def _scope_queryset_by_gestionnaire_ids(queryset, user, modalite_prefix):
    """
    Applique le scope gestionnaire sur une relation vers ModaliteGestion.

    Exemple de prefix:
    - 'ouvrage__modalites_gestion__'
    - 'point_eau__ouvrage__modalites_gestion__'
    - 'modalites_gestion__'
    """
    gestionnaire_ids = _get_user_gestionnaire_ids(user)
    if gestionnaire_ids is None:
        return queryset
    if not gestionnaire_ids:
        return queryset.none()
    prefix = modalite_prefix[:-2] if modalite_prefix.endswith('__') else modalite_prefix
    return queryset.filter(
        current_modalite_q(prefix),
        **{f'{modalite_prefix}gestionnaire_id__in': gestionnaire_ids},
    ).distinct()


def _get_ouvrages_ids_by_gestionnaire_scope(user, modalites=None):
    """
    Retourne les IDs d'ouvrages visibles selon le scope gestionnaire.

    - superuser: pas de restriction
    - gestionnaire: ses ouvrages
    - partenaire: ouvrages des gestionnaires affectés
    """
    from apps.billing.models import ModaliteGestion

    gestionnaire_ids = _get_user_gestionnaire_ids(user)
    qs = filter_current_modalites(ModaliteGestion.objects.all())
    if modalites:
        qs = qs.filter(modalitepaiement__in=modalites)

    if gestionnaire_ids is None:
        return set(qs.values_list('ouvrage_id', flat=True).distinct())
    if not gestionnaire_ids:
        return set()
    return set(
        qs.filter(gestionnaire_id__in=gestionnaire_ids).values_list('ouvrage_id', flat=True).distinct()
    )


def _normalize_filter_value(value):
    normalized = str(value or '').strip()
    if normalized.lower() in {'', 'all', 'none', 'null'}:
        return ''
    return normalized


def _resolve_effective_gestionnaire_scope(user, filter_organisation=''):
    """
    Calcule le scope gestionnaire effectif selon le filtre organisation demandé.

    Retour:
    - organisation_user: organisation de l'utilisateur
    - accessible_gestionnaire_ids: None (superuser) ou liste des IDs accessibles
    - selected_organisation_id: ID organisation retenu ('' si aucun)
    - effective_gestionnaire_ids: None (pas de restriction) ou liste d'IDs
    """
    organisation_user = get_user_organisation(user)
    gestionnaire_ids = _get_user_gestionnaire_ids(user)
    accessible_ids = None if gestionnaire_ids is None else [str(_id) for _id in gestionnaire_ids]

    selected_organisation_id = _normalize_filter_value(filter_organisation)
    effective_gestionnaire_ids = accessible_ids

    if selected_organisation_id:
        if accessible_ids is None:
            effective_gestionnaire_ids = [selected_organisation_id]
        elif selected_organisation_id in set(accessible_ids):
            effective_gestionnaire_ids = [selected_organisation_id]
        else:
            # Filtre non autorisé pour cet utilisateur -> aucun accès.
            effective_gestionnaire_ids = []

    return {
        'organisation_user': organisation_user,
        'accessible_gestionnaire_ids': accessible_ids,
        'selected_organisation_id': selected_organisation_id,
        'effective_gestionnaire_ids': effective_gestionnaire_ids,
    }


def _get_gestionnaire_organisations_for_filter(accessible_gestionnaire_ids):
    organisations_qs = Organisation.objects.filter(
        type_organisation=Organisation.TYPE_GESTIONNAIRE
    )
    if accessible_gestionnaire_ids is None:
        return organisations_qs.order_by('nom_organisation')
    if not accessible_gestionnaire_ids:
        return organisations_qs.none()
    return organisations_qs.filter(id__in=accessible_gestionnaire_ids).order_by('nom_organisation')


def _get_ouvrages_ids_by_effective_gestionnaire_ids(effective_gestionnaire_ids, modalites=None):
    from apps.billing.models import ModaliteGestion

    ouvrages_qs = filter_current_modalites(ModaliteGestion.objects.all())
    if modalites:
        ouvrages_qs = ouvrages_qs.filter(modalitepaiement__in=modalites)

    if effective_gestionnaire_ids is None:
        return set(ouvrages_qs.values_list('ouvrage_id', flat=True).distinct())
    if not effective_gestionnaire_ids:
        return set()

    return set(
        ouvrages_qs.filter(
            gestionnaire_id__in=effective_gestionnaire_ids
        ).values_list('ouvrage_id', flat=True).distinct()
    )


def _get_responsable_scoped_ouvrage_ids(user, effective_gestionnaire_ids=None, modalites=None):
    ouvrage_ids = _get_ouvrages_ids_by_effective_gestionnaire_ids(
        effective_gestionnaire_ids,
        modalites=modalites,
    )
    return apply_user_responsable_ouvrage_scope(
        ouvrage_ids,
        user,
        allow_same_base_support_roles=True,
    )


def _normalize_id_set(values):
    return {str(value) for value in (values or []) if value}


def _get_allowed_diamex_progs(user):
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


def _get_diamex_scope_by_prog(user):
    qs = BaseDiameX.objects.all()
    if getattr(user, 'is_superuser', False):
        return qs
    allowed_progs = _get_allowed_diamex_progs(user)
    if not allowed_progs:
        return qs.none()
    return qs.filter(prog__in=allowed_progs)


def _exclude_sensitive_diamex_lines_for_non_privileged(entries_qs, user):
    """
    Cache les lignes salaires/CNAPS/IRSA/FMFP pour les postes non autorisés.
    """
    if _can_view_sensitive_diamex_lines(user):
        return entries_qs

    sensitive_q = (
        Q(compte_code__startswith='641') |
        Q(compte_code__startswith='646') |
        Q(description__icontains='salaire') |
        Q(description__icontains='irsa') |
        Q(description__icontains='cnaps') |
        Q(description__icontains='fmfp') |
        Q(info__icontains='salaire') |
        Q(info__icontains='irsa') |
        Q(info__icontains='cnaps') |
        Q(info__icontains='fmfp') |
        Q(detail__icontains='salaire') |
        Q(detail__icontains='irsa') |
        Q(detail__icontains='cnaps') |
        Q(detail__icontains='fmfp')
    )
    return entries_qs.exclude(sensitive_q)


def import_diamex_home(request):
    """Page d'accueil de l'import DiameX avec statistiques"""
    from apps.employees.models import EmployeBaseDiameX

    # Récupérer les bases DiameX de l'employé connecté
    employe = getattr(request.user, 'employe', None) if hasattr(request.user, 'employe') else None
    bases_employe = []

    if employe:
        bases_qs = EmployeBaseDiameX.objects.filter(employe=employe)
        bases_employe = []
        for base in bases_qs:
            bases_employe.append({
                'id': str(base.id),
                'base_diamex': base.base_diamex,
                'chemin_base_diamex': base.chemin_base_diamex,
                'chemin_complet': base.chemin_complet,  # Ajout du chemin complet
            })

    # Statistiques filtrées par employé - OPTIMISé avec agrégation
    from django.db.models import Count, Max

    if employe:
        entries_qs = BaseDiameX.objects.filter(imported_by=employe)
    else:
        entries_qs = BaseDiameX.objects.all()

    # Une seule requète agrégée pour toutes les stats
    aggregate_stats = entries_qs.aggregate(
        total_entries=Count('id'),
        last_import_date=Max('date_import'),
        fichiers_count=Count('fichier_source', distinct=True)
    )

    # Récupérer la dernière entrée importée (seulement si nécessaire pour affichage)
    last_import_entry = None
    if aggregate_stats['last_import_date']:
        last_import_entry = entries_qs.filter(
            date_import=aggregate_stats['last_import_date']
        ).first()

    stats = {
        'total_entries': aggregate_stats['total_entries'] or 0,
        'last_import': last_import_entry,
        'fichiers_importes': aggregate_stats['fichiers_count'] or 0,
    }

    # Statistiques par fichier - UNE SEULE requète avec GROUP BY
    fichiers_stats_qs = entries_qs.values('fichier_source').annotate(
        count=Count('id')
    ).order_by('fichier_source')

    fichiers_stats = {item['fichier_source']: item['count'] for item in fichiers_stats_qs}

    return render(request, 'accounting/import_diamex.html', {
        'stats': stats,
        'fichiers_stats': fichiers_stats,
        'bases_employe': bases_employe,
        'employe': employe,
    })


def _normalize_selected_import_months(raw_months):
    selected_months = []
    seen = set()
    for item in raw_months or []:
        value = str(item or '').strip()
        if len(value) == 7 and value[4] == '-':
            year_part = value[:4]
            month_part = value[5:7]
            if year_part.isdigit() and month_part.isdigit():
                month_number = int(month_part)
                if 1 <= month_number <= 12 and value not in seen:
                    seen.add(value)
                    selected_months.append(value)
    return selected_months


def _extract_import_month_key(date_value):
    if not date_value:
        return ''
    if hasattr(date_value, 'strftime'):
        return date_value.strftime('%Y-%m')
    value = str(date_value).strip()
    if len(value) >= 7 and value[4] == '-':
        return value[:7]
    for fmt in ('%d/%m/%Y', '%d/%m/%Y %H:%M:%S', '%Y/%m/%d', '%m/%d/%Y'):
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.strftime('%Y-%m')
        except ValueError:
            continue
    return ''


def _build_selected_months_q(selected_months, field_name='date_m'):
    query = Q()
    for value in selected_months or []:
        year = int(value[:4])
        month = int(value[5:7])
        query |= Q(**{f'{field_name}__year': year, f'{field_name}__month': month})
    return query


def _rattacher_fichier_diamex_renomme(fichier_nom, progs, log_progress):
    """
    Un fichier Access renommé garde son Prog : on rattache au nouveau nom les
    lignes déjà importées sous l'ancien nom, au lieu de les réimporter en double.
    Les lignes d'origine (et leurs scans, écritures, pointages) sont conservées ;
    les doublons déjà créés sous le nouveau nom sont supprimés.
    """
    from django.db import IntegrityError
    from .models import DocumentationComptable, ScanVerificationCache
    from .models_pointage import MoisPointage

    progs = {str(p) for p in progs if p not in (None, '')}
    if not progs:
        return
    anciens_noms = set(
        BaseDiameX.objects.filter(prog__in=progs)
        .exclude(fichier_source=fichier_nom)
        .values_list('fichier_source', flat=True)
        .distinct()
    )
    if not anciens_noms:
        return

    with transaction.atomic():
        for ancien in sorted(anciens_noms):
            anciennes = BaseDiameX.objects.filter(fichier_source=ancien, prog__in=progs)
            cles_anciennes = set(anciennes.values_list('prog', 'id_access'))
            doublons_ids = [
                pk for pk, prog, id_access in BaseDiameX.objects.filter(
                    fichier_source=fichier_nom
                ).values_list('id', 'prog', 'id_access')
                if (prog, id_access) in cles_anciennes
            ]
            nb_doublons = 0
            for entry in BaseDiameX.objects.filter(id__in=doublons_ids):
                _clear_imported_scan(entry)
                entry.delete()
                nb_doublons += 1
            nb_renommees = anciennes.update(fichier_source=fichier_nom)
            log_progress(
                f"[RENAME] '{ancien}' -> '{fichier_nom}' : {nb_renommees} ligne(s) rattachee(s), "
                f"{nb_doublons} doublon(s) supprime(s)"
            )

            # Les tables annexes ne suivent que si l'ancien fichier est entièrement repris.
            if BaseDiameX.objects.filter(fichier_source=ancien).exists():
                log_progress(f"[WARN] '{ancien}' contient d'autres Prog : tables annexes non renommees")
                continue

            cles_soldes = set(
                SoldesReels.objects.filter(fichier_source=ancien).values_list('journal', 'date_m', 'rec')
            )
            SoldesReels.objects.filter(
                id__in=[
                    pk for pk, j, d, r in SoldesReels.objects.filter(
                        fichier_source=fichier_nom
                    ).values_list('id', 'journal', 'date_m', 'rec')
                    if (j, d, r) in cles_soldes
                ]
            ).delete()
            SoldesReels.objects.filter(fichier_source=ancien).update(fichier_source=fichier_nom)

            periodes_nouvelles = set(
                MoisPointage.objects.filter(fichier_source=fichier_nom).values_list('periode', flat=True)
            )
            conflits = MoisPointage.objects.filter(fichier_source=ancien, periode__in=periodes_nouvelles)
            if conflits.exists():
                log_progress(
                    f"[WARN] Pointage deja commence sous les deux noms pour "
                    f"{', '.join(p.strftime('%m/%Y') for p in conflits.values_list('periode', flat=True))} : "
                    f"mois conserves sous '{ancien}'"
                )
            MoisPointage.objects.filter(fichier_source=ancien).exclude(
                periode__in=periodes_nouvelles
            ).update(fichier_source=fichier_nom)

            for doc in DocumentationComptable.objects.filter(fichier_source=ancien):
                doc.fichier_source = fichier_nom
                try:
                    with transaction.atomic():
                        doc.save(update_fields=['fichier_source'])
                except IntegrityError:
                    log_progress(f"[WARN] Documentation {doc.pk} deja presente sous le nouveau nom, conservee sous '{ancien}'")

            ScanVerificationCache.objects.filter(fichier_source=ancien).delete()


@csrf_exempt
@require_http_methods(["POST"])
@diamex_agent_required
def import_from_access(request):
    """
    Import des données depuis un fichier Access.
    Supporte 2 modes:
    1. Mode FICHIER VPS: Reçoit file_path â†’ Lit avec pyodbc (existant)
    2. Mode LOCAL CLIENT: Reçoit data_rows JSON â†’ Import direct sans pyodbc
    """
    import json

    file_path = request.POST.get('file_path')
    fichier_nom = request.POST.get('fichier_nom', os.path.basename(file_path) if file_path else 'Inconnu')

    # Créer un ID de session pour le tracking
    from django.core.cache import cache
    import uuid
    session_id = str(uuid.uuid4())

    # Fonction helper pour logger
    def log_progress(message, step=None, total=None):
        cache_key = f'import_progress_{session_id}'
        logs = cache.get(cache_key, [])
        log_entry = {
            'message': message,
            'timestamp': timezone.now().isoformat(),
            'step': step,
            'total': total
        }
        logs.append(log_entry)
        cache.set(cache_key, logs, 300)  # 5 minutes
        print(f"[LOG] {message}")

    # ========== MODE 2: DONNéES JSON DEPUIS CLIENT ==========
    # Si le client envoie data_rows (fichier Access lu localement), on skip pyodbc
    data_json = request.POST.get('data_rows')
    soldes_json = request.POST.get('soldes_rows')
    selected_months = _normalize_selected_import_months(
        request.POST.getlist('selected_months') or request.POST.get('selected_months', '').split(',')
    )
    selected_months_set = set(selected_months)
    chunk_index = max(1, int(request.POST.get('chunk_index') or 1))
    chunk_count = max(1, int(request.POST.get('chunk_count') or 1))
    is_chunked_import = chunk_count > 1
    is_first_chunk = chunk_index == 1
    is_last_chunk = chunk_index >= chunk_count

    if data_json:
        # MODE LOCAL CLIENT - Import depuis JSON
        log_progress(f"[MODE] Import LOCAL CLIENT depuis JSON pour: {fichier_nom}")
        if is_chunked_import:
            log_progress(f"[CHUNK] Lot {chunk_index}/{chunk_count}")

        try:
            data_rows = json.loads(data_json)
            soldes_rows = json.loads(soldes_json) if soldes_json else []
            if selected_months_set:
                data_rows = [
                    row for row in data_rows
                    if _extract_import_month_key(row.get('DateM')) in selected_months_set
                ]
                soldes_rows = [
                    row for row in soldes_rows
                    if _extract_import_month_key(row.get('DateM')) in selected_months_set
                ]

            log_progress(f"[OK] Données JSON reçues: {len(data_rows)} lignes DATA, {len(soldes_rows)} lignes SoldesReels")
            if selected_months_set:
                log_progress(f"[FILTER] Import partiel sur mois: {', '.join(selected_months)}")

            # Statistiques d'import
            imported_count = 0
            updated_count = 0
            deleted_count = 0
            errors = []

            total_rows = len(data_rows)
            log_progress(f"[SAVE] Import de {total_rows} enregistrements DATA vers Django...")

            importing_employe = getattr(request.user, 'employe', None) if hasattr(request.user, 'employe') else None
            employe = importing_employe
            employe_surnom = request.POST.get('employe_surnom')
            if employe_surnom:
                from apps.employees.models import Employe
                employe = Employe.objects.filter(surnom=employe_surnom).first()
                if not employe:
                    employe = Employe.objects.filter(surnom__iexact=employe_surnom).first()
                if employe:
                    log_progress(f"[OK] Employe trouve: {employe.surnom} (ID: {employe.id})")
                else:
                    total_employes = Employe.objects.count()
                    surnoms = list(Employe.objects.values_list('surnom', flat=True)[:10])
                    log_progress(f"[WARN] Employe avec surnom '{employe_surnom}' non trouve. Total employes: {total_employes}")
                    log_progress(f"[DEBUG] Exemples de surnoms: {surnoms}")

            if is_first_chunk:
                scope_label = f"les mois {', '.join(selected_months)}" if selected_months_set else "tous les mois"
                log_progress(
                    f"[SAFE] Mise a jour DATA pour {scope_label}: les scans web existants sont conserves"
                )

            journal_codes = {
                row.get('Journal') for row in data_rows
                if row.get('Journal')
            }
            compte_codes = {
                row.get('Cat') for row in data_rows
                if row.get('Cat')
            }
            journals_map = {
                journal.code: journal
                for journal in Journal.objects.filter(code__in=journal_codes)
            }
            comptes_map = {
                compte.compte: compte
                for compte in Compte.objects.filter(compte__in=compte_codes)
            }
            _rattacher_fichier_diamex_renomme(
                fichier_nom,
                {row.get('Prog') for row in data_rows},
                log_progress,
            )
            existing_entries_map = {
                (entry.prog, entry.id_access): entry
                for entry in BaseDiameX.objects.filter(fichier_source=fichier_nom)
            }

            with transaction.atomic():
                # éTAPE 1 : Collecter tous les IDs présents
                access_ids = set()
                current_row = 0
                missing_id_count = 0
                duplicate_key_count = 0
                entries_to_create = []
                entries_to_update = []

                for row_data in data_rows:
                    current_row += 1
                    if current_row % 100 == 0:
                        log_progress(f"[PROGRESS] Import DATA: {current_row}/{total_rows}", current_row, total_rows)
                    try:
                        # ID Access et Prog
                        id_access = row_data.get('ID')
                        prog = row_data.get('Prog')

                        if not id_access:
                            missing_id_count += 1
                            continue

                        key = (prog, id_access)
                        if key in access_ids:
                            duplicate_key_count += 1
                        access_ids.add(key)

                        existing = existing_entries_map.get(key)

                        journal_code = row_data.get('Journal')
                        compte_code = row_data.get('Cat')
                        scan_value = row_data.get('Scan')
                        entry_data = {
                            'fichier_source': fichier_nom,
                            'id_access': id_access,
                            'journal_code': journal_code,
                            'date_m': row_data.get('DateM'),
                            'rec': row_data.get('Rec'),
                            'date_rec': row_data.get('DateRec'),
                            'description': row_data.get('Description'),
                            'montant_in': float(row_data.get('In') or 0),
                            'montant_out': float(row_data.get('Out') or 0),
                            'compte_code': compte_code,
                            'pers': row_data.get('PERS'),
                            'detail': row_data.get('Detail'),
                            'info': row_data.get('Info'),
                            'fin': row_data.get('Fin'),
                            'activ': row_data.get('Activ'),
                            'scan': scan_value,
                            'prog': prog,
                            'fournisseur': row_data.get('Fournisseur'),
                            'date_input': row_data.get('DateInput'),
                            'is_checked': bool(row_data.get('Check')),
                            'match': row_data.get('Match'),
                            'bank_rec': row_data.get('BankRec'),
                            'imported_by': employe,
                            'journal': journals_map.get(journal_code),
                            'compte': comptes_map.get(compte_code),
                        }

                        # Créer ou mettre à jour
                        if existing:
                            # Chemin Scan vide dans Access : le scan déjà importé sur le VPS est conservé
                            # (il n'est supprimé qu'avec l'écriture elle-même).
                            for key, value in entry_data.items():
                                setattr(existing, key, value)
                            entries_to_update.append(existing)
                        else:
                            entries_to_create.append(BaseDiameX(**entry_data))

                    except Exception as e:
                        errors.append(f"Erreur ligne ID {id_access}: {str(e)}")

                if entries_to_create:
                    BaseDiameX.objects.bulk_create(entries_to_create, batch_size=500)
                if entries_to_update:
                    BaseDiameX.objects.bulk_update(
                        entries_to_update,
                        [
                            'fichier_source', 'journal_code', 'date_m', 'rec', 'date_rec',
                            'description', 'montant_in', 'montant_out', 'compte_code',
                            'pers', 'detail', 'info', 'fin', 'activ', 'scan', 'prog',
                            'fournisseur', 'date_input', 'is_checked', 'match',
                            'bank_rec', 'imported_by', 'journal', 'compte'
                        ],
                        batch_size=500
                    )
                imported_count = len(entries_to_create)
                updated_count = len(entries_to_update)

                cleanup_keys = None
                if is_last_chunk:
                    all_entry_keys_raw = request.POST.get('all_entry_keys')
                    if all_entry_keys_raw:
                        try:
                            cleanup_keys = {
                                (
                                    None if item.get('prog') is None else str(item.get('prog')),
                                    int(item.get('id_access')),
                                )
                                for item in json.loads(all_entry_keys_raw)
                                if item.get('id_access') is not None
                            }
                        except (TypeError, ValueError, json.JSONDecodeError):
                            cleanup_keys = None
                    elif not is_chunked_import:
                        cleanup_keys = {
                            (None if prog is None else str(prog), int(id_access))
                            for prog, id_access in access_ids
                        }

                if cleanup_keys is not None:
                    log_progress(f"[PROGRESS] Nettoyage des entrées supprimées...")
                    cleanup_qs = BaseDiameX.objects.filter(fichier_source=fichier_nom)
                    if selected_months_set:
                        cleanup_qs = cleanup_qs.filter(
                            _build_selected_months_q(selected_months, field_name='date_m')
                        )
                    existing_entries = list(cleanup_qs)

                    for entry in existing_entries:
                        entry_key = (
                            None if entry.prog is None else str(entry.prog),
                            int(entry.id_access),
                        )
                        if entry_key not in cleanup_keys:
                            _clear_imported_scan(entry)
                            entry.delete()
                            deleted_count += 1

                    if deleted_count > 0:
                        log_progress(f"[OK] {deleted_count} entrée(s) supprimée(s)")

            log_progress(f"[STATS] Lignes DATA détectées: {total_rows}; clés uniques: {len(access_ids)}; doublons: {duplicate_key_count}; ID manquants: {missing_id_count}")
            log_progress(f"[OK] Import DATA terminé: {imported_count} nouveaux, {updated_count} mis à jour, {deleted_count} supprimés")
            if missing_id_count:
                log_progress(f"[WARN] {missing_id_count} lignes DATA ignorées car ID absent")

            # Import SoldesReels si fourni
            soldes_imported = 0
            soldes_updated = 0

            if soldes_rows:
                log_progress(f"[SAVE] Import de {len(soldes_rows)} enregistrements SoldesReels...")
                from .models import SoldesReels
                if selected_months_set and is_first_chunk:
                    month_query = _build_selected_months_q(selected_months, field_name='date_m')
                    partial_soldes_deleted = SoldesReels.objects.filter(
                        fichier_source=fichier_nom
                    ).filter(month_query).delete()[0]
                    log_progress(
                        f"[SAFE] Import partiel: {partial_soldes_deleted} ligne(s) SoldesReels supprimée(s) pour {', '.join(selected_months)}"
                    )
                elif not selected_months_set and is_first_chunk:
                    soldes_deleted = SoldesReels.objects.filter(fichier_source=fichier_nom).delete()[0]
                    if soldes_deleted:
                        log_progress(
                            f"[SAFE] Remplacement complet: {soldes_deleted} ligne(s) SoldesReels supprimée(s)"
                        )
                existing_soldes_map = {
                    (solde.journal, solde.date_m, solde.rec): solde
                    for solde in SoldesReels.objects.filter(fichier_source=fichier_nom)
                }

                with transaction.atomic():
                    soldes_keys = set()
                    soldes_to_create = []
                    soldes_to_update = []

                    for row_data in soldes_rows:
                        try:
                            journal = row_data.get('Journal')
                            date_m = row_data.get('DateM')
                            rec = row_data.get('Rec')

                            if journal is None or date_m is None or rec is None:
                                continue

                            soldes_keys.add((journal, date_m, rec))

                            existing_solde = existing_soldes_map.get((journal, date_m, rec))

                            solde_entry_data = {
                                'fichier_source': fichier_nom,
                                'chemin_base': os.path.dirname(file_path) if file_path else '',
                                'journal': journal,
                                'date_m': date_m,
                                'rec': rec,
                                'date_rec': row_data.get('DateRec'),
                                'description': row_data.get('Description'),
                                'ccy': float(row_data.get('CCY') or 0),
                                'validation': row_data.get('Validation'),
                                'scan': row_data.get('Scan'),
                                'date_input': row_data.get('DateInput'),
                                'imported_by': employe
                            }

                            if existing_solde:
                                for key, value in solde_entry_data.items():
                                    setattr(existing_solde, key, value)
                                soldes_to_update.append(existing_solde)
                            else:
                                soldes_to_create.append(SoldesReels(**solde_entry_data))

                        except Exception as e:
                            errors.append(f"Erreur SoldesReels: {str(e)}")

                    if soldes_to_create:
                        SoldesReels.objects.bulk_create(soldes_to_create, batch_size=200)
                    if soldes_to_update:
                        SoldesReels.objects.bulk_update(
                            soldes_to_update,
                            [
                                'fichier_source', 'chemin_base', 'journal', 'date_m', 'rec',
                                'date_rec', 'description', 'ccy', 'validation', 'scan',
                                'date_input', 'imported_by'
                            ],
                            batch_size=200
                        )
                    soldes_imported = len(soldes_to_create)
                    soldes_updated = len(soldes_to_update)

                    if not selected_months_set and not is_chunked_import:
                        for solde in existing_soldes_map.values():
                            if (solde.journal, solde.date_m, solde.rec) not in soldes_keys:
                                solde.delete()

                log_progress(f"[OK] Import SoldesReels terminé: {soldes_imported} nouveaux, {soldes_updated} mis à jour")

            return JsonResponse({
                'success': True,
                'message': (
                    f"Import {'lot ' + str(chunk_index) + '/' + str(chunk_count) if is_chunked_import else 'terminé'}: "
                    f"{imported_count} nouveaux, {updated_count} mis à jour, {deleted_count} supprimés"
                ),
                'session_id': session_id,
                'chunked': is_chunked_import,
                'chunk_index': chunk_index,
                'chunk_count': chunk_count,
                'is_last_chunk': is_last_chunk,
                'stats': {
                    'data': {
                        'imported': imported_count,
                        'updated': updated_count,
                        'deleted': deleted_count
                    },
                    'soldes': {
                        'imported': soldes_imported,
                        'updated': soldes_updated
                    }
                },
                'errors': errors[:10]  # Limiter à 10 erreurs
            })

        except Exception as e:
            log_progress(f"[ERROR] Erreur import JSON: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': str(e),
                'session_id': session_id
            }, status=500)

    # ========== MODE 1: FICHIER VPS (EXISTANT) ==========
    if not file_path:
        return JsonResponse({'success': False, 'error': 'Aucun fichier spécifié', 'session_id': session_id})

    if not os.path.exists(file_path):
        return JsonResponse({'success': False, 'error': f'Fichier introuvable: {file_path}', 'session_id': session_id})

    try:
        log_progress(f"[CONNECT] Connexion au fichier Access: {fichier_nom}")

        # Connexion au fichier Access
        conn_str = (
            r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
            f'DBQ={file_path};'
        )
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        log_progress("[READ] Lecture de la table DATA...")

        # Lire les données de la table DATA
        cursor.execute("SELECT * FROM DATA")
        columns = [column[0] for column in cursor.description]

        log_progress(f"[OK] Table DATA trouvée ({len(columns)} colonnes)")

        # Statistiques d'import
        imported_count = 0
        updated_count = 0
        deleted_count = 0
        errors = []

        # Compter le nombre total de lignes
        total_rows = len(cursor.fetchall())
        cursor.execute("SELECT * FROM DATA")  # Re-exécuter pour réinitialiser le curseur
        cursor.fetchall()  # Lire à nouveau
        cursor.execute("SELECT * FROM DATA")  # Re-exécuter une dernière fois

        log_progress(f"[SAVE] Import de {total_rows} enregistrements DATA vers Django...")

        with transaction.atomic():
            # éTAPE 1 : Collecter tous les IDs présents dans le fichier Access
            access_ids = set()
            current_row = 0
            missing_id_count = 0

            employe = getattr(request.user, 'employe', None) if hasattr(request.user, 'employe') else None
            for row in cursor.fetchall():
                current_row += 1
                if current_row % 100 == 0:
                    log_progress(f"[PROGRESS] Import DATA: {current_row}/{total_rows}", current_row, total_rows)
                try:
                    # Créer un dictionnaire des données
                    data = dict(zip(columns, row))

                    # ID Access et Prog
                    id_access = data.get('ID')
                    prog = data.get('Prog')

                    if not id_access:
                        missing_id_count += 1
                        continue

                    # Ajouter (prog, id_access) à l'ensemble des clés présentes
                    access_ids.add((prog, id_access))

                    # Chercher une entrée existante par (prog, id_access)
                    existing = BaseDiameX.objects.filter(
                        prog=prog,
                        id_access=id_access
                    ).first()

                    # Préparer les données
                    entry_data = {
                        'fichier_source': fichier_nom,
                        'id_access': id_access,
                        'journal_code': data.get('Journal'),
                        'date_m': data.get('DateM'),
                        'rec': data.get('Rec'),
                        'date_rec': data.get('DateRec'),
                        'description': data.get('Description'),
                        'montant_in': float(data.get('In') or 0),
                        'montant_out': float(data.get('Out') or 0),
                        'compte_code': data.get('Cat'),
                        'pers': data.get('PERS'),
                        'detail': data.get('Detail'),
                        'info': data.get('Info'),
                        'fin': data.get('Fin'),
                        'activ': data.get('Activ'),
                        'scan': data.get('Scan'),
                        'prog': prog,
                        'fournisseur': data.get('Fournisseur'),
                        'date_input': data.get('DateInput'),
                        'is_checked': bool(data.get('Check')),
                        'match': data.get('Match'),
                        'bank_rec': data.get('BankRec'),
                        'imported_by': employe
                    }

                    # Relier au journal si possible
                    if entry_data['journal_code']:
                        journal = Journal.objects.filter(code=entry_data['journal_code']).first()
                        if journal:
                            entry_data['journal'] = journal

                    # Relier au compte si possible
                    if entry_data['compte_code']:
                        compte = Compte.objects.filter(compte=entry_data['compte_code']).first()
                        if compte:
                            entry_data['compte'] = compte

                    # Créer ou mettre à jour
                    if existing:
                        for key, value in entry_data.items():
                            setattr(existing, key, value)
                        existing.save()
                        updated_count += 1
                    else:
                        BaseDiameX.objects.create(**entry_data)
                        imported_count += 1

                except Exception as e:
                    errors.append(f"Erreur ligne ID {id_access}: {str(e)}")

            # éTAPE 2 : Supprimer les entrées qui n'existent plus dans Access
            log_progress(f"[PROGRESS] Nettoyage des entrées supprimées dans Access...")

            # Récupérer toutes les entrées de ce fichier dans PostgreSQL
            existing_entries = BaseDiameX.objects.filter(fichier_source=fichier_nom)
            deleted_count = 0

            for entry in existing_entries:
                # Vérifier par (prog, id_access)
                if (entry.prog, entry.id_access) not in access_ids:
                    # Cette entrée n'existe plus dans Access, la supprimer
                    _clear_imported_scan(entry)
                    entry.delete()
                    deleted_count += 1

            if deleted_count > 0:
                log_progress(f"[OK] {deleted_count} entrée(s) supprimée(s) (n'existent plus dans Access)")

        log_progress(f"[OK] Import DATA terminé: {imported_count} nouveaux, {updated_count} mis à jour, {deleted_count} supprimés")
        if missing_id_count:
            log_progress(f"[WARN] {missing_id_count} lignes DATA ignorées car ID absent")

        # Import de la table SoldesReels
        soldes_imported = 0
        soldes_updated = 0
        soldes_errors = []

        try:
            # Vérifier si la table SoldesReels existe dans le fichier Access
            log_progress(f"[SEARCH] Recherche table SoldesReels dans {fichier_nom}...")
            print(f"[SEARCH] DEBUG: Tentative de lecture table SoldesReels...")

            cursor.execute("SELECT * FROM SoldesReels")
            soldes_columns = [column[0] for column in cursor.description]
            log_progress(f"[OK] Table SoldesReels trouvée ! ({len(soldes_columns)} colonnes)")
            print(f"[OK] DEBUG: Colonnes trouvées: {', '.join(soldes_columns)}")
            # Vérifier si colonne Scan existe
            has_scan_column = 'Scan' in soldes_columns
            print(f"[OK] DEBUG: Colonne 'Scan' présente: {has_scan_column}")

            # Extraire le chemin de base depuis file_path pour préfixer les scans
            chemin_base = os.path.dirname(file_path)

            # Récupérer l'employé connecté
            employe = getattr(request.user, 'employe', None) if hasattr(request.user, 'employe') else None

            from .models import SoldesReels

            # Compter le nombre total de lignes SoldesReels
            total_soldes_rows = len(cursor.fetchall())
            cursor.execute("SELECT * FROM SoldesReels")  # Re-exécuter
            log_progress(f"[SAVE] Import de {total_soldes_rows} enregistrements SoldesReels vers Django...")

            with transaction.atomic():
                # éTAPE 1 : Collecter tous les triplets (journal, date_m, rec) présents dans Access
                soldes_keys = set()
                current_solde_row = 0

                for row in cursor.fetchall():
                    current_solde_row += 1
                    if current_solde_row % 50 == 0:  # Log tous les 50 enregistrements
                        log_progress(f"[PROGRESS] Import SoldesReels: {current_solde_row}/{total_soldes_rows}", current_solde_row, total_soldes_rows)
                    try:
                        soldes_data = dict(zip(soldes_columns, row))

                        # Identifiant unique: journal + date_m + rec
                        journal = soldes_data.get('Journal')
                        date_m = soldes_data.get('DateM')
                        rec = soldes_data.get('Rec')

                        # [OK] Vérifier si None (pas si falsy, car rec peut ètre 0.0)
                        if journal is None or date_m is None or rec is None:
                            continue

                        # Ajouter la clé au set
                        soldes_keys.add((journal, date_m, rec))

                        # Chercher une entrée existante
                        existing_solde = SoldesReels.objects.filter(
                            fichier_source=fichier_nom,
                            journal=journal,
                            date_m=date_m,
                            rec=rec
                        ).first()

                        # Préparer les données
                        scan_value = soldes_data.get('Scan')
                        # DEBUG: Afficher valeur Scan pour les 5 premières lignes
                        if current_solde_row <= 5:
                            has_scan = 'OUI' if scan_value and scan_value.strip() else 'NON'
                            log_progress(f"[DATA] Ligne {current_solde_row}: {journal} {date_m} Scan={has_scan}")
                            if scan_value:
                                log_progress(f"   Valeur: {scan_value[:80]}")

                        solde_entry_data = {
                            'fichier_source': fichier_nom,
                            'chemin_base': chemin_base,
                            'journal': journal,
                            'date_m': date_m,
                            'rec': rec,
                            'date_rec': soldes_data.get('DateRec'),
                            'description': soldes_data.get('Description'),
                            'ccy': float(soldes_data.get('CCY') or 0),
                            'validation': soldes_data.get('Validation'),
                            'scan': scan_value,
                            'date_input': soldes_data.get('DateInput'),
                            'imported_by': employe
                        }

                        # Créer ou mettre à jour
                        if existing_solde:
                            # Ne mettre à jour que si nouvelle valeur NON None
                            # Sauf pour les champs obligatoires
                            champs_obligatoires = ['fichier_source', 'chemin_base', 'journal', 'date_m', 'rec', 'ccy']
                            for key, value in solde_entry_data.items():
                                if value is not None or key in champs_obligatoires:
                                    setattr(existing_solde, key, value)
                            existing_solde.save()
                            soldes_updated += 1
                        else:
                            SoldesReels.objects.create(**solde_entry_data)
                            soldes_imported += 1

                    except Exception as e:
                        error_msg = f"Erreur SoldesReels {journal}/{date_m}/{rec}: {str(e)}"
                        soldes_errors.append(error_msg)
                        log_progress(f"[ERROR] {error_msg}")

                # éTAPE 2 : Supprimer les entrées SoldesReels qui n'existent plus dans Access
                log_progress(f"[PROGRESS] Nettoyage SoldesReels - Suppression des entrées obsolètes...")

                existing_soldes = SoldesReels.objects.filter(fichier_source=fichier_nom)
                soldes_deleted_count = 0

                for solde_entry in existing_soldes:
                    solde_key = (solde_entry.journal, solde_entry.date_m, solde_entry.rec)
                    if solde_key not in soldes_keys:
                        # Cette entrée n'existe plus dans Access, la supprimer
                        solde_entry.delete()
                        soldes_deleted_count += 1

                if soldes_deleted_count > 0:
                    log_progress(f"[OK] {soldes_deleted_count} entrée(s) SoldesReels supprimée(s) (n'existent plus dans Access)")

                # Log de fin d'import SoldesReels
                log_progress(f"[OK] Import SoldesReels terminé: {soldes_imported} nouveaux, {soldes_updated} mis à jour, {soldes_deleted_count} supprimés")
                if soldes_errors:
                    log_progress(f"[WARNING] {len(soldes_errors)} erreur(s) SoldesReels")
                    for i, err in enumerate(soldes_errors[:10], 1):
                        log_progress(f"  Erreur {i}: {err}")

        except pyodbc.Error as e:
            # Table SoldesReels n'existe pas dans ce fichier Access
            error_msg = str(e)
            print(f"[WARNING] DEBUG: Erreur pyodbc - {error_msg}")
            if "no such table" in error_msg.lower() or "table" in error_msg.lower():
                log_progress(f"[INFO] Table SoldesReels absente dans {fichier_nom}")
                soldes_errors.append(f"Table SoldesReels absente dans {fichier_nom}")
            else:
                log_progress(f"[WARNING] Erreur pyodbc SoldesReels: {error_msg}")
                soldes_errors.append(f"Erreur Access SoldesReels: {error_msg}")
        except Exception as e:
            print(f"[ERROR] DEBUG: Exception générale - {str(e)} - Type: {type(e).__name__}")
            import traceback
            print(traceback.format_exc())
            log_progress(f"[ERROR] Erreur générale SoldesReels: {str(e)}")
            soldes_errors.append(f"Erreur générale SoldesReels: {str(e)}")

        cursor.close()
        conn.close()

        log_progress("[OK] Import terminé avec succès")

        return JsonResponse({
            'success': True,
            'imported': imported_count,
            'updated': updated_count,
            'errors': errors,
            'fichier': fichier_nom,
            'soldes_imported': soldes_imported,
            'soldes_updated': soldes_updated,
            'soldes_errors': soldes_errors,
            'session_id': session_id,  # [OK] Retourne le session_id pour polling frontend
        })
    
    except Exception as e:
        log_progress(f"[ERROR] ERREUR CRITIQUE: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'Erreur lors de l\'import: {str(e)}',
            'session_id': session_id
        })


@csrf_exempt
@require_http_methods(["POST"])
@diamex_agent_required
def imported_scans_status(request):
    try:
        payload = json.loads(request.body or '{}')
    except ValueError:
        return JsonResponse({'success': False, 'error': 'JSON invalide'}, status=400)

    fichier_nom = (payload.get('fichier_nom') or '').strip()
    requested_entries = payload.get('entries') or []

    if not fichier_nom:
        return JsonResponse({'success': False, 'error': 'fichier_nom manquant'}, status=400)

    if not isinstance(requested_entries, list):
        return JsonResponse({'success': False, 'error': 'entries invalide'}, status=400)

    requested_scans = {}
    requested_extensions = {}
    requested_ids = []
    for item in requested_entries:
        try:
            id_access = int(item.get('id_access'))
        except (TypeError, ValueError):
            continue
        requested_ids.append(id_access)
        requested_scans[id_access] = _normalize_scan_value(item.get('scan_value'))
        requested_extensions[id_access] = (item.get('local_extension') or '').strip().lower()

    existing_ids = []
    entries_qs = BaseDiameX.objects.filter(
        fichier_source=fichier_nom,
        id_access__in=requested_ids,
    )

    for entry in entries_qs:
        scan_importe_name = getattr(getattr(entry, 'scan_importe', None), 'name', '') or ''
        if not scan_importe_name or not default_storage.exists(scan_importe_name):
            continue
        requested_scan = requested_scans.get(entry.id_access, '')
        requested_extension = requested_extensions.get(entry.id_access, '')
        if requested_extension in ('.tif', '.tiff') and _is_jpg_name(scan_importe_name):
            continue
        if _is_tiff_file(requested_scan) and not _is_pdf_name(scan_importe_name):
            continue
        existing_ids.append(entry.id_access)

    return JsonResponse({
        'success': True,
        'existing_ids': sorted(set(existing_ids)),
    })


@csrf_exempt
@require_http_methods(["POST"])
@diamex_agent_required
def upload_imported_scans(request):
    try:
        fichier_nom = (request.POST.get('fichier_nom') or '').strip()
        metadata_raw = request.POST.get('scans_metadata') or '[]'
        scans_metadata = json.loads(metadata_raw)
    except ValueError:
        return JsonResponse({'success': False, 'error': 'Metadata scans invalide'}, status=400)

    if not fichier_nom:
        return JsonResponse({'success': False, 'error': 'fichier_nom manquant'}, status=400)

    if not isinstance(scans_metadata, list):
        return JsonResponse({'success': False, 'error': 'Format scans_metadata invalide'}, status=400)

    uploaded_count = 0
    missing_entries = 0
    skipped_existing = 0
    errors = []

    for meta in scans_metadata:
        field_name = (meta.get('field_name') or '').strip()
        id_access_raw = meta.get('id_access')
        scan_value = (meta.get('scan_value') or '').strip()
        upload_name = (meta.get('upload_name') or '').strip()
        local_extension = (meta.get('local_extension') or '').strip().lower()

        if not field_name:
            errors.append('Champ fichier scan manquant')
            continue

        uploaded_file = request.FILES.get(field_name)
        if not uploaded_file:
            errors.append(f'Fichier manquant pour {field_name}')
            continue

        try:
            id_access = int(id_access_raw)
        except (TypeError, ValueError):
            errors.append(f'ID Access invalide: {id_access_raw}')
            continue

        entry = BaseDiameX.objects.filter(
            fichier_source=fichier_nom,
            id_access=id_access,
        ).first()

        if not entry:
            missing_entries += 1
            errors.append(f'Entrée introuvable pour ID {id_access} ({fichier_nom})')
            continue

        requested_scan = _normalize_scan_value(scan_value)
        scan_importe_name = getattr(getattr(entry, 'scan_importe', None), 'name', '') or ''
        existing_import_available = bool(scan_importe_name and default_storage.exists(scan_importe_name))
        uploaded_name = upload_name or uploaded_file.name or ''
        replacing_non_pdf_with_tiff = (
            existing_import_available and
            not _is_pdf_name(scan_importe_name) and
            (
                _is_tiff_file(uploaded_name) or
                local_extension in ('.tif', '.tiff')
            )
        )
        replacing_jpg_with_local_tiff = (
            existing_import_available and
            _is_jpg_name(scan_importe_name) and
            local_extension in ('.tif', '.tiff')
        )
        if (
            existing_import_available and
            not replacing_non_pdf_with_tiff and
            not replacing_jpg_with_local_tiff
        ):
            skipped_existing += 1
            continue

        try:
            content = uploaded_file.read()
            if not content:
                errors.append(f'Fichier scan vide pour ID {id_access}')
                continue

            content_file = ContentFile(content, name=upload_name or uploaded_file.name or f'{id_access}.bin')
            stale_name = _save_imported_scan_file(entry, content_file)

            update_fields = ['scan_importe']
            if scan_value:
                entry.scan = scan_value
                update_fields.append('scan')
            entry.save(update_fields=update_fields)
            if stale_name:
                # Suppression de l'ancien scan seulement après enregistrement du nouveau en base.
                default_storage.delete(stale_name)
            uploaded_count += 1
        except Exception as exc:
            errors.append(f'Erreur scan ID {id_access}: {exc}')

    return JsonResponse({
        'success': len(errors) == 0,
        'uploaded': uploaded_count,
        'missing_entries': missing_entries,
        'skipped_existing': skipped_existing,
        'errors': errors[:20],
    })


@require_http_methods(["GET"])
def api_import_progress(request, session_id):
    """API pour récupérer les logs de progression d'un import en cours"""
    from django.core.cache import cache

    cache_key = f'import_progress_{session_id}'
    logs = cache.get(cache_key, [])

    return JsonResponse({
        'success': True,
        'logs': logs,
        'total_logs': len(logs)
    })


@require_http_methods(["POST"])
def clear_all_data(request):
    """Supprime les données DiameX de l'employé connecté uniquement"""
    try:
        employe = getattr(request.user, 'employe', None) if hasattr(request.user, 'employe') else None

        if employe:
            # Supprimer uniquement les imports de cet employé
            entries_qs = BaseDiameX.objects.filter(imported_by=employe)
            count = entries_qs.count()
            for entry in entries_qs.iterator():
                _clear_imported_scan(entry)
            entries_qs.delete()
        else:
            # Si pas d'employé lié, supprimer tout (admin)
            entries_qs = BaseDiameX.objects.all()
            count = entries_qs.count()
            for entry in entries_qs.iterator():
                _clear_imported_scan(entry)
            entries_qs.delete()

        return JsonResponse({
            'success': True,
            'deleted': count,
            'message': f'{count} entrées supprimées'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@require_http_methods(["POST"])
def delete_file_data(request):
    """Supprime les données importées pour un fichier source précis."""
    try:
        fichier_source = (request.POST.get('fichier_source') or '').strip()
        if not fichier_source:
            return JsonResponse({
                'success': False,
                'error': 'Paramètre fichier_source manquant'
            }, status=400)

        from .models import SoldesReels

        employe = getattr(request.user, 'employe', None) if hasattr(request.user, 'employe') else None

        if employe:
            base_entries_qs = BaseDiameX.objects.filter(
                imported_by=employe,
                fichier_source=fichier_source
            )
            base_count = base_entries_qs.count()
            soldes_count = SoldesReels.objects.filter(
                imported_by=employe,
                fichier_source=fichier_source
            ).count()

            for entry in base_entries_qs.iterator():
                _clear_imported_scan(entry)
            base_entries_qs.delete()
            SoldesReels.objects.filter(
                imported_by=employe,
                fichier_source=fichier_source
            ).delete()
        else:
            base_entries_qs = BaseDiameX.objects.filter(fichier_source=fichier_source)
            base_count = base_entries_qs.count()
            soldes_count = SoldesReels.objects.filter(fichier_source=fichier_source).count()

            for entry in base_entries_qs.iterator():
                _clear_imported_scan(entry)
            base_entries_qs.delete()
            SoldesReels.objects.filter(fichier_source=fichier_source).delete()

        deleted_total = base_count + soldes_count

        return JsonResponse({
            'success': True,
            'deleted': deleted_total,
            'deleted_base_diamex': base_count,
            'deleted_soldes_reels': soldes_count,
            'fichier_source': fichier_source,
            'message': f'{deleted_total} entrées supprimées pour "{fichier_source}"'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@require_http_methods(["POST"])
def import_from_bases(request):
    """Import depuis les bases EmployeBaseDiameX cochées"""
    import json
    from apps.employees.models import EmployeBaseDiameX
    from django.core.cache import cache
    import uuid

    # [OK] Créer un ID de session pour le tracking
    session_id = str(uuid.uuid4())

    # [OK] Fonction helper pour logger
    def log_progress(message, step=None, total=None):
        cache_key = f'import_progress_{session_id}'
        logs = cache.get(cache_key, [])
        log_entry = {
            'message': message,
            'timestamp': timezone.now().isoformat(),
            'step': step,
            'total': total
        }
        logs.append(log_entry)
        cache.set(cache_key, logs, 300)  # 5 minutes
        print(f"[LOG] {message}")

    try:
        employe = getattr(request.user, 'employe', None) if hasattr(request.user, 'employe') else None
        if not employe:
            return JsonResponse({'success': False, 'error': 'Utilisateur non lié à un employé', 'session_id': session_id})

        # Récupérer les IDs des bases cochées
        body = json.loads(request.body)
        base_ids = body.get('base_ids', [])
        selected_months = _normalize_selected_import_months(body.get('selected_months', []))
        selected_months_set = set(selected_months)

        if not base_ids:
            return JsonResponse({'success': False, 'error': 'Aucune base sélectionnée', 'session_id': session_id})

        # Récupérer les bases de l'employé
        bases = EmployeBaseDiameX.objects.filter(
            id__in=base_ids,
            employe=employe
        )

        if not bases.exists():
            return JsonResponse({'success': False, 'error': 'Aucune base valide trouvée', 'session_id': session_id})

        total_imported = 0
        total_updated = 0
        all_errors = []
        total_soldes_imported = 0
        total_soldes_updated = 0
        all_soldes_errors = []

        for base in bases:
            file_path = base.chemin_complet  # Concatène chemin_base_diamex + base_diamex
            fichier_nom = base.base_diamex

            if not os.path.exists(file_path):
                error_msg = f'{fichier_nom}: Fichier introuvable - {file_path}'
                log_progress(f"[ERROR] {error_msg}")
                all_errors.append(error_msg)
                continue

            try:
                # [OK] Log connexion
                log_progress(f"[CONNECT] Connexion au fichier Access: {fichier_nom}")

                # Connexion au fichier Access
                conn_str = (
                    r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
                    f'DBQ={file_path};'
                )
                conn = pyodbc.connect(conn_str)
                cursor = conn.cursor()

                # [OK] Log lecture DATA
                log_progress(f"[READ] Lecture de la table DATA...")
                cursor.execute("SELECT * FROM DATA")
                columns = [column[0] for column in cursor.description]
                log_progress(f"[OK] Table DATA trouvée ({len(columns)} colonnes)")

                raw_rows = cursor.fetchall()
                if selected_months_set:
                    filtered_rows = []
                    for row in raw_rows:
                        row_data = dict(zip(columns, row))
                        if _extract_import_month_key(row_data.get('DateM')) in selected_months_set:
                            filtered_rows.append(row)
                else:
                    filtered_rows = raw_rows
                total_rows = len(filtered_rows)
                log_progress(f"[SAVE] Import de {total_rows} enregistrements DATA vers Django...")
                if selected_months_set:
                    log_progress(f"[FILTER] Import partiel sur mois: {', '.join(selected_months)}")

                imported_count = 0
                updated_count = 0
                current_row = 0
                deleted_count = 0

                if selected_months_set:
                    month_query = _build_selected_months_q(selected_months, field_name='date_m')
                    partial_entries_qs = BaseDiameX.objects.filter(fichier_source=fichier_nom).filter(month_query)
                    partial_entries = list(partial_entries_qs)
                    deleted_count = len(partial_entries)
                    for entry in partial_entries:
                        _clear_imported_scan(entry)
                    partial_entries_qs.delete()
                    log_progress(
                        f"[SAFE] Import partiel VPS: {deleted_count} ligne(s) DATA supprimée(s) pour {', '.join(selected_months)}"
                    )

                with transaction.atomic():
                    access_ids = set()
                    existing_entries_map = {
                        (entry.prog, entry.id_access): entry
                        for entry in BaseDiameX.objects.filter(fichier_source=fichier_nom)
                    }
                    for row in filtered_rows:
                        current_row += 1
                        if current_row % 100 == 0:  # [OK] Log tous les 100 enregistrements
                            log_progress(f"[PROGRESS] Import DATA: {current_row}/{total_rows}", current_row, total_rows)

                        try:
                            # Créer un dictionnaire des données
                            data = dict(zip(columns, row))

                            # ID Access et Prog
                            id_access = data.get('ID')
                            prog = data.get('Prog')

                            if not id_access:
                                continue
                            access_ids.add((prog, id_access))

                            # Chercher une entrée existante par (prog, id_access)
                            existing = existing_entries_map.get((prog, id_access))

                            # Préparer les données
                            entry_data = {
                                'fichier_source': fichier_nom,
                                'id_access': id_access,
                                'journal_code': data.get('Journal'),
                                'date_m': data.get('DateM'),
                                'rec': data.get('Rec'),
                                'date_rec': data.get('DateRec'),
                                'description': data.get('Description'),
                                'montant_in': float(data.get('In') or 0),
                                'montant_out': float(data.get('Out') or 0),
                                'compte_code': data.get('Cat'),
                                'pers': data.get('PERS'),
                                'detail': data.get('Detail'),
                                'info': data.get('Info'),
                                'fin': data.get('Fin'),
                                'activ': data.get('Activ'),
                                'scan': data.get('Scan'),
                                'prog': prog,
                                'fournisseur': data.get('Fournisseur'),
                                'date_input': data.get('DateInput'),
                                'is_checked': bool(data.get('Check')),
                                'match': data.get('Match'),
                                'bank_rec': data.get('BankRec'),
                                'imported_by': employe,  # Lier à l'employé
                            }

                            # Relier au journal si possible
                            if entry_data['journal_code']:
                                journal = Journal.objects.filter(code=entry_data['journal_code']).first()
                                if journal:
                                    entry_data['journal'] = journal

                            # Relier au compte si possible
                            if entry_data['compte_code']:
                                compte = Compte.objects.filter(compte=entry_data['compte_code']).first()
                                if compte:
                                    entry_data['compte'] = compte

                            if existing:
                                # Mise à jour
                                for key, value in entry_data.items():
                                    setattr(existing, key, value)
                                existing.save()
                                updated_count += 1
                            else:
                                # Création
                                BaseDiameX.objects.create(**entry_data)
                                imported_count += 1

                        except Exception as e:
                            all_errors.append(f"{fichier_nom} - Erreur ligne ID {id_access}: {str(e)}")

                    if not selected_months_set:
                        for entry in existing_entries_map.values():
                            if (entry.prog, entry.id_access) not in access_ids:
                                _clear_imported_scan(entry)
                                entry.delete()

                # [OK] Log fin import DATA
                log_progress(f"[OK] Import DATA terminé: {imported_count} nouveaux, {updated_count} mis à jour, {deleted_count} supprimés")

                # [OK] Import de la table SoldesReels
                soldes_imported = 0
                soldes_updated = 0
                soldes_errors = []

                try:
                    log_progress(f"[SEARCH] Recherche table SoldesReels dans {fichier_nom}...")
                    cursor.execute("SELECT * FROM SoldesReels")
                    soldes_columns = [column[0] for column in cursor.description]
                    log_progress(f"[OK] Table SoldesReels trouvée ! ({len(soldes_columns)} colonnes)")
                    log_progress(f"[DATA] Colonnes SoldesReels: {', '.join(soldes_columns)}")

                    # Extraire le chemin de base depuis file_path pour préfixer les scans
                    chemin_base = os.path.dirname(file_path)

                    from .models import SoldesReels

                    raw_soldes_rows = cursor.fetchall()
                    if selected_months_set:
                        filtered_soldes_rows = []
                        for row in raw_soldes_rows:
                            soldes_row_data = dict(zip(soldes_columns, row))
                            if _extract_import_month_key(soldes_row_data.get('DateM')) in selected_months_set:
                                filtered_soldes_rows.append(row)
                    else:
                        filtered_soldes_rows = raw_soldes_rows
                    total_soldes_rows = len(filtered_soldes_rows)
                    log_progress(f"[SAVE] Import de {total_soldes_rows} enregistrements SoldesReels vers Django...")

                    if selected_months_set:
                        month_query = _build_selected_months_q(selected_months, field_name='date_m')
                        deleted_soldes_count = SoldesReels.objects.filter(
                            fichier_source=fichier_nom
                        ).filter(month_query).delete()[0]
                        log_progress(
                            f"[SAFE] Import partiel VPS: {deleted_soldes_count} ligne(s) SoldesReels supprimée(s) pour {', '.join(selected_months)}"
                        )

                    with transaction.atomic():
                        current_solde_row = 0
                        skipped_rows = 0
                        soldes_keys = set()
                        existing_soldes_map = {}
                        for solde in SoldesReels.objects.filter(fichier_source=fichier_nom):
                            existing_soldes_map[(solde.journal, solde.date_m, solde.rec)] = solde
                        for row in filtered_soldes_rows:
                            current_solde_row += 1
                            if current_solde_row % 50 == 0:  # Log tous les 50 enregistrements
                                log_progress(f"[PROGRESS] Import SoldesReels: {current_solde_row}/{total_soldes_rows}", current_solde_row, total_soldes_rows)
                            try:
                                soldes_data = dict(zip(soldes_columns, row))

                                # Identifiant unique: journal + date_m + rec
                                journal = soldes_data.get('Journal')
                                date_m = soldes_data.get('DateM')
                                rec = soldes_data.get('Rec')

                                # [OK] Vérifier si None (pas si falsy, car rec peut ètre 0.0)
                                if journal is None or date_m is None or rec is None:
                                    skipped_rows += 1
                                    if skipped_rows <= 3:  # Logger les 3 premières lignes ignorées
                                        log_progress(f"[WARNING] Ligne ignorée (données manquantes): Journal={journal}, DateM={date_m}, Rec={rec}")
                                    continue
                                soldes_keys.add((journal, date_m, rec))

                                # Chercher une entrée existante
                                existing_solde = existing_soldes_map.get((journal, date_m, rec))

                                # Préparer les données
                                solde_entry_data = {
                                    'fichier_source': fichier_nom,
                                    'chemin_base': chemin_base,
                                    'journal': journal,
                                    'date_m': date_m,
                                    'rec': rec,
                                    'date_rec': soldes_data.get('DateRec'),
                                    'description': soldes_data.get('Description'),
                                    'ccy': float(soldes_data.get('CCY') or 0),
                                    'validation': soldes_data.get('Validation'),
                                    'imported_by': employe,
                                }

                                # Créer ou mettre à jour
                                if existing_solde:
                                    for key, value in solde_entry_data.items():
                                        setattr(existing_solde, key, value)
                                    existing_solde.save()
                                    soldes_updated += 1
                                else:
                                    SoldesReels.objects.create(**solde_entry_data)
                                    soldes_imported += 1

                            except Exception as e:
                                soldes_errors.append(f"Erreur SoldesReels {journal}/{date_m}/{rec}: {str(e)}")

                        if not selected_months_set:
                            for solde in existing_soldes_map.values():
                                if (solde.journal, solde.date_m, solde.rec) not in soldes_keys:
                                    solde.delete()

                    # Log de fin d'import SoldesReels
                    if skipped_rows > 0:
                        log_progress(f"[WARNING] {skipped_rows} ligne(s) ignorée(s) (données manquantes)")
                    log_progress(f"[OK] Import SoldesReels terminé: {soldes_imported} nouveaux, {soldes_updated} mis à jour")

                except pyodbc.Error as e:
                    # Table SoldesReels n'existe pas dans ce fichier Access
                    error_msg = str(e)
                    if "no such table" in error_msg.lower() or "table" in error_msg.lower():
                        log_progress(f"[INFO] Table SoldesReels absente dans {fichier_nom}")
                        soldes_errors.append(f"Table SoldesReels absente dans {fichier_nom}")
                    else:
                        log_progress(f"[WARNING] Erreur pyodbc SoldesReels: {error_msg}")
                        soldes_errors.append(f"Erreur Access SoldesReels: {error_msg}")
                except Exception as e:
                    log_progress(f"[ERROR] Erreur générale SoldesReels: {str(e)}")
                    soldes_errors.append(f"Erreur générale SoldesReels: {str(e)}")

                cursor.close()
                conn.close()

                total_imported += imported_count
                total_updated += updated_count
                total_soldes_imported += soldes_imported
                total_soldes_updated += soldes_updated
                all_soldes_errors.extend(soldes_errors)

            except Exception as e:
                error_msg = f'{fichier_nom}: Erreur - {str(e)}'
                log_progress(f"[ERROR] {error_msg}")
                all_errors.append(error_msg)

        # [OK] Log fin de l'import complet
        log_progress("[OK] Import terminé avec succès")

        return JsonResponse({
            'success': True,
            'imported': total_imported,
            'updated': total_updated,
            'errors': all_errors,
            'soldes_imported': total_soldes_imported,
            'soldes_updated': total_soldes_updated,
            'soldes_errors': all_soldes_errors,
            'session_id': session_id,  # [OK] Retourne le session_id pour polling frontend
        })

    except Exception as e:
        log_progress(f"[ERROR] ERREUR CRITIQUE: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'Erreur: {str(e)}',
            'session_id': session_id
        })


def _user_can_see_indemnities(user):
    """Les indemnites nomment des beneficiaires : reservees aux utilisateurs internes (pas aux comptes clients)."""
    return not bool(getattr(user, 'client', None)) or user.is_staff


def entries_list(request):
    """Liste des entrées DiameX avec filtres et pagination"""
    # Récupérer les filtres
    search = request.GET.get('search', '').strip()
    fichier_source = request.GET.get('fichier_source', '').strip()
    journal_code = request.GET.get('journal', '').strip()
    compte_code = request.GET.get('compte', '').strip()
    categorie_parente = request.GET.get('categorie', '').strip()
    fin_filter = request.GET.get('fin', '').strip()
    financement_conformite = request.GET.get('financement_conformite', '').strip()
    activ_filter = request.GET.get('activ', '').strip()
    mois_filter = request.GET.get('mois', '').strip()
    date_debut = request.GET.get('date_debut', '').strip()
    date_fin = request.GET.get('date_fin', '').strip()
    pers_filter = request.GET.get('pers', '').strip()  # Nouveau filtre PERS
    detail_filter = request.GET.get('detail', '').strip()  # Nouveau filtre DETAIL
    scan_filter = request.GET.get('scan', '').strip()  # Nouveau filtre SCAN
    compte_categorie_filter = request.GET.get('compte_categorie', '').strip()
    nif_isi_filter = request.GET.get('nif_isi', '').strip().upper()
    fournisseur_filter = request.GET.get('fournisseur', '').strip()
    ouvrage_filter = request.GET.get('ouvrage', '').strip()
    employe_surnom_filter = request.GET.get('employe_surnom', '').strip()
    mouvement_filter = request.GET.get('mouvement', '').strip()
    sort_amount = request.GET.get('sort_amount', '').strip()
    view_mode = request.GET.get('view_mode', 'liste').strip() or 'liste'
    if view_mode not in {'liste', 'grand_livre', 'grand_livre_cards'}:
        view_mode = 'liste'

    # Queryset de base - filtré par organisation + restriction lignes sensibles
    entries = _get_diamex_entries_scope_queryset(request)
    entries = _exclude_sensitive_diamex_lines_for_non_privileged(entries, request.user)
    entries = entries.select_related('journal', 'compte')

    # Appliquer les filtres
    if search:
        entries = entries.filter(
            Q(description__icontains=search) |
            Q(info__icontains=search) |
            Q(pers__icontains=search) |
            Q(detail__icontains=search)
        )

    if fichier_source:
        entries = entries.filter(fichier_source=fichier_source)

    if journal_code:
        entries = entries.filter(journal_code=journal_code)

    if compte_code:
        entries = entries.filter(compte_code=compte_code)

    # Nouveaux filtres PERS et DETAIL (case-insensitive)
    if pers_filter:
        if pers_filter == '(Vide)':
            entries = entries.filter(Q(pers__isnull=True) | Q(pers=''))
        else:
            entries = entries.filter(pers__iexact=pers_filter)

    if detail_filter:
        if detail_filter == '(Vide)':
            entries = entries.filter(Q(detail__isnull=True) | Q(detail=''))
        else:
            entries = entries.filter(detail__iexact=detail_filter)

    if fin_filter:
        # Filtrer par sous-catégorie Fin (toutes les transactions avec ce FIN, sauf 00PERS et 00BOOK)
        if fin_filter == '(Vide)':
            entries = entries.filter(fin__isnull=True).exclude(
                Q(compte_code__startswith='00PERS') | Q(compte_code__startswith='00BOOK')
            )
        else:
            normalized_fin_filter = _normalize_fin_bucket(fin_filter)
            matching_fin_values = [
                value for value in entries.values_list('fin', flat=True).distinct()
                if _normalize_fin_bucket(value) == normalized_fin_filter
            ]
            entries = entries.filter(fin__in=matching_fin_values).exclude(
                Q(compte_code__startswith='00PERS') | Q(compte_code__startswith='00BOOK')
            )

    if financement_conformite:
        # Comparaison insensible à la casse et aux espaces en début/fin.
        entries = entries.annotate(
            financement_diamex_normalise=Lower(Trim('fin')),
            financement_attendu_normalise=Lower(Trim('compte__financement')),
        )
        if financement_conformite == 'non_conforme':
            entries = entries.exclude(
                Q(compte__isnull=True) | Q(compte__financement='')
            ).filter(
                Q(financement_diamex_normalise__isnull=True) |
                ~Q(financement_diamex_normalise=F('financement_attendu_normalise'))
            )
        elif financement_conformite == 'conforme':
            entries = entries.exclude(
                Q(compte__isnull=True) | Q(compte__financement='')
            ).filter(
                financement_diamex_normalise=F('financement_attendu_normalise')
            )
        elif financement_conformite == 'non_controle':
            entries = entries.filter(
                Q(compte__isnull=True) | Q(compte__financement='')
            )

    if activ_filter:
        # Filtrer par sous-catégorie Activ (autres comptes)
        if activ_filter == '(Vide)':
            entries = entries.exclude(compte_code__startswith='00').filter(activ__isnull=True)
        else:
            entries = entries.exclude(compte_code__startswith='00').filter(activ=activ_filter)

    if mois_filter:
        # Filtrer par mois (YYYY-MM)
        year, month = mois_filter.split('-')
        entries = entries.filter(date_m__year=year, date_m__month=month)

    if date_debut:
        entries = entries.filter(date_m__gte=date_debut)

    if date_fin:
        entries = entries.filter(date_m__lte=date_fin)

    if mouvement_filter == 'entrees':
        entries = entries.filter(montant_in__gt=0)
    elif mouvement_filter == 'sorties':
        entries = entries.filter(montant_out__gt=0)

    if compte_categorie_filter == 'paiements_employes':
        entries = entries.filter(compte__employe_obligatoire=True)
    elif compte_categorie_filter == 'paiements_fournisseurs':
        entries = entries.filter(compte__fournisseur_obligatoire=True)
    elif compte_categorie_filter == 'avec_ouvrage':
        entries = entries.filter(
            compte__necessite_ouvrage=True
        ).exclude(
            Q(compte__employe_obligatoire=True) | Q(compte__fournisseur_obligatoire=True)
        )
    elif compte_categorie_filter == 'compte_tiers':
        entries = entries.filter(
            Q(compte_code__icontains='00PERS') | Q(journal_code__icontains='00PERS')
        )
    elif compte_categorie_filter == 'transfert':
        entries = entries.filter(
            Q(compte_code__icontains='00BOOK') |
            Q(journal_code__icontains='00BOOK') |
            Q(compte_code__icontains='00FND1') |
            Q(journal_code__icontains='00FND1') |
            Q(compte_code__icontains='00FND2') |
            Q(journal_code__icontains='00FND2') |
            Q(compte_code__icontains='00FND3') |
            Q(journal_code__icontains='00FND3')
        )
    elif compte_categorie_filter == 'sans_ouvrage':
        entries = entries.exclude(
            Q(compte_code__icontains='00BOOK') |
            Q(journal_code__icontains='00BOOK') |
            Q(compte_code__icontains='00FND1') |
            Q(journal_code__icontains='00FND1') |
            Q(compte_code__icontains='00FND2') |
            Q(journal_code__icontains='00FND2') |
            Q(compte_code__icontains='00FND3') |
            Q(journal_code__icontains='00FND3') |
            Q(compte_code__icontains='00PERS') |
            Q(journal_code__icontains='00PERS') |
            Q(compte__employe_obligatoire=True) |
            Q(compte__fournisseur_obligatoire=True) |
            Q(compte__necessite_ouvrage=True)
        ).exclude(
            compte_code__in=OUVRAGE_EXTRACTION_ACCOUNT_CODES
        )

    # [OK] Récupérer le cache de vérification AVANT le filtre par scan
    from .models import ScanVerificationCache
    derniere_verif = ScanVerificationCache.get_derniere_verification(fichier_source=fichier_source if fichier_source else None)

    if derniere_verif:
        scans_valides_ids = derniere_verif.scans_valides_ids
        liens_morts_ids = derniere_verif.liens_morts_ids
    else:
        scans_valides_ids = []
        liens_morts_ids = []

    # Filtre par scan
    if scan_filter:
        if scan_filter == 'avec_scan':
            entries = entries.filter(scan__isnull=False).exclude(scan='')
        elif scan_filter == 'scans_valides':
            # Utiliser le cache des IDs de scans valides
            if scans_valides_ids:
                entries = entries.filter(id__in=scans_valides_ids)
            else:
                entries = entries.none()  # Aucun résultat si pas de cache
        elif scan_filter == 'liens_morts':
            # Utiliser le cache des IDs de liens morts
            if liens_morts_ids:
                entries = entries.filter(id__in=liens_morts_ids)
            else:
                entries = entries.none()  # Aucun résultat si pas de cache
        elif scan_filter == 'sans_scan':
            # Exclure 00BOOK et 00PERS qui n'ont pas besoin de scan
            entries = entries.exclude(
                Q(compte_code__icontains='00BOOK') | Q(compte_code__icontains='00PERS')
            ).filter(Q(scan__isnull=True) | Q(scan=''))
        elif scan_filter == 'tous_sans_scan':
            # Tous sans scan (y compris 00BOOK et 00PERS)
            entries = entries.filter(Q(scan__isnull=True) | Q(scan=''))

    # Ordonner
    valid_sort_amounts = {
        'entree_desc': ('-montant_in', '-date_m', '-id'),
        'entree_asc': ('montant_in', '-date_m', '-id'),
        'sortie_desc': ('-montant_out', '-date_m', '-id'),
        'sortie_asc': ('montant_out', '-date_m', '-id'),
    }
    if sort_amount in valid_sort_amounts:
        entries = entries.order_by(*valid_sort_amounts[sort_amount])
    else:
        entries = entries.order_by('-date_m', '-id')

    # Vue grand livre : l'arbre n'affiche que des totaux agrégés (activ > financement >
    # catégorie) ; « Voir les comptes » ouvre les comptes d'une catégorie (gl_activ,
    # gl_fin, gl_cat) et « Ouvrir les écritures » le détail paginé d'un compte
    # (gl_detail=1). Aucun de ces niveaux ne charge tout le journal.
    gl_cat_param = request.GET.get('gl_cat', '').strip()
    gl_detail = (
        request.GET.get('gl_detail') == '1'
        and view_mode in {'grand_livre', 'grand_livre_cards'}
    )
    gl_comptes_mode = (
        view_mode in {'grand_livre', 'grand_livre_cards'}
        and not gl_detail
        and bool(gl_cat_param)
        and request.GET.get('format') != 'json'
    )
    if gl_detail or gl_comptes_mode:
        entries = _apply_grand_livre_narrow_filter(entries, request, avec_compte=gl_detail)

    gl_tree_mode = (
        view_mode in {'grand_livre', 'grand_livre_cards'}
        and not gl_detail
        and not gl_comptes_mode
        and request.GET.get('format') != 'json'
    )

    # Filtre par catégorie parente (en Python car méthode calculée)
    # IMPORTANT: Faire AVANT les stats pour que les stats soient filtrées aussi
    if categorie_parente:
        entries_list = list(entries)
        # Gestion compatibilité: si ancienne catégorie "Transfert", matcher les deux nouvelles
        if categorie_parente == 'Transfert':
            entries_filtered = [entry for entry in entries_list
                                if entry.get_categorie_parente() in ['Transferts 00BOOK', 'Transferts 00FND1']]
        elif categorie_parente == 'Paiements employés':
            entries_filtered = [entry for entry in entries_list
                                if entry.get_categorie_parente() in EMPLOYEE_PAYMENT_PARENT_CATEGORIES]
        else:
            entries_filtered = [entry for entry in entries_list if entry.get_categorie_parente() == categorie_parente]
        # Récupérer les IDs des entrées filtrées
        filtered_ids = [entry.id for entry in entries_filtered]
        # Filtrer le queryset original par ces IDs
        entries = BaseDiameX.objects.filter(id__in=filtered_ids).order_by('-date_m', '-id')

    if nif_isi_filter or fournisseur_filter or ouvrage_filter or employe_surnom_filter:
        fournisseurs_index = _build_fournisseurs_index()
        fournisseurs_index['__employes_index__'] = _build_employes_index()
        fournisseur_filter_normalized = _normalize_text(fournisseur_filter)
        ouvrage_filter_normalized = _normalize_text(ouvrage_filter)
        employe_surnom_filter_normalized = _normalize_text(employe_surnom_filter)
        entries_list = list(entries)
        filtered_ids = []
        from .resolution_memoire import resolution_memoire

        with resolution_memoire():
            for entry in entries_list:
                _populate_entry_extracted_fields(entry, fournisseurs_index)
                if nif_isi_filter:
                    extracted_nif_isi = (entry.extracted_nif_ou_isi or '').upper()
                    if nif_isi_filter == '(VIDE)':
                        if extracted_nif_isi:
                            continue
                    elif extracted_nif_isi != nif_isi_filter:
                        continue
                if fournisseur_filter_normalized:
                    extracted_supplier = _normalize_text(entry.extracted_nom_fournisseur)
                    if fournisseur_filter_normalized not in extracted_supplier:
                        continue
                if ouvrage_filter_normalized:
                    extracted_ouvrage = _normalize_text(entry.extracted_nom_ouvrage)
                    if ouvrage_filter_normalized not in extracted_ouvrage:
                        continue
                if employe_surnom_filter_normalized:
                    extracted_employe_surnom = _normalize_text(entry.extracted_employe_surnom)
                    if employe_surnom_filter_normalized not in extracted_employe_surnom:
                        continue
                filtered_ids.append(entry.id)
        entries = BaseDiameX.objects.filter(id__in=filtered_ids).order_by('-date_m', '-id')

    # Filtre issu d'un clic dans le panneau "Indemnites RBF par point d'eau" (point d'eau + annee). Le panneau garde
    # tous les points meme quand l'un d'eux est selectionne : il se calcule donc sur les ecritures d'avant ce filtre.
    rbf_point_filter = request.GET.get('rbf_point', '').strip()
    rbf_annee_filter = request.GET.get('rbf_annee', '').strip()
    rbf_panel_entries = entries
    rbf_selected = None
    if rbf_point_filter and rbf_annee_filter.isdigit():
        try:
            from apps.accounting.indemnites_points import line_ids_for_point
            from apps.core.views_ouvrage_interventions import _rbf_indemnity_lines_by_ouvrage
            selected_ids = line_ids_for_point(
                _rbf_indemnity_lines_by_ouvrage(), rbf_point_filter, int(rbf_annee_filter))
            entries = entries.filter(id__in=selected_ids)
            rbf_selected = (rbf_point_filter, int(rbf_annee_filter))
        except Exception:  # noqa: BLE001 - filtre secondaire : sans lui la liste reste complete
            import logging
            logging.getLogger(__name__).exception("Filtre par point d'eau (indemnites RBF) impossible")

    # Chemin rapide du grand livre : l'arbre (ou les comptes d'une catégorie) est rendu
    # à partir d'agrégats SQL, sans charger ni enrichir les écritures. Le détail d'un
    # compte (gl_detail=1) passe par la table paginée habituelle, plus bas.
    if (gl_tree_mode or gl_comptes_mode) and request.GET.get('format') != 'json':
        return _render_grand_livre_agrege(
            request, entries,
            view_mode=view_mode,
            gl_comptes_mode=gl_comptes_mode,
            derniere_verif=derniere_verif,
            scans_valides_ids=scans_valides_ids,
            liens_morts_ids=liens_morts_ids,
        )

    # Statistiques par type de compte (appliquées APRES filtre catégorie)
    # 00BOOK = transferts (IN - OUT doit ètre = 0)
    # 00FND1 sans "EDF" = aussi des transferts
    # 00PERS = avances tiers (IN - OUT)
    # Recettes/Dépenses = tous les autres comptes

    # Transferts 00BOOK
    book_entries = entries.filter(compte_code__startswith='00BOOK')

    # Transferts 00FND1 SANS "EDF" dans le libellé (description ou info)
    fnd1_transferts = entries.filter(compte_code__startswith='00FND1').exclude(
        Q(description__icontains='EDF') | Q(info__icontains='EDF')
    )

    # Tous les transferts (00BOOK + 00FND1 sans EDF)
    transferts_entries = book_entries | fnd1_transferts

    # Avances 00PERS
    pers_entries = entries.filter(compte_code__startswith='00PERS')

    # Recettes/Dépenses = SANS 00BOOK, SANS 00PERS, SANS 00FND1 (sans EDF)
    recettes_entries = entries.exclude(
        Q(compte_code__startswith='00BOOK') |
        Q(compte_code__startswith='00PERS')
    ).exclude(
        # Exclure 00FND1 SANS "EDF"
        Q(compte_code__startswith='00FND1') &
        ~(Q(description__icontains='EDF') | Q(info__icontains='EDF'))
    )

    recettes_totaux = recettes_entries.aggregate(
        recettes_in=Sum('montant_in'),
        recettes_out=Sum('montant_out')
    )
    recettes = recettes_totaux['recettes_in'] or 0
    depenses = recettes_totaux['recettes_out'] or 0
    solde = recettes - depenses

    # Transferts (00BOOK + 00FND1 sans EDF) - IN - OUT doit ètre = 0
    transferts_totaux = transferts_entries.aggregate(
        transferts_in=Sum('montant_in'),
        transferts_out=Sum('montant_out')
    )
    transferts_solde = (transferts_totaux['transferts_in'] or 0) - (transferts_totaux['transferts_out'] or 0)

    # Avances 00PERS - Calcul selon règles:
    # - 00PERS dans Cat (compte_code): OUT = tiers doivent (+), IN = org doit (-)
    # - 00PERS dans Journal (journal_code): OUT = org doit (-), IN = tiers doivent (+)
    # Lecture allégée (values_list + iterator) : le grand livre peut porter des dizaines
    # de milliers d'avances, inutile de matérialiser les objets complets.
    pers_solde = Decimal('0')
    for compte_code_pers, journal_code_pers, montant_in_pers, montant_out_pers in \
            pers_entries.values_list('compte_code', 'journal_code', 'montant_in', 'montant_out').iterator():
        montant_in = Decimal(str(montant_in_pers or 0))
        montant_out = Decimal(str(montant_out_pers or 0))

        # Vérifier si 00PERS est dans le compte (Cat) ou journal
        if compte_code_pers and '00PERS' in compte_code_pers:
            # Cat: OUT = tiers doivent (+), IN = org doit (-)
            pers_solde += montant_out - montant_in
        elif journal_code_pers and '00PERS' in journal_code_pers:
            # Journal: OUT = org doit (-), IN = tiers doivent (+)
            pers_solde += montant_in - montant_out

    pers_solde = float(pers_solde)

    # Vérification des pièces justificatives
    # Recettes et dépenses SANS scan (pièce justificative manquante)
    recettes_sans_scan = recettes_entries.filter(
        Q(scan__isnull=True) | Q(scan='')
    ).filter(
        Q(montant_in__gt=0) | Q(montant_out__gt=0)
    ).order_by('-date_m')

    # Compter les recettes et dépenses avec/sans scan
    recettes_avec_scan = recettes_entries.filter(montant_in__gt=0).exclude(
        Q(scan__isnull=True) | Q(scan='')
    ).count()
    recettes_total = recettes_entries.filter(montant_in__gt=0).count()

    depenses_avec_scan = recettes_entries.filter(montant_out__gt=0).exclude(
        Q(scan__isnull=True) | Q(scan='')
    ).count()
    depenses_total = recettes_entries.filter(montant_out__gt=0).count()

    # Pourcentage de couverture
    recettes_couverture = (recettes_avec_scan / recettes_total * 100) if recettes_total > 0 else 0
    depenses_couverture = (depenses_avec_scan / depenses_total * 100) if depenses_total > 0 else 0

    # Pagination pour la vue liste et le détail d'un groupe du grand livre.
    # Les appels AJAX JSON depuis le dashboard doivent recevoir tout le périmètre filtré,
    # pas seulement la première page récente. L'arbre du grand livre et le niveau
    # « comptes d'une catégorie » sont rendus plus haut : ils ne chargent aucune écriture
    # (c'est ce qui provoquait le 504).
    if request.GET.get('format') == 'json':
        entries_display = list(entries)
        paginator = Paginator(entries_display or [None], max(len(entries_display), 1))
        page_obj = entries_display
    else:
        paginator = Paginator(entries, 50)
        page_number = request.GET.get('page', 1)

        # Valider le numéro de page
        try:
            page_number = int(page_number)
            if page_number < 1:
                page_number = 1
        except (ValueError, TypeError):
            page_number = 1

        page_obj = paginator.get_page(page_number)

    # [OK] Reconstituer les chemins absolus des scans
    from apps.employees.models import EmployeBaseDiameX
    # Créer un dictionnaire fichier_source -> chemin_base
    organisation = getattr(
        getattr(getattr(request.user, 'employe', None), 'base', None),
        'organisation',
        None
    )
    bases_dict = {}
    bases_qs = EmployeBaseDiameX.objects.all()
    if organisation:
        bases_qs = bases_qs.filter(employe__base__organisation=organisation)
    for base in bases_qs:
        if base.base_diamex:
            bases_dict[base.base_diamex] = base.chemin_base_diamex or ''

    # Parcourir les entrées paginées et reconstituer les scans + déterminer le statut
    for entry in page_obj:
        # Déterminer si l'entrée a besoin d'un scan (hors 00BOOK et 00PERS)
        entry.a_besoin_scan = not (
            '00BOOK' in (entry.compte_code or '').upper() or
            '00PERS' in (entry.compte_code or '').upper()
        )
        scan_importe_name = getattr(getattr(entry, 'scan_importe', None), 'name', '') or ''
        entry.scan_importe_disponible = bool(scan_importe_name and default_storage.exists(scan_importe_name))

        # Reconstituer le chemin absolu si scan existe
        if entry.scan:
            scan_candidates = _resolve_entry_scan_candidates(entry)
            if scan_candidates:
                entry.scan_absolu = scan_candidates[0]
            else:
                entry.scan_absolu = entry.scan

            # Vérifier si le scan est valide (fichier existe) en utilisant le cache
            if scans_valides_ids and entry.id in scans_valides_ids:
                entry.scan_statut = 'valide'
            elif liens_morts_ids and entry.id in liens_morts_ids:
                entry.scan_statut = 'lien_mort'
            else:
                entry.scan_statut = 'non_verifie'  # Pas encore vérifié
        else:
            entry.scan_absolu = entry.scan or ''
            entry.scan_statut = None  # Pas de scan

    page_obj = _build_entries_enrichment(page_obj)
    if view_mode == 'liste' and request.GET.get('format') != 'json':
        # Pointage (748411 / 707401) et recoupement des indemnites (621102) sous le libelle : indicateurs
        # secondaires, la liste des ecritures doit rester utilisable s'ils echouent.
        try:
            from . import pointage_ecritures
            page_entries = list(page_obj)
            pointage_ecritures.attach_pointage(page_entries)
            if any(e.compte_code == pointage_ecritures.COMPTE_INDEMNITES for e in page_entries) \
                    and _user_can_see_indemnities(request.user):
                from apps.core.views_ouvrage_interventions import _rbf_indemnity_lines_by_ouvrage
                pointage_ecritures.attach_recoupement_indemnites(page_entries, _rbf_indemnity_lines_by_ouvrage())
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception("Pointage / recoupement des ecritures impossible")
    # L'arbre du grand livre et le niveau « comptes d'une catégorie » sont rendus plus
    # haut (chemin agrégé). Ici : vue liste, détail paginé d'un compte, ou export JSON.
    grand_livre_groups = []
    grand_livre_comptes = []
    grand_livre_back_url = _grand_livre_back_url(request, 'comptes') if gl_detail else ''

    # [OK] Statistiques des scans (sur toutes les entrées, pas seulement paginées)
    # Exclure les transferts 00BOOK et 00PERS qui n'ont pas besoin de scan
    entries_necessitant_scan = entries.exclude(
        Q(compte_code__icontains='00BOOK') | Q(compte_code__icontains='00PERS')
    )

    # Compter les opérations sans scan (hors 00BOOK et 00PERS)
    operations_sans_scan = entries_necessitant_scan.filter(
        Q(scan__isnull=True) | Q(scan='')
    ).filter(
        Q(montant_in__gt=0) | Q(montant_out__gt=0)
    ).count()

    # Les stats suivent le périmètre réellement affiché.
    operations_total = entries_necessitant_scan.filter(
        Q(montant_in__gt=0) | Q(montant_out__gt=0)
    ).count()

    if derniere_verif:
        imported_scan_ids = set(
            entries_necessitant_scan.exclude(
                Q(scan_importe__isnull=True) | Q(scan_importe='')
            ).filter(
                Q(montant_in__gt=0) | Q(montant_out__gt=0)
            ).values_list('id', flat=True)
        )
        valid_scan_ids = set(scans_valides_ids) | imported_scan_ids
        dead_scan_ids = set(liens_morts_ids) - imported_scan_ids

        scans_valides_count = _count_entries_with_ids(
            entries_necessitant_scan.filter(Q(montant_in__gt=0) | Q(montant_out__gt=0)),
            valid_scan_ids,
        )
        liens_morts_count = _count_entries_with_ids(
            entries_necessitant_scan.filter(Q(montant_in__gt=0) | Q(montant_out__gt=0)),
            dead_scan_ids,
        )
        date_derniere_verif = derniere_verif.date_verification
    else:
        scans_valides_count = 0
        liens_morts_count = 0
        date_derniere_verif = None

    # Pourcentages
    taux_sans_scan = int((operations_sans_scan / operations_total * 100) if operations_total > 0 else 0)
    taux_liens_morts = int((liens_morts_count / operations_total * 100) if operations_total > 0 else 0)
    taux_scans_valides = int((scans_valides_count / operations_total * 100) if operations_total > 0 else 0)

    # Listes pour filtres (avec suppression des doublons et valeurs vides)
    fichiers_sources_raw = entries.values_list('fichier_source', flat=True).distinct()
    fichiers_sources = sorted(set(f for f in fichiers_sources_raw if f))

    journaux_codes_raw = entries.values_list('journal_code', flat=True).distinct()
    journaux_codes = sorted(set(j for j in journaux_codes_raw if j))

    comptes_noms_par_code = {}
    for code, nom_compte in entries.values_list(
        'compte_code', 'compte__nom_compte'
    ).distinct():
        code = (code or '').strip()
        nom_compte = (nom_compte or '').strip()
        if not code:
            continue
        comptes_noms_par_code.setdefault(code, set())
        if nom_compte:
            comptes_noms_par_code[code].add(nom_compte)

    # Certains imports historiques n'ont pas encore leur clé étrangère `compte`
    # renseignée. Dans ce cas, retrouver le libellé dans le plan comptable de
    # l'organisation accessible à l'utilisateur.
    codes_sans_nom = [
        code for code, noms in comptes_noms_par_code.items() if not noms
    ]
    if codes_sans_nom:
        comptes_reference = Compte.objects.filter(compte__in=codes_sans_nom)
        organisation_id = _get_user_organisation_id(request.user)
        if organisation_id:
            comptes_reference = comptes_reference.filter(organisation_id=organisation_id)
        elif not getattr(request.user, 'is_superuser', False):
            comptes_reference = comptes_reference.none()

        for code, nom_compte in comptes_reference.values_list('compte', 'nom_compte'):
            code = (code or '').strip()
            nom_compte = (nom_compte or '').strip()
            if code in comptes_noms_par_code and nom_compte:
                comptes_noms_par_code[code].add(nom_compte)

    comptes_options = [
        {
            'code': code,
            'nom': ' / '.join(sorted(comptes_noms_par_code[code], key=str.casefold)),
        }
        for code in sorted(comptes_noms_par_code, key=str.casefold)
    ]

    # Nouveaux filtres pour colonnes PERS, DETAIL, FIN, ACTIVITY
    # PERS et DETAIL : normaliser par casse (regrouper majuscules/minuscules)
    pers_values_raw = entries.values_list('pers', flat=True).distinct()
    pers_dict = {}
    for p in pers_values_raw:
        if p:
            p_lower = p.lower()
            if p_lower not in pers_dict:
                pers_dict[p_lower] = p
    pers_values = sorted(pers_dict.values(), key=str.lower)

    detail_values_raw = entries.values_list('detail', flat=True).distinct()
    detail_dict = {}
    for d in detail_values_raw:
        if d:
            d_lower = d.lower()
            if d_lower not in detail_dict:
                detail_dict[d_lower] = d
    detail_values = sorted(detail_dict.values(), key=str.lower)

    fin_values_raw = entries.values_list('fin', flat=True).distinct()
    fin_values = sorted(set(f for f in fin_values_raw if f))

    activ_values_raw = entries.values_list('activ', flat=True).distinct()
    activ_values = sorted(set(a for a in activ_values_raw if a))
    # Dans l'arbre du grand livre, aucune écriture n'est chargée : les listes
    # d'autocomplétion viennent des référentiels (bien moins coûteux que d'enrichir
    # un échantillon de 500 écritures, chaque enrichissement interrogeant la base).
    autocomplete_values = (
        _build_grand_livre_autocomplete_values() if view_mode in {'grand_livre', 'grand_livre_cards'}
        else _build_entries_autocomplete_values(entries)
    )

    # Liste des catégories parentes disponibles
    categories_parentes = [
        'Transferts 00BOOK', 'Transferts 00FND1', 'EDF', 'Compte de tiers', 'Acquisition', 'Matériaux',
        'Fournitures', 'équipement', 'Carburant', 'Fonctionnement',
        'Entretien véhicules', "Main d'Å“uvre", 'Paiements employés', 'Impots',
        'Autres recettes', 'Vente eau au volume', 'Paiement extension', 'Vente eau au forfait',
        'Vente carte sociale', 'Autres'
    ]

    # Si format JSON demandé (pour AJAX depuis dashboard)
    if request.GET.get('format') == 'json':
        entries_data = []
        for entry in page_obj:
            entries_data.append({
                'id': entry.id,
                'date_m': entry.date_m.strftime('%Y-%m-%d') if entry.date_m else None,
                'date_rec': entry.date_rec.strftime('%d/%m/%Y') if entry.date_rec else '',
                'rec': entry.rec or '',
                'compte_code': entry.compte_code,
                'compte_nom': getattr(getattr(entry, 'compte', None), 'nom_compte', '') or '',
                'description': entry.description,
                'montant_in': float(entry.montant_in or 0),
                'montant_out': float(entry.montant_out or 0),
                'fin': entry.fin,
                'financement_attendu': entry.financement_attendu,
                'financement_conforme': entry.financement_conforme,
                'detail': entry.detail,
                'activ': entry.activ,
                'scan': entry.scan or '',
                'scan_absolu': getattr(entry, 'scan_absolu', '') or '',
                'scan_importe_disponible': bool(getattr(entry, 'scan_importe_disponible', False)),
                'scan_statut': getattr(entry, 'scan_statut', None),
                'a_besoin_scan': bool(getattr(entry, 'a_besoin_scan', False)),
                'compte_categorie': entry.compte_categorie_label,
                'nif_ou_isi': entry.extracted_nif_ou_isi,
                'nom_fournisseur': entry.extracted_nom_fournisseur,
                'libelle_extrait': entry.extracted_libelle,
                'nom_ouvrage': entry.extracted_nom_ouvrage,
                'employe_surnom': entry.extracted_employe_surnom,
                'quantite_extraite': entry.extracted_quantite,
                'prix_unitaire_extrait': entry.extracted_prix_unitaire,
                'vehicule_extrait': entry.extracted_vehicule,
                'vehicule_employe_extrait': entry.extracted_vehicule_employe,
            })
        return JsonResponse({'entries': entries_data})

    # Compteur d'indemnites RBF (621102) point d'eau par point d'eau : uniquement quand on filtre sur ce compte.
    rbf_points_context = {}
    rbf_plafond = None
    if compte_code == '621102' and view_mode == 'liste':
        try:
            from apps.accounting.indemnites_points import build_context as build_rbf_points_context
            from apps.core.views_ouvrage_interventions import (
                PLAFOND_INDEMNITE_PAR_POINT_EAU_PUBLIC,
                _rbf_indemnity_lines_by_ouvrage,
            )
            rbf_plafond = PLAFOND_INDEMNITE_PAR_POINT_EAU_PUBLIC
            rbf_points_context = build_rbf_points_context(
                list(rbf_panel_entries.values_list('id', flat=True)), page_obj,
                _rbf_indemnity_lines_by_ouvrage(), rbf_plafond)

            # Par defaut seuls les points au-dessus du plafond sont listes ; ?rbf_tous=1 affiche aussi les autres.
            all_rows = rbf_points_context.get('rows') or []
            rbf_show_all = request.GET.get('rbf_tous') == '1'
            base_params = request.GET.copy()
            for name in ('page', 'rbf_point', 'rbf_annee'):
                base_params.pop(name, None)
            toggle_params = request.GET.copy()
            toggle_params.pop('page', None)
            if rbf_show_all:
                toggle_params.pop('rbf_tous', None)
            else:
                toggle_params['rbf_tous'] = '1'
            visible_rows = all_rows if rbf_show_all else [row for row in all_rows if row['over']]
            for row in visible_rows:
                row_params = base_params.copy()
                row_params['rbf_point'] = row['key']
                row_params['rbf_annee'] = str(row['year'])
                row['url'] = '?' + row_params.urlencode()
                row['selected'] = rbf_selected == (row['key'], row['year'])
            rbf_points_context['rows'] = visible_rows
            rbf_points_context['hidden_count'] = len(all_rows) - len(visible_rows)
            rbf_points_context['show_all'] = rbf_show_all
            rbf_points_context['toggle_url'] = '?' + toggle_params.urlencode()
            rbf_points_context['reset_url'] = '?' + base_params.urlencode()
            selected_row = next(
                (row for row in all_rows if rbf_selected == (row['key'], row['year'])), None)
            rbf_points_context['selected'] = (
                {'label': selected_row['point_label'], 'ouvrage': selected_row['ouvrage'],
                 'year': selected_row['year'], 'over': selected_row['over']}
                if selected_row else None)
        except Exception:  # noqa: BLE001 - indicateur secondaire : ne jamais casser la liste des ecritures
            import logging
            logging.getLogger(__name__).exception("Compteur d'indemnites RBF par point d'eau impossible")
            rbf_points_context = {}

    return render(request, 'accounting/entries_list.html', {
        'rbf_points': rbf_points_context.get('rows') or [],
        'rbf_points_summary': rbf_points_context.get('summary'),
        'rbf_hidden_count': rbf_points_context.get('hidden_count', 0),
        'rbf_show_all': rbf_points_context.get('show_all', False),
        'rbf_toggle_url': rbf_points_context.get('toggle_url', ''),
        'rbf_reset_url': rbf_points_context.get('reset_url', ''),
        'rbf_selected': rbf_points_context.get('selected'),
        'rbf_plafond': rbf_plafond,
        'page_obj': page_obj,
        'entries': page_obj,
        'fichiers_sources': fichiers_sources,
        'journaux_codes': journaux_codes,
        'comptes_options': comptes_options,
        'categories_parentes': categories_parentes,
        'pers_values': pers_values,  # Nouveau
        'detail_values': detail_values,  # Nouveau
        'fin_values': fin_values,  # Nouveau
        'activ_values': activ_values,  # Nouveau
        'recettes': recettes,
        'depenses': depenses,
        'solde': solde,
        'total_count': (
            entries.count() if view_mode in {'grand_livre', 'grand_livre_cards'}
            else paginator.count
        ),
        'transferts_solde': transferts_solde,
        'transferts_count': transferts_entries.count(),
        'pers_solde': pers_solde,
        'pers_count': pers_entries.count(),
        # Statistiques pièces justificatives (anciennes - à garder pour compatibilité)
        'recettes_sans_scan': recettes_sans_scan[:100],  # Limiter à 100 pour l'affichage
        'recettes_sans_scan_count': recettes_sans_scan.count(),
        'recettes_avec_scan': recettes_avec_scan,
        'recettes_total': recettes_total,
        'recettes_couverture': round(recettes_couverture, 1),
        # Nouvelles statistiques des scans (hors 00BOOK)
        'operations_sans_scan': operations_sans_scan,
        'liens_morts_count': liens_morts_count,
        'scans_valides_count': scans_valides_count,
        'operations_total': operations_total,
        'taux_sans_scan': taux_sans_scan,
        'taux_liens_morts': taux_liens_morts,
        'taux_scans_valides': taux_scans_valides,
        'date_derniere_verif': date_derniere_verif,
        'depenses_avec_scan': depenses_avec_scan,
        'depenses_total': depenses_total,
        'depenses_couverture': round(depenses_couverture, 1),
        'compte_category_choices': ENTRY_COMPTE_CATEGORY_CHOICES,
        'mouvement_filter': mouvement_filter,
        'sort_amount': sort_amount,
        'view_mode': view_mode,
        'grand_livre_groups': grand_livre_groups,
        'grand_livre_comptes': grand_livre_comptes,
        'gl_detail': gl_detail,
        'gl_comptes_mode': gl_comptes_mode,
        'gl_back_url': grand_livre_back_url,
        'gl_narrow_label': (
            _grand_livre_narrow_label(request, avec_compte=gl_detail)
            if (gl_detail or gl_comptes_mode) else ''
        ),
        **autocomplete_values,
    })

    # Si format JSON demandé (pour AJAX)
    if request.GET.get('format') == 'json':
        entries_data = []
        for entry in page_obj:
            entries_data.append({
                'id': entry.id,
                'date_m': entry.date_rec.strftime('%Y-%m-%d') if entry.date_rec else None,  # Afficher DateRec au lieu de DateM
                'compte_code': entry.compte_code,
                'description': entry.description,
                'montant_in': float(entry.montant_in or 0),
                'montant_out': float(entry.montant_out or 0),
                'fin': entry.fin,
                'detail': entry.detail,
                'activ': entry.activ,
            })
        return JsonResponse({'entries': entries_data})

    return context


def detail_avances_pers(request):
    """Page de détail des avances 00PERS avec répartition par tiers"""
    # Récupérer les filtres
    fichier_source = request.GET.get('fichier_source', '').strip()
    mois_filter = request.GET.get('mois', '').strip()

    # Récupérer l'employé connecté
    employe = getattr(request.user, 'employe', None) if hasattr(request.user, 'employe') else None

    # Charger tous les fournisseurs pour mapping IDxls -> nom
    from apps.billing.models import Fournisseur
    fournisseurs_dict = {
        str(f.idxls): f.nom_fournisseur
        for f in Fournisseur.objects.filter(idxls__isnull=False)
    }

    # Filtrer les entrées 00PERS
    if employe:
        pers_entries = BaseDiameX.objects.select_related('journal', 'compte').filter(
            imported_by=employe
        ).filter(
            Q(compte_code__startswith='00PERS') | Q(journal_code__startswith='00PERS')
        )
    else:
        pers_entries = BaseDiameX.objects.select_related('journal', 'compte').filter(
            Q(compte_code__startswith='00PERS') | Q(journal_code__startswith='00PERS')
        )

    # Appliquer filtres
    if fichier_source:
        pers_entries = pers_entries.filter(fichier_source=fichier_source)

    if mois_filter:
        year, month = mois_filter.split('-')
        pers_entries = pers_entries.filter(date_m__year=year, date_m__month=month)

    # Calculer solde par tiers avec notion "org doit" et "tiers doit"
    # Normaliser les noms de tiers en minuscules pour regrouper (case-insensitive)
    from collections import defaultdict
    soldes_par_tiers = defaultdict(lambda: {
        'org_doit': Decimal('0'),      # Ce que l'organisation doit au tiers
        'tiers_doit': Decimal('0'),    # Ce que le tiers doit à l'organisation
        'solde': Decimal('0'),
        'type': 'inconnu',
        'nom_original': ''  # Garder un nom d'affichage
    })

    for entry in pers_entries:
        # Ignorer les lignes avec Match non vide (déjà pointées/équilibrées)
        if entry.match:
            continue

        tiers_original = entry.pers or 'Non spécifié'
        tiers = tiers_original.lower()  # Normaliser en minuscules
        montant_in = Decimal(str(entry.montant_in or 0))
        montant_out = Decimal(str(entry.montant_out or 0))

        # Garder le premier nom rencontré pour l'affichage
        if not soldes_par_tiers[tiers]['nom_original']:
            # Si c'est un numéro, essayer de récupérer le nom du fournisseur
            nom_affichage = tiers_original
            if tiers_original != 'Non spécifié':
                try:
                    int(tiers_original)
                    # C'est un numéro, chercher le fournisseur
                    nom_fournisseur = fournisseurs_dict.get(tiers_original)
                    if nom_fournisseur:
                        nom_affichage = f"{nom_fournisseur} ({tiers_original})"
                    else:
                        nom_affichage = f"Fournisseur #{tiers_original}"
                except (ValueError, TypeError):
                    # C'est du texte, garder tel quel
                    pass
            soldes_par_tiers[tiers]['nom_original'] = nom_affichage

        # Déterminer le type de tiers (numérique = fournisseur, texte = employé)
        if tiers_original != 'Non spécifié':
            try:
                int(tiers_original)
                soldes_par_tiers[tiers]['type'] = 'fournisseur'
            except (ValueError, TypeError):
                soldes_par_tiers[tiers]['type'] = 'employe'

        # Appliquer les règles de calcul
        if entry.compte_code and '00PERS' in entry.compte_code:
            # Cat: OUT = tiers doivent (+), IN = org doit (-)
            soldes_par_tiers[tiers]['tiers_doit'] += montant_out  # OUT = tiers doit
            soldes_par_tiers[tiers]['org_doit'] += montant_in     # IN = org doit
            soldes_par_tiers[tiers]['solde'] += montant_out - montant_in
        elif entry.journal_code and '00PERS' in entry.journal_code:
            # Journal: OUT = org doit (-), IN = tiers doivent (+)
            soldes_par_tiers[tiers]['tiers_doit'] += montant_in   # IN = tiers doit
            soldes_par_tiers[tiers]['org_doit'] += montant_out    # OUT = org doit
            soldes_par_tiers[tiers]['solde'] += montant_in - montant_out

    # Convertir en liste triée et filtrer les soldes équilibrés
    soldes_tiers_list = []
    for tiers_key, data in soldes_par_tiers.items():
        solde_float = float(data['solde'])
        # Filtrer les comptes équilibrés (solde = 0 avec tolérance de 1 centime)
        if abs(solde_float) >= 0.01:
            soldes_tiers_list.append({
                'tiers': data['nom_original'],  # Nom formaté pour l'affichage
                'tiers_id': tiers_key,  # Clé normalisée (lowercase) pour le filtrage JS
                'type': data['type'],
                'org_doit': float(data['org_doit']),       # Ce que l'org doit
                'tiers_doit': float(data['tiers_doit']),   # Ce que le tiers doit
                'solde': solde_float,
            })

    # Trier par solde décroissant (les tiers qui doivent le plus en premier)
    soldes_tiers_list.sort(key=lambda x: x['solde'], reverse=True)

    # Calculer totaux
    solde_total = sum(t['solde'] for t in soldes_tiers_list)
    total_org_doit = sum(t['org_doit'] for t in soldes_tiers_list)
    total_tiers_doit = sum(t['tiers_doit'] for t in soldes_tiers_list)

    # POINTAGE DES COMPTES DE TIERS (Match, Prog)
    # Grouper par couple (Match, Prog) et calculer le solde
    pointages = defaultdict(lambda: {
        'match': None,
        'prog': None,
        'solde': Decimal('0'),
        'nb_lignes': 0,
        'lignes': [],
        'equilibre': False,
    })

    lignes_non_pointees = []

    for entry in pers_entries:
        match_val = entry.match
        prog_val = entry.prog or 'Vide'

        # Calculer l'impact selon les règles
        if entry.compte_code and '00PERS' in entry.compte_code:
            # Cat: OUT = tiers doivent (+), IN = org doit (-)
            impact = Decimal(str(entry.montant_out or 0)) - Decimal(str(entry.montant_in or 0))
        elif entry.journal_code and '00PERS' in entry.journal_code:
            # Journal: OUT = org doit (-), IN = tiers doivent (+)
            impact = Decimal(str(entry.montant_in or 0)) - Decimal(str(entry.montant_out or 0))
        else:
            impact = Decimal('0')

        # Si Match est vide, c'est une ligne non pointée
        if match_val is None or match_val == '':
            lignes_non_pointees.append({
                'entry': entry,
                'impact': float(impact),
                'tiers': entry.pers or 'Non spécifié',
                'prog': prog_val,
            })
        else:
            # Pointage par couple (Match, Prog)
            key = (match_val, prog_val)
            pointages[key]['match'] = match_val
            pointages[key]['prog'] = prog_val
            pointages[key]['solde'] += impact
            pointages[key]['nb_lignes'] += 1
            pointages[key]['lignes'].append(entry)

    # Convertir les pointages en liste et vérifier l'équilibre
    # Compter les équilibrés et déséquilibrés avant filtrage
    nb_pointages_equilibres_total = 0
    nb_pointages_desequilibres_total = 0
    pointages_list = []

    for key, data in pointages.items():
        data['solde'] = float(data['solde'])
        data['equilibre'] = abs(data['solde']) < 0.01  # Tolérance de 1 centime

        if data['equilibre']:
            nb_pointages_equilibres_total += 1
        else:
            nb_pointages_desequilibres_total += 1
            # Ne garder que les pointages déséquilibrés dans la liste affichée
            pointages_list.append(data)

    # Trier par match
    pointages_list.sort(key=lambda x: x['match'] or 0)

    # Stats pointage (afficher le total mème si on cache les équilibrés)
    nb_pointages_total = nb_pointages_equilibres_total + nb_pointages_desequilibres_total
    nb_pointages_equilibres = nb_pointages_equilibres_total
    nb_pointages_desequilibres = nb_pointages_desequilibres_total
    nb_lignes_non_pointees = len(lignes_non_pointees)

    # Ordonner les transactions par date et calculer l'impact sur le solde
    pers_entries_ordered = pers_entries.order_by('-date_m', '-id')

    # Ajouter l'impact du solde pour chaque transaction
    transactions_with_impact = []
    for entry in pers_entries_ordered:
        entry_dict = {
            'entry': entry,
            'impact_solde': 0,
            'impact_positif': False,
        }

        # Calculer l'impact selon les règles
        if entry.compte_code and '00PERS' in entry.compte_code:
            # Cat: OUT = tiers doivent (+), IN = org doit (-)
            entry_dict['impact_solde'] = (entry.montant_out or 0) - (entry.montant_in or 0)
        elif entry.journal_code and '00PERS' in entry.journal_code:
            # Journal: OUT = org doit (-), IN = tiers doivent (+)
            entry_dict['impact_solde'] = (entry.montant_in or 0) - (entry.montant_out or 0)

        entry_dict['impact_positif'] = entry_dict['impact_solde'] > 0
        transactions_with_impact.append(entry_dict)

    # Sérialiser les transactions pour JavaScript
    import json
    transactions_json = []
    for trans in transactions_with_impact:
        entry = trans['entry']
        transactions_json.append({
            'entry': {
                'id': entry.id,  # Ajout de l'ID pour le bouton Modifier
                'date_m': entry.date_m.isoformat() if entry.date_m else None,
                'journal_code': entry.journal_code,
                'compte_code': entry.compte_code,
                'description': entry.description,
                'info': entry.info,  # Ajout du champ info
                'pers': entry.pers,
                'detail': entry.detail,  # Ajout du champ detail
                'montant_in': float(entry.montant_in or 0),
                'montant_out': float(entry.montant_out or 0),
                'match': entry.match,
                'prog': entry.prog,
                'fichier_source': entry.fichier_source,
            },
            'impact_solde': float(trans['impact_solde']),
            'impact_positif': trans['impact_positif'],
        })

    # Récupérer les valeurs distinctes pour les dropdowns du modal d'édition
    pers_values_raw = BaseDiameX.objects.values_list('pers', flat=True).distinct()
    pers_dict = {}
    for p in pers_values_raw:
        if p:
            p_lower = p.lower()
            if p_lower not in pers_dict:
                # Si c'est un numéro, essayer de récupérer le nom du fournisseur
                try:
                    int(p)
                    nom_fournisseur = fournisseurs_dict.get(p)
                    if nom_fournisseur:
                        pers_dict[p_lower] = f"{nom_fournisseur} ({p})"
                    else:
                        pers_dict[p_lower] = f"Fournisseur #{p}"
                except (ValueError, TypeError):
                    pers_dict[p_lower] = p
    pers_values = sorted(pers_dict.values(), key=str.lower)

    detail_values_raw = BaseDiameX.objects.values_list('detail', flat=True).distinct()
    detail_dict = {}
    for d in detail_values_raw:
        if d:
            d_lower = d.lower()
            if d_lower not in detail_dict:
                detail_dict[d_lower] = d
    detail_values = sorted(detail_dict.values(), key=str.lower)

    return render(request, 'accounting/detail_avances_pers.html', {
        'soldes_tiers': soldes_tiers_list,
        'transactions': transactions_with_impact,
        'transactions_json': json.dumps(transactions_json),
        'solde_total': solde_total,
        'total_org_doit': total_org_doit,
        'total_tiers_doit': total_tiers_doit,
        'total_count': pers_entries.count(),
        'fichier_source': fichier_source,
        'mois_filter': mois_filter,
        # Pointage des comptes de tiers
        'pointages': pointages_list,
        'nb_pointages_total': nb_pointages_total,
        'nb_pointages_equilibres': nb_pointages_equilibres,
        'nb_pointages_desequilibres': nb_pointages_desequilibres,
        'lignes_non_pointees': lignes_non_pointees,
        'nb_lignes_non_pointees': nb_lignes_non_pointees,
        # Valeurs pour les dropdowns du modal d'édition
        'pers_values': pers_values,
        'detail_values': detail_values,
    })


def _get_pointage_tiers_base_queryset(user):
    organisation_id = None
    try:
        organisation_id = user.employe.base.organisation_id
    except Exception:
        organisation_id = None

    bases = Base.objects.select_related('organisation').exclude(
        prog_diamex__isnull=True
    ).exclude(
        prog_diamex=''
    )
    if organisation_id:
        return bases.filter(organisation_id=organisation_id).order_by('nom_base')
    if getattr(user, 'is_superuser', False):
        return bases.order_by('nom_base')
    return bases.none()


def _get_tiers_pointage_impact(entry):
    if entry.compte_code and '00PERS' in entry.compte_code:
        return Decimal(str(entry.montant_out or 0)) - Decimal(str(entry.montant_in or 0))
    if entry.journal_code and '00PERS' in entry.journal_code:
        return Decimal(str(entry.montant_in or 0)) - Decimal(str(entry.montant_out or 0))
    return Decimal('0')


def _get_tiers_display_label(raw_tiers, fournisseurs_dict=None):
    fournisseurs_dict = fournisseurs_dict or {}
    raw_tiers = (raw_tiers or '').strip()
    if not raw_tiers:
        return 'Non specifie'
    try:
        int(raw_tiers)
        fournisseur_nom = fournisseurs_dict.get(raw_tiers)
        if fournisseur_nom:
            return f"{fournisseur_nom} ({raw_tiers})"
        return f"Fournisseur #{raw_tiers}"
    except (TypeError, ValueError):
        return raw_tiers


@login_required
def workflow_pointage_tiers(request):
    base_id = (request.GET.get('base_id') or '').strip()
    tiers_key = (request.GET.get('tiers') or '').strip()

    from apps.billing.models import Fournisseur

    fournisseurs_dict = {
        str(f.idxls): f.nom_fournisseur
        for f in Fournisseur.objects.filter(idxls__isnull=False)
    }

    bases = list(_get_pointage_tiers_base_queryset(request.user))
    selected_base = next((base for base in bases if str(base.id) == base_id), None)

    entries_qs = _get_diamex_entries_scope_queryset(request).filter(
        Q(compte_code__startswith='00PERS') | Q(journal_code__startswith='00PERS')
    )
    if selected_base and selected_base.prog_diamex:
        entries_qs = entries_qs.filter(prog=selected_base.prog_diamex)

    scoped_entries = list(entries_qs.order_by('-date_m', '-id'))

    tiers_options_map = {}
    for entry in scoped_entries:
        normalized_tiers = _normalize_text(entry.pers or 'Non specifie')
        if normalized_tiers and normalized_tiers not in tiers_options_map:
            tiers_options_map[normalized_tiers] = {
                'value': normalized_tiers,
                'label': _get_tiers_display_label(entry.pers or 'Non specifie', fournisseurs_dict),
            }
    tiers_options = sorted(tiers_options_map.values(), key=lambda item: item['label'].lower())

    selected_entries = []
    if tiers_key:
        selected_entries = [
            entry for entry in scoped_entries
            if _normalize_text(entry.pers or 'Non specifie') == tiers_key
        ]

    non_pointes = []
    pointages_map = defaultdict(lambda: {
        'match': None,
        'prog': '',
        'solde': Decimal('0'),
        'lignes': [],
        'nb_lignes': 0,
        'tiers_labels': set(),
    })

    for entry in selected_entries:
        impact = _get_tiers_pointage_impact(entry)
        tiers_label = _get_tiers_display_label(entry.pers or 'Non specifie', fournisseurs_dict)
        prog_value = (entry.prog or '').strip()
        entry_payload = {
            'id': entry.id,
            'id_access': entry.id_access,
            'date_m': entry.date_m,
            'journal_code': entry.journal_code or '',
            'compte_code': entry.compte_code or '',
            'description': entry.description or '',
            'montant_in': float(entry.montant_in or 0),
            'montant_out': float(entry.montant_out or 0),
            'impact': float(impact),
            'impact_display': impact,
            'prog': prog_value,
            'tiers': tiers_label,
            'match': entry.match,
        }

        if entry.match in (None, ''):
            non_pointes.append(entry_payload)
            continue

        group_key = (int(entry.match), prog_value)
        pointages_map[group_key]['match'] = int(entry.match)
        pointages_map[group_key]['prog'] = prog_value
        pointages_map[group_key]['solde'] += impact
        pointages_map[group_key]['nb_lignes'] += 1
        pointages_map[group_key]['lignes'].append(entry_payload)
        pointages_map[group_key]['tiers_labels'].add(tiers_label)

    pointages = []
    for _, group in pointages_map.items():
        group['equilibre'] = abs(group['solde']) < Decimal('0.01')
        group['tiers_labels'] = sorted(group['tiers_labels'])
        pointages.append(group)

    pointages.sort(key=lambda item: ((item['prog'] or ''), item['match'] or 0))

    selected_tiers_label = ''
    if tiers_key and tiers_options_map.get(tiers_key):
        selected_tiers_label = tiers_options_map[tiers_key]['label']

    workflow_app_mode = getattr(request, 'urlconf', None) == 'hydria.urls_saisie'
    home_url = '/accueil/' if workflow_app_mode else reverse('core:home_launcher')
    main_entries_url = '/comptabilite/entries/'
    main_tiers_url = '/comptabilite/entries/avances-pers/'
    pointage_validate_url = '/pointage-tiers/api/valider/' if workflow_app_mode else '/comptabilite/workflow/pointage-tiers/api/valider/'
    pointage_cancel_url = '/pointage-tiers/api/annuler/' if workflow_app_mode else '/comptabilite/workflow/pointage-tiers/api/annuler/'

    context = {
        'title': 'Workflow pointage comptes de tiers',
        'bases': bases,
        'selected_base_id': base_id,
        'selected_tiers_key': tiers_key,
        'selected_tiers_label': selected_tiers_label,
        'tiers_options': tiers_options,
        'non_pointes': non_pointes,
        'pointages': pointages,
        'selected_entries_count': len(selected_entries),
        'main_entries_url': main_entries_url,
        'main_tiers_url': main_tiers_url,
        'home_url': home_url,
        'pointage_validate_url': pointage_validate_url,
        'pointage_cancel_url': pointage_cancel_url,
    }
    return render(request, 'accounting/workflow_pointage_tiers.html', context)


@login_required
@require_http_methods(["POST"])
def api_workflow_pointage_tiers(request):
    try:
        payload = json.loads(request.body or '{}')
        entry_ids = payload.get('entry_ids') or []
        if not isinstance(entry_ids, list) or not entry_ids:
            return JsonResponse({'success': False, 'error': 'Aucune ligne selectionnee'}, status=400)

        entries = list(
            _get_diamex_entries_scope_queryset(request)
            .filter(id__in=entry_ids)
            .filter(Q(compte_code__startswith='00PERS') | Q(journal_code__startswith='00PERS'))
            .order_by('id')
        )

        if len(entries) != len(entry_ids):
            return JsonResponse({'success': False, 'error': 'Certaines lignes sont introuvables ou hors scope'}, status=404)

        tiers_values = {_normalize_text(entry.pers or 'Non specifie') for entry in entries}
        if len(tiers_values) != 1:
            return JsonResponse({'success': False, 'error': 'Le pointage doit concerner un seul tiers a la fois'}, status=400)

        prog_values = {(entry.prog or '').strip() for entry in entries}
        if len(prog_values) != 1:
            return JsonResponse({'success': False, 'error': 'Toutes les lignes selectionnees doivent appartenir a la meme base'}, status=400)

        if any(entry.match not in (None, '') for entry in entries):
            return JsonResponse({'success': False, 'error': 'Une ou plusieurs lignes sont deja pointees'}, status=400)

        solde = sum((_get_tiers_pointage_impact(entry) for entry in entries), Decimal('0'))
        if abs(solde) >= Decimal('0.01'):
            return JsonResponse({
                'success': False,
                'error': f'Solde non nul: {solde:.2f}. Le pointage exige un solde de 0.'
            }, status=400)

        match_value = entries[0].id_access or entries[0].id
        with transaction.atomic():
            for entry in entries:
                entry.match = int(match_value)
            BaseDiameX.objects.bulk_update(entries, ['match'])

        return JsonResponse({
            'success': True,
            'match': int(match_value),
            'message': f'Pointage cree sur {len(entries)} ligne(s)'
        })
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
@require_http_methods(["POST"])
def api_workflow_depointage_tiers(request):
    try:
        payload = json.loads(request.body or '{}')
        match_value = payload.get('match')
        prog_value = (payload.get('prog') or '').strip()

        if match_value in (None, ''):
            return JsonResponse({'success': False, 'error': 'Match manquant'}, status=400)

        scope_qs = _get_diamex_entries_scope_queryset(request).filter(
            Q(compte_code__startswith='00PERS') | Q(journal_code__startswith='00PERS'),
            match=int(match_value),
        )
        if prog_value:
            scope_qs = scope_qs.filter(prog=prog_value)
        else:
            scope_qs = scope_qs.filter(Q(prog__isnull=True) | Q(prog=''))

        entries = list(scope_qs)
        if not entries:
            return JsonResponse({'success': False, 'error': 'Pointage introuvable ou hors scope'}, status=404)

        with transaction.atomic():
            for entry in entries:
                entry.match = None
            BaseDiameX.objects.bulk_update(entries, ['match'])

        return JsonResponse({
            'success': True,
            'message': f'Pointage {match_value} annule sur {len(entries)} ligne(s)'
        })
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


def _build_soldes_workflow_data(request, journal_filter=''):
    soldes_reels_qs = SoldesReels.objects.exclude(
        journal__in=['00PERS', '00SPLITBOOK-MGA']
    ).exclude(
        date_m__isnull=True
    )
    entries_qs = _get_diamex_entries_scope_queryset(request).exclude(
        journal_code__in=['00PERS', '00SPLITBOOK-MGA']
    ).exclude(
        date_m__isnull=True
    )

    if not request.user.is_superuser:
        allowed_fichiers = list(
            entries_qs.exclude(fichier_source__isnull=True)
            .exclude(fichier_source='')
            .values_list('fichier_source', flat=True)
            .distinct()
        )
        soldes_reels_qs = soldes_reels_qs.filter(fichier_source__in=allowed_fichiers)

    if journal_filter:
        soldes_reels_qs = soldes_reels_qs.filter(journal=journal_filter)
        entries_qs = entries_qs.filter(journal_code=journal_filter)

    journaux_options = sorted(
        set(entries_qs.values_list('journal_code', flat=True)).union(
            set(soldes_reels_qs.values_list('journal', flat=True))
        )
    )
    journaux_options = [j for j in journaux_options if j]

    soldes_reels_dict = {}
    description_par_cle = {}
    scan_par_cle = {}
    solde_id_par_cle = {}
    validation_par_cle = {}
    fichiers_par_cle = {}

    for solde in soldes_reels_qs.values('journal', 'date_m', 'fichier_source').annotate(total=Sum('ccy')).order_by('date_m', 'journal'):
        key = (solde['journal'], solde['date_m'], solde['fichier_source'] or '')
        soldes_reels_dict[key] = Decimal(str(solde['total'] or 0))
        fichiers_par_cle[key] = solde['fichier_source'] or ''
        dernier_solde = soldes_reels_qs.filter(
            journal=solde['journal'],
            date_m=solde['date_m'],
            fichier_source=solde['fichier_source']
        ).order_by('-date_rec', '-id').first()
        if dernier_solde:
            description_par_cle[key] = dernier_solde.description or ''
            scan_par_cle[key] = dernier_solde.scan or ''
            solde_id_par_cle[key] = dernier_solde.id
            validation_par_cle[key] = dernier_solde.validation or ''

    mouvements_groupes = entries_qs.values('journal_code', 'fichier_source', 'date_m').annotate(
        total_in=Sum('montant_in'),
        total_out=Sum('montant_out')
    ).order_by('journal_code', 'fichier_source', 'date_m')

    mouvements_par_journal = defaultdict(dict)
    for row in mouvements_groupes:
        if not row['date_m']:
            continue
        key = (row['journal_code'], row['fichier_source'] or '')
        mouvements_par_journal[key][row['date_m']] = Decimal(str(row['total_in'] or 0)) - Decimal(str(row['total_out'] or 0))

    from dateutil.relativedelta import relativedelta

    soldes_calcules_dict = {}
    all_journal_files = set(mouvements_par_journal.keys()).union({
        (row['journal'], row['fichier_source'] or '')
        for row in soldes_reels_qs.values('journal', 'fichier_source').distinct()
    })

    for journal_code, fichier_source in all_journal_files:
        mouvements = mouvements_par_journal.get((journal_code, fichier_source), {})
        dates_soldes = list(
            soldes_reels_qs.filter(
                journal=journal_code,
                fichier_source=fichier_source
            ).exclude(
                date_m__isnull=True
            ).values_list('date_m', flat=True).distinct()
        )
        toutes_dates = set(mouvements.keys()) | set(dates_soldes)
        if not toutes_dates:
            continue

        dates_triees = sorted(toutes_dates)
        date_courante = dates_triees[0]
        date_fin = dates_triees[-1]
        solde_cumule = Decimal('0')

        while date_courante <= date_fin:
            solde_cumule += mouvements.get(date_courante, Decimal('0'))
            key = (journal_code, date_courante, fichier_source)
            soldes_calcules_dict[key] = solde_cumule
            fichiers_par_cle.setdefault(key, fichier_source)
            date_courante = date_courante.replace(day=1) + relativedelta(months=1)

    rows = []
    all_keys = set(soldes_reels_dict.keys()) | set(soldes_calcules_dict.keys())
    for journal, date_m, fichier_source in sorted(all_keys, key=lambda item: ((item[0] or ''), item[1] or timezone.now().date(), item[2] or '')):
        solde_calcule = Decimal(str(soldes_calcules_dict.get((journal, date_m, fichier_source), Decimal('0'))))
        solde_reel = Decimal(str(soldes_reels_dict.get((journal, date_m, fichier_source), Decimal('0'))))
        ecart = solde_reel - solde_calcule
        rows.append({
            'journal': journal,
            'date_m': date_m,
            'fichier_source': fichier_source,
            'solde_calcule': solde_calcule,
            'solde_reel': solde_reel,
            'ecart': ecart,
            'est_rapproche': abs(ecart) < Decimal('0.01'),
            'description': description_par_cle.get((journal, date_m, fichier_source), ''),
            'scan': scan_par_cle.get((journal, date_m, fichier_source), ''),
            'solde_id': solde_id_par_cle.get((journal, date_m, fichier_source)),
            'validation': validation_par_cle.get((journal, date_m, fichier_source), ''),
        })

    return {
        'journaux_options': journaux_options,
        'rows': rows,
    }


@login_required
def workflow_soldes_reels(request):
    journal_filter = (request.GET.get('journal') or '').strip()
    workflow_data = _build_soldes_workflow_data(request, journal_filter=journal_filter)
    workflow_app_mode = getattr(request, 'urlconf', None) == 'hydria.urls_saisie'

    context = {
        'title': 'Workflow soldes reels',
        'journal_filter': journal_filter,
        'journaux_options': workflow_data['journaux_options'],
        'rows': workflow_data['rows'],
        'home_url': '/accueil/' if workflow_app_mode else reverse('core:home_launcher'),
        'main_comparaison_url': '/comptabilite/comparaison-soldes/',
        'main_soldes_url': '/comptabilite/soldes-reels/',
        'save_url': '/soldes-reels-workflow/api/save/' if workflow_app_mode else '/comptabilite/soldes-reels-workflow/api/save/',
        'details_url': '/comptabilite/api/details-solde/' if not workflow_app_mode else '/api/details-solde/',
    }
    return render(request, 'accounting/workflow_soldes_reels.html', context)


@login_required
@require_http_methods(["POST"])
def api_workflow_soldes_reels_save(request):
    try:
        solde_id = (request.POST.get('solde_id') or '').strip()
        journal = (request.POST.get('journal') or '').strip()
        fichier_source = (request.POST.get('fichier_source') or '').strip()
        date_m_str = (request.POST.get('date_m') or '').strip()
        description = (request.POST.get('description') or '').strip()
        validation = (request.POST.get('validation') or '').strip()
        ccy_raw = (request.POST.get('ccy') or '').strip()
        scan_file = request.FILES.get('scan_file')

        if not journal or not fichier_source or not date_m_str:
            return JsonResponse({'success': False, 'error': 'Journal, base et date sont obligatoires'}, status=400)

        try:
            date_m = datetime.strptime(date_m_str, '%Y-%m-%d').date()
        except ValueError:
            return JsonResponse({'success': False, 'error': 'Date invalide'}, status=400)

        try:
            ccy = Decimal(ccy_raw.replace(' ', '').replace(',', '.'))
        except Exception:
            return JsonResponse({'success': False, 'error': 'Solde reel invalide'}, status=400)

        if not request.user.is_superuser:
            allowed_fichiers = set(
                _get_diamex_entries_scope_queryset(request)
                .exclude(fichier_source__isnull=True)
                .exclude(fichier_source='')
                .values_list('fichier_source', flat=True)
                .distinct()
            )
            if fichier_source not in allowed_fichiers:
                return JsonResponse({'success': False, 'error': 'Acces refuse a cette base'}, status=403)

        solde = None
        if solde_id:
            solde = SoldesReels.objects.filter(id=solde_id).first()

        if not solde:
            solde = SoldesReels.objects.filter(
                journal=journal,
                date_m=date_m,
                fichier_source=fichier_source
            ).order_by('-id').first()

        if not solde:
            solde = SoldesReels(
                journal=journal,
                date_m=date_m,
                fichier_source=fichier_source,
                imported_by=getattr(request.user, 'employe', None),
            )

        solde.ccy = ccy
        solde.description = description
        solde.validation = validation
        solde.date_rec = timezone.now().date()
        solde.date_input = timezone.now()

        if scan_file:
            safe_journal = (journal or 'journal').replace('/', '-').replace('\\', '-')
            safe_file = (fichier_source or 'base').replace('/', '-').replace('\\', '-')
            filename = f"soldes_reels/{safe_file}_{safe_journal}_{date_m.strftime('%Y_%m')}_{scan_file.name}"
            saved_path = default_storage.save(filename, ContentFile(scan_file.read()))
            solde.scan = default_storage.url(saved_path)

        solde.save()

        return JsonResponse({
            'success': True,
            'message': 'Solde reel enregistre',
            'solde_id': solde.id,
            'scan': solde.scan or '',
        })
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


def soldes_reels_list(request):
    """Liste des soldes réels avec filtres et controles qualité"""
    from .models import SoldesReels

    # Récupérer les filtres
    search = request.GET.get('search', '').strip()
    fichier_source = request.GET.get('fichier_source', '').strip()
    journal_filter = request.GET.get('journal', '').strip()
    date_debut = request.GET.get('date_debut', '')
    date_fin = request.GET.get('date_fin', '')

    # Queryset de base
    soldes = SoldesReels.objects.all()

    # Appliquer les filtres
    if search:
        soldes = soldes.filter(
            Q(description__icontains=search) |
            Q(journal__icontains=search) |
            Q(validation__icontains=search)
        )

    if fichier_source:
        soldes = soldes.filter(fichier_source=fichier_source)

    if journal_filter:
        soldes = soldes.filter(journal=journal_filter)

    if date_debut:
        soldes = soldes.filter(date_m__gte=date_debut)

    if date_fin:
        soldes = soldes.filter(date_m__lte=date_fin)

    # Statistiques de qualité
    total_soldes = soldes.count()
    sans_scan = soldes.filter(Q(scan__isnull=True) | Q(scan='')).count()
    avec_scan = total_soldes - sans_scan
    couverture_scan = (avec_scan / total_soldes * 100) if total_soldes > 0 else 0

    # Pagination
    paginator = Paginator(soldes, 100)  # 100 éléments par page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Listes pour les filtres
    fichiers = SoldesReels.objects.values_list('fichier_source', flat=True).distinct().order_by('fichier_source')
    journaux = SoldesReels.objects.values_list('journal', flat=True).distinct().order_by('journal')

    return render(request, 'accounting/soldes_reels_list.html', {
        'title': 'Soldes Réels',
        'page_obj': page_obj,
        'fichiers': fichiers,
        'journaux': journaux,
        'filters': {
            'search': search,
            'fichier_source': fichier_source,
            'journal': journal_filter,
            'date_debut': date_debut,
            'date_fin': date_fin,
        },
        'total_soldes': total_soldes,
        'avec_scan': avec_scan,
        'sans_scan': sans_scan,
        'couverture_scan': round(couverture_scan, 1),
    })


@login_required
def comparaison_soldes(request):
    """
    Comparaison des soldes calculés (DATA) vs soldes réels (SoldesReels)
    Les soldes doivent ètre strictement égaux pour chaque journal/mois
    """
    from .models import SoldesReels, BaseDiameX
    from django.db.models import Sum, Q
    from collections import defaultdict

    # Filtres
    fichier_source = request.GET.get('fichier_source', '').strip()
    journal_filter = request.GET.get('journal', '').strip()
    date_debut = request.GET.get('date_debut', '')
    date_fin = request.GET.get('date_fin', '')
    statut_filter = request.GET.get('statut', '')  # Filtre par statut

    # Query de base - Exclure 00PERS et 00SPLITBOOK-MGA
    soldes_reels_qs = SoldesReels.objects.exclude(
        journal__in=['00PERS', '00SPLITBOOK-MGA']
    ).exclude(date_m__isnull=True)
    entries_qs = _get_diamex_entries_scope_queryset(request).exclude(
        journal_code__in=['00PERS', '00SPLITBOOK-MGA']
    ).exclude(date_m__isnull=True)

    if not request.user.is_superuser:
        allowed_fichiers = list(
            entries_qs.exclude(fichier_source__isnull=True)
            .exclude(fichier_source='')
            .values_list('fichier_source', flat=True)
            .distinct()
        )
        soldes_reels_qs = soldes_reels_qs.filter(fichier_source__in=allowed_fichiers)

    # Appliquer les filtres
    if fichier_source:
        soldes_reels_qs = soldes_reels_qs.filter(fichier_source=fichier_source)
        entries_qs = entries_qs.filter(fichier_source=fichier_source)

    if journal_filter:
        soldes_reels_qs = soldes_reels_qs.filter(journal=journal_filter)
        entries_qs = entries_qs.filter(journal_code=journal_filter)

    if date_debut:
        soldes_reels_qs = soldes_reels_qs.filter(date_m__gte=date_debut)
        entries_qs = entries_qs.filter(date_m__gte=date_debut)

    if date_fin:
        soldes_reels_qs = soldes_reels_qs.filter(date_m__lte=date_fin)
        entries_qs = entries_qs.filter(date_m__lte=date_fin)

    # Calculer les soldes réels par journal/mois/fichier
    soldes_reels_dict = {}
    fichiers_par_cle = {}  # Pour stocker le fichier_source par clé
    description_par_cle = {}  # Pour stocker la description
    scan_par_cle = {}  # Pour stocker le scan
    solde_id_par_cle = {}  # Pour stocker l'ID du solde

    for solde in soldes_reels_qs.values('journal', 'date_m', 'fichier_source').annotate(total=Sum('ccy')).order_by('date_m', 'journal'):
        key = (solde['journal'], solde['date_m'])
        soldes_reels_dict[key] = float(solde['total'] or 0)
        fichiers_par_cle[key] = solde['fichier_source']  # Stocker le fichier

        # Récupérer description et scan du dernier enregistrement
        dernier_solde = soldes_reels_qs.filter(
            journal=solde['journal'],
            date_m=solde['date_m'],
            fichier_source=solde['fichier_source']
        ).order_by('-date_rec').first()

        if dernier_solde:
            description_par_cle[key] = dernier_solde.description or ''
            # [OK] CRITICAL: Enregistrer l'ID TOUJOURS (pas seulement si scan existe)
            solde_id_par_cle[key] = dernier_solde.id
            # [OK] Utiliser directement le scan (déjà absolu grâce à fix_all_scans.py)
            scan_par_cle[key] = dernier_solde.scan or ''

    # [OK] Calculer les soldes calculés (DATA) par journal/mois - SOLDE CUMULé
    # Il faut générer TOUS les mois présents dans SoldesReels OU DATA
    soldes_calcules_dict = {}
    from dateutil.relativedelta import relativedelta

    # Récupérer tous les journaux uniques (union de DATA et SoldesReels)
    journaux_data = set((j['journal_code'], j['fichier_source']) for j in entries_qs.values('journal_code', 'fichier_source').distinct())
    journaux_soldes = set((s['journal'], s['fichier_source']) for s in soldes_reels_qs.values('journal', 'fichier_source').distinct())
    tous_journaux = journaux_data | journaux_soldes

    for journal_code, fichier in tous_journaux:
        # Récupérer toutes les écritures DATA de ce journal
        ecritures = entries_qs.filter(
            journal_code=journal_code,
            fichier_source=fichier
        ).order_by('date_m').values('date_m').annotate(
            total_in=Sum('montant_in'),
            total_out=Sum('montant_out')
        )

        # Créer un dict des mouvements par date
        mouvements_par_mois = {}
        for ecriture in ecritures:
            if not ecriture['date_m']:
                continue
            mouvements_par_mois[ecriture['date_m']] = float(ecriture['total_in'] or 0) - float(ecriture['total_out'] or 0)

        # Récupérer les dates SoldesReels pour ce journal
        dates_soldes = list(soldes_reels_qs.filter(
            journal=journal_code,
            fichier_source=fichier
        ).exclude(date_m__isnull=True).values_list('date_m', flat=True).distinct())

        # Union des dates DATA et SoldesReels
        toutes_dates = set(mouvements_par_mois.keys()) | set(dates_soldes)

        if not toutes_dates:
            continue

        # Déterminer la plage complète (du premier au dernier mois)
        dates_triees = sorted(d for d in toutes_dates if d is not None)
        if not dates_triees:
            continue
        date_debut = dates_triees[0]
        date_fin = dates_triees[-1]

        # [OK] Générer TOUS les mois entre le début et la fin
        solde_cumule = 0
        date_courante = date_debut

        while date_courante <= date_fin:
            # Ajouter le mouvement du mois (0 si pas de transaction)
            solde_mois = mouvements_par_mois.get(date_courante, 0)
            solde_cumule += solde_mois

            key = (journal_code, date_courante)
            soldes_calcules_dict[key] = solde_cumule
            if key not in fichiers_par_cle:
                fichiers_par_cle[key] = fichier

            # Passer au mois suivant
            date_courante = date_courante.replace(day=1) + relativedelta(months=1)

    # Comparer les deux dictionnaires
    comparaisons = []
    tous_les_cles = set(soldes_reels_dict.keys()) | set(soldes_calcules_dict.keys())

    for cle in sorted(tous_les_cles, key=lambda c: (c[0] or '', c[1] is None, c[1])):
        journal, date_m = cle
        solde_reel = soldes_reels_dict.get(cle, 0)
        solde_calcule = soldes_calcules_dict.get(cle, 0)
        ecart = abs(solde_reel - solde_calcule)

        # Déterminer le statut
        est_conforme = ecart < 0.01
        est_explique = not est_conforme and bool(description_par_cle.get(cle, '').strip())
        statut = 'conforme' if est_conforme else ('explique' if est_explique else 'non_conforme')

        # Appliquer le filtre statut
        if statut_filter and statut != statut_filter:
            continue

        comparaisons.append({
            'journal': journal,
            'date_m': date_m,
            'fichier_source': fichiers_par_cle.get(cle, ''),  # [OK] Ajouter le fichier
            'solde_reel': solde_reel,
            'solde_calcule': solde_calcule,
            'ecart': ecart,
            'est_conforme': est_conforme,
            'est_explique': est_explique,
            'statut': statut,
            'description': description_par_cle.get(cle, ''),
            'scan': scan_par_cle.get(cle, ''),
            'solde_id': solde_id_par_cle.get(cle, None),
        })

    # Statistiques améliorées
    total_comparaisons = len(comparaisons)
    conformes = sum(1 for c in comparaisons if c['statut'] == 'conforme')
    expliques = sum(1 for c in comparaisons if c['statut'] == 'explique')
    non_conformes = sum(1 for c in comparaisons if c['statut'] == 'non_conforme')
    taux_conformite = (conformes / total_comparaisons * 100) if total_comparaisons > 0 else 0
    taux_expliques = (expliques / total_comparaisons * 100) if total_comparaisons > 0 else 0

    # Stats des scans
    avec_scan = sum(1 for c in comparaisons if c['scan'])
    sans_scan = total_comparaisons - avec_scan
    taux_avec_scan = int((avec_scan / total_comparaisons * 100) if total_comparaisons > 0 else 0)

    # Listes pour les filtres - Exclure 00PERS
    fichiers_soldes = soldes_reels_qs.values_list('fichier_source', flat=True).distinct().order_by('fichier_source')
    journaux_soldes = soldes_reels_qs.values_list('journal', flat=True).distinct().order_by('journal')

    # Derniers soldes par journal (selon filtres)
    # [OK] CORRECTION: Recalculer jusqu'à la dernière transaction DATA (pas seulement dernier SoldesReels)
    # Inclure TOUS les journaux (SoldesReels ET DATA)
    journaux_data_list = entries_qs.values_list('journal_code', flat=True).distinct()
    tous_journaux_uniques = set(journaux_soldes) | set(journaux_data_list)

    derniers_soldes = []
    for journal in tous_journaux_uniques:
        # Récupérer la dernière date dans DATA pour ce journal
        from datetime import date as date_class
        dernier_date_data = entries_qs.filter(
            journal_code=journal
        ).aggregate(Max('date_m'))['date_m__max']

        if not dernier_date_data:
            # Pas de transactions DATA, utiliser le dernier solde SoldesReels si disponible
            comps_journal = [c for c in comparaisons if c['journal'] == journal]
            if comps_journal:
                dernier = max(comps_journal, key=lambda x: x['date_m'])
                derniers_soldes.append(dernier)
            continue

        # Vérifier si on a déjà cette date dans comparaisons
        comparaison_existante = next(
            (c for c in comparaisons if c['journal'] == journal and c['date_m'] == dernier_date_data),
            None
        )

        if comparaison_existante:
            # Utiliser la comparaison existante
            derniers_soldes.append(comparaison_existante)
        else:
            # Recalculer le solde jusqu'à cette date
            # (Cette date n'a pas de SoldesReels, donc solde_reel = solde_calcule)
            solde_cumule = soldes_calcules_dict.get((journal, dernier_date_data), 0)

            derniers_soldes.append({
                'journal': journal,
                'date_m': dernier_date_data,
                'fichier_source': fichiers_par_cle.get((journal, dernier_date_data), ''),
                'solde_reel': solde_cumule,  # Pas de SoldesReels, on met le calcule
                'solde_calcule': solde_cumule,
                'ecart': 0,
                'est_conforme': True,
                'est_explique': False,
                'statut': 'conforme',
                'description': '',
                'scan': '',
                'solde_id': None,
            })

    # Trier par date décroissante
    derniers_soldes.sort(
        key=lambda x: (x['date_m'] is None, x['date_m']),
        reverse=True
    )

    # Total des soldes calculés des derniers soldes
    total_soldes_calcules = sum(s['solde_calcule'] for s in derniers_soldes)

    return render(request, 'accounting/comparaison_soldes.html', {
        'title': 'Comparaison des Soldes',
        'comparaisons': comparaisons,
        'fichiers': fichiers_soldes,
        'journaux': journaux_soldes,
        'filters': {
            'fichier_source': fichier_source,
            'journal': journal_filter,
            'date_debut': date_debut,
            'date_fin': date_fin,
            'statut': statut_filter,
        },
        'total_comparaisons': total_comparaisons,
        'conformes': conformes,
        'expliques': expliques,
        'non_conformes': non_conformes,
        'taux_conformite': int(taux_conformite),
        'taux_expliques': int(taux_expliques),
        'taux_non_conformes': int((non_conformes / total_comparaisons * 100) if total_comparaisons > 0 else 0),
        'avec_scan': avec_scan,
        'sans_scan': sans_scan,
        'taux_avec_scan': taux_avec_scan,
        'derniers_soldes': derniers_soldes,
        'total_soldes_calcules': total_soldes_calcules,
    })


@login_required
@require_http_methods(["GET"])
def api_details_solde(request):
    """API pour récupérer les détails d'un solde (toutes les écritures DATA d'un journal/mois)"""
    from .models import BaseDiameX
    from datetime import datetime
    from dateutil.relativedelta import relativedelta

    fichier_source = request.GET.get('fichier_source', '').strip()
    journal = request.GET.get('journal', '').strip()
    date_m_str = request.GET.get('date_m', '').strip()

    if not all([fichier_source, journal, date_m_str]):
        return JsonResponse({'success': False, 'error': 'Paramètres manquants'}, status=400)

    # Parser la date
    date_m = datetime.strptime(date_m_str, '%Y-%m-%d').date()

    entries_scope = _get_diamex_entries_scope_queryset(request).filter(
        fichier_source=fichier_source,
        journal_code=journal
    )

    # [OK] Calculer le solde du mois précédent (solde initial)
    # Récupérer TOUTES les écritures AVANT ce mois
    solde_initial = entries_scope.filter(
        date_m__lt=date_m
    ).aggregate(
        total_in=Sum('montant_in'),
        total_out=Sum('montant_out')
    )

    solde_cumule = float(solde_initial['total_in'] or 0) - float(solde_initial['total_out'] or 0)

    # Récupérer les écritures du mois en cours
    entries = entries_scope.filter(
        date_m=date_m
    ).order_by('date_rec', 'rec').values(
        'id_access', 'rec', 'date_rec', 'description',
        'montant_in', 'montant_out', 'compte_code',
        'pers', 'detail', 'info', 'scan'
    )

    # Calculer le solde cumulé ligne par ligne
    entries_list = []
    for entry in entries:
        solde_cumule += float(entry['montant_in'] or 0) - float(entry['montant_out'] or 0)
        entries_list.append({
            'id_access': entry['id_access'],
            'rec': entry['rec'],
            'date_rec': entry['date_rec'].strftime('%d/%m/%Y') if entry['date_rec'] else '',
            'description': entry['description'] or '',
            'montant_in': float(entry['montant_in'] or 0),
            'montant_out': float(entry['montant_out'] or 0),
            'compte': entry['compte_code'] or '',
            'pers': entry['pers'] or '',
            'detail': entry['detail'] or '',
            'info': entry['info'] or '',
            'scan': entry['scan'] or '',
            'solde_cumule': round(solde_cumule, 2),
        })

    # Calculer le solde initial (avant les écritures du mois)
    solde_initial_mois = solde_cumule
    if entries_list:
        # Soustraire les mouvements du mois pour retrouver le solde initial
        solde_initial_mois = solde_cumule
        for e in reversed(entries_list):
            solde_initial_mois -= e['montant_in'] - e['montant_out']

    return JsonResponse({
        'success': True,
        'entries': entries_list,
        'solde_initial': round(float(solde_initial['total_in'] or 0) - float(solde_initial['total_out'] or 0), 2),
        'total_in': sum(e['montant_in'] for e in entries_list),
        'total_out': sum(e['montant_out'] for e in entries_list),
        'solde_final': round(solde_cumule, 2),
        'count': len(entries_list),
    })


def verification_comptabilite(request):
    """
    Page dédiée à la vérification de la comptabilité
    - Filtrage par mois, compte, fichier source
    - Vérification des pièces justificatives (scan)
    - Reconstruction et test des liens scan
    """
    from apps.organization.models import Base
    import os

    # Récupérer les filtres
    search = request.GET.get('search', '').strip()
    fichier_source = request.GET.get('fichier_source', '').strip()
    compte_code = request.GET.get('compte', '').strip()
    categorie_parente = request.GET.get('categorie', '').strip()
    prog_code = request.GET.get('prog', '').strip()
    mois = request.GET.get('mois', '').strip()  # Format YYYY-MM
    ordre_date = request.GET.get('ordre', 'desc')  # 'asc' ou 'desc'

    # Queryset de base
    entries = BaseDiameX.objects.select_related('journal', 'compte').all()

    # Si filtre compte explicite, ne PAS appliquer les exclusions automatiques
    if not compte_code:
        # Exclure les transferts et avances (seulement si pas de filtre compte)
        # Transferts 00BOOK
        book_entries = entries.filter(compte_code__startswith='00BOOK')

        # Transferts 00FND1 SANS "EDF"
        fnd1_transferts = entries.filter(compte_code__startswith='00FND1').exclude(
            Q(description__icontains='EDF') | Q(info__icontains='EDF')
        )

        # Tous les transferts
        transferts_entries = book_entries | fnd1_transferts

        # Avances 00PERS
        pers_entries = entries.filter(compte_code__startswith='00PERS')

        # Recettes/Dépenses = SANS transferts et SANS avances
        entries = entries.exclude(
            Q(compte_code__startswith='00BOOK') |
            Q(compte_code__startswith='00PERS')
        ).exclude(
            Q(compte_code__startswith='00FND1') &
            ~(Q(description__icontains='EDF') | Q(info__icontains='EDF'))
        )

    # Filtrer uniquement les entrées avec montant (recettes OU dépenses)
    entries = entries.filter(Q(montant_in__gt=0) | Q(montant_out__gt=0))

    # Appliquer les filtres
    if search:
        entries = entries.filter(
            Q(description__icontains=search) |
            Q(info__icontains=search) |
            Q(pers__icontains=search) |
            Q(detail__icontains=search)
        )

    if fichier_source:
        entries = entries.filter(fichier_source=fichier_source)

    if compte_code:
        entries = entries.filter(compte_code=compte_code)

    if prog_code:
        entries = entries.filter(prog=prog_code)

    if mois:
        # Filtrer par mois (YYYY-MM)
        year, month = mois.split('-')
        entries = entries.filter(date_m__year=year, date_m__month=month)

    # Ordonner par date selon le paramètre ordre
    if ordre_date == 'asc':
        entries = entries.order_by('date_m', 'id')
    else:
        entries = entries.order_by('-date_m', '-id')

    # Filtre par catégorie parente (en Python car méthode calculée)
    if categorie_parente:
        entries_list = list(entries)
        # Gestion compatibilité: si ancienne catégorie "Transfert", matcher les deux nouvelles
        if categorie_parente == 'Transfert':
            entries_filtered = [entry for entry in entries_list
                                if entry.get_categorie_parente() in ['Transferts 00BOOK', 'Transferts 00FND1']]
        else:
            entries_filtered = [entry for entry in entries_list if entry.get_categorie_parente() == categorie_parente]
        # Récupérer les IDs des entrées filtrées
        filtered_ids = [entry.id for entry in entries_filtered]
        # Filtrer le queryset original par ces IDs
        entries = BaseDiameX.objects.filter(id__in=filtered_ids).select_related('journal', 'compte')
        if ordre_date == 'asc':
            entries = entries.order_by('date_m', 'id')
        else:
            entries = entries.order_by('-date_m', '-id')

    # Récupérer toutes les bases pour matcher prog -> chemin
    bases_dict = {}
    for base in Base.objects.all():
        if base.prog_diamex:
            bases_dict[base.prog_diamex] = {
                'chemin': base.chemin_base_diamex or '',
                'nom': base.nom_base,
            }

    # Enrichir les entrées avec les liens scan reconstruits
    entries_enriched = []
    for entry in entries:
        # Déterminer si scan manquant
        has_scan = entry.scan and entry.scan.strip()

        # Reconstruire le lien scan complet
        full_scan_path = None
        scan_status = 'missing'  # missing, invalid, exists, dead

        if has_scan:
            # Trouver la base correspondante via prog
            base_info = bases_dict.get(entry.prog)

            if base_info and base_info['chemin']:
                chemin_base = base_info['chemin']
                scan_relatif = entry.scan

                # [OK] Nettoyer les caractères # au début et à la fin
                scan_relatif = scan_relatif.strip('#')

                # Enlever le "." au début si présent
                if scan_relatif.startswith('.'):
                    scan_relatif = scan_relatif[1:]

                # Construire le chemin complet
                # Si scan contient déjà le chemin absolu, ne pas concaténer
                if scan_relatif.startswith(chemin_base):
                    full_scan_path = scan_relatif
                else:
                    full_scan_path = chemin_base + scan_relatif

                # Vérifier si le fichier existe
                if os.path.exists(full_scan_path):
                    scan_status = 'exists'
                else:
                    scan_status = 'dead'
            else:
                scan_status = 'invalid'  # Prog introuvable ou chemin base manquant

        # Générer des suggestions de reformulation pour la description
        from apps.accounting.extracteurs_description import generer_suggestions_reformulation
        suggestions = generer_suggestions_reformulation(entry.description)

        entries_enriched.append({
            'entry': entry,
            'has_scan': has_scan,
            'full_scan_path': full_scan_path,
            'scan_status': scan_status,
            'base_info': bases_dict.get(entry.prog),
            'suggestions': suggestions,
        })

    # Statistiques globales
    total_entries = len(entries_enriched)
    sans_scan = sum(1 for e in entries_enriched if e['scan_status'] == 'missing')
    liens_morts = sum(1 for e in entries_enriched if e['scan_status'] == 'dead')
    liens_invalides = sum(1 for e in entries_enriched if e['scan_status'] == 'invalid')
    liens_ok = sum(1 for e in entries_enriched if e['scan_status'] == 'exists')

    # Calculer les montants
    total_recettes = sum(e['entry'].montant_in for e in entries_enriched)
    total_depenses = sum(e['entry'].montant_out for e in entries_enriched)

    # Pagination
    paginator = Paginator(entries_enriched, 50)
    page_number = request.GET.get('page', 1)

    # Valider le numéro de page
    try:
        page_number = int(page_number)
        if page_number < 1:
            page_number = 1
    except (ValueError, TypeError):
        page_number = 1

    page_obj = paginator.get_page(page_number)

    # Listes pour filtres - Utiliser un set pour éliminer les doublons puis trier
    fichiers_sources_raw = BaseDiameX.objects.values_list('fichier_source', flat=True).distinct()
    fichiers_sources = sorted(set(f for f in fichiers_sources_raw if f))  # Enlever les None/vides

    # Liste de TOUS les comptes disponibles (sans exclusion pour le dropdown)
    comptes_codes_raw = BaseDiameX.objects.values_list('compte_code', flat=True).distinct()
    comptes_codes = sorted(set(c for c in comptes_codes_raw if c))

    # Liste des progs disponibles
    progs_codes_raw = BaseDiameX.objects.values_list('prog', flat=True).distinct()
    progs_codes = sorted(set(p for p in progs_codes_raw if p))  # Enlever les None/vides

    # Liste des catégories parentes disponibles
    categories_parentes = [
        'Transferts 00BOOK', 'Transferts 00FND1', 'EDF', 'Compte de tiers', 'Acquisition', 'Matériaux',
        'Fournitures', 'équipement', 'Carburant', 'Fonctionnement',
        'Entretien véhicules', "Main d'Å“uvre", 'Paiements employés', 'Impots',
        'Autres recettes', 'Vente eau au volume', 'Paiement extension', 'Vente eau au forfait',
        'Vente carte sociale', 'Autres'
    ]

    return render(request, 'accounting/verification_comptabilite.html', {
        'page_obj': page_obj,
        'entries_enriched': page_obj,
        'fichiers_sources': fichiers_sources,
        'comptes_codes': comptes_codes,
        'categories_parentes': categories_parentes,
        'progs_codes': progs_codes,
        'ordre_date': ordre_date,
        'total_entries': total_entries,
        'sans_scan': sans_scan,
        'liens_morts': liens_morts,
        'liens_invalides': liens_invalides,
        'liens_ok': liens_ok,
        'total_recettes': total_recettes,
        'total_depenses': total_depenses,
        'taux_couverture': round((liens_ok / total_entries * 100) if total_entries > 0 else 0, 1),
    })


@login_required
def diagnostic_soldes(request):
    """Page de diagnostic des soldes par compte"""
    from django.db.models import Sum, Count
    from apps.organization.models import Base

    # Calculer les soldes par compte
    base_query = BaseDiameX.objects.all()
    user_organisation_id = getattr(
        getattr(getattr(request.user, 'employe', None), 'base', None),
        'organisation_id',
        None
    )
    if user_organisation_id and not request.user.is_superuser:
        allowed_progs = list(
            Base.objects.filter(organisation_id=user_organisation_id)
            .exclude(prog_diamex__isnull=True)
            .exclude(prog_diamex='')
            .values_list('prog_diamex', flat=True)
            .distinct()
        )
        if allowed_progs:
            base_query = base_query.filter(prog__in=allowed_progs)
        else:
            base_query = base_query.none()

    soldes_query = base_query.values(
        'compte_code'
    ).annotate(
        total_in=Sum('montant_in'),
        total_out=Sum('montant_out'),
        count=Count('id')
    ).order_by('compte_code')

    soldes = []
    total_in_global = 0
    total_out_global = 0
    total_count_global = 0

    for item in soldes_query:
        if not item['compte_code']:
            continue

        total_in = item['total_in'] or 0
        total_out = item['total_out'] or 0
        solde = total_in - total_out

        # Recuperer le nom du compte si disponible
        compte_qs = Compte.objects.filter(compte=item['compte_code'])
        if user_organisation_id and not request.user.is_superuser:
            compte_qs = compte_qs.filter(organisation_id=user_organisation_id)
        compte_obj = compte_qs.first()
        compte_nom = compte_obj.nom_compte if compte_obj else None

        soldes.append({
            'compte_code': item['compte_code'],
            'compte_nom': compte_nom,
            'total_in': total_in,
            'total_out': total_out,
            'solde': solde,
            'count': item['count'],
        })

        total_in_global += total_in
        total_out_global += total_out
        total_count_global += item['count']

    # Trier par solde absolu decroissant (mettre les desequilibres en premier)
    soldes.sort(key=lambda x: abs(x['solde']), reverse=True)

    return render(request, 'accounting/diagnostic_soldes.html', {
        'soldes': soldes,
        'total_in': total_in_global,
        'total_out': total_out_global,
        'total_solde': total_in_global - total_out_global,
        'total_count': total_count_global,
    })


def serve_scan_file(request, entry_id):
    """
    Sert un fichier scan via HTTP
    Reconstruit le chemin complet et retourne le fichier
    """
    from django.http import FileResponse, Http404, HttpResponse
    from apps.employees.models import EmployeBaseDiameX
    import os
    import mimetypes

    try:
        requested_page = request.GET.get('page')
        raw_mode = request.GET.get('raw') == '1'

        # Récupérer l'entrée comptable
        entry = BaseDiameX.objects.get(id=entry_id)

        if entry.scan_importe and getattr(entry.scan_importe, 'name', ''):
            scan_path = entry.scan_importe.path
            if os.path.exists(scan_path) and os.path.isfile(scan_path):
                if _is_tiff_file(scan_path):
                    if raw_mode:
                        content_type = 'image/tiff'
                        response = FileResponse(entry.scan_importe.open('rb'), content_type=content_type)
                        response['Content-Disposition'] = f'inline; filename="{os.path.basename(scan_path)}"'
                        return response
                    if requested_page:
                        return _serve_tiff_page(scan_path, int(requested_page))
                    return render(
                        request,
                        'accounting/tiff_viewer.html',
                        {
                            'entry_id': entry_id,
                            'filename': os.path.basename(scan_path),
                            'raw_url': request.build_absolute_uri(f'?raw=1'),
                        }
                    )

                content_type, _ = mimetypes.guess_type(scan_path)
                if not content_type:
                    content_type = 'application/octet-stream'

                response = FileResponse(entry.scan_importe.open('rb'), content_type=content_type)
                response['Content-Disposition'] = f'inline; filename="{os.path.basename(scan_path)}"'
                return response

        # Vérifier qu'il y a un scan
        if not entry.scan or not entry.scan.strip():
            raise Http404("Aucun scan défini pour cette entrée")

        # Nettoyer la valeur scan
        scan_value = (entry.scan or '').strip().strip('#')
        if not scan_value:
            raise Http404("Scan vide")
        full_scan_path, candidates = _resolve_entry_scan_path(entry)
        if not full_scan_path:
            # Fallback UX: si le fichier n'est pas sur le serveur, essayer l'agent local
            # pour éviter une page 404 brute quand le scan est sur le PC utilisateur.
            candidates_json = json.dumps([p for p in candidates if p], ensure_ascii=False)
            html = f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>Ouverture du scan</title>
  <style>
    body {{ font-family: Arial, sans-serif; padding: 24px; line-height: 1.4; }}
    .muted {{ color: #666; }}
    code {{ background: #f3f3f3; padding: 2px 6px; border-radius: 4px; }}
  </style>
</head>
<body>
  <h3>Tentative d'ouverture locale du scan...</h3>
  <p class="muted">Le scan n'est pas disponible sur le serveur. Essai via l'agent local.</p>
  <p class="muted">Entrée: <code>{entry_id}</code></p>
  <script>
    (async function() {{
      const candidates = {candidates_json};
      async function tryOpen(path) {{
        const res = await fetch('http://127.0.0.1:8765/open-file', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ file_path: path }})
        }});
        const data = await res.json();
        return !!(data && data.ok && data.success);
      }}
      for (const p of candidates) {{
        if (!p) continue;
        try {{
          const ok = await tryOpen(p);
          if (ok) {{
            document.body.innerHTML = '<h3>Scan ouvert localement.</h3><p class="muted">Vous pouvez fermer cet onglet.</p>';
            return;
          }}
        }} catch (e) {{
          // continue
        }}
      }}
      document.body.innerHTML = '<h3>Impossible d\\'ouvrir le scan.</h3>' +
        '<p>1) Lancez <code>LANCER_AGENT_DIAMEX.bat</code><br>2) Vérifiez que le fichier existe sur ce PC</p>';
    }})();
  </script>
</body>
</html>"""
            return HttpResponse(html, content_type='text/html; charset=utf-8')

        # Vérifier que c'est bien un fichier (pas un dossier)
        if not os.path.isfile(full_scan_path):
            raise Http404("Le chemin ne pointe pas vers un fichier")

        if _is_tiff_file(full_scan_path):
            if raw_mode:
                response = FileResponse(open(full_scan_path, 'rb'), content_type='image/tiff')
                response['Content-Disposition'] = f'inline; filename="{os.path.basename(full_scan_path)}"'
                return response
            if requested_page:
                return _serve_tiff_page(full_scan_path, int(requested_page))
            return render(
                request,
                'accounting/tiff_viewer.html',
                {
                    'entry_id': entry_id,
                    'filename': os.path.basename(full_scan_path),
                    'raw_url': request.build_absolute_uri(f'?raw=1'),
                }
            )

        # Déterminer le type MIME
        content_type, _ = mimetypes.guess_type(full_scan_path)
        if not content_type:
            content_type = 'application/octet-stream'

        # Ouvrir et retourner le fichier
        file_handle = open(full_scan_path, 'rb')
        response = FileResponse(file_handle, content_type=content_type)

        # Suggérer un nom de fichier pour le téléchargement
        filename = os.path.basename(full_scan_path)
        response['Content-Disposition'] = f'inline; filename="{filename}"'

        return response

    except BaseDiameX.DoesNotExist:
        raise Http404("Entrée comptable introuvable")
    except Http404:
        raise
    except Exception as e:
        raise Http404(f"Erreur lors de l'ouverture du fichier: {str(e)}")


@require_http_methods(["POST"])
def update_entry(request, entry_id):
    """
    Met à jour une entrée comptable dans Django ET dans le fichier Access
    """
    from django.http import Http404
    import pyodbc
    import os

    try:
        entry = BaseDiameX.objects.get(id=entry_id)

        # Sauvegarder les anciennes valeurs AVANT modification
        old_description = entry.description or ''
        old_info = entry.info or ''
        old_pers = entry.pers or ''
        old_detail = entry.detail or ''
        old_scan = entry.scan or ''
        old_compte_code = entry.compte_code or ''

        # Récupérer les nouvelles valeurs (SANS scan - géré uniquement dans Access)
        description = request.POST.get('description', '').strip()
        info = request.POST.get('info', '').strip()
        detail = request.POST.get('detail', '').strip()
        compte_code = request.POST.get('compte_code', '').strip()

        # 1. Mettre à jour Django d'abord (SANS scan et pers)
        entry.description = description
        entry.info = info
        entry.detail = detail
        if compte_code:  # Mettre à jour le compte si fourni
            entry.compte_code = compte_code
        entry.save()

        # Préparer les modifications Access (servira aussi au fallback agent local)
        access_updates = {}
        if description != old_description:
            access_updates["Description"] = description
        if info != old_info:
            access_updates["Info"] = info
        if detail != old_detail:
            access_updates["Detail"] = detail
        if compte_code and compte_code != old_compte_code:
            access_updates["Cat"] = compte_code

        # 2. Tenter de mettre à jour Access
        access_updated = False
        access_error = None
        access_payload = None

        # Trouver le chemin complet du fichier Access via EmployeBaseDiameX
        if entry.fichier_source:
            from apps.employees.models import EmployeBaseDiameX

            # Chercher la base DiameX correspondante (priorité: utilisateur courant)
            base_diamex = None
            user_employe = getattr(request.user, 'employe', None)
            if user_employe:
                base_diamex = EmployeBaseDiameX.objects.filter(
                    employe=user_employe,
                    base_diamex=entry.fichier_source
                ).first()

            # Fallback 1: employe qui a importé
            if not base_diamex and entry.imported_by:
                base_diamex = EmployeBaseDiameX.objects.filter(
                    employe=entry.imported_by,
                    base_diamex=entry.fichier_source
                ).first()

            # Fallback 2: recherche large par nom de base/prog
            if not base_diamex:
                prog_value = (entry.prog or '').strip()
                if prog_value:
                    base_diamex = EmployeBaseDiameX.objects.filter(base_diamex__icontains=prog_value).first()
            if not base_diamex:
                base_diamex = EmployeBaseDiameX.objects.filter(base_diamex=entry.fichier_source).first()

            if base_diamex:
                access_path = base_diamex.chemin_complet
                if access_updates:
                    access_payload = {
                        'file_path': access_path,
                        'id_access': entry.id_access,
                        'updates': access_updates
                    }
            else:
                access_error = f"Base DiameX '{entry.fichier_source}' introuvable pour cet employé"
                access_path = None

            if access_path:
                try:
                    # Vérifier que le fichier existe
                    if os.path.exists(access_path):
                        conn_str = (
                            r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
                            f'DBQ={access_path};'
                        )
                        conn = pyodbc.connect(conn_str)
                        cursor = conn.cursor()

                        # Construire la requète UPDATE dynamiquement selon les champs modifiés
                        updates = []
                        params = []
                        for field_name, field_value in access_updates.items():
                            updates.append(f"{field_name}=?")
                            params.append(field_value)

                        # Mettre à jour uniquement si des champs ont changé
                        if updates:
                            params.append(entry.id_access)  # WHERE ID=?

                            sql = f"UPDATE DATA SET {', '.join(updates)} WHERE ID=?"

                            try:
                                cursor.execute(sql, params)
                                conn.commit()
                                access_updated = True
                            except pyodbc.IntegrityError as e:
                                # Erreur d'intégrité (ex: contrainte sur Cat)
                                access_error = f"Erreur Access: {str(e)}"
                                raise
                        else:
                            # Aucun changement détecté
                            access_updated = True
                            access_error = "Aucune modification détectée dans Access"

                        cursor.close()
                        conn.close()
                    else:
                        access_error = f"Fichier Access introuvable: {access_path}"

                except pyodbc.Error as e:
                    access_error = f"Erreur Access: {str(e)}"
                except Exception as e:
                    access_error = f"Erreur inattendue: {str(e)}"

        # Retourner le résultat avec détails de débogage
        if access_updated:
            if access_error:
                # Mise à jour partielle (sans PERS)
                return JsonResponse({
                    'success': True,
                    'message': 'Modification enregistrée dans Django et Access (partielle)',
                    'access_updated': True,
                    'partial': True,
                    'warning': access_error
                })
            else:
                # Mise à jour complète
                return JsonResponse({
                    'success': True,
                    'message': 'Modification enregistrée dans Django et Access',
                    'access_updated': True
                })
        else:
            # Ajouter plus de détails pour le débogage
            debug_info = {
                'fichier_source': entry.fichier_source,
                'imported_by': str(entry.imported_by) if entry.imported_by else None,
                'access_path': access_path if 'access_path' in locals() else 'Non déterminé',
            }

            return JsonResponse({
                'success': True,
                'message': 'Modification enregistrée dans Django uniquement',
                'access_updated': False,
                'access_error': access_error,
                'access_payload': access_payload,
                'debug_info': debug_info,
                'warning': 'Le fichier Access n\'a pas pu ètre mis à jour'
            })

    except BaseDiameX.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Entrée introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["POST"])
def open_file_windows(request):
    """
    Ouvre un fichier avec l'application par défaut Windows via subprocess
    Contourne les restrictions du navigateur
    """
    import subprocess
    import os

    try:
        file_path = request.POST.get('file_path')

        if not file_path:
            return JsonResponse({'success': False, 'error': 'Aucun chemin fourni'})

        # Vérifier que le fichier existe
        if not os.path.exists(file_path):
            return JsonResponse({
                'success': False,
                'error': f'Fichier introuvable: {file_path}',
                'debug_info': {
                    'file_path': file_path,
                    'exists': os.path.exists(file_path)
                }
            })

        # Ouvrir avec l'application par défaut Windows
        try:
            # Méthode : os.startfile (Windows uniquement)
            os.startfile(file_path)
            return JsonResponse({'success': True, 'message': 'Fichier ouvert'})
        except AttributeError:
            # Fallback pour non-Windows
            subprocess.Popen(['xdg-open', file_path])
            return JsonResponse({'success': True, 'message': 'Fichier ouvert'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': f'Erreur lors de l\'ouverture: {str(e)}'})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def recoupement_planning(request):
    """
    Recoupement entre PlanningDetails et BaseDiameX
    Tous les PlanningDetails avec numeroDiameX DOIVENT ètre trouvés dans la comptabilité
    Clé: (numeroDiameX, BaseDiameX) <-> (ID, Prog)
    """
    # Filtres depuis GET
    filter_status = request.GET.get('status', '')  # ok, warning, error, missing
    filter_employe = request.GET.get('employe', '')
    filter_base = request.GET.get('base', '')
    filter_mois = request.GET.get('mois', '')

    # Récupérer tous les PlanningDetails avec numeroDiameX non null
    planning_details = PlanningDetail.objects.filter(
        numeroDiameX__isnull=False,
        BaseDiameX__isnull=False
    ).select_related(
        'designation',
        'planning',
        'planning__employe',
        'planning__ouvrage',  # [OK] Ajout pour fallback ouvrage
        'equipement_constitutif',
        'equipement_constitutif__ouvrage',
        'point_eau',
        'point_eau__ouvrage',
        'point_eau__parcelle',
        'point_eau__parcelle__village',
        'point_eau__parcelle__village__fokontany',
        'point_eau__parcelle__village__fokontany__commune'
    )
    organisation_ids = _get_user_scope_organisation_ids(request.user)
    if organisation_ids is not None:
        if organisation_ids:
            planning_details = planning_details.filter(
                planning__employe__base__organisation_id__in=organisation_ids
            )
        else:
            planning_details = planning_details.none()

    diamex_scope_qs = _get_diamex_scope_by_prog(request.user)

    # Appliquer filtre employe
    if filter_employe:
        planning_details = planning_details.filter(planning__employe__surnom__icontains=filter_employe)

    # Appliquer filtre base
    if filter_base:
        planning_details = planning_details.filter(BaseDiameX=filter_base)

    # Appliquer filtre mois
    if filter_mois:
        import pytz
        from django.utils import timezone as dj_timezone
        tz_madagascar = pytz.timezone('Indian/Antananarivo')

        try:
            year, month = filter_mois.split('-')
            year = int(year)
            month = int(month)

            # Filtrer en Python apres conversion timezone
            filtered_details = []
            for detail in planning_details:
                if detail.planning and detail.planning.date:
                    date_aware = detail.planning.date if detail.planning.date.tzinfo else dj_timezone.make_aware(detail.planning.date)
                    date_madagascar = date_aware.astimezone(tz_madagascar)
                    date_obj = date_madagascar.date()

                    if date_obj.year == year and date_obj.month == month:
                        filtered_details.append(detail)

            planning_details = filtered_details
        except (ValueError, AttributeError):
            pass  # Ignorer filtre mois invalide

    # Grouper par couple (numeroDiameX, BaseDiameX)
    recoupements = {}

    for detail in planning_details:
        key = (detail.numeroDiameX, detail.BaseDiameX)

        if key not in recoupements:
            # Déterminer l'ouvrage et la commune depuis le detail
            ouvrage = None
            commune = None

            # 1. Essayer via equipement_constitutif
            if detail.equipement_constitutif and detail.equipement_constitutif.ouvrage:
                ouvrage = detail.equipement_constitutif.ouvrage
            # 2. Essayer via point_eau
            elif detail.point_eau and detail.point_eau.ouvrage:
                ouvrage = detail.point_eau.ouvrage
            # 3. Fallback : utiliser l'ouvrage du Planning parent
            elif detail.planning and detail.planning.ouvrage:
                ouvrage = detail.planning.ouvrage

            # Obtenir la commune via point_eau â†’ parcelle â†’ village â†’ fokontany â†’ commune
            if detail.point_eau and detail.point_eau.parcelle:
                parcelle = detail.point_eau.parcelle
                if parcelle.village and parcelle.village.fokontany:
                    commune = parcelle.village.fokontany.commune
            # Fallback : essayer via l'ouvrage du Planning
            elif ouvrage:
                # Chercher un point d'eau de cet ouvrage pour obtenir la commune
                from apps.billing.models import PointEau
                pe_ouvrage = PointEau.objects.filter(
                    ouvrage=ouvrage,
                    parcelle__isnull=False,
                    parcelle__village__isnull=False,
                    parcelle__village__fokontany__isnull=False,
                    parcelle__village__fokontany__commune__isnull=False
                ).select_related(
                    'parcelle__village__fokontany__commune'
                ).first()
                if pe_ouvrage and pe_ouvrage.parcelle:
                    parcelle = pe_ouvrage.parcelle
                    if parcelle.village and parcelle.village.fokontany:
                        commune = parcelle.village.fokontany.commune

            recoupements[key] = {
                'numero_diamex': detail.numeroDiameX,
                'base_diamex': detail.BaseDiameX,
                'planning_details': [],
                'total_planning': Decimal('0'),
                'recettes_planning': Decimal('0'),  # Recettes uniquement
                'depenses_planning': Decimal('0'),  # Dépenses uniquement
                'comptabilite_in': None,
                'comptabilite_out': None,
                'comptabilite_solde': None,
                'comptabilite_entry': None,
                'ecart_recettes': None,
                'ecart_depenses': None,
                'ecart_total': None,
                'status': 'unknown',
                # Informations supplémentaires du premier détail (pour affichage)
                'employe': None,
                'date_planning': None,
                'nb_details': 0,
                'ouvrage': ouvrage,
                'commune': commune,
            }

        recoupements[key]['planning_details'].append(detail)
        recoupements[key]['total_planning'] += Decimal(str(detail.montant))
        recoupements[key]['nb_details'] += 1

        # Séparer recettes et dépenses
        if detail.designation.type_avance_caissiere == 'recette':
            recoupements[key]['recettes_planning'] += Decimal(str(detail.montant))
        else:
            # Tout ce qui n'est pas recette est considéré comme dépense
            recoupements[key]['depenses_planning'] += Decimal(str(detail.montant))

        # Récupérer info du premier détail pour affichage
        if recoupements[key]['employe'] is None and detail.planning:
            recoupements[key]['employe'] = detail.planning.employe
            recoupements[key]['date_planning'] = detail.planning.date

    # Pour chaque couple du planning, chercher l'entrée correspondante dans BaseDiameX
    for key, data in recoupements.items():
        numero, base = key

        # Chercher dans BaseDiameX: id_access = numeroDiameX, prog = BaseDiameX
        diamex_entry = diamex_scope_qs.filter(
            id_access=numero,
            prog=base
        ).first()

        if diamex_entry:
            data['comptabilite_entry'] = diamex_entry
            data['comptabilite_in'] = diamex_entry.montant_in
            data['comptabilite_out'] = diamex_entry.montant_out
            data['comptabilite_solde'] = diamex_entry.ccy  # IN - OUT

            # Calculer les écarts séparément
            # Recettes planning doivent égaler IN comptabilité
            data['ecart_recettes'] = data['recettes_planning'] - Decimal(str(data['comptabilite_in']))
            # Dépenses planning doivent égaler OUT comptabilité
            data['ecart_depenses'] = data['depenses_planning'] - Decimal(str(data['comptabilite_out']))
            # écart total
            data['ecart_total'] = data['ecart_recettes'] + data['ecart_depenses']

            # Déterminer le statut basé sur l'écart total
            if abs(data['ecart_total']) < Decimal('0.01'):  # Tolérance 1 centime
                data['status'] = 'ok'
            elif abs(data['ecart_total']) < Decimal('100'):
                data['status'] = 'warning'
            else:
                data['status'] = 'error'
        else:
            # CRITIQUE : Tous les PlanningDetails DOIVENT avoir une entrée compta
            data['status'] = 'missing'
            data['ecart_total'] = data['total_planning']

    # Convertir en liste et trier : d'abord les missing/error, puis par écart
    recoupements_list = sorted(
        recoupements.values(),
        key=lambda x: (
            0 if x['status'] == 'missing' else 1 if x['status'] == 'error' else 2,
            abs(x['ecart_total']) if x['ecart_total'] is not None else 0
        ),
        reverse=False
    )
    # Inverser pour avoir les plus gros écarts en premier
    recoupements_list = sorted(
        recoupements_list,
        key=lambda x: abs(x['ecart_total']) if x['ecart_total'] is not None else 0,
        reverse=True
    )

    # Appliquer filtre status APRES le calcul de toutes les stats
    if filter_status:
        recoupements_list = [r for r in recoupements_list if r['status'] == filter_status]

    # Regrouper par district â†’ commune â†’ ouvrage
    recoupements_par_district = {}
    for rec in recoupements_list:
        # Récupérer district via commune
        if rec['commune']:
            district_id = str(rec['commune'].district.id) if rec['commune'].district else 'sans_district'
            district_nom = rec['commune'].district.nom_district if rec['commune'].district else 'Sans district'
        else:
            district_id = 'sans_district'
            district_nom = 'Sans district'

        commune_id = str(rec['commune'].id) if rec['commune'] else 'sans_commune'
        commune_nom = rec['commune'].nom_commune if rec['commune'] else 'Sans commune'

        # Créer le district si nécessaire
        if district_id not in recoupements_par_district:
            recoupements_par_district[district_id] = {
                'district_nom': district_nom,
                'communes': {},
                'total_recoupements': 0
            }

        # Créer la commune si nécessaire
        if commune_id not in recoupements_par_district[district_id]['communes']:
            recoupements_par_district[district_id]['communes'][commune_id] = {
                'commune_nom': commune_nom,
                'ouvrages': {},
                'total_recoupements': 0
            }

        ouvrage_id = str(rec['ouvrage'].id) if rec['ouvrage'] else 'sans_ouvrage'
        ouvrage_nom = rec['ouvrage'].nom_ouvrage if rec['ouvrage'] else 'Sans ouvrage'

        # Créer l'ouvrage si nécessaire
        if ouvrage_id not in recoupements_par_district[district_id]['communes'][commune_id]['ouvrages']:
            recoupements_par_district[district_id]['communes'][commune_id]['ouvrages'][ouvrage_id] = {
                'ouvrage_nom': ouvrage_nom,
                'recoupements': []
            }

        # Ajouter le recoupement
        recoupements_par_district[district_id]['communes'][commune_id]['ouvrages'][ouvrage_id]['recoupements'].append(rec)

        # Incrémenter les compteurs
        recoupements_par_district[district_id]['total_recoupements'] += 1
        recoupements_par_district[district_id]['communes'][commune_id]['total_recoupements'] += 1

    # Statistiques GLOBALES (avant filtre status pour afficher totaux)
    stats_global = {
        'total': len(recoupements_list) if not filter_status else sum(1 for r in recoupements.values()),
        'ok': sum(1 for r in recoupements.values() if r['status'] == 'ok'),
        'warning': sum(1 for r in recoupements.values() if r['status'] == 'warning'),
        'error': sum(1 for r in recoupements.values() if r['status'] == 'error'),
        'missing': sum(1 for r in recoupements.values() if r['status'] == 'missing'),
    }

    # Statistiques FILTREES (apres tous les filtres)
    stats_filtered = {
        'total': len(recoupements_list),
        'ok': sum(1 for r in recoupements_list if r['status'] == 'ok'),
        'warning': sum(1 for r in recoupements_list if r['status'] == 'warning'),
        'error': sum(1 for r in recoupements_list if r['status'] == 'error'),
        'missing': sum(1 for r in recoupements_list if r['status'] == 'missing'),
    }

    # Pagination (50 par page)
    paginator = Paginator(recoupements_list, 50)
    page_number = request.GET.get('page', 1)

    # Valider le numéro de page
    try:
        page_number = int(page_number)
        if page_number < 1:
            page_number = 1
    except (ValueError, TypeError):
        page_number = 1

    page_obj = paginator.get_page(page_number)

    # Listes pour les filtres
    employes_qs = PlanningDetail.objects.filter(
        numeroDiameX__isnull=False,
        BaseDiameX__isnull=False,
        planning__employe__isnull=False
    )
    if organisation_ids is not None:
        if organisation_ids:
            employes_qs = employes_qs.filter(
                planning__employe__base__organisation_id__in=organisation_ids
            )
        else:
            employes_qs = employes_qs.none()

    employes_map = {}
    for detail in employes_qs.select_related(
        'planning__employe__base',
        'planning__employe__poste',
    ):
        employe = detail.planning.employe if detail.planning else None
        filter_value = getattr(employe, 'surnom', None) if employe else None
        if not filter_value:
            continue
        employes_map.setdefault(filter_value, {
            'id': filter_value,
            'display_name': filter_value,
            'base_name': employe.base.nom_base if employe.base else 'Sans base',
            'poste_name': employe.poste.nom_poste if employe.poste else 'Sans poste',
        })
    employes_list = list(employes_map.values())

    bases_qs = PlanningDetail.objects.filter(
        numeroDiameX__isnull=False,
        BaseDiameX__isnull=False
    )
    if organisation_ids is not None:
        if organisation_ids:
            bases_qs = bases_qs.filter(
                planning__employe__base__organisation_id__in=organisation_ids
            )
        else:
            bases_qs = bases_qs.none()

    bases_list = sorted(set(
        detail.BaseDiameX
        for detail in bases_qs
        if detail.BaseDiameX
    ))

    # ===== VéRIFICATION INVERSE : DiameX â†’ Application =====
    # Pour chaque ligne DiameX avec les comptes autorisés pour plannings_details,
    # vérifier qu'elle correspond à des PlanningDetails
    from apps.accounting.helpers_recoupement import verifier_recoupement_inverse
    from apps.organization.models import CompteTable

    # Récupérer les filtres pour vérification inverse
    filter_prog_inverse = request.GET.get('prog_inverse', '')
    filter_mois_inverse = request.GET.get('mois_inverse', '')

    # Récupérer dynamiquement les comptes autorisés pour plannings_details depuis CompteTable
    comptes_planning = CompteTable.objects.filter(
        nom_table='plannings_details',
        actif=True
    ).select_related('compte').values_list('compte__compte', flat=True)

    comptes_cat_planning = list(comptes_planning)

    # Filtrer par bases si demandé
    fichiers_sources = None
    if filter_base:
        fichiers_sources = [filter_base]

    # Appeler la fonction d'aide pour vérification inverse
    resultats_inverses = verifier_recoupement_inverse(
        comptes_cat=comptes_cat_planning,
        fichiers_sources=fichiers_sources,
        type_recoupement='planning',
        allowed_progs=_get_allowed_diamex_progs(request.user)
    )

    # Appliquer filtres sur les résultats inverses
    recoupements_inverses_list = resultats_inverses['recoupements_inverses']

    # Filtre par Prog
    if filter_prog_inverse:
        recoupements_inverses_list = [r for r in recoupements_inverses_list if r['prog'] == filter_prog_inverse]

    # Filtre par Mois
    if filter_mois_inverse:
        try:
            year, month = filter_mois_inverse.split('-')
            year = int(year)
            month = int(month)
            recoupements_inverses_list = [
                r for r in recoupements_inverses_list
                if r['date_m'] and r['date_m'].year == year and r['date_m'].month == month
            ]
        except (ValueError, AttributeError):
            pass

    # Regrouper par Prog
    recoupements_inverses_par_prog = {}
    for rec in recoupements_inverses_list:
        prog = rec['prog'] or 'Sans prog'

        if prog not in recoupements_inverses_par_prog:
            recoupements_inverses_par_prog[prog] = {
                'prog': prog,
                'recoupements': [],
                'total_recoupements': 0,
                'missing': 0,
                'error': 0,
                'warning': 0,
                'ok': 0
            }

        recoupements_inverses_par_prog[prog]['recoupements'].append(rec)
        recoupements_inverses_par_prog[prog]['total_recoupements'] += 1
        recoupements_inverses_par_prog[prog][rec['status']] += 1

    # Listes pour filtres
    progs_list_inverse = sorted(set(r['prog'] for r in resultats_inverses['recoupements_inverses'] if r['prog']))

    # Paginer les résultats inverses (50 par page)
    recoupements_inverses_list_for_pagination = recoupements_inverses_list
    paginator_inverse = Paginator(recoupements_inverses_list, 50)
    page_number_inverse = request.GET.get('page_inverse', 1)

    try:
        page_number_inverse = int(page_number_inverse)
        if page_number_inverse < 1:
            page_number_inverse = 1
    except (ValueError, TypeError):
        page_number_inverse = 1

    page_obj_inverse = paginator_inverse.get_page(page_number_inverse)

    return render(request, 'accounting/recoupement_planning.html', {
        'page_obj': page_obj,
        'recoupements': page_obj,
        'recoupements_par_district': recoupements_par_district,  # Changé de commune à district
        'stats': stats_filtered,
        'stats_global': stats_global,
        'employes_list': employes_list,
        'bases_list': bases_list,
        # Nouveaux contextes pour vérification inverse
        'recoupements_inverses': page_obj_inverse,
        'recoupements_inverses_par_prog': recoupements_inverses_par_prog,  # [OK] Ajouté
        'stats_inverses': resultats_inverses['stats'],
        'comptes_cat_planning': comptes_cat_planning,  # Pour affichage dans le template
        'progs_list_inverse': progs_list_inverse,  # [OK] Ajouté
        'filter_prog_inverse': filter_prog_inverse,  # [OK] Ajouté
        'filter_mois_inverse': filter_mois_inverse,  # [OK] Ajouté
    })


@login_required
def recoupement_achats(request):
    """
    Recoupement entre Achats (Purchase) et BaseDiameX
    Tous les Achats avec numeroDiameX DOIVENT ètre trouvés dans la comptabilité
    Clé: (numeroDiameX, baseDiameX) <-> (ID, Prog)
    """
    from apps.inventory.models import Purchase
    from decimal import Decimal
    from django.core.paginator import Paginator

    # Filtres depuis GET
    filter_status = request.GET.get('status', '')  # ok, warning, error, missing
    filter_fournisseur = request.GET.get('fournisseur', '')
    filter_base = request.GET.get('base', '')
    filter_mois = request.GET.get('mois', '')

    # Récupérer tous les achats avec numeroDiameX non null
    organisation_id = _get_user_organisation_id(request.user)
    organisation_ids = _get_user_scope_organisation_ids(request.user)
    diamex_scope_qs = _get_diamex_scope_by_prog(request.user)

    achats = Purchase.objects.filter(
        numeroDiameX__isnull=False,
        baseDiameX__isnull=False
    ).select_related(
        'fournisseur',
        'magasin',
        'magasin__base',
        'magasin__base__organisation',
        'ordered_by'
    ).prefetch_related('purchase_items__designation')
    if organisation_ids is not None:
        if organisation_ids:
            achats = achats.filter(magasin__base__organisation_id__in=organisation_ids)
        else:
            achats = achats.none()

    # Appliquer filtre fournisseur
    if filter_fournisseur:
        achats = achats.filter(fournisseur__nom_fournisseur__icontains=filter_fournisseur)

    # Appliquer filtre base
    if filter_base:
        achats = achats.filter(baseDiameX=filter_base)

    # Appliquer filtre mois
    if filter_mois:
        try:
            year, month = filter_mois.split('-')
            year = int(year)
            month = int(month)
            achats = achats.filter(purchase_date__year=year, purchase_date__month=month)
        except (ValueError, AttributeError):
            pass  # Ignorer filtre mois invalide

    # Grouper par couple (numeroDiameX, baseDiameX)
    recoupements = {}

    for achat in achats:
        key = (achat.numeroDiameX, achat.baseDiameX)

        if key not in recoupements:
            recoupements[key] = {
                'numero_diamex': achat.numeroDiameX,
                'base_diamex': achat.baseDiameX,
                'achats': [],
                'total_achats': Decimal('0'),
                'comptabilite_in': None,
                'comptabilite_out': None,
                'comptabilite_solde': None,
                'comptabilite_entry': None,
                'ecart_total': None,
                'status': 'unknown',
                # Informations supplémentaires du premier achat (pour affichage)
                'fournisseur': None,
                'date_achat': None,
                'nb_achats': 0,
                'organisation': None,
            }

        recoupements[key]['achats'].append(achat)
        recoupements[key]['total_achats'] += Decimal(str(achat.total_amount))
        recoupements[key]['nb_achats'] += 1

        # Récupérer info du premier achat pour affichage
        if recoupements[key]['fournisseur'] is None:
            recoupements[key]['fournisseur'] = achat.fournisseur
            recoupements[key]['date_achat'] = achat.purchase_date
            if achat.magasin and achat.magasin.base:
                recoupements[key]['organisation'] = achat.magasin.base.organisation

    # Pour chaque couple, chercher l'entrée correspondante dans BaseDiameX
    for key, data in recoupements.items():
        numero, base = key

        # Chercher dans BaseDiameX: id_access = numeroDiameX, prog = baseDiameX
        try:
            numero_int = int(str(numero).strip())
        except (TypeError, ValueError):
            numero_int = None
        diamex_entry = None
        if numero_int is not None and base:
            diamex_entry = diamex_scope_qs.filter(
                id_access=numero_int,
                prog=base
            ).first()

        if diamex_entry:
            data['comptabilite_entry'] = diamex_entry
            data['comptabilite_in'] = diamex_entry.montant_in
            data['comptabilite_out'] = diamex_entry.montant_out
            data['comptabilite_solde'] = diamex_entry.ccy  # IN - OUT

            # Pour les achats, c'est toujours une dépense (OUT)
            # L'écart = total_achats - comptabilite_out
            data['ecart_total'] = data['total_achats'] - Decimal(str(data['comptabilite_out']))

            # Déterminer le statut basé sur l'écart
            if abs(data['ecart_total']) < Decimal('0.01'):  # Tolérance 1 centime
                data['status'] = 'ok'
            elif abs(data['ecart_total']) < Decimal('100'):
                data['status'] = 'warning'
            else:
                data['status'] = 'error'
        else:
            # CRITIQUE : Tous les achats DOIVENT avoir une entrée compta
            data['status'] = 'missing'
            data['ecart_total'] = data['total_achats']

    # Convertir en liste et trier par écart décroissant
    recoupements_list = sorted(
        recoupements.values(),
        key=lambda x: abs(x['ecart_total']) if x['ecart_total'] is not None else 0,
        reverse=True
    )

    # Appliquer filtre status APRES le calcul de toutes les stats
    if filter_status:
        recoupements_list = [r for r in recoupements_list if r['status'] == filter_status]

    # Regrouper par Base DiameX
    recoupements_par_base = {}
    for rec in recoupements_list:
        base_id = rec['base_diamex'] or 'sans_base'
        base_nom = rec['base_diamex'] or 'Sans base'

        if base_id not in recoupements_par_base:
            recoupements_par_base[base_id] = {
                'base_nom': base_nom,
                'recoupements': [],
                'total_recoupements': 0,
                'ok': 0,
                'warning': 0,
                'error': 0,
                'missing': 0
            }

        recoupements_par_base[base_id]['recoupements'].append(rec)
        recoupements_par_base[base_id]['total_recoupements'] += 1
        recoupements_par_base[base_id][rec['status']] += 1

    # Statistiques GLOBALES (avant filtre status)
    stats_global = {
        'total': len(recoupements_list) if not filter_status else sum(1 for r in recoupements.values()),
        'ok': sum(1 for r in recoupements.values() if r['status'] == 'ok'),
        'warning': sum(1 for r in recoupements.values() if r['status'] == 'warning'),
        'error': sum(1 for r in recoupements.values() if r['status'] == 'error'),
        'missing': sum(1 for r in recoupements.values() if r['status'] == 'missing'),
    }

    # Statistiques FILTREES
    stats_filtered = {
        'total': len(recoupements_list),
        'ok': sum(1 for r in recoupements_list if r['status'] == 'ok'),
        'warning': sum(1 for r in recoupements_list if r['status'] == 'warning'),
        'error': sum(1 for r in recoupements_list if r['status'] == 'error'),
        'missing': sum(1 for r in recoupements_list if r['status'] == 'missing'),
    }

    # Pagination (50 par page)
    paginator = Paginator(recoupements_list, 50)
    page_number = request.GET.get('page', 1)

    # Valider le numéro de page
    try:
        page_number = int(page_number)
        if page_number < 1:
            page_number = 1
    except (ValueError, TypeError):
        page_number = 1

    page_obj = paginator.get_page(page_number)

    # Listes pour les filtres
    achats_filtres_qs = Purchase.objects.filter(
        numeroDiameX__isnull=False,
        baseDiameX__isnull=False
    )
    if organisation_ids is not None:
        if organisation_ids:
            achats_filtres_qs = achats_filtres_qs.filter(
                magasin__base__organisation_id__in=organisation_ids
            )
        else:
            achats_filtres_qs = achats_filtres_qs.none()

    fournisseurs_list = sorted(set(
        achat.fournisseur.nom_fournisseur
        for achat in achats_filtres_qs.filter(
            fournisseur__isnull=False
        ).select_related('fournisseur')
        if achat.fournisseur
    ))

    bases_list = sorted(set(
        achat.baseDiameX
        for achat in achats_filtres_qs
        if achat.baseDiameX
    ))

    # ===== VéRIFICATION INVERSE : DiameX â†’ Application (Achats) =====
    from apps.accounting.helpers_recoupement import verifier_recoupement_inverse
    from apps.organization.models import CompteTable

    # Récupérer les filtres pour vérification inverse
    filter_prog_inverse = request.GET.get('prog_inverse', '')
    filter_mois_inverse = request.GET.get('mois_inverse', '')

    # Récupérer dynamiquement les comptes autorisés pour achats depuis CompteTable
    comptes_achats = CompteTable.objects.filter(
        nom_table='achats',
        actif=True
    ).select_related('compte').values_list('compte__compte', flat=True)

    comptes_cat_achats = list(comptes_achats)

    # Filtrer par bases si demandé
    fichiers_sources = None
    if filter_base:
        fichiers_sources = [filter_base]

    # Appeler la fonction d'aide pour vérification inverse
    resultats_inverses = verifier_recoupement_inverse(
        comptes_cat=comptes_cat_achats,
        fichiers_sources=fichiers_sources,
        type_recoupement='achats',
        allowed_progs=_get_allowed_diamex_progs(request.user)
    )

    # Appliquer filtres sur les résultats inverses
    recoupements_inverses_list = resultats_inverses['recoupements_inverses']

    # Filtre par Prog
    if filter_prog_inverse:
        recoupements_inverses_list = [r for r in recoupements_inverses_list if r['prog'] == filter_prog_inverse]

    # Filtre par Mois
    if filter_mois_inverse:
        try:
            year, month = filter_mois_inverse.split('-')
            year = int(year)
            month = int(month)
            recoupements_inverses_list = [
                r for r in recoupements_inverses_list
                if r['date_m'] and r['date_m'].year == year and r['date_m'].month == month
            ]
        except (ValueError, AttributeError):
            pass

    # Regrouper par Prog
    recoupements_inverses_par_prog = {}
    for rec in recoupements_inverses_list:
        prog = rec['prog'] or 'Sans prog'

        if prog not in recoupements_inverses_par_prog:
            recoupements_inverses_par_prog[prog] = {
                'prog': prog,
                'recoupements': [],
                'total_recoupements': 0,
                'missing': 0,
                'error': 0,
                'warning': 0,
                'ok': 0
            }

        recoupements_inverses_par_prog[prog]['recoupements'].append(rec)
        recoupements_inverses_par_prog[prog]['total_recoupements'] += 1
        recoupements_inverses_par_prog[prog][rec['status']] += 1

    # Listes pour filtres
    progs_list_inverse = sorted(set(r['prog'] for r in resultats_inverses['recoupements_inverses'] if r['prog']))

    return render(request, 'accounting/recoupement_achats.html', {
        'page_obj': page_obj,
        'recoupements': page_obj,
        'recoupements_par_base': recoupements_par_base,  # [OK] Changé de organisation à base
        'stats': stats_filtered,
        'stats_global': stats_global,
        'fournisseurs_list': fournisseurs_list,
        'bases_list': bases_list,
        # Nouveaux contextes pour vérification inverse
        'recoupements_inverses_par_prog': recoupements_inverses_par_prog,
        'stats_inverses': resultats_inverses['stats'],
        'comptes_cat_achats': comptes_cat_achats,
        'progs_list_inverse': progs_list_inverse,
        'filter_prog_inverse': filter_prog_inverse,
        'filter_mois_inverse': filter_mois_inverse,
    })


@login_required
def recoupement_demandes_bp(request):
    """
    Recoupement entre Demandes BP (PointEau) et BaseDiameX
    Clé: (numerodiamexdemande, basediamexdemande) <-> (id_access, prog)
    """
    from apps.billing.models import PointEau

    # Filtres depuis GET
    filter_status = request.GET.get('status', '')
    filter_point_eau = request.GET.get('point_eau', '')
    filter_base = request.GET.get('base', '')
    filter_mois_paiement = request.GET.get('mois_paiement', '')

    organisation_id = _get_user_organisation_id(request.user)
    organisation_ids = _get_user_scope_organisation_ids(request.user)
    diamex_scope_qs = _get_diamex_scope_by_prog(request.user)

    # Récupérer tous les PointsEau avec demande BP (numerodiamexdemande non null)
    points_eau = PointEau.objects.filter(
        numerodiamexdemande__isnull=False,
        basediamexdemande__isnull=False
    ).exclude(
        basediamexdemande=''
    ).select_related(
        'ouvrage',
        'type_point_eau',
        'parcelle',
        'parcelle__village',
        'parcelle__village__fokontany',
        'parcelle__village__fokontany__commune'
    )
    points_eau = _scope_queryset_by_gestionnaire_ids(
        points_eau,
        request.user,
        'ouvrage__modalites_gestion__'
    )

    # Appliquer filtres
    if filter_point_eau:
        points_eau = points_eau.filter(nomabonne__icontains=filter_point_eau)

    if filter_base:
        points_eau = points_eau.filter(basediamexdemande=filter_base)

    if filter_mois_paiement:
        # Format: YYYY-MM
        try:
            year, month = filter_mois_paiement.split('-')
            points_eau = points_eau.filter(
                datepaiementdemande__year=int(year),
                datepaiementdemande__month=int(month)
            )
        except (ValueError, AttributeError):
            pass  # Ignorer si format invalide

    # Grouper par couple (numerodiamexdemande, basediamexdemande)
    recoupements = {}

    for pe in points_eau:
        key = (pe.numerodiamexdemande, pe.basediamexdemande)

        if key not in recoupements:
            # Déterminer la commune via parcelle â†’ village â†’ fokontany â†’ commune
            commune = None
            if pe.parcelle and pe.parcelle.village and pe.parcelle.village.fokontany:
                commune = pe.parcelle.village.fokontany.commune

            recoupements[key] = {
                'numero_diamex': pe.numerodiamexdemande,
                'base_diamex': pe.basediamexdemande,
                'points_eau': [],
                'total_demandes': Decimal('0'),
                'comptabilite_in': None,
                'comptabilite_out': None,
                'comptabilite_solde': None,
                'comptabilite_entry': None,
                'ecart': None,
                'status': 'unknown',
                'point_eau': None,
                'ouvrage': None,
                'commune': commune,
                'nb_points_eau': 0,
                'scan': None,
            }

        recoupements[key]['points_eau'].append(pe)
        montant_demande = Decimal(str(pe.montant_demande_bp)) if pe.montant_demande_bp else Decimal('0')
        recoupements[key]['total_demandes'] += montant_demande
        recoupements[key]['nb_points_eau'] += 1

        if recoupements[key]['point_eau'] is None:
            recoupements[key]['point_eau'] = pe
            recoupements[key]['ouvrage'] = pe.ouvrage

    # Chercher dans BaseDiameX
    from apps.employees.models import EmployeBaseDiameX

    for key, data in recoupements.items():
        numero, base = key

        try:
            numero_int = int(str(numero).strip())
        except (TypeError, ValueError):
            numero_int = None

        diamex_entry = None
        if numero_int is not None and base:
            diamex_entry = diamex_scope_qs.filter(
                id_access=numero_int,
                prog=base
            ).first()

        if diamex_entry:
            data['comptabilite_entry'] = diamex_entry
            data['comptabilite_in'] = diamex_entry.montant_in
            data['comptabilite_out'] = diamex_entry.montant_out
            data['comptabilite_solde'] = diamex_entry.ccy

            # Récupérer le scan
            data['scan'] = None
            if diamex_entry.scan and diamex_entry.fichier_source:
                employe_base = EmployeBaseDiameX.objects.filter(
                    base_diamex=diamex_entry.fichier_source
                )
                if organisation_ids is not None:
                    if organisation_ids:
                        employe_base = employe_base.filter(
                            employe__base__organisation_id__in=organisation_ids
                        )
                    else:
                        employe_base = employe_base.none()
                employe_base = employe_base.first()

                if employe_base and employe_base.chemin_base_diamex:
                    scan_relatif = diamex_entry.scan
                    if scan_relatif.startswith('.'):
                        scan_relatif = scan_relatif[1:]
                    if scan_relatif.startswith(employe_base.chemin_base_diamex):
                        data['scan'] = scan_relatif
                    else:
                        data['scan'] = employe_base.chemin_base_diamex + scan_relatif

            # Calculer écart (demandes sont des recettes IN)
            data['ecart'] = data['total_demandes'] - Decimal(str(data['comptabilite_in']))

            if abs(data['ecart']) < Decimal('0.01'):
                data['status'] = 'ok'
            elif abs(data['ecart']) < Decimal('100'):
                data['status'] = 'warning'
            else:
                data['status'] = 'error'
        else:
            data['status'] = 'missing'
            data['ecart'] = data['total_demandes']

    # Convertir en liste et trier
    recoupements_list = sorted(
        recoupements.values(),
        key=lambda x: abs(x['ecart']) if x['ecart'] is not None else 0,
        reverse=True
    )

    if filter_status:
        recoupements_list = [r for r in recoupements_list if r['status'] == filter_status]

    # Stats globales (avant filtrage par status)
    stats_global = {
        'total': len(list(recoupements.values())),
        'ok': sum(1 for r in recoupements.values() if r['status'] == 'ok'),
        'warning': sum(1 for r in recoupements.values() if r['status'] == 'warning'),
        'error': sum(1 for r in recoupements.values() if r['status'] == 'error'),
        'missing': sum(1 for r in recoupements.values() if r['status'] == 'missing'),
    }

    # Regrouper par Base DiameX
    recoupements_par_base = {}
    for rec in recoupements_list:
        base_id = rec['base_diamex'] or 'sans_base'
        base_nom = rec['base_diamex'] or 'Sans base'

        if base_id not in recoupements_par_base:
            recoupements_par_base[base_id] = {
                'base_nom': base_nom,
                'recoupements': [],
                'total_recoupements': 0,
                'ok': 0,
                'warning': 0,
                'error': 0,
                'missing': 0
            }

        recoupements_par_base[base_id]['recoupements'].append(rec)
        recoupements_par_base[base_id]['total_recoupements'] += 1
        recoupements_par_base[base_id][rec['status']] += 1

    # Statistiques
    stats = {
        'total': len(recoupements_list),
        'ok': sum(1 for r in recoupements_list if r['status'] == 'ok'),
        'warning': sum(1 for r in recoupements_list if r['status'] == 'warning'),
        'error': sum(1 for r in recoupements_list if r['status'] == 'error'),
        'missing': sum(1 for r in recoupements_list if r['status'] == 'missing'),
    }

    # Liste des bases uniques pour le filtre
    bases_list = sorted(set(r['base_diamex'] for r in recoupements.values() if r['base_diamex']))

    # ===== VéRIFICATION INVERSE : DiameX â†’ Application (Demandes BP) =====
    from apps.accounting.helpers_recoupement import verifier_recoupement_inverse
    from apps.organization.models import CompteTable

    filter_prog_inverse = request.GET.get('prog_inverse', '')
    filter_mois_inverse = request.GET.get('mois_inverse', '')

    comptes_demandes = CompteTable.objects.filter(
        nom_table='points_eau_demandes',
        actif=True
    ).select_related('compte').values_list('compte__compte', flat=True)

    comptes_cat_demandes = list(comptes_demandes)

    fichiers_sources = None
    if filter_base:
        fichiers_sources = [filter_base]

    resultats_inverses = verifier_recoupement_inverse(
        comptes_cat=comptes_cat_demandes,
        fichiers_sources=fichiers_sources,
        type_recoupement='demandes_bp',
        allowed_progs=_get_allowed_diamex_progs(request.user)
    )

    recoupements_inverses_list = resultats_inverses['recoupements_inverses']

    if filter_prog_inverse:
        recoupements_inverses_list = [r for r in recoupements_inverses_list if r['prog'] == filter_prog_inverse]

    if filter_mois_inverse:
        try:
            year, month = filter_mois_inverse.split('-')
            year = int(year)
            month = int(month)
            recoupements_inverses_list = [
                r for r in recoupements_inverses_list
                if r['date_m'] and r['date_m'].year == year and r['date_m'].month == month
            ]
        except (ValueError, AttributeError):
            pass

    recoupements_inverses_par_prog = {}
    for rec in recoupements_inverses_list:
        prog = rec['prog'] or 'Sans prog'
        if prog not in recoupements_inverses_par_prog:
            recoupements_inverses_par_prog[prog] = {
                'prog': prog,
                'recoupements': [],
                'total_recoupements': 0,
                'missing': 0,
                'error': 0,
                'warning': 0,
                'ok': 0
            }
        recoupements_inverses_par_prog[prog]['recoupements'].append(rec)
        recoupements_inverses_par_prog[prog]['total_recoupements'] += 1
        recoupements_inverses_par_prog[prog][rec['status']] += 1

    progs_list_inverse = sorted(set(r['prog'] for r in resultats_inverses['recoupements_inverses'] if r['prog']))

    context = {
        'recoupements': recoupements_list,
        'recoupements_par_base': recoupements_par_base,
        'stats': stats,
        'stats_global': stats_global,
        'bases_list': bases_list,
        'filter_status': filter_status,
        'filter_point_eau': filter_point_eau,
        'filter_base': filter_base,
        'filter_mois_paiement': filter_mois_paiement,
        # Inverse verification contexts
        'recoupements_inverses_par_prog': recoupements_inverses_par_prog,
        'stats_inverses': resultats_inverses['stats'],
        'comptes_cat_demandes': comptes_cat_demandes,
        'progs_list_inverse': progs_list_inverse,
        'filter_prog_inverse': filter_prog_inverse,
        'filter_mois_inverse': filter_mois_inverse,
        'type_recoupement': 'demandes_bp',
        'titre': 'Recoupement Demandes BP'
    }

    return render(request, 'accounting/recoupement_generic.html', context)


@csrf_exempt
@require_http_methods(["GET"])
def api_get_points_eau_demande_bp(request):
    """API pour récupérer les points d'eau par numéro et base DiameX demande"""
    from apps.billing.models import PointEau
    import json

    numero = request.GET.get('numero')
    base = request.GET.get('base')

    if not numero or not base:
        return JsonResponse({'success': False, 'error': 'Numéro et base requis'}, status=400)

    try:
        points_eau = PointEau.objects.filter(
            numerodiamexdemande=numero,
            basediamexdemande=base
        ).select_related('ouvrage', 'type_point_eau')

        data = []
        for pe in points_eau:
            data.append({
                'id': str(pe.id),
                'nomabonne': pe.nomabonne or '',
                'idxls': pe.idxls or '',
                'code_point_eau': pe.code_point_eau or '',
                'ouvrage_nom': pe.ouvrage.nom_ouvrage if pe.ouvrage else '',
                'ouvrage_id': str(pe.ouvrage.id) if pe.ouvrage else '',
                'numerodiamexdemande': pe.numerodiamexdemande or '',
                'basediamexdemande': pe.basediamexdemande or '',
                'montant_demande_bp': float(pe.montant_demande_bp) if pe.montant_demande_bp else 0,
                'datebranchement': pe.datebranchement.strftime('%Y-%m-%d') if pe.datebranchement else None,
                'datepaiementdemande': pe.datepaiementdemande.strftime('%Y-%m-%d') if pe.datepaiementdemande else None,
            })

        return JsonResponse({'success': True, 'points_eau': data})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_update_point_eau_demande_bp(request):
    """API pour mettre à jour un point d'eau (demande BP)"""
    from apps.billing.models import PointEau
    import json

    try:
        data = json.loads(request.body)
        point_eau_id = data.get('point_eau_id')

        if not point_eau_id:
            return JsonResponse({'success': False, 'error': 'ID point d\'eau requis'}, status=400)

        pe = PointEau.objects.get(id=point_eau_id)

        # Mise à jour des champs
        if 'nomabonne' in data:
            pe.nomabonne = data['nomabonne']
        if 'numerodiamexdemande' in data:
            pe.numerodiamexdemande = data['numerodiamexdemande']
        if 'basediamexdemande' in data:
            pe.basediamexdemande = data['basediamexdemande']
        if 'montant_demande_bp' in data:
            from decimal import Decimal
            pe.montant_demande_bp = Decimal(str(data['montant_demande_bp']))

        pe.save()

        return JsonResponse({
            'success': True,
            'message': 'Point d\'eau mis à jour avec succès'
        })
    except PointEau.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Point d\'eau introuvable'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
@login_required
def api_get_points_eau_devis_bp(request):
    """API pour récupérer les points d'eau par numéro et base DiameX devis"""
    from apps.billing.models import PointEau
    import json

    numero = request.GET.get('numero')
    base = request.GET.get('base')

    if not numero or not base:
        return JsonResponse({'success': False, 'error': 'Numéro et base requis'}, status=400)

    try:
        points_eau = PointEau.objects.filter(
            numerodiamexdevis=numero,
            basediamexdevis=base
        ).select_related('ouvrage', 'type_point_eau')
        organisation_id = _get_user_organisation_id(request.user)
        points_eau = _scope_queryset_by_gestionnaire_ids(
            points_eau,
            request.user,
            'ouvrage__modalites_gestion__'
        )

        data = []
        for pe in points_eau:
            data.append({
                'id': str(pe.id),
                'nomabonne': pe.nomabonne or '',
                'idxls': pe.idxls or '',
                'code_point_eau': pe.code_point_eau or '',
                'ouvrage_nom': pe.ouvrage.nom_ouvrage if pe.ouvrage else '',
                'ouvrage_id': str(pe.ouvrage.id) if pe.ouvrage else '',
                'numerodiamexdevis': pe.numerodiamexdevis or '',
                'basediamexdevis': pe.basediamexdevis or '',
                'montantdevispaye': float(pe.montantdevispaye) if pe.montantdevispaye else 0,
                'datebranchement': pe.datebranchement.strftime('%Y-%m-%d') if pe.datebranchement else None,
                'datepaiementdevis': pe.datepaiementdevis.strftime('%Y-%m-%d') if pe.datepaiementdevis else None,
            })

        return JsonResponse({'success': True, 'points_eau': data})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_update_point_eau_devis_bp(request):
    """API pour mettre à jour un point d'eau (devis BP)"""
    from apps.billing.models import PointEau
    import json

    try:
        data = json.loads(request.body)
        point_eau_id = data.get('point_eau_id')

        if not point_eau_id:
            return JsonResponse({'success': False, 'error': 'ID point d\'eau requis'}, status=400)

        pe_qs = PointEau.objects.filter(id=point_eau_id)
        organisation_id = _get_user_organisation_id(request.user)
        pe_qs = _scope_queryset_by_gestionnaire_ids(
            pe_qs,
            request.user,
            'ouvrage__modalites_gestion__'
        )
        pe = pe_qs.get()

        # Mise à jour des champs
        if 'nomabonne' in data:
            pe.nomabonne = data['nomabonne']
        if 'numerodiamexdevis' in data:
            pe.numerodiamexdevis = data['numerodiamexdevis']
        if 'basediamexdevis' in data:
            pe.basediamexdevis = data['basediamexdevis']
        if 'montantdevispaye' in data:
            from decimal import Decimal
            pe.montantdevispaye = Decimal(str(data['montantdevispaye']))

        pe.save()

        return JsonResponse({
            'success': True,
            'message': 'Point d\'eau mis à jour avec succès'
        })
    except PointEau.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Point d\'eau introuvable'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def recoupement_devis_bp(request):
    """
    Recoupement entre Devis BP (PointEau) et BaseDiameX
    Clé: (numerodiamexdevis, basediamexdevis) <-> (id_access, prog)
    """
    from apps.billing.models import PointEau

    filter_status = request.GET.get('status', '')
    filter_point_eau = request.GET.get('point_eau', '')
    filter_base = request.GET.get('base', '')
    filter_mois_paiement = request.GET.get('mois_paiement', '')

    organisation_ids = _get_user_scope_organisation_ids(request.user)
    diamex_scope_qs = _get_diamex_scope_by_prog(request.user)

    points_eau = PointEau.objects.filter(
        numerodiamexdevis__isnull=False,
        basediamexdevis__isnull=False
    ).select_related(
        'ouvrage',
        'type_point_eau',
        'parcelle',
        'parcelle__village',
        'parcelle__village__fokontany',
        'parcelle__village__fokontany__commune'
    )
    points_eau = _scope_queryset_by_gestionnaire_ids(
        points_eau,
        request.user,
        'ouvrage__modalites_gestion__'
    )

    if filter_point_eau:
        points_eau = points_eau.filter(nomabonne__icontains=filter_point_eau)

    if filter_base:
        points_eau = points_eau.filter(basediamexdevis=filter_base)

    if filter_mois_paiement:
        # Format: YYYY-MM
        try:
            year, month = filter_mois_paiement.split('-')
            points_eau = points_eau.filter(
                datepaiementdevis__year=int(year),
                datepaiementdevis__month=int(month)
            )
        except (ValueError, AttributeError):
            pass  # Ignorer si format invalide

    recoupements = {}

    for pe in points_eau:
        key = (pe.numerodiamexdevis, pe.basediamexdevis)

        if key not in recoupements:
            # Déterminer la commune via parcelle â†’ village â†’ fokontany â†’ commune
            commune = None
            if pe.parcelle and pe.parcelle.village and pe.parcelle.village.fokontany:
                commune = pe.parcelle.village.fokontany.commune

            recoupements[key] = {
                'numero_diamex': pe.numerodiamexdevis,
                'base_diamex': pe.basediamexdevis,
                'points_eau': [],
                'total_devis': Decimal('0'),
                'comptabilite_in': None,
                'comptabilite_out': None,
                'comptabilite_solde': None,
                'comptabilite_entry': None,
                'ecart': None,
                'status': 'unknown',
                'point_eau': None,
                'ouvrage': None,
                'commune': commune,
                'nb_points_eau': 0,
                'scan': None,
            }

        recoupements[key]['points_eau'].append(pe)
        montant_devis = Decimal(str(pe.montantdevispaye)) if pe.montantdevispaye else Decimal('0')
        recoupements[key]['total_devis'] += montant_devis
        recoupements[key]['nb_points_eau'] += 1

        if recoupements[key]['point_eau'] is None:
            recoupements[key]['point_eau'] = pe
            recoupements[key]['ouvrage'] = pe.ouvrage

    from apps.employees.models import EmployeBaseDiameX

    for key, data in recoupements.items():
        numero, base = key

        try:
            numero_int = int(str(numero).strip())
        except (TypeError, ValueError):
            numero_int = None
        diamex_entry = None
        if numero_int is not None and base:
            diamex_entry = diamex_scope_qs.filter(
                id_access=numero_int,
                prog=base
            ).first()

        if diamex_entry:
            data['comptabilite_entry'] = diamex_entry
            data['comptabilite_in'] = diamex_entry.montant_in
            data['comptabilite_out'] = diamex_entry.montant_out
            data['comptabilite_solde'] = diamex_entry.ccy

            data['scan'] = None
            if diamex_entry.scan and diamex_entry.fichier_source:
                employe_base = EmployeBaseDiameX.objects.filter(
                    base_diamex=diamex_entry.fichier_source
                )
                if organisation_ids is not None:
                    if organisation_ids:
                        employe_base = employe_base.filter(
                            employe__base__organisation_id__in=organisation_ids
                        )
                    else:
                        employe_base = employe_base.none()
                employe_base = employe_base.first()

                if employe_base and employe_base.chemin_base_diamex:
                    scan_relatif = diamex_entry.scan
                    if scan_relatif.startswith('.'):
                        scan_relatif = scan_relatif[1:]
                    if scan_relatif.startswith(employe_base.chemin_base_diamex):
                        data['scan'] = scan_relatif
                    else:
                        data['scan'] = employe_base.chemin_base_diamex + scan_relatif

            data['ecart'] = data['total_devis'] - Decimal(str(data['comptabilite_in']))

            if abs(data['ecart']) < Decimal('0.01'):
                data['status'] = 'ok'
            elif abs(data['ecart']) < Decimal('100'):
                data['status'] = 'warning'
            else:
                data['status'] = 'error'
        else:
            data['status'] = 'missing'
            data['ecart'] = data['total_devis']

    recoupements_list = sorted(
        recoupements.values(),
        key=lambda x: abs(x['ecart']) if x['ecart'] is not None else 0,
        reverse=True
    )

    if filter_status:
        recoupements_list = [r for r in recoupements_list if r['status'] == filter_status]

    # Stats globales (avant filtrage par status)
    stats_global = {
        'total': len(list(recoupements.values())),
        'ok': sum(1 for r in recoupements.values() if r['status'] == 'ok'),
        'warning': sum(1 for r in recoupements.values() if r['status'] == 'warning'),
        'error': sum(1 for r in recoupements.values() if r['status'] == 'error'),
        'missing': sum(1 for r in recoupements.values() if r['status'] == 'missing'),
    }

    # Regrouper par Base DiameX
    recoupements_par_base = {}
    for rec in recoupements_list:
        base_id = rec['base_diamex'] or 'sans_base'
        base_nom = rec['base_diamex'] or 'Sans base'

        if base_id not in recoupements_par_base:
            recoupements_par_base[base_id] = {
                'base_nom': base_nom,
                'recoupements': [],
                'total_recoupements': 0,
                'ok': 0,
                'warning': 0,
                'error': 0,
                'missing': 0
            }

        recoupements_par_base[base_id]['recoupements'].append(rec)
        recoupements_par_base[base_id]['total_recoupements'] += 1
        recoupements_par_base[base_id][rec['status']] += 1

    stats = {
        'total': len(recoupements_list),
        'ok': sum(1 for r in recoupements_list if r['status'] == 'ok'),
        'warning': sum(1 for r in recoupements_list if r['status'] == 'warning'),
        'error': sum(1 for r in recoupements_list if r['status'] == 'error'),
        'missing': sum(1 for r in recoupements_list if r['status'] == 'missing'),
    }

    bases_list = sorted(set(r['base_diamex'] for r in recoupements.values() if r['base_diamex']))

    # ===== VéRIFICATION INVERSE : DiameX â†’ Application (Devis BP) =====
    from apps.accounting.helpers_recoupement import verifier_recoupement_inverse
    from apps.organization.models import CompteTable

    filter_prog_inverse = request.GET.get('prog_inverse', '')
    filter_mois_inverse = request.GET.get('mois_inverse', '')

    comptes_devis = CompteTable.objects.filter(
        nom_table='points_eau_devis',
        actif=True
    ).select_related('compte').values_list('compte__compte', flat=True)

    comptes_cat_devis = list(comptes_devis)

    fichiers_sources = None
    if filter_base:
        fichiers_sources = [filter_base]

    resultats_inverses = verifier_recoupement_inverse(
        comptes_cat=comptes_cat_devis,
        fichiers_sources=fichiers_sources,
        type_recoupement='devis_bp',
        allowed_progs=_get_allowed_diamex_progs(request.user)
    )

    recoupements_inverses_list = resultats_inverses['recoupements_inverses']

    if filter_prog_inverse:
        recoupements_inverses_list = [r for r in recoupements_inverses_list if r['prog'] == filter_prog_inverse]

    if filter_mois_inverse:
        try:
            year, month = filter_mois_inverse.split('-')
            year = int(year)
            month = int(month)
            recoupements_inverses_list = [
                r for r in recoupements_inverses_list
                if r['date_m'] and r['date_m'].year == year and r['date_m'].month == month
            ]
        except (ValueError, AttributeError):
            pass

    recoupements_inverses_par_prog = {}
    for rec in recoupements_inverses_list:
        prog = rec['prog'] or 'Sans prog'
        if prog not in recoupements_inverses_par_prog:
            recoupements_inverses_par_prog[prog] = {
                'prog': prog,
                'recoupements': [],
                'total_recoupements': 0,
                'missing': 0,
                'error': 0,
                'warning': 0,
                'ok': 0
            }
        recoupements_inverses_par_prog[prog]['recoupements'].append(rec)
        recoupements_inverses_par_prog[prog]['total_recoupements'] += 1
        recoupements_inverses_par_prog[prog][rec['status']] += 1

    progs_list_inverse = sorted(set(r['prog'] for r in resultats_inverses['recoupements_inverses'] if r['prog']))

    context = {
        'recoupements': recoupements_list,
        'recoupements_par_base': recoupements_par_base,
        'stats': stats,
        'stats_global': stats_global,
        'bases_list': bases_list,
        'filter_status': filter_status,
        'filter_point_eau': filter_point_eau,
        'filter_base': filter_base,
        'filter_mois_paiement': filter_mois_paiement,
        # Inverse verification contexts
        'recoupements_inverses_par_prog': recoupements_inverses_par_prog,
        'stats_inverses': resultats_inverses['stats'],
        'comptes_cat_devis': comptes_cat_devis,
        'progs_list_inverse': progs_list_inverse,
        'filter_prog_inverse': filter_prog_inverse,
        'filter_mois_inverse': filter_mois_inverse,
        'type_recoupement': 'devis_bp',
        'titre': 'Recoupement Devis BP'
    }

    return render(request, 'accounting/recoupement_generic.html', context)


@login_required
def recoupement_cartes_sociales(request):
    """
    Recoupement entre Consommations Cartes Sociales et BaseDiameX
    Clé: (numeroDiameX, baseDiameX) <-> (id_access, prog)
    """
    from apps.billing.models import ConsoCarteSociale
    from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique

    filter_status = request.GET.get('status', '')
    filter_carte = request.GET.get('carte', '')
    filter_base = request.GET.get('base', '')

    organisation_id = _get_user_organisation_id(request.user)
    organisation_ids = _get_user_scope_organisation_ids(request.user)
    diamex_scope_qs = _get_diamex_scope_by_prog(request.user)

    consos = ConsoCarteSociale.objects.filter(
        numeroDiameX__isnull=False,
        baseDiameX__isnull=False
    ).select_related(
        'carte_sociale',
        'carte_sociale__ouvrage',
        'carte_sociale__point_eau',
        'carte_sociale__point_eau__parcelle',
        'carte_sociale__point_eau__parcelle__village',
        'carte_sociale__point_eau__parcelle__village__fokontany',
        'carte_sociale__point_eau__parcelle__village__fokontany__commune'
    )
    consos = _scope_queryset_by_gestionnaire_ids(
        consos,
        request.user,
        'carte_sociale__ouvrage__modalites_gestion__'
    )

    if filter_carte:
        consos = consos.filter(carte_sociale__numero_carte__icontains=filter_carte)

    if filter_base:
        consos = consos.filter(baseDiameX=filter_base)

    recoupements = {}

    for conso in consos:
        key = (conso.numeroDiameX, conso.baseDiameX)

        if key not in recoupements:
            # Déterminer l'ouvrage et la commune depuis la carte sociale
            ouvrage = None
            commune = None

            if conso.carte_sociale:
                ouvrage = conso.carte_sociale.ouvrage
                # Obtenir la commune via point_eau â†’ parcelle â†’ village â†’ fokontany â†’ commune
                if conso.carte_sociale.point_eau and conso.carte_sociale.point_eau.parcelle:
                    parcelle = conso.carte_sociale.point_eau.parcelle
                    if parcelle.village and parcelle.village.fokontany:
                        commune = parcelle.village.fokontany.commune

            recoupements[key] = {
                'numero_diamex': conso.numeroDiameX,
                'base_diamex': conso.baseDiameX,
                'cartes': [],
                'total_paye': Decimal('0'),
                'comptabilite_in': None,
                'comptabilite_out': None,
                'comptabilite_solde': None,
                'comptabilite_entry': None,
                'ecart': None,
                'status': 'unknown',
                'carte': None,
                'ouvrage': ouvrage,
                'commune': commune,
                'nb_cartes': 0,
                'scan': None,
            }

        recoupements[key]['cartes'].append(conso)
        montant_paye = Decimal(str(conso.montant_paye)) if conso.montant_paye else Decimal('0')
        recoupements[key]['total_paye'] += montant_paye
        recoupements[key]['nb_cartes'] += 1

        if recoupements[key]['carte'] is None:
            recoupements[key]['carte'] = conso.carte_sociale

    from apps.employees.models import EmployeBaseDiameX

    for key, data in recoupements.items():
        numero, base = key

        try:
            numero_int = int(str(numero).strip())
        except (TypeError, ValueError):
            numero_int = None
        diamex_entry = None
        if numero_int is not None and base:
            diamex_entry = diamex_scope_qs.filter(
                id_access=numero_int,
                prog=base
            ).first()

        if diamex_entry:
            data['comptabilite_entry'] = diamex_entry
            data['comptabilite_in'] = diamex_entry.montant_in
            data['comptabilite_out'] = diamex_entry.montant_out
            data['comptabilite_solde'] = diamex_entry.ccy

            data['scan'] = None
            if diamex_entry.scan and diamex_entry.fichier_source:
                employe_base = EmployeBaseDiameX.objects.filter(
                    base_diamex=diamex_entry.fichier_source
                )
                if organisation_ids is not None:
                    if organisation_ids:
                        employe_base = employe_base.filter(
                            employe__base__organisation_id__in=organisation_ids
                        )
                    else:
                        employe_base = employe_base.none()
                employe_base = employe_base.first()

                if employe_base and employe_base.chemin_base_diamex:
                    scan_relatif = diamex_entry.scan
                    if scan_relatif.startswith('.'):
                        scan_relatif = scan_relatif[1:]
                    if scan_relatif.startswith(employe_base.chemin_base_diamex):
                        data['scan'] = scan_relatif
                    else:
                        data['scan'] = employe_base.chemin_base_diamex + scan_relatif

            data['ecart'] = data['total_paye'] - Decimal(str(data['comptabilite_in']))

            if abs(data['ecart']) < Decimal('0.01'):
                data['status'] = 'ok'
            elif abs(data['ecart']) < Decimal('100'):
                data['status'] = 'warning'
            else:
                data['status'] = 'error'
        else:
            data['status'] = 'missing'
            data['ecart'] = data['total_paye']

    recoupements_list = sorted(
        recoupements.values(),
        key=lambda x: abs(x['ecart']) if x['ecart'] is not None else 0,
        reverse=True
    )

    if filter_status:
        recoupements_list = [r for r in recoupements_list if r['status'] == filter_status]

    # Stats globales (avant filtrage par status)
    stats_global = {
        'total': len(list(recoupements.values())),
        'ok': sum(1 for r in recoupements.values() if r['status'] == 'ok'),
        'warning': sum(1 for r in recoupements.values() if r['status'] == 'warning'),
        'error': sum(1 for r in recoupements.values() if r['status'] == 'error'),
        'missing': sum(1 for r in recoupements.values() if r['status'] == 'missing'),
    }

    # Regrouper par Base DiameX
    recoupements_par_base = {}
    for rec in recoupements_list:
        base_id = rec['base_diamex'] or 'sans_base'
        base_nom = rec['base_diamex'] or 'Sans base'

        if base_id not in recoupements_par_base:
            recoupements_par_base[base_id] = {
                'base_nom': base_nom,
                'recoupements': [],
                'total_recoupements': 0,
                'ok': 0,
                'warning': 0,
                'error': 0,
                'missing': 0
            }

        recoupements_par_base[base_id]['recoupements'].append(rec)
        recoupements_par_base[base_id]['total_recoupements'] += 1
        recoupements_par_base[base_id][rec['status']] += 1

    stats = {
        'total': len(recoupements_list),
        'ok': sum(1 for r in recoupements_list if r['status'] == 'ok'),
        'warning': sum(1 for r in recoupements_list if r['status'] == 'warning'),
        'error': sum(1 for r in recoupements_list if r['status'] == 'error'),
        'missing': sum(1 for r in recoupements_list if r['status'] == 'missing'),
    }

    bases_list = sorted(set(r['base_diamex'] for r in recoupements.values() if r['base_diamex']))

    # ===== VéRIFICATION INVERSE : DiameX â†’ Application (Cartes Sociales) =====
    from apps.accounting.helpers_recoupement import verifier_recoupement_inverse
    from apps.organization.models import CompteTable

    # Récupérer les filtres pour vérification inverse
    filter_prog_inverse = request.GET.get('prog_inverse', '')
    filter_mois_inverse = request.GET.get('mois_inverse', '')

    # Récupérer dynamiquement les comptes autorisés pour cartes sociales
    # Essayer d'abord 'conso_carte_sociale', sinon 'consommations_cartes_sociales'
    comptes_cartes = CompteTable.objects.filter(
        nom_table='conso_carte_sociale',
        actif=True
    ).select_related('compte').values_list('compte__compte', flat=True)

    comptes_cat_cartes = list(comptes_cartes)

    # Si aucun compte trouvé, fallback sur l'ancien nom
    if not comptes_cat_cartes:
        comptes_cartes = CompteTable.objects.filter(
            nom_table='consommations_cartes_sociales',
            actif=True
        ).select_related('compte').values_list('compte__compte', flat=True)
        comptes_cat_cartes = list(comptes_cartes)

    # Filtrer par bases si demandé
    fichiers_sources = None
    if filter_base:
        fichiers_sources = [filter_base]

    # Appeler la fonction d'aide pour vérification inverse
    resultats_inverses = verifier_recoupement_inverse(
        comptes_cat=comptes_cat_cartes,
        fichiers_sources=fichiers_sources,
        type_recoupement='cartes_sociales',
        allowed_progs=_get_allowed_diamex_progs(request.user)
    )

    # Appliquer filtres sur les résultats inverses
    recoupements_inverses_list = resultats_inverses['recoupements_inverses']

    # Filtre par Prog
    if filter_prog_inverse:
        recoupements_inverses_list = [r for r in recoupements_inverses_list if r['prog'] == filter_prog_inverse]

    # Filtre par Mois
    if filter_mois_inverse:
        try:
            year, month = filter_mois_inverse.split('-')
            year = int(year)
            month = int(month)
            recoupements_inverses_list = [
                r for r in recoupements_inverses_list
                if r['date_m'] and r['date_m'].year == year and r['date_m'].month == month
            ]
        except (ValueError, AttributeError):
            pass

    # Regrouper par Prog
    recoupements_inverses_par_prog = {}
    for rec in recoupements_inverses_list:
        prog = rec['prog'] or 'Sans prog'
        if prog not in recoupements_inverses_par_prog:
            recoupements_inverses_par_prog[prog] = {
                'prog': prog,
                'entries': [],  #  Changé: recoupements â†’ entries
                'total': 0,     #  Changé: total_recoupements â†’ total
                'trouves': 0,   # Pour stats (toujours 0 en vérif inverse)
                'non_trouves': 0,
                'missing': 0,
                'error': 0,
                'warning': 0,
                'ok': 0
            }
        recoupements_inverses_par_prog[prog]['entries'].append(rec)
        recoupements_inverses_par_prog[prog]['total'] += 1
        recoupements_inverses_par_prog[prog]['non_trouves'] += 1  # Toutes les entrées sont "non trouvées" dans la vérification inverse
        recoupements_inverses_par_prog[prog][rec['status']] += 1

    # Listes pour filtres
    progs_list_inverse = sorted(set(r['prog'] for r in resultats_inverses['recoupements_inverses'] if r['prog']))

    # ========== SECTION 3 : RECOUPEMENT PAR EXTRACTION ==========
    # BaseDiameX (comptes cartes sociales) â†’ Extraction ouvrage â†’ ConsoCarteSociale
    # AVEC REGROUPEMENT PAR OUVRAGE ET MOIS

    filter_ouvrage_extraction = request.GET.get('ouvrage_extraction', '')
    filter_mois_extraction = request.GET.get('mois_extraction', '')
    filter_prog_extraction = request.GET.get('prog_extraction', '')
    filter_status_extraction = request.GET.get('status_extraction', '')

    # Récupérer toutes les entrées DiameX avec comptes cartes sociales
    diamex_extraction = BaseDiameX.objects.filter(
        compte_code__in=comptes_cat_cartes
    ).order_by('-date_m')

    # Filtrer par mois
    if filter_mois_extraction:
        try:
            year, month = filter_mois_extraction.split('-')
            diamex_extraction = diamex_extraction.filter(
                date_m__year=int(year),
                date_m__month=int(month)
            )
        except (ValueError, AttributeError):
            pass

    # Filtrer par Prog
    if filter_prog_extraction:
        diamex_extraction = diamex_extraction.filter(prog=filter_prog_extraction)

    # Dictionnaires pour regroupements
    # Format: {(ouvrage_id, year, month): {'diamex': [], 'consos': [], ...}}
    regroupements_par_ouvrage_mois = {}
    recoupements_extraction = []

    for entry in diamex_extraction:
        # Extraire l'ouvrage depuis la description
        extraction = extraire_ouvrage_et_mois_generique(entry.description, entry.compte_code)

        ouvrage_obj = extraction.get('ouvrage_obj')
        ouvrage_nom = extraction.get('ouvrage_nom')

        # Filtrer par ouvrage si demandé
        if filter_ouvrage_extraction and ouvrage_nom:
            if filter_ouvrage_extraction.lower() not in ouvrage_nom.lower():
                continue

        # Créer clé de regroupement (ouvrage_id, année, mois)
        if ouvrage_obj and entry.date_m:
            key = (ouvrage_obj.id, entry.date_m.year, entry.date_m.month)
        else:
            # Clé pour entrées sans ouvrage ou sans date
            key = (None, entry.date_m.year if entry.date_m else None, entry.date_m.month if entry.date_m else None)

        if key not in regroupements_par_ouvrage_mois:
            regroupements_par_ouvrage_mois[key] = {
                'ouvrage_obj': ouvrage_obj,
                'ouvrage_nom': ouvrage_nom,
                'annee': entry.date_m.year if entry.date_m else None,
                'mois': entry.date_m.month if entry.date_m else None,
                'prog': entry.prog,
                'diamex_entries': [],
                'consos_cartes': set(),  # Set pour éviter doublons
                'total_diamex': Decimal('0'),
                'total_consos': Decimal('0'),
            }

        regroupements_par_ouvrage_mois[key]['diamex_entries'].append(entry)
        regroupements_par_ouvrage_mois[key]['total_diamex'] += Decimal(str(entry.montant_in)) if entry.montant_in else Decimal('0')

    # Pour chaque regroupement, chercher les consommations cartes sociales correspondantes
    for key, groupe in regroupements_par_ouvrage_mois.items():
        ouvrage_obj = groupe['ouvrage_obj']
        annee = groupe['annee']
        mois = groupe['mois']

        if ouvrage_obj and annee and mois:
            # Chercher consommations pour cet ouvrage ET ce mois précis
            consos_liees = ConsoCarteSociale.objects.filter(
                carte_sociale__ouvrage=ouvrage_obj,
                date__year=annee,
                date__month=mois
            ).select_related('carte_sociale', 'carte_sociale__ouvrage')

            for c in consos_liees:
                groupe['consos_cartes'].add(c.id)
                if c.montant_paye:
                    groupe['total_consos'] += Decimal(str(c.montant_paye))

    # Créer liste de recoupements à partir des regroupements
    for key, groupe in regroupements_par_ouvrage_mois.items():
        # Calculer écart et statut
        ecart = groupe['total_consos'] - groupe['total_diamex']
        nb_consos = len(groupe['consos_cartes'])

        if nb_consos > 0:
            if abs(ecart) < Decimal('0.01'):
                status = 'ok'
            elif abs(ecart) < Decimal('100'):
                status = 'warning'
            else:
                status = 'error'
        else:
            if groupe['ouvrage_obj']:
                status = 'missing'  # Ouvrage trouvé mais pas de consommations
            else:
                status = 'error'  # Ouvrage non extrait

        # Filtrer par statut si demandé
        if filter_status_extraction and status != filter_status_extraction:
            continue

        recoupements_extraction.append({
            'ouvrage_nom': groupe['ouvrage_nom'],
            'ouvrage_obj': groupe['ouvrage_obj'],
            'annee': groupe['annee'],
            'mois': groupe['mois'],
            'prog': groupe['prog'],
            'nb_entries_diamex': len(groupe['diamex_entries']),
            'total_diamex': groupe['total_diamex'],
            'nb_consos': nb_consos,
            'total_consos': groupe['total_consos'],
            'ecart': ecart,
            'status': status,
            'diamex_entries': groupe['diamex_entries'],  # Pour afficher détails
            'consos_ids': list(groupe['consos_cartes']),
        })

    # Grouper Section 3 par Prog puis par Ouvrage
    recoupements_extraction_par_prog = {}
    for rec in recoupements_extraction:
        prog = rec['prog']
        if prog not in recoupements_extraction_par_prog:
            recoupements_extraction_par_prog[prog] = {}

        ouvrage_nom = rec['ouvrage_nom'] if rec['ouvrage_nom'] else 'Non extrait'
        if ouvrage_nom not in recoupements_extraction_par_prog[prog]:
            recoupements_extraction_par_prog[prog][ouvrage_nom] = []

        recoupements_extraction_par_prog[prog][ouvrage_nom].append(rec)

    # Stats extraction
    stats_extraction = {
        'total': len(recoupements_extraction),
        'ok': sum(1 for r in recoupements_extraction if r['status'] == 'ok'),
        'warning': sum(1 for r in recoupements_extraction if r['status'] == 'warning'),
        'error': sum(1 for r in recoupements_extraction if r['status'] == 'error'),
        'missing': sum(1 for r in recoupements_extraction if r['status'] == 'missing'),
    }

    # Liste des progs pour filtre extraction
    progs_list_extraction = sorted(set(r['prog'] for r in recoupements_extraction if r['prog']))

    context = {
        'recoupements': recoupements_list,
        'recoupements_par_base': recoupements_par_base,
        'stats': stats,
        'stats_global': stats_global,
        'bases_list': bases_list,
        'filter_status': filter_status,
        'filter_carte': filter_carte,
        'filter_base': filter_base,
        # Inverse verification contexts
        'recoupements_inverses_par_prog': recoupements_inverses_par_prog,
        'stats_inverse': resultats_inverses['stats'],  #  Corrigé: stats_inverse sans 's'
        'comptes_cat_cartes': comptes_cat_cartes,
        'progs_list_inverse': progs_list_inverse,
        'filter_prog_inverse': filter_prog_inverse,
        'filter_mois_inverse': filter_mois_inverse,
        # Extraction verification contexts (Section 3)
        'recoupements_extraction_par_prog': recoupements_extraction_par_prog,
        'stats_extraction': stats_extraction,
        'progs_list_extraction': progs_list_extraction,
        'filter_prog_extraction': filter_prog_extraction,
        'filter_status_extraction': filter_status_extraction,
        'filter_ouvrage_extraction': filter_ouvrage_extraction,
        'filter_mois_extraction': filter_mois_extraction,
        'type_recoupement': 'cartes_sociales',
        'titre': 'Recoupement Cartes Sociales'
    }

    return render(request, 'accounting/recoupement_generic.html', context)


@login_required
def recoupement_releves(request):
    """
    Recoupement entre Relevés et BaseDiameX
    Tous les Relevés avec numeroDiameX DOIVENT ètre trouvés dans la comptabilité
    Clé: (numeroDiameX, baseDiameX) <-> (id_access, prog)
    """
    from apps.billing.models import Releve

    # Filtres depuis GET
    filter_status = request.GET.get('status', '')  # ok, warning, error, missing
    filter_point_eau = request.GET.get('point_eau', '')
    filter_base = request.GET.get('base', '')
    filter_mois = request.GET.get('mois', '')

    # Récupérer tous les Relevés avec numeroDiameX non null
    releves = Releve.objects.filter(
        numeroDiameX__isnull=False,
        baseDiameX__isnull=False
    ).select_related(
        'point_eau',
        'point_eau__ouvrage',
        'point_eau__parcelle',
        'point_eau__parcelle__village',
        'point_eau__parcelle__village__fokontany',
        'point_eau__parcelle__village__fokontany__commune'
    )
    organisation_id = _get_user_organisation_id(request.user)
    releves = _scope_queryset_by_gestionnaire_ids(
        releves,
        request.user,
        'point_eau__ouvrage__modalites_gestion__'
    )

    diamex_scope_qs = _get_diamex_scope_by_prog(request.user)

    # Appliquer filtre point d'eau
    if filter_point_eau:
        releves = releves.filter(point_eau__nomabonne__icontains=filter_point_eau)

    # Appliquer filtre base
    if filter_base:
        releves = releves.filter(baseDiameX=filter_base)

    # Appliquer filtre mois
    if filter_mois:
        try:
            year, month = filter_mois.split('-')
            year = int(year)
            month = int(month)
            releves = releves.filter(datereleve__year=year, datereleve__month=month)
        except (ValueError, AttributeError):
            pass  # Ignorer filtre mois invalide

    # Grouper par couple (numeroDiameX, baseDiameX)
    recoupements = {}

    for releve in releves:
        key = (releve.numeroDiameX, releve.baseDiameX)

        if key not in recoupements:
            recoupements[key] = {
                'numero_diamex': releve.numeroDiameX,
                'base_diamex': releve.baseDiameX,
                'releves': [],
                'total_releves': Decimal('0'),
                'comptabilite_in': None,
                'comptabilite_out': None,
                'comptabilite_solde': None,
                'comptabilite_entry': None,
                'ecart': None,
                'status': 'unknown',
                # Informations supplémentaires du premier relevé (pour affichage)
                'point_eau': None,
                'ouvrage': None,
                'commune': None,
                'date_releve': None,
                'nb_releves': 0,
                'scan': None,  # [OK] Ajout du scan
            }

        recoupements[key]['releves'].append(releve)
        recoupements[key]['total_releves'] += Decimal(str(releve.montant)) if releve.montant else Decimal('0')
        recoupements[key]['nb_releves'] += 1

        # Récupérer info du premier relevé pour affichage
        if recoupements[key]['point_eau'] is None:
            recoupements[key]['point_eau'] = releve.point_eau
            recoupements[key]['ouvrage'] = releve.point_eau.ouvrage if releve.point_eau else None
            recoupements[key]['date_releve'] = releve.datereleve

            # Déterminer la commune via parcelle â†’ village â†’ fokontany â†’ commune
            recoupements[key]['commune'] = None
            if releve.point_eau and releve.point_eau.parcelle:
                parcelle = releve.point_eau.parcelle
                if parcelle.village and parcelle.village.fokontany:
                    recoupements[key]['commune'] = parcelle.village.fokontany.commune

    # Pour chaque couple du relevé, chercher l'entrée correspondante dans BaseDiameX
    from apps.employees.models import EmployeBaseDiameX

    for key, data in recoupements.items():
        numero, base = key

        # Chercher dans BaseDiameX: id_access = numeroDiameX, prog = baseDiameX
        diamex_entry = BaseDiameX.objects.filter(
            id_access=numero,
            prog=base
        ).first()

        if diamex_entry:
            data['comptabilite_entry'] = diamex_entry
            data['comptabilite_in'] = diamex_entry.montant_in
            data['comptabilite_out'] = diamex_entry.montant_out
            data['comptabilite_solde'] = diamex_entry.ccy  # IN - OUT

            # [OK] Récupérer le scan depuis BaseDiameX (DATA)
            data['scan'] = None
            if diamex_entry.scan and diamex_entry.fichier_source:
                # Récupérer le chemin_base depuis EmployeBaseDiameX
                employe_base = EmployeBaseDiameX.objects.filter(
                    base_diamex=diamex_entry.fichier_source
                ).first()

                if employe_base and employe_base.chemin_base_diamex:
                    scan_relatif = diamex_entry.scan
                    # Enlever le "." au début si présent
                    if scan_relatif.startswith('.'):
                        scan_relatif = scan_relatif[1:]
                    # Construire le chemin complet
                    # Si scan contient déjà le chemin absolu, ne pas concaténer
                    if scan_relatif.startswith(employe_base.chemin_base_diamex):
                        data['scan'] = scan_relatif
                    else:
                        data['scan'] = employe_base.chemin_base_diamex + scan_relatif

            # Calculer l'écart : relevés sont des recettes (IN)
            # Total relevés doit égaler IN comptabilité
            data['ecart'] = data['total_releves'] - Decimal(str(data['comptabilite_in']))

            # Déterminer le statut basé sur l'écart
            if abs(data['ecart']) < Decimal('0.01'):  # Tolérance 1 centime
                data['status'] = 'ok'
            elif abs(data['ecart']) < Decimal('100'):
                data['status'] = 'warning'
            else:
                data['status'] = 'error'
        else:
            # CRITIQUE : Tous les Relevés DOIVENT avoir une entrée compta
            data['status'] = 'missing'
            data['ecart'] = data['total_releves']

    # Convertir en liste et trier par écart décroissant
    recoupements_list = sorted(
        recoupements.values(),
        key=lambda x: (
            0 if x['status'] == 'missing' else 1 if x['status'] == 'error' else 2,
            abs(x['ecart']) if x['ecart'] is not None else 0
        ),
        reverse=False
    )
    # Inverser pour avoir les plus gros écarts en premier
    recoupements_list = sorted(
        recoupements_list,
        key=lambda x: abs(x['ecart']) if x['ecart'] is not None else 0,
        reverse=True
    )

    # Appliquer filtre status APRES le calcul de toutes les stats
    if filter_status:
        recoupements_list = [r for r in recoupements_list if r['status'] == filter_status]

    # Regrouper par Base DiameX
    recoupements_par_base = {}
    for rec in recoupements_list:
        base_id = rec['base_diamex'] or 'sans_base'
        base_nom = rec['base_diamex'] or 'Sans base'

        if base_id not in recoupements_par_base:
            recoupements_par_base[base_id] = {
                'base_nom': base_nom,
                'recoupements': [],
                'total_recoupements': 0,
                'ok': 0,
                'warning': 0,
                'error': 0,
                'missing': 0
            }

        recoupements_par_base[base_id]['recoupements'].append(rec)
        recoupements_par_base[base_id]['total_recoupements'] += 1
        recoupements_par_base[base_id][rec['status']] += 1

    # Statistiques GLOBALES (avant filtre status pour afficher totaux)
    stats_global = {
        'total': len(recoupements_list) if not filter_status else sum(1 for r in recoupements.values()),
        'ok': sum(1 for r in recoupements.values() if r['status'] == 'ok'),
        'warning': sum(1 for r in recoupements.values() if r['status'] == 'warning'),
        'error': sum(1 for r in recoupements.values() if r['status'] == 'error'),
        'missing': sum(1 for r in recoupements.values() if r['status'] == 'missing'),
    }

    # Statistiques FILTREES (apres tous les filtres)
    stats_filtered = {
        'total': len(recoupements_list),
        'ok': sum(1 for r in recoupements_list if r['status'] == 'ok'),
        'warning': sum(1 for r in recoupements_list if r['status'] == 'warning'),
        'error': sum(1 for r in recoupements_list if r['status'] == 'error'),
        'missing': sum(1 for r in recoupements_list if r['status'] == 'missing'),
    }

    # Pagination (50 par page)
    paginator = Paginator(recoupements_list, 50)
    page_number = request.GET.get('page', 1)

    # Valider le numéro de page
    try:
        page_number = int(page_number)
        if page_number < 1:
            page_number = 1
    except (ValueError, TypeError):
        page_number = 1

    page_obj = paginator.get_page(page_number)

    # Listes pour les filtres
    points_eau_qs = Releve.objects.filter(
        numeroDiameX__isnull=False,
        baseDiameX__isnull=False,
        point_eau__isnull=False
    )
    points_eau_qs = _scope_queryset_by_gestionnaire_ids(
        points_eau_qs,
        request.user,
        'point_eau__ouvrage__modalites_gestion__'
    )

    points_eau_list = sorted(set(
        releve.point_eau.nomabonne
        for releve in points_eau_qs.select_related('point_eau')
        if releve.point_eau and releve.point_eau.nomabonne
    ))

    bases_qs = Releve.objects.filter(
        numeroDiameX__isnull=False,
        baseDiameX__isnull=False
    )
    bases_qs = _scope_queryset_by_gestionnaire_ids(
        bases_qs,
        request.user,
        'point_eau__ouvrage__modalites_gestion__'
    )

    bases_list = sorted(set(
        releve.baseDiameX
        for releve in bases_qs
        if releve.baseDiameX
    ))

    # ===== VéRIFICATION INVERSE : DiameX â†’ Application (Relevés) =====
    from apps.accounting.helpers_recoupement import verifier_recoupement_inverse
    from apps.organization.models import CompteTable

    # Récupérer les filtres pour vérification inverse
    filter_prog_inverse = request.GET.get('prog_inverse', '')
    filter_mois_inverse = request.GET.get('mois_inverse', '')

    # Récupérer dynamiquement les comptes autorisés pour releves depuis CompteTable
    comptes_releves = CompteTable.objects.filter(
        nom_table='releves',
        actif=True
    ).select_related('compte').values_list('compte__compte', flat=True)

    comptes_cat_releves = list(comptes_releves)

    # Filtrer par bases si demandé
    fichiers_sources = None
    if filter_base:
        fichiers_sources = [filter_base]

    # Appeler la fonction d'aide pour vérification inverse
    resultats_inverses = verifier_recoupement_inverse(
        comptes_cat=comptes_cat_releves,
        fichiers_sources=fichiers_sources,
        type_recoupement='releves',
        allowed_progs=_get_allowed_diamex_progs(request.user)
    )

    # Appliquer filtres sur les résultats inverses
    recoupements_inverses_list = resultats_inverses['recoupements_inverses']

    # Filtre par Prog
    if filter_prog_inverse:
        recoupements_inverses_list = [r for r in recoupements_inverses_list if r['prog'] == filter_prog_inverse]

    # Filtre par Mois
    if filter_mois_inverse:
        try:
            year, month = filter_mois_inverse.split('-')
            year = int(year)
            month = int(month)
            recoupements_inverses_list = [
                r for r in recoupements_inverses_list
                if r['date_m'] and r['date_m'].year == year and r['date_m'].month == month
            ]
        except (ValueError, AttributeError):
            pass

    # Regrouper par Prog
    recoupements_inverses_par_prog = {}
    for rec in recoupements_inverses_list:
        prog = rec['prog'] or 'Sans prog'
        if prog not in recoupements_inverses_par_prog:
            recoupements_inverses_par_prog[prog] = {
                'prog': prog,
                'entries': [],  #  Changé: recoupements â†’ entries
                'total': 0,     #  Changé: total_recoupements â†’ total
                'trouves': 0,   # Pour stats (toujours 0 en vérif inverse)
                'non_trouves': 0,
                'missing': 0,
                'error': 0,
                'warning': 0,
                'ok': 0
            }
        recoupements_inverses_par_prog[prog]['entries'].append(rec)
        recoupements_inverses_par_prog[prog]['total'] += 1
        recoupements_inverses_par_prog[prog]['non_trouves'] += 1  # Toutes les entrées sont "non trouvées" dans la vérification inverse
        recoupements_inverses_par_prog[prog][rec['status']] += 1

    # Listes pour filtres
    progs_list_inverse = sorted(set(r['prog'] for r in resultats_inverses['recoupements_inverses'] if r['prog']))

    # ===== 3e RECOUPEMENT : Relevés par Ouvrage vs DiameX 707401 par Ouvrage =====
    from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique
    from apps.organization.models import Ouvrage

    # Filtres pour le 3e recoupement
    filter_ouvrage_3e = request.GET.get('ouvrage_3e', '')
    filter_mois_3e = request.GET.get('mois_3e', '')

    # Agréger les relevés par ouvrage et mois
    # On prend TOUS les relevés qui ont un montant (peu importe s'ils ont numeroDiameX ou pas)
    # CRITICAL: Filtrer pour inclure décembre 2024 (car janvier 2025 = décembre 2024 + 1 mois)
    # On filtre (année >= 2025) OU (année = 2024 ET mois = 12)
    from django.db.models import Q
    releves_tous = Releve.objects.filter(
        montant__isnull=False,
        montant__gt=0,
        point_eau__ouvrage__isnull=False
    ).filter(
        Q(datereleve__year__gte=2025) |  # Année 2025 ou plus
        Q(datereleve__year=2024, datereleve__month=12)  # OU décembre 2024
    ).exclude(
        remarque__icontains='coupé'  # Exclure les relevés avec "coupé" dans la remarque
    ).select_related('point_eau', 'point_eau__ouvrage')
    releves_tous = _scope_queryset_by_gestionnaire_ids(
        releves_tous,
        request.user,
        'point_eau__ouvrage__modalites_gestion__'
    )

    # Appliquer les filtres
    if filter_ouvrage_3e:
        releves_tous = releves_tous.filter(point_eau__ouvrage_id=filter_ouvrage_3e)

    # CRITICAL: Le filtre mois correspond à la date de FACTURATION (mois suivant le relevé)
    # Donc pour filtrer les factures de janvier 2025, on cherche les relevés de décembre 2024
    filter_year_facturation = None
    filter_month_facturation = None
    if filter_mois_3e:
        try:
            from datetime import datetime
            from dateutil.relativedelta import relativedelta

            year, month = filter_mois_3e.split('-')
            filter_year_facturation = int(year)
            filter_month_facturation = int(month)

            # Calculer le mois de relevé (mois précédent)
            date_facturation = datetime(filter_year_facturation, filter_month_facturation, 1)
            date_releve = date_facturation - relativedelta(months=1)

            releves_tous = releves_tous.filter(
                datereleve__year=date_releve.year,
                datereleve__month=date_releve.month
            )
        except (ValueError, AttributeError):
            pass

    # Grouper par (ouvrage, année, mois)
    # CRITICAL: Grouper par date de FACTURATION (mois suivant le relevé)
    from dateutil.relativedelta import relativedelta

    releves_par_ouvrage = {}
    for releve in releves_tous:
        if releve.point_eau and releve.point_eau.ouvrage and releve.datereleve:
            # Calculer la date de facturation (mois suivant le relevé)
            date_facturation = releve.datereleve + relativedelta(months=1)

            key = (
                releve.point_eau.ouvrage.id,
                date_facturation.year,
                date_facturation.month
            )

            if key not in releves_par_ouvrage:
                releves_par_ouvrage[key] = {
                    'ouvrage': releve.point_eau.ouvrage,
                    'ouvrage_id': releve.point_eau.ouvrage.id,
                    'ouvrage_nom': releve.point_eau.ouvrage.nom_ouvrage,
                    'annee': key[1],
                    'mois': key[2],
                    'total_releves': Decimal('0'),
                    'total_diamex': Decimal('0'),
                    'nb_releves': 0,
                    'nb_transactions_diamex': 0,
                    'ecart': Decimal('0'),
                    'status': 'unknown'
                }

            releves_par_ouvrage[key]['total_releves'] += Decimal(str(releve.montant))
            releves_par_ouvrage[key]['nb_releves'] += 1

    # Pour chaque groupe (ouvrage, année, mois), chercher les transactions DiameX compte 707401
    for key, data in releves_par_ouvrage.items():
        ouvrage_id, annee, mois = key

        # Récupérer toutes les transactions DiameX pour le compte 707401
        # CRITICAL: Filtrer uniquement les années >= 2025 (cohérence avec les relevés)
        diamex_707401 = diamex_scope_qs.filter(
            compte_code='707401',
            date_rec__year__gte=2025  # FILTRE ANNéE >= 2025
        )

        # Filtrer par mois/année si la date existe
        if annee and mois:
            diamex_707401 = diamex_707401.filter(
                date_rec__year=annee,
                date_rec__month=mois
            )

        # Pour chaque transaction, vérifier si multi-segments
        for entry in diamex_707401:
            # Détection des paiements multi-segments (contient ';')
            segments = []
            if entry.description and ';' in entry.description:
                segments = diviser_paiement_volume_multi(
                    entry.description,
                    entry.compte_code,
                    entry.montant_in if entry.montant_in else 0
                )

            if segments:
                # Traiter chaque segment séparément
                for segment in segments:
                    extraction = segment['extraction']

                    # Vérifier si l'ouvrage du segment correspond à celui du groupe
                    if extraction['ouvrage_obj'] and extraction['ouvrage_obj'].id == ouvrage_id:
                        # Vérifier que le mois/année du segment correspondent
                        mois_ok = True
                        if extraction['mois'] and extraction['annee']:
                            mois_ok = (extraction['mois'] == mois and extraction['annee'] == annee)

                        if mois_ok:
                            # Ce segment correspond à cet ouvrage/mois
                            montant_segment = Decimal(str(segment['montant']))
                            data['total_diamex'] += montant_segment
                            data['nb_transactions_diamex'] += 1
            else:
                # Traitement normal pour les entrées non segmentées
                extraction = extraire_ouvrage_et_mois_generique(entry.description or '', entry.compte_code)

                # Vérifier si l'ouvrage extrait correspond à celui du groupe
                if extraction['ouvrage_obj'] and extraction['ouvrage_obj'].id == ouvrage_id:
                    # Vérifier aussi que le mois/année correspondent (si extraits)
                    mois_ok = True
                    if extraction['mois'] and extraction['annee']:
                        mois_ok = (extraction['mois'] == mois and extraction['annee'] == annee)

                    if mois_ok:
                        # Cette transaction correspond à cet ouvrage/mois
                        montant_diamex = Decimal(str(entry.montant_in)) if entry.montant_in else Decimal('0')
                        data['total_diamex'] += montant_diamex
                        data['nb_transactions_diamex'] += 1

        # Calculer l'écart
        data['ecart'] = data['total_releves'] - data['total_diamex']

        # Calculer le taux de recouvrement (Total DiameX / Total Relevés * 100)
        if data['total_releves'] > 0:
            data['taux_recouvrement'] = int((data['total_diamex'] / data['total_releves']) * 100)
        else:
            data['taux_recouvrement'] = 0

        # Déterminer le statut
        if abs(data['ecart']) < Decimal('0.01'):
            data['status'] = 'ok'
        elif abs(data['ecart']) < Decimal('100'):
            data['status'] = 'warning'
        else:
            data['status'] = 'error'

    # Convertir en liste et trier par ouvrage puis par date (année/mois)
    # IMPORTANT: On trie par ouvrage_nom puis par année/mois pour que le regroupement Django fonctionne
    # Le tri par écart est supprimé car il empèche le regroupement par ouvrage dans le template
    recoupements_3e_list = sorted(
        releves_par_ouvrage.values(),
        key=lambda x: (x['ouvrage_nom'], x['annee'], x['mois'])
    )

    # Statistiques du 3e recoupement
    stats_3e = {
        'total': len(recoupements_3e_list),
        'ok': sum(1 for r in recoupements_3e_list if r['status'] == 'ok'),
        'warning': sum(1 for r in recoupements_3e_list if r['status'] == 'warning'),
        'error': sum(1 for r in recoupements_3e_list if r['status'] == 'error'),
        'total_ecart': sum(abs(r['ecart']) for r in recoupements_3e_list)
    }

    # Liste des ouvrages pour les filtres
    # La relation est Ouvrage -> PointEau (related_name par défaut) -> Releve (related_name='releves')
    ouvrages_avec_releves = Ouvrage.objects.filter(
        pointeau__releves__montant__isnull=False
    ).distinct().order_by('nom_ouvrage')
    ouvrages_avec_releves = _scope_queryset_by_gestionnaire_ids(
        ouvrages_avec_releves,
        request.user,
        'modalites_gestion__'
    )

    return render(request, 'accounting/recoupement_releves.html', {
        'page_obj': page_obj,
        'recoupements': page_obj,
        'recoupements_par_base': recoupements_par_base,
        'stats': stats_filtered,
        'stats_global': stats_global,
        'points_eau_list': points_eau_list,
        'bases_list': bases_list,
        # Inverse verification contexts
        'recoupements_inverses_par_prog': recoupements_inverses_par_prog,
        'stats_inverses': resultats_inverses['stats'],
        'comptes_cat_releves': comptes_cat_releves,
        'progs_list_inverse': progs_list_inverse,
        'filter_prog_inverse': filter_prog_inverse,
        'filter_mois_inverse': filter_mois_inverse,
        # 3e recoupement contexts
        'recoupements_3e': recoupements_3e_list,
        'stats_3e': stats_3e,
        'ouvrages_avec_releves': ouvrages_avec_releves,
        'filter_ouvrage_3e': filter_ouvrage_3e,
        'filter_mois_3e': filter_mois_3e,
    })


@login_required
@require_http_methods(["GET"])
def api_get_releves_ouvrage_mois(request):
    """
    API pour récupérer les relevés d'un ouvrage pour un mois donné.
    Utilisé pour afficher les relevés dans une modal et permettre la mise à jour
    des champs numeroDiameX et baseDiameX.
    """
    try:
        from apps.billing.models import Releve, PointEau

        ouvrage_id = request.GET.get('ouvrage_id')
        annee = request.GET.get('annee')
        mois = request.GET.get('mois')

        if not all([ouvrage_id, annee, mois]):
            return JsonResponse({
                'success': False,
                'error': 'Paramètres manquants (ouvrage_id, annee, mois)'
            }, status=400)

        try:
            annee = int(annee)
            mois = int(mois)
        except (ValueError, TypeError):
            return JsonResponse({
                'success': False,
                'error': 'Format année/mois invalide'
            }, status=400)

        organisation_id = _get_user_organisation_id(request.user)
        allowed_progs = _get_allowed_diamex_progs(request.user)
        diamex_scope_qs = _get_diamex_scope_by_prog(request.user)

        # Récupérer l'ouvrage pour obtenir son nom
        from apps.organization.models import Ouvrage
        try:
            ouvrage_qs = Ouvrage.objects.filter(id=ouvrage_id)
            ouvrage_qs = _scope_queryset_by_gestionnaire_ids(
                ouvrage_qs,
                request.user,
                'modalites_gestion__'
            )
            ouvrage = ouvrage_qs.get()
            ouvrage_nom = ouvrage.nom_ouvrage
        except Ouvrage.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Ouvrage hors périmètre ou introuvable'
            }, status=404)

        # Récupérer les points d'eau de l'ouvrage
        points_eau_qs = PointEau.objects.filter(
            ouvrage_id=ouvrage_id
        )
        points_eau_qs = _scope_queryset_by_gestionnaire_ids(
            points_eau_qs,
            request.user,
            'ouvrage__modalites_gestion__'
        )
        points_eau_ids = points_eau_qs.values_list('id', flat=True)

        # Récupérer les relevés sans tri (tri en Python après)
        # CRITICAL: Exclure les relevés avec remarque contenant "coupé" (insensible à la casse)
        from django.db.models import Q
        releves = Releve.objects.filter(
            point_eau_id__in=points_eau_ids,
            datereleve__year=annee,
            datereleve__month=mois
        ).exclude(
            Q(remarque__icontains='coupé') | Q(remarque__icontains='Coupé')
        ).select_related('point_eau')

        # Récupérer les montants DATA (In) groupés par (numeroDiameX, baseDiameX)
        # Un mème couple peut avoir plusieurs relevés, ils partagent le mème montant DATA
        from apps.accounting.models import BaseDiameX
        montants_data_par_couple = {}

        for releve in releves:
            if releve.numeroDiameX and releve.baseDiameX:
                key = (releve.numeroDiameX, releve.baseDiameX)
                if key not in montants_data_par_couple:
                    try:
                        diamex_entry = diamex_scope_qs.filter(
                            id_access=int(releve.numeroDiameX),
                            prog=releve.baseDiameX
                        ).first()
                        if diamex_entry:
                            montants_data_par_couple[key] = float(diamex_entry.montant_in or 0)
                        else:
                            montants_data_par_couple[key] = 0
                    except (ValueError, TypeError):
                        montants_data_par_couple[key] = 0

        # Sérialiser les données
        releves_data = []
        for releve in releves:
            # Récupérer le montant DATA (In) via le couple (numeroDiameX, baseDiameX)
            key = (releve.numeroDiameX, releve.baseDiameX) if releve.numeroDiameX and releve.baseDiameX else None
            montant_data_in = montants_data_par_couple.get(key, 0) if key else 0

            releves_data.append({
                'id': str(releve.id),
                'point_eau_nom': releve.point_eau.nomabonne if releve.point_eau else 'N/A',
                'idxls': releve.point_eau.idxls if releve.point_eau else '',
                'abonne': releve.abonne,
                'date_releve': releve.datereleve.strftime('%Y-%m-%d'),
                'ancien_index': float(releve.ancienindex),
                'nouvel_index': float(releve.nouvelindex),
                'consommation': float(releve.consommation),
                'volume_facture': float(releve.volume_facture) if releve.volume_facture else float(releve.consommation),
                'montant': float(releve.montant) if releve.montant else 0,
                'montant_data_in': montant_data_in,
                'numero_diamex': releve.numeroDiameX or '',
                'base_diamex': releve.baseDiameX or '',
                'statut': releve.statut,
            })

        # Trier par IDxls (converti en entier) puis par date
        def sort_key(item):
            try:
                idxls_int = int(item['idxls']) if item['idxls'] else 999999
            except (ValueError, TypeError):
                idxls_int = 999999
            return (idxls_int, item['date_releve'])

        releves_data.sort(key=sort_key)

        return JsonResponse({
            'success': True,
            'ouvrage_nom': ouvrage_nom,
            'releves': releves_data,
            'total': len(releves_data)
        })

    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': f'Erreur serveur: {str(e)}',
            'traceback': traceback.format_exc()
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_update_releve_diamex(request):
    """
    API pour mettre à jour les champs numeroDiameX, baseDiameX et montant d'un relevé.
    """
    from apps.billing.models import Releve

    try:
        employe = getattr(request.user, 'employe', None)
        if not employe or not employe.is_directeur:
            return JsonResponse({
                'success': False,
                'error': 'Accès refusé. Seul un directeur peut modifier un pointage.'
            }, status=403)

        data = json.loads(request.body)
        releve_id = data.get('releve_id')
        numero_diamex = data.get('numero_diamex', '').strip()
        base_diamex = data.get('base_diamex', '').strip()
        montant_raw = data.get('montant')

        if not releve_id:
            return JsonResponse({
                'success': False,
                'error': 'ID du relevé manquant'
            }, status=400)

        allowed_ouvrage_ids = _get_responsable_scoped_ouvrage_ids(request.user)
        releve_qs = Releve.objects.filter(
            id=releve_id,
            point_eau__ouvrage_id__in=allowed_ouvrage_ids,
        )
        releve = releve_qs.get()

        if montant_raw in (None, ''):
            montant = Decimal(str(releve.montant or 0))
        else:
            try:
                montant = Decimal(str(montant_raw).replace(',', '.'))
            except Exception:
                return JsonResponse({
                    'success': False,
                    'error': 'Montant invalide'
                }, status=400)

            if montant < 0:
                return JsonResponse({
                    'success': False,
                    'error': 'Le montant ne peut pas être négatif'
                }, status=400)

        allowed_progs = _get_allowed_diamex_progs(request.user)
        if allowed_progs is not None and base_diamex and base_diamex not in allowed_progs:
            return JsonResponse({
                'success': False,
                'error': 'Base DiameX hors périmètre'
            }, status=403)

        # Mettre à jour les champs
        releve.numeroDiameX = numero_diamex if numero_diamex else None
        releve.baseDiameX = base_diamex if base_diamex else None
        releve.montant = montant
        releve.save()

        return JsonResponse({
            'success': True,
            'message': 'Relevé mis à jour avec succès',
            'releve': {
                'id': str(releve.id),
                'numero_diamex': releve.numeroDiameX or '',
                'base_diamex': releve.baseDiameX or '',
                'montant': float(releve.montant or 0),
            }
        })

    except Releve.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Relevé introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_pointage_releves_diamex(request):
    """
    Pointe un lot de relevés sur une ligne DiameX:
    - Vérifie que la somme des relevés = montant DiameX
    - Recopie numeroDiameX (id_access) et baseDiameX (prog) sur chaque relevé
    """
    from apps.billing.models import Releve

    try:
        data = json.loads(request.body)
        releve_ids = data.get('releve_ids') or []
        diamex_entry_id = data.get('diamex_entry_id')
        montant_diamex_selection = data.get('montant_diamex_selection')
        allowed_ouvrage_ids = _get_responsable_scoped_ouvrage_ids(request.user)

        if not isinstance(releve_ids, list) or not releve_ids:
            return JsonResponse({
                'success': False,
                'error': 'Aucun relevé sélectionné'
            }, status=400)

        if not diamex_entry_id:
            return JsonResponse({
                'success': False,
                'error': 'Ligne DiameX manquante'
            }, status=400)

        try:
            diamex_entry = BaseDiameX.objects.get(id=int(diamex_entry_id))
        except (BaseDiameX.DoesNotExist, ValueError, TypeError):
            return JsonResponse({
                'success': False,
                'error': 'Ligne DiameX introuvable'
            }, status=404)

        if (diamex_entry.compte_code or '') != '707401':
            return JsonResponse({
                'success': False,
                'error': 'La ligne sélectionnée n\'est pas du compte 707401'
            }, status=400)

        entry_allowed = False
        segments = []
        if diamex_entry.description and ';' in diamex_entry.description:
            segments = diviser_paiement_volume_multi(
                diamex_entry.description,
                diamex_entry.compte_code,
                diamex_entry.montant_in if diamex_entry.montant_in else 0
            )
        if segments:
            for segment in segments:
                extraction = segment.get('extraction') or {}
                ouvrage_obj = extraction.get('ouvrage_obj')
                if ouvrage_obj and ouvrage_obj.id in allowed_ouvrage_ids:
                    entry_allowed = True
                    break
        else:
            extraction = extraire_ouvrage_et_mois_generique(diamex_entry.description or '', diamex_entry.compte_code)
            ouvrage_obj = extraction.get('ouvrage_obj') if extraction else None
            entry_allowed = bool(ouvrage_obj and ouvrage_obj.id in allowed_ouvrage_ids)

        if not entry_allowed:
            return JsonResponse({
                'success': False,
                'error': 'Acces refuse a cette ligne DiameX'
            }, status=403)

        if diamex_entry.id_access is None:
            return JsonResponse({
                'success': False,
                'error': 'ID DiameX introuvable sur la ligne sélectionnée'
            }, status=400)

        if not (diamex_entry.prog or '').strip():
            return JsonResponse({
                'success': False,
                'error': 'Prog/Base DiameX introuvable sur la ligne sélectionnée'
            }, status=400)

        releves = list(
            Releve.objects.filter(
                id__in=releve_ids,
                point_eau__ouvrage_id__in=allowed_ouvrage_ids,
            )
        )
        if len(releves) != len(releve_ids):
            return JsonResponse({
                'success': False,
                'error': 'Un ou plusieurs releves sont introuvables ou hors scope'
            }, status=404)

        # Verrouiller uniquement les lignes déjà pointées via N°DiameX.
        # Une BaseDiameX résiduelle seule ne doit pas bloquer le re-pointage.
        locked_releves = [
            r for r in releves
            if str(r.numeroDiameX or '').strip()
        ]
        if locked_releves:
            return JsonResponse({
                'success': False,
                'error': (
                    f"{len(locked_releves)} relevé(s) déjà pointé(s) "
                    "sont verrouillés et ne peuvent pas être re-pointés."
                )
            }, status=400)

        total_releves = sum(Decimal(str(r.montant or 0)) for r in releves)
        montant_diamex = Decimal(str(diamex_entry.montant_in or 0))

        # Support des transactions multi-segments affichées dans le modal:
        # la ligne sélectionnée peut représenter une part du montant de l'écriture DiameX.
        if montant_diamex_selection is not None:
            try:
                montant_selection = Decimal(str(montant_diamex_selection))
                if Decimal('0') < montant_selection <= montant_diamex:
                    montant_diamex = montant_selection
            except Exception:
                pass

        ecart = total_releves - montant_diamex
        if abs(ecart) > Decimal('0.01'):
            return JsonResponse({
                'success': False,
                'error': (
                    f"Pointage impossible: total relevés ({total_releves}) "
                    f"≠ montant DiameX ({montant_diamex})"
                ),
                'total_releves': float(total_releves),
                'montant_diamex': float(montant_diamex),
                'ecart': float(ecart),
            }, status=400)

        numero_diamex = str(diamex_entry.id_access)
        base_diamex = (diamex_entry.prog or '').strip()

        with transaction.atomic():
            for releve in releves:
                releve.numeroDiameX = numero_diamex
                releve.baseDiameX = base_diamex
                releve.save(update_fields=['numeroDiameX', 'baseDiameX'])

        return JsonResponse({
            'success': True,
            'message': f'Pointage appliqué à {len(releves)} relevé(s)',
            'numero_diamex': numero_diamex,
            'base_diamex': base_diamex,
            'total_releves': float(total_releves),
            'montant_diamex': float(montant_diamex),
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_details_paiements_cartes_sociales(request):
    """
    Détails mensuels cartes sociales pour un ouvrage:
    - Lignes conso (prévu) depuis conso_cartes_sociales
    - Lignes compta (réalisé) depuis BaseDiameX compte 748415
    """
    try:
        from apps.billing.models import ConsoCarteSociale
        from apps.employees.models import EmployeBaseDiameX
        from apps.organization.models import Ouvrage

        ouvrage_id = request.GET.get('ouvrage_id')
        annee = request.GET.get('annee')
        mois = request.GET.get('mois')

        if not all([ouvrage_id, annee, mois]):
            return JsonResponse({
                'success': False,
                'error': 'Paramètres manquants (ouvrage_id, annee, mois requis)'
            }, status=400)

        try:
            annee = int(annee)
            mois = int(mois)
        except ValueError:
            return JsonResponse({
                'success': False,
                'error': 'Année et mois doivent être des entiers'
            }, status=400)

        allowed_ouvrage_ids = _get_responsable_scoped_ouvrage_ids(
            request.user,
            effective_gestionnaire_ids=_get_user_gestionnaire_ids(request.user),
            modalites=['au_volume', 'mixte'],
        )
        if str(ouvrage_id) not in _normalize_id_set(allowed_ouvrage_ids):
            return JsonResponse({
                'success': False,
                'error': 'Accès refusé pour cet ouvrage'
            }, status=403)

        try:
            ouvrage = Ouvrage.objects.get(id=ouvrage_id)
        except Ouvrage.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Ouvrage non trouvé'
            }, status=404)

        # Nettoyage automatique: les lignes sans consommation ne doivent pas rester dans la table.
        ConsoCarteSociale.objects.filter(
            carte_sociale__ouvrage_id=ouvrage_id,
            date__year=annee,
            date__month=mois
        ).filter(
            Q(volume_total__isnull=True) | Q(volume_total=0) | Q(quantite_bidons__isnull=True) | Q(quantite_bidons=0)
        ).delete()

        consos = ConsoCarteSociale.objects.filter(
            carte_sociale__ouvrage_id=ouvrage_id,
            date__year=annee,
            date__month=mois
        ).select_related(
            'carte_sociale',
            'carte_sociale__point_eau'
        ).order_by('date', 'id')

        consos_data = []
        total_consos = Decimal('0')
        pointed_couples = set()

        for conso in consos:
            montant = Decimal(str(conso.montant_paye or 0))
            total_consos += montant

            numero_diamex = (conso.numeroDiameX or '').strip()
            base_diamex = (conso.baseDiameX or '').strip()
            if numero_diamex and base_diamex:
                pointed_couples.add((numero_diamex, base_diamex))

            carte = conso.carte_sociale
            point_eau = carte.point_eau if carte else None
            consos_data.append({
                'id': str(conso.id),
                'date': conso.date.strftime('%d/%m/%Y') if conso.date else '-',
                'numero_carte': (carte.numero_carte if carte else '') or '-',
                'beneficiaire': (carte.nom_beneficiaire if carte else '') or '-',
                'point_eau': (point_eau.nomabonne if point_eau else '') or '-',
                'quantite_bidons': int(conso.quantite_bidons or 0),
                'volume_total': float(conso.volume_total or 0),
                'montant_paye': float(montant),
                'numeroDiameX': conso.numeroDiameX or '',
                'baseDiameX': conso.baseDiameX or '',
                'can_delete': Decimal(str(conso.volume_total or 0)) == Decimal('0'),
                'is_pointed': bool(numero_diamex and base_diamex),
            })

        # Lignes comptables 748415 rattachées via extracteur.
        transactions_data = []
        total_diamex = Decimal('0')
        diamex_748415 = BaseDiameX.objects.filter(compte_code='748415')
        base_cache = {}

        def _resolve_scan_path(scan_value, prog_value):
            scan_raw = (scan_value or '').strip()
            if not scan_raw:
                return ''

            scan_clean = scan_raw.lstrip('#')
            if (
                (len(scan_clean) > 2 and scan_clean[1] == ':' and scan_clean[2] in ('\\', '/')) or
                scan_clean.startswith('\\\\') or
                scan_clean.startswith('/')
            ):
                return scan_clean

            prog_key = (prog_value or '').strip()
            if not prog_key:
                return scan_clean

            if prog_key not in base_cache:
                base_cache[prog_key] = EmployeBaseDiameX.objects.filter(base_diamex__icontains=prog_key).first()

            employe_base = base_cache.get(prog_key)
            chemin_base = (employe_base.chemin_base_diamex or '').strip() if employe_base else ''
            if not chemin_base:
                return scan_clean

            scan_rel = scan_clean[2:] if scan_clean.startswith('./') or scan_clean.startswith('.\\') else scan_clean.lstrip('.')
            return os.path.normpath(os.path.join(chemin_base, scan_rel.lstrip('\\/')))

        for entry in diamex_748415:
            extraction = extraire_ouvrage_et_mois_generique(entry.description or '', entry.compte_code)
            ouvrage_obj = extraction.get('ouvrage_obj')
            if not ouvrage_obj or ouvrage_obj.id != ouvrage.id:
                continue
            if extraction.get('annee') != annee or extraction.get('mois') != mois:
                continue

            montant_entry = Decimal(str(entry.montant_in or 0))
            numero_diamex = str(entry.id_access).strip() if entry.id_access is not None else ''
            base_diamex = (entry.prog or '').strip()
            already_pointed = bool(numero_diamex and base_diamex and (numero_diamex, base_diamex) in pointed_couples)
            scan_path = _resolve_scan_path(entry.scan, entry.prog)

            transactions_data.append({
                'id': entry.id,
                'entry_id': entry.id,
                'id_access': numero_diamex,
                'date_rec': entry.date_rec.strftime('%d/%m/%Y') if entry.date_rec else '-',
                'description': entry.description or '',
                'montant_in': float(montant_entry),
                'prog': entry.prog or '',
                'scan': entry.scan or '',
                'scan_path': scan_path,
                'rec': entry.rec or '',
                'already_pointed': already_pointed
            })
            total_diamex += montant_entry

        ecart = total_consos - total_diamex
        if abs(ecart) < Decimal('0.01'):
            status = 'ok'
        elif abs(ecart) < Decimal('100'):
            status = 'warning'
        else:
            status = 'error'

        auto_pointage_data = build_auto_pointage_suggestions(consos_data, transactions_data)

        return JsonResponse({
            'success': True,
            'ouvrage': {
                'id': str(ouvrage.id),
                'nom': ouvrage.nom_ouvrage
            },
            'periode': {
                'mois': mois,
                'annee': annee,
                'label': f"{mois:02d}/{annee}"
            },
            'consos': consos_data,
            'transactions_diamex': transactions_data,
            'stats': {
                'nb_consos': len(consos_data),
                'nb_transactions_diamex': len(transactions_data),
                'total_consos': float(total_consos),
                'total_diamex': float(total_diamex),
                'ecart': float(ecart),
                'status': status,
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_pointage_consos_cartes_sociales(request):
    """
    Pointe un lot de lignes conso cartes sociales sur une ligne DiameX 748415:
    - Vérifie que somme conso = montant DiameX
    - Recopie numeroDiameX (id_access) et baseDiameX (prog) sur chaque conso
    """
    try:
        from apps.billing.models import ConsoCarteSociale

        data = json.loads(request.body)
        conso_ids = data.get('conso_ids') or []
        diamex_entry_id = data.get('diamex_entry_id')
        montant_diamex_selection = data.get('montant_diamex_selection')
        allowed_ouvrage_ids = _get_responsable_scoped_ouvrage_ids(
            request.user,
            effective_gestionnaire_ids=_get_user_gestionnaire_ids(request.user),
            modalites=['au_volume', 'mixte'],
        )

        if not isinstance(conso_ids, list) or not conso_ids:
            return JsonResponse({
                'success': False,
                'error': 'Aucune ligne conso sélectionnée'
            }, status=400)
        if not diamex_entry_id:
            return JsonResponse({
                'success': False,
                'error': 'Ligne DiameX manquante'
            }, status=400)

        try:
            diamex_entry = BaseDiameX.objects.get(id=int(diamex_entry_id))
        except (BaseDiameX.DoesNotExist, ValueError, TypeError):
            return JsonResponse({
                'success': False,
                'error': 'Ligne DiameX introuvable'
            }, status=404)

        if (diamex_entry.compte_code or '') != '748415':
            return JsonResponse({
                'success': False,
                'error': 'La ligne sélectionnée n\'est pas du compte 748415'
            }, status=400)

        if diamex_entry.id_access is None:
            return JsonResponse({
                'success': False,
                'error': 'ID DiameX introuvable sur la ligne sélectionnée'
            }, status=400)
        if not (diamex_entry.prog or '').strip():
            return JsonResponse({
                'success': False,
                'error': 'Prog/Base DiameX introuvable sur la ligne sélectionnée'
            }, status=400)

        entry_allowed = False
        extraction_info = extraire_ouvrage_et_mois_generique(diamex_entry.description or '', diamex_entry.compte_code)
        extraction_items = extraction_info if isinstance(extraction_info, list) else [extraction_info]
        for extraction in extraction_items:
            if not isinstance(extraction, dict):
                continue
            ouvrage_obj = extraction.get('ouvrage_obj')
            if ouvrage_obj and ouvrage_obj.id in allowed_ouvrage_ids:
                entry_allowed = True
                break

        if not entry_allowed:
            return JsonResponse({
                'success': False,
                'error': 'Acces refuse a cette ligne DiameX'
            }, status=403)

        consos = list(
            ConsoCarteSociale.objects.filter(
                id__in=conso_ids,
                carte_sociale__ouvrage_id__in=allowed_ouvrage_ids,
            )
        )
        if len(consos) != len(conso_ids):
            return JsonResponse({
                'success': False,
                'error': 'Une ou plusieurs lignes conso sont introuvables ou hors scope'
            }, status=404)

        total_consos = sum(Decimal(str(c.montant_paye or 0)) for c in consos)
        montant_diamex = Decimal(str(diamex_entry.montant_in or 0))
        if montant_diamex_selection is not None:
            try:
                montant_selection = Decimal(str(montant_diamex_selection))
                if Decimal('0') < montant_selection <= montant_diamex:
                    montant_diamex = montant_selection
            except Exception:
                pass

        ecart = total_consos - montant_diamex
        if abs(ecart) > Decimal('0.01'):
            return JsonResponse({
                'success': False,
                'error': (
                    f"Pointage impossible: total conso ({total_consos}) "
                    f"≠ montant DiameX ({montant_diamex})"
                ),
                'total_consos': float(total_consos),
                'montant_diamex': float(montant_diamex),
                'ecart': float(ecart),
            }, status=400)

        numero_diamex = str(diamex_entry.id_access)
        base_diamex = (diamex_entry.prog or '').strip()

        with transaction.atomic():
            for conso in consos:
                conso.numeroDiameX = numero_diamex
                conso.baseDiameX = base_diamex
                conso.save(update_fields=['numeroDiameX', 'baseDiameX'])

        return JsonResponse({
            'success': True,
            'message': f'Pointage appliqué à {len(consos)} ligne(s) conso',
            'numero_diamex': numero_diamex,
            'base_diamex': base_diamex,
            'total_consos': float(total_consos),
            'montant_diamex': float(montant_diamex),
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_delete_conso_carte_sociale_zero(request):
    """Supprime une facture/conso carte sociale uniquement si son volume est egal a 0."""
    try:
        from apps.billing.models import ConsoCarteSociale

        data = json.loads(request.body or '{}')
        conso_id = data.get('conso_id')
        if not conso_id:
            return JsonResponse({'success': False, 'error': 'conso_id manquant'}, status=400)

        allowed_ouvrage_ids = _get_responsable_scoped_ouvrage_ids(
            request.user,
            effective_gestionnaire_ids=_get_user_gestionnaire_ids(request.user),
            modalites=['au_volume', 'mixte'],
        )
        conso = ConsoCarteSociale.objects.select_related('carte_sociale').filter(
            id=conso_id,
            carte_sociale__ouvrage_id__in=allowed_ouvrage_ids,
        ).first()
        if not conso:
            return JsonResponse({'success': False, 'error': 'Facture introuvable ou hors scope'}, status=404)

        volume = Decimal(str(conso.volume_total or 0))
        if volume != Decimal('0'):
            return JsonResponse({
                'success': False,
                'error': 'Suppression refusee: le volume de cette facture est different de 0'
            }, status=400)

        conso.delete()
        return JsonResponse({'success': True, 'message': 'Facture a volume 0 supprimee'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_annuler_pointage_conso_carte_sociale(request):
    """Annule le pointage DiameX d'une ligne de consommation carte sociale."""
    try:
        from apps.billing.models import ConsoCarteSociale

        data = json.loads(request.body or '{}')
        conso_id = data.get('conso_id')
        if not conso_id:
            return JsonResponse({'success': False, 'error': 'conso_id manquant'}, status=400)

        allowed_ouvrage_ids = _get_responsable_scoped_ouvrage_ids(
            request.user,
            effective_gestionnaire_ids=_get_user_gestionnaire_ids(request.user),
            modalites=['au_volume', 'mixte'],
        )
        conso = ConsoCarteSociale.objects.select_related('carte_sociale').filter(
            id=conso_id,
            carte_sociale__ouvrage_id__in=allowed_ouvrage_ids,
        ).first()
        if not conso:
            return JsonResponse({'success': False, 'error': 'Ligne conso introuvable ou hors scope'}, status=404)

        conso.numeroDiameX = ''
        conso.baseDiameX = ''
        conso.save(update_fields=['numeroDiameX', 'baseDiameX'])
        return JsonResponse({'success': True, 'message': 'Pointage annule'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_annuler_pointage_releves_diamex(request):
    """
    Annule un pointage volume pour un couple (numeroDiameX, baseDiameX).

    Effets:
    - vide numeroDiameX/baseDiameX sur tous les relevés du couple dans le périmètre autorisé
    - rend à nouveau disponible la ligne comptable 707401 correspondante
    """
    from apps.billing.models import Releve

    try:
        employe = getattr(request.user, 'employe', None)
        if not employe or not employe.is_directeur:
            return JsonResponse({
                'success': False,
                'error': 'Accès refusé. Seul un directeur peut annuler un pointage.'
            }, status=403)

        data = json.loads(request.body)
        numero_diamex = str(data.get('numero_diamex') or '').strip()
        base_diamex = str(data.get('base_diamex') or '').strip()

        if not numero_diamex:
            return JsonResponse({
                'success': False,
                'error': 'Numero DiameX manquant'
            }, status=400)
        if not base_diamex:
            return JsonResponse({
                'success': False,
                'error': 'Base DiameX manquante'
            }, status=400)

        allowed_progs = _get_allowed_diamex_progs(request.user)
        if allowed_progs is not None and base_diamex not in allowed_progs:
            return JsonResponse({
                'success': False,
                'error': 'Base DiameX hors périmètre'
            }, status=403)

        allowed_ouvrage_ids = _get_responsable_scoped_ouvrage_ids(request.user)
        releves_qs = Releve.objects.filter(
            numeroDiameX=numero_diamex,
            baseDiameX=base_diamex,
            point_eau__ouvrage_id__in=allowed_ouvrage_ids,
        )
        releves = list(releves_qs)
        if not releves:
            return JsonResponse({
                'success': False,
                'error': 'Aucun relevé ne correspond à ce pointage'
            }, status=404)

        try:
            numero_diamex_int = int(numero_diamex)
        except (TypeError, ValueError):
            numero_diamex_int = None

        diamex_entries_qs = _get_diamex_scope_by_prog(request.user).filter(
            compte_code='707401',
            prog=base_diamex,
        )
        if numero_diamex_int is not None:
            diamex_entries_qs = diamex_entries_qs.filter(id_access=numero_diamex_int)
        else:
            diamex_entries_qs = diamex_entries_qs.none()

        releve_ids = [str(releve.id) for releve in releves]
        diamex_entry_ids = list(diamex_entries_qs.values_list('id', flat=True))

        with transaction.atomic():
            Releve.objects.filter(id__in=releve_ids).update(
                numeroDiameX=None,
                baseDiameX=None
            )

        return JsonResponse({
            'success': True,
            'message': (
                f'Pointage annulé pour {len(releve_ids)} relevé(s). '
                f'{len(diamex_entry_ids)} ligne(s) comptables 707401 partageaient ce couple.'
            ),
            'numero_diamex': numero_diamex,
            'base_diamex': base_diamex,
            'releve_ids': releve_ids,
            'diamex_entry_ids': diamex_entry_ids,
            'releves_count': len(releve_ids),
            'diamex_entries_count': len(diamex_entry_ids),
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_delete_releve_pointage(request):
    """Supprime un relevé depuis le modal (réservé au directeur)."""
    from apps.billing.models import Releve

    try:
        employe = getattr(request.user, 'employe', None)
        if not employe or not employe.is_directeur:
            return JsonResponse({
                'success': False,
                'error': 'Accès refusé. Seul un directeur peut supprimer un relevé.'
            }, status=403)

        data = json.loads(request.body)
        releve_id = data.get('releve_id')
        if not releve_id:
            return JsonResponse({
                'success': False,
                'error': 'ID relevé manquant'
            }, status=400)

        allowed_ouvrage_ids = _get_responsable_scoped_ouvrage_ids(request.user)
        try:
            releve = Releve.objects.get(
                id=releve_id,
                point_eau__ouvrage_id__in=allowed_ouvrage_ids,
            )
        except Releve.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Relevé introuvable'
            }, status=404)

        releve.delete()
        return JsonResponse({
            'success': True,
            'message': 'Relevé supprimé avec succès'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def dashboard_comptabilite(request):
    """
    Tableau de bord comptabilité avec statistiques détaillées par catégorie
    """
    from apps.organization.models import Base
    from datetime import date
    from dateutil.relativedelta import relativedelta

    # Récupération des filtres
    annee = request.GET.get('annee', '')
    mois = request.GET.get('mois', '')
    fichier_source = request.GET.get('fichier_source', '')
    prog_code = request.GET.get('prog', '')
    selected_fin_filters = request.GET.getlist('fin_category')

    # Base queryset : mêmes restrictions que l'accueil compta (périmètre des programmes de
    # l'utilisateur, lignes salaires / IRSA / CNaPS / FMFP masquées aux postes non autorisés)
    base_scope = _exclude_sensitive_diamex_lines_for_non_privileged(
        _get_diamex_scope_by_prog(request.user), request.user
    )
    entries = base_scope.select_related('journal', 'compte')
    fin_entries_source = base_scope.select_related('journal', 'compte')

    # Appliquer les filtres
    if mois:
        year, month = mois.split('-')
        entries = entries.filter(date_m__year=year, date_m__month=month)
        last_day = calendar.monthrange(int(year), int(month))[1]
        cutoff_date = date(int(year), int(month), last_day)
        fin_entries_source = fin_entries_source.filter(date_m__lte=cutoff_date)
    elif annee and annee.isdigit():
        # Recettes / dépenses par catégorie = flux : l'année seule est correcte.
        entries = entries.filter(date_m__year=int(annee))
        # Soldes par financement (Fin) = stock : cumul jusqu'au 31/12 de l'année, comme le filtre
        # Mois (fin de mois) et l'accueil compta ; sinon le report des années précédentes manque.
        fin_entries_source = fin_entries_source.filter(date_m__lte=date(int(annee), 12, 31))
    elif annee:
        annee = ''  # année invalide dans l'URL : ignorée (auparavant : erreur 500)

    if fichier_source:
        entries = entries.filter(fichier_source=fichier_source)
        fin_entries_source = fin_entries_source.filter(fichier_source=fichier_source)

    if prog_code:
        entries = entries.filter(prog=prog_code)
        fin_entries_source = fin_entries_source.filter(prog=prog_code)

    # Filtrer uniquement les entrées avec montant (recettes OU dépenses)
    entries = entries.filter(Q(montant_in__gt=0) | Q(montant_out__gt=0))
    fin_entries_source = fin_entries_source.filter(Q(montant_in__gt=0) | Q(montant_out__gt=0))

    # Calculer les soldes Fin avec la même logique que l'accueil compta:
    # - toutes les lignes sauf 00PERS et 00BOOK
    # - regrouper sous "Sans financement" si fin vide
    # - EDF alimente le solde mais pas les colonnes recettes/sorties
    #   dès que le compte ou journal est en 00FNDx
    entries_fin = fin_entries_source.exclude(
        Q(compte_code__startswith='00PERS') |
        Q(compte_code__startswith='00BOOK')
    )

    # Stats détaillées Fin par sous-catégorie (champ 'fin')
    fin_details = defaultdict(lambda: {
        'label': '',
        'edf': Decimal('0'),
        'in': Decimal('0'),
        'out': Decimal('0'),
        'solde': Decimal('0'),
        'count': 0
    })

    for entry in entries_fin:
        fin_raw = _clean_fin_label(entry.fin)
        fin_cat = fin_raw or 'Sans financement'
        fin_key = _normalize_fin_bucket(fin_cat) or '(vide)'
        montant_in = Decimal(str(entry.montant_in)) if entry.montant_in is not None else Decimal('0')
        montant_out = Decimal(str(entry.montant_out)) if entry.montant_out is not None else Decimal('0')
        is_edf_line = _is_edf_financement_entry(entry)
        solde_entry = montant_in - montant_out

        if not fin_details[fin_key]['label'] or (
            fin_cat != 'Sans financement' and len(fin_cat) < len(fin_details[fin_key]['label'])
        ):
            fin_details[fin_key]['label'] = fin_cat

        if is_edf_line:
            fin_details[fin_key]['edf'] += solde_entry
        else:
            fin_details[fin_key]['in'] += montant_in
            fin_details[fin_key]['out'] += montant_out
        fin_details[fin_key]['solde'] += solde_entry
        fin_details[fin_key]['count'] += 1

    # Total aligné avec compta_home: somme des soldes par financement,
    # avec les lignes EDF incluses dans le solde uniquement.
    solde_fin_edf = sum((item['edf'] for item in fin_details.values()), Decimal('0'))
    solde_fin_in = sum((item['in'] for item in fin_details.values()), Decimal('0'))
    solde_fin_out = sum((item['out'] for item in fin_details.values()), Decimal('0'))
    solde_fin_montant = sum((item['solde'] for item in fin_details.values()), Decimal('0'))

    # Activ = code compte ne commence pas par 00
    entries_activ = entries.exclude(compte_code__startswith='00')

    # Stats détaillées Activ par sous-catégorie (champ 'activ')
    activ_details = defaultdict(lambda: {
        'in': Decimal('0'),
        'out': Decimal('0'),
        'solde': Decimal('0'),
        'count': 0
    })

    for entry in entries_activ:
        activ_cat = entry.activ if entry.activ else '(Vide)'
        montant_in = Decimal(str(entry.montant_in)) if entry.montant_in is not None else Decimal('0')
        montant_out = Decimal(str(entry.montant_out)) if entry.montant_out is not None else Decimal('0')

        activ_details[activ_cat]['in'] += montant_in
        activ_details[activ_cat]['out'] += montant_out
        activ_details[activ_cat]['solde'] = activ_details[activ_cat]['in'] - activ_details[activ_cat]['out']
        activ_details[activ_cat]['count'] += 1

    # Totaux Activ
    solde_activ = entries_activ.aggregate(
        total_in=Sum('montant_in'),
        total_out=Sum('montant_out')
    )
    solde_activ_montant = (solde_activ['total_in'] or 0) - (solde_activ['total_out'] or 0)

    # Exclure transferts et avances pour recettes/dépenses
    entries_recettes_depenses = entries.exclude(
        Q(compte_code__startswith='00BOOK') |
        Q(compte_code__startswith='00PERS')
    ).exclude(
        Q(compte_code__startswith='00FND1') &
        ~(Q(description__icontains='EDF') | Q(info__icontains='EDF'))
    )

    fin_filter_options, selected_fin_filters, category_fin_raw_values = (
        _build_dashboard_fin_filter_options(
            entries_recettes_depenses.values_list('fin', flat=True).distinct(),
            selected_fin_filters,
        )
    )
    category_entries = entries_recettes_depenses
    if selected_fin_filters:
        non_null_fin_values = [value for value in category_fin_raw_values if value is not None]
        fin_query = Q(fin__in=non_null_fin_values)
        if None in category_fin_raw_values:
            fin_query |= Q(fin__isnull=True)
        category_entries = category_entries.filter(fin_query)

    # Calculer les stats globales
    total_recettes = entries_recettes_depenses.aggregate(total=Sum('montant_in'))['total'] or 0
    total_depenses = entries_recettes_depenses.aggregate(total=Sum('montant_out'))['total'] or 0
    solde_global = total_recettes - total_depenses

    # Stats par catégorie
    categories_stats = defaultdict(lambda: {
        'recettes': Decimal('0'),
        'depenses': Decimal('0'),
        'solde': Decimal('0'),
        'count': 0
    })

    # Liste des catégories
    categories_parentes = [
        'Transferts 00BOOK', 'Transferts 00FND1', 'EDF', 'Compte de tiers', 'Acquisition', 'Matériaux',
        'Fournitures', 'équipement', 'Carburant', 'Fonctionnement',
        'Entretien véhicules', "Main d'Å“uvre", 'Paiements employés', 'Impots',
        'Autres recettes',
        'Vente eau au volume', 'Paiement extension', 'Vente eau au forfait',
        'Vente carte sociale', 'Autres'
    ]

    category_totals = category_entries.aggregate(
        recettes=Sum('montant_in'),
        depenses=Sum('montant_out'),
    )
    category_total_recettes = Decimal(str(category_totals['recettes'] or 0))
    category_total_depenses = Decimal(str(category_totals['depenses'] or 0))
    category_solde_global = category_total_recettes - category_total_depenses

    # Calculer les stats pour chaque catégorie
    # Note: Nous devons itérer car get_categorie_parente() est une méthode Python
    for entry in category_entries:
        categorie = _group_dashboard_parent_category(entry.get_categorie_parente())

        # Convertir explicitement en Decimal pour éviter les erreurs de type
        montant_in = Decimal(str(entry.montant_in)) if entry.montant_in is not None else Decimal('0')
        montant_out = Decimal(str(entry.montant_out)) if entry.montant_out is not None else Decimal('0')

        categories_stats[categorie]['recettes'] += montant_in
        categories_stats[categorie]['depenses'] += montant_out
        categories_stats[categorie]['solde'] = categories_stats[categorie]['recettes'] - categories_stats[categorie]['depenses']
        categories_stats[categorie]['count'] += 1

    # Trier les catégories par dépenses décroissantes et formater
    categories_data = []
    for cat in categories_parentes:
        if cat in categories_stats or categories_stats[cat]['count'] > 0:
            recettes = categories_stats[cat]['recettes']
            depenses = categories_stats[cat]['depenses']
            progression_recettes = 0
            progression_depenses = 0
            if category_total_recettes > 0:
                progression_recettes = int((recettes / category_total_recettes) * 100)
            if category_total_depenses > 0:
                progression_depenses = int((depenses / category_total_depenses) * 100)
            categories_data.append({
                'nom': cat,
                'filter_name': cat,
                'compte_categorie': 'paiements_employes' if cat == 'Paiements employés' else '',
                'recettes': recettes,
                'depenses': depenses,
                'solde': categories_stats[cat]['solde'],
                'count': categories_stats[cat]['count'],
                'progression_recettes': progression_recettes,
                'progression_depenses': progression_depenses,
            })
    categories_data.sort(key=lambda item: (item['depenses'], item['count']), reverse=True)

    # Listes pour filtres
    annees = sorted(set(
        y for y in BaseDiameX.objects.exclude(date_m__isnull=True).values_list('date_m__year', flat=True).distinct() if y
    ), reverse=True)
    fichiers_sources = sorted(set(
        f for f in BaseDiameX.objects.values_list('fichier_source', flat=True).distinct() if f
    ))
    progs_codes = sorted(set(
        p for p in BaseDiameX.objects.values_list('prog', flat=True).distinct() if p
    ))

    # Formater les détails Fin et Activ pour le template
    fin_details_list = [
        {
            'nom': fin_details[cat]['label'] or cat,
            'edf': fin_details[cat]['edf'],
            'in': fin_details[cat]['in'],
            'out': fin_details[cat]['out'],
            'solde': fin_details[cat]['solde'],
            'count': fin_details[cat]['count']
        }
        for cat in sorted(fin_details.keys(), key=lambda key: _normalize_text(fin_details[key]['label'] or key))
    ]

    activ_details_list = [
        {
            'nom': cat,
            'in': activ_details[cat]['in'],
            'out': activ_details[cat]['out'],
            'solde': activ_details[cat]['solde'],
            'count': activ_details[cat]['count']
        }
        for cat in sorted(activ_details.keys())
    ]

    # === SOLDES DES JOURNAUX (début et fin de période) ===
    soldes_journaux = {}
    if mois or annee:
        if mois:
            year, month = mois.split('-')
            date_debut = date(int(year), int(month), 1)
            date_fin = (date_debut + relativedelta(months=1)) - relativedelta(days=1)
        else:
            date_debut = date(int(annee), 1, 1)
            date_fin = date(int(annee), 12, 31)

        # Optimisation : récupérer seulement les journaux avec activité pendant la période
        # (exclure 00PERS et 00SPLITBOOK-MGA qui ne sont pas de vrais journaux)
        journaux_qs = BaseDiameX.objects.exclude(
            journal_code__in=['00PERS', '00SPLITBOOK-MGA', '', None]
        )
        if fichier_source:
            journaux_qs = journaux_qs.filter(fichier_source=fichier_source)
        if prog_code:
            journaux_qs = journaux_qs.filter(prog=prog_code)

        journaux = journaux_qs.values_list('journal_code', flat=True).distinct()

        for journal_code in journaux:
            if not journal_code:
                continue

            # Solde au début (toutes les entrées avant le début de la période)
            entries_avant = BaseDiameX.objects.filter(
                journal_code=journal_code,
                date_m__lt=date_debut
            )
            if fichier_source:
                entries_avant = entries_avant.filter(fichier_source=fichier_source)
            if prog_code:
                entries_avant = entries_avant.filter(prog=prog_code)

            solde_debut_data = entries_avant.aggregate(
                total_in=Sum('montant_in'),
                total_out=Sum('montant_out')
            )
            solde_debut = (solde_debut_data['total_in'] or 0) - (solde_debut_data['total_out'] or 0)

            # Solde à la fin (toutes les entrées jusqu'à la fin de la période)
            entries_fin = BaseDiameX.objects.filter(
                journal_code=journal_code,
                date_m__lte=date_fin
            )
            if fichier_source:
                entries_fin = entries_fin.filter(fichier_source=fichier_source)
            if prog_code:
                entries_fin = entries_fin.filter(prog=prog_code)

            solde_fin_data = entries_fin.aggregate(
                total_in=Sum('montant_in'),
                total_out=Sum('montant_out')
            )
            solde_fin_journal = (solde_fin_data['total_in'] or 0) - (solde_fin_data['total_out'] or 0)

            # Mouvement de la période
            mouvement = solde_fin_journal - solde_debut

            # Ne garder que les journaux avec activité
            if solde_debut != 0 or solde_fin_journal != 0 or mouvement != 0:
                soldes_journaux[journal_code] = {
                    'solde_debut': solde_debut,
                    'mouvement': mouvement,
                    'solde_fin': solde_fin_journal
                }

    # === SOLDES DES COMPTES DE TIERS (00PERS) ===
    from apps.billing.models import Fournisseur

    # Charger tous les fournisseurs pour mapping IDxls -> nom
    fournisseurs_dict = {
        str(f.idxls): f.nom_fournisseur
        for f in Fournisseur.objects.filter(idxls__isnull=False)
    }

    # Filtrer les entrées 00PERS
    pers_entries = BaseDiameX.objects.filter(
        Q(compte_code__startswith='00PERS') | Q(journal_code__startswith='00PERS')
    )

    # Appliquer les filtres
    if fichier_source:
        pers_entries = pers_entries.filter(fichier_source=fichier_source)
    if mois:
        year, month = mois.split('-')
        pers_entries = pers_entries.filter(date_m__year=year, date_m__month=month)
    elif annee:
        pers_entries = pers_entries.filter(date_m__year=annee)
    if prog_code:
        pers_entries = pers_entries.filter(prog=prog_code)

    # Calculer solde par tiers
    soldes_par_tiers = defaultdict(lambda: {
        'org_doit': Decimal('0'),
        'tiers_doit': Decimal('0'),
        'solde': Decimal('0'),
        'type': 'inconnu',
        'nom_original': ''
    })

    for entry in pers_entries:
        # Ignorer les lignes avec Match non vide
        if entry.match:
            continue

        tiers_original = entry.pers or 'Non spécifié'
        tiers = tiers_original.lower()
        montant_in = Decimal(str(entry.montant_in or 0))
        montant_out = Decimal(str(entry.montant_out or 0))

        # Nom d'affichage
        if not soldes_par_tiers[tiers]['nom_original']:
            nom_affichage = tiers_original
            if tiers_original != 'Non spécifié':
                try:
                    int(tiers_original)
                    nom_fournisseur = fournisseurs_dict.get(tiers_original)
                    if nom_fournisseur:
                        nom_affichage = f"{nom_fournisseur} ({tiers_original})"
                    else:
                        nom_affichage = f"Fournisseur #{tiers_original}"
                except (ValueError, TypeError):
                    pass
            soldes_par_tiers[tiers]['nom_original'] = nom_affichage

        # Type de tiers
        if tiers_original != 'Non spécifié':
            try:
                int(tiers_original)
                soldes_par_tiers[tiers]['type'] = 'fournisseur'
            except (ValueError, TypeError):
                soldes_par_tiers[tiers]['type'] = 'employe'

        # Calcul selon compte ou journal
        if entry.compte_code and '00PERS' in entry.compte_code:
            soldes_par_tiers[tiers]['tiers_doit'] += montant_out
            soldes_par_tiers[tiers]['org_doit'] += montant_in
            soldes_par_tiers[tiers]['solde'] += montant_out - montant_in
        elif entry.journal_code and '00PERS' in entry.journal_code:
            soldes_par_tiers[tiers]['tiers_doit'] += montant_in
            soldes_par_tiers[tiers]['org_doit'] += montant_out
            soldes_par_tiers[tiers]['solde'] += montant_in - montant_out

    # Filtrer soldes non nuls
    soldes_tiers_list = []
    for tiers_key, data in soldes_par_tiers.items():
        if abs(float(data['solde'])) > 0.01:  # Tolérance de 1 centime
            soldes_tiers_list.append({
                'nom': data['nom_original'],
                'type': data['type'],
                'org_doit': data['org_doit'],
                'tiers_doit': data['tiers_doit'],
                'solde': data['solde']
            })

    # Trier par solde décroissant
    soldes_tiers_list.sort(key=lambda x: abs(float(x['solde'])), reverse=True)

    context = {
        'base_template': 'analyses/base.html' if getattr(request, 'is_analyses_subdomain', False) else 'accounting/base.html',
        'total_recettes': total_recettes,
        'total_depenses': total_depenses,
        'solde_global': solde_global,
        'annees': annees,
        'annee': annee,
        'mois': mois,
        'fichier_source': fichier_source,
        'prog_code': prog_code,
        'solde_fin_edf': solde_fin_edf,
        'solde_fin_in': solde_fin_in,
        'solde_fin_out': solde_fin_out,
        'solde_fin': solde_fin_montant,
        'fin_details': fin_details_list,
        'solde_activ_in': solde_activ['total_in'] or 0,
        'solde_activ_out': solde_activ['total_out'] or 0,
        'solde_activ': solde_activ_montant,
        'activ_details': activ_details_list,
        'categories_data': categories_data,
        'fin_filter_options': fin_filter_options,
        'selected_fin_filters': selected_fin_filters,
        'category_fin_raw_values': category_fin_raw_values,
        'category_total_recettes': category_total_recettes,
        'category_total_depenses': category_total_depenses,
        'category_solde_global': category_solde_global,
        'fichiers_sources': fichiers_sources,
        'progs_codes': progs_codes,
        'soldes_journaux': soldes_journaux,
        'soldes_tiers': soldes_tiers_list,
    }

    return render(request, 'accounting/dashboard_comptabilite.html', context)


@login_required
def analyse_categorie_salaires(request):
    from apps.employees.models import Employe, GrilleSalaire, Salaire, Poste

    if not _can_view_sensitive_diamex_lines(request.user) and not getattr(request.user, 'is_superuser', False):
        return render(request, 'accounting/compta_forbidden.html', status=403)

    current_year = timezone.now().year
    try:
        annee = int(request.GET.get('annee') or current_year)
    except (TypeError, ValueError):
        annee = current_year

    mois = request.GET.get('mois', '')
    organisation_id = request.GET.get('organisation', '')
    base_id = request.GET.get('base', '')
    poste_id = request.GET.get('poste', '')
    employe_id = request.GET.get('employe', '')

    allowed_organisation_ids = _get_user_scope_organisation_ids(request.user)

    organisations_qs = Organisation.objects.all()
    if allowed_organisation_ids is not None:
        organisations_qs = organisations_qs.filter(id__in=allowed_organisation_ids)
    if organisation_id:
        organisations_qs = organisations_qs.filter(id=organisation_id)

    bases_qs = Base.objects.select_related('organisation').all()
    if allowed_organisation_ids is not None:
        bases_qs = bases_qs.filter(organisation_id__in=allowed_organisation_ids)
    if organisation_id:
        bases_qs = bases_qs.filter(organisation_id=organisation_id)

    postes_qs = Poste.objects.select_related('organisation').all()
    if allowed_organisation_ids is not None:
        postes_qs = postes_qs.filter(organisation_id__in=allowed_organisation_ids)
    if organisation_id:
        postes_qs = postes_qs.filter(organisation_id=organisation_id)

    employes_qs = Employe.objects.select_related('base', 'base__organisation', 'poste').all()
    if allowed_organisation_ids is not None:
        employes_qs = employes_qs.filter(base__organisation_id__in=allowed_organisation_ids)
    if organisation_id:
        employes_qs = employes_qs.filter(base__organisation_id=organisation_id)
    if base_id:
        employes_qs = employes_qs.filter(base_id=base_id)
    if poste_id:
        employes_qs = employes_qs.filter(poste_id=poste_id)

    grilles_qs = GrilleSalaire.objects.select_related(
        'contrat',
        'contrat__employe',
        'contrat__employe__base',
        'contrat__employe__base__organisation',
        'contrat__employe__poste',
        'contrat__poste',
    ).prefetch_related('salaires').filter(date_salaire__year=annee)

    if allowed_organisation_ids is not None:
        grilles_qs = grilles_qs.filter(contrat__employe__base__organisation_id__in=allowed_organisation_ids)
    if mois:
        grilles_qs = grilles_qs.filter(date_salaire__month=mois)
    if organisation_id:
        grilles_qs = grilles_qs.filter(contrat__employe__base__organisation_id=organisation_id)
    if base_id:
        grilles_qs = grilles_qs.filter(contrat__employe__base_id=base_id)
    if poste_id:
        grilles_qs = grilles_qs.filter(Q(contrat__poste_id=poste_id) | Q(contrat__employe__poste_id=poste_id))
    if employe_id:
        grilles_qs = grilles_qs.filter(contrat__employe_id=employe_id)

    salaires_qs = Salaire.objects.select_related(
        'grille_salaire',
        'grille_salaire__contrat',
        'grille_salaire__contrat__employe',
        'grille_salaire__contrat__employe__base',
        'grille_salaire__contrat__employe__base__organisation',
    ).filter(grille_salaire__in=grilles_qs)

    rh_totaux = grilles_qs.aggregate(
        total_brut=Sum('salaire_brut_total'),
        total_cnaps_employe=Sum('charge_cnaps_employe'),
        total_irsa=Sum('irsa'),
        total_mutuelle=Sum('mutuelle_sante'),
        total_net=Sum('salaire_net'),
    )
    paiements_totaux = salaires_qs.aggregate(
        total_net_paye=Sum('salaire_net_paye'),
        total_irsa_paye=Sum('irsa_paye'),
        total_cnaps_paye=Sum('cnaps_paye'),
        total_fmfp_paye=Sum('fmfp_paye'),
        total_mutuelle_payee=Sum('mutuelle_sante_paye'),
    )

    compta_entries = _get_diamex_entries_scope_queryset(request).filter(date_m__year=annee)
    if mois:
        compta_entries = compta_entries.filter(date_m__month=mois)
    if organisation_id:
        compta_entries = compta_entries.filter(imported_by__base__organisation_id=organisation_id)
    if base_id:
        compta_entries = compta_entries.filter(imported_by__base_id=base_id)
    if poste_id:
        compta_entries = compta_entries.filter(imported_by__poste_id=poste_id)
    if employe_id:
        compta_entries = compta_entries.filter(imported_by_id=employe_id)

    compta_salaires = Decimal('0')
    compta_charges = Decimal('0')
    compta_indemnites = Decimal('0')
    compta_par_categorie = defaultdict(lambda: Decimal('0'))
    for entry in compta_entries:
        categorie = _group_dashboard_parent_category(entry.get_categorie_parente())
        montant_out = Decimal(str(entry.montant_out or 0))
        if categorie == 'Salaires':
            compta_salaires += montant_out
        elif categorie == 'Charges salariales':
            compta_charges += montant_out
        elif categorie == 'Indemnité':
            compta_indemnites += montant_out
        if categorie in EMPLOYEE_PAYMENT_PARENT_CATEGORIES:
            compta_par_categorie[categorie] += montant_out

    employe_map = {}
    poste_map = {}
    base_map = {}
    mois_map = {}

    for grille in grilles_qs:
        employe = grille.contrat.employe
        organisation = getattr(getattr(employe, 'base', None), 'organisation', None)
        poste = grille.contrat.poste or employe.poste
        base = getattr(employe, 'base', None)
        mois_key = grille.date_salaire.month
        salaires_lies = list(grille.salaires.all())
        salaire = salaires_lies[0] if salaires_lies else None

        brut = Decimal(str(grille.salaire_brut_total or 0))
        net = Decimal(str(grille.salaire_net or 0))
        irsa = Decimal(str(grille.irsa or 0))
        cnaps_emp = Decimal(str(grille.charge_cnaps_employe or 0))
        mutuelle = Decimal(str(grille.mutuelle_sante or 0))
        cout_employeur = brut + (cnaps_emp * Decimal('15')) + mutuelle
        net_paye = Decimal(str(getattr(salaire, 'salaire_net_paye', 0) or 0))

        employe_bucket = employe_map.setdefault(str(employe.id), {
            'employe_id': str(employe.id),
            'nom': employe.surnom or getattr(employe, 'nom_complet', None) or employe.nom_employe,
            'nom_complet': employe.nom_employe,
            'poste': getattr(poste, 'nom_poste', 'Sans poste'),
            'base': getattr(base, 'nom_base', 'Sans base'),
            'organisation': getattr(organisation, 'nom_organisation', 'Sans organisation'),
            'nb_grilles': 0,
            'brut': Decimal('0'),
            'net': Decimal('0'),
            'irsa': Decimal('0'),
            'cnaps_employe': Decimal('0'),
            'mutuelle': Decimal('0'),
            'cout_employeur': Decimal('0'),
            'net_paye': Decimal('0'),
        })
        employe_bucket['nb_grilles'] += 1
        employe_bucket['brut'] += brut
        employe_bucket['net'] += net
        employe_bucket['irsa'] += irsa
        employe_bucket['cnaps_employe'] += cnaps_emp
        employe_bucket['mutuelle'] += mutuelle
        employe_bucket['cout_employeur'] += cout_employeur
        employe_bucket['net_paye'] += net_paye

        poste_key = str(getattr(poste, 'id', 'sans-poste'))
        poste_bucket = poste_map.setdefault(poste_key, {
            'poste': getattr(poste, 'nom_poste', 'Sans poste'),
            'organisation': getattr(getattr(poste, 'organisation', None), 'nom_organisation', getattr(organisation, 'nom_organisation', 'Sans organisation')),
            'effectif': set(),
            'nb_grilles': 0,
            'brut': Decimal('0'),
            'net': Decimal('0'),
            'cout_employeur': Decimal('0'),
        })
        poste_bucket['effectif'].add(str(employe.id))
        poste_bucket['nb_grilles'] += 1
        poste_bucket['brut'] += brut
        poste_bucket['net'] += net
        poste_bucket['cout_employeur'] += cout_employeur

        base_key = str(getattr(base, 'id', 'sans-base'))
        base_bucket = base_map.setdefault(base_key, {
            'base': getattr(base, 'nom_base', 'Sans base'),
            'organisation': getattr(organisation, 'nom_organisation', 'Sans organisation'),
            'effectif': set(),
            'brut': Decimal('0'),
            'net': Decimal('0'),
            'cout_employeur': Decimal('0'),
        })
        base_bucket['effectif'].add(str(employe.id))
        base_bucket['brut'] += brut
        base_bucket['net'] += net
        base_bucket['cout_employeur'] += cout_employeur

        mois_bucket = mois_map.setdefault(mois_key, {
            'mois': mois_key,
            'label': datetime(annee, mois_key, 1).strftime('%B %Y').capitalize(),
            'effectif': set(),
            'brut': Decimal('0'),
            'net': Decimal('0'),
            'cout_employeur': Decimal('0'),
            'net_paye': Decimal('0'),
        })
        mois_bucket['effectif'].add(str(employe.id))
        mois_bucket['brut'] += brut
        mois_bucket['net'] += net
        mois_bucket['cout_employeur'] += cout_employeur
        mois_bucket['net_paye'] += net_paye

    par_employe = []
    for row in employe_map.values():
        row['ecart_paiement'] = row['net'] - row['net_paye']
        par_employe.append(row)
    par_employe.sort(key=lambda item: item['cout_employeur'], reverse=True)

    par_poste = []
    for row in poste_map.values():
        row['effectif'] = len(row['effectif'])
        row['cout_moyen'] = (row['cout_employeur'] / row['effectif']) if row['effectif'] else Decimal('0')
        par_poste.append(row)
    par_poste.sort(key=lambda item: item['cout_employeur'], reverse=True)

    par_base = []
    for row in base_map.values():
        row['effectif'] = len(row['effectif'])
        row['cout_moyen'] = (row['cout_employeur'] / row['effectif']) if row['effectif'] else Decimal('0')
        par_base.append(row)
    par_base.sort(key=lambda item: item['cout_employeur'], reverse=True)

    par_mois = []
    for row in mois_map.values():
        row['effectif'] = len(row['effectif'])
        par_mois.append(row)
    par_mois.sort(key=lambda item: item['mois'])

    annees_disponibles = sorted(set(
        y for y in GrilleSalaire.objects.exclude(date_salaire__isnull=True).values_list('date_salaire__year', flat=True).distinct() if y
    ), reverse=True)

    context = {
        'base_template': 'analyses/base.html' if getattr(request, 'is_analyses_subdomain', False) else 'accounting/base.html',
        'annee': annee,
        'mois': mois,
        'organisation_id': organisation_id,
        'base_id': base_id,
        'poste_id': poste_id,
        'employe_id': employe_id,
        'annees': annees_disponibles,
        'organisations': organisations_qs.order_by('nom_organisation'),
        'bases': bases_qs.order_by('nom_base'),
        'postes': postes_qs.order_by('ordre_affichage', 'nom_poste'),
        'employes': employes_qs.order_by('surnom', 'nom', 'prenom'),
        'indicateurs': {
            'effectif': len(employe_map),
            'nb_grilles': grilles_qs.count(),
            'total_brut': rh_totaux['total_brut'] or Decimal('0'),
            'total_net': rh_totaux['total_net'] or Decimal('0'),
            'total_irsa': rh_totaux['total_irsa'] or Decimal('0'),
            'total_cnaps_employe': rh_totaux['total_cnaps_employe'] or Decimal('0'),
            'total_mutuelle': rh_totaux['total_mutuelle'] or Decimal('0'),
            'total_net_paye': paiements_totaux['total_net_paye'] or Decimal('0'),
        },
        'rapprochement': {
            'compta_salaires': compta_salaires,
            'compta_charges': compta_charges,
            'compta_indemnites': compta_indemnites,
            'compta_paiements_employes': compta_salaires + compta_charges + compta_indemnites,
            'rh_net_paye': paiements_totaux['total_net_paye'] or Decimal('0'),
            'rh_irsa': paiements_totaux['total_irsa_paye'] or Decimal('0'),
            'rh_cnaps': paiements_totaux['total_cnaps_paye'] or Decimal('0'),
            'rh_fmfp': paiements_totaux['total_fmfp_paye'] or Decimal('0'),
            'rh_mutuelle': paiements_totaux['total_mutuelle_payee'] or Decimal('0'),
            'rh_paiements_employes': (
                (paiements_totaux['total_net_paye'] or Decimal('0')) +
                (paiements_totaux['total_irsa_paye'] or Decimal('0')) +
                (paiements_totaux['total_cnaps_paye'] or Decimal('0')) +
                (paiements_totaux['total_fmfp_paye'] or Decimal('0')) +
                (paiements_totaux['total_mutuelle_payee'] or Decimal('0'))
            ),
            'ecart_salaires': compta_salaires - (paiements_totaux['total_net_paye'] or Decimal('0')),
            'ecart_charges': compta_charges - (
                (paiements_totaux['total_irsa_paye'] or Decimal('0')) +
                (paiements_totaux['total_cnaps_paye'] or Decimal('0')) +
                (paiements_totaux['total_fmfp_paye'] or Decimal('0')) +
                (paiements_totaux['total_mutuelle_payee'] or Decimal('0'))
            ),
            'ecart_paiements_employes': (
                (compta_salaires + compta_charges + compta_indemnites) - (
                    (paiements_totaux['total_net_paye'] or Decimal('0')) +
                    (paiements_totaux['total_irsa_paye'] or Decimal('0')) +
                    (paiements_totaux['total_cnaps_paye'] or Decimal('0')) +
                    (paiements_totaux['total_fmfp_paye'] or Decimal('0')) +
                    (paiements_totaux['total_mutuelle_payee'] or Decimal('0'))
                )
            ),
        },
        'compta_categories_employes': [
            {'nom': 'Salaires', 'montant': compta_par_categorie['Salaires']},
            {'nom': 'Charges salariales', 'montant': compta_par_categorie['Charges salariales']},
            {'nom': 'Indemnité', 'montant': compta_par_categorie['Indemnité']},
        ],
        'par_employe': par_employe,
        'par_poste': par_poste,
        'par_base': par_base,
        'par_mois': par_mois,
    }
    return render(request, 'accounting/analyse_categorie_salaires.html', context)


@login_required
def verification_transferts(request):
    """
    Page de vérification des transferts avec diagnostic des problèmes
    Sépare les transferts 00BOOK (pas de problème normalement) et 00FND1 (inter-fichiers)
    """
    from decimal import Decimal
    from collections import defaultdict
    from datetime import timedelta

    # Récupération des filtres
    mois = request.GET.get('mois', '')
    fichier_source = request.GET.get('fichier_source', '')
    prog_code = request.GET.get('prog', '')

    # Base queryset pour tous les transferts
    transferts_00book = BaseDiameX.objects.filter(
        compte_code__startswith='00BOOK'
    ).select_related('journal', 'compte')

    # Libellés qui ne demandent PAS de contrepartie (exclus du matching et des stats) :
    # - EDF
    # - "Report à nouveau" (avec ou sans accent : icontains est sensible aux accents)
    transferts_00fnd1 = BaseDiameX.objects.filter(
        compte_code__startswith='00FND1'
    ).exclude(
        Q(description__icontains='EDF') | Q(info__icontains='EDF') |
        Q(description__icontains='report à nouveau') | Q(info__icontains='report à nouveau') |
        Q(description__icontains='report a nouveau') | Q(info__icontains='report a nouveau')
    ).select_related('journal', 'compte')

    # Tolérance (jours) de la 2e passe de rapprochement, dates décalées (ex. 1 mois et plus)
    try:
        tolerance_jours = max(8, min(int(request.GET.get('tolerance_jours', 90)), 366))
    except (TypeError, ValueError):
        tolerance_jours = 90

    # Appliquer les filtres
    if mois:
        year, month = mois.split('-')
        transferts_00book = transferts_00book.filter(date_m__year=year, date_m__month=month)
        transferts_00fnd1 = transferts_00fnd1.filter(date_m__year=year, date_m__month=month)

    if fichier_source:
        transferts_00book = transferts_00book.filter(fichier_source=fichier_source)
        transferts_00fnd1 = transferts_00fnd1.filter(fichier_source=fichier_source)

    if prog_code:
        transferts_00book = transferts_00book.filter(prog=prog_code)
        transferts_00fnd1 = transferts_00fnd1.filter(prog=prog_code)

    # ========== Statistiques et matching 00BOOK ==========
    stats_00book = transferts_00book.aggregate(
        total_in=Sum('montant_in'),
        total_out=Sum('montant_out'),
        count=Count('id')
    )
    stats_00book['total_in'] = Decimal(str(stats_00book['total_in'] or 0))
    stats_00book['total_out'] = Decimal(str(stats_00book['total_out'] or 0))
    stats_00book['solde'] = stats_00book['total_in'] - stats_00book['total_out']
    stats_00book['solde_abs'] = abs(stats_00book['solde'])  # Valeur absolue pour template
    stats_00book['count'] = stats_00book['count'] or 0

    # Matching des transferts 00BOOK par numéro Rec et montant
    # Grouper par (rec, montant) pour trouver les paires IN/OUT
    book_matches = defaultdict(lambda: {'in': [], 'out': [], 'solde': Decimal('0')})
    book_problemes = []  # Transferts sans paire

    for entry in transferts_00book:
        rec = entry.rec
        montant_in = Decimal(str(entry.montant_in)) if entry.montant_in else Decimal('0')
        montant_out = Decimal(str(entry.montant_out)) if entry.montant_out else Decimal('0')

        # Clé de groupement: (rec, montant_principal)
        # Le montant principal est celui qui est non-nul
        montant_principal = montant_in if montant_in > 0 else montant_out

        if rec and montant_principal > 0:
            key = (rec, montant_principal)
            if montant_in > 0:
                book_matches[key]['in'].append(entry)
            if montant_out > 0:
                book_matches[key]['out'].append(entry)
        else:
            # Pas de Rec ou montant = 0 â†’ problématique
            book_problemes.append({
                'entry': entry,
                'raison': 'Pas de numéro Rec' if not rec else 'Montant = 0'
            })

    # Calculer les soldes par groupe et identifier les problèmes
    book_groupes = []
    for (rec, montant), data in book_matches.items():
        total_in = sum(Decimal(str(e.montant_in)) for e in data['in'])
        total_out = sum(Decimal(str(e.montant_out)) for e in data['out'])
        solde = total_in - total_out

        statut = 'ok' if abs(solde) < Decimal('0.01') else 'probleme'

        book_groupes.append({
            'rec': rec,
            'montant': montant,
            'entries_in': data['in'],
            'entries_out': data['out'],
            'count_in': len(data['in']),
            'count_out': len(data['out']),
            'total_in': total_in,
            'total_out': total_out,
            'solde': solde,
            'solde_abs': abs(solde),
            'statut': statut
        })

    # Trier: problèmes d'abord, puis par montant décroissant
    book_groupes.sort(key=lambda g: (0 if g['statut'] == 'probleme' else 1, -g['montant']))

    stats_00book['count_groupes'] = len(book_groupes)
    stats_00book['count_ok'] = sum(1 for g in book_groupes if g['statut'] == 'ok')
    stats_00book['count_problemes_groupes'] = sum(1 for g in book_groupes if g['statut'] == 'probleme')
    stats_00book['count_problemes_sans_rec'] = len(book_problemes)

    # ========== Statistiques et matching 00FND1 ==========
    # Grouper par fichier_source
    transferts_00fnd1_par_fichier = defaultdict(lambda: {
        'entries': [],
        'total_in': Decimal('0'),
        'total_out': Decimal('0'),
        'solde': Decimal('0'),
        'count': 0
    })

    for entry in transferts_00fnd1:
        fichier = entry.fichier_source
        transferts_00fnd1_par_fichier[fichier]['entries'].append(entry)
        transferts_00fnd1_par_fichier[fichier]['total_in'] += Decimal(str(entry.montant_in))
        transferts_00fnd1_par_fichier[fichier]['total_out'] += Decimal(str(entry.montant_out))
        transferts_00fnd1_par_fichier[fichier]['count'] += 1

    # Calculer les soldes par fichier
    for fichier in transferts_00fnd1_par_fichier:
        data = transferts_00fnd1_par_fichier[fichier]
        data['solde'] = data['total_in'] - data['total_out']

    # ========== Matching des transferts 00FND1 inter-fichiers ==========
    # Pour chaque OUT dans un fichier, chercher un IN correspondant dans un autre fichier
    # Critères: mème montant (ou très proche), dates Â±7 jours, fichiers différents

    # Récupérer tous les transferts 00FND1 pour le matching
    all_transferts_fnd1 = list(transferts_00fnd1)

    # Séparer les IN et OUT
    transferts_in = [t for t in all_transferts_fnd1 if t.montant_in > 0]
    transferts_out = [t for t in all_transferts_fnd1 if t.montant_out > 0]

    # Détecter les transferts sans contrepartie avec matching amélioré
    matched_in_ids = set()
    matched_out_ids = set()
    matches = []  # Liste des paires matchées pour debug

    # Algorithme de matching : matcher les OUT avec les IN les plus proches
    for out_entry in transferts_out:
        montant_out = Decimal(str(out_entry.montant_out))
        date_out = out_entry.date_m

        if not date_out:
            continue  # Ignorer si pas de date

        # Chercher TOUS les IN candidats (mème montant, dates proches)
        candidats = []
        for in_entry in transferts_in:
            if in_entry.id in matched_in_ids:
                continue  # Déjà matché

            montant_in = Decimal(str(in_entry.montant_in))
            date_in = in_entry.date_m

            if not date_in:
                continue  # Ignorer si pas de date

            # Vérifier montant identique (tolérance 0.01)
            if abs(montant_in - montant_out) < Decimal('0.01'):
                delta = abs((date_out - date_in).days)
                if delta <= 7:
                    # Candidat valide - priorité aux fichiers différents
                    same_file = in_entry.fichier_source == out_entry.fichier_source
                    candidats.append({
                        'entry': in_entry,
                        'delta_days': delta,
                        'montant': montant_in,
                        'same_file': same_file
                    })

        # Choisir le meilleur candidat (fichiers différents prioritaires, puis date la plus proche)
        if candidats:
            # Trier par: 1) fichiers différents d'abord (False < True), 2) delta de date
            candidats.sort(key=lambda c: (c['same_file'], c['delta_days']))
            best_match = candidats[0]

            # Marquer comme matché
            matched_in_ids.add(best_match['entry'].id)
            matched_out_ids.add(out_entry.id)

            matches.append({
                'out': out_entry,
                'in': best_match['entry'],
                'montant': montant_out,
                'delta_days': best_match['delta_days'],
                'approx': False,
            })

    # 2e passe : OUT / IN restants de même montant, fichiers DIFFÉRENTS, dates plus éloignées
    # (un transfert saisi dans un fichier un mois ou plus après l'autre).
    # On génère toutes les paires possibles, puis on attribue les plus proches en premier
    # pour limiter les faux rapprochements quand un même montant revient souvent.
    ins_restants = defaultdict(list)
    for in_entry in transferts_in:
        if in_entry.id not in matched_in_ids and in_entry.date_m:
            ins_restants[Decimal(str(in_entry.montant_in)).quantize(Decimal('0.01'))].append(in_entry)

    paires_approx = []
    for out_entry in transferts_out:
        if out_entry.id in matched_out_ids or not out_entry.date_m:
            continue
        cle = Decimal(str(out_entry.montant_out)).quantize(Decimal('0.01'))
        for in_entry in ins_restants.get(cle, []):
            if in_entry.fichier_source == out_entry.fichier_source:
                continue
            delta = abs((out_entry.date_m - in_entry.date_m).days)
            if delta <= tolerance_jours:
                paires_approx.append((delta, out_entry, in_entry, cle))

    paires_approx.sort(key=lambda p: p[0])
    for delta, out_entry, in_entry, cle in paires_approx:
        if out_entry.id in matched_out_ids or in_entry.id in matched_in_ids:
            continue
        matched_out_ids.add(out_entry.id)
        matched_in_ids.add(in_entry.id)
        matches.append({
            'out': out_entry,
            'in': in_entry,
            'montant': cle,
            'delta_days': delta,
            'approx': True,
        })

    matches_approx = [m for m in matches if m['approx']]
    matches_approx.sort(key=lambda m: -m['delta_days'])

    # Lister les transferts problématiques (non matchés)
    problemes = []

    for out_entry in transferts_out:
        if out_entry.id not in matched_out_ids:
            problemes.append({
                'type': 'OUT sans contrepartie',
                'entry': out_entry,
                'montant': Decimal(str(out_entry.montant_out)),
                'fichier': out_entry.fichier_source,
                'date': out_entry.date_rec if out_entry.date_rec else out_entry.date_m,
                'description': out_entry.description,
                'id': out_entry.id,
                'id_access': out_entry.id_access,
                'journal': out_entry.journal_code,
                'rec': out_entry.rec,
                'prog': out_entry.prog
            })

    for in_entry in transferts_in:
        if in_entry.id not in matched_in_ids:
            problemes.append({
                'type': 'IN sans contrepartie',
                'entry': in_entry,
                'montant': Decimal(str(in_entry.montant_in)),
                'fichier': in_entry.fichier_source,
                'date': in_entry.date_rec if in_entry.date_rec else in_entry.date_m,
                'description': in_entry.description,
                'id': in_entry.id,
                'id_access': in_entry.id_access,
                'journal': in_entry.journal_code,
                'rec': in_entry.rec,
                'prog': in_entry.prog
            })

    # Statistiques globales 00FND1
    stats_00fnd1 = {
        'total_in': sum(d['total_in'] for d in transferts_00fnd1_par_fichier.values()),
        'total_out': sum(d['total_out'] for d in transferts_00fnd1_par_fichier.values()),
        'count': sum(d['count'] for d in transferts_00fnd1_par_fichier.values()),
        'count_matched': len(matched_in_ids) + len(matched_out_ids),
        'count_problemes': len(problemes)
    }
    stats_00fnd1['solde'] = stats_00fnd1['total_in'] - stats_00fnd1['total_out']
    stats_00fnd1['solde_abs'] = abs(stats_00fnd1['solde'])  # Valeur absolue pour template

    # Listes pour les filtres
    fichiers_sources = sorted(set(BaseDiameX.objects.values_list('fichier_source', flat=True).distinct()))
    progs = sorted(set(BaseDiameX.objects.filter(prog__isnull=False).values_list('prog', flat=True).distinct()))

    # Pagination pour 00BOOK groupes
    from django.core.paginator import Paginator
    page_book = request.GET.get('page_book', 1)
    filtre_book = request.GET.get('filtre_book', 'tous')  # tous, problemes, ok

    # Filtrer les groupes selon le choix
    if filtre_book == 'problemes':
        book_groupes_filtres = [g for g in book_groupes if g['statut'] == 'probleme']
    elif filtre_book == 'ok':
        book_groupes_filtres = [g for g in book_groupes if g['statut'] == 'ok']
    else:
        book_groupes_filtres = book_groupes

    paginator_book = Paginator(book_groupes_filtres, 20)  # 20 groupes par page
    page_obj_book = paginator_book.get_page(page_book)

    # Pagination pour 00FND1 problèmes
    page_fnd1 = request.GET.get('page_fnd1', 1)
    paginator_fnd1 = Paginator(problemes, 50)  # 50 par page
    page_obj_fnd1 = paginator_fnd1.get_page(page_fnd1)

    return render(request, 'accounting/verification_transferts.html', {
        'stats_00book': stats_00book,
        'page_obj_book': page_obj_book,
        'book_problemes': book_problemes,  # Transferts sans Rec
        'stats_00fnd1': stats_00fnd1,
        'transferts_00fnd1_par_fichier': dict(transferts_00fnd1_par_fichier),
        'page_obj_fnd1': page_obj_fnd1,
        'matches': matches,  # Paires matchées pour debug
        'matches_approx': matches_approx,  # Paires à dates décalées (à contrôler)
        'tolerance_jours': tolerance_jours,
        'fichiers_sources': fichiers_sources,
        'progs': progs,
    })


@login_required
@require_http_methods(["POST"])
def api_update_solde_reel(request):
    """API pour mettre à jour un solde réel (Django + Access)"""
    import json
    from .models import SoldesReels

    try:
        data = json.loads(request.body)
        solde_id = data.get('solde_id')
        nouveau_ccy = data.get('ccy')
        description = data.get('description', '')
        scan = data.get('scan', '')

        if not solde_id:
            return JsonResponse({'success': False, 'error': 'ID solde manquant'}, status=400)

        # Mise à jour Django
        solde = SoldesReels.objects.get(id=solde_id)
        if not request.user.is_superuser:
            org_id = getattr(
                getattr(getattr(request.user, 'employe', None), 'base', None),
                'organisation_id',
                None
            )
            allowed = False
            if org_id and solde.imported_by and solde.imported_by.base_id:
                allowed = (solde.imported_by.base.organisation_id == org_id)
            if not allowed:
                allowed_fichiers = set(
                    _get_diamex_entries_scope_queryset(request)
                    .exclude(fichier_source__isnull=True)
                    .exclude(fichier_source='')
                    .values_list('fichier_source', flat=True)
                    .distinct()
                )
                allowed = solde.fichier_source in allowed_fichiers
            if not allowed:
                return JsonResponse({'success': False, 'error': 'Acces refuse'}, status=403)

        if nouveau_ccy is not None:
            solde.ccy = nouveau_ccy
        solde.description = description
        solde.scan = scan
        solde.save()

        # Mise à jour Access
        access_success = False
        access_error = None
        try:
            from apps.employees.models import EmployeBaseDiameX
            employe = request.user.employe if hasattr(request.user, 'employe') else None
            if employe:
                base_diamex = EmployeBaseDiameX.objects.filter(
                    employe=employe,
                    base_diamex=solde.fichier_source
                ).first()

                if base_diamex and os.path.exists(base_diamex.chemin_complet):
                    conn_str = r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};' + f'DBQ={base_diamex.chemin_complet};'
                    conn = pyodbc.connect(conn_str)
                    cursor = conn.cursor()

                    update_sql = """
                        UPDATE SoldesReels
                        SET CCY = ?, Description = ?, Scan = ?
                        WHERE Journal = ? AND DateM = ? AND Rec = ?
                    """
                    cursor.execute(update_sql, (
                        float(solde.ccy),
                        solde.description,
                        solde.scan,
                        solde.journal,
                        solde.date_m,
                        solde.rec
                    ))
                    conn.commit()
                    cursor.close()
                    conn.close()
                    access_success = True
        except Exception as e:
            access_error = str(e)

        return JsonResponse({
            'success': True,
            'django_updated': True,
            'access_updated': access_success,
            'access_error': access_error,
            'message': 'Solde réel mis à jour avec succès' if access_success else 'Solde mis à jour dans Django, mais échec Access'
        })
    except SoldesReels.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Solde réel introuvable'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["GET"])
@login_required
def api_verifier_scans(request):
    """
    API avec streaming pour la vérification des scans.
    Utilise Server-Sent Events (SSE) pour envoyer la progression en temps réel.
    """
    from django.http import StreamingHttpResponse
    from .models import ScanVerificationCache
    from apps.employees.models import EmployeBaseDiameX
    import json
    import time

    def generate_progress():
        try:
            # Récupérer le filtre fichier_source si fourni
            fichier_filter = request.GET.get('fichier_source')

            # Envoyer message de démarrage
            yield f"data: {json.dumps({'type': 'start', 'message': 'Démarrage de la vérification...'})}\n\n"
            time.sleep(0.1)

            # Créer une nouvelle entrée de cache
            cache = ScanVerificationCache.objects.create(
                fichier_source=fichier_filter if fichier_filter else None,
                statut='en_cours'
            )

            yield f"data: {json.dumps({'type': 'progress', 'message': 'Construction du dictionnaire des chemins...', 'percent': 5})}\n\n"
            time.sleep(0.1)

            # Construire le dictionnaire des chemins de base
            bases_dict = {}
            for base in EmployeBaseDiameX.objects.all():
                if base.base_diamex:
                    bases_dict[base.base_diamex] = base.chemin_base_diamex or ''

            # Récupérer toutes les entrées
            entries = BaseDiameX.objects.all()

            # Appliquer le filtre fichier_source si fourni
            if fichier_filter:
                entries = entries.filter(fichier_source=fichier_filter)

            # Exclure 00BOOK et 00PERS qui n'ont pas besoin de scan
            entries_necessitant_scan = entries.exclude(
                Q(compte_code__icontains='00BOOK') | Q(compte_code__icontains='00PERS')
            )

            yield f"data: {json.dumps({'type': 'progress', 'message': 'Comptage des opérations sans scan...', 'percent': 10})}\n\n"
            time.sleep(0.1)

            # Compter les opérations sans scan
            operations_sans_scan = entries_necessitant_scan.filter(
                Q(scan__isnull=True) | Q(scan='')
            ).filter(
                Q(montant_in__gt=0) | Q(montant_out__gt=0)
            ).count()

            # Vérifier les scans existants
            scans_valides_ids = []
            liens_morts_ids = []

            entries_avec_scan = entries_necessitant_scan.filter(
                scan__isnull=False
            ).exclude(scan='')

            total_to_check = entries_avec_scan.count()
            yield f"data: {json.dumps({'type': 'progress', 'message': f'Vérification de {total_to_check} scans...', 'percent': 15})}\n\n"

            # Vérifier chaque scan avec progression
            from .scan_resolution import copie_serveur_existe
            for idx, entry in enumerate(entries_avec_scan, 1):
                if copie_serveur_existe(entry):
                    # La copie sur le VPS prime : si elle existe, le scan est valide (le chemin local ne compte plus)
                    scans_valides_ids.append(entry.id)
                elif entry.fichier_source:
                    chemin_base = bases_dict.get(entry.fichier_source, '')
                    if chemin_base:
                        # [OK] Nettoyer les caractères # au début et à la fin
                        scan_relatif = entry.scan.strip('#')
                        if scan_relatif.startswith('.'):
                            scan_relatif = scan_relatif[1:]
                        # Si scan contient déjà le chemin absolu, ne pas concaténer
                        if scan_relatif.startswith(chemin_base):
                            full_path = scan_relatif
                        else:
                            full_path = chemin_base + scan_relatif

                        # Vérifier si le fichier existe
                        if os.path.exists(full_path):
                            scans_valides_ids.append(entry.id)
                        else:
                            liens_morts_ids.append(entry.id)

                # Envoyer progression tous les 100 éléments
                if idx % 100 == 0 or idx == total_to_check:
                    percent = 15 + int((idx / total_to_check) * 70)  # De 15% à 85%
                    yield f"data: {json.dumps({'type': 'progress', 'message': f'Vérifié {idx}/{total_to_check} scans...', 'percent': percent, 'scans_valides': len(scans_valides_ids), 'liens_morts': len(liens_morts_ids)})}\n\n"

            yield f"data: {json.dumps({'type': 'progress', 'message': 'Calcul des totaux...', 'percent': 90})}\n\n"
            time.sleep(0.1)

            # Total des opérations nécessitant un scan
            operations_total = entries_necessitant_scan.filter(
                Q(montant_in__gt=0) | Q(montant_out__gt=0)
            ).count()

            yield f"data: {json.dumps({'type': 'progress', 'message': 'Sauvegarde des résultats...', 'percent': 95})}\n\n"
            time.sleep(0.1)

            # Mettre à jour le cache avec les résultats
            cache.scans_valides_count = len(scans_valides_ids)
            cache.liens_morts_count = len(liens_morts_ids)
            cache.operations_sans_scan_count = operations_sans_scan
            cache.operations_total_count = operations_total
            cache.scans_valides_ids = scans_valides_ids
            cache.liens_morts_ids = liens_morts_ids
            cache.statut = 'termine'
            cache.save()

            # Envoyer message de fin
            yield f"data: {json.dumps({'type': 'complete', 'message': 'Vérification terminée !', 'percent': 100, 'stats': {'scans_valides': len(scans_valides_ids), 'liens_morts': len(liens_morts_ids), 'sans_scan': operations_sans_scan, 'total': operations_total}})}\n\n"

        except Exception as e:
            # Marquer le cache comme erreur si créé
            if 'cache' in locals():
                cache.statut = 'erreur'
                cache.message_erreur = str(e)
                cache.save()

            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    response = StreamingHttpResponse(generate_progress(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


def _build_coupure_periods_by_point(point_eau_ids):
    """
    Construit les périodes de coupure par point d'eau à partir de CoupureEau.
    Intervalle de coupure: [date_coupure, date_remise).
    """
    from collections import defaultdict
    from datetime import datetime as dt_datetime
    from apps.billing.models import CoupureEau, PointEau

    point_eau_ids = [str(pid) for pid in point_eau_ids if pid]
    if not point_eau_ids:
        return {}

    evenements = CoupureEau.objects.filter(
        point_eau_id__in=point_eau_ids
    ).order_by('point_eau_id', 'date_evenement', 'created_at').values(
        'point_eau_id',
        'type_evenement',
        'date_evenement'
    )

    periodes = defaultdict(list)
    coupure_ouverte = {}

    for evt in evenements:
        pe_id = str(evt.get('point_eau_id'))
        type_evt = evt.get('type_evenement')
        date_evt = evt.get('date_evenement')

        if not pe_id or not date_evt:
            continue

        if type_evt == 'coupure':
            # Dernière coupure fait foi jusqu'à remise.
            coupure_ouverte[pe_id] = date_evt
        elif type_evt == 'remise':
            debut = coupure_ouverte.get(pe_id)
            if debut:
                periodes[pe_id].append((debut, date_evt))
                coupure_ouverte.pop(pe_id, None)

    # Coupure encore active: pas de borne de fin
    for pe_id, debut in coupure_ouverte.items():
        periodes[pe_id].append((debut, None))

    # Harmoniser avec l'etat courant du point d'eau (source de verite):
    # - si datearretbranchement est renseigne, l'intervalle ouvert doit commencer a cette date
    # - si datearretbranchement est vide, aucune coupure ouverte ne doit rester active
    for point in PointEau.objects.filter(id__in=point_eau_ids).values('id', 'datearretbranchement'):
        pe_id = str(point.get('id'))
        date_arret = point.get('datearretbranchement')

        closed_periods = [(debut, fin) for debut, fin in periodes.get(pe_id, []) if fin is not None]

        if isinstance(date_arret, dt_datetime):
            date_arret = date_arret.date()

        if date_arret:
            closed_periods = [(debut, fin) for debut, fin in closed_periods if debut < date_arret]
            closed_periods.append((date_arret, None))

        periodes[pe_id] = closed_periods

    return periodes


def _is_releve_during_coupure(releve, periodes_par_point, check_facturation_month=False):
    """
    True si le relevé doit être exclu à cause d'une coupure.
    - Mode standard: la date du relevé tombe dans une période de coupure.
    - Mode facturation: une période de coupure chevauche le mois facturé (mois+1 du relevé).
    """
    from datetime import date, datetime as dt_datetime

    if not releve or not releve.point_eau or not releve.datereleve:
        return False

    pe_id = str(releve.point_eau.id)

    if check_facturation_month:
        # Mois facturé = mois suivant le relevé.
        date_rel = releve.datereleve
        if date_rel.month == 12:
            mois_facturation_debut = date(date_rel.year + 1, 1, 1)
            mois_facturation_fin = date(date_rel.year + 1, 2, 1)
        else:
            mois_facturation_debut = date(date_rel.year, date_rel.month + 1, 1)
            if date_rel.month == 11:
                mois_facturation_fin = date(date_rel.year + 1, 1, 1)
            else:
                mois_facturation_fin = date(date_rel.year, date_rel.month + 2, 1)

        # Garde-fou métier: si le point est marqué coupé avant la fin du mois facturé,
        # la facture du mois ne doit pas être comptée en "prévu", même sans événements complets.
        date_arret = getattr(releve.point_eau, 'datearretbranchement', None)
        if isinstance(date_arret, dt_datetime):
            date_arret = date_arret.date()
        if date_arret and date_arret < mois_facturation_fin:
            return True

        for debut, fin in periodes_par_point.get(pe_id, []):
            # Chevauchement d'intervalles: [debut, fin) avec [mois_facturation_debut, mois_facturation_fin)
            if debut < mois_facturation_fin and (fin is None or fin > mois_facturation_debut):
                return True
        return False

    date_rel = releve.datereleve
    for debut, fin in periodes_par_point.get(pe_id, []):
        if date_rel >= debut and (fin is None or date_rel < fin):
            return True
    return False


def _is_releve_pointe(releve):
    """Un relevé est pointé lorsque le couple numéro/base DiameX est complet."""
    numero_diamex = str(getattr(releve, 'numeroDiameX', '') or '').strip()
    base_diamex = str(getattr(releve, 'baseDiameX', '') or '').strip()
    return bool(numero_diamex and base_diamex)


def _is_releve_non_recouvrable(releve, periodes_par_point=None):
    """
    Toutes les factures d'un point d'eau actuellement coupé restent visibles
    et pointables, mais sortent du prévu tant que leur pointage DiameX n'est
    pas complet. La date de la facture n'intervient pas dans cette règle.
    """
    point_eau = getattr(releve, 'point_eau', None)
    est_actuellement_coupe = bool(
        point_eau and getattr(point_eau, 'datearretbranchement', None)
    )
    return bool(est_actuellement_coupe and not _is_releve_pointe(releve))



@login_required
@require_http_methods(["GET"])
def api_details_recoupement_3e(request):
    """
    API pour récupérer les détails d'un recoupement 3e (DiameX + Relevés)
    pour un ouvrage et une période donnés.

    Paramètres GET:
        - ouvrage_id: UUID de l'ouvrage
        - annee: Année (ex: 2025)
        - mois: Mois (ex: 1 pour janvier)

    Retourne:
        JSON avec:
        - transactions_diamex: Liste des transactions DiameX 707401
        - releves: Liste des relevés
        - stats: Statistiques (totaux, écarts)
    """
    try:
        from apps.billing.models import Releve, PointEau
        from apps.organization.models import Ouvrage
        from apps.employees.models import EmployeBaseDiameX
        from .extracteurs_description import extraire_ouvrage_et_mois_generique
        organisation_ids = _get_user_scope_organisation_ids(request.user)
        diamex_scope_qs = _get_diamex_scope_by_prog(request.user)

        # Récupérer les paramètres
        ouvrage_id = request.GET.get('ouvrage_id')
        annee = request.GET.get('annee')
        mois = request.GET.get('mois')

        if not all([ouvrage_id, annee, mois]):
            return JsonResponse({
                'success': False,
                'error': 'Paramètres manquants (ouvrage_id, annee, mois requis)'
            }, status=400)

        try:
            annee = int(annee)
            mois = int(mois)
        except ValueError:
            return JsonResponse({
                'success': False,
                'error': 'Année et mois doivent ètre des entiers'
            }, status=400)

        allowed_ouvrage_ids = _get_responsable_scoped_ouvrage_ids(request.user)
        if ouvrage_id not in _normalize_id_set(allowed_ouvrage_ids):
            return JsonResponse({
                'success': False,
                'error': 'Acces refuse a cet ouvrage'
            }, status=403)

        # Vérifier que l'ouvrage existe
        try:
            ouvrage = Ouvrage.objects.get(id=ouvrage_id)
        except Ouvrage.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Ouvrage non trouvé'
            }, status=404)

        # 1. Récupérer les relevés de cet ouvrage pour cette période
        # CRITICAL: La date de facturation = mois SUIVANT le relevé
        # Ex: Relevé décembre 2024 â†’ Facturé janvier 2025
        # Donc pour les factures de janvier 2025, on cherche les relevés de décembre 2024
        from datetime import datetime
        from dateutil.relativedelta import relativedelta

        # Calculer le mois précédent (mois de relevé)
        date_facturation = datetime(annee, mois, 1)
        date_releve = date_facturation - relativedelta(months=1)

        releves = Releve.objects.filter(
            montant__isnull=False,
            montant__gt=0,
            point_eau__ouvrage_id=ouvrage_id,
            point_eau__ouvrage_id__in=allowed_ouvrage_ids,
            datereleve__year=date_releve.year,
            datereleve__month=date_releve.month
        ).exclude(
            remarque__icontains='coupé'  # Exclure les relevés avec "coupé" dans la remarque
        ).select_related('point_eau', 'point_eau__type_point_eau')

        # Conserver les relevés de points coupés dans le modal afin qu'ils
        # restent pointables. Seuls les totaux « à collecter » les excluent.
        releves = list(releves)
        point_eau_ids = {str(r.point_eau.id) for r in releves if r.point_eau}
        periodes_coupure = _build_coupure_periods_by_point(point_eau_ids)

        releves_data = []
        total_releves = Decimal('0')
        total_non_recouvrable = Decimal('0')
        nb_non_recouvrables = 0

        for releve in releves:
            non_recouvrable = _is_releve_non_recouvrable(releve, periodes_coupure)
            idxls_str = releve.point_eau.idxls if releve.point_eau and releve.point_eau.idxls else '-'
            numero_diamex = (releve.numeroDiameX or '').strip()
            base_diamex = (releve.baseDiameX or '').strip()
            # Regle metier du modal:
            # un releve n'est plus pointable des que le numero DiameX existe,
            # meme si la base est vide ou incoherente.
            already_pointed = bool(numero_diamex)

            # Récupérer nom abonné et type de point d'eau
            nom_abonne = '-'
            type_point_eau = ''
            if releve.point_eau:
                nom_abonne = releve.point_eau.nomabonne or '-'
                if releve.point_eau.type_point_eau:
                    type_point_eau = releve.point_eau.type_point_eau.nom_type

            releves_data.append({
                'id': str(releve.id),
                'point_eau_id': str(releve.point_eau.id) if releve.point_eau else '',
                'idxls': idxls_str,
                'idxls_num': int(idxls_str) if idxls_str.isdigit() else 999999,  # Pour tri numérique
                'nom_abonne': nom_abonne,
                'type_point_eau': type_point_eau,
                'datereleve': releve.datereleve.strftime('%d/%m/%Y') if releve.datereleve else '-',
                'index_ancien': float(releve.ancienindex) if releve.ancienindex else 0,
                'nouvelindex': float(releve.nouvelindex) if releve.nouvelindex else 0,
                'consommation': float(releve.consommation) if releve.consommation else 0,
                'montant': float(releve.montant) if releve.montant else 0,
                'numeroDiameX': numero_diamex,
                'baseDiameX': base_diamex,
                'already_pointed': already_pointed,
                'est_coupe': bool(releve.point_eau and releve.point_eau.datearretbranchement),
                'non_recouvrable': non_recouvrable,
            })
            montant_releve = Decimal(str(releve.montant)) if releve.montant else Decimal('0')
            if non_recouvrable:
                total_non_recouvrable += montant_releve
                nb_non_recouvrables += 1
            else:
                total_releves += montant_releve

        # Trier les relevés par IDXLS numérique
        releves_data.sort(key=lambda x: x['idxls_num'])

        def _as_clean_str(value):
            if value is None:
                return ''
            return str(value).strip()

        pointed_couples = set()
        for rel in releves_data:
            numero_diamex = _as_clean_str(rel.get('numeroDiameX'))
            base_diamex = _as_clean_str(rel.get('baseDiameX'))
            if numero_diamex and base_diamex:
                pointed_couples.add((numero_diamex, base_diamex))

        # 2. Récupérer les transactions DiameX 707401 pour cette période
        # Important: ne pas filtrer par date_rec (date de paiement).
        # Le rattachement annuel se fait via la date de facture extraite du libellé.
        diamex_707401 = diamex_scope_qs.filter(
            compte_code='707401'
        )

        transactions_data = []
        total_diamex = Decimal('0')

        for entry in diamex_707401:
            # Vérifier si cette transaction concerne cet ouvrage
            # Détecter les paiements multi-segments
            segments = []
            if entry.description and ';' in entry.description:
                segments = diviser_paiement_volume_multi(
                    entry.description,
                    entry.compte_code,
                    entry.montant_in if entry.montant_in else 0
                )

            # Si segments, vérifier si au moins un segment concerne cet ouvrage
            concerne_ouvrage = False
            montant_attribue = Decimal('0')

            if segments:
                for segment in segments:
                    extraction = segment['extraction']
                    if extraction['ouvrage_obj'] and extraction['ouvrage_obj'].id == ouvrage.id:
                        if extraction['mois'] == mois and extraction['annee'] == annee:
                            concerne_ouvrage = True
                            montant_attribue += Decimal(str(segment['montant']))
            else:
                # Traitement normal
                extraction = extraire_ouvrage_et_mois_generique(entry.description or '', entry.compte_code)
                if extraction['ouvrage_obj'] and extraction['ouvrage_obj'].id == ouvrage.id:
                    if extraction['mois'] == mois and extraction['annee'] == annee:
                        concerne_ouvrage = True
                        montant_attribue = Decimal(str(entry.montant_in)) if entry.montant_in else Decimal('0')

            if concerne_ouvrage:
                numero_diamex = str(entry.id_access).strip() if entry.id_access is not None else ''
                base_diamex = (entry.prog or '').strip()
                already_pointed = bool(numero_diamex and base_diamex and (numero_diamex, base_diamex) in pointed_couples)

                # Récupérer le chemin_base pour le scan
                scan_path = ''
                if entry.scan:
                    # Essayer de trouver l'EmployeBaseDiameX avec une correspondance partielle
                    # prog format: "EHA-Soakoja-Tana" ou "EHA-Soakoja-Fenerive Est"
                    # base_diamex format: "DiameX v3.16.1 - 3 - Soakoja Tana 20251014 RAF.accde"
                    employe_base = None
                    if entry.prog:
                        # Extraire la partie significative du prog (ex: "Tana" ou "Fenerive Est")
                        prog_parts = entry.prog.split('-')
                        if len(prog_parts) >= 2:
                            search_term = prog_parts[-1].strip()  # "Tana" ou "Fenerive Est"

                            # Si le search_term contient "Fenerive", essayer avec accent
                            if 'Fenerive' in search_term:
                                # Essayer avec "Fénérive" (accent)
                                employe_base_qs = EmployeBaseDiameX.objects.filter(
                                    base_diamex__icontains='Fénérive'
                                )
                                if organisation_ids is not None:
                                    if organisation_ids:
                                        employe_base_qs = employe_base_qs.filter(
                                            employe__base__organisation_id__in=organisation_ids
                                        )
                                    else:
                                        employe_base_qs = employe_base_qs.none()
                                employe_base = employe_base_qs.first()

                            # Si pas trouvé, essayer avec le terme d'origine
                            if not employe_base:
                                # Extraire juste le premier mot pour "Fenerive Est" -> "Fenerive"
                                first_word = search_term.split()[0] if ' ' in search_term else search_term
                                employe_base_qs = EmployeBaseDiameX.objects.filter(
                                    base_diamex__icontains=first_word
                                )
                                if organisation_ids is not None:
                                    if organisation_ids:
                                        employe_base_qs = employe_base_qs.filter(
                                            employe__base__organisation_id__in=organisation_ids
                                        )
                                    else:
                                        employe_base_qs = employe_base_qs.none()
                                employe_base = employe_base_qs.first()

                    if employe_base:
                        chemin_base = employe_base.chemin_base_diamex or ''
                        scan_clean = entry.scan
                        if scan_clean.startswith('./') or scan_clean.startswith('.\\'):
                            scan_clean = scan_clean[2:]
                        elif scan_clean.startswith('.'):
                            scan_clean = scan_clean[1:]

                        if not chemin_base.endswith(os.sep):
                            scan_path = chemin_base + os.sep + scan_clean
                        else:
                            scan_path = chemin_base + scan_clean

                transactions_data.append({
                    'id': entry.id,
                    'entry_id': entry.id,
                    'id_access': numero_diamex,
                    'date_rec': entry.date_rec.strftime('%d/%m/%Y') if entry.date_rec else '-',
                    'description': entry.description or '',
                    'montant_in': float(montant_attribue),
                    'prog': entry.prog or '',
                    'scan': entry.scan or '',
                    'scan_path': scan_path,
                    'is_segment': bool(segments),
                    'rec': entry.rec or '',
                    'already_pointed': already_pointed
                })
                total_diamex += montant_attribue

        # 2.bis Totaux globaux par couple commun numero/prog, sans filtre ouvrage/mois
        # (utile pour voir l'historique global de chaque couple).
        def _pair_key(num, base):
            return f"{_as_clean_str(num).lower()}||{_as_clean_str(base).lower()}"

        diamex_couples = set()
        for tx in transactions_data:
            num = _as_clean_str(tx.get('id_access'))
            base = _as_clean_str(tx.get('prog'))
            if num and base:
                diamex_couples.add((num, base))

        common_couples = pointed_couples.intersection(diamex_couples)
        matching_couples_stats = []

        if common_couples:
            q_releves = Q()
            q_diamex = Q()
            for numero_diamex, base_diamex in common_couples:
                q_releves |= Q(numeroDiameX=numero_diamex, baseDiameX=base_diamex)
                q_diamex |= Q(id_access=numero_diamex, prog=base_diamex)

            releves_global_rows = Releve.objects.filter(
                q_releves,
                montant__isnull=False
            ).values('numeroDiameX', 'baseDiameX').annotate(total=Sum('montant'))

            diamex_global_entries = BaseDiameX.objects.filter(
                q_diamex,
                compte_code='707401',
                montant_in__isnull=False
            )

            releves_global_details = Releve.objects.filter(
                q_releves,
                montant__isnull=False
            ).select_related('point_eau')

            releves_totals = {
                _pair_key(row['numeroDiameX'], row['baseDiameX']): Decimal(str(row['total'] or 0))
                for row in releves_global_rows
            }

            releves_pointes_par_couple = {}
            for releve in releves_global_details:
                key = _pair_key(releve.numeroDiameX, releve.baseDiameX)
                date_facture_releve = (
                    releve.datereleve + relativedelta(months=1)
                    if releve.datereleve
                    else None
                )
                releves_pointes_par_couple.setdefault(key, set()).add((
                    str(getattr(releve.point_eau, 'ouvrage_id', '') or ''),
                    date_facture_releve.year if date_facture_releve else None,
                    date_facture_releve.month if date_facture_releve else None,
                ))

            diamex_totals = {}
            for entry in diamex_global_entries:
                key = _pair_key(entry.id_access, entry.prog)
                diamex_totals.setdefault(key, Decimal('0'))

                segments = []
                if entry.description and ';' in entry.description:
                    segments = diviser_paiement_volume_multi(
                        entry.description,
                        entry.compte_code,
                        entry.montant_in if entry.montant_in else 0
                    )

                if segments:
                    couple_releves = releves_pointes_par_couple.get(key, set())
                    for segment in segments:
                        extraction = segment.get('extraction') or {}
                        ouvrage_obj = extraction.get('ouvrage_obj')
                        segment_signature = (
                            str(getattr(ouvrage_obj, 'id', '') or ''),
                            extraction.get('annee'),
                            extraction.get('mois'),
                        )
                        if (
                            ouvrage_obj
                            and extraction.get('annee')
                            and extraction.get('mois')
                            and segment_signature in couple_releves
                        ):
                            diamex_totals[key] += Decimal(str(segment.get('montant') or 0))
                else:
                    diamex_totals[key] += Decimal(str(entry.montant_in or 0))

            for numero_diamex, base_diamex in sorted(common_couples, key=lambda x: (x[0], x[1])):
                key = _pair_key(numero_diamex, base_diamex)
                total_releve_global = releves_totals.get(key, Decimal('0'))
                total_diamex_global = diamex_totals.get(key, Decimal('0'))
                ecart_global = total_releve_global - total_diamex_global
                matching_couples_stats.append({
                    'numero_diamex': numero_diamex,
                    'base_diamex': base_diamex,
                    'pair_key': key,
                    'total_releves_global': float(total_releve_global),
                    'total_diamex_global': float(total_diamex_global),
                    'ecart_global': float(ecart_global),
                })

        # 3. Calculer les statistiques
        ecart = total_releves - total_diamex

        if abs(ecart) < Decimal('0.01'):
            status = 'ok'
        elif abs(ecart) < Decimal('100'):
            status = 'warning'
        else:
            status = 'error'

        auto_pointage_data = build_auto_pointage_suggestions(releves_data, transactions_data)

        return JsonResponse({
            'success': True,
            'ouvrage': {
                'id': str(ouvrage.id),
                'nom': ouvrage.nom_ouvrage
            },
            'periode': {
                'mois': mois,
                'annee': annee,
                'label': f"{mois:02d}/{annee}"
            },
            'releves': releves_data,
            'transactions_diamex': transactions_data,
            'matching_couples_stats': matching_couples_stats,
            'auto_pointage': auto_pointage_data,
            'stats': {
                'nb_releves': len(releves_data) - nb_non_recouvrables,
                'nb_releves_visibles': len(releves_data),
                'nb_non_recouvrables': nb_non_recouvrables,
                'total_non_recouvrable': float(total_non_recouvrable),
                'nb_transactions_diamex': len(transactions_data),
                'total_releves': float(total_releves),
                'total_diamex': float(total_diamex),
                'ecart': float(ecart),
                'status': status
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def api_save_remarque_recouvrement_volume(request):
    try:
        from apps.organization.models import Ouvrage

        data = json.loads(request.body or '{}')
        ouvrage_id = str(data.get('ouvrage_id') or '').strip()
        remarque = str(data.get('remarque') or '').strip()

        try:
            annee = int(data.get('annee'))
            mois = int(data.get('mois'))
        except (TypeError, ValueError):
            return JsonResponse({
                'success': False,
                'error': 'Annee et mois invalides'
            }, status=400)

        if not ouvrage_id:
            return JsonResponse({
                'success': False,
                'error': 'Ouvrage manquant'
            }, status=400)

        if mois < 1 or mois > 12:
            return JsonResponse({
                'success': False,
                'error': 'Mois invalide'
            }, status=400)

        allowed_ouvrage_ids = _get_responsable_scoped_ouvrage_ids(request.user)
        if ouvrage_id not in _normalize_id_set(allowed_ouvrage_ids):
            return JsonResponse({
                'success': False,
                'error': 'Acces refuse a cet ouvrage'
            }, status=403)

        try:
            ouvrage = Ouvrage.objects.get(id=ouvrage_id)
        except Ouvrage.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Ouvrage non trouve'
            }, status=404)

        employe = getattr(request.user, 'employe', None)
        obj, created = RemarqueRecouvrementVolume.objects.get_or_create(
            ouvrage=ouvrage,
            annee=annee,
            mois=mois,
            defaults={
                'remarque': remarque,
                'created_by': employe,
                'updated_by': employe,
            }
        )

        if not created:
            obj.remarque = remarque
            obj.updated_by = employe
            if obj.created_by_id is None and employe is not None:
                obj.created_by = employe
            obj.save(update_fields=['remarque', 'updated_by', 'created_by', 'updated_at'])

        return JsonResponse({
            'success': True,
            'remarque': obj.remarque or '',
            'message': 'Remarque enregistree'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def dashboard_paiements_volume(request):
    """
    Dashboard complet pour les paiements au volume avec:
    - Stats de recouvrement par ouvrage et par période
    - Analyse des délais de paiement
    - Graphiques et tableaux interactifs
    """
    from django.db.models import Sum, Count, Q
    from decimal import Decimal
    from datetime import datetime
    import re
    import pytz
    from .extracteurs_description import extraire_ouvrage_et_mois_paiement_volume
    from apps.billing.models import Releve
    from .models import BaseDiameX
    from apps.organization.models import Ouvrage
    from apps.geography.models import District, Commune, Region
    from .dashboard_employee_filter import (
        calculate_water_point_score,
        get_water_point_score_gap_ids,
        is_closed_payment_month,
        resolve_dashboard_employee_filter,
        resolve_score_scope,
    )

    # Timezone Madagascar
    tz_madagascar = pytz.timezone('Indian/Antananarivo')

    # Filtres
    filter_annee = request.GET.get('annee', str(datetime.now().year))
    filter_trimestre = request.GET.get('trimestre', 'all')
    filter_semestre = request.GET.get('semestre', '').strip().upper()
    filter_organisation = request.GET.get('organisation', '')
    filter_region = request.GET.get('region', '')
    filter_district = request.GET.get('district', '')
    filter_commune = request.GET.get('commune', '')
    filter_ouvrage = request.GET.get('ouvrage', '')
    filter_employe = request.GET.get('employe', '')
    filter_type_pe = request.GET.get('type_pe', '')
    filter_type_abonne = request.GET.get('type_abonne', '').strip().lower()
    if filter_type_abonne not in {'particulier', 'boutique'}:
        filter_type_abonne = ''
    # Un filtre par type de point d'eau / d'abonné rend le « payé » DiameX inutilisable
    # (écritures rattachées à l'ouvrage, pas au point d'eau) : on bascule sur les pointés.
    type_filter_actif = bool(filter_type_abonne or (filter_type_pe and filter_type_pe != 'all'))
    filter_non_pointe = request.GET.get('non_pointe', '')
    filter_non_pointe_periode = request.GET.get('non_pointe_periode', '').strip().lower()
    if filter_non_pointe_periode not in {'passes', 'courant'}:
        filter_non_pointe_periode = ''
    score_ecart_filter = str(request.GET.get('score_ecart', '') or '').strip().lower()
    show_only_score_gap = score_ecart_filter in {'1', 'true', 'on', 'yes'}

    try:
        annee = int(filter_annee)
    except:
        annee = datetime.now().year

    trimestre_to_months = {
        'all': list(range(1, 13)),
        'T1': [1, 2, 3],
        'T2': [1, 2, 3, 4, 5, 6],
        'T3': [1, 2, 3, 4, 5, 6, 7, 8, 9],
        'T4': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    }
    semestre_to_months = {
        'S1': [1, 2, 3, 4, 5, 6],
        'S2': [7, 8, 9, 10, 11, 12],
    }
    if filter_semestre in semestre_to_months:
        selected_months = semestre_to_months[filter_semestre]
    else:
        filter_semestre = ''
        selected_months = trimestre_to_months.get(filter_trimestre, trimestre_to_months['all'])
    selected_months_set = set(selected_months)

    def _resolve_billing_period(releve_date):
        if not releve_date:
            return None, None
        if releve_date.month == 12:
            return releve_date.year + 1, 1
        return releve_date.year, releve_date.month + 1

    # Scope gestionnaire de l'utilisateur connecté + filtre organisation optionnel
    scope_info = _resolve_effective_gestionnaire_scope(request.user, filter_organisation)
    organisation_user = scope_info['organisation_user']
    accessible_gestionnaire_ids = scope_info['accessible_gestionnaire_ids']
    effective_gestionnaire_ids = scope_info['effective_gestionnaire_ids']
    filter_organisation = scope_info['selected_organisation_id']
    has_gestionnaire_scope = effective_gestionnaire_ids is None or bool(effective_gestionnaire_ids)
    organisations = _get_gestionnaire_organisations_for_filter(accessible_gestionnaire_ids)

    # 1. Récupérer les relevés avec montant pour l'année sélectionnée
    releves_qs = Releve.objects.filter(
        montant__isnull=False,
        montant__gt=0,
        point_eau__ouvrage__isnull=False
    ).filter(
        Q(datereleve__year__gte=2025) |
        Q(datereleve__year=2024, datereleve__month=12)
    ).exclude(
        remarque__icontains='coupé'
    ).select_related(
        'point_eau',
        'point_eau__type_point_eau',
        'point_eau__ouvrage',
        'point_eau__ouvrage__type_ouvrage',
        'point_eau__parcelle',
        'point_eau__parcelle__village',
        'point_eau__parcelle__village__fokontany',
        'point_eau__parcelle__village__fokontany__commune',
        'point_eau__parcelle__village__fokontany__commune__district'
    )

    # Filtrer par année (datereleve est un DateField, pas besoin de conversion timezone)
    if annee:
        releves_filtered = []
        for releve in releves_qs:
            if not releve.datereleve:
                continue
            if releve.datereleve.year == annee:
                releves_filtered.append(releve)
                continue
            # Inclure décembre de l'année précédente (reporté sur janvier)
            if releve.datereleve.year == (annee - 1) and releve.datereleve.month == 12:
                releves_filtered.append(releve)
        releves_qs = releves_filtered

    # Filtrer par trimestre sur le mois de facturation cible du dashboard.
    releves_qs = [
        releve for releve in releves_qs
        if _resolve_billing_period(releve.datereleve)[0] == annee
        and _resolve_billing_period(releve.datereleve)[1] in selected_months_set
    ]

    # Filtrer automatiquement par scope organisation (via ModaliteGestion)
    ouvrages_org = _get_responsable_scoped_ouvrage_ids(
        request.user,
        effective_gestionnaire_ids=effective_gestionnaire_ids,
    )
    employes_responsables, ouvrages_org = resolve_dashboard_employee_filter(
        ouvrages_org,
        filter_employe,
    )
    if filter_employe and not any(
        str(option.get('id', '')) == str(filter_employe)
        for option in employes_responsables
    ):
        filter_employe = ''
    employe_ids_par_ouvrage = {}
    for employe_option in employes_responsables:
        for employe_ouvrage_id in employe_option.get('ouvrage_ids', []):
            employe_ids_par_ouvrage.setdefault(str(employe_ouvrage_id), set()).add(
                str(employe_option['id'])
            )
    ouvrages_org_ids_str = _normalize_id_set(ouvrages_org)
    releves_qs = [
        r for r in releves_qs
        if r.point_eau and r.point_eau.ouvrage and str(r.point_eau.ouvrage.id) in ouvrages_org_ids_str
    ]

    # Filtrer par district
    if filter_district and filter_district != 'all':
        releves_qs = [r for r in releves_qs if r.point_eau and r.point_eau.parcelle and
                      r.point_eau.parcelle.village and r.point_eau.parcelle.village.fokontany and
                      r.point_eau.parcelle.village.fokontany.commune and
                      r.point_eau.parcelle.village.fokontany.commune.district and
                      str(r.point_eau.parcelle.village.fokontany.commune.district.id) == filter_district]

    # Filtrer par region
    if filter_region and filter_region != 'all':
        releves_qs = [r for r in releves_qs if r.point_eau and r.point_eau.parcelle and
                      r.point_eau.parcelle.village and r.point_eau.parcelle.village.fokontany and
                      r.point_eau.parcelle.village.fokontany.commune and
                      r.point_eau.parcelle.village.fokontany.commune.district and
                      r.point_eau.parcelle.village.fokontany.commune.district.region and
                      str(r.point_eau.parcelle.village.fokontany.commune.district.region.id) == filter_region]

    # Filtrer par commune
    if filter_commune and filter_commune != 'all':
        releves_qs = [r for r in releves_qs if r.point_eau and r.point_eau.parcelle and
                      r.point_eau.parcelle.village and r.point_eau.parcelle.village.fokontany and
                      r.point_eau.parcelle.village.fokontany.commune and
                      str(r.point_eau.parcelle.village.fokontany.commune.id) == filter_commune]

    # Filtrer par ouvrage
    if filter_ouvrage and filter_ouvrage != 'all':
        releves_qs = [r for r in releves_qs if r.point_eau and r.point_eau.ouvrage and
                      str(r.point_eau.ouvrage.id) == filter_ouvrage]

    from apps.billing.models import TypePointEau

    # Filtrer par type de point d'eau
    if filter_type_pe and filter_type_pe != 'all':
        releves_qs = [r for r in releves_qs if r.point_eau and r.point_eau.type_point_eau_id
                      and str(r.point_eau.type_point_eau_id) == filter_type_pe]

    # Filtrer par type d'abonné (particulier / boutique)
    if filter_type_abonne:
        releves_qs = [r for r in releves_qs if r.point_eau
                      and (r.point_eau.typeabonne or '').strip().lower() == filter_type_abonne]

    # Identifier les factures temporairement hors recouvrement sans les retirer
    # de la vue : elles doivent rester accessibles au pointage.
    point_eau_ids = {str(r.point_eau.id) for r in releves_qs if r.point_eau}
    periodes_coupure = _build_coupure_periods_by_point(point_eau_ids)

    ouvrage_ids_stats = set()
    point_eau_ids_stats = set()
    points_eau_par_type = {}
    for releve in releves_qs:
        point_eau = getattr(releve, 'point_eau', None)
        if not point_eau:
            continue

        if point_eau.ouvrage_id:
            ouvrage_ids_stats.add(str(point_eau.ouvrage_id))

        point_eau_id = str(point_eau.id)
        if point_eau_id in point_eau_ids_stats:
            continue

        point_eau_ids_stats.add(point_eau_id)
        type_obj = getattr(point_eau, 'type_point_eau', None)
        type_label = getattr(type_obj, 'nom_type', None) or 'Sans type'
        points_eau_par_type[type_label] = points_eau_par_type.get(type_label, 0) + 1

    total_points_eau_stats = len(point_eau_ids_stats)
    points_eau_par_type_list = [
        {
            'type_nom': type_nom,
            'count': count,
            'pct_points_eau': int((count / total_points_eau_stats) * 100) if total_points_eau_stats > 0 else 0,
        }
        for type_nom, count in sorted(points_eau_par_type.items(), key=lambda item: (-item[1], item[0].lower()))
    ]
    # 2. Grouper par ouvrage et par mois - CALCUL DES RELEVéS
    recouvrement_par_ouvrage_mois = {}
    recouvrement_par_ouvrage_annee = {}
    encaisse_details_volume = []  # lignes pour les modales des tuiles Encaissé / Écart
    pointed_pairs_par_cle_mois = {}
    pointage_points_eau_par_ouvrage = {}
    pointage_points_eau_par_ouvrage_mois = {}

    def _pair_key(numero_diamex, base_diamex):
        num = str(numero_diamex or '').strip().lower()
        base = str(base_diamex or '').strip().lower()
        if not num or not base:
            return ''
        return f"{num}||{base}"

    for releve in releves_qs:
        if not releve.point_eau or not releve.point_eau.ouvrage:
            continue

        ouvrage = releve.point_eau.ouvrage
        ouvrage_id = str(ouvrage.id)
        ouvrage_nom = ouvrage.nom_ouvrage

        # Récupérer le district via la chaîne de relations
        district_nom = None
        if releve.point_eau.parcelle and releve.point_eau.parcelle.village:
            village = releve.point_eau.parcelle.village
            if village.fokontany and village.fokontany.commune and village.fokontany.commune.district:
                district_nom = village.fokontany.commune.district.nom_district

        annee_cible, mois_cible = _resolve_billing_period(releve.datereleve)
        if annee_cible != annee or mois_cible not in selected_months_set:
            continue

        mois = mois_cible

        # Clé pour groupement par mois
        cle_mois = f"{ouvrage_id}_{annee}_{mois:02d}"
        if cle_mois not in recouvrement_par_ouvrage_mois:
            recouvrement_par_ouvrage_mois[cle_mois] = {
                'ouvrage_id': ouvrage_id,
                'ouvrage_nom': ouvrage_nom,
                'annee': annee,
                'mois': mois,
                'total_releves': Decimal('0'),
                'total_diamex': Decimal('0'),
                'nb_releves': 0,
                'montant_non_pointe_releve': Decimal('0'),
                'montant_non_pointe_compta': Decimal('0'),
                'nb_non_pointe_releve': 0,
                'nb_non_pointe_compta': 0,
                'montant_non_recouvrable': Decimal('0'),
                'nb_non_recouvrable': 0,
            }
        if cle_mois not in pointed_pairs_par_cle_mois:
            pointed_pairs_par_cle_mois[cle_mois] = set()

        point_eau_id = str(releve.point_eau.id)
        if ouvrage_id not in pointage_points_eau_par_ouvrage:
            pointage_points_eau_par_ouvrage[ouvrage_id] = {}
        if point_eau_id not in pointage_points_eau_par_ouvrage[ouvrage_id]:
            pointage_points_eau_par_ouvrage[ouvrage_id][point_eau_id] = {
                'nb_factures': 0,
                'nb_factures_pointees': 0,
            }
        if ouvrage_id not in pointage_points_eau_par_ouvrage_mois:
            pointage_points_eau_par_ouvrage_mois[ouvrage_id] = {}
        if mois not in pointage_points_eau_par_ouvrage_mois[ouvrage_id]:
            pointage_points_eau_par_ouvrage_mois[ouvrage_id][mois] = {}
        if point_eau_id not in pointage_points_eau_par_ouvrage_mois[ouvrage_id][mois]:
            pointage_points_eau_par_ouvrage_mois[ouvrage_id][mois][point_eau_id] = {
                'nb_factures': 0,
                'nb_factures_pointees': 0,
            }

        montant = Decimal(str(releve.montant)) if releve.montant else Decimal('0')
        non_recouvrable = _is_releve_non_recouvrable(releve, periodes_coupure)

        if non_recouvrable:
            recouvrement_par_ouvrage_mois[cle_mois]['montant_non_recouvrable'] += montant
            recouvrement_par_ouvrage_mois[cle_mois]['nb_non_recouvrable'] += 1
        else:
            recouvrement_par_ouvrage_mois[cle_mois]['total_releves'] += montant
            recouvrement_par_ouvrage_mois[cle_mois]['nb_releves'] += 1
            pointage_points_eau_par_ouvrage[ouvrage_id][point_eau_id]['nb_factures'] += 1
            pointage_points_eau_par_ouvrage_mois[ouvrage_id][mois][point_eau_id]['nb_factures'] += 1

        # Relevé pointé si et seulement si numeroDiameX ET baseDiameX sont renseignés
        pair_key = _pair_key(releve.numeroDiameX, releve.baseDiameX)
        if pair_key:
            pointed_pairs_par_cle_mois[cle_mois].add(pair_key)
            if not non_recouvrable:
                pointage_points_eau_par_ouvrage[ouvrage_id][point_eau_id]['nb_factures_pointees'] += 1
                pointage_points_eau_par_ouvrage_mois[ouvrage_id][mois][point_eau_id]['nb_factures_pointees'] += 1
        elif not non_recouvrable:
            recouvrement_par_ouvrage_mois[cle_mois]['montant_non_pointe_compta'] += montant
            recouvrement_par_ouvrage_mois[cle_mois]['nb_non_pointe_compta'] += 1

        # Filtre par type : le payé = relevés pointés (cf. type_filter_actif)
        paye_pointe = montant if (type_filter_actif and pair_key and not non_recouvrable) else Decimal('0')
        recouvrement_par_ouvrage_mois[cle_mois]['total_diamex'] += paye_pointe

        # Clé pour groupement annuel
        if ouvrage_id not in recouvrement_par_ouvrage_annee:
            recouvrement_par_ouvrage_annee[ouvrage_id] = {
                'ouvrage_id': ouvrage_id,
                'ouvrage_nom': ouvrage_nom,
                'district_nom': district_nom or 'Sans district',
                'annee': annee,
                'total_releves': Decimal('0'),
                'total_diamex': Decimal('0'),
                'nb_releves': 0,
                'montant_non_pointe_releve': Decimal('0'),
                'nb_non_pointe_releve': 0,
                'montant_non_recouvrable': Decimal('0'),
                'nb_non_recouvrable': 0,
            }

        if non_recouvrable:
            recouvrement_par_ouvrage_annee[ouvrage_id]['montant_non_recouvrable'] += montant
            recouvrement_par_ouvrage_annee[ouvrage_id]['nb_non_recouvrable'] += 1
        else:
            recouvrement_par_ouvrage_annee[ouvrage_id]['total_releves'] += montant
            recouvrement_par_ouvrage_annee[ouvrage_id]['nb_releves'] += 1
            recouvrement_par_ouvrage_annee[ouvrage_id]['total_diamex'] += paye_pointe

            # Suivi rapide : facture encaissée par la caissière (datepaiement posée par le
            # workflow d'encaissement) ou déjà pointée. Calculé sur les relevés, donc sans
            # double comptage avec les écritures DiameX de la compta.
            if releve.datepaiement or pair_key:
                encaisse_details_volume.append({
                    'mois': mois,
                    'ouvrage': ouvrage_nom,
                    'point_eau': releve.point_eau.nomabonne or releve.point_eau.code_point_eau or '-',
                    'idxls': str(getattr(releve.point_eau, 'idxls', '') or ''),
                    'reference': f"{mois:02d}/{annee}",
                    'montant': float(montant),
                    'date_encaissement': releve.datepaiement.strftime('%d/%m/%Y') if releve.datepaiement else '',
                    'pointe': bool(pair_key),
                    'numero': str(releve.numeroDiameX or ''),
                })
                for cible in (recouvrement_par_ouvrage_mois[cle_mois], recouvrement_par_ouvrage_annee[ouvrage_id]):
                    cible['montant_encaisse'] = cible.get('montant_encaisse', Decimal('0')) + montant
                    cible['nb_encaisse'] = cible.get('nb_encaisse', 0) + 1
                    if not pair_key:
                        cible['montant_encaisse_non_pointe'] = cible.get('montant_encaisse_non_pointe', Decimal('0')) + montant
                        cible['nb_encaisse_non_pointe'] = cible.get('nb_encaisse_non_pointe', 0) + 1

    # Donnees detaillees destinees a l'onglet Excel "Taux mensuels".
    # Une ligne represente un point d'eau pour un mois de facturation. Le
    # montant paye est rattache au point d'eau lorsque le releve est pointe
    # (numeroDiameX et baseDiameX tous les deux renseignes).
    taux_mensuels_points_export_map = {}
    for releve in releves_qs:
        point_eau = getattr(releve, 'point_eau', None)
        ouvrage = getattr(point_eau, 'ouvrage', None) if point_eau else None
        if not point_eau or not ouvrage:
            continue

        annee_cible, mois_cible = _resolve_billing_period(releve.datereleve)
        if annee_cible != annee or mois_cible not in selected_months_set:
            continue

        parcelle = getattr(point_eau, 'parcelle', None)
        village = getattr(parcelle, 'village', None) if parcelle else None
        fokontany = getattr(village, 'fokontany', None) if village else None
        commune = getattr(fokontany, 'commune', None) if fokontany else None
        district = getattr(commune, 'district', None) if commune else None
        type_point_eau = getattr(point_eau, 'type_point_eau', None)

        export_key = (str(ouvrage.id), str(point_eau.id), mois_cible)
        export_row = taux_mensuels_points_export_map.setdefault(export_key, {
            'district': getattr(district, 'nom_district', None) or 'Sans district',
            'ouvrage': ouvrage.nom_ouvrage or '',
            'code_point_eau': (
                point_eau.code_point_eau
                or point_eau.idxls
                or str(point_eau.id)
            ),
            'point_eau': point_eau.nomabonne or '',
            'type_point_eau': getattr(type_point_eau, 'nom_type', None) or 'Sans type',
            'mois': mois_cible,
            'volume_consomme': Decimal('0'),
            'prevu': Decimal('0'),
            'paye': Decimal('0'),
            'non_recouvrable': Decimal('0'),
        })
        montant_releve = Decimal(str(releve.montant or 0))
        export_row['volume_consomme'] += Decimal(str(releve.consommation or 0))
        if _is_releve_non_recouvrable(releve, periodes_coupure):
            export_row['non_recouvrable'] += montant_releve
        else:
            export_row['prevu'] += montant_releve
            if _pair_key(releve.numeroDiameX, releve.baseDiameX):
                export_row['paye'] += montant_releve

    taux_mensuels_points_export = []
    for export_row in sorted(
        taux_mensuels_points_export_map.values(),
        key=lambda item: (
            item['district'].casefold(),
            item['ouvrage'].casefold(),
            item['point_eau'].casefold(),
            item['mois'],
        ),
    ):
        taux_mensuels_points_export.append({
            **export_row,
            'code_point_eau': str(export_row['code_point_eau']),
            'volume_consomme': float(export_row['volume_consomme']),
            'prevu': float(export_row['prevu']),
            'paye': float(export_row['paye']),
            'non_recouvrable': float(export_row['non_recouvrable']),
        })

    employee_points_score = {'visible': False}
    score_reference_month = timezone.localdate().replace(day=1)
    employee_score_point_ids = set()
    payment_totals_by_point = defaultdict(
        lambda: {'expected': Decimal('0'), 'paid': Decimal('0')}
    )
    for releve in releves_qs:
        point_eau = getattr(releve, 'point_eau', None)
        if not point_eau or _is_releve_non_recouvrable(releve, periodes_coupure):
            continue
        billing_year, billing_month = _resolve_billing_period(releve.datereleve)
        if not billing_year or not billing_month:
            continue
        if not is_closed_payment_month(
            datetime(billing_year, billing_month, 1).date(),
            score_reference_month,
        ):
            continue
        point_eau_id = str(point_eau.id)
        employee_score_point_ids.add(point_eau_id)
        montant_releve = Decimal(str(releve.montant or 0))
        payment_totals_by_point[point_eau_id]['expected'] += montant_releve
        if _pair_key(releve.numeroDiameX, releve.baseDiameX):
            payment_totals_by_point[point_eau_id]['paid'] += montant_releve

    employee_points_score = calculate_water_point_score(
        employee_score_point_ids,
        payment_totals_by_point,
    )
    score_gap_point_ids = get_water_point_score_gap_ids(
        employee_score_point_ids,
        payment_totals_by_point,
    )
    score_gap_ouvrage_ids = {
        str(releve.point_eau.ouvrage_id)
        for releve in releves_qs
        if releve.point_eau
        and releve.point_eau.ouvrage_id
        and str(releve.point_eau.id) in score_gap_point_ids
    }
    employee_points_score.update({
        'visible': True,
        **resolve_score_scope(
            employee_options=employes_responsables,
            employee_id=filter_employe,
            ouvrage_id=filter_ouvrage,
            commune_id=filter_commune,
            district_id=filter_district,
            region_id=filter_region,
            organisation_id=filter_organisation,
            default_organisation_name=getattr(organisation_user, 'nom_organisation', '') or '',
        ),
    })

    # 3. NOUVEAU : Calculer les paiements depuis DiameX (compte 707401)
    # Récupérer toutes les transactions DiameX pour l'année
    ouvrages_filtres_ids = {
        str(r.point_eau.ouvrage.id)
        for r in releves_qs
        if r.point_eau and r.point_eau.ouvrage
    }

    # Important: ne pas filtrer par date_rec (date de paiement).
    # Le rattachement annuel se fait via la date de facture extraite du libellé.
    # NOTE METIER: ceci est volontairement DIFFERENT du calcul des taxes communales,
    # qui, lui, est basé sur la date de paiement (date_rec).
    diamex_707401 = BaseDiameX.objects.filter(
        compte_code='707401'
    )
    if type_filter_actif:
        diamex_707401 = diamex_707401.none()

    # Pour chaque transaction, extraire l'ouvrage et le mois, puis attribuer le montant
    for entry in diamex_707401:
        # Détecter les paiements multi-segments
        segments = []
        if entry.description and ';' in entry.description:
            segments = diviser_paiement_volume_multi(
                entry.description,
                entry.compte_code,
                entry.montant_in if entry.montant_in else 0
            )

        if segments:
            # Traitement multi-segments
            for segment in segments:
                extraction = segment['extraction']
                if extraction['ouvrage_obj'] and extraction['mois'] and extraction['annee'] == annee and extraction['mois'] in selected_months_set:
                    ouvrage_id = str(extraction['ouvrage_obj'].id)
                    if ouvrage_id not in ouvrages_filtres_ids:
                        continue
                    mois = extraction['mois']
                    montant_segment = Decimal(str(segment['montant']))

                    # Clé mensuelle
                    cle_mois = f"{ouvrage_id}_{annee}_{mois:02d}"
                    if cle_mois not in recouvrement_par_ouvrage_mois:
                        # Créer une ligne "paiement sans relevé" pour signaler l'anomalie
                        recouvrement_par_ouvrage_mois[cle_mois] = {
                            'ouvrage_id': ouvrage_id,
                            'ouvrage_nom': extraction['ouvrage_obj'].nom_ouvrage,
                            'annee': annee,
                            'mois': mois,
                            'total_releves': Decimal('0'),
                            'total_diamex': Decimal('0'),
                            'nb_releves': 0,
                            'montant_non_pointe_releve': Decimal('0'),
                            'montant_non_pointe_compta': Decimal('0'),
                            'nb_non_pointe_releve': 0,
                            'nb_non_pointe_compta': 0,
                        }
                    if cle_mois not in pointed_pairs_par_cle_mois:
                        pointed_pairs_par_cle_mois[cle_mois] = set()
                    recouvrement_par_ouvrage_mois[cle_mois]['total_diamex'] += montant_segment
                    diamex_pair_key = _pair_key(entry.id_access, entry.prog)
                    is_diamex_pointe = bool(
                        diamex_pair_key and diamex_pair_key in pointed_pairs_par_cle_mois.get(cle_mois, set())
                    )
                    if not is_diamex_pointe:
                        recouvrement_par_ouvrage_mois[cle_mois]['montant_non_pointe_releve'] += montant_segment
                        recouvrement_par_ouvrage_mois[cle_mois]['nb_non_pointe_releve'] += 1

                    # Clé annuelle
                    if ouvrage_id not in recouvrement_par_ouvrage_annee:
                        recouvrement_par_ouvrage_annee[ouvrage_id] = {
                            'ouvrage_id': ouvrage_id,
                            'ouvrage_nom': extraction['ouvrage_obj'].nom_ouvrage,
                            'district_nom': 'Sans district',
                            'annee': annee,
                            'total_releves': Decimal('0'),
                            'total_diamex': Decimal('0'),
                            'nb_releves': 0,
                            'montant_non_pointe_releve': Decimal('0'),
                            'nb_non_pointe_releve': 0,
                        }
                    recouvrement_par_ouvrage_annee[ouvrage_id]['total_diamex'] += montant_segment
                    if not is_diamex_pointe:
                        recouvrement_par_ouvrage_annee[ouvrage_id]['montant_non_pointe_releve'] += montant_segment
                        recouvrement_par_ouvrage_annee[ouvrage_id]['nb_non_pointe_releve'] += 1
        else:
            # Traitement normal (transaction unique)
            extraction = extraire_ouvrage_et_mois_generique(entry.description or '', entry.compte_code)
            if extraction['ouvrage_obj'] and extraction['mois'] and extraction['annee'] == annee and extraction['mois'] in selected_months_set:
                ouvrage_id = str(extraction['ouvrage_obj'].id)
                if ouvrage_id not in ouvrages_filtres_ids:
                    continue
                mois = extraction['mois']
                montant_entry = Decimal(str(entry.montant_in)) if entry.montant_in else Decimal('0')

                # Clé mensuelle
                cle_mois = f"{ouvrage_id}_{annee}_{mois:02d}"
                if cle_mois not in recouvrement_par_ouvrage_mois:
                    recouvrement_par_ouvrage_mois[cle_mois] = {
                        'ouvrage_id': ouvrage_id,
                        'ouvrage_nom': extraction['ouvrage_obj'].nom_ouvrage,
                        'annee': annee,
                        'mois': mois,
                        'total_releves': Decimal('0'),
                        'total_diamex': Decimal('0'),
                        'nb_releves': 0,
                        'montant_non_pointe_releve': Decimal('0'),
                        'montant_non_pointe_compta': Decimal('0'),
                        'nb_non_pointe_releve': 0,
                        'nb_non_pointe_compta': 0,
                    }
                if cle_mois not in pointed_pairs_par_cle_mois:
                    pointed_pairs_par_cle_mois[cle_mois] = set()
                recouvrement_par_ouvrage_mois[cle_mois]['total_diamex'] += montant_entry
                diamex_pair_key = _pair_key(entry.id_access, entry.prog)
                is_diamex_pointe = bool(
                    diamex_pair_key and diamex_pair_key in pointed_pairs_par_cle_mois.get(cle_mois, set())
                )
                if not is_diamex_pointe:
                    recouvrement_par_ouvrage_mois[cle_mois]['montant_non_pointe_releve'] += montant_entry
                    recouvrement_par_ouvrage_mois[cle_mois]['nb_non_pointe_releve'] += 1

                # Clé annuelle
                if ouvrage_id not in recouvrement_par_ouvrage_annee:
                    recouvrement_par_ouvrage_annee[ouvrage_id] = {
                        'ouvrage_id': ouvrage_id,
                        'ouvrage_nom': extraction['ouvrage_obj'].nom_ouvrage,
                        'district_nom': 'Sans district',
                        'annee': annee,
                        'total_releves': Decimal('0'),
                        'total_diamex': Decimal('0'),
                        'nb_releves': 0,
                        'montant_non_pointe_releve': Decimal('0'),
                        'nb_non_pointe_releve': 0,
                    }
                recouvrement_par_ouvrage_annee[ouvrage_id]['total_diamex'] += montant_entry
                if not is_diamex_pointe:
                    recouvrement_par_ouvrage_annee[ouvrage_id]['montant_non_pointe_releve'] += montant_entry
                    recouvrement_par_ouvrage_annee[ouvrage_id]['nb_non_pointe_releve'] += 1

    # Identifier les transactions DiameX non affectées pour signaler les libellés/date à corriger
    anomalies_diamex = []
    # Transactions dont l'extraction a totalement échoué (ouvrage introuvable et/ou
    # date/mois absent(e) du libellé) : ces lignes ne sont JAMAIS comptées nulle part
    # dans les totaux, contrairement aux anomalies ci-dessus qui sont extraites mais
    # simplement hors du périmètre affiché. Il faut les signaler explicitement pour
    # que l'utilisateur corrige le libellé DiameX ou l'orthographe de l'ouvrage.
    transactions_non_appariees = []

    def _diagnostiquer_echec_extraction(extraction):
        if not extraction['ouvrage_obj'] and not (extraction['mois'] and extraction['annee']):
            return "Ouvrage introuvable et date/mois absent(e) du libellé"
        if not extraction['ouvrage_obj']:
            return "Ouvrage introuvable (vérifier l'orthographe dans le libellé)"
        return "Date/mois absent(e) ou invalide dans le libellé"

    for entry in diamex_707401:
        matched = False
        in_scope = False
        extraction_echouee = False
        raison_echec = ''
        # Multi-segments
        segments = []
        if entry.description and ';' in entry.description:
            segments = diviser_paiement_volume_multi(
                entry.description,
                entry.compte_code,
                entry.montant_in if entry.montant_in else 0
            )
        if segments:
            for segment in segments:
                extraction = segment['extraction']
                if extraction['ouvrage_obj'] and extraction['mois'] and extraction['annee']:
                    if extraction['annee'] != annee or extraction['mois'] not in selected_months_set:
                        continue
                    if str(extraction['ouvrage_obj'].id) not in ouvrages_filtres_ids:
                        continue
                    in_scope = True
                    cle = f"{extraction['ouvrage_obj'].id}_{extraction['annee']}_{extraction['mois']:02d}"
                    if cle in recouvrement_par_ouvrage_mois:
                        matched = True
                        break
                else:
                    extraction_echouee = True
                    raison_echec = _diagnostiquer_echec_extraction(extraction)
        else:
            extraction = extraire_ouvrage_et_mois_generique(entry.description or '', entry.compte_code)
            if extraction['ouvrage_obj'] and extraction['mois'] and extraction['annee']:
                if extraction['annee'] != annee or extraction['mois'] not in selected_months_set:
                    continue
                if str(extraction['ouvrage_obj'].id) not in ouvrages_filtres_ids:
                    continue
                in_scope = True
                cle = f"{extraction['ouvrage_obj'].id}_{extraction['annee']}_{extraction['mois']:02d}"
                if cle in recouvrement_par_ouvrage_mois:
                    matched = True
            else:
                extraction_echouee = True
                raison_echec = _diagnostiquer_echec_extraction(extraction)

        if extraction_echouee and not matched:
            transactions_non_appariees.append({
                'id_access': entry.id_access,
                'prog': entry.prog or '',
                'date_rec': entry.date_rec,
                'montant': float(entry.montant_in or 0),
                'description': entry.description or '',
                'raison': raison_echec,
            })
            continue

        # Ignorer les transactions en dehors du périmètre de la vue courante.
        if not in_scope:
            continue

        if not matched:
            anomalies_diamex.append({
                'date_rec': entry.date_rec,
                'montant': float(entry.montant_in or 0),
                'description': entry.description or '',
                'raison': 'Aucune correspondance mois/ouvrage (libellé ou date à corriger)'
            })

    transactions_non_appariees.sort(key=lambda item: item['date_rec'] or datetime.min.date(), reverse=True)
    montant_total_non_appariees = sum(
        (Decimal(str(item['montant'])) for item in transactions_non_appariees),
        Decimal('0')
    )

    # Indicateurs complémentaires par ouvrage (affichage compact à côté du nom)
    # - nb_releves_dernier_mois: nombre de relevés du dernier mois facturé de l'année filtrée
    # - moyenne_montant_total_facture: moyenne mensuelle des montants facturés (mois avec facture > 0)
    # - montant_moyen_par_releve: moyenne annuelle par relevé
    indicateurs_par_ouvrage = {}
    for data_mois in recouvrement_par_ouvrage_mois.values():
        ouvrage_id = data_mois.get('ouvrage_id')
        if not ouvrage_id:
            continue

        total_releves_mois = Decimal(str(data_mois.get('total_releves') or 0))
        mois = data_mois.get('mois')
        nb_releves_mois = int(data_mois.get('nb_releves') or 0)

        if ouvrage_id not in indicateurs_par_ouvrage:
            indicateurs_par_ouvrage[ouvrage_id] = {
                'mois_factures': set(),
                'somme_montants_mensuels': Decimal('0'),
                'dernier_mois_releve': None,
                'nb_releves_dernier_mois': 0,
            }

        indic = indicateurs_par_ouvrage[ouvrage_id]

        if total_releves_mois > 0:
            indic['mois_factures'].add(mois)
            indic['somme_montants_mensuels'] += total_releves_mois

        if nb_releves_mois > 0 and (indic['dernier_mois_releve'] is None or mois > indic['dernier_mois_releve']):
            indic['dernier_mois_releve'] = mois
            indic['nb_releves_dernier_mois'] = nb_releves_mois

    # Calculer l'écart et le taux pour chaque ouvrage (Total Relevés - Total DiameX)
    for ouvrage_id, data in recouvrement_par_ouvrage_annee.items():
        indic = indicateurs_par_ouvrage.get(ouvrage_id, {})
        nb_mois_factures = len(indic.get('mois_factures', set()))
        somme_montants_mensuels = Decimal(str(indic.get('somme_montants_mensuels') or 0))
        nb_releves_total = int(data.get('nb_releves') or 0)

        data['dernier_mois_releve'] = indic.get('dernier_mois_releve')
        data['nb_releves_dernier_mois'] = int(indic.get('nb_releves_dernier_mois') or 0)
        data['moyenne_montant_total_facture'] = (
            somme_montants_mensuels / Decimal(nb_mois_factures)
            if nb_mois_factures > 0 else Decimal('0')
        )
        data['montant_moyen_par_releve'] = (
            data['total_releves'] / Decimal(nb_releves_total)
            if nb_releves_total > 0 else Decimal('0')
        )

        point_eau_stats = pointage_points_eau_par_ouvrage.get(ouvrage_id, {})
        nb_points_eau_affiches = sum(
            1 for pe_data in point_eau_stats.values()
            if pe_data.get('nb_factures', 0) > 0
        )
        nb_points_eau_integralement_pointes = sum(
            1
            for pe_data in point_eau_stats.values()
            if pe_data.get('nb_factures', 0) > 0
            and pe_data.get('nb_factures') == pe_data.get('nb_factures_pointees')
        )
        taux_points_eau_integralement_pointes = int(
            (Decimal(nb_points_eau_integralement_pointes) / Decimal(nb_points_eau_affiches)) * 100
        ) if nb_points_eau_affiches > 0 else 0

        if taux_points_eau_integralement_pointes >= 80:
            couleur_pointage_points_eau = 'success'
        elif taux_points_eau_integralement_pointes >= 50:
            couleur_pointage_points_eau = 'warning'
        else:
            couleur_pointage_points_eau = 'error'

        data['nb_points_eau_affiches'] = nb_points_eau_affiches
        data['nb_points_eau_integralement_pointes'] = nb_points_eau_integralement_pointes
        data['taux_points_eau_integralement_pointes'] = taux_points_eau_integralement_pointes
        data['couleur_pointage_points_eau'] = couleur_pointage_points_eau

        data['ecart'] = data['total_releves'] - data['total_diamex']
        # Calculer le taux de recouvrement
        if data['total_releves'] > 0:
            data['taux'] = int((data['total_diamex'] / data['total_releves']) * 100)
        else:
            data['taux'] = 0

        # Encaissé caissière (relevés encaissés ou pointés) : suivi avant saisie compta
        data.setdefault('montant_encaisse', Decimal('0'))
        data.setdefault('montant_encaisse_non_pointe', Decimal('0'))
        data.setdefault('nb_encaisse_non_pointe', 0)
        data['taux_encaisse'] = (
            int((data['montant_encaisse'] / data['total_releves']) * 100)
            if data['total_releves'] > 0 else 0
        )

    if filter_non_pointe == '1':
        date_locale_filtre = timezone.now().astimezone(tz_madagascar).date()
        if filter_non_pointe_periode == 'passes':
            mois_non_pointes = {
                mois for mois in selected_months_set
                if annee < date_locale_filtre.year
                or (annee == date_locale_filtre.year and mois < date_locale_filtre.month)
            }
        elif filter_non_pointe_periode == 'courant':
            mois_non_pointes = (
                {date_locale_filtre.month}
                if annee == date_locale_filtre.year
                and date_locale_filtre.month in selected_months_set
                else set()
            )
        else:
            mois_non_pointes = set(selected_months_set)

        ouvrages_non_pointes = {
            str(data.get('ouvrage_id'))
            for data in recouvrement_par_ouvrage_mois.values()
            if data.get('mois') in mois_non_pointes
            and Decimal(str(data.get('montant_non_pointe_releve') or 0)) > 0
        }
        recouvrement_par_ouvrage_annee = {
            ouvrage_id: data
            for ouvrage_id, data in recouvrement_par_ouvrage_annee.items()
            if str(ouvrage_id) in ouvrages_non_pointes
        }

    # Convertir en liste et trier par district puis par taux décroissant
    from itertools import groupby

    recouvrement_liste = sorted(
        recouvrement_par_ouvrage_annee.values(),
        key=lambda x: (x['district_nom'], -x['taux'])
    )

    # Grouper par district
    recouvrement_par_district = {}
    for district_nom, items in groupby(recouvrement_liste, key=lambda x: x['district_nom']):
        recouvrement_par_district[district_nom] = list(items)

    # Calculer les taux de recouvrement mensuels pour chaque ouvrage
    taux_mensuels_par_ouvrage = {}
    for cle_mois, data in recouvrement_par_ouvrage_mois.items():
        ouvrage_id = data['ouvrage_id']
        mois = data['mois']

        # Calculer le taux pour ce mois
        if data['total_releves'] > 0:
            taux = int((data['total_diamex'] / data['total_releves']) * 100)
        else:
            taux = 0

        # Initialiser le dict pour cet ouvrage si nécessaire
        if ouvrage_id not in taux_mensuels_par_ouvrage:
            taux_mensuels_par_ouvrage[ouvrage_id] = {
                'ouvrage_id': ouvrage_id,
                'ouvrage_nom': data['ouvrage_nom'],
                'taux_annuel': recouvrement_par_ouvrage_annee.get(ouvrage_id, {}).get('taux', 0),
                'nb_points_eau_affiches': recouvrement_par_ouvrage_annee.get(ouvrage_id, {}).get('nb_points_eau_affiches', 0),
                'nb_points_eau_integralement_pointes': recouvrement_par_ouvrage_annee.get(ouvrage_id, {}).get('nb_points_eau_integralement_pointes', 0),
                'taux_points_eau_integralement_pointes': recouvrement_par_ouvrage_annee.get(ouvrage_id, {}).get('taux_points_eau_integralement_pointes', 0),
                'couleur_pointage_points_eau': recouvrement_par_ouvrage_annee.get(ouvrage_id, {}).get('couleur_pointage_points_eau', 'error'),
                'taux_par_mois': {}
            }

        # Stocker les détails pour ce mois (clé = numéro du mois)
        total_releves_mois = Decimal(str(data.get('total_releves') or 0))
        total_diamex_mois = Decimal(str(data.get('total_diamex') or 0))
        ecart_mois = data.get('ecart')
        if ecart_mois is None:
            ecart_mois = total_releves_mois - total_diamex_mois
        non_pointe_releve_mois = Decimal(str(data.get('montant_non_pointe_releve') or 0))
        non_pointe_compta_mois = Decimal(str(data.get('montant_non_pointe_compta') or 0))
        nb_non_pointe_releve_mois = int(data.get('nb_non_pointe_releve') or 0)
        nb_non_pointe_compta_mois = int(data.get('nb_non_pointe_compta') or 0)
        montant_non_recouvrable_mois = Decimal(str(data.get('montant_non_recouvrable') or 0))
        nb_non_recouvrable_mois = int(data.get('nb_non_recouvrable') or 0)

        taux_mensuels_par_ouvrage[ouvrage_id]['taux_par_mois'][mois] = {
            'taux': taux,
            'total_releves': float(total_releves_mois),
            'total_diamex': float(total_diamex_mois),
            'ecart': float(ecart_mois),
            'non_pointe_releve': float(non_pointe_releve_mois),
            'non_pointe_compta': float(non_pointe_compta_mois),
            'nb_non_pointe_releve': nb_non_pointe_releve_mois,
            'nb_non_pointe_compta': nb_non_pointe_compta_mois,
            'montant_non_recouvrable': float(montant_non_recouvrable_mois),
            'nb_non_recouvrable': nb_non_recouvrable_mois,
            'nb_releves': data['nb_releves']
        }

    # Grouper les ouvrages avec taux mensuels par district
    taux_mensuels_par_district = {}
    for ouvrage_id, taux_data in taux_mensuels_par_ouvrage.items():
        # Trouver le district de cet ouvrage dans recouvrement_par_ouvrage_annee
        if ouvrage_id in recouvrement_par_ouvrage_annee:
            district_nom = recouvrement_par_ouvrage_annee[ouvrage_id]['district_nom']

            if district_nom not in taux_mensuels_par_district:
                taux_mensuels_par_district[district_nom] = []

            taux_mensuels_par_district[district_nom].append(taux_data)

    remarques_qs = RemarqueRecouvrementVolume.objects.filter(
        ouvrage_id__in=list(taux_mensuels_par_ouvrage.keys()),
        annee=annee,
        mois__in=list(selected_months_set),
    ).values('ouvrage_id', 'mois', 'remarque')
    remarques_volume_map = {
        (str(item['ouvrage_id']), int(item['mois'])): (item['remarque'] or '').strip()
        for item in remarques_qs
    }

    volume_visible_month_labels = [
        {'number': 1, 'label': 'Jan'},
        {'number': 2, 'label': 'Fev'},
        {'number': 3, 'label': 'Mar'},
        {'number': 4, 'label': 'Avr'},
        {'number': 5, 'label': 'Mai'},
        {'number': 6, 'label': 'Jui'},
        {'number': 7, 'label': 'Jlt'},
        {'number': 8, 'label': 'Aou'},
        {'number': 9, 'label': 'Sep'},
        {'number': 10, 'label': 'Oct'},
        {'number': 11, 'label': 'Nov'},
        {'number': 12, 'label': 'Dec'},
    ]
    volume_visible_month_labels = [
        month for month in volume_visible_month_labels
        if month['number'] in selected_months_set
    ]
    visible_volume_month_numbers = [
        month['number']
        for month in volume_visible_month_labels
        if any(
            ouvrage_data['taux_par_mois'].get(month['number'])
            and (
                Decimal(str(ouvrage_data['taux_par_mois'][month['number']].get('total_releves') or 0)) > 0
                or Decimal(str(ouvrage_data['taux_par_mois'][month['number']].get('total_diamex') or 0)) > 0
                or Decimal(str(ouvrage_data['taux_par_mois'][month['number']].get('non_pointe_releve') or 0)) > 0
                or Decimal(str(ouvrage_data['taux_par_mois'][month['number']].get('non_pointe_compta') or 0)) > 0
                or Decimal(str(ouvrage_data['taux_par_mois'][month['number']].get('montant_non_recouvrable') or 0)) > 0
                or Decimal(str(ouvrage_data['taux_par_mois'][month['number']].get('ecart') or 0)) != 0
            )
            for ouvrage_data in taux_mensuels_par_ouvrage.values()
        )
    ]
    volume_visible_month_labels = [
        month
        for month in volume_visible_month_labels
        if month['number'] in visible_volume_month_numbers
    ]

    # Trier les ouvrages par nom dans chaque district et formater les données pour le template
    current_local_date = timezone.now().astimezone(tz_madagascar).date()
    current_month_number = current_local_date.month if annee == current_local_date.year else None

    if annee < current_local_date.year:
        mois_passes_stats = set(selected_months_set)
        mois_en_cours_stats = set()
    elif annee == current_local_date.year:
        mois_passes_stats = {
            mois for mois in selected_months_set
            if mois < current_local_date.month
        }
        mois_en_cours_stats = (
            {current_local_date.month}
            if current_local_date.month in selected_months_set
            else set()
        )
    else:
        mois_passes_stats = set()
        mois_en_cours_stats = set()

    def _pointage_points_eau_pour_mois(ouvrage_id, month_numbers):
        points_eau_agreges = {}
        donnees_mensuelles = pointage_points_eau_par_ouvrage_mois.get(ouvrage_id, {})
        for month_number in month_numbers:
            for point_eau_id, point_data in donnees_mensuelles.get(month_number, {}).items():
                if point_eau_id not in points_eau_agreges:
                    points_eau_agreges[point_eau_id] = {
                        'nb_factures': 0,
                        'nb_factures_pointees': 0,
                    }
                points_eau_agreges[point_eau_id]['nb_factures'] += int(
                    point_data.get('nb_factures') or 0
                )
                points_eau_agreges[point_eau_id]['nb_factures_pointees'] += int(
                    point_data.get('nb_factures_pointees') or 0
                )

        nb_points_eau = len(points_eau_agreges)
        nb_integralement_pointes = sum(
            1
            for point_data in points_eau_agreges.values()
            if point_data['nb_factures'] > 0
            and point_data['nb_factures'] == point_data['nb_factures_pointees']
        )
        taux = int(
            (Decimal(nb_integralement_pointes) / Decimal(nb_points_eau)) * 100
        ) if nb_points_eau > 0 else 0
        if taux >= 80:
            couleur = 'success'
        elif taux >= 50:
            couleur = 'warning'
        else:
            couleur = 'error'
        return {
            'nb_points_eau': nb_points_eau,
            'nb_integralement_pointes': nb_integralement_pointes,
            'taux': taux,
            'progression': min(taux, 100),
            'couleur': couleur,
            'has_data': nb_points_eau > 0,
        }

    for district_nom in taux_mensuels_par_district:
        taux_mensuels_par_district[district_nom].sort(key=lambda x: x['ouvrage_nom'])
        # Formater taux_par_mois pour faciliter l'accès dans le template
        for ouvrage_data in taux_mensuels_par_district[district_nom]:
            # Contrôle: alerter si le montant prévu mensuel dépasse de 50% la moyenne
            montants_prevus = [
                Decimal(str(item.get('total_releves') or 0))
                for item in ouvrage_data['taux_par_mois'].values()
                if Decimal(str(item.get('total_releves') or 0)) > 0
            ]

            moyenne_prevu = Decimal('0')
            if montants_prevus:
                moyenne_prevu = sum(montants_prevus, Decimal('0')) / Decimal(len(montants_prevus))
            seuil_alerte_prevu = moyenne_prevu * Decimal('1.5')

            nb_mois_depassement = 0
            for item in ouvrage_data['taux_par_mois'].values():
                total_releves_item = Decimal(str(item.get('total_releves') or 0))
                depasse_50_moyenne = (
                    moyenne_prevu > 0 and total_releves_item > seuil_alerte_prevu
                )
                item['depasse_50_moyenne'] = depasse_50_moyenne
                item['moyenne_prevu_ouvrage'] = float(moyenne_prevu)
                item['seuil_alerte_prevu'] = float(seuil_alerte_prevu)
                if depasse_50_moyenne:
                    nb_mois_depassement += 1

            ouvrage_data['moyenne_prevu'] = float(moyenne_prevu)
            ouvrage_data['seuil_alerte_prevu'] = float(seuil_alerte_prevu)
            ouvrage_data['nb_mois_depassement_prevu'] = nb_mois_depassement

            total_releves_mois_passes = Decimal('0')
            total_diamex_mois_passes = Decimal('0')
            total_releves_mois_en_cours = Decimal('0')
            total_diamex_mois_en_cours = Decimal('0')

            for month_number, month_data in ouvrage_data['taux_par_mois'].items():
                total_releves_month = Decimal(str(month_data.get('total_releves') or 0))
                total_diamex_month = Decimal(str(month_data.get('total_diamex') or 0))

                if current_month_number and month_number == current_month_number:
                    total_releves_mois_en_cours += total_releves_month
                    total_diamex_mois_en_cours += total_diamex_month
                elif current_month_number and month_number < current_month_number:
                    total_releves_mois_passes += total_releves_month
                    total_diamex_mois_passes += total_diamex_month
                elif current_month_number is None:
                    total_releves_mois_passes += total_releves_month
                    total_diamex_mois_passes += total_diamex_month

            ouvrage_data['taux_mois_passes'] = int(
                (total_diamex_mois_passes / total_releves_mois_passes) * 100
            ) if total_releves_mois_passes > 0 else 0
            ouvrage_data['taux_mois_en_cours'] = int(
                (total_diamex_mois_en_cours / total_releves_mois_en_cours) * 100
            ) if total_releves_mois_en_cours > 0 else 0
            ouvrage_data['has_mois_en_cours'] = bool(
                current_month_number
                and current_month_number in ouvrage_data['taux_par_mois']
            )
            ouvrage_data['pointage_pe_mois_passes'] = _pointage_points_eau_pour_mois(
                ouvrage_data['ouvrage_id'],
                mois_passes_stats,
            )
            ouvrage_data['pointage_pe_mois_en_cours'] = _pointage_points_eau_pour_mois(
                ouvrage_data['ouvrage_id'],
                mois_en_cours_stats,
            )

            # Créer une liste ordonnée des données pour les 12 mois
            ouvrage_data['taux_mois_list'] = [
                ouvrage_data['taux_par_mois'].get(mois, None) for mois in range(1, 13)
            ]
            ouvrage_data['visible_months'] = [
                {
                    'number': month['number'],
                    'label': month['label'],
                    'data': ouvrage_data['taux_par_mois'].get(month['number']),
                    'remarque': remarques_volume_map.get((str(ouvrage_data['ouvrage_id']), month['number']), ''),
                }
                for month in volume_visible_month_labels
            ]

    # 3. Analyse des délais de paiement
    # Récupérer les transactions DiameX 707401 (factures volumétriques)
    transactions_factures = BaseDiameX.objects.filter(
        compte_code='707401',
        description__isnull=False
    ).exclude(description='')

    delais_paiement = {
        'meme_mois': {'nb': 0, 'montant': Decimal('0')},
        '1_mois': {'nb': 0, 'montant': Decimal('0')},
        '2_mois': {'nb': 0, 'montant': Decimal('0')},
        '3_mois_plus': {'nb': 0, 'montant': Decimal('0')},
        'non_determine': {'nb': 0, 'montant': Decimal('0')},
        'non_paye': {'nb': 0, 'montant': Decimal('0')}
    }

    for transaction in transactions_factures:
        # Utiliser l'extracteur existant pour parser la description
        # Format: "Paiement au volume Ankorabe 01/12/2025" ou multiple entrées séparées par ";"
        info = extraire_ouvrage_et_mois_paiement_volume(transaction.description)

        # L'extracteur peut retourner un dict (paiement simple) ou une liste (multi-paiements)
        infos_list = info if isinstance(info, list) else [info]

        # Pour les multi-paiements, on divise le montant total de la transaction
        montant_transaction = Decimal(str(transaction.montant_in)) if transaction.montant_in else Decimal('0')
        nb_paiements = len([i for i in infos_list if i.get('mois') and i.get('annee')])
        montant_par_paiement = montant_transaction / nb_paiements if nb_paiements > 0 else montant_transaction

        for info_item in infos_list:
            ouvrage_obj = info_item.get('ouvrage_obj') if info_item else None
            if not ouvrage_obj or str(ouvrage_obj.id) not in ouvrages_filtres_ids:
                continue

            if info_item and info_item.get('mois') and info_item.get('annee'):
                mois_facture = info_item['mois']
                annee_facture = info_item['annee']
                if annee_facture != annee or mois_facture not in selected_months_set:
                    continue

                # Date de paiement (date_rec est un DateField)
                if transaction.date_rec:
                    mois_paiement = transaction.date_rec.month
                    annee_paiement = transaction.date_rec.year

                    # Calculer le délai en mois
                    delai_mois = (annee_paiement - annee_facture) * 12 + (mois_paiement - mois_facture)

                    montant = montant_par_paiement

                    # Catégoriser
                    if delai_mois == 0:
                        delais_paiement['meme_mois']['nb'] += 1
                        delais_paiement['meme_mois']['montant'] += montant
                    elif delai_mois == 1:
                        delais_paiement['1_mois']['nb'] += 1
                        delais_paiement['1_mois']['montant'] += montant
                    elif delai_mois == 2:
                        delais_paiement['2_mois']['nb'] += 1
                        delais_paiement['2_mois']['montant'] += montant
                    elif delai_mois >= 3:
                        delais_paiement['3_mois_plus']['nb'] += 1
                        delais_paiement['3_mois_plus']['montant'] += montant
                    else:
                        # Délai négatif (paiement avant facture - anomalie)
                        delais_paiement['non_determine']['nb'] += 1
                        delais_paiement['non_determine']['montant'] += montant
    # Calculer les relevés non payés (sans numeroDiameX)
    for releve in releves_qs:
        if (
            releve.montant
            and not releve.numeroDiameX
            and not _is_releve_non_recouvrable(releve, periodes_coupure)
        ):
            montant = Decimal(str(releve.montant))
            delais_paiement['non_paye']['nb'] += 1
            delais_paiement['non_paye']['montant'] += montant

    # 4. Statistiques globales
    total_releves_global = sum(d['total_releves'] for d in recouvrement_par_ouvrage_annee.values())
    total_diamex_global = sum(d['total_diamex'] for d in recouvrement_par_ouvrage_annee.values())
    montant_non_recouvrable_global = sum(
        (Decimal(str(d.get('montant_non_recouvrable') or 0)) for d in recouvrement_par_ouvrage_annee.values()),
        Decimal('0'),
    )
    nb_non_recouvrable_global = sum(
        int(d.get('nb_non_recouvrable') or 0)
        for d in recouvrement_par_ouvrage_annee.values()
    )
    total_non_paye_global = total_releves_global - total_diamex_global  # Part non payée
    taux_recouvrement_global = int((total_diamex_global / total_releves_global * 100) if total_releves_global > 0 else 0)

    # Encaissé par la caissière (suivi rapide) : relevés encaissés ou pointés
    total_encaisse_global = sum(
        (Decimal(str(d.get('montant_encaisse') or 0)) for d in recouvrement_par_ouvrage_annee.values()),
        Decimal('0'),
    )
    total_encaisse_non_pointe_global = sum(
        (Decimal(str(d.get('montant_encaisse_non_pointe') or 0)) for d in recouvrement_par_ouvrage_annee.values()),
        Decimal('0'),
    )
    nb_encaisse_non_pointe_global = sum(
        int(d.get('nb_encaisse_non_pointe') or 0) for d in recouvrement_par_ouvrage_annee.values()
    )
    taux_encaisse_global = int((total_encaisse_global / total_releves_global * 100) if total_releves_global > 0 else 0)

    # Separer le recouvrement des periodes deja echues de celui du mois courant.
    # Le classement repose sur le mois de facturation extrait/rattache, pas sur la
    # date d'encaissement DiameX. Les mois futurs ne figurent dans aucun des deux KPI.
    def _totaux_recouvrement_pour_mois(month_numbers):
        total_prevu = sum(
            (
                Decimal(str(data.get('total_releves') or 0))
                for data in recouvrement_par_ouvrage_mois.values()
                if data.get('mois') in month_numbers
            ),
            Decimal('0')
        )
        total_paye = sum(
            (
                Decimal(str(data.get('total_diamex') or 0))
                for data in recouvrement_par_ouvrage_mois.values()
                if data.get('mois') in month_numbers
            ),
            Decimal('0')
        )
        taux = int((total_paye / total_prevu) * 100) if total_prevu > 0 else 0
        ecart = total_prevu - total_paye
        # Encaissé caissière (relevés encaissés ou pointés) sur les mêmes mois que le prévu
        mois_periode = [d for d in recouvrement_par_ouvrage_mois.values() if d.get('mois') in month_numbers]
        total_encaisse = sum((Decimal(str(d.get('montant_encaisse') or 0)) for d in mois_periode), Decimal('0'))
        encaisse_non_pointe = sum((Decimal(str(d.get('montant_encaisse_non_pointe') or 0)) for d in mois_periode), Decimal('0'))
        return {
            'total_encaisse': total_encaisse,
            'total_encaisse_k': int(total_encaisse / 1000),
            'encaisse_non_pointe_k': int(encaisse_non_pointe / 1000),
            'nb_encaisse_non_pointe': sum(int(d.get('nb_encaisse_non_pointe') or 0) for d in mois_periode),
            # Pointé = encaissé confirmé par le pointage ; écart = encaissé - pointé
            'total_pointe_k': int((total_encaisse - encaisse_non_pointe) / 1000),
            'ecart_encaisse_pointe': encaisse_non_pointe,
            'taux_encaisse': int((total_encaisse / total_prevu) * 100) if total_prevu > 0 else 0,
            'total_prevu': total_prevu,
            'total_paye': total_paye,
            'total_prevu_k': int(total_prevu / 1000),
            'total_paye_k': int(total_paye / 1000),
            'ecart': ecart,
            'ecart_k': int(ecart / 1000),
            'taux': taux,
            'progression': min(taux, 100),
            'has_data': total_prevu > 0,
        }

    recouvrement_mois_passes = _totaux_recouvrement_pour_mois(mois_passes_stats)
    recouvrement_mois_en_cours = _totaux_recouvrement_pour_mois(mois_en_cours_stats)

    # Recouvrement ventilé par type de point d'eau (et, pour les kiosques, par
    # type d'abonné). Le « payé » est ici le montant des relevés POINTÉS : les
    # écritures DiameX sont rattachées à l'ouvrage et au mois, jamais au point d'eau.
    def _segment_point_eau(point_eau):
        type_obj = getattr(point_eau, 'type_point_eau', None)
        type_nom = getattr(type_obj, 'nom_type', None) or 'Sans type'
        sous_segment = None
        if type_nom.strip().lower() == 'kiosque':
            abonne = (getattr(point_eau, 'typeabonne', None) or '').strip().lower()
            sous_segment = abonne if abonne in ('particulier', 'boutique') else 'non_renseigne'
        return type_nom, sous_segment

    def _compteurs_vides():
        return {
            'prevu': Decimal('0'), 'paye': Decimal('0'),
            'encaisse': Decimal('0'), 'encaisse_non_pointe': Decimal('0'),
            'nb_encaisse_non_pointe': 0,
        }

    def _finaliser_compteurs(c):
        prevu, paye = c['prevu'], c['paye']
        taux = int((paye / prevu) * 100) if prevu > 0 else 0
        ecart = prevu - paye
        return {
            'has_data': prevu > 0,
            'taux': taux,
            'progression': min(taux, 100),
            'total_prevu_k': int(prevu / 1000),
            'total_paye_k': int(paye / 1000),
            'ecart': ecart,
            'ecart_k': int(ecart / 1000),
            'taux_encaisse': int((c['encaisse'] / prevu) * 100) if prevu > 0 else 0,
            'total_encaisse_k': int(c['encaisse'] / 1000),
            'total_pointe_k': int((c['encaisse'] - c['encaisse_non_pointe']) / 1000),
            'encaisse_non_pointe_k': int(c['encaisse_non_pointe'] / 1000),
            'ecart_encaisse_pointe': c['encaisse_non_pointe'],
            'nb_encaisse_non_pointe': c['nb_encaisse_non_pointe'],
        }

    segments_compteurs = {}
    for releve in releves_qs:
        point_eau = getattr(releve, 'point_eau', None)
        if not point_eau or _is_releve_non_recouvrable(releve, periodes_coupure):
            continue
        annee_cible, mois_cible = _resolve_billing_period(releve.datereleve)
        if annee_cible != annee:
            continue
        if mois_cible in mois_passes_stats:
            periode = 'passes'
        elif mois_cible in mois_en_cours_stats:
            periode = 'en_cours'
        else:
            continue

        montant = Decimal(str(releve.montant or 0))
        pointe = bool(_pair_key(releve.numeroDiameX, releve.baseDiameX))
        type_nom, sous_segment = _segment_point_eau(point_eau)
        cibles = [(type_nom, None)]
        if sous_segment:
            cibles.append((type_nom, sous_segment))
        for cle in cibles:
            compteurs = segments_compteurs.setdefault(cle, {
                'passes': _compteurs_vides(), 'en_cours': _compteurs_vides(),
            })[periode]
            compteurs['prevu'] += montant
            if pointe:
                compteurs['paye'] += montant
            if releve.datepaiement or pointe:
                compteurs['encaisse'] += montant
                if not pointe:
                    compteurs['encaisse_non_pointe'] += montant
                    compteurs['nb_encaisse_non_pointe'] += 1

    libelles_sous_segments = {
        'particulier': 'Particuliers',
        'boutique': 'Boutiques',
        'non_renseigne': 'Type d\'abonné non renseigné',
    }

    def _construire_segment(label, par_periode):
        return {
            'label': label,
            'passes': _finaliser_compteurs(par_periode['passes']),
            'en_cours': _finaliser_compteurs(par_periode['en_cours']),
            'prevu_total': par_periode['passes']['prevu'] + par_periode['en_cours']['prevu'],
            'sous_segments': [],
        }

    segments_recouvrement = []
    for (type_nom, sous), par_periode in segments_compteurs.items():
        if sous is None:
            segments_recouvrement.append(_construire_segment(type_nom, par_periode))
    segments_recouvrement.sort(key=lambda s: (-s['prevu_total'], s['label'].lower()))
    for segment in segments_recouvrement:
        enfants = [
            (sous, par_periode)
            for (type_nom, sous), par_periode in segments_compteurs.items()
            if type_nom == segment['label'] and sous is not None
        ]
        for sous, par_periode in sorted(enfants, key=lambda item: ('non_renseigne' == item[0], item[0])):
            segment['sous_segments'].append(
                _construire_segment(libelles_sous_segments[sous], par_periode)
            )

    noms_mois_fr = [
        '', 'Janvier', 'Fevrier', 'Mars', 'Avril', 'Mai', 'Juin',
        'Juillet', 'Aout', 'Septembre', 'Octobre', 'Novembre', 'Decembre'
    ]
    recouvrement_mois_passes['nb_mois'] = len(mois_passes_stats)
    recouvrement_mois_en_cours['libelle_mois'] = (
        noms_mois_fr[current_local_date.month]
        if mois_en_cours_stats
        else ''
    )
    nb_ouvrages_recouvrement_100 = sum(
        1
        for d in recouvrement_par_ouvrage_annee.values()
        if Decimal(str(d.get('total_releves') or 0)) > 0
        and Decimal(str(d.get('total_diamex') or 0)) >= Decimal(str(d.get('total_releves') or 0))
    )
    # Montants non pointés basés sur les lignes réellement pointées/non pointées
    montant_non_pointe_releve = sum(
        (Decimal(str(d.get('montant_non_pointe_releve') or 0)) for d in recouvrement_par_ouvrage_mois.values()),
        Decimal('0')
    )
    montant_non_pointe_releve_mois_passes = sum(
        (
            Decimal(str(d.get('montant_non_pointe_releve') or 0))
            for d in recouvrement_par_ouvrage_mois.values()
            if d.get('mois') in mois_passes_stats
        ),
        Decimal('0')
    )
    montant_non_pointe_releve_mois_en_cours = sum(
        (
            Decimal(str(d.get('montant_non_pointe_releve') or 0))
            for d in recouvrement_par_ouvrage_mois.values()
            if d.get('mois') in mois_en_cours_stats
        ),
        Decimal('0')
    )
    montant_non_pointe_compta = sum(
        (Decimal(str(d.get('montant_non_pointe_compta') or 0)) for d in recouvrement_par_ouvrage_mois.values()),
        Decimal('0')
    )
    montant_non_pointe_compta_mois_passes = sum(
        (
            Decimal(str(d.get('montant_non_pointe_compta') or 0))
            for d in recouvrement_par_ouvrage_mois.values()
            if d.get('mois') in mois_passes_stats
        ),
        Decimal('0')
    )
    montant_non_pointe_compta_mois_en_cours = sum(
        (
            Decimal(str(d.get('montant_non_pointe_compta') or 0))
            for d in recouvrement_par_ouvrage_mois.values()
            if d.get('mois') in mois_en_cours_stats
        ),
        Decimal('0')
    )
    nb_lignes_releve_non_pointe = sum(
        int(d.get('nb_non_pointe_releve') or 0)
        for d in recouvrement_par_ouvrage_mois.values()
    )
    nb_lignes_diamex_non_pointe = sum(
        int(d.get('nb_non_pointe_compta') or 0)
        for d in recouvrement_par_ouvrage_mois.values()
    )
    nb_lignes_diamex_non_pointe_mois_passes = sum(
        int(d.get('nb_non_pointe_compta') or 0)
        for d in recouvrement_par_ouvrage_mois.values()
        if d.get('mois') in mois_passes_stats
    )
    nb_lignes_diamex_non_pointe_mois_en_cours = sum(
        int(d.get('nb_non_pointe_compta') or 0)
        for d in recouvrement_par_ouvrage_mois.values()
        if d.get('mois') in mois_en_cours_stats
    )
    nb_lignes_releve_non_pointe_mois_passes = sum(
        int(d.get('nb_non_pointe_releve') or 0)
        for d in recouvrement_par_ouvrage_mois.values()
        if d.get('mois') in mois_passes_stats
    )
    nb_lignes_releve_non_pointe_mois_en_cours = sum(
        int(d.get('nb_non_pointe_releve') or 0)
        for d in recouvrement_par_ouvrage_mois.values()
        if d.get('mois') in mois_en_cours_stats
    )

    # Conversion en milliers d'ariary pour l'affichage des cartes KPI.
    total_releves_global_k = int(total_releves_global / 1000)
    total_diamex_global_k = int(total_diamex_global / 1000)
    ecart_global_k = int((total_releves_global - total_diamex_global) / 1000)
    montant_non_pointe_releve_k = int(montant_non_pointe_releve / 1000)
    montant_non_pointe_releve_mois_passes_k = int(montant_non_pointe_releve_mois_passes / 1000)
    montant_non_pointe_releve_mois_en_cours_k = int(montant_non_pointe_releve_mois_en_cours / 1000)
    montant_non_pointe_compta_k = int(montant_non_pointe_compta / 1000)
    montant_non_pointe_compta_mois_passes_k = int(montant_non_pointe_compta_mois_passes / 1000)
    montant_non_pointe_compta_mois_en_cours_k = int(montant_non_pointe_compta_mois_en_cours / 1000)

    # 5. Préparer les données pour les graphiques
    # Graphique recouvrement par mois
    mois_labels = []
    montants_prevus = []
    montants_payes = []

    for mois in selected_months:
        mois_labels.append(datetime(annee, mois, 1).strftime('%b'))
        total_prevu = sum(d['total_releves'] for d in recouvrement_par_ouvrage_mois.values() if d['mois'] == mois)
        total_paye = sum(d['total_diamex'] for d in recouvrement_par_ouvrage_mois.values() if d['mois'] == mois)
        montants_prevus.append(float(total_prevu))
        montants_payes.append(float(total_paye))

    # Listes pour filtres
    from apps.organization.models import Ouvrage
    from apps.geography.models import District, Commune

    # Récupérer les IDs des ouvrages de l'organisation (via ModaliteGestion)
    ouvrages_org_ids = list(
        _get_responsable_scoped_ouvrage_ids(
            request.user,
            effective_gestionnaire_ids=effective_gestionnaire_ids,
            modalites=['au_volume', 'mixte'],
        )
    )

    # APPROCHE RESTRUCTURéE : Filtrer via PointEau d'abord, puis extraire les IDs géographiques
    from apps.billing.models import PointEau

    # Récupérer les PointEau filtrés par organisation et année
    points_eau_filtre_base = PointEau.objects.filter(
        ouvrage_id__in=ouvrages_org_ids,
        releves__datereleve__year=annee,
        releves__montant__isnull=False
    ).select_related('parcelle__village__fokontany__commune__district__region')
    if filter_trimestre != 'all':
        source_months = [12] if 1 in selected_months_set else []
        source_months.extend([month - 1 for month in selected_months if month > 1])
        points_eau_filtre_base = points_eau_filtre_base.filter(releves__datereleve__month__in=source_months)

    # Extraire les IDs uniques et les chemins géographiques disponibles.
    # Un ouvrage peut avoir des points d'eau dans plusieurs communes : les
    # chemins sont donc conservés ici, puis le premier chemin correspondant
    # aux filtres actifs est utilisé pour l'afficher une seule fois.
    district_ids = set()
    region_ids = set()
    commune_ids = set()
    ouvrage_ids_actifs = set()
    ouvrage_geo_paths = defaultdict(set)

    points_eau_actifs = list(points_eau_filtre_base.distinct())
    for pe in points_eau_actifs:
        ouvrage_ids_actifs.add(pe.ouvrage_id)
        if pe.parcelle and pe.parcelle.village and pe.parcelle.village.fokontany:
            fokontany = pe.parcelle.village.fokontany
            if fokontany.commune:
                commune = fokontany.commune
                commune_ids.add(commune.id)
                if commune.district:
                    district = commune.district
                    district_ids.add(district.id)
                    if district.region:
                        region = district.region
                        region_ids.add(region.id)
                        ouvrage_geo_paths[str(pe.ouvrage_id)].add((
                            str(region.id),
                            region.nom_region or 'Sans région',
                            str(district.id),
                            district.nom_district or 'Sans district',
                            str(commune.id),
                            commune.nom_commune or 'Sans commune',
                        ))

    # Regions disponibles
    regions = Region.objects.filter(
        id__in=list(region_ids)
    ).order_by('nom_region') if has_gestionnaire_scope and region_ids else Region.objects.none()

    # Districts disponibles
    districts_qs = District.objects.filter(id__in=list(district_ids))
    if filter_region and filter_region != 'all':
        districts_qs = districts_qs.filter(region_id=filter_region)

    districts = list(
        districts_qs.select_related('region').order_by('region__nom_region', 'nom_district')
    ) if has_gestionnaire_scope and district_ids else []

    # Communes disponibles (filtrées par district si sélectionné)
    communes_qs = Commune.objects.filter(id__in=list(commune_ids))
    if filter_district and filter_district != 'all':
        communes_qs = communes_qs.filter(district_id=filter_district)
    elif filter_region and filter_region != 'all':
        communes_qs = communes_qs.filter(district__region_id=filter_region)
    communes = list(
        communes_qs.select_related('district__region').order_by(
            'district__region__nom_region', 'district__nom_district', 'nom_commune'
        )
    ) if has_gestionnaire_scope and commune_ids else []

    # Ouvrages disponibles (filtrés par commune ou district si sélectionné)
    ouvrages_qs = Ouvrage.objects.filter(id__in=list(ouvrage_ids_actifs))

    if filter_commune and filter_commune != 'all':
        # Filtrer ouvrages par points d'eau dans cette commune
        pe_commune = PointEau.objects.filter(
            ouvrage_id__in=list(ouvrage_ids_actifs),
            parcelle__village__fokontany__commune_id=filter_commune
        ).values_list('ouvrage_id', flat=True).distinct()
        ouvrages_qs = ouvrages_qs.filter(id__in=list(pe_commune))
    elif filter_district and filter_district != 'all':
        # Filtrer ouvrages par points d'eau dans ce district
        pe_district = PointEau.objects.filter(
            ouvrage_id__in=list(ouvrage_ids_actifs),
            parcelle__village__fokontany__commune__district_id=filter_district
        ).values_list('ouvrage_id', flat=True).distinct()
        ouvrages_qs = ouvrages_qs.filter(id__in=list(pe_district))
    elif filter_region and filter_region != 'all':
        pe_region = PointEau.objects.filter(
            ouvrage_id__in=list(ouvrage_ids_actifs),
            parcelle__village__fokontany__commune__district__region_id=filter_region
        ).values_list('ouvrage_id', flat=True).distinct()
        ouvrages_qs = ouvrages_qs.filter(id__in=list(pe_region))

    ouvrages = list(ouvrages_qs.order_by('nom_ouvrage'))

    # Options hiérarchiques des listes déroulantes. Les lignes de regroupement
    # sont rendues désactivées dans le template et le niveau correspondant est
    # omis dès que son filtre parent est actif.
    region_active = bool(filter_region and filter_region != 'all')
    district_active = bool(filter_district and filter_district != 'all')
    commune_active = bool(filter_commune and filter_commune != 'all')

    # Un filtre enfant actif rend également inutiles tous les regroupements
    # situés au-dessus de lui. Par exemple, avec un district sélectionné, les
    # listes Commune et Ouvrage n'affichent plus ni Région ni District.
    hide_region_in_communes = region_active or district_active
    hide_region_in_ouvrages = region_active or district_active or commune_active
    hide_district_in_ouvrages = district_active or commune_active

    district_filter_options = []
    last_region_id = None
    for district in districts:
        region = district.region
        region_id = str(region.id) if region else ''
        if not region_active and region_id != last_region_id:
            district_filter_options.append({
                'kind': 'region',
                'label': region.nom_region if region else 'Sans région',
            })
        district_filter_options.append({
            'kind': 'option',
            'id': district.id,
            'label': district.nom_district,
            'region_id': region_id,
        })
        last_region_id = region_id

    commune_filter_options = []
    last_region_id = None
    last_district_id = None
    for commune in communes:
        district = commune.district
        region = district.region if district else None
        region_id = str(region.id) if region else ''
        district_id = str(district.id) if district else ''
        if not hide_region_in_communes and region_id != last_region_id:
            commune_filter_options.append({
                'kind': 'region',
                'label': region.nom_region if region else 'Sans région',
            })
            last_district_id = None
        if not district_active and district_id != last_district_id:
            commune_filter_options.append({
                'kind': 'district',
                'label': district.nom_district if district else 'Sans district',
            })
        commune_filter_options.append({
            'kind': 'option',
            'id': commune.id,
            'label': commune.nom_commune,
            'region_id': region_id,
            'district_id': district_id,
        })
        last_region_id = region_id
        last_district_id = district_id

    ouvrage_filter_options = []
    ouvrage_rows = []
    for ouvrage in ouvrages:
        paths = list(ouvrage_geo_paths.get(str(ouvrage.id), set()))
        if region_active:
            paths = [path for path in paths if path[0] == str(filter_region)]
        if district_active:
            paths = [path for path in paths if path[2] == str(filter_district)]
        if commune_active:
            paths = [path for path in paths if path[4] == str(filter_commune)]
        path = sorted(paths, key=lambda item: (item[1].lower(), item[3].lower(), item[5].lower()))[0] if paths else (
            '', 'Sans région', '', 'Sans district', '', 'Sans commune'
        )
        ouvrage_rows.append((path, ouvrage))

    ouvrage_rows.sort(key=lambda item: (
        item[0][1].lower(), item[0][3].lower(), item[0][5].lower(),
        (item[1].nom_ouvrage or '').lower()
    ))
    last_region_id = None
    last_district_id = None
    last_commune_id = None
    for path, ouvrage in ouvrage_rows:
        region_id, region_label, district_id, district_label, commune_id, commune_label = path
        if not hide_region_in_ouvrages and region_id != last_region_id:
            ouvrage_filter_options.append({'kind': 'region', 'label': region_label})
            last_district_id = None
            last_commune_id = None
        if not hide_district_in_ouvrages and district_id != last_district_id:
            ouvrage_filter_options.append({'kind': 'district', 'label': district_label})
            last_commune_id = None
        if not commune_active and commune_id != last_commune_id:
            ouvrage_filter_options.append({'kind': 'commune', 'label': commune_label})
        ouvrage_filter_options.append({
            'kind': 'option',
            'id': ouvrage.id,
            'label': ouvrage.nom_ouvrage,
            'region_id': region_id,
            'district_id': district_id,
            'commune_id': commune_id,
        })
        last_region_id = region_id
        last_district_id = district_id
        last_commune_id = commune_id

    # Métadonnées utilisées par la cascade Employé -> Région -> District -> Commune -> Ouvrage.
    employe_ids_par_region = defaultdict(set)
    employe_ids_par_district = defaultdict(set)
    employe_ids_par_commune = defaultdict(set)
    for point_eau in points_eau_actifs:
        employee_ids = employe_ids_par_ouvrage.get(str(point_eau.ouvrage_id), set())
        parcelle_obj = getattr(point_eau, 'parcelle', None)
        village_obj = getattr(parcelle_obj, 'village', None)
        fokontany_obj = getattr(village_obj, 'fokontany', None)
        commune_obj = getattr(fokontany_obj, 'commune', None)
        if not commune_obj:
            continue
        for employee_id in employee_ids:
            employe_ids_par_commune[str(commune_obj.id)].add(employee_id)
            employe_ids_par_district[str(commune_obj.district_id)].add(employee_id)
            employe_ids_par_region[str(commune_obj.district.region_id)].add(employee_id)

    regions = list(regions)
    for region in regions:
        region.filter_employe_ids = ','.join(sorted(employe_ids_par_region[str(region.id)]))
    for district in districts:
        district.filter_employe_ids = ','.join(sorted(employe_ids_par_district[str(district.id)]))
    for commune in communes:
        commune.filter_employe_ids = ','.join(sorted(employe_ids_par_commune[str(commune.id)]))
    for item in district_filter_options:
        if item.get('kind') == 'option':
            item['employe_ids'] = ','.join(sorted(employe_ids_par_district[str(item['id'])]))
    for item in commune_filter_options:
        if item.get('kind') == 'option':
            item['employe_ids'] = ','.join(sorted(employe_ids_par_commune[str(item['id'])]))
    for item in ouvrage_filter_options:
        if item.get('kind') == 'option':
            item['employe_ids'] = ','.join(sorted(employe_ids_par_ouvrage.get(str(item['id']), set())))

    # 6. Préparer données pour graphique comparaison par commune
    # Grouper les données de recouvrement par commune
    recouvrement_par_commune = {}
    for releve in releves_qs:
        if not releve.point_eau or not releve.point_eau.parcelle:
            continue
        if _is_releve_non_recouvrable(releve, periodes_coupure):
            continue

        # Récupérer la commune via la chaîne de relations
        commune_nom = None
        if releve.point_eau.parcelle.village and releve.point_eau.parcelle.village.fokontany:
            fokontany = releve.point_eau.parcelle.village.fokontany
            if fokontany.commune:
                commune_nom = fokontany.commune.nom_commune

        if not commune_nom:
            continue

        if commune_nom not in recouvrement_par_commune:
            recouvrement_par_commune[commune_nom] = {
                'total_releves': Decimal('0'),
                'total_diamex': Decimal('0')
            }

        montant = Decimal(str(releve.montant)) if releve.montant else Decimal('0')
        recouvrement_par_commune[commune_nom]['total_releves'] += montant

        if releve.numeroDiameX:
            recouvrement_par_commune[commune_nom]['total_diamex'] += montant

    # Préparer les données pour le graphique
    communes_labels = []
    communes_prevus = []
    communes_payes = []
    communes_taux = []

    for commune_nom in sorted(recouvrement_par_commune.keys()):
        data = recouvrement_par_commune[commune_nom]
        communes_labels.append(commune_nom)
        communes_prevus.append(float(data['total_releves']))
        communes_payes.append(float(data['total_diamex']))
        taux = int((data['total_diamex'] / data['total_releves'] * 100) if data['total_releves'] > 0 else 0)
        communes_taux.append(taux)
    if show_only_score_gap:
        recouvrement_liste = [
            item for item in recouvrement_liste
            if str(item['ouvrage_id']) in score_gap_ouvrage_ids
        ]
        recouvrement_par_district = {
            district_nom: [
                item for item in items
                if str(item['ouvrage_id']) in score_gap_ouvrage_ids
            ]
            for district_nom, items in recouvrement_par_district.items()
        }
        recouvrement_par_district = {
            district_nom: items
            for district_nom, items in recouvrement_par_district.items()
            if items
        }
        taux_mensuels_par_district = {
            district_nom: [
                item for item in items
                if str(item['ouvrage_id']) in score_gap_ouvrage_ids
            ]
            for district_nom, items in taux_mensuels_par_district.items()
        }
        taux_mensuels_par_district = {
            district_nom: items
            for district_nom, items in taux_mensuels_par_district.items()
            if items
        }

    # Totaux agrégés par mois visible pour l'en-tête du tableau mensuel.
    # Reflète le filtre en cours : somme de tous les ouvrages affichés.
    volume_month_totals = {}
    for _mois_num in [_m['number'] for _m in volume_visible_month_labels]:
        _tot_releves_mois = Decimal('0')
        _tot_diamex_mois = Decimal('0')
        for _district_ouvrages in taux_mensuels_par_district.values():
            for _ouvrage_data in _district_ouvrages:
                _month_data = _ouvrage_data['taux_par_mois'].get(_mois_num)
                if not _month_data:
                    continue
                _tot_releves_mois += Decimal(str(_month_data.get('total_releves') or 0))
                _tot_diamex_mois += Decimal(str(_month_data.get('total_diamex') or 0))
        _taux_mois = (
            int((_tot_diamex_mois / _tot_releves_mois) * 100)
            if _tot_releves_mois > 0 else 0
        )
        volume_month_totals[_mois_num] = {
            'taux': _taux_mois,
            'total_releves': float(_tot_releves_mois),
            'total_diamex': float(_tot_diamex_mois),
            'has_data': _tot_releves_mois > 0 or _tot_diamex_mois > 0,
        }

    for _month in volume_visible_month_labels:
        _month['total'] = volume_month_totals.get(_month['number'])

    context = {
        'annee': annee,
        'afficher_recouvrement_mois_en_cours': annee == current_local_date.year,
        'segments_recouvrement': segments_recouvrement,
        'filter_type_pe': filter_type_pe,
        'filter_type_abonne': filter_type_abonne,
        'type_filter_actif': type_filter_actif,
        'types_point_eau_options': [
            {'id': str(t.id), 'nom': t.nom_type}
            for t in TypePointEau.objects.filter(actif=True).order_by('nom_type')
        ],
        'filter_trimestre': filter_trimestre,
        'filter_semestre': filter_semestre,
        'filter_organisation': filter_organisation,
        'filter_region': filter_region,
        'filter_district': filter_district,
        'filter_commune': filter_commune,
        'filter_ouvrage': filter_ouvrage,
        'filter_employe': filter_employe,
        'filter_non_pointe': filter_non_pointe,
        'filter_non_pointe_periode': filter_non_pointe_periode,
        'organisations': organisations,
        'show_organisation_filter': bool(
            organisation_user and getattr(organisation_user, 'is_partenaire', False)
        ),
        'regions': regions,
        'districts': districts,
        'communes': communes,
        'ouvrages': ouvrages,
        'district_filter_options': district_filter_options,
        'commune_filter_options': commune_filter_options,
        'ouvrage_filter_options': ouvrage_filter_options,
        'employes_responsables': employes_responsables,
        'employee_points_score': employee_points_score,
        'show_only_score_gap': show_only_score_gap,
        'stats_global': {
            'total_releves': float(total_releves_global),
            'total_diamex': float(total_diamex_global),
            'ecart': float(total_releves_global - total_diamex_global),
            'total_releves_k': total_releves_global_k,
            'total_diamex_k': total_diamex_global_k,
            'ecart_k': ecart_global_k,
            'montant_non_pointe_releve': float(montant_non_pointe_releve),
            'montant_non_pointe_compta': float(montant_non_pointe_compta),
            'montant_non_pointe_releve_k': montant_non_pointe_releve_k,
            'montant_non_pointe_releve_mois_passes': float(montant_non_pointe_releve_mois_passes),
            'montant_non_pointe_releve_mois_passes_k': montant_non_pointe_releve_mois_passes_k,
            'montant_non_pointe_releve_mois_en_cours': float(montant_non_pointe_releve_mois_en_cours),
            'montant_non_pointe_releve_mois_en_cours_k': montant_non_pointe_releve_mois_en_cours_k,
            'montant_non_pointe_compta_k': montant_non_pointe_compta_k,
            'montant_non_pointe_compta_mois_passes': float(montant_non_pointe_compta_mois_passes),
            'montant_non_pointe_compta_mois_passes_k': montant_non_pointe_compta_mois_passes_k,
            'montant_non_pointe_compta_mois_en_cours': float(montant_non_pointe_compta_mois_en_cours),
            'montant_non_pointe_compta_mois_en_cours_k': montant_non_pointe_compta_mois_en_cours_k,
            'nb_lignes_releve_non_pointe': nb_lignes_releve_non_pointe,
            'nb_lignes_releve_non_pointe_mois_passes': nb_lignes_releve_non_pointe_mois_passes,
            'nb_lignes_releve_non_pointe_mois_en_cours': nb_lignes_releve_non_pointe_mois_en_cours,
            'nb_lignes_diamex_non_pointe': nb_lignes_diamex_non_pointe,
            'nb_lignes_diamex_non_pointe_mois_passes': nb_lignes_diamex_non_pointe_mois_passes,
            'nb_lignes_diamex_non_pointe_mois_en_cours': nb_lignes_diamex_non_pointe_mois_en_cours,
            'montant_non_recouvrable': float(montant_non_recouvrable_global),
            'nb_non_recouvrable': nb_non_recouvrable_global,
            'taux_recouvrement': taux_recouvrement_global,
            'encaisse_details': [
                {**d, 'periode': 'passes' if d['mois'] in mois_passes_stats else 'en_cours'}
                for d in encaisse_details_volume
                if d['mois'] in mois_passes_stats or d['mois'] in mois_en_cours_stats
            ],
            'total_encaisse_k': int(total_encaisse_global / 1000),
            'total_encaisse_non_pointe_k': int(total_encaisse_non_pointe_global / 1000),
            'nb_encaisse_non_pointe': nb_encaisse_non_pointe_global,
            'taux_encaisse': taux_encaisse_global,
            'recouvrement_mois_passes': recouvrement_mois_passes,
            'recouvrement_mois_en_cours': recouvrement_mois_en_cours,
            'nb_ouvrages': len(recouvrement_par_ouvrage_annee),
            'nb_ouvrages_recouvrement_100': nb_ouvrages_recouvrement_100,
            'nb_ouvrages_stats': len(ouvrage_ids_stats),
            'nb_points_eau': len(point_eau_ids_stats),
        },
        'points_eau_par_type': points_eau_par_type_list,
        'recouvrement_par_mois': list(recouvrement_par_ouvrage_mois.values()),
        'recouvrement_par_annee': recouvrement_liste,  # Liste triée
        'recouvrement_par_district': recouvrement_par_district,  # Groupé par district
        'taux_mensuels_par_district': taux_mensuels_par_district,  # Nouveau: Taux mensuels par district
        'taux_mensuels_points_export': taux_mensuels_points_export,
        'volume_visible_month_labels': volume_visible_month_labels,
        'delais_paiement': delais_paiement,
        'graphique_mois': {
            'labels': mois_labels,
            'prevus': montants_prevus,
            'payes': montants_payes
        },
        'selected_months': selected_months,
        'anomalies_diamex': anomalies_diamex,
        'transactions_non_appariees': transactions_non_appariees,
        'montant_total_non_appariees': montant_total_non_appariees,
        'graphique_communes': {
            'labels': communes_labels,
            'prevus': communes_prevus,
            'payes': communes_payes,
            'taux': communes_taux
        },
        'is_directeur_poste': bool(getattr(getattr(request.user, 'employe', None), 'is_directeur', False))
    }

    return render(request, 'accounting/dashboard_paiements_volume.html', context)


def _build_ecart_detail_for_ouvrage(request, ouvrage_id):
    """
    Reconstruit, pour UN ouvrage et les memes filtres que le dashboard
    Paiements Volume (annee/trimestre/semestre/region/district/commune/
    employe/organisation), la liste detaillee des releves responsables de
    l'ecart de score (point d'eau dont l'exigible n'est pas entierement
    pointe DiameX). Reprend exactement la meme logique que la section
    "score" de dashboard_paiements_volume pour rester coherente avec le
    tableau filtre par score_ecart=1.
    """
    from decimal import Decimal
    from datetime import datetime
    import pytz
    from apps.billing.models import Releve
    from apps.organization.models import Ouvrage
    from .dashboard_employee_filter import (
        get_water_point_score_gap_ids,
        is_closed_payment_month,
        resolve_dashboard_employee_filter,
    )

    tz_madagascar = pytz.timezone('Indian/Antananarivo')

    filter_annee = request.GET.get('annee', str(datetime.now().year))
    filter_trimestre = request.GET.get('trimestre', 'all')
    filter_semestre = request.GET.get('semestre', '').strip().upper()
    filter_organisation = request.GET.get('organisation', '')
    filter_region = request.GET.get('region', '')
    filter_district = request.GET.get('district', '')
    filter_commune = request.GET.get('commune', '')
    filter_employe = request.GET.get('employe', '')

    try:
        annee = int(filter_annee)
    except (TypeError, ValueError):
        annee = datetime.now().year

    trimestre_to_months = {
        'all': list(range(1, 13)),
        'T1': [1, 2, 3],
        'T2': [1, 2, 3, 4, 5, 6],
        'T3': [1, 2, 3, 4, 5, 6, 7, 8, 9],
        'T4': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    }
    semestre_to_months = {
        'S1': [1, 2, 3, 4, 5, 6],
        'S2': [7, 8, 9, 10, 11, 12],
    }
    if filter_semestre in semestre_to_months:
        selected_months = semestre_to_months[filter_semestre]
    else:
        selected_months = trimestre_to_months.get(filter_trimestre, trimestre_to_months['all'])
    selected_months_set = set(selected_months)

    def _resolve_billing_period(releve_date):
        if not releve_date:
            return None, None
        if releve_date.month == 12:
            return releve_date.year + 1, 1
        return releve_date.year, releve_date.month + 1

    def _pair_key(numero_diamex, base_diamex):
        num = str(numero_diamex or '').strip().lower()
        base = str(base_diamex or '').strip().lower()
        if not num or not base:
            return ''
        return f"{num}||{base}"

    ouvrage = Ouvrage.objects.filter(id=ouvrage_id).first()
    if not ouvrage:
        return None

    scope_info = _resolve_effective_gestionnaire_scope(request.user, filter_organisation)
    effective_gestionnaire_ids = scope_info['effective_gestionnaire_ids']

    releves_qs = Releve.objects.filter(
        montant__isnull=False,
        montant__gt=0,
        point_eau__ouvrage_id=ouvrage_id,
    ).filter(
        Q(datereleve__year__gte=2025) |
        Q(datereleve__year=2024, datereleve__month=12)
    ).exclude(
        remarque__icontains='coupé'
    ).select_related(
        'point_eau',
        'point_eau__type_point_eau',
        'point_eau__ouvrage',
        'point_eau__parcelle',
        'point_eau__parcelle__village',
        'point_eau__parcelle__village__fokontany',
        'point_eau__parcelle__village__fokontany__commune',
        'point_eau__parcelle__village__fokontany__commune__district',
    )

    releves_filtered = []
    for releve in releves_qs:
        if not releve.datereleve:
            continue
        if releve.datereleve.year == annee:
            releves_filtered.append(releve)
            continue
        if releve.datereleve.year == (annee - 1) and releve.datereleve.month == 12:
            releves_filtered.append(releve)
    releves_qs = releves_filtered

    releves_qs = [
        releve for releve in releves_qs
        if _resolve_billing_period(releve.datereleve)[0] == annee
        and _resolve_billing_period(releve.datereleve)[1] in selected_months_set
    ]

    ouvrages_org = _get_responsable_scoped_ouvrage_ids(
        request.user,
        effective_gestionnaire_ids=effective_gestionnaire_ids,
    )
    employes_responsables, ouvrages_org = resolve_dashboard_employee_filter(
        ouvrages_org,
        filter_employe,
    )
    ouvrages_org_ids_str = _normalize_id_set(ouvrages_org)
    if str(ouvrage_id) not in ouvrages_org_ids_str:
        return None

    if filter_district and filter_district != 'all':
        releves_qs = [r for r in releves_qs if r.point_eau and r.point_eau.parcelle and
                      r.point_eau.parcelle.village and r.point_eau.parcelle.village.fokontany and
                      r.point_eau.parcelle.village.fokontany.commune and
                      r.point_eau.parcelle.village.fokontany.commune.district and
                      str(r.point_eau.parcelle.village.fokontany.commune.district.id) == filter_district]

    if filter_region and filter_region != 'all':
        releves_qs = [r for r in releves_qs if r.point_eau and r.point_eau.parcelle and
                      r.point_eau.parcelle.village and r.point_eau.parcelle.village.fokontany and
                      r.point_eau.parcelle.village.fokontany.commune and
                      r.point_eau.parcelle.village.fokontany.commune.district and
                      r.point_eau.parcelle.village.fokontany.commune.district.region and
                      str(r.point_eau.parcelle.village.fokontany.commune.district.region.id) == filter_region]

    if filter_commune and filter_commune != 'all':
        releves_qs = [r for r in releves_qs if r.point_eau and r.point_eau.parcelle and
                      r.point_eau.parcelle.village and r.point_eau.parcelle.village.fokontany and
                      r.point_eau.parcelle.village.fokontany.commune and
                      str(r.point_eau.parcelle.village.fokontany.commune.id) == filter_commune]

    periodes_coupure = _build_coupure_periods_by_point(
        [r.point_eau_id for r in releves_qs if r.point_eau_id]
    )

    score_reference_month = timezone.localdate().replace(day=1)
    payment_totals_by_point = defaultdict(
        lambda: {'expected': Decimal('0'), 'paid': Decimal('0')}
    )
    releves_par_point = defaultdict(list)
    all_point_ids = set()

    for releve in releves_qs:
        point_eau = getattr(releve, 'point_eau', None)
        if not point_eau or _is_releve_non_recouvrable(releve, periodes_coupure):
            continue
        billing_year, billing_month = _resolve_billing_period(releve.datereleve)
        if not billing_year or not billing_month:
            continue
        if not is_closed_payment_month(
            datetime(billing_year, billing_month, 1).date(),
            score_reference_month,
        ):
            continue
        point_eau_id = str(point_eau.id)
        all_point_ids.add(point_eau_id)
        montant_releve = Decimal(str(releve.montant or 0))
        payment_totals_by_point[point_eau_id]['expected'] += montant_releve
        est_pointe = bool(_pair_key(releve.numeroDiameX, releve.baseDiameX))
        if est_pointe:
            payment_totals_by_point[point_eau_id]['paid'] += montant_releve
        releves_par_point[point_eau_id].append({
            'releve': releve,
            'billing_year': billing_year,
            'billing_month': billing_month,
            'est_pointe': est_pointe,
        })

    score_gap_point_ids = get_water_point_score_gap_ids(all_point_ids, payment_totals_by_point)

    points_detail = []
    for point_eau_id in score_gap_point_ids:
        entries = releves_par_point.get(point_eau_id, [])
        if not entries:
            continue
        point_eau = entries[0]['releve'].point_eau
        totals = payment_totals_by_point.get(point_eau_id, {'expected': Decimal('0'), 'paid': Decimal('0')})

        village = None
        commune_nom = ''
        try:
            if point_eau.parcelle and point_eau.parcelle.village:
                village = point_eau.parcelle.village
                if village.fokontany and village.fokontany.commune:
                    commune_nom = village.fokontany.commune.nom_commune
        except Exception:
            pass

        factures = []
        for entry in sorted(entries, key=lambda e: (e['billing_year'], e['billing_month'])):
            releve = entry['releve']
            montant_releve = Decimal(str(releve.montant or 0))
            factures.append({
                'mois': entry['billing_month'],
                'annee': entry['billing_year'],
                'periode_label': f"{entry['billing_month']:02d}/{entry['billing_year']}",
                'date_releve': releve.datereleve.isoformat() if releve.datereleve else None,
                'montant': float(montant_releve),
                'numero_diamex': releve.numeroDiameX or '',
                'base_diamex': releve.baseDiameX or '',
                'est_pointe': entry['est_pointe'],
            })

        points_detail.append({
            'point_eau_id': point_eau_id,
            'idxls': point_eau.idxls or '',
            'nom_abonne': point_eau.nomabonne or '',
            'village_nom': village.nom_village if village else '',
            'commune_nom': commune_nom,
            'montant_exigible': float(totals['expected']),
            'montant_paye': float(totals['paid']),
            'ecart': float(totals['expected'] - totals['paid']),
            'nb_factures_impayees': sum(1 for f in factures if not f['est_pointe']),
            'factures': factures,
        })

    points_detail.sort(key=lambda p: -p['ecart'])

    return {
        'ouvrage_id': str(ouvrage.id),
        'ouvrage_nom': ouvrage.nom_ouvrage,
        'annee': annee,
        'trimestre': filter_trimestre,
        'semestre': filter_semestre,
        'points_detail': points_detail,
        'total_ecart': float(sum(Decimal(str(p['ecart'])) for p in points_detail)),
        'nb_points_en_ecart': len(points_detail),
    }


def api_ouvrage_ecart_detail(request, ouvrage_id):
    """
    API JSON : detail des points d'eau et factures responsables de l'ecart
    de score pour un ouvrage, sur la periode filtree du dashboard Paiements
    Volume (memes parametres GET annee/trimestre/semestre/region/district/
    commune/employe/organisation).
    """
    try:
        detail = _build_ecart_detail_for_ouvrage(request, ouvrage_id)
        if detail is None:
            return JsonResponse({
                'success': False,
                'error': "Ouvrage introuvable ou hors de votre perimetre.",
            }, status=404)
        return JsonResponse({'success': True, **detail})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def dashboard_paiements_volume_ecart_impression(request, ouvrage_id):
    """
    Version imprimable (sobre, papier) de la liste des points d'eau et
    factures en ecart pour un ouvrage, a remettre a un agent terrain.
    """
    from django.utils import timezone as dj_timezone

    detail = _build_ecart_detail_for_ouvrage(request, ouvrage_id)
    if detail is None:
        return render(request, 'accounting/dashboard_paiements_volume_ecart_impression.html', {
            'error': "Ouvrage introuvable ou hors de votre perimetre.",
        }, status=404)

    context = {
        **detail,
        'date_impression': dj_timezone.localtime(dj_timezone.now()),
    }
    return render(request, 'accounting/dashboard_paiements_volume_ecart_impression.html', context)


@login_required
def dashboard_paiements_cartes_sociales(request):
    """
    Dashboard recouvrement cartes sociales.
    - Prévus: consommations cartes sociales (conso_cartes_sociales)
    - Réalisés: écritures comptables compte 748415
    """
    from collections import defaultdict
    from datetime import datetime
    from decimal import Decimal
    from itertools import groupby

    from apps.billing.models import ConsoCarteSociale, ModaliteGestion, PointEau
    from apps.geography.models import Commune, District, Region
    from apps.organization.models import Ouvrage

    filter_annee = request.GET.get('annee', str(datetime.now().year))
    filter_region = request.GET.get('region', '')
    filter_district = request.GET.get('district', '')
    filter_commune = request.GET.get('commune', '')
    filter_ouvrage = request.GET.get('ouvrage', '')

    try:
        annee = int(filter_annee)
    except Exception:
        annee = datetime.now().year

    organisation_user = get_user_organisation(request.user)
    gestionnaire_ids = _get_user_gestionnaire_ids(request.user)
    has_gestionnaire_scope = gestionnaire_ids is None or bool(gestionnaire_ids)

    # Scope ouvrages: ouvrages avec cartes sociales et modalité active.
    ouvrages_scope_ids = _get_responsable_scoped_ouvrage_ids(
        request.user,
        effective_gestionnaire_ids=gestionnaire_ids,
        modalites=['au_volume', 'mixte'],
    )
    ouvrages_scope_qs = Ouvrage.objects.filter(
        id__in=ouvrages_scope_ids,
        cartes_sociales_infra__isnull=False,
        modalites_gestion__date_fin__isnull=True,
        modalites_gestion__modalitepaiement__in=['au_volume', 'mixte']
    ).distinct()

    # Nettoyage automatique global dans le perimetre accessible:
    # une ligne sans consommation ne doit pas rester comme facture carte sociale.
    ConsoCarteSociale.objects.filter(
        carte_sociale__ouvrage_id__in=ouvrages_scope_ids
    ).filter(
        Q(volume_total__isnull=True) | Q(volume_total=0) | Q(quantite_bidons__isnull=True) | Q(quantite_bidons=0)
    ).delete()

    # Construire les options de filtres via les points d'eau liés aux cartes sociales.
    point_eau_scope = PointEau.objects.filter(
        cartes_sociales__ouvrage_id__in=ouvrages_scope_qs.values_list('id', flat=True)
    ).select_related(
        'ouvrage',
        'parcelle__village__fokontany__commune__district__region'
    ).distinct()

    regions_map = {}
    districts_map = {}
    communes_map = {}
    ouvrages_geo = defaultdict(lambda: {'region_ids': set(), 'district_ids': set(), 'commune_ids': set()})

    for pe in point_eau_scope:
        ouvrage = pe.ouvrage
        if not ouvrage:
            continue
        ouvrages_geo[str(ouvrage.id)]  # initialise

        commune = None
        district = None
        region = None
        if pe.parcelle and pe.parcelle.village and pe.parcelle.village.fokontany:
            commune = pe.parcelle.village.fokontany.commune
            if commune and commune.district:
                district = commune.district
                if district.region:
                    region = district.region

        if commune:
            communes_map[str(commune.id)] = commune
            ouvrages_geo[str(ouvrage.id)]['commune_ids'].add(str(commune.id))
        if district:
            districts_map[str(district.id)] = district
            ouvrages_geo[str(ouvrage.id)]['district_ids'].add(str(district.id))
        if region:
            regions_map[str(region.id)] = region
            ouvrages_geo[str(ouvrage.id)]['region_ids'].add(str(region.id))

    # Helper labels géographiques par ouvrage
    def _resolve_region_nom_for_ouvrage(ouvrage_id):
        region_ids = sorted(list(ouvrages_geo.get(ouvrage_id, {}).get('region_ids', set())))
        if not region_ids:
            return 'Sans région'
        region_obj = regions_map.get(region_ids[0])
        return region_obj.nom_region if region_obj else 'Sans région'

    def _resolve_district_nom_for_ouvrage(ouvrage_id):
        district_ids = sorted(list(ouvrages_geo.get(ouvrage_id, {}).get('district_ids', set())))
        if not district_ids:
            return 'Sans district'
        district_obj = districts_map.get(district_ids[0])
        return district_obj.nom_district if district_obj else 'Sans district'

    # Appliquer filtres géographiques sur le scope ouvrages.
    ouvrages_filtres_ids = set(str(o.id) for o in ouvrages_scope_qs)
    if filter_region and filter_region != 'all':
        ouvrages_filtres_ids = {
            oid for oid in ouvrages_filtres_ids
            if filter_region in ouvrages_geo.get(oid, {}).get('region_ids', set())
        }
    if filter_district and filter_district != 'all':
        ouvrages_filtres_ids = {
            oid for oid in ouvrages_filtres_ids
            if filter_district in ouvrages_geo.get(oid, {}).get('district_ids', set())
        }
    if filter_commune and filter_commune != 'all':
        ouvrages_filtres_ids = {
            oid for oid in ouvrages_filtres_ids
            if filter_commune in ouvrages_geo.get(oid, {}).get('commune_ids', set())
        }
    if filter_ouvrage and filter_ouvrage != 'all':
        ouvrages_filtres_ids = {oid for oid in ouvrages_filtres_ids if oid == filter_ouvrage}

    recouvrement_par_ouvrage_mois = {}
    recouvrement_par_ouvrage_annee = {}

    # 1) Prévus depuis conso_carte_sociales (montant_paye).
    consos_qs = ConsoCarteSociale.objects.filter(
        date__year=annee,
        carte_sociale__ouvrage__isnull=False,
        carte_sociale__ouvrage_id__in=list(ouvrages_filtres_ids)
    ).select_related(
        'carte_sociale__ouvrage',
        'carte_sociale__point_eau__parcelle__village__fokontany__commune__district'
    )

    for conso in consos_qs:
        ouvrage = conso.carte_sociale.ouvrage
        if not ouvrage or not conso.date:
            continue

        ouvrage_id = str(ouvrage.id)
        mois = conso.date.month
        montant_prevu = Decimal(str(conso.montant_paye or 0))

        district_nom = _resolve_district_nom_for_ouvrage(ouvrage_id)
        region_nom = _resolve_region_nom_for_ouvrage(ouvrage_id)

        cle_mois = f"{ouvrage_id}_{annee}_{mois:02d}"
        if cle_mois not in recouvrement_par_ouvrage_mois:
            recouvrement_par_ouvrage_mois[cle_mois] = {
                'ouvrage_id': ouvrage_id,
                'ouvrage_nom': ouvrage.nom_ouvrage,
                'annee': annee,
                'mois': mois,
                'total_prevu': Decimal('0'),
                'total_realise': Decimal('0'),
                'nb_consos': 0
            }
        recouvrement_par_ouvrage_mois[cle_mois]['total_prevu'] += montant_prevu
        recouvrement_par_ouvrage_mois[cle_mois]['nb_consos'] += 1

        if ouvrage_id not in recouvrement_par_ouvrage_annee:
            recouvrement_par_ouvrage_annee[ouvrage_id] = {
                'ouvrage_id': ouvrage_id,
                'ouvrage_nom': ouvrage.nom_ouvrage,
                'region_nom': region_nom,
                'district_nom': district_nom,
                'annee': annee,
                'total_prevu': Decimal('0'),
                'total_realise': Decimal('0'),
                'nb_consos': 0
            }
        recouvrement_par_ouvrage_annee[ouvrage_id]['total_prevu'] += montant_prevu
        recouvrement_par_ouvrage_annee[ouvrage_id]['nb_consos'] += 1

    # 2) Réalisés depuis comptabilité (compte 748415), rattachés via extracteur (ouvrage/date dans libellé).
    diamex_748415 = BaseDiameX.objects.filter(compte_code='748415')
    anomalies_diamex = []

    for entry in diamex_748415:
        extraction = extraire_ouvrage_et_mois_generique(entry.description or '', entry.compte_code)
        ouvrage_obj = extraction.get('ouvrage_obj')
        mois = extraction.get('mois')
        annee_entry = extraction.get('annee')

        if not ouvrage_obj or not mois or not annee_entry:
            # Hors scope si pas de rattachement exploitable.
            continue
        if annee_entry != annee:
            continue

        ouvrage_id = str(ouvrage_obj.id)
        if ouvrage_id not in ouvrages_filtres_ids:
            continue

        montant_realise = Decimal(str(entry.montant_in or 0))
        cle_mois = f"{ouvrage_id}_{annee}_{mois:02d}"

        if cle_mois not in recouvrement_par_ouvrage_mois:
            recouvrement_par_ouvrage_mois[cle_mois] = {
                'ouvrage_id': ouvrage_id,
                'ouvrage_nom': ouvrage_obj.nom_ouvrage,
                'annee': annee,
                'mois': mois,
                'total_prevu': Decimal('0'),
                'total_realise': Decimal('0'),
                'nb_consos': 0
            }
        recouvrement_par_ouvrage_mois[cle_mois]['total_realise'] += montant_realise

        if ouvrage_id not in recouvrement_par_ouvrage_annee:
            recouvrement_par_ouvrage_annee[ouvrage_id] = {
                'ouvrage_id': ouvrage_id,
                'ouvrage_nom': ouvrage_obj.nom_ouvrage,
                'region_nom': _resolve_region_nom_for_ouvrage(ouvrage_id),
                'district_nom': 'Sans district',
                'annee': annee,
                'total_prevu': Decimal('0'),
                'total_realise': Decimal('0'),
                'nb_consos': 0
            }
        recouvrement_par_ouvrage_annee[ouvrage_id]['total_realise'] += montant_realise

    # KPIs par ouvrage + taux.
    for ouvrage_id, data in recouvrement_par_ouvrage_annee.items():
        total_prevu = Decimal(str(data.get('total_prevu') or 0))
        total_realise = Decimal(str(data.get('total_realise') or 0))
        nb_consos = int(data.get('nb_consos') or 0)

        data['ecart'] = total_prevu - total_realise
        data['taux'] = int((total_realise / total_prevu) * 100) if total_prevu > 0 else 0
        data['montant_moyen_par_conso'] = (total_prevu / Decimal(nb_consos)) if nb_consos > 0 else Decimal('0')

    # Nb cartes sociales par ouvrage
    from apps.infrastructure.models import CarteSociale
    nb_cartes_map = {
        str(item['ouvrage']): int(item['nb'] or 0)
        for item in CarteSociale.objects.filter(
            ouvrage_id__in=list(ouvrages_filtres_ids),
            statut='active'
        ).values('ouvrage').annotate(nb=Count('id'))
    }

    for ouvrage_id, data in recouvrement_par_ouvrage_annee.items():
        data['nb_cartes_sociales'] = int(nb_cartes_map.get(ouvrage_id, 0))
        if not data.get('region_nom'):
            data['region_nom'] = _resolve_region_nom_for_ouvrage(ouvrage_id)
        if not data.get('district_nom') or data.get('district_nom') == 'Sans district':
            data['district_nom'] = _resolve_district_nom_for_ouvrage(ouvrage_id)

    recouvrement_liste = sorted(
        recouvrement_par_ouvrage_annee.values(),
        key=lambda x: (x.get('region_nom', 'Sans région'), x['district_nom'], -x['taux'], x['ouvrage_nom'])
    )

    recouvrement_par_region_district = {}
    for region_nom, region_items in groupby(recouvrement_liste, key=lambda x: x.get('region_nom', 'Sans région')):
        region_list = list(region_items)
        recouvrement_par_region_district[region_nom] = {}
        for district_nom, district_items in groupby(region_list, key=lambda x: x['district_nom']):
            recouvrement_par_region_district[region_nom][district_nom] = list(district_items)

    # Taux mensuels par ouvrage.
    taux_mensuels_par_ouvrage = {}
    for data in recouvrement_par_ouvrage_mois.values():
        ouvrage_id = data['ouvrage_id']
        mois = data['mois']
        total_prevu = Decimal(str(data.get('total_prevu') or 0))
        total_realise = Decimal(str(data.get('total_realise') or 0))
        taux = int((total_realise / total_prevu) * 100) if total_prevu > 0 else 0

        if ouvrage_id not in taux_mensuels_par_ouvrage:
            taux_mensuels_par_ouvrage[ouvrage_id] = {
                'ouvrage_id': ouvrage_id,
                'ouvrage_nom': data['ouvrage_nom'],
                'taux_par_mois': {}
            }

        taux_mensuels_par_ouvrage[ouvrage_id]['taux_par_mois'][mois] = {
            'taux': taux,
            'total_prevu': float(total_prevu),
            'total_realise': float(total_realise),
            'ecart': float(total_prevu - total_realise),
            'nb_consos': int(data.get('nb_consos') or 0),
        }

    taux_mensuels_par_region_district = {}
    for ouvrage_id, taux_data in taux_mensuels_par_ouvrage.items():
        region_nom = recouvrement_par_ouvrage_annee.get(ouvrage_id, {}).get('region_nom', _resolve_region_nom_for_ouvrage(ouvrage_id))
        district_nom = recouvrement_par_ouvrage_annee.get(ouvrage_id, {}).get('district_nom', _resolve_district_nom_for_ouvrage(ouvrage_id))
        if region_nom not in taux_mensuels_par_region_district:
            taux_mensuels_par_region_district[region_nom] = {}
        taux_mensuels_par_region_district[region_nom].setdefault(district_nom, []).append(taux_data)

    cartes_visible_month_labels = [
        {'number': 1, 'label': 'Jan'},
        {'number': 2, 'label': 'Fev'},
        {'number': 3, 'label': 'Mar'},
        {'number': 4, 'label': 'Avr'},
        {'number': 5, 'label': 'Mai'},
        {'number': 6, 'label': 'Juin'},
        {'number': 7, 'label': 'Juil'},
        {'number': 8, 'label': 'Aou'},
        {'number': 9, 'label': 'Sep'},
        {'number': 10, 'label': 'Oct'},
        {'number': 11, 'label': 'Nov'},
        {'number': 12, 'label': 'Dec'},
    ]
    visible_cartes_month_numbers = [
        month['number']
        for month in cartes_visible_month_labels
        if any(
            ouvrage_data['taux_par_mois'].get(month['number'])
            and (
                Decimal(str(ouvrage_data['taux_par_mois'][month['number']].get('total_prevu') or 0)) > 0
                or Decimal(str(ouvrage_data['taux_par_mois'][month['number']].get('total_realise') or 0)) > 0
                or Decimal(str(ouvrage_data['taux_par_mois'][month['number']].get('ecart') or 0)) != 0
            )
            for ouvrage_data in taux_mensuels_par_ouvrage.values()
        )
    ]
    cartes_visible_month_labels = [
        month
        for month in cartes_visible_month_labels
        if month['number'] in visible_cartes_month_numbers
    ]

    for region_nom in taux_mensuels_par_region_district:
        for district_nom in taux_mensuels_par_region_district[region_nom]:
            taux_mensuels_par_region_district[region_nom][district_nom].sort(key=lambda x: x['ouvrage_nom'])
            for ouvrage_data in taux_mensuels_par_region_district[region_nom][district_nom]:
                ouvrage_data['taux_mois_list'] = [ouvrage_data['taux_par_mois'].get(mois) for mois in range(1, 13)]
                ouvrage_data['visible_months'] = [
                    {
                        'number': month['number'],
                        'label': month['label'],
                        'data': ouvrage_data['taux_par_mois'].get(month['number']),
                    }
                    for month in cartes_visible_month_labels
                ]

    total_prevu_global = sum((d['total_prevu'] for d in recouvrement_par_ouvrage_annee.values()), Decimal('0'))
    total_realise_global = sum((d['total_realise'] for d in recouvrement_par_ouvrage_annee.values()), Decimal('0'))
    taux_global = int((total_realise_global / total_prevu_global) * 100) if total_prevu_global > 0 else 0

    # Options filtres (avec dépendances simples).
    regions = sorted(regions_map.values(), key=lambda r: r.nom_region)

    districts = sorted(
        [
            d for d in districts_map.values()
            if not filter_region or filter_region == 'all' or str(d.region_id) == filter_region
        ],
        key=lambda d: d.nom_district
    )

    communes = sorted(
        [
            c for c in communes_map.values()
            if (
                (not filter_district or filter_district == 'all' or str(c.district_id) == filter_district) and
                (
                    not filter_region or filter_region == 'all' or
                    str(c.district.region_id) == filter_region
                )
            )
        ],
        key=lambda c: c.nom_commune
    )

    ouvrages_all = Ouvrage.objects.filter(id__in=list(ouvrages_scope_qs.values_list('id', flat=True))).order_by('nom_ouvrage')
    ouvrages = []
    for ouvrage in ouvrages_all:
        geo = ouvrages_geo.get(str(ouvrage.id), {'region_ids': set(), 'district_ids': set(), 'commune_ids': set()})
        if filter_region and filter_region != 'all' and filter_region not in geo['region_ids']:
            continue
        if filter_district and filter_district != 'all' and filter_district not in geo['district_ids']:
            continue
        if filter_commune and filter_commune != 'all' and filter_commune not in geo['commune_ids']:
            continue
        ouvrages.append(ouvrage)

    context = {
        'annee': annee,
        'filter_region': filter_region,
        'filter_district': filter_district,
        'filter_commune': filter_commune,
        'filter_ouvrage': filter_ouvrage,
        'regions': regions,
        'districts': districts,
        'communes': communes,
        'ouvrages': ouvrages,
        'stats_global': {
            'total_prevu': float(total_prevu_global),
            'total_realise': float(total_realise_global),
            'ecart': float(total_prevu_global - total_realise_global),
            'taux_recouvrement': taux_global,
            'nb_ouvrages': len(recouvrement_par_ouvrage_annee),
        },
        'recouvrement_par_annee': recouvrement_liste,
        'recouvrement_par_region_district': recouvrement_par_region_district,
        'taux_mensuels_par_region_district': taux_mensuels_par_region_district,
        'cartes_visible_month_labels': cartes_visible_month_labels,
        'anomalies_diamex': anomalies_diamex,
    }
    return render(request, 'accounting/dashboard_paiements_cartes_sociales.html', context)


def dashboard_paiements_volume_impression(request):
    """
    Version imprimable du dashboard paiements au volume.
    Réutilise la logique de la vue principale mais avec un template simplifié.
    """
    # Réutiliser la mème logique que dashboard_paiements_volume
    # mais retourner un template différent
    from django.db.models import Sum, Count, Q
    from decimal import Decimal
    from datetime import datetime
    import pytz
    from apps.billing.models import Releve
    from apps.organization.models import Ouvrage
    from apps.geography.models import District, Commune, Region
    from .dashboard_employee_filter import (
        build_employee_geo_filter_options,
        resolve_dashboard_employee_filter,
    )

    # Timezone Madagascar
    tz_madagascar = pytz.timezone('Indian/Antananarivo')

    # Filtres (mèmes que la vue principale)
    print_mode = request.GET.get('mode', '').strip()
    show_non_pointe_print = request.GET.get('show_non_pointe_print', '').strip()
    filter_annee = request.GET.get('annee', str(datetime.now().year))
    filter_organisation = request.GET.get('organisation', '')
    filter_region = request.GET.get('region', '')
    filter_district = request.GET.get('district', '')
    filter_commune = request.GET.get('commune', '')
    filter_ouvrage = request.GET.get('ouvrage', '')
    filter_employe = request.GET.get('employe', '')

    try:
        annee = int(filter_annee)
    except:
        annee = datetime.now().year

    def _resolve_billing_period(releve_date):
        if not releve_date:
            return None, None
        if releve_date.month == 12:
            return releve_date.year + 1, 1
        return releve_date.year, releve_date.month + 1

    # Scope gestionnaire de l'utilisateur connecté + filtre organisation optionnel
    scope_info = _resolve_effective_gestionnaire_scope(request.user, filter_organisation)
    organisation_user = scope_info['organisation_user']
    accessible_gestionnaire_ids = scope_info['accessible_gestionnaire_ids']
    effective_gestionnaire_ids = scope_info['effective_gestionnaire_ids']
    filter_organisation = scope_info['selected_organisation_id']
    has_gestionnaire_scope = effective_gestionnaire_ids is None or bool(effective_gestionnaire_ids)
    organisations = _get_gestionnaire_organisations_for_filter(accessible_gestionnaire_ids)

    # Récupérer les relevés (mème logique que vue principale)
    releves_qs = Releve.objects.filter(
        montant__isnull=False,
        montant__gt=0,
        point_eau__ouvrage__isnull=False
    ).filter(
        Q(datereleve__year__gte=2025) |
        Q(datereleve__year=2024, datereleve__month=12)
    ).exclude(
        remarque__icontains='coupé'
    ).select_related(
        'point_eau',
        'point_eau__ouvrage',
        'point_eau__ouvrage__type_ouvrage',
        'point_eau__parcelle',
        'point_eau__parcelle__village',
        'point_eau__parcelle__village__fokontany',
        'point_eau__parcelle__village__fokontany__commune',
        'point_eau__parcelle__village__fokontany__commune__district',
        'point_eau__parcelle__village__fokontany__commune__district__region'
    )

    # Filtrer par année
    if annee:
        releves_filtered = []
        for releve in releves_qs:
            if releve.datereleve and releve.datereleve.year == annee:
                releves_filtered.append(releve)
        releves_qs = releves_filtered

    # Filtrer par scope gestionnaire
    ouvrages_org = _get_responsable_scoped_ouvrage_ids(
        request.user,
        effective_gestionnaire_ids=effective_gestionnaire_ids,
    )
    ouvrages_org_filter_scope = set(ouvrages_org)
    employes_responsables, ouvrages_org = resolve_dashboard_employee_filter(
        ouvrages_org,
        filter_employe,
    )
    if filter_employe and not any(
        str(option.get('id', '')) == str(filter_employe)
        for option in employes_responsables
    ):
        filter_employe = ''
    employe_nom = next((
        option.get('label', '')
        for option in employes_responsables
        if str(option.get('id', '')) == str(filter_employe)
    ), '')
    ouvrages_org_ids_str = _normalize_id_set(ouvrages_org)
    releves_qs = [
        r for r in releves_qs
        if r.point_eau and r.point_eau.ouvrage and str(r.point_eau.ouvrage.id) in ouvrages_org_ids_str
    ]

    # Appliquer filtres géographiques et ouvrage
    if filter_region and filter_region != 'all':
        releves_qs = [r for r in releves_qs if r.point_eau and r.point_eau.parcelle and
                      r.point_eau.parcelle.village and r.point_eau.parcelle.village.fokontany and
                      r.point_eau.parcelle.village.fokontany.commune and
                      r.point_eau.parcelle.village.fokontany.commune.district and
                      r.point_eau.parcelle.village.fokontany.commune.district.region and
                      str(r.point_eau.parcelle.village.fokontany.commune.district.region.id) == filter_region]

    if filter_district and filter_district != 'all':
        releves_qs = [r for r in releves_qs if r.point_eau and r.point_eau.parcelle and
                      r.point_eau.parcelle.village and r.point_eau.parcelle.village.fokontany and
                      r.point_eau.parcelle.village.fokontany.commune and
                      r.point_eau.parcelle.village.fokontany.commune.district and
                      str(r.point_eau.parcelle.village.fokontany.commune.district.id) == filter_district]

    if filter_commune and filter_commune != 'all':
        releves_qs = [r for r in releves_qs if r.point_eau and r.point_eau.parcelle and
                      r.point_eau.parcelle.village and r.point_eau.parcelle.village.fokontany and
                      r.point_eau.parcelle.village.fokontany.commune and
                      str(r.point_eau.parcelle.village.fokontany.commune.id) == filter_commune]

    if filter_ouvrage and filter_ouvrage != 'all':
        releves_qs = [r for r in releves_qs if r.point_eau and r.point_eau.ouvrage and
                      str(r.point_eau.ouvrage.id) == filter_ouvrage]

    # Exclure les relevés pendant les coupures d'eau.
    point_eau_ids = {str(r.point_eau.id) for r in releves_qs if r.point_eau}
    periodes_coupure = _build_coupure_periods_by_point(point_eau_ids)
    releves_qs = [
        r for r in releves_qs
        if not _is_releve_during_coupure(r, periodes_coupure, check_facturation_month=True)
    ]

    # Grouper par ouvrage
    from itertools import groupby
    from dateutil.relativedelta import relativedelta

    recouvrement_par_ouvrage_annee = {}

    for releve in releves_qs:
        if not releve.point_eau or not releve.point_eau.ouvrage:
            continue

        ouvrage = releve.point_eau.ouvrage
        ouvrage_id = ouvrage.id
        ouvrage_nom = ouvrage.nom_ouvrage

        # Récupérer le district
        district_nom = 'Sans district'
        if releve.point_eau.parcelle and releve.point_eau.parcelle.village:
            village = releve.point_eau.parcelle.village
            if village.fokontany and village.fokontany.commune and village.fokontany.commune.district:
                district_nom = village.fokontany.commune.district.nom_district

        if ouvrage_id not in recouvrement_par_ouvrage_annee:
            recouvrement_par_ouvrage_annee[ouvrage_id] = {
                'ouvrage_id': ouvrage_id,
                'ouvrage_nom': ouvrage_nom,
                'district_nom': district_nom,
                'total_releves': Decimal('0'),
                'total_diamex': Decimal('0'),
                'ecart': Decimal('0'),
                'taux': 0,
                'nb_releves': 0,
                'nb_payes': 0
            }

        montant = Decimal(str(releve.montant)) if releve.montant else Decimal('0')
        recouvrement_par_ouvrage_annee[ouvrage_id]['total_releves'] += montant
        recouvrement_par_ouvrage_annee[ouvrage_id]['nb_releves'] += 1

        if releve.numeroDiameX:
            recouvrement_par_ouvrage_annee[ouvrage_id]['total_diamex'] += montant
            recouvrement_par_ouvrage_annee[ouvrage_id]['nb_payes'] += 1

    # Calculer écarts et taux
    for data in recouvrement_par_ouvrage_annee.values():
        data['ecart'] = data['total_releves'] - data['total_diamex']
        data['taux'] = int((data['total_diamex'] / data['total_releves'] * 100) if data['total_releves'] > 0 else 0)

    # Trier par district puis par taux décroissant
    recouvrement_liste = sorted(
        recouvrement_par_ouvrage_annee.values(),
        key=lambda x: (x['district_nom'], -x['taux'])
    )

    # Grouper par district
    recouvrement_par_district = {}
    for district_nom, items in groupby(recouvrement_liste, key=lambda x: x['district_nom']):
        recouvrement_par_district[district_nom] = list(items)

    # Statistiques globales
    total_releves_global = sum(d['total_releves'] for d in recouvrement_par_ouvrage_annee.values())
    total_diamex_global = sum(d['total_diamex'] for d in recouvrement_par_ouvrage_annee.values())
    taux_recouvrement_global = int((total_diamex_global / total_releves_global * 100) if total_releves_global > 0 else 0)

    # Options complètes pour la cascade Employé -> Région -> District -> Commune -> Ouvrage.
    regions, districts, communes, ouvrages = build_employee_geo_filter_options(
        ouvrages_org_filter_scope,
        employes_responsables,
        require_forfait_tariff=False,
    )

    organisation_label = 'Toutes'
    if filter_organisation:
        selected_organisation = organisations.filter(id=filter_organisation).first()
        if selected_organisation:
            organisation_label = selected_organisation.nom_organisation
    elif organisation_user and getattr(organisation_user, 'is_gestionnaire', False):
        organisation_label = organisation_user.nom_organisation
    elif organisation_user and getattr(organisation_user, 'is_partenaire', False):
        organisation_label = 'Toutes (organisations affectees)'

    current_madagascar_date = datetime.now(tz_madagascar)
    if annee < current_madagascar_date.year:
        allowed_non_pointe_month_numbers = list(range(1, 13))
    elif annee == current_madagascar_date.year:
        allowed_non_pointe_month_numbers = list(range(1, current_madagascar_date.month))
    else:
        allowed_non_pointe_month_numbers = []

    allowed_non_pointe_months_set = set(allowed_non_pointe_month_numbers)
    non_pointe_print_months = [
        {'number': month, 'label': datetime(annee, month, 1).strftime('%b')}
        for month in allowed_non_pointe_month_numbers
    ]
    non_pointe_preview_count = 0
    non_pointe_preview_total = Decimal('0')
    non_pointe_preview_abonnes = 0
    non_pointe_print_rows = []
    non_pointe_print_totals = {month: Decimal('0') for month in allowed_non_pointe_month_numbers}
    selected_ouvrage_obj = None

    if print_mode == 'non_pointe_releves' and filter_ouvrage and filter_ouvrage != 'all':
        # ``build_employee_geo_filter_options`` retourne une liste enrichie afin
        # d'alimenter la cascade côté navigateur, et non plus un QuerySet.
        selected_ouvrage_obj = next((
            ouvrage
            for ouvrage in ouvrages
            if str(ouvrage.id) == str(filter_ouvrage)
        ), None)
        if selected_ouvrage_obj:
            releves_non_pointes_qs = Releve.objects.filter(
                montant__isnull=False,
                montant__gt=0,
                point_eau__ouvrage_id=selected_ouvrage_obj.id
            ).filter(
                Q(datereleve__year=annee) |
                Q(datereleve__year=annee - 1, datereleve__month=12)
            ).exclude(
                remarque__icontains='coupé'
            ).select_related(
                'point_eau'
            )

            releves_non_pointes = list(releves_non_pointes_qs)
            point_eau_ids_non_pointes = {
                str(r.point_eau.id) for r in releves_non_pointes if r.point_eau
            }
            periodes_coupure_non_pointes = _build_coupure_periods_by_point(point_eau_ids_non_pointes)

            rows_map = {}
            for releve in releves_non_pointes:
                if not releve.point_eau:
                    continue
                if _is_releve_during_coupure(releve, periodes_coupure_non_pointes, check_facturation_month=True):
                    continue

                annee_cible, mois_cible = _resolve_billing_period(releve.datereleve)
                if annee_cible != annee or not mois_cible or mois_cible not in allowed_non_pointe_months_set:
                    continue

                numero_diamex = (releve.numeroDiameX or '').strip()
                base_diamex = (releve.baseDiameX or '').strip()
                if numero_diamex and base_diamex:
                    continue

                montant = Decimal(str(releve.montant or 0))
                point_eau = releve.point_eau
                row_key = str(point_eau.id)
                idxls = (point_eau.idxls or '').strip() or '-'
                nom_abonne = (point_eau.nomabonne or '').strip() or (releve.abonne or '').strip() or '-'

                if row_key not in rows_map:
                    rows_map[row_key] = {
                        'point_eau_id': row_key,
                        'idxls': idxls,
                        'idxls_num': int(idxls) if idxls.isdigit() else 999999,
                        'nom_abonne': nom_abonne,
                        'months': {month: Decimal('0') for month in allowed_non_pointe_month_numbers},
                        'total': Decimal('0'),
                        'nb_releves': 0,
                    }

                rows_map[row_key]['months'][mois_cible] += montant
                rows_map[row_key]['total'] += montant
                rows_map[row_key]['nb_releves'] += 1
                non_pointe_print_totals[mois_cible] += montant
                non_pointe_preview_count += 1
                non_pointe_preview_total += montant

            non_pointe_print_rows = sorted(
                rows_map.values(),
                key=lambda item: (item['idxls_num'], item['nom_abonne'].lower())
            )
            non_pointe_preview_abonnes = len(non_pointe_print_rows)

    context = {
        'print_mode': print_mode,
        'show_non_pointe_print': show_non_pointe_print,
        'annee': annee,
        'filter_organisation': filter_organisation,
        'filter_region': filter_region,
        'filter_district': filter_district,
        'filter_commune': filter_commune,
        'filter_ouvrage': filter_ouvrage,
        'filter_employe': filter_employe,
        'employe_nom': employe_nom,
        'organisations': organisations,
        'show_organisation_filter': bool(
            organisation_user and getattr(organisation_user, 'is_partenaire', False)
        ),
        'regions': regions,
        'districts': districts,
        'communes': communes,
        'ouvrages': ouvrages,
        'employes_responsables': employes_responsables,
        'date_impression': datetime.now(tz_madagascar),
        'organisation': organisation_label,
        'stats_global': {
            'total_releves': float(total_releves_global),
            'total_diamex': float(total_diamex_global),
            'ecart': float(total_releves_global - total_diamex_global),
            'taux_recouvrement': taux_recouvrement_global,
            'nb_ouvrages': len(recouvrement_par_ouvrage_annee)
        },
        'recouvrement_par_district': recouvrement_par_district,
        'selected_ouvrage_obj': selected_ouvrage_obj,
        'non_pointe_print_months': non_pointe_print_months,
        'non_pointe_preview_count': non_pointe_preview_count,
        'non_pointe_preview_total': float(non_pointe_preview_total),
        'non_pointe_preview_abonnes': non_pointe_preview_abonnes,
        'non_pointe_print_rows': non_pointe_print_rows,
        'non_pointe_print_totals': non_pointe_print_totals,
    }

    return render(request, 'accounting/dashboard_paiements_volume_impression.html', context)


@login_required
def api_paiements_volume_communes_summary(request):
    """API pour lister le recouvrement au volume par commune (groupé par région/district)"""
    if request.method != 'GET':
        from django.http import JsonResponse
        return JsonResponse({'success': False, 'error': 'Méthode non autorisée'}, status=405)

    try:
        from django.http import JsonResponse
        from django.db.models import Q
        from decimal import Decimal
        from datetime import datetime
        from apps.billing.models import Releve
        from .models import BaseDiameX

        # Filtres
        filter_annee = request.GET.get('annee', str(datetime.now().year))
        filter_organisation = request.GET.get('organisation', '')
        filter_region = request.GET.get('region', '')
        filter_district = request.GET.get('district', '')
        filter_commune = request.GET.get('commune', '')
        filter_ouvrage = request.GET.get('ouvrage', '')

        try:
            annee = int(filter_annee)
        except Exception:
            annee = datetime.now().year

        # Scope gestionnaire de l'utilisateur + filtre organisation optionnel
        scope_info = _resolve_effective_gestionnaire_scope(request.user, filter_organisation)
        effective_gestionnaire_ids = scope_info['effective_gestionnaire_ids']

        # Releves de base (meme logique que dashboard_paiements_volume)
        releves_qs = Releve.objects.filter(
            montant__isnull=False,
            montant__gt=0,
            point_eau__ouvrage__isnull=False
        ).filter(
            Q(datereleve__year__gte=2025) |
            Q(datereleve__year=2024, datereleve__month=12)
        ).exclude(
            remarque__icontains='coupé'
        ).select_related(
            'point_eau',
            'point_eau__ouvrage',
            'point_eau__ouvrage__type_ouvrage',
            'point_eau__parcelle',
            'point_eau__parcelle__village',
            'point_eau__parcelle__village__fokontany',
            'point_eau__parcelle__village__fokontany__commune',
            'point_eau__parcelle__village__fokontany__commune__district',
            'point_eau__parcelle__village__fokontany__commune__district__region'
        )

        # Filtrer par année (inclure décembre N-1 reporté sur janvier, comme la vue Ouvrages)
        if annee:
            releves_filtered = []
            for releve in releves_qs:
                if not releve.datereleve:
                    continue
                if releve.datereleve.year == annee:
                    releves_filtered.append(releve)
                    continue
                if releve.datereleve.year == (annee - 1) and releve.datereleve.month == 12:
                    releves_filtered.append(releve)
            releves_qs = releves_filtered

        # Filtrer par scope gestionnaire (ModaliteGestion active)
        ouvrages_org = _get_responsable_scoped_ouvrage_ids(
            request.user,
            effective_gestionnaire_ids=effective_gestionnaire_ids,
        )
        ouvrages_org_ids_str = _normalize_id_set(ouvrages_org)
        releves_qs = [
            r for r in releves_qs
            if r.point_eau and r.point_eau.ouvrage and str(r.point_eau.ouvrage.id) in ouvrages_org_ids_str
        ]

        # Filtre district
        if filter_district and filter_district != 'all':
            releves_qs = [
                r for r in releves_qs
                if r.point_eau and r.point_eau.parcelle and r.point_eau.parcelle.village and
                r.point_eau.parcelle.village.fokontany and r.point_eau.parcelle.village.fokontany.commune and
                r.point_eau.parcelle.village.fokontany.commune.district and
                str(r.point_eau.parcelle.village.fokontany.commune.district.id) == filter_district
            ]
            
        # Filtre region
        if filter_region and filter_region != 'all':
            releves_qs = [
                r for r in releves_qs
                if r.point_eau and r.point_eau.parcelle and r.point_eau.parcelle.village and
                r.point_eau.parcelle.village.fokontany and r.point_eau.parcelle.village.fokontany.commune and
                r.point_eau.parcelle.village.fokontany.commune.district and
                r.point_eau.parcelle.village.fokontany.commune.district.region and
                str(r.point_eau.parcelle.village.fokontany.commune.district.region.id) == filter_region
            ]

        # Filtre commune
        if filter_commune and filter_commune != 'all':
            releves_qs = [
                r for r in releves_qs
                if r.point_eau and r.point_eau.parcelle and r.point_eau.parcelle.village and
                r.point_eau.parcelle.village.fokontany and r.point_eau.parcelle.village.fokontany.commune and
                str(r.point_eau.parcelle.village.fokontany.commune.id) == filter_commune
            ]

        # Filtre ouvrage
        if filter_ouvrage and filter_ouvrage != 'all':
            releves_qs = [
                r for r in releves_qs
                if r.point_eau and r.point_eau.ouvrage and str(r.point_eau.ouvrage.id) == filter_ouvrage
            ]

        # Exclure les relevés pendant les coupures d'eau (même logique que le dashboard)
        point_eau_ids = {str(r.point_eau.id) for r in releves_qs if r.point_eau}
        periodes_coupure = _build_coupure_periods_by_point(point_eau_ids)
        releves_qs = [
            r for r in releves_qs
            if not _is_releve_during_coupure(r, periodes_coupure, check_facturation_month=True)
        ]

        # Préparer les métadonnées géographiques par ouvrage (sur la base filtrée)
        ouvrages_meta = {}
        ouvrages_filtres_ids = set()
        for releve in releves_qs:
            if not releve.point_eau or not releve.point_eau.ouvrage:
                continue

            ouvrage_id = str(releve.point_eau.ouvrage.id)
            ouvrages_filtres_ids.add(ouvrage_id)

            if ouvrage_id in ouvrages_meta:
                continue

            commune = None
            district = None
            region = None
            if (
                releve.point_eau.parcelle and
                releve.point_eau.parcelle.village and
                releve.point_eau.parcelle.village.fokontany
            ):
                commune = releve.point_eau.parcelle.village.fokontany.commune
                if commune and commune.district:
                    district = commune.district
                    if district.region:
                        region = district.region

            commune_id = str(commune.id) if commune else None
            commune_nom = commune.nom_commune if commune else 'Non defini'
            district_nom = district.nom_district if district else 'Non defini'
            region_nom = region.nom_region if region else 'Non defini'

            ouvrages_meta[ouvrage_id] = {
                'commune_id': commune_id,
                'commune': commune_nom,
                'district': district_nom,
                'region': region_nom
            }

        # 1) Total relevés par ouvrage (avec décalage de mois identique à la vue Ouvrages)
        releves_par_ouvrage = {}
        for releve in releves_qs:
            if not releve.point_eau or not releve.point_eau.ouvrage or not releve.datereleve:
                continue

            mois = releve.datereleve.month
            if mois == 12:
                annee_cible = releve.datereleve.year + 1
            else:
                annee_cible = releve.datereleve.year

            if annee_cible != annee:
                continue

            ouvrage_id = str(releve.point_eau.ouvrage.id)
            if ouvrage_id not in releves_par_ouvrage:
                releves_par_ouvrage[ouvrage_id] = {
                    'total_releves': Decimal('0'),
                    'nb_releves': 0
                }

            row = releves_par_ouvrage[ouvrage_id]
            montant = Decimal(str(releve.montant)) if releve.montant else Decimal('0')
            row['nb_releves'] += 1
            row['total_releves'] += montant

        # 2) Total paiements DiameX par ouvrage (même extraction que la vue Ouvrages)
        diamex_par_ouvrage = {}
        # Important: ne pas filtrer par date_rec (date de paiement).
        # Le rattachement annuel se fait via la date de facture extraite du libellé.
        diamex_707401 = BaseDiameX.objects.filter(
            compte_code='707401'
        )

        for entry in diamex_707401:
            segments = []
            if entry.description and ';' in entry.description:
                segments = diviser_paiement_volume_multi(
                    entry.description,
                    entry.compte_code,
                    entry.montant_in if entry.montant_in else 0
                )

            if segments:
                for segment in segments:
                    extraction = segment['extraction']
                    if not extraction['ouvrage_obj'] or not extraction['mois'] or extraction['annee'] != annee:
                        continue

                    ouvrage_id = str(extraction['ouvrage_obj'].id)
                    if ouvrage_id not in ouvrages_filtres_ids:
                        continue

                    if ouvrage_id not in diamex_par_ouvrage:
                        diamex_par_ouvrage[ouvrage_id] = Decimal('0')
                    diamex_par_ouvrage[ouvrage_id] += Decimal(str(segment['montant']))
            else:
                extraction = extraire_ouvrage_et_mois_generique(entry.description or '', entry.compte_code)
                if not extraction['ouvrage_obj'] or not extraction['mois'] or extraction['annee'] != annee:
                    continue

                ouvrage_id = str(extraction['ouvrage_obj'].id)
                if ouvrage_id not in ouvrages_filtres_ids:
                    continue

                if ouvrage_id not in diamex_par_ouvrage:
                    diamex_par_ouvrage[ouvrage_id] = Decimal('0')
                diamex_par_ouvrage[ouvrage_id] += Decimal(str(entry.montant_in)) if entry.montant_in else Decimal('0')

        # 3) Agrégation finale par commune
        communes_data = {}
        all_ouvrage_ids = set(releves_par_ouvrage.keys()) | set(diamex_par_ouvrage.keys())
        for ouvrage_id in all_ouvrage_ids:
            meta = ouvrages_meta.get(ouvrage_id, {
                'commune_id': None,
                'commune': 'Non defini',
                'district': 'Non defini',
                'region': 'Non defini'
            })
            commune_key = meta['commune_id'] if meta['commune_id'] else f"none-{meta['commune']}"

            if commune_key not in communes_data:
                communes_data[commune_key] = {
                    'commune_id': meta['commune_id'],
                    'commune': meta['commune'],
                    'district': meta['district'],
                    'region': meta['region'],
                    'nb_releves': 0,
                    'total_releves': Decimal('0'),
                    'total_diamex': Decimal('0'),
                    'ouvrages': set()
                }

            commune_row = communes_data[commune_key]
            releve_data = releves_par_ouvrage.get(ouvrage_id)
            if releve_data:
                commune_row['nb_releves'] += releve_data['nb_releves']
                commune_row['total_releves'] += releve_data['total_releves']

            commune_row['total_diamex'] += diamex_par_ouvrage.get(ouvrage_id, Decimal('0'))
            commune_row['ouvrages'].add(ouvrage_id)

        communes_list = []
        for row in communes_data.values():
            total_releves = row['total_releves']
            total_diamex = row['total_diamex']
            taux = int((total_diamex / total_releves) * 100) if total_releves > 0 else 0
            ecart = total_releves - total_diamex

            communes_list.append({
                'commune_id': row['commune_id'],
                'commune': row['commune'],
                'district': row['district'],
                'region': row['region'],
                'nb_ouvrages': len(row['ouvrages']),
                'nb_releves': row['nb_releves'],
                'total_releves': float(total_releves),
                'total_diamex': float(total_diamex),
                'ecart': float(ecart),
                'taux': taux
            })

        communes_list.sort(
            key=lambda item: (item.get('region') or '', item.get('district') or '', item.get('commune') or '')
        )

        return JsonResponse({
            'success': True,
            'communes': communes_list,
            'total': len(communes_list)
        })
    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


@login_required
def api_delais_paiement_details(request):
    """
    API pour retourner les détails des transactions par catégorie de délai de paiement
    """
    from django.http import JsonResponse
    from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_paiement_volume
    from django.utils import timezone
    import traceback

    try:
        categorie_delai = request.GET.get('categorie_delai')
        if not categorie_delai:
            return JsonResponse({'success': False, 'error': 'Catégorie de délai manquante'}, status=400)

        # Récupérer les paramètres de filtres
        organisation_id = request.GET.get('organisation')
        annee_str = request.GET.get('annee', str(timezone.now().year))
        try:
            annee = int(annee_str)
        except (ValueError, TypeError):
            annee = timezone.now().year

        scope_info = _resolve_effective_gestionnaire_scope(request.user, organisation_id)
        ouvrages_org_ids = list(
            _get_responsable_scoped_ouvrage_ids(
                request.user,
                effective_gestionnaire_ids=scope_info['effective_gestionnaire_ids'],
                modalites=['au_volume', 'mixte'],
            )
        )

        # Cas spécial pour 'non_paye' : récupérer les relevés sans numeroDiameX
        if categorie_delai == 'non_paye':
            from apps.billing.models import Releve

            releves_non_payes = Releve.objects.filter(
                montant__isnull=False,
                numeroDiameX__isnull=True,
                datereleve__year=annee,
                point_eau__ouvrage_id__in=ouvrages_org_ids
            ).select_related('point_eau', 'point_eau__ouvrage').order_by('-datereleve')

            transactions_par_categorie = []
            for releve in releves_non_payes:
                ouvrage_nom = releve.point_eau.ouvrage.nom_ouvrage if releve.point_eau and releve.point_eau.ouvrage else None

                transactions_par_categorie.append({
                    'numero': str(releve.id)[:8],
                    'ouvrage': ouvrage_nom,
                    'description': f"Relevé {releve.point_eau.code_point_eau if releve.point_eau else 'N/A'}",
                    'montant': float(releve.montant),
                    'date_facture': releve.datereleve.strftime('%m/%Y'),
                    'date_paiement': None,
                    'mois_facture': releve.datereleve.month,
                    'annee_facture': releve.datereleve.year,
                    'mois_paiement': None,
                    'annee_paiement': None,
                })

            return JsonResponse({
                'success': True,
                'transactions': transactions_par_categorie,
                'categorie': categorie_delai
            })

        # Récupérer toutes les transactions DiameX de l'année
        # Utiliser date_rec__year pour correspondre à la vue principale
        # Important: ne pas filtrer par date_rec (date de paiement).
        # Le rattachement annuel se fait via la date de facture extraite du libellé.
        transactions_qs = BaseDiameX.objects.filter(
            compte_code='707401'
        ).exclude(description__isnull=True).exclude(description='')

        # Classifier les transactions par délai
        transactions_par_categorie = []

        for transaction in transactions_qs:
            # Extraire l'ouvrage et la date de facture depuis la description
            info = extraire_ouvrage_et_mois_paiement_volume(transaction.description)
            infos_list = info if isinstance(info, list) else [info]

            # Calcul du montant par paiement (cas des multi-paiements)
            montant_total_transaction = float(transaction.montant_in) if transaction.montant_in else 0.0
            valides = [i for i in infos_list if i.get('mois') and i.get('annee')]
            nb_paiements = len(valides)
            montant_par_paiement = montant_total_transaction / nb_paiements if nb_paiements > 0 else montant_total_transaction

            found_any_date = any(i.get('mois') and i.get('annee') for i in infos_list)

            for info_item in infos_list:
                ouvrage_obj = info_item.get('ouvrage_obj')
                if not (ouvrage_obj and ouvrage_obj.id in ouvrages_org_ids):
                    continue

                mois_paiement = None
                annee_paiement = None
                mois_facture = None
                annee_facture = None
                date_facture_str = None
                categorie = None

                if info_item and info_item.get('mois') and info_item.get('annee'):
                    mois_facture = info_item['mois']
                    annee_facture = info_item['annee']
                    if annee_facture != annee:
                        continue

                    # Date de paiement souhaitée (date_rec)
                    if transaction.date_rec:
                        mois_paiement = transaction.date_rec.month
                        annee_paiement = transaction.date_rec.year

                        # Délai en mois
                        delai_mois = (annee_paiement - annee_facture) * 12 + (mois_paiement - mois_facture)

                        # Déterminer la catégorie
                        if delai_mois == 0:
                            categorie = 'meme_mois'
                        elif delai_mois == 1:
                            categorie = '1_mois'
                        elif delai_mois == 2:
                            categorie = '2_mois'
                        elif delai_mois >= 3:
                            categorie = '3_mois_plus'
                        else:
                            categorie = 'anomalie' # Paiement avant facture
                    else:
                        categorie = 'non_determine' # Pas de date de paiement

                    date_facture_str = f"{mois_facture:02d}/{annee_facture}"
                else:
                    continue

                # Si c'est la catégorie demandée, ajouter à la liste
                if categorie == categorie_delai:
                    ouvrage_nom = ouvrage_obj.nom_ouvrage if ouvrage_obj else info_item.get('ouvrage_nom')

                    transactions_par_categorie.append({
                        'numero': str(transaction.id)[:8],
                        'ouvrage': ouvrage_nom,
                        'description': transaction.description,
                        'montant': montant_par_paiement,
                        'date_facture': date_facture_str,
                        'date_paiement': transaction.date_rec.strftime('%d/%m/%Y') if transaction.date_rec else None,
                        'mois_facture': mois_facture,
                        'annee_facture': annee_facture,
                        'mois_paiement': mois_paiement,
                        'annee_paiement': annee_paiement,
                    })

        return JsonResponse({
            'success': True,
            'transactions': transactions_par_categorie,
            'categorie': categorie_delai
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)
