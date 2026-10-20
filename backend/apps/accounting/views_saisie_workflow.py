"""
Workflow de saisie comptable manuelle (separe de BaseDiameX).
"""

import json
import re
import unicodedata
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.billing.models import Fournisseur
from apps.organization.models import Base, Compte, Journal

from apps.employees.permissions import can_override_saisie_controls

from .charte_verification import verifier_charte_compte
from .controle_indemnites_saisie import controler_indemnite_saisie
from .models import SaisieComptable
from .pointage_ecritures import COMPTE_INDEMNITES
from .saisie_articles import (
    DETAIL_MAX,
    appliquer_effets,
    composer_detail,
    compte_concerne,
    enregistrer_articles,
    parse_articles,
)
from . import views as legacy_views

DEROGATION_MOTIF_MIN = 10


def _get_user_organisation_id(user):
    try:
        return user.employe.base.organisation_id
    except Exception:
        return None


def _get_scoped_bases_queryset(user):
    qs = Base.objects.select_related('organisation').all()
    organisation_id = _get_user_organisation_id(user)
    if organisation_id:
        return qs.filter(organisation_id=organisation_id)
    if getattr(user, 'is_superuser', False):
        return qs
    if not organisation_id:
        return qs.none()
    return qs.none()


def _journal_ferme(journal):
    """Un journal fermé est signalé par « (fermé) » dans son nom (aucun champ dédié en base)."""
    name = unicodedata.normalize('NFKD', journal.nom_journal or '')
    name = ''.join(c for c in name if not unicodedata.combining(c)).casefold()
    return bool(re.search(r'\bfermee?s?\b', name))


def _get_scoped_journaux_queryset(user):
    qs = Journal.objects.select_related('base', 'base__organisation').all()
    organisation_id = _get_user_organisation_id(user)
    if organisation_id:
        return qs.filter(base__organisation_id=organisation_id)
    if getattr(user, 'is_superuser', False):
        return qs
    if not organisation_id:
        return qs.none()
    return qs.none()


def _get_scoped_comptes_queryset(user):
    qs = Compte.objects.select_related('organisation').all()
    organisation_id = _get_user_organisation_id(user)
    if organisation_id:
        return qs.filter(organisation_id=organisation_id)
    if getattr(user, 'is_superuser', False):
        return qs
    if not organisation_id:
        return qs.none()
    return qs.none()


def _get_scoped_saisie_queryset(user):
    qs = SaisieComptable.objects.select_related(
        'base', 'journal', 'compte', 'created_by', 'validated_by'
    )
    organisation_id = _get_user_organisation_id(user)
    if organisation_id:
        return qs.filter(base__organisation_id=organisation_id)
    if getattr(user, 'is_superuser', False):
        return qs
    if not organisation_id:
        return qs.none()
    return qs.none()


def _get_current_employe(user):
    try:
        return user.employe
    except Exception:
        return None


workflow_pointage_tiers = legacy_views.workflow_pointage_tiers
api_workflow_pointage_tiers = legacy_views.api_workflow_pointage_tiers
api_workflow_depointage_tiers = legacy_views.api_workflow_depointage_tiers
workflow_soldes_reels = legacy_views.workflow_soldes_reels
api_workflow_soldes_reels_save = legacy_views.api_workflow_soldes_reels_save
api_details_solde = legacy_views.api_details_solde


def _parse_date(value):
    if not value:
        return None
    try:
        return timezone.datetime.strptime(str(value), '%Y-%m-%d').date()
    except Exception:
        return None


def _parse_decimal(value, default='0'):
    raw_value = default if value in (None, '') else value
    try:
        return Decimal(str(raw_value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _extract_fournisseur_idxls(value):
    if not value:
        return None
    cleaned = str(value).strip()
    if cleaned.isdigit():
        return cleaned
    match = re.match(r'^(\d+)\b', cleaned)
    if match:
        return match.group(1)
    return None


def _normalize_financement(value):
    """Normalise une valeur Fin sans masquer une faute d'accent ou de libellé."""
    normalized = unicodedata.normalize('NFKC', str(value or ''))
    return ' '.join(normalized.split()).casefold()


def _serialize_saisie(entry):
    return {
        'id': str(entry.id),
        'base': entry.base.nom_base if entry.base else '',
        'journal': entry.journal.nom_journal if entry.journal else '',
        'journal_code': entry.journal.code if entry.journal else '',
        'compte_code': entry.compte_code or '',
        'compte_nom': entry.compte.nom_compte if entry.compte else '',
        'date_m': entry.date_m.isoformat() if entry.date_m else '',
        'description': entry.description or '',
        'montant_in': float(entry.montant_in or 0),
        'montant_out': float(entry.montant_out or 0),
        'fournisseur': entry.fournisseur or '',
        'detail': entry.detail or '',
        'statut': entry.statut,
        'conforme': bool(entry.conforme),
        'errors_count': len(entry.erreurs_validation or []),
        'warnings_count': len(entry.avertissements_validation or []),
        'created_at': entry.created_at.isoformat() if entry.created_at else '',
        'created_by': (
            entry.created_by.nom_complet
            if entry.created_by and hasattr(entry.created_by, 'nom_complet')
            else (entry.created_by.nom_employe if entry.created_by else '')
        ),
    }


def _validate_saisie_payload(payload, user):
    errors = []
    warnings = []
    rules = []
    derogeables = []  # controles metier : bloquants, mais un directeur peut valider malgre eux

    base = _get_scoped_bases_queryset(user).filter(id=payload.get('base_id')).first()
    if not base:
        errors.append('Base invalide ou non autorisee.')

    journal = _get_scoped_journaux_queryset(user).filter(id=payload.get('journal_id')).first()
    if not journal:
        errors.append('Journal invalide ou non autorise.')
    elif base and journal.base_id != base.id:
        errors.append('Le journal selectionne ne correspond pas a la base.')
    elif _journal_ferme(journal):
        errors.append('Ce journal est ferme : choisir un journal ouvert.')

    compte = _get_scoped_comptes_queryset(user).filter(id=payload.get('compte_id')).first()
    if not compte:
        errors.append('Compte cat invalide ou non autorise.')

    date_m = _parse_date(payload.get('date_m'))
    if not date_m:
        errors.append('Date mouvement invalide (format attendu YYYY-MM-DD).')

    date_rec = _parse_date(payload.get('date_rec'))

    description = (payload.get('description') or '').strip()
    if not description:
        errors.append('Description obligatoire.')

    montant_in = _parse_decimal(payload.get('montant_in'), default='0')
    montant_out = _parse_decimal(payload.get('montant_out'), default='0')
    if montant_in is None or montant_out is None:
        errors.append('Montants invalides.')
        montant_in = Decimal('0')
        montant_out = Decimal('0')

    if montant_in < 0 or montant_out < 0:
        errors.append('Les montants ne peuvent pas etre negatifs.')

    if montant_in > 0 and montant_out > 0:
        errors.append('Saisir soit un montant In soit un montant Out, pas les deux.')
    if montant_in == 0 and montant_out == 0:
        errors.append('Saisir un montant (In ou Out).')

    pers = (payload.get('pers') or '').strip()
    detail = (payload.get('detail') or '').strip()
    info = (payload.get('info') or '').strip()
    fin = (payload.get('fin') or '').strip()
    activ = (payload.get('activ') or '').strip()
    prog = (payload.get('prog') or '').strip()
    fournisseur = (payload.get('fournisseur') or '').strip()

    if base:
        if not prog and base.prog_diamex:
            prog = base.prog_diamex
            rules.append('Prog auto-rempli depuis la base.')
        if not activ and base.volet:
            activ = base.volet
            rules.append('Activ auto-rempli depuis le volet de la base.')

    if compte:
        compte_code = compte.compte or ''
        rules.append(f"Compte cat: {compte_code or 'non renseigne'} - {compte.nom_compte}")

        financement_attendu = (compte.financement or '').strip()
        if financement_attendu:
            rules.append(f'Financement attendu: {financement_attendu}')
            if not fin:
                errors.append(
                    f'Financement obligatoire pour ce compte : saisir « {financement_attendu} » dans Fin.'
                )
            elif _normalize_financement(fin) != _normalize_financement(financement_attendu):
                errors.append(
                    f'Financement incorrect : « {fin} » saisi, « {financement_attendu} » attendu pour ce compte.'
                )

        if compte.fournisseur_obligatoire:
            rules.append('Fournisseur obligatoire pour ce compte.')
            if not fournisseur:
                errors.append('Fournisseur obligatoire pour ce compte cat.')

        if compte.employe_obligatoire:
            rules.append('Compte employe: detail/pers recommande.')
            if not detail and not pers:
                errors.append('Detail ou Personne est obligatoire pour un compte employe.')

        if compte.necessite_ouvrage:
            rules.append('Compte necessitant un ouvrage dans la description.')

        charte_type = (compte.charte_verification or '').strip()
        if charte_type:
            rules.append(f'Charte active: {charte_type}')
            charte_result = verifier_charte_compte(description, charte_type, compte_code)
            if not charte_result.get('conforme', False):
                for err in charte_result.get('erreurs', []):
                    errors.append(f'Charte: {err}')

        if compte.fournisseur_obligatoire and description:
            try:
                from .views_verification_fournisseurs import verifier_format_charte_fournisseur
                fournisseur_idxls = _extract_fournisseur_idxls(fournisseur)
                fournisseur_check = verifier_format_charte_fournisseur(
                    description,
                    fournisseur_idxls=fournisseur_idxls,
                    compte_code=compte_code
                )
                if not fournisseur_check.get('conforme', True):
                    for err in fournisseur_check.get('erreurs', []):
                        errors.append(f'Pattern fournisseur: {err}')
                rules.append('Pattern fournisseur (page verification fournisseurs) applique.')
            except Exception:
                warnings.append('Verification fournisseur detaillee indisponible pour le moment.')

        if compte.employe_obligatoire and description:
            try:
                from .views_verification_unifiee import (
                    PATTERNS_PAIEMENTS_EMPLOYES,
                    verifier_pattern_description,
                )
                pattern_ok, _, _ = verifier_pattern_description(description, PATTERNS_PAIEMENTS_EMPLOYES)
                if not pattern_ok:
                    warnings.append(
                        'Description employe non reconnue par les patterns de verification employes.'
                    )
                rules.append('Patterns paiements employes (verification unifiee) appliques.')
            except Exception:
                warnings.append('Patterns employes indisponibles pour le moment.')

    if compte and compte.compte == COMPTE_INDEMNITES and date_m and montant_out and montant_out > 0:
        try:
            controle = controler_indemnite_saisie(description, date_m, montant_out, compte.compte)
            derogeables.extend(controle['derogeables'])
            warnings.extend(controle['warnings'])
            rules.append('Controle indemnites : plafond 40 000 Ar/point d\'eau/an et paiements forfaitaires pointes.')
        except Exception:
            # Un controle qu'on ne peut pas faire ne doit pas laisser passer la saisie en silence.
            derogeables.append('Controle des indemnites indisponible : validation par le directeur requise.')

    lignes_articles, art_errors, art_warnings, art_rules = parse_articles(
        payload.get('articles'), user, compte.compte if compte else '', montant_out
    )
    errors.extend(art_errors)
    warnings.extend(art_warnings)
    rules.extend(art_rules)
    detail_suggere = composer_detail(lignes_articles)
    if not detail and detail_suggere:
        detail = detail_suggere
        rules.append('Detail auto-rempli depuis les articles hors stock (RAL = reste a livrer).')
    if len(detail) > DETAIL_MAX:
        errors.append(f'Detail trop long ({len(detail)} caracteres, maximum {DETAIL_MAX}).')

    normalized = {
        'articles': lignes_articles,
        'base': base,
        'journal': journal,
        'compte': compte,
        'compte_code': (compte.compte if compte else ''),
        'date_m': date_m,
        'date_rec': date_rec,
        'description': description,
        'montant_in': montant_in.quantize(Decimal('0.01')) if montant_in is not None else Decimal('0.00'),
        'montant_out': montant_out.quantize(Decimal('0.01')) if montant_out is not None else Decimal('0.00'),
        'pers': pers,
        'detail': detail,
        'info': info,
        'fin': fin,
        'activ': activ,
        'prog': prog,
        'fournisseur': fournisseur,
    }

    return {
        'valid': len(errors) == 0 and len(derogeables) == 0,
        'errors': errors,
        'derogeables': derogeables,
        'peut_deroger': can_override_saisie_controls(user),
        'warnings': warnings,
        'rules': rules,
        'detail_suggere': detail_suggere,
        'normalized': normalized,
    }


def _derogation_accordee(validation, payload):
    """
    Vrai si la saisie n'est bloquee que par des controles derogeables, que l'utilisateur peut les lever
    (Directeur / Responsable operationnel) et qu'il a motive sa decision.
    """
    motif = (payload.get('derogation_motif') or '').strip()
    return bool(
        not validation['errors']
        and validation['derogeables']
        and validation['peut_deroger']
        and len(motif) >= DEROGATION_MOTIF_MIN
    )


@login_required
def saisie_comptable_workflow(request):
    """Page principale du workflow de saisie comptable."""
    bases_qs = _get_scoped_bases_queryset(request.user).order_by('nom_base')
    journaux_qs = _get_scoped_journaux_queryset(request.user).order_by('base__nom_base', 'nom_journal')
    comptes_qs = _get_scoped_comptes_queryset(request.user).order_by('compte', 'nom_compte')
    fournisseurs_qs = Fournisseur.objects.order_by('nom_fournisseur').only('idxls', 'nom_fournisseur')[:500]

    charte_labels = dict(Compte.CHARTE_CHOICES)

    bases_data = [
        {
            'id': str(base.id),
            'nom': base.nom_base,
            'prog_diamex': base.prog_diamex or '',
            'volet': base.volet or '',
        }
        for base in bases_qs
    ]
    journaux_data = [
        {
            'id': str(journal.id),
            'nom': journal.nom_journal,
            'code': journal.code or '',
            'base_id': str(journal.base_id) if journal.base_id else '',
        }
        for journal in journaux_qs
        if not _journal_ferme(journal)
    ]
    comptes_data = [
        {
            'id': str(compte.id),
            'compte': compte.compte or '',
            'nom': compte.nom_compte or '',
            'fournisseur_obligatoire': bool(compte.fournisseur_obligatoire),
            'employe_obligatoire': bool(compte.employe_obligatoire),
            'necessite_ouvrage': bool(compte.necessite_ouvrage),
            'financement': compte.financement or '',
            'charte_verification': compte.charte_verification or '',
            'charte_label': charte_labels.get(compte.charte_verification, ''),
        }
        for compte in comptes_qs
    ]
    fournisseurs_data = [
        {
            'idxls': fournisseur.idxls,
            'nom': fournisseur.nom_fournisseur,
            'label': (
                f"{fournisseur.idxls} - {fournisseur.nom_fournisseur}"
                if fournisseur.idxls is not None
                else fournisseur.nom_fournisseur
            ),
        }
        for fournisseur in fournisseurs_qs
    ]

    # Base de l'employe connecte, pre-selectionnee si elle fait partie de celles qu'il peut utiliser.
    employe_base_id = str(getattr(_get_current_employe(request.user), 'base_id', '') or '')
    default_base_id = employe_base_id if any(item['id'] == employe_base_id for item in bases_data) else ''

    recent_entries = _get_scoped_saisie_queryset(request.user)[:25]
    recent_data = [_serialize_saisie(entry) for entry in recent_entries]
    workflow_app_mode = bool(getattr(request, 'is_accounting_workflow_subdomain', False))
    main_site_url = (getattr(settings, 'MAIN_SITE_URL', '') or '').rstrip('/')

    template_name = (
        'accounting/saisie_workflow_compta.html'
        if workflow_app_mode
        else 'accounting/saisie_workflow.html'
    )

    return render(request, template_name, {
        'title': 'Workflow Saisie Comptabilite',
        'today': timezone.now().date().isoformat(),
        'bases_json': json.dumps(bases_data),
        'journaux_json': json.dumps(journaux_data),
        'comptes_json': json.dumps(comptes_data),
        'fournisseurs_json': json.dumps(fournisseurs_data),
        'recent_entries_json': json.dumps(recent_data),
        'workflow_app_mode': workflow_app_mode,
        'peut_deroger': can_override_saisie_controls(request.user),
        'default_base_id': default_base_id,
        'main_entries_url': f'{main_site_url}/comptabilite/entries/' if main_site_url else '',
        'main_verification_url': f'{main_site_url}/comptabilite/verification-unifiee/' if main_site_url else '',
    })


@login_required
@require_http_methods(["POST"])
def api_saisie_comptable_validate(request):
    """Valide une saisie sans enregistrement."""
    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Payload JSON invalide.'}, status=400)

    validation = _validate_saisie_payload(payload, request.user)
    return JsonResponse({
        'success': True,
        'valid': validation['valid'],
        'errors': validation['errors'],
        'derogeables': validation['derogeables'],
        'peut_deroger': validation['peut_deroger'],
        'warnings': validation['warnings'],
        'rules': validation['rules'],
        'detail_suggere': validation['detail_suggere'],
    })


@login_required
@require_http_methods(["POST"])
def api_saisie_comptable_save(request):
    """Valide puis enregistre la saisie dans la table dediee."""
    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Payload JSON invalide.'}, status=400)

    mode = (payload.get('mode') or 'brouillon').strip().lower()
    validation = _validate_saisie_payload(payload, request.user)

    derogation = _derogation_accordee(validation, payload)

    if mode == 'valider' and not validation['valid'] and not derogation:
        if validation['errors']:
            message = 'Validation echouee. Corriger les erreurs avant validation.'
        elif not validation['peut_deroger']:
            message = ('Controle metier non respecte : seule une validation par le Directeur ou le Responsable '
                       'operationnel est possible. Enregistrer en brouillon pour la lui transmettre.')
        else:
            message = (f'Controle metier non respecte : saisir le motif de la derogation '
                       f'(au moins {DEROGATION_MOTIF_MIN} caracteres) pour valider malgre tout.')
        return JsonResponse({
            'success': False,
            'error': message,
            'valid': False,
            'errors': validation['errors'],
            'derogeables': validation['derogeables'],
            'peut_deroger': validation['peut_deroger'],
            'warnings': validation['warnings'],
            'rules': validation['rules'],
        }, status=400)

    normalized = validation['normalized']
    persistence_errors = list(validation['errors'])

    # Meme en brouillon, la table impose ces champs non nuls.
    if not normalized.get('base'):
        persistence_errors.append('Base obligatoire pour enregistrer la ligne.')
    if not normalized.get('journal'):
        persistence_errors.append('Journal obligatoire pour enregistrer la ligne.')
    if not normalized.get('compte'):
        persistence_errors.append('Compte cat obligatoire pour enregistrer la ligne.')
    if not normalized.get('date_m'):
        persistence_errors.append('Date mouvement obligatoire pour enregistrer la ligne.')
    if not normalized.get('description'):
        persistence_errors.append('Description obligatoire pour enregistrer la ligne.')

    if persistence_errors:
        deduped_errors = list(dict.fromkeys(persistence_errors))
        return JsonResponse({
            'success': False,
            'error': 'Champs obligatoires manquants pour enregistrer.',
            'valid': False,
            'errors': deduped_errors,
            'warnings': validation['warnings'],
            'rules': validation['rules'],
        }, status=400)

    statut = 'brouillon'
    conforme = validation['valid']
    validated_at = None
    validated_by = None
    created_by = _get_current_employe(request.user)
    warnings = list(validation['warnings'])
    rules = list(validation['rules'])

    if mode == 'valider' and (validation['valid'] or derogation):
        statut = 'valide'
        validated_at = timezone.now()
        validated_by = created_by
        if derogation:
            auteur = getattr(created_by, 'nom_affichage', '') or request.user.get_username()
            motif = (payload.get('derogation_motif') or '').strip()
            rules.append(f'Derogation accordee par {auteur} : {motif}')
    elif not validation['valid']:
        statut = 'a_corriger'

    with transaction.atomic():
        entry = SaisieComptable.objects.create(
            base=normalized['base'],
            journal=normalized['journal'],
            compte=normalized['compte'],
            compte_code=normalized['compte_code'],
            date_m=normalized['date_m'],
            date_rec=normalized['date_rec'],
            description=normalized['description'],
            montant_in=normalized['montant_in'],
            montant_out=normalized['montant_out'],
            pers=normalized['pers'],
            detail=normalized['detail'],
            info=normalized['info'],
            fin=normalized['fin'],
            activ=normalized['activ'],
            prog=normalized['prog'],
            fournisseur=normalized['fournisseur'],
            statut=statut,
            conforme=conforme,
            erreurs_validation=validation['errors'] + validation['derogeables'],
            avertissements_validation=warnings,
            regles_appliquees=rules,
            created_by=created_by,
            validated_by=validated_by,
            validated_at=validated_at,
            source_saisie='workflow',
        )
        enregistrer_articles(entry, normalized.get('articles') or [])
        if statut == 'valide':
            appliquer_effets(entry)

    return JsonResponse({
        'success': True,
        'message': 'Saisie validee par derogation.' if derogation and statut == 'valide' else 'Saisie enregistree.',
        'entry': _serialize_saisie(entry),
        'valid': validation['valid'],
        'errors': validation['errors'],
        'derogeables': validation['derogeables'],
        'peut_deroger': validation['peut_deroger'],
        'warnings': warnings,
        'rules': rules,
    })


def _payload_from_saisie(entry):
    """Recompose le payload de validation d'une saisie enregistree, pour la re-controler avec l'etat actuel."""
    return {
        'base_id': str(entry.base_id or ''),
        'journal_id': str(entry.journal_id or ''),
        'compte_id': str(entry.compte_id or ''),
        'date_m': entry.date_m.isoformat() if entry.date_m else '',
        'date_rec': entry.date_rec.isoformat() if entry.date_rec else '',
        'description': entry.description or '',
        'montant_in': str(entry.montant_in or 0),
        'montant_out': str(entry.montant_out or 0),
        'pers': entry.pers or '',
        'detail': entry.detail or '',
        'info': entry.info or '',
        'fin': entry.fin or '',
        'activ': entry.activ or '',
        'prog': entry.prog or '',
        'fournisseur': entry.fournisseur or '',
        'articles': [
            {
                'designation_id': str(a.designation_id),
                'mode': a.mode,
                'quantite': str(a.quantite),
                'quantite_recue': str(a.quantite_recue),
                'prix_unitaire': '' if a.prix_unitaire is None else str(a.prix_unitaire),
                'destination_type': a.destination_type,
                'destination_id': str(a.ouvrage_id or a.employe_id or a.vehicule_id or ''),
            }
            for a in entry.articles.all()
        ],
    }


@login_required
@require_http_methods(["GET"])
def api_saisie_comptable_pending(request):
    """
    Saisies en attente de la direction : enregistrees `a_corriger` et uniquement bloquees par des controles
    derogeables. Elles sont re-controlees a chaque appel : une saisie devenue conforme ou ayant une vraie erreur
    n'apparait plus ici.
    """
    if not can_override_saisie_controls(request.user):
        return JsonResponse({'success': False, 'error': 'Reserve au Directeur et au Responsable operationnel.'}, status=403)

    items = []
    for entry in _get_scoped_saisie_queryset(request.user).filter(statut='a_corriger')[:100]:
        validation = _validate_saisie_payload(_payload_from_saisie(entry), request.user)
        if validation['errors'] or not validation['derogeables']:
            continue
        items.append({**_serialize_saisie(entry), 'controles': validation['derogeables']})
    return JsonResponse({'success': True, 'entries': items})


@login_required
@require_http_methods(["POST"])
def api_saisie_comptable_approve(request):
    """Valide une saisie en attente malgre ses controles derogeables (Directeur / Responsable operationnel)."""
    if not can_override_saisie_controls(request.user):
        return JsonResponse({'success': False, 'error': 'Reserve au Directeur et au Responsable operationnel.'}, status=403)
    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Payload JSON invalide.'}, status=400)

    entry = _get_scoped_saisie_queryset(request.user).filter(id=data.get('id'), statut='a_corriger').first()
    if entry is None:
        return JsonResponse({'success': False, 'error': 'Saisie introuvable ou deja traitee.'}, status=404)

    validation = _validate_saisie_payload(_payload_from_saisie(entry), request.user)
    if validation['errors']:
        return JsonResponse({
            'success': False,
            'error': 'La saisie contient des erreurs a corriger par son auteur : ' + ' '.join(validation['errors']),
        }, status=400)

    motif = (data.get('motif') or '').strip()
    rules = list(validation['rules'])
    employe = _get_current_employe(request.user)
    if validation['derogeables']:
        if len(motif) < DEROGATION_MOTIF_MIN:
            return JsonResponse({
                'success': False,
                'error': f'Saisir le motif de la derogation (au moins {DEROGATION_MOTIF_MIN} caracteres).',
            }, status=400)
        auteur = getattr(employe, 'nom_affichage', '') or request.user.get_username()
        rules.append(f'Derogation accordee par {auteur} : {motif}')

    entry.statut = 'valide'
    entry.conforme = validation['valid']
    entry.validated_by = employe
    entry.validated_at = timezone.now()
    entry.erreurs_validation = validation['derogeables']
    entry.avertissements_validation = validation['warnings']
    entry.regles_appliquees = rules
    with transaction.atomic():
        entry.save()
        appliquer_effets(entry)
    return JsonResponse({'success': True, 'message': 'Saisie validee.', 'entry': _serialize_saisie(entry)})


@login_required
@require_http_methods(["GET"])
def api_saisie_comptable_recent(request):
    """Retourne les dernieres saisies scopees de l'utilisateur."""
    try:
        limit = int(request.GET.get('limit', 25))
    except (TypeError, ValueError):
        limit = 25
    limit = max(5, min(limit, 100))

    entries = _get_scoped_saisie_queryset(request.user)[:limit]
    return JsonResponse({
        'success': True,
        'entries': [_serialize_saisie(entry) for entry in entries],
    })


@login_required
@require_http_methods(["GET"])
def api_saisie_articles_designations(request):
    """Recherche de designations actives pour le detail des articles (autocompletion)."""
    from apps.planning.models import Designation

    terme = (request.GET.get('q') or '').strip()
    qs = Designation.objects.filter(actif=True)
    if terme:
        qs = qs.filter(nom__icontains=terme)
    items = [
        {
            'id': str(d.id),
            'nom': d.nom,
            'unite': d.unite or '',
            'prix_unitaire': float(d.prix_unitaire) if d.prix_unitaire is not None else None,
            'date_prix': d.date_prix.isoformat() if d.date_prix else '',
        }
        for d in qs.order_by('nom')[:30]
    ]
    return JsonResponse({'success': True, 'designations': items})


@login_required
@require_http_methods(["GET"])
def api_saisie_articles_destinations(request):
    """Recherche d'ouvrages / employes / vehicules pour les articles livres hors stock."""
    from apps.core.views_ouvrage_interventions import _accessible_ouvrages
    from apps.employees.models import Employe
    from apps.inventory.models import Vehicule
    from django.db.models import Q

    dest_type = (request.GET.get('type') or '').strip()
    terme = (request.GET.get('q') or '').strip()
    items = []
    if dest_type == 'ouvrage':
        qs = _accessible_ouvrages(request.user, include_other_bases=True)
        if terme:
            qs = qs.filter(nom_ouvrage__icontains=terme)
        items = [{'id': str(o.id), 'label': o.nom_ouvrage} for o in qs.distinct().order_by('nom_ouvrage')[:30]]
    elif dest_type == 'employe':
        qs = Employe.objects.all()
        organisation_id = _get_user_organisation_id(request.user)
        if organisation_id:
            qs = qs.filter(base__organisation_id=organisation_id)
        elif not getattr(request.user, 'is_superuser', False):
            qs = qs.none()
        if terme:
            qs = qs.filter(Q(nom__icontains=terme) | Q(prenom__icontains=terme) | Q(surnom__icontains=terme))
        items = [
            {'id': str(e.id), 'label': ' '.join(x for x in (e.surnom or e.prenom, e.nom) if x)}
            for e in qs.order_by('nom')[:30]
        ]
    elif dest_type == 'vehicule':
        qs = Vehicule.objects.all()
        if terme:
            qs = qs.filter(Q(immatriculation__icontains=terme) | Q(marque__icontains=terme) | Q(modele__icontains=terme))
        items = [
            {'id': str(v.id), 'label': f'{v.immatriculation} - {v.marque} {v.modele}'}
            for v in qs.order_by('immatriculation')[:30]
        ]
    return JsonResponse({'success': True, 'items': items})
