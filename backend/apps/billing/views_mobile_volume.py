"""Native offline workflow. Quotes are computed by the existing billing engine.

Every mutation is atomic, scoped, version checked and durably idempotent.
The client can queue work offline; only a server receipt confirms posting.
"""
import hashlib
import json
import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.core.views_mobile_auth import mobile_auth_required
from apps.accounting.models import BaseDiameX, DiameXTemporaire
from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique
from apps.accounting.views_verification_ouvrages import diviser_paiement_volume_multi
from apps.organization.models import Ouvrage, Journal
from .models import Releve, MobileVolumeOperation, MobileVolumeInvoiceSnapshot
from .views_facturation import (
    calculer_montant_releve, _get_allowed_ouvrage_ids, _get_user_organisation_id,
    _get_first_attr, _get_ouvrage_responsable_contact,
)
from .services_compteurs_abonnes import serialize_segments
from apps.organization.models import Organisation
from .views_encaissement import _build_facture_qr_payload, _get_releve_facturation_period


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str,
                                     separators=(',', ':')).encode()).hexdigest()


def available_journals(user):
    employee = getattr(user, 'employe', None)
    values = [{'code': '00PERS', 'nom': 'Caisse personnelle'}]
    if employee and employee.base_id:
        values.extend({'code': journal.code, 'nom': journal.nom_journal}
                      for journal in Journal.objects.filter(base_id=employee.base_id).exclude(
                          code='00PERS').order_by('code') if journal.code)
    return values


def invoice_data(releve):
    calculation = calculer_montant_releve(releve)
    amount = releve.montant
    locked = bool(releve.facture_imprimee or releve.datepaiement or releve.numeroDiameX)
    if not locked and calculation.get('success'):
        amount = Decimal(str(calculation['montant_total']))
    detail = calculation.get('detail', {})
    if locked:
        frozen = MobileVolumeInvoiceSnapshot.objects.filter(releve_id=releve.pk).first()
        if frozen and Decimal(frozen.data['montant']) == amount:
            detail = frozen.data.get('detail', {})
        elif not calculation.get('success') or Decimal(str(calculation['montant_total'])) != amount:
            # Historic invoice amounts remain authoritative; never invent a
            # breakdown using today's tariff for an old printed invoice.
            detail = {}
    year, month = _get_releve_facturation_period(releve)
    data = {
        # Tant que la facture n'a pas de numero_facture assigne (avant impression),
        # ne jamais afficher l'identifiant technique (UUID) a l'agent terrain.
        'id': str(releve.pk), 'numero': releve.numero_facture or 'Sans numéro',
        'point_id': str(releve.point_eau_id), 'abonne': releve.point_eau.nomabonne or '',
        'idxls': str(getattr(releve.point_eau, 'idxls', '') or ''),
        'type_pe': getattr(releve.point_eau.type_point_eau, 'nom_type', '') if getattr(releve.point_eau, 'type_point_eau', None) else '',
        'ouvrage_id': str(releve.point_eau.ouvrage_id),
        'ouvrage': releve.point_eau.ouvrage.nom_ouvrage,
        'mois': f'{year:04d}-{month:02d}', 'date_releve': str(releve.datereleve),
        'ancien_index': str(releve.ancienindex), 'nouvel_index': str(releve.nouvelindex),
        'montant': format(amount.quantize(Decimal('0.01')), 'f') if amount is not None else None,
        'detail': detail,
        'erreur_calcul': '' if calculation.get('success') else calculation.get('error', ''),
        'validee': releve.montant is not None and releve.montant == amount,
        'imprimee': releve.facture_imprimee,
        'encaissee': releve.datepaiement is not None,
        'pointee': bool(str(releve.numeroDiameX or '').strip()),
        'numero_diamex': releve.numeroDiameX or '',
        'base_diamex': releve.baseDiameX or '',
        'qr': _build_facture_qr_payload(releve),
    }
    # Payment/print status is checked separately. A queued validation followed
    # by a payment must still share the same quote fingerprint.
    data['version'] = digest({key: data[key] for key in (
        'id', 'montant', 'detail', 'ancien_index', 'nouvel_index', 'mois',
    )})
    return data


def print_fields(releve, responsable):
    """Champs d'impression au format de api_calculer_factures (page web
    Facturation), pour que le client Desktop imprime la facture avec le meme
    gabarit static/js/print_factures_a4.js. Hors empreinte `version`."""
    point = releve.point_eau
    year, month = _get_releve_facturation_period(releve)
    return {
        'releve_id': str(releve.pk),
        'ouvrage_id': str(point.ouvrage_id),
        'ouvrage_nom': point.ouvrage.nom_ouvrage if point.ouvrage else '',
        'responsable_ouvrage_nom': responsable['nom'],
        'responsable_ouvrage_telephone': responsable['telephone'],
        'numero_facture': releve.numero_facture or '',
        'point_eau': point.code_point_eau or point.nomabonne,
        'abonne': releve.abonne or 'N/A',
        'idxls': point.idxls or '',
        'ancienindex': float(releve.ancienindex) if releve.ancienindex is not None else None,
        'nouvelindex': float(releve.nouvelindex) if releve.nouvelindex is not None else None,
        'parcelle': point.parcelle.reference_parcelle if point.parcelle else 'N/A',
        'type_point_eau': point.type_point_eau.nom_type if point.type_point_eau else 'N/A',
        'volume_facture': float(releve.volume_facture or 0),
        'segments_compteur': serialize_segments(releve),
        'qr_payload': _build_facture_qr_payload(releve, year, month),
    }


def organisation_print_data(request):
    """Meme en-tete que workflow_facturation (organisationData de la page web)."""
    organisation_id = _get_user_organisation_id(request.user)
    organisation = Organisation.objects.filter(id=organisation_id).first() if organisation_id else None
    logo_url = ''
    if organisation and getattr(organisation, 'logo', None):
        try:
            logo_url = request.build_absolute_uri(organisation.logo.url)
        except Exception:
            logo_url = ''
    employee = getattr(request.user, 'employe', None)
    base = getattr(employee, 'base', None) if employee else None
    return {
        'nom': _get_first_attr(organisation, 'nom_organisation', 'nom', 'organisation', 'designation',
                               default=str(organisation) if organisation else 'HYDRIA'),
        'logo_url': logo_url,
        'nif': _get_first_attr(organisation, 'nif', 'NIF', default=''),
        'stat': _get_first_attr(organisation, 'stat', 'STAT', default=''),
        'base': getattr(base, 'nom_base', '') or '',
        'base_telephone': getattr(base, 'telephone', '') or '',
        'adresse': _get_first_attr(organisation, 'adresse1', 'adresse', 'address', default=''),
    }


def entry_segments(entry):
    segments = diviser_paiement_volume_multi(
        entry.description, entry.compte_code, entry.montant_in or 0
    ) if ';' in (entry.description or '') else []
    if not segments:
        segments = [{'extraction': extraire_ouvrage_et_mois_generique(
            entry.description or '', entry.compte_code), 'montant': entry.montant_in or 0}]
    grouped = {}
    for segment in segments:
        extraction = segment.get('extraction') or {}
        ouvrage = extraction.get('ouvrage_obj')
        year, month = extraction.get('annee'), extraction.get('mois')
        if ouvrage and year and month:
            key = (str(ouvrage.pk), f'{int(year):04d}-{int(month):02d}')
            grouped[key] = grouped.get(key, Decimal('0')) + Decimal(str(segment['montant']))
    return grouped


@mobile_auth_required
@require_GET
def bootstrap(request):
    allowed = _get_allowed_ouvrage_ids(request.user)
    ouvrages = Ouvrage.objects.filter(id__in=allowed).order_by('nom_ouvrage')
    ouvrage_id, period = request.GET.get('ouvrage_id'), request.GET.get('mois')
    if not ouvrage_id:
        return JsonResponse({'success': True, 'ouvrages': [
            {'id': str(o.pk), 'nom': o.nom_ouvrage} for o in ouvrages]})
    try:
        ouvrage_id = str(uuid.UUID(ouvrage_id))
        start = date.fromisoformat(period + '-01')
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Ouvrage ou mois invalide'}, status=400)
    if not ouvrages.filter(pk=ouvrage_id).exists():
        return JsonResponse({'success': False, 'error': 'Ouvrage non autorisé'}, status=403)
    previous = start - timedelta(days=1)
    invoices = Releve.objects.filter(
        point_eau__ouvrage_id=ouvrage_id, datereleve__year=previous.year,
        datereleve__month=previous.month,
    ).select_related('point_eau__ouvrage', 'point_eau__type_point_eau',
                     'point_eau__parcelle').order_by('id')
    responsable = _get_ouvrage_responsable_contact(ouvrage_id)
    factures = []
    for releve in invoices:
        data = invoice_data(releve)
        data['impression'] = print_fields(releve, responsable)
        factures.append(data)
    entries = []
    # Date of receipt may be in a later accounting year. Do not restrict to
    # the invoice year. Extraction, not a client-supplied amount, scopes rows.
    for entry in BaseDiameX.objects.filter(compte_code='707401').iterator(chunk_size=500):
        amount = entry_segments(entry).get((ouvrage_id, period))
        if amount is not None and amount > 0 and entry.id_access is not None and entry.prog:
            pointed = Releve.objects.filter(point_eau__ouvrage_id=ouvrage_id,
                datereleve__year=previous.year, datereleve__month=previous.month,
                numeroDiameX=str(entry.id_access), baseDiameX=entry.prog).exists()
            entries.append({'id': str(entry.pk), 'numero': str(entry.id_access),
                            'base': entry.prog, 'montant': str(amount),
                            'date': str(entry.date_rec or ''), 'pointee': pointed,
                            'description': entry.description or ''})
    return JsonResponse({'success': True, 'ouvrage_id': ouvrage_id, 'mois': period,
                         'generated_at': timezone.now().isoformat(),
                         'factures': factures, 'diamex': entries,
                         'journaux': available_journals(request.user),
                         'impression': {'organisation': organisation_print_data(request)}})


class WorkflowConflict(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise WorkflowConflict(message)


@csrf_exempt
@mobile_auth_required
@require_POST
def sync_operation(request):
    try:
        payload = json.loads(request.body)
        require(isinstance(payload, dict), 'Objet JSON attendu')
        operation_id = uuid.UUID(payload['local_uuid'])
        action = payload['action']
        items = payload['factures']
        require(action in ('validate', 'printed', 'collect', 'point'), 'Action inconnue')
        require(isinstance(items, list) and 0 < len(items) <= 500, 'Sélection invalide (1 à 500 factures)')
        require(all(isinstance(item, dict) and isinstance(item.get('version'), str) for item in items),
                'Version de facture manquante')
        ids = [str(uuid.UUID(item['id'])) for item in items]
        require(len(set(ids)) == len(ids), 'Factures en doublon')
        payload_hash = digest(payload)
        with transaction.atomic():
            # Serializes UUID retries for one account, including concurrent
            # requests arriving before the first receipt exists.
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            receipt = MobileVolumeOperation.objects.filter(pk=operation_id).first()
            if receipt:
                require(receipt.user_id == request.user.pk and receipt.payload_hash == payload_hash,
                        'Identifiant déjà utilisé pour une autre opération')
                return JsonResponse(receipt.response)
            allowed = _get_allowed_ouvrage_ids(request.user)
            records = list(Releve.objects.select_for_update().filter(
                pk__in=ids, point_eau__ouvrage_id__in=allowed).order_by('pk'))
            require(len(records) == len(ids), 'Facture introuvable ou non autorisée')
            expected = {identity: item['version'] for identity, item in zip(ids, items)}
            quotes = {str(r.pk): invoice_data(r) for r in records}
            for record in records:
                quote = quotes[str(record.pk)]
                require(quote['version'] == expected[str(record.pk)],
                        'Conflit : le relevé ou le tarif a changé. Actualisez et vérifiez la facture.')
                require(quote['montant'] is not None, 'Montant indisponible')
                require(Decimal(quote['montant']).is_finite() and Decimal(quote['montant']) >= 0,
                        'Montant de facture invalide')
            total = sum(Decimal(quotes[str(r.pk)]['montant']) for r in records)
            result = {'success': True, 'local_uuid': str(operation_id), 'action': action}
            if action == 'validate':
                for record in records:
                    quote = quotes[str(record.pk)]
                    require(not quote['erreur_calcul'], quote['erreur_calcul'])
                    if record.montant != Decimal(quote['montant']):
                        require(not record.facture_imprimee and not record.datepaiement and not record.numeroDiameX,
                                'Facture verrouillée')
                        record.montant = Decimal(quote['montant'])
                        record.save(update_fields=['montant'])
                    if not record.facture_imprimee and not record.datepaiement and not record.numeroDiameX:
                        MobileVolumeInvoiceSnapshot.objects.update_or_create(releve=record, defaults={'data': quote})
            elif action == 'printed':
                for record in records:
                    require(record.montant == Decimal(quotes[str(record.pk)]['montant']),
                            'Validez la facture avant de confirmer son impression')
                    if not record.facture_imprimee:
                        MobileVolumeInvoiceSnapshot.objects.update_or_create(releve=record, defaults={'data': quotes[str(record.pk)]})
                        record.facture_imprimee = True
                        record.date_impression = timezone.now()
                        record.save(update_fields=['facture_imprimee', 'date_impression'])
            else:
                groups = {(q['ouvrage_id'], q['mois']) for q in quotes.values()}
                require(len(groups) == 1, 'Sélectionnez un seul ouvrage et un seul mois')
                require(total > 0, 'Le montant doit être positif')
                for record in records:
                    require(record.montant == Decimal(quotes[str(record.pk)]['montant']),
                            'Facture non validée sur le serveur')
                    require(not record.numeroDiameX, 'Facture déjà pointée')
                if action == 'collect':
                    payment_date = date.fromisoformat(payload['date'])
                    require(payment_date <= timezone.localdate(), 'Date future interdite')
                    employee = getattr(request.user, 'employe', None)
                    require(employee and employee.base, 'Employé et base requis pour encaisser')
                    journal_code = payload.get('journal_code', '00PERS')
                    require(journal_code in {j['code'] for j in available_journals(request.user)},
                            'Journal non autorisé pour cette base')
                    for record in records:
                        require(record.datepaiement is None and not record.montantpaye,
                                'Conflit : facture déjà encaissée')
                    quote = next(iter(quotes.values()))
                    description = f'Paiement au volume {quote["ouvrage"]} {quote["mois"][5:]}/{quote["mois"][:4]}'
                    require(len(description) <= 255, 'Nom ouvrage trop long pour la description DiameX')
                    line = DiameXTemporaire.objects.create(
                        type_transaction='recette', journal_code=journal_code, date_rec=payment_date,
                        description=description,
                        montant_in=total, montant_out=0, compte_code='707401',
                        pers=(employee.nom or '')[:50] if journal_code == '00PERS' else None,
                        activ=str(employee.base.volet or '')[:50],
                        prog=str(employee.base.prog_diamex or employee.base.nom_base)[:50],
                        detail=f'MOBILE:{operation_id}'[:50], info='hydria paiement facture au volume',
                        statut='en_attente', created_by=employee,
                    )
                    for record in records:
                        MobileVolumeInvoiceSnapshot.objects.update_or_create(
                            releve=record, defaults={'data': quotes[str(record.pk)]})
                        record.statut = 'paye'
                        record.datepaiement = payment_date
                        record.montantpaye = record.montant
                        record.save(update_fields=['statut', 'datepaiement', 'montantpaye'])
                    result['diamex_temporaire_id'] = line.pk
                else:
                    entry = BaseDiameX.objects.select_for_update().get(pk=int(payload['diamex_id']))
                    require(entry.compte_code == '707401' and entry.id_access is not None and entry.prog,
                            'Écriture DiameX invalide')
                    group = next(iter(groups))
                    segment_amount = entry_segments(entry).get(group)
                    require(segment_amount is not None, 'Écriture hors ouvrage ou période')
                    # Protect the same segment against a second batch on another device.
                    existing = Releve.objects.filter(numeroDiameX=str(entry.id_access), baseDiameX=entry.prog,
                        point_eau__ouvrage_id=group[0])
                    already = any('%04d-%02d' % _get_releve_facturation_period(r) == group[1] for r in existing)
                    require(not already and total == segment_amount,
                            'Montant différent ou segment DiameX déjà pointé')
                    for record in records:
                        record.numeroDiameX = str(entry.id_access)
                        record.baseDiameX = entry.prog
                        record.save(update_fields=['numeroDiameX', 'baseDiameX'])
            result['factures'] = [invoice_data(r) for r in records]
            MobileVolumeOperation.objects.create(id=operation_id, user=request.user,
                                                 payload_hash=payload_hash, response=result)
            return JsonResponse(result)
    except WorkflowConflict as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=409)
    except (ValueError, TypeError, KeyError, BaseDiameX.DoesNotExist):
        return JsonResponse({'success': False, 'error': 'Données invalides ou écriture introuvable'}, status=400)
