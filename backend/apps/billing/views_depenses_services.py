"""
APIs pour la gestion des dépenses de services
"""
from decimal import Decimal, InvalidOperation
import unicodedata

import json

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.employees.permissions import has_admin_compta_access, is_directeur_poste
from .models import DepenseService, DepenseServiceLigne, Fournisseur


FORBIDDEN_DESIGNATION_LABELS = {
    'salaire',
    'indemnite',
}


def _normalize_designation_label(value):
    normalized = unicodedata.normalize('NFKD', str(value or ''))
    normalized = ''.join(ch for ch in normalized if not unicodedata.combining(ch))
    return ' '.join(normalized.strip().lower().split())


def _validate_designation(designation, line_index=None):
    if not designation:
        if line_index is None:
            raise ValueError("La designation / motif est obligatoire")
        raise ValueError(f"La designation est obligatoire pour la ligne {line_index}")

    if _normalize_designation_label(designation) in FORBIDDEN_DESIGNATION_LABELS:
        if line_index is None:
            raise ValueError("Les designations 'Salaire' et 'Indemnite' sont interdites")
        raise ValueError(f"Les designations 'Salaire' et 'Indemnite' sont interdites pour la ligne {line_index}")


def _parse_decimal(value):
    if value in (None, ''):
        return Decimal('0')
    try:
        return Decimal(str(value).replace(',', '.'))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Valeur monétaire invalide")


def _parse_payload(request):
    if not request.body:
        return {}

    try:
        return json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        raise ValueError("Payload JSON invalide")


def _default_signataire(request):
    employe = getattr(request.user, 'employe', None)
    if employe:
        full_name = " ".join(
            filter(
                None,
                [getattr(employe, 'prenom', ''), getattr(employe, 'nom', '')]
            )
        ).strip()
        if full_name:
            return full_name
        if getattr(employe, 'surnom', None):
            return employe.surnom

    return request.user.get_username()


def _can_sign_first(user):
    return bool(getattr(user, 'is_superuser', False) or has_admin_compta_access(user))


def _can_sign_second(user):
    return bool(getattr(user, 'is_superuser', False) or is_directeur_poste(user))


def _can_manage_depenses(user):
    return bool(user and getattr(user, 'is_authenticated', False))


def _serialize_depense(depense, user=None):
    can_sign_1 = False
    can_sign_2 = False
    can_manage = False
    if user is not None:
        can_sign_1 = _can_sign_first(user)
        can_sign_2 = _can_sign_second(user)
        can_manage = _can_manage_depenses(user)

    lignes = list(getattr(depense, '_prefetched_objects_cache', {}).get('lignes', []) or depense.lignes.all())
    serialized_lignes = [
        {
            'id': str(ligne.id),
            'designation': ligne.designation,
            'unite': ligne.unite,
            'prix_unitaire': float(ligne.prix_unitaire),
            'montant': float(ligne.montant),
            'total': float(ligne.total),
            'ordre': ligne.ordre,
        }
        for ligne in lignes
    ]
    if not serialized_lignes:
        serialized_lignes = [{
            'id': '',
            'designation': depense.designation,
            'unite': depense.unite,
            'prix_unitaire': float(depense.prix_unitaire),
            'montant': float(depense.montant),
            'total': float(depense.total),
            'ordre': 0,
        }]

    return {
        'id': str(depense.id),
        'date_facture': depense.date_facture.isoformat(),
        'fournisseur_id': str(depense.fournisseur_id),
        'fournisseur_nom': depense.fournisseur.nom_fournisseur if depense.fournisseur else '',
        'designation': depense.designation,
        'unite': depense.unite,
        'prix_unitaire': float(depense.prix_unitaire),
        'montant': float(depense.montant),
        'total': float(depense.total),
        'total_lettres': depense.total_lettres,
        'statut': depense.statut,
        'signataire_1': depense.signataire_1 or '',
        'date_signature_1': depense.date_signature_1.isoformat() if depense.date_signature_1 else '',
        'signataire_2': depense.signataire_2 or '',
        'date_signature_2': depense.date_signature_2.isoformat() if depense.date_signature_2 else '',
        'created_at': depense.created_at.isoformat() if depense.created_at else '',
        'updated_at': depense.updated_at.isoformat() if depense.updated_at else '',
        'lignes': serialized_lignes,
        'nb_lignes': len(serialized_lignes),
        'can_sign_1': can_sign_1,
        'can_sign_2': can_sign_2,
        'can_manage': can_manage,
    }


def _build_payload(data):
    date_facture = parse_date(data.get('date_facture'))
    if not date_facture:
        raise ValueError("Date de facture invalide")

    try:
        fournisseur = Fournisseur.objects.get(pk=data.get('fournisseur_id'))
    except Fournisseur.DoesNotExist:
        raise ValueError("Fournisseur introuvable")
    except TypeError:
        raise ValueError("Fournisseur invalide")

    lignes = data.get('lignes') or []
    if not isinstance(lignes, list):
        raise ValueError("Les lignes de facture sont invalides")

    cleaned_lignes = []
    for index, ligne in enumerate(lignes, start=1):
        if not isinstance(ligne, dict):
            raise ValueError(f"Ligne {index} invalide")
        designation = (ligne.get('designation') or '').strip()
        unite = (ligne.get('unite') or '').strip()
        prix_unitaire = _parse_decimal(ligne.get('prix_unitaire'))
        montant = _parse_decimal(ligne.get('montant'))
        _validate_designation(designation, line_index=index)
        if not unite:
            raise ValueError(f"L'unit? est obligatoire pour la ligne {index}")
        if prix_unitaire <= 0:
            raise ValueError(f"Le prix unitaire doit ?tre sup?rieur ? 0 pour la ligne {index}")
        if montant <= 0:
            raise ValueError(f"Le montant doit ?tre sup?rieur ? 0 pour la ligne {index}")
        cleaned_lignes.append({
            'designation': designation,
            'unite': unite,
            'prix_unitaire': prix_unitaire,
            'montant': montant,
            'ordre': index - 1,
        })

    if not cleaned_lignes:
        designation = (data.get('designation') or '').strip()
        unite = (data.get('unite') or '').strip()
        prix_unitaire = _parse_decimal(data.get('prix_unitaire'))
        montant = _parse_decimal(data.get('montant'))
        _validate_designation(designation)
        if not unite:
            raise ValueError("L'unit? est obligatoire")
        if prix_unitaire <= 0:
            raise ValueError("Le prix unitaire doit ?tre sup?rieur ? 0")
        if montant <= 0:
            raise ValueError("Le montant doit ?tre sup?rieur ? 0")
        cleaned_lignes.append({
            'designation': designation,
            'unite': unite,
            'prix_unitaire': prix_unitaire,
            'montant': montant,
            'ordre': 0,
        })

    first_line = cleaned_lignes[0]
    return {
        'date_facture': date_facture,
        'fournisseur': fournisseur,
        'designation': first_line['designation'],
        'unite': first_line['unite'],
        'prix_unitaire': first_line['prix_unitaire'],
        'montant': first_line['montant'],
        'lignes': cleaned_lignes,
    }


def _replace_depense_lignes(depense, lignes):
    depense.lignes.all().delete()
    created_lignes = []
    for ligne in lignes:
        prix_unitaire = ligne['prix_unitaire']
        montant = ligne['montant']
        created_lignes.append(DepenseServiceLigne(
            depense_service=depense,
            designation=ligne['designation'],
            unite=ligne['unite'],
            prix_unitaire=prix_unitaire,
            montant=montant,
            total=prix_unitaire * montant,
            ordre=ligne['ordre'],
        ))
    if created_lignes:
        DepenseServiceLigne.objects.bulk_create(created_lignes)
    depense.refresh_from_db()
    depense.recalculate_from_lignes()
    depense.save(update_fields=['designation', 'unite', 'prix_unitaire', 'montant', 'total', 'total_lettres', 'updated_at'])


@login_required
def depenses_services_workflow(request):
    organisation_payeur = ''
    try:
        employe = getattr(request.user, 'employe', None)
        base = getattr(employe, 'base', None)
        organisation = getattr(base, 'organisation', None)
        organisation_payeur = getattr(organisation, 'nom_organisation', '') or ''
    except Exception:
        organisation_payeur = ''

    return render(request, 'billing/depenses_services_workflow.html', {
        'title': 'Workflow depenses services',
        'organisation_payeur': organisation_payeur,
    })


@login_required
@require_http_methods(["GET"])
def api_depenses_services_list(request):
    try:
        statut = (request.GET.get('statut') or '').strip()
        fournisseur_id = (request.GET.get('fournisseur_id') or '').strip()
        search = (request.GET.get('search') or '').strip()
        from_date = parse_date(request.GET.get('from_date', ''))
        to_date = parse_date(request.GET.get('to_date', ''))

        page = int(request.GET.get('page', '1') or 1)
        per_page = int(request.GET.get('per_page', '50') or 50)
        page = max(1, page)
        per_page = min(max(1, per_page), 200)

        qs = DepenseService.objects.select_related('fournisseur').prefetch_related('lignes').all().order_by('-date_facture', '-created_at')

        if statut:
            qs = qs.filter(statut=statut)
        if fournisseur_id:
            qs = qs.filter(fournisseur_id=fournisseur_id)
        if from_date:
            qs = qs.filter(date_facture__gte=from_date)
        if to_date:
            qs = qs.filter(date_facture__lte=to_date)
        if search:
            qs = qs.filter(
                Q(designation__icontains=search)
                | Q(unite__icontains=search)
                | Q(fournisseur__nom_fournisseur__icontains=search)
            )

        paginator = Paginator(qs, per_page)
        page_obj = paginator.get_page(page)

        depenses = [_serialize_depense(depense, request.user) for depense in page_obj.object_list]

        stats = qs.aggregate(
            total_montant=Sum('total'),
            total_brouillons=Sum('total', filter=Q(statut=DepenseService.STATUT_BROUILLON)),
            total_en_attente=Sum('total', filter=Q(statut=DepenseService.STATUT_ATTENTE_SIGNATURE)),
            total_valides=Sum('total', filter=Q(statut=DepenseService.STATUT_VALIDE)),
        )

        return JsonResponse({
            'success': True,
            'depenses': depenses,
            'permissions': {
                'can_manage': _can_manage_depenses(request.user),
                'can_sign_1': _can_sign_first(request.user),
                'can_sign_2': _can_sign_second(request.user),
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
            },
            'stats': {
                'total_records': paginator.count,
                'total_montant': float(stats.get('total_montant') or 0),
                'total_brouillons': float(stats.get('total_brouillons') or 0),
                'total_en_attente': float(stats.get('total_en_attente') or 0),
                'total_valides': float(stats.get('total_valides') or 0),
            },
            'search': search,
            'statut': statut,
            'fournisseur_id': fournisseur_id
        })

    except ValueError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_depenses_services_create(request):
    try:
        if not _can_manage_depenses(request.user):
            return JsonResponse({'success': False, 'error': 'Acces refuse'}, status=403)

        data = _parse_payload(request)
        payload = _build_payload(data)
        lignes = payload.pop('lignes', [])

        with transaction.atomic():
            depense = DepenseService.objects.create(**payload)
            _replace_depense_lignes(depense, lignes)
        return JsonResponse({
            'success': True,
            'message': 'Dépense créée avec succès',
            'depense': _serialize_depense(depense, request.user),
        })
    except ValueError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_depenses_services_update(request, depense_id):
    try:
        if not _can_manage_depenses(request.user):
            return JsonResponse({'success': False, 'error': 'Acces refuse'}, status=403)

        depense = get_object_or_404(DepenseService, pk=depense_id)
        if depense.statut == DepenseService.STATUT_VALIDE:
            return JsonResponse({'success': False, 'error': 'Impossible de modifier une dépense validée'}, status=400)

        data = _parse_payload(request)
        payload = _build_payload(data)
        lignes = payload.pop('lignes', [])

        with transaction.atomic():
            for key, value in payload.items():
                setattr(depense, key, value)
            depense.save()
            _replace_depense_lignes(depense, lignes)

        return JsonResponse({
            'success': True,
            'message': 'Dépense modifiée avec succès',
            'depense': _serialize_depense(depense, request.user),
        })
    except ValueError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
@csrf_exempt
@require_http_methods(["DELETE"])
def api_depenses_services_delete(request, depense_id):
    try:
        if not _can_manage_depenses(request.user):
            return JsonResponse({'success': False, 'error': 'Acces refuse'}, status=403)

        depense = get_object_or_404(DepenseService, pk=depense_id)
        if depense.statut == DepenseService.STATUT_VALIDE:
            return JsonResponse({'success': False, 'error': 'Impossible de supprimer une dépense validée'}, status=400)

        depense.delete()
        return JsonResponse({'success': True, 'message': 'Dépense supprimée avec succès'})
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_depenses_services_signer(request, depense_id):
    try:
        depense = get_object_or_404(DepenseService, pk=depense_id)
        data = _parse_payload(request)

        try:
            signature_index = int(data.get('signature_index'))
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'error': 'signature_index doit être 1 ou 2'}, status=400)

        if signature_index not in (1, 2):
            return JsonResponse({'success': False, 'error': 'signature_index doit être 1 ou 2'}, status=400)

        if signature_index == 1 and not _can_sign_first(request.user):
            return JsonResponse({'success': False, 'error': 'Acces refuse pour la premiere signature'}, status=403)
        if signature_index == 2 and not _can_sign_second(request.user):
            return JsonResponse({'success': False, 'error': 'Acces reserve aux Directeurs pour la deuxieme signature'}, status=403)

        signataire = (data.get('signataire') or '').strip() or _default_signataire(request)
        date_signature = parse_date(data.get('date_signature')) or timezone.localdate()

        if signature_index == 1:
            if depense.statut == DepenseService.STATUT_VALIDE:
                return JsonResponse({'success': False, 'error': 'Dépense déjà validée'}, status=400)
            depense.signataire_1 = signataire
            depense.date_signature_1 = date_signature
            if depense.statut == DepenseService.STATUT_BROUILLON:
                depense.statut = DepenseService.STATUT_ATTENTE_SIGNATURE

            return_message = 'Première signature enregistrée'

        else:
            if depense.statut != DepenseService.STATUT_ATTENTE_SIGNATURE:
                return JsonResponse({'success': False, 'error': 'La deuxième signature nécessite la première signature'}, status=400)
            if not depense.signataire_1:
                return JsonResponse({'success': False, 'error': 'La première signature est manquante'}, status=400)

            depense.signataire_2 = signataire
            depense.date_signature_2 = date_signature
            depense.statut = DepenseService.STATUT_VALIDE
            return_message = 'Deuxième signature enregistrée'

        depense.save()

        return JsonResponse({
            'success': True,
            'message': return_message,
            'depense': _serialize_depense(depense, request.user),
        })
    except ValueError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_depenses_services_total_lettres(request):
    try:
        data = _parse_payload(request)
        total = _parse_decimal(data.get('total'))

        return JsonResponse({
            'success': True,
            'total': float(total),
            'total_lettres': DepenseService.convertir_montant_en_lettres(total),
        })
    except ValueError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)
