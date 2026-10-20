"""
API mobile d'ecriture pour le workflow Volumetrique (app Android Hydria
Terrain) - a la suite de api_mobile_volume_bootstrap (lecture).

Chaque action reprend la logique exacte des vues web equivalentes,
adaptee au contrat mobile (payload {local_uuid, action, factures, ...}) :
  - "validate" -> comme api_valider_factures (enregistre Releve.montant)
  - "printed"  -> comme api_marquer_factures_imprimees (facture_imprimee)
  - "collect"  -> comme api_valider_encaissement_groupe (cree une ligne
                  DiameXTemporaire "recette", marque les releves payes)

Le pointage DiameX ("point") n'est pas traite ici (voir la note dans
views_mobile_volume_bootstrap.py) : une action "point" recoit une erreur
explicite plutot qu'un comportement approximatif.
"""
import json
from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.core.views_mobile_auth import mobile_auth_required
from apps.billing.models import Releve
from apps.billing.views_facturation import _get_allowed_ouvrage_ids
from apps.billing.views_encaissement import _get_releve_facturation_period
from apps.accounting.models import DiameXTemporaire

from apps.billing.views_mobile_volume_bootstrap import _version_of, serialize_mobile_facture

ACTIONS_SUPPORTEES = {'validate', 'printed', 'collect'}


def _mois_facture_str(releve):
    """
    Reconstruit le "mois" (AAAA-MM) d'un releve pour le renvoyer dans la
    reponse de synchro - sans ca, VolumeRepository.accept() ecraserait le
    cache local de la facture en perdant ce champ (utilise ensuite par
    VolumeWorkflow.recap et l'affichage), meme si l'action elle-meme n'a
    rien a voir avec le mois.
    """
    annee, mois = _get_releve_facturation_period(releve)
    return f'{annee:04d}-{mois:02d}' if annee and mois else ''


@mobile_auth_required
@csrf_exempt
@require_http_methods(["POST"])
def api_mobile_volume_sync(request):
    try:
        data = json.loads(request.body or '{}')
        local_uuid = data.get('local_uuid')
        action = data.get('action')
        factures_payload = data.get('factures') or []
        ids = [f.get('id') for f in factures_payload if f.get('id')]

        if not local_uuid or not action or not ids:
            return JsonResponse({'success': False, 'error': 'Parametres manquants'}, status=400)

        if action == 'point':
            return JsonResponse({
                'success': False,
                'error': "Le pointage DiameX depuis le mobile n'est pas encore disponible.",
            }, status=400)

        if action not in ACTIONS_SUPPORTEES:
            return JsonResponse({'success': False, 'error': f"Action inconnue : {action}"}, status=400)

        allowed_ouvrage_ids = _get_allowed_ouvrage_ids(request.user)
        releves = list(
            Releve.objects.filter(id__in=ids, point_eau__ouvrage_id__in=allowed_ouvrage_ids)
            .select_related('point_eau', 'point_eau__type_point_eau', 'point_eau__ouvrage')
        )
        if len(releves) != len(ids):
            return JsonResponse({'success': False, 'error': 'Facture introuvable ou non autorisee'}, status=404)

        # Verrou optimiste : si la version vue par le mobile ne correspond
        # plus a l'etat serveur actuel, quelque chose d'autre a deja
        # modifie cette facture entre-temps (web, autre telephone) ->
        # conflit explicite plutot qu'ecrasement silencieux d'argent.
        expected_versions = {f.get('id'): f.get('version') for f in factures_payload}
        conflits = [r for r in releves if expected_versions.get(str(r.id)) != _version_of(r)]
        if conflits:
            return JsonResponse({
                'success': False,
                'error': 'Une ou plusieurs factures ont ete modifiees depuis le telechargement. '
                         'Reactualisez avant de reessayer.',
                'factures': [serialize_mobile_facture(r, _mois_facture_str(r)) for r in releves],
            }, status=409)

        diamex_temporaire_id = None

        if action == 'validate':
            montants = {f.get('id'): f.get('montant') for f in factures_payload}
            for releve in releves:
                montant = montants.get(str(releve.id))
                if montant is None:
                    continue
                releve.montant = Decimal(str(montant))
                releve.save(update_fields=['montant'])

        elif action == 'printed':
            for releve in releves:
                if not releve.facture_imprimee:
                    releve.facture_imprimee = True
                    releve.date_impression = timezone.now()
                    releve.save(update_fields=['facture_imprimee', 'date_impression'])

        elif action == 'collect':
            date_str = data.get('date')
            journal_code = data.get('journal_code') or '00PERS'
            if not date_str:
                return JsonResponse({'success': False, 'error': "Date d'encaissement requise"}, status=400)
            try:
                date_encaissement = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({'success': False, 'error': 'Format de date invalide (attendu AAAA-MM-JJ)'}, status=400)

            releves_valides = [
                r for r in releves
                if r.montant is not None and not r.datepaiement and not r.numeroDiameX
            ]
            if not releves_valides:
                return JsonResponse({'success': False, 'error': 'Aucune facture valide a encaisser'}, status=400)

            ouvrage_ids = {r.point_eau.ouvrage_id for r in releves_valides if r.point_eau}
            mois_set = {_get_releve_facturation_period(r) for r in releves_valides}
            if len(ouvrage_ids) != 1 or len(mois_set) != 1:
                return JsonResponse({
                    'success': False,
                    'error': "Un encaissement ne peut contenir que des factures d'un seul ouvrage et d'un seul mois",
                }, status=400)

            employe = getattr(request.user, 'employe', None)
            ouvrage = releves_valides[0].point_eau.ouvrage
            montant_total = sum((r.montant for r in releves_valides), Decimal('0'))

            idxls_values = []
            for r in releves_valides:
                v = str(getattr(r.point_eau, 'idxls', '') or '').strip()
                if v and v not in idxls_values:
                    idxls_values.append(v)
            if idxls_values and len(idxls_values) <= 5:
                suffixe = ';'.join(idxls_values)
                detail_diamex = f'IDXLS:{suffixe}'
            else:
                suffixe = f'{len(releves_valides)} releves'
                detail_diamex = f'NB_RELEVES:{len(releves_valides)}'

            description = f'Paiement au volume "{ouvrage.nom_ouvrage}" {date_encaissement.strftime("%d/%m/%Y")} ({suffixe})'
            pers = employe.nom if employe and journal_code == '00PERS' else None
            if pers and len(pers) > 50:
                pers = pers[:50]
            volet = employe.base.volet if employe and employe.base else None
            prog = (employe.base.prog_diamex or employe.base.nom_base) if employe and employe.base else None

            with transaction.atomic():
                ligne = DiameXTemporaire.objects.create(
                    type_transaction='recette',
                    journal_code=journal_code[:50] if journal_code else None,
                    date_rec=date_encaissement,
                    description=description[:255],
                    montant_in=float(montant_total),
                    montant_out=0,
                    compte_code='707401',
                    pers=pers,
                    detail=detail_diamex[:50],
                    activ=volet[:50] if volet else volet,
                    prog=prog[:50] if prog else prog,
                    info='hydria paiement facture au volume (mobile)',
                    statut='en_attente',
                    created_by=employe,
                )
                for r in releves_valides:
                    r.statut = 'paye'
                    r.datepaiement = date_encaissement
                    r.montantpaye = r.montant
                    r.save(update_fields=['statut', 'datepaiement', 'montantpaye'])
            diamex_temporaire_id = str(ligne.id)

        releves_frais = (
            Releve.objects.filter(id__in=ids)
            .select_related('point_eau', 'point_eau__type_point_eau', 'point_eau__ouvrage')
        )
        response = {
            'success': True,
            'local_uuid': local_uuid,
            'factures': [serialize_mobile_facture(r, _mois_facture_str(r)) for r in releves_frais],
        }
        if diamex_temporaire_id:
            response['diamex_temporaire_id'] = diamex_temporaire_id
        return JsonResponse(response)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
