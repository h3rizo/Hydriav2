"""
Vues pour la vérification de conformité avec séparation selon nécessité d'ouvrage
- Page 1: Comptes nécessitant un ouvrage (necessite_ouvrage=True)
- Page 2: Comptes ne nécessitant pas d'ouvrage (necessite_ouvrage=False)
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import JsonResponse, StreamingHttpResponse
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.db.models import Q, Count, F
from apps.accounting.models import BaseDiameX
from apps.organization.models import Compte, Base
from apps.accounting.charte_verification import verifier_charte_compte
from apps.accounting.extracteurs_description import (
    enrichir_point_eau_par_nom_abonne,
    extraire_ouvrage_et_mois_generique,
)
from apps.billing.models import PointEau
from apps.employees.permissions import filter_queryset_by_permissions
import json
import re
from datetime import datetime
from decimal import Decimal


def _get_user_organisation_id(user):
    if getattr(user, 'is_superuser', False):
        return None
    try:
        return user.employe.base.organisation_id
    except Exception:
        return None


def _filter_comptes_by_scope(queryset, user):
    if getattr(user, 'is_superuser', False):
        return queryset
    organisation_id = _get_user_organisation_id(user)
    if not organisation_id:
        return queryset.none()
    return queryset.filter(organisation_id=organisation_id)


def _get_scoped_diamex_queryset(user):
    qs = BaseDiameX.objects.all()
    if getattr(user, 'is_superuser', False):
        return qs

    organisation_id = _get_user_organisation_id(user)
    if not organisation_id:
        return qs.none()

    allowed_progs = list(
        Base.objects.filter(organisation_id=organisation_id)
        .exclude(prog_diamex__isnull=True)
        .exclude(prog_diamex='')
        .values_list('prog_diamex', flat=True)
        .distinct()
    )
    if not allowed_progs:
        return qs.none()
    return qs.filter(prog__in=allowed_progs)


def diviser_paiement_volume_multi(description, compte_code, montant_total):
    """
    Divise une description de paiement volumétrique contenant plusieurs paiements

    Formats supportés:
    1. Avec montants explicites: "Paiement au volume Antsahatanteraka 01/02/2025 84200; Antsahatanteraka 01/03/2024 296600"
    2. Sans montants (nouveaux formats):
       - Ouvrage répété: "Paiement au volume Anjahambe 03/2025 9200; Anjahambe 04/2025 246500; ..."
       - Ouvrage hérité: "Paiement au volume Anjahambe 12/2025 41400; 01/2025 24200; 02/2025 21900; ..."

    Args:
        description: Description complète de la ligne DiameX
        compte_code: Code compte de la ligne
        montant_total: Montant total IN de la ligne originale

    Returns:
        list: Liste de dict avec {description_partielle, montant, extraction}
              Retourne une liste vide si le format ne correspond pas
    """
    from apps.accounting.extracteurs_description import est_paiement_volume_multi

    if not description or not est_paiement_volume_multi(description):
        return []

    # Utiliser la nouvelle fonction d'extraction qui supporte les multi-paiements
    from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_paiement_volume

    result = extraire_ouvrage_et_mois_paiement_volume(description)

    # Si c'est un dict (paiement simple), retourner liste vide (pas de multi-paiement)
    if not isinstance(result, list):
        return []

    # Filtrer les éléments valides (qui ont au moins un ouvrage et une date)
    valid_items = [item for item in result if item.get('ouvrage_nom') and item.get('mois') and item.get('annee')]

    if not valid_items:
        return []

    # Calculer les montants explicites présents dans le libellé
    montants_explicites = [item.get('montant') for item in valid_items if item.get('montant') is not None]

    # Cas 1 : on a des montants explicites -> on les respecte, même si le total ne correspond pas
    if montants_explicites:
        segments = []
        reste_total = float(montant_total) if montant_total else 0.0
        nb_sans_montant = len([item for item in valid_items if item.get('montant') is None])
        # montant à répartir pour les segments sans montant explicite
        montant_par_defaut = (reste_total - sum(montants_explicites)) / nb_sans_montant if nb_sans_montant > 0 else 0

        for item in valid_items:
            description_partielle = f"Paiement au volume {item['ouvrage_nom']} {item['date_str']}"
            montant_seg = float(item['montant']) if item.get('montant') is not None else montant_par_defaut
            segments.append({
                'description_partielle': description_partielle,
                'montant': montant_seg,
                'ouvrage_nom': item['ouvrage_nom'],
                'mois': item['mois'],
                'annee': item['annee'],
                'date_str': item['date_str'],
                'extraction': item
            })
        return segments

    # Cas 2 : pas de montants explicites -> diviser le montant total également
    elif montant_total:
        nb_paiements = len(valid_items)
        montant_par_paiement = float(montant_total) / nb_paiements if nb_paiements > 0 else 0

        segments = []
        for item in valid_items:
            description_partielle = f"Paiement au volume {item['ouvrage_nom']} {item['date_str']}"
            segments.append({
                'description_partielle': description_partielle,
                'montant': montant_par_paiement,
                'ouvrage_nom': item['ouvrage_nom'],
                'mois': item['mois'],
                'annee': item['annee'],
                'date_str': item['date_str'],
                'extraction': item
            })
        return segments

    # Aucun montant disponible
    return []


@login_required
def verification_avec_ouvrage(request):
    """Page de vérification des comptes nécessitant un ouvrage"""

    # Filtrer les comptes qui nécessitent un ouvrage
    comptes_qs = _filter_comptes_by_scope(
        Compte.objects.filter(necessite_ouvrage=True),
        request.user
    )

    # Exclure les comptes employés et fournisseurs
    comptes_qs = comptes_qs.exclude(
        Q(employe_obligatoire=True) |
        Q(fournisseur_obligatoire=True)
    )

    comptes = comptes_qs.select_related('organisation')

    context = {
        'title': 'Vérification - Comptes avec Ouvrage',
        'comptes': comptes,
        'comptes_count': comptes.count(),
        'necessite_ouvrage': True,  # Flag pour le template
        'verification_nav_key': 'avec_ouvrage',
    }

    return render(request, 'accounting/verification_par_ouvrage.html', context)


@login_required
def verification_sans_ouvrage(request):
    """Page de vérification des comptes ne nécessitant pas d'ouvrage"""

    # Filtrer les comptes qui ne nécessitent pas d'ouvrage
    comptes_qs = _filter_comptes_by_scope(
        Compte.objects.filter(necessite_ouvrage=False),
        request.user
    )

    # Exclure les comptes employés et fournisseurs
    comptes_qs = comptes_qs.exclude(
        Q(employe_obligatoire=True) |
        Q(fournisseur_obligatoire=True)
    )

    comptes = comptes_qs.select_related('organisation')

    context = {
        'title': 'Vérification - Comptes sans Ouvrage',
        'comptes': comptes,
        'comptes_count': comptes.count(),
        'necessite_ouvrage': False,  # Flag pour le template
        'verification_nav_key': 'sans_ouvrage',
    }

    return render(request, 'accounting/verification_par_ouvrage.html', context)


@login_required
@require_http_methods(["POST"])
def api_integrer_nom_abonne_point_eau(request):
    """Enregistre explicitement le nom extrait dans PointEau.nomabonne."""
    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Corps JSON invalide.'}, status=400)

    point_eau_id = str(payload.get('point_eau_id') or '').strip()
    nom_abonne = ' '.join(str(payload.get('nom_abonne') or '').split())
    force = payload.get('force') is True
    if not point_eau_id or not nom_abonne:
        return JsonResponse({
            'success': False,
            'error': "Le point d'eau et le nom extrait sont obligatoires.",
        }, status=400)
    if len(nom_abonne) > 255:
        return JsonResponse({'success': False, 'error': 'Le nom dépasse 255 caractères.'}, status=400)

    points_accessibles = filter_queryset_by_permissions(PointEau.objects.all(), request.user)
    point_eau = points_accessibles.filter(pk=point_eau_id).first()
    if not point_eau:
        return JsonResponse({'success': False, 'error': "Point d'eau introuvable ou accès refusé."}, status=404)

    nom_actuel = (point_eau.nomabonne or '').strip()
    if nom_actuel and nom_actuel.casefold() != nom_abonne.casefold() and not force:
        return JsonResponse({
            'success': False,
            'confirmation_required': True,
            'nom_actuel': nom_actuel,
            'nom_extrait': nom_abonne,
            'error': 'Un autre nom est déjà enregistré.',
        }, status=409)

    point_eau.nomabonne = nom_abonne
    point_eau.save(update_fields=['nomabonne'])
    return JsonResponse({
        'success': True,
        'message': f'Nom de l’abonné enregistré : {nom_abonne}',
        'point_eau_id': str(point_eau.id),
        'nom_abonne': nom_abonne,
    })


def _nom_abonne_est_numerique(value):
    compact = re.sub(r'[\s()+./-]+', '', str(value or ''))
    return bool(compact) and compact.isdigit()


@login_required
@require_http_methods(["POST"])
def api_peupler_noms_abonnes(request):
    """Peuple les noms depuis les lignes DiameX, des plus recentes aux plus anciennes."""
    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Corps JSON invalide.'}, status=400)

    try:
        limit = max(100, min(int(payload.get('limit') or 5000), 20000))
    except (TypeError, ValueError):
        limit = 5000
    replace_conflicts = payload.get('replace_conflicts') is True

    comptes = _filter_comptes_by_scope(
        Compte.objects.filter(necessite_ouvrage=True).exclude(
            Q(employe_obligatoire=True) | Q(fournisseur_obligatoire=True)
        ),
        request.user,
    )
    codes = list(comptes.values_list('compte', flat=True))
    entries = _get_scoped_diamex_queryset(request.user).filter(
        compte_code__in=codes,
        description__contains='_',
    ).order_by(
        F('date_rec').desc(nulls_last=True),
        F('date_m').desc(nulls_last=True),
        '-id',
    )[:limit]

    # La premiere occurrence d'un point gagne puisque la liste est triee de
    # la plus recente vers la plus ancienne.
    latest_by_point = {}
    analysed = 0
    for entry in entries:
        analysed += 1
        try:
            extraction = extraire_ouvrage_et_mois_generique(
                entry.description or '',
                entry.compte_code,
            )
            extractions = extraction if isinstance(extraction, list) else [extraction]
            for item in extractions:
                point_eau = item.get('point_eau_obj') if isinstance(item, dict) else None
                nom_extrait = (
                    item.get('point_eau_nom_extrait')
                    or item.get('point_eau_nom')
                ) if isinstance(item, dict) else None
                nom_extrait = ' '.join(str(nom_extrait or '').split())
                if not point_eau or not nom_extrait or not any(char.isalpha() for char in nom_extrait):
                    continue
                latest_by_point.setdefault(str(point_eau.id), {
                    'point_eau': point_eau,
                    'nom_extrait': nom_extrait,
                    'entry_id': entry.id,
                    'date': entry.date_rec or entry.date_m,
                })
        except Exception:
            continue

    accessible_ids = set(
        filter_queryset_by_permissions(
            PointEau.objects.filter(id__in=latest_by_point.keys()),
            request.user,
        ).values_list('id', flat=True)
    )

    updates = []
    conflicts = []
    stats = {
        'analysed': analysed,
        'candidates': 0,
        'updated_empty': 0,
        'updated_numeric': 0,
        'updated_conflicts': 0,
        'unchanged': 0,
        'conflicts': 0,
    }
    for point_id, candidate in latest_by_point.items():
        if candidate['point_eau'].id not in accessible_ids:
            continue
        stats['candidates'] += 1
        point_eau = candidate['point_eau']
        nom_actuel = (point_eau.nomabonne or '').strip()
        nom_extrait = candidate['nom_extrait']

        if nom_actuel.casefold() == nom_extrait.casefold():
            stats['unchanged'] += 1
            continue
        if not nom_actuel:
            point_eau.nomabonne = nom_extrait
            updates.append(point_eau)
            stats['updated_empty'] += 1
            continue
        if _nom_abonne_est_numerique(nom_actuel):
            point_eau.nomabonne = nom_extrait
            updates.append(point_eau)
            stats['updated_numeric'] += 1
            continue

        conflict = {
            'point_eau_id': point_id,
            'idxls': point_eau.idxls,
            'nom_actuel': nom_actuel,
            'nom_extrait': nom_extrait,
            'entry_id': candidate['entry_id'],
            'date': candidate['date'].isoformat() if candidate['date'] else None,
        }
        conflicts.append(conflict)
        if replace_conflicts:
            point_eau.nomabonne = nom_extrait
            updates.append(point_eau)
            stats['updated_conflicts'] += 1

    stats['conflicts'] = len(conflicts)
    if updates:
        with transaction.atomic():
            PointEau.objects.bulk_update(updates, ['nomabonne'], batch_size=500)

    return JsonResponse({
        'success': True,
        'stats': stats,
        'conflicts': conflicts[:100],
        'conflicts_truncated': len(conflicts) > 100,
        'limit': limit,
    })


@login_required
@require_http_methods(["POST"])
def api_peupler_noms_abonnes_stream(request):
    """Peuple les noms et diffuse la progression au format NDJSON."""
    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Corps JSON invalide.'}, status=400)

    try:
        limit = max(100, min(int(payload.get('limit') or 5000), 20000))
    except (TypeError, ValueError):
        limit = 5000
    try:
        offset = max(0, int(payload.get('offset') or 0))
    except (TypeError, ValueError):
        offset = 0
    excluded_point_ids = {
        str(value) for value in (payload.get('excluded_point_ids') or [])[:20000]
        if value
    }
    replace_conflicts = payload.get('replace_conflicts') is True

    comptes = _filter_comptes_by_scope(
        Compte.objects.filter(necessite_ouvrage=True).exclude(
            Q(employe_obligatoire=True) | Q(fournisseur_obligatoire=True)
        ),
        request.user,
    )
    codes = list(comptes.values_list('compte', flat=True))

    def event(data):
        return json.dumps(data, ensure_ascii=False) + '\n'

    def stream():
        stats = {
            'analysed': 0,
            'candidates': 0,
            'processed': 0,
            'updated_empty': 0,
            'updated_numeric': 0,
            'updated_conflicts': 0,
            'unchanged': 0,
            'conflicts': 0,
        }
        conflicts = []
        try:
            yield event({
                'type': 'start',
                'limit': limit,
                'offset': offset,
                'batch_number': (offset // limit) + 1,
                'replace_conflicts': replace_conflicts,
                'message': f'Recherche du lot {(offset // limit) + 1} (lignes {offset + 1} à {offset + limit})…',
            })

            entries_with_next = list(
                _get_scoped_diamex_queryset(request.user).filter(
                    compte_code__in=codes,
                    description__contains='_',
                ).order_by(
                    F('date_rec').desc(nulls_last=True),
                    F('date_m').desc(nulls_last=True),
                    '-id',
                )[offset:offset + limit + 1]
            )
            has_more = len(entries_with_next) > limit
            entries = entries_with_next[:limit]
            total_entries = len(entries)
            yield event({
                'type': 'phase',
                'phase': 'analysis',
                'total': total_entries,
                'message': f'Analyse de {total_entries} ligne(s) DiameX…',
            })

            # La première occurrence gagne : les écritures sont triées des plus
            # récentes aux plus anciennes.
            latest_by_point = {}
            for entry in entries:
                stats['analysed'] += 1
                try:
                    extraction = extraire_ouvrage_et_mois_generique(
                        entry.description or '',
                        entry.compte_code,
                    )
                    extractions = extraction if isinstance(extraction, list) else [extraction]
                    for item in extractions:
                        point_eau = item.get('point_eau_obj') if isinstance(item, dict) else None
                        nom_extrait = (
                            item.get('point_eau_nom_extrait') or item.get('point_eau_nom')
                        ) if isinstance(item, dict) else None
                        nom_extrait = ' '.join(str(nom_extrait or '').split())
                        if not point_eau or not nom_extrait or not any(char.isalpha() for char in nom_extrait):
                            continue
                        latest_by_point.setdefault(str(point_eau.id), {
                            'point_eau': point_eau,
                            'nom_extrait': nom_extrait,
                            'entry_id': entry.id,
                            'date': entry.date_rec or entry.date_m,
                        })
                except Exception:
                    pass

                if stats['analysed'] % 50 == 0 or stats['analysed'] == total_entries:
                    yield event({
                        'type': 'progress',
                        'phase': 'analysis',
                        'current': stats['analysed'],
                        'total': total_entries,
                        'candidates_found': len(latest_by_point),
                        'stats': stats,
                    })

            accessible_ids = set(
                filter_queryset_by_permissions(
                    PointEau.objects.filter(id__in=latest_by_point.keys()),
                    request.user,
                ).values_list('id', flat=True)
            )
            candidates = [
                candidate for candidate in latest_by_point.values()
                if candidate['point_eau'].id in accessible_ids
                and str(candidate['point_eau'].id) not in excluded_point_ids
            ]
            stats['candidates'] = len(candidates)
            yield event({
                'type': 'phase',
                'phase': 'update',
                'total': len(candidates),
                'message': f'Traitement de {len(candidates)} point(s) d’eau…',
                'stats': stats,
            })

            for candidate in candidates:
                point_eau = candidate['point_eau']
                nom_actuel = (point_eau.nomabonne or '').strip()
                nom_extrait = candidate['nom_extrait']
                action = 'unchanged'

                if nom_actuel.casefold() == nom_extrait.casefold():
                    stats['unchanged'] += 1
                elif not nom_actuel:
                    point_eau.nomabonne = nom_extrait
                    point_eau.save(update_fields=['nomabonne'])
                    stats['updated_empty'] += 1
                    action = 'updated_empty'
                elif _nom_abonne_est_numerique(nom_actuel):
                    point_eau.nomabonne = nom_extrait
                    point_eau.save(update_fields=['nomabonne'])
                    stats['updated_numeric'] += 1
                    action = 'updated_numeric'
                else:
                    conflict = {
                        'point_eau_id': str(point_eau.id),
                        'idxls': point_eau.idxls,
                        'nom_actuel': nom_actuel,
                        'nom_extrait': nom_extrait,
                        'entry_id': candidate['entry_id'],
                        'date': candidate['date'].isoformat() if candidate['date'] else None,
                    }
                    conflicts.append(conflict)
                    action = 'conflict'
                    if replace_conflicts:
                        point_eau.nomabonne = nom_extrait
                        point_eau.save(update_fields=['nomabonne'])
                        stats['updated_conflicts'] += 1
                        action = 'updated_conflict'

                stats['processed'] += 1
                stats['conflicts'] = len(conflicts)
                yield event({
                    'type': 'change',
                    'action': action,
                    'current': stats['processed'],
                    'total': len(candidates),
                    'point_eau_id': str(point_eau.id),
                    'idxls': point_eau.idxls,
                    'nom_actuel': nom_actuel,
                    'nom_extrait': nom_extrait,
                    'stats': stats,
                })

            yield event({
                'type': 'complete',
                'success': True,
                'stats': stats,
                'conflicts': conflicts[:100],
                'conflicts_truncated': len(conflicts) > 100,
                'limit': limit,
                'offset': offset,
                'batch_number': (offset // limit) + 1,
                'next_offset': offset + limit,
                'has_more': has_more,
                'candidate_point_ids': [str(candidate['point_eau'].id) for candidate in candidates],
                'message': 'Traitement terminé.',
            })
        except Exception as exc:
            yield event({
                'type': 'error',
                'success': False,
                'error': str(exc),
                'stats': stats,
            })

    response = StreamingHttpResponse(stream(), content_type='application/x-ndjson; charset=utf-8')
    response['Cache-Control'] = 'no-cache, no-transform'
    response['X-Accel-Buffering'] = 'no'
    return response


@login_required
@require_http_methods(["POST"])
def api_renseigner_telephone_point_eau(request):
    """Enregistre manuellement le telephone lu sur le scan DiameX."""
    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Corps JSON invalide.'}, status=400)

    point_eau_id = str(payload.get('point_eau_id') or '').strip()
    telephone = ' '.join(str(payload.get('telephone') or '').split())
    force = payload.get('force') is True
    digits = re.sub(r'\D', '', telephone)
    if not point_eau_id or not telephone:
        return JsonResponse({'success': False, 'error': 'Le point d’eau et le téléphone sont obligatoires.'}, status=400)
    if len(telephone) > 20 or len(digits) < 6 or not re.fullmatch(r'[0-9+().\s/-]+', telephone):
        return JsonResponse({'success': False, 'error': 'Format de numéro de téléphone invalide.'}, status=400)

    point_eau = filter_queryset_by_permissions(
        PointEau.objects.all(),
        request.user,
    ).filter(pk=point_eau_id).first()
    if not point_eau:
        return JsonResponse({'success': False, 'error': "Point d'eau introuvable ou accès refusé."}, status=404)

    telephone_actuel = (point_eau.numeroteleph or '').strip()
    if telephone_actuel and telephone_actuel != telephone and not force:
        return JsonResponse({
            'success': False,
            'confirmation_required': True,
            'telephone_actuel': telephone_actuel,
            'telephone_nouveau': telephone,
            'error': 'Un autre numéro est déjà enregistré.',
        }, status=409)

    point_eau.numeroteleph = telephone
    point_eau.save(update_fields=['numeroteleph'])
    return JsonResponse({
        'success': True,
        'message': f'Numéro de téléphone enregistré : {telephone}',
        'telephone': telephone,
    })


@login_required
@require_http_methods(["GET"])
def api_extractions_point_eau(request, point_eau_id):
    """Retourne les propositions DiameX 621102 correspondant exactement au point d'eau."""
    point_eau = filter_queryset_by_permissions(
        PointEau.objects.select_related('ouvrage'),
        request.user,
    ).filter(pk=point_eau_id).first()
    if not point_eau:
        return JsonResponse({
            'success': False,
            'error': "Point d'eau introuvable ou accès refusé.",
        }, status=404)

    idxls = str(point_eau.idxls or '').strip()
    ouvrage_nom = (point_eau.ouvrage.nom_ouvrage or '').strip() if point_eau.ouvrage else ''
    point_data = {
        'id': str(point_eau.id),
        'nom_actuel': point_eau.nomabonne or '',
        'telephone_actuel': point_eau.numeroteleph or '',
        'idxls': idxls,
        'ouvrage': ouvrage_nom,
    }
    if not idxls or not ouvrage_nom:
        return JsonResponse({
            'success': True,
            'point_eau': point_data,
            'results': [],
            'message': "L'ouvrage et l'IDXls doivent être renseignés pour chercher les écritures DiameX.",
        })

    # Le préfiltrage évite d'analyser toute la comptabilité. La validation
    # exacte ouvrage + IDXls ci-dessous empêche d'associer un autre point.
    entries = _get_scoped_diamex_queryset(request.user).filter(
        Q(description__icontains=f'RBF{idxls}') & Q(description__icontains=ouvrage_nom),
        compte_code='621102',
    ).order_by(
        F('date_rec').desc(nulls_last=True),
        F('date_m').desc(nulls_last=True),
        '-id',
    )[:200]

    results = []
    seen = set()
    for entry in entries:
        try:
            extraction = extraire_ouvrage_et_mois_generique(
                entry.description or '',
                entry.compte_code,
            )
            items = extraction if isinstance(extraction, list) else [extraction]
            for item in items:
                if not isinstance(item, dict):
                    continue
                ouvrage_extrait = item.get('ouvrage_obj')
                idxls_extrait = str(item.get('point_eau_idxls') or '').strip()
                if not ouvrage_extrait or ouvrage_extrait.id != point_eau.ouvrage_id or idxls_extrait != idxls:
                    continue

                nom_extrait = ' '.join(str(
                    item.get('point_eau_nom_extrait') or item.get('point_eau_nom') or ''
                ).split())
                if not nom_extrait or not any(char.isalpha() for char in nom_extrait):
                    continue

                key = (entry.id, nom_extrait.casefold())
                if key in seen:
                    continue
                seen.add(key)
                date_entry = entry.date_rec or entry.date_m
                results.append({
                    'entry_id': entry.id,
                    'date': date_entry.isoformat() if date_entry else None,
                    'nom_extrait': nom_extrait,
                    'idxls': idxls_extrait,
                    'ouvrage': item.get('ouvrage_nom') or ouvrage_nom,
                    'description': entry.description or '',
                    'scan_disponible': bool(entry.scan or entry.scan_importe),
                    'scan_url': reverse('accounting:serve_scan', args=[entry.id]),
                })
                if len(results) >= 20:
                    break
            if len(results) >= 20:
                break
        except Exception:
            continue

    return JsonResponse({
        'success': True,
        'point_eau': point_data,
        'results': results,
    })


@login_required
@require_http_methods(["GET"])
def api_verification_list(request):
    """
    API pour récupérer les entrées DiameX des comptes avec filtrage par necessite_ouvrage
    Réutilise la même structure que l'API verification_autres
    """
    # Paramètres de filtrage
    search = request.GET.get('search', '').strip()
    prog_filter = request.GET.get('prog', '').strip()
    compte_filter = request.GET.get('compte', '').strip()
    source_filter = request.GET.get('source', '').strip()
    type_filter = request.GET.get('type', '').strip()  # 'entree', 'sortie', 'all'
    conformite_filter = request.GET.get('conformite', '').strip()  # 'conforme', 'non_conforme', 'all'
    mois_filter = request.GET.get('mois', '').strip()  # 'AAAA-MM' ou vide
    ouvrage_filter = request.GET.get('ouvrage', '').strip()  # 'sans_ouvrage', 'non_trouve', 'trouve', 'all'
    necessite_ouvrage = request.GET.get('necessite_ouvrage', '').strip()  # 'true' ou 'false'

    # Pagination
    page = int(request.GET.get('page', 1))
    per_page = int(request.GET.get('per_page', 50))

    # Récupérer les codes selon le filtre necessite_ouvrage
    if necessite_ouvrage == 'true':
        codes_inclus = list(_filter_comptes_by_scope(
            Compte.objects.filter(necessite_ouvrage=True),
            request.user
        ).values_list('compte', flat=True))
    else:
        codes_inclus = list(_filter_comptes_by_scope(
            Compte.objects.filter(necessite_ouvrage=False),
            request.user
        ).values_list('compte', flat=True))

    # Toujours exclure les employés et fournisseurs
    codes_employes = list(_filter_comptes_by_scope(
        Compte.objects.filter(employe_obligatoire=True),
        request.user
    ).values_list('compte', flat=True))
    codes_fournisseurs = list(_filter_comptes_by_scope(
        Compte.objects.filter(fournisseur_obligatoire=True),
        request.user
    ).values_list('compte', flat=True))
    codes_exclus = set(codes_employes + codes_fournisseurs)

    # Construire la requête - filtrer par codes_inclus et exclure employés/fournisseurs
    entries_qs = _get_scoped_diamex_queryset(request.user).filter(
        compte_code__in=codes_inclus
    ).exclude(
        compte_code__in=codes_exclus
    ).exclude(
        # Exclure les comptes techniques (transferts, comptes de tiers, etc.)
        Q(compte_code__istartswith='00BOOK') |
        Q(compte_code__istartswith='00PERS') |
        Q(compte_code__istartswith='00SPLITBOOK') |
        Q(compte_code__istartswith='00FND1')
    ).select_related('imported_by')

    # Appliquer les filtres
    if prog_filter and prog_filter != 'all':
        entries_qs = entries_qs.filter(prog=prog_filter)

    if compte_filter and compte_filter != 'all':
        entries_qs = entries_qs.filter(compte_code=compte_filter)

    if source_filter and source_filter != 'all':
        entries_qs = entries_qs.filter(fichier_source=source_filter)

    if type_filter and type_filter != 'all':
        if type_filter == 'entree':
            entries_qs = entries_qs.filter(Q(montant_in__isnull=False) | Q(montant_in__gt=0))
        elif type_filter == 'sortie':
            entries_qs = entries_qs.filter(Q(montant_out__isnull=False) | Q(montant_out__gt=0))

    if mois_filter:
        try:
            annee_m, mois_m = mois_filter.split('-')
            entries_qs = entries_qs.filter(
                date_rec__year=int(annee_m), date_rec__month=int(mois_m)
            )
        except ValueError:
            pass  # format invalide : filtre ignoré

    if search:
        entries_qs = entries_qs.filter(
            Q(description__icontains=search) |
            Q(pers__icontains=search) |
            Q(detail__icontains=search) |
            Q(compte_code__icontains=search)
        )

    # Récupérer toutes les entrées pour calculer les stats
    all_entries = entries_qs.order_by('-date_m', '-id')

    # Analyser chaque entrée (utilise la même logique que verification_autres)
    entries_analysees = []
    total_entrees = 0
    total_sorties = 0
    montant_total_entrees = 0
    montant_total_sorties = 0

    for entry in all_entries:
        # Déterminer le type
        is_entree = entry.montant_in and entry.montant_in > 0
        is_sortie = entry.montant_out and entry.montant_out > 0

        entry_type = 'Entrée' if is_entree else 'Sortie' if is_sortie else 'Inconnu'

        # Compter UNE SEULE FOIS pour les stats (même si divisé en plusieurs lignes)
        if is_entree:
            total_entrees += 1
            montant_total_entrees += float(entry.montant_in)
        elif is_sortie:
            total_sorties += 1
            montant_total_sorties += float(entry.montant_out)

        # Récupérer le compte pour vérification
        try:
            compte_obj = _filter_comptes_by_scope(
                Compte.objects.filter(compte=entry.compte_code),
                request.user
            ).first()
        except Exception:
            compte_obj = None

        # Vérification de la charte
        charte_result = None
        if compte_obj and compte_obj.charte_verification:
            charte_result = verifier_charte_compte(
                description=entry.description or '',
                charte_type=compte_obj.charte_verification,
                compte_code=entry.compte_code
            )

        # NOUVEAU : Vérifier si c'est un paiement volumétrique multi-segments (compte 707401)
        segments = []
        if entry.compte_code == '707401' and entry.description and ';' in entry.description:
            segments = diviser_paiement_volume_multi(
                entry.description,
                entry.compte_code,
                entry.montant_in if is_entree else entry.montant_out
            )

        # Si on a des segments, créer une ligne par segment
        if segments:
            for idx, segment in enumerate(segments):
                # Utiliser l'extraction déjà faite dans diviser_paiement_volume_multi
                extraction = enrichir_point_eau_par_nom_abonne(
                    entry.description or '',
                    segment['extraction'],
                )
                charte_result_segment = charte_result
                if compte_obj and compte_obj.charte_verification:
                    charte_result_segment = verifier_charte_compte(
                        description=segment['description_partielle'],
                        charte_type=compte_obj.charte_verification,
                        compte_code=entry.compte_code
                    )

                # Si un point d'eau a été trouvé, récupérer son IDxls
                point_eau_idxls_final = extraction.get('point_eau_idxls')
                if extraction.get('point_eau_obj') and hasattr(extraction.get('point_eau_obj'), 'idxls'):
                    point_eau_idxls_final = extraction.get('point_eau_obj').idxls

                entry_data = {
                    'id': f"{entry.id}_seg{idx}",  # ID unique pour chaque segment
                    'original_id': entry.id,  # ID original de la ligne DiameX
                    'segment_index': idx,
                    'is_segment': True,
                    'rec': entry.rec,
                    'compte_code': entry.compte_code,
                    'cat_libelle': compte_obj.nom_compte if compte_obj else '',
                    'prog': entry.prog,
                    'description': segment['description_partielle'],  # Description partielle
                    'detail': entry.detail or '',
                    'pers': entry.pers or '',
                    'date_m': entry.date_rec.strftime('%d/%m/%Y') if entry.date_rec else None,
                    'montant_in': segment['montant'] if is_entree else 0,  # Montant du segment
                    'montant_out': segment['montant'] if is_sortie else 0,
                    'scan': entry.scan or '',
                    'scan_disponible': bool(entry.scan or entry.scan_importe),
                    'fichier_source': entry.fichier_source or '',
                    'entry_type': entry_type,

                    # Charte verification (même résultat pour tous les segments)
                    'charte_conforme': charte_result_segment['conforme'] if charte_result_segment else None,
                    'charte_erreurs': charte_result_segment['erreurs'] if charte_result_segment else [],
                    'charte_details': charte_result_segment['details'] if charte_result_segment else {},

                    # Extraction ouvrage et mois (spécifique au segment)
                    'ouvrage_extrait_nom': extraction['ouvrage_nom'],
                    'ouvrage_extrait_id': str(extraction['ouvrage_obj'].id) if extraction['ouvrage_obj'] else None,
                    'point_eau_extrait_idxls': point_eau_idxls_final,
                    'point_eau_extrait_id': str(extraction['point_eau_obj'].id) if extraction.get('point_eau_obj') else None,
                    'point_eau_extrait_nom': (
                        extraction.get('point_eau_nom_extrait')
                        or extraction.get('point_eau_nom')
                        or (extraction['point_eau_obj'].nomabonne if extraction.get('point_eau_obj') else None)
                    ),
                    'point_eau_nom_en_base': extraction['point_eau_obj'].nomabonne if extraction.get('point_eau_obj') else None,
                    'point_eau_telephone': extraction['point_eau_obj'].numeroteleph if extraction.get('point_eau_obj') else None,
                    'mois_extrait': extraction['mois'],
                    'annee_extrait': extraction['annee'],
                    'date_str_extrait': extraction['date_str'],
                }

                entries_analysees.append(entry_data)
        else:
            # Pas de segments : traitement normal (une seule ligne)
            extraction = extraire_ouvrage_et_mois_generique(entry.description or '', entry.compte_code)

            # Si un point d'eau a été trouvé, récupérer son IDxls
            point_eau_idxls_final = extraction.get('point_eau_idxls')
            if extraction.get('point_eau_obj') and hasattr(extraction.get('point_eau_obj'), 'idxls'):
                point_eau_idxls_final = extraction.get('point_eau_obj').idxls

            entry_data = {
                'id': entry.id,
                'is_segment': False,
                'rec': entry.rec,
                'compte_code': entry.compte_code,
                'cat_libelle': compte_obj.nom_compte if compte_obj else '',
                'prog': entry.prog,
                'description': entry.description or '',
                'detail': entry.detail or '',
                'pers': entry.pers or '',
                'date_m': entry.date_rec.strftime('%d/%m/%Y') if entry.date_rec else None,
                'montant_in': float(entry.montant_in) if entry.montant_in else 0,
                'montant_out': float(entry.montant_out) if entry.montant_out else 0,
                'scan': entry.scan or '',
                'scan_disponible': bool(entry.scan or entry.scan_importe),
                'fichier_source': entry.fichier_source or '',
                'entry_type': entry_type,

                # Charte verification
                'charte_conforme': charte_result['conforme'] if charte_result else None,
                'charte_erreurs': charte_result['erreurs'] if charte_result else [],
                'charte_details': charte_result['details'] if charte_result else {},

                # Extraction ouvrage et mois
                'ouvrage_extrait_nom': extraction['ouvrage_nom'],
                'ouvrage_extrait_id': str(extraction['ouvrage_obj'].id) if extraction['ouvrage_obj'] else None,
                'point_eau_extrait_idxls': point_eau_idxls_final,
                'point_eau_extrait_id': str(extraction['point_eau_obj'].id) if extraction.get('point_eau_obj') else None,
                'point_eau_extrait_nom': (
                    extraction.get('point_eau_nom_extrait')
                    or extraction.get('point_eau_nom')
                    or (extraction['point_eau_obj'].nomabonne if extraction.get('point_eau_obj') else None)
                ),
                'point_eau_nom_en_base': extraction['point_eau_obj'].nomabonne if extraction.get('point_eau_obj') else None,
                'point_eau_telephone': extraction['point_eau_obj'].numeroteleph if extraction.get('point_eau_obj') else None,
                'mois_extrait': extraction['mois'],
                'annee_extrait': extraction['annee'],
                'date_str_extrait': extraction['date_str'],
            }

            entries_analysees.append(entry_data)

    # Calculer les stats AVANT le filtrage (pour avoir les totaux complets)
    stats_globales = {
        'total': len(entries_analysees),
        'entrees': total_entrees,
        'sorties': total_sorties,
        'montant_entrees': montant_total_entrees,
        'montant_sorties': montant_total_sorties,
        'conformes': sum(1 for e in entries_analysees if e['charte_conforme'] == True),
        'non_conformes': sum(1 for e in entries_analysees if e['charte_conforme'] == False),
        # Stats sur les ouvrages extraits (AVANT filtrage)
        'sans_ouvrage': sum(1 for e in entries_analysees if not e['ouvrage_extrait_nom']),
        'ouvrage_non_trouve': sum(1 for e in entries_analysees if e['ouvrage_extrait_nom'] and not e['ouvrage_extrait_id']),
        'ouvrage_trouve': sum(1 for e in entries_analysees if e['ouvrage_extrait_nom'] and e['ouvrage_extrait_id']),
    }

    # Filtrage par conformité (après analyse)
    if conformite_filter and conformite_filter != 'all':
        if conformite_filter == 'conforme':
            entries_analysees = [e for e in entries_analysees if e['charte_conforme'] == True]
        elif conformite_filter == 'non_conforme':
            entries_analysees = [e for e in entries_analysees if e['charte_conforme'] == False]

    # Filtrage par statut d'ouvrage (après analyse)
    if ouvrage_filter and ouvrage_filter != 'all':
        if ouvrage_filter == 'sans_ouvrage':
            # Aucun nom d'ouvrage extrait
            entries_analysees = [e for e in entries_analysees if not e['ouvrage_extrait_nom']]
        elif ouvrage_filter == 'non_trouve':
            # Nom extrait mais pas d'objet trouvé en base
            entries_analysees = [e for e in entries_analysees if e['ouvrage_extrait_nom'] and not e['ouvrage_extrait_id']]
        elif ouvrage_filter == 'trouve':
            # Nom extrait ET objet trouvé en base
            entries_analysees = [e for e in entries_analysees if e['ouvrage_extrait_nom'] and e['ouvrage_extrait_id']]

    # Pagination
    total_count = len(entries_analysees)
    total_pages = (total_count + per_page - 1) // per_page
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    entries_page = entries_analysees[start_idx:end_idx]

    # Les stats retournées sont les stats globales (non filtrées)
    stats = {
        'total': len(entries_analysees),
        'entrees': sum(1 for e in entries_analysees if e['entry_type'] == 'Entrée'),
        'sorties': sum(1 for e in entries_analysees if e['entry_type'] == 'Sortie'),
        'montant_entrees': sum(e['montant_in'] or 0 for e in entries_analysees),
        'montant_sorties': sum(e['montant_out'] or 0 for e in entries_analysees),
        'conformes': sum(1 for e in entries_analysees if e['charte_conforme'] == True),
        'non_conformes': sum(1 for e in entries_analysees if e['charte_conforme'] == False),
        'sans_ouvrage': sum(1 for e in entries_analysees if not e['ouvrage_extrait_nom']),
        'ouvrage_non_trouve': sum(1 for e in entries_analysees if e['ouvrage_extrait_nom'] and not e['ouvrage_extrait_id']),
        'ouvrage_trouve': sum(1 for e in entries_analysees if e['ouvrage_extrait_nom'] and e['ouvrage_extrait_id']),
    }

    return JsonResponse({
        'entries': entries_page,
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages,
        'total_count': total_count,
        'stats': stats
    })


@login_required
@require_http_methods(["GET"])
def verification_ouvrage_print(request):
    """
    Version imprimable des pages « avec ouvrage » / « sans ouvrage ».

    Réutilise api_verification_list (mêmes filtres, mêmes lignes, même périmètre
    utilisateur que l'écran) avec une pagination désactivée, puis groupe par Prog → Compte.
    """
    necessite = request.GET.get('necessite_ouvrage', '').strip().lower() == 'true'

    params = request.GET.copy()
    params['page'] = '1'
    params['per_page'] = '1000000'
    params['necessite_ouvrage'] = 'true' if necessite else 'false'
    request.GET = params

    response = api_verification_list(request)
    payload = json.loads(response.content)
    entries = payload.get('entries', [])

    groupes = {}
    for e in entries:
        prog = e.get('prog') or 'Sans Prog'
        compte = e.get('compte_code') or 'Sans Compte'
        e['est_entree'] = bool(e.get('montant_in'))
        groupes.setdefault(prog, {}).setdefault(compte, []).append(e)

    total = len(entries)
    conformes = sum(1 for e in entries if e.get('charte_conforme') is True)
    non_conformes = sum(1 for e in entries if e.get('charte_conforme') is False)
    stats = {
        'total': total,
        'entrees': sum(1 for e in entries if e['est_entree']),
        'sorties': sum(1 for e in entries if not e['est_entree']),
        'montant_entrees': sum(e.get('montant_in') or 0 for e in entries),
        'montant_sorties': sum(e.get('montant_out') or 0 for e in entries),
        'conformes': conformes,
        'non_conformes': non_conformes,
        'taux_conformite': int(conformes / total * 100) if total else 0,
        'sans_ouvrage': sum(1 for e in entries if not e.get('ouvrage_extrait_nom')),
        'ouvrage_non_trouve': sum(
            1 for e in entries if e.get('ouvrage_extrait_nom') and not e.get('ouvrage_extrait_id')
        ),
    }

    libelles = {'sans_ouvrage': 'Sans ouvrage', 'non_trouve': 'Ouvrage non trouvé en base',
                'trouve': 'Ouvrage trouvé en base', 'conforme': 'Conformes',
                'non_conforme': 'Non conformes', 'entree': 'Entrées', 'sortie': 'Sorties'}
    filtres_actifs = []
    for cle, label in [('mois', 'Mois'), ('prog', 'Prog'), ('compte', 'Compte'), ('source', 'Source'),
                       ('type', 'Type'), ('conformite', 'Conformité'), ('ouvrage', 'Statut ouvrage'),
                       ('search', 'Recherche')]:
        valeur = (request.GET.get(cle) or '').strip()
        if valeur and valeur != 'all':
            filtres_actifs.append((label, libelles.get(valeur, valeur)))

    context = {
        'title': 'Vérification - Comptes avec Ouvrage' if necessite else 'Vérification - Comptes sans Ouvrage',
        'necessite_ouvrage': necessite,
        'groupes': groupes,
        'stats': stats,
        'filtres_actifs': filtres_actifs,
        'date_impression': datetime.now(),
        'erreur': payload.get('error') if response.status_code != 200 else None,
    }
    return render(request, 'accounting/verification_ouvrage_print.html', context)
